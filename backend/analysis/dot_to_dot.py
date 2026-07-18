"""
Real numbered dot-to-dot (brief §14) — built from the Phase-3 vector paths,
like a classic printable: sequential numbers, continuous paths, dots dense at
curves and corners, sparse on straights, difficulty levels, and a solution
variant. Replaces the old unnumbered "smart dots" render.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from ..utils.fonts import get_font

# difficulty → (which paths, target dot range)
DIFFICULTIES = {
    "simple":   dict(contour="simple",   internal=0,  tonal=False, target=(30, 80)),
    "standard": dict(contour="standard", internal=4,  tonal=False, target=(80, 200)),
    "detailed": dict(contour="refined",  internal=12, tonal=True,  target=(200, 500)),
}


def _resample(points: list, closed: bool, max_gap: float) -> list[tuple[float, float]]:
    """Keep every vertex (corners/curves — approxPolyDP already put vertices
    there) and subdivide long straight runs so gaps never exceed max_gap.
    Vertices cluster on curves ⇒ dense there; straights get few dots."""
    pts = [tuple(p) for p in points]
    if closed and pts and pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    out: list[tuple[float, float]] = []
    for a, b in zip(pts, pts[1:]):
        out.append(a)
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n_extra = int(d // max_gap)
        for k in range(1, n_extra + 1):
            t = k / (n_extra + 1)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    if not closed and pts:
        out.append(pts[-1])
    return out


def _paths_for(drawing: dict, cfg: dict) -> list[tuple[list, bool]]:
    """Ordered path groups (points, closed) — silhouette first (pedagogical
    order), then the most important internal / tonal shapes."""
    groups: list[tuple[list, bool]] = []
    sil = (drawing.get("silhouette_levels") or {}).get(cfg["contour"]) or drawing.get("silhouette")
    if sil and len(sil.get("points", [])) >= 3:
        groups.append((sil["points"], True))
    internals = sorted(drawing.get("internal_paths", []),
                       key=lambda p: -p.get("importance", 0))[: cfg["internal"]]
    for p in internals:
        if len(p.get("points", [])) >= 2:
            groups.append((p["points"], bool(p.get("closed"))))
    if cfg["tonal"]:
        for p in (drawing.get("tonal_paths") or [])[:4]:
            if len(p.get("points", [])) >= 3:
                groups.append((p["points"], True))
    return groups


def build_dots(drawing: dict, difficulty: str = "standard") -> list[list[tuple[float, float]]]:
    """Numbered dot groups for one difficulty, tuned into its target range."""
    cfg = DIFFICULTIES[difficulty]
    lo, hi = cfg["target"]
    W, H = drawing.get("image_width", 1), drawing.get("image_height", 1)
    diag = math.hypot(W, H)
    groups = _paths_for(drawing, cfg)
    if not groups:
        return []
    # Binary-search the gap so the total lands inside the target range.
    gap = diag / 30
    for _ in range(12):
        dots = [_resample(pts, closed, gap) for pts, closed in groups]
        total = sum(len(d) for d in dots)
        if total < lo:
            gap *= 0.75
        elif total > hi:
            gap *= 1.3
        else:
            break
    return dots


def render_dot_to_dot(drawing: dict, out_path, difficulty: str = "standard",
                      show_solution: bool = False) -> dict | None:
    """Printable page: white ground, numbered dots (dense on curves, sparse on
    straights), continuous numbering across groups; optional faint solution."""
    groups = build_dots(drawing, difficulty)
    if not groups:
        return None
    W, H = drawing["image_width"], drawing["image_height"]
    scale = max(1.0, 900 / max(W, H))          # print-friendly resolution
    img = Image.new("RGB", (int(W * scale), int(H * scale)), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    font = get_font(max(9, int(11 * scale * max(W, H) / 900)))
    r = max(2, int(2.2 * scale))
    n = 0
    for pts in groups:
        S = [(x * scale, y * scale) for x, y in pts]
        if show_solution and len(S) >= 2:
            dr.line(S + [S[0]] if len(S) > 2 else S, fill=(200, 200, 200), width=max(1, int(scale)))
        prev = None
        for (x, y) in S:
            n += 1
            dr.ellipse([x - r, y - r, x + r, y + r], fill=(30, 30, 30))
            # place the number away from the previous dot so it doesn't sit on the line
            ang = math.atan2(y - prev[1], x - prev[0]) + math.pi / 2 if prev else -math.pi / 3
            tx, ty = x + math.cos(ang) * r * 3.2, y + math.sin(ang) * r * 3.2
            dr.text((tx, ty), str(n), fill=(60, 60, 60), font=font, anchor="mm")
            prev = (x, y)
    img.save(out_path)
    return {"path": str(out_path), "difficulty": difficulty, "n_dots": n,
            "n_groups": len(groups)}


def render_all(drawing: dict, out_dir) -> dict:
    """All difficulty variants (+ solutions). dot_to_dot.png stays the
    standard one so existing manifests keep resolving."""
    from pathlib import Path
    out_dir = Path(out_dir)
    variants: dict[str, dict] = {}
    for diff in DIFFICULTIES:
        stem = "dot_to_dot" if diff == "standard" else f"dot_to_dot_{diff}"
        info = render_dot_to_dot(drawing, out_dir / f"{stem}.png", diff)
        if info:
            sol = render_dot_to_dot(drawing, out_dir / f"{stem}_solution.png", diff,
                                    show_solution=True)
            info["solution"] = sol["path"] if sol else None
            variants[diff] = info
    return variants
