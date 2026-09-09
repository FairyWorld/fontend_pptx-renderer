import { expect, test } from '@playwright/test';

// Set PLAYWRIGHT_CHANNEL=chrome on machines with Chrome but no downloaded Chromium.
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });

test('browser accepts deterministic OOXML runtime geometry and bounded donut adjustments', async ({
  page,
}) => {
  await page.goto('/test/browser/blank.html');
  const { results, multiPathResults, donutResults, groupedDonut, pictureClipD } =
    await page.evaluate(async () => {
      const { getPresetShapePath } = await import('/src/shapes/presets.ts');
      const { parseXml } = await import('/src/parser/XmlParser.ts');
      const { parseShapeNode } = await import('/src/model/nodes/ShapeNode.ts');
      const { parsePicNode } = await import('/src/model/nodes/PicNode.ts');
      const { parseGroupNode } = await import('/src/model/nodes/GroupNode.ts');
      const { renderShape } = await import('/src/renderer/ShapeRenderer.ts');
      const { renderImage } = await import('/src/renderer/ImageRenderer.ts');
      const { renderGroup } = await import('/src/renderer/GroupRenderer.ts');
      const { createMockRenderContext } = await import('/test/unit/helpers/mockContext.ts');
      const { ooxmlPresetRuntimeMultiPathShapeNames, ooxmlPresetRuntimeShapeNames } =
        await import('/src/shapes/ooxmlGeometryRuntime.ts');
      const results = ooxmlPresetRuntimeShapeNames.map((name) => {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const d = getPresetShapePath(name, 400, 280);
        svg.setAttribute('viewBox', '0 0 400 280');
        path.setAttribute('d', d);
        svg.append(path);
        document.body.append(svg);
        const box = path.getBBox();
        return { name, d, x: box.x, y: box.y, width: box.width, height: box.height };
      });
      const multiPathResults = ooxmlPresetRuntimeMultiPathShapeNames.map((name) => {
        const xml = `<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
        <p:nvSpPr><p:cNvPr id="1" name="Flowchart"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="3810000" cy="2667000"/></a:xfrm>
          <a:prstGeom prst="${name}"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="4472C4"/></a:solidFill>
          <a:ln w="12700"><a:solidFill><a:srgbClr val="203864"/></a:solidFill></a:ln>
        </p:spPr>
      </p:sp>`;
        const rendered = renderShape(parseShapeNode(parseXml(xml)), createMockRenderContext());
        document.body.append(rendered);
        return {
          name,
          paths: Array.from(rendered.querySelectorAll('svg > path')).map((path) => ({
            d: path.getAttribute('d'),
            fill: path.getAttribute('fill'),
            stroke: path.getAttribute('stroke'),
          })),
        };
      });
      const donutResults = [0, 10000, 25000, 50000].map((adjustment) => {
        const xml = `<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
        <p:nvSpPr><p:cNvPr id="18" name="Donut"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="3810000" cy="1714500"/></a:xfrm>
          <a:prstGeom prst="donut"><a:avLst><a:gd name="adj" fmla="val ${adjustment}"/></a:avLst></a:prstGeom>
          <a:solidFill><a:srgbClr val="4472C4"/></a:solidFill>
        </p:spPr>
      </p:sp>`;
        const rendered = renderShape(parseShapeNode(parseXml(xml)), createMockRenderContext());
        document.body.append(rendered);
        const path = rendered.querySelector('svg > path')!;
        const box = path.getBBox();
        return {
          adjustment,
          d: path.getAttribute('d') ?? '',
          box: { x: box.x, y: box.y, width: box.width, height: box.height },
        };
      });

      const groupXml = `<p:grpSp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
        xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:nvGrpSpPr><p:cNvPr id="40" name="Donut group"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1905000" cy="1905000"/><a:chOff x="0" y="0"/><a:chExt cx="3810000" cy="952500"/></a:xfrm></p:grpSpPr>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="18" name="Grouped donut"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1905000" cy="952500"/></a:xfrm><a:prstGeom prst="donut"><a:avLst><a:gd name="adj" fmla="val 10000"/></a:avLst></a:prstGeom><a:solidFill><a:srgbClr val="4472C4"/></a:solidFill></p:spPr>
      </p:sp>
    </p:grpSp>`;
      const group = renderGroup(
        parseGroupNode(parseXml(groupXml)),
        createMockRenderContext(),
        (node, context) => renderShape(node as Parameters<typeof renderShape>[0], context),
      );
      document.body.append(group);
      const groupedShape = group.firstElementChild as HTMLElement;
      const groupedDonut = {
        width: groupedShape.getBoundingClientRect().width,
        height: groupedShape.getBoundingClientRect().height,
        d: groupedShape.querySelector('svg > path')?.getAttribute('d') ?? '',
      };

      const pictureXml = `<p:pic xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
        xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
        xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <p:nvPicPr><p:cNvPr id="19" name="Donut picture"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
      <p:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
      <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1905000" cy="952500"/></a:xfrm><a:prstGeom prst="donut"><a:avLst><a:gd name="adj" fmla="val 10000"/></a:avLst></a:prstGeom></p:spPr>
    </p:pic>`;
      const pictureContext = createMockRenderContext();
      pictureContext.slide.rels.set('rId1', { type: 'image', target: 'ppt/media/image1.png' });
      pictureContext.presentation.media.set(
        'ppt/media/image1.png',
        new Uint8Array([0x89, 0x50, 0x4e, 0x47]),
      );
      const picture = renderImage(parsePicNode(parseXml(pictureXml)), pictureContext);
      document.body.append(picture);
      const pictureClipD = picture.querySelector('clipPath path')?.getAttribute('d') ?? '';

      return { results, multiPathResults, donutResults, groupedDonut, pictureClipD };
    });

  expect(results).toHaveLength(29);
  for (const result of results) {
    expect(result.d, result.name).not.toMatch(/NaN|Infinity/);
    expect(result.width, result.name).toBeGreaterThan(0);
    expect(result.height, result.name).toBeGreaterThan(0);
    expect([result.x, result.y, result.width, result.height].every(Number.isFinite)).toBe(true);
  }
  expect(results.find(({ name }) => name === 'flowChartTerminator')?.d).toBe(
    'M64.351852,0 L335.648148,0 A64.351852,140 0 0,1 335.648148,280 L64.351852,280 A64.351852,140 0 0,1 64.351852,0 Z',
  );
  expect(multiPathResults).toHaveLength(8);
  for (const result of multiPathResults) {
    expect(result.paths, result.name).toHaveLength(3);
    expect(result.paths.map(({ fill }) => fill)).toEqual(['#4472C4', 'none', 'none']);
    expect(result.paths[0].stroke).toBe('none');
    expect(result.paths[1].stroke).toBe('#203864');
    expect(result.paths[2].stroke).toBe(
      result.name === 'flowChartMultidocument' ? 'none' : '#203864',
    );
    expect(result.paths.every(({ d }) => !!d && !/NaN|Infinity/.test(d))).toBe(true);
  }
  for (const result of donutResults) {
    expect(result.d.match(/M/g), `donut adj=${result.adjustment}`).toHaveLength(2);
    expect(result.d, `donut adj=${result.adjustment}`).not.toMatch(/NaN|Infinity/);
    expect(result.box).toEqual({ x: 0, y: 0, width: 400, height: 180 });
  }
  expect(groupedDonut).toMatchObject({ width: 100, height: 200 });
  expect(groupedDonut.d).toContain('M10,100 A40,90');
  expect(pictureClipD).toContain('M10,50 A90,40');
});

test('bounded static DrawingML 3D stays stable across shapes, pictures, groups, and disposal', async ({
  page,
}) => {
  await page.goto('/test/browser/blank.html');
  const result = await page.evaluate(async () => {
    const { parseXml } = await import('/src/parser/XmlParser.ts');
    const { parseShapeNode } = await import('/src/model/nodes/ShapeNode.ts');
    const { parsePicNode } = await import('/src/model/nodes/PicNode.ts');
    const { parseGroupNode } = await import('/src/model/nodes/GroupNode.ts');
    const { renderShape } = await import('/src/renderer/ShapeRenderer.ts');
    const { renderGroup } = await import('/src/renderer/GroupRenderer.ts');
    const { renderSlide } = await import('/src/renderer/SlideRenderer.ts');
    const { createMockRenderContext } = await import('/test/unit/helpers/mockContext.ts');

    const scene =
      '<a:scene3d><a:camera prst="orthographicFront"/><a:lightRig rig="threePt" dir="t"/></a:scene3d>';
    const bevel = '<a:sp3d><a:bevelT w="127000" h="127000" prst="circle"/></a:sp3d>';
    const shapeXml = (preset: string, width: number, height: number, color: string) => `
      <p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
        <p:nvSpPr><p:cNvPr id="1" name="3D ${preset}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="${width * 9525}" cy="${height * 9525}"/></a:xfrm>
          <a:prstGeom prst="${preset}"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="${color}"/></a:solidFill>${scene}${bevel}
        </p:spPr>
      </p:sp>`;

    document.body.style.margin = '0';
    const host = document.createElement('div');
    host.id = 'shape3d-browser-host';
    Object.assign(host.style, {
      display: 'flex',
      flexWrap: 'wrap',
      gap: '20px',
      width: '900px',
      padding: '20px',
      overflow: 'auto',
      background: 'white',
    });
    document.body.append(host);
    const ctx = createMockRenderContext();
    for (const spec of [
      ['rect', 260, 80, '2F75B5'],
      ['rect', 80, 220, '2F75B5'],
      ['roundRect', 220, 100, '2F75B5'],
      ['rect', 240, 100, '70AD47'],
    ] as const) {
      const shape = renderShape(
        parseShapeNode(parseXml(shapeXml(...spec))),
        createMockRenderContext(),
      );
      shape.style.position = 'relative';
      shape.style.left = '0';
      shape.style.top = '0';
      host.append(shape);
    }

    const flat = renderShape(
      parseShapeNode(
        parseXml(
          shapeXml('ellipse', 120, 80, '2F75B5').replace('orthographicFront', 'perspectiveFront'),
        ),
      ),
      createMockRenderContext(),
    );
    flat.style.position = 'relative';
    flat.style.left = '0';
    flat.style.top = '0';
    host.append(flat);

    const groupXml = `
      <p:grpSp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
               xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
        <p:nvGrpSpPr><p:cNvPr id="20" name="3D group"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
        <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1905000" cy="952500"/><a:chOff x="0" y="0"/><a:chExt cx="3810000" cy="1905000"/></a:xfrm></p:grpSpPr>
        ${shapeXml('rect', 200, 100, '70AD47')}
      </p:grpSp>`;
    const group = renderGroup(
      parseGroupNode(parseXml(groupXml)),
      createMockRenderContext(),
      (node, context) => renderShape(node as Parameters<typeof renderShape>[0], context),
    );
    group.style.position = 'relative';
    group.style.left = '0';
    group.style.top = '0';
    host.append(group);

    const png = Uint8Array.from(
      atob(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z2S8AAAAASUVORK5CYII=',
      ),
      (char) => char.charCodeAt(0),
    );
    const pictureXml = `
      <p:pic xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        <p:nvPicPr><p:cNvPr id="30" name="3D picture"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
        <p:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="1905000" cy="952500"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>${scene}${bevel}
        </p:spPr>
      </p:pic>`;
    ctx.slide.rels.set('rId1', { type: 'image', target: 'ppt/media/image1.png' });
    ctx.presentation.media.set('ppt/media/image1.png', png);
    ctx.slide.nodes = [parsePicNode(parseXml(pictureXml))];
    const revoked: string[] = [];
    const originalRevoke = URL.revokeObjectURL.bind(URL);
    URL.revokeObjectURL = (url: string) => {
      revoked.push(url);
      originalRevoke(url);
    };
    const handle = renderSlide(ctx.presentation, ctx.slide);
    handle.element.style.position = 'absolute';
    handle.element.style.left = '-2000px';
    document.body.append(handle.element);
    await handle.ready;
    const disposableHadBevel = !!handle.element.querySelector('[data-pptx-shape3d-bevel]');
    handle.dispose();
    URL.revokeObjectURL = originalRevoke;
    handle.element.remove();

    await document.fonts.ready;
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
    const ids = Array.from(host.querySelectorAll('[id]'), (element) => element.id);
    const groupChild = group.firstElementChild as HTMLElement;
    return {
      bevelCount: host.querySelectorAll('[data-pptx-shape3d-bevel]').length,
      flatHasBevel: !!flat.querySelector('[data-pptx-shape3d-bevel]'),
      uniqueIds: new Set(ids).size === ids.length,
      noHorizontalGrowth: host.scrollWidth === host.clientWidth,
      groupBounds: {
        width: group.getBoundingClientRect().width,
        height: group.getBoundingClientRect().height,
        childWidth: groupChild.getBoundingClientRect().width,
        childHeight: groupChild.getBoundingClientRect().height,
      },
      disposableHadBevel,
      revokedCount: revoked.length,
    };
  });

  expect(result).toEqual(
    expect.objectContaining({
      bevelCount: 5,
      flatHasBevel: false,
      uniqueIds: true,
      noHorizontalGrowth: true,
      disposableHadBevel: true,
      revokedCount: 1,
    }),
  );
  expect(result.groupBounds).toEqual({ width: 200, height: 100, childWidth: 100, childHeight: 50 });

  const host = page.locator('#shape3d-browser-host');
  const first = await host.screenshot();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
  );
  const second = await host.screenshot();
  expect(first.equals(second)).toBe(true);
});

for (const hostWhiteSpace of ['normal', 'pre', 'nowrap']) {
  for (const wrap of ['square', 'none']) {
    test(`text wrap=${wrap} inside white-space:${hostWhiteSpace}`, async ({ page }) => {
      await page.goto('/test/browser/blank.html');
      const result = await page.evaluate(
        async ({ hostWhiteSpace, wrap }) => {
          const { renderTextFixture } = await import('/test/fixtures/text-coverage.ts');
          document.body.style.whiteSpace = hostWhiteSpace;
          const { element, span, para, container } = renderTextFixture(
            `<bodyPr wrap="${wrap}" lIns="0" tIns="0" rIns="0" bIns="0"><noAutofit/></bodyPr>`,
          );
          document.body.append(element);
          await document.fonts.ready;
          const range = document.createRange();
          range.selectNodeContents(span);
          return {
            whiteSpace: getComputedStyle(container).whiteSpace,
            lineCount: range.getClientRects().length,
            width: element.getBoundingClientRect().width,
            paragraphWidth: para.getBoundingClientRect().width,
            scale: container.style.transform,
            fontSize: getComputedStyle(span).fontSize,
          };
        },
        { hostWhiteSpace, wrap },
      );
      expect(result.whiteSpace).toBe(wrap === 'none' ? 'nowrap' : 'normal');
      expect(result.fontSize).toBe('32px');
      expect(result.scale).toBe('');
      expect(result.paragraphWidth).toBeLessThanOrEqual(result.width);
      if (wrap === 'none') expect(result.lineCount).toBe(1);
      else expect(result.lineCount).toBeGreaterThan(1);
    });
  }
}

test('spAutoFit grows a wrapped CJK text box without shrinking glyphs or reflowing siblings', async ({
  page,
}) => {
  await page.goto('/test/browser/blank.html');
  const result = await page.evaluate(async () => {
    const { renderTextFixture } = await import('/test/fixtures/text-coverage.ts');
    const { element, span, container } = renderTextFixture(
      '<bodyPr wrap="square" lIns="109728" rIns="109728" tIns="73152" bIns="73152"><spAutoFit/></bodyPr>',
      '',
      '',
      '',
      '<a:r><a:rPr sz="3000"><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:rPr><a:t>Alpha 坚守问题导向，持续提升复杂演示文稿的渲染质量与一致性。</a:t></a:r>',
    );
    const parent = document.createElement('div');
    Object.assign(parent.style, {
      position: 'relative',
      width: '500px',
      height: '300px',
    });
    const sibling = document.createElement('div');
    Object.assign(sibling.style, {
      position: 'absolute',
      left: '0',
      top: '140px',
      width: '20px',
      height: '20px',
    });
    parent.append(element, sibling);
    document.body.append(parent);
    await document.fonts.ready;
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
    const range = document.createRange();
    range.selectNodeContents(span);
    return {
      fontSize: getComputedStyle(span).fontSize,
      lineCount: range.getClientRects().length,
      transform: container.style.transform,
      overflowY: getComputedStyle(container).overflowY,
      shapeHeight: element.getBoundingClientRect().height,
      textHeight: container.getBoundingClientRect().height,
      parentHeight: parent.getBoundingClientRect().height,
      siblingTop: sibling.offsetTop,
    };
  });

  expect(result.fontSize).toBe('40px');
  expect(result.lineCount).toBeGreaterThan(2);
  expect(result.transform).toBe('');
  expect(result.overflowY).toBe('visible');
  expect(result.shapeHeight).toBeGreaterThan(80);
  expect(result.textHeight).toBeCloseTo(result.shapeHeight, 1);
  expect(result.parentHeight).toBe(300);
  expect(result.siblingTop).toBe(140);
});

test('spAutoFit grows a compact wide text box when its run preserves an explicit font size', async ({
  page,
}) => {
  await page.goto('/test/browser/blank.html');
  const result = await page.evaluate(async () => {
    const { renderTextFixture } = await import('/test/fixtures/text-coverage.ts');
    const { element, span, container } = renderTextFixture(
      '<bodyPr wrap="square"><spAutoFit/></bodyPr>',
      '',
      '',
      '',
      '<a:r><a:rPr sz="3000"><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:rPr><a:t>Alpha 坚守问题导向，持续提升复杂演示文稿的渲染质量与一致性。</a:t></a:r>',
      undefined,
      { cx: 7680960, cy: 411480 },
    );
    const centered = renderTextFixture(
      '<bodyPr wrap="square" anchor="ctr"><spAutoFit/></bodyPr>',
      '',
      '',
      '',
      '<a:r><a:rPr sz="3000"><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:rPr><a:t>Alpha 坚守问题导向，持续提升复杂演示文稿的渲染质量与一致性。</a:t></a:r>',
      undefined,
      { cx: 7680960, cy: 411480 },
    );
    document.body.append(element, centered.element);
    await document.fonts.ready;
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
    const range = document.createRange();
    range.selectNodeContents(span);
    return {
      fontSize: getComputedStyle(span).fontSize,
      lineCount: range.getClientRects().length,
      transform: container.style.transform,
      overflowY: getComputedStyle(container).overflowY,
      shapeWidth: element.getBoundingClientRect().width,
      shapeHeight: element.getBoundingClientRect().height,
      centeredTransform: centered.container.style.transform,
      centeredShapeHeight: centered.element.getBoundingClientRect().height,
    };
  });

  expect(result.fontSize).toBe('40px');
  expect(result.lineCount).toBeGreaterThan(1);
  expect(result.transform).toBe('');
  expect(result.overflowY).toBe('visible');
  expect(result.shapeWidth).toBeCloseTo(806.4, 1);
  expect(result.shapeHeight).toBeGreaterThan(43.2);
  expect(result.centeredTransform).toContain('scale(');
  expect(result.centeredShapeHeight).toBeCloseTo(43.2, 1);
});

for (const [x, y] of [
  ['clip', 'clip'],
  ['clip', 'overflow'],
  ['overflow', 'clip'],
  ['overflow', 'overflow'],
]) {
  test(`noAutofit clip hit-testing and parent geometry ${x}/${y}`, async ({ page }) => {
    await page.goto('/test/browser/blank.html');
    const result = await page.evaluate(
      async ({ x, y }) => {
        const { renderTextFixture } = await import('/test/fixtures/text-coverage.ts');
        const { element, container } = renderTextFixture(
          `<bodyPr wrap="none" horzOverflow="${x}" vertOverflow="${y}" lIns="0" tIns="0" rIns="0" bIns="0"><noAutofit/></bodyPr>`,
          '',
          '',
          '',
          '<a:r><a:rPr sz="2400"/><a:t>Alpha beta gamma delta epsilon</a:t></a:r><a:br/><a:r><a:rPr sz="2400"/><a:t>Second</a:t></a:r><a:br/><a:r><a:rPr sz="2400"/><a:t>Third</a:t></a:r><a:br/><a:r><a:rPr sz="2400"/><a:t>Fourth</a:t></a:r>',
        );
        const parent = document.createElement('div');
        Object.assign(parent.style, {
          position: 'relative',
          width: '500px',
          height: '300px',
          margin: '40px',
          whiteSpace: 'pre',
        });
        parent.append(element);
        document.body.append(parent);
        await document.fonts.ready;
        const rect = container.getBoundingClientRect();
        const hit = (px: number, py: number) =>
          container.contains(document.elementFromPoint(px, py));
        return {
          overflowX: getComputedStyle(container).overflowX,
          overflowY: getComputedStyle(container).overflowY,
          horizontalHit: hit(rect.right + 15, rect.top + 15),
          verticalHit: hit(rect.left + 15, rect.bottom + 25),
          shapeHeight: element.getBoundingClientRect().height,
          parentWidth: parent.getBoundingClientRect().width,
        };
      },
      { x, y },
    );
    expect(result.overflowX).toBe(x === 'clip' ? 'clip' : 'visible');
    expect(result.overflowY).toBe(y === 'clip' ? 'clip' : 'visible');
    expect(result.horizontalHit).toBe(x === 'overflow');
    expect(result.verticalHit).toBe(y === 'overflow');
    expect(result.shapeHeight).toBe(80);
    expect(result.parentWidth).toBe(500);
  });
}

for (const [own, inherited, expectedSize] of [
  ['<noAutofit/>', '<normAutofit fontScale="50000"/>', '32px'],
  ['<normAutofit fontScale="50%"/>', '<noAutofit/>', '16px'],
  ['<spAutoFit/>', '<normAutofit fontScale="50000"/>', '32px'],
  ['', '<normAutofit fontScale="50000"/>', '16px'],
]) {
  test(`autofit choice ${own || 'inherited'} supersedes ${inherited}`, async ({ page }) => {
    await page.goto('/test/browser/blank.html');
    const result = await page.evaluate(
      async ({ own, inherited }) => {
        const { renderTextFixture } = await import('/test/fixtures/text-coverage.ts');
        const { element, span, container } = renderTextFixture(
          `<bodyPr wrap="square" horzOverflow="overflow" vertOverflow="overflow" lIns="0" tIns="0" rIns="0" bIns="0">${own}</bodyPr>`,
          '',
          '',
          '',
          '<a:r><a:rPr sz="2400"/><a:t>Alpha</a:t></a:r>',
          `<bodyPr>${inherited}</bodyPr>`,
        );
        document.body.append(element);
        await document.fonts.ready;
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        );
        return {
          fontSize: getComputedStyle(span).fontSize,
          width: element.getBoundingClientRect().width,
          transform: container.style.transform,
        };
      },
      { own, inherited },
    );
    expect(result.fontSize).toBe(expectedSize);
    expect(result.width).toBe(160);
    expect(result.transform).toBe('');
  });
}

test('vertical text, adjacent runs, bullets and multiple paragraphs preserve container bounds', async ({
  page,
}) => {
  await page.goto('/test/browser/blank.html');
  const result = await page.evaluate(async () => {
    const { renderTextFixture } = await import('/test/fixtures/text-coverage.ts');
    const { element, node, ctx } = renderTextFixture(
      '<bodyPr vert="eaVert" wrap="square" lIns="0" tIns="0" rIns="0" bIns="0"><noAutofit/></bodyPr>',
      '<buAutoNum type="arabicPeriod"/>',
      '<lvl1pPr><buChar char="•"/></lvl1pPr>',
      '',
      '<a:r><a:rPr sz="1200"/><a:t>Alpha</a:t></a:r><a:r><a:rPr sz="1200"/><a:t>乙</a:t></a:r>',
    );
    node.textBody!.paragraphs.push({ ...node.textBody!.paragraphs[0], runs: [{ text: 'Second' }] });
    const { renderShape } = await import('/src/renderer/ShapeRenderer.ts');
    const rendered = renderShape(node, ctx);
    element.remove();
    document.body.style.whiteSpace = 'pre';
    document.body.append(rendered);
    await document.fonts.ready;
    const span = [...rendered.querySelectorAll('span')].find((s) => s.textContent === 'Alpha')!;
    const container = span.closest('div')!.parentElement!;
    return {
      text: rendered.textContent,
      writingMode: getComputedStyle(container).writingMode,
      width: rendered.getBoundingClientRect().width,
      whiteSpace: getComputedStyle(container).whiteSpace,
    };
  });
  expect(result.text).toContain('1.');
  expect(result.text).toContain('2.');
  expect(result.text).not.toContain('•');
  expect(result.writingMode).toBe('vertical-rl');
  expect(result.whiteSpace).toBe('normal');
  expect(result.width).toBe(160);
});

test('near-fit square-wrapped heading stays on one line with bounded scale', async ({ page }) => {
  await page.goto('/test/browser/blank.html');
  const result = await page.evaluate(async () => {
    const { parseXml } = await import('/src/parser/XmlParser.ts');
    const { parseShapeNode } = await import('/src/model/nodes/ShapeNode.ts');
    const { renderShape } = await import('/src/renderer/ShapeRenderer.ts');
    const { createMockRenderContext } = await import('/test/unit/helpers/mockContext.ts');
    const text = '发扬遵义会议精神自觉做到 “两个维护”';
    const shapeXml = (wrap: string, noAutofit: boolean) => `
      <p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
        <p:nvSpPr><p:cNvPr id="248" name="Near-fit heading"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="28575000" cy="1905000"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/>
        </p:spPr>
        <p:txBody>
          <a:bodyPr wrap="${wrap}" lIns="0" tIns="0" rIns="0" bIns="0">${noAutofit ? '<a:noAutofit/>' : ''}</a:bodyPr>
          <a:lstStyle/>
          <a:p>
            <a:r><a:rPr sz="5400" b="1" spc="50"><a:latin typeface="Arial"/><a:ea typeface="Arial"/></a:rPr><a:t>发扬遵义会议精神自觉做到</a:t></a:r>
            <a:r><a:rPr sz="5400" spc="-1380"><a:latin typeface="Arial"/><a:ea typeface="Arial"/></a:rPr><a:t xml:space="preserve"> </a:t></a:r>
            <a:r><a:rPr sz="5400" b="1" spc="50"><a:latin typeface="Arial"/><a:ea typeface="Arial"/></a:rPr><a:t>“两个维护”</a:t></a:r>
          </a:p>
        </p:txBody>
      </p:sp>`;
    const findContainer = (element: HTMLElement) =>
      Array.from(element.querySelectorAll('div')).find(
        (candidate) => candidate.textContent === text && candidate.style.flexDirection === 'column',
      ) as HTMLElement;

    const referenceNode = parseShapeNode(parseXml(shapeXml('none', true)));
    const reference = renderShape(referenceNode, createMockRenderContext());
    document.body.append(reference);
    await document.fonts.ready;
    const referenceContainer = findContainer(reference);
    const range = document.createRange();
    const referenceSpans = referenceContainer.querySelectorAll('span');
    range.setStart(referenceSpans[0].firstChild!, 0);
    range.setEnd(
      referenceSpans[referenceSpans.length - 1].firstChild!,
      referenceSpans[referenceSpans.length - 1].textContent!.length,
    );
    const naturalRect = range.getBoundingClientRect();
    reference.remove();

    const targetNode = parseShapeNode(parseXml(shapeXml('square', false)));
    targetNode.size.w = naturalRect.width - 24;
    targetNode.size.h = naturalRect.height + 4;
    const target = renderShape(targetNode, createMockRenderContext());
    document.body.append(target);
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
    const targetContainer = findContainer(target);
    const targetRange = document.createRange();
    const targetSpans = targetContainer.querySelectorAll('span');
    targetRange.setStart(targetSpans[0].firstChild!, 0);
    targetRange.setEnd(
      targetSpans[targetSpans.length - 1].firstChild!,
      targetSpans[targetSpans.length - 1].textContent!.length,
    );
    const lineCount = new Set(
      Array.from(targetRange.getClientRects(), (rect) => Math.round(rect.top)),
    ).size;
    const scale = Number(targetContainer.style.transform.match(/scale\(([^)]+)\)/)?.[1]);

    return {
      lineCount,
      naturalWidth: naturalRect.width,
      targetWidth: targetNode.size.w,
      scale,
    };
  });

  expect(result.naturalWidth - result.targetWidth).toBeCloseTo(24, 1);
  expect(result.lineCount).toBe(1);
  expect(result.scale).toBeGreaterThan(0.98);
  expect(result.scale).toBeLessThan(1);
});

test('headless renderSlide registers and releases host-provided font faces', async ({ page }) => {
  await page.goto('/test/browser/blank.html');
  const result = await page.evaluate(async () => {
    const { parseXml } = await import('/src/parser/XmlParser.ts');
    const { parseShapeNode } = await import('/src/model/nodes/ShapeNode.ts');
    const { renderSlide } = await import('/src/renderer/SlideRenderer.ts');
    const { createMockRenderContext } = await import('/test/unit/helpers/mockContext.ts');
    const ctx = createMockRenderContext();
    const node = parseShapeNode(
      parseXml(`
        <p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <p:nvSpPr><p:cNvPr id="2" name="Configured font"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
          <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1524000" cy="762000"/></a:xfrm><a:prstGeom prst="rect"/></p:spPr>
          <p:txBody>
            <a:bodyPr wrap="none"><a:noAutofit/></a:bodyPr><a:lstStyle/>
            <a:p><a:r><a:rPr sz="2400"><a:latin typeface="Configured Deck Face"/></a:rPr><a:t>Configured font</a:t></a:r></a:p>
          </p:txBody>
        </p:sp>`),
    );
    ctx.slide.nodes = [node];
    const config = [
      {
        family: 'Configured Deck Face',
        source: 'url("/test/browser/missing-font.woff2") format("woff2")',
        descriptors: { weight: '400' },
      },
    ];
    const handle = renderSlide(ctx.presentation, ctx.slide, { fontFaces: config });
    document.body.append(handle.element);
    const registeredFamilies = Array.from(document.fonts, (face) => face.family);
    const registeredImmediately = registeredFamilies.some((family) =>
      family.includes('Configured Deck Face'),
    );
    const family = getComputedStyle(handle.element.querySelector('span')!).fontFamily;
    await handle.ready;
    const registeredAfterReady = Array.from(document.fonts).some((face) =>
      face.family.includes('Configured Deck Face'),
    );
    handle.dispose();
    const registeredAfterDispose = Array.from(document.fonts).some((face) =>
      face.family.includes('Configured Deck Face'),
    );
    return {
      family,
      registeredFamilies,
      registeredImmediately,
      registeredAfterReady,
      registeredAfterDispose,
    };
  });

  expect(result).toEqual(expect.objectContaining({ registeredImmediately: true }));
  expect(result.family).toContain('Configured Deck Face');
  // The missing URL must remove the rejected face while keeping the slide usable.
  expect(result.registeredAfterReady).toBe(false);
  expect(result.registeredAfterDispose).toBe(false);
});
