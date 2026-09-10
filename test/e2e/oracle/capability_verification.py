from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from oracle.capability_contract import (
    CapabilityDefinition,
    capability_definition_fingerprint,
)
from oracle.capability_evidence import compute_implementation_fingerprint


DERIVED_GATES = frozenset(
    {"native-powerpoint", "manual-visual", "regression", "bevel-local", "camera-local"}
)
SSIM_REGRESSION_BUDGET = 0.02
BEVEL_SCORE_THRESHOLD = 0.60
BEVEL_CORNER_SCORE_THRESHOLD = 0.78
BEVEL_MINIMUM_BAND_WIDTH_PX = 4.0
CAMERA_CORNER_SCORE_THRESHOLD = 0.98
CAMERA_COLOR_SCORE_THRESHOLD = 0.97
CAMERA_GRADIENT_RANGE_RATIO_THRESHOLD = 0.65
CAMERA_GRADIENT_DIRECTION_THRESHOLD = 0.95
CAMERA_MINIMUM_REFERENCE_GRADIENT_RANGE = 4.0
CAMERA_TEXT_RASTER_TOLERANCE_RATIO = 0.0025
CAMERA_TEXT_TOLERANT_FOREGROUND_F1_THRESHOLD = 0.90
CAMERA_TEXT_TOLERANT_BOUNDS_SCORE_THRESHOLD = 0.98
CAMERA_TEXT_INK_COVERAGE_RATIO_THRESHOLD = 0.90
CAMERA_SHADOW_RING_INNER_RATIO = 0.0018
CAMERA_SHADOW_RING_OUTER_RATIO = 0.016
CAMERA_SHADOW_BACKGROUND_LEVEL = 252.0
CAMERA_MINIMUM_REFERENCE_SHADOW_DENSITY = 0.25
CAMERA_SHADOW_ENERGY_RATIO_THRESHOLD = 0.70
CAMERA_SHADOW_DIRECTION_THRESHOLD = 0.95
CAMERA_PICTURE_CORNER_SCORE_THRESHOLD = 0.98
CAMERA_PICTURE_RECTIFIED_COLOR_SCORE_THRESHOLD = 0.95
CAMERA_PICTURE_RECTIFIED_EDGE_F1_THRESHOLD = 0.90
CAMERA_PICTURE_RECTIFIED_SIZE = 384
CAMERA_PICTURE_EDGE_TOLERANCE_RATIO = 0.008
CAMERA_PICTURE_CROP_MUTATION_RATIO = 0.12


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


def _validate_bevel_local(
    report: Mapping[str, Any],
    current: Mapping[str, Mapping[str, Any]],
    current_revision: str,
    repo: Path,
) -> None:
    if report.get("schemaVersion") != 1:
        raise CapabilityVerificationError("bevel-local report requires schemaVersion=1")
    renderer = _mapping(report.get("renderer"), "bevel-local renderer")
    if renderer.get("revision") != current_revision or renderer.get("dirty") is not False:
        raise CapabilityVerificationError(
            "bevel-local report must match the clean native-report revision"
        )
    thresholds = _mapping(report.get("thresholds"), "bevel-local thresholds")
    if thresholds != {
        "score": BEVEL_SCORE_THRESHOLD,
        "cornerScore": BEVEL_CORNER_SCORE_THRESHOLD,
    }:
        raise CapabilityVerificationError("bevel-local report uses unexpected thresholds")
    values = report.get("caseResults")
    if not isinstance(values, list) or any(not isinstance(value, Mapping) for value in values):
        raise CapabilityVerificationError("bevel-local caseResults must be a list of objects")
    by_case: dict[str, Mapping[str, Any]] = {}
    for value in values:
        case_id = value.get("caseId")
        if not isinstance(case_id, str) or not case_id or case_id in by_case:
            raise CapabilityVerificationError("bevel-local case IDs must be unique strings")
        by_case[case_id] = value
    if set(by_case) != set(current):
        raise CapabilityVerificationError("bevel-local case IDs must match native reports")
    applicable_count = 0
    all_cases_passed = True
    for case_id, value in by_case.items():
        source_hash, ground_truth_hash = _case_hashes(current[case_id], case_id)
        if value.get("sourceSha256") != source_hash or value.get(
            "groundTruthSha256"
        ) != ground_truth_hash:
            raise CapabilityVerificationError(
                f"{case_id} bevel-local input hashes must match native reports"
            )
        slides = value.get("slides")
        if not isinstance(slides, list) or any(not isinstance(slide, Mapping) for slide in slides):
            raise CapabilityVerificationError(f"{case_id} bevel-local slides must be objects")
        native_slide_values = current[case_id].get("perSlide")
        if not isinstance(native_slide_values, list) or any(
            not isinstance(slide, Mapping) for slide in native_slide_values
        ):
            raise CapabilityVerificationError(
                f"{case_id} native report is missing per-slide artifacts"
            )
        native_slides = {
            slide.get("slideIdx"): slide
            for slide in native_slide_values
            if isinstance(slide.get("slideIdx"), int) and slide.get("hidden") is not True
        }
        evaluable_regions = 0
        slide_passes: list[bool] = []
        for slide_index, slide in enumerate(slides):
            context = f"{case_id} bevel-local slide {slide_index}"
            if not isinstance(slide.get("slideIdx"), int) or slide.get("slideIdx") < 0:
                raise CapabilityVerificationError(f"{context} index is invalid")
            native_slide = native_slides.get(slide.get("slideIdx"))
            if native_slide is None:
                raise CapabilityVerificationError(f"{context} is absent from the native report")
            native_artifacts = _mapping(
                native_slide.get("renderArtifacts"), f"{context} native render artifacts"
            )
            for kind in ("reference", "candidate"):
                path_value = slide.get(f"{kind}Path")
                expected_hash = _sha256(slide.get(f"{kind}Sha256"), f"{context} {kind}")
                native_artifact = _mapping(
                    native_artifacts.get(kind), f"{context} native {kind} artifact"
                )
                if (
                    native_artifact.get("path") != path_value
                    or native_artifact.get("sha256") != expected_hash
                ):
                    raise CapabilityVerificationError(
                        f"{context} does not match native report artifacts"
                    )
                if not isinstance(path_value, str) or "\\" in path_value:
                    raise CapabilityVerificationError(f"{context} {kind} path is invalid")
                relative = PurePosixPath(path_value)
                if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
                    raise CapabilityVerificationError(f"{context} {kind} path is invalid")
                artifact = (repo / relative.as_posix()).resolve()
                try:
                    artifact.relative_to(repo.resolve())
                except ValueError as error:
                    raise CapabilityVerificationError(
                        f"{context} {kind} path escapes the repository"
                    ) from error
                if not artifact.is_file():
                    raise CapabilityVerificationError(f"{context} {kind} artifact is missing")
                digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
                if digest != expected_hash:
                    raise CapabilityVerificationError(f"{context} {kind} artifact hash changed")
            regions = slide.get("regions")
            if not isinstance(regions, list) or not regions or any(
                not isinstance(region, Mapping) for region in regions
            ):
                raise CapabilityVerificationError(f"{context} regions must be non-empty objects")
            region_passes: list[bool] = []
            for region_index, region in enumerate(regions):
                metric_context = f"{context} region {region_index}"
                _mapping(region.get("region"), f"{metric_context} geometry")
                metrics = _mapping(region.get("metrics"), f"{metric_context} metrics")
                evaluable = metrics.get("evaluable")
                if not isinstance(evaluable, bool):
                    raise CapabilityVerificationError(f"{metric_context} evaluable is invalid")
                if not isinstance(metrics.get("passed"), bool):
                    raise CapabilityVerificationError(f"{metric_context} pass status is invalid")
                metric_thresholds = _mapping(
                    metrics.get("thresholds"), f"{metric_context} thresholds"
                )
                if evaluable:
                    evaluable_regions += 1
                    score = _finite_metric(metrics.get("score"), f"{metric_context} score")
                    corner_required = metrics.get("cornerRequired")
                    if not isinstance(corner_required, bool):
                        raise CapabilityVerificationError(
                            f"{metric_context} corner requirement is invalid"
                        )
                    corner_score = _finite_metric(
                        metrics.get("cornerScore"), f"{metric_context} corner score"
                    )
                    if metric_thresholds != thresholds:
                        raise CapabilityVerificationError(
                            f"{metric_context} uses unexpected thresholds"
                        )
                    expected_pass = score >= BEVEL_SCORE_THRESHOLD and (
                        not corner_required or corner_score >= BEVEL_CORNER_SCORE_THRESHOLD
                    )
                else:
                    if metrics.get("reason") != "bevel-band-below-resolution-floor":
                        raise CapabilityVerificationError(
                            f"{metric_context} has an unknown unevaluable reason"
                        )
                    band_width = _finite_metric(
                        metrics.get("bandWidthPx"), f"{metric_context} band width"
                    )
                    expected_thresholds = {
                        **thresholds,
                        "minimumBandWidthPx": BEVEL_MINIMUM_BAND_WIDTH_PX,
                    }
                    if (
                        band_width >= BEVEL_MINIMUM_BAND_WIDTH_PX
                        or metric_thresholds != expected_thresholds
                    ):
                        raise CapabilityVerificationError(
                            f"{metric_context} resolution limit is inconsistent"
                        )
                    expected_pass = True
                if metrics.get("passed") is not expected_pass:
                    raise CapabilityVerificationError(
                        f"{metric_context} metric pass status is inconsistent"
                    )
                region_passes.append(expected_pass)
            slide_passed = all(region_passes)
            if slide.get("passed") is not slide_passed:
                raise CapabilityVerificationError(f"{context} pass status is inconsistent")
            slide_passes.append(slide_passed)
        applicable = value.get("applicable")
        if not isinstance(applicable, bool) or applicable is not (evaluable_regions > 0):
            raise CapabilityVerificationError(f"{case_id} bevel-local applicability is inconsistent")
        if applicable:
            applicable_count += 1
        case_passed = all(slide_passes)
        if value.get("passed") is not case_passed:
            raise CapabilityVerificationError(f"{case_id} bevel-local pass status is inconsistent")
        all_cases_passed = all_cases_passed and case_passed
        if not case_passed:
            raise CapabilityVerificationError(f"{case_id} bevel-local report failed")
    if applicable_count < 1 or report.get("applicableCaseCount") != applicable_count:
        raise CapabilityVerificationError("bevel-local report requires applicable case evidence")
    if report.get("passed") is not all_cases_passed or report.get("passed") is not True:
        raise CapabilityVerificationError("bevel-local report failed")


def _validate_camera_local(
    report: Mapping[str, Any],
    current: Mapping[str, Mapping[str, Any]],
    current_revision: str,
    repo: Path,
) -> None:
    if report.get("schemaVersion") != 4:
        raise CapabilityVerificationError("camera-local report requires schemaVersion=4")
    renderer = _mapping(report.get("renderer"), "camera-local renderer")
    if renderer.get("revision") != current_revision or renderer.get("dirty") is not False:
        raise CapabilityVerificationError(
            "camera-local report must match the clean native-report revision"
        )
    expected_thresholds = {
        "plane": {
            "cornerScore": CAMERA_CORNER_SCORE_THRESHOLD,
            "colorScore": CAMERA_COLOR_SCORE_THRESHOLD,
            "gradientRangeRatio": CAMERA_GRADIENT_RANGE_RATIO_THRESHOLD,
            "gradientDirection": CAMERA_GRADIENT_DIRECTION_THRESHOLD,
            "minimumReferenceGradientRange": CAMERA_MINIMUM_REFERENCE_GRADIENT_RANGE,
            "shadowRingInnerRatio": CAMERA_SHADOW_RING_INNER_RATIO,
            "shadowRingOuterRatio": CAMERA_SHADOW_RING_OUTER_RATIO,
            "shadowBackgroundLevel": CAMERA_SHADOW_BACKGROUND_LEVEL,
            "minimumReferenceShadowDensity": CAMERA_MINIMUM_REFERENCE_SHADOW_DENSITY,
            "shadowEnergyRatio": CAMERA_SHADOW_ENERGY_RATIO_THRESHOLD,
            "shadowDirectionCosine": CAMERA_SHADOW_DIRECTION_THRESHOLD,
        },
        "text": {
            "rasterToleranceRatio": CAMERA_TEXT_RASTER_TOLERANCE_RATIO,
            "tolerantForegroundF1": CAMERA_TEXT_TOLERANT_FOREGROUND_F1_THRESHOLD,
            "tolerantBoundsScore": CAMERA_TEXT_TOLERANT_BOUNDS_SCORE_THRESHOLD,
            "inkCoverageRatio": CAMERA_TEXT_INK_COVERAGE_RATIO_THRESHOLD,
        },
        "picture": {
            "cornerScore": CAMERA_PICTURE_CORNER_SCORE_THRESHOLD,
            "rectifiedColorScore": CAMERA_PICTURE_RECTIFIED_COLOR_SCORE_THRESHOLD,
            "rectifiedEdgeF1": CAMERA_PICTURE_RECTIFIED_EDGE_F1_THRESHOLD,
            "rectifiedSize": CAMERA_PICTURE_RECTIFIED_SIZE,
            "edgeToleranceRatio": CAMERA_PICTURE_EDGE_TOLERANCE_RATIO,
            "cropMutationRatio": CAMERA_PICTURE_CROP_MUTATION_RATIO,
        },
    }
    thresholds = _mapping(report.get("thresholds"), "camera-local thresholds")
    if thresholds != expected_thresholds:
        raise CapabilityVerificationError("camera-local report uses unexpected thresholds")

    values = report.get("caseResults")
    if not isinstance(values, list) or any(not isinstance(value, Mapping) for value in values):
        raise CapabilityVerificationError("camera-local caseResults must be a list of objects")
    by_case: dict[str, Mapping[str, Any]] = {}
    for value in values:
        case_id = value.get("caseId")
        if not isinstance(case_id, str) or not case_id or case_id in by_case:
            raise CapabilityVerificationError("camera-local case IDs must be unique strings")
        by_case[case_id] = value
    if set(by_case) != set(current):
        raise CapabilityVerificationError("camera-local case IDs must match native reports")

    applicable_count = 0
    all_cases_passed = True
    for case_id, value in by_case.items():
        source_hash, ground_truth_hash = _case_hashes(current[case_id], case_id)
        if value.get("sourceSha256") != source_hash or value.get(
            "groundTruthSha256"
        ) != ground_truth_hash:
            raise CapabilityVerificationError(
                f"{case_id} camera-local input hashes must match native reports"
            )
        slides = value.get("slides")
        if not isinstance(slides, list) or any(not isinstance(slide, Mapping) for slide in slides):
            raise CapabilityVerificationError(f"{case_id} camera-local slides must be objects")
        native_slide_values = current[case_id].get("perSlide")
        if not isinstance(native_slide_values, list) or any(
            not isinstance(slide, Mapping) for slide in native_slide_values
        ):
            raise CapabilityVerificationError(
                f"{case_id} native report is missing per-slide artifacts"
            )
        native_slides = {
            slide.get("slideIdx"): slide
            for slide in native_slide_values
            if isinstance(slide.get("slideIdx"), int) and slide.get("hidden") is not True
        }
        seen_slide_indices: set[int] = set()
        slide_passes: list[bool] = []
        for slide_index, slide in enumerate(slides):
            context = f"{case_id} camera-local slide {slide_index}"
            source_slide_index = slide.get("slideIdx")
            if (
                not isinstance(source_slide_index, int)
                or source_slide_index < 0
                or source_slide_index in seen_slide_indices
            ):
                raise CapabilityVerificationError(f"{context} index is invalid or duplicated")
            seen_slide_indices.add(source_slide_index)
            native_slide = native_slides.get(source_slide_index)
            if native_slide is None:
                raise CapabilityVerificationError(f"{context} is absent from the native report")
            native_artifacts = _mapping(
                native_slide.get("renderArtifacts"), f"{context} native render artifacts"
            )
            for kind in ("reference", "candidate"):
                path_value = slide.get(f"{kind}Path")
                expected_hash = _sha256(slide.get(f"{kind}Sha256"), f"{context} {kind}")
                native_artifact = _mapping(
                    native_artifacts.get(kind), f"{context} native {kind} artifact"
                )
                if (
                    native_artifact.get("path") != path_value
                    or native_artifact.get("sha256") != expected_hash
                ):
                    raise CapabilityVerificationError(
                        f"{context} does not match native report artifacts"
                    )
                if not isinstance(path_value, str) or "\\" in path_value:
                    raise CapabilityVerificationError(f"{context} {kind} path is invalid")
                relative = PurePosixPath(path_value)
                if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
                    raise CapabilityVerificationError(f"{context} {kind} path is invalid")
                artifact = (repo / relative.as_posix()).resolve()
                try:
                    artifact.relative_to(repo.resolve())
                except ValueError as error:
                    raise CapabilityVerificationError(
                        f"{context} {kind} path escapes the repository"
                    ) from error
                if not artifact.is_file():
                    raise CapabilityVerificationError(f"{context} {kind} artifact is missing")
                digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
                if digest != expected_hash:
                    raise CapabilityVerificationError(f"{context} {kind} artifact hash changed")

            modality = slide.get("modality")
            if modality not in expected_thresholds:
                raise CapabilityVerificationError(f"{context} modality is unsupported")
            modality_thresholds = expected_thresholds[modality]
            metrics = _mapping(slide.get("metrics"), f"{context} metrics")
            if metrics.get("evaluable") is not True:
                raise CapabilityVerificationError(f"{context} must contain evaluable metrics")
            if (
                _mapping(metrics.get("thresholds"), f"{context} thresholds")
                != modality_thresholds
            ):
                raise CapabilityVerificationError(f"{context} uses unexpected thresholds")
            if modality == "plane":
                corner_score = _finite_metric(
                    metrics.get("cornerScore"), f"{context} corner score"
                )
                mean_corner_error = _finite_metric(
                    metrics.get("meanCornerErrorRatio"), f"{context} corner error"
                )
                color_score = _finite_metric(
                    metrics.get("colorScore"), f"{context} color score"
                )
                reference_range = _finite_metric(
                    metrics.get("referenceGradientRange"),
                    f"{context} reference gradient range",
                )
                candidate_range = _finite_metric(
                    metrics.get("candidateGradientRange"),
                    f"{context} candidate gradient range",
                )
                range_ratio = _finite_metric(
                    metrics.get("gradientRangeRatio"), f"{context} gradient range ratio"
                )
                direction = _finite_metric(
                    metrics.get("gradientDirection"), f"{context} gradient direction"
                )
                shadow_required = metrics.get("shadowRequired")
                shadow_measurable = metrics.get("shadowMeasurable")
                shadow_passed = metrics.get("shadowPassed")
                if (
                    not isinstance(shadow_required, bool)
                    or not isinstance(shadow_measurable, bool)
                    or not isinstance(shadow_passed, bool)
                ):
                    raise CapabilityVerificationError(
                        f"{context} shadow flags must be booleans"
                    )
                reference_shadow_density = _finite_metric(
                    metrics.get("referenceShadowDensity"),
                    f"{context} reference shadow density",
                )
                candidate_shadow_density = _finite_metric(
                    metrics.get("candidateShadowDensity"),
                    f"{context} candidate shadow density",
                )
                shadow_energy_ratio = _finite_metric(
                    metrics.get("shadowEnergyRatio"),
                    f"{context} shadow energy ratio",
                )
                shadow_direction = _finite_metric(
                    metrics.get("shadowDirectionCosine"),
                    f"{context} shadow direction cosine",
                )
                ring_values = {
                    name: metrics.get(name)
                    for name in (
                        "referenceShadowRingPixels",
                        "candidateShadowRingPixels",
                        "shadowRingInnerPx",
                        "shadowRingOuterPx",
                    )
                }
                if any(
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or value < 1
                    for value in ring_values.values()
                ) or ring_values["shadowRingOuterPx"] <= ring_values["shadowRingInnerPx"]:
                    raise CapabilityVerificationError(
                        f"{context} shadow ring dimensions are invalid"
                    )
                if (
                    not 0 <= corner_score <= 1
                    or mean_corner_error < 0
                    or not 0 <= color_score <= 1
                    or reference_range < 0
                    or candidate_range < 0
                    or not 0 <= range_ratio <= 1
                    or not -1 <= direction <= 1
                    or reference_shadow_density < 0
                    or candidate_shadow_density < 0
                    or not 0 <= shadow_energy_ratio <= 1
                    or not -1 <= shadow_direction <= 1
                ):
                    raise CapabilityVerificationError(
                        f"{context} metrics are outside their domains"
                    )
                gradient_required = metrics.get("gradientRequired")
                if not isinstance(gradient_required, bool) or gradient_required is not (
                    reference_range >= CAMERA_MINIMUM_REFERENCE_GRADIENT_RANGE
                ):
                    raise CapabilityVerificationError(
                        f"{context} gradient requirement is inconsistent"
                    )
                expected_corner_score = max(0.0, 1.0 - mean_corner_error)
                expected_range_ratio = (
                    min(reference_range, candidate_range)
                    / max(reference_range, candidate_range)
                    if max(reference_range, candidate_range) > 0
                    else 1.0
                )
                if (
                    abs(corner_score - expected_corner_score) > 1e-9
                    or abs(range_ratio - expected_range_ratio) > 1e-9
                ):
                    raise CapabilityVerificationError(
                        f"{context} plane metrics are inconsistent"
                    )
                expected_shadow_measurable = (
                    shadow_required
                    and reference_shadow_density
                    >= CAMERA_MINIMUM_REFERENCE_SHADOW_DENSITY
                )
                maximum_shadow_density = max(
                    reference_shadow_density,
                    candidate_shadow_density,
                )
                expected_shadow_energy_ratio = (
                    min(reference_shadow_density, candidate_shadow_density)
                    / maximum_shadow_density
                    if maximum_shadow_density > 1e-9
                    else 1.0
                )
                expected_shadow_passed = not expected_shadow_measurable or (
                    shadow_energy_ratio >= CAMERA_SHADOW_ENERGY_RATIO_THRESHOLD
                    and shadow_direction >= CAMERA_SHADOW_DIRECTION_THRESHOLD
                )
                if (
                    abs(shadow_energy_ratio - expected_shadow_energy_ratio) > 1e-9
                    or shadow_measurable is not expected_shadow_measurable
                    or shadow_passed is not expected_shadow_passed
                ):
                    raise CapabilityVerificationError(
                        f"{context} shadow metrics are inconsistent"
                    )
                shadow_sensitivity = _mapping(
                    metrics.get("shadowSensitivity"),
                    f"{context} shadow sensitivity",
                )
                if (
                    shadow_sensitivity.get("mutation") != "erase-exterior-shadow"
                    or shadow_sensitivity.get("applicable")
                    is not expected_shadow_measurable
                ):
                    raise CapabilityVerificationError(
                        f"{context} shadow sensitivity is inconsistent"
                    )
                if expected_shadow_measurable:
                    mutated_density = _finite_metric(
                        shadow_sensitivity.get("mutatedCandidateShadowDensity"),
                        f"{context} mutated shadow density",
                    )
                    mutated_energy_ratio = _finite_metric(
                        shadow_sensitivity.get("mutatedShadowEnergyRatio"),
                        f"{context} mutated shadow energy ratio",
                    )
                    mutated_direction = _finite_metric(
                        shadow_sensitivity.get("mutatedShadowDirectionCosine"),
                        f"{context} mutated shadow direction",
                    )
                    mutated_passed = shadow_sensitivity.get("mutatedShadowPassed")
                    detected = shadow_sensitivity.get("detected")
                    if (
                        mutated_density < 0
                        or not 0 <= mutated_energy_ratio <= 1
                        or not -1 <= mutated_direction <= 1
                        or not isinstance(mutated_passed, bool)
                        or not isinstance(detected, bool)
                    ):
                        raise CapabilityVerificationError(
                            f"{context} shadow sensitivity is outside its domain"
                        )
                    mutated_maximum_density = max(
                        reference_shadow_density,
                        mutated_density,
                    )
                    expected_mutated_energy_ratio = (
                        min(reference_shadow_density, mutated_density)
                        / mutated_maximum_density
                        if mutated_maximum_density > 1e-9
                        else 1.0
                    )
                    expected_mutated_passed = (
                        mutated_energy_ratio >= CAMERA_SHADOW_ENERGY_RATIO_THRESHOLD
                        and mutated_direction >= CAMERA_SHADOW_DIRECTION_THRESHOLD
                    )
                    if (
                        abs(mutated_energy_ratio - expected_mutated_energy_ratio) > 1e-9
                        or mutated_passed is not expected_mutated_passed
                        or detected is not (not expected_mutated_passed)
                        or detected is not True
                    ):
                        raise CapabilityVerificationError(
                            f"{context} shadow sensitivity is inconsistent"
                        )
                elif shadow_sensitivity.get("detected") is not None:
                    raise CapabilityVerificationError(
                        f"{context} shadow sensitivity is inconsistent"
                    )
                expected_pass = (
                    corner_score >= CAMERA_CORNER_SCORE_THRESHOLD
                    and color_score >= CAMERA_COLOR_SCORE_THRESHOLD
                    and (
                        not gradient_required
                        or (
                            range_ratio >= CAMERA_GRADIENT_RANGE_RATIO_THRESHOLD
                            and direction >= CAMERA_GRADIENT_DIRECTION_THRESHOLD
                        )
                    )
                    and expected_shadow_passed
                )
            elif modality == "text":
                foreground_iou = _finite_metric(
                    metrics.get("foregroundIou"), f"{context} foreground IoU"
                )
                bounds_score = _finite_metric(
                    metrics.get("boundsScore"), f"{context} bounds score"
                )
                mean_bounds_error = _finite_metric(
                    metrics.get("meanBoundsErrorRatio"), f"{context} bounds error"
                )
                raster_tolerance_px = metrics.get("rasterTolerancePx")
                if (
                    not isinstance(raster_tolerance_px, int)
                    or isinstance(raster_tolerance_px, bool)
                    or raster_tolerance_px < 1
                ):
                    raise CapabilityVerificationError(
                        f"{context} raster tolerance must be a positive integer"
                    )
                reference_coverage = _finite_metric(
                    metrics.get("referenceCoverageAtTolerance"),
                    f"{context} reference coverage at tolerance",
                )
                candidate_coverage = _finite_metric(
                    metrics.get("candidateCoverageAtTolerance"),
                    f"{context} candidate coverage at tolerance",
                )
                tolerant_foreground_f1 = _finite_metric(
                    metrics.get("tolerantForegroundF1"),
                    f"{context} tolerant foreground F1",
                )
                tolerant_bounds_score = _finite_metric(
                    metrics.get("tolerantBoundsScore"),
                    f"{context} tolerant bounds score",
                )
                tolerant_mean_bounds_error = _finite_metric(
                    metrics.get("tolerantMeanBoundsErrorRatio"),
                    f"{context} tolerant bounds error",
                )
                ink_coverage_ratio = _finite_metric(
                    metrics.get("inkCoverageRatio"), f"{context} ink coverage ratio"
                )
                reference_ink_density = _finite_metric(
                    metrics.get("referenceInkDensity"), f"{context} reference ink density"
                )
                candidate_ink_density = _finite_metric(
                    metrics.get("candidateInkDensity"), f"{context} candidate ink density"
                )
                if (
                    not 0 <= foreground_iou <= 1
                    or not 0 <= bounds_score <= 1
                    or mean_bounds_error < 0
                    or not 0 <= reference_coverage <= 1
                    or not 0 <= candidate_coverage <= 1
                    or not 0 <= tolerant_foreground_f1 <= 1
                    or not 0 <= tolerant_bounds_score <= 1
                    or tolerant_mean_bounds_error < 0
                    or not 0 <= ink_coverage_ratio <= 1
                    or reference_ink_density <= 0
                    or candidate_ink_density <= 0
                ):
                    raise CapabilityVerificationError(
                        f"{context} metrics are outside their domains"
                    )
                expected_tolerant_foreground_f1 = (
                    2
                    * reference_coverage
                    * candidate_coverage
                    / (reference_coverage + candidate_coverage)
                    if reference_coverage + candidate_coverage > 0
                    else 0.0
                )
                if (
                    abs(tolerant_foreground_f1 - expected_tolerant_foreground_f1) > 1e-9
                    or abs(
                        tolerant_bounds_score
                        - max(0.0, 1.0 - tolerant_mean_bounds_error)
                    )
                    > 1e-9
                ):
                    raise CapabilityVerificationError(
                        f"{context} tolerant metrics are inconsistent"
                    )
                for kind in ("reference", "candidate"):
                    bounds = metrics.get(f"{kind}Bounds")
                    if (
                        not isinstance(bounds, list)
                        or len(bounds) != 4
                        or any(
                            not isinstance(coordinate, (int, float))
                            or isinstance(coordinate, bool)
                            or not math.isfinite(coordinate)
                            or coordinate < 0
                            for coordinate in bounds
                        )
                        or bounds[0] > bounds[2]
                        or bounds[1] > bounds[3]
                    ):
                        raise CapabilityVerificationError(
                            f"{context} {kind} bounds are invalid"
                        )
                expected_pass = (
                    tolerant_foreground_f1
                    >= CAMERA_TEXT_TOLERANT_FOREGROUND_F1_THRESHOLD
                    and tolerant_bounds_score >= CAMERA_TEXT_TOLERANT_BOUNDS_SCORE_THRESHOLD
                    and ink_coverage_ratio >= CAMERA_TEXT_INK_COVERAGE_RATIO_THRESHOLD
                )
            else:
                corner_score = _finite_metric(
                    metrics.get("cornerScore"), f"{context} picture corner score"
                )
                mean_corner_error = _finite_metric(
                    metrics.get("meanCornerErrorRatio"),
                    f"{context} picture corner error",
                )
                rectified_color_score = _finite_metric(
                    metrics.get("rectifiedColorScore"),
                    f"{context} rectified picture color score",
                )
                rectified_edge_f1 = _finite_metric(
                    metrics.get("rectifiedEdgeF1"),
                    f"{context} rectified picture edge F1",
                )
                reference_edge_coverage = _finite_metric(
                    metrics.get("referenceEdgeCoverageAtTolerance"),
                    f"{context} reference picture edge coverage",
                )
                candidate_edge_coverage = _finite_metric(
                    metrics.get("candidateEdgeCoverageAtTolerance"),
                    f"{context} candidate picture edge coverage",
                )
                edge_tolerance_px = metrics.get("edgeTolerancePx")
                rectified_size = metrics.get("rectifiedSize")
                if (
                    not 0 <= corner_score <= 1
                    or mean_corner_error < 0
                    or not 0 <= rectified_color_score <= 1
                    or not 0 <= rectified_edge_f1 <= 1
                    or not 0 <= reference_edge_coverage <= 1
                    or not 0 <= candidate_edge_coverage <= 1
                ):
                    raise CapabilityVerificationError(
                        f"{context} metrics are outside their domains"
                    )
                if (
                    not isinstance(edge_tolerance_px, int)
                    or isinstance(edge_tolerance_px, bool)
                    or edge_tolerance_px < 1
                    or edge_tolerance_px
                    != max(
                        1,
                        round(
                            CAMERA_PICTURE_RECTIFIED_SIZE
                            * CAMERA_PICTURE_EDGE_TOLERANCE_RATIO
                        ),
                    )
                    or rectified_size != CAMERA_PICTURE_RECTIFIED_SIZE
                ):
                    raise CapabilityVerificationError(
                        f"{context} picture raster dimensions are invalid"
                    )
                expected_corner_score = max(0.0, 1.0 - mean_corner_error)
                expected_edge_f1 = (
                    2
                    * reference_edge_coverage
                    * candidate_edge_coverage
                    / (reference_edge_coverage + candidate_edge_coverage)
                    if reference_edge_coverage + candidate_edge_coverage > 0
                    else 0.0
                )
                if abs(corner_score - expected_corner_score) > 1e-9:
                    raise CapabilityVerificationError(
                        f"{context} picture corner metrics are inconsistent"
                    )
                if abs(rectified_edge_f1 - expected_edge_f1) > 1e-9:
                    raise CapabilityVerificationError(
                        f"{context} picture edge metrics are inconsistent"
                    )
                crop_sensitivity = _mapping(
                    metrics.get("cropSensitivity"),
                    f"{context} crop sensitivity",
                )
                if (
                    crop_sensitivity.get("mutation") != "left-crop-and-rescale"
                    or crop_sensitivity.get("cropRatio")
                    != CAMERA_PICTURE_CROP_MUTATION_RATIO
                ):
                    raise CapabilityVerificationError(
                        f"{context} crop sensitivity is inconsistent"
                    )
                mutated_color_score = _finite_metric(
                    crop_sensitivity.get("mutatedRectifiedColorScore"),
                    f"{context} mutated picture color score",
                )
                mutated_edge_f1 = _finite_metric(
                    crop_sensitivity.get("mutatedRectifiedEdgeF1"),
                    f"{context} mutated picture edge F1",
                )
                mutated_reference_coverage = _finite_metric(
                    crop_sensitivity.get("mutatedReferenceEdgeCoverageAtTolerance"),
                    f"{context} mutated reference picture edge coverage",
                )
                mutated_candidate_coverage = _finite_metric(
                    crop_sensitivity.get("mutatedCandidateEdgeCoverageAtTolerance"),
                    f"{context} mutated candidate picture edge coverage",
                )
                mutated_passed = crop_sensitivity.get("mutatedPassed")
                detected = crop_sensitivity.get("detected")
                if (
                    not 0 <= mutated_color_score <= 1
                    or not 0 <= mutated_edge_f1 <= 1
                    or not 0 <= mutated_reference_coverage <= 1
                    or not 0 <= mutated_candidate_coverage <= 1
                    or not isinstance(mutated_passed, bool)
                    or not isinstance(detected, bool)
                ):
                    raise CapabilityVerificationError(
                        f"{context} crop sensitivity is outside its domain"
                    )
                expected_mutated_edge_f1 = (
                    2
                    * mutated_reference_coverage
                    * mutated_candidate_coverage
                    / (mutated_reference_coverage + mutated_candidate_coverage)
                    if mutated_reference_coverage + mutated_candidate_coverage > 0
                    else 0.0
                )
                expected_mutated_passed = (
                    mutated_color_score
                    >= CAMERA_PICTURE_RECTIFIED_COLOR_SCORE_THRESHOLD
                    and mutated_edge_f1 >= CAMERA_PICTURE_RECTIFIED_EDGE_F1_THRESHOLD
                )
                if (
                    abs(mutated_edge_f1 - expected_mutated_edge_f1) > 1e-9
                    or mutated_passed is not expected_mutated_passed
                    or detected is not (not expected_mutated_passed)
                    or detected is not True
                ):
                    raise CapabilityVerificationError(
                        f"{context} crop sensitivity is inconsistent"
                    )
                expected_pass = (
                    corner_score >= CAMERA_PICTURE_CORNER_SCORE_THRESHOLD
                    and rectified_color_score
                    >= CAMERA_PICTURE_RECTIFIED_COLOR_SCORE_THRESHOLD
                    and rectified_edge_f1
                    >= CAMERA_PICTURE_RECTIFIED_EDGE_F1_THRESHOLD
                    and detected
                )
            if (
                metrics.get("passed") is not expected_pass
                or slide.get("passed") is not expected_pass
            ):
                raise CapabilityVerificationError(f"{context} metric pass status is inconsistent")
            slide_passes.append(expected_pass)

        applicable = value.get("applicable")
        if not isinstance(applicable, bool) or applicable is not bool(slides):
            raise CapabilityVerificationError(
                f"{case_id} camera-local applicability is inconsistent"
            )
        if applicable:
            applicable_count += 1
        case_passed = applicable and all(slide_passes)
        if value.get("passed") is not case_passed:
            raise CapabilityVerificationError(f"{case_id} camera-local pass status is inconsistent")
        all_cases_passed = all_cases_passed and case_passed
        if not case_passed:
            raise CapabilityVerificationError(f"{case_id} camera-local report failed")
    if applicable_count < 1 or report.get("applicableCaseCount") != applicable_count:
        raise CapabilityVerificationError("camera-local report requires applicable case evidence")
    if report.get("passed") is not all_cases_passed or report.get("passed") is not True:
        raise CapabilityVerificationError("camera-local report failed")


def normalize_native_evaluation_reports(
    capability: CapabilityDefinition,
    reports: Sequence[Mapping[str, Any]],
    repo: Path,
    *,
    oracle: str,
    baseline_reports: Sequence[Mapping[str, Any]] = (),
    passed_gates: Iterable[str] = (),
    manual_verdicts: Mapping[str, str] | None = None,
    bevel_report: Mapping[str, Any] | None = None,
    camera_report: Mapping[str, Any] | None = None,
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
    bevel_local_passed = False
    if bevel_report is not None:
        _validate_bevel_local(bevel_report, current, next(iter(revisions)), repo)
        bevel_local_passed = True
    camera_local_passed = False
    if camera_report is not None:
        _validate_camera_local(camera_report, current, next(iter(revisions)), repo)
        camera_local_passed = True
    gates = {
        gate: (
            "passed"
            if gate in supplied_gates
            or (gate == "native-powerpoint" and all(case["passed"] for case in case_results))
            or (gate == "manual-visual")
            or (gate == "regression" and baseline_reports)
            or (gate == "bevel-local" and bevel_local_passed)
            or (gate == "camera-local" and camera_local_passed)
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
