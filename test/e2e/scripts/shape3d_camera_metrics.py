#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence
from zipfile import ZipFile

import cv2
import numpy as np
from lxml import etree
from PIL import Image


E2E_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = E2E_DIR.parents[1]
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"p": P_NS, "a": A_NS}

CORNER_SCORE_THRESHOLD = 0.98
COLOR_SCORE_THRESHOLD = 0.97
GRADIENT_RANGE_RATIO_THRESHOLD = 0.65
GRADIENT_DIRECTION_THRESHOLD = 0.95
MIN_REFERENCE_GRADIENT_RANGE = 4.0
TEXT_FOREGROUND_IOU_THRESHOLD = 0.72
TEXT_BOUNDS_SCORE_THRESHOLD = 0.98
TEXT_INK_COVERAGE_RATIO_THRESHOLD = 0.90


def _slide_number(path: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", path)
    return int(match.group(1)) if match else 0


def _zero_or_absent(value: str | None) -> bool:
    if value is None:
        return True
    try:
        numeric = float(value)
    except ValueError:
        return False
    return math.isfinite(numeric) and numeric == 0


def _rotation_matches(node, expected: tuple[float, float, float]) -> bool:
    if node is None:
        return False
    try:
        values = tuple(float(node.get(name, "0")) for name in ("lat", "lon", "rev"))
    except ValueError:
        return False
    return all(math.isfinite(value) and value == target for value, target in zip(values, expected))


def _supported_camera(camera) -> str | None:
    if camera.get("zoom") is not None:
        return None
    preset = camera.get("prst")
    rotation = camera.find("a:rot", NS)
    if preset == "orthographicFront" and camera.get("fov") is None:
        if rotation is None or _rotation_matches(rotation, (1200000, 1800000, 0)):
            return "orthographic"
        return None
    if (
        preset == "perspectiveRelaxedModerately"
        and camera.get("fov") == "7200000"
        and _rotation_matches(rotation, (18590633, 0, 0))
    ):
        return "perspective"
    return None


def _supported_camera_fill(
    shape,
    shape_properties,
    camera_kind: str,
    verified_theme_accent1: bool,
) -> bool:
    solid = shape_properties.find("a:solidFill", NS)
    if solid is not None:
        color = solid.find("a:srgbClr", NS)
        return (
            color is not None
            and color.get("val", "").upper() == "2F75B5"
            and len(color) == 0
        )
    if camera_kind != "perspective" or not verified_theme_accent1:
        return False
    return bool(
        shape.xpath(
            "boolean(p:style/a:fillRef[@idx='1']/a:schemeClr[@val='accent1'])",
            namespaces=NS,
        )
    )


def _is_supported_camera_shape(shape, verified_theme_accent1: bool) -> bool:
    shape_properties = shape.find("p:spPr", NS)
    if shape_properties is None:
        return False
    geometry = shape_properties.find("a:prstGeom", NS)
    scene = shape_properties.find("a:scene3d", NS)
    shape3d = shape_properties.find("a:sp3d", NS)
    if (
        geometry is None
        or geometry.get("prst") != "rect"
        or scene is None
        or scene.find("a:backdrop", NS) is not None
    ):
        return False
    camera = scene.find("a:camera", NS)
    light = scene.find("a:lightRig", NS)
    if camera is None or light is None:
        return False
    camera_kind = _supported_camera(camera)
    if (
        camera_kind is None
        or light.get("rig") != "threePt"
        or light.get("dir") != "t"
        or light.find("a:rot", NS) is not None
    ):
        return False
    transform = shape_properties.find("a:xfrm", NS)
    if transform is not None and any(
        not _zero_or_absent(transform.get(name)) for name in ("rot", "flipH", "flipV")
    ):
        return False
    if shape3d is None:
        # Native case 0014 proves absence is implicit zero depth only for the exact relaxed
        # perspective tuple. Orthographic absence remains outside this metric's contract.
        if camera_kind != "perspective":
            return False
    elif any(
        not _zero_or_absent(shape3d.get(name)) for name in ("z", "extrusionH", "contourW")
    ) or (
        shape3d.get("prstMaterial") is not None
        or shape3d.find("a:bevelT", NS) is not None
        or shape3d.find("a:bevelB", NS) is not None
        or shape3d.find("a:extrusionClr", NS) is not None
        or shape3d.find("a:contourClr", NS) is not None
    ):
        return False
    if (
        shape_properties.find("a:effectLst", NS) is not None
        or shape_properties.find("a:effectDag", NS) is not None
        or shape_properties.find("a:ln/a:noFill", NS) is None
    ):
        return False
    if shape.xpath("boolean(p:txBody//a:t[normalize-space(.) != ''])", namespaces=NS):
        return False
    return _supported_camera_fill(
        shape,
        shape_properties,
        camera_kind,
        verified_theme_accent1,
    )


def _has_verified_theme_accent1(archive: ZipFile) -> bool:
    values: set[str] = set()
    for name in archive.namelist():
        if not re.fullmatch(r"ppt/theme/theme\d+\.xml", name):
            continue
        root = etree.fromstring(archive.read(name))
        values.update(
            value.upper()
            for value in root.xpath(".//a:clrScheme/a:accent1/a:srgbClr/@val", namespaces=NS)
        )
    return values == {"4F81BD"}


def extract_camera_slide_indices(source_pptx: Path) -> set[int]:
    """Return slides containing the bounded zero-depth rectangular camera-plane tuple."""
    indices: set[int] = set()
    with ZipFile(source_pptx) as archive:
        verified_theme_accent1 = _has_verified_theme_accent1(archive)
        slide_paths = sorted(
            (
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ),
            key=_slide_number,
        )
        for slide_index, slide_path in enumerate(slide_paths):
            slide = etree.fromstring(archive.read(slide_path))
            for shape in slide.xpath(".//p:sp", namespaces=NS):
                if _is_supported_camera_shape(shape, verified_theme_accent1):
                    indices.add(slide_index)
                    break
    return indices


def _is_supported_text_camera_shape(shape) -> bool:
    shape_properties = shape.find("p:spPr", NS)
    if shape_properties is None:
        return False
    geometry = shape_properties.find("a:prstGeom", NS)
    scene = shape_properties.find("a:scene3d", NS)
    if (
        geometry is None
        or geometry.get("prst") != "rect"
        or scene is None
        or shape_properties.find("a:sp3d", NS) is not None
        or scene.find("a:backdrop", NS) is not None
    ):
        return False
    camera = scene.find("a:camera", NS)
    light = scene.find("a:lightRig", NS)
    if (
        camera is None
        or camera.get("prst") != "perspectiveContrastingRightFacing"
        or camera.get("fov") != "5100000"
        or camera.get("zoom") is not None
        or not _rotation_matches(camera.find("a:rot", NS), (0, 19532225, 0))
        or light is None
        or light.get("rig") != "threePt"
        or light.get("dir") != "t"
        or light.find("a:rot", NS) is not None
    ):
        return False
    transform = shape_properties.find("a:xfrm", NS)
    if transform is not None and any(
        not _zero_or_absent(transform.get(name)) for name in ("rot", "flipH", "flipV")
    ):
        return False
    body = shape.find("p:txBody/a:bodyPr", NS)
    if (
        shape_properties.find("a:noFill", NS) is None
        or shape_properties.find("a:ln", NS) is not None
        or shape_properties.find("a:effectLst", NS) is not None
        or shape_properties.find("a:effectDag", NS) is not None
        or shape.find("p:style", NS) is not None
        or body is None
        or body.get("wrap") != "none"
        or body.get("anchor") != "ctr"
        or body.get("vert") is not None
        or body.find("a:spAutoFit", NS) is None
        or body.find("a:normAutofit", NS) is not None
        or body.find("a:noAutofit", NS) is not None
        or not shape.xpath("boolean(p:txBody//a:t[normalize-space(.) != ''])", namespaces=NS)
    ):
        return False
    return True


def extract_text_camera_slide_indices(source_pptx: Path) -> set[int]:
    """Return slides containing the exact scene-only editable-text camera tuple."""
    indices: set[int] = set()
    with ZipFile(source_pptx) as archive:
        slide_paths = sorted(
            (
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ),
            key=_slide_number,
        )
        for slide_index, slide_path in enumerate(slide_paths):
            slide = etree.fromstring(archive.read(slide_path))
            if any(
                _is_supported_text_camera_shape(shape)
                for shape in slide.xpath(".//p:sp", namespaces=NS)
            ):
                indices.add(slide_index)
    return indices


def _foreground_mask(image: np.ndarray) -> np.ndarray:
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError("camera metric requires an RGB image")
    rgb = image[..., :3].astype(np.int16, copy=False)
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    # The native camera matrix uses saturated blue probes on a white slide. Requiring chroma keeps
    # PDF antialiasing while excluding the white page and makes the local gate independent of the
    # renderer's own source bounds.
    return (spread > 18) & (rgb.min(axis=2) < 245)


def _ordered_normalized_corners(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mask = _foreground_mask(image)
    contours, _ = cv2.findContours(
        mask.astype(np.uint8) * 255,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    if not contours:
        raise ValueError("camera plane foreground is empty")
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 64:
        raise ValueError("camera plane foreground is below the resolution floor")
    hull = cv2.convexHull(contour)
    perimeter = cv2.arcLength(hull, True)
    polygon = None
    for epsilon in (0.003, 0.005, 0.008, 0.012, 0.02):
        candidate = cv2.approxPolyDP(hull, epsilon * perimeter, True).reshape(-1, 2)
        if len(candidate) == 4:
            polygon = candidate.astype(np.float64)
            break
    if polygon is None:
        raise ValueError("camera plane foreground is not a four-corner convex polygon")
    polygon[:, 0] /= image.shape[1]
    polygon[:, 1] /= image.shape[0]
    sums = polygon.sum(axis=1)
    differences = polygon[:, 0] - polygon[:, 1]
    ordered = np.asarray(
        [
            polygon[np.argmin(sums)],
            polygon[np.argmax(differences)],
            polygon[np.argmax(sums)],
            polygon[np.argmin(differences)],
        ]
    )
    if len({tuple(point) for point in ordered}) != 4:
        raise ValueError("camera plane corners are ambiguous")
    return ordered, mask


def _material_bands(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    foreground_rows = np.flatnonzero(mask.any(axis=1))
    if foreground_rows.size == 0:
        raise ValueError("camera plane foreground is empty")
    top = int(foreground_rows[0])
    bottom = int(foreground_rows[-1])
    height = max(bottom - top, 1)
    yy = np.arange(image.shape[0])[:, None]
    bands: list[np.ndarray] = []
    for fraction in (0.1, 0.5, 0.9):
        center = top + fraction * height
        radius = max(2.0, height * 0.015)
        selection = mask & (np.abs(yy - center) <= radius)
        values = image[..., :3][selection]
        if values.shape[0] < 16:
            raise ValueError("camera material band contains too few pixels")
        bands.append(np.median(values, axis=0))
    return np.asarray(bands, dtype=np.float64)


def compute_camera_plane_metrics(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    corner_score_threshold: float = CORNER_SCORE_THRESHOLD,
    color_score_threshold: float = COLOR_SCORE_THRESHOLD,
    gradient_range_ratio_threshold: float = GRADIENT_RANGE_RATIO_THRESHOLD,
    gradient_direction_threshold: float = GRADIENT_DIRECTION_THRESHOLD,
) -> dict[str, Any]:
    reference_corners, reference_mask = _ordered_normalized_corners(reference)
    candidate_corners, candidate_mask = _ordered_normalized_corners(candidate)
    left, top = reference_corners.min(axis=0)
    right, bottom = reference_corners.max(axis=0)
    diagonal = math.hypot(right - left, bottom - top)
    if diagonal <= 0:
        raise ValueError("camera plane reference bounds are degenerate")
    mean_corner_error = float(
        np.linalg.norm(reference_corners - candidate_corners, axis=1).mean() / diagonal
    )
    corner_score = max(0.0, 1.0 - mean_corner_error)

    reference_bands = _material_bands(reference, reference_mask)
    candidate_bands = _material_bands(candidate, candidate_mask)
    color_score = max(0.0, 1.0 - float(np.abs(reference_bands - candidate_bands).mean()) / 255)
    reference_vector = reference_bands[0] - reference_bands[-1]
    candidate_vector = candidate_bands[0] - candidate_bands[-1]
    reference_range = float(np.linalg.norm(reference_vector))
    candidate_range = float(np.linalg.norm(candidate_vector))
    gradient_required = reference_range >= MIN_REFERENCE_GRADIENT_RANGE
    if max(reference_range, candidate_range) > 0:
        gradient_range_ratio = min(reference_range, candidate_range) / max(
            reference_range, candidate_range
        )
    else:
        gradient_range_ratio = 1.0
    if reference_range > 1 and candidate_range > 1:
        gradient_direction = float(
            np.dot(reference_vector, candidate_vector) / (reference_range * candidate_range)
        )
    elif reference_range <= 1 and candidate_range <= 1:
        gradient_direction = 1.0
    else:
        gradient_direction = 0.0
    passed = (
        corner_score >= corner_score_threshold
        and color_score >= color_score_threshold
        and (
            not gradient_required
            or (
                gradient_range_ratio >= gradient_range_ratio_threshold
                and gradient_direction >= gradient_direction_threshold
            )
        )
    )
    return {
        "evaluable": True,
        "cornerScore": corner_score,
        "meanCornerErrorRatio": mean_corner_error,
        "colorScore": color_score,
        "gradientRequired": gradient_required,
        "referenceGradientRange": reference_range,
        "candidateGradientRange": candidate_range,
        "gradientRangeRatio": float(gradient_range_ratio),
        "gradientDirection": gradient_direction,
        "referenceBands": reference_bands.round(3).tolist(),
        "candidateBands": candidate_bands.round(3).tolist(),
        "thresholds": {
            "cornerScore": corner_score_threshold,
            "colorScore": color_score_threshold,
            "gradientRangeRatio": gradient_range_ratio_threshold,
            "gradientDirection": gradient_direction_threshold,
            "minimumReferenceGradientRange": MIN_REFERENCE_GRADIENT_RANGE,
        },
        "passed": passed,
    }


def compute_text_camera_metrics(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    foreground_iou_threshold: float = TEXT_FOREGROUND_IOU_THRESHOLD,
    bounds_score_threshold: float = TEXT_BOUNDS_SCORE_THRESHOLD,
    ink_coverage_ratio_threshold: float = TEXT_INK_COVERAGE_RATIO_THRESHOLD,
) -> dict[str, Any]:
    if reference.ndim != 3 or candidate.ndim != 3:
        raise ValueError("text camera metric requires RGB images")
    reference_ink_density = float((255 - reference[..., :3].astype(np.float64)).mean())
    candidate_ink_density = float((255 - candidate[..., :3].astype(np.float64)).mean())
    if max(reference_ink_density, candidate_ink_density) <= 0:
        raise ValueError("text camera ink coverage is empty")
    ink_coverage_ratio = min(reference_ink_density, candidate_ink_density) / max(
        reference_ink_density, candidate_ink_density
    )
    if candidate.shape[:2] != reference.shape[:2]:
        candidate = cv2.resize(
            candidate,
            (reference.shape[1], reference.shape[0]),
            interpolation=cv2.INTER_AREA,
        )
    reference_mask = _foreground_mask(reference)
    candidate_mask = _foreground_mask(candidate)
    reference_y, reference_x = np.nonzero(reference_mask)
    candidate_y, candidate_x = np.nonzero(candidate_mask)
    if reference_x.size < 32 or candidate_x.size < 32:
        raise ValueError("text camera foreground is below the resolution floor")

    intersection = int(np.logical_and(reference_mask, candidate_mask).sum())
    union = int(np.logical_or(reference_mask, candidate_mask).sum())
    foreground_iou = intersection / max(union, 1)
    reference_bounds = np.asarray(
        [reference_x.min(), reference_y.min(), reference_x.max(), reference_y.max()],
        dtype=np.float64,
    )
    candidate_bounds = np.asarray(
        [candidate_x.min(), candidate_y.min(), candidate_x.max(), candidate_y.max()],
        dtype=np.float64,
    )
    reference_diagonal = math.hypot(
        reference_bounds[2] - reference_bounds[0],
        reference_bounds[3] - reference_bounds[1],
    )
    if reference_diagonal <= 0:
        raise ValueError("text camera reference bounds are degenerate")
    top_left_error = np.linalg.norm(reference_bounds[:2] - candidate_bounds[:2])
    bottom_right_error = np.linalg.norm(reference_bounds[2:] - candidate_bounds[2:])
    mean_bounds_error_ratio = float(
        (top_left_error + bottom_right_error) / (2 * reference_diagonal)
    )
    bounds_score = max(0.0, 1.0 - mean_bounds_error_ratio)
    passed = (
        foreground_iou >= foreground_iou_threshold
        and bounds_score >= bounds_score_threshold
        and ink_coverage_ratio >= ink_coverage_ratio_threshold
    )
    return {
        "evaluable": True,
        "foregroundIou": float(foreground_iou),
        "boundsScore": bounds_score,
        "meanBoundsErrorRatio": mean_bounds_error_ratio,
        "inkCoverageRatio": float(ink_coverage_ratio),
        "referenceInkDensity": reference_ink_density,
        "candidateInkDensity": candidate_ink_density,
        "referenceBounds": reference_bounds.astype(int).tolist(),
        "candidateBounds": candidate_bounds.astype(int).tolist(),
        "thresholds": {
            "foregroundIou": foreground_iou_threshold,
            "boundsScore": bounds_score_threshold,
            "inkCoverageRatio": ink_coverage_ratio_threshold,
        },
        "passed": passed,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repository_relative(path: Path, repo: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"camera artifact must be inside the repository: {path}") from error


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON report must be an object: {path}")
    return value


def build_camera_report(
    case_report_paths: Sequence[Path],
    repo: Path,
    reports_dir: Path,
) -> dict[str, Any]:
    if not case_report_paths:
        raise ValueError("at least one case report is required")
    cases: list[dict[str, Any]] = []
    renderer: Mapping[str, Any] | None = None
    for case_report_path in case_report_paths:
        case_report = _load_json(case_report_path)
        case_id = case_report.get("testFile")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"case report is missing testFile: {case_report_path}")
        provenance = case_report.get("provenance")
        if not isinstance(provenance, Mapping):
            raise ValueError(f"case report is missing provenance: {case_id}")
        report_renderer = provenance.get("renderer")
        if not isinstance(report_renderer, Mapping):
            raise ValueError(f"case report is missing renderer provenance: {case_id}")
        if renderer is None:
            renderer = dict(report_renderer)
        elif dict(renderer) != dict(report_renderer):
            raise ValueError("case reports must use one renderer revision")
        inputs = provenance.get("inputs")
        if not isinstance(inputs, Mapping):
            raise ValueError(f"case report is missing input provenance: {case_id}")
        source_info = inputs.get("sourcePptx")
        ground_truth_info = inputs.get("groundTruth")
        if not isinstance(source_info, Mapping) or not isinstance(ground_truth_info, Mapping):
            raise ValueError(f"case report is missing source or ground-truth provenance: {case_id}")
        source_value = source_info.get("path")
        if not isinstance(source_value, str):
            raise ValueError(f"case report is missing source path: {case_id}")
        source_path = repo / source_value
        plane_slides = extract_camera_slide_indices(source_path)
        text_slides = extract_text_camera_slide_indices(source_path)
        applicable_slides = plane_slides | text_slides
        slide_results: list[dict[str, Any]] = []
        for slide in case_report.get("perSlide", []):
            if not isinstance(slide, Mapping) or slide.get("hidden") is True:
                continue
            slide_index = slide.get("slideIdx")
            if not isinstance(slide_index, int) or slide_index not in applicable_slides:
                continue
            render_artifacts = slide.get("renderArtifacts")
            if not isinstance(render_artifacts, Mapping):
                raise ValueError(f"native report is missing render artifacts: {case_id} slide {slide_index}")
            artifact_values: dict[str, dict[str, Any]] = {}
            for kind, suffix in (("reference", "pdf"), ("candidate", "html")):
                path = reports_dir / f"{case_id}_slide{slide_index}_{suffix}.png"
                artifact = render_artifacts.get(kind)
                if not isinstance(artifact, Mapping):
                    raise ValueError(
                        f"native report is missing {kind} artifact: {case_id} slide {slide_index}"
                    )
                actual = {
                    "path": _repository_relative(path, repo),
                    "sizeBytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
                if any(artifact.get(key) != value for key, value in actual.items()):
                    raise ValueError(
                        f"native report artifact does not match {kind} raster: "
                        f"{case_id} slide {slide_index}"
                    )
                artifact_values[kind] = actual
            reference = np.asarray(
                Image.open(reports_dir / f"{case_id}_slide{slide_index}_pdf.png").convert("RGB")
            )
            candidate = np.asarray(
                Image.open(reports_dir / f"{case_id}_slide{slide_index}_html.png").convert("RGB")
            )
            modality = "plane" if slide_index in plane_slides else "text"
            metrics = (
                compute_camera_plane_metrics(reference, candidate)
                if modality == "plane"
                else compute_text_camera_metrics(reference, candidate)
            )
            slide_results.append(
                {
                    "slideIdx": slide_index,
                    "modality": modality,
                    "referencePath": artifact_values["reference"]["path"],
                    "candidatePath": artifact_values["candidate"]["path"],
                    "referenceSha256": artifact_values["reference"]["sha256"],
                    "candidateSha256": artifact_values["candidate"]["sha256"],
                    "metrics": metrics,
                    "passed": metrics["passed"],
                }
            )
        applicable = bool(applicable_slides)
        passed = applicable and len(slide_results) == len(applicable_slides) and all(
            slide["passed"] for slide in slide_results
        )
        cases.append(
            {
                "caseId": case_id,
                "sourceSha256": source_info.get("sha256"),
                "groundTruthSha256": ground_truth_info.get("combinedSha256"),
                "applicable": applicable,
                "passed": passed,
                "slides": slide_results,
            }
        )
    applicable_count = sum(1 for case in cases if case["applicable"])
    return {
        "schemaVersion": 2,
        "renderer": dict(renderer or {}),
        "thresholds": {
            "plane": {
                "cornerScore": CORNER_SCORE_THRESHOLD,
                "colorScore": COLOR_SCORE_THRESHOLD,
                "gradientRangeRatio": GRADIENT_RANGE_RATIO_THRESHOLD,
                "gradientDirection": GRADIENT_DIRECTION_THRESHOLD,
                "minimumReferenceGradientRange": MIN_REFERENCE_GRADIENT_RANGE,
            },
            "text": {
                "foregroundIou": TEXT_FOREGROUND_IOU_THRESHOLD,
                "boundsScore": TEXT_BOUNDS_SCORE_THRESHOLD,
                "inkCoverageRatio": TEXT_INK_COVERAGE_RATIO_THRESHOLD,
            },
        },
        "caseResults": sorted(cases, key=lambda case: case["caseId"]),
        "applicableCaseCount": applicable_count,
        "passed": applicable_count > 0 and all(case["passed"] for case in cases),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate local Shape 3D camera-plane fidelity")
    parser.add_argument("--repo-root", default=str(PROJECT_ROOT))
    parser.add_argument("--case-report", action="append", required=True)
    parser.add_argument("--reports-dir", default="test/e2e/reports")
    parser.add_argument(
        "--out",
        default="test/e2e/reports/capability-loop/shape3d-camera-local.json",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo_root).resolve()
    reports_dir = Path(args.reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = repo / reports_dir
    output = Path(args.out)
    if not output.is_absolute():
        output = repo / output
    try:
        report = build_camera_report(
            [Path(path) if Path(path).is_absolute() else repo / path for path in args.case_report],
            repo,
            reports_dir,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"evaluated {report['applicableCaseCount']} applicable camera case(s); "
        f"passed={report['passed']} -> {output}"
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
