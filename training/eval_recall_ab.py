#!/usr/bin/env python3
"""Class-agnostic recall A/B on the zenix val set via the serving endpoint.

For each val frame, POST its pcd to /pointCloud/recognition and count a GT box
as recalled if any prediction (conf >= --conf) lies within --gate metres in BEV.
Lets us compare the finetuned model against the zero-shot nuScenes / VoxelNeXt
baselines on the SAME frames + metric (the pretrained heads differ, so OpenPCDet
mAP isn't comparable, but class-agnostic "did it find the object" recall is).

Usage:
  python3 training/eval_recall_ab.py --label ft           # current serving
  python3 training/eval_recall_ab.py --label centerpoint  # after switching serving
"""
import argparse
import json
import math
import sys
import urllib.request
from pathlib import Path

REC = Path("training/val_eval_ab.json")
OUT = Path("training/recall_ab_results.json")
import os
SERVE = os.environ.get("XTREME1_SERVE", "http://localhost:8293") + "/pointCloud/recognition"


def predict(url, timeout=120):
    body = json.dumps({"datas": [{"id": 1, "pointCloudUrl": url}]}).encode()
    req = urllib.request.Request(SERVE, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    res = (resp.get("data") or [{}])[0]
    if res.get("code") not in (None, "OK"):
        raise RuntimeError(res.get("message", "")[:120])
    return res.get("objects") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="model label for this run")
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--gate", type=float, default=2.0, help="BEV match distance (m)")
    ap.add_argument("--limit", type=int, default=0, help="0 = all val frames")
    ap.add_argument("--pred-fov", default=None,
                    help="fov_sector json: drop predictions outside the sector before "
                         "scoring (GT is FOV-only, so out-of-FOV preds would be unfair FP). "
                         "Mirrors cropping the serving input to the trained FOV.")
    args = ap.parse_args()

    import math as _m
    fov = None
    if args.pred_fov:
        s = json.loads(Path(args.pred_fov).read_text())
        fov = (s["azimuth_min_deg"], s["azimuth_max_deg"])

    def in_fov(px, py):
        if fov is None:
            return True
        az = _m.degrees(_m.atan2(py, px))
        return fov[0] <= az <= fov[1]

    recs = json.loads(REC.read_text())
    if args.limit:
        recs = recs[: args.limit]

    tot_gt = matched = tot_pred = frames = errs = 0
    for i, rc in enumerate(recs):
        try:
            objs = predict(rc["url"])
        except Exception as e:  # noqa: BLE001
            errs += 1
            continue
        frames += 1
        preds = [(o["x"], o["y"]) for o in objs
                 if o.get("confidence", 0) >= args.conf and in_fov(o["x"], o["y"])]
        gts = list(rc["gt"])
        tot_pred += len(preds)
        tot_gt += len(gts)
        # greedy 1:1 matching: each GT consumes its nearest unused prediction within
        # the gate. matched GTs -> recall numerator; matched preds -> precision numerator.
        used = [False] * len(preds)
        g2 = args.gate ** 2
        for gx, gy in gts:
            best_j, best_d = -1, g2
            for j, (px, py) in enumerate(preds):
                if used[j]:
                    continue
                d = (gx - px) ** 2 + (gy - py) ** 2
                if d <= best_d:
                    best_d, best_j = d, j
            if best_j >= 0:
                used[best_j] = True
                matched += 1
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(recs)}  recall={matched/max(tot_gt,1):.3f}", flush=True)

    recall = matched / max(tot_gt, 1)            # matched GT / total GT
    precision = matched / max(tot_pred, 1)       # matched preds / total preds (TP/(TP+FP))
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    summary = {
        "label": args.label, "conf": args.conf, "gate_m": args.gate,
        "frames": frames, "errors": errs, "total_gt": tot_gt,
        "matched": matched, "recall": round(recall, 4),
        "precision": round(precision, 4), "f1": round(f1, 4),
        "total_pred": tot_pred, "pred_per_frame": round(tot_pred / max(frames, 1), 2),
        "false_pos": tot_pred - matched, "fp_per_frame": round((tot_pred - matched) / max(frames, 1), 2),
    }
    print(json.dumps(summary, indent=2))
    allr = json.loads(OUT.read_text()) if OUT.exists() else {}
    allr[args.label] = summary
    OUT.write_text(json.dumps(allr, indent=2))
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
