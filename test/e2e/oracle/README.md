# PowerPoint Oracle E2E Plan

This directory contains the local-macOS PowerPoint oracle pipeline used to drive renderer improvements.

## Capability Loop

The oracle now has a tracked capability contract in `capabilities.json` and sanitized historical
promotion receipts in `capability-acceptance.json`. The loop separates intended render mode from
current evidence state and only permits a public `supported` claim when a bounded capability is
both `native` and freshly `verified`.

```bash
# From the repository root
pnpm capability:check
pnpm capability:inventory

# Inspect all commands
python3 test/e2e/scripts/run_capability_loop.py --help
```

`capability_contract.py`, `capability_inventory.py`, `capability_evidence.py`,
`capability_verification.py`, and `capability_ranking.py` contain the domain rules.
`scripts/run_capability_loop.py` only composes them. Local outputs are written below
`test/e2e/reports/capability-loop/` and remain ignored because
they may refer to private case aliases. Tracked receipts keep stable case IDs and SHA-256 values,
but remove absolute paths, usernames, free-form issue bodies, and private labels.

The default inventory limits match the renderer safety contract: 4,000 ZIP entries, 32 MiB per
decoded entry, and 256 MiB decoded in total. Ranking counts byte-identical PPTX files once. A dirty
report, missing or changed inputs, stale relevant implementation files, skipped required cases,
failed structural checks, or an unresolved manual-review row blocks promotion. Corpus scans isolate
and report rejected packages instead of losing all other observations; use `--fail-on-rejected` for
a strict nonzero exit after the report is written. Unknown, verified, and externally blocked rows
remain in the ledger for observation but are not selected as the next implementation cohort.
When a committed goal deliberately selects a lower-ranked cohort, pass `--selection-reason`; the
work packet records the override instead of silently hiding the global ordering.

`verify` consumes raw `/api/evaluate` JSON reports from one clean committed renderer revision. It
derives native-PowerPoint, manual-review, and regression status, including a matching baseline case
set, identical input/runtime fingerprints from an earlier revision, and the 0.02 SSIM budget. The
bounded top-bevel capability additionally requires a `--bevel-report`; the camera-plane capability
requires a `--camera-report`. Their derived `bevel-local` and `camera-local` gates bind the exact
case set, source/ground-truth hashes, and per-slide raster hashes to the same clean revision and
current files. Other `--passed-gate` values only record checks already executed by the caller; they
are not run by the command. Review rows require an explicit case verdict.

## Current Implemented Pieces

1. `powerpoint_oracle.py`
- `export_pptx_to_pdf_mac(...)`: stages a PPTX in a fixed runtime directory, opens that exact file
  in PowerPoint, and exports PDF with retry and a bounded timeout.
- `run_macro_export_mac(...)`: opens an exact macro host `.pptm`, runs a filename-qualified VBA
  macro, and optionally exports that same host.
- `run_macro_only_mac(...)`: runs a filename-qualified VBA macro when the macro writes its own
  fixed sink artifacts.

2. AppleScript runners
- `scripts/export_pptx_to_pdf.applescript`
- `scripts/run_macro_export.applescript`
- `scripts/run_macro_only.applescript`

3. Case compiler and metrics
- `case_compiler.py`: compiles JSON case files into a VBA-friendly line spec.
- `metrics.py`: visual metrics (`ssim`, `fg_iou`, `fg_iou_tolerant`, `chamfer_score`, `color_hist_corr`, `mae`) and quality gate. Pass/fail uses only `ssim ≥ 0.95` and `color_hist_corr ≥ 0.80`; the foreground color metric tolerates one HSV histogram bin and negligible visually blank PDF residue. Other metrics are diagnostic.
- `../scripts/shape3d_bevel_metrics.py`: source-OOXML-derived bevel-ring and round-corner lighting
  gate for the bounded static 3D cohort.
- `../scripts/shape3d_camera_metrics.py`: source-OOXML-derived four-corner projection and material
  field gate for the bounded zero-depth camera-plane cohort.
- `shape` nodes support `shapeTypeId` (numeric `MsoAutoShapeType`) for forward-compatible shape coverage.

4. VBA probe module
- `vba/GenerateProbeDeck.bas`
- Includes a no-arg entry `GenerateProbeDeck_Default` so it appears in `Tools -> Macro -> Macros...`.
- Includes `GenerateProbeDeck_FromSpec(specPath)` to generate decks from compiled case specs.
- Import this module into `pptx-macro-host.pptm` only when the VBA file changes; case JSON edits do not require re-import.
- `SHAPE` spec token supports both names (`RECTANGLE`) and numeric ids (`1`, `182`, ...). Numeric is preferred for new shape coverage.

5. Tests
- `test_oracle_powerpoint.py`: unit tests for command assembly/retry/error behavior.
- `test_oracle_macro_pipeline.py`: local smoke test for macro-driven oracle export.
- `test_oracle_case_compiler.py`: validates JSON -> spec compilation.
- `test_oracle_metrics.py`: validates visual metrics + quality gate logic.
- `test_oracle_auto_pipeline.py`: end-to-end local pipeline (`case -> macro -> pptx/pdf -> renderer compare`).
- `test_oracle_attention_ranking.py`: verifies ranked `attention_cases` output.
- `../test_pypptx_generator_cases.py`: locks the 28 zero-adjustment flowchart mappings and their
  84-slide square/wide/grouped-tall native matrix before PowerPoint export.

6. Reproducible evaluation provenance
- Every `/api/evaluate/{case}` result fingerprints the source PPTX and PDF/PNG ground truth.
- Reports also record the exact reference/HTML raster pair used for each visual metric row, the
  renderer Git state, actual browser version, and the configured local font-profile
  manifest/font hashes.
- `font-profile.example.json` documents the ignored local profile format without distributing
  font binaries.

## How To Run

1. Unit tests (no PowerPoint dependency)
```bash
cd test/e2e
.venv/bin/python -m pytest -q test_oracle_powerpoint.py
```

2. Local macro smoke test
```bash
cd test/e2e
PPTX_ORACLE_MACRO_HOST=/tmp/pptx-macro-host.pptm \
.venv/bin/python -m pytest -q test_oracle_macro_pipeline.py
```

Optional macro name override:
```bash
PPTX_ORACLE_MACRO_NAME=ExportSmartArtLayouts_ToFile
```

The smoke passes a fixed catalog path to the macro and verifies that at least one `Id|Name` row is
written. An override must follow the same one-output-path contract.

3. End-to-end local oracle pipeline
```bash
cd test/e2e
PPTX_ORACLE_MACRO_HOST=/absolute/path/to/pptx-macro-host.pptm \
.venv/bin/python -m pytest -q test_oracle_auto_pipeline.py -m local_oracle
```

Generated artifacts are intentionally persisted to:
- `test/e2e/testdata/cases/oracle-auto-basic-shapes-smoke/source.pptx`
- `test/e2e/testdata/cases/oracle-auto-basic-shapes-smoke/ground-truth.pdf`

This makes the auto-generated file pair visible in `/test/pages/e2e-compare.html`
for manual visual alignment.

## Batch-generate Oracle Cases

The python-pptx corpus includes `oracle-pypptx-flowchart-0061-*` through
`oracle-pypptx-flowchart-0088-*`. Each file has three slides covering explicit solid paint, a theme
style reference, and a non-identity group transform. Generate only that cohort with:

```bash
cd test/e2e
.venv/bin/python scripts/generate_pypptx_cases.py \
  --case 'oracle-pypptx-flowchart-*'
```

Run this to generate all JSON cases under `oracle/cases/` into `test/e2e/testdata/cases/`:

```bash
cd test/e2e
.venv/bin/python -m pytest -q test_oracle_generate_cases_local.py -m local_oracle
```

Generated pairs (e.g. `oracle-shape-rectangle.*`, `oracle-smartart-basic-process.*`)
will appear in `/test/pages/e2e-compare.html` file dropdown automatically.

## One-Shot Full Ground Truth (Large Baseline)

For a larger baseline (beyond curated `oracle/cases/*.json`), use:

- `../scripts/one_shot_full_ground_truth.py`

It supports:

- SmartArt: export all layouts available on the local PowerPoint build and generate cases automatically.
- Shapes: probe numeric `MsoAutoShapeType` ranges (e.g. `1..500`) via `shapeTypeId`.
- Cache reuse by default (`--no-reuse` to force regeneration).
- Unified JSON report output.

Example:

```bash
cd test/e2e
.venv/bin/python scripts/one_shot_full_ground_truth.py \
  --macro-host testdata/pptx-macro-host.pptm \
  --cases-dir oracle/cases-full \
  --testdata-dir testdata \
  --shape-id-min 1 \
  --shape-id-max 500
```

Report (default):

- `test/e2e/reports/oracle-failures/full-ground-truth-one-shot.json`

## Python-pptx Ground Truth Pipeline

A second pipeline uses `python-pptx` for PPTX creation and native PowerPoint automation for
ground-truth export. It defines 172 cases under `oracle/cases-pypptx/` with the
`oracle-pypptx-*` prefix:

- **Text** (59 cases): fonts, sizes, styles, alignment, colors, bullets, vertical text,
  placeholder inheritance, plus a 16-case CJK wrap/autofit/line-spacing interaction matrix whose
  final four cases cover square/wide/tall `spAutoFit` growth and explicit-overflow opt-out, and a
  four-case `defRPr`/`fontRef` color-precedence matrix with explicit-run and inverse controls
- **Shape adjustments** (31 cases): adjustment handles for roundRect, chevron, arrow, star, donut, cross, trapezoid, blockArc, bevel, triangle, pentagon, can, heart, moon, brace
- **Zero-adjustment flowcharts** (28 cases, 84 slides): presets in shape IDs 61-88, each with
  square explicit paint, wide theme-reference paint, and grouped-tall rendering
- **Static DrawingML 3D** (13 cases, 24 slides): flat picture opt-out plus a bounded
  `orthographicFront`/`twoPt:t|threePt:t`/circle-top-bevel matrix across picture, rect,
  roundRect, ellipse, contour, wide/tall, and grouped-shape contexts; the seventh case mirrors the
  `model-platform` picture tuple including light rotation, implicit defaults, outline, and outer
  shadow, cases 8-10 isolate horizontal, vertical, and combined `a:srcRect` crops, case 11
  covers square explicit, wide theme-reference, and grouped-tall ellipse rendering, and case 12
  covers donut adjustment bounds/default plus wide-theme and grouped-tall variants; case 13 adds
  identity and rotated orthographic camera controls plus square/wide/tall, explicit/theme, and
  grouped perspective zero-depth planes
- **Composites** (20 cases): multi-element layouts combining shapes, text, tables, charts, connectors, merged cells, vertical text, transparent overlaps, and scaled groups
- **Charts** (21 cases): column, bar, line, pie, doughnut, area, scatter, radar, bubble variants

Generate cases:

```bash
cd test/e2e
.venv/bin/python3 scripts/generate_pypptx_cases.py

# Focus one or more exact/glob patterns; this example selects text IDs 0040-0059.
.venv/bin/python3 scripts/generate_pypptx_cases.py \
  --case 'oracle-pypptx-text-00[45]*'

# Generate only the bounded static DrawingML 3D matrix.
.venv/bin/python3 scripts/generate_pypptx_cases.py \
  --case 'oracle-pypptx-shape3d-*'

# Generate eight ignored discovery probes without widening the supported cohort.
.venv/bin/python3 scripts/generate_pypptx_cases.py \
  --include-local-shape3d-matrix \
  --case 'oracle-local-shape3d-*'
```

macOS exports PDF; Windows exports PDF plus optional per-slide PNG. `--pptx-only` works without
PowerPoint. On macOS each export is isolated to its staged input path and fixed runtime sink;
PowerPoint itself may remain running. The exporter normalizes macOS's `/private/tmp` firmlink to
the `/tmp` spelling reported by PowerPoint, then resolves and closes only the presentation whose
full path matches that staged input. Unrelated user presentations stay outside the export
lifecycle. The binary artifacts remain ignored under `testdata/`, while tracked case JSON records
coverage and font requirements. The generation report includes the selected patterns and SHA-256
fingerprints.

The opt-in `oracle-local-shape3d-*` matrix explores ellipse, adjusted donut/star, concave freeform,
shape rotation, nested group scaling, and glow interaction. Its definition files
default to ignored `oracle-runtime/local-shape3d-cases/`, and its PPTX/PDF output remains under
ignored `testdata/`. These cases are discovery inputs; they do not alter the tracked 172-case matrix.
The original one-slide ellipse and donut probes remain useful for preflight comparisons, while the
tracked three-slide ellipse and five-slide donut matrices bound the public
`drawingml.shape.3d.top-bevel-contour` claim. That tuple also requires an absent scene backdrop,
zero or omitted shape `z`, and no extrusion color.

After evaluating top-bevel cases 0001-0012, run `../scripts/shape3d_bevel_metrics.py` with one
`--case-report` per case. It reads the source OOXML to locate supported regions and builds independent
rect, roundRect, ellipse, and donut masks before comparing the native and HTML luminance fields only
inside the bevel ring. Unknown silhouettes and rotations fail as unevaluable instead of borrowing a
rectangular mask. It requires a general score of `0.60` and applies an additional `0.78` corner score
to `roundRect`. Zero-thickness donuts remain covered by the full-slide gate; bands below four pixels are reported as
resolution-limited and remain subject to full-slide and manual checks. Pass the resulting JSON to
`run_capability_loop.py verify --bevel-report ...`; both commands verify the API and on-disk raster
hashes, and callers cannot self-attest `bevel-local`.

After evaluating case 0013, run `../scripts/shape3d_camera_metrics.py` with its clean native report.
It binds the exact source, ground truth, revision, and per-slide raster hashes, extracts a normalized
four-corner polygon from each applicable slide, and compares three material color bands. The gate
requires corner score `0.98`, color score `0.97`, and, where native output has a measurable material
gradient, range ratio `0.65` and direction cosine `0.95`. Pass its report to
`run_capability_loop.py verify --camera-report ...`; callers cannot self-attest `camera-local`.

On macOS the PowerPoint interactive session must remain available. Error `-9074` can come from a
locked session, a pending dialog, or a staged `_pptx-input.pptx` left open by an interrupted run.
Export and macro timeouts stop immediately and point to the unlock state or a pending **Grant File
Access** or macro-security dialog. A file-backed export-script compile error (`-2741`) switches to
an equivalent inline exact-path script within the same attempt. VBA calls are qualified as
`<macro-host-filename>!<macro-name>` because an unqualified procedure can return `-18` when another
presentation is open. The exporter removes stale output before every attempt and preserves the
original AppleScript stderr.

## Optional Font Profile

For font-sensitive text cases, copy `font-profile.example.json` to an ignored path such as
`testdata/font-profiles/local-office-fonts.json`, then point each face at an ignored local font or
symlink. Paths are relative to `testdata/`; do not commit licensed fonts.

```bash
PPTX_E2E_VITE_SERVER_URL=http://127.0.0.1:5183 \
PPTX_E2E_FONT_PROFILE=font-profiles/local-office-fonts.json \
PPTX_E2E_BROWSER_CHANNEL=chrome \
.venv/bin/python server.py
```

The single-slide page registers the profile before layout. Evaluation provenance records the
profile manifest, every face hash, the browser version, renderer revision, and source/ground-truth
hashes. Only compare metric runs whose relevant provenance matches.

## Local Development Loop (Incremental by default)

Use this when actively improving shape/SmartArt support.

```bash
cd test/e2e
PPTX_ORACLE_MACRO_HOST=/absolute/path/to/pptx-macro-host.pptm \
.venv/bin/python -m pytest -q test_oracle_regression_matrix_local.py -m local_oracle
```

Default behavior is optimized for local development:

- Runs only cases that are not yet marked `supported` in:
  - `test/e2e/reports/oracle-failures/support-catalog.json`
- Reuses cached ground truth (`source.pptx` + `ground-truth.pdf`) in `test/e2e/testdata/cases/{stem}/` when both files already exist.
- Writes updated pass/fail status back into the support catalog after the run.

This keeps each iteration focused on unsupported coverage and avoids regenerating existing oracle artifacts.

### Force Full Regression

```bash
ORACLE_CASE_SCOPE=all \
PPTX_ORACLE_MACRO_HOST=/absolute/path/to/pptx-macro-host.pptm \
.venv/bin/python -m pytest -q test_oracle_regression_matrix_local.py -m local_oracle
```

### Force Ground-Truth Regeneration

```bash
ORACLE_REUSE_GROUND_TRUTH=0 \
PPTX_ORACLE_MACRO_HOST=/absolute/path/to/pptx-macro-host.pptm \
.venv/bin/python -m pytest -q test_oracle_regression_matrix_local.py -m local_oracle
```

## Bootstrap Coverage from Existing Large Decks

Generate seed cases by scanning shape presets and SmartArt layout IDs from your own existing PPTX decks. Use case stems under `testdata/cases/` that already have `source.pptx` (and optionally `ground-truth.pdf`):

```bash
cd test/e2e
.venv/bin/python -m oracle.seed_catalog \
  --testdata-dir testdata \
  --cases-dir oracle/cases \
  --sources <stem1> <stem2> ... \
  --min-source-size-mb 1 \
  --report-path reports/oracle-failures/seed-bootstrap-from-sources.json
```

The seed catalog is written to `test/e2e/reports/oracle-failures/seed-bootstrap-from-sources.json`.

Then generate/refresh oracle ground truth for these seed cases (cached by default):

```bash
cd test/e2e
PPTX_ORACLE_MACRO_HOST=/absolute/path/to/pptx-macro-host.pptm \
.venv/bin/python -m pytest -q test_oracle_seed_bootstrap_local.py -m local_oracle
```

## Manual Confirmation via E2E Page

Open:

- `http://localhost:5173/test/pages/e2e-compare.html`

Each slide card now supports a manual verdict (`supported` / `unsupported` / `unsure`) and note.

Saving feedback calls:

- `POST /api/manual-review`

Feedback is persisted to:

- `test/e2e/reports/oracle-failures/manual-review.json`

For oracle case files, `supported`/`unsupported` feedback also updates:

- `test/e2e/reports/oracle-failures/support-catalog.json`

## Attention Ranking Output

`test_oracle_regression_matrix_local.py` writes `test/e2e/reports/oracle-failures/suite-summary.json` with:
- `failed_by_label`: hard failures by shape/smartart label.
- `attention_cases`: warning-only cases sorted by severity for manual review priority.

## Evaluate all shapes + SmartArt (SSIM + fg_iou)

To get **SSIM and fg_iou** for shapes and SmartArt by iterating `POST /api/evaluate/{case}`:

1. Start dev servers: `pnpm dev:e2e` (Vite + Python API).
2. Run one of:

```bash
cd test/e2e
# Shapes (id 1..500) + SmartArt (all oracle-full-smartart-*.json in oracle/cases-full)
.venv/bin/python scripts/run_all_shapes_eval.py --shape-id-min 1 --shape-id-max 500 --smartart-cases-dir oracle/cases-full
# Shapes only
.venv/bin/python scripts/run_all_shapes_eval.py --shape-id-min 1 --shape-id-max 500
# SmartArt only
.venv/bin/python scripts/run_all_shapes_eval.py --smartart-cases-dir oracle/cases-full
# Everything in testdata (single evaluate-all call)
.venv/bin/python scripts/run_all_shapes_eval.py
```

Output:

- `reports/oracle-failures/all-shapes-eval.json` — full report with `results[].summary.ssim`, `results[].summary.fg_iou`, etc.
- `reports/oracle-failures/all-shapes-eval.csv` — CSV with columns `case`, `ssim`, `color_hist_corr`, `fg_iou_tolerant`, `chamfer_score`, `fg_iou`, `passed`, `needs_review` for sorting/filtering.

Optional: `--api-base`, `--out`, `--no-csv`.

## Directory Authorization (macOS)

To avoid repeated PowerPoint permission prompts, keep oracle IO in one fixed directory:

- Fixed runtime dir: `test/e2e/testdata/oracle-runtime`
- PowerPoint now writes only to fixed sink files in that dir:
  - `test/e2e/testdata/oracle-runtime/_pptx-input.pptx`
  - `test/e2e/testdata/oracle-runtime/_pptx-output.pdf`
  - `test/e2e/testdata/oracle-runtime/_macro-output.pptx`
  - `test/e2e/testdata/oracle-runtime/_macro-output.pdf`
- Macro spec path is also fixed:
  - `test/e2e/testdata/oracle-runtime/_macro-spec.txt`
  Generated per-case files are copied from these sinks by Python.

Authorize this directory once when prompted by PowerPoint.

The macOS runner also needs an unlocked user session, Automation permission for the calling app to
control Microsoft PowerPoint, and permission to run the repository-owned macro host. Keep these
native-oracle permissions on a dedicated development user or machine when running unattended
corpora; do not mix untrusted macro-enabled documents into that session.

## Next Steps (TDD Sequence)

1. Expand shape/smartart coverage in `oracle/cases/*.json`.
2. Add auto-minimization for failing cases and persist them into a stable regression suite.
3. Add PR (`smoke`) vs nightly (`full`) matrix commands in CI scripts.

## Standard TDD Loop For New Render Support

Use this as the default development workflow for adding new shape/SmartArt compatibility:

1. Add a new oracle case (or include it in `cases-full`).
2. Generate/reuse ground truth (`pptx/pdf`).
3. Run local oracle matrix and confirm failure signal.
4. Add a failing renderer/unit test for the exact mismatch.
5. Implement minimal fix in parser/shape preset/renderer.
6. Re-run:
   - unit tests
   - targeted oracle case
   - matrix (incremental or full)
7. Confirm support status update in:
   - `reports/oracle-failures/support-catalog.json`
