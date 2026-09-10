# Testing Guide

This project uses layered verification across two test ecosystems:

- **Unit tests** (vitest): parser/model/renderer behavior in isolation.
- **Browser package tests** (Playwright): built standalone entry, ECharts registration
  matrix, and isolated PDF.js Worker rendering in Chromium.
- **E2E tests** (pytest + Playwright): structural validation, visual comparison against PowerPoint PDF output, and baseline-driven shape/SmartArt regression.

## Unit Tests

```bash
pnpm test              # Run all unit tests
pnpm test -- --watch   # Watch mode
pnpm test:coverage     # With v8 coverage report → coverage/
```

## Browser Package Tests

```bash
pnpm build
pnpm exec playwright install chromium
pnpm test:browser
```

On machines with branded Chrome but no downloaded Playwright Chromium, run
`PLAYWRIGHT_CHANNEL=chrome pnpm test:browser`. The channel applies to the complete browser suite.
For Python E2E runs, use `PPTX_E2E_BROWSER_CHANNEL=chrome`; the same value is also consumed by the
evaluation API server.

These tests load the built standalone browser artifact with a tracked PPTX, initialize
every renderer-supported ECharts series through the modular runtime, verify computed
overflow behavior for all text-axis combinations, and execute the actual outer-Worker
plus PDF.js-worker path. CI runs the PDF test against both supported PDF.js major lines;
Node-only imports are not accepted as browser compatibility evidence. The Vite test server allows
the resolved `pdfjs-dist` package root explicitly, including when a worktree's dependency symlink
points outside the worktree. Set `PDFJS_DIST_DIR` to test a different installed PDF.js package.

The dedicated `compatible-content-package.spec.ts` generates an OPC PPTX package and
loads it through the built exported `parseZip`, `buildPresentation`, `renderSlide`, and
serialization APIs. It checks eager/lazy MCE selection and nested order, decoded SVG/OLE
picture previews, and actual chart Canvas colors for local override/identity/absence while
ordinary slide colors retain the parent map. Run it alone after a build with:

```bash
pnpm exec playwright test --config test/browser/playwright.config.ts test/browser/compatible-content-package.spec.ts --workers=1
```

Other coverage specs exercise source modules for focused text, table/chart, and media/lifecycle
interactions. Keep these distinct from built-package coverage and PowerPoint oracle evidence.
Browser media tests explicitly await image decoding/playback; `handle.ready` covers scheduled
renderer work, not automatic playback or every browser decoder completion. Hidden charts can
initialize after visibility returns. H264 checks require branded Chrome; default Chromium still
runs WAV/WebM checks.

Coverage areas:

- Parser safety and correctness (ZipParser, relationship parsing, EMU/angle/PCT unit conversion)
- Shape geometry (preset shape path tests in `test/unit/shapes/presets.test.ts`)
- Renderer behavior (batching, windowed mounting, hyperlink safety)
- Color utilities (HSL/RGB conversion, lumMod/lumOff/tint/shade modifiers)

## OOXML Geometry Compiler Gate

The full-corpus compiler and emitter remain development tooling. A generated production subset
routes 29 definitions through `src/shapes/ooxmlGeometryRuntime.ts`: all 28 zero-adjustment
flowcharts in shape IDs 61-88 (20 one-path and eight ordered three-path definitions), plus `donut`
with pinned `adj=25000` default and `0..50000` handle bounds. Other presets remain handwritten.
Focused tests cover every guide-formula operator, PowerPoint
numeric deviations, predefined guides, ordered guide rebinding, adjustment overrides, every IR
section, all six path commands, path-coordinate scaling, non-circular elliptical arcs,
positive/negative sweeps, full circles, serialization rounding, runtime/build-time parity,
multi-path fill/stroke order, picture silhouettes, and error boundaries.

```bash
pnpm exec vitest run \
  test/unit/build/ooxmlGeometrySource.test.ts \
  test/unit/build/ooxmlGeometryIr.test.ts \
  test/unit/build/ooxmlGeometryPathEmitter.test.ts \
  test/unit/shapes/ooxmlGeometryRuntime.test.ts

pnpm geometry:check
```

`geometry:check` verifies the vendored ECMA archive/XML hashes, reconciliation rules, generated
catalog bytes, complete IR structural SHA-256, and default evaluation plus SVG emission of all
186 unique shapes at 216x216, 400x180, and 180x400. Each emitted profile requires all 319 paths
to be non-empty, rejects non-finite output, and has its own SHA-256. The command also verifies the
generated production-subset module byte-for-byte. These checks establish deterministic compilation
and path serialization. Browser and native PowerPoint equivalence remain separate per-shape gates.
The browser gate renders all 29 production definitions, checks the eight multi-path flowcharts as
three ordered SVG paths, and exercises donut bounds in standalone, non-uniform group, and adjusted
picture-clip contexts. The native flowchart gate compares all 28 presets against PowerPoint in 28
cases and 84 slides: square explicit paint, wide theme-reference paint, and tall rendering through a
non-identity group. The bounded donut gate remains separate. Both record per-case provenance,
runtime errors, review status, and metric deltas from a fresh clean baseline.

Report native comparisons with the exact source revision, case IDs, environment, errors,
pre-existing metric failures, new regressions, and visual-review status. A sampled run is not a
full-corpus acceptance result. Do not change thresholds or baseline images to hide failures.
The API exposes per-slide runtime failures through `evaluationErrorCount` and `evaluationErrors`;
they are excluded from visual metrics and reported as runtime errors. The batch runner retries
HTTP and per-slide runtime errors once by default (`--retries`) for explicit and discovered cases.
Unresolved native questions (including negative percent-stacked chart normalization and text
inheritance through some empty body-property/autofit combinations) need specific native evidence.

## E2E Tests

### Setup

```bash
cd test/e2e
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

`pytest-timeout` is installed by the E2E package and enforces the suite-wide 180-second per-test
limit. The suite uses explicit `asyncio.run(...)` calls rather than pytest async test functions.

### Running

```bash
# Start dev servers first (from project root)
pnpm dev:e2e    # Vite :5173 + Python API :8080

# Then run tests
cd test/e2e
pytest -v                       # All E2E layers
pytest test_structural.py -v    # Layer 1: model structure vs ground truth
pytest test_visual.py -v        # Layer 2: HTML screenshots vs PDF (SSIM >= 0.65/slide)
pytest test_regression.py -v    # Layer 3: scores vs stored baselines
```

The default corpus is `testdata/cases`. Windows-generated oracle cases live under
`testdata/windows-cases` and can be selected without changing test code:

```bash
pytest -v --testdata-source=windows    # Windows-generated cases only
pytest -v --testdata-source=all        # Default + Windows-generated cases

# Equivalent environment override:
PPTX_E2E_TESTDATA_SOURCE=windows pytest test_visual.py -v
```

Windows case ids are encoded with a `win__` prefix during pytest
parametrization so baseline/report filenames stay distinct from default cases.

### Local Corpus Contract

Binary oracle artifacts stay local under `test/e2e/testdata/` and are ignored by Git:

- `cases/{stem}/source.pptx`
- `cases/{stem}/ground-truth.pdf`
- optional `cases/{stem}/slides/slide{N}.png`

Keep the generator, tracked case JSON, and its `coverage` metadata in the repository. This
preserves case IDs, intended OOXML features, required fonts, and the native-oracle requirement
without committing large or licensed files. Generation reports record SHA-256 hashes for local
artifacts; visual evaluation reports independently fingerprint the exact inputs they consumed.

### Test Layers

| Layer               | File                             | What it checks                                              |
| ------------------- | -------------------------------- | ----------------------------------------------------------- |
| Structural          | `test_structural.py`             | Word coverage, shape count/position from exported model     |
| Visual              | `test_visual.py`                 | SSIM between HTML screenshots and PDF pages                 |
| Regression          | `test_regression.py`             | No score drops > 0.02 SSIM or 2% text coverage vs baselines |
| Baseline generation | `test_oracle_case_generation.py` | Baseline case JSON validity and generation pipeline         |

## Baseline-Driven Shape/SmartArt Evaluation

The baseline pipeline is the primary tool for expanding and verifying rendering quality. It generates isolated test cases (one shape or SmartArt layout per slide), renders them, and compares against PowerPoint output.

### Running Baseline Evaluation

```bash
cd test/e2e
source .venv/bin/activate

# Evaluate all preset shapes (by MsoAutoShapeType ID)
.venv/bin/python3 scripts/run_all_shapes_eval.py --shape-id-min 1 --shape-id-max 200

# Evaluate all SmartArt layouts
.venv/bin/python3 scripts/run_all_shapes_eval.py --smartart-cases-dir oracle/cases-full

# Both at once
.venv/bin/python3 scripts/run_all_shapes_eval.py \
  --shape-id-min 1 --shape-id-max 200 \
  --smartart-cases-dir oracle/cases-full

# Find failures
grep "False" reports/oracle-failures/all-shapes-eval.csv | sort -t, -k2 -n
```

Output files:

- `reports/oracle-failures/all-shapes-eval.json` — full metrics per case
- `reports/oracle-failures/all-shapes-eval.csv` — case,ssim,color_hist_corr,fg_iou_tolerant,chamfer_score,fg_iou,passed,needs_review
- `reports/<case>_slide0_{pdf,html,diff}.png` — visual comparison images

### Generating Ground Truth

Ground truth requires Microsoft PowerPoint (macOS or Windows). A VBA macro creates PPTX files and exports PDFs:

```bash
cd test/e2e
.venv/bin/python scripts/one_shot_full_ground_truth.py \
  --macro-host testdata/pptx-macro-host.pptm \
  --cases-dir oracle/cases-full \
  --testdata-dir testdata \
  --shape-id-min 1 \
  --shape-id-max 500
```

This generates/reuses ground truth for all SmartArt layouts available on the local PowerPoint build plus the specified shape ID range.

For text, shape-adjustment, zero-adjustment flowchart, bounded static DrawingML 3D, composite, and
chart interaction cases, use the python-pptx generator. It currently defines 176 cases: 59 text,
31 shape-adjustment, 28 flowchart, 17 static 3D, 20 composite, and 21 chart cases. Each flowchart
case maps one shape ID from 61 through 88 to its exact OOXML preset and contains three slides:
square explicit paint, wide theme-reference paint, and grouped tall explicit paint. The group uses
a non-identity child coordinate space, and every source keeps an empty `a:avLst` with no adjustment
guides. The static 3D matrix covers flat opt-out, picture and
shape containers, `twoPt:t` and `threePt:t` lighting, donut/ellipse/rect/roundRect, white contour,
wide/tall aspect ratios, a non-identity group, and the light rotation plus implicit defaults
observed in the local `model-platform` corpus. Its real-property sentinel also retains the coexisting picture
outline and outer shadow so the 3D effect is not tested in isolation from its actual container.
The seventeen cases are one opt-out control, nine single-slide positive bevel cases, one three-slide
ellipse matrix, one five-slide donut matrix, one six-slide omitted/explicit bevel-default matrix,
two six-slide camera-plane matrices, one three-slide
`perspectiveLeft` editable-text matrix, and one four-slide `perspectiveRight` picture matrix. The first
camera-plane row covers identity and 20°/30° rotated `orthographicFront`, then square, wide, tall,
theme-fill, and non-identity-group `perspectiveRelaxedModerately` rendering at the exact verified
120° field of view and camera rotation. The second proves scene-only implicit zero depth across
square/wide/tall solid planes, including the theme `effectRef=2` outer shadow on the projected
surface without filter clipping, and preserves square/wide/tall editable DOM text for the exact
`perspectiveContrastingRightFacing` tuple. The third camera matrix isolates the observed
`perspectiveLeft` camera at a 120-degree field of view with absent explicit rotation, `threePt:t`
lighting, no fill, `wrap="none"`, default top anchoring, and `spAutoFit` across square, wide, and
tall editable CJK/mixed-text planes. The fourth camera matrix preserves live PNG content under the
observed 95-degree `perspectiveRight` camera and implicit -20-degree longitude across square, wide,
tall, and real-corpus asymmetric-crop rows. The real-property slice is copied from the ignored local
corpus; the last three picture rows isolate horizontal, vertical, and combined nonnegative
`a:srcRect` crops against the existing no-crop control. The ellipse row spans square explicit paint, wide theme-reference paint,
and a tall ellipse under a non-identity group transform. The donut row spans the `0..50000`
adjustment bounds, the `25000` default, an adjusted wide theme-fill shape, and an adjusted grouped
tall shape. Together
they pin picture versus shape rendering, wide/tall extents, a non-identity parent group, contour
layering, stable repeated frames, unique SVG
effect IDs, distance-field texture readiness, no horizontal growth, picture-URL disposal, abort-safe
cleanup, and the flat fallback for an unsupported camera. The accepted support claim is limited to
the exact tuple in
`drawingml.shape.3d.top-bevel-contour`; a high aggregate score cannot broaden that registry scope.
An opt-in eight-case local matrix retains the original ellipse discovery probe and adds adjusted
donut, adjusted star, concave freeform, rotation, nested non-identity groups, glow interaction, and
an eleven-slide bottom-`relaxedInset` isolation matrix. The bottom-bevel rows compare flat versus full
scene tuples, implicit versus explicit 76200 EMU dimensions, material and light-rotation opt-outs,
live CJK text, a 5% alpha overlay, a `circle` neighbor, and square/wide/tall extents. Those cases use
the `oracle-local-shape3d-*` prefix, write metadata only below the ignored `oracle-runtime` directory,
and remain local evidence. Only the exact opaque bottom-front rows are consumed by the separately
bounded capability and native gate; the other local rows remain discovery evidence.
For the current macOS PowerPoint oracle, the implicit/explicit dimension rows, the explicit/omitted
light-rotation rows, and the `relaxedInset`/`circle` rows are byte-identical pairs. A matching
transparent flat control differs from the 5% alpha 3D row by at most one RGB level. The opaque
material opt-out remains intentionally distinct; this isolates the visible front-face response
from an invented bottom-edge geometry effect.
The CJK text matrix at IDs 0040-0055 covers square/no-wrap behavior, omitted and explicit autofit
modes, percentage and point line spacing, paragraph spacing, adjacent run spacing, centered text
inside a parent shape, and square/wide/tall `spAutoFit` growth. IDs 0052-0054 require native
PowerPoint and the renderer to retain the explicit 30 pt CJK run while growing the standalone text
box; ID 0055 is the inverse control where explicit horizontal and vertical overflow remain visible
and suppress shape growth. Browser coverage also checks that host `white-space` values cannot
change the result and that absolutely positioned siblings do not reflow.
Text IDs 0056-0059 cover color precedence independently from layout behavior: paragraph `defRPr`
`srgbClr` and `schemeClr` over a conflicting shape `fontRef`, an explicit run color over both, and
the inverse fallback to `fontRef` when local fills are absent. The cases span square, wide, and tall
containers and retain exact color values in their tracked OOXML metadata.

```bash
cd test/e2e

# Generate all definitions and native ground truth.
.venv/bin/python scripts/generate_pypptx_cases.py

# Generate the focused text matrices. --case is repeatable and accepts exact names or globs.
.venv/bin/python scripts/generate_pypptx_cases.py \
  --case 'oracle-pypptx-text-00[45]*'

# Generate only the bounded static DrawingML 3D matrix.
.venv/bin/python scripts/generate_pypptx_cases.py \
  --case 'oracle-pypptx-shape3d-*'

# Generate the 28-case, 84-slide zero-adjustment flowchart matrix.
.venv/bin/python scripts/generate_pypptx_cases.py \
  --case 'oracle-pypptx-flowchart-*'

# Generate the ignored local 3D discovery matrix. Add --pptx-only without PowerPoint.
.venv/bin/python scripts/generate_pypptx_cases.py \
  --include-local-shape3d-matrix \
  --case 'oracle-local-shape3d-*'

# Package-only inspection on a host without PowerPoint.
.venv/bin/python scripts/generate_pypptx_cases.py \
  --pptx-only \
  --case 'oracle-pypptx-text-0044-*'
```

macOS PowerPoint exports PDF ground truth. Windows PowerPoint exports PDF and, by default,
per-slide PNG. The generator refreshes tracked case metadata even when cached local binaries are
reused and writes artifact fingerprints to
`reports/oracle-failures/pypptx-ground-truth.json`, including every available slide PNG.
The local discovery definitions default to `oracle-runtime/local-shape3d-cases/`; they never write
into tracked `oracle/cases-pypptx/` and do not change the 176-case default matrix.

The top-bevel capability also has a region-level lighting gate. After clean native API reports for
cases 0001-0012 and 0017 have refreshed `reports/<case>_slide0_{pdf,html}.png`, run:

```bash
# Run from the repository root; report paths are repository-relative.
test/e2e/.venv/bin/python test/e2e/scripts/shape3d_bevel_metrics.py \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0001-flat-optout.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0002-picture-rect-circle-bevel.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0003-roundrect-bevel-contour.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0004-wide-bevel.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0005-tall-bevel.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0006-grouped-bevel.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0007-real-picture-bevel-slice.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0008-picture-horizontal-crop-bevel.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0009-picture-vertical-crop-bevel.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0010-picture-asymmetric-crop-bevel.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0011-ellipse-circle-bevel-matrix.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0012-donut-circle-bevel-adjustment-matrix.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0017-default-top-bevel-dimensions-matrix.json \
  --out test/e2e/reports/capability-loop/shape3d-bevel-local-<revision>.json
```

The metric extracts shape bounds, group transforms, ellipse contours, round-rectangle corners, and
donut inner/outer radii independently from source OOXML, then compares luminance only in the inward
bevel ring. Unknown silhouettes and rotated shapes fail as unevaluable instead of being scored with
a rectangular mask. The schema-v6 gate requires a general field score of at least `0.60`, dynamic
range ratio `0.85`, shadow-amplitude ratio `0.85`, and candidate/native shadow overshoot no greater
than `1.05`; solid donut faces use the tighter native-backed `1.01` peak ceiling and a `1.05`
ceiling for mean negative shadow energy. The energy check catches a wider/heavier dark band even
when its 5th-percentile amplitude is correct. Solid-shape highlight
amplitude requires `0.80`; picture lighting uses its separately verified `0.70` floor. Verified
`roundRect` corners also require `0.78`. The symmetric amplitude
ratios catch large weak or excessive lighting, while the directional ceiling rejects a smaller but
visible over-dark edge even when correlation leaves the composite score high. A zero-thickness
donut stays in the full-slide native gate because it has no interior bevel surface. A band below
four output pixels is explicitly recorded as
resolution-limited and remains covered by full-slide and manual gates rather than guessed from too
few pixels. The flat control has no applicable region. This local metric complements the full-page
SSIM/color-histogram gate; it does not replace it. Each native API slide row fingerprints the exact
reference and HTML rasters. The metric generator rejects a stale or replaced raster before scoring.
Case 0017 additionally declares three implicit/explicit slide pairs. The same report requires exact
reference-raster equality and exact candidate-raster equality for every pair, so a parser-default
regression cannot hide behind a high full-slide score.
It is also sensitive to material-specific lighting: the tracked picture case must retain the native
top/right shadow and bottom/left relief instead of passing only because its rectangular bounds match.

The camera-plane capability has a separate local gate. After all clean camera case reports have
refreshed the native and HTML rasters, run:

```bash
test/e2e/.venv/bin/python test/e2e/scripts/shape3d_camera_metrics.py \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0013-camera-projection-matrix.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0014-scene-only-plane-matrix.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0015-perspective-left-text-plane-matrix.json \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-pypptx-shape3d-0016-perspective-right-picture-plane-matrix.json \
  --out test/e2e/reports/capability-loop/shape3d-camera-local-<revision>.json
```

Run the bounded bottom-front capability against its own clean native report:

```bash
test/e2e/.venv/bin/python test/e2e/scripts/shape3d_camera_metrics.py \
  --case-report test/e2e/reports/capability-loop/current-<revision>-oracle-local-shape3d-0008-bottom-relaxed-inset-matrix.json \
  --out test/e2e/reports/capability-loop/shape3d-bottom-front-local-<revision>.json
```

This schema-v5 gate derives each applicable modality from source OOXML and binds both raster hashes
to the native API report. Solid rows extract the largest saturated four-corner plane independently
from renderer DOM bounds: normalized corner score must be at least `0.98`, material-band color
score at least `0.97`, and a measurable native gradient requires at least `0.65` range ratio and
`0.95` direction cosine. When source OOXML selects the exact verified theme outer shadow, the native
reference must expose enough external shadow energy to be measurable; the candidate then requires
at least `0.70` symmetric energy ratio and `0.95` direction cosine. This rejects a visible but
materially weaker shadow instead of treating mere presence as fidelity. Live-text rows use a
resolution-normalized raster tolerance of `0.25%`, then require bidirectional foreground F1 `0.90`,
tolerant projected-bounds score `0.98`, and grayscale ink-density retention `0.90`. Picture rows are
inverse-projected to `384×384` and require corner score `0.98`, rectified color score `0.95`, and
tolerant edge F1 `0.90`; this makes crop/content errors visible even when the outer quadrilateral is
correct. Raw IoU and raw bounds stay in the report for diagnosis. The verifier recomputes pass
status and derived ratios from fixed thresholds. It also requires deterministic mutation controls
to fail: exterior-shadow erasure on every measurable shadow row and a 12% left crop plus rescale on
every rectified picture row. Bottom-front rows require normalized corner score `0.98`, mean RGB
error no greater than `1.0` across three interior material bands, and rejection after restoring the
source flat `#4472C4` fill. A corpus row whose local metric cannot detect its matching mutation is
not promotable. Callers cannot self-attest any modality.

PowerPoint automation on macOS needs an available interactive session. Error `-9074` can mean the
session is locked, PowerPoint is waiting for a dialog, or the fixed staged input is still open from
an interrupted run; it is an environment failure, not a renderer result. Ordinary exports stage
`_pptx-input.pptx` and `_pptx-output.pdf` in the ignored `testdata/oracle-runtime` directory; grant
PowerPoint access to that directory once. Each script normalizes macOS's `/private/tmp` firmlink to
the `/tmp` spelling returned by PowerPoint, matches the opened file by exact `full name`, never
exports or closes `active presentation`, and closes only the matched object on success or failure.
If PowerPoint cannot compile the file-backed export script (`-2741`), the exporter retries the same
exact-path lifecycle as inline AppleScript within the same attempt. Macro names are qualified with
their loaded `.pptm` filename because an unqualified name can return PowerPoint error `-18` when
another deck is open. The 120-second export and macro timeouts stop without retry and tell the
operator to check the unlock state and any pending **Grant File Access** or macro-security dialog.
Stale output PDFs are removed before each attempt. AppleScript stderr remains in the reported
error.

The native macro smoke uses `ExportSmartArtLayouts_ToFile` with a fixed runtime output and verifies
that the resulting catalog is non-empty. Run it only on a host where the repository macro host is
trusted:

```bash
cd test/e2e
.venv/bin/python -m pytest -q test_oracle_macro_pipeline.py
```

### Reproducing Fonts in Oracle Runs

Text metrics are only comparable when the browser can use the same font faces as PowerPoint.
Create an ignored profile under `test/e2e/testdata/` using
`test/e2e/oracle/font-profile.example.json` as the format. Each `path` is relative to the testdata
root; it may be an ignored symlink to a locally installed and properly licensed font. Do not copy
or commit proprietary font files.

Start the API with an explicit code server, browser channel, and profile:

```bash
# Terminal 1, project root
pnpm dev --host 127.0.0.1 --port 5183 --strictPort

# Terminal 2, test/e2e
PPTX_E2E_VITE_SERVER_URL=http://127.0.0.1:5183 \
PPTX_E2E_FONT_PROFILE=font-profiles/local-office-fonts.json \
PPTX_E2E_BROWSER_CHANNEL=chrome \
.venv/bin/python server.py
```

`PPTX_E2E_API_PORT` can move the API from port 8080 when needed. The single-slide page accepts
the corresponding `fontProfile` query parameter and passes those faces to `renderSlide()` before
layout measurement.

Every `/api/evaluate/{case}` response includes `provenance` with:

- source PPTX and ground-truth kind, size, and SHA-256;
- renderer Git revision and tracked dirty state;
- OS/Python details and the actual browser version;
- optional font-profile manifest and font-file hashes.

`scripts/run_all_shapes_eval.py` preserves this object in every `results[]` row. Compare or update
a baseline only when the input hashes and relevant runtime profile match; otherwise treat the
difference as an environment/corpus change and rerun before changing renderer code.

### Manual Review

For cases that pass automated metrics but have visual nuances:

1. Open `/test/pages/e2e-compare.html`
2. Review side-by-side PDF vs HTML renders with SSIM scores
3. Save verdicts per slide card
4. Verdicts persist in `reports/oracle-failures/manual-review.json`

## Visual Evaluation Metrics

The comparison pipeline uses a **two-layer metric system**. This design was arrived at empirically by testing many metrics against 300+ shape cases.

### Pass/Fail Layer (automated)

These two metrics determine automated pass/fail for this oracle evaluator. Their thresholds are regression gates, not proof that every feature is correct or that the corpus has no failures:

| Metric            | Range   | Threshold | What it catches                                                                 |
| ----------------- | ------- | --------- | ------------------------------------------------------------------------------- |
| `ssim`            | 0-1     | >= 0.95   | Structural errors: wrong geometry, missing elements, layout shifts              |
| `color_hist_corr` | -1 to 1 | >= 0.80   | Color errors: wrong scheme resolution, gradient bugs, tint/shade misapplication |

### Warning Layer (human review)

| Condition                       | Flag                | Purpose                                                     |
| ------------------------------- | ------------------- | ----------------------------------------------------------- |
| Any visible slide `ssim < 0.99` | `needsReview: true` | Flags near-misses for human inspection without auto-failing |

The case-level flag is the union of visible per-slide review flags, evaluation errors, and detected
oracle page mismatches. A high multi-slide average cannot hide one page that needs inspection.

### Diagnostic Layer (display only)

These metrics appear in the UI for reference but do not affect pass/fail:

| Metric            | Range | Description                                    |
| ----------------- | ----- | ---------------------------------------------- |
| `fg_iou`          | 0-1   | Foreground pixel IoU (non-white pixel overlap) |
| `fg_iou_tolerant` | 0-1   | FG IoU with 1px morphological dilation         |
| `chamfer_score`   | 0-1   | 1 - normalized Chamfer Distance                |
| `mae`             | 0-1   | Mean Absolute Error per pixel                  |

### Why Only SSIM + Color Histogram?

- **`fg_iou` was removed from pass/fail** — thin-stroke shapes (brackets, braces, arcs) get ~50% IoU drop from 1px anti-aliasing differences despite correct geometry.
- **`chamfer_score` was not promoted** — its "dilution effect" masks localized errors when most of the shape is correct.
- **SSIM and color histogram are complementary signals.** Color histogram adds sensitivity to pure-color errors, while both can miss localized semantic defects, incorrect branch selection, or lifecycle behavior. Use source-based assertions, decoded media/Canvas checks, and native visual inspection for those boundaries.

Previously evaluated but rejected: `edge_iou` (too noisy), `fg_area_ratio` (redundant), `fg_centroid_distance` (no observed failures), patch-based SSIM (can't detect < 1% area defects), LPIPS (heavy PyTorch dependency, marginal improvement).

### Color Histogram Correlation Details

- Computed over H, S, V channels independently (30 H bins, 32 S/V bins), then averaged
- Only foreground pixels (gray < 245) are compared, ignoring white backgrounds
- Each channel tolerates a one-bin displacement before correlation (circular for hue, clamped for
  saturation/value), preventing a small color quantization shift from becoming a false mismatch
- Sparse foreground in both images (< 1.5% coverage) returns 1.0 to avoid anti-aliasing noise on
  thin-stroke shapes
- When only one image has foreground, it remains a mismatch unless that image contains at most
  0.01% black-equivalent ink, which covers visually blank PDF anti-alias residue without hiding a
  meaningful missing line
- Score of 1.0 = identical color distributions; >= 0.80 = pass threshold

## Shape Fix Protocol (TDD Required)

For complex shape regressions (curved arrows, multi-segment geometry, 3D faces):

1. Isolate one baseline case ID and one slide.
2. Record baseline metrics (`ssim`, `color_hist_corr`, `fg_iou`, `chamfer_score`).
3. Extract ground-truth geometry from ECMA-376 `presetShapeDefinitions.xml` before editing path code.
4. Add a failing unit test for the specific mismatch.
5. Implement minimal geometry patch.
6. Verify: unit tests pass, baseline metrics do not regress, visual review confirms correctness.
7. Only then mark the case fixed and move to the next.

Do not use blind parameter tuning. When topology or shape semantics are wrong, derive the fix from the OOXML spec.

### Spec-Compiled Geometry Source Gate

The M0 geometry source contract is independent of local PowerPoint ground-truth files:

```bash
pnpm geometry:generate  # regenerate after an intentional source or contract change
pnpm geometry:check     # validate source hashes and fail on generated drift
pnpm exec vitest run \
  test/unit/build/ooxmlGeometrySource.test.ts \
  test/unit/build/ooxmlGeometryIr.test.ts \
  test/unit/build/ooxmlGeometryPathEmitter.test.ts \
  test/unit/shapes/ooxmlGeometryRuntime.test.ts
```

`geometry:check` validates the unchanged ECMA archive and nested XML hashes, all 17 formula
operators and arities, document-order guide references, DrawingML path namespaces and
command structure, duplicate-source handling, source reconciliation, deterministic catalog
bytes, finite IR evaluation, and deterministic SVG emission. It runs in CI before the package
build.

The generated catalog is evidence about source coverage; it is not renderer acceptance. The
production subset is a separate generated module and currently contains 29 definitions: all 28
zero-adjustment flowcharts in shape IDs 61-88 (20 single-path and eight ordered three-path
definitions), plus bounded-adjustment `donut`.
Before adding a definition, add tests for formula semantics and path topology plus browser checks
for both ordinary shapes and picture clips. Then compare square, wide, and tall shapes and
relevant adjustment bounds against native PowerPoint ground truth. Group, flip, rotation,
line-like, and multi-path cases require their own coverage when applicable.

M0 rejects active source overrides. Before enabling one, add an offline check that reads the
alternative source bytes, verifies their SHA-256 and requested shape, and resolves an
existing native PowerPoint oracle record. Do not update a visual baseline merely to make a
generated definition pass.

## Capability Loop Contract

The capability loop turns corpus observations into one reviewable renderer cohort at a time. Its
tracked inputs are `test/e2e/oracle/capabilities.json` and
`test/e2e/oracle/capability-acceptance.json`. Its local inventory, ledger, ranking, work packet, and
verification files stay ignored under `test/e2e/reports/capability-loop/`.

```bash
# CI-safe contract check; requires no private corpus or PowerPoint installation
pnpm capability:check

# Scan the default ignored testdata/cases corpus
pnpm capability:inventory

# Add more local corpora and an optional read-only issue snapshot
python3 test/e2e/scripts/run_capability_loop.py inventory \
  --corpus test/e2e/testdata/cases \
  --corpus test/e2e/testdata/windows-cases \
  --issues docs/agent-tmp/open-issues.json
```

The scanner reads ZIP members in memory without extracting them. It rejects path traversal, more
than 4,000 entries, a decoded entry over 32 MiB, or more than 256 MiB decoded in total. Identical
PPTX bytes count once for ranking while all corpus aliases remain available in the ignored report.
Selectors match XML namespace, local name, and optional attribute predicates; similarly named
elements from unrelated namespaces do not count. A rejected package is isolated and recorded with
a stable reason so the rest of a private corpus still produces evidence; add `--fail-on-rejected`
when any rejected package must also make the command exit nonzero.

Ranking is lexicographic and retains every input dimension: impact, currently reproduced issues,
unique observed packages, failure type, native-oracle readiness, dependency depth, then capability
ID. It does not generate a weighted quality percentage. `unknown`, stable `verified`, and externally
`blocked` rows remain visible in the ledger but do not enter the executable queue. An open issue only
contributes demand after the issue snapshot explicitly records a current reproduction.
Selecting anything other than the first executable row requires `work-packet --selection-reason`;
the resulting packet records both the original rank and the reason, such as a previously committed
release goal.

Normalize committed, clean native API results before promotion:

```bash
python3 test/e2e/scripts/run_capability_loop.py verify \
  --capability drawingml.shape.geometry.adjustment.donut \
  --case-report test/e2e/reports/capability-loop/donut-thin-native.json \
  --case-report test/e2e/reports/capability-loop/donut-thick-native.json \
  --baseline-report test/e2e/reports/capability-loop/donut-thin-baseline.json \
  --baseline-report test/e2e/reports/capability-loop/donut-thick-baseline.json \
  --oracle powerpoint-macos \
  --passed-gate source --passed-gate structural --passed-gate unit \
  --passed-gate browser --passed-gate docs
```

`verify` checks one clean renderer revision, exact case/input/ground-truth hashes, API runtime
errors, PowerPoint quality status, matching baseline case IDs, and the 0.02 SSIM regression budget.
Regression baselines must use one earlier clean revision with identical source, ground-truth, and
runtime-environment fingerprints.
It derives `native-powerpoint`, `manual-visual`, and `regression`; callers cannot self-attest those
gates. A capability that requires `bevel-local` must also supply `--bevel-report`, while one that
requires `camera-local` must supply `--camera-report`. Verification derives either local gate only
when the clean revision, exact case set, source hashes, ground-truth hashes, native per-slide raster
hashes, on-disk raster hashes, thresholds, and every local result match. `--passed-gate` records
separate checks that have already run and does not execute them. A `needsReview` case requires
`--manual-verdict CASE_ID=passed` (or `accepted`).

Promotion uses the `accept` command only after the capability registry says `renderMode=native` and
the candidate implementation is committed. The command requires a clean tracked tree, matching
HEAD and relevant-file fingerprints, source and ground-truth SHA-256 values, every declared gate,
no skipped/runtime-failed cases, and an accepted manual verdict for every review row. It writes a
sanitized receipt atomically and never changes GitHub issues or visual baselines.

DrawingML shape 3D, chart 3D, Office 2017 embedded models, and PresentationML animation are separate
capability IDs. A verified flat 2D fallback in one lane cannot promote native behavior in another.
The `drawingml.shape.3d.top-bevel-contour` cohort promotes only `orthographicFront` circular top bevels on opaque
solid `donut`/`ellipse`/`rect`/`roundRect` shapes and rectangular stretch-filled pictures, with absent or bounded
nonnegative `a:srcRect` crops, the documented `twoPt:t`/`threePt:t` lighting tuple, zero extrusion
and `z`, no scene backdrop or extrusion color, an optional contour with a resolvable color, and an
optional outer shadow. The visual gate checks
that `bevelT@w` controls the inward edge width,
`bevelT@h` changes contrast rather than geometry, directional lighting remains distinct, and rounded
corners follow continuous silhouette normals. The default-value matrix additionally requires
omitted `prst`, `w`, or `h` to match explicit `circle`/76200-EMU encodings exactly. The picture row additionally verifies the lower
relative-overlay response and native `twoPt:t` edge ordering. Verification
uses cases 0001-0012 plus 0017 and the same thirteen earlier-revision baselines,
the derived `bevel-local` report, explicit manual verdicts for review rows, and the `source`,
`structural`, `unit`, `browser`, `performance`, `package-size`, and `docs` caller-run gates.

The separate `drawingml.shape.3d.camera-projected-plane` cohort uses cases 0013-0016. It promotes
exact zero-depth solid rectangles, two scene-only no-fill live-text tuples, and one live-picture
tuple with absent or bounded nonnegative source crop; all exclude local transform, backdrop,
nonzero `z`, explicit effect lists, bevel, contour, extrusion color, and material. The scene-only
solid row retains the exact theme outer-shadow style; the text rows exclude `p:style`, vertical text,
independent bounds, and
local body properties outside the registry's `wrap`, anchor, and autofit tuples. Its exact cameras, paint values,
aspect ratios, container rows, and implicit-depth semantics are declared in the registry. The
picture row additionally excludes visible outlines, non-rectangular geometry, `a:fillRect`, tiles,
style references, picture background fills, blip effects, and degenerate crops. Verification uses
all earlier/current report pairs plus the derived schema-v5 `camera-local` plane/text/picture report
and the same caller-run gate classes. The broad
`drawingml.shape.3d.scene` fallback remains in inventory as a conservative residual, so observing a
verified narrow tuple cannot hide unimplemented scene values.

The separate `drawingml.shape.3d.bottom-bevel-front-material` cohort promotes only the exact
standalone opaque rectangle rows declared in the registry: default-size `relaxedInset`/`circle`
bottom bevel, `orthographicFront`, bounded `threePt:t` rotation, zero depth, `dkEdge` or implicit
material, and the three verified aspect ratios. It retains live centered text, emits a uniform
native front-face color, draws no bottom rim, and requires the schema-v5 bottom-material modality
plus its restored-flat-fill mutation.

Other perspective and arbitrary rotations, nonzero extrusion, materials and bottom bevels outside
that exact cohort, tiled pictures,
negative or degenerate source crops, other paint/effect combinations, and other shape or picture
presets remain flat fallbacks. Opt-in local probes for these contexts do not promote the public
support boundary.

## Chart Fix Protocol

Chart rendering is validated at two levels:

1. Add focused unit tests in `test/unit/renderer/ChartRenderer.test.ts` for OOXML
   semantics such as stacking mode, axis orientation, per-point data labels,
   chart color styles, legend data, and combo-axis wiring.
2. Run targeted oracle comparisons through the E2E API or pytest. Use
   `--testdata-source=windows` for Windows-generated chart oracle cases, which
   include many Office chart defaults not present in lightweight generated decks.

Current chart 3D support is intentionally a 2D fallback for render continuity.
Do not treat `surface3DChart` or 3D perspective/depth mismatches as fixed unless
there is a real 3D rendering implementation and corresponding oracle coverage.

## Test Pages

| Page                                 | Purpose                                                        |
| ------------------------------------ | -------------------------------------------------------------- |
| `/test/pages/index.html`             | Upload preview with model search and lazy thumbnail navigation |
| `/test/pages/render-slide.html`      | Single slide at native resolution                              |
| `/test/pages/e2e-compare.html`       | E2E dashboard with SSIM scores                                 |
| `/test/pages/compare-renderers.html` | Renderer-to-renderer comparison                                |
| `/test/pages/export.html`            | Model JSON tree viewer                                         |

URL params for list rendering performance: `listStrategy`, `listBatchSize`, `windowedInitialSlides`, `windowedOverscanViewport`.

## Contribution Requirement

For behavior changes:

- Add or update at least one relevant test.
- Keep existing test suite green before opening PR.
- For shape geometry changes, run the baseline evaluation on affected cases.
