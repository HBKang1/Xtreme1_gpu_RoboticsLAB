/**
 * Client-side box-quality validation for the Confidence Review Queue (#1).
 *
 * This module is the FRONTEND MIRROR of the canonical thresholds that live in
 * the serving entrypoint `deploy/point-cloud-detection/app.py` (`VALID_SIZE` /
 * `VALID_IOU`). Serving owns the canonical *values*; the frontend evaluates the
 * geometric *predicate* here for highlighting, because serving-emitted flags are
 * stripped by the closed Java `ModelResultConverter` before they reach the DB and
 * never survive to the loaded box (see plan §0). Computing the predicate from the
 * geometry already on every loaded box is therefore the only route that lights up
 * batch-DB-loaded scenes with no Java change.
 *
 * R-drift mitigation: keep these values byte-identical to `app.py`. A committed
 * parity check (Increment 2) asserts the two sources match — `app.py` is canonical.
 *
 * All thresholds are tuning constants (no inline magic numbers). The size ranges
 * below are starting points and may be re-tuned; whatever lands here MUST equal
 * `app.py`'s `VALID_SIZE` / `VALID_IOU`.
 */

/**
 * Per-class size envelope, keyed by UPPER-cased class name.
 * Tuple is [min, max] in meters for each box dimension: [x (length), y (width), z (height)].
 *
 * Axis convention matches the loaded box geometry: a box's `size3D` is its local
 * scale (x,y,z), with x along the heading (length), y lateral (width), z up (height).
 * A box `bad_size` iff any of x/y/z falls outside its class [min, max].
 */
export const VALID_SIZE: Record<string, { x: [number, number]; y: [number, number]; z: [number, number] }> = {
    CAR: { x: [2.5, 6.5], y: [1.4, 2.4], z: [1.2, 2.2] },
    TRUCK: { x: [4.0, 14.0], y: [1.8, 3.2], z: [1.8, 4.5] },
    BUS: { x: [6.0, 18.0], y: [2.0, 3.2], z: [2.5, 4.5] },
    PEDESTRIAN: { x: [0.2, 1.2], y: [0.2, 1.2], z: [1.0, 2.2] },
    BICYCLE: { x: [1.0, 2.2], y: [0.3, 1.0], z: [1.0, 2.0] },
    MOTORCYCLE: { x: [1.2, 2.7], y: [0.4, 1.3], z: [1.0, 2.0] },
};

/** BEV IoU threshold above which a same-frame pair is flagged `overlap`. */
export const VALID_IOU = 0.5;

/**
 * Tracking fallback confidence (serving contract, never reassigned). A box with
 * this exact confidence is a propagated fallback, not a fresh detection — it is
 * always "suspicious" for #1 and is exempt from hard size failure.
 */
export const TRACK_FALLBACK_CONFIDENCE = 0.1;

/**
 * Normalized box geometry used by the validators. The frontend's loaded boxes are
 * THREE objects that carry geometry as `position` (center), `scale` (size3D) and
 * `rotation` (Euler; z is heading) — NOT the `center3D/size3D/rotation3D` DTO keys
 * (those exist only on the serialized backend object). `toGeom()` normalizes both
 * shapes to this tuple so callers can pass either a live box or a DTO.
 */
export interface IBoxGeom {
    x: number;
    y: number;
    dx: number;
    dy: number;
    dz: number;
    /** heading (yaw) in radians, around the z axis */
    heading: number;
}

interface IVec3Like {
    x: number;
    y: number;
    z: number;
}

/**
 * Minimal structural view of whatever a caller hands us: a live loaded box
 * (THREE position/scale/rotation + userData) or a serialized DTO
 * (center3D/size3D/rotation3D + className/classType). Kept loose on purpose so this
 * module stays decoupled from pc-render's Box type and the backend DTO type.
 */
export interface IValidatableBox {
    position?: IVec3Like;
    scale?: IVec3Like;
    rotation?: IVec3Like;
    center3D?: IVec3Like;
    size3D?: IVec3Like;
    rotation3D?: IVec3Like;
    className?: string;
    classType?: string;
    userData?: {
        confidence?: number;
        classType?: string;
        modelClass?: string;
        className?: string;
    };
}

/**
 * Normalize a live box (position/scale/rotation) or a DTO (center3D/size3D/rotation3D)
 * to the uniform geometry tuple. Returns null if neither shape is present.
 */
export function toGeom(box: IValidatableBox): IBoxGeom | null {
    const center = box.position ?? box.center3D;
    const size = box.scale ?? box.size3D;
    const rot = box.rotation ?? box.rotation3D;
    if (!center || !size || !rot) return null;
    return {
        x: center.x,
        y: center.y,
        dx: size.x,
        dy: size.y,
        dz: size.z,
        heading: rot.z,
    };
}

/**
 * Resolve a box's class name for size lookup. On a loaded box the class config
 * name lives in `userData.classType` (set to `classConfig.name` at load), falling
 * back to `userData.modelClass`. DTO/test callers may pass `className`/`classType`
 * directly. Upper-cased to match `VALID_SIZE` keys; '' if unknown.
 */
export function getClassName(box: IValidatableBox): string {
    const raw =
        box.userData?.classType ||
        box.userData?.modelClass ||
        box.userData?.className ||
        box.className ||
        box.classType ||
        '';
    return raw.toUpperCase();
}

function getConfidence(box: IValidatableBox): number | undefined {
    return box.userData?.confidence;
}

/** Project the 4 BEV corners of a box (x, y, dx, dy, heading) to world XY. */
function bevCorners(g: IBoxGeom): Array<[number, number]> {
    const cos = Math.cos(g.heading);
    const sin = Math.sin(g.heading);
    const hx = g.dx / 2;
    const hy = g.dy / 2;
    // local corners: (+hx,+hy), (+hx,-hy), (-hx,-hy), (-hx,+hy)
    const local: Array<[number, number]> = [
        [hx, hy],
        [hx, -hy],
        [-hx, -hy],
        [-hx, hy],
    ];
    return local.map(([lx, ly]) => [g.x + lx * cos - ly * sin, g.y + lx * sin + ly * cos]);
}

/** Signed polygon area (shoelace); positive for CCW. */
function polyArea(poly: Array<[number, number]>): number {
    let area = 0;
    for (let i = 0; i < poly.length; i++) {
        const [x1, y1] = poly[i];
        const [x2, y2] = poly[(i + 1) % poly.length];
        area += x1 * y2 - x2 * y1;
    }
    return Math.abs(area) / 2;
}

/**
 * Clip subject polygon by a convex clip polygon (Sutherland–Hodgman).
 * Both polygons must be ordered CCW. Returns the clipped polygon (possibly empty).
 */
function clipPolygon(
    subject: Array<[number, number]>,
    clip: Array<[number, number]>,
): Array<[number, number]> {
    let output = subject;
    for (let i = 0; i < clip.length; i++) {
        if (output.length === 0) break;
        const a = clip[i];
        const b = clip[(i + 1) % clip.length];
        // inside test: point is to the left of directed edge a->b (CCW clip)
        const inside = (p: [number, number]) =>
            (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0;
        const input = output;
        output = [];
        for (let j = 0; j < input.length; j++) {
            const cur = input[j];
            const prev = input[(j + input.length - 1) % input.length];
            const curIn = inside(cur);
            const prevIn = inside(prev);
            if (curIn) {
                if (!prevIn) {
                    const ip = intersect(prev, cur, a, b);
                    if (ip) output.push(ip);
                }
                output.push(cur);
            } else if (prevIn) {
                const ip = intersect(prev, cur, a, b);
                if (ip) output.push(ip);
            }
        }
    }
    return output;
}

/** Intersection of segment p1->p2 with the infinite line through a->b. */
function intersect(
    p1: [number, number],
    p2: [number, number],
    a: [number, number],
    b: [number, number],
): [number, number] | null {
    const x1 = p1[0];
    const y1 = p1[1];
    const x2 = p2[0];
    const y2 = p2[1];
    const x3 = a[0];
    const y3 = a[1];
    const x4 = b[0];
    const y4 = b[1];
    const denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
    if (Math.abs(denom) < 1e-12) return null;
    const t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom;
    return [x1 + t * (x2 - x1), y1 + t * (y2 - y1)];
}

/** Ensure a quad is ordered CCW (positive signed area). */
function ensureCCW(poly: Array<[number, number]>): Array<[number, number]> {
    let signed = 0;
    for (let i = 0; i < poly.length; i++) {
        const [x1, y1] = poly[i];
        const [x2, y2] = poly[(i + 1) % poly.length];
        signed += x1 * y2 - x2 * y1;
    }
    return signed < 0 ? [...poly].reverse() : poly;
}

/**
 * Rotated-2D (BEV) IoU between two boxes, from (x, y, dx, dy, heading).
 * TS twin of `app.py`'s `_bev_iou`. Returns intersection-over-union in [0, 1].
 */
export function bevIou(boxA: IValidatableBox | IBoxGeom, boxB: IValidatableBox | IBoxGeom): number {
    const ga = isGeom(boxA) ? boxA : toGeom(boxA);
    const gb = isGeom(boxB) ? boxB : toGeom(boxB);
    if (!ga || !gb) return 0;

    const polyA = ensureCCW(bevCorners(ga));
    const polyB = ensureCCW(bevCorners(gb));

    const inter = polyArea(clipPolygon(polyA, polyB));
    if (inter <= 0) return 0;

    const areaA = ga.dx * ga.dy;
    const areaB = gb.dx * gb.dy;
    const union = areaA + areaB - inter;
    if (union <= 0) return 0;

    return inter / union;
}

function isGeom(b: IValidatableBox | IBoxGeom): b is IBoxGeom {
    return (b as IBoxGeom).dx !== undefined && (b as IBoxGeom).heading !== undefined;
}

export interface IViolations {
    badSize: boolean;
    overlap: boolean;
}

/**
 * Evaluate the size + overlap rules for one loaded box against its same-frame
 * neighbors. Pure function of geometry already on the box — no serving flag, no
 * DB round-trip. `sameFrameBoxes` are the other loaded boxes in the same frame
 * (e.g. `editor.dataManager.getFrameObject(frameId)`); the box itself may be
 * included and is skipped by identity.
 *
 * - badSize: any size3D axis outside its class [min, max]. Unknown class => not
 *   flagged. Fallback boxes (`confidence == TRACK_FALLBACK_CONFIDENCE`) are exempt
 *   from hard size failure (they are propagations, mirrors app.py).
 * - overlap: BEV IoU with any same-frame neighbor exceeds VALID_IOU.
 */
export function evaluateViolations(
    box: IValidatableBox,
    sameFrameBoxes: IValidatableBox[] = [],
): IViolations {
    const geom = toGeom(box);
    if (!geom) return { badSize: false, overlap: false };

    const result: IViolations = { badSize: false, overlap: false };

    // size rule
    const isFallback = getConfidence(box) === TRACK_FALLBACK_CONFIDENCE;
    if (!isFallback) {
        const env = VALID_SIZE[getClassName(box)];
        if (env) {
            result.badSize =
                geom.dx < env.x[0] ||
                geom.dx > env.x[1] ||
                geom.dy < env.y[0] ||
                geom.dy > env.y[1] ||
                geom.dz < env.z[0] ||
                geom.dz > env.z[1];
        }
    }

    // overlap rule
    for (const other of sameFrameBoxes) {
        if (other === box) continue;
        const otherGeom = toGeom(other);
        if (!otherGeom) continue;
        if (bevIou(geom, otherGeom) > VALID_IOU) {
            result.overlap = true;
            break;
        }
    }

    return result;
}

/**
 * Single source of truth for the #1 "suspicious" predicate used by the panel
 * sort/filter, the timeline highlight, and the jump-to-next hotkey:
 *   suspicious = fallback (confidence == 0.1) OR badSize OR overlap.
 */
export function isSuspicious(box: IValidatableBox, sameFrameBoxes: IValidatableBox[] = []): boolean {
    if (getConfidence(box) === TRACK_FALLBACK_CONFIDENCE) return true;
    const v = evaluateViolations(box, sameFrameBoxes);
    return v.badSize || v.overlap;
}
