#!/usr/bin/env python3
"""
Benchmark the hierarchical analysis pipeline.

Usage:
    cd /tmp/painting-instructor
    python scripts/benchmark.py

Requires: requirements.txt installed (no ML models needed).
Reports per-stage timing and peak RSS memory for synthetic test images.
"""
from __future__ import annotations
import sys
import time
import tracemalloc
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

# Make sure backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Synthetic image generators ────────────────────────────────────────────────

def _portrait(px: int) -> Image.Image:
    """Gradient portrait: smooth skin tones + dark background."""
    arr = np.zeros((px, px, 3), dtype=np.uint8)
    cx, cy = px // 2, px // 2
    r = px // 3
    for y in range(px):
        for x in range(px):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            t = np.clip(1 - d / r, 0, 1)
            arr[y, x] = [
                int(200 * t + 30 * (1 - t)),
                int(150 * t + 20 * (1 - t)),
                int(120 * t + 15 * (1 - t)),
            ]
    return Image.fromarray(arr)


def _textured(px: int) -> Image.Image:
    """High-frequency noise texture."""
    rng = np.random.default_rng(42)
    base = rng.integers(60, 200, (px, px, 3), dtype=np.uint8)
    noise = rng.integers(0, 40, (px, px, 3), dtype=np.uint8)
    return Image.fromarray(np.clip(base.astype(int) + noise, 0, 255).astype(np.uint8))


def _flat(px: int) -> Image.Image:
    """Flat decorative image with a few solid colour blocks."""
    arr = np.full((px, px, 3), 240, dtype=np.uint8)
    colours = [(220, 80, 60), (60, 140, 200), (80, 180, 80), (240, 200, 50)]
    block = px // 4
    for i, c in enumerate(colours):
        r = i // 2
        col = i % 2
        arr[r * (px // 2): r * (px // 2) + px // 2,
            col * (px // 2): col * (px // 2) + px // 2] = c
    return Image.fromarray(arr)


# ── Benchmark harness ─────────────────────────────────────────────────────────

@dataclass
class StageResult:
    name: str
    wall_ms: float
    peak_kb: int = 0


@dataclass
class BenchResult:
    image_name: str
    px: int
    stages: list[StageResult] = field(default_factory=list)
    total_wall_ms: float = 0.0
    peak_kb: int = 0
    n_regions: int = 0
    n_edges: int = 0


def _bench_one(name: str, img: Image.Image, px: int) -> BenchResult:
    from backend.analysis.preprocessing import prepare
    from backend.analysis.values import compute_value_zones
    from backend.analysis.colours import extract_colour_families
    from backend.analysis.regions import build_region_hierarchy
    from backend.analysis.edges import extract_edge_hierarchy
    from backend.analysis.renderer import render_detail_levels

    import tempfile, os
    out_dir = Path(tempfile.mkdtemp()) / "bench_out"
    out_dir.mkdir()

    stages: list[StageResult] = []
    res = BenchResult(image_name=name, px=px)

    tracemalloc.start()
    t_global = time.perf_counter()

    def stage(stage_name: str, fn):
        t0 = time.perf_counter()
        result = fn()
        ms = (time.perf_counter() - t0) * 1000
        _, peak = tracemalloc.get_traced_memory()
        stages.append(StageResult(stage_name, ms, peak // 1024))
        return result

    cache = stage("preprocessing", lambda: prepare(img))
    zone_map, zones = stage("value_zones", lambda: compute_value_zones(cache, 5))
    families, palette, internal = stage("colour_families", lambda: extract_colour_families(cache, 12))
    label_maps, regions = stage(
        "build_hierarchy",
        lambda: build_region_hierarchy(cache, 12, 3, 5, internal),
    )

    lm_for_edges = None
    for k in ["l3", "l4", "l2", "l5", "l1"]:
        if k in label_maps:
            lm_for_edges = label_maps[k]
            break
    mapping = {r.source_label: r.id for r in regions if r.scale == k}

    edges, edge_maps = stage(
        "edge_hierarchy",
        lambda: extract_edge_hierarchy(cache, lm_for_edges, label_to_region_id=mapping),
    )

    from backend.analysis.edges import render_outline_levels
    outlines = stage("outline_composites", lambda: render_outline_levels(edge_maps))

    detail_levels = stage(
        "render_5_levels",
        lambda: render_detail_levels(
            cache=cache,
            label_maps=label_maps,
            regions=regions,
            families=families,
            value_zones=zones,
            zone_map=zone_map,
            outline_composites=outlines,
            out_dir=out_dir,
        ),
    )

    total_ms = (time.perf_counter() - t_global) * 1000
    _, peak_kb = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    res.stages = stages
    res.total_wall_ms = total_ms
    res.peak_kb = peak_kb // 1024
    res.n_regions = len(regions)
    res.n_edges = len(edges)

    import shutil
    shutil.rmtree(str(out_dir.parent), ignore_errors=True)
    return res


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    cases = [
        ("portrait-512",  _portrait(512),  512),
        ("portrait-1024", _portrait(1024), 1024),
        ("textured-1024", _textured(1024), 1024),
        ("flat-1024",     _flat(1024),     1024),
    ]

    results: list[BenchResult] = []
    for name, img, px in cases:
        print(f"  benchmarking {name} … ", end="", flush=True)
        try:
            r = _bench_one(name, img, px)
            results.append(r)
            print(f"{r.total_wall_ms:.0f} ms  peak {r.peak_kb} KB  "
                  f"{r.n_regions} regions  {r.n_edges} edges")
        except Exception as e:
            print(f"FAILED: {e}")
            traceback_str = __import__("traceback").format_exc()
            print(traceback_str[:500])

    # ── Print summary table ───────────────────────────────────────────────────
    if not results:
        print("No results.")
        return

    print("\n" + "=" * 90)
    print("BENCHMARK RESULTS — Hierarchical Analysis Pipeline")
    print("=" * 90)

    # Per-stage table
    all_stages = [s.name for s in results[0].stages]
    col_w = 22
    img_w = 16
    header = f"{'Stage':{col_w}}" + "".join(f"{r.image_name:{img_w}}" for r in results)
    print(header)
    print("-" * len(header))
    for stage_name in all_stages:
        row = f"{stage_name:{col_w}}"
        for r in results:
            ms = next((s.wall_ms for s in r.stages if s.name == stage_name), 0)
            row += f"{ms:>10.0f} ms   "
        print(row)

    print("-" * len(header))
    row = f"{'TOTAL':{col_w}}"
    for r in results:
        row += f"{r.total_wall_ms:>10.0f} ms   "
    print(row)

    row = f"{'Peak memory (MB)':{col_w}}"
    for r in results:
        row += f"{r.peak_kb / 1024:>10.1f} MB   "
    print(row)

    row = f"{'Regions':{col_w}}"
    for r in results:
        row += f"{r.n_regions:>12}    "
    print(row)

    row = f"{'Edges':{col_w}}"
    for r in results:
        row += f"{r.n_edges:>12}    "
    print(row)

    print("=" * 90)
    print("\nNotes:")
    print("  - 'before' baseline not available (previous code rendered empty images)")
    print("  - Timings exclude: video generation, PDF, classic pipeline steps")
    print("  - No ML models loaded (rembg/controlnet not required for core analysis)")
    print("  - Run on macOS (Darwin 25.5.0, Apple Silicon)")


if __name__ == "__main__":
    main()
