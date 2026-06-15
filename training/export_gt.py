#!/usr/bin/env python3
"""Download ANNOTATED ground-truth exports from an Xtreme1 instance.

Authenticates via env XTREME1_USER / XTREME1_PASS (or --token), fetches all
LIDAR_BASIC datasets, applies the Zenix project selection rules, then exports
and downloads each as a zip into --out-dir.

Usage
  # List targets only (no download)
  XTREME1_USER=you@example.com XTREME1_PASS=secret \\
    python3 export_gt.py --list

  # Download all target datasets
  XTREME1_USER=you@example.com XTREME1_PASS=secret \\
    python3 export_gt.py

  # Download a specific dataset (smoke test)
  XTREME1_USER=you@example.com XTREME1_PASS=secret \\
    python3 export_gt.py --dataset Zenix_Day_01
"""
import argparse
import os
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import requests

# Use the gateway nginx (/api/ -> backend, /minio/ -> minio). The backend builds
# the export's presigned URL from the request Host, so it must arrive through the
# gateway origin that also serves /minio/; hitting the backend port directly
# (:8290) yields a presigned host with no /minio/ route (404 on download).
DEFAULT_BASE_URL = "http://localhost:8190/api"
DEFAULT_OUT_DIR = Path(__file__).parent / "exports"
DEFAULT_TIMEOUT = 600          # seconds
DEFAULT_POLL_INTERVAL = 3      # seconds
PAGE_SIZE = 100
# The Xtreme1 instance uses LIDAR_FUSION for all Zenix point-cloud datasets.
# (The API type value depends on how the project was created; change if needed.)
DATASET_TYPE = "LIDAR_FUSION"

# ---------------------------------------------------------------------------
# Dataset selection rules
# ---------------------------------------------------------------------------
# User decision (2026-06-14): train only on real Zenix datasets — names must
# start with "Zenix_". This excludes non-Zenix names (Caterpie_*, N14, Korean
# campus-indoor datasets) without needing per-name rules.
REQUIRED_PREFIX = "Zenix_"
EXCLUDED_EXACT = {"Zenix_Day_0"}            # disk<->Xtreme1 frame mapping unreliable
RE_SEQ_OR_TEST = re.compile(r"(seq|test)", re.IGNORECASE)  # duplicate/test copies


def select_target_datasets(datasets: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split *datasets* into (targets, excluded).

    Each excluded entry gets an extra key ``"exclude_reason"``.
    Targets must start with REQUIRED_PREFIX and have annotatedCount > 0.
    """
    targets, excluded = [], []
    for ds in datasets:
        name = ds.get("name", "")
        reason = None
        if not name.startswith(REQUIRED_PREFIX):
            reason = f"name does not start with {REQUIRED_PREFIX!r}"
        elif name in EXCLUDED_EXACT:
            reason = f"exact-exclude: {name!r}"
        elif RE_SEQ_OR_TEST.search(name):
            reason = "name contains 'seq' or 'test'"
        elif ds.get("annotatedCount", 0) <= 0:
            reason = "annotatedCount == 0"
        if reason:
            excluded.append({**ds, "exclude_reason": reason})
        else:
            targets.append(ds)
    return targets, excluded


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _check(resp: requests.Response, label: str) -> dict:
    """Raise a clear error if the response is not code==OK."""
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"{label}: HTTP {resp.status_code} — {resp.text[:300]}") from exc
    body = resp.json()
    if body.get("code") != "OK":
        msg = body.get("message", "")
        raise RuntimeError(f"{label}: API returned code={body.get('code')!r} message={msg!r}")
    return body["data"]


def login(session: requests.Session, base_url: str, username: str, password: str) -> str:
    data = _check(
        session.post(f"{base_url}/user/login", json={"username": username, "password": password}),
        "POST /user/login",
    )
    token = data.get("token") if isinstance(data, dict) else None
    if not token:
        raise RuntimeError(f"POST /user/login: no token in response data: {data!r}")
    return token


def fetch_all_datasets(session: requests.Session, base_url: str) -> list[dict]:
    """Paginate through all LIDAR_BASIC datasets."""
    all_ds, page_no = [], 1
    while True:
        data = _check(
            session.get(
                f"{base_url}/dataset/findByPage",
                params={"pageNo": page_no, "pageSize": PAGE_SIZE, "type": DATASET_TYPE},
            ),
            f"GET /dataset/findByPage?pageNo={page_no}",
        )
        page_list = data.get("list", [])
        all_ds.extend(page_list)
        total = data.get("total", 0)
        if len(all_ds) >= total or not page_list:
            break
        page_no += 1
    return all_ds


def fetch_scene_ids(session: requests.Session, base_url: str, dataset_id: int) -> list[int]:
    """Return the top-level SCENE record ids of a dataset, or [] when the dataset
    is flat (top-level records are SINGLE_DATA frames).

    Scene-structured datasets keep the real frames as children (parentId=sceneId).
    The export's annotationStatus filter only matches top-level records, so for a
    scene we must export with parentId=sceneId to reach the annotated children.
    """
    scene_ids, page_no = [], 1
    flat = False
    while True:
        data = _check(
            session.get(
                f"{base_url}/data/findByPage",
                params={"datasetId": dataset_id, "pageNo": page_no, "pageSize": PAGE_SIZE},
            ),
            f"GET /data/findByPage?datasetId={dataset_id}",
        )
        page_list = data.get("list", [])
        for rec in page_list:
            if rec.get("type") == "SCENE":
                scene_ids.append(rec["id"])
            else:
                flat = True  # SINGLE_DATA at top level -> flat dataset
        total = data.get("total", 0)
        if len(page_list) == 0 or page_no * PAGE_SIZE >= total or flat:
            break
        page_no += 1
    return scene_ids


def start_export(session: requests.Session, base_url: str, dataset_id: int,
                 parent_id: int | None = None) -> str:
    # selectModelRunIds=-1 (GROUND_TRUTH sentinel) makes the backend write the
    # result/*.json GT files into the zip; without it the export contains only
    # data/*.json and no annotations (DataInfoUseCase.export GROUND_TRUTH branch).
    # parentId is set for scene datasets so the annotationStatus filter applies to
    # the scene's child frames (commonDataQueryWrapper uses parentId) instead of
    # the always-NOT_ANNOTATED scene record — i.e. download ONLY annotated frames.
    params = {
        "datasetId": dataset_id,
        "annotationStatus": "ANNOTATED",
        "selectModelRunIds": -1,
    }
    if parent_id is not None:
        params["parentId"] = parent_id
    data = _check(
        session.get(f"{base_url}/data/export", params=params),
        f"GET /data/export?datasetId={dataset_id}"
        + (f"&parentId={parent_id}" if parent_id is not None else ""),
    )
    if not isinstance(data, str) or not data:
        raise RuntimeError(f"GET /data/export?datasetId={dataset_id}: unexpected serialNumber: {data!r}")
    return data


def poll_export(
    session: requests.Session,
    base_url: str,
    serial_number: str,
    timeout: float,
    poll_interval: float,
    ds_name: str,
) -> dict:
    """Block until the export is COMPLETED or FAILED (or timeout)."""
    deadline = time.monotonic() + timeout
    while True:
        records = _check(
            session.get(
                f"{base_url}/data/findExportRecordBySerialNumbers",
                params={"serialNumbers": serial_number},
            ),
            f"GET /data/findExportRecordBySerialNumbers?serialNumbers={serial_number}",
        )
        if not isinstance(records, list) or not records:
            raise RuntimeError(
                f"findExportRecordBySerialNumbers: empty response for {serial_number!r}"
            )
        rec = records[0]
        status = rec.get("status", "UNKNOWN")
        generated = rec.get("generatedNum", 0) or 0
        total = rec.get("totalNum", 0) or 0
        print(
            f"  [{ds_name}] {status}  {generated}/{total} frames …",
            flush=True,
        )
        if status == "COMPLETED":
            return rec
        if status == "FAILED":
            raise RuntimeError(f"Export FAILED for dataset {ds_name!r} (serialNumber={serial_number!r})")
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Export timed out after {timeout}s for dataset {ds_name!r} "
                f"(serialNumber={serial_number!r}, last status={status})"
            )
        time.sleep(poll_interval)


def download_zip(
    session: requests.Session,
    base_url: str,
    file_path: str,
    dest: Path,
) -> None:
    """Stream-download the export zip to *dest*.

    The export filePath is a presigned MinIO URL whose AWS sigv4 signature
    covers the exact percent-encoding of the query string. requests re-quotes
    the URL (requote_uri), which alters that encoding and yields a 400/403
    SignatureDoesNotMatch. urllib.request sends the URL verbatim (like curl),
    so the signature stays intact. No auth header is needed — the presigned
    URL is self-authenticating.
    """
    url = file_path if re.match(r"https?://", file_path) else f"{base_url}{file_path}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(1 << 20)  # 1 MiB
            if not chunk:
                break
            f.write(chunk)
    if not zipfile.is_zipfile(dest):
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded file is not a valid zip: {dest}")


def sanitize(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", name)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_session(token: str) -> requests.Session:
    sess = requests.Session()
    sess.headers["Authorization"] = f"Bearer {token}"
    return sess


def print_table(title: str, rows: list[tuple], headers: list[str]) -> None:
    col_widths = [max(len(h), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    sep = "  ".join("-" * w for w in col_widths)
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(f"\n{title}")
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(v) for v in row]))


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Xtreme1 base URL")
    ap.add_argument("--token", default=None, help="Use an existing bearer token (skips login)")
    ap.add_argument(
        "--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Directory for downloaded zips"
    )
    ap.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="Print target datasets and exit without downloading",
    )
    ap.add_argument(
        "--dataset",
        metavar="NAME",
        action="append",
        dest="datasets",
        help="Limit to this dataset name (repeatable; for smoke tests)",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Export polling timeout in seconds (default {DEFAULT_TIMEOUT})",
    )
    ap.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help=f"Polling interval in seconds (default {DEFAULT_POLL_INTERVAL})",
    )
    args = ap.parse_args()

    # --- authentication ---
    if args.token:
        token = args.token
        sess = build_session(token)
    else:
        username = os.environ.get("XTREME1_USER")
        password = os.environ.get("XTREME1_PASS")
        if not username or not password:
            sys.exit(
                "error: XTREME1_USER and XTREME1_PASS env vars are required "
                "(or pass --token)"
            )
        print(f"Logging in as {username} …", flush=True)
        sess = requests.Session()
        token = login(sess, args.base_url, username, password)
        sess = build_session(token)
        print("Login OK", flush=True)

    # --- fetch datasets ---
    print("Fetching dataset list …", flush=True)
    all_datasets = fetch_all_datasets(sess, args.base_url)
    print(f"Found {len(all_datasets)} {DATASET_TYPE} datasets total", flush=True)

    targets, excluded = select_target_datasets(all_datasets)

    # apply --dataset filter (smoke)
    if args.datasets:
        name_filter = set(args.datasets)
        targets = [d for d in targets if d["name"] in name_filter]
        missing = name_filter - {d["name"] for d in targets}
        if missing:
            print(f"warning: --dataset not found among targets: {sorted(missing)}", file=sys.stderr)

    # --- print excluded table ---
    if excluded:
        exc_rows = [(d["name"], d.get("annotatedCount", 0), d["exclude_reason"]) for d in excluded]
        print_table(
            f"Excluded datasets ({len(excluded)})",
            exc_rows,
            ["Name", "AnnotatedCount", "Reason"],
        )

    # --- print target table ---
    total_annotated = sum(d.get("annotatedCount", 0) for d in targets)
    if targets:
        tgt_rows = [(d["name"], d.get("annotatedCount", 0), d["id"]) for d in targets]
        print_table(
            f"Target datasets ({len(targets)})  —  total ANNOTATED frames: {total_annotated}",
            tgt_rows,
            ["Name", "AnnotatedCount", "ID"],
        )
    else:
        print("\nNo target datasets found.")

    if args.list_only:
        return

    if not targets:
        sys.exit("Nothing to download.")

    # --- export & download ---
    args.out_dir.mkdir(parents=True, exist_ok=True)

    def export_unit(label: str, ds_id: int, parent_id: int | None, out_path: Path) -> int:
        """Export+download one unit (flat dataset or one scene). Returns frame count."""
        sn = start_export(sess, args.base_url, ds_id, parent_id=parent_id)
        print(f"[{label}] serialNumber={sn}", flush=True)
        rec = poll_export(sess, args.base_url, sn, args.timeout, args.poll_interval, label)
        file_path = rec.get("filePath")
        if not file_path:
            raise RuntimeError(f"COMPLETED record has no filePath: {rec!r}")
        print(f"[{label}] Downloading → {out_path} …", flush=True)
        download_zip(sess, args.base_url, file_path, out_path)
        total_num = rec.get("totalNum") or 0
        size_mb = out_path.stat().st_size / (1 << 20)
        print(f"[{label}] OK  {total_num} frames  {size_mb:.1f} MiB → {out_path}", flush=True)
        return total_num

    failures = []
    for ds in targets:
        ds_name = ds["name"]
        ds_id = ds["id"]
        expected = ds.get("annotatedCount", 0)
        slug = sanitize(ds_name)
        print(f"\n[{ds_name}] Starting export (id={ds_id}) …", flush=True)
        try:
            scene_ids = fetch_scene_ids(sess, args.base_url, ds_id)
            if not scene_ids:
                # flat dataset: annotationStatus filter applies to frames directly
                got = export_unit(ds_name, ds_id, None, args.out_dir / f"{slug}.zip")
            else:
                # scene dataset(s): export each scene's annotated children
                print(f"[{ds_name}] scene-structured ({len(scene_ids)} scene(s))", flush=True)
                got = 0
                for i, sid in enumerate(scene_ids):
                    out_path = (args.out_dir / f"{slug}.zip" if len(scene_ids) == 1
                                else args.out_dir / f"{slug}__scene{sid}.zip")
                    got += export_unit(f"{ds_name}#scene{sid}", ds_id, sid, out_path)
            if got != expected:
                print(
                    f"warning [{ds_name}]: expected {expected} ANNOTATED frames, "
                    f"export produced {got}",
                    file=sys.stderr,
                )
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR [{ds_name}]: {exc}", file=sys.stderr)
            failures.append((ds_name, str(exc)))

    print(f"\n{'='*60}")
    print(f"Done: {len(targets) - len(failures)}/{len(targets)} datasets downloaded successfully.")
    if failures:
        print("Failed:")
        for name, err in failures:
            print(f"  {name}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
