#!/usr/bin/env python3
"""Parity guard for the two mirrored rule-validation constant sources.

VALID_SIZE / VALID_IOU are CANONICAL in app.py and mirrored in the frontend at
frontend/pc-tool/src/packages/pc-editor/config/validation.ts. The frontend
computes the suspicious-box predicate client-side (serving flags are stripped by
the closed Java ModelResultConverter), so the two sets must stay identical or
#1 (client highlight) and #2 (serving emission) would disagree silently (R-drift).

This asserts they are equal. Run it directly:

    python3 deploy/point-cloud-detection/test_validation_parity.py

It also exposes test_* functions so a pytest run picks it up. If validation.ts
does not exist yet (worker-1 lands it in parallel), the test is skipped with a
clear message rather than failing -- it activates once the mirror is committed.
"""
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
VALIDATION_TS = os.path.join(
    REPO_ROOT, 'frontend', 'pc-tool', 'src', 'packages',
    'pc-editor', 'config', 'validation.ts')


def _load_app_constants():
    """Read VALID_SIZE / VALID_IOU from app.py WITHOUT importing it.

    app.py imports heavy runtime deps (numpy, pcdet_open, requests) that are not
    present in a bare test environment, so parse the module's AST and evaluate
    only the two constant assignments we care about."""
    tree = ast.parse(open(os.path.join(HERE, 'app.py')).read())
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in (
                    'VALID_SIZE', 'VALID_IOU'):
                found[target.id] = ast.literal_eval(node.value)
    missing = {'VALID_SIZE', 'VALID_IOU'} - set(found)
    if missing:
        raise AssertionError(f"app.py is missing constant(s): {sorted(missing)}")
    return found['VALID_SIZE'], found['VALID_IOU']


def _parse_ts_valid_iou(src):
    # anchor on the `export const VALID_IOU = <number>` assignment; a leading
    # `export const` avoids matching the `VALID_IOU` mentioned in a comment, and
    # requiring `=` avoids the `:` of any type annotation.
    m = re.search(r'\bconst\s+VALID_IOU\b[^=]*=\s*([0-9.]+)', src)
    if not m:
        raise AssertionError("could not find VALID_IOU assignment in validation.ts")
    return float(m.group(1))


def _parse_ts_valid_size(src):
    """Extract the VALID_SIZE object literal and coerce it to the same nested
    {CLASS: {axis: [min, max]}} dict shape app.py uses. Tolerant of trailing
    commas, single quotes, and a TS type annotation (`: Record<...> =`); converts
    the JS object body to JSON."""
    # find the `= {` that opens the object literal, skipping any `: <type>` part
    m = re.search(r'\bconst\s+VALID_SIZE\b[^=]*=\s*\{', src)
    if not m:
        raise AssertionError("could not find VALID_SIZE assignment in validation.ts")
    start = src.index('{', m.end() - 1)
    depth = 0
    end = None
    for i in range(start, len(src)):
        c = src[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise AssertionError("unbalanced braces in VALID_SIZE literal")
    body = src[start:end]
    # strip line comments, quote bare keys, normalize quotes, drop trailing commas
    body = re.sub(r'//[^\n]*', '', body)
    body = re.sub(r"'", '"', body)
    body = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', body)
    body = re.sub(r',(\s*[}\]])', r'\1', body)
    return json.loads(body)


def _normalize(size):
    """Canonicalize both sources to {CLASS: {axis: (min, max)}} with float
    tuples so a Python dict (tuples) and JSON parse (lists) compare equal."""
    out = {}
    for cls, axes in size.items():
        out[cls] = {ax: (float(rng[0]), float(rng[1])) for ax, rng in axes.items()}
    return out


def check_parity():
    app_size, app_iou = _load_app_constants()
    if not os.path.exists(VALIDATION_TS):
        return ('skip', f"validation.ts not present yet at {VALIDATION_TS}; "
                        "parity guard will activate once it is committed.")
    src = open(VALIDATION_TS).read()
    ts_iou = _parse_ts_valid_iou(src)
    ts_size = _parse_ts_valid_size(src)

    assert app_iou == ts_iou, f"VALID_IOU mismatch: app.py={app_iou} ts={ts_iou}"
    a, t = _normalize(app_size), _normalize(ts_size)
    assert a == t, (
        "VALID_SIZE mismatch between app.py and validation.ts:\n"
        f"  app.py keys: {sorted(a)}\n  ts keys:     {sorted(t)}\n"
        f"  per-class diffs: "
        f"{[(c, a.get(c), t.get(c)) for c in set(a) | set(t) if a.get(c) != t.get(c)]}")
    return ('ok', "VALID_SIZE / VALID_IOU are identical across app.py and validation.ts")


def test_valid_iou_parity():
    app_size, app_iou = _load_app_constants()
    if not os.path.exists(VALIDATION_TS):
        return  # mirror not committed yet; guard is dormant
    ts_iou = _parse_ts_valid_iou(open(VALIDATION_TS).read())
    assert app_iou == ts_iou, f"VALID_IOU mismatch: app.py={app_iou} ts={ts_iou}"


def test_valid_size_parity():
    app_size, app_iou = _load_app_constants()
    if not os.path.exists(VALIDATION_TS):
        return  # mirror not committed yet; guard is dormant
    ts_size = _parse_ts_valid_size(open(VALIDATION_TS).read())
    assert _normalize(app_size) == _normalize(ts_size)


if __name__ == '__main__':
    status, msg = check_parity()
    print(f"[{status.upper()}] {msg}")
    sys.exit(0 if status in ('ok', 'skip') else 1)
