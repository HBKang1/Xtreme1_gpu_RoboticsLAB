#!/usr/bin/env python3
"""Restore the intensity channel of zenix dataset .pcd files in place.

The original bag->pcd conversion dropped intensity (FIELDS x y z). The
intermediate KITTI-style raw dumps (raw_0124/raw_0224, float32 x,y,z,intensity)
preserve it, and verification showed dataset pcds keep the EXACT point order
and coordinates of the raw .bin frames. So restoration is: read the pcd's own
xyz (unchanged -> GT annotations stay valid), verify byte-equality against the
matching raw .bin, append the bin's intensity column, rewrite as binary pcd
`FIELDS x y z intensity`.

Mapping (verified):
  dataset file  z{NN}-{TS}[_{sensordir}]_{FRAME}.pcd
  raw frame     {raw_root}/{NN}_{TS}/{sensor}/data/{FRAME}.bin
  sensor dir    point_cloud_16|lidar_point_cloud_16 -> velodyne_points
                lidar_point_cloud_0|lidar_point_cloud_64 -> hesai64_hesai_pandar

Idempotent: pcds that already contain intensity are skipped. Writes are atomic
(tmp + rename). Per-file results go to an ndjson log for the report.

Usage:
  python3 restore_intensity.py --apply            # full run (both datasets)
  python3 restore_intensity.py --limit 20         # dry-run sample (no --apply = dry-run)
  python3 restore_intensity.py --apply --only dataset_0224
"""
import argparse
import json
import os
import re
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ZENIX = Path('/home/a/dataset_custom/zenix_dataset')
PAIRS = {'dataset_0124': 'raw_0124', 'dataset_0224': 'raw_0224'}
SENSOR_MAP = {
    'point_cloud_16': 'velodyne_points',
    'lidar_point_cloud_16': 'velodyne_points',
    'lidar_point_cloud_0': 'hesai64_hesai_pandar',
    'lidar_point_cloud_64': 'hesai64_hesai_pandar',
}
NAME_RE = re.compile(r'^z(\d+)-(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})(?:_lidar_point_cloud_\d+)?_(\d{10})\.pcd$')


def parse_pcd_header(f):
    header = {}
    while True:
        line = f.readline().decode('ascii', errors='ignore').strip()
        key, _, value = line.partition(' ')
        header[key.upper()] = value
        if key.upper() == 'DATA':
            return header


def restore_one(args):
    pcd_path, raw_root, apply_changes = args
    rec = {'file': str(pcd_path)}
    try:
        m = NAME_RE.match(pcd_path.name)
        if not m:
            return {**rec, 'status': 'skip', 'reason': 'unrecognized filename'}
        scene_no, ts, frame = m.groups()
        sensor = SENSOR_MAP.get(pcd_path.parent.name)
        if sensor is None:
            return {**rec, 'status': 'skip', 'reason': f'unknown sensor dir {pcd_path.parent.name}'}
        bin_path = raw_root / f'{scene_no}_{ts}' / sensor / 'data' / f'{frame}.bin'
        if not bin_path.exists():
            return {**rec, 'status': 'skip', 'reason': f'raw bin missing: {bin_path}'}

        with open(pcd_path, 'rb') as f:
            header = parse_pcd_header(f)
            fields = header.get('FIELDS', '')
            if fields == 'x y z intensity':
                return {**rec, 'status': 'already', 'reason': 'intensity present'}
            if fields != 'x y z' or header.get('DATA') != 'binary':
                return {**rec, 'status': 'skip', 'reason': f'unexpected format: {fields}/{header.get("DATA")}'}
            n = int(header['POINTS'])
            xyz = np.frombuffer(f.read(n * 12), dtype=np.float32).reshape(-1, 3)
            if xyz.shape[0] != n:
                return {**rec, 'status': 'skip', 'reason': 'truncated pcd payload'}

        raw = np.fromfile(bin_path, dtype=np.float32)
        if raw.size % 4:
            return {**rec, 'status': 'skip', 'reason': 'bin size not multiple of 16'}
        raw = raw.reshape(-1, 4)
        if raw.shape[0] != n or not np.array_equal(xyz, raw[:, :3]):
            # order/coordinate mismatch — refuse rather than guess
            return {**rec, 'status': 'mismatch',
                    'reason': f'pcd {n} pts vs bin {raw.shape[0]} pts, order-exact failed'}

        rec['points'] = n
        rec['intensity_min'] = float(raw[:, 3].min())
        rec['intensity_max'] = float(raw[:, 3].max())
        if not apply_changes:
            return {**rec, 'status': 'would-restore'}

        out = np.empty((n, 4), dtype=np.float32)
        out[:, :3] = xyz
        out[:, 3] = raw[:, 3]
        viewpoint = header.get('VIEWPOINT', '0 0 0 1 0 0 0')
        new_header = (
            '# .PCD v0.7 - Point Cloud Data file format\n'
            'VERSION 0.7\n'
            'FIELDS x y z intensity\n'
            'SIZE 4 4 4 4\n'
            'TYPE F F F F\n'
            'COUNT 1 1 1 1\n'
            f'WIDTH {n}\n'
            'HEIGHT 1\n'
            f'VIEWPOINT {viewpoint}\n'
            f'POINTS {n}\n'
            'DATA binary\n'
        ).encode('ascii')
        tmp = pcd_path.with_suffix('.pcd.tmp')
        with open(tmp, 'wb') as f:
            f.write(new_header)
            f.write(out.tobytes())
        os.replace(tmp, pcd_path)
        return {**rec, 'status': 'restored'}
    except Exception as e:
        return {**rec, 'status': 'error', 'reason': repr(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='actually rewrite files (default: dry-run)')
    ap.add_argument('--only', choices=list(PAIRS), help='restrict to one dataset')
    ap.add_argument('--limit', type=int, help='process at most N files (sampling/dry-run)')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--log', type=Path, default=Path('/tmp/restore_intensity.ndjson'))
    args = ap.parse_args()

    tasks = []
    for ds, raw in PAIRS.items():
        if args.only and ds != args.only:
            continue
        raw_root = ZENIX / raw
        for sensor_dir in SENSOR_MAP:
            for pcd in (ZENIX / ds).glob(f'*/{sensor_dir}/*.pcd'):
                tasks.append((pcd, raw_root, args.apply))
    tasks.sort(key=lambda t: str(t[0]))
    if args.limit:
        step = max(1, len(tasks) // args.limit)
        tasks = tasks[::step][:args.limit]
    print(f'{len(tasks)} pcd files queued (apply={args.apply})', flush=True)

    counts, t0 = {}, time.time()
    with open(args.log, 'w') as logf, Pool(args.workers) as pool:
        for i, rec in enumerate(pool.imap_unordered(restore_one, tasks, chunksize=16)):
            counts[rec['status']] = counts.get(rec['status'], 0) + 1
            if rec['status'] not in ('restored', 'already', 'would-restore'):
                logf.write(json.dumps(rec, ensure_ascii=False) + '\n')
            if (i + 1) % 5000 == 0:
                rate = (i + 1) / (time.time() - t0)
                print(f'{i+1}/{len(tasks)} ({rate:.0f}/s) {counts}', flush=True)
        logf.write(json.dumps({'summary': counts, 'total': len(tasks)}) + '\n')
    print(f'DONE in {time.time()-t0:.0f}s: {counts}', flush=True)
    bad = sum(v for k, v in counts.items() if k in ('mismatch', 'error'))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
