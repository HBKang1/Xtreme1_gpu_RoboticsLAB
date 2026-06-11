#!/usr/bin/env python3
"""Convert an Xtreme1 LIDAR_BASIC export (+ source .pcd files) into the
OpenPCDet CustomDataset layout for fine-tuning.

Input
  --export    Xtreme1 export zip or extracted directory. Layout per data item:
                data/<name>.json    -> lidarPointClouds[0].filename (source pcd)
                result/<name>.json  -> [{sourceName, objects:[{type:"3D_BOX",
                                         className, contour:{center3D,size3D,rotation3D}}]}]
              (scene exports nest the same data/ + result/ pairs one level deeper)
  --pcd-root  Directory searched recursively for the source .pcd files.

Output (OpenPCDet custom dataset, see docs/CUSTOM_DATASET_TUTORIAL.md)
  <out>/points/<frame>.npy   float32 [N,4] = x,y,z,intensity (0 when pcd has none)
  <out>/labels/<frame>.txt   "x y z dx dy dz heading category" per object
  <out>/ImageSets/{train,val}.txt

Usage
  python3 convert_xtreme1_to_openpcdet.py \
      --export ~/Downloads/zenix-export.zip \
      --pcd-root /home/a/dataset_custom/zenix_dataset/dataset_0124 \
      --output ./data/zenix
"""
import argparse
import json
import re
import struct
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


def read_pcd(path: Path) -> np.ndarray:
    """Return float32 [N,4] (x,y,z,intensity). Supports ascii/binary pcd."""
    with open(path, 'rb') as f:
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
    if 'intensity' in raw.dtype.names:
        inten = raw['intensity'].astype(np.float32)
        lo, hi = float(inten.min(initial=0.0)), float(inten.max(initial=0.0))
        if hi > 1.0:  # normalize to [0,1] like the serving wrapper does
            inten = (inten - lo) / max(hi - lo, 1e-6)
        out[:, 3] = inten
    return out


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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--export', required=True, type=Path)
    ap.add_argument('--pcd-root', required=True, type=Path)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--source', default='GROUND_TRUTH',
                    help='result sourceName to use (default GROUND_TRUTH)')
    ap.add_argument('--class-map', type=Path, default=None,
                    help='optional JSON {"exported className": "TrainingClass"}')
    ap.add_argument('--val-ratio', type=float, default=0.1)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--keep-empty', action='store_true',
                    help='also emit frames whose GT has zero objects')
    args = ap.parse_args()

    class_map = json.loads(args.class_map.read_text()) if args.class_map else {}

    pcd_index = {}
    for p in args.pcd_root.rglob('*.pcd'):
        pcd_index.setdefault(p.name, p)
    if not pcd_index:
        sys.exit(f'no .pcd files under {args.pcd_root}')
    print(f'indexed {len(pcd_index)} pcd files under {args.pcd_root}')

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
                objects.append((row, cls))
                class_hist[cls] += 1
            if not objects and not args.keep_empty:
                skipped['frame with empty GT'] += 1
                continue

            # resolve the source pcd: data json filename first, then <name>.pcd
            pcd_path = None
            if data_json.exists():
                try:
                    info = json.loads(data_json.read_text())
                    clouds = info.get('lidarPointClouds') or []
                    if clouds and clouds[0].get('filename'):
                        pcd_path = pcd_index.get(Path(clouds[0]['filename']).name)
                except json.JSONDecodeError:
                    pass
            if pcd_path is None:
                pcd_path = pcd_index.get(f'{name}.pcd')
            if pcd_path is None:
                skipped['pcd not found'] += 1
                continue

            frame_id = sanitize(name)
            try:
                pts = read_pcd(pcd_path)
            except ValueError as e:
                print(f'  ! {e}', file=sys.stderr)
                skipped['pcd parse error'] += 1
                continue
            np.save(points_dir / f'{frame_id}.npy', pts)
            with open(labels_dir / f'{frame_id}.txt', 'w') as f:
                for row, cls in objects:
                    f.write(' '.join(f'{v:.4f}' for v in row) + f' {cls}\n')
            frames.append(frame_id)

    if not frames:
        sys.exit('no frames converted — check --export / --pcd-root / --source')

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
