from __future__ import annotations

import hashlib
import json
from zipfile import ZIP_DEFLATED, ZipFile

import cv2
import numpy as np
import pytest
from PIL import Image

from scripts.shape3d_camera_metrics import (
    build_camera_report,
    compute_camera_plane_metrics,
    extract_camera_slide_indices,
)


def _plane_specimen(
    width: int,
    height: int,
    corners: tuple[tuple[float, float], ...],
    top_color=(75, 148, 214),
    bottom_color=(60, 133, 199),
):
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    points = np.asarray([(round(x * width), round(y * height)) for x, y in corners], np.int32)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillConvexPoly(mask, points, 255)
    top = points[:, 1].min()
    bottom = points[:, 1].max()
    for y in range(max(0, top), min(height, bottom + 1)):
        ratio = (y - top) / max(bottom - top, 1)
        color = np.asarray(top_color) * (1 - ratio) + np.asarray(bottom_color) * ratio
        image[y, mask[y] > 0] = np.rint(color).astype(np.uint8)
    return image


def test_camera_metric_accepts_scaled_equivalent_projection_and_material_field():
    corners = ((0.39, 0.28), (0.61, 0.28), (0.79, 0.82), (0.21, 0.82))
    reference = _plane_specimen(600, 360, corners)
    candidate = _plane_specimen(300, 180, corners)

    metrics = compute_camera_plane_metrics(reference, candidate)

    assert metrics["passed"] is True
    assert metrics["cornerScore"] > 0.995
    assert metrics["colorScore"] > 0.995
    assert metrics["gradientRequired"] is True
    assert metrics["gradientRangeRatio"] > 0.95
    assert metrics["gradientDirection"] > 0.99


def test_camera_metric_rejects_flat_geometry_and_flat_material():
    reference = _plane_specimen(
        600,
        360,
        ((0.39, 0.28), (0.61, 0.28), (0.79, 0.82), (0.21, 0.82)),
    )
    flat = _plane_specimen(
        600,
        360,
        ((0.34, 0.22), (0.66, 0.22), (0.66, 0.78), (0.34, 0.78)),
        top_color=(47, 117, 181),
        bottom_color=(47, 117, 181),
    )

    metrics = compute_camera_plane_metrics(reference, flat)

    assert metrics["passed"] is False
    assert metrics["cornerScore"] < 0.95
    assert metrics["gradientRangeRatio"] == 0
    assert metrics["gradientDirection"] == 0


def test_camera_metric_does_not_require_a_gradient_for_a_native_flat_control():
    corners = ((0.3, 0.25), (0.7, 0.25), (0.7, 0.75), (0.3, 0.75))
    reference = _plane_specimen(400, 240, corners, (54, 127, 193), (54, 127, 193))
    candidate = reference.copy()

    metrics = compute_camera_plane_metrics(reference, candidate)

    assert metrics["gradientRequired"] is False
    assert metrics["passed"] is True


def test_extracts_only_zero_depth_rect_camera_planes(tmp_path):
    source = tmp_path / "camera.pptx"
    presentation = """
      <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
        <p:sldSz cx="1000" cy="500"/>
      </p:presentation>"""
    positive = """
      <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
        <p:cSld><p:spTree><p:sp><p:spPr>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="2F75B5"/></a:solidFill>
          <a:ln><a:noFill/></a:ln>
          <a:scene3d><a:camera prst="orthographicFront"/><a:lightRig rig="threePt" dir="t"/></a:scene3d>
          <a:sp3d extrusionH="0"/>
        </p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp></p:spTree></p:cSld>
      </p:sld>"""
    perspective = positive.replace(
        '<a:camera prst="orthographicFront"/>',
        '<a:camera prst="perspectiveRelaxedModerately" fov="7200000"><a:rot lat="18590633" lon="0" rev="0"/></a:camera>',
    )
    theme = perspective.replace(
        '<a:solidFill><a:srgbClr val="2F75B5"/></a:solidFill>',
        '',
    ).replace(
        '</p:spPr><p:txBody>',
        '</p:spPr><p:style><a:fillRef idx="1"><a:schemeClr val="accent1"/></a:fillRef></p:style><p:txBody>',
    )
    negatives = [
        positive.replace('prst="rect"', 'prst="ellipse"'),
        positive.replace('prst="orthographicFront"', 'prst="perspectiveFront"'),
        positive.replace('<a:lightRig rig="threePt" dir="t"/>', '<a:lightRig rig="twoPt" dir="t"/>'),
        positive.replace('</a:scene3d>', '<a:backdrop/></a:scene3d>'),
        positive.replace('extrusionH="0"', 'z="12700" extrusionH="0"'),
        positive.replace('<a:sp3d extrusionH="0"/>', '<a:sp3d extrusionH="0"><a:extrusionClr><a:srgbClr val="FFFFFF"/></a:extrusionClr></a:sp3d>'),
        positive.replace('<a:p/>', '<a:p><a:r><a:t>Visible</a:t></a:r></a:p>'),
        positive.replace('<a:ln><a:noFill/></a:ln>', '<a:ln><a:solidFill><a:srgbClr val="000000"/></a:solidFill></a:ln>'),
        positive.replace('val="2F75B5"', 'val="70AD47"'),
    ]
    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr(
            "ppt/theme/theme1.xml",
            '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:themeElements><a:clrScheme name="Verified"><a:accent1><a:srgbClr val="4F81BD"/></a:accent1></a:clrScheme></a:themeElements></a:theme>',
        )
        archive.writestr("ppt/slides/slide1.xml", positive)
        archive.writestr("ppt/slides/slide2.xml", perspective)
        archive.writestr("ppt/slides/slide3.xml", theme)
        for index, negative in enumerate(negatives, start=4):
            archive.writestr(f"ppt/slides/slide{index}.xml", negative)

    assert extract_camera_slide_indices(source) == {0, 1, 2}

    wrong_theme = tmp_path / "camera-wrong-theme.pptx"
    with ZipFile(source) as source_archive, ZipFile(wrong_theme, "w", ZIP_DEFLATED) as target:
        for name in source_archive.namelist():
            data = source_archive.read(name)
            if name == "ppt/theme/theme1.xml":
                data = data.replace(b"4F81BD", b"4472C4")
            target.writestr(name, data)
    assert extract_camera_slide_indices(wrong_theme) == {0, 1}


def test_camera_report_binds_exact_native_rasters_and_rejects_hash_drift(tmp_path):
    repo = tmp_path / "repo"
    case_id = "camera-case"
    source = repo / f"test/e2e/testdata/cases/{case_id}/source.pptx"
    source.parent.mkdir(parents=True)
    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "ppt/presentation.xml",
            '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldSz cx="1000" cy="500"/></p:presentation>',
        )
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="2F75B5"/></a:solidFill><a:ln><a:noFill/></a:ln><a:scene3d><a:camera prst="orthographicFront"/><a:lightRig rig="threePt" dir="t"/></a:scene3d><a:sp3d extrusionH="0"/></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp></p:spTree></p:cSld></p:sld>',
        )
    image = _plane_specimen(
        300,
        180,
        ((0.3, 0.25), (0.7, 0.25), (0.7, 0.75), (0.3, 0.75)),
        (54, 127, 193),
        (54, 127, 193),
    )
    reports_dir = repo / "test/e2e/reports"
    reports_dir.mkdir(parents=True)
    reference_path = reports_dir / f"{case_id}_slide0_pdf.png"
    candidate_path = reports_dir / f"{case_id}_slide0_html.png"
    Image.fromarray(image).save(reference_path)
    Image.fromarray(image).save(candidate_path)

    def artifact(path):
        return {
            "path": path.relative_to(repo).as_posix(),
            "sizeBytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    native = {
        "testFile": case_id,
        "provenance": {
            "renderer": {"revision": "a" * 40, "dirty": False},
            "inputs": {
                "sourcePptx": {
                    "path": source.relative_to(repo).as_posix(),
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                },
                "groundTruth": {"combinedSha256": "f" * 64},
            },
        },
        "perSlide": [
            {
                "slideIdx": 0,
                "hidden": False,
                "renderArtifacts": {
                    "reference": artifact(reference_path),
                    "candidate": artifact(candidate_path),
                },
            }
        ],
    }
    native_path = repo / "native.json"
    native_path.write_text(json.dumps(native), encoding="utf-8")

    report = build_camera_report([native_path], repo, reports_dir)
    assert report["passed"] is True
    assert report["caseResults"][0]["slides"][0]["metrics"]["cornerScore"] > 0.99

    native["perSlide"][0]["renderArtifacts"]["candidate"]["sha256"] = "0" * 64
    native_path.write_text(json.dumps(native), encoding="utf-8")
    with pytest.raises(ValueError, match="native report artifact"):
        build_camera_report([native_path], repo, reports_dir)
