#!/usr/bin/env python3
"""
Fetch the optional local-ML-tier model weights into backend/models/.

The subject mask (u2netp.onnx, ~4.6 MB) is committed with the repo, so the app
works out of the box. The depth model (~99 MB) is too large for git — run this
once to enable the depth/planes tier. Everything degrades gracefully without it.

Usage:
    python scripts/fetch_models.py            # fetch everything missing
    python scripts/fetch_models.py --force    # re-download even if present
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1] / "backend" / "models"

# name -> (url, approx MB). Kept to permissive-licence, offline-usable exports.
MODELS = {
    "depth_anything_v2_vits.onnx": (
        "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx",
        99,
    ),
    # u2netp is committed; listed so --force can refresh it if ever needed.
    "u2netp.onnx": (
        "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
        5,
    ),
}


def _fetch(name: str, url: str, approx_mb: int, force: bool) -> None:
    dest = MODELS_DIR / name
    if dest.exists() and not force:
        print(f"✓ {name} already present ({dest.stat().st_size // (1024*1024)} MB)")
        return
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"↓ {name} (~{approx_mb} MB) …")
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
        print(f"✓ {name} -> {dest} ({dest.stat().st_size // (1024*1024)} MB)")
    except Exception as e:  # noqa: BLE001 - CLI, surface the reason and continue
        tmp.unlink(missing_ok=True)
        print(f"✗ {name} failed: {e}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    ap.add_argument("--only", help="fetch only this model filename")
    args = ap.parse_args()

    items = MODELS.items()
    if args.only:
        if args.only not in MODELS:
            sys.exit(f"unknown model {args.only!r}; choices: {', '.join(MODELS)}")
        items = [(args.only, MODELS[args.only])]

    for name, (url, mb) in items:
        _fetch(name, url, mb, args.force)


if __name__ == "__main__":
    main()
