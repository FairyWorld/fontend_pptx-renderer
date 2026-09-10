from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from zipfile import ZipFile

from lxml import etree


GENERATOR_PATH = Path(__file__).resolve().parent / "scripts" / "generate_pypptx_cases.py"

FLOWCHART_ZERO_ADJUSTMENT_CASES = {
    "oracle-pypptx-flowchart-0061-process": "flowChartProcess",
    "oracle-pypptx-flowchart-0062-alternate-process": "flowChartAlternateProcess",
    "oracle-pypptx-flowchart-0063-decision": "flowChartDecision",
    "oracle-pypptx-flowchart-0064-input-output": "flowChartInputOutput",
    "oracle-pypptx-flowchart-0065-predefined-process": "flowChartPredefinedProcess",
    "oracle-pypptx-flowchart-0066-internal-storage": "flowChartInternalStorage",
    "oracle-pypptx-flowchart-0067-document": "flowChartDocument",
    "oracle-pypptx-flowchart-0068-multidocument": "flowChartMultidocument",
    "oracle-pypptx-flowchart-0069-terminator": "flowChartTerminator",
    "oracle-pypptx-flowchart-0070-preparation": "flowChartPreparation",
    "oracle-pypptx-flowchart-0071-manual-input": "flowChartManualInput",
    "oracle-pypptx-flowchart-0072-manual-operation": "flowChartManualOperation",
    "oracle-pypptx-flowchart-0073-connector": "flowChartConnector",
    "oracle-pypptx-flowchart-0074-offpage-connector": "flowChartOffpageConnector",
    "oracle-pypptx-flowchart-0075-punched-card": "flowChartPunchedCard",
    "oracle-pypptx-flowchart-0076-punched-tape": "flowChartPunchedTape",
    "oracle-pypptx-flowchart-0077-summing-junction": "flowChartSummingJunction",
    "oracle-pypptx-flowchart-0078-or": "flowChartOr",
    "oracle-pypptx-flowchart-0079-collate": "flowChartCollate",
    "oracle-pypptx-flowchart-0080-sort": "flowChartSort",
    "oracle-pypptx-flowchart-0081-extract": "flowChartExtract",
    "oracle-pypptx-flowchart-0082-merge": "flowChartMerge",
    "oracle-pypptx-flowchart-0083-online-storage": "flowChartOnlineStorage",
    "oracle-pypptx-flowchart-0084-delay": "flowChartDelay",
    "oracle-pypptx-flowchart-0085-magnetic-tape": "flowChartMagneticTape",
    "oracle-pypptx-flowchart-0086-magnetic-disk": "flowChartMagneticDisk",
    "oracle-pypptx-flowchart-0087-magnetic-drum": "flowChartMagneticDrum",
    "oracle-pypptx-flowchart-0088-display": "flowChartDisplay",
}


def _load_generator_module():
    spec = importlib.util.spec_from_file_location("generate_pypptx_cases", GENERATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _placeholder_attrs(zf: ZipFile, part: str) -> list[dict[str, str]]:
    root = etree.fromstring(zf.read(part))
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    return [dict(ph.attrib) for ph in root.xpath(".//p:ph", namespaces=ns)]


def test_placeholder_idx_inheritance_case_generates_idx_only_slide_placeholders(
    tmp_path: Path,
):
    generator = _load_generator_module()
    case_defs = generator._build_all_case_defs()
    case = next(
        c for c in case_defs if c["name"] == "oracle-pypptx-text-0039-placeholder-idx-inheritance"
    )
    pptx_path = tmp_path / "source.pptx"

    generator._generate_pptx(case, pptx_path)

    with ZipFile(pptx_path) as zf:
        slide_placeholders = _placeholder_attrs(zf, "ppt/slides/slide1.xml")
        layout_placeholders = _placeholder_attrs(zf, "ppt/slideLayouts/slideLayout2.xml")
        master_placeholders = _placeholder_attrs(zf, "ppt/slideMasters/slideMaster1.xml")

    assert {"idx": "0"} in slide_placeholders
    assert {"idx": "1"} in slide_placeholders
    assert {"type": "title", "idx": "0"} in layout_placeholders
    assert {"type": "body", "idx": "1"} in master_placeholders


def test_cjk_text_layout_matrix_is_registered():
    generator = _load_generator_module()
    case_defs = generator._build_all_case_defs()
    text_names = [
        case["name"] for case in case_defs if case["name"].startswith("oracle-pypptx-text-")
    ]

    expected_names = {
        "oracle-pypptx-text-0040-cjk-wrap-square-no-autofit",
        "oracle-pypptx-text-0041-cjk-wrap-square-implicit-autofit",
        "oracle-pypptx-text-0042-cjk-wrap-none-no-autofit",
        "oracle-pypptx-text-0043-cjk-sp-autofit-narrow",
        "oracle-pypptx-text-0044-cjk-norm-autofit-scaled",
        "oracle-pypptx-text-0045-cjk-line-spacing-100pct",
        "oracle-pypptx-text-0046-cjk-line-spacing-130pct",
        "oracle-pypptx-text-0047-cjk-line-spacing-28pt",
        "oracle-pypptx-text-0048-cjk-paragraph-spacing-points",
        "oracle-pypptx-text-0049-cjk-paragraph-spacing-percent",
        "oracle-pypptx-text-0050-cjk-mixed-run-character-spacing",
        "oracle-pypptx-text-0051-cjk-rounded-shape-centered-spacing",
        "oracle-pypptx-text-0052-cjk-sp-autofit-square-growth",
        "oracle-pypptx-text-0053-cjk-sp-autofit-tall-growth",
        "oracle-pypptx-text-0054-cjk-sp-autofit-wide-compact",
        "oracle-pypptx-text-0055-cjk-sp-autofit-explicit-overflow",
        "oracle-pypptx-text-0056-defrpr-srgb-over-fontref-square",
        "oracle-pypptx-text-0057-defrpr-scheme-over-fontref-wide",
        "oracle-pypptx-text-0058-run-color-over-defrpr-tall",
        "oracle-pypptx-text-0059-fontref-fallback-no-defrpr",
    }

    assert expected_names.issubset(text_names)
    assert len(text_names) == 59


def test_cjk_text_layout_matrix_serializes_autofit_and_spacing_ooxml(tmp_path: Path):
    generator = _load_generator_module()
    case_defs = generator._build_all_case_defs()
    wanted = {
        "oracle-pypptx-text-0040-cjk-wrap-square-no-autofit",
        "oracle-pypptx-text-0044-cjk-norm-autofit-scaled",
        "oracle-pypptx-text-0046-cjk-line-spacing-130pct",
        "oracle-pypptx-text-0049-cjk-paragraph-spacing-percent",
        "oracle-pypptx-text-0050-cjk-mixed-run-character-spacing",
        "oracle-pypptx-text-0051-cjk-rounded-shape-centered-spacing",
        "oracle-pypptx-text-0052-cjk-sp-autofit-square-growth",
        "oracle-pypptx-text-0053-cjk-sp-autofit-tall-growth",
        "oracle-pypptx-text-0054-cjk-sp-autofit-wide-compact",
        "oracle-pypptx-text-0055-cjk-sp-autofit-explicit-overflow",
    }
    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    roots = {}

    for case in case_defs:
        if case["name"] not in wanted:
            continue
        pptx_path = tmp_path / case["name"] / "source.pptx"
        generator._generate_pptx(case, pptx_path)
        with ZipFile(pptx_path) as zf:
            roots[case["name"]] = etree.fromstring(zf.read("ppt/slides/slide1.xml"))

    no_autofit = roots["oracle-pypptx-text-0040-cjk-wrap-square-no-autofit"]
    assert no_autofit.xpath("boolean(.//a:bodyPr[@wrap='square']/a:noAutofit)", namespaces=ns)

    norm_autofit = roots["oracle-pypptx-text-0044-cjk-norm-autofit-scaled"]
    assert norm_autofit.xpath(
        "boolean(.//a:normAutofit[@fontScale='85000'][@lnSpcReduction='10000'])",
        namespaces=ns,
    )

    line_spacing = roots["oracle-pypptx-text-0046-cjk-line-spacing-130pct"]
    assert line_spacing.xpath(
        "boolean(.//a:pPr/a:lnSpc/a:spcPct[@val='130000'])",
        namespaces=ns,
    )
    assert len(line_spacing.xpath(".//a:p/a:br", namespaces=ns)) == 2
    assert all(
        "_x000B_" not in text
        for text in line_spacing.xpath(".//a:p/a:r/a:t/text()", namespaces=ns)
    )

    centered_shape = roots["oracle-pypptx-text-0051-cjk-rounded-shape-centered-spacing"]
    assert len(centered_shape.xpath(".//a:p/a:br", namespaces=ns)) == 2
    assert all(
        "_x000B_" not in text
        for text in centered_shape.xpath(".//a:p/a:r/a:t/text()", namespaces=ns)
    )

    paragraph_spacing = roots["oracle-pypptx-text-0049-cjk-paragraph-spacing-percent"]
    assert paragraph_spacing.xpath(
        "boolean(.//a:pPr/a:spcBef/a:spcPct[@val='30000'])",
        namespaces=ns,
    )
    assert paragraph_spacing.xpath(
        "boolean(.//a:pPr/a:spcAft/a:spcPct[@val='50000'])",
        namespaces=ns,
    )

    mixed_runs = roots["oracle-pypptx-text-0050-cjk-mixed-run-character-spacing"]
    assert mixed_runs.xpath("boolean(.//a:rPr[@spc='180'])", namespaces=ns)
    assert mixed_runs.xpath("boolean(.//a:rPr[@spc='-120'])", namespaces=ns)

    square = roots["oracle-pypptx-text-0052-cjk-sp-autofit-square-growth"]
    square_ext = square.xpath(".//p:sp/p:spPr/a:xfrm/a:ext", namespaces=ns)[0]
    assert square_ext.get("cx") == square_ext.get("cy")
    assert square.xpath("boolean(.//a:bodyPr[@wrap='square']/a:spAutoFit)", namespaces=ns)

    tall = roots["oracle-pypptx-text-0053-cjk-sp-autofit-tall-growth"]
    tall_ext = tall.xpath(".//p:sp/p:spPr/a:xfrm/a:ext", namespaces=ns)[0]
    assert int(tall_ext.get("cy")) > int(tall_ext.get("cx"))
    assert tall.xpath("boolean(.//a:bodyPr[@wrap='square']/a:spAutoFit)", namespaces=ns)

    wide = roots["oracle-pypptx-text-0054-cjk-sp-autofit-wide-compact"]
    wide_ext = wide.xpath(".//p:sp/p:spPr/a:xfrm/a:ext", namespaces=ns)[0]
    assert int(wide_ext.get("cx")) > 10 * int(wide_ext.get("cy"))
    assert wide.xpath("boolean(.//a:bodyPr[@wrap='square']/a:spAutoFit)", namespaces=ns)

    explicit_overflow = roots["oracle-pypptx-text-0055-cjk-sp-autofit-explicit-overflow"]
    assert explicit_overflow.xpath(
        "boolean(.//a:bodyPr[@wrap='none'][@horzOverflow='overflow'][@vertOverflow='overflow']/a:spAutoFit)",
        namespaces=ns,
    )


def test_defrpr_color_precedence_matrix_serializes_exact_ooxml(tmp_path: Path):
    generator = _load_generator_module()
    wanted = {
        "oracle-pypptx-text-0056-defrpr-srgb-over-fontref-square",
        "oracle-pypptx-text-0057-defrpr-scheme-over-fontref-wide",
        "oracle-pypptx-text-0058-run-color-over-defrpr-tall",
        "oracle-pypptx-text-0059-fontref-fallback-no-defrpr",
    }
    cases = {
        case["name"]: case
        for case in generator._build_all_case_defs()
        if case["name"] in wanted
    }
    assert set(cases) == wanted

    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    roots = {}
    for name, case in cases.items():
        pptx_path = tmp_path / name / "source.pptx"
        generator._generate_pptx(case, pptx_path)
        with ZipFile(pptx_path) as zf:
            roots[name] = etree.fromstring(zf.read("ppt/slides/slide1.xml"))

    square = roots["oracle-pypptx-text-0056-defrpr-srgb-over-fontref-square"]
    square_ext = square.xpath(".//p:sp/p:spPr/a:xfrm/a:ext", namespaces=ns)[0]
    assert square_ext.get("cx") == square_ext.get("cy")
    assert square.xpath(
        "boolean(.//p:sp/p:style/a:fontRef/a:schemeClr[@val='accent1'])",
        namespaces=ns,
    )
    assert square.xpath(
        "boolean(.//a:pPr/a:defRPr/a:solidFill/a:srgbClr[@val='C00000'])",
        namespaces=ns,
    )
    assert not square.xpath(".//a:r/a:rPr/a:solidFill", namespaces=ns)

    wide = roots["oracle-pypptx-text-0057-defrpr-scheme-over-fontref-wide"]
    wide_ext = wide.xpath(".//p:sp/p:spPr/a:xfrm/a:ext", namespaces=ns)[0]
    assert int(wide_ext.get("cx")) > int(wide_ext.get("cy"))
    assert wide.xpath(
        "boolean(.//a:pPr/a:defRPr/a:solidFill/a:schemeClr[@val='accent2'])",
        namespaces=ns,
    )

    tall = roots["oracle-pypptx-text-0058-run-color-over-defrpr-tall"]
    tall_ext = tall.xpath(".//p:sp/p:spPr/a:xfrm/a:ext", namespaces=ns)[0]
    assert int(tall_ext.get("cy")) > int(tall_ext.get("cx"))
    assert tall.xpath(
        "boolean(.//a:pPr/a:defRPr/a:solidFill/a:schemeClr[@val='accent2'])",
        namespaces=ns,
    )
    assert tall.xpath(
        "boolean(.//a:r/a:rPr/a:solidFill/a:srgbClr[@val='7030A0'])",
        namespaces=ns,
    )

    inverse = roots["oracle-pypptx-text-0059-fontref-fallback-no-defrpr"]
    assert inverse.xpath(
        "boolean(.//p:sp/p:style/a:fontRef/a:schemeClr[@val='accent1'])",
        namespaces=ns,
    )
    assert not inverse.xpath(".//a:pPr/a:defRPr/a:solidFill", namespaces=ns)
    assert not inverse.xpath(".//a:r/a:rPr/a:solidFill", namespaces=ns)


def test_case_pattern_selection_supports_exact_and_glob_filters():
    generator = _load_generator_module()
    case_defs = generator._build_all_case_defs()

    selected = generator._select_case_defs(
        case_defs,
        [
            "oracle-pypptx-text-0045-cjk-line-spacing-100pct",
            "oracle-pypptx-text-004[89]-*",
        ],
    )

    assert [case["name"] for case in selected] == [
        "oracle-pypptx-text-0045-cjk-line-spacing-100pct",
        "oracle-pypptx-text-0048-cjk-paragraph-spacing-points",
        "oracle-pypptx-text-0049-cjk-paragraph-spacing-percent",
    ]


def test_case_artifact_record_fingerprints_pdf_and_slide_pngs(tmp_path: Path):
    generator = _load_generator_module()
    pptx_path = tmp_path / "source.pptx"
    pdf_path = tmp_path / "ground-truth.pdf"
    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    pptx_path.write_bytes(b"pptx")
    pdf_path.write_bytes(b"pdf")
    (slides_dir / "slide2.png").write_bytes(b"png-2")
    (slides_dir / "slide1.png").write_bytes(b"png-1")

    record = generator._case_artifact_record(
        "sample",
        "generated",
        pptx_path,
        pdf_path,
        slides_dir,
    )

    assert record["source_pptx"]["sha256"]
    assert record["ground_truth_pdf"]["sha256"]
    assert [item["name"] for item in record["ground_truth_pngs"]] == [
        "slide1.png",
        "slide2.png",
    ]
    assert all(item["sha256"] for item in record["ground_truth_pngs"])


def test_generator_uses_one_shared_powerpoint_runtime_directory(
    tmp_path: Path,
    monkeypatch,
):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"] == "oracle-pypptx-text-0040-cjk-wrap-square-no-autofit"
    )
    captured = {}

    def fake_export(pptx_path, pdf_path, **kwargs):
        captured["runtime_dir"] = kwargs.get("runtime_dir")
        Path(pdf_path).write_bytes(b"%PDF-1.4\n")

    import oracle.powerpoint_oracle as powerpoint_oracle

    monkeypatch.setattr(generator, "_build_all_case_defs", lambda **_kwargs: [case])
    monkeypatch.setattr(powerpoint_oracle, "export_pptx_ground_truth", fake_export)

    cases_dir = tmp_path / "definitions"
    testdata_dir = tmp_path / "testdata"
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(GENERATOR_PATH),
            "--cases-dir",
            str(cases_dir),
            "--testdata-dir",
            str(testdata_dir),
            "--report-path",
            str(report_path),
            "--no-export-png",
            "--no-reuse",
        ],
    )

    assert generator.main() == 0
    assert captured["runtime_dir"] == (testdata_dir / "oracle-runtime").resolve()


def test_cjk_case_json_records_coverage_and_font_requirements(tmp_path: Path):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"] == "oracle-pypptx-text-0044-cjk-norm-autofit-scaled"
    )

    path = generator._write_case_json(case, tmp_path)
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))

    assert payload["coverage"]["oracle"] == "native-powerpoint"
    assert payload["coverage"]["requiredFonts"] == ["Microsoft YaHei"]
    assert "bodyPr.normAutofit" in payload["coverage"]["features"]
    assert "normAutofit.fontScale=85000" in payload["coverage"]["features"]


def test_complex_composite_cases_are_registered():
    generator = _load_generator_module()
    case_defs = generator._build_all_case_defs()
    names = {case["name"] for case in case_defs}

    expected_names = {
        "oracle-pypptx-composite-0011-process-flow-connectors",
        "oracle-pypptx-composite-0012-merged-table-callouts",
        "oracle-pypptx-composite-0013-rotated-text-and-shapes",
        "oracle-pypptx-composite-0014-chart-table-callout-overlay",
        "oracle-pypptx-composite-0015-layered-transparent-shapes",
        "oracle-pypptx-composite-0016-dense-cjk-bullet-cards",
        "oracle-pypptx-composite-0017-scaled-group-diagram",
        "oracle-pypptx-composite-0018-vertical-text-with-table",
        "oracle-pypptx-composite-0019-mixed-dash-connectors",
        "oracle-pypptx-composite-0020-mini-report-all-systems",
    }
    composite_names = [name for name in names if name.startswith("oracle-pypptx-composite-")]

    assert expected_names.issubset(names)
    assert len(composite_names) >= 20


def test_scaled_group_composite_case_generates_non_identity_group_space(tmp_path: Path):
    generator = _load_generator_module()
    case_defs = generator._build_all_case_defs()
    case = next(c for c in case_defs if c["name"] == "oracle-pypptx-composite-0017-scaled-group-diagram")
    pptx_path = tmp_path / "source.pptx"

    generator._generate_pptx(case, pptx_path)

    with ZipFile(pptx_path) as zf:
        root = etree.fromstring(zf.read("ppt/slides/slide1.xml"))

    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    group_xfrm = root.xpath(".//p:grpSp/p:grpSpPr/a:xfrm", namespaces=ns)
    group_children = root.xpath(".//p:grpSp/p:sp", namespaces=ns)

    assert group_xfrm
    assert len(group_children) >= 3
    assert group_xfrm[0].xpath("a:ext/@cx", namespaces=ns) != group_xfrm[0].xpath(
        "a:chExt/@cx",
        namespaces=ns,
    )
    assert group_xfrm[0].xpath("a:ext/@cy", namespaces=ns) != group_xfrm[0].xpath(
        "a:chExt/@cy",
        namespaces=ns,
    )


def test_flowchart_zero_adjustment_matrix_is_registered():
    generator = _load_generator_module()
    cases = {
        case["name"]: case
        for case in generator._build_all_case_defs()
        if case["name"].startswith("oracle-pypptx-flowchart-")
    }

    assert set(cases) == set(FLOWCHART_ZERO_ADJUSTMENT_CASES)
    assert all(case["slide_count"] == 3 for case in cases.values())
    assert all(case["coverage"]["oracle"] == "native-powerpoint" for case in cases.values())


def test_flowchart_zero_adjustment_matrix_serializes_three_aspects_and_paints(tmp_path: Path):
    generator = _load_generator_module()
    cases = {
        case["name"]: case
        for case in generator._build_all_case_defs()
        if case["name"] in FLOWCHART_ZERO_ADJUSTMENT_CASES
    }
    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }

    for name, preset in FLOWCHART_ZERO_ADJUSTMENT_CASES.items():
        pptx_path = tmp_path / name / "source.pptx"
        generator._generate_pptx(cases[name], pptx_path)
        with ZipFile(pptx_path) as zf:
            roots = [
                etree.fromstring(zf.read(f"ppt/slides/slide{index}.xml"))
                for index in range(1, 4)
            ]

        for root in roots:
            preset_nodes = root.xpath(".//a:prstGeom", namespaces=ns)
            assert len(preset_nodes) == 1, name
            assert preset_nodes[0].get("prst") == preset, name
            assert not preset_nodes[0].xpath("a:avLst/a:gd", namespaces=ns), name

        square_ext = [
            int(value)
            for value in roots[0].xpath(".//p:sp/p:spPr/a:xfrm/a:ext/@*", namespaces=ns)
        ]
        assert square_ext[0] == square_ext[1], name
        assert roots[0].xpath(
            "boolean(.//p:sp/p:spPr/a:solidFill/a:srgbClr[@val='5B9BD5'])",
            namespaces=ns,
        ), name
        assert roots[0].xpath(
            "boolean(.//p:sp/p:spPr/a:ln/a:solidFill/a:srgbClr[@val='203864'])",
            namespaces=ns,
        ), name

        wide_ext = [
            int(value)
            for value in roots[1].xpath(".//p:sp/p:spPr/a:xfrm/a:ext/@*", namespaces=ns)
        ]
        assert wide_ext[0] > wide_ext[1], name
        assert not roots[1].xpath(".//p:sp/p:spPr/a:solidFill", namespaces=ns), name
        assert roots[1].xpath(
            "boolean(.//p:sp/p:style/a:fillRef[@idx='1']/a:schemeClr[@val='accent1'])",
            namespaces=ns,
        ), name

        assert roots[2].xpath("boolean(.//p:grpSp/p:sp)", namespaces=ns), name
        group_xfrm = roots[2].xpath(".//p:grpSp/p:grpSpPr/a:xfrm", namespaces=ns)[0]
        group_ext = [int(value) for value in group_xfrm.xpath("a:ext/@*", namespaces=ns)]
        group_child_ext = [int(value) for value in group_xfrm.xpath("a:chExt/@*", namespaces=ns)]
        assert group_ext[1] > group_ext[0], name
        assert group_ext != group_child_ext, name


def test_flowchart_zero_adjustment_case_json_records_all_three_slides(tmp_path: Path):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"] == "oracle-pypptx-flowchart-0061-process"
    )

    path = generator._write_case_json(case, tmp_path)
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))

    assert len(payload["slides"]) == 3
    assert payload["coverage"] == {
        "oracle": "native-powerpoint",
        "features": [
            "p:sp.prstGeom=flowChartProcess",
            "a:avLst.adjustmentGuideCount=0",
            "geometry.aspect=square|wide|tall",
            "container=standalone|nonIdentityGroup",
            "paint=explicitSolid|themeStyleReference",
        ],
    }


def test_static_shape3d_matrix_is_registered():
    generator = _load_generator_module()
    names = {
        case["name"]
        for case in generator._build_all_case_defs()
        if case["name"].startswith("oracle-pypptx-shape3d-")
    }

    assert names == {
        "oracle-pypptx-shape3d-0001-flat-optout",
        "oracle-pypptx-shape3d-0002-picture-rect-circle-bevel",
        "oracle-pypptx-shape3d-0003-roundrect-bevel-contour",
        "oracle-pypptx-shape3d-0004-wide-bevel",
        "oracle-pypptx-shape3d-0005-tall-bevel",
        "oracle-pypptx-shape3d-0006-grouped-bevel",
        "oracle-pypptx-shape3d-0007-real-picture-bevel-slice",
        "oracle-pypptx-shape3d-0008-picture-horizontal-crop-bevel",
        "oracle-pypptx-shape3d-0009-picture-vertical-crop-bevel",
        "oracle-pypptx-shape3d-0010-picture-asymmetric-crop-bevel",
        "oracle-pypptx-shape3d-0011-ellipse-circle-bevel-matrix",
        "oracle-pypptx-shape3d-0012-donut-circle-bevel-adjustment-matrix",
        "oracle-pypptx-shape3d-0013-camera-projection-matrix",
        "oracle-pypptx-shape3d-0014-scene-only-plane-matrix",
        "oracle-pypptx-shape3d-0015-perspective-left-text-plane-matrix",
        "oracle-pypptx-shape3d-0016-perspective-right-picture-plane-matrix",
    }


def test_static_shape3d_matrix_serializes_bounded_ooxml(tmp_path: Path):
    generator = _load_generator_module()
    cases = {
        case["name"]: case
        for case in generator._build_all_case_defs()
        if case["name"].startswith("oracle-pypptx-shape3d-")
    }
    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    roots = {}

    for name, case in cases.items():
        pptx_path = tmp_path / name / "source.pptx"
        generator._generate_pptx(case, pptx_path)
        with ZipFile(pptx_path) as zf:
            roots[name] = etree.fromstring(zf.read("ppt/slides/slide1.xml"))

    optout = roots["oracle-pypptx-shape3d-0001-flat-optout"]
    assert not optout.xpath(".//a:scene3d | .//a:sp3d", namespaces=ns)

    positive_names = set(cases) - {
        "oracle-pypptx-shape3d-0001-flat-optout",
        "oracle-pypptx-shape3d-0013-camera-projection-matrix",
        "oracle-pypptx-shape3d-0014-scene-only-plane-matrix",
        "oracle-pypptx-shape3d-0015-perspective-left-text-plane-matrix",
        "oracle-pypptx-shape3d-0016-perspective-right-picture-plane-matrix",
    }
    for name in positive_names:
        root = roots[name]
        targets = root.xpath(
            ".//*[self::p:sp or self::p:pic][p:spPr/a:scene3d and p:spPr/a:sp3d]",
            namespaces=ns,
        )
        assert len(targets) == 1, name
        target = targets[0]
        assert target.xpath(
            "boolean(p:spPr/a:scene3d/a:camera[@prst='orthographicFront'])",
            namespaces=ns,
        ), name
        expected_light_rig = (
            "twoPt"
            if name
            in {
                "oracle-pypptx-shape3d-0002-picture-rect-circle-bevel",
                "oracle-pypptx-shape3d-0007-real-picture-bevel-slice",
                "oracle-pypptx-shape3d-0008-picture-horizontal-crop-bevel",
                "oracle-pypptx-shape3d-0009-picture-vertical-crop-bevel",
                "oracle-pypptx-shape3d-0010-picture-asymmetric-crop-bevel",
            }
            else "threePt"
        )
        assert target.xpath(
            "boolean(p:spPr/a:scene3d/a:lightRig[@rig=$rig][@dir='t'])",
            namespaces=ns,
            rig=expected_light_rig,
        ), name
        if name != "oracle-pypptx-shape3d-0007-real-picture-bevel-slice":
            assert target.xpath(
                "boolean(p:spPr/a:sp3d[@extrusionH='0']/a:bevelT"
                "[@w='127000'][@h='127000'][@prst='circle'])",
                namespaces=ns,
            ), name
        assert not target.xpath(
            "p:spPr/a:scene3d/a:camera/a:rot | p:spPr/a:sp3d/a:bevelB",
            namespaces=ns,
        ), name
        assert not target.xpath("p:spPr/a:sp3d/@prstMaterial", namespaces=ns), name

    picture = roots["oracle-pypptx-shape3d-0002-picture-rect-circle-bevel"]
    assert len(picture.xpath(".//p:pic[p:spPr/a:sp3d]", namespaces=ns)) == 1

    contour = roots["oracle-pypptx-shape3d-0003-roundrect-bevel-contour"]
    assert contour.xpath(
        "boolean(.//p:sp/p:spPr/a:sp3d[@contourW='12700']"
        "/a:contourClr/a:srgbClr[@val='FFFFFF'])",
        namespaces=ns,
    )

    wide = roots["oracle-pypptx-shape3d-0004-wide-bevel"]
    wide_ext = [int(value) for value in wide.xpath(".//p:sp[p:spPr/a:sp3d]/p:spPr/a:xfrm/a:ext/@*", namespaces=ns)]
    assert wide_ext[0] > wide_ext[1]

    tall = roots["oracle-pypptx-shape3d-0005-tall-bevel"]
    tall_ext = [int(value) for value in tall.xpath(".//p:sp[p:spPr/a:sp3d]/p:spPr/a:xfrm/a:ext/@*", namespaces=ns)]
    assert tall_ext[1] > tall_ext[0]

    grouped = roots["oracle-pypptx-shape3d-0006-grouped-bevel"]
    assert len(grouped.xpath(".//p:grpSp/p:sp[p:spPr/a:sp3d]", namespaces=ns)) == 1

    real_picture = roots["oracle-pypptx-shape3d-0007-real-picture-bevel-slice"]
    assert real_picture.xpath(
        "boolean(.//p:pic/p:spPr/a:scene3d/a:lightRig[@rig='twoPt'][@dir='t']"
        "/a:rot[@lat='0'][@lon='0'][@rev='7200000'])",
        namespaces=ns,
    )
    assert real_picture.xpath(
        "boolean(.//p:pic/p:spPr/a:sp3d[not(@extrusionH)][not(@contourW)]"
        "/a:bevelT[@w='25400'][@h='19050'][not(@prst)])",
        namespaces=ns,
    )
    assert real_picture.xpath(
        "boolean(.//p:pic/p:spPr/a:sp3d/a:contourClr/a:srgbClr[@val='FFFFFF'])",
        namespaces=ns,
    )
    assert real_picture.xpath(
        "boolean(.//p:pic/p:spPr/a:effectLst/a:outerShdw"
        "[@blurRad='55000'][@dist='18000'][@dir='5400000'][@algn='tl']"
        "/a:srgbClr[@val='000000']/a:alpha[@val='40000'])",
        namespaces=ns,
    )

    horizontal_crop = roots["oracle-pypptx-shape3d-0008-picture-horizontal-crop-bevel"]
    assert horizontal_crop.xpath(
        "boolean(.//p:pic/p:blipFill/a:srcRect[@l='22000'][@r='8000'][not(@t)][not(@b)])",
        namespaces=ns,
    )

    vertical_crop = roots["oracle-pypptx-shape3d-0009-picture-vertical-crop-bevel"]
    assert vertical_crop.xpath(
        "boolean(.//p:pic/p:blipFill/a:srcRect[@t='18000'][@b='12000'][not(@l)][not(@r)])",
        namespaces=ns,
    )

    asymmetric_crop = roots["oracle-pypptx-shape3d-0010-picture-asymmetric-crop-bevel"]
    assert asymmetric_crop.xpath(
        "boolean(.//p:pic/p:blipFill/a:srcRect"
        "[@l='12000'][@t='8000'][@r='18000'][@b='10000'])",
        namespaces=ns,
    )


def test_static_shape3d_scene_only_plane_matrix_serializes_absent_shape_format_and_modalities(
    tmp_path: Path,
):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"] == "oracle-pypptx-shape3d-0014-scene-only-plane-matrix"
    )
    assert case["slide_count"] == 6
    assert case["coverage"]["features"] == [
        "p:sp.prstGeom=rect",
        "geometry.aspect=square|wide|tall",
        "surface=solidPlane|noFillTextPlane",
        "text.bodyPr=wrap-none|anchor-ctr|spAutoFit",
        "a:scene3d.camera=perspectiveRelaxedModerately|perspectiveContrastingRightFacing",
        "a:scene3d.camera.rot=18590633,0,0|0,19532225,0",
        "a:scene3d.camera.fov=7200000|5100000",
        "a:scene3d.lightRig=threePt:t",
        "a:sp3d=absent",
        "effects=absent",
    ]

    pptx_path = tmp_path / "source.pptx"
    generator._generate_pptx(case, pptx_path)
    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    with ZipFile(pptx_path) as archive:
        roots = [
            etree.fromstring(archive.read(f"ppt/slides/slide{index}.xml"))
            for index in range(1, 7)
        ]

    for index, root in enumerate(roots):
        targets = root.xpath(".//p:sp[p:spPr/a:scene3d]", namespaces=ns)
        assert len(targets) == 1
        target = targets[0]
        assert target.xpath("boolean(p:spPr/a:prstGeom[@prst='rect'])", namespaces=ns)
        assert not target.xpath("p:spPr/a:sp3d", namespaces=ns)
        assert not target.xpath("p:spPr/a:effectLst | p:spPr/a:effectDag", namespaces=ns)
        assert target.xpath(
            "boolean(p:spPr/a:scene3d/a:lightRig[@rig='threePt'][@dir='t'][not(a:rot)])",
            namespaces=ns,
        )
        if index < 3:
            assert target.xpath(
                "boolean(p:spPr/a:scene3d/a:camera"
                "[@prst='perspectiveRelaxedModerately'][@fov='7200000']"
                "/a:rot[@lat='18590633'][@lon='0'][@rev='0'])",
                namespaces=ns,
            )
            assert target.xpath(
                "boolean(p:spPr/a:solidFill/a:srgbClr[@val='2F75B5'])",
                namespaces=ns,
            )
            assert not target.xpath(
                "p:txBody//a:t[normalize-space(.) != '']",
                namespaces=ns,
            )
        else:
            assert target.xpath("boolean(p:nvSpPr/p:cNvSpPr[@txBox='1'])", namespaces=ns)
            assert target.xpath(
                "boolean(p:spPr/a:scene3d/a:camera"
                "[@prst='perspectiveContrastingRightFacing'][@fov='5100000']"
                "/a:rot[@lat='0'][@lon='19532225'][@rev='0'])",
                namespaces=ns,
            )
            assert target.xpath("boolean(p:spPr/a:noFill)", namespaces=ns)
            assert not target.xpath("p:spPr/a:ln | p:style", namespaces=ns)
            assert target.xpath(
                "boolean(p:txBody/a:bodyPr[@wrap='none'][@anchor='ctr']/a:spAutoFit)",
                namespaces=ns,
            )
            assert target.xpath(
                "boolean(p:txBody//a:t[normalize-space(.) != ''])",
                namespaces=ns,
            )


def test_static_shape3d_perspective_left_text_matrix_serializes_implicit_camera_rotation(
    tmp_path: Path,
):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"]
        == "oracle-pypptx-shape3d-0015-perspective-left-text-plane-matrix"
    )
    assert case["slide_count"] == 3
    assert case["coverage"]["features"] == [
        "p:sp.prstGeom=rect",
        "geometry.aspect=square|wide|tall",
        "surface=noFillTextPlane",
        "text.content=CJK|latin|digits",
        "text.bodyPr=wrap-none|anchor-absent|spAutoFit",
        "a:scene3d.camera=perspectiveLeft",
        "a:scene3d.camera.rot=absent",
        "a:scene3d.camera.fov=7200000",
        "a:scene3d.lightRig=threePt:t",
        "a:sp3d=absent",
        "effects=absent",
    ]

    pptx_path = tmp_path / "source.pptx"
    generator._generate_pptx(case, pptx_path)
    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    with ZipFile(pptx_path) as archive:
        roots = [
            etree.fromstring(archive.read(f"ppt/slides/slide{index}.xml"))
            for index in range(1, 4)
        ]

    extents: list[tuple[int, int]] = []
    for root in roots:
        targets = root.xpath(".//p:sp[p:spPr/a:scene3d]", namespaces=ns)
        assert len(targets) == 1
        target = targets[0]
        assert target.xpath("boolean(p:nvSpPr/p:cNvSpPr[@txBox='1'])", namespaces=ns)
        assert target.xpath("boolean(p:spPr/a:prstGeom[@prst='rect'])", namespaces=ns)
        assert target.xpath("boolean(p:spPr/a:noFill)", namespaces=ns)
        assert not target.xpath(
            "p:spPr/a:ln | p:style | p:spPr/a:sp3d"
            " | p:spPr/a:effectLst | p:spPr/a:effectDag",
            namespaces=ns,
        )
        assert target.xpath(
            "boolean(p:spPr/a:scene3d/a:camera"
            "[@prst='perspectiveLeft'][@fov='7200000'][not(a:rot)])",
            namespaces=ns,
        )
        assert target.xpath(
            "boolean(p:spPr/a:scene3d/a:lightRig"
            "[@rig='threePt'][@dir='t'][not(a:rot)])",
            namespaces=ns,
        )
        assert target.xpath(
            "boolean(p:txBody/a:bodyPr[@wrap='none'][not(@anchor)]/a:spAutoFit)",
            namespaces=ns,
        )
        visible_text = "".join(target.xpath("p:txBody//a:t/text()", namespaces=ns))
        assert visible_text == "透视 LEFT 120"
        cx, cy = target.xpath("p:spPr/a:xfrm/a:ext", namespaces=ns)[0].attrib.values()
        extents.append((int(cx), int(cy)))

    assert extents[0][0] == extents[0][1]
    assert extents[1][0] > extents[1][1]
    assert extents[2][1] > extents[2][0]


def test_static_shape3d_perspective_right_picture_matrix_serializes_crop_interactions(
    tmp_path: Path,
):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"]
        == "oracle-pypptx-shape3d-0016-perspective-right-picture-plane-matrix"
    )
    assert case["slide_count"] == 4
    assert case["coverage"]["features"] == [
        "p:pic.prstGeom=rect",
        "geometry.aspect=square|wide|tall",
        "surface=stretchPngPicture",
        "a:srcRect=absent|horizontal|vertical|real-asymmetric",
        "a:scene3d.camera=perspectiveRight",
        "a:scene3d.camera.rot=absent",
        "a:scene3d.camera.fov=5700000",
        "a:scene3d.lightRig=threePt:t",
        "a:sp3d=absent",
        "effects=absent",
    ]

    pptx_path = tmp_path / "source.pptx"
    generator._generate_pptx(case, pptx_path)
    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    with ZipFile(pptx_path) as archive:
        roots = [
            etree.fromstring(archive.read(f"ppt/slides/slide{index}.xml"))
            for index in range(1, 5)
        ]

    expected_crops = (
        {},
        {"l": "22000", "r": "8000"},
        {"t": "18000", "b": "12000"},
        {"l": "1705", "t": "3350", "r": "1323", "b": "3350"},
    )
    extents: list[tuple[int, int]] = []
    for root, expected_crop in zip(roots, expected_crops, strict=True):
        targets = root.xpath(".//p:pic[p:spPr/a:scene3d]", namespaces=ns)
        assert len(targets) == 1
        target = targets[0]
        assert target.xpath("boolean(p:spPr/a:prstGeom[@prst='rect'])", namespaces=ns)
        assert target.xpath(
            "boolean(p:blipFill/a:blip[@r:embed])",
            namespaces={
                **ns,
                "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            },
        )
        assert target.xpath("boolean(p:blipFill/a:stretch[not(a:fillRect)])", namespaces=ns)
        assert not target.xpath(
            "p:blipFill/a:tile | p:spPr/a:ln | p:spPr/a:sp3d"
            " | p:spPr/a:effectLst | p:spPr/a:effectDag",
            namespaces=ns,
        )
        assert target.xpath(
            "boolean(p:spPr/a:scene3d/a:camera"
            "[@prst='perspectiveRight'][@fov='5700000'][not(a:rot)])",
            namespaces=ns,
        )
        assert target.xpath(
            "boolean(p:spPr/a:scene3d/a:lightRig"
            "[@rig='threePt'][@dir='t'][not(a:rot)])",
            namespaces=ns,
        )
        crops = target.xpath("p:blipFill/a:srcRect", namespaces=ns)
        if expected_crop:
            assert len(crops) == 1
            assert crops[0].attrib == expected_crop
        else:
            assert crops == []
        cx, cy = target.xpath("p:spPr/a:xfrm/a:ext", namespaces=ns)[0].attrib.values()
        extents.append((int(cx), int(cy)))

    assert extents[0][0] == extents[0][1]
    assert extents[1][0] > extents[1][1]
    assert extents[2][1] > extents[2][0]
    assert extents[3][0] > extents[3][1]


def test_static_shape3d_ellipse_matrix_serializes_aspects_paints_and_group(tmp_path: Path):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"] == "oracle-pypptx-shape3d-0011-ellipse-circle-bevel-matrix"
    )
    assert case["slide_count"] == 3

    pptx_path = tmp_path / "source.pptx"
    generator._generate_pptx(case, pptx_path)
    with ZipFile(pptx_path) as zf:
        roots = [
            etree.fromstring(zf.read(f"ppt/slides/slide{index}.xml"))
            for index in range(1, 4)
        ]

    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    for root in roots:
        assert root.xpath(
            "boolean(.//p:sp/p:spPr/a:prstGeom[@prst='ellipse'])",
            namespaces=ns,
        )
        assert root.xpath(
            "boolean(.//p:sp/p:spPr/a:scene3d/a:camera[@prst='orthographicFront'])",
            namespaces=ns,
        )
        assert root.xpath(
            "boolean(.//p:sp/p:spPr/a:scene3d/a:lightRig[@rig='threePt'][@dir='t'])",
            namespaces=ns,
        )
        assert root.xpath(
            "boolean(.//p:sp/p:spPr/a:sp3d[@extrusionH='0']/a:bevelT"
            "[@w='127000'][@h='127000'][@prst='circle'])",
            namespaces=ns,
        )

    square_ext = [
        int(value)
        for value in roots[0].xpath(".//p:sp/p:spPr/a:xfrm/a:ext/@*", namespaces=ns)
    ]
    assert square_ext[0] == square_ext[1]
    assert roots[0].xpath(
        "boolean(.//p:sp/p:spPr/a:solidFill/a:srgbClr[@val='2F75B5'])",
        namespaces=ns,
    )

    wide_ext = [
        int(value)
        for value in roots[1].xpath(".//p:sp/p:spPr/a:xfrm/a:ext/@*", namespaces=ns)
    ]
    assert wide_ext[0] > wide_ext[1]
    assert not roots[1].xpath(".//p:sp/p:spPr/a:solidFill", namespaces=ns)
    assert roots[1].xpath(
        "boolean(.//p:sp/p:style/a:fillRef[@idx='1']/a:schemeClr[@val='accent1'])",
        namespaces=ns,
    )

    assert roots[2].xpath("boolean(.//p:grpSp/p:sp)", namespaces=ns)
    group_xfrm = roots[2].xpath(".//p:grpSp/p:grpSpPr/a:xfrm", namespaces=ns)[0]
    group_ext = [int(value) for value in group_xfrm.xpath("a:ext/@*", namespaces=ns)]
    group_child_ext = [int(value) for value in group_xfrm.xpath("a:chExt/@*", namespaces=ns)]
    assert group_ext[1] > group_ext[0]
    assert group_ext != group_child_ext


def test_static_shape3d_ellipse_case_json_records_all_three_slides(tmp_path: Path):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"] == "oracle-pypptx-shape3d-0011-ellipse-circle-bevel-matrix"
    )

    path = generator._write_case_json(case, tmp_path)
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))

    assert len(payload["slides"]) == 3
    assert payload["coverage"] == {
        "oracle": "native-powerpoint",
        "features": [
            "p:sp.prstGeom=ellipse",
            "geometry.aspect=square|wide|tall",
            "container=standalone|nonIdentityGroup",
            "paint=explicitSolid|themeStyleReference",
            "a:scene3d.camera=orthographicFront",
            "a:scene3d.lightRig=threePt:t",
            "a:sp3d.extrusionH=0",
            "a:sp3d.bevelT=circle",
        ],
    }


def test_static_shape3d_donut_matrix_serializes_adjustments_aspects_paints_and_group(
    tmp_path: Path,
):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"] == "oracle-pypptx-shape3d-0012-donut-circle-bevel-adjustment-matrix"
    )
    assert case["slide_count"] == 5

    pptx_path = tmp_path / "source.pptx"
    generator._generate_pptx(case, pptx_path)
    with ZipFile(pptx_path) as zf:
        roots = [
            etree.fromstring(zf.read(f"ppt/slides/slide{index}.xml"))
            for index in range(1, 6)
        ]

    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    for root in roots:
        assert root.xpath(
            "boolean(.//p:sp/p:spPr/a:prstGeom[@prst='donut'])",
            namespaces=ns,
        )
        assert root.xpath(
            "boolean(.//p:sp/p:spPr/a:scene3d/a:camera[@prst='orthographicFront'])",
            namespaces=ns,
        )
        assert root.xpath(
            "boolean(.//p:sp/p:spPr/a:sp3d[@extrusionH='0']/a:bevelT"
            "[@w='127000'][@h='127000'][@prst='circle'])",
            namespaces=ns,
        )

    adjustment_values = [
        root.xpath(
            "string(.//p:sp/p:spPr/a:prstGeom/a:avLst/a:gd[@name='adj']/@fmla)",
            namespaces=ns,
        )
        for root in roots
    ]
    assert adjustment_values == ["", "val 0", "val 50000", "val 32000", "val 10000"]

    wide_ext = [
        int(value)
        for value in roots[3].xpath(".//p:sp/p:spPr/a:xfrm/a:ext/@*", namespaces=ns)
    ]
    assert wide_ext[0] > wide_ext[1]
    assert not roots[3].xpath(".//p:sp/p:spPr/a:solidFill", namespaces=ns)
    assert roots[3].xpath(
        "boolean(.//p:sp/p:style/a:fillRef[@idx='1']/a:schemeClr[@val='accent1'])",
        namespaces=ns,
    )

    assert roots[4].xpath("boolean(.//p:grpSp/p:sp)", namespaces=ns)
    group_xfrm = roots[4].xpath(".//p:grpSp/p:grpSpPr/a:xfrm", namespaces=ns)[0]
    group_ext = [int(value) for value in group_xfrm.xpath("a:ext/@*", namespaces=ns)]
    group_child_ext = [int(value) for value in group_xfrm.xpath("a:chExt/@*", namespaces=ns)]
    assert group_ext[1] > group_ext[0]
    assert group_ext != group_child_ext


def test_static_shape3d_donut_case_json_records_all_five_slides(tmp_path: Path):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"] == "oracle-pypptx-shape3d-0012-donut-circle-bevel-adjustment-matrix"
    )

    path = generator._write_case_json(case, tmp_path)
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))

    assert len(payload["slides"]) == 5
    assert payload["coverage"] == {
        "oracle": "native-powerpoint",
        "features": [
            "p:sp.prstGeom=donut",
            "geometry.adjustment=0|10000|default25000|32000|50000",
            "geometry.aspect=square|wide|tall",
            "container=standalone|nonIdentityGroup",
            "paint=explicitSolid|themeStyleReference",
            "a:scene3d.camera=orthographicFront",
            "a:scene3d.lightRig=threePt:t",
            "a:sp3d.extrusionH=0",
            "a:sp3d.bevelT=circle",
        ],
    }


def test_static_shape3d_camera_matrix_serializes_bounded_flat_plane_scenes(tmp_path: Path):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"] == "oracle-pypptx-shape3d-0013-camera-projection-matrix"
    )
    assert case["slide_count"] == 6

    pptx_path = tmp_path / "source.pptx"
    generator._generate_pptx(case, pptx_path)
    with ZipFile(pptx_path) as zf:
        roots = [
            etree.fromstring(zf.read(f"ppt/slides/slide{index}.xml"))
            for index in range(1, 7)
        ]

    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    for root in roots:
        assert root.xpath(
            "boolean(.//p:sp/p:spPr/a:prstGeom[@prst='rect'])",
            namespaces=ns,
        )
        assert root.xpath(
            "boolean(.//p:sp/p:spPr/a:scene3d/a:lightRig[@rig='threePt'][@dir='t'])",
            namespaces=ns,
        )
        assert root.xpath(
            "boolean(.//p:sp/p:spPr/a:sp3d[@extrusionH='0'])",
            namespaces=ns,
        )
        assert not root.xpath(
            ".//p:sp/p:spPr/a:sp3d/* | .//p:sp/p:spPr/a:sp3d/@contourW"
            " | .//p:sp/p:spPr/a:sp3d/@prstMaterial | .//p:sp/p:spPr/a:effectLst"
            " | .//p:sp/p:txBody//a:t[string-length(.) > 0]",
            namespaces=ns,
        )

    assert roots[0].xpath(
        "boolean(.//a:camera[@prst='orthographicFront'][not(a:rot)][not(@fov)])",
        namespaces=ns,
    )
    assert roots[1].xpath(
        "boolean(.//a:camera[@prst='orthographicFront']/a:rot"
        "[@lat='1200000'][@lon='1800000'][@rev='0'])",
        namespaces=ns,
    )
    for root in roots[2:]:
        assert root.xpath(
            "boolean(.//a:camera[@prst='perspectiveRelaxedModerately'][@fov='7200000']"
            "/a:rot[@lat='18590633'][@lon='0'][@rev='0'])",
            namespaces=ns,
        )

    square_ext = [
        int(value)
        for value in roots[2].xpath(".//p:sp/p:spPr/a:xfrm/a:ext/@*", namespaces=ns)
    ]
    wide_ext = [
        int(value)
        for value in roots[3].xpath(".//p:sp/p:spPr/a:xfrm/a:ext/@*", namespaces=ns)
    ]
    tall_ext = [
        int(value)
        for value in roots[4].xpath(".//p:sp/p:spPr/a:xfrm/a:ext/@*", namespaces=ns)
    ]
    assert square_ext[0] == square_ext[1]
    assert wide_ext[0] > wide_ext[1]
    assert tall_ext[1] > tall_ext[0]
    assert roots[3].xpath(
        "boolean(.//p:sp/p:style/a:fillRef[@idx='1']/a:schemeClr[@val='accent1'])",
        namespaces=ns,
    )
    assert roots[5].xpath("boolean(.//p:grpSp/p:sp[p:spPr/a:scene3d])", namespaces=ns)
    group_xfrm = roots[5].xpath(".//p:grpSp/p:grpSpPr/a:xfrm", namespaces=ns)[0]
    assert group_xfrm.xpath("a:ext/@cx", namespaces=ns) != group_xfrm.xpath(
        "a:chExt/@cx",
        namespaces=ns,
    )


def test_static_shape3d_camera_case_json_records_all_six_slides(tmp_path: Path):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"] == "oracle-pypptx-shape3d-0013-camera-projection-matrix"
    )

    path = generator._write_case_json(case, tmp_path)
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))

    assert len(payload["slides"]) == 6
    assert payload["coverage"] == {
        "oracle": "native-powerpoint",
        "features": [
            "p:sp.prstGeom=rect",
            "geometry.aspect=square|wide|tall",
            "container=standalone|nonIdentityGroup",
            "paint=explicitSolid|themeStyleReference",
            "a:scene3d.camera=orthographicFront|perspectiveRelaxedModerately",
            "a:scene3d.camera.rot=absent|20deg,30deg,0deg|18590633,0,0",
            "a:scene3d.camera.fov=absent|7200000",
            "a:scene3d.lightRig=threePt:t",
            "a:sp3d.extrusionH=0",
            "a:sp3d.bevel=absent",
        ],
    }


def test_static_shape3d_case_json_records_exact_scope(tmp_path: Path):
    generator = _load_generator_module()
    case = next(
        case
        for case in generator._build_all_case_defs()
        if case["name"] == "oracle-pypptx-shape3d-0002-picture-rect-circle-bevel"
    )

    path = generator._write_case_json(case, tmp_path)
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))

    assert payload["coverage"] == {
        "oracle": "native-powerpoint",
        "features": [
            "p:pic",
            "a:scene3d.camera=orthographicFront",
            "a:scene3d.lightRig=twoPt:t",
            "a:sp3d.extrusionH=0",
            "a:sp3d.bevelT=circle",
        ],
    }


def test_local_shape3d_experiment_matrix_is_opt_in_and_separate_from_support_cases():
    generator = _load_generator_module()

    default_names = {case["name"] for case in generator._build_all_case_defs()}
    expanded = generator._build_all_case_defs(include_local_shape3d=True)
    local_cases = [
        case for case in expanded if case["name"].startswith("oracle-local-shape3d-")
    ]

    assert not any(name.startswith("oracle-local-shape3d-") for name in default_names)
    assert {case["name"] for case in local_cases} == {
        "oracle-local-shape3d-0001-ellipse-circle-bevel",
        "oracle-local-shape3d-0002-donut-adjusted-circle-bevel",
        "oracle-local-shape3d-0003-star5-adjusted-circle-bevel",
        "oracle-local-shape3d-0004-freeform-concave-circle-bevel",
        "oracle-local-shape3d-0005-rotated-roundrect-bevel",
        "oracle-local-shape3d-0006-nested-group-scaled-bevel",
        "oracle-local-shape3d-0007-glow-roundrect-bevel",
    }
    assert all(case["local_only"] is True for case in local_cases)
    assert all(case["coverage"]["cohort"] == "experimental-local" for case in local_cases)
    assert all(case["coverage"]["claim"] == "discovery-only" for case in local_cases)


def test_local_shape3d_experiment_matrix_serializes_geometry_transform_and_effect_probes(
    tmp_path: Path,
):
    generator = _load_generator_module()
    cases = {
        case["name"]: case
        for case in generator._build_all_case_defs(include_local_shape3d=True)
        if case["name"].startswith("oracle-local-shape3d-")
    }
    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    roots = {}

    for name, case in cases.items():
        pptx_path = tmp_path / name / "source.pptx"
        generator._generate_pptx(case, pptx_path)
        with ZipFile(pptx_path) as zf:
            roots[name] = etree.fromstring(zf.read("ppt/slides/slide1.xml"))

    for name, root in roots.items():
        assert root.xpath(
            "boolean(.//*[self::p:sp or self::p:pic][p:spPr/a:scene3d and p:spPr/a:sp3d])",
            namespaces=ns,
        ), name

    assert roots["oracle-local-shape3d-0001-ellipse-circle-bevel"].xpath(
        "boolean(.//p:sp/p:spPr/a:prstGeom[@prst='ellipse'])",
        namespaces=ns,
    )
    assert roots["oracle-local-shape3d-0002-donut-adjusted-circle-bevel"].xpath(
        "boolean(.//p:sp/p:spPr/a:prstGeom[@prst='donut']/a:avLst/a:gd)",
        namespaces=ns,
    )
    assert roots["oracle-local-shape3d-0003-star5-adjusted-circle-bevel"].xpath(
        "boolean(.//p:sp/p:spPr/a:prstGeom[@prst='star5']/a:avLst/a:gd)",
        namespaces=ns,
    )
    assert roots["oracle-local-shape3d-0004-freeform-concave-circle-bevel"].xpath(
        "boolean(.//p:sp/p:spPr/a:custGeom/a:pathLst/a:path/a:lnTo)",
        namespaces=ns,
    )
    assert roots["oracle-local-shape3d-0005-rotated-roundrect-bevel"].xpath(
        "boolean(.//p:sp[p:spPr/a:sp3d]/p:spPr/a:xfrm[@rot='1800000'])",
        namespaces=ns,
    )
    nested = roots["oracle-local-shape3d-0006-nested-group-scaled-bevel"]
    assert nested.xpath("count(.//p:grpSp/p:grpSp/p:sp[p:spPr/a:sp3d])", namespaces=ns) == 1
    assert nested.xpath(
        "boolean(.//p:grpSp/p:grpSp/p:grpSpPr/a:xfrm"
        "[a:ext/@cx != a:chExt/@cx or a:ext/@cy != a:chExt/@cy])",
        namespaces=ns,
    )
    assert roots["oracle-local-shape3d-0007-glow-roundrect-bevel"].xpath(
        "boolean(.//p:sp/p:spPr/a:effectLst/a:glow[@rad='114300']"
        "/a:srgbClr[@val='00B0F0']/a:alpha[@val='65000'])",
        namespaces=ns,
    )


def test_local_shape3d_cli_writes_metadata_to_ignored_directory(tmp_path: Path, monkeypatch):
    generator = _load_generator_module()
    tracked_cases_dir = tmp_path / "tracked-definitions"
    local_cases_dir = tmp_path / "oracle-runtime" / "local-shape3d-cases"
    testdata_dir = tmp_path / "testdata"
    report_path = tmp_path / "report.json"
    case_name = "oracle-local-shape3d-0001-ellipse-circle-bevel"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(GENERATOR_PATH),
            "--cases-dir",
            str(tracked_cases_dir),
            "--local-cases-dir",
            str(local_cases_dir),
            "--testdata-dir",
            str(testdata_dir),
            "--report-path",
            str(report_path),
            "--pptx-only",
            "--no-reuse",
            "--include-local-shape3d-matrix",
            "--case",
            case_name,
        ],
    )

    assert generator.main() == 0
    assert not (tracked_cases_dir / f"{case_name}.json").exists()
    local_definition = local_cases_dir / f"{case_name}.json"
    assert local_definition.exists()
    payload = __import__("json").loads(local_definition.read_text(encoding="utf-8"))
    assert payload["coverage"]["cohort"] == "experimental-local"
    report = __import__("json").loads(report_path.read_text(encoding="utf-8"))
    assert report["local_shape3d_matrix"] is True
    assert report["local_cases_dir"] == str(local_cases_dir.resolve())
