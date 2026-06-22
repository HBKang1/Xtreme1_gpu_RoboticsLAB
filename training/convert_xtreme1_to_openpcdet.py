#!/usr/bin/env python3
"""Convert an Xtreme1 LIDAR_BASIC export (+ source .pcd files) into the
OpenPCDet CustomDataset layout for fine-tuning.

Input
  --export    Xtreme1 export zip or extracted directory. Layout per data item:
                data/<name>.json    -> lidarPointClouds[0].filename (source pcd)
                result/<name>.json  -> [{sourceName, objects:[{type:"3D_BOX",
                                         className, contour:{center3D,size3D,rotation3D}}]}]
              (scene exports nest the same data/ + result/ pairs one level deeper)
  --pcd-root  One or more directories searched recursively for the source .pcd
              files (duplicate basenames across roots abort the run).

Output (OpenPCDet custom dataset, see docs/CUSTOM_DATASET_TUTORIAL.md)
  <out>/points/<frame>.npy   float32 [N,4] = x,y,z,intensity (0 when pcd has none).
                             intensity follows the serving pipeline: raw>2 filter
                             then raw/255 into [0,1] (deploy app.py:60-66).
  <out>/labels/<frame>.txt   "x y z dx dy dz heading category" per object
  <out>/ImageSets/{train,val}.txt

  Optional --fov-sector <fov_sector.json> (from analyze_fov.py) crops points to
  the front sector and asserts every GT box center lies inside it.

Usage
  python3 convert_xtreme1_to_openpcdet.py \
      --export ~/Downloads/zenix-export.zip \
      --pcd-root /home/a/dataset_custom/zenix_dataset/dataset_0124 \
                 /home/a/dataset_custom/zenix_dataset/dataset_0224 \
      --fov-sector training/fov_sector.json \
      --output ./data/zenix
"""
import argparse
import json
import math
import re
import sys
import zipfile
import random
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np

PCD_TYPE_MAP = {('F', 4): 'f4', ('F', 8): 'f8',
                ('I', 1): 'i1', ('I', 2): 'i2', ('I', 4): 'i4',
                ('U', 1): 'u1', ('U', 2): 'u2', ('U', 4): 'u4'}


def read_pcd(path: Path):
    """Return (float32 [N,4] x,y,z,intensity, has_intensity) from a disk pcd."""
    with open(path, 'rb') as f:
        return _parse_pcd_stream(f, str(path))


def read_pcd_url(url: str):
    """Same as read_pcd but fetches the pcd bytes from a MinIO presigned URL.

    Used for datasets whose disk pcd names don't match the Xtreme1 export names
    (e.g. Day datasets renamed by a2z); the export's url points at the exact pcd
    that was annotated, so GT alignment is guaranteed. urllib (not requests)
    keeps the presigned sigv4 query intact, like download_zip.
    """
    import io
    import urllib.request
    with urllib.request.urlopen(urllib.request.Request(url), timeout=120) as resp:
        return _parse_pcd_stream(io.BytesIO(resp.read()), url[:80])


def _parse_pcd_stream(f, label: str):
    """Return (float32 [N,4] x,y,z,intensity, has_intensity: bool).

    intensity is returned RAW (no normalization); the main loop applies the
    serving-equivalent pipeline (raw>2 filter, then raw/255). pcds without an
    intensity field load with the column filled with zeros and has_intensity
    False so the loop can mirror serving's "filter only when the cloud has an
    intensity column" guard (deploy app.py:62 `pc.shape[1] >= 4`).
    """
    path = label
    header = {}
    while True:
        line = f.readline().decode('ascii', errors='ignore').strip()
        if not line or line.startswith('#'):
            continue
        key, _, value = line.partition(' ')
        header[key.upper()] = value
        if key.upper() == 'DATA':
            break
    fields = header['FIELDS'].split()
    sizes = list(map(int, header['SIZE'].split()))
    types = header['TYPE'].split()
    counts = list(map(int, header.get('COUNT', ' '.join(['1'] * len(fields))).split()))
    n_points = int(header['POINTS'])
    data_fmt = header['DATA']

    dtype_fields = []
    for name, size, typ, cnt in zip(fields, sizes, types, counts):
        base = PCD_TYPE_MAP.get((typ, size))
        if base is None:
            raise ValueError(f'{path}: unsupported pcd field {name} {typ}{size}')
        for i in range(cnt):
            dtype_fields.append((f'{name}_{i}' if cnt > 1 else name, base))
    dtype = np.dtype(dtype_fields)

    if data_fmt == 'binary':
        raw = np.frombuffer(f.read(dtype.itemsize * n_points), dtype=dtype, count=n_points)
    elif data_fmt == 'ascii':
        raw = np.loadtxt(f, dtype=np.float64, max_rows=n_points)
        raw = np.core.records.fromarrays(raw.T, dtype=np.dtype(
            [(n, 'f8') for n, _ in dtype_fields]))
    else:
        raise ValueError(f'{path}: DATA {data_fmt} not supported (binary_compressed: '
                         f'convert with pypcd/open3d first)')

    out = np.zeros((n_points, 4), dtype=np.float32)
    for i, axis in enumerate(('x', 'y', 'z')):
        out[:, i] = raw[axis].astype(np.float32)
    has_intensity = 'intensity' in raw.dtype.names
    if has_intensity:
        out[:, 3] = raw['intensity'].astype(np.float32)  # raw; filter/scale later
    return out, has_intensity


def load_export(export: Path, workdir: Path) -> Path:
    if export.is_dir():
        return export
    if zipfile.is_zipfile(export):
        dest = workdir / export.stem
        with zipfile.ZipFile(export) as zf:
            zf.extractall(dest)
        return dest
    sys.exit(f'--export {export}: not a directory or zip')


def sanitize(name: str) -> str:
    return re.sub(r'[^0-9A-Za-z_.-]+', '_', name)


def azimuth_in_sector(az: float, sector: dict) -> bool:
    """True when scalar azimuth (deg, (-180,180]) falls inside the FOV sector."""
    lo = sector['azimuth_min_deg']
    hi = sector['azimuth_max_deg']
    if sector.get('wraps'):
        return az >= lo or az <= hi
    return lo <= az <= hi


def crop_to_fov(pts: np.ndarray, sector: dict) -> np.ndarray:
    """Keep only points whose azimuth (deg, (-180,180]) is inside the sector.

    az = degrees(arctan2(y, x)).  wraps=False keeps [min,max]; wraps=True keeps
    az>=min OR az<=max.  range_xy_m (when non-null) adds a horizontal-distance
    cap.  Mirrors training/analyze_fov.py's azimuth convention.
    """
    if pts.shape[0] == 0:
        return pts
    az = np.degrees(np.arctan2(pts[:, 1], pts[:, 0]))  # (-180, 180]
    lo = sector['azimuth_min_deg']
    hi = sector['azimuth_max_deg']
    if sector.get('wraps'):
        keep = (az >= lo) | (az <= hi)
    else:
        keep = (az >= lo) & (az <= hi)
    range_xy = sector.get('range_xy_m')
    if range_xy is not None:
        r_xy = np.hypot(pts[:, 0], pts[:, 1])
        keep &= r_xy <= float(range_xy)
    return pts[keep]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--export', required=True, type=Path)
    ap.add_argument('--pcd-root', type=Path, nargs='+', default=None,
                    help='one or more directories searched recursively for .pcd '
                         '(duplicate basenames across roots are a fatal error). '
                         'Required unless --from-url.')
    ap.add_argument('--from-url', action='store_true',
                    help='fetch each frame pcd from its Xtreme1 export url (MinIO) '
                         'instead of disk; use for datasets whose disk pcd names '
                         'do not match the export (e.g. a2z-renamed Day datasets)')
    ap.add_argument('--pcd-include-dir', nargs='*', default=['lidar_point_cloud_0'],
                    help='only index .pcd whose immediate parent dir name is in '
                         'this list (default lidar_point_cloud_0 — the Hesai 64ch '
                         'that Xtreme1/serving uses; avoids point_cloud_16 name '
                         'collisions). Pass with no value to index every sensor.')
    ap.add_argument('--pcd-exclude', nargs='*', default=['_old'],
                    help='skip any .pcd whose path contains one of these substrings '
                         '(default _old — stale recording copies on the NAS)')
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--source', default='Ground Truth',
                    help='result sourceName to use (default "Ground Truth" — the '
                         'GROUND_TRUTH_NAME the Xtreme1 export writes)')
    ap.add_argument('--class-map', type=Path, default=None,
                    help='optional JSON {"exported className": "TrainingClass"}')
    ap.add_argument('--fov-sector', type=Path, default=None,
                    help='optional fov_sector.json from analyze_fov.py: crop '
                         'points to the sector and assert all GT lies inside')
    ap.add_argument('--frame-prefix', default='',
                    help='prefix prepended to every frame_id; use a unique value '
                         'per dataset when merging several into one --output to '
                         'avoid cross-dataset frame_id collisions')
    ap.add_argument('--val-ratio', type=float, default=0.1)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--keep-empty', action='store_true',
                    help='also emit frames whose GT has zero objects')
    ap.add_argument('--allow-missing-pcd', action='store_true',
                    help='warn instead of failing when some results have no pcd')
    ap.add_argument('--expected-frames', type=Path, default=None,
                    help='optional JSON: int or {"<key>": int} expected frame '
                         'count; mismatch fails the conversion')
    args = ap.parse_args()

    class_map = json.loads(args.class_map.read_text()) if args.class_map else {}

    sector = json.loads(args.fov_sector.read_text()) if args.fov_sector else None
    if sector is not None:
        print(f'FOV sector [{sector["azimuth_min_deg"]}, '
              f'{sector["azimuth_max_deg"]}] wraps={sector.get("wraps")} '
              f'range_xy_m={sector.get("range_xy_m")}')

    pcd_index = {}
    if not args.from_url:
        if not args.pcd_root:
            sys.exit('--pcd-root is required unless --from-url is given')
        include_dirs = set(args.pcd_include_dir or [])
        exclude_subs = args.pcd_exclude or []
        for root in args.pcd_root:
            n_root = 0
            for p in root.rglob('*.pcd'):
                if include_dirs and p.parent.name not in include_dirs:
                    continue
                if any(sub in str(p) for sub in exclude_subs):
                    continue
                prev = pcd_index.get(p.name)
                if prev is not None:
                    sys.exit(f'duplicate pcd basename {p.name}:\n  {prev}\n  {p}\n'
                             f'(ambiguous reference — narrow --pcd-include-dir/--pcd-exclude '
                             f'or split the inputs)')
                pcd_index[p.name] = p
                n_root += 1
            print(f'  indexed {n_root} pcd files under {root}'
                  f'{f" (dirs={sorted(include_dirs)})" if include_dirs else ""}')
        if not pcd_index:
            sys.exit(f'no .pcd files under {args.pcd_root} '
                     f'(include_dirs={sorted(include_dirs)}, exclude={exclude_subs})')
        print(f'indexed {len(pcd_index)} pcd files total')
    else:
        print('--from-url: fetching pcds from MinIO export urls (no disk index)')

    points_dir = args.output / 'points'
    labels_dir = args.output / 'labels'
    imagesets = args.output / 'ImageSets'
    for d in (points_dir, labels_dir, imagesets):
        d.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = load_export(args.export, Path(tmp))
        result_files = sorted(root.rglob('result/*.json'))
        if not result_files:
            sys.exit(f'no result/*.json found under {root} — export with annotation results')
        print(f'found {len(result_files)} result files')

        frames, class_hist, skipped = [], Counter(), Counter()
        for rf in result_files:
            name = rf.stem
            data_json = rf.parent.parent / 'data' / rf.name
            try:
                results = json.loads(rf.read_text())
            except json.JSONDecodeError:
                skipped['bad result json'] += 1
                continue
            gt = next((r for r in results if r.get('sourceName') == args.source), None)
            if gt is None:
                skipped[f'no {args.source} source'] += 1
                continue

            objects = []
            for obj in gt.get('objects') or []:
                if obj.get('type') != '3D_BOX':
                    skipped[f"object type {obj.get('type')}"] += 1
                    continue
                contour = obj.get('contour') or {}
                c, s, r = (contour.get(k) or {} for k in ('center3D', 'size3D', 'rotation3D'))
                cls = (obj.get('className') or '').strip()
                cls = class_map.get(cls, cls)
                if not cls:
                    skipped['object without className'] += 1
                    continue
                cls = sanitize(cls)
                try:
                    row = [float(c['x']), float(c['y']), float(c['z']),
                           float(s['x']), float(s['y']), float(s['z']),
                           float(r.get('z', 0.0))]
                except (KeyError, TypeError, ValueError):
                    skipped['malformed contour'] += 1
                    continue
                if sector is not None:
                    box_az = math.degrees(math.atan2(row[1], row[0]))
                    if not azimuth_in_sector(box_az, sector):
                        # the box centre is outside the crop sector, so its points
                        # are being removed — drop the (now point-less) label rather
                        # than keep a degenerate sample. These are the <0.1% outliers
                        # the analyze_fov percentile intentionally excluded.
                        skipped['gt box outside fov'] += 1
                        continue
                objects.append((row, cls))
                class_hist[cls] += 1
            if not objects and not args.keep_empty:
                skipped['frame with empty GT'] += 1
                continue

            # resolve the source pcd from the data json (filename for disk, url for MinIO)
            cloud = None
            if data_json.exists():
                try:
                    info = json.loads(data_json.read_text())
                    clouds = info.get('lidarPointClouds') or []
                    cloud = clouds[0] if clouds else None
                except json.JSONDecodeError:
                    pass
            pcd_path = pcd_url = None
            if args.from_url:
                # MinIO source: the export url points at the exact annotated pcd,
                # sidestepping disk name mismatches (e.g. a2z-renamed Day datasets).
                pcd_url = cloud.get('url') if cloud else None
                if not pcd_url:
                    skipped['pcd url not found'] += 1
                    continue
            else:
                if cloud and cloud.get('filename'):
                    pcd_path = pcd_index.get(Path(cloud['filename']).name)
                if pcd_path is None:
                    pcd_path = pcd_index.get(f'{name}.pcd')
                if pcd_path is None:
                    skipped['pcd not found'] += 1
                    continue

            frame_id = args.frame_prefix + sanitize(name)
            # merge-safety: a frame_id colliding across datasets (same --output)
            # would silently overwrite a prior dataset's npy/labels. Refuse it;
            # use --frame-prefix to namespace per-dataset runs.
            if (points_dir / f'{frame_id}.npy').exists():
                sys.exit(f'frame_id {frame_id!r} already exists in {points_dir} — '
                         f'cross-dataset collision; rerun this dataset with a unique '
                         f'--frame-prefix (or clear --output for a fresh build)')
            try:
                pts, has_intensity = (read_pcd_url(pcd_url) if args.from_url
                                      else read_pcd(pcd_path))
            except ValueError as e:
                print(f'  ! {e}', file=sys.stderr)
                skipped['pcd parse error'] += 1
                continue
            except Exception as e:  # noqa: BLE001 — url fetch (HTTP/URL errors)
                print(f'  ! fetch {pcd_url}: {e}', file=sys.stderr)
                skipped['pcd fetch error'] += 1
                continue
            # crop to FOV sector before intensity processing / save
            if sector is not None:
                pts = crop_to_fov(pts, sector)
            # serving-equivalent intensity pipeline (deploy app.py:62-66):
            # filter raw>2 (snow noise) whenever the cloud has an intensity column
            # (mirrors serving's `pc.shape[1] >= 4` guard), then raw/255 into [0,1].
            if has_intensity and pts.shape[0]:
                pts = pts[pts[:, 3] > 2]
            pts[:, 3] = np.clip(pts[:, 3] / 255.0, 0.0, 1.0)
            # drop degenerate frames: a labelled frame with no points after
            # crop/filter is a "boxes but no cloud" sample that hurts training.
            if pts.shape[0] == 0:
                skipped['empty after crop/filter'] += 1
                continue
            np.save(points_dir / f'{frame_id}.npy', pts)
            with open(labels_dir / f'{frame_id}.txt', 'w') as f:
                for row, cls in objects:
                    f.write(' '.join(f'{v:.4f}' for v in row) + f' {cls}\n')
            frames.append(frame_id)

    if not frames:
        sys.exit('no frames converted — check --export / --pcd-root / --source')

    # hard gate: missing/unfetchable pcds are silent data loss unless allowed
    n_missing = (skipped.get('pcd not found', 0) + skipped.get('pcd url not found', 0)
                 + skipped.get('pcd fetch error', 0))
    if n_missing:
        msg = f'{n_missing} result(s) had no usable pcd (missing/unfetchable)'
        if args.allow_missing_pcd:
            print(f'WARNING: {msg} (continuing: --allow-missing-pcd)', file=sys.stderr)
        else:
            sys.exit(f'{msg} — aborting to avoid silent data loss '
                     f'(pass --allow-missing-pcd to continue)')

    # hard gate: converted frame count must match the expected count when given
    if args.expected_frames is not None:
        spec = json.loads(args.expected_frames.read_text())
        expected = spec if isinstance(spec, int) else sum(spec.values())
        if len(frames) != expected:
            sys.exit(f'expected {expected} frames, converted {len(frames)}')

    random.Random(args.seed).shuffle(frames)
    n_val = max(1, int(len(frames) * args.val_ratio))
    val, train = sorted(frames[:n_val]), sorted(frames[n_val:])
    (imagesets / 'train.txt').write_text('\n'.join(train) + '\n')
    (imagesets / 'val.txt').write_text('\n'.join(val) + '\n')

    print(f'\nconverted {len(frames)} frames -> {args.output}  '
          f'(train {len(train)} / val {len(val)})')
    print('class histogram:')
    for cls, cnt in class_hist.most_common():
        print(f'  {cls:30s} {cnt}')
    if skipped:
        print('skipped:')
        for why, cnt in skipped.most_common():
            print(f'  {why:30s} {cnt}')
    print('\nCLASS_NAMES for the yaml configs (paste into both):')
    print('  CLASS_NAMES: ' + json.dumps([c for c, _ in class_hist.most_common()]))


if __name__ == '__main__':
    main()
