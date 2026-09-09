/**
 * Bounded DrawingML static 3D renderer.
 *
 * This module deliberately supports one small, native-oracle-backed tuple: orthographic-front
 * circle top bevels on solid rect/roundRect shapes and rectangular pictures. Everything else
 * returns an explicit flat plan so detection cannot be confused with rendering support.
 */

import type { Shape3DProperties, Shape3DRotation } from '../model/nodes/Shape3D';
import type { RenderContext } from './RenderContext';
import { resolveColor } from './StyleResolver';
import { applyLumMod, applyLumOff, applySatMod } from '../utils/color';

type StaticShape3DSurface = 'shape' | 'picture';
type StaticShape3DGeometry = 'rect' | 'roundrect';
type BevelFace = 'top' | 'right' | 'bottom' | 'left';

type StaticShape3DFallbackReason =
  | 'missing-properties'
  | 'parser-unsupported'
  | 'invalid-bounds'
  | 'line-like'
  | 'geometry-preset'
  | 'paint-kind'
  | 'contour-paint'
  | 'tiled-picture';

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
}

export interface StaticShape3DFlatPlan {
  mode: 'flat';
  reason: StaticShape3DFallbackReason;
  parserReasons?: readonly string[];
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
  };
}

export type StaticShape3DPlan = StaticShape3DFlatPlan | StaticShape3DSupportedPlan;

interface AppendStaticShape3DEffectsOptions {
  svg: SVGSVGElement;
  defs: SVGDefsElement;
  pathD: string;
  bounds: { width: number; height: number };
  plan: StaticShape3DPlan;
}

interface AppendedStaticShape3DEffects {
  group: SVGGElement;
  clipId: string;
}

const SUPPORTED_SHAPE_PRESETS = new Set(['rect', 'roundrect']);
const SUPPORTED_PICTURE_PRESETS = new Set(['rect']);
let shape3dIdCounter = 0;

function flat(
  reason: StaticShape3DFallbackReason,
  parserReasons?: readonly string[],
): StaticShape3DFlatPlan {
  return parserReasons?.length ? { mode: 'flat', reason, parserReasons } : { mode: 'flat', reason };
}

function normalizedPreset(target: StaticShape3DTarget): string {
  if (!target.presetGeometry && target.nodeType === 'picture') return 'rect';
  return target.presetGeometry?.toLowerCase() ?? '';
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
  if (properties.unsupportedReasons.length > 0) {
    return flat('parser-unsupported', properties.unsupportedReasons);
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

  const bevel = properties.shape?.bevelTop;
  const scene = properties.scene;
  if (
    !bevel ||
    bevel.preset !== 'circle' ||
    !Number.isFinite(bevel.width) ||
    !Number.isFinite(bevel.height) ||
    !(bevel.width! > 0) ||
    !(bevel.height! > 0) ||
    (scene?.lightRig !== 'twoPt' && scene?.lightRig !== 'threePt') ||
    scene.lightDirection !== 't'
  ) {
    // The model parser normally rejects these first. Keep the renderer total for callers that
    // construct model objects directly.
    return flat('parser-unsupported');
  }

  const contour = resolveContour(properties, ctx);
  if ((properties.shape?.contourWidth ?? 0) > 0 && !contour) {
    return flat('contour-paint');
  }

  const width = Math.min(bevel.width!, target.width / 2);
  const height = Math.min(bevel.height!, target.height / 2);
  if (!(width > 0) || !(height > 0)) return flat('invalid-bounds');

  const rig = scene.lightRig;
  const rotation = scene.lightRotation;
  // PowerPoint's top rigs illuminate the upper-left face in the scoped native cases. The real
  // picture sentinel carries a 120-degree revolution; retain it in the plan and rotate the mapped
  // light modestly instead of broadening support to arbitrary rotations.
  const azimuth = rig === 'threePt' ? 315 : rotation?.revolution === 120 ? 285 : 300;

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
      elevation: rig === 'threePt' ? 50 : 45,
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

/** Append the scoped bevel overlay without filtering sibling text or mutating the base path. */
export function appendStaticShape3DEffects(
  options: AppendStaticShape3DEffectsOptions,
): AppendedStaticShape3DEffects | undefined {
  const { svg, defs, pathD, bounds, plan } = options;
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

  if (!defs.parentNode) svg.insertBefore(defs, svg.firstChild);
  return { group, clipId };
}
