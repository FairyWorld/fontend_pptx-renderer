import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from oracle.capability_contract import load_capability_registry
from oracle.capability_evidence import compute_implementation_fingerprint
from oracle.capability_verification import (
    CapabilityVerificationError,
    normalize_native_evaluation_reports,
)


def capability_fixture(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/renderer.ts").write_text("renderer", encoding="utf-8")
    registry_path = repo / "capabilities.json"
    registry_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "capabilities": [
                    {
                        "id": "drawingml.shape.geometry.adjustment.donut",
                        "component": "shape",
                        "renderMode": "native",
                        "impact": "fidelity",
                        "selectors": [],
                        "scope": {"presets": ["donut"]},
                        "fallback": "Use the handwritten geometry.",
                        "implementationPaths": ["src/renderer.ts"],
                        "requiredGates": [
                            "source",
                            "structural",
                            "unit",
                            "browser",
                            "native-powerpoint",
                            "manual-visual",
                            "regression",
                            "docs",
                        ],
                        "issueUrls": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    capability = load_capability_registry(registry_path).capabilities[0]
    return repo, capability


def native_report(
    case_id: str,
    *,
    revision: str = "a" * 40,
    dirty: bool = False,
    ssim: float = 0.99,
    needs_review: bool = False,
) -> dict:
    suffix = "1" if case_id.endswith("thin") else "2"
    return {
        "testFile": case_id,
        "evaluationErrorCount": 0,
        "evaluationErrors": [],
        "oracleMismatchCount": 0,
        "avgSsim": ssim,
        "supported": True,
        "quality": {"passed": True, "needsReview": needs_review},
        "provenance": {
            "inputs": {
                "sourcePptx": {"sha256": suffix * 64},
                "groundTruth": {"kind": "png", "combinedSha256": ("f" + suffix) * 32},
            },
            "renderer": {"revision": revision, "dirty": dirty},
            "runtime": {
                "platform": "macOS-test",
                "python": "3.11.11",
                "browser": {"name": "chrome", "version": "152"},
                "fontProfile": None,
            },
        },
    }


def bevel_report(case: dict, repo: Path, *, passed: bool = True) -> dict:
    case_id = case["testFile"]
    reports_dir = repo / "test/e2e/reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    reference_path = reports_dir / f"{case_id}_pdf.png"
    candidate_path = reports_dir / f"{case_id}_html.png"
    reference_path.write_bytes(b"native-reference")
    candidate_path.write_bytes(b"renderer-candidate")
    reference_hash = hashlib.sha256(reference_path.read_bytes()).hexdigest()
    candidate_hash = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    native_artifacts = {
        "reference": {
            "path": reference_path.relative_to(repo).as_posix(),
            "sizeBytes": reference_path.stat().st_size,
            "sha256": reference_hash,
        },
        "candidate": {
            "path": candidate_path.relative_to(repo).as_posix(),
            "sizeBytes": candidate_path.stat().st_size,
            "sha256": candidate_hash,
        },
    }
    case["perSlide"] = [
        {"slideIdx": 0, "hidden": False, "renderArtifacts": native_artifacts}
    ]
    return {
        "schemaVersion": 1,
        "renderer": dict(case["provenance"]["renderer"]),
        "thresholds": {"score": 0.6, "cornerScore": 0.78},
        "applicableCaseCount": 1,
        "passed": passed,
        "caseResults": [
            {
                "caseId": case_id,
                "sourceSha256": case["provenance"]["inputs"]["sourcePptx"]["sha256"],
                "groundTruthSha256": case["provenance"]["inputs"]["groundTruth"][
                    "combinedSha256"
                ],
                "applicable": True,
                "passed": passed,
                "slides": [
                    {
                        "slideIdx": 0,
                        "referencePath": native_artifacts["reference"]["path"],
                        "candidatePath": native_artifacts["candidate"]["path"],
                        "referenceSha256": reference_hash,
                        "candidateSha256": candidate_hash,
                        "passed": passed,
                        "regions": [
                            {
                                "region": {"preset": "roundRect"},
                                "metrics": {
                                    "evaluable": True,
                                    "score": 0.9 if passed else 0.4,
                                    "cornerScore": 0.9 if passed else 0.4,
                                    "cornerRequired": True,
                                    "thresholds": {"score": 0.6, "cornerScore": 0.78},
                                    "passed": passed,
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_normalizes_native_reports_into_promotion_evidence(tmp_path: Path):
    repo, capability = capability_fixture(tmp_path)
    current = [native_report("donut-thin"), native_report("donut-thick")]
    baseline = [
        native_report("donut-thin", revision="b" * 40, ssim=0.98),
        native_report("donut-thick", revision="b" * 40, ssim=0.985),
    ]

    verification = normalize_native_evaluation_reports(
        capability,
        current,
        repo,
        oracle="powerpoint-macos",
        baseline_reports=baseline,
        passed_gates=("source", "structural", "unit", "browser", "docs"),
    )

    assert verification["renderer"] == {
        "revision": "a" * 40,
        "dirty": False,
        "implementationFingerprint": compute_implementation_fingerprint(
            repo, capability.implementation_paths
        ),
    }
    assert set(verification["gates"].values()) == {"passed"}
    assert [case["caseId"] for case in verification["caseResults"]] == [
        "donut-thick",
        "donut-thin",
    ]
    assert all(case["manualVerdict"] == "not-required" for case in verification["caseResults"])
    assert verification["environment"]["oracle"] == "powerpoint-macos"
    assert verification["environment"]["browser"] == {"name": "chrome", "version": "152"}


def test_rejects_regression_beyond_the_ssim_budget(tmp_path: Path):
    repo, capability = capability_fixture(tmp_path)

    with pytest.raises(CapabilityVerificationError, match="SSIM regression"):
        normalize_native_evaluation_reports(
            capability,
            [native_report("donut-thin", ssim=0.95)],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[native_report("donut-thin", revision="b" * 40, ssim=0.98)],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
        )


def test_rejects_incomparable_regression_baselines(tmp_path: Path):
    repo, capability = capability_fixture(tmp_path)
    current = [native_report("donut-thin")]
    same_revision = [native_report("donut-thin")]

    with pytest.raises(CapabilityVerificationError, match="earlier renderer revision"):
        normalize_native_evaluation_reports(
            capability,
            current,
            repo,
            oracle="powerpoint-macos",
            baseline_reports=same_revision,
            passed_gates=("source", "structural", "unit", "browser", "docs"),
        )

    changed_input = native_report("donut-thin", revision="b" * 40)
    changed_input["provenance"]["inputs"]["sourcePptx"]["sha256"] = "e" * 64
    with pytest.raises(CapabilityVerificationError, match="input hashes must match"):
        normalize_native_evaluation_reports(
            capability,
            current,
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[changed_input],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
        )


def test_requires_explicit_verdict_for_a_review_row(tmp_path: Path):
    repo, capability = capability_fixture(tmp_path)
    current = [native_report("donut-thin", needs_review=True)]
    baseline = [native_report("donut-thin", revision="b" * 40)]

    with pytest.raises(CapabilityVerificationError, match="manual verdict"):
        normalize_native_evaluation_reports(
            capability,
            current,
            repo,
            oracle="powerpoint-macos",
            baseline_reports=baseline,
            passed_gates=("source", "structural", "unit", "browser", "docs"),
        )

    verification = normalize_native_evaluation_reports(
        capability,
        current,
        repo,
        oracle="powerpoint-macos",
        baseline_reports=baseline,
        passed_gates=("source", "structural", "unit", "browser", "docs"),
        manual_verdicts={"donut-thin": "passed"},
    )
    assert verification["caseResults"][0]["manualVerdict"] == "passed"


def test_rejects_dirty_or_mixed_revision_reports(tmp_path: Path):
    repo, capability = capability_fixture(tmp_path)
    baseline = [native_report("donut-thin", revision="b" * 40)]

    with pytest.raises(CapabilityVerificationError, match="clean renderer revision"):
        normalize_native_evaluation_reports(
            capability,
            [native_report("donut-thin", dirty=True)],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=baseline,
            passed_gates=("source", "structural", "unit", "browser", "docs"),
        )

    with pytest.raises(CapabilityVerificationError, match="one renderer revision"):
        normalize_native_evaluation_reports(
            capability,
            [
                native_report("donut-thin"),
                native_report("donut-thick", revision="c" * 40),
            ],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[
                native_report("donut-thin", revision="b" * 40),
                native_report("donut-thick", revision="b" * 40),
            ],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
        )


def test_does_not_allow_callers_to_self_attest_derived_gates(tmp_path: Path):
    repo, capability = capability_fixture(tmp_path)

    with pytest.raises(CapabilityVerificationError, match="derived gate"):
        normalize_native_evaluation_reports(
            capability,
            [native_report("donut-thin")],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[native_report("donut-thin", revision="b" * 40)],
            passed_gates=("native-powerpoint",),
        )


def test_derives_bevel_local_gate_from_matching_artifact_evidence(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "bevel-local"),
    )
    current = native_report("donut-thin")
    baseline = native_report("donut-thin", revision="b" * 40)

    missing = normalize_native_evaluation_reports(
        capability,
        [current],
        repo,
        oracle="powerpoint-macos",
        baseline_reports=[baseline],
        passed_gates=("source", "structural", "unit", "browser", "docs"),
    )
    assert missing["gates"]["bevel-local"] == "missing"

    verified = normalize_native_evaluation_reports(
        capability,
        [current],
        repo,
        oracle="powerpoint-macos",
        baseline_reports=[baseline],
        passed_gates=("source", "structural", "unit", "browser", "docs"),
        bevel_report=bevel_report(current, repo),
    )
    assert verified["gates"]["bevel-local"] == "passed"


def test_rejects_bevel_local_evidence_for_different_inputs_or_failed_metrics(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "bevel-local"),
    )
    current = native_report("donut-thin")
    baseline = native_report("donut-thin", revision="b" * 40)
    wrong_input = bevel_report(current, repo)
    wrong_input["caseResults"][0]["sourceSha256"] = "e" * 64

    with pytest.raises(CapabilityVerificationError, match="input hashes"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            bevel_report=wrong_input,
        )

    with pytest.raises(CapabilityVerificationError, match="bevel-local report failed"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            bevel_report=bevel_report(current, repo, passed=False),
        )


def test_rejects_tampered_bevel_artifacts_and_inconsistent_metric_results(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "bevel-local"),
    )
    current = native_report("donut-thin")
    baseline = native_report("donut-thin", revision="b" * 40)
    tampered = bevel_report(current, repo)
    candidate_path = repo / tampered["caseResults"][0]["slides"][0]["candidatePath"]
    candidate_path.write_bytes(b"changed-after-metric")

    with pytest.raises(CapabilityVerificationError, match="artifact hash"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            bevel_report=tampered,
        )

    mismatched_native = bevel_report(current, repo)
    current["perSlide"][0]["renderArtifacts"]["candidate"]["sha256"] = "0" * 64
    with pytest.raises(CapabilityVerificationError, match="native report artifacts"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            bevel_report=mismatched_native,
        )

    inconsistent = bevel_report(current, repo)
    metrics = inconsistent["caseResults"][0]["slides"][0]["regions"][0]["metrics"]
    metrics["score"] = 0.2

    with pytest.raises(CapabilityVerificationError, match="metric pass status"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            bevel_report=inconsistent,
        )
