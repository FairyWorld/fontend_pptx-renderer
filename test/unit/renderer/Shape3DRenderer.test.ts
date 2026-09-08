import { describe, expect, it } from 'vitest';
import { parseXml } from '../../../src/parser/XmlParser';
import { parseShapeNode } from '../../../src/model/nodes/ShapeNode';
import {
  appendStaticShape3DEffects,
  buildStaticShape3DPlan,
} from '../../../src/renderer/Shape3DRenderer';
import { createMockRenderContext } from '../helpers/mockContext';

function parseShape3D(sceneXml: string, shapeXml: string, extraShapeProperties = '') {
  const xml = `
    <p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:nvSpPr><p:cNvPr id="1" name="3D probe"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="1905000" cy="952500"/></a:xfrm>
        <a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom>
        ${extraShapeProperties}
        ${sceneXml}
        ${shapeXml}
      </p:spPr>
    </p:sp>`;
  return parseShapeNode(parseXml(xml)).shape3d;
}

const supportedScene = `
  <a:scene3d>
    <a:camera prst="orthographicFront"/>
    <a:lightRig rig="threePt" dir="t"/>
  </a:scene3d>`;

const supportedShape = `
  <a:sp3d contourW="12700">
    <a:bevelT w="127000" h="127000" prst="circle"/>
    <a:contourClr><a:srgbClr val="FFFFFF"/></a:contourClr>
  </a:sp3d>`;

describe('buildStaticShape3DPlan', () => {
  it('builds the bounded orthographic circle top-bevel and contour plan', () => {
    const shape3d = parseShape3D(supportedScene, supportedShape);
    const plan = buildStaticShape3DPlan(
      shape3d,
      {
        nodeType: 'shape',
        presetGeometry: 'roundRect',
        width: 200,
        height: 100,
        paintKind: 'solid',
        baseFill: '#2F75B5',
      },
      createMockRenderContext(),
    );

    expect(plan).toMatchObject({
      mode: 'orthographic-top-bevel',
      surface: 'shape',
      faceColor: '#327ec4',
      bevel: { preset: 'circle' },
      contour: { color: '#FFFFFF' },
      light: { rig: 'threePt', direction: 't' },
    });
    if (plan.mode !== 'orthographic-top-bevel') throw new Error('expected supported plan');
    expect(plan.bevel.width).toBeCloseTo(13.3333, 3);
    expect(plan.bevel.height).toBeCloseTo(13.3333, 3);
    expect(plan.contour?.width).toBeCloseTo(1.3333, 3);
  });

  it('accepts the exact real-corpus picture light rotation and implicit circle bevel', () => {
    const shape3d = parseShape3D(
      `<a:scene3d>
         <a:camera prst="orthographicFront"/>
         <a:lightRig rig="twoPt" dir="t"><a:rot lat="0" lon="0" rev="7200000"/></a:lightRig>
       </a:scene3d>`,
      `<a:sp3d><a:bevelT w="25400" h="19050"/><a:contourClr><a:srgbClr val="FFFFFF"/></a:contourClr></a:sp3d>`,
      `<a:effectLst><a:outerShdw blurRad="55000" dist="18000"><a:srgbClr val="000000"/></a:outerShdw></a:effectLst>`,
    );
    const plan = buildStaticShape3DPlan(
      shape3d,
      { nodeType: 'picture', presetGeometry: 'rect', width: 320, height: 180 },
      createMockRenderContext(),
    );

    expect(plan).toMatchObject({
      mode: 'orthographic-top-bevel',
      surface: 'picture',
      bevel: { preset: 'circle' },
      contour: undefined,
      light: {
        rig: 'twoPt',
        direction: 't',
        rotation: { latitude: 0, longitude: 0, revolution: 120 },
      },
    });
  });

  it.each([
    [
      'parser rejection',
      parseShape3D(supportedScene, supportedShape, '<a:effectLst><a:glow rad="1"/></a:effectLst>'),
      'parser-unsupported',
    ],
    ['line-like geometry', parseShape3D(supportedScene, supportedShape), 'line-like'],
  ])('keeps a flat fallback for %s', (label, shape3d, reason) => {
    const plan = buildStaticShape3DPlan(
      shape3d,
      {
        nodeType: 'shape',
        presetGeometry: label === 'line-like geometry' ? 'line' : 'roundRect',
        width: 200,
        height: 100,
        isLineLike: label === 'line-like geometry',
        paintKind: 'solid',
        baseFill: '#2F75B5',
      },
      createMockRenderContext(),
    );

    expect(plan).toMatchObject({ mode: 'flat', reason });
  });

  it.each([
    ['shape', 'ellipse'],
    ['picture', 'roundRect'],
  ] as const)('does not widen the %s geometry cohort to %s', (nodeType, presetGeometry) => {
    const plan = buildStaticShape3DPlan(
      parseShape3D(supportedScene, supportedShape),
      {
        nodeType,
        presetGeometry,
        width: 200,
        height: 100,
        paintKind: nodeType === 'shape' ? 'solid' : 'picture',
        baseFill: nodeType === 'shape' ? '#2F75B5' : undefined,
      },
      createMockRenderContext(),
    );

    expect(plan).toMatchObject({ mode: 'flat', reason: 'geometry-preset' });
  });

  it('rejects invalid render bounds instead of producing non-finite filter values', () => {
    const plan = buildStaticShape3DPlan(
      parseShape3D(supportedScene, supportedShape),
      {
        nodeType: 'shape',
        presetGeometry: 'rect',
        width: Number.NaN,
        height: 100,
        paintKind: 'solid',
        baseFill: '#2F75B5',
      },
      createMockRenderContext(),
    );

    expect(plan).toMatchObject({ mode: 'flat', reason: 'invalid-bounds' });
  });

  it('requires a resolved opaque solid color for the shape face material', () => {
    const plan = buildStaticShape3DPlan(
      parseShape3D(supportedScene, supportedShape),
      {
        nodeType: 'shape',
        presetGeometry: 'rect',
        width: 200,
        height: 100,
        paintKind: 'solid',
      },
      createMockRenderContext(),
    );

    expect(plan).toMatchObject({ mode: 'flat', reason: 'paint-kind' });
  });

  it('rejects a positive contour width without a resolvable contour color', () => {
    const plan = buildStaticShape3DPlan(
      parseShape3D(
        supportedScene,
        `<a:sp3d contourW="12700">
           <a:bevelT w="127000" h="127000" prst="circle"/>
         </a:sp3d>`,
      ),
      {
        nodeType: 'shape',
        presetGeometry: 'rect',
        width: 200,
        height: 100,
        paintKind: 'solid',
        baseFill: '#2F75B5',
      },
      createMockRenderContext(),
    );

    expect(plan).toMatchObject({ mode: 'flat', reason: 'contour-paint' });
  });
});

describe('appendStaticShape3DEffects', () => {
  it('adds bounded source-alpha lighting, a clipped bevel, and a separate contour', () => {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    const defs = document.createElementNS(ns, 'defs');
    const base = document.createElementNS(ns, 'path');
    const pathD = 'M0,0 L200,0 L200,100 L0,100 Z';
    base.setAttribute('d', pathD);
    svg.append(defs, base);
    const plan = buildStaticShape3DPlan(
      parseShape3D(supportedScene, supportedShape),
      {
        nodeType: 'shape',
        presetGeometry: 'rect',
        width: 200,
        height: 100,
        paintKind: 'solid',
        baseFill: '#2F75B5',
      },
      createMockRenderContext(),
    );

    const result = appendStaticShape3DEffects({
      svg,
      defs,
      pathD,
      bounds: { width: 200, height: 100 },
      plan,
    });

    expect(result).toBeTruthy();
    const filter = svg.querySelector('filter[data-pptx-shape3d-filter]');
    expect(filter).toBeTruthy();
    expect(filter?.getAttribute('filterUnits')).toBe('userSpaceOnUse');
    expect(filter?.getAttribute('color-interpolation-filters')).toBe('linearRGB');
    for (const name of ['x', 'y', 'width', 'height']) {
      expect(Number(filter?.getAttribute(name)), name).toSatisfy(Number.isFinite);
    }
    expect(filter?.querySelector('feGaussianBlur')?.getAttribute('in')).toBe('SourceAlpha');
    expect(filter?.querySelector('feDiffuseLighting feDistantLight')).toBeTruthy();
    expect(filter?.querySelector('feSpecularLighting feDistantLight')).toBeTruthy();

    const bevel = svg.querySelector('[data-pptx-shape3d-bevel]');
    expect(bevel?.getAttribute('clip-path')).toMatch(/^url\(#shape3d-clip-/);
    expect(bevel?.querySelector('path[filter]')?.getAttribute('d')).toBe(pathD);
    expect(bevel?.querySelector('path[filter]')?.getAttribute('filter')).toMatch(
      /^url\(#shape3d-filter-/,
    );

    const contour = svg.querySelector('path[data-pptx-shape3d-contour]');
    expect(contour?.getAttribute('fill')).toBe('none');
    expect(contour?.getAttribute('stroke')).toBe('#FFFFFF');
    expect(contour?.hasAttribute('filter')).toBe(false);
  });

  it('allocates unique local IDs and is a no-op for a flat plan', () => {
    const ns = 'http://www.w3.org/2000/svg';
    const makeSvg = () => {
      const svg = document.createElementNS(ns, 'svg');
      const defs = document.createElementNS(ns, 'defs');
      svg.appendChild(defs);
      return { svg, defs };
    };
    const supported = buildStaticShape3DPlan(
      parseShape3D(supportedScene, supportedShape),
      {
        nodeType: 'shape',
        presetGeometry: 'rect',
        width: 200,
        height: 100,
        paintKind: 'solid',
        baseFill: '#2F75B5',
      },
      createMockRenderContext(),
    );
    const first = makeSvg();
    const second = makeSvg();

    appendStaticShape3DEffects({
      ...first,
      pathD: 'M0,0 H200 V100 H0 Z',
      bounds: { width: 200, height: 100 },
      plan: supported,
    });
    appendStaticShape3DEffects({
      ...second,
      pathD: 'M0,0 H200 V100 H0 Z',
      bounds: { width: 200, height: 100 },
      plan: supported,
    });

    const ids = [first.svg, second.svg].flatMap((root) =>
      Array.from(root.querySelectorAll('[id]'), (el) => el.id),
    );
    expect(new Set(ids).size).toBe(ids.length);

    const flat = buildStaticShape3DPlan(
      undefined,
      {
        nodeType: 'shape',
        presetGeometry: 'rect',
        width: 200,
        height: 100,
        paintKind: 'solid',
        baseFill: '#2F75B5',
      },
      createMockRenderContext(),
    );
    const target = makeSvg();
    expect(
      appendStaticShape3DEffects({
        ...target,
        pathD: 'M0,0 H200 V100 H0 Z',
        bounds: { width: 200, height: 100 },
        plan: flat,
      }),
    ).toBeUndefined();
    expect(target.svg.querySelector('[data-pptx-shape3d-bevel]')).toBeNull();
  });
});
