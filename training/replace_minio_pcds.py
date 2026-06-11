#!/usr/bin/env python3
"""Replace Xtreme1 MinIO pcd objects with intensity-restored disk pcds.

Stage 1 (Night-series): targets are DB `file` records whose name is the
original z{NN}-{ts}_{frame}.pcd disk filename. For each record:
  1. find disk candidates by exact filename under dataset_0124 sensor dirs
  2. disambiguate velodyne/hesai (and scene-copy dirs) by point count:
     the old object size must equal header+N*12 of the candidate
  3. PUT the restored pcd (FIELDS x y z intensity) over the original key
  4. PUT the same payload with header field renamed to `i` over the
     binary-* key (matches the pcd-tools binary format; render untouched)
  5. record new sizes for a later batched `UPDATE file SET size=...`

Resume-safe: successful ids are appended to done.ids and skipped on rerun.
No DB writes here — sizes are written to sizes.tsv for a separate step.

Usage:
  python3 replace_minio_pcds.py --targets night_targets.tsv [--limit 5] [--apply]
"""
import argparse
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from minio import Minio

DATASET_ROOT = Path('/home/a/dataset_custom/zenix_dataset/dataset_0124')
SENSOR_DIRS = ('point_cloud_16', 'lidar_point_cloud_0')
ENDPOINT, ACCESS, SECRET = 'localhost:8193', 'admin', '1tQB970y'
HDR_SLACK = 80  # allowed |old_size - (N*12 + 196)| for matching


def parse_header(buf):
    """Return (header_dict, header_len) from pcd bytes."""
    h, pos = {}, 0
    while True:
        nl = buf.index(b'\n', pos)
        line = buf[pos:nl].decode('ascii', 'ignore').strip()
        pos = nl + 1
        k, _, v = line.partition(' ')
        h[k.upper()] = v
        if k.upper() == 'DATA':
            return h, pos


def read_points_count(path):
    with open(path, 'rb') as f:
        head = f.read(400)
    h, _ = parse_header(head)
    return int(h['POINTS'])


class Replacer:
    def __init__(self, apply_changes, workdir):
        self.apply = apply_changes
        self.cli = Minio(ENDPOINT, access_key=ACCESS, secret_key=SECRET, secure=False)
        self.lock = Lock()
        self.done_path = workdir / 'done.ids'
        self.sizes_path = workdir / 'sizes.tsv'
        self.err_path = workdir / 'errors.ndjson'
        self.done = set()
        if self.done_path.exists():
            self.done = {int(x) for x in self.done_path.read_text().split()}
        self.counts = {}
        self.points_cache = {}

        print('indexing disk pcds...', flush=True)
        self.index = {}
        for sd in SENSOR_DIRS:
            for p in DATASET_ROOT.glob(f'*/{sd}/*.pcd'):
                self.index.setdefault(p.name, []).append(p)
        print(f'indexed {sum(len(v) for v in self.index.values())} files, '
              f'{len(self.index)} unique names', flush=True)

    def bump(self, key):
        with self.lock:
            self.counts[key] = self.counts.get(key, 0) + 1

    def log_err(self, rec):
        with self.lock, open(self.err_path, 'a') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    def pick_candidate(self, name, old_size):
        cands = []
        for p in self.index.get(name, []):
            key = str(p)
            n = self.points_cache.get(key)
            if n is None:
                n = read_points_count(p)
                self.points_cache[key] = n
            if abs(old_size - (n * 12 + 196)) <= HDR_SLACK:
                cands.append((p, n))
        if len(cands) > 1:  # scene-copy dirs (e.g. 06 vs 06_old): prefer non-_old
            non_old = [c for c in cands if '_old' not in c[0].parts[-3]]
            if len(non_old) == 1:
                return non_old[0], None
            return None, f'ambiguous: {[str(c[0]) for c in cands]}'
        if not cands:
            return None, 'no disk candidate matching name+pointcount'
        return cands[0], None

    def process(self, row):
        oid, old_size, bucket, opath, bid, bpath = row[:6]
        if oid in self.done:
            self.bump('resume-skip')
            return
        if len(row) > 6:  # pre-paired disk path (Day-series order mapping)
            disk_path = Path(row[6])
            n = read_points_count(disk_path)
            if abs(old_size - (n * 12 + 196)) > HDR_SLACK:
                self.bump('skip')
                self.log_err({'id': oid, 'path': opath,
                              'reason': f'paired size/pointcount mismatch: old={old_size} n={n}'})
                return
        else:
            name = opath.rsplit('/', 1)[-1]
            cand, why = self.pick_candidate(name, old_size)
            if cand is None:
                self.bump('skip')
                self.log_err({'id': oid, 'path': opath, 'reason': why})
                return
            disk_path, n = cand
        data = disk_path.read_bytes()
        h, hlen = parse_header(data)
        if h.get('FIELDS') != 'x y z intensity' or int(h['POINTS']) != n:
            self.bump('skip')
            self.log_err({'id': oid, 'path': opath, 'reason': f'unexpected disk format {h.get("FIELDS")}'})
            return
        payload = data[hlen:]
        if len(payload) != n * 16:
            self.bump('skip')
            self.log_err({'id': oid, 'path': opath, 'reason': 'payload size mismatch'})
            return
        bin_data = data[:hlen].replace(b'FIELDS x y z intensity', b'FIELDS x y z i') + payload

        if not self.apply:
            self.bump('would-replace')
            return
        self.cli.put_object(bucket, opath, io.BytesIO(data), len(data),
                            content_type='application/octet-stream')
        self.cli.put_object(bucket, bpath, io.BytesIO(bin_data), len(bin_data),
                            content_type='application/octet-stream')
        with self.lock, open(self.sizes_path, 'a') as sf, open(self.done_path, 'a') as df:
            sf.write(f'{oid}\t{len(data)}\n{bid}\t{len(bin_data)}\n')
            df.write(f'{oid}\n')
        self.bump('replaced')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--targets', required=True, type=Path)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()

    rows = []
    for line in args.targets.read_text().splitlines():
        parts = line.split('\t')
        oid, size, bucket, opath, bid, bpath = parts[:6]
        rows.append((int(oid), int(size), bucket, opath, int(bid), bpath, *parts[6:]))
    if args.limit:
        rows = rows[:args.limit]

    r = Replacer(args.apply, args.targets.parent)
    t0 = time.time()
    with ThreadPoolExecutor(args.workers) as ex:
        for i, _ in enumerate(ex.map(r.process, rows)):
            if (i + 1) % 2000 == 0:
                rate = (i + 1) / (time.time() - t0)
                print(f'{i+1}/{len(rows)} ({rate:.1f}/s) {r.counts}', flush=True)
    print(f'DONE in {time.time()-t0:.0f}s: {r.counts}', flush=True)
    sys.exit(1 if r.counts.get('skip') else 0)


if __name__ == '__main__':
    main()
