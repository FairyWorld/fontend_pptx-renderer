import type { Shape3DRotation } from '../../model/nodes/Shape3D';

export interface ProjectedPoint {
  x: number;
  y: number;
}

export interface FlatPlaneProjection {
  corners: readonly [ProjectedPoint, ProjectedPoint, ProjectedPoint, ProjectedPoint];
  cameraDistance?: number;
}

export interface FlatPlaneProjectionOptions {
  kind: 'orthographic' | 'perspective';
  width: number;
  height: number;
  presentationWidth: number;
  rotation: Shape3DRotation;
  fieldOfView?: number;
  /** Preset-specific view-volume scale established by the native PowerPoint matrix. */
  presetViewportScale?: number;
  /** Preset-specific projected-plane scale around the local center. */
  presetProjectionScale?: number;
}

const HOMOGRAPHY_EPSILON = 1e-9;

function finitePoint(point: ProjectedPoint): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.y);
}

/**
 * Encode the projective map from a local rectangle to a four-corner camera plane.
 *
 * CSS `matrix3d()` exposes the homogeneous W row needed for a true quadrilateral map, so live
 * text remains selectable while its line boxes follow the same zero-depth camera plane as SVG.
 */
export function projectiveTransformToCssMatrix3d(
  width: number,
  height: number,
  corners: readonly [ProjectedPoint, ProjectedPoint, ProjectedPoint, ProjectedPoint],
): string | undefined {
  if (
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0 ||
    !corners.every(finitePoint)
  ) {
    return undefined;
  }

  const [topLeft, topRight, bottomRight, bottomLeft] = corners;
  const twiceArea = corners.reduce((sum, point, index) => {
    const next = corners[(index + 1) % corners.length];
    return sum + point.x * next.y - next.x * point.y;
  }, 0);
  if (!Number.isFinite(twiceArea) || Math.abs(twiceArea) <= HOMOGRAPHY_EPSILON) return undefined;

  const dx1 = topRight.x - bottomRight.x;
  const dx2 = bottomLeft.x - bottomRight.x;
  const dx3 = topLeft.x - topRight.x + bottomRight.x - bottomLeft.x;
  const dy1 = topRight.y - bottomRight.y;
  const dy2 = bottomLeft.y - bottomRight.y;
  const dy3 = topLeft.y - topRight.y + bottomRight.y - bottomLeft.y;

  let perspectiveX = 0;
  let perspectiveY = 0;
  if (Math.abs(dx3) > HOMOGRAPHY_EPSILON || Math.abs(dy3) > HOMOGRAPHY_EPSILON) {
    const denominator = dx1 * dy2 - dx2 * dy1;
    if (!Number.isFinite(denominator) || Math.abs(denominator) <= HOMOGRAPHY_EPSILON) {
      return undefined;
    }
    perspectiveX = (dx3 * dy2 - dx2 * dy3) / denominator;
    perspectiveY = (dx1 * dy3 - dx3 * dy1) / denominator;
  }

  const h11 = (topRight.x - topLeft.x + perspectiveX * topRight.x) / width;
  const h12 = (bottomLeft.x - topLeft.x + perspectiveY * bottomLeft.x) / height;
  const h13 = topLeft.x;
  const h21 = (topRight.y - topLeft.y + perspectiveX * topRight.y) / width;
  const h22 = (bottomLeft.y - topLeft.y + perspectiveY * bottomLeft.y) / height;
  const h23 = topLeft.y;
  const h31 = perspectiveX / width;
  const h32 = perspectiveY / height;
  const values = [h11, h21, 0, h31, h12, h22, 0, h32, 0, 0, 1, 0, h13, h23, 0, 1];
  if (values.some((value) => !Number.isFinite(value))) return undefined;
  return `matrix3d(${values.map((value) => Number(value.toFixed(12))).join(',')})`;
}

function radians(degrees: number): number {
  const normalized = ((((degrees + 180) % 360) + 360) % 360) - 180;
  return (normalized * Math.PI) / 180;
}

/**
 * Project a zero-depth DrawingML plane around its local center.
 *
 * DrawingML records the camera rotations but does not prescribe a browser rasterizer. The
 * rotation order and perspective division here are pinned to native PowerPoint corner evidence.
 */
export function projectFlatPlane(
  options: FlatPlaneProjectionOptions,
): FlatPlaneProjection | undefined {
  const { kind, width, height, presentationWidth, rotation } = options;
  if (
    ![width, height, presentationWidth].every(Number.isFinite) ||
    width <= 0 ||
    height <= 0 ||
    presentationWidth <= 0
  ) {
    return undefined;
  }

  const latitude = radians(rotation.latitude);
  const longitude = radians(rotation.longitude);
  const revolution = radians(rotation.revolution);
  const cosLatitude = Math.cos(latitude);
  const sinLatitude = Math.sin(latitude);
  const cosLongitude = Math.cos(longitude);
  const sinLongitude = Math.sin(longitude);
  const cosRevolution = Math.cos(revolution);
  const sinRevolution = Math.sin(revolution);

  let cameraDistance: number | undefined;
  if (kind === 'perspective') {
    const fieldOfView = options.fieldOfView;
    const viewportScale = options.presetViewportScale;
    if (
      fieldOfView === undefined ||
      viewportScale === undefined ||
      !Number.isFinite(fieldOfView) ||
      !Number.isFinite(viewportScale) ||
      fieldOfView <= 0 ||
      fieldOfView >= 180 ||
      viewportScale <= 0
    ) {
      return undefined;
    }
    cameraDistance =
      (presentationWidth / (2 * Math.tan((fieldOfView * Math.PI) / 360))) * viewportScale;
    if (!Number.isFinite(cameraDistance) || cameraDistance <= 0) return undefined;
  }

  const halfWidth = width / 2;
  const halfHeight = height / 2;
  const sourceCorners = [
    [-halfWidth, -halfHeight],
    [halfWidth, -halfHeight],
    [halfWidth, halfHeight],
    [-halfWidth, halfHeight],
  ] as const;
  const projected: ProjectedPoint[] = [];

  for (const [sourceX, sourceY] of sourceCorners) {
    // A zero-depth plane first rotates around Y (longitude), then X (latitude). This order is
    // observable in the 20°/30° orthographic control, whose two vertical sides remain parallel.
    const rotatedX = sourceX * cosLongitude;
    const rotatedY = sourceY * cosLatitude + sourceX * sinLongitude * sinLatitude;
    const rotatedZ = sourceY * sinLatitude - sourceX * sinLongitude * cosLatitude;
    let projectedX = rotatedX;
    let projectedY = rotatedY;
    if (cameraDistance !== undefined) {
      const denominator = cameraDistance + rotatedZ;
      // Do not let an unverified large plane cross the camera and explode the SVG bounds.
      if (!Number.isFinite(denominator) || denominator <= cameraDistance * 0.1) return undefined;
      const scale = cameraDistance / denominator;
      projectedX *= scale;
      projectedY *= scale;
    }
    const projectionScale = options.presetProjectionScale ?? 1;
    if (!Number.isFinite(projectionScale) || projectionScale <= 0) return undefined;
    const revolvedX = (projectedX * cosRevolution - projectedY * sinRevolution) * projectionScale;
    const revolvedY = (projectedX * sinRevolution + projectedY * cosRevolution) * projectionScale;
    const point = { x: halfWidth + revolvedX, y: halfHeight + revolvedY };
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return undefined;
    projected.push(point);
  }

  return {
    corners: projected as [ProjectedPoint, ProjectedPoint, ProjectedPoint, ProjectedPoint],
    cameraDistance,
  };
}
