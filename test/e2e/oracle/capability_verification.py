from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from oracle.capability_contract import (
    CapabilityDefinition,
    capability_definition_fingerprint,
)
from oracle.capability_evidence import compute_implementation_fingerprint


DERIVED_GATES = frozenset({"native-powerpoint", "manual-visual", "regression"})
SSIM_REGRESSION_BUDGET = 0.02


class CapabilityVerificationError(ValueError):
    pass


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CapabilityVerificationError(f"{context} must be an object")
    return value


def _sha256(value: Any, context: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CapabilityVerificationError(f"{context} must be a lowercase SHA-256")
    return value


def _finite_metric(value: Any, context: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise CapabilityVerificationError(f"{context} must be finite")
    return float(value)


def _runtime_environment(report: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    provenance = _mapping(report.get("provenance"), f"{case_id} provenance")
    return _mapping(provenance.get("runtime"), f"{case_id} runtime")


def _renderer_state(report: Mapping[str, Any], case_id: str) -> tuple[str, bool]:
    provenance = _mapping(report.get("provenance"), f"{case_id} provenance")
    renderer = _mapping(provenance.get("renderer"), f"{case_id} renderer")
    revision = renderer.get("revision")
    dirty = renderer.get("dirty")
    if not isinstance(revision, str) or len(revision) < 40 or dirty is not False:
        raise CapabilityVerificationError(
            f"{case_id} must come from one clean renderer revision"
        )
    return revision, dirty


def _case_id(report: Mapping[str, Any]) -> str:
    case_id = report.get("testFile")
    if not isinstance(case_id, str) or not case_id:
        raise CapabilityVerificationError("native evaluation report is missing testFile")
    return case_id


def _case_hashes(report: Mapping[str, Any], case_id: str) -> tuple[str, str]:
    provenance = _mapping(report.get("provenance"), f"{case_id} provenance")
    inputs = _mapping(provenance.get("inputs"), f"{case_id} inputs")
    source = _mapping(inputs.get("sourcePptx"), f"{case_id} sourcePptx")
    ground_truth = _mapping(inputs.get("groundTruth"), f"{case_id} groundTruth")
    if ground_truth.get("kind") not in {"pdf", "png"}:
        raise CapabilityVerificationError(f"{case_id} ground truth must be PDF or PNG")
    return (
        _sha256(source.get("sha256"), f"{case_id} source"),
        _sha256(ground_truth.get("combinedSha256"), f"{case_id} ground truth"),
    )


def _case_result(
    report: Mapping[str, Any],
    manual_verdicts: Mapping[str, str],
) -> dict[str, Any]:
    case_id = _case_id(report)
    source_hash, ground_truth_hash = _case_hashes(report, case_id)
    quality = _mapping(report.get("quality"), f"{case_id} quality")
    errors = report.get("evaluationErrors")
    if not isinstance(errors, list):
        raise CapabilityVerificationError(f"{case_id} evaluationErrors must be a list")
    error_count = report.get("evaluationErrorCount")
    if not isinstance(error_count, int) or error_count != len(errors):
        raise CapabilityVerificationError(f"{case_id} evaluation error count is inconsistent")
    mismatch_count = report.get("oracleMismatchCount")
    if not isinstance(mismatch_count, int) or mismatch_count < 0:
        raise CapabilityVerificationError(f"{case_id} oracle mismatch count is invalid")
    needs_review = quality.get("needsReview") is True
    manual_verdict = manual_verdicts.get(case_id)
    if needs_review and manual_verdict not in {"passed", "accepted"}:
        raise CapabilityVerificationError(f"{case_id} requires an explicit passing manual verdict")
    if not needs_review:
        manual_verdict = "not-required"
    passed = (
        report.get("supported") is True
        and quality.get("passed") is True
        and not errors
        and mismatch_count == 0
    )
    return {
        "caseId": case_id,
        "sourceSha256": source_hash,
        "groundTruthSha256": ground_truth_hash,
        "skipped": False,
        "passed": passed,
        "needsReview": needs_review,
        "manualVerdict": manual_verdict,
        "runtimeErrors": list(errors),
        "metrics": {"ssim": _finite_metric(report.get("avgSsim"), f"{case_id} avgSsim")},
    }


def _reports_by_case(
    reports: Sequence[Mapping[str, Any]], context: str
) -> dict[str, Mapping[str, Any]]:
    if not reports:
        raise CapabilityVerificationError(f"{context} requires at least one report")
    by_case: dict[str, Mapping[str, Any]] = {}
    for report in reports:
        if not isinstance(report, Mapping):
            raise CapabilityVerificationError(f"{context} entries must be objects")
        case_id = _case_id(report)
        if case_id in by_case:
            raise CapabilityVerificationError(f"{context} contains duplicate case {case_id}")
        by_case[case_id] = report
    return by_case


def _environment_key(report: Mapping[str, Any], case_id: str) -> str:
    return json.dumps(
        _runtime_environment(report, case_id),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _validate_regression(
    current: Mapping[str, Mapping[str, Any]],
    baseline_reports: Sequence[Mapping[str, Any]],
    current_revision: str,
) -> None:
    baseline = _reports_by_case(baseline_reports, "regression baseline")
    if set(current) != set(baseline):
        raise CapabilityVerificationError("regression baseline case IDs must match current reports")
    baseline_revisions = {
        _renderer_state(report, case_id)[0] for case_id, report in baseline.items()
    }
    if len(baseline_revisions) != 1 or current_revision in baseline_revisions:
        raise CapabilityVerificationError(
            "regression baseline must use one earlier renderer revision"
        )
    for case_id in sorted(current):
        if _case_hashes(current[case_id], case_id) != _case_hashes(baseline[case_id], case_id):
            raise CapabilityVerificationError(
                f"{case_id} regression input hashes must match the current report"
            )
        if _environment_key(current[case_id], case_id) != _environment_key(
            baseline[case_id], case_id
        ):
            raise CapabilityVerificationError(
                f"{case_id} regression runtime environment must match the current report"
            )
        current_ssim = _finite_metric(current[case_id].get("avgSsim"), f"{case_id} current SSIM")
        baseline_ssim = _finite_metric(
            baseline[case_id].get("avgSsim"), f"{case_id} baseline SSIM"
        )
        if baseline_ssim - current_ssim > SSIM_REGRESSION_BUDGET + 1e-12:
            raise CapabilityVerificationError(
                f"{case_id} SSIM regression exceeds {SSIM_REGRESSION_BUDGET:.2f}: "
                f"{baseline_ssim:.4f} -> {current_ssim:.4f}"
            )


def normalize_native_evaluation_reports(
    capability: CapabilityDefinition,
    reports: Sequence[Mapping[str, Any]],
    repo: Path,
    *,
    oracle: str,
    baseline_reports: Sequence[Mapping[str, Any]] = (),
    passed_gates: Iterable[str] = (),
    manual_verdicts: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if oracle not in {"powerpoint-macos", "powerpoint-windows"}:
        raise CapabilityVerificationError(
            "oracle must identify native PowerPoint on macOS or Windows"
        )
    supplied_gates = tuple(passed_gates)
    if len(supplied_gates) != len(set(supplied_gates)):
        raise CapabilityVerificationError("passed gates must be unique")
    unknown_gates = set(supplied_gates) - set(capability.required_gates)
    if unknown_gates:
        raise CapabilityVerificationError(
            f"passed gate is not required by capability: {', '.join(sorted(unknown_gates))}"
        )
    derived = set(supplied_gates) & DERIVED_GATES
    if derived:
        raise CapabilityVerificationError(
            f"derived gate cannot be self-attested: {', '.join(sorted(derived))}"
        )

    current = _reports_by_case(reports, "native verification")
    verdicts = dict(manual_verdicts or {})
    unknown_verdicts = set(verdicts) - set(current)
    if unknown_verdicts:
        raise CapabilityVerificationError(
            f"manual verdict references unknown case: {', '.join(sorted(unknown_verdicts))}"
        )
    revisions = {_renderer_state(report, case_id)[0] for case_id, report in current.items()}
    if len(revisions) != 1:
        raise CapabilityVerificationError("native reports must use one renderer revision")
    runtime_environments = {
        _environment_key(report, case_id) for case_id, report in current.items()
    }
    if len(runtime_environments) != 1:
        raise CapabilityVerificationError("native reports must use one runtime environment")

    case_results = tuple(
        _case_result(current[case_id], verdicts) for case_id in sorted(current)
    )
    required = set(capability.required_gates)
    if "regression" in required:
        _validate_regression(current, baseline_reports, next(iter(revisions)))
    gates = {
        gate: (
            "passed"
            if gate in supplied_gates
            or (gate == "native-powerpoint" and all(case["passed"] for case in case_results))
            or (gate == "manual-visual")
            or (gate == "regression" and baseline_reports)
            else "failed"
            if gate == "native-powerpoint"
            else "missing"
        )
        for gate in capability.required_gates
    }
    first_case = sorted(current)[0]
    runtime = dict(_runtime_environment(current[first_case], first_case))
    environment = {
        "oracle": oracle,
        "platform": runtime.get("platform"),
        "python": runtime.get("python"),
        "browser": runtime.get("browser"),
        "fontProfile": runtime.get("fontProfile"),
    }
    return {
        "schemaVersion": 1,
        "capabilityId": capability.id,
        "definitionFingerprint": capability_definition_fingerprint(capability),
        "renderer": {
            "revision": next(iter(revisions)),
            "dirty": False,
            "implementationFingerprint": compute_implementation_fingerprint(
                repo, capability.implementation_paths
            ),
        },
        "environment": environment,
        "gates": gates,
        "caseResults": list(case_results),
    }
