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
