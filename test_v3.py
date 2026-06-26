#!/usr/bin/env python3
"""
Test script for v3 pipeline processors.
Run from: /Users/haralambospieri/Desktop/personal-art-book/
"""
from __future__ import annotations
import sys
import time
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent / "backend"))

IMG_PATH = "/Users/haralambospieri/Desktop/6A97CAA2-5421-4C9D-800D-DB2C91DB10ED_1_105_c.jpeg"
OUT_DIR  = Path(__file__).parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)

def load(path: str, max_side: int = 800) -> Image.Image:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    return img


def run(name: str, fn, save_path: str):
    print(f"\n── {name} ──", flush=True)
    t0 = time.time()
    try:
        result = fn()
        result.save(save_path)
        print(f"   ✓  {save_path}  ({time.time()-t0:.1f}s)", flush=True)
    except Exception as e:
        import traceback
        print(f"   ✗  {e}", flush=True)
        traceback.print_exc()


if __name__ == "__main__":
    print(f"Loading: {IMG_PATH}", flush=True)
    img = load(IMG_PATH)
    print(f"Image: {img.size[0]}x{img.size[1]}px\n", flush=True)

    # ── Line art v3 ──────────────────────────────────────────────────────────
    from pipeline.line_art.processor import process as line_art_v3
    run("Line art v3 (composite 3-layer)", lambda: line_art_v3(img), str(OUT_DIR / "v3_line_art.png"))

    # ── Dot to dot v3 ────────────────────────────────────────────────────────
    from pipeline.dot_to_dot.processor import process as dot_to_dot_v3
    run("Dot to dot v3 (DexiNed+skeleton)", lambda: dot_to_dot_v3(img, n_dots=500), str(OUT_DIR / "v3_dot_to_dot.png"))

    # ── Color by number v3 ───────────────────────────────────────────────────
    from pipeline.color_by_number.processor import process as cbn_v3
    run("Color by number v3 (bilateral+BiSeNet+32c)", lambda: cbn_v3(img, n_colors=32), str(OUT_DIR / "v3_color_by_number.png"))

    print("\n✓ All steps complete. Check outputs/", flush=True)
