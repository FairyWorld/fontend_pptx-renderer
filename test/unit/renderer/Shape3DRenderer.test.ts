import { afterEach, describe, expect, it, vi } from 'vitest';
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

const originalImageDecode = Object.getOwnPropertyDescriptor(
  HTMLImageElement.prototype,
  'decode',
);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  if (originalImageDecode) {
    Object.defineProperty(HTMLImageElement.prototype, 'decode', originalImageDecode);
  } else {
    delete (HTMLImageElement.prototype as Partial<HTMLImageElement>).decode;
  }
});

function installShape3DRasterMocks() {
  vi.stubGlobal(
    'Path2D',
    class MockPath2D {
      constructor(readonly path: string) {}
    },
  );

  const maskContext = {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    fill: vi.fn(),
    fillStyle: '',
    getImageData: vi.fn((_x: number, _y: number, width: number, height: number) => {
      const data = new Uint8ClampedArray(width * height * 4);
      for (let offset = 3; offset < data.length; offset += 4) data[offset] = 255;
      return { data, width, height } as ImageData;
    }),
  };
  const outputContext = {
    createImageData: vi.fn((width: number, height: number) => ({
      data: new Uint8ClampedArray(width * height * 4),
      width,
      height,
    })),
    putImageData: vi.fn(),
  };
  let contextCount = 0;
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => {
    contextCount += 1;
    return (contextCount === 1 ? maskContext : outputContext) as never;
  });
  let completeBlob: BlobCallback | undefined;
  const toBlob = vi
    .spyOn(HTMLCanvasElement.prototype, 'toBlob')
    .mockImplementation((callback) => {
      completeBlob = callback;
    });
  Object.defineProperty(HTMLImageElement.prototype, 'decode', {
    configurable: true,
    value: vi.fn().mockResolvedValue(undefined),
  });

  return {
    maskContext,
    outputContext,
    toBlob,
    complete(blob: Blob | null) {
      if (!completeBlob) throw new Error('toBlob callback was not registered');
      completeBlob(blob);
    },
  };
}

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
      geometry: 'roundrect',
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

  it('calibrates implicit two-point picture lighting to the native edge ordering', () => {
    const shape3d = parseShape3D(
      `<a:scene3d>
         <a:camera prst="orthographicFront"/>
         <a:lightRig rig="twoPt" dir="t"/>
       </a:scene3d>`,
      `<a:sp3d extrusionH="0"><a:bevelT w="127000" h="127000" prst="circle"/></a:sp3d>`,
    );
    const plan = buildStaticShape3DPlan(
      shape3d,
      { nodeType: 'picture', presetGeometry: 'rect', width: 704, height: 384 },
      createMockRenderContext(),
    );

    expect(plan).toMatchObject({
      mode: 'orthographic-top-bevel',
      surface: 'picture',
      light: {
        rig: 'twoPt',
        direction: 't',
        azimuth: 225,
        elevation: 60,
        intensity: 0.8,
      },
    });
  });

  it('accepts only bounded nonnegative source crops with a visible picture area', () => {
    const shape3d = parseShape3D(
      `<a:scene3d>
         <a:camera prst="orthographicFront"/>
         <a:lightRig rig="twoPt" dir="t"/>
       </a:scene3d>`,
      `<a:sp3d extrusionH="0"><a:bevelT w="127000" h="127000" prst="circle"/></a:sp3d>`,
    );
    const target = {
      nodeType: 'picture' as const,
      presetGeometry: 'rect',
      width: 200,
      height: 100,
    };
    const ctx = createMockRenderContext();

    expect(
      buildStaticShape3DPlan(
        shape3d,
        {
          ...target,
          sourceCrop: { left: 0.22, top: 0.18, right: 0.08, bottom: 0.12 },
        },
        ctx,
      ),
    ).toMatchObject({ mode: 'orthographic-top-bevel', surface: 'picture' });
    for (const sourceCrop of [
      { left: -0.1, top: 0, right: 0, bottom: 0 },
      { left: 0.6, top: 0, right: 0.5, bottom: 0 },
      { left: 0, top: 0.999, right: 0, bottom: 0 },
    ]) {
      expect(buildStaticShape3DPlan(shape3d, { ...target, sourceCrop }, ctx)).toEqual({
        mode: 'flat',
        reason: 'picture-source-crop',
      });
    }
  });

  it.each([
    [
      'conflicting effect',
      parseShape3D(supportedScene, supportedShape, '<a:effectLst><a:glow rad="1"/></a:effectLst>'),
      'effect-list-conflict',
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
    [
      'camera-preset',
      `<a:scene3d><a:camera prst="perspectiveRelaxed"/><a:lightRig rig="threePt" dir="t"/></a:scene3d>`,
      supportedShape,
    ],
    [
      'camera-rotation',
      `<a:scene3d><a:camera prst="orthographicFront"><a:rot lat="0" lon="0" rev="60000"/></a:camera><a:lightRig rig="threePt" dir="t"/></a:scene3d>`,
      supportedShape,
    ],
    [
      'extrusion-height',
      supportedScene,
      supportedShape.replace('<a:sp3d ', '<a:sp3d extrusionH="12700" '),
    ],
    [
      'bottom-bevel',
      supportedScene,
      supportedShape.replace('</a:sp3d>', '<a:bevelB w="12700" h="12700"/></a:sp3d>'),
    ],
    [
      'preset-material',
      supportedScene,
      supportedShape.replace('<a:sp3d ', '<a:sp3d prstMaterial="metal" '),
    ],
  ])('classifies %s in the render planner', (reason, sceneXml, shapeXml) => {
    const plan = buildStaticShape3DPlan(
      parseShape3D(sceneXml, shapeXml),
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
  it('keeps vector faces until the contour-aware texture is ready, then swaps only the lighting', async () => {
    const mocks = installShape3DRasterMocks();
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    const defs = document.createElementNS(ns, 'defs');
    svg.appendChild(defs);
    const ctx = createMockRenderContext({ asyncTasks: [] });
    const plan = buildStaticShape3DPlan(
      parseShape3D(supportedScene, supportedShape),
      {
        nodeType: 'shape',
        presetGeometry: 'roundRect',
        width: 200,
        height: 100,
        paintKind: 'solid',
        baseFill: '#2F75B5',
      },
      ctx,
    );

    const result = appendStaticShape3DEffects({
      svg,
      defs,
      pathD: 'M0,20 Q0,0 20,0 H180 Q200,0 200,20 V80 Q200,100 180,100 H20 Q0,100 0,80 Z',
      bounds: { width: 200, height: 100 },
      plan,
      ctx,
    });

    expect(result?.group.querySelectorAll('[data-pptx-shape3d-face]')).toHaveLength(4);
    expect(result?.group.querySelector('[data-pptx-shape3d-lighting]')).toBeNull();
    expect(ctx.asyncTasks).toHaveLength(1);
    mocks.complete(new Blob([new Uint8Array([1, 2, 3])], { type: 'image/png' }));
    await Promise.all(ctx.asyncTasks!);

    expect(result?.group.querySelectorAll('[data-pptx-shape3d-face]')).toHaveLength(0);
    const lighting = result?.group.querySelector('[data-pptx-shape3d-lighting]');
    expect(lighting?.getAttribute('data-pptx-shape3d-lighting')).toBe('distance-field');
    expect(lighting?.getAttribute('width')).toBe('200');
    expect(lighting?.getAttribute('height')).toBe('100');
    expect(ctx.mediaUrlCache.size).toBe(1);
    expect(mocks.maskContext.fill).toHaveBeenCalledWith(expect.anything(), 'evenodd');
    expect(mocks.outputContext.putImageData).toHaveBeenCalledOnce();
  });

  it('keeps the vector fallback and blocks late DOM writes when the slide is aborted', async () => {
    const mocks = installShape3DRasterMocks();
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    const defs = document.createElementNS(ns, 'defs');
    svg.appendChild(defs);
    const abortController = new AbortController();
    const ctx = createMockRenderContext({ asyncTasks: [], signal: abortController.signal });
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
      ctx,
    );
    const result = appendStaticShape3DEffects({
      svg,
      defs,
      pathD: 'M0,0 H200 V100 H0 Z',
      bounds: { width: 200, height: 100 },
      plan,
      ctx,
    });

    abortController.abort();
    mocks.complete(new Blob([new Uint8Array([1])], { type: 'image/png' }));
    await Promise.all(ctx.asyncTasks!);

    expect(result?.group.querySelectorAll('[data-pptx-shape3d-face]')).toHaveLength(4);
    expect(result?.group.querySelector('[data-pptx-shape3d-lighting]')).toBeNull();
    expect(ctx.mediaUrlCache.size).toBe(0);
  });

  it('reuses a completed texture through the render-context media cache', async () => {
    const mocks = installShape3DRasterMocks();
    const ns = 'http://www.w3.org/2000/svg';
    const makeSvg = () => {
      const svg = document.createElementNS(ns, 'svg');
      const defs = document.createElementNS(ns, 'defs');
      svg.appendChild(defs);
      return { svg, defs };
    };
    const ctx = createMockRenderContext({ asyncTasks: [] });
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
      ctx,
    );
    const first = makeSvg();
    appendStaticShape3DEffects({
      ...first,
      pathD: 'M0,0 H200 V100 H0 Z',
      bounds: { width: 200, height: 100 },
      plan,
      ctx,
    });
    mocks.complete(new Blob([new Uint8Array([1])], { type: 'image/png' }));
    await Promise.all(ctx.asyncTasks!);

    const firstHref = first.svg
      .querySelector('[data-pptx-shape3d-lighting]')
      ?.getAttribute('href');
    const second = makeSvg();
    appendStaticShape3DEffects({
      ...second,
      pathD: 'M0,0 H200 V100 H0 Z',
      bounds: { width: 200, height: 100 },
      plan,
      ctx,
    });
    await Promise.all(ctx.asyncTasks!);

    expect(second.svg.querySelector('[data-pptx-shape3d-lighting]')?.getAttribute('href')).toBe(
      firstHref,
    );
    expect(mocks.toBlob).toHaveBeenCalledOnce();
  });

  it('resolves a missing Canvas backend without removing the vector fallback', async () => {
    vi.stubGlobal('Path2D', class MockPath2D {});
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    const defs = document.createElementNS(ns, 'defs');
    svg.appendChild(defs);
    const ctx = createMockRenderContext({ asyncTasks: [] });
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
      ctx,
    );
    const result = appendStaticShape3DEffects({
      svg,
      defs,
      pathD: 'M0,0 H200 V100 H0 Z',
      bounds: { width: 200, height: 100 },
      plan,
      ctx,
    });
    await Promise.all(ctx.asyncTasks!);

    expect(result?.group.querySelectorAll('[data-pptx-shape3d-face]')).toHaveLength(4);
    expect(result?.group.querySelector('[data-pptx-shape3d-lighting]')).toBeNull();
  });

  it('partitions the inward bevel into independently lit faces and a separate contour', () => {
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
    const bevel = svg.querySelector('[data-pptx-shape3d-bevel]');
    expect(bevel?.getAttribute('clip-path')).toMatch(/^url\(#shape3d-clip-/);
    expect(
      Array.from(bevel?.querySelectorAll('path[data-pptx-shape3d-face]') ?? [], (path) =>
        path.getAttribute('data-pptx-shape3d-face'),
      ),
    ).toEqual(['top', 'right', 'bottom', 'left']);
    expect(bevel?.querySelectorAll('path[data-pptx-shape3d-face][filter]')).toHaveLength(0);
    expect(
      Array.from(bevel?.querySelectorAll('path[data-pptx-shape3d-face]') ?? []).every(
        (path) => path.getAttribute('d') === pathD,
      ),
    ).toBe(true);
    expect(svg.querySelectorAll('linearGradient[data-pptx-shape3d-face-gradient]')).toHaveLength(4);

    const contour = svg.querySelector('path[data-pptx-shape3d-contour]');
    expect(contour?.getAttribute('fill')).toBe('none');
    expect(contour?.getAttribute('stroke')).toBe('#FFFFFF');
    expect(contour?.hasAttribute('filter')).toBe(false);
  });

  it('uses bevel width for the inward extent and height only for lighting contrast', () => {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    const defs = document.createElementNS(ns, 'defs');
    svg.appendChild(defs);
    const plan = buildStaticShape3DPlan(
      parseShape3D(supportedScene, supportedShape.replace('h="127000"', 'h="254000"')),
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

    appendStaticShape3DEffects({
      svg,
      defs,
      pathD: 'M0,0 H200 V100 H0 Z',
      bounds: { width: 200, height: 100 },
      plan,
    });

    for (const face of svg.querySelectorAll('path[data-pptx-shape3d-face]')) {
      expect(Number(face.getAttribute('stroke-width'))).toBeCloseTo(26.6667, 3);
    }
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
