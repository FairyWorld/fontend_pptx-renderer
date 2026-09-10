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
        "schemaVersion": 6,
        "renderer": dict(case["provenance"]["renderer"]),
        "thresholds": {
            "score": 0.6,
            "cornerScore": 0.78,
            "rangeRatio": 0.85,
            "highlightAmplitudeRatio": 0.8,
            "pictureHighlightAmplitudeRatio": 0.7,
            "shadowAmplitudeRatio": 0.85,
            "shadowOvershootRatio": 1.05,
            "solidDonutShadowOvershootRatio": 1.01,
            "solidDonutShadowEnergyOvershootRatio": 1.05,
        },
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
                "equivalencePairs": [],
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
                                "region": {"preset": "roundRect", "surface": "shape"},
                                "metrics": {
                                    "evaluable": True,
                                    "score": 0.9 if passed else 0.4,
                                    "cornerScore": 0.9 if passed else 0.4,
                                    "cornerRequired": True,
                                    "rangeRatio": 1.0,
                                    "referenceDynamicRange": 80.0,
                                    "candidateDynamicRange": 80.0,
                                    "highlightAmplitudeRatio": 1.0,
                                    "referenceHighlightAmplitude": 35.0,
                                    "candidateHighlightAmplitude": 35.0,
                                    "shadowAmplitudeRatio": 1.0,
                                    "shadowOvershootRatio": 1.0,
                                    "referenceShadowAmplitude": 45.0,
                                    "candidateShadowAmplitude": 45.0,
                                    "referenceShadowEnergy": 12.0,
                                    "candidateShadowEnergy": 12.0,
                                    "shadowEnergyOvershootRatio": 1.0,
                                    "thresholds": {
                                        "score": 0.6,
                                        "cornerScore": 0.78,
                                        "rangeRatio": 0.85,
                                        "highlightAmplitudeRatio": 0.8,
                                        "pictureHighlightAmplitudeRatio": 0.7,
                                        "shadowAmplitudeRatio": 0.85,
                                        "shadowOvershootRatio": 1.05,
                                        "solidDonutShadowOvershootRatio": 1.01,
                                        "solidDonutShadowEnergyOvershootRatio": 1.05,
                                    },
                                    "passed": passed,
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }


def camera_report(
    case: dict,
    repo: Path,
    *,
    passed: bool = True,
    modality: str = "plane",
) -> dict:
    case_id = case["testFile"]
    reports_dir = repo / "test/e2e/reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    reference_path = reports_dir / f"{case_id}_pdf.png"
    candidate_path = reports_dir / f"{case_id}_html.png"
    reference_path.write_bytes(b"native-camera-reference")
    candidate_path.write_bytes(b"renderer-camera-candidate")
    reference_hash = hashlib.sha256(reference_path.read_bytes()).hexdigest()
    candidate_hash = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    artifacts = {
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
    case["perSlide"] = [{"slideIdx": 0, "hidden": False, "renderArtifacts": artifacts}]
    plane_thresholds = {
        "cornerScore": 0.98,
        "colorScore": 0.97,
        "gradientRangeRatio": 0.65,
        "gradientDirection": 0.95,
        "minimumReferenceGradientRange": 4.0,
        "shadowRingInnerRatio": 0.0018,
        "shadowRingOuterRatio": 0.016,
        "shadowBackgroundLevel": 252.0,
        "minimumReferenceShadowDensity": 0.25,
        "shadowEnergyRatio": 0.70,
        "shadowDirectionCosine": 0.95,
    }
    text_thresholds = {
        "rasterToleranceRatio": 0.0025,
        "tolerantForegroundF1": 0.90,
        "tolerantBoundsScore": 0.98,
        "inkCoverageRatio": 0.90,
    }
    picture_thresholds = {
        "cornerScore": 0.98,
        "rectifiedColorScore": 0.95,
        "rectifiedEdgeF1": 0.90,
        "rectifiedSize": 384,
        "edgeToleranceRatio": 0.008,
        "cropMutationRatio": 0.12,
    }
    bottom_material_thresholds = {
        "cornerScore": 0.98,
        "meanBandColorError": 1.0,
        "sourceFlatFill": [68, 114, 196],
    }
    thresholds = {
        "plane": plane_thresholds,
        "text": text_thresholds,
        "picture": picture_thresholds,
        "bottom-material": bottom_material_thresholds,
    }
    if modality == "plane":
        metrics = {
            "evaluable": True,
            "cornerScore": 0.995 if passed else 0.9,
            "meanCornerErrorRatio": 0.005 if passed else 0.1,
            "colorScore": 0.99,
            "gradientRequired": True,
            "referenceGradientRange": 20.0,
            "candidateGradientRange": 18.0,
            "gradientRangeRatio": 0.9,
            "gradientDirection": 1.0,
            "referenceBands": [[1, 2, 3]] * 3,
            "candidateBands": [[1, 2, 3]] * 3,
            "shadowRequired": True,
            "shadowMeasurable": True,
            "referenceShadowDensity": 2.0,
            "candidateShadowDensity": 1.6 if passed else 0.1,
            "shadowEnergyRatio": 0.8 if passed else 0.05,
            "shadowDirectionCosine": 1.0,
            "referenceShadowRingPixels": 500,
            "candidateShadowRingPixels": 500,
            "shadowRingInnerPx": 3,
            "shadowRingOuterPx": 24,
            "shadowPassed": passed,
            "shadowSensitivity": {
                "mutation": "erase-exterior-shadow",
                "applicable": True,
                "mutatedCandidateShadowDensity": 0.0,
                "mutatedShadowEnergyRatio": 0.0,
                "mutatedShadowDirectionCosine": 0.0,
                "mutatedShadowPassed": False,
                "detected": True,
            },
            "thresholds": plane_thresholds,
            "passed": passed,
        }
    elif modality == "bottom-material":
        metrics = {
            "evaluable": True,
            "cornerScore": 0.995 if passed else 0.9,
            "meanCornerErrorRatio": 0.005 if passed else 0.1,
            "referenceBands": [[70, 118, 203]] * 3,
            "candidateBands": ([[70, 118, 203]] * 3 if passed else [[68, 114, 196]] * 3),
            "meanBandColorError": 0.0 if passed else 13 / 3,
            "flatFillSensitivity": {
                "mutation": "restore-source-flat-fill",
                "sourceFlatFill": [68, 114, 196],
                "mutatedBands": [[68, 114, 196]] * 3,
                "mutatedMeanBandColorError": 13 / 3,
                "mutatedPassed": False,
                "detected": True,
            },
            "thresholds": bottom_material_thresholds,
            "passed": passed,
        }
    elif modality == "text":
        metrics = {
            "evaluable": True,
            "foregroundIou": 0.4,
            "boundsScore": 0.995,
            "meanBoundsErrorRatio": 0.005,
            "rasterTolerancePx": 3,
            "referenceCoverageAtTolerance": 0.95 if passed else 0.4,
            "candidateCoverageAtTolerance": 0.95 if passed else 0.4,
            "tolerantForegroundF1": 0.95 if passed else 0.4,
            "tolerantBoundsScore": 0.998,
            "tolerantMeanBoundsErrorRatio": 0.002,
            "inkCoverageRatio": 0.96,
            "referenceInkDensity": 1.5,
            "candidateInkDensity": 1.45,
            "referenceBounds": [10, 20, 100, 80],
            "candidateBounds": [10, 20, 100, 80],
            "thresholds": text_thresholds,
            "passed": passed,
        }
    else:
        reference_edge_coverage = 0.96
        candidate_edge_coverage = 0.94
        mutated_reference_edge_coverage = 0.52
        mutated_candidate_edge_coverage = 0.61
        metrics = {
            "evaluable": True,
            "cornerScore": 0.995 if passed else 0.9,
            "meanCornerErrorRatio": 0.005 if passed else 0.1,
            "rectifiedColorScore": 0.97,
            "rectifiedEdgeF1": (
                2
                * reference_edge_coverage
                * candidate_edge_coverage
                / (reference_edge_coverage + candidate_edge_coverage)
            ),
            "referenceEdgeCoverageAtTolerance": reference_edge_coverage,
            "candidateEdgeCoverageAtTolerance": candidate_edge_coverage,
            "edgeTolerancePx": 3,
            "rectifiedSize": 384,
            "cropSensitivity": {
                "mutation": "left-crop-and-rescale",
                "cropRatio": 0.12,
                "mutatedRectifiedColorScore": 0.91,
                "mutatedRectifiedEdgeF1": (
                    2
                    * mutated_reference_edge_coverage
                    * mutated_candidate_edge_coverage
                    / (
                        mutated_reference_edge_coverage
                        + mutated_candidate_edge_coverage
                    )
                ),
                "mutatedReferenceEdgeCoverageAtTolerance": (
                    mutated_reference_edge_coverage
                ),
                "mutatedCandidateEdgeCoverageAtTolerance": (
                    mutated_candidate_edge_coverage
                ),
                "mutatedPassed": False,
                "detected": True,
            },
            "thresholds": picture_thresholds,
            "passed": passed,
        }
    return {
        "schemaVersion": 5,
        "renderer": dict(case["provenance"]["renderer"]),
        "thresholds": thresholds,
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
                        "modality": modality,
                        "referencePath": artifacts["reference"]["path"],
                        "candidatePath": artifacts["candidate"]["path"],
                        "referenceSha256": reference_hash,
                        "candidateSha256": candidate_hash,
                        "metrics": metrics,
                        "passed": passed,
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


def test_derives_camera_local_gate_from_matching_artifact_evidence(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "camera-local"),
    )
    current = native_report("camera-plane")
    baseline = native_report("camera-plane", revision="b" * 40)

    missing = normalize_native_evaluation_reports(
        capability,
        [current],
        repo,
        oracle="powerpoint-macos",
        baseline_reports=[baseline],
        passed_gates=("source", "structural", "unit", "browser", "docs"),
    )
    assert missing["gates"]["camera-local"] == "missing"

    verified = normalize_native_evaluation_reports(
        capability,
        [current],
        repo,
        oracle="powerpoint-macos",
        baseline_reports=[baseline],
        passed_gates=("source", "structural", "unit", "browser", "docs"),
        camera_report=camera_report(current, repo),
    )
    assert verified["gates"]["camera-local"] == "passed"


def test_derives_camera_local_gate_from_live_text_projection_evidence(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "camera-local"),
    )
    current = native_report("camera-text")
    baseline = native_report("camera-text", revision="b" * 40)

    verified = normalize_native_evaluation_reports(
        capability,
        [current],
        repo,
        oracle="powerpoint-macos",
        baseline_reports=[baseline],
        passed_gates=("source", "structural", "unit", "browser", "docs"),
        camera_report=camera_report(current, repo, modality="text"),
    )

    assert verified["gates"]["camera-local"] == "passed"


def test_derives_camera_local_gate_from_live_picture_projection_evidence(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "camera-local"),
    )
    current = native_report("camera-picture")
    baseline = native_report("camera-picture", revision="b" * 40)

    verified = normalize_native_evaluation_reports(
        capability,
        [current],
        repo,
        oracle="powerpoint-macos",
        baseline_reports=[baseline],
        passed_gates=("source", "structural", "unit", "browser", "docs"),
        camera_report=camera_report(current, repo, modality="picture"),
    )

    assert verified["gates"]["camera-local"] == "passed"


def test_derives_camera_local_gate_from_bottom_bevel_front_material_evidence(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "camera-local"),
    )
    current = native_report("bottom-material")
    baseline = native_report("bottom-material", revision="b" * 40)

    verified = normalize_native_evaluation_reports(
        capability,
        [current],
        repo,
        oracle="powerpoint-macos",
        baseline_reports=[baseline],
        passed_gates=("source", "structural", "unit", "browser", "docs"),
        camera_report=camera_report(current, repo, modality="bottom-material"),
    )

    assert verified["gates"]["camera-local"] == "passed"


def test_rejects_undetected_bottom_bevel_flat_fill_mutation(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "camera-local"),
    )
    current = native_report("bottom-material")
    baseline = native_report("bottom-material", revision="b" * 40)
    report = camera_report(current, repo, modality="bottom-material")
    report["caseResults"][0]["slides"][0]["metrics"]["flatFillSensitivity"][
        "detected"
    ] = False

    with pytest.raises(CapabilityVerificationError, match="flat fill sensitivity"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            camera_report=report,
        )


def test_rejects_failed_or_tampered_camera_local_evidence(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "camera-local"),
    )
    current = native_report("camera-plane")
    baseline = native_report("camera-plane", revision="b" * 40)
    failed = camera_report(current, repo, passed=False)
    with pytest.raises(CapabilityVerificationError, match="camera-local report failed"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            camera_report=failed,
        )

    tampered = camera_report(current, repo)
    (repo / tampered["caseResults"][0]["slides"][0]["candidatePath"]).write_bytes(b"changed")
    with pytest.raises(CapabilityVerificationError, match="artifact hash"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            camera_report=tampered,
        )


def test_rejects_inconsistent_camera_shadow_or_picture_metrics(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "camera-local"),
    )

    plane = native_report("camera-plane")
    plane_baseline = native_report("camera-plane", revision="b" * 40)
    inconsistent_shadow = camera_report(plane, repo)
    inconsistent_shadow["caseResults"][0]["slides"][0]["metrics"][
        "shadowEnergyRatio"
    ] = 0.05
    with pytest.raises(CapabilityVerificationError, match="shadow metrics are inconsistent"):
        normalize_native_evaluation_reports(
            capability,
            [plane],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[plane_baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            camera_report=inconsistent_shadow,
        )

    materially_weak_shadow = camera_report(plane, repo)
    materially_weak_shadow["caseResults"][0]["slides"][0]["metrics"].update(
        shadowEnergyRatio=0.5,
        shadowPassed=True,
        passed=True,
    )
    with pytest.raises(CapabilityVerificationError, match="shadow metrics are inconsistent"):
        normalize_native_evaluation_reports(
            capability,
            [plane],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[plane_baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            camera_report=materially_weak_shadow,
        )

    undetected_shadow = camera_report(plane, repo)
    undetected_shadow["caseResults"][0]["slides"][0]["metrics"][
        "shadowSensitivity"
    ]["detected"] = False
    with pytest.raises(CapabilityVerificationError, match="shadow sensitivity is inconsistent"):
        normalize_native_evaluation_reports(
            capability,
            [plane],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[plane_baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            camera_report=undetected_shadow,
        )

    picture = native_report("camera-picture")
    picture_baseline = native_report("camera-picture", revision="b" * 40)
    inconsistent_picture = camera_report(picture, repo, modality="picture")
    inconsistent_picture["caseResults"][0]["slides"][0]["metrics"][
        "rectifiedEdgeF1"
    ] = 0.5
    with pytest.raises(CapabilityVerificationError, match="picture edge metrics are inconsistent"):
        normalize_native_evaluation_reports(
            capability,
            [picture],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[picture_baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            camera_report=inconsistent_picture,
        )

    undetected_crop = camera_report(picture, repo, modality="picture")
    undetected_crop["caseResults"][0]["slides"][0]["metrics"]["cropSensitivity"][
        "detected"
    ] = False
    with pytest.raises(CapabilityVerificationError, match="crop sensitivity is inconsistent"):
        normalize_native_evaluation_reports(
            capability,
            [picture],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[picture_baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            camera_report=undetected_crop,
        )


def test_rejects_inconsistent_camera_text_metrics_or_thresholds(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "camera-local"),
    )
    current = native_report("camera-text")
    baseline = native_report("camera-text", revision="b" * 40)

    inconsistent = camera_report(current, repo, modality="text")
    inconsistent["caseResults"][0]["slides"][0]["metrics"][
        "tolerantForegroundF1"
    ] = 1.0
    with pytest.raises(CapabilityVerificationError, match="tolerant metrics are inconsistent"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            camera_report=inconsistent,
        )

    threshold_drift = camera_report(current, repo, modality="text")
    threshold_drift["thresholds"]["text"]["tolerantForegroundF1"] = 0.1
    with pytest.raises(CapabilityVerificationError, match="unexpected thresholds"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            camera_report=threshold_drift,
        )


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

    overdark = bevel_report(current, repo)
    metrics = overdark["caseResults"][0]["slides"][0]["regions"][0]["metrics"]
    metrics.update(
        candidateDynamicRange=120.0,
        rangeRatio=80.0 / 120.0,
        candidateShadowAmplitude=90.0,
        shadowAmplitudeRatio=0.5,
        shadowOvershootRatio=2.0,
    )

    with pytest.raises(CapabilityVerificationError, match="metric pass status"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            bevel_report=overdark,
        )

    visible_overshoot = bevel_report(current, repo)
    metrics = visible_overshoot["caseResults"][0]["slides"][0]["regions"][0]["metrics"]
    metrics.update(
        candidateDynamicRange=82.7,
        rangeRatio=80.0 / 82.7,
        candidateShadowAmplitude=47.7,
        shadowAmplitudeRatio=45.0 / 47.7,
        shadowOvershootRatio=47.7 / 45.0,
    )

    with pytest.raises(CapabilityVerificationError, match="metric pass status"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            bevel_report=visible_overshoot,
        )

    donut_overshoot = bevel_report(current, repo)
    region = donut_overshoot["caseResults"][0]["slides"][0]["regions"][0]
    region["region"]["preset"] = "donut"
    metrics = region["metrics"]
    metrics.update(
        candidateDynamicRange=80.675,
        rangeRatio=80.0 / 80.675,
        candidateShadowAmplitude=45.675,
        shadowAmplitudeRatio=45.0 / 45.675,
        shadowOvershootRatio=45.675 / 45.0,
    )

    with pytest.raises(CapabilityVerificationError, match="metric pass status"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            bevel_report=donut_overshoot,
        )

    donut_energy_overshoot = bevel_report(current, repo)
    region = donut_energy_overshoot["caseResults"][0]["slides"][0]["regions"][0]
    region["region"]["preset"] = "donut"
    metrics = region["metrics"]
    metrics.update(
        referenceShadowEnergy=12.0,
        candidateShadowEnergy=12.72,
        shadowEnergyOvershootRatio=1.06,
    )

    with pytest.raises(CapabilityVerificationError, match="metric pass status"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            bevel_report=donut_energy_overshoot,
        )


def test_rejects_inconsistent_bevel_equivalence_evidence(tmp_path: Path):
    repo, base_capability = capability_fixture(tmp_path)
    capability = replace(
        base_capability,
        required_gates=(*base_capability.required_gates, "bevel-local"),
    )
    current = native_report("default-bevel-pair")
    baseline = native_report("default-bevel-pair", revision="b" * 40)
    evidence = bevel_report(current, repo)
    native_slide = current["perSlide"][0]
    second_native_slide = {
        **native_slide,
        "slideIdx": 1,
    }
    current["perSlide"].append(second_native_slide)
    evidence_slide = evidence["caseResults"][0]["slides"][0]
    evidence["caseResults"][0]["slides"].append(
        {
            **evidence_slide,
            "slideIdx": 1,
        }
    )
    evidence["caseResults"][0]["equivalencePairs"] = [
        {
            "leftSlideIdx": 0,
            "rightSlideIdx": 1,
            "referenceEqual": False,
            "candidateEqual": True,
            "passed": False,
        }
    ]
    evidence["caseResults"][0]["passed"] = False
    evidence["passed"] = False

    with pytest.raises(CapabilityVerificationError, match="equivalence evidence is inconsistent"):
        normalize_native_evaluation_reports(
            capability,
            [current],
            repo,
            oracle="powerpoint-macos",
            baseline_reports=[baseline],
            passed_gates=("source", "structural", "unit", "browser", "docs"),
            bevel_report=evidence,
        )
