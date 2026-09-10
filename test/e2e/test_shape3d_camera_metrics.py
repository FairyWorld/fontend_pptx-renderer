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
    compute_picture_camera_metrics,
    compute_text_camera_metrics,
    extract_camera_shadow_slide_indices,
    extract_camera_slide_indices,
    extract_picture_camera_slide_indices,
    extract_text_camera_slide_indices,
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


def _shadowed_plane_specimen(
    width: int,
    height: int,
    corners: tuple[tuple[float, float], ...],
):
    image = _plane_specimen(width, height, corners)
    points = np.asarray([(round(x * width), round(y * height)) for x, y in corners], np.int32)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillConvexPoly(mask, points, 255)
    shift_y = max(1, round(height / 36))
    sigma = max(1.0, height / 45)
    shifted = np.zeros_like(mask)
    shifted[shift_y:] = mask[:-shift_y]
    shadow = (
        cv2.GaussianBlur(shifted, (0, 0), sigmaX=sigma, sigmaY=sigma).astype(np.float64) / 255
    )
    background = np.full_like(image, 255, dtype=np.float64)
    background -= shadow[..., None] * 80
    background[mask > 0] = image[mask > 0]
    return np.rint(background).astype(np.uint8)


def _picture_plane_specimen(
    width: int,
    height: int,
    corners: tuple[tuple[float, float], ...],
    *,
    crop_left: float = 0,
):
    source = np.zeros((240, 320, 3), dtype=np.uint8)
    source[..., 0] = np.linspace(20, 80, source.shape[1], dtype=np.uint8)
    source[..., 1] = np.linspace(80, 180, source.shape[1], dtype=np.uint8)
    source[..., 2] = 190
    cv2.rectangle(source, (24, 20), (295, 218), (250, 205, 65), 8)
    cv2.ellipse(source, (160, 120), (45, 62), 0, 0, 360, (245, 245, 245), -1)
    cv2.ellipse(source, (160, 120), (45, 62), 0, 0, 360, (25, 45, 70), 6)
    left = min(source.shape[1] - 2, round(source.shape[1] * crop_left))
    source = source[:, left:]
    destination = np.asarray(
        [(round(x * width), round(y * height)) for x, y in corners], dtype=np.float32
    )
    source_corners = np.asarray(
        [
            [0, 0],
            [source.shape[1] - 1, 0],
            [source.shape[1] - 1, source.shape[0] - 1],
            [0, source.shape[0] - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source_corners, destination)
    image = cv2.warpPerspective(
        source,
        transform,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    plane_mask = cv2.warpPerspective(
        np.full(source.shape[:2], 255, dtype=np.uint8),
        transform,
        (width, height),
        flags=cv2.INTER_NEAREST,
    )
    image[plane_mask == 0] = 255
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


def test_camera_metric_requires_native_shadow_energy_outside_the_projected_plane():
    corners = ((0.39, 0.28), (0.61, 0.28), (0.79, 0.82), (0.21, 0.82))
    reference = _shadowed_plane_specimen(600, 360, corners)
    candidate = _shadowed_plane_specimen(300, 180, corners)
    missing_shadow = _plane_specimen(300, 180, corners)

    present = compute_camera_plane_metrics(reference, candidate, shadow_required=True)
    missing = compute_camera_plane_metrics(reference, missing_shadow, shadow_required=True)

    assert present["shadowRequired"] is True
    assert present["shadowMeasurable"] is True
    assert present["shadowPassed"] is True
    assert present["shadowSensitivity"]["mutation"] == "erase-exterior-shadow"
    assert present["shadowSensitivity"]["applicable"] is True
    assert present["shadowSensitivity"]["mutatedShadowPassed"] is False
    assert present["shadowSensitivity"]["detected"] is True
    assert present["passed"] is True
    assert missing["cornerScore"] > 0.995
    assert missing["colorScore"] > 0.995
    assert missing["shadowEnergyRatio"] < present["thresholds"]["shadowEnergyRatio"]
    assert missing["shadowPassed"] is False
    assert missing["passed"] is False


def test_camera_metric_rejects_a_visible_but_materially_weaker_shadow():
    corners = ((0.39, 0.28), (0.61, 0.28), (0.79, 0.82), (0.21, 0.82))
    reference = _shadowed_plane_specimen(600, 360, corners)
    full_shadow = _shadowed_plane_specimen(300, 180, corners)
    flat = _plane_specimen(300, 180, corners).astype(np.float64)
    weak_shadow = np.rint(flat * 0.55 + full_shadow.astype(np.float64) * 0.45).astype(np.uint8)

    metrics = compute_camera_plane_metrics(reference, weak_shadow, shadow_required=True)

    assert 0.18 < metrics["shadowEnergyRatio"] < 0.70
    assert metrics["shadowPassed"] is False
    assert metrics["passed"] is False


def test_picture_camera_metric_rectifies_projection_and_rejects_wrong_source_crop():
    corners = ((0.34, 0.22), (0.67, 0.27), (0.67, 0.78), (0.34, 0.83))
    reference = _picture_plane_specimen(800, 450, corners)
    candidate = _picture_plane_specimen(400, 225, corners)
    wrong_crop = _picture_plane_specimen(400, 225, corners, crop_left=0.22)

    matching = compute_picture_camera_metrics(reference, candidate)
    mismatched = compute_picture_camera_metrics(reference, wrong_crop)

    assert matching["passed"] is True
    assert matching["cornerScore"] > 0.995
    assert matching["rectifiedColorScore"] > 0.98
    assert matching["rectifiedEdgeF1"] > 0.95
    assert matching["cropSensitivity"]["mutation"] == "left-crop-and-rescale"
    assert matching["cropSensitivity"]["cropRatio"] == 0.12
    assert matching["cropSensitivity"]["mutatedPassed"] is False
    assert matching["cropSensitivity"]["detected"] is True
    assert mismatched["cornerScore"] > 0.995
    assert mismatched["rectifiedEdgeF1"] < matching["thresholds"]["rectifiedEdgeF1"]
    assert mismatched["passed"] is False


def _text_specimen(width: int, height: int, *, offset_x: int = 0, offset_y: int = 0):
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    for row, label in enumerate(("ZERO DEPTH", "EDITABLE TEXT", "NATIVE CAMERA")):
        cv2.putText(
            image,
            label,
            (
                round(width * 0.38) + offset_x,
                round(height * (0.43 + row * 0.07)) + offset_y,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            width / 1800,
            (32, 56, 100),
            max(1, round(width / 700)),
            cv2.LINE_AA,
        )
    return image


def test_text_camera_metric_accepts_scaled_equivalent_live_text_projection():
    reference = _text_specimen(1200, 675)
    candidate = cv2.resize(reference, (640, 360), interpolation=cv2.INTER_LINEAR)

    metrics = compute_text_camera_metrics(reference, candidate)

    assert metrics["passed"] is True
    assert metrics["foregroundIou"] > 0.8
    assert metrics["boundsScore"] > 0.99
    assert metrics["tolerantForegroundF1"] > 0.99
    assert metrics["tolerantBoundsScore"] > 0.99


def test_text_camera_metric_tolerates_small_font_raster_offset_but_keeps_raw_diagnostics():
    reference = _text_specimen(1200, 675)
    shifted = _text_specimen(1200, 675, offset_y=-3)

    metrics = compute_text_camera_metrics(reference, shifted)

    assert metrics["foregroundIou"] < 0.72
    assert metrics["boundsScore"] < 0.99
    assert metrics["rasterTolerancePx"] == 3
    assert metrics["tolerantForegroundF1"] > 0.90
    assert metrics["tolerantBoundsScore"] > 0.99
    assert metrics["passed"] is True


def test_text_camera_metric_rejects_unprojected_position_drift():
    reference = _text_specimen(1200, 675)
    shifted = _text_specimen(1200, 675, offset_x=-100)

    metrics = compute_text_camera_metrics(reference, shifted)

    assert metrics["passed"] is False
    assert metrics["foregroundIou"] < 0.5
    assert metrics["tolerantForegroundF1"] < 0.5


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
    implicit_zero_depth = perspective.replace('<a:sp3d extrusionH="0"/>', '')
    unverified_implicit_orthographic = positive.replace('<a:sp3d extrusionH="0"/>', '')
    text_plane = positive.replace(
        '<a:solidFill><a:srgbClr val="2F75B5"/></a:solidFill>\n          <a:ln><a:noFill/></a:ln>',
        '<a:noFill/>',
    ).replace(
        '<a:camera prst="orthographicFront"/>',
        '<a:camera prst="perspectiveContrastingRightFacing" fov="5100000"><a:rot lat="0" lon="19532225" rev="0"/></a:camera>',
    ).replace(
        '<a:sp3d extrusionH="0"/>',
        '',
    ).replace(
        '<a:bodyPr/><a:lstStyle/><a:p/>',
        '<a:bodyPr wrap="none" anchor="ctr"><a:spAutoFit/></a:bodyPr><a:lstStyle/><a:p><a:r><a:t>Visible text</a:t></a:r></a:p>',
    )
    unverified_text_plane = text_plane.replace('wrap="none"', 'wrap="square"')
    perspective_left_text_plane = text_plane.replace(
        '<a:camera prst="perspectiveContrastingRightFacing" fov="5100000"><a:rot lat="0" lon="19532225" rev="0"/></a:camera>',
        '<a:camera prst="perspectiveLeft" fov="7200000"/>',
    ).replace(' anchor="ctr"', '')
    perspective_left_with_explicit_rotation = perspective_left_text_plane.replace(
        '<a:camera prst="perspectiveLeft" fov="7200000"/>',
        '<a:camera prst="perspectiveLeft" fov="7200000"><a:rot lat="0" lon="1200000" rev="0"/></a:camera>',
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
        archive.writestr("ppt/slides/slide4.xml", implicit_zero_depth)
        archive.writestr("ppt/slides/slide5.xml", unverified_implicit_orthographic)
        archive.writestr("ppt/slides/slide6.xml", text_plane)
        archive.writestr("ppt/slides/slide7.xml", perspective_left_text_plane)
        archive.writestr("ppt/slides/slide8.xml", unverified_text_plane)
        archive.writestr("ppt/slides/slide9.xml", perspective_left_with_explicit_rotation)
        for index, negative in enumerate(negatives, start=10):
            archive.writestr(f"ppt/slides/slide{index}.xml", negative)

    assert extract_camera_slide_indices(source) == {0, 1, 2, 3}
    assert extract_text_camera_slide_indices(source) == {5, 6}

    wrong_theme = tmp_path / "camera-wrong-theme.pptx"
    with ZipFile(source) as source_archive, ZipFile(wrong_theme, "w", ZIP_DEFLATED) as target:
        for name in source_archive.namelist():
            data = source_archive.read(name)
            if name == "ppt/theme/theme1.xml":
                data = data.replace(b"4F81BD", b"4472C4")
            target.writestr(name, data)
    assert extract_camera_slide_indices(wrong_theme) == {0, 1, 3}
    assert extract_text_camera_slide_indices(wrong_theme) == {5, 6}


def test_extracts_exact_theme_shadow_contract_for_solid_camera_planes(tmp_path):
    source = tmp_path / "camera-shadow.pptx"
    shape = """
      <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
        <p:cSld><p:spTree><p:sp><p:spPr>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="2F75B5"/></a:solidFill><a:ln><a:noFill/></a:ln>
          <a:scene3d><a:camera prst="perspectiveRelaxedModerately" fov="7200000"><a:rot lat="18590633" lon="0" rev="0"/></a:camera><a:lightRig rig="threePt" dir="t"/></a:scene3d>
        </p:spPr><p:style><a:effectRef idx="EFFECT_INDEX"><a:schemeClr val="accent1"/></a:effectRef></p:style><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp></p:spTree></p:cSld>
      </p:sld>"""
    theme = """
      <a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:themeElements>
        <a:clrScheme name="Verified"><a:accent1><a:srgbClr val="4F81BD"/></a:accent1></a:clrScheme>
        <a:fmtScheme name="Verified"><a:effectStyleLst>
          <a:effectStyle><a:effectLst/></a:effectStyle>
          <a:effectStyle><a:effectLst><a:outerShdw blurRad="40000" dist="23000" dir="5400000" rotWithShape="0"><a:srgbClr val="000000"><a:alpha val="35000"/></a:srgbClr></a:outerShdw></a:effectLst></a:effectStyle>
        </a:effectStyleLst></a:fmtScheme>
      </a:themeElements></a:theme>"""
    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
        archive.writestr("ppt/theme/theme1.xml", theme)
        archive.writestr("ppt/slides/slide1.xml", shape.replace("EFFECT_INDEX", "2"))
        archive.writestr("ppt/slides/slide2.xml", shape.replace("EFFECT_INDEX", "0"))

    assert extract_camera_slide_indices(source) == {0, 1}
    assert extract_camera_shadow_slide_indices(source) == {0}

    wrong_theme = tmp_path / "camera-shadow-wrong-theme.pptx"
    with ZipFile(source) as source_archive, ZipFile(wrong_theme, "w", ZIP_DEFLATED) as target:
        for name in source_archive.namelist():
            data = source_archive.read(name)
            if name == "ppt/theme/theme1.xml":
                data = data.replace(b'alpha val="35000"', b'alpha val="34000"')
            target.writestr(name, data)
    assert extract_camera_slide_indices(wrong_theme) == {1}
    assert extract_camera_shadow_slide_indices(wrong_theme) == set()


def test_extracts_only_exact_perspective_right_picture_plane_tuple(tmp_path):
    source = tmp_path / "camera-picture.pptx"
    positive = """
      <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        <p:cSld><p:spTree><p:pic><p:nvPicPr/><p:blipFill>
          <a:blip r:embed="rId2"/><a:srcRect l="22000" r="8000"/><a:stretch/>
        </p:blipFill><p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="1000" cy="500"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:scene3d><a:camera prst="perspectiveRight" fov="5700000"/><a:lightRig rig="threePt" dir="t"/></a:scene3d>
        </p:spPr></p:pic></p:spTree></p:cSld>
      </p:sld>"""
    negatives = [
        positive.replace("<a:stretch/>", "<a:stretch><a:fillRect/></a:stretch>"),
        positive.replace("<a:blip r:embed=\"rId2\"/>", "<a:blip r:embed=\"rId2\"><a:alphaModFix amt=\"50000\"/></a:blip>"),
        positive.replace("l=\"22000\" r=\"8000\"", "l=\"99000\" r=\"1000\""),
        positive.replace(
            '<a:camera prst="perspectiveRight" fov="5700000"/>',
            '<a:camera prst="perspectiveRight" fov="5700000"><a:rot lat="0" lon="0" rev="0"/></a:camera>',
        ),
    ]
    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", positive)
        for index, negative in enumerate(negatives, start=2):
            archive.writestr(f"ppt/slides/slide{index}.xml", negative)

    assert extract_picture_camera_slide_indices(source) == {0}


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
