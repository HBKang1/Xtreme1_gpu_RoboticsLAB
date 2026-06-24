import numpy as np
from pcdet_open.service import *

from pcdet_open.src.load_pcd import PointCloud
from pcdet_open.src.predictor import Predictor

import io
import re
import requests
from os.path import join, dirname, abspath
import gc

# tracking parameters (initial values; tune during Zenix validation)
TRACK_MATCH_GATE_M = 2.0        # base BEV gate for seed<->detection match
TRACK_GATE_GROWTH = 0.5         # gate grows 50% per consecutive miss (CV error accumulates)
TRACK_GATE_MAX_M = 4.0          # gate ceiling
TRACK_SCORE_FLOOR = 0.1         # detections below this score are not match candidates
TRACK_FALLBACK_CONFIDENCE = 0.1
TRACK_MAX_MISSES = 5            # deactivate a track after this many consecutive misses
TRACK_SNAP_MIN_POINTS = 10      # min in-box points for a fallback to snap onto the cloud
TRACK_SNAP_RADIUS_SCALE = 0.75  # BEV snap window = max(length, width) * this

# rule-validation thresholds (CANONICAL SOURCE). The frontend mirrors these in
# frontend/pc-tool/src/packages/pc-editor/config/validation.ts; a parity test
# (test_validation_parity.py) guards the two against silent drift. Note: these
# flags are stripped by the closed Java ModelResultConverter before reaching the
# DB/frontend, so they exist for curl-verification only -- the frontend computes
# the same predicate client-side from loaded box geometry.
# Per UPPER class name -> per-axis (min, max) in meters for (dx, dy, dz).
VALID_SIZE = {
    'CAR':        {'x': (2.5, 6.5),  'y': (1.4, 2.4), 'z': (1.2, 2.2)},
    'TRUCK':      {'x': (4.0, 14.0), 'y': (1.8, 3.2), 'z': (1.8, 4.5)},
    'BUS':        {'x': (6.0, 18.0), 'y': (2.0, 3.2), 'z': (2.5, 4.5)},
    'PEDESTRIAN': {'x': (0.2, 1.2),  'y': (0.2, 1.2), 'z': (1.0, 2.2)},
    'BICYCLE':    {'x': (1.0, 2.2),  'y': (0.3, 1.0), 'z': (1.0, 2.0)},
    'MOTORCYCLE': {'x': (1.2, 2.7),  'y': (0.4, 1.3), 'z': (1.0, 2.0)},
}
VALID_IOU = 0.5  # BEV IoU above which a same-frame pair is flagged as overlapping


def ang_diff(a: float, b: float) -> float:
    """Signed smallest angle difference a-b, in (-pi, pi]."""
    return (a - b + np.pi) % (2 * np.pi) - np.pi


def _dims_heading(box):
    """Normalize a box dict to a uniform (x, y, dx, dy, dz, heading) tuple,
    handling both emission shapes used in this file:
      - NESTED (TrackHandler): center3D.{x,y,z}, size3D.{x,y,z}, rotation3D.z
      - FLAT (AppHandler / SequenceHandler._emit_object): x/y/z, dx/dy/dz, rotZ
    size3D may itself be a dict ({x,y,z}) or a [dx,dy,dz] list/tuple."""
    if 'center3D' in box:
        c = box['center3D']
        s = box['size3D']
        if isinstance(s, dict):
            dx, dy, dz = float(s['x']), float(s['y']), float(s['z'])
        else:
            dx, dy, dz = float(s[0]), float(s[1]), float(s[2])
        return (float(c['x']), float(c['y']), dx, dy, dz,
                float(box['rotation3D']['z']))
    return (float(box['x']), float(box['y']),
            float(box['dx']), float(box['dy']), float(box['dz']),
            float(box['rotZ']))


def _bad_size(label, dx, dy, dz):
    """True iff the box dimensions fall outside VALID_SIZE for its class.
    Unknown classes (not in VALID_SIZE) are never flagged."""
    rng = VALID_SIZE.get(label)
    if rng is None:
        return False
    return not (rng['x'][0] <= dx <= rng['x'][1] and
                rng['y'][0] <= dy <= rng['y'][1] and
                rng['z'][0] <= dz <= rng['z'][1])


def _bev_iou(box_a, box_b):
    """Rotated-2D (bird's-eye-view) IoU of two boxes, each a
    (x, y, dx, dy, heading) tuple. Uses Sutherland-Hodgman polygon clipping of
    the two rotated rectangles -- no external geometry deps."""
    poly_a = _box_corners(box_a)
    poly_b = _box_corners(box_b)
    inter = _poly_area(_clip_poly(poly_a, poly_b))
    if inter <= 0.0:
        return 0.0
    area_a = box_a[2] * box_a[3]
    area_b = box_b[2] * box_b[3]
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def _box_corners(box):
    """Four CCW corners of a rotated BEV rectangle (x, y, dx, dy, heading)."""
    x, y, dx, dy, heading = box
    hx, hy = dx / 2.0, dy / 2.0
    cos_h, sin_h = np.cos(heading), np.sin(heading)
    local = ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))
    return [(x + lx * cos_h - ly * sin_h, y + lx * sin_h + ly * cos_h)
            for lx, ly in local]


def _clip_poly(subject, clip):
    """Sutherland-Hodgman clip of convex polygon `subject` by convex polygon
    `clip` (both CCW). Returns the intersection polygon's vertex list."""
    output = subject
    cn = len(clip)
    for i in range(cn):
        if not output:
            break
        a = clip[i]
        b = clip[(i + 1) % cn]
        # edge a->b; inside = left side for a CCW clip polygon
        edge_x, edge_y = b[0] - a[0], b[1] - a[1]

        def _inside(p):
            return edge_x * (p[1] - a[1]) - edge_y * (p[0] - a[0]) >= 0.0

        inp = output
        output = []
        prev = inp[-1]
        prev_in = _inside(prev)
        for cur in inp:
            cur_in = _inside(cur)
            if cur_in:
                if not prev_in:
                    output.append(_line_intersect(prev, cur, a, b))
                output.append(cur)
            elif prev_in:
                output.append(_line_intersect(prev, cur, a, b))
            prev, prev_in = cur, cur_in
    return output


def _line_intersect(p1, p2, p3, p4):
    """Intersection point of segment p1->p2 with the infinite line p3->p4."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if denom == 0.0:
        return p1
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def _poly_area(poly):
    """Shoelace area of a polygon (>= 0 for any winding)."""
    n = len(poly)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _mark_overlaps(boxes):
    """Set overlap=True on every box of any same-frame pair whose BEV IoU
    exceeds VALID_IOU. `boxes` is a list of emitted box dicts (any shape)."""
    n = len(boxes)
    if n < 2:
        return
    bev = []
    for b in boxes:
        x, y, dx, dy, _dz, heading = _dims_heading(b)
        bev.append((x, y, dx, dy, heading))
    for i in range(n):
        for j in range(i + 1, n):
            if _bev_iou(bev[i], bev[j]) > VALID_IOU:
                boxes[i]['overlap'] = True
                boxes[j]['overlap'] = True

# browser-facing presigned URLs look like {scheme}://{gateway}/minio/<bucket>/<obj>?<sig>.
# the MinIO signature is computed for the path AFTER nginx strips /minio, so the
# in-network equivalent keeps path+query verbatim and only swaps the origin.
_MINIO_PREFIX_RE = re.compile(r'^https?://[^/]+/minio(?=/)')


def normalize_pcd_url(url: str) -> str:
    return _MINIO_PREFIX_RE.sub('http://minio:9000', url)


def download_and_clean(pcd_url: str, t=None):
    r = requests.get(pcd_url, allow_redirects=True, timeout=60)
    r.raise_for_status()
    if t:
        t.log_interval(f"DOWNLOAD pcd({len(r.content)/1024/1024:.2g}MB)")

    pc = PointCloud(io.BytesIO(r.content)).normalized_numpy()
    if t:
        t.log_interval(f"LOAD pcd")

    # remove nan and zeros
    count1 = len(pc)
    pc = pc[~np.isnan(pc[:, :3]).any(axis=1)]
    count2 = len(pc)
    if count2 < count1:
        logging.info(f"\tremove {count1 - count2} nan points")

    pc = pc[(pc[:, :3] != 0).any(axis=1)]
    count3 = len(pc)
    if count3 < count2:
        logging.info(f"\tremove {count2 - count3} zero points")

    # remove low-intensity points (snow noise): raw intensity 0,1,2
    # guard: pcds without intensity field load as (N, 3) — skip filtering
    if pc.shape[1] >= 4:
        count4 = len(pc)
        pc = pc[pc[:, 3] > 2]
        if len(pc) < count4:
            logging.info(f"\tremove {count4 - len(pc)} low-intensity points (raw intensity <= 2)")
    if t:
        t.log_interval(f"VALIDATE points")
    return pc


class AppHandler(BaseApiHandler):
    predictor = None
    full_nms = True

    @staticmethod
    def _supports_full_nms(model):
        # query-based models (e.g. TransFusion) have no DENSE_HEAD.POST_PROCESSING.NMS_CONFIG;
        # calling Predictor with full_nms=True would raise KeyError for them
        try:
            return 'NMS_CONFIG' in model.model_cfg.DENSE_HEAD.POST_PROCESSING
        except (AttributeError, KeyError, TypeError):
            return False

    # override: Called for each request.
    def initialize(self, cfg_file: str, ckpt: str):
        if AppHandler.predictor is None:
            AppHandler.predictor = Predictor(cfg_file=cfg_file, ckpt=ckpt)
            AppHandler.full_nms = self._supports_full_nms(AppHandler.predictor.model)
            logging.info(f"full_nms={AppHandler.full_nms} (auto-detected from cfg)")

    # override
    def post(self):
        args = self.args
        datas = self.get_field(args, key='datas', type_=list, check_empty=True)

        results = [self.process_data(data) for data in datas]

        # clean up memory to avoid OOM
        gc.collect()

        self.return_ok(results)

    @staticmethod
    def _build_item_error(code: str, message: str, id: int = None):
        return {
            "id": id,
            "code": code,
            "message": message
        }

    def process_data(self, data):
        if not isinstance(data, dict):
            return self._build_item_error("InvalidArgument", "data must be a dictionary")

        id = data.get("id", None)
        if id is None:
            return self._build_item_error("InvalidArgument", 'missing "id"')

        pcd_url = self.get_field(data, key='pointCloudUrl', type_=str)
        if pcd_url is None:
            return self._build_item_error("InvalidArgument", 'missing "pointCloudUrl"')

        try:
            t = Timing()
            logging.info(f"{'-'*10} {pcd_url} {'-'*10}")

            pc = download_and_clean(pcd_url, t=t)

            # predict
            results, _ = self.predictor(points=pc, full_nms=AppHandler.full_nms)
            t.log_interval(f"MODEL run")
            logging.info(f"{pc.shape} => {len(results['pred_boxes'])} objects")
        except Exception as e:
            logging.exception(e)
            return self._build_item_error("SystemError", str(e), id=id)

        class_names = self.predictor.class_names
        objects = [
            {
                "label": class_names[label-1].upper(),
                "confidence": score,

                "x": box[0],
                "y": box[1],
                "z": box[2],
                "dx": box[3],
                "dy": box[4],
                "dz": box[5],
                "rotX": 0,
                "rotY": 0,
                "rotZ": box[6],
                # rule-validation flags (curl-verifiable; stripped by the Java
                # converter before reaching the frontend -- see VALID_SIZE note)
                "bad_size": _bad_size(class_names[label-1].upper(),
                                      box[3], box[4], box[5]),
                "overlap": False,
            }
            for box, score, label in zip(
                results['pred_boxes'].astype(np.float64).round(3).tolist(),
                results['pred_scores'].astype(np.float64).round(3).tolist(),
                results['pred_labels'].tolist())
        ]
        _mark_overlaps(objects)

        return {
            "id": id,
            "code": "OK",
            "message": "",
            "objects": objects
        }


class TrackHandler(AppHandler):
    """Prototype tracking endpoint: propagate seed boxes over target frames by
    re-detecting each frame and matching detections to seeds (BEV nearest within
    a gate); unmatched seeds advance by constant velocity with low confidence.
    Called directly from pc-tool via the gateway nginx (no Java backend involved).
    Inherits initialize() (shared predictor) from AppHandler."""

    # override
    def post(self):
        args = self.args
        seeds = self.get_field(args, key='seedObjects', type_=list, check_empty=True)
        frames = self.get_field(args, key='frames', type_=list, check_empty=True)
        keep = args.get('keep') or {}
        keep_z = bool(keep.get('z', True))          # keep seed height instead of detection z
        keep_rot = bool(keep.get('rotation', True))  # keep seed heading instead of detection heading

        tracks = [self._build_track(seed, keep_z) for seed in seeds]

        # frames are processed in order: each frame's outcome (matched position or
        # constant-velocity prediction) becomes the next frame's reference
        results = [self._track_frame(frame, tracks, keep_z, keep_rot) for frame in frames]

        gc.collect()
        self.return_ok(results)

    @staticmethod
    def _vec(d):
        return np.array([d['x'], d['y'], d['z']], dtype=np.float64)

    def _build_track(self, seed, keep_z):
        pos = self._vec(seed['center3D'])
        prev = seed.get('prevCenter3D') or None
        vel = pos - self._vec(prev) if prev else np.zeros(3, dtype=np.float64)
        if keep_z:
            vel[2] = 0.0
        # class label for bad_size: the pc-tool seed carries modelClass (may be
        # null) but no class-name field; fall back to None -> never flagged.
        label = seed.get('modelClass') or seed.get('label')
        return {
            'id': seed['trackingId'],
            'label': label.upper() if isinstance(label, str) else None,
            'pos': pos,
            'vel': vel,
            'size': seed['size3D'],
            'rot': seed['rotation3D'],
            'heading': float(seed['rotation3D']['z']),
            'miss': 0,
            'active': True,
        }

    @staticmethod
    def _gate(track):
        return min(TRACK_MATCH_GATE_M * (1 + TRACK_GATE_GROWTH * track['miss']),
                   TRACK_GATE_MAX_M)

    def _track_frame(self, frame, tracks, keep_z, keep_rot):
        frame_id = frame.get('id')
        active = [t for t in tracks if t['active']]
        if not active:
            return {'id': frame_id, 'code': 'OK', 'message': '', 'objects': []}
        try:
            t = Timing()
            url = normalize_pcd_url(frame['pointCloudUrl'])
            logging.info(f"{'-'*10} TRACK {frame_id} {url} {'-'*10}")

            pc = download_and_clean(url, t=t)
            det, _ = AppHandler.predictor(points=pc, full_nms=AppHandler.full_nms)
            t.log_interval(f"MODEL run")

            boxes = det['pred_boxes']
            scores = det['pred_scores']
            score_mask = scores >= TRACK_SCORE_FLOOR
            boxes, scores = boxes[score_mask], scores[score_mask]

            matches = self._greedy_match(active, boxes)
            objects = []
            snap_count = 0
            for i, track in enumerate(active):
                j = matches.get(i)
                if j is not None:
                    new_pos = boxes[j, :3].astype(np.float64)
                    if keep_z:
                        new_pos[2] = track['pos'][2]
                    # front/back ambiguity: flip detection heading if it is more
                    # than 90 degrees away from the track's current heading
                    det_heading = float(boxes[j, 6])
                    if abs(ang_diff(det_heading, track['heading'])) > np.pi / 2:
                        det_heading = ang_diff(det_heading + np.pi, 0.0)
                    if not keep_rot:
                        track['heading'] = det_heading
                    track['vel'] = new_pos - track['pos']
                    track['pos'] = new_pos
                    track['miss'] = 0
                    confidence = float(scores[j])
                else:
                    pred = track['pos'] + track['vel']
                    snap_xy = self._snap_to_points(pc, pred, track['size'], self._gate(track))
                    if snap_xy is not None:
                        new_pos = np.array([snap_xy[0], snap_xy[1], pred[2]])
                        snap_count += 1
                    else:
                        new_pos = pred.copy()
                    if keep_z:
                        new_pos[2] = track['pos'][2]
                    if snap_xy is not None:
                        # snapping is weak evidence: let it steer the velocity too
                        track['vel'] = new_pos - track['pos']
                    track['pos'] = new_pos
                    track['miss'] += 1
                    confidence = TRACK_FALLBACK_CONFIDENCE
                    if track['miss'] > TRACK_MAX_MISSES:
                        track['active'] = False
                        logging.info(f"TRACK {track['id']}: deactivated after "
                                     f"{track['miss']} consecutive misses")
                        continue
                size = track['size']
                # fallback boxes (constant-velocity propagations) are exempt from
                # hard size failure -- they are not fresh detections
                is_fallback = confidence == TRACK_FALLBACK_CONFIDENCE
                bad_size = (not is_fallback) and _bad_size(
                    track['label'],
                    float(size['x']), float(size['y']), float(size['z']))
                objects.append({
                    'trackingId': track['id'],
                    'center3D': {'x': float(track['pos'][0]),
                                 'y': float(track['pos'][1]),
                                 'z': float(track['pos'][2])},
                    'size3D': size,
                    'rotation3D': {'x': float(track['rot']['x']),
                                   'y': float(track['rot']['y']),
                                   'z': float(track['heading'])},
                    'confidence': confidence,
                    'bad_size': bad_size,
                    'overlap': False,
                })
            _mark_overlaps(objects)
            logging.info(f"TRACK {frame_id}: {len(boxes)} detections, "
                         f"{len(matches)}/{len(active)} matched, {snap_count} snapped")
            return {'id': frame_id, 'code': 'OK', 'message': '', 'objects': objects}
        except Exception as e:
            logging.exception(e)
            # keep the chain alive: advance active tracks by velocity so the next
            # frame's matching does not use a stale reference (no miss counted —
            # a download/server error says nothing about the object)
            for track in active:
                track['pos'] = track['pos'] + track['vel']
            return {'id': frame_id, 'code': 'SystemError', 'message': str(e), 'objects': []}

    @staticmethod
    def _snap_to_points(pc, pred, size, max_shift):
        """Fallback refinement: median BEV center of points inside the predicted
        box footprint (square window, z limited to the box's vertical span above
        ground level). Returns xy or None when too few points."""
        radius = max(float(size['x']), float(size['y'])) * TRACK_SNAP_RADIUS_SCALE
        mask = (np.abs(pc[:, 0] - pred[0]) < radius) & (np.abs(pc[:, 1] - pred[1]) < radius)
        pts = pc[mask]
        z_lo = pred[2] - float(size['z']) / 2 + 0.3   # skip road-surface points
        z_hi = pred[2] + float(size['z']) / 2 + 0.5
        pts = pts[(pts[:, 2] > z_lo) & (pts[:, 2] < z_hi)]
        if len(pts) < TRACK_SNAP_MIN_POINTS:
            return None
        center = np.median(pts[:, :2], axis=0)
        shift = center - pred[:2]
        dist = float(np.linalg.norm(shift))
        if dist > max_shift:   # never jump further than the matching gate
            center = pred[:2] + shift / dist * max_shift
        return center

    @classmethod
    def _greedy_match(cls, tracks, boxes):
        """Greedy 1:1 assignment of tracks to detections by BEV center distance.
        Each track's gate widens with its consecutive-miss count."""
        matches = {}
        if len(boxes) == 0 or len(tracks) == 0:
            return matches
        gates = np.array([cls._gate(t) for t in tracks])
        predicted = np.stack([t['pos'] + t['vel'] for t in tracks])     # (T, 3)
        dists = np.linalg.norm(
            predicted[:, None, :2] - boxes[None, :, :2], axis=2)       # (T, D)
        pairs = [(dists[i, j], i, j)
                 for i in range(dists.shape[0])
                 for j in range(dists.shape[1])
                 if dists[i, j] <= gates[i]]
        used_dets = set()
        for _, i, j in sorted(pairs):
            if i in matches or j in used_dets:
                continue
            matches[i] = j
            used_dets.add(j)
        return matches


class SequenceHandler(AppHandler):
    """Detection-driven sequence detection+tracking endpoint (/pointCloud/sequence).

    This is the INVERSE of TrackHandler. TrackHandler propagates a fixed set of
    seed boxes (discarding unmatched detections and emitting synthetic
    constant-velocity/snap boxes). Here "detection is truth":
      - every frame is fully detected (shared predictor + intensity<=2 filter);
      - detections are associated to active tracks only to carry the trackingId
        forward (greedy BEV match against constant-velocity predictions);
      - a matched track is updated with the DETECTION's geometry (box=detection,
        not a fixed seed size); keep_z/keep_rot default False -> use detection
        z and heading;
      - an UNMATCHED DETECTION spawns a NEW track (monotonic per-call id);
      - an UNMATCHED TRACK only increments miss (terminated after
        TRACK_MAX_MISSES) and emits NOTHING -- no synthetic fallback boxes.
    Only real detections appear in the output. Called server-to-server from the
    Java backend (chunked sequence). Inherits initialize() (shared predictor)
    and reuses _greedy_match/_gate/ang_diff/download_and_clean/TRACK_* from
    AppHandler/TrackHandler.
    """

    # override
    def post(self):
        args = self.args
        frames = self.get_field(args, key='frames', type_=list, check_empty=True)
        seeds = args.get('seedObjects') or []
        keep = args.get('keep') or {}
        keep_z = bool(keep.get('z', False))          # detection is truth -> default False
        keep_rot = bool(keep.get('rotation', False))

        # monotonic per-call trackingId counter; never below backend-provided floor
        # (startId) so new ids are globally monotonic across chunks even when all
        # prior tracks have terminated (avoids reusing a dead track's id)
        seed_ids = [int(s['trackingId']) for s in seeds if s.get('trackingId') is not None]
        start_id = int(args.get('startId') or 0)
        self._next_id = max(start_id, (max(seed_ids) + 1) if seed_ids else 0)

        tracks = [self._build_seed_track(seed, keep_z) for seed in seeds]

        # frames are processed in order. The frame[0]-vs-frame[i>0] distinction
        # the spec calls for is handled uniformly: at frame[0] the active tracks
        # are exactly the seeds (or none), so detections greedy-match the seeds
        # for ID continuity and unmatched detections spawn new tracks -- same
        # code path as every later frame.
        out_frames = [self._process_frame(frame, tracks, keep_z, keep_rot)
                      for frame in frames]

        # clean up memory to avoid OOM (mirrors AppHandler.post)
        gc.collect()

        self.return_ok({
            'frames': out_frames,
            'trackStates': self._track_states(tracks),
        })

    def _alloc_id(self):
        tid = self._next_id
        self._next_id += 1
        return tid

    @staticmethod
    def _vec(x, y, z):
        return np.array([float(x), float(y), float(z)], dtype=np.float64)

    def _build_seed_track(self, seed, keep_z):
        """Build an active track from a chunk-continuity seed (flat geometry)."""
        pos = self._vec(seed['x'], seed['y'], seed['z'])
        has_prev = seed.get('prevX') is not None
        if has_prev:
            prev = self._vec(seed['prevX'], seed['prevY'], seed['prevZ'])
            vel = pos - prev
        else:
            vel = np.zeros(3, dtype=np.float64)
        if keep_z:
            vel[2] = 0.0
        return {
            'id': int(seed['trackingId']),
            'label': seed['label'],
            'pos': pos,
            'vel': vel,
            'size': [float(seed['dx']), float(seed['dy']), float(seed['dz'])],
            'heading': float(seed['rotZ']),
            'confidence': float(seed.get('confidence', TRACK_FALLBACK_CONFIDENCE)),
            'miss': 0,
            'active': True,
            'emitted': False,   # whether the track produced an object in the current frame
        }

    def _spawn_track(self, box, score, label):
        """Create a new track from an unmatched detection (box = (7,) array).
        A new track always adopts the detection's full geometry (z + heading),
        so keep_z/keep_rot do not apply here."""
        pos = box[:3].astype(np.float64).copy()
        track = {
            'id': self._alloc_id(),
            'label': label,
            'pos': pos,
            'vel': np.zeros(3, dtype=np.float64),
            'size': [float(box[3]), float(box[4]), float(box[5])],
            'heading': float(box[6]),
            'confidence': float(score),
            'miss': 0,
            'active': True,
            'emitted': False,
        }
        return track

    def _update_track(self, track, box, score, keep_z, keep_rot):
        """Update a matched track with the detection geometry (box = (7,) array)."""
        new_pos = box[:3].astype(np.float64).copy()
        if keep_z:
            new_pos[2] = track['pos'][2]
        # front/back ambiguity: flip detection heading if it is more than 90
        # degrees away from the track's current heading (same rule as TrackHandler)
        det_heading = float(box[6])
        if abs(ang_diff(det_heading, track['heading'])) > np.pi / 2:
            det_heading = ang_diff(det_heading + np.pi, 0.0)
        if not keep_rot:
            track['heading'] = det_heading
        track['vel'] = new_pos - track['pos']
        track['pos'] = new_pos
        # box geometry is always the detection's (detection is truth); keep_z/
        # keep_rot only govern the z/heading components handled above
        track['size'] = [float(box[3]), float(box[4]), float(box[5])]
        track['confidence'] = float(score)
        track['miss'] = 0

    def _emit_object(self, track):
        """Flat object matching the /pointCloud/recognition shape + trackingId."""
        dx, dy, dz = (round(float(track['size'][0]), 3),
                      round(float(track['size'][1]), 3),
                      round(float(track['size'][2]), 3))
        # fallback boxes (propagated, confidence==0.1) are exempt from hard
        # size failure; overlap is set per-frame in _process_frame
        is_fallback = float(track['confidence']) == TRACK_FALLBACK_CONFIDENCE
        label = track['label'].upper() if isinstance(track['label'], str) else None
        bad_size = (not is_fallback) and _bad_size(label, dx, dy, dz)
        return {
            'trackingId': track['id'],
            'label': track['label'],
            'confidence': round(float(track['confidence']), 3),
            'x': round(float(track['pos'][0]), 3),
            'y': round(float(track['pos'][1]), 3),
            'z': round(float(track['pos'][2]), 3),
            'dx': dx,
            'dy': dy,
            'dz': dz,
            'rotX': 0,
            'rotY': 0,
            'rotZ': round(float(track['heading']), 3),
            'bad_size': bad_size,
            'overlap': False,
        }

    def _track_states(self, tracks):
        """Active tracks at the LAST processed frame -> next chunk's seedObjects.
        prev* is the previous-frame center (pos - vel) so the next chunk can
        reconstruct velocity for constant-velocity prediction."""
        states = []
        for t in tracks:
            if not t['active']:
                continue
            prev = t['pos'] - t['vel']
            states.append({
                'trackingId': t['id'],
                'label': t['label'],
                'x': round(float(t['pos'][0]), 3),
                'y': round(float(t['pos'][1]), 3),
                'z': round(float(t['pos'][2]), 3),
                'dx': round(float(t['size'][0]), 3),
                'dy': round(float(t['size'][1]), 3),
                'dz': round(float(t['size'][2]), 3),
                'rotZ': round(float(t['heading']), 3),
                'prevX': round(float(prev[0]), 3),
                'prevY': round(float(prev[1]), 3),
                'prevZ': round(float(prev[2]), 3),
            })
        return states

    def _process_frame(self, frame, tracks, keep_z, keep_rot):
        frame_id = frame.get('id')
        try:
            t = Timing()
            url = normalize_pcd_url(frame['pointCloudUrl'])
            logging.info(f"{'-'*10} SEQUENCE {frame_id} {url} {'-'*10}")

            pc = download_and_clean(url, t=t)
            det, _ = AppHandler.predictor(points=pc, full_nms=AppHandler.full_nms)
            t.log_interval(f"MODEL run")

            boxes = det['pred_boxes']
            scores = det['pred_scores']
            labels = det['pred_labels']
            # drop low-score detections (same floor TrackHandler uses)
            score_mask = scores >= TRACK_SCORE_FLOOR
            boxes = boxes[score_mask]
            scores = scores[score_mask]
            labels = labels[score_mask]
            class_names = self.predictor.class_names
        except Exception as e:
            logging.exception(e)
            # advance active tracks by velocity and count the frame as a miss so
            # ghost tracks are eventually terminated during an outage rather than
            # drifting forever; same lifecycle as a normal unmatched frame
            for tr in tracks:
                if tr['active']:
                    tr['pos'] = tr['pos'] + tr['vel']
                    tr['miss'] += 1
                    if tr['miss'] > TRACK_MAX_MISSES:
                        tr['active'] = False
            return {'id': frame_id, 'objects': [], 'frameError': True}

        # frame[0]: match detections against incoming seeds for ID continuity;
        # frame[i>0]: match detections against active tracks (CV prediction).
        # In both cases _greedy_match associates by BEV center distance with a
        # per-track gate that widens with consecutive misses.
        for tr in tracks:
            tr['emitted'] = False
        active = [tr for tr in tracks if tr['active']]

        # reuse TrackHandler's greedy BEV matcher + gate (SequenceHandler does
        # not inherit TrackHandler -- only its association primitives are reused)
        matches = TrackHandler._greedy_match(active, boxes)   # {track_idx: det_idx}
        matched_dets = set(matches.values())

        objects = []
        # 1) matched tracks -> update with detection geometry, emit
        for i, track in enumerate(active):
            j = matches.get(i)
            if j is None:
                continue
            self._update_track(track, boxes[j], float(scores[j]), keep_z, keep_rot)
            track['emitted'] = True
            objects.append(self._emit_object(track))

        # 2) unmatched detections -> spawn a NEW track, emit
        for j in range(len(boxes)):
            if j in matched_dets:
                continue
            label = class_names[int(labels[j]) - 1].upper()
            new_track = self._spawn_track(boxes[j], float(scores[j]), label)
            tracks.append(new_track)
            new_track['emitted'] = True
            objects.append(self._emit_object(new_track))

        # 3) unmatched active tracks -> miss++, predict pos forward (for next
        # frame's matching only), terminate after TRACK_MAX_MISSES. NO synthetic
        # box is emitted for an unmatched track (detection is truth).
        for track in active:
            if track['emitted']:
                continue
            track['pos'] = track['pos'] + track['vel']
            track['miss'] += 1
            if track['miss'] > TRACK_MAX_MISSES:
                track['active'] = False
                logging.info(f"SEQUENCE {track['id']}: terminated after "
                             f"{track['miss']} consecutive misses")

        _mark_overlaps(objects)
        logging.info(f"SEQUENCE {frame_id}: {len(boxes)} detections, "
                     f"{len(matches)}/{len(active)} matched, "
                     f"{len(boxes) - len(matched_dets)} new tracks")
        return {'id': frame_id, 'objects': objects}


# model presets: cfg + default checkpoint. full_nms is auto-detected from the cfg,
# so any OpenPCDet model can also be served via explicit --cfg/--ckpt without code changes.
# OpenPCDet tools/cfgs yamls resolve _BASE_CONFIG_ relative to working_dir (/app/pcdet_open).
MODELS = {
    'centerpoint': {
        'cfg': 'cfgs/nuscenes_models/cbgs_voxel0075_res3d_centerpoint.yaml',  # relative to app dir
        'ckpt': '/app/cbgs_voxel0075_centerpoint_nds_6648.pth',               # shipped in image
    },
    'transfusion': {
        'cfg': '/app/OpenPCDet/tools/cfgs/nuscenes_models/transfusion_lidar.yaml',
        'ckpt': '/app/cbgs_transfusion_lidar.pth',                            # mount via compose
    },
    'voxelnext': {
        'cfg': '/app/OpenPCDet/tools/cfgs/nuscenes_models/cbgs_voxel0075_voxelnext.yaml',
        'ckpt': '/app/cbgs_voxel0075_voxelnext.pth',                          # mount via compose
    },
}


def main():
    parser = ArgumentParser()
    parser.add_argument('--model', type=str, default='centerpoint', choices=sorted(MODELS),
                        help='model preset (cfg + default checkpoint)')
    parser.add_argument('--cfg', type=str, default=None, help='override cfg yaml path')
    parser.add_argument('--ckpt', type=str, default=None, help='override checkpoint path')
    args = parse_args(parser)

    app_dir = dirname(abspath(__file__))
    preset = MODELS[args.model]
    cfg_file = args.cfg or join(app_dir, preset['cfg'])
    ckpt = args.ckpt or preset['ckpt']
    logging.info(f"model={args.model} cfg={cfg_file} ckpt={ckpt}")

    start_service([
            (r'/pointCloud/recognition', AppHandler, dict(cfg_file=cfg_file, ckpt=ckpt)),
            (r'/pointCloud/track', TrackHandler, dict(cfg_file=cfg_file, ckpt=ckpt)),
            (r'/pointCloud/sequence', SequenceHandler, dict(cfg_file=cfg_file, ckpt=ckpt)),
        ],
        args)


if __name__ == '__main__':
    main()
