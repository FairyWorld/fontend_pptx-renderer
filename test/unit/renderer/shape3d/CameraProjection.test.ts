import { describe, expect, it } from 'vitest';
import { projectFlatPlane } from '../../../../src/renderer/shape3d/CameraProjection';

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
});
