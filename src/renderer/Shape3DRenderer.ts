/**
 * Bounded DrawingML static 3D renderer.
 *
 * This module deliberately supports one small, native-oracle-backed tuple: orthographic-front
 * circle top bevels on solid ellipse/rect/roundRect shapes and rectangular pictures with bounded
 * source crops. Everything else returns an explicit flat plan so detection cannot be confused
 * with rendering support.
 */

import type { Shape3DProperties, Shape3DRotation } from '../model/nodes/Shape3D';
import type { RenderContext } from './RenderContext';
import { resolveColor } from './StyleResolver';
import { applyLumMod, applyLumOff, applySatMod, hexToRgb } from '../utils/color';
import { fitShape3DRasterScale, renderCircleBevelOverlay } from './shape3d/BevelLighting';

type StaticShape3DSurface = 'shape' | 'picture';
type StaticShape3DGeometry = 'ellipse' | 'rect' | 'roundrect';
type BevelFace = 'top' | 'right' | 'bottom' | 'left';

type StaticShape3DFallbackReason =
  | 'missing-properties'
  | 'parse-issue'
  | 'missing-scene'
  | 'missing-camera'
  | 'missing-light-rig'
  | 'missing-shape-format'
  | 'missing-top-bevel'
  | 'camera-preset'
  | 'camera-rotation'
  | 'light-rig'
  | 'light-direction'
  | 'light-rotation'
  | 'extrusion-height'
  | 'bottom-bevel'
  | 'top-bevel-preset'
  | 'top-bevel-dimensions'
  | 'preset-material'
  | 'effect-list-conflict'
  | 'invalid-bounds'
  | 'line-like'
  | 'geometry-preset'
  | 'paint-kind'
  | 'contour-paint'
  | 'picture-source-crop'
  | 'tiled-picture';

interface StaticShape3DSourceCrop {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

interface StaticShape3DTarget {
  nodeType: StaticShape3DSurface;
  presetGeometry?: string;
  width: number;
  height: number;
  isLineLike?: boolean;
  /** The shape lane is promoted only for a normal solid fill. */
  paintKind?: 'solid' | 'picture' | 'gradient' | 'pattern' | 'group' | 'none' | 'unknown';
  /** Resolved opaque solid paint used for the native-material face adjustment. */
  baseFill?: string;
  isTiledPicture?: boolean;
  /** Parsed a:srcRect fractions removed from each source-image edge. */
  sourceCrop?: StaticShape3DSourceCrop;
}

export interface StaticShape3DFlatPlan {
  mode: 'flat';
  reason: StaticShape3DFallbackReason;
  parseIssues?: readonly string[];
}

export interface StaticShape3DSupportedPlan {
  mode: 'orthographic-top-bevel';
  surface: StaticShape3DSurface;
  geometry: StaticShape3DGeometry;
  faceColor?: string;
  bounds: { width: number; height: number };
  bevel: {
    preset: 'circle';
    width: number;
    height: number;
  };
  contour?: {
    width: number;
    color: string;
    alpha: number;
  };
  light: {
    rig: 'twoPt' | 'threePt';
    direction: 't';
    rotation?: Shape3DRotation;
    azimuth: number;
    elevation: number;
    intensity: number;
  };
}

export type StaticShape3DPlan = StaticShape3DFlatPlan | StaticShape3DSupportedPlan;

interface AppendStaticShape3DEffectsOptions {
  svg: SVGSVGElement;
  defs: SVGDefsElement;
  pathD: string;
  bounds: { width: number; height: number };
  plan: StaticShape3DPlan;
  /** Without a render context, the synchronous vector fallback remains in place. */
  ctx?: RenderContext;
}

interface AppendedStaticShape3DEffects {
  group: SVGGElement;
  clipId: string;
}

const SUPPORTED_SHAPE_PRESETS = new Set(['ellipse', 'rect', 'roundrect']);
const SUPPORTED_PICTURE_PRESETS = new Set(['rect']);
const SHAPE3D_LIGHTING_VERSION = 'distance-field-v1';
const MAX_SHAPE3D_RASTER_PIXELS = 262_144;
const TARGET_SHAPE3D_RASTER_SCALE = 2;
const shape3dTaskTails = new WeakMap<Promise<void>[], Promise<void>>();
let shape3dIdCounter = 0;

function flat(
  reason: StaticShape3DFallbackReason,
  parseIssues?: readonly string[],
): StaticShape3DFlatPlan {
  return parseIssues?.length ? { mode: 'flat', reason, parseIssues } : { mode: 'flat', reason };
}

function isSupportedLightRotation(
  rig: string | undefined,
  direction: string | undefined,
  rotation: Shape3DRotation,
): boolean {
  return (
    rig === 'twoPt' &&
    direction === 't' &&
    rotation.latitude === 0 &&
    rotation.longitude === 0 &&
    rotation.revolution === 120
  );
}

function normalizedPreset(target: StaticShape3DTarget): string {
  if (!target.presetGeometry && target.nodeType === 'picture') return 'rect';
  return target.presetGeometry?.toLowerCase() ?? '';
}

function hasSupportedPictureSourceCrop(crop: StaticShape3DSourceCrop | undefined): boolean {
  if (!crop) return true;
  const values = [crop.top, crop.right, crop.bottom, crop.left];
  return (
    values.every((value) => Number.isFinite(value) && value >= 0 && value <= 1) &&
    crop.left + crop.right < 0.999 &&
    crop.top + crop.bottom < 0.999
  );
}

function resolveContour(
  properties: Shape3DProperties,
  ctx: RenderContext,
): StaticShape3DSupportedPlan['contour'] {
  const width = properties.shape?.contourWidth ?? 0;
  const source = properties.shape?.contourColorSource;
  if (!(width > 0) || !source?.exists()) return undefined;
  const { color, alpha } = resolveColor(source, ctx);
  if (!color || alpha <= 0) return undefined;
  return { width, color: color.startsWith('#') ? color : `#${color}`, alpha };
}

/** Build an explicit supported/fallback plan before mutating the SVG DOM. */
export function buildStaticShape3DPlan(
  properties: Shape3DProperties | undefined,
  target: StaticShape3DTarget,
  ctx: RenderContext,
): StaticShape3DPlan {
  if (!properties) return flat('missing-properties');
  if (properties.parseIssues.length > 0) {
    return flat('parse-issue', properties.parseIssues);
  }
  if (
    !Number.isFinite(target.width) ||
    !Number.isFinite(target.height) ||
    target.width <= 0 ||
    target.height <= 0
  ) {
    return flat('invalid-bounds');
  }
  if (target.isLineLike) return flat('line-like');
  if (target.isTiledPicture) return flat('tiled-picture');
  if (target.nodeType === 'picture' && !hasSupportedPictureSourceCrop(target.sourceCrop)) {
    return flat('picture-source-crop');
  }

  const scene = properties.scene;
  if (!scene) return flat('missing-scene');
  if (!scene.cameraPreset) return flat('missing-camera');
  if (scene.cameraPreset !== 'orthographicFront') return flat('camera-preset');
  if (scene.cameraRotation) return flat('camera-rotation');
  if (!scene.lightRig) return flat('missing-light-rig');
  if (scene.lightRig !== 'twoPt' && scene.lightRig !== 'threePt') return flat('light-rig');
  if (scene.lightDirection !== 't') return flat('light-direction');
  if (
    scene.lightRotation &&
    !isSupportedLightRotation(scene.lightRig, scene.lightDirection, scene.lightRotation)
  ) {
    return flat('light-rotation');
  }

  const shape = properties.shape;
  if (!shape) return flat('missing-shape-format');
  if (properties.effectKinds.some((effect) => effect !== 'outerShdw')) {
    return flat('effect-list-conflict');
  }
  if ((shape.extrusionHeight ?? 0) > 0) return flat('extrusion-height');
  if (shape.bevelBottom) return flat('bottom-bevel');
  if (!shape.bevelTop) return flat('missing-top-bevel');
  if (shape.bevelTop.preset !== 'circle') return flat('top-bevel-preset');
  if (
    !Number.isFinite(shape.bevelTop.width) ||
    !Number.isFinite(shape.bevelTop.height) ||
    !(shape.bevelTop.width! > 0) ||
    !(shape.bevelTop.height! > 0)
  ) {
    return flat('top-bevel-dimensions');
  }
  if (shape.presetMaterial !== undefined) return flat('preset-material');

  const preset = normalizedPreset(target);
  const supportedPresets =
    target.nodeType === 'shape' ? SUPPORTED_SHAPE_PRESETS : SUPPORTED_PICTURE_PRESETS;
  if (!supportedPresets.has(preset)) return flat('geometry-preset');
  if (target.nodeType === 'shape' && target.paintKind && target.paintKind !== 'solid') {
    return flat('paint-kind');
  }
  if (
    target.nodeType === 'shape' &&
    (!target.baseFill || !/^#[0-9a-f]{6}$/i.test(target.baseFill))
  ) {
    return flat('paint-kind');
  }

  const bevel = shape.bevelTop;

  const contour = resolveContour(properties, ctx);
  if ((properties.shape?.contourWidth ?? 0) > 0 && !contour) {
    return flat('contour-paint');
  }

  const width = Math.min(bevel.width!, target.width / 2);
  const height = Math.min(bevel.height!, target.height / 2);
  if (!(width > 0) || !(height > 0)) return flat('invalid-bounds');

  const rig = scene.lightRig;
  const rotation = scene.lightRotation;
  // Native evidence gives each bounded rig a distinct response. The implicit two-point picture
  // light is lower-left dominant and more elevated; three-point is top-dominant with a small
  // leftward component. Keep the separately observed 120-degree sentinel explicit instead of
  // broadening support to arbitrary rotations.
  const rotatedPictureSentinel = rig === 'twoPt' && rotation?.revolution === 120;
  const azimuth = rig === 'threePt' ? 350 : rotatedPictureSentinel ? 285 : 225;
  const elevation = rig === 'threePt' ? 50 : rotatedPictureSentinel ? 45 : 60;

  return {
    mode: 'orthographic-top-bevel',
    surface: target.nodeType,
    geometry: preset as StaticShape3DGeometry,
    faceColor:
      target.nodeType === 'shape' && target.baseFill
        ? applySatMod(applyLumOff(target.baseFill, 3500), 102000)
        : undefined,
    bounds: { width: target.width, height: target.height },
    bevel: { preset: 'circle', width, height },
    contour,
    light: {
      rig,
      direction: 't',
      rotation,
      azimuth,
      elevation,
      intensity: target.nodeType === 'picture' ? 0.8 : 1.75,
    },
  };
}

function appendStop(
  gradient: SVGLinearGradientElement,
  offset: string,
  color: string,
  opacity: number,
): void {
  const stop = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
  stop.setAttribute('offset', offset);
  stop.setAttribute('stop-color', color);
  stop.setAttribute('stop-opacity', String(opacity));
  gradient.appendChild(stop);
}

function appendBevelStop(
  gradient: SVGLinearGradientElement,
  plan: StaticShape3DSupportedPlan,
  offset: string,
  overlayColor: string,
  overlayOpacity: number,
): void {
  if (plan.surface !== 'shape' || !plan.faceColor) {
    appendStop(gradient, offset, overlayColor, overlayOpacity);
    return;
  }

  // Solid materials retain their hue under PowerPoint lighting. Resolve each stop to an opaque
  // material color; a translucent white overlay washes the specular band toward gray.
  const materialColor =
    overlayColor === '#FFFFFF'
      ? applySatMod(
          applyLumOff(plan.faceColor, Math.round(overlayOpacity * 40000)),
          Math.round(100000 + overlayOpacity * 130000),
        )
      : applyLumMod(plan.faceColor, Math.round((1 - overlayOpacity * 0.85) * 100000));
  appendStop(gradient, offset, materialColor, 1);
}

interface BevelFaceDefinition {
  face: BevelFace;
  gradient: { x1: number; y1: number; x2: number; y2: number };
  points: readonly [number, number][];
  stops: readonly [offset: string, color: string, opacity: number][];
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function buildBevelFaces(
  bounds: { width: number; height: number },
  inset: number,
): readonly BevelFaceDefinition[] {
  const { width, height } = bounds;
  return [
    {
      face: 'top',
      gradient: { x1: 0, y1: 0, x2: 0, y2: inset },
      points: [
        [0, 0],
        [width, 0],
        [width - inset, inset],
        [inset, inset],
      ],
      stops: [
        ['0%', '#000000', 0.28],
        ['18%', '#000000', 0.08],
        ['35%', '#FFFFFF', 0.28],
        ['58%', '#FFFFFF', 0.58],
        ['82%', '#FFFFFF', 0.18],
        ['100%', '#FFFFFF', 0],
      ],
    },
    {
      face: 'right',
      gradient: { x1: width, y1: 0, x2: width - inset, y2: 0 },
      points: [
        [width, 0],
        [width, height],
        [width - inset, height - inset],
        [width - inset, inset],
      ],
      stops: [
        ['0%', '#000000', 0.9],
        ['55%', '#000000', 0.62],
        ['100%', '#000000', 0],
      ],
    },
    {
      face: 'bottom',
      gradient: { x1: 0, y1: height, x2: 0, y2: height - inset },
      points: [
        [width, height],
        [0, height],
        [inset, height - inset],
        [width - inset, height - inset],
      ],
      stops: [
        ['0%', '#000000', 0.8],
        ['52%', '#000000', 0.55],
        ['100%', '#000000', 0],
      ],
    },
    {
      face: 'left',
      gradient: { x1: 0, y1: 0, x2: inset, y2: 0 },
      points: [
        [0, height],
        [0, 0],
        [inset, inset],
        [inset, height - inset],
      ],
      stops: [
        ['0%', '#000000', 0.48],
        ['45%', '#000000', 0.16],
        ['65%', '#FFFFFF', 0.1],
        ['100%', '#FFFFFF', 0],
      ],
    },
  ];
}

function shape3DLightingCacheKey(
  pathD: string,
  plan: StaticShape3DSupportedPlan,
  rasterWidth: number,
  rasterHeight: number,
): string {
  return [
    `shape3d-lighting:${SHAPE3D_LIGHTING_VERSION}`,
    plan.surface,
    plan.geometry,
    `${plan.bounds.width}x${plan.bounds.height}`,
    `${rasterWidth}x${rasterHeight}`,
    `${plan.bevel.width}:${plan.bevel.height}`,
    `${plan.light.rig}:${plan.light.azimuth}:${plan.light.elevation}:${plan.light.intensity}`,
    pathD,
  ].join('|');
}

function canvasToPngBlob(canvas: HTMLCanvasElement): Promise<Blob | undefined> {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob ?? undefined), 'image/png');
  });
}

async function waitForImageDecode(url: string, signal: AbortSignal | undefined): Promise<boolean> {
  if (signal?.aborted) return false;
  const image = document.createElement('img');

  let removeAbortListener: () => void = () => {};
  const abort = new Promise<boolean>((resolve) => {
    if (!signal) return;
    const onAbort = () => resolve(false);
    signal.addEventListener('abort', onAbort, { once: true });
    removeAbortListener = () => signal.removeEventListener('abort', onAbort);
  });

  const decoded = new Promise<boolean>((resolve) => {
    if (typeof image.decode === 'function') {
      image.src = url;
      void image.decode().then(
        () => resolve(true),
        () => resolve(false),
      );
    } else {
      image.onload = () => resolve(true);
      image.onerror = () => resolve(false);
      image.src = url;
    }
  });

  try {
    return signal ? await Promise.race([decoded, abort]) : await decoded;
  } finally {
    removeAbortListener();
  }
}

function appendLightingImage(
  group: SVGGElement,
  url: string,
  bounds: { width: number; height: number },
): void {
  const image = document.createElementNS('http://www.w3.org/2000/svg', 'image');
  image.dataset.pptxShape3dLighting = 'distance-field';
  image.setAttribute('x', '0');
  image.setAttribute('y', '0');
  image.setAttribute('width', String(bounds.width));
  image.setAttribute('height', String(bounds.height));
  image.setAttribute('preserveAspectRatio', 'none');
  image.setAttribute('href', url);
  for (const face of group.querySelectorAll('[data-pptx-shape3d-face]')) face.remove();
  group.appendChild(image);
}

function applySolidMaterialLighting(
  lighting: Uint8ClampedArray,
  faceColor: string,
): Uint8ClampedArray {
  const positive = new Uint8Array(256 * 3);
  const negative = new Uint8Array(256 * 3);
  for (let alpha = 1; alpha <= 255; alpha += 1) {
    const strength = alpha / 255;
    const lightColor = hexToRgb(
      applySatMod(
        applyLumOff(faceColor, Math.round(strength * 40000)),
        Math.round(100000 + strength * 130000),
      ),
    );
    const shadowColor = hexToRgb(
      applyLumMod(faceColor, Math.round((1 - strength * 0.85) * 100000)),
    );
    for (const [table, color] of [
      [positive, lightColor],
      [negative, shadowColor],
    ] as const) {
      const offset = alpha * 3;
      table[offset] = color.r;
      table[offset + 1] = color.g;
      table[offset + 2] = color.b;
    }
  }

  const material = new Uint8ClampedArray(lighting.length);
  for (let offset = 0; offset < lighting.length; offset += 4) {
    const strength = lighting[offset + 3];
    if (strength === 0) continue;
    const table = lighting[offset] >= 128 ? positive : negative;
    const colorOffset = strength * 3;
    material[offset] = table[colorOffset];
    material[offset + 1] = table[colorOffset + 1];
    material[offset + 2] = table[colorOffset + 2];
    material[offset + 3] = 255;
  }
  return material;
}

async function renderDistanceFieldLighting(
  group: SVGGElement,
  pathD: string,
  plan: StaticShape3DSupportedPlan,
  ctx: RenderContext,
): Promise<void> {
  if (ctx.signal?.aborted || typeof Path2D !== 'function') return;

  const scale = fitShape3DRasterScale(
    plan.bounds.width,
    plan.bounds.height,
    TARGET_SHAPE3D_RASTER_SCALE,
    MAX_SHAPE3D_RASTER_PIXELS,
  );
  if (scale < 0.25) return;
  const rasterWidth = Math.max(1, Math.ceil(plan.bounds.width * scale));
  const rasterHeight = Math.max(1, Math.ceil(plan.bounds.height * scale));
  const cacheKey = shape3DLightingCacheKey(pathD, plan, rasterWidth, rasterHeight);
  const cachedUrl = ctx.mediaUrlCache.get(cacheKey);
  if (cachedUrl) {
    if ((await waitForImageDecode(cachedUrl, ctx.signal)) && !ctx.signal?.aborted) {
      appendLightingImage(group, cachedUrl, plan.bounds);
    }
    return;
  }

  const maskCanvas = document.createElement('canvas');
  maskCanvas.width = rasterWidth;
  maskCanvas.height = rasterHeight;
  const maskContext = maskCanvas.getContext('2d', { willReadFrequently: true });
  if (!maskContext) return;
  maskContext.setTransform(
    rasterWidth / plan.bounds.width,
    0,
    0,
    rasterHeight / plan.bounds.height,
    0,
    0,
  );
  maskContext.fillStyle = '#000000';
  maskContext.fill(new Path2D(pathD), 'evenodd');

  const rgba = maskContext.getImageData(0, 0, rasterWidth, rasterHeight).data;
  const alpha = new Uint8Array(rasterWidth * rasterHeight);
  for (let pixel = 0, offset = 3; pixel < alpha.length; pixel += 1, offset += 4) {
    alpha[pixel] = rgba[offset];
  }
  const effectiveScale = Math.sqrt(
    (rasterWidth / plan.bounds.width) * (rasterHeight / plan.bounds.height),
  );
  let lighting = renderCircleBevelOverlay(alpha, rasterWidth, rasterHeight, {
    bandPx: plan.bevel.width * effectiveScale,
    heightPx: plan.bevel.height * effectiveScale,
    lightAzimuthDeg: plan.light.azimuth,
    lightElevationDeg: plan.light.elevation,
    intensity: plan.light.intensity,
  });
  if (plan.surface === 'shape' && plan.faceColor) {
    lighting = applySolidMaterialLighting(lighting, plan.faceColor);
  }

  const outputCanvas = document.createElement('canvas');
  outputCanvas.width = rasterWidth;
  outputCanvas.height = rasterHeight;
  const outputContext = outputCanvas.getContext('2d');
  if (!outputContext) return;
  const imageData = outputContext.createImageData(rasterWidth, rasterHeight);
  imageData.data.set(lighting);
  outputContext.putImageData(imageData, 0, 0);
  const blob = await canvasToPngBlob(outputCanvas);
  if (!blob || ctx.signal?.aborted) return;

  const existingUrl = ctx.mediaUrlCache.get(cacheKey);
  const url = existingUrl ?? URL.createObjectURL(blob);
  const ownsUrl = !existingUrl;
  if (ownsUrl) ctx.mediaUrlCache.set(cacheKey, url);
  const decoded = await waitForImageDecode(url, ctx.signal);
  if (!decoded) {
    if (ownsUrl && ctx.mediaUrlCache.get(cacheKey) === url && !ctx.signal?.aborted) {
      ctx.mediaUrlCache.delete(cacheKey);
      URL.revokeObjectURL(url);
    }
    return;
  }
  if (!ctx.signal?.aborted) appendLightingImage(group, url, plan.bounds);
}

function scheduleDistanceFieldLighting(
  group: SVGGElement,
  pathD: string,
  plan: StaticShape3DSupportedPlan,
  ctx: RenderContext,
): void {
  const run = () => renderDistanceFieldLighting(group, pathD, plan, ctx).catch(() => undefined);
  const tasks = ctx.asyncTasks;
  if (!tasks) {
    void run();
    return;
  }

  const previous = shape3dTaskTails.get(tasks);
  const task = previous ? previous.then(run, run) : run();
  shape3dTaskTails.set(tasks, task);
  tasks.push(task);
}

/** Append the scoped bevel overlay without filtering sibling text or mutating the base path. */
export function appendStaticShape3DEffects(
  options: AppendStaticShape3DEffectsOptions,
): AppendedStaticShape3DEffects | undefined {
  const { svg, defs, pathD, bounds, plan, ctx } = options;
  if (plan.mode !== 'orthographic-top-bevel' || !pathD) return undefined;
  if (
    !Number.isFinite(bounds.width) ||
    !Number.isFinite(bounds.height) ||
    bounds.width <= 0 ||
    bounds.height <= 0
  ) {
    return undefined;
  }

  const ns = 'http://www.w3.org/2000/svg';
  const id = ++shape3dIdCounter;
  const clipId = `shape3d-clip-${id}`;

  const clipPath = document.createElementNS(ns, 'clipPath');
  clipPath.id = clipId;
  clipPath.setAttribute('clipPathUnits', 'userSpaceOnUse');
  const clipShape = document.createElementNS(ns, 'path');
  clipShape.setAttribute('d', pathD);
  clipPath.appendChild(clipShape);
  defs.appendChild(clipPath);

  const group = document.createElementNS(ns, 'g');
  group.dataset.pptxShape3dBevel = 'orthographic-top-bevel';
  group.setAttribute('clip-path', `url(#${clipId})`);
  group.setAttribute('pointer-events', 'none');

  if (plan.surface === 'shape' && plan.faceColor) {
    const faceSheen = document.createElementNS(ns, 'path');
    faceSheen.setAttribute('d', pathD);
    faceSheen.setAttribute('fill', plan.faceColor);
    faceSheen.setAttribute('stroke', 'none');
    faceSheen.dataset.pptxShape3dSurface = 'sheen';
    group.appendChild(faceSheen);
  }

  // bevelT@w is the in-plane inset. bevelT@h is elevation, so it scales contrast without
  // making the visible ring wider. Four clipped strokes preserve the directional face normals
  // that are lost when the bevel is represented by one filtered border.
  const inset = Math.min(plan.bevel.width, bounds.width / 2, bounds.height / 2);
  const heightStrength = clamp(Math.sqrt(plan.bevel.height / inset), 0.65, 1.25);
  const surfaceStrength = plan.surface === 'picture' ? 0.9 : 1;
  const rigStrength = plan.light.rig === 'threePt' ? 1 : 0.9;
  const opacityScale = heightStrength * surfaceStrength * rigStrength;

  for (const definition of buildBevelFaces(bounds, inset)) {
    const faceId = `${id}-${definition.face}`;
    const gradientId = `shape3d-gradient-${faceId}`;
    const faceClipId = `shape3d-face-clip-${faceId}`;

    const gradient = document.createElementNS(ns, 'linearGradient');
    gradient.id = gradientId;
    gradient.dataset.pptxShape3dFaceGradient = definition.face;
    gradient.setAttribute('gradientUnits', 'userSpaceOnUse');
    gradient.setAttribute('color-interpolation', 'linearRGB');
    for (const [name, value] of Object.entries(definition.gradient)) {
      gradient.setAttribute(name, String(value));
    }
    for (const [offset, color, opacity] of definition.stops) {
      appendBevelStop(gradient, plan, offset, color, clamp(opacity * opacityScale, 0, 1));
    }
    defs.appendChild(gradient);

    const faceClip = document.createElementNS(ns, 'clipPath');
    faceClip.id = faceClipId;
    faceClip.setAttribute('clipPathUnits', 'userSpaceOnUse');
    const polygon = document.createElementNS(ns, 'polygon');
    polygon.setAttribute('points', definition.points.map(([x, y]) => `${x},${y}`).join(' '));
    faceClip.appendChild(polygon);
    defs.appendChild(faceClip);

    const facePath = document.createElementNS(ns, 'path');
    facePath.dataset.pptxShape3dFace = definition.face;
    facePath.setAttribute('d', pathD);
    facePath.setAttribute('fill', 'none');
    facePath.setAttribute('stroke', `url(#${gradientId})`);
    facePath.setAttribute('stroke-width', String(inset * 2));
    facePath.setAttribute('stroke-linejoin', plan.geometry === 'roundrect' ? 'round' : 'miter');
    facePath.setAttribute('clip-path', `url(#${faceClipId})`);
    group.appendChild(facePath);
  }
  svg.appendChild(group);

  if (plan.contour) {
    const contour = document.createElementNS(ns, 'path');
    contour.dataset.pptxShape3dContour = 'true';
    contour.setAttribute('d', pathD);
    contour.setAttribute('fill', 'none');
    contour.setAttribute('stroke', plan.contour.color);
    contour.setAttribute('stroke-opacity', String(plan.contour.alpha));
    contour.setAttribute('stroke-width', String(plan.contour.width));
    contour.setAttribute('stroke-linejoin', 'round');
    contour.setAttribute('pointer-events', 'none');
    svg.appendChild(contour);
  }

  if (ctx) scheduleDistanceFieldLighting(group, pathD, plan, ctx);

  if (!defs.parentNode) svg.insertBefore(defs, svg.firstChild);
  return { group, clipId };
}
