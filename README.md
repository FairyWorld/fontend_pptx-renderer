# pptx-renderer

[![CI](https://github.com/aiden0z/pptx-renderer/actions/workflows/ci.yml/badge.svg)](https://github.com/aiden0z/pptx-renderer/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/aiden0z/pptx-renderer/graph/badge.svg)](https://codecov.io/gh/aiden0z/pptx-renderer) [![npm](https://img.shields.io/npm/v/@aiden0z/pptx-renderer)](https://www.npmjs.com/package/@aiden0z/pptx-renderer) [![License](https://img.shields.io/github/license/aiden0z/pptx-renderer)](https://github.com/aiden0z/pptx-renderer/blob/main/LICENSE) [![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/) [![Node](https://img.shields.io/badge/Node.js-≥20-339933?logo=node.js&logoColor=white)](https://nodejs.org/) [![Demo](https://img.shields.io/badge/Demo-GitHub%20Pages-brightgreen)](https://aiden0z.github.io/pptx-renderer/)

A high-fidelity, browser-native PPTX renderer that parses Office Open XML (`.pptx`) files and renders slides as HTML/SVG DOM.

Supports shapes, text, images, tables, charts, SmartArt fallback data, groups, backgrounds, gradients, pattern fills, bounded static DrawingML 3D, and OOXML color inheritance. Rendering fidelity depends on the source features and available preview data; see the support boundaries below.

## Rendering Example

A complex slide with charts, text styles, shapes, and SmartArt — PowerPoint ground truth vs browser-rendered output:

<table>
<tr>
<th>PowerPoint (Ground Truth)</th>
<th>pptx-renderer (Browser)</th>
</tr>
<tr>
<td><img src="docs/example/1-chart-and-complex/slides/Slide1.png" alt="PowerPoint ground truth" width="480" /></td>
<td><img src="docs/example/1-chart-and-complex/rendered-result.png" alt="pptx-renderer output" width="480" /></td>
</tr>
</table>

## Visual Regression Testing

Visual regression suites compare selected shape, SmartArt, fill/stroke, text, table, and chart cases against PowerPoint output. Each API evaluation records the renderer revision, browser, optional font profile, and SHA-256 fingerprints of its PPTX and ground truth so results can be compared against the same inputs. A passing aggregate score does not establish semantic correctness or full PowerPoint parity; structural assertions and targeted browser/native inspection complement the metrics.

<img src="docs/example/e2e-test-page.png" alt="E2E evaluation dashboard" width="800" />

<sup>E2E evaluation dashboard: side-by-side ground truth vs rendered output with SSIM, color histogram, and IoU metrics per slide.</sup>

> Ground truth binaries (PPTX/PDF/PNG) stay in the ignored `test/e2e/testdata/` tree. Tracked case definitions and coverage metadata keep that local corpus reproducible. Generate shape/SmartArt corpora with `scripts/one_shot_full_ground_truth.py` or focused text/chart/composite cases with `scripts/generate_pypptx_cases.py`; both macOS and Windows PowerPoint are supported. See [`docs/TESTING.md`](docs/TESTING.md).

On macOS, native exports use one fixed ignored `oracle-runtime` directory and target the requested
presentation by its exact full path. Keep the interactive PowerPoint session available and inspect
pending dialogs when automation fails. This lets local oracle runs coexist with other open
presentations without treating the active window as the export target.

### Evidence-Driven Capability Loop

Renderer support is tracked by bounded OOXML capability rather than by a single aggregate score.
The tracked registry at `test/e2e/oracle/capabilities.json` declares each feature's exact scope,
current render mode, fallback, relevant implementation files, and mandatory gates. Promotion
receipts in `test/e2e/oracle/capability-acceptance.json` bind an accepted scope to its implementation,
PPTX inputs, PowerPoint ground truth, environment, and revision hashes.

```bash
pnpm capability:check      # validate tracked contracts and relevant file paths
pnpm capability:inventory  # scan the local ignored corpus into an ignored evidence report
python3 test/e2e/scripts/run_capability_loop.py verify --help
```

Inventory, ledger, ranking, work-packet, and verification reports stay under the ignored
`test/e2e/reports/capability-loop/` directory. `native` describes the intended render behavior;
the public `supported` claim additionally requires a fresh `verified` receipt. A report from a
dirty tree, a changed capability scope, changed implementation files, changed input/ground-truth
hashes, skipped cases, or an unresolved manual review cannot promote a capability.
The `verify` command converts raw `/api/evaluate` results into the promotion schema and derives
native-PowerPoint, manual-review, and regression gates from those results. Other `--passed-gate`
values record checks already run by the caller; the command does not execute or infer them.

## Install

```bash
npm install @aiden0z/pptx-renderer
# or
pnpm add @aiden0z/pptx-renderer

# Optional: only needed for SmartArt / EMF files with embedded PDF fallback previews
pnpm add pdfjs-dist
```

Requires Node.js 20+ for development. Runtime is browser-only.

## Quick Start

For bundlers and npm-based apps:

```ts
import { PptxViewer, RECOMMENDED_ZIP_LIMITS } from '@aiden0z/pptx-renderer';

const container = document.getElementById('pptx-container')!;
const resp = await fetch('/slides/demo.pptx');

// One-liner: parse, build model, and render
const viewer = await PptxViewer.open(await resp.arrayBuffer(), container, {
  zipLimits: RECOMMENDED_ZIP_LIMITS,
  listOptions: { windowed: true },
});
```

For direct browser usage without a bundler, import the standalone browser ESM build. This
entry bundles JSZip and ECharts, and replaces Node-style `process.env` checks at build time.
PDF.js remains optional and is only needed for EMF-embedded PDF fallback previews:

```html
<script type="module">
  import {
    PptxViewer,
    RECOMMENDED_ZIP_LIMITS,
  } from '/vendor/pptx-renderer/aiden0z-pptx-renderer.browser.es.js';

  const container = document.getElementById('pptx-container');
  const resp = await fetch('/slides/demo.pptx');
  await PptxViewer.open(await resp.arrayBuffer(), container, {
    zipLimits: RECOMMENDED_ZIP_LIMITS,
  });
</script>
```

Copy the standalone artifact from the published package into your application's versioned
static assets. The entry bundles JSZip and the ECharts chart types supported by this
renderer; PDF.js remains an optional external asset. A pinned CDN URL can also be used,
but the project does not depend on or deploy through a CDN provider.

For large decks, combine windowed mounting with on-demand slide parsing and media decoding:

```ts
const viewer = await PptxViewer.open(buffer, container, {
  zipLimits: RECOMMENDED_ZIP_LIMITS,
  lazySlides: true,
  lazyMedia: true,
  listOptions: { windowed: true, initialSlides: 4, batchSize: 4 },
});
```

### Optional PDF.js Fallback for SmartArt/EMF Preview Images

PowerPoint often stores SmartArt or pasted vector artwork as EMF fallback images. This
library does **not** implement a full EMF/WMF vector renderer. It can render the common
Office fallback cases where an EMF contains an embedded PDF preview or bitmap preview.

For EMF files with embedded PDF previews, install `pdfjs-dist` and pass explicit asset
URLs. This keeps PDF.js optional and avoids forcing every consumer bundle to include it.
This is only needed for EMF-PDF fallback previews; ordinary PPTX rendering does not
require any code changes.

```ts
import { PptxViewer } from '@aiden0z/pptx-renderer';

const pdfjs = {
  moduleUrl: new URL('pdfjs-dist/build/pdf.min.mjs', import.meta.url).toString(),
  workerUrl: new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString(),
};

const viewer = await PptxViewer.open(buffer, container, {
  pdfjs,
});
```

If your app uses a CDN or pre-copied assets, point those fields at your hosted files.
Set `pdfjs: false` to disable EMF-PDF fallback rendering entirely. With no `pdfjs`
configuration, the renderer attempts only a best-effort automatic resolution and
otherwise degrades gracefully.

```ts
type PdfjsConfig =
  | {
      moduleUrl?: string;
      workerUrl?: string;
    }
  | false;
```

For a no-bundler deployment, copy the two PDF.js files into your application's static
assets and pass absolute self-hosted URLs:

```ts
const pdfjs = {
  moduleUrl: '/vendor/pdfjs/pdf.min.mjs',
  workerUrl: '/vendor/pdfjs/pdf.worker.min.mjs',
};
```

The PDF fallback uses short-lived blob Workers. A restrictive Content Security Policy
must allow the chosen asset origin and `blob:` Workers, for example:

```text
script-src 'self';
worker-src 'self' blob:;
img-src 'self' data: blob:;
```

If a CDN is used instead, pin exact package versions and add only that origin to the
relevant CSP directives.

Or with more control over each step:

```ts
import {
  PptxViewer,
  parseZip,
  buildPresentation,
  RECOMMENDED_ZIP_LIMITS,
} from '@aiden0z/pptx-renderer';

const container = document.getElementById('pptx-container')!;
const viewer = new PptxViewer(container, { fitMode: 'contain' });

const files = await parseZip(arrayBuffer, RECOMMENDED_ZIP_LIMITS);
const presentation = buildPresentation(files);
viewer.load(presentation);
await viewer.renderList({ windowed: true, batchSize: 8 });
```

To delay both media decompression and slide node parsing until rendered slides actually need
them, use `parseZipLazyMedia()` and pass `{ lazySlides: true }` to `buildPresentation()`:

```ts
import {
  PptxViewer,
  parseZipLazyMedia,
  buildPresentation,
  RECOMMENDED_ZIP_LIMITS,
} from '@aiden0z/pptx-renderer';

const files = await parseZipLazyMedia(arrayBuffer, RECOMMENDED_ZIP_LIMITS);
const presentation = buildPresentation(files, { lazySlides: true });

const viewer = new PptxViewer(container);
viewer.load(presentation);
await viewer.renderList({ windowed: true, initialSlides: 4 });
```

## API

### `PptxViewer` (primary, extends `EventTarget`)

#### `PptxViewer.open(input, container, options?)` — Static Factory

Parse, build, and render in one call. Returns a `Promise<PptxViewer>`.

```ts
const viewer = await PptxViewer.open(buffer, container, {
  renderMode: 'list', // 'list' (default) | 'slide'
  zipLimits: RECOMMENDED_ZIP_LIMITS,
  listOptions: { windowed: true, batchSize: 8 },
  signal: abortController.signal, // optional AbortSignal
  // ...ViewerOptions
});
```

#### `new PptxViewer(container, options?)`

| Option               | Type                        | Default       | Description                                                                                                       |
| -------------------- | --------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------- |
| `width`              | `number`                    | --            | Container width hint (omit for auto-detect)                                                                       |
| `fitMode`            | `'contain' \| 'none'`       | `'contain'`   | Responsive fit or fixed size                                                                                      |
| `zoomPercent`        | `number`                    | `100`         | Zoom level (10–400)                                                                                               |
| `scrollContainer`    | `HTMLElement`               | --            | Scroll container for IntersectionObserver root                                                                    |
| `zipLimits`          | `ZipParseLimits`            | --            | Security limits for ZIP parsing (used by `.open()`). Use `RECOMMENDED_ZIP_LIMITS` for untrusted input.            |
| `lazyMedia`          | `boolean`                   | `false`       | Decode embedded media on demand instead of during ZIP parsing. Best for large decks with windowed list rendering. |
| `lazySlides`         | `boolean`                   | `false`       | Parse slide shape/table/chart nodes on demand. Best for large decks with windowed list rendering.                 |
| `pdfjs`              | `PdfjsConfig`               | --            | Optional PDF.js URLs for EMF-embedded PDF fallback rendering, or `false` to disable it.                           |
| `embeddedFontLimits` | `EmbeddedFontLimits`        | safe defaults | Optional embedded-font resource limit overrides. Omitted fields retain the built-in defaults.                     |
| `fontFaces`          | `readonly FontFaceConfig[]` | --            | Host-provided font faces for typefaces referenced by the PPTX but not embedded in it.                             |
| `onSlideChange`      | `(index) => void`           | --            | Shorthand for `slidechange` event                                                                                 |
| `onSlideRendered`    | `(index, element) => void`  | --            | Shorthand for `sliderendered` event                                                                               |
| `onSlideError`       | `(index, error) => void`    | --            | Shorthand for `slideerror` event                                                                                  |
| `onSlideUnmounted`   | `(index) => void`           | --            | Shorthand for `slideunmounted` event                                                                              |
| `onNodeError`        | `(nodeId, error) => void`   | --            | Shorthand for `nodeerror` event                                                                                   |
| `onRenderStart`      | `() => void`                | --            | Shorthand for `renderstart` event                                                                                 |
| `onRenderComplete`   | `() => void`                | --            | Shorthand for `rendercomplete` event                                                                              |

All shorthand callbacks are also available as `EventTarget` events (e.g. `viewer.addEventListener('slidechange', ...)`).

Embedded font decompression is bounded by default. Trusted applications can provide partial
`embeddedFontLimits` overrides; see the [performance guide](docs/PERFORMANCE.md#embedded-font-limits)
for defaults, examples, and the soft processing-time boundary.

For decks that reference fonts unavailable in the browser, provide regular/bold faces before
layout through `fontFaces`. Sources follow the browser `FontFace` API and can be font bytes or a
CSS `url(...)` source (subject to the host page's CSP and CORS policy):

```ts
const [regular, bold] = await Promise.all([
  fetch('/fonts/brand-sans-regular.woff2').then((response) => response.arrayBuffer()),
  fetch('/fonts/brand-sans-bold.woff2').then((response) => response.arrayBuffer()),
]);

const viewer = new PptxViewer(container, {
  fontFaces: [
    { family: 'Brand Sans', source: regular, descriptors: { weight: '400' } },
    { family: 'Brand Sans', source: bold, descriptors: { weight: '700' } },
  ],
});
```

#### Instance Methods

```ts
viewer.load(presentation);                              // Load a PresentationData model (no render)
await viewer.renderList({ windowed: true });             // Render all slides in scrollable list
await viewer.renderSlide(0);                             // Render a single slide (no built-in nav UI)

// Load from binary input (parse → build → render). Cleans up previous state on re-open.
await viewer.open(buffer, { renderMode: 'list', signal: abortController.signal });

await viewer.goToSlide(index);                           // Jump to slide (0-based), returns Promise<void>
await viewer.goToSlide(index, { behavior: 'instant' }); // Custom ScrollIntoViewOptions (list mode)
await viewer.setZoom(150);                               // Runtime zoom (10–400)
await viewer.setFitMode('none');                         // Switch fit mode
const matches = viewer.searchText('GPU');                 // Search parsed model text
const hit = await viewer.highlightSearchResult(matches[0]); // Default node overlay highlight
hit?.dispose();
viewer.clearSearchHighlights();                          // Remove active search overlays

// Render a single slide into an external container (React/Vue integration, thumbnails).
// Returns a SlideHandle; caller owns it and must call handle.dispose() when done.
const handle = viewer.renderSlideToContainer(index, container, scale?);
handle.dispose();                                        // Clean up slide-specific resources

// Render a lightweight scaled slide preview into an external container.
// This preserves the original slide layout and uses transform scaling; it is
// not a bitmap thumbnail generator, so use lazy/windowed mounting for decks.
const thumb = viewer.renderThumbnailToContainer(index, sidebarItem, { width: 180 });
await thumb?.ready;
thumb?.dispose();

// Query which slides are currently mounted in the DOM
viewer.isSlideMounted(index);   // boolean
viewer.getMountedSlides();      // number[] (sorted)

// Typed event helpers (return `this` for chaining)
viewer.on('slidechange', (e) => console.log(e.detail.index));
viewer.off('slidechange', listener);

viewer.destroy();               // Cleanup blob URLs, observers, and DOM
viewer[Symbol.dispose]();       // TC39 Explicit Resource Management (calls destroy)
```

#### Text Search

`PptxViewer.searchText(query, options?)` searches the parsed `PresentationData` model,
not the rendered DOM. This keeps search available before or after a slide is mounted and
avoids mutating renderer-generated text runs.

String queries are case-insensitive by default. Pass `matchCase: true` when you need
exact casing. RegExp queries keep their own flags, so `/GPU/` remains case-sensitive
and `/GPU/i` remains case-insensitive.

```ts
import type { TextSearchResult } from '@aiden0z/pptx-renderer';

const matches: TextSearchResult[] = viewer.searchText('GPU', {
  matchCase: false,
  wholeWord: true,
  snippetRadius: 48,
});

const exactMatches = viewer.searchText('GPU', { matchCase: true });
const regexMatches = viewer.searchText(/GPU|CPU/i);

for (const match of matches) {
  await viewer.goToSlide(match.slideIndex, { behavior: 'smooth', block: 'center' });
  // Use match.bounds for node-level highlight overlays in your own UI.
}
```

Each `TextSearchResult` includes `slideIndex`, `nodeId`, `nodePath`, `nodeType`,
`textKind`, full `text`, `matchStart`, `matchEnd`, `snippet`, and `bounds`.
`bounds` is the matched shape or table bounds in intrinsic slide coordinates, so
application code can draw node-level highlight overlays on top of a rendered slide.

The renderer intentionally does not rewrite text nodes for character-level text highlighting.
Character-level text highlighting would require mapping match offsets back to shaped Office
text runs and line layout, which is a separate, higher-risk renderer feature. Today the
stable API boundary is model-level search plus node-level bounds.

For the common UI case, `highlightSearchResult(result, options?)` draws a node-level
overlay using a default highlight style. Pass `SearchHighlightOptions` for custom colors,
spacing, shadows, and class names:

```ts
const hit = await viewer.highlightSearchResult(matches[0], {
  className: 'my-search-hit',
  borderColor: '#22c55e',
  backgroundColor: 'rgba(34, 197, 94, 0.18)',
  borderRadius: 6,
  borderWidth: 2,
  boxShadow: '0 0 0 2px rgba(15, 23, 42, 0.35)',
  padding: 3,
});

// The caller owns returned highlight handles.
hit?.dispose();
viewer.clearSearchHighlights();
```

#### Scaled Slide Previews

`PptxViewer.renderThumbnailToContainer(index, container, options?)` renders a slide at
its intrinsic layout size and applies CSS transform scaling inside a clipped wrapper.
This avoids the layout drift that can happen if a PPTX slide is rendered directly into a
small thumbnail-sized container.

```ts
const thumb = viewer.renderThumbnailToContainer(slideIndex, thumbnailEl, { width: 96 });
await thumb?.ready;

// The caller owns externally rendered previews.
thumb?.dispose();
```

This is not a bitmap thumbnail generator: it still creates a scaled DOM/SVG slide
preview, so large decks should mount previews lazily with `IntersectionObserver` or a
windowed list and dispose handles when they scroll out of view.

#### `ListRenderOptions`

| Option             | Type      | Default | Description                        |
| ------------------ | --------- | ------- | ---------------------------------- |
| `windowed`         | `boolean` | `false` | Use IntersectionObserver windowing |
| `batchSize`        | `number`  | `12`    | Slides per render batch            |
| `initialSlides`    | `number`  | `4`     | Initial slides to mount (windowed) |
| `overscanViewport` | `number`  | `1.5`   | Viewport overscan multiplier       |

#### `ZipParseLimits` and Resource Safety

`parseZip(buffer)` defaults to no ZIP limits for backward compatibility. For files from users or other untrusted sources, pass `RECOMMENDED_ZIP_LIMITS` or stricter values:

| Limit                       | Recommended value | What it protects                            |
| --------------------------- | ----------------- | ------------------------------------------- |
| `maxEntries`                | `4000`            | Archives with excessive file counts         |
| `maxEntryUncompressedBytes` | `32 MiB`          | A single oversized XML/media entry          |
| `maxTotalUncompressedBytes` | `256 MiB`         | Total decompressed archive size             |
| `maxMediaBytes`             | `192 MiB`         | Total media payload size under `ppt/media/` |
| `maxConcurrency`            | `8`               | Parallel ZIP entry reads                    |

When ZIP metadata does not expose a reliable uncompressed size, the parser falls back to the actual decoded entry size before accepting the entry. This keeps `maxEntryUncompressedBytes`, `maxTotalUncompressedBytes`, and `maxMediaBytes` effective for XML/text entries and media entries alike.

Renderer-level guards also apply after ZIP parsing:

- Chart caches do not allocate from oversized `c:ptCount`; chart point indexes are capped at `10,000` per cache.
- EMF bitmap previews are rejected when decoded size exceeds `16,777,216` pixels, dimensions exceed `8192x8192`, or pixel payload is shorter than the declared bitmap.
- External audio/video relationships only render for safe `http`/`https` URLs with `TargetMode="External"` and are created with `preload="none"`.

#### Events (`PptxViewerEventMap`)

```ts
viewer.addEventListener('renderstart', () => {
  /* render cycle began */
});
viewer.addEventListener('rendercomplete', () => {
  /* render cycle finished (fires even on error) */
});
viewer.addEventListener('slidechange', (e) => console.log(e.detail.index));
viewer.addEventListener('sliderendered', (e) => console.log(e.detail.index, e.detail.element));
viewer.addEventListener('slideerror', (e) => console.error(e.detail.index, e.detail.error));
viewer.addEventListener('slideunmounted', (e) => console.log(e.detail.index));
viewer.addEventListener('nodeerror', (e) => console.warn(e.detail.nodeId, e.detail.error));
```

`slidechange` fires both on `goToSlide()` navigation and after each render cycle (initial render included). `renderstart`/`rendercomplete` bracket every render cycle (renderList, renderSlide, setZoom, setFitMode). When calls overlap, the newer render request supersedes older queued or batched work, so stale list batches stop before appending more DOM.

#### Instance Properties (read-only)

```ts
viewer.presentationData; // PresentationData | null — the parsed model, null before load()
viewer.slideCount; // number — total slides (0 if not loaded)
viewer.slideWidth; // number — intrinsic slide width in px
viewer.slideHeight; // number — intrinsic slide height in px
viewer.currentSlideIndex; // number — currently active slide (0-based)
viewer.isRendering; // boolean — true between renderstart and rendercomplete
viewer.zoomPercent; // number — current zoom level (e.g. 100, 200)
viewer.fitMode; // FitMode — current fit mode ('contain' | 'none')
```

### `PptxRenderer` (deprecated v1 compat)

`PptxRenderer` extends `PptxViewer` and provides the legacy `preview(input)` API with built-in nav buttons in slide mode. Migrate to `PptxViewer` for new code.

```ts
import { PptxRenderer } from '@aiden0z/pptx-renderer';

const renderer = new PptxRenderer(container, { mode: 'list', listMountStrategy: 'windowed' });
await renderer.preview(buffer); // deprecated — use PptxViewer.open() instead
```

`PptxRenderer` accepts the same optional `lazyMedia`, `lazySlides`, and `pdfjs`
configuration as `PptxViewer`, so legacy users can enable performance options or
EMF-PDF fallback rendering without changing APIs.

### Utility Exports

```ts
import {
  parseZip,
  parseZipLazyMedia,
  buildPresentation,
  materializeAllSlideNodes,
  serializePresentation,
  buildTextIndex,
  searchText,
  searchPresentation,
  RECOMMENDED_ZIP_LIMITS,
} from '@aiden0z/pptx-renderer';

const files = await parseZip(arrayBuffer, RECOMMENDED_ZIP_LIMITS); // PptxFiles
const lazyFiles = await parseZipLazyMedia(arrayBuffer, RECOMMENDED_ZIP_LIMITS); // media resolves on demand
const presentation = buildPresentation(files); // PresentationData
const lazyPresentation = buildPresentation(lazyFiles, { lazySlides: true }); // slide nodes parse on demand
materializeAllSlideNodes(lazyPresentation); // optional: force full model materialization
const json = serializePresentation(presentation); // SerializedPresentation (JSON-safe)
const index = buildTextIndex(presentation); // TextIndexEntry[]
const matches = searchText(index, '算力'); // TextSearchResult[]
const directMatches = searchPresentation(presentation, /GPU|CPU/i); // TextSearchResult[]
```

#### Headless Slide Rendering

For advanced use cases (server-side screenshot, custom rendering pipeline):

```ts
import { renderSlide } from '@aiden0z/pptx-renderer';
import type { SlideHandle } from '@aiden0z/pptx-renderer';

const handle = renderSlide(presentation, presentation.slides[0], {
  onNodeError: (nodeId, err) => console.warn(nodeId, err),
  mediaUrlCache: new Map(), // optional shared cache for blob URLs
  pdfjs, // optional, only for EMF-embedded PDF fallback rendering
  fontFaces, // optional host-provided FontFaceConfig[]
});
document.body.appendChild(handle.element);

// Await async media such as EMF-PDF fallback previews before screenshots/exports.
await handle.ready;

// Cancels pending PDF fallbacks and disposes charts + owned blob URLs.
handle.dispose();
```

#### Model Types

All model types are exported for consumers building custom tooling:

```ts
import type {
  PresentationData,
  BuildPresentationOptions,
  SlideData,
  SlideNode,
  ThemeData,
  BaseNodeData,
  ShapeNodeData,
  PicNodeData,
  TableNodeData,
  GroupNodeData,
  ChartNodeData,
  TextBody,
  TextParagraph,
  TextRun,
  Position,
  Size,
  NodeType,
  SerializedPresentation,
  SerializedSlide,
  SerializedNode,
  PptxFiles,
  ZipParseLimits,
  FitMode,
  PreviewInput,
  ViewerOptions,
  FontFaceConfig,
  ListRenderOptions,
  ThumbnailRenderOptions,
  SearchHighlightHandle,
  SearchHighlightOptions,
  PptxViewerEventMap,
  SlideHandle,
  PdfjsOptions,
  PdfjsConfig,
  TextBounds,
  TextIndexEntry,
  TextIndexOptions,
  TextSearchOptions,
  TextSearchResult,
} from '@aiden0z/pptx-renderer';
```

## Rendering Capabilities

### Shapes — Broad Preset Coverage + Custom Geometry

All commonly used OOXML `DrawingML` preset shapes, organized by category:

| Category          | Count | Highlights                                                     |
| ----------------- | ----: | -------------------------------------------------------------- |
| Basic & Geometric |    70 | Rectangles, ovals, polygons, stars, arcs, clouds, gears, etc.  |
| Flowchart         |    30 | All standard flowchart shapes                                  |
| Arrows            |    22 | Directional, bent, curved, striped, chevron                    |
| Stars & Banners   |    17 | N-point stars, explosions, ribbons, scrolls                    |
| Callouts          |    17 | Rectangular, rounded, oval, cloud, line callout variants       |
| Connectors        |    12 | Straight, bent, curved (2-5 segments)                          |
| Action Buttons    |     9 | Multi-path 3D with darken/lighten face modifiers               |
| Math & Brackets   |    12 | Plus, minus, multiply, division, brackets, braces              |
| **Multi-path 3D** |   33+ | Bevel, cube, can, ribbons — multi-layer SVG with 3D appearance |

Custom geometry (`<a:custGeom>`) supports numeric move, line, quadratic/cubic Bézier, arc,
and close commands, including multiple paths and inferred source extents. The pinned OOXML
compiler evaluates the complete preset-shape formula corpus into renderer-independent IR and SVG
paths. A generated production subset now renders 29 definitions: all 28 zero-adjustment flowchart
presets in shape IDs 61-88, plus `donut` with its OOXML `adj=25000` default and `0..50000` polar
handle bounds. The flowcharts comprise 20 single-path and eight ordered three-path definitions;
each flowchart is also covered by a three-slide native PowerPoint matrix spanning square explicit
paint, wide theme-reference paint, and tall rendering through a non-identity group. The donut
retains both outer and inner contours across square, wide, tall, grouped, and picture-clip rendering.
Other presets retain the handwritten implementation until their own layering, adjustment, and
oracle gates pass. Symbolic `gdLst` formulas in arbitrary `<a:custGeom>` content remain unsupported.

### Static DrawingML 3D — Bounded Top Bevel, Camera Plane, and Bottom Front Material

The renderer recognizes `a:scene3d` and `a:sp3d` on ordinary shapes and pictures and preserves the
parsed observations in serialized model output. A native-oracle-backed static subset renders an
orthographic circular top bevel and optional contour with silhouette-aware lighting:

- shape lane: opaque resolved solid-fill `donut`, `ellipse`, `rect`, and `roundRect`; ellipse
  coverage spans square explicit paint, wide theme-reference paint, and tall rendering through a
  non-identity group transform; donut coverage adds the `0..50000` adjustment bounds, the `25000`
  default, a representative `32000` hole, and grouped/aspect-ratio variants; omitted `bevelT@w`,
  `bevelT@h`, and `bevelT@prst` use the DrawingML defaults of 76200 EMU per dimension and `circle`
  for the native-verified rect/roundRect/ellipse rows;
- picture lane: rectangular, stretch-filled pictures with no `a:srcRect`, or nonnegative source
  crops whose remaining horizontal and vertical extents are both positive;
- `orthographicFront`, no camera rotation, `twoPt:t` or `threePt:t` lighting, with either no light
  rotation or the observed `twoPt:t` rotation `lat=0`, `lon=0`, `rev=120°`;
- zero or omitted extrusion and `z`, no scene backdrop or extrusion color, an absent/zero contour or
  a positive contour with a resolvable color, no bottom bevel or preset material, and no effect-list
  entry other than a coexisting outer shadow.

The renderer keeps the normal flat shape or picture whenever the complete tuple does not match.
For a supported tuple it first paints a synchronous four-gradient vector fallback, then rasterizes
the exact SVG silhouette into an alpha mask. An exact interior Euclidean distance field supplies
continuous perimeter normals; a circular cross-section and the bounded light rig produce the final
bevel texture. This makes rounded corners follow the source contour instead of inheriting rectangular
face edges. Shape textures retain the resolved material hue, while picture textures remain relative
black/white lighting so the source pixels stay visible. The supported implicit `twoPt:t` picture
response uses its native-validated edge direction and a lower material intensity than opaque solid
shapes; the bevel geometry remains shared. Solid highlights keep their common material mapping,
while dark-face attenuation is interpolated across the native square, wide, and tall matrices.
Square ellipse/donut rows use the native-fitted effective 330° light bearing; other verified
three-point rows retain 350°, with a smooth near-square transition for those curved presets. Wide
rect/ellipse rows keep the native-backed `0.415` dark-face response, while solid donuts additionally
interpolate a native-backed broad shadow floor and a compressed directional shadow lobe across the
tall, square, and wide matrices. This better matches PowerPoint's three-point material rim without
moving the key highlight. `roundRect` retains its independently measured response.
The native 6 pt square-rectangle row and the 10 pt tall-rectangle row also have bounded shadow
anchors. The bevel-local gate checks peak amplitude, aggregate energy, and non-cancelling per-pixel
local shadow excess, so an over-dark sector cannot be hidden by an under-dark sector elsewhere.
A six-slide matrix pairs each omitted/default encoding with an explicit equivalent, and the local
gate requires both PowerPoint and renderer raster pairs to remain byte-identical.

The asynchronous texture work is serialized per slide, capped at 262,144 pixels per texture, cached
with the render context, and tied to slide abort and blob-URL cleanup. If Canvas, decoding, scale, or
rendering is unavailable, the vector fallback remains visible. Text stays outside the SVG lighting
overlay, picture outlines remain centered on the source bounds, and group transforms retain the
existing coordinate mapping.

The separate camera-plane lane has three zero-depth rectangle modalities. Solid planes become SVG
quadrilaterals. No-fill text planes and stretch-filled pictures retain their live DOM content and
receive a CSS `matrix3d` homography, so text remains selectable and picture crop stays in the normal
image pipeline. The solid matrix contains
`orthographicFront` with absent rotation, `orthographicFront` with exactly `lat=20°`, `lon=30°`,
`rev=0°`, and `perspectiveRelaxedModerately` with `fov=120°` and exactly
`lat=18590633/60000°`, `lon=0°`, `rev=0°`. The live-text rows are
`perspectiveContrastingRightFacing` with `fov=85°` and exactly `lat=0°`,
`lon=19532225/60000°`, `rev=0°`, plus `perspectiveLeft` with `fov=120°`, absent explicit
rotation, and the preset's implicit `lat=0°`, `lon=20°`, `rev=0°`. The picture row uses
`perspectiveRight` with `fov=95°`, absent explicit rotation, and implicit `lat=0°`, `lon=-20°`,
`rev=0°`. All rows use an unrotated `threePt:t` light.

Nineteen native slides cover the original six explicit-`a:sp3d` solid controls, scene-only solid,
two live-text square/wide/tall matrices, and a four-slide picture matrix spanning absent,
horizontal, vertical, and asymmetric source crops. An absent `a:sp3d` is treated as implicit zero
depth only for those exact scene-only tuples. Solid shapes must have no visible text or stroke and use the
verified explicit `#2F75B5` or theme `#4F81BD` rows. Live-text shapes must use explicit `a:noFill`,
omit the line element and `p:style`, and declare local `bodyPr wrap="none"` with `a:spAutoFit`.
The contrasting-right row requires `anchor="ctr"`; the perspective-left row requires the anchor to
be absent so Office's top default applies. Vertical text and independent text bounds remain outside
this lane. Picture rows require rectangular `a:stretch` without `a:fillRect`, style references,
visible outlines, picture background fills, or direct blip effects; source crops must be finite,
nonnegative, and leave positive visible width and height. All three modalities exclude local
rotation/flip, backdrop, nonzero `z`, explicit effect lists, bevel, contour, extrusion color,
material, and extrusion. Solid oracle rows retain their generated theme `effectRef=2` style;
its resolved `outerShdw` is applied to the visible projected polygon with a filter region covering
the projected four-corner bounds. Blur and distance follow the plane's measured horizontal
projection scale; orthographic rows apply their native-calibrated `0.95` footprint factor. The
camera-local gate requires at least `0.70` of measurable native shadow energy. Live-text rows omit
the entire shape style.

The separate bottom-bevel front-material lane covers a native-verified edge-on case without
inventing depth. It requires a standalone, non-placeholder `rect` with an explicit opaque
`#4472C4` fill and no visible outline; `orthographicFront`; `threePt:t` with no light rotation or
exactly `lat=0`, `lon=0`, `rev=50°`; zero depth, contour, and `z`; a default-size 76200-EMU
`relaxedInset` or `circle` `bevelB`; and either `dkEdge` or an absent material. The three verified
aspect ratios are 2:1, 1:1, and 3.2:5.2. The renderer replaces only the flat SVG face with the
native uniform response (`#4676CB` for `dkEdge`, `#4B7BD0` for absent material) and keeps live text
outside that SVG group. Because PowerPoint shows no visible bottom rim in this view, the renderer
does not draw one. Group, placeholder, layout, and master parents remain diagnostic flat fallbacks.
A 5% alpha overlay remains on the ordinary transparent composition path: its exact native 3D versus
flat control differs by at most one 8-bit RGB level, which is insufficient evidence for an opaque
material replacement.

This plane projection uses small independent SVG math rather than a mesh engine: longitude,
latitude, and revolution rotations are followed by orthographic or perspective division. OOXML
provides the camera properties; preset viewport scale and material response are pinned to native
PowerPoint evidence. A dedicated gate compares normalized four-corner geometry, three material
color bands, gradient range, gradient direction, and source-required external shadow energy and
direction for solid planes. Schema v5 keeps raw foreground IoU and bounds for live-text diagnosis,
then gates on bidirectional foreground F1 and bounds after a resolution-normalized `0.25%` raster
tolerance, plus grayscale ink-density retention. It inverse-projects picture planes to a fixed
rectangle and gates their content with color similarity and tolerant edge F1, so a correct outer
quadrilateral cannot hide a wrong crop. The tolerance absorbs font and image rasterization
differences while preserving semantic failures against the same hashed native rasters.
For bottom-front rows it additionally requires mean RGB error across three interior bands to stay
at or below `1.0`, then restores the source flat `#4472C4` fill and requires that mutation to fail.
For every measurable shadow row, the report erases the candidate's exterior shadow and requires the
shadow metric to reject that mutation. Every picture row likewise injects a 12% left crop and
rescale after rectification and requires the content metric to reject it. A gate therefore proves
both that the current rendering passes and that its local assertions still detect the targeted
failure modes.

This support does not include camera values outside that exact plane matrix, nonzero extrusion,
arbitrary light rotation, other bevel presets, tiled pictures, negative or degenerate source crops,
gradient/pattern/group/image-filled shapes, other text-body/style combinations, or pixel-identical
PowerPoint material simulation.
Although the distance-field backend can follow arbitrary alpha silhouettes, the public support
claim remains limited to native-verified `donut`/`ellipse`/`rect`/`roundRect` shapes and rectangular
pictures. Star, freeform, rotation, and glow probes stay in an opt-in ignored discovery matrix until
their own geometry-aware native gates pass. The eleven-slide bottom-bevel matrix now backs only the
separately declared uniform-front-material capability above; all other bottom-bevel combinations
remain discovery evidence. The original ellipse and donut probes remain preflight
neighbors to their tracked multi-slide matrices.

### Text — 7-Level Style Inheritance

Full OOXML text cascade: master → layout → shape → paragraph → run. Supports theme fonts, numbered/symbol/picture bullets, multi-level indent, vertical text, superscript/subscript, hyperlinks, and per-shape text insets.

Local text color follows DrawingML precedence: an explicit run fill overrides paragraph
`defRPr`; paragraph `defRPr` overrides the shape `fontRef`; `fontRef` supplies the fallback only
when neither local level declares a fill. Native PowerPoint cases cover `srgbClr`, `schemeClr`, the
inverse fallback, and square, wide, and tall text boxes.

### Charts via ECharts

Powered by [ECharts](https://echarts.apache.org/). Supports Bar/Column (clustered, stacked, 100% stacked), Line/Area (standard, stacked, 100% stacked), Pie, multi-ring Doughnut, Radar, Scatter, Bubble, and Stock/Candlestick charts, with axis labels, legends, data labels, grid lines, chart color-style palettes, marker symbols, and custom number formats.

The renderer registers only the ECharts charts, components, features, and Canvas renderer
that it uses. Bundler consumers keep ECharts external; the standalone browser entry
contains this same tree-shakeable runtime.

OOXML 3D chart elements such as `bar3DChart`, `line3DChart`, `pie3DChart`, `area3DChart`, and `surface3DChart` are parsed as graceful 2D fallbacks where possible. Their perspective, depth walls, and surface meshes are not rendered as native 3D.

### Fill, Stroke & Color

- **Fills**: solid, linear/radial/rectangular gradient, 52+ pattern fills, image (stretch/tile)
- **Strokes**: 8 dash styles, 5 arrowhead types, compound lines, line joins
- **Colors**: OOXML pipeline — `schemeClr` → `colorMap` remap → theme lookup → modifiers (lumMod, lumOff, tint, shade, alpha, satMod, etc.). All 6 color spaces supported. Effective maps follow slide → layout → master overrides, including explicit identity mappings and master resets; chart-local maps remain isolated from the parent slide.

Supported chart combinations include combo charts and secondary axes. Sparse scatter/bubble caches preserve missing coordinates and explicit zeros, with gap/span/zero handling; literal data sources and explicit negative-bar inversion flags are honored. Negative percent-stacked normalization is not newly guaranteed by these checks.

### SmartArt, Tables, Images & More

- **SmartArt**: renders available PowerPoint diagram fallback data; individual layout fidelity varies. EMF-embedded PDF previews can be rendered with optional [pdfjs-dist](https://mozilla.github.io/pdf.js/) configuration.
- **Tables**: OOXML table styles, merged-cell inside/outer borders, conditional corner styles, explicit no-fill border clearing, and direct-cell overrides
- **Images**: raster/SVG previews with crop and geometry clipping; grayscale, duotone, luminance, and biLevel effects on clipped pictures. Embedded audio/video playback uses browser-supported codecs, with posters/placeholders when playback data is unavailable.
- **Groups**: coordinate remapping with recursive child rendering; diagram-specific compensation requires matching diagram layout provenance
- **Backgrounds**: slide → layout → master inheritance chain

### Compatible Content and Text Inheritance

`mc:AlternateContent` selects one compatible `Choice` (including the supported SVG picture extension), otherwise its `Fallback`, across ordinary slide/template/group content and OLE picture previews. Unknown extension namespaces do not become supported merely because they occur in a `Choice`. Eager and lazy rendering retain selected branch order.

Placeholder inheritance follows the matched layout placeholder into its master category, preserves explicit zero transforms/insets, and resolves omitted body properties and mutually exclusive autofit choices. Explicit no-autofit clipping and whitespace behavior are checked in real browser containers. These combinations do not establish native equivalence for every text/autofit variant.

Percentage line spacing and paragraph before/after spacing follow Office line-unit semantics;
ordinary text boxes trim spacing outside the first and last visible paragraphs. A 16-case CJK
native matrix covers wrapping, autofit, line/paragraph spacing, adjacent runs, parent-shape layout,
and square/wide/tall `spAutoFit` text-box growth, while font availability remains part of the
evaluation provenance.

For a square-wrapped standalone horizontal text box with top/default anchoring and no explicit
overflow override, `spAutoFit` can grow the shape at its authored font size. The verified growth
cohort includes multiple visible paragraphs and single-paragraph runs with an explicit font size
whose unwrapped width is materially larger than the original box. The wrapper and its shape SVG
grow together without reflowing absolutely positioned siblings. Explicit overflow axes remain
authoritative; other wrapping modes, center/bottom anchors, vertical text, inherited compact
labels, diagram text bounds, and non-text-box shapes retain their bounded measurement paths.

## Architecture

Three-layer pipeline: **Parse -> Model -> Render**

```
ArrayBuffer (.pptx)
  -> ZipParser (jszip extraction)
  -> XmlParser (DOMParser + SafeXmlNode null-safe wrapper)
  -> buildPresentation() (assembles slides/layouts/masters/themes with relationship chains)
  -> SlideRenderer (background -> master shapes -> layout shapes -> slide shapes -> DOM)
```

Key design decisions:

- **SafeXmlNode**: Null-safe XML traversal — returns empty nodes instead of null, enabling deep chaining without null checks.
- **Lazy slide parsing**: Optional `lazySlides` mode keeps per-slide nodes deferred until render, search, serialization, or explicit materialization.
- **Lazy group parsing**: Group children stored as raw XML, parsed during rendering to avoid deep recursion in model layer.
- **Error isolation**: Per-node try/catch. A failed shape renders as a dashed-red placeholder; the slide continues.
- **No external CSS**: All styles inline. The library outputs self-contained HTML fragments.
- **Blob URL lifecycle**: Created for images/media, tracked in `mediaUrlCache`, revoked on `destroy()`.

## Performance

The default behavior stays eager for compatibility: parse the package, build the full
model, and render according to the selected mode. For large or media-heavy decks, opt
into the lazy/windowed path so the first visible slides can render without materializing
every slide and every media entry up front.

Use this preset for interactive viewers:

```ts
const viewer = await PptxViewer.open(buffer, container, {
  zipLimits: RECOMMENDED_ZIP_LIMITS,
  lazySlides: true,
  lazyMedia: true,
  listOptions: {
    windowed: true,
    batchSize: 8,
    initialSlides: 4,
    overscanViewport: 1.5,
  },
});
```

Recommended choices:

| Scenario                              | Recommended options                                     | Main benefit                                 |
| ------------------------------------- | ------------------------------------------------------- | -------------------------------------------- |
| User-uploaded PPTX                    | `zipLimits: RECOMMENDED_ZIP_LIMITS`                     | Bounds ZIP parsing work and decoded payloads |
| Long scrollable viewer                | `listOptions.windowed: true`                            | Keeps off-screen slides out of the DOM       |
| Large decks with many slide elements  | `lazySlides: true` plus windowed list rendering         | Defers per-slide node parsing until needed   |
| Media-heavy decks                     | `lazyMedia: true` plus windowed list rendering          | Defers image/audio/video byte decoding       |
| Export, print, or full comparison job | Eager defaults, or explicitly materialize before export | Ensures all slides are ready in one pass     |

In local benchmarks, `lazySlides` reduced model build time by roughly 52-66% on medium
and large decks, and lowered first-window parse + build + render time by roughly 16-22%.
For media-heavy windowed viewers, `lazyMedia` reduced initially decompressed media bytes
by about 72-97%, depending on deck content. These options preserve rendering semantics;
they mainly move work from initial load to the moment a slide or media item is actually
needed.

Manual pipelines can use the same building blocks:

```ts
const files = await parseZipLazyMedia(buffer, RECOMMENDED_ZIP_LIMITS);
const presentation = buildPresentation(files, { lazySlides: true });

const viewer = new PptxViewer(container);
viewer.load(presentation);
await viewer.renderList({ windowed: true, initialSlides: 4 });
```

Details: [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md)

## Security

- Treat PPTX input as untrusted. Start with `RECOMMENDED_ZIP_LIMITS`, then tighten for your deployment.
- External hyperlinks are protocol-filtered (no `javascript:`, `data:`, etc.).
- Reporting: [`docs/SECURITY.md`](docs/SECURITY.md)

## Development

```bash
pnpm install
pnpm dev          # Vite dev server
pnpm test         # Unit tests (vitest)
pnpm test:coverage # Coverage report → coverage/
pnpm build        # Production build
pnpm test:package # Verify package entries, packlist boundaries, and notice links
pnpm test:browser # Real Chromium checks for standalone, charts, and PDF.js
pnpm dev:e2e      # Dev server + Python E2E API server
pnpm geometry:check # Verify pinned OOXML geometry compile/evaluate/emit output
pnpm lint         # ESLint
pnpm typecheck    # tsc --noEmit
pnpm knip         # Dead code / unused exports detection
```

Dev pages at `http://127.0.0.1:5173`:

| Page                            | Purpose                                   |
| ------------------------------- | ----------------------------------------- |
| `/test/pages/index.html`        | Upload preview with search and thumbnails |
| `/test/pages/render-slide.html` | Single slide at native resolution         |
| `/test/pages/e2e-compare.html`  | Side-by-side PDF vs HTML with SSIM scores |
| `/test/pages/export.html`       | Model JSON tree viewer                    |

## Documentation

| Doc                                       | Content                                                                |
| ----------------------------------------- | ---------------------------------------------------------------------- |
| [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Parse/model/render pipeline design                                     |
| [`PERFORMANCE.md`](docs/PERFORMANCE.md)   | Tuning options and presets                                             |
| [`TESTING.md`](docs/TESTING.md)           | Unit/E2E strategy, two-layer metric system, visual regression workflow |
| [`CONTRIBUTING.md`](docs/CONTRIBUTING.md) | PR checklist, code quality tools, and workflow                         |
| [`SECURITY.md`](docs/SECURITY.md)         | Vulnerability reporting                                                |

## What's Not Yet Supported

DrawingML shape/picture 3D outside the bounded circular top-bevel, zero-depth camera-plane, and
edge-on bottom-bevel front-material tuples above retains the flat 2D fallback. This includes other
perspective or rotated cameras, nonzero extrusion, other bottom or non-circular bevels, other preset
materials, unsupported lighting, tiled pictures,
and unsupported paint, text, stroke, transform, or effect combinations. True 3D chart
perspective/depth/surface meshes, Office 2017 embedded 3D
models, animations/transitions, equations (OMML), full EMF/WMF vector rendering, executing/editing
embedded OLE objects, and slide notes rendering are outside the verified native scope. Available OLE
picture previews can render; they are not an OLE object engine. EMF bitmap and embedded-PDF previews
remain supported (PDF previews require PDF.js); arbitrary EMF/WMF vector records remain excluded.
Exact current boundaries live in the capability registry described above.

## FAQ

**Does this run on Node.js?**
No. Rendering depends on browser DOM APIs.

**Why is my PPTX rendering incomplete?**
OOXML is a vast spec. Please open a compatibility issue with a minimal PPTX sample — the visual regression pipeline makes it straightforward to add coverage for new cases.

**How do I render 100+ slide decks efficiently?**
Use `windowed: true` in `listOptions`, and enable `lazySlides: true`. For media-heavy
decks, also enable `lazyMedia: true`.

## License

Apache License 2.0. See `LICENSE`.
