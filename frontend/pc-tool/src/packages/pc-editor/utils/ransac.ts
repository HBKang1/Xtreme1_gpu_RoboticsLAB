// #3 ground toggle — RANSAC ground-plane fitting.
//
// Fits a single dominant plane to a point cloud and returns it as the implicit
// plane a*x + b*y + c*z + d = 0 with a unit normal (a, b, c). The plane is used
// ONLY as a render/snap reference (view discard + AIBox/track snap z): it never
// mutates the detector input buffer nor the saved center3D/size3D/rotation3D.
//
// Mitigations for sparse 16-beam night LiDAR (R-ransac):
//   - candidate seed points are drawn from a LOWER-Z BAND so a wall/ceiling is
//     unlikely to be sampled as the seed plane,
//   - only NEAR-HORIZONTAL candidate planes (|normal.z| >= NORMAL_Z_MIN) are
//     scored, so vertical surfaces are rejected outright,
//   - if the best inlier count is below RANSAC_MIN_INLIERS the caller is told the
//     fit failed (ok=false) and is expected to fall back to the fixed-z heuristic.

// Max perpendicular distance (metres) for a point to count as a plane inlier.
export const RANSAC_DISTANCE = 0.2;
// Number of random 3-point hypotheses to try.
export const RANSAC_ITERATIONS = 80;
// Reject candidate planes whose normal is more tilted than this (|n.z| floor).
// 0.85 ≈ within ~31° of horizontal — generous enough for banked roads, tight
// enough to reject walls.
export const NORMAL_Z_MIN = 0.85;
// Fraction of the z-range, measured up from z_min, that seed points are sampled
// from. Keeps RANSAC seeds on/near the ground, away from tall structures.
export const SEED_Z_BAND = 0.25;
// Minimum inlier count for a fit to be considered trustworthy.
export const RANSAC_MIN_INLIERS = 50;

export interface IPlane {
    a: number;
    b: number;
    c: number;
    d: number;
}

export interface IGroundPlaneResult extends IPlane {
    // false when RANSAC could not find a confident horizontal plane; the caller
    // should fall back to the fixed-z road heuristic.
    ok: boolean;
    inliers: number;
}

export interface IFitOptions {
    distanceThreshold?: number;
    iterations?: number;
    minInliers?: number;
}

// Flat [x0,y0,z0, x1,y1,z1, ...] is also accepted to avoid copies in the worker.
export type PointInput = Float32Array | number[] | ReadonlyArray<number>;

function getXYZ(points: PointInput, i: number): [number, number, number] {
    const o = i * 3;
    return [points[o], points[o + 1], points[o + 2]];
}

// Plane through 3 points with a unit normal; null if the points are collinear.
function planeFrom3(
    p0: [number, number, number],
    p1: [number, number, number],
    p2: [number, number, number],
): IPlane | null {
    const ux = p1[0] - p0[0];
    const uy = p1[1] - p0[1];
    const uz = p1[2] - p0[2];
    const vx = p2[0] - p0[0];
    const vy = p2[1] - p0[1];
    const vz = p2[2] - p0[2];
    // normal = u × v
    let nx = uy * vz - uz * vy;
    let ny = uz * vx - ux * vz;
    let nz = ux * vy - uy * vx;
    const len = Math.sqrt(nx * nx + ny * ny + nz * nz);
    if (len < 1e-6) return null; // degenerate / collinear
    nx /= len;
    ny /= len;
    nz /= len;
    const d = -(nx * p0[0] + ny * p0[1] + nz * p0[2]);
    return { a: nx, b: ny, c: nz, d };
}

/**
 * Fit a ground plane via RANSAC. Returns the plane plus an `ok` flag — when
 * `ok` is false the caller should keep using the fixed-z road heuristic.
 */
export function fitGroundPlane(points: PointInput, opts: IFitOptions = {}): IGroundPlaneResult {
    const distanceThreshold = opts.distanceThreshold ?? RANSAC_DISTANCE;
    const iterations = opts.iterations ?? RANSAC_ITERATIONS;
    const minInliers = opts.minInliers ?? RANSAC_MIN_INLIERS;

    const n = Math.floor(points.length / 3);
    const fail: IGroundPlaneResult = { a: 0, b: 0, c: 1, d: 0, ok: false, inliers: 0 };
    if (n < 3) return fail;

    // z-band for seed sampling (lower part of the cloud only).
    let zMin = Infinity;
    let zMax = -Infinity;
    for (let i = 0; i < n; i++) {
        const z = points[i * 3 + 2];
        if (z < zMin) zMin = z;
        if (z > zMax) zMax = z;
    }
    const zBandTop = zMin + (zMax - zMin) * SEED_Z_BAND;
    const seedIdx: number[] = [];
    for (let i = 0; i < n; i++) {
        if (points[i * 3 + 2] <= zBandTop) seedIdx.push(i);
    }
    // If the band is too small to sample 3 distinct seeds, sample from the whole cloud.
    const pool = seedIdx.length >= 3 ? seedIdx : null;
    const poolSize = pool ? pool.length : n;
    const pick = () => {
        const r = Math.floor(Math.random() * poolSize);
        return pool ? pool[r] : r;
    };

    let best: IPlane | null = null;
    let bestInliers = 0;

    for (let it = 0; it < iterations; it++) {
        const i0 = pick();
        let i1 = pick();
        let i2 = pick();
        if (i1 === i0) i1 = (i1 + 1) % n;
        if (i2 === i0 || i2 === i1) i2 = (i2 + 2) % n;

        const plane = planeFrom3(getXYZ(points, i0), getXYZ(points, i1), getXYZ(points, i2));
        if (!plane) continue;
        // Reject non-horizontal candidate planes outright.
        if (Math.abs(plane.c) < NORMAL_Z_MIN) continue;

        let inliers = 0;
        for (let i = 0; i < n; i++) {
            const x = points[i * 3];
            const y = points[i * 3 + 1];
            const z = points[i * 3 + 2];
            const dist = Math.abs(plane.a * x + plane.b * y + plane.c * z + plane.d);
            if (dist <= distanceThreshold) inliers++;
        }
        if (inliers > bestInliers) {
            bestInliers = inliers;
            best = plane;
        }
    }

    if (!best || bestInliers < minInliers) return fail;

    // Orient the normal so c > 0 (z grows "up") for a stable planeZ() query.
    if (best.c < 0) {
        best = { a: -best.a, b: -best.b, c: -best.c, d: -best.d };
    }
    return { ...best, ok: true, inliers: bestInliers };
}

// Solve for z on the plane at a given (x, y): z = -(a*x + b*y + d) / c.
export function planeZ(plane: IPlane, x: number, y: number): number {
    if (Math.abs(plane.c) < 1e-6) return 0;
    return -(plane.a * x + plane.b * y + plane.d) / plane.c;
}
