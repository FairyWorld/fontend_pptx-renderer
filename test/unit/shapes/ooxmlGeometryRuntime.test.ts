import { describe, expect, it } from 'vitest';

import {
  evaluateOoxmlGuideFormula,
  getOoxmlPresetShapePaths,
  ooxmlPresetPilotShapeNames,
  ooxmlPresetPilotSourceSha256,
} from '../../../src/shapes/ooxmlGeometryRuntime';
import {
  compilePresetShapeDefinitions,
  evaluatePresetShape,
} from '../../../scripts/ooxml-geometry/geometry-ir.mjs';
import { emitPresetShapePaths } from '../../../scripts/ooxml-geometry/path-emitter.mjs';
import { loadPinnedPresetShapeDefinitions } from '../../../scripts/ooxml-geometry/source-validator.mjs';
import sourceManifest from '../../../scripts/ooxml-geometry/source-manifest.json';
import sourceReconciliation from '../../../scripts/ooxml-geometry/source-reconciliation.json';

describe('OOXML preset geometry runtime pilot', () => {
  it('keeps the production allowlist explicit and leaves other presets on handwritten geometry', () => {
    expect(ooxmlPresetPilotShapeNames).toEqual(['flowChartTerminator']);
    expect(ooxmlPresetPilotSourceSha256).toBe(sourceManifest.presetShapeDefinitions.sha256);
    expect(getOoxmlPresetShapePaths('rect', 400, 280)).toBeNull();
    expect(getOoxmlPresetShapePaths('unknownShape', 400, 280)).toBeNull();
  });

  it.each([
    ['*/', [6, 7, 3], 14],
    ['+-', [10, 3, 4], 9],
    ['+/', [10, 2, 3], 4],
    ['?:', [1, 20, 30], 20],
    ['abs', [-7], 7],
    ['at2', [1, 1], 2700000],
    ['cat2', [10, 3, 4], 6],
    ['cos', [10, 5400000], 0],
    ['max', [-2, 3], 3],
    ['min', [-2, 3], -2],
    ['mod', [2, 3, 6], 7],
    ['pin', [0, 11, 10], 10],
    ['sat2', [10, 3, 4], 8],
    ['sin', [10, 5400000], 10],
    ['sqrt', [-9], 3],
    ['tan', [10, 2700000], 10],
    ['val', [-2], -2],
  ] as const)(
    'evaluates runtime operator %s with the M1 numeric contract',
    (operator, values, expected) => {
      expect(evaluateOoxmlGuideFormula(operator, [...values])).toBeCloseTo(expected, 6);
    },
  );

  it('emits the approved pilot deterministically and accepts case-insensitive lookup', () => {
    const expected =
      'M64.351852,0 L335.648148,0 A64.351852,140 0 0,1 335.648148,280 L64.351852,280 A64.351852,140 0 0,1 64.351852,0 Z';

    expect(getOoxmlPresetShapePaths('flowChartTerminator', 400, 280)?.[0].d).toBe(expected);
    expect(getOoxmlPresetShapePaths('FLOWCHARTTERMINATOR', 400, 280)?.[0].d).toBe(expected);
  });

  it('matches the build-time compiler and emitter at square, wide, and tall extents', async () => {
    const source = await loadPinnedPresetShapeDefinitions(process.cwd(), sourceManifest);
    const ir = compilePresetShapeDefinitions(source.xml, sourceManifest, sourceReconciliation);
    const shape = ir.shapes.find(({ name }: { name: string }) => name === 'flowChartTerminator');
    expect(shape).toBeDefined();

    for (const dimensions of [
      { width: 216, height: 216 },
      { width: 400, height: 180 },
      { width: 180, height: 400 },
    ]) {
      const buildTime = emitPresetShapePaths(evaluatePresetShape(shape, dimensions)).paths;
      expect(
        getOoxmlPresetShapePaths('flowChartTerminator', dimensions.width, dimensions.height),
      ).toEqual(buildTime);
    }
  }, 20_000);

  it('rejects invalid dimensions and ignores unrelated legacy adjustment entries', () => {
    expect(() => getOoxmlPresetShapePaths('flowChartTerminator', 0, 280)).toThrow(
      /width.*greater than zero/i,
    );
    expect(
      getOoxmlPresetShapePaths('flowChartTerminator', 400, 280, new Map([['unsupported', 1]])),
    ).toEqual(getOoxmlPresetShapePaths('flowChartTerminator', 400, 280));
  });

  it('rejects malformed runtime formulas before they can emit invalid SVG', () => {
    expect(() => evaluateOoxmlGuideFormula('*/', [1, 2, 0])).toThrow(/division by zero/i);
    expect(() => evaluateOoxmlGuideFormula('unknown', [])).toThrow(/unknown.*operator/i);
    expect(() => evaluateOoxmlGuideFormula('val', [Number.NaN])).toThrow(/finite/i);
  });
});
