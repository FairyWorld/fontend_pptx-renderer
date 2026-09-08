from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from oracle.capability_contract import (
    CapabilityDefinition,
    PromotionReceipt,
    capability_definition_fingerprint,
)


_SHA256_LENGTH = 64


class CapabilityEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceState:
    name: str
    reasons: tuple[str, ...]


def _validate_relative_pattern(pattern: str) -> None:
    if not pattern or "\x00" in pattern or "\\" in pattern:
        raise CapabilityEvidenceError(f"implementation path must be repository-relative: {pattern}")
    path = PurePosixPath(pattern)
    if path.is_absolute() or ".." in path.parts:
        raise CapabilityEvidenceError(f"implementation path must be repository-relative: {pattern}")


def _expand_implementation_paths(repo: Path, patterns: Iterable[str]) -> tuple[Path, ...]:
    root = repo.resolve()
    paths: dict[str, Path] = {}
    for pattern in patterns:
        _validate_relative_pattern(pattern)
        matches = sorted(path for path in repo.glob(pattern) if path.is_file())
        if not matches:
            raise CapabilityEvidenceError(f"implementation path has no file matches: {pattern}")
        for path in matches:
            resolved = path.resolve()
            try:
                relative = resolved.relative_to(root).as_posix()
            except ValueError as error:
                raise CapabilityEvidenceError(
                    f"implementation path resolves outside repository: {pattern}"
                ) from error
            paths[relative] = resolved
    return tuple(paths[name] for name in sorted(paths))


def compute_implementation_fingerprint(repo: Path, patterns: Iterable[str]) -> str:
    repo = Path(repo)
    root = repo.resolve()
    digest = hashlib.sha256()
    for path in _expand_implementation_paths(repo, patterns):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != _SHA256_LENGTH:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _report_mapping(report: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = report.get(key)
    return value if isinstance(value, Mapping) else {}


def _report_cases(report: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    value = report.get("caseResults")
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _case_fingerprints(
    cases: tuple[Mapping[str, Any], ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    case_ids: list[str] = []
    source_hashes: list[str] = []
    ground_truth_hashes: list[str] = []
    for case in cases:
        case_id = case.get("caseId")
        source_hash = case.get("sourceSha256")
        ground_truth_hash = case.get("groundTruthSha256")
        if (
            not isinstance(case_id, str)
            or not case_id
            or not _is_sha256(source_hash)
            or not _is_sha256(ground_truth_hash)
        ):
            return None
        case_ids.append(case_id)
        source_hashes.append(source_hash)
        ground_truth_hashes.append(ground_truth_hash)
    if not case_ids or len(case_ids) != len(set(case_ids)):
        return None
    return tuple(case_ids), tuple(source_hashes), tuple(ground_truth_hashes)


def _verification_reasons(
    capability: CapabilityDefinition,
    report: Mapping[str, Any],
    current_fingerprint: str,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if report.get("schemaVersion") != 1:
        return ("evidence:unsupported-schema",)
    if report.get("capabilityId") != capability.id:
        return ("evidence:capability-id-mismatch",)
    if report.get("definitionFingerprint") != capability_definition_fingerprint(capability):
        reasons.append("evidence:definition-fingerprint-drift")

    renderer = _report_mapping(report, "renderer")
    if renderer.get("implementationFingerprint") != current_fingerprint:
        reasons.append("evidence:implementation-fingerprint-drift")
    if renderer.get("dirty") is not False:
        reasons.append("evidence:dirty-worktree")
    revision = renderer.get("revision")
    if not isinstance(revision, str) or len(revision) < 40:
        reasons.append("evidence:missing-renderer-revision")

    gates = _report_mapping(report, "gates")
    for gate in capability.required_gates:
        status = gates.get(gate)
        if status != "passed":
            reasons.append(f"gate:{gate}:{status if isinstance(status, str) else 'missing'}")

    cases = _report_cases(report)
    for case in cases:
        case_id = case.get("caseId") if isinstance(case.get("caseId"), str) else "unknown"
        if case.get("skipped") is True:
            reasons.append("evidence:skipped-required-case")
        if case.get("passed") is not True:
            reasons.append(f"case:{case_id}:failed")
        runtime_errors = case.get("runtimeErrors")
        if not isinstance(runtime_errors, list) or runtime_errors:
            reasons.append(f"case:{case_id}:runtime-error")
        if case.get("needsReview") is True and case.get("manualVerdict") not in {
            "passed",
            "accepted",
        }:
            reasons.append("evidence:manual-review-required")
    return tuple(dict.fromkeys(reasons))


def evaluate_evidence_state(
    capability: CapabilityDefinition,
    receipt: PromotionReceipt | None,
    report: Mapping[str, Any] | None,
    repo: Path,
) -> EvidenceState:
    current_fingerprint = compute_implementation_fingerprint(repo, capability.implementation_paths)
    definition_fingerprint = capability_definition_fingerprint(capability)
    if receipt is not None:
        if receipt.capability_id != capability.id:
            return EvidenceState("regressed", ("evidence:receipt-capability-id-mismatch",))
        if receipt.definition_fingerprint != definition_fingerprint:
            return EvidenceState("regressed", ("evidence:definition-fingerprint-drift",))
        if receipt.implementation_fingerprint != current_fingerprint:
            return EvidenceState("regressed", ("evidence:implementation-fingerprint-drift",))

    if report is None:
        if receipt is not None:
            return EvidenceState("verified", ())
        return EvidenceState("unknown", ("evidence:no-verification-report",))

    cases = _report_cases(report)
    fingerprints = _case_fingerprints(cases)
    if fingerprints is None:
        return EvidenceState("reproducible", ("evidence:missing-input-hash",))

    reasons = list(_verification_reasons(capability, report, current_fingerprint))
    if receipt is not None:
        case_ids, source_hashes, ground_truth_hashes = fingerprints
        if receipt.case_ids != case_ids:
            reasons.append("evidence:case-id-drift")
        if receipt.case_input_fingerprints != source_hashes:
            reasons.append("evidence:case-input-fingerprint-drift")
        if receipt.ground_truth_fingerprints != ground_truth_hashes:
            reasons.append("evidence:ground-truth-fingerprint-drift")
        if reasons:
            return EvidenceState("regressed", tuple(dict.fromkeys(reasons)))
        return EvidenceState("verified", ())

    reasons.append("evidence:missing-promotion-receipt")
    return EvidenceState("candidate", tuple(dict.fromkeys(reasons)))


def build_promotion_receipt(
    capability: CapabilityDefinition,
    report: Mapping[str, Any],
    repo: Path,
    accepted_at: str,
) -> PromotionReceipt:
    current_fingerprint = compute_implementation_fingerprint(repo, capability.implementation_paths)
    reasons = list(_verification_reasons(capability, report, current_fingerprint))
    cases = _report_cases(report)
    fingerprints = _case_fingerprints(cases)
    if fingerprints is None:
        reasons.append("evidence:missing-input-hash")
    if reasons:
        raise CapabilityEvidenceError(
            "cannot promote capability: " + ", ".join(dict.fromkeys(reasons))
        )
    renderer = _report_mapping(report, "renderer")
    revision = renderer["revision"]
    case_ids, source_hashes, ground_truth_hashes = fingerprints
    environment = report.get("environment")
    if not isinstance(environment, Mapping) or not environment:
        raise CapabilityEvidenceError("cannot promote capability: evidence:missing-environment")
    gates = _report_mapping(report, "gates")
    passed_gates = tuple(gate for gate in capability.required_gates if gates.get(gate) == "passed")
    return PromotionReceipt(
        capability_id=capability.id,
        definition_fingerprint=capability_definition_fingerprint(capability),
        accepted_revision=revision,
        implementation_fingerprint=current_fingerprint,
        case_ids=case_ids,
        case_input_fingerprints=source_hashes,
        ground_truth_fingerprints=ground_truth_hashes,
        gates=passed_gates,
        environment=dict(environment),
        accepted_at=accepted_at,
    )


def _sanitize_value(value: Any, key: str = "") -> Any:
    normalized_key = key.lower()
    if any(token in normalized_key for token in ("path", "username", "issuebody", "caselabel")):
        return None
    if isinstance(value, Mapping):
        result = {}
        for child_key, child_value in sorted(value.items()):
            if not isinstance(child_key, str):
                continue
            sanitized = _sanitize_value(child_value, child_key)
            if sanitized is not None:
                result[child_key] = sanitized
        return result
    if isinstance(value, (list, tuple)):
        return [item for item in (_sanitize_value(item, key) for item in value) if item is not None]
    if isinstance(value, str):
        if (
            value.startswith(("/", "~", "\\\\", "file://"))
            or re.match(r"^[A-Za-z]:[\\/]", value)
            or "/Users/" in value
            or "/home/" in value
        ):
            return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def sanitize_receipt_for_tracking(receipt: PromotionReceipt) -> dict[str, Any]:
    environment = _sanitize_value(receipt.environment)
    if not isinstance(environment, dict) or not environment:
        raise CapabilityEvidenceError("sanitized promotion environment must not be empty")
    payload = {
        "capabilityId": receipt.capability_id,
        "definitionFingerprint": receipt.definition_fingerprint,
        "acceptedRevision": receipt.accepted_revision,
        "implementationFingerprint": receipt.implementation_fingerprint,
        "caseIds": list(receipt.case_ids),
        "caseInputFingerprints": list(receipt.case_input_fingerprints),
        "groundTruthFingerprints": list(receipt.ground_truth_fingerprints),
        "gates": list(receipt.gates),
        "environment": environment,
        "acceptedAt": receipt.accepted_at,
    }
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload
