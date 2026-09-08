import json
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
