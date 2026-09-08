/**
 * Typed observations for DrawingML `a:scene3d` and `a:sp3d` properties.
 *
 * The first renderer cohort is intentionally narrow. The parser preserves values outside that
 * cohort and emits stable reason codes so callers can retain the ordinary 2D fallback without
 * mistaking detection for support.
 */

import { SafeXmlNode } from '../../parser/XmlParser';
import { angleToDeg, emuToPx } from '../../parser/units';

export type Shape3DUnsupportedReason =
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
  | 'malformed-numeric';

export interface Shape3DRotation {
  latitude: number;
  longitude: number;
  revolution: number;
}

export interface Scene3DProperties {
  cameraPreset?: string;
  cameraRotation?: Shape3DRotation;
  lightRig?: string;
  lightDirection?: string;
  lightRotation?: Shape3DRotation;
}

export interface Shape3DBevelProperties {
  preset: string;
  presetExplicit: boolean;
  width?: number;
  height?: number;
}

export interface Shape3DColorObservation {
  type: string;
  value?: string;
}

export interface Shape3DFormatProperties {
  extrusionHeight?: number;
  contourWidth?: number;
  presetMaterial?: string;
  bevelTop?: Shape3DBevelProperties;
  bevelBottom?: Shape3DBevelProperties;
  contourColor?: Shape3DColorObservation;
  /** @internal Wrapper color node consumed by the normal theme/color resolver. */
  contourColorSource?: SafeXmlNode;
}

export interface Shape3DProperties {
  scene?: Scene3DProperties;
  shape?: Shape3DFormatProperties;
  unsupportedReasons: Shape3DUnsupportedReason[];
}

function addReason(reasons: Shape3DUnsupportedReason[], reason: Shape3DUnsupportedReason): void {
  if (!reasons.includes(reason)) reasons.push(reason);
}

function parseRotation(
  node: SafeXmlNode,
  reasons: Shape3DUnsupportedReason[],
): Shape3DRotation | undefined {
  if (!node.exists()) return undefined;
  const rawValues = [node.attr('lat'), node.attr('lon'), node.attr('rev')];
  const values = rawValues.map((raw) => (raw === undefined ? 0 : Number(raw)));
  if (values.some((value) => !Number.isFinite(value))) {
    addReason(reasons, 'malformed-numeric');
    return undefined;
  }
  return {
    latitude: angleToDeg(values[0]),
    longitude: angleToDeg(values[1]),
    revolution: angleToDeg(values[2]),
  };
}

function parseLength(
  node: SafeXmlNode,
  attr: string,
  defaultEmu: number,
  reasons: Shape3DUnsupportedReason[],
): number | undefined {
  const raw = node.attr(attr);
  if (raw === undefined) return emuToPx(defaultEmu);
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) {
    addReason(reasons, 'malformed-numeric');
    return undefined;
  }
  return emuToPx(value);
}

function parseBevel(
  node: SafeXmlNode,
  reasons: Shape3DUnsupportedReason[],
): Shape3DBevelProperties | undefined {
  if (!node.exists()) return undefined;
  const explicitPreset = node.attr('prst');
  return {
    preset: explicitPreset ?? 'circle',
    presetExplicit: explicitPreset !== undefined,
    width: parseLength(node, 'w', 0, reasons),
    height: parseLength(node, 'h', 0, reasons),
  };
}

function parseColorObservation(node: SafeXmlNode): Shape3DColorObservation | undefined {
  if (!node.exists()) return undefined;
  const color = node.allChildren()[0];
  if (!color?.exists()) return undefined;
  return {
    type: color.localName,
    value: color.attr('val') ?? color.attr('lastClr'),
  };
}

function isSupportedLightRotation(
  lightRig: string | undefined,
  lightDirection: string | undefined,
  rotation: Shape3DRotation,
): boolean {
  if (lightRig !== 'twoPt' || lightDirection !== 't') return false;
  return rotation.latitude === 0 && rotation.longitude === 0 && rotation.revolution === 120;
}

/** Parse direct `a:scene3d`/`a:sp3d` children from one shape-properties node. */
export function parseShape3DProperties(spPr: SafeXmlNode): Shape3DProperties | undefined {
  const scene3d = spPr.child('scene3d');
  const sp3d = spPr.child('sp3d');
  if (!scene3d.exists() && !sp3d.exists()) return undefined;

  const unsupportedReasons: Shape3DUnsupportedReason[] = [];
  let scene: Scene3DProperties | undefined;
  let shape: Shape3DFormatProperties | undefined;

  if (!scene3d.exists()) {
    addReason(unsupportedReasons, 'missing-scene');
  } else {
    const camera = scene3d.child('camera');
    const light = scene3d.child('lightRig');
    scene = {};

    if (!camera.exists()) {
      addReason(unsupportedReasons, 'missing-camera');
    } else {
      scene.cameraPreset = camera.attr('prst');
      if (scene.cameraPreset !== 'orthographicFront') {
        addReason(unsupportedReasons, 'camera-preset');
      }
      const cameraRotationNode = camera.child('rot');
      scene.cameraRotation = parseRotation(cameraRotationNode, unsupportedReasons);
      if (cameraRotationNode.exists()) addReason(unsupportedReasons, 'camera-rotation');
    }

    if (!light.exists()) {
      addReason(unsupportedReasons, 'missing-light-rig');
    } else {
      scene.lightRig = light.attr('rig');
      scene.lightDirection = light.attr('dir');
      if (scene.lightRig !== 'twoPt' && scene.lightRig !== 'threePt') {
        addReason(unsupportedReasons, 'light-rig');
      }
      if (scene.lightDirection !== 't') {
        addReason(unsupportedReasons, 'light-direction');
      }
      const lightRotationNode = light.child('rot');
      scene.lightRotation = parseRotation(lightRotationNode, unsupportedReasons);
      if (
        lightRotationNode.exists() &&
        (!scene.lightRotation ||
          !isSupportedLightRotation(scene.lightRig, scene.lightDirection, scene.lightRotation))
      ) {
        addReason(unsupportedReasons, 'light-rotation');
      }
    }
  }

  if (!sp3d.exists()) {
    addReason(unsupportedReasons, 'missing-shape-format');
  } else {
    const bevelTop = parseBevel(sp3d.child('bevelT'), unsupportedReasons);
    const bevelBottom = parseBevel(sp3d.child('bevelB'), unsupportedReasons);
    const contourColorSource = sp3d.child('contourClr');
    const extrusionHeight = parseLength(sp3d, 'extrusionH', 0, unsupportedReasons);
    const contourWidth = parseLength(sp3d, 'contourW', 0, unsupportedReasons);
    const presetMaterial = sp3d.attr('prstMaterial');

    shape = {
      extrusionHeight,
      contourWidth,
      presetMaterial,
      bevelTop,
      bevelBottom,
      contourColor: parseColorObservation(contourColorSource),
      contourColorSource: contourColorSource.exists() ? contourColorSource : undefined,
    };

    if (extrusionHeight !== undefined && extrusionHeight > 0) {
      addReason(unsupportedReasons, 'extrusion-height');
    }
    if (bevelBottom) addReason(unsupportedReasons, 'bottom-bevel');
    if (!bevelTop) {
      addReason(unsupportedReasons, 'missing-top-bevel');
    } else {
      if (bevelTop.preset !== 'circle') addReason(unsupportedReasons, 'top-bevel-preset');
      if (
        bevelTop.width === undefined ||
        bevelTop.height === undefined ||
        bevelTop.width <= 0 ||
        bevelTop.height <= 0
      ) {
        addReason(unsupportedReasons, 'top-bevel-dimensions');
      }
    }
    if (presetMaterial !== undefined) addReason(unsupportedReasons, 'preset-material');
  }

  const effectList = spPr.child('effectLst');
  if (
    effectList.exists() &&
    effectList.allChildren().some((effect) => effect.localName !== 'outerShdw')
  ) {
    addReason(unsupportedReasons, 'effect-list-conflict');
  }

  return { scene, shape, unsupportedReasons };
}
