#!/usr/bin/env python3
"""Run pending v3 outputs: dot_to_dot (using existing line art) and color_by_number."""
from __future__ import annotations
import sys, time
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent / "backend"))

IMG_PATH  = "/Users/haralambospieri/Desktop/6A97CAA2-5421-4C9D-800D-DB2C91DB10ED_1_105_c.jpeg"
OUT_DIR   = Path(__file__).parent / "outputs"


def load(path, max_side=800):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        s = max_side / max(w, h)
        img = img.resize((int(w*s), int(h*s)), Image.LANCZOS)
    return img


def run(name, fn, save_path):
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
    img      = load(IMG_PATH)
    line_art = Image.open(OUT_DIR / "v3_line_art.png").convert("RGB")
    print(f"Image: {img.size[0]}x{img.size[1]}px — using existing line art", flush=True)

    from pipeline.dot_to_dot.processor import process as dot_to_dot_v3
    run(
        "Dot-to-dot v3 (skeleton from line art — no DexiNed)",
        lambda: dot_to_dot_v3(img, n_dots=500, line_art_img=line_art),
        str(OUT_DIR / "v3_dot_to_dot.png"),
    )

    from pipeline.color_by_number.processor import process as cbn_v3
    run(
        "Color-by-number v3 (bilateral+BiSeNet+32c)",
        lambda: cbn_v3(img, n_colors=32),
        str(OUT_DIR / "v3_color_by_number.png"),
    )

    print("\n✓ Done", flush=True)
