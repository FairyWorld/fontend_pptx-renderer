import { expect, test } from '@playwright/test';

// Set PLAYWRIGHT_CHANNEL=chrome on machines with Chrome but no downloaded Chromium.
test.use({ channel: process.env.PLAYWRIGHT_CHANNEL });

test('eaLnBrk isolates East Asian line-breaking semantics from host CSS', async ({ page }) => {
  await page.goto('/test/browser/blank.html');
  const result = await page.evaluate(async () => {
    const { renderTextFixture } = await import('/test/fixtures/text-coverage.ts');
    document.body.style.lineBreak = 'strict';

    const disabled = renderTextFixture(undefined, '', '<a:lvl1pPr eaLnBrk="0"/>');
    const enabled = renderTextFixture(undefined, '', '<a:lvl1pPr eaLnBrk="1"/>');
    const omitted = renderTextFixture();
    document.body.append(disabled.element, enabled.element, omitted.element);

    return {
      disabled: getComputedStyle(disabled.para).lineBreak,
      enabled: getComputedStyle(enabled.para).lineBreak,
      omitted: getComputedStyle(omitted.para).lineBreak,
    };
  });

  expect(result).toEqual({
    disabled: 'anywhere',
    enabled: 'auto',
    omitted: 'auto',
  });
});

test('soft breaks preserve their own run metrics without changing visible text metrics', async ({
  page,
}) => {
  await page.goto('/test/browser/blank.html');
  const result = await page.evaluate(async () => {
    const { parseXml } = await import('/src/parser/XmlParser.ts');
    const { parseShapeNode } = await import('/src/model/nodes/ShapeNode.ts');
    const { renderShape } = await import('/src/renderer/ShapeRenderer.ts');
    const { createMockRenderContext } = await import('/test/unit/helpers/mockContext.ts');
    const shape = parseShapeNode(
      parseXml(`
        <p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <p:nvSpPr><p:cNvPr id="1" name="Styled soft break"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
          <p:spPr>
            <a:xfrm><a:off x="0" y="0"/><a:ext cx="3810000" cy="1905000"/></a:xfrm>
            <a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/>
          </p:spPr>
          <p:txBody>
            <a:bodyPr lIns="0" tIns="0" rIns="0" bIns="0"><a:noAutofit/></a:bodyPr>
            <a:lstStyle/>
            <a:p>
              <a:pPr><a:lnSpc><a:spcPct val="100000"/></a:lnSpc></a:pPr>
              <a:br><a:rPr sz="3000"><a:latin typeface="Arial"/></a:rPr></a:br>
              <a:r><a:rPr sz="1000"><a:latin typeface="Courier New"/></a:rPr><a:t>Visible</a:t></a:r>
            </a:p>
          </p:txBody>
        </p:sp>`),
    );
    const rendered = renderShape(shape, createMockRenderContext());
    document.body.append(rendered);
    const textContainer = Array.from(rendered.children).find(
      (element) => element instanceof HTMLElement && element.textContent === 'Visible',
    ) as HTMLElement;
    const paragraph = textContainer.firstElementChild as HTMLElement;
    const breakSpan = paragraph.querySelector('br')?.parentElement as HTMLElement;
    const visibleSpan = Array.from(paragraph.querySelectorAll('span')).find(
      (element) => element.textContent === 'Visible',
    ) as HTMLElement;
    return {
      paragraphFontSize: getComputedStyle(paragraph).fontSize,
      breakParent: breakSpan.tagName,
      breakFontSize: getComputedStyle(breakSpan).fontSize,
      breakFontFamily: getComputedStyle(breakSpan).fontFamily,
      visibleFontSize: getComputedStyle(visibleSpan).fontSize,
      visibleFontFamily: getComputedStyle(visibleSpan).fontFamily,
    };
  });

  expect(result.paragraphFontSize).toBe('13.3333px');
  expect(result.breakParent).toBe('SPAN');
  expect(result.breakFontSize).toBe('40px');
  expect(result.breakFontFamily).toContain('Arial');
  expect(result.visibleFontSize).toBe('13.3333px');
  expect(result.visibleFontFamily).toContain('Courier New');
});
