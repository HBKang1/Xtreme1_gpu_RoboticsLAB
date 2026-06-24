#!/usr/bin/env python3
"""Score and rank frames by model uncertainty for active-learning selection.

Reads a directory of per-frame prediction JSON (the /pointCloud/recognition
response shape — same shape eval_recall_ab.py already posts/reads) and scores
each frame on three signals:

  fallbackRate   fraction of boxes with confidence == TRACK_FALLBACK_CONFIDENCE
                 (these are tracking propagations, not fresh detections)
  meanConf       mean confidence across all boxes (lower = more uncertain)
  instability    mean geometry jump per trackId vs the previous frame
                 (works on GT exports too, since it only needs trackId + geometry)

Composite score (higher = more uncertain = higher priority for manual review):

  score = W_FALLBACK * fallbackRate
        + W_MEANCONF * (1 - clipped_meanConf)
        + W_INSTABILITY * clipped_instability

REPRODUCIBILITY NOTE
--------------------
fallbackRate and meanConf are computed from a PREDICTION SNAPSHOT (a live
serving pass), so they are model- and run-dependent. instability is computed
from box geometry (trackId + center3D/size3D/rotation3D) and is GT-stable —
it is reproducible from the export alone. This distinction is recorded in the
ranking artifact (ranking.json) so any ranking can be audited.

Usage
-----
  # Score frames from a prediction-JSON directory; print top-20
  python3 training/rank_frames.py --predictions training/exports/pred_2026-06-23/ --top-k 20

  # Also record model id and weights in the artifact
  python3 training/rank_frames.py \\
      --predictions training/exports/pred_2026-06-23/ \\
      --top-k 20 \\
      --model-id TransFusion-L-zenix-v3 \\
      --out-dir training/exports/ranking-2026-06-23

The script persists the scored predictions and a ranking.json inside --out-dir
(default: training/exports/ranking-<timestamp>/) so a ranking is reproducible
and auditable.
"""
import argparse
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Tuning constants — adjust to reweight the three uncertainty signals
# ---------------------------------------------------------------------------
TRACK_FALLBACK_CONFIDENCE: float = 0.1   # mirrors app.py TRACK_FALLBACK_CONFIDENCE

W_FALLBACK:     float = 0.4   # weight for fallback-box fraction
W_MEANCONF:     float = 0.3   # weight for (1 - mean_confidence) term
W_INSTABILITY:  float = 0.3   # weight for cross-frame geometry instability

# Geometry delta normalisation caps — prevent runaway outliers from dominating
_INSTABILITY_DIST_CAP:    float = 10.0  # metres, BEV centre displacement
_INSTABILITY_SIZE_CAP:    float = 5.0   # metres, per-dimension size change
_INSTABILITY_HEADING_CAP: float = math.pi  # radians, heading delta (max π)


# ---------------------------------------------------------------------------
# Per-frame signal computation
# ---------------------------------------------------------------------------
def _require(d: dict, *keys: str, context: str = "") -> None:
    """Raise a clear KeyError if any key is missing from *d*."""
    for k in keys:
        if k not in d:
            raise KeyError(
                f"Missing required field {k!r} in prediction dict"
                + (f" ({context})" if context else "")
            )


def _extract_geometry(box: dict) -> tuple[float, float, float, float, float, float, float]:
    """Return (x, y, z, dx, dy, dz, heading) from a recognition-response box.

    Supports both the nested shape (center3D / size3D / rotation3D) and the
    flat shape (x/y/z, dx/dy/dz, rotZ).  Raises KeyError loudly on missing
    fields (R-export-coupling mitigation).
    """
    if "center3D" in box:
        c = box["center3D"]
        s = box["size3D"]
        r = box["rotation3D"]
        _require(c, "x", "y", "z", context="center3D")
        _require(s, "x", "y", "z", context="size3D")
        _require(r, "z", context="rotation3D")
        return c["x"], c["y"], c["z"], s["x"], s["y"], s["z"], r["z"]
    # flat shape
    _require(box, "x", "y", "z", "dx", "dy", "dz", "rotZ")
    return box["x"], box["y"], box["z"], box["dx"], box["dy"], box["dz"], box["rotZ"]


def _angle_delta(a: float, b: float) -> float:
    """Signed shortest-path angular difference in [0, π]."""
    d = (b - a) % (2 * math.pi)
    if d > math.pi:
        d = 2 * math.pi - d
    return abs(d)


def score_frame(boxes: list[dict]) -> dict:
    """Compute (fallbackRate, meanConf, rawInstability) for a single frame.

    *boxes* is the 'objects' list from one /pointCloud/recognition response
    entry (or equivalent flat list loaded from disk).

    instability is set to 0.0 here; it requires cross-frame context and is
    computed later in score_all_frames().
    """
    if not boxes:
        return {"fallbackRate": 0.0, "meanConf": 1.0, "instability": 0.0, "n_boxes": 0}

    fallback_count = 0
    conf_sum = 0.0
    for box in boxes:
        _require(box, "confidence", context="box")
        conf = box["confidence"]
        if conf == TRACK_FALLBACK_CONFIDENCE:
            fallback_count += 1
        conf_sum += conf

    return {
        "fallbackRate": fallback_count / len(boxes),
        "meanConf": conf_sum / len(boxes),
        "instability": 0.0,  # populated by score_all_frames
        "n_boxes": len(boxes),
    }


def _geometry_delta(g_prev: tuple, g_curr: tuple) -> float:
    """Unsigned geometry distance between two (x,y,z,dx,dy,dz,heading) tuples.

    Returns a normalised scalar in [0, 1] after capping each component.
    """
    xp, yp, _, dxp, dyp, dzp, hp = g_prev
    xc, yc, _, dxc, dyc, dzc, hc = g_curr

    bev_dist = math.sqrt((xc - xp) ** 2 + (yc - yp) ** 2)
    size_delta = (abs(dxc - dxp) + abs(dyc - dyp) + abs(dzc - dzp)) / 3.0
    head_delta = _angle_delta(hp, hc)

    # Normalise to [0, 1] by capping against known-reasonable maximums
    norm_dist = min(bev_dist, _INSTABILITY_DIST_CAP) / _INSTABILITY_DIST_CAP
    norm_size = min(size_delta, _INSTABILITY_SIZE_CAP) / _INSTABILITY_SIZE_CAP
    norm_head = min(head_delta, _INSTABILITY_HEADING_CAP) / _INSTABILITY_HEADING_CAP

    return (norm_dist + norm_size + norm_head) / 3.0


def score_all_frames(
    frames: list[dict],
) -> list[dict]:
    """Score every frame; populate instability via cross-frame trackId matching.

    *frames* is a list of dicts, each with keys:
      - frame_id (str): dataId or file stem used as the output frame identifier
      - boxes (list[dict]): the 'objects' list from the recognition response

    Returns a list of per-frame score dicts (same order as input).
    """
    # Build per-track geometry history: track_id -> last seen geometry
    track_prev: dict[str, tuple] = {}

    scored: list[dict] = []
    for frame in frames:
        frame_id = frame["frame_id"]
        boxes = frame["boxes"]

        base = score_frame(boxes)

        # Compute instability: for each box that has a trackId and a previous
        # geometry snapshot, accumulate the normalised geometry delta.
        track_deltas: list[float] = []
        track_seen: dict[str, tuple] = {}
        for box in boxes:
            track_id = box.get("trackId")
            if track_id is None:
                continue
            try:
                geom = _extract_geometry(box)
            except KeyError as exc:
                print(f"warning: frame {frame_id!r}: {exc} — skipping box for instability", file=sys.stderr)
                continue
            track_seen[str(track_id)] = geom
            prev = track_prev.get(str(track_id))
            if prev is not None:
                track_deltas.append(_geometry_delta(prev, geom))

        # Update history (use end-of-frame snapshot)
        track_prev.update(track_seen)

        instability = sum(track_deltas) / len(track_deltas) if track_deltas else 0.0
        base["instability"] = instability
        base["frame_id"] = frame_id
        scored.append(base)

    return scored


def composite_score(s: dict) -> float:
    """Higher score = more uncertain = higher priority for labelling."""
    clipped_mean = max(0.0, min(1.0, s["meanConf"]))
    clipped_inst = max(0.0, min(1.0, s["instability"]))
    return (
        W_FALLBACK * s["fallbackRate"]
        + W_MEANCONF * (1.0 - clipped_mean)
        + W_INSTABILITY * clipped_inst
    )


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------
def load_prediction_dir(pred_dir: Path) -> list[dict]:
    """Load per-frame prediction JSON files from *pred_dir*.

    Each file must be a JSON object with an 'objects' key (list of box dicts)
    and optionally a 'dataId' key.  The file stem is used as the frame_id when
    dataId is absent.  Files are sorted lexicographically for deterministic
    cross-frame instability tracking order.
    """
    json_files = sorted(pred_dir.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No *.json files found in predictions directory: {pred_dir}")

    frames: list[dict] = []
    for path in json_files:
        raw = json.loads(path.read_text())

        # Support two layouts:
        #   1. Direct recognition response: {"data": [{"objects": [...], "dataId": ...}]}
        #   2. Pre-extracted objects list (flat): {"objects": [...], "dataId": ...}
        #   3. A list of such dicts (batch response inner data array)
        if isinstance(raw, dict) and "data" in raw:
            entries = raw["data"] or []
        elif isinstance(raw, list):
            entries = raw
        elif isinstance(raw, dict) and "objects" in raw:
            entries = [raw]
        else:
            print(f"warning: {path.name}: unrecognised JSON shape, skipping", file=sys.stderr)
            continue

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            objects = entry.get("objects")
            if objects is None:
                print(f"warning: {path.name}: entry missing 'objects' key, skipping", file=sys.stderr)
                continue
            data_id = entry.get("dataId") or path.stem
            frames.append({"frame_id": str(data_id), "boxes": objects})

    return frames


def persist_artifact(
    pred_dir: Path,
    scores: list[dict],
    ranked_ids: list[str],
    top_k: int,
    model_id: str,
    out_dir: Path,
) -> Path:
    """Persist the prediction snapshot and ranking.json into *out_dir*.

    Layout:
      out_dir/
        predictions/          — copy of the scored prediction JSON files
        ranking.json          — artifact manifest: weights, model, scores, top-K ids

    Returns the path to ranking.json.
    """
    pred_out = out_dir / "predictions"
    pred_out.mkdir(parents=True, exist_ok=True)

    # Copy (or symlink) prediction files for auditability
    for src in sorted(pred_dir.glob("*.json")):
        dst = pred_out / src.name
        if not dst.exists():
            shutil.copy2(src, dst)

    artifact = {
        "schema_version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_id": model_id,
        "predictions_path": str(pred_out.resolve()),
        "weights": {
            "W_FALLBACK": W_FALLBACK,
            "W_MEANCONF": W_MEANCONF,
            "W_INSTABILITY": W_INSTABILITY,
        },
        "signal_notes": {
            "fallbackRate": "SNAPSHOT-DEPENDENT: computed from prediction JSON; varies with model/weights.",
            "meanConf": "SNAPSHOT-DEPENDENT: computed from prediction JSON; varies with model/weights.",
            "instability": "GT-STABLE: computed from box geometry (trackId + center3D/size3D/rotation3D); reproducible from any export with the same annotations.",
        },
        "top_k": top_k,
        "top_k_frame_ids": ranked_ids[:top_k],
        "all_frame_scores": scores,
    }
    ranking_path = out_dir / "ranking.json"
    ranking_path.write_text(json.dumps(artifact, indent=2))
    return ranking_path


# ---------------------------------------------------------------------------
# Public API (importable by export_gt.py)
# ---------------------------------------------------------------------------
def rank_frames(
    pred_dir: Path,
    top_k: int,
    model_id: str = "unknown",
    out_dir: Path | None = None,
) -> tuple[list[str], Path]:
    """Score all frames in *pred_dir* and return (ranked_frame_ids, artifact_path).

    ranked_frame_ids is sorted descending by composite uncertainty score
    (highest uncertainty first).  The artifact is persisted under *out_dir*
    (auto-generated timestamp dir if None).

    This function is imported and called by export_gt.py --top-k.
    """
    if out_dir is None:
        out_dir = Path("training/exports") / f"ranking-{time.strftime('%Y%m%d-%H%M%S')}"

    frames = load_prediction_dir(pred_dir)
    if not frames:
        raise RuntimeError(f"No frames loaded from {pred_dir}")

    scores = score_all_frames(frames)
    scores_sorted = sorted(scores, key=composite_score, reverse=True)
    ranked_ids = [s["frame_id"] for s in scores_sorted]

    artifact_path = persist_artifact(
        pred_dir=pred_dir,
        scores=scores_sorted,
        ranked_ids=ranked_ids,
        top_k=top_k,
        model_id=model_id,
        out_dir=out_dir,
    )
    return ranked_ids, artifact_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--predictions",
        metavar="DIR",
        required=True,
        type=Path,
        help="Directory of per-frame prediction JSON files (recognition response shape)",
    )
    ap.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of top-uncertainty frames to output (default 20)",
    )
    ap.add_argument(
        "--model-id",
        default="unknown",
        help="Model identifier recorded in the ranking artifact (e.g. TransFusion-L-zenix-v3)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Artifact output directory (default: training/exports/ranking-<timestamp>/)",
    )
    args = ap.parse_args()

    if not args.predictions.is_dir():
        sys.exit(f"error: --predictions must be a directory: {args.predictions}")

    print(f"Loading predictions from {args.predictions} …", flush=True)
    ranked_ids, artifact_path = rank_frames(
        pred_dir=args.predictions,
        top_k=args.top_k,
        model_id=args.model_id,
        out_dir=args.out_dir,
    )

    print(f"\nTop-{args.top_k} frames by descending uncertainty (highest first):")
    for rank, fid in enumerate(ranked_ids[: args.top_k], 1):
        print(f"  {rank:3d}. {fid}")

    print(f"\nRanking artifact saved: {artifact_path}")
    print(
        "\nNOTE: fallbackRate and meanConf are SNAPSHOT-DEPENDENT (prediction-run-specific).\n"
        "      instability is GT-STABLE (reproducible from exported annotations).\n"
        "      See ranking.json signal_notes for details."
    )


# ---------------------------------------------------------------------------
# Self-test (runnable sanity check — kept to one assert block per ponytail rule)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse as _argparse_check  # noqa: F401 (already imported above)

    # When invoked directly with no args, run the self-test instead of the CLI.
    if len(sys.argv) == 1:
        print("rank_frames.py self-test …", flush=True)

        # Synthesize two fake frames with known properties:
        #   frame_A: 2 boxes, both fallback (conf=0.1), high uncertainty
        #   frame_B: 2 boxes, both high-conf (conf=0.9), low uncertainty
        # Expectation: frame_A scores higher than frame_B.

        fake_frames = [
            {
                "frame_id": "frame_A",
                "boxes": [
                    {
                        "confidence": 0.1,  # fallback
                        "trackId": "track-1",
                        "center3D": {"x": 10.0, "y": 5.0, "z": 0.5},
                        "size3D": {"x": 4.0, "y": 2.0, "z": 1.5},
                        "rotation3D": {"x": 0.0, "y": 0.0, "z": 0.2},
                    },
                    {
                        "confidence": 0.1,  # fallback
                        "trackId": "track-2",
                        "center3D": {"x": 20.0, "y": -3.0, "z": 0.5},
                        "size3D": {"x": 4.0, "y": 2.0, "z": 1.5},
                        "rotation3D": {"x": 0.0, "y": 0.0, "z": 0.0},
                    },
                ],
            },
            {
                "frame_id": "frame_B",
                "boxes": [
                    {
                        "confidence": 0.9,
                        "trackId": "track-1",
                        "center3D": {"x": 12.0, "y": 5.0, "z": 0.5},
                        "size3D": {"x": 4.0, "y": 2.0, "z": 1.5},
                        "rotation3D": {"x": 0.0, "y": 0.0, "z": 0.2},
                    },
                    {
                        "confidence": 0.9,
                        "trackId": "track-2",
                        "center3D": {"x": 20.5, "y": -3.0, "z": 0.5},
                        "size3D": {"x": 4.0, "y": 2.0, "z": 1.5},
                        "rotation3D": {"x": 0.0, "y": 0.0, "z": 0.0},
                    },
                ],
            },
        ]

        scores = score_all_frames(fake_frames)
        score_map = {s["frame_id"]: composite_score(s) for s in scores}

        assert score_map["frame_A"] > score_map["frame_B"], (
            f"Self-test FAILED: expected frame_A ({score_map['frame_A']:.4f}) "
            f"> frame_B ({score_map['frame_B']:.4f})"
        )
        print(
            f"  frame_A score={score_map['frame_A']:.4f}  "
            f"frame_B score={score_map['frame_B']:.4f}"
        )
        print("Self-test PASSED: higher-fallback frame ranks first.")
        sys.exit(0)

    main()
