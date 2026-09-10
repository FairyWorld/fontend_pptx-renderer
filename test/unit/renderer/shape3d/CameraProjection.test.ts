import { describe, expect, it } from 'vitest';
import {
  projectFlatPlane,
  projectiveTransformToCssMatrix3d,
} from '../../../../src/renderer/shape3d/CameraProjection';

describe('projectFlatPlane', () => {
  it('applies the DrawingML orthographic rotation chain around the shape center', () => {
    const projection = projectFlatPlane({
      kind: 'orthographic',
      width: 403.2,
      height: 403.2,
      presentationWidth: 1280,
      rotation: { latitude: 20, longitude: 30, revolution: 0 },
    });

    expect(projection).toBeDefined();
    expect(projection!.corners[0]).toMatchObject({ x: expect.closeTo(27.0, 1) });
    expect(projection!.corners[0].y).toBeCloseTo(-22.3, 1);
    expect(projection!.corners[1].x).toBeCloseTo(376.2, 1);
    expect(projection!.corners[1].y).toBeCloseTo(46.6, 1);
    expect(projection!.corners[2].x).toBeCloseTo(376.2, 1);
    expect(projection!.corners[2].y).toBeCloseTo(425.5, 1);
    expect(projection!.corners[3].x).toBeCloseTo(27.0, 1);
    expect(projection!.corners[3].y).toBeCloseTo(356.6, 1);
  });

  it('matches the native PowerPoint perspective corner model across aspect ratios', () => {
    const square = projectFlatPlane({
      kind: 'perspective',
      width: 403.2,
      height: 403.2,
      presentationWidth: 1280,
      fieldOfView: 120,
      presetViewportScale: 0.95,
      presetProjectionScale: 0.996,
      rotation: { latitude: 18590633 / 60000, longitude: 0, revolution: 0 },
    });
    const wide = projectFlatPlane({
      kind: 'perspective',
      width: 768,
      height: 307.2,
      presentationWidth: 1280,
      fieldOfView: 120,
      presetViewportScale: 0.95,
      presetProjectionScale: 0.996,
      rotation: { latitude: 18590633 / 60000, longitude: 0, revolution: 0 },
    });

    expect(square).toBeDefined();
    expect(square!.corners[0].x).toBeCloseTo(62.3, 1);
    expect(square!.corners[0].y).toBeCloseTo(112.3, 1);
    expect(square!.corners[2].x).toBeCloseTo(560.8, 1);
    expect(square!.corners[2].y).toBeCloseTo(431.7, 1);

    expect(wide).toBeDefined();
    expect(wide!.corners[0].x).toBeCloseTo(97.7, 1);
    expect(wide!.corners[0].y).toBeCloseTo(80.2, 1);
    expect(wide!.corners[2].x).toBeCloseTo(960.0, 1);
    expect(wide!.corners[2].y).toBeCloseTo(301.2, 1);
  });

  it('rejects a perspective plane that reaches or crosses the camera', () => {
    expect(
      projectFlatPlane({
        kind: 'perspective',
        width: 200,
        height: 2000,
        presentationWidth: 960,
        fieldOfView: 120,
        presetViewportScale: 0.95,
        rotation: { latitude: -50, longitude: 0, revolution: 0 },
      }),
    ).toBeUndefined();
  });

  it('matches the native perspective-contrasting-right-facing zero-depth corners', () => {
    const projection = projectFlatPlane({
      kind: 'perspective',
      width: 441.6,
      height: 384,
      presentationWidth: 1280,
      fieldOfView: 85,
      presetViewportScale: 0.95,
      rotation: { latitude: 0, longitude: 19532225 / 60000, revolution: 0 },
    });

    expect(projection).toBeDefined();
    expect(projection!.corners[0].x).toBeCloseTo(-3.5, 1);
    expect(projection!.corners[0].y).toBeCloseTo(-44.5, 1);
    expect(projection!.corners[1].x).toBeCloseTo(374.0, 1);
    expect(projection!.corners[1].y).toBeCloseTo(30.4, 1);
    expect(projection!.corners[2].x).toBeCloseTo(374.0, 1);
    expect(projection!.corners[2].y).toBeCloseTo(353.6, 1);
    expect(projection!.corners[3].x).toBeCloseTo(-3.5, 1);
    expect(projection!.corners[3].y).toBeCloseTo(428.5, 1);
  });

  it('encodes a rectangle-to-camera-quad homography as a CSS matrix3d', () => {
    const corners = [
      { x: -3.5, y: -44.5 },
      { x: 374.0, y: 30.4 },
      { x: 374.0, y: 353.6 },
      { x: -3.5, y: 428.5 },
    ] as const;
    const css = projectiveTransformToCssMatrix3d(441.6, 384, corners);

    expect(css).toMatch(/^matrix3d\(/);
    const values = css!.slice('matrix3d('.length, -1).split(',').map(Number);
    expect(values).toHaveLength(16);
    const apply = (x: number, y: number) => {
      const denominator = values[3] * x + values[7] * y + values[15];
      return {
        x: (values[0] * x + values[4] * y + values[12]) / denominator,
        y: (values[1] * x + values[5] * y + values[13]) / denominator,
      };
    };
    const projected = [apply(0, 0), apply(441.6, 0), apply(441.6, 384), apply(0, 384)];
    projected.forEach((point, index) => {
      expect(point.x).toBeCloseTo(corners[index].x, 5);
      expect(point.y).toBeCloseTo(corners[index].y, 5);
    });
  });

  it('rejects a degenerate projective text plane', () => {
    expect(
      projectiveTransformToCssMatrix3d(200, 100, [
        { x: 0, y: 0 },
        { x: 0, y: 0 },
        { x: 0, y: 0 },
        { x: 0, y: 0 },
      ]),
    ).toBeUndefined();
  });
});
