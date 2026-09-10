/**
 * Bounded DrawingML static 3D renderer.
 *
 * This module deliberately supports small, native-oracle-backed tuples: orthographic-front circle
 * top bevels and zero-depth rectangular camera planes. Everything else returns an explicit flat
 * plan so detection cannot be confused with rendering support.
 */

import type { Shape3DProperties, Shape3DRotation } from '../model/nodes/Shape3D';
import type { RenderContext } from './RenderContext';
import { resolveColor } from './StyleResolver';
import {
  applyLumMod,
  applyLumOff,
  applySatMod,
  hexToRgb,
  rgbToHex,
  rgbToHsl,
} from '../utils/color';
import { fitShape3DRasterScale, renderCircleBevelOverlay } from './shape3d/BevelLighting';
import {
  projectFlatPlane,
  projectiveTransformToCssMatrix3d,
  type ProjectedPoint,
} from './shape3d/CameraProjection';

type StaticShape3DSurface = 'shape' | 'picture';
type StaticShape3DGeometry = 'donut' | 'ellipse' | 'rect' | 'roundrect';
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
  | 'camera-field-of-view'
  | 'camera-zoom'
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
  | 'picture-fill-rect'
  | 'picture-blip-effect'
  | 'picture-shape-format'
  | 'picture-stretch-mode'
  | 'tiled-picture'
  | 'visible-text'
  | 'text-body-properties'
  | 'style-reference'
  | 'visible-stroke'
  | 'shape-transform'
  | 'paint-value'
  | 'backdrop'
  | 'z-position'
  | 'extrusion-paint'
  | 'projection-out-of-range';

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
  hasVisibleText?: boolean;
  /** Presence of p:style can add unverified text/effect inheritance to a live text plane. */
  hasStyleReference?: boolean;
  hasVisibleStroke?: boolean;
  rotation?: number;
  flipH?: boolean;
  flipV?: boolean;
  /** The shape lane is promoted only for a normal solid fill. */
  paintKind?: 'solid' | 'picture' | 'gradient' | 'pattern' | 'group' | 'none' | 'unknown';
  /** Resolved opaque solid paint used for the native-material face adjustment. */
  baseFill?: string;
  isTiledPicture?: boolean;
  /** A non-default a:stretch/a:fillRect changes the picture destination rectangle. */
  hasStretchFillRect?: boolean;
  hasStretchMode?: boolean;
  /** Direct a:blip effects are outside the native-backed picture-plane tuple. */
  hasBlipEffects?: boolean;
  hasPictureBackgroundFill?: boolean;
  hasCustomGeometry?: boolean;
  /** Parsed a:srcRect fractions removed from each source-image edge. */
  sourceCrop?: StaticShape3DSourceCrop;
  /** Exact live-text layout tuple covered by the scene-only native matrix. */
  textPlane?: {
    wrap?: string;
    anchor?: string;
    autofit?: 'spAutoFit' | 'normAutofit' | 'noAutofit' | 'none';
    vertical?: string;
    hasIndependentBounds?: boolean;
  };
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

export interface StaticShape3DCameraPlan {
  mode: 'camera-projected-plane';
  surface: 'shape';
  geometry: 'rect';
  bounds: { width: number; height: number };
  corners: readonly [ProjectedPoint, ProjectedPoint, ProjectedPoint, ProjectedPoint];
  camera: {
    kind: 'orthographic' | 'perspective';
    preset: 'orthographicFront' | 'perspectiveRelaxedModerately';
    rotation: Shape3DRotation;
    fieldOfView?: number;
  };
  fill: {
    top: string;
    middle?: string;
    bottom: string;
  };
}

export interface StaticShape3DTextCameraPlan {
  mode: 'camera-projected-text-plane';
  surface: 'shape';
  geometry: 'rect';
  bounds: { width: number; height: number };
  corners: readonly [ProjectedPoint, ProjectedPoint, ProjectedPoint, ProjectedPoint];
  camera: {
    kind: 'perspective';
    preset: 'perspectiveContrastingRightFacing' | 'perspectiveLeft';
    rotation: Shape3DRotation;
    fieldOfView: number;
  };
}

export interface StaticShape3DPictureCameraPlan {
  mode: 'camera-projected-picture-plane';
  surface: 'picture';
  geometry: 'rect';
  bounds: { width: number; height: number };
  corners: readonly [ProjectedPoint, ProjectedPoint, ProjectedPoint, ProjectedPoint];
  camera: {
    kind: 'perspective';
    preset: 'perspectiveRight';
    rotation: Shape3DRotation;
    fieldOfView: number;
  };
  lighting: {
    brightness: number;
    color: '#FFFFFF';
    opacity: number;
  };
}

export type StaticShape3DPlan =
  | StaticShape3DFlatPlan
  | StaticShape3DSupportedPlan
  | StaticShape3DCameraPlan
  | StaticShape3DTextCameraPlan
  | StaticShape3DPictureCameraPlan;

/** Apply the supported camera homography to live text without rasterizing its DOM content. */
export function applyStaticShape3DTextPlane(
  textContainer: HTMLElement,
  plan: StaticShape3DPlan | undefined,
): boolean {
  if (plan?.mode !== 'camera-projected-text-plane' || textContainer.style.transform) return false;
  const transform = projectiveTransformToCssMatrix3d(
    plan.bounds.width,
    plan.bounds.height,
    plan.corners,
  );
  if (!transform) return false;
  textContainer.dataset.pptxShape3dProjectedTextPlane = plan.camera.kind;
  textContainer.style.transformOrigin = '0px 0px';
  textContainer.style.transform = transform;
  return true;
}

/** Apply the native-backed camera homography to a live, crop-clipping picture stage. */
export function applyStaticShape3DPicturePlane(
  pictureStage: HTMLElement,
  plan: StaticShape3DPlan | undefined,
): boolean {
  if (plan?.mode !== 'camera-projected-picture-plane' || pictureStage.style.transform) return false;
  const transform = projectiveTransformToCssMatrix3d(
    plan.bounds.width,
    plan.bounds.height,
    plan.corners,
  );
  if (!transform) return false;
  pictureStage.dataset.pptxShape3dProjectedPicturePlane = plan.camera.kind;
  pictureStage.style.transformOrigin = '0px 0px';
  pictureStage.style.transform = transform;
  return true;
}

interface AppendStaticShape3DEffectsOptions {
  svg: SVGSVGElement;
  defs: SVGDefsElement;
  /** Main two-dimensional path hidden only after a projected replacement is ready. */
  basePath?: SVGPathElement;
  pathD: string;
  bounds: { width: number; height: number };
  plan: StaticShape3DPlan;
  /** Without a render context, the synchronous vector fallback remains in place. */
  ctx?: RenderContext;
}

interface AppendedStaticShape3DEffects {
  group: SVGGElement;
  clipId?: string;
}

const SUPPORTED_SHAPE_PRESETS = new Set(['donut', 'ellipse', 'rect', 'roundrect']);
const SUPPORTED_PICTURE_PRESETS = new Set(['rect']);
const SUPPORTED_CAMERA_BASE_FILLS = new Set(['#2f75b5', '#4f81bd']);
const SHAPE3D_LIGHTING_VERSION = 'distance-field-v3';
const MAX_SHAPE3D_RASTER_PIXELS = 262_144;
const TARGET_SHAPE3D_RASTER_SCALE = 2;
const PERSPECTIVE_RELAXED_MODERATELY_VIEWPORT_SCALE = 0.95;
const PERSPECTIVE_RELAXED_MODERATELY_PROJECTION_SCALE = 0.996;
const PERSPECTIVE_CONTRASTING_RIGHT_FACING_VIEWPORT_SCALE = 0.95;
const PERSPECTIVE_LEFT_VIEWPORT_SCALE = 0.95;
const PERSPECTIVE_RIGHT_VIEWPORT_SCALE = 0.95;
const shape3dTaskTails = new WeakMap<Promise<void>[], Promise<void>>();
let shape3dIdCounter = 0;

const SOLID_BEVEL_SHADOW_STRENGTH_ANCHORS = [
  { aspect: 0.55, strength: 0.72 },
  { aspect: 1, strength: 0.58 },
  { aspect: 1.6, strength: 0.45 },
] as const;

export function solidBevelShadowStrength(
  width: number,
  height: number,
  geometry: StaticShape3DGeometry,
  bevelWidth: number,
): number {
  const aspect = width / height;
  let lower: (typeof SOLID_BEVEL_SHADOW_STRENGTH_ANCHORS)[number] =
    SOLID_BEVEL_SHADOW_STRENGTH_ANCHORS[0];
  let upper: (typeof SOLID_BEVEL_SHADOW_STRENGTH_ANCHORS)[number] =
    SOLID_BEVEL_SHADOW_STRENGTH_ANCHORS[SOLID_BEVEL_SHADOW_STRENGTH_ANCHORS.length - 1];
  for (let index = 1; index < SOLID_BEVEL_SHADOW_STRENGTH_ANCHORS.length; index += 1) {
    if (aspect <= SOLID_BEVEL_SHADOW_STRENGTH_ANCHORS[index].aspect) {
      lower = SOLID_BEVEL_SHADOW_STRENGTH_ANCHORS[index - 1];
      upper = SOLID_BEVEL_SHADOW_STRENGTH_ANCHORS[index];
      break;
    }
  }
  const lowerLog = Math.log(lower.aspect);
  const upperLog = Math.log(upper.aspect);
  const ratio = clamp((Math.log(aspect) - lowerLog) / Math.max(upperLog - lowerLog, 1e-9), 0, 1);
  const aspectStrength = lower.strength + (upper.strength - lower.strength) * ratio;
  if (geometry !== 'rect' || Math.abs(aspect - 1) > 1e-6) return aspectStrength;

  // The native 6 pt square-rectangle probe has a steeper dark face than the existing 10 pt
  // cohort, while roundRect/ellipse/donut keep the aspect-only response. Interpolate only across
  // those two native-backed rectangular anchors so the 10 pt donut calibration remains unchanged.
  const defaultBevelWidth = 8;
  const establishedBevelWidth = 40 / 3;
  const smallBevelWeight = clamp(
    (establishedBevelWidth - bevelWidth) / (establishedBevelWidth - defaultBevelWidth),
    0,
    1,
  );
  return aspectStrength + (0.7 - aspectStrength) * smallBevelWeight;
}

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

function rotationEquals(rotation: Shape3DRotation | undefined, expected: Shape3DRotation): boolean {
  if (!rotation) return false;
  return (['latitude', 'longitude', 'revolution'] as const).every(
    (axis) => Math.abs(rotation[axis] - expected[axis]) <= 1e-6,
  );
}

function cameraMaterialFill(
  baseFill: string,
  kind: 'orthographic-identity' | 'orthographic-rotated' | 'perspective',
): StaticShape3DCameraPlan['fill'] {
  if (kind === 'orthographic-identity') {
    const color = applySatMod(applyLumOff(baseFill, 3700), 96000);
    return { top: color, bottom: color };
  }
  if (kind === 'orthographic-rotated') {
    const color = applySatMod(applyLumOff(baseFill, 1800), 100000);
    return { top: color, bottom: color };
  }

  // The native matrix includes an explicit Office-blue solid and a theme-style blue. Interpolating
  // between those two verified HSL endpoints reproduces their distinct material responses.
  const baseRgb = hexToRgb(baseFill);
  const { s, l } = rgbToHsl(baseRgb.r, baseRgb.g, baseRgb.b);
  const lightnessMix = clamp((l - 0.4470588235) / (0.5254901961 - 0.4470588235), 0, 1);
  const saturationMix = clamp((s - 0.5877192982) / (0.4545454545 - 0.5877192982), 0, 1);
  const topLumOff = Math.round(12000 + (7800 - 12000) * lightnessMix);
  const bottomLumOff = Math.round(6100 + (3900 - 6100) * lightnessMix);
  const topSatMod = Math.round(107000 + (124000 - 107000) * saturationMix);
  const bottomSatMod = Math.round(94000 + (113000 - 94000) * saturationMix);
  return {
    top: applySatMod(applyLumOff(baseFill, topLumOff), topSatMod),
    bottom: applySatMod(applyLumOff(baseFill, bottomLumOff), bottomSatMod),
  };
}

interface NativeMaterialAnchor {
  aspect: number;
  top: readonly [number, number, number];
  middle: readonly [number, number, number];
  bottom: readonly [number, number, number];
}

const SCENE_ONLY_MATERIAL_ANCHORS: readonly NativeMaterialAnchor[] = [
  {
    aspect: 3.2 / 5.4,
    top: [73, 146, 212],
    middle: [61, 134, 200],
    bottom: [55, 128, 194],
  },
  {
    aspect: 1,
    top: [75, 148, 214],
    middle: [67, 139, 206],
    bottom: [60, 133, 199],
  },
  {
    aspect: 8 / 3.2,
    top: [64, 137, 203],
    middle: [60, 133, 199],
    bottom: [54, 126, 193],
  },
];

function interpolateRgb(
  lower: readonly [number, number, number],
  upper: readonly [number, number, number],
  ratio: number,
): string {
  return rgbToHex(
    lower[0] + (upper[0] - lower[0]) * ratio,
    lower[1] + (upper[1] - lower[1]) * ratio,
    lower[2] + (upper[2] - lower[2]) * ratio,
  );
}

/** Piecewise log-aspect interpolation through the three native scene-only material probes. */
function sceneOnlyCameraMaterialFill(
  width: number,
  height: number,
): StaticShape3DCameraPlan['fill'] {
  const aspect = width / height;
  let lower = SCENE_ONLY_MATERIAL_ANCHORS[0];
  let upper = SCENE_ONLY_MATERIAL_ANCHORS[SCENE_ONLY_MATERIAL_ANCHORS.length - 1];
  for (let index = 1; index < SCENE_ONLY_MATERIAL_ANCHORS.length; index += 1) {
    if (aspect <= SCENE_ONLY_MATERIAL_ANCHORS[index].aspect) {
      lower = SCENE_ONLY_MATERIAL_ANCHORS[index - 1];
      upper = SCENE_ONLY_MATERIAL_ANCHORS[index];
      break;
    }
  }
  const lowerLog = Math.log(lower.aspect);
  const upperLog = Math.log(upper.aspect);
  const ratio =
    lower === upper
      ? 0
      : clamp((Math.log(aspect) - lowerLog) / Math.max(upperLog - lowerLog, 1e-9), 0, 1);
  return {
    top: interpolateRgb(lower.top, upper.top, ratio),
    middle: interpolateRgb(lower.middle, upper.middle, ratio),
    bottom: interpolateRgb(lower.bottom, upper.bottom, ratio),
  };
}

function buildCameraProjectionPlan(
  properties: Shape3DProperties,
  target: StaticShape3DTarget,
  ctx: RenderContext,
): StaticShape3DPlan {
  const scene = properties.scene!;
  const shape = properties.shape;
  if (target.hasVisibleStroke) return flat('visible-stroke');
  if ((target.rotation ?? 0) !== 0 || target.flipH || target.flipV) return flat('shape-transform');
  if (properties.effectKinds.length > 0) return flat('effect-list-conflict');
  if ((shape?.extrusionHeight ?? 0) > 0) return flat('extrusion-height');
  if (shape?.bevelBottom) return flat('bottom-bevel');
  if (shape?.presetMaterial !== undefined) return flat('preset-material');
  if ((shape?.contourWidth ?? 0) > 0 || shape?.contourColorSource?.exists()) {
    return flat('contour-paint');
  }
  if (normalizedPreset(target) !== 'rect') return flat('geometry-preset');
  if (!scene.lightRig) return flat('missing-light-rig');
  if (scene.lightRig !== 'threePt') return flat('light-rig');
  if (scene.lightDirection !== 't') return flat('light-direction');
  if (scene.lightRotation) return flat('light-rotation');
  if (scene.cameraZoom !== undefined) return flat('camera-zoom');

  if (target.nodeType === 'picture') {
    if (shape) return flat('picture-shape-format');
    if (target.paintKind !== 'picture') return flat('paint-kind');
    if (target.hasStyleReference) return flat('style-reference');
    if (target.presetGeometry?.toLowerCase() !== 'rect' || target.hasCustomGeometry) {
      return flat('geometry-preset');
    }
    if (!target.hasStretchMode) return flat('picture-stretch-mode');
    if (target.hasStretchFillRect) return flat('picture-fill-rect');
    if (target.hasBlipEffects) return flat('picture-blip-effect');
    if (target.hasPictureBackgroundFill) return flat('paint-kind');
    if (scene.cameraPreset !== 'perspectiveRight') return flat('camera-preset');
    if (scene.fieldOfView === undefined || Math.abs(scene.fieldOfView - 95) > 1e-6) {
      return flat('camera-field-of-view');
    }
    if (scene.cameraRotation) return flat('camera-rotation');
    // The Office preset supplies a -20-degree longitude when a:rot is absent.
    const rotation = { latitude: 0, longitude: -20, revolution: 0 };
    const projection = projectFlatPlane({
      kind: 'perspective',
      width: target.width,
      height: target.height,
      presentationWidth: ctx.presentation.width,
      rotation,
      fieldOfView: scene.fieldOfView,
      presetViewportScale: PERSPECTIVE_RIGHT_VIEWPORT_SCALE,
    });
    if (!projection) return flat('projection-out-of-range');
    return {
      mode: 'camera-projected-picture-plane',
      surface: 'picture',
      geometry: 'rect',
      bounds: { width: target.width, height: target.height },
      corners: projection.corners,
      camera: {
        kind: 'perspective',
        preset: 'perspectiveRight',
        rotation,
        fieldOfView: scene.fieldOfView,
      },
      // The native matrix consistently brightens this zero-depth picture material under
      // threePt:t. These constants are fitted across all four aspect/crop probes, not one slide.
      lighting: { brightness: 1.01, color: '#FFFFFF', opacity: 0.09 },
    };
  }

  if (target.hasVisibleText) {
    if (shape) return flat('visible-text');
    if (target.paintKind !== 'none') return flat('paint-kind');
    if (target.hasStyleReference) return flat('style-reference');
    const textPlane = target.textPlane;
    if (
      !textPlane ||
      textPlane.wrap !== 'none' ||
      textPlane.autofit !== 'spAutoFit' ||
      textPlane.vertical !== undefined ||
      textPlane.hasIndependentBounds
    ) {
      return flat('text-body-properties');
    }
    let preset: StaticShape3DTextCameraPlan['camera']['preset'];
    let rotation: Shape3DRotation;
    let fieldOfView: number;
    let presetViewportScale: number;
    if (scene.cameraPreset === 'perspectiveContrastingRightFacing') {
      if (textPlane.anchor !== 'ctr') return flat('text-body-properties');
      if (scene.fieldOfView === undefined || Math.abs(scene.fieldOfView - 85) > 1e-6) {
        return flat('camera-field-of-view');
      }
      const expectedRotation = {
        latitude: 0,
        longitude: 19532225 / 60000,
        revolution: 0,
      };
      if (!rotationEquals(scene.cameraRotation, expectedRotation)) return flat('camera-rotation');
      preset = 'perspectiveContrastingRightFacing';
      rotation = scene.cameraRotation!;
      fieldOfView = scene.fieldOfView;
      presetViewportScale = PERSPECTIVE_CONTRASTING_RIGHT_FACING_VIEWPORT_SCALE;
    } else if (scene.cameraPreset === 'perspectiveLeft') {
      if (textPlane.anchor !== undefined) return flat('text-body-properties');
      if (scene.fieldOfView === undefined || Math.abs(scene.fieldOfView - 120) > 1e-6) {
        return flat('camera-field-of-view');
      }
      if (scene.cameraRotation) return flat('camera-rotation');
      // The preset carries a 20-degree longitude when a:rot is absent. This fixed rotation is
      // defined by the Office camera preset and preserves the source's implicit semantics.
      preset = 'perspectiveLeft';
      rotation = { latitude: 0, longitude: 20, revolution: 0 };
      fieldOfView = scene.fieldOfView;
      presetViewportScale = PERSPECTIVE_LEFT_VIEWPORT_SCALE;
    } else {
      return flat('camera-preset');
    }
    const projection = projectFlatPlane({
      kind: 'perspective',
      width: target.width,
      height: target.height,
      presentationWidth: ctx.presentation.width,
      rotation,
      fieldOfView,
      presetViewportScale,
    });
    if (!projection) return flat('projection-out-of-range');
    return {
      mode: 'camera-projected-text-plane',
      surface: 'shape',
      geometry: 'rect',
      bounds: { width: target.width, height: target.height },
      corners: projection.corners,
      camera: {
        kind: 'perspective',
        preset,
        rotation,
        fieldOfView,
      },
    };
  }

  if (
    target.paintKind !== 'solid' ||
    !target.baseFill ||
    !/^#[0-9a-f]{6}$/i.test(target.baseFill)
  ) {
    return flat('paint-kind');
  }
  const baseFill = target.baseFill.toLowerCase();
  if (!SUPPORTED_CAMERA_BASE_FILLS.has(baseFill)) return flat('paint-value');
  if (!shape && baseFill !== '#2f75b5') return flat('paint-value');

  let kind: StaticShape3DCameraPlan['camera']['kind'];
  let preset: StaticShape3DCameraPlan['camera']['preset'];
  let rotation: Shape3DRotation;
  let fieldOfView: number | undefined;
  let materialKind: Parameters<typeof cameraMaterialFill>[1];
  let presetViewportScale: number | undefined;

  if (scene.cameraPreset === 'orthographicFront') {
    if (scene.fieldOfView !== undefined) return flat('camera-field-of-view');
    if (baseFill !== '#2f75b5') return flat('paint-value');
    kind = 'orthographic';
    preset = 'orthographicFront';
    if (!scene.cameraRotation) {
      rotation = { latitude: 0, longitude: 0, revolution: 0 };
      materialKind = 'orthographic-identity';
    } else if (
      rotationEquals(scene.cameraRotation, { latitude: 20, longitude: 30, revolution: 0 })
    ) {
      rotation = scene.cameraRotation;
      materialKind = 'orthographic-rotated';
    } else {
      return flat('camera-rotation');
    }
  } else if (scene.cameraPreset === 'perspectiveRelaxedModerately') {
    if (scene.fieldOfView === undefined || Math.abs(scene.fieldOfView - 120) > 1e-6) {
      return flat('camera-field-of-view');
    }
    const expectedRotation = {
      latitude: 18590633 / 60000,
      longitude: 0,
      revolution: 0,
    };
    if (!rotationEquals(scene.cameraRotation, expectedRotation)) return flat('camera-rotation');
    kind = 'perspective';
    preset = 'perspectiveRelaxedModerately';
    rotation = scene.cameraRotation!;
    fieldOfView = scene.fieldOfView;
    materialKind = 'perspective';
    presetViewportScale = PERSPECTIVE_RELAXED_MODERATELY_VIEWPORT_SCALE;
    // Absence of a:sp3d is verified as an implicit zero-depth plane only for this exact tuple.
  } else {
    if (!shape) return flat('missing-shape-format');
    return flat('camera-preset');
  }

  const projection = projectFlatPlane({
    kind,
    width: target.width,
    height: target.height,
    presentationWidth: ctx.presentation.width,
    rotation,
    fieldOfView,
    presetViewportScale,
    presetProjectionScale:
      kind === 'perspective' ? PERSPECTIVE_RELAXED_MODERATELY_PROJECTION_SCALE : undefined,
  });
  if (!projection) return flat('projection-out-of-range');
  return {
    mode: 'camera-projected-plane',
    surface: 'shape',
    geometry: 'rect',
    bounds: { width: target.width, height: target.height },
    corners: projection.corners,
    camera: { kind, preset, rotation, fieldOfView },
    fill: shape
      ? cameraMaterialFill(baseFill, materialKind)
      : sceneOnlyCameraMaterialFill(target.width, target.height),
  };
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
  const shape = properties.shape;
  if (scene.hasBackdrop) return flat('backdrop');
  if (Math.abs(shape?.zPosition ?? 0) > 1e-9) return flat('z-position');
  if (shape?.extrusionColor) return flat('extrusion-paint');
  if (!shape?.bevelTop) return buildCameraProjectionPlan(properties, target, ctx);
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

  if (properties.effectKinds.some((effect) => effect !== 'outerShdw')) {
    return flat('effect-list-conflict');
  }
  if ((shape.extrusionHeight ?? 0) > 0) return flat('extrusion-height');
  if (shape.bevelBottom) return flat('bottom-bevel');
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
  shadowStrength: number,
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
      applyLumMod(faceColor, Math.round((1 - strength * shadowStrength) * 100000)),
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
    lighting = applySolidMaterialLighting(
      lighting,
      plan.faceColor,
      solidBevelShadowStrength(
        plan.bounds.width,
        plan.bounds.height,
        plan.geometry,
        plan.bevel.width,
      ),
    );
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

function cameraPlanePath(
  corners: readonly [ProjectedPoint, ProjectedPoint, ProjectedPoint, ProjectedPoint],
): string {
  return `${corners
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x},${point.y}`)
    .join(' ')} Z`;
}

function appendCameraProjectedPlane(
  svg: SVGSVGElement,
  defs: SVGDefsElement,
  basePath: SVGPathElement | undefined,
  plan: StaticShape3DCameraPlan,
): AppendedStaticShape3DEffects | undefined {
  if (!basePath) return undefined;
  const ns = 'http://www.w3.org/2000/svg';
  const id = ++shape3dIdCounter;
  const group = document.createElementNS(ns, 'g');
  group.dataset.pptxShape3dCamera = plan.camera.preset;
  group.setAttribute('pointer-events', 'none');

  const projectedPath = document.createElementNS(ns, 'path');
  projectedPath.dataset.pptxShape3dProjectedPlane = plan.camera.kind;
  projectedPath.setAttribute('d', cameraPlanePath(plan.corners));
  projectedPath.setAttribute('stroke', 'none');
  if (plan.fill.top === plan.fill.bottom) {
    projectedPath.setAttribute('fill', plan.fill.top);
  } else {
    const gradientId = `shape3d-camera-gradient-${id}`;
    const gradient = document.createElementNS(ns, 'linearGradient');
    gradient.id = gradientId;
    gradient.dataset.pptxShape3dCameraGradient = plan.camera.preset;
    gradient.setAttribute('gradientUnits', 'userSpaceOnUse');
    gradient.setAttribute('color-interpolation', 'linearRGB');
    const yValues = plan.corners.map((point) => point.y);
    gradient.setAttribute('x1', String(plan.bounds.width / 2));
    gradient.setAttribute('x2', String(plan.bounds.width / 2));
    gradient.setAttribute('y1', String(Math.min(...yValues)));
    gradient.setAttribute('y2', String(Math.max(...yValues)));
    appendStop(gradient, '0%', plan.fill.top, 1);
    if (plan.fill.middle) appendStop(gradient, '50%', plan.fill.middle, 1);
    appendStop(gradient, '100%', plan.fill.bottom, 1);
    defs.appendChild(gradient);
    projectedPath.setAttribute('fill', `url(#${gradientId})`);
  }
  group.appendChild(projectedPath);
  svg.appendChild(group);
  basePath.setAttribute('visibility', 'hidden');
  if (defs.children.length > 0 && !defs.parentNode) svg.insertBefore(defs, svg.firstChild);
  return { group };
}

/** Append the scoped bevel overlay without filtering sibling text or mutating the base path. */
export function appendStaticShape3DEffects(
  options: AppendStaticShape3DEffectsOptions,
): AppendedStaticShape3DEffects | undefined {
  const { svg, defs, basePath, pathD, bounds, plan, ctx } = options;
  if (plan.mode === 'camera-projected-plane') {
    return appendCameraProjectedPlane(svg, defs, basePath, plan);
  }
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
  clipShape.setAttribute('fill-rule', 'evenodd');
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
    faceSheen.setAttribute('fill-rule', 'evenodd');
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
