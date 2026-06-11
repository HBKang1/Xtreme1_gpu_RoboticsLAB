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


def ang_diff(a: float, b: float) -> float:
    """Signed smallest angle difference a-b, in (-pi, pi]."""
    return (a - b + np.pi) % (2 * np.pi) - np.pi

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
                "rotZ": box[6]
            }
            for box, score, label in zip(
                results['pred_boxes'].astype(np.float64).round(3).tolist(),
                results['pred_scores'].astype(np.float64).round(3).tolist(),
                results['pred_labels'].tolist())
        ]

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
        return {
            'id': seed['trackingId'],
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
                objects.append({
                    'trackingId': track['id'],
                    'center3D': {'x': float(track['pos'][0]),
                                 'y': float(track['pos'][1]),
                                 'z': float(track['pos'][2])},
                    'size3D': track['size'],
                    'rotation3D': {'x': float(track['rot']['x']),
                                   'y': float(track['rot']['y']),
                                   'z': float(track['heading'])},
                    'confidence': confidence,
                })
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
        ],
        args)


if __name__ == '__main__':
    main()
