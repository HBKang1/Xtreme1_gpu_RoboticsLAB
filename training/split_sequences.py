#!/usr/bin/env python3
"""Regenerate ImageSets/{train,val}.txt for an OpenPCDet CustomDataset using
sequence-level holdout instead of random per-frame splitting.

Adjacent frames in the same recording share spatial context, so a random
frame split leaks ground-truth context into validation.  This tool groups
every frame into its originating recording (sequence) and assigns whole
sequences to either train or val.

Usage
  python3 split_sequences.py --data-dir ./data/zenix --val-ratio 0.12 --seed 42
  python3 split_sequences.py --data-dir ./data/zenix --dry-run
"""
import argparse
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Sequence-key extraction
# ---------------------------------------------------------------------------

# Primary pattern produced by convert_xtreme1_to_openpcdet.py. The Xtreme1 pcd
# names embed a dashed date-time stamp, e.g. z06-2026-01-24-01-29-16_0000000017
# (and the older numeric form z03-1706068986_42). [\d-]+ captures either; the
# trailing _(\d+) is the frame index.
_PRIMARY = re.compile(r'^(z\d+-[\d-]+?)_(\d+)$')

# Generalised fallback: any prefix, optional dashes/underscores, ending in
# an underscore-separated numeric frame index.
_TRAILING_NUM = re.compile(r'^(.+)_(\d+)$')

# Heuristics that flag a remaining prefix as "looks like a recording ID"
# (contains a timestamp-like long digit run OR the z\d+ prefix).
_TIMESTAMP_LIKE = re.compile(r'\d{6,}')   # ≥6-digit run ~ unix timestamp
_ZENIX_PREFIX   = re.compile(r'z\d+')


def sequence_key(frame_id: str) -> tuple[str, bool]:
    """Return (key, confident) where key identifies the recording.

    confident=True  — pattern is unambiguous; safe to use for val holdout.
    confident=False — heuristic or no match; frame will be forced to train.
    """
    # 0. converter --frame-prefix convention "<dataset>__<orig_frame_id>": each
    #    dataset here is one continuous recording, so the prefix IS the sequence.
    if "__" in frame_id:
        return frame_id.split("__", 1)[0], True

    # 1. Primary: z{NN}-{ts}_{frame}
    m = _PRIMARY.match(frame_id)
    if m:
        return m.group(1), True

    # 2. Generalised trailing numeric index
    m = _TRAILING_NUM.match(frame_id)
    if m:
        prefix = m.group(1)
        looks_like_recording = bool(
            _TIMESTAMP_LIKE.search(prefix) or _ZENIX_PREFIX.search(prefix)
        )
        return prefix, looks_like_recording

    # 3. No match at all — treat the whole id as its own key
    return frame_id, False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        '--data-dir', type=Path, default=Path('./data/zenix'),
        help='root of the OpenPCDet CustomDataset (default: ./data/zenix)',
    )
    ap.add_argument(
        '--val-ratio', type=float, default=0.12,
        help='target fraction of frames assigned to val (default: 0.12)',
    )
    ap.add_argument(
        '--seed', type=int, default=42,
        help='random seed for sequence shuffle (default: 42)',
    )
    ap.add_argument(
        '--dry-run', action='store_true',
        help='print the plan but do not write any files',
    )
    ap.add_argument(
        '--random', action='store_true',
        help='random frame-level split instead of sequence-level holdout. For '
             'AUTO-LABELING (not generalization): trains on all recordings and the '
             'in-distribution val reflects auto-labeling quality; adjacent-frame '
             '"leakage" is representative of the use case, not a flaw.',
    )
    args = ap.parse_args()

    data_dir: Path = args.data_dir.resolve()
    points_dir = data_dir / 'points'
    imagesets_dir = data_dir / 'ImageSets'

    if not points_dir.is_dir():
        sys.exit(f'ERROR: points directory not found: {points_dir}')

    # ------------------------------------------------------------------
    # Collect frame IDs from *.npy files under points/
    # ------------------------------------------------------------------
    frame_ids: list[str] = sorted(p.stem for p in points_dir.glob('*.npy'))
    if not frame_ids:
        sys.exit(f'ERROR: no .npy files found under {points_dir}')

    total_frames = len(frame_ids)

    # ------------------------------------------------------------------
    # Random frame-level split (auto-labeling mode)
    # ------------------------------------------------------------------
    if args.random:
        shuffled = frame_ids[:]
        random.Random(args.seed).shuffle(shuffled)
        n_val = max(1, round(args.val_ratio * total_frames)) if args.val_ratio > 0 else 0
        val_frames = sorted(shuffled[:n_val])
        train_frames = sorted(shuffled[n_val:])
        print(f'data-dir        : {data_dir}')
        print(f'total frames    : {total_frames}  (RANDOM frame-level split)')
        print(f'val frames      : {len(val_frames)}  (ratio {args.val_ratio:.2%})')
        print(f'train frames    : {len(train_frames)}  (ALL recordings represented)')
        if not train_frames:
            sys.exit('ERROR: train split is empty.')
        if args.dry_run:
            print('\n[dry-run] no files written.')
            return
        imagesets_dir.mkdir(parents=True, exist_ok=True)
        (imagesets_dir / 'train.txt').write_text('\n'.join(train_frames) + '\n')
        (imagesets_dir / 'val.txt').write_text('\n'.join(val_frames) + ('\n' if val_frames else ''))
        print(f"\nwrote {imagesets_dir / 'train.txt'}  ({len(train_frames)} lines)")
        print(f"wrote {imagesets_dir / 'val.txt'}  ({len(val_frames)} lines)")
        return

    # ------------------------------------------------------------------
    # Group frames by sequence key
    # ------------------------------------------------------------------
    seq_to_frames: dict[str, list[str]] = defaultdict(list)
    uncertain_frames: list[str] = []

    for fid in frame_ids:
        key, confident = sequence_key(fid)
        if confident:
            seq_to_frames[key].append(fid)
        else:
            uncertain_frames.append(fid)

    sequences = sorted(seq_to_frames.keys())

    # ------------------------------------------------------------------
    # Sequence-level val selection (confident frames only)
    # ------------------------------------------------------------------
    # sequence-level holdout needs >=2 confident sequences, else one split is empty
    if len(sequences) < 2:
        sys.exit(
            f'ERROR: only {len(sequences)} confident sequence(s) found — cannot do '
            f'sequence-level holdout without leaking adjacent frames. Convert more '
            f'datasets into --data-dir first, or split manually.'
        )

    # Pick whole sequences for val smallest-first so the holdout lands close to the
    # target ratio. With few, very uneven recordings (e.g. 34..788 frames) a random
    # order can overshoot badly (one big recording = 40% val); smallest-first keeps
    # val near val_ratio and naturally mixes several short recordings. Tie-break by
    # seeded shuffle for determinism without size bias within equal sizes.
    rng = random.Random(args.seed)
    shuffled_seqs = sequences[:]
    rng.shuffle(shuffled_seqs)
    ordered_seqs = sorted(shuffled_seqs, key=lambda s: len(seq_to_frames[s]))

    val_target = args.val_ratio * total_frames
    val_sequences: list[str] = []
    val_frame_count = 0
    for seq in ordered_seqs:
        if val_frame_count >= val_target:
            break
        # always leave at least one sequence for train
        if len(val_sequences) >= len(sequences) - 1:
            break
        val_sequences.append(seq)
        val_frame_count += len(seq_to_frames[seq])

    val_seq_set = set(val_sequences)

    # ------------------------------------------------------------------
    # Build train / val frame lists
    # ------------------------------------------------------------------
    val_frames: list[str] = []
    train_frames: list[str] = []

    for seq in sequences:
        frames = seq_to_frames[seq]
        if seq in val_seq_set:
            val_frames.extend(frames)
        else:
            train_frames.extend(frames)

    # uncertain frames always go to train (never contaminate val)
    train_frames.extend(uncertain_frames)

    train_frames.sort()
    val_frames.sort()

    # ------------------------------------------------------------------
    # Leakage assertion: no sequence key appears in both splits
    # ------------------------------------------------------------------
    train_keys: set[str] = set()
    for fid in train_frames:
        k, _ = sequence_key(fid)
        train_keys.add(k)

    val_keys: set[str] = set()
    for fid in val_frames:
        k, _ = sequence_key(fid)
        val_keys.add(k)

    leaked = train_keys & val_keys
    if leaked:
        examples = sorted(leaked)[:5]
        sys.exit(
            f'ERROR: sequence leakage detected — {len(leaked)} key(s) appear in '
            f'both splits. Examples: {examples}\n'
            f'This is a bug; please file an issue.'
        )

    # guard: neither split may be empty (val drives the eval gate; train must learn)
    if not train_frames:
        sys.exit('ERROR: train split is empty — too few sequences for holdout.')
    if not val_frames:
        sys.exit('ERROR: val split is empty — raise --val-ratio or add more sequences '
                 '(the eval gate needs a non-empty val set).')

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    actual_val_ratio = len(val_frames) / total_frames if total_frames else 0.0

    print(f'data-dir        : {data_dir}')
    print(f'total frames    : {total_frames}')
    print(f'total sequences : {len(sequences)}  (confident pattern)')
    print(f'uncertain frames: {len(uncertain_frames)}  (confident=False → train only)')
    if uncertain_frames:
        examples = uncertain_frames[:5]
        print(f'  examples      : {examples}')
    print(f'val sequences   : {len(val_sequences)}  / {len(sequences)}')
    print(f'val frames      : {len(val_frames)}  (target ratio {args.val_ratio:.2%})')
    print(f'train frames    : {len(train_frames)}')
    print(f'actual val ratio: {actual_val_ratio:.4f}')
    print('leakage check   : PASS')

    if args.dry_run:
        print('\n[dry-run] no files written.')
        if val_sequences:
            print('val sequences (sample):')
            for s in val_sequences[:10]:
                print(f'  {s}  ({len(seq_to_frames[s])} frames)')
        return

    # ------------------------------------------------------------------
    # Write ImageSets/{train,val}.txt
    # ------------------------------------------------------------------
    imagesets_dir.mkdir(parents=True, exist_ok=True)
    (imagesets_dir / 'train.txt').write_text('\n'.join(train_frames) + '\n')
    (imagesets_dir / 'val.txt').write_text('\n'.join(val_frames) + '\n')
    print(f'\nwrote {imagesets_dir / "train.txt"}  ({len(train_frames)} lines)')
    print(f'wrote {imagesets_dir / "val.txt"}  ({len(val_frames)} lines)')


if __name__ == '__main__':
    main()
