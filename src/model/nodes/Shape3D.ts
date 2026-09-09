/**
 * Typed observations for DrawingML `a:scene3d` and `a:sp3d` properties.
 *
 * The parser records source semantics without deciding which renderer backend can display them.
 * Capability classification belongs to the renderer planner.
 */

import { SafeXmlNode } from '../../parser/XmlParser';
import { angleToDeg, emuToPx } from '../../parser/units';

/** Problems with the source data itself, independent of renderer capability. */
export type Shape3DParseIssue = 'malformed-numeric';

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
  /** Direct child effect names observed beside the 3D properties. */
  effectKinds: string[];
  /** Invalid source values that could not be represented safely. */
  parseIssues: Shape3DParseIssue[];
}

function addIssue(issues: Shape3DParseIssue[], issue: Shape3DParseIssue): void {
  if (!issues.includes(issue)) issues.push(issue);
}

function parseRotation(
  node: SafeXmlNode,
  issues: Shape3DParseIssue[],
): Shape3DRotation | undefined {
  if (!node.exists()) return undefined;
  const rawValues = [node.attr('lat'), node.attr('lon'), node.attr('rev')];
  const values = rawValues.map((raw) => (raw === undefined ? 0 : Number(raw)));
  if (values.some((value) => !Number.isFinite(value))) {
    addIssue(issues, 'malformed-numeric');
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
  issues: Shape3DParseIssue[],
): number | undefined {
  const raw = node.attr(attr);
  if (raw === undefined) return emuToPx(defaultEmu);
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) {
    addIssue(issues, 'malformed-numeric');
    return undefined;
  }
  return emuToPx(value);
}

function parseBevel(
  node: SafeXmlNode,
  issues: Shape3DParseIssue[],
): Shape3DBevelProperties | undefined {
  if (!node.exists()) return undefined;
  const explicitPreset = node.attr('prst');
  return {
    preset: explicitPreset ?? 'circle',
    presetExplicit: explicitPreset !== undefined,
    width: parseLength(node, 'w', 0, issues),
    height: parseLength(node, 'h', 0, issues),
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

/** Parse direct `a:scene3d`/`a:sp3d` children from one shape-properties node. */
export function parseShape3DProperties(spPr: SafeXmlNode): Shape3DProperties | undefined {
  const scene3d = spPr.child('scene3d');
  const sp3d = spPr.child('sp3d');
  if (!scene3d.exists() && !sp3d.exists()) return undefined;

  const parseIssues: Shape3DParseIssue[] = [];
  let scene: Scene3DProperties | undefined;
  let shape: Shape3DFormatProperties | undefined;

  if (scene3d.exists()) {
    const camera = scene3d.child('camera');
    const light = scene3d.child('lightRig');
    scene = {};

    if (camera.exists()) {
      scene.cameraPreset = camera.attr('prst');
      const cameraRotationNode = camera.child('rot');
      scene.cameraRotation = parseRotation(cameraRotationNode, parseIssues);
    }

    if (light.exists()) {
      scene.lightRig = light.attr('rig');
      scene.lightDirection = light.attr('dir');
      const lightRotationNode = light.child('rot');
      scene.lightRotation = parseRotation(lightRotationNode, parseIssues);
    }
  }

  if (sp3d.exists()) {
    const bevelTop = parseBevel(sp3d.child('bevelT'), parseIssues);
    const bevelBottom = parseBevel(sp3d.child('bevelB'), parseIssues);
    const contourColorSource = sp3d.child('contourClr');
    const extrusionHeight = parseLength(sp3d, 'extrusionH', 0, parseIssues);
    const contourWidth = parseLength(sp3d, 'contourW', 0, parseIssues);
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
  }

  const effectList = spPr.child('effectLst');
  return {
    scene,
    shape,
    effectKinds: effectList.exists()
      ? effectList.allChildren().map((effect) => effect.localName)
      : [],
    parseIssues,
  };
}
