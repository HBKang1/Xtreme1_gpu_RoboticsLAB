#!/usr/bin/env python3
"""Derive the front-camera FOV sector from Xtreme1 GT azimuth distribution.

Because GT annotation was performed only in the forward region, this script
analyses the azimuth of every GT 3-D box and emits the tightest symmetric
sector (plus a configurable margin) that covers 99.9 % of the GT boxes.
The result is written to training/fov_sector.json for consumption by the
convert/train pipeline.

Input
  --export <path>   Xtreme1 export zip or extracted directory (repeatable).
  --export-dir <d>  Directory whose immediate children are export dirs/zips.

  Each export:  result/*.json -> [{sourceName, objects:[{type:"3D_BOX",
                    className, contour:{center3D:{x,y,z}, size3D, rotation3D}}]}]
  Scene exports nest the same result/ one level deeper; rglob handles both.

Output
  training/fov_sector.json (schema consumed by convert_xtreme1_to_openpcdet):
  {
    "azimuth_min_deg": float,   # sector lower bound (after margin)
    "azimuth_max_deg": float,   # sector upper bound (after margin)
    "margin_deg": float,
    "wraps": false,
    "range_xy_m": null,
    "bev_occupancy_ratio": float,
    "method": "gt_azimuth_p99.9_plus_margin",
    "per_ds": { "<ds_key>": {"az_low_deg":f, "az_high_deg":f,
                              "r_max_m":f, "box_count":i} },
    "total_boxes": int
  }

Usage
  python3 analyze_fov.py --export ~/exports/ds1.zip --export ~/exports/ds2
  python3 analyze_fov.py --export-dir ~/exports/
"""
import argparse
import json
import math
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_export(export: Path, workdir: Path) -> tuple[Path, str]:
    """Return (root_path, ds_key).  Extracts zip when necessary."""
    if export.is_dir():
        return export, export.name
    if zipfile.is_zipfile(export):
        dest = Path(workdir) / export.stem
        with zipfile.ZipFile(export) as zf:
            zf.extractall(dest)
        return dest, export.stem
    sys.exit(f'--export {export}: not a directory or zip file')


def iter_result_files(root: Path):
    """Yield all result/*.json paths beneath root (handles scene nesting)."""
    yield from sorted(root.rglob('result/*.json'))


def parse_boxes(rf: Path, source: str) -> list[tuple[float, float]]:
    """Return list of (azimuth_deg, r_xy) tuples from one result file."""
    try:
        records = json.loads(rf.read_text())
    except json.JSONDecodeError:
        print(f'  ! skipping malformed JSON: {rf}', file=sys.stderr)
        return []

    gt = next((r for r in records if r.get('sourceName') == source), None)
    if gt is None:
        return []

    boxes = []
    for obj in gt.get('objects') or []:
        if obj.get('type') != '3D_BOX':
            continue
        contour = obj.get('contour') or {}
        c = contour.get('center3D') or {}
        try:
            x = float(c['x'])
            y = float(c['y'])
        except (KeyError, TypeError, ValueError):
            continue
        az = math.degrees(math.atan2(y, x))   # (-180, 180]
        r = math.hypot(x, y)
        boxes.append((az, r))
    return boxes


# ---------------------------------------------------------------------------
# Angular range helpers
# ---------------------------------------------------------------------------

def angular_span(azimuths: np.ndarray, lo_pct: float = 0.05,
                 hi_pct: float = 99.95) -> tuple[float, float, bool]:
    """Return (az_low, az_high, wraps) using the largest-gap method.

    Algorithm:
    1. Sort azimuths and find the biggest empty arc (gap) between consecutive
       samples.  The occupied sector is the complement of that gap.
    2. Re-orient the azimuths so the sector is contiguous (shift values that
       fall in the gap by +360°), then apply percentile trimming.
    3. Map results back to (-180, 180].
    4. wraps=True when the occupied sector straddles the ±180° boundary
       (i.e. az_high_raw > 180 in shifted space, meaning the normalised
       az_high < az_low in output).

    For typical front-facing data the gap is the rear half of the circle
    (around ±180°) so wraps will be False.
    """
    sorted_az = np.sort(azimuths)
    n = len(sorted_az)

    # Gaps between consecutive angles; wrap gap from last sample back to first
    gaps = np.diff(sorted_az)
    wrap_gap = (sorted_az[0] + 360.0) - sorted_az[-1]
    all_gaps = np.append(gaps, wrap_gap)
    max_gap_idx = int(np.argmax(all_gaps))

    # sector_start: the azimuth immediately after the largest gap
    if max_gap_idx < n - 1:
        sector_start = sorted_az[max_gap_idx + 1]
    else:
        # wrap gap is largest -> sector runs from sorted_az[0] straight through
        sector_start = sorted_az[0]

    # Shift azimuths so the sector is contiguous starting at sector_start
    az_shifted = np.where(azimuths < sector_start, azimuths + 360.0, azimuths)

    az_low_raw = float(np.percentile(az_shifted, lo_pct))
    az_high_raw = float(np.percentile(az_shifted, hi_pct))

    # Normalise back to (-180, 180]
    def normalise(a: float) -> float:
        while a > 180.0:
            a -= 360.0
        while a <= -180.0:
            a += 360.0
        return a

    az_low = normalise(az_low_raw)
    az_high = normalise(az_high_raw)

    # The sector wraps around ±180° iff the raw span extended past 180° in
    # shifted space (which normalises az_high to a value < az_low).
    wraps = az_high < az_low

    return az_low, az_high, wraps


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--export', type=Path, action='append', default=[],
                    metavar='PATH',
                    help='Xtreme1 export zip or directory (repeatable)')
    ap.add_argument('--export-dir', type=Path, default=None,
                    metavar='DIR',
                    help='Directory whose children are export dirs/zips')
    ap.add_argument('--source', default='Ground Truth',
                    help='result sourceName to use (default: "Ground Truth")')
    ap.add_argument('--margin-deg', type=float, default=5.0,
                    help='margin added to each side of the sector (default: 5.0)')
    ap.add_argument('--output', type=Path,
                    default=Path('training/fov_sector.json'),
                    help='output JSON path (default: training/fov_sector.json)')
    args = ap.parse_args()

    exports: list[Path] = list(args.export)
    if args.export_dir:
        if not args.export_dir.is_dir():
            sys.exit(f'--export-dir {args.export_dir}: not a directory')
        for child in sorted(args.export_dir.iterdir()):
            if child.is_dir() or (child.is_file() and zipfile.is_zipfile(child)):
                exports.append(child)

    if not exports:
        ap.error('provide at least one --export path or --export-dir')

    # Collect per-DS boxes
    per_ds: dict[str, list[tuple[float, float]]] = {}

    with tempfile.TemporaryDirectory() as tmp:
        for exp_path in exports:
            root, ds_key = load_export(exp_path, Path(tmp))
            result_files = list(iter_result_files(root))
            if not result_files:
                print(f'  ! no result/*.json under {root} — skipping', file=sys.stderr)
                continue
            ds_boxes: list[tuple[float, float]] = []
            for rf in result_files:
                ds_boxes.extend(parse_boxes(rf, args.source))
            if not ds_boxes:
                print(f'  ! DS "{ds_key}": no {args.source} boxes found — skipping',
                      file=sys.stderr)
                continue
            per_ds[ds_key] = ds_boxes
            print(f'  DS "{ds_key}": {len(ds_boxes)} boxes from '
                  f'{len(result_files)} result files')

    if not per_ds:
        sys.exit(f'no GT boxes found in any export for source "{args.source}"')

    # Per-DS statistics
    LO_PCT = 0.05
    HI_PCT = 99.95

    ds_stats: dict[str, dict] = {}
    ds_wraps: dict[str, bool] = {}
    for ds_key, boxes in per_ds.items():
        az_arr = np.array([b[0] for b in boxes])
        r_arr = np.array([b[1] for b in boxes])
        az_low, az_high, _w = angular_span(az_arr, LO_PCT, HI_PCT)
        ds_wraps[ds_key] = _w
        ds_stats[ds_key] = {
            'az_low_deg': round(az_low, 4),
            'az_high_deg': round(az_high, 4),
            'r_max_m': round(float(r_arr.max()), 4),
            'box_count': len(boxes),
        }

    # Mixed orientations make a min/max union meaningless (some DS wrap ±180,
    # others don't). Front-only GT should never wrap; warn loudly if it does.
    if len(set(ds_wraps.values())) > 1:
        wrapped = [k for k, w in ds_wraps.items() if w]
        print(f'WARNING: datasets disagree on ±180° wrap (wrapping: {wrapped}). '
              f'The union sector below may be wrong — inspect per_ds bounds.',
              file=sys.stderr)

    # Global sector = union of DS bounds (min of lows, max of highs)
    global_low = min(v['az_low_deg'] for v in ds_stats.values())
    global_high = max(v['az_high_deg'] for v in ds_stats.values())

    # Apply margin, then clamp into (-180, 180]. Without clamping a margin that
    # pushes az_max past 180 silently disables the converter's upper crop/gate
    # (every real azimuth is <= 180), letting rear points leak back in.
    az_min = max(global_low - args.margin_deg, -180.0)
    az_max = min(global_high + args.margin_deg, 180.0)

    # Wrap detection: run angular_span on the full combined azimuth set.
    # wraps=True means the occupied sector crosses the ±180° discontinuity.
    all_az = np.concatenate([np.array([b[0] for b in boxes])
                             for boxes in per_ds.values()])
    _, _, wraps = angular_span(all_az, LO_PCT, HI_PCT)

    # If the (clamped) sector covers most of the circle the crop is near useless;
    # for front-only GT this signals a wrap or contaminated rear boxes.
    if (az_max - az_min) > 180.0 and not wraps:
        print('WARNING: sector span > 180° after margin/clamp — crop is nearly a '
              'no-op. Verify GT is front-facing only (possible ±180° wrap).',
              file=sys.stderr)

    # BEV occupancy ratio
    # wraps=False: sector arc = az_max - az_min
    # wraps=True : sector arc = 360 - (az_low_in_shifted - az_high_normalized)
    #              Simpler: compute the arc correctly via az_min/az_max.
    if wraps:
        # Sector crosses ±180°: arc = 360 + az_max - az_min when az_max < az_min
        # (e.g. az_min=150°, az_max=-150° -> arc = 360 - 300 = 60°)
        arc = 360.0 + az_max - az_min if az_max < az_min else az_max - az_min
        bev_ratio = round(arc / 360.0, 6)
    else:
        bev_ratio = round((az_max - az_min) / 360.0, 6)

    # DS consistency check (warn if any DS boundary deviates > 5° from others)
    consistency_threshold = 5.0
    if len(ds_stats) > 1:
        low_vals = [v['az_low_deg'] for v in ds_stats.values()]
        high_vals = [v['az_high_deg'] for v in ds_stats.values()]
        low_range = max(low_vals) - min(low_vals)
        high_range = max(high_vals) - min(high_vals)
        if low_range > consistency_threshold or high_range > consistency_threshold:
            print('\nWARNING: DS azimuth boundaries are inconsistent '
                  f'(low spread {low_range:.1f}°, high spread {high_range:.1f}°). '
                  'Consider checking whether all exports cover the same FOV '
                  'before using a merged sector for training.', file=sys.stderr)
            print('  DS boundary table:', file=sys.stderr)
            print(f'  {"DS":30s}  {"az_low":>8s}  {"az_high":>8s}  {"boxes":>6s}',
                  file=sys.stderr)
            for ds_key, st in ds_stats.items():
                print(f'  {ds_key:30s}  {st["az_low_deg"]:8.2f}  '
                      f'{st["az_high_deg"]:8.2f}  {st["box_count"]:6d}',
                      file=sys.stderr)
            print('  Action recommended: inspect per-DS distributions before merging.',
                  file=sys.stderr)

    total_boxes = sum(v['box_count'] for v in ds_stats.values())

    result = {
        'azimuth_min_deg': round(az_min, 4),
        'azimuth_max_deg': round(az_max, 4),
        'margin_deg': args.margin_deg,
        'wraps': wraps,
        'range_xy_m': None,
        'bev_occupancy_ratio': bev_ratio,
        'method': 'gt_azimuth_p99.9_plus_margin',
        'per_ds': ds_stats,
        'total_boxes': total_boxes,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')

    # Human-readable summary to stdout
    print('\n=== FOV Sector Analysis ===')
    print(f'Source filter : {args.source}')
    print(f'Total GT boxes: {total_boxes}')
    print(f'Margin        : ±{args.margin_deg}°')
    print()
    print(f'Sector        : [{az_min:.2f}°, {az_max:.2f}°]  '
          f'(span {az_max - az_min:.2f}°)')
    print(f'Wraps ±180°   : {wraps}')
    print(f'BEV occupancy : {bev_ratio:.4f}  ({bev_ratio * 100:.2f}% of 360°)')
    print()
    print(f'  {"DS":30s}  {"az_low":>8s}  {"az_high":>8s}  '
          f'{"r_max_m":>8s}  {"boxes":>6s}')
    print('  ' + '-' * 70)
    for ds_key, st in ds_stats.items():
        print(f'  {ds_key:30s}  {st["az_low_deg"]:8.2f}  {st["az_high_deg"]:8.2f}  '
              f'  {st["r_max_m"]:6.1f}  {st["box_count"]:6d}')
    print()
    print(f'Written: {args.output}')


if __name__ == '__main__':
    main()
