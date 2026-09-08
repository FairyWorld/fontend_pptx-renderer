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
import { applyLumOff, applySatMod } from '../utils/color';

export type StaticShape3DSurface = 'shape' | 'picture';

export type StaticShape3DFallbackReason =
  | 'missing-properties'
  | 'parser-unsupported'
  | 'invalid-bounds'
  | 'line-like'
  | 'geometry-preset'
  | 'paint-kind'
  | 'tiled-picture';

export interface StaticShape3DTarget {
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

export interface AppendStaticShape3DEffectsOptions {
  svg: SVGSVGElement;
  defs: SVGDefsElement;
  pathD: string;
  bounds: { width: number; height: number };
  plan: StaticShape3DPlan;
}

export interface AppendedStaticShape3DEffects {
  group: SVGGElement;
  filterId: string;
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
    faceColor:
      target.nodeType === 'shape' && target.baseFill
        ? applySatMod(applyLumOff(target.baseFill, 3500), 102000)
        : undefined,
    bounds: { width: target.width, height: target.height },
    bevel: { preset: 'circle', width, height },
    contour: resolveContour(properties, ctx),
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

function appendAlphaScale(
  ns: string,
  filter: SVGFilterElement,
  input: string,
  result: string,
  slope: number,
): void {
  const transfer = document.createElementNS(ns, 'feComponentTransfer');
  transfer.setAttribute('in', input);
  transfer.setAttribute('result', result);
  const alpha = document.createElementNS(ns, 'feFuncA');
  alpha.setAttribute('type', 'linear');
  alpha.setAttribute('slope', String(slope));
  transfer.appendChild(alpha);
  filter.appendChild(transfer);
}

function appendDistantLight(
  ns: string,
  parent: SVGElement,
  plan: StaticShape3DSupportedPlan,
): void {
  const light = document.createElementNS(ns, 'feDistantLight');
  light.setAttribute('azimuth', String(plan.light.azimuth));
  light.setAttribute('elevation', String(plan.light.elevation));
  parent.appendChild(light);
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
  const gradientId = `shape3d-gradient-${id}`;
  const filterId = `shape3d-filter-${id}`;

  const clipPath = document.createElementNS(ns, 'clipPath');
  clipPath.id = clipId;
  clipPath.setAttribute('clipPathUnits', 'userSpaceOnUse');
  const clipShape = document.createElementNS(ns, 'path');
  clipShape.setAttribute('d', pathD);
  clipPath.appendChild(clipShape);
  defs.appendChild(clipPath);

  const gradient = document.createElementNS(ns, 'linearGradient');
  gradient.id = gradientId;
  gradient.setAttribute('gradientUnits', 'userSpaceOnUse');
  gradient.setAttribute('color-interpolation', 'linearRGB');
  gradient.setAttribute('x1', '0');
  gradient.setAttribute('y1', '0');
  gradient.setAttribute('x2', String(bounds.width));
  gradient.setAttribute('y2', String(bounds.height));
  const isPicture = plan.surface === 'picture';
  appendStop(gradient, '0%', '#FFFFFF', isPicture ? 0.62 : 0.72);
  appendStop(gradient, '38%', '#FFFFFF', isPicture ? 0.12 : 0.18);
  appendStop(gradient, '56%', '#000000', isPicture ? 0.08 : 0.12);
  appendStop(gradient, '100%', '#000000', isPicture ? 0.62 : 0.72);
  defs.appendChild(gradient);

  const filter = document.createElementNS(ns, 'filter');
  filter.id = filterId;
  filter.dataset.pptxShape3dFilter = 'orthographic-top-bevel';
  filter.setAttribute('filterUnits', 'userSpaceOnUse');
  filter.setAttribute('primitiveUnits', 'userSpaceOnUse');
  filter.setAttribute('color-interpolation-filters', 'linearRGB');
  const bevelExtent = Math.max(plan.bevel.width, plan.bevel.height, plan.contour?.width ?? 0, 1);
  const margin = Math.min(bevelExtent * 2, Math.max(bounds.width, bounds.height));
  filter.setAttribute('x', String(-margin));
  filter.setAttribute('y', String(-margin));
  filter.setAttribute('width', String(bounds.width + margin * 2));
  filter.setAttribute('height', String(bounds.height + margin * 2));

  const blur = document.createElementNS(ns, 'feGaussianBlur');
  blur.setAttribute('in', 'SourceAlpha');
  blur.setAttribute(
    'stdDeviation',
    `${Math.max(0.25, plan.bevel.width / 4)} ${Math.max(0.25, plan.bevel.height / 4)}`,
  );
  blur.setAttribute('result', 'shape3d-bump');
  filter.appendChild(blur);

  const diffuse = document.createElementNS(ns, 'feDiffuseLighting');
  diffuse.setAttribute('in', 'shape3d-bump');
  diffuse.setAttribute('surfaceScale', String(Math.max(1, bevelExtent * 0.8)));
  diffuse.setAttribute('diffuseConstant', plan.light.rig === 'threePt' ? '0.78' : '0.65');
  diffuse.setAttribute('lighting-color', '#FFFFFF');
  diffuse.setAttribute('result', 'shape3d-diffuse');
  appendDistantLight(ns, diffuse, plan);
  filter.appendChild(diffuse);

  const diffuseClip = document.createElementNS(ns, 'feComposite');
  diffuseClip.setAttribute('in', 'shape3d-diffuse');
  diffuseClip.setAttribute('in2', 'SourceAlpha');
  diffuseClip.setAttribute('operator', 'in');
  diffuseClip.setAttribute('result', 'shape3d-diffuse-clip');
  filter.appendChild(diffuseClip);
  appendAlphaScale(ns, filter, 'shape3d-diffuse-clip', 'shape3d-diffuse-tone', 0.28);

  const specular = document.createElementNS(ns, 'feSpecularLighting');
  specular.setAttribute('in', 'shape3d-bump');
  specular.setAttribute('surfaceScale', String(Math.max(1, bevelExtent)));
  specular.setAttribute('specularConstant', plan.light.rig === 'threePt' ? '0.82' : '0.65');
  specular.setAttribute('specularExponent', '18');
  specular.setAttribute('lighting-color', '#FFFFFF');
  specular.setAttribute('result', 'shape3d-specular');
  appendDistantLight(ns, specular, plan);
  filter.appendChild(specular);

  const specularClip = document.createElementNS(ns, 'feComposite');
  specularClip.setAttribute('in', 'shape3d-specular');
  specularClip.setAttribute('in2', 'SourceAlpha');
  specularClip.setAttribute('operator', 'in');
  specularClip.setAttribute('result', 'shape3d-specular-clip');
  filter.appendChild(specularClip);
  appendAlphaScale(ns, filter, 'shape3d-specular-clip', 'shape3d-specular-tone', 0.5);

  const multiply = document.createElementNS(ns, 'feBlend');
  multiply.setAttribute('in', 'SourceGraphic');
  multiply.setAttribute('in2', 'shape3d-diffuse-tone');
  multiply.setAttribute('mode', 'multiply');
  multiply.setAttribute('result', 'shape3d-lit-edge');
  filter.appendChild(multiply);

  const screen = document.createElementNS(ns, 'feBlend');
  screen.setAttribute('in', 'shape3d-lit-edge');
  screen.setAttribute('in2', 'shape3d-specular-tone');
  screen.setAttribute('mode', 'screen');
  filter.appendChild(screen);
  defs.appendChild(filter);

  const group = document.createElementNS(ns, 'g');
  group.dataset.pptxShape3dBevel = 'orthographic-top-bevel';
  group.setAttribute('clip-path', `url(#${clipId})`);
  group.setAttribute('pointer-events', 'none');

  if (plan.surface === 'shape' && plan.faceColor) {
    const faceSheen = document.createElementNS(ns, 'path');
    faceSheen.setAttribute('d', pathD);
    faceSheen.setAttribute('fill', plan.faceColor);
    faceSheen.setAttribute('stroke', 'none');
    faceSheen.dataset.pptxShape3dFace = 'sheen';
    group.appendChild(faceSheen);
  }

  const bevelPath = document.createElementNS(ns, 'path');
  bevelPath.setAttribute('d', pathD);
  bevelPath.setAttribute('fill', 'none');
  bevelPath.setAttribute('stroke', `url(#${gradientId})`);
  bevelPath.setAttribute('stroke-width', String(Math.max(plan.bevel.width, plan.bevel.height) * 2));
  bevelPath.setAttribute('stroke-linejoin', 'round');
  bevelPath.setAttribute('filter', `url(#${filterId})`);
  bevelPath.setAttribute('opacity', plan.surface === 'picture' ? '0.82' : '0.9');
  group.appendChild(bevelPath);
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
  return { group, filterId, clipId };
}
