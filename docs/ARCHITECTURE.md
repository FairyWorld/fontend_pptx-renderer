# Architecture

`@aiden0z/pptx-renderer` follows a three-stage pipeline:

1. Parse
2. Model
3. Render

Renderer evolution is governed by a separate evidence loop. It observes source packages and test
results, but does not bypass or rewrite the Parse → Model → Render boundaries.

## Capability Evidence Boundary

`test/e2e/oracle/capabilities.json` is the tracked support contract. Each stable capability ID
declares namespace-aware OOXML selectors, a bounded scope, current render mode, fallback, relevant
implementation/test paths, and required gates. `capability-acceptance.json` stores only sanitized
promotion receipts; private PPTX/PDF/PNG artifacts and generated inventory remain ignored.

The loop has five domain modules and a thin CLI:

- `capability_contract.py` validates immutable registry and receipt types.
- `capability_inventory.py` scans PPTX ZIP/XML within fixed entry and decoded-byte limits and
  deduplicates packages by SHA-256.
- `capability_evidence.py` binds receipts to capability definitions, relevant file content, source
  PPTX, ground truth, gates, environment, and revision.
- `capability_verification.py` normalizes native evaluation API results, rejects mixed or dirty
  revisions, and derives native, manual-review, and SSIM-regression gate outcomes.
- `capability_ranking.py` applies a documented lexicographic priority and emits one bounded work
  packet.
- `scripts/run_capability_loop.py` composes `validate`, `inventory`, `rank`, `work-packet`,
  `verify`, and `accept`; it does not edit GitHub issues or accept visual baselines.

Render mode and evidence state are independent. Render modes are `none`, `fallback`, `approximate`,
`native`, and `excluded`; evidence moves through `unknown`, `observed`, `reproducible`, `candidate`,
`verified`, `regressed`, or `blocked`. User-facing support requires both `native` and `verified` for
the declared scope. A relevant implementation or scope change invalidates the receipt, while an
unrelated documentation-only commit does not.

## 1) Parse Layer

Core modules:

- `src/parser/ZipParser.ts`
- `src/parser/XmlParser.ts`
- `src/parser/RelParser.ts`

Responsibilities:

- Open PPTX ZIP package and read entry files.
- Enforce resource limits (`ZipParseLimits`) to reduce DoS surface.
- Parse OOXML + relationship targets into safe intermediate structures.

## 2) Model Layer

Core modules:

- `src/model/Presentation.ts`
- `src/model/Slide.ts`
- `src/model/nodes/*`
- `src/search/TextSearch.ts`

Responsibilities:

- Build normalized in-memory presentation model.
- Resolve layout/master/theme inheritance.
- Parse node-level geometry, text, style, and relationship references.
- Optionally defer per-slide node parsing with `lazySlides` until render, search, or
  serialization consumes that slide.
- Build model-level text indexes and search results that are independent of mounted DOM.

## 3) Render Layer

Core modules:

- `src/core/Viewer.ts` — `PptxViewer` (primary API, extends `EventTarget`)
- `src/core/Renderer.ts` — `PptxRenderer` (deprecated v1 wrapper, extends `PptxViewer`)
- `src/renderer/SlideRenderer.ts` — returns `SlideHandle` with per-slide resource lifecycle
- `src/renderer/*Renderer.ts`

Responsibilities:

- Convert model into DOM elements per slide.
- Handle list/single-slide render modes via `renderList()` / `renderSlide()`.
- Instance-level `open()` for one-call parse→build→render (static `PptxViewer.open()` delegates to this).
- Render lifecycle events: `renderstart` / `rendercomplete` bracket every render cycle; `slidechange` fires after render.
- A newer render request supersedes older queued or batched work; stale list batches stop at frame boundaries before appending more DOM.
- Typed `on()` / `off()` helpers and state getters (`isRendering`, `zoomPercent`, `fitMode`).
- Manage media object URL lifecycle (blob URLs tracked per-handle and per-viewer).
- Handle internal/external navigation (with URL safety checks).
- Expose external slide rendering, scaled thumbnail preview, and search highlight helpers.
- Render common EMF fallback previews when the file contains embedded bitmap data or,
  with optional `pdfjs` URLs, an embedded PDF preview.

### Async Resource Lifecycle

Each `renderSlide()` call owns an `AbortController`. `SlideHandle.dispose()` aborts
in-flight EMF-PDF work before disposing chart instances and owned blob URLs. Async
renderers must check the context signal before mutating DOM or shared caches, and must
revoke any blob URL that arrives after cancellation. `PptxViewer.destroy()` disposes its
slide handles before clearing the viewer-level media cache.

PDF.js runs inside a short-lived isolated Worker, with PDF.js using its own nested Worker.
Success, worker error, timeout, and cancellation share one cleanup path that terminates
the outer Worker. No PDF.js module state is imported or configured on the host page.

### Chart Runtime and Distribution

`src/renderer/chart/echartsRuntime.ts` is the only runtime ECharts registration point. It
imports from `echarts/core`, registers every supported chart/component plus
`CanvasRenderer`, and is explicitly declared as side-effectful package code. Type-only
imports may still come from `echarts` without pulling the full runtime into the bundle.

The normal ESM/CJS builds externalize `echarts/*` and JSZip for application bundlers. The
`./browser` entry bundles JSZip and the registered ECharts subset while keeping PDF.js
optional and external.

## OOXML Geometry Compilation Boundary

The handwritten `src/shapes/presets.ts` registry remains the compatibility geometry engine. The
M0-M4 tooling under `scripts/ooxml-geometry/` pins and validates the ECMA-376 DrawingML geometry
addendum, implements the complete guide-formula contract, compiles all unique definitions into
renderer-independent plain data, and emits deterministic SVG paths. The generator also writes a
tree-shakeable production subset to `src/shapes/generated/ooxmlPresetGeometrySubset.ts`.
`src/shapes/ooxmlGeometryRuntime.ts` evaluates that data before the handwritten lookup.
The subset contains 29 definitions: all 28 zero-adjustment flowcharts in shape IDs 61-88 (20
single-path definitions and eight ordered three-path definitions), plus `donut`. Donut generation
pins the source default (`adj=25000`) and its polar-handle bounds (`0..50000`) before admitting the
definition. Other shapes continue through the handwritten registry.

The compiled IR retains ordered adjustment/calculated guides, adjustment handles, connection
sites, text rectangles, path coordinate systems, path styling metadata, and the six DrawingML
path command kinds. Its evaluator resolves a concrete width, height, and named adjustment map
without DOM or SVG dependencies. The generation gate fingerprints the structural IR and
evaluates the complete corpus at square, wide, and tall extents.

Path emission scales each declared path coordinate space into the shape extent and converts
DrawingML visual-angle arcs into SVG ellipse segments. Full circles are split at serialization,
and output rounding is confined to that boundary. The runtime subset supports the same 17 formula
operators and predefined guides as the build-time evaluator. SVG fill/theme resolution, browser
masks, connector markers, picture/media ownership, effects, and render lifecycle stay in their
existing render modules. The multi-path adapter preserves each definition's ordered fill/stroke
records; the renderer still owns theme paint, dash/cap/join attributes, masks, effects, and image
layering. Generated paths retain the current per-node geometry cache and are not added to the
serialized presentation model. Picture preset clipping uses the first generated fill-bearing
silhouette, without adding detail or outline paths to the clip geometry. Picture nodes retain
preset-geometry adjustments so generated clipping uses the same bounded guide values as ordinary
and grouped shapes.

ECMA source differences are recorded through `source-reconciliation.json`. M1 rejects active
alternative definitions because it does not yet verify their bytes or native PowerPoint
evidence. A later override gate must verify the local source bytes and hash, confirm the
requested shape exists, and resolve native-oracle metadata before activation. Production
migration is per shape or shape family, so the existing handwritten implementation remains
active for shapes that have not passed that gate. Expanding the production subset requires
formula/IR parity, SVG structure, parent renderer, picture clip, browser, package, and current
native PowerPoint oracle evidence for the selected shape family.

### Text wrapping and shape autofit

`ShapeRenderer` resolves `a:bodyPr` through the existing shape/layout/master inheritance chain
before it chooses CSS wrapping, overflow, and autofit behavior. `wrap="square"` uses browser line
wrapping and `wrap="none"` uses a single-line container; both are written as inline styles so a
host page's `white-space` rule cannot replace the presentation semantics. Explicit
`horzOverflow` and `vertOverflow` values are resolved independently.

The three autofit choices remain mutually exclusive:

- `noAutofit` keeps the authored font size and applies the requested clip or overflow axes;
- `normAutofit` applies the serialized `fontScale` and `lnSpcReduction` within the fixed shape;
- `spAutoFit` measures the final browser text after fonts are ready. A square-wrapped,
  top/default-anchored standalone horizontal `txBox` with no explicit overflow override can grow
  when it contains multiple visible
  paragraphs, or when an explicit visible-run font size would otherwise require material
  single-line shrinking. The wrapper and its main SVG receive the same grown dimensions, while
  absolutely positioned siblings keep their coordinates.

Before every measurement pass, the renderer restores the authored wrapper, SVG, whitespace, and
transform state. This prevents fallback-font measurements from leaving stale growth after the
declared fonts become available. Other wrapping modes, center/bottom anchors, vertical text,
diagram-specific text bounds, non-text-box shapes, explicit overflow overrides, and compact labels
whose size comes only from inheritance remain on the bounded fit path. The native evidence is
therefore a finite text-box cohort, not a claim of editor-level parity for every PowerPoint autofit
context.

### Bounded static DrawingML 3D

`src/model/nodes/Shape3D.ts` parses direct `a:scene3d` and `a:sp3d` children into typed camera,
light, bevel, contour, extrusion, material, and color observations. It attaches those observations
to both shape and picture nodes and emits stable unsupported-reason codes. Serialization removes
the retained `SafeXmlNode` color source while preserving its JSON-safe observation, so detection is
available without exposing parser internals.

`src/renderer/Shape3DRenderer.ts` is a narrow decision and effect layer. It returns either an
`orthographic-top-bevel` plan or an explicit flat-fallback reason before touching the DOM. The
supported plan requires all of the following:

- `orthographicFront` without camera rotation;
- `twoPt:t` or `threePt:t` light, with no rotation except the real-corpus
  `twoPt:t/lat=0/lon=0/rev=120°` tuple;
- a positive circular top bevel, zero or omitted extrusion, an absent/zero contour or a positive
  contour with a resolvable color, no bottom bevel or preset material, and only an optional outer
  shadow in `effectLst`;
- an opaque resolved solid-fill `rect`/`roundRect` shape, or a rectangular stretch-filled picture.

The renderer builds one clipped SVG bevel overlay from `SourceAlpha`, `feDiffuseLighting`, and
`feSpecularLighting`, using bounded `userSpaceOnUse` filter coordinates and `linearRGB` filter
interpolation. It adds the contour as a separate unfiltered path, keeps shape text outside the
filter, and draws a 3D picture's ordinary outline as a centered SVG path so the image bounds do not
shrink. Unique per-effect IDs prevent cross-slide collisions. Existing wrapper transforms, outer
shadows, media ownership, and cleanup remain in their owning renderers.

Anything outside that full tuple stays on the existing flat path with a stable reason. Perspective,
nonzero extrusion, other materials/bevels/lights, gradient/pattern/group/image-filled shapes,
tiled pictures, chart `view3D`, and Office 2017 `model3d` are separate capability lanes. This SVG
surface model is a bounded static rendering, not a general mesh or PowerPoint material engine.

## Rendering Strategies

`renderList()` supports:

- Default (`windowed: false`): mount all slide DOM nodes.
- Windowed (`windowed: true`): mount near-viewport slides via `IntersectionObserver`, with fallback to full mode when unavailable.

This keeps default behavior backward compatible while enabling lower memory pressure for large decks.
For large viewer surfaces, `windowed: true` pairs with `lazySlides: true` so off-screen
slides do not pay shape/table/chart parsing cost before the first visible slides render.
For media-heavy decks, `lazyMedia: true` also keeps package media compressed until a
rendered slide references it.

## Search, Highlights, and Scaled Previews

Text search is a model-layer feature. `buildTextIndex()`, `searchText()`, and
`searchPresentation()` read normalized shape, table, and group text from `PresentationData`
instead of scanning rendered DOM nodes. `PptxViewer.searchText()` is the viewer-level
convenience wrapper around the same search model.

String queries default to case-insensitive matching and can opt into exact casing with
`matchCase: true`. RegExp queries keep caller-provided flags; the search layer only adds
`g` so all matches can be collected.

Search results return `TextSearchResult` metadata such as `slideIndex`, `nodeId`,
`nodePath`, match offsets, snippet text, and node `bounds`. The bounds are intrinsic
slide coordinates for the matched shape or table cell owner. This keeps the public API
stable even when a slide is not currently mounted.

`highlightSearchResult()` is a DOM helper for the common viewer UI case. It draws a
node-level overlay using default highlight styling, and accepts `SearchHighlightOptions`
for custom class names, border colors, background colors, shadows, padding, radius, and
z-index. The returned `SearchHighlightHandle` is owned by the caller; call
`dispose()` or `clearSearchHighlights()` to remove overlays.

The renderer intentionally does not provide character-level text highlighting today.
Mapping match offsets back to shaped Office text runs, wrapped lines, bullets, and
vertical text is a separate renderer problem. The current boundary is model-level search
plus node-level highlight overlays.

`renderThumbnailToContainer()` renders a slide at intrinsic size and scales the result
with CSS transforms inside a clipped wrapper. It is a scaled DOM/SVG preview for
navigation surfaces, not a separate bitmap generation pipeline. The caller owns the
returned `SlideHandle` and must dispose it when the preview is no longer needed.

## Design Constraints

- Keep parser/model deterministic for reproducible QA runs.
- Keep rendering resilient: per-node/per-slide failures should not crash the whole deck.
- Keep security boundaries explicit at parse and navigation boundaries.
- Keep optional heavy dependencies such as `pdfjs-dist` outside the core render path unless
  the consumer explicitly configures them.

## Non-Goals (Current)

- Full fidelity parity with Microsoft PowerPoint for every OOXML edge case.
- Server-side rendering runtime in this repository.
- Full EMF/WMF vector instruction rendering. EMF support is limited to fallback previews.
