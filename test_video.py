#!/usr/bin/env python3
"""Generate the progressive painting tutorial video from already-produced v3 outputs."""
from __future__ import annotations
import sys, time
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent / "backend"))

IMG_PATH  = "/Users/haralambospieri/Desktop/6A97CAA2-5421-4C9D-800D-DB2C91DB10ED_1_105_c.jpeg"
OUT_DIR   = Path(__file__).parent / "outputs"
OUT_VIDEO = str(OUT_DIR / "v3_tutorial.mp4")


def load(path, max_side=800):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        s = max_side / max(w, h)
        img = img.resize((int(w*s), int(h*s)), Image.LANCZOS)
    return img


if __name__ == "__main__":
    print("Loading images...", flush=True)
    reference     = load(IMG_PATH)
    line_art      = Image.open(OUT_DIR / "v3_line_art.png").convert("RGB")
    notan         = Image.open(OUT_DIR / "v3_notan_3zone.png").convert("RGB")
    color_blocking = Image.open(OUT_DIR / "v3_color_by_number.png").convert("RGB")

    from pipeline.video.processor import generate

    print("Generating video...", flush=True)
    t0 = time.time()
    out = generate(
        reference=reference,
        line_art=line_art,
        notan=notan,
        color_blocking=color_blocking,
        output_path=OUT_VIDEO,
        fps=24,
        out_w=1080,
    )
    print(f"✓  {out}  ({time.time()-t0:.1f}s)", flush=True)
