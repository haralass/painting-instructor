from __future__ import annotations
"""
Progressive painting tutorial video generator.

Produces a time-lapse style video showing how to build up a painting from
scratch, phase by phase — the way a real instructor would demonstrate. The
six phases follow the same construction -> values -> colour -> edges ->
detail sequence every medium's teaching stages already describe:

  Phase 0 — Reference photo (2s hold)
  Phase 1 — Ground / construction     (stage 1: toned ground, construction lines...)
  Phase 2 — Lay-in / gesture          (stage 2: block-in, outlines)
  Phase 3 — Value masses              (stage 3: value development)
  Phase 4 — Colour blocking           (stage 4: colour modelling)
  Phase 5 — Edge refinement & detail  (stages 5-6: edge control, final detail)
  Phase 6 — Final comparison (split: left=reference, right=painting)

When `medium_stages` (a medium's ordered teaching stages) and `stage_images`
(a resolved image per stage order, from the lesson_plan) are provided, each
phase's on-screen title/subtitle and visual content come from that medium's
real stage — otherwise it falls back to generic labels using the four
classic assets, exactly as before. The wipe/fade/scan mechanics are
unchanged either way; only what gets displayed and labelled changes.

The video is MP4, default 1080px wide, 24 fps.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

from ...utils.fonts import get_font as _font

FPS       = 24
OUT_W     = 1080          # output video width (height derived from aspect)
HOLD_SECS = 2.0           # hold time for static frames (reference, final)
FADE_SECS = 3.0           # transition duration for animated phases


def _to_rgb(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    """Resize PIL image to (W, H) and return HxWx3 uint8 numpy."""
    return np.array(img.convert("RGB").resize(size, Image.LANCZOS))


def _lerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    return np.clip(a.astype(float) * (1 - t) + b.astype(float) * t, 0, 255).astype(np.uint8)


def _label_frame(frame: np.ndarray, text: str, sub: str = "") -> np.ndarray:
    """Burn phase label into bottom-left of frame (in-place copy)."""
    out = frame.copy()
    img = Image.fromarray(out)
    dr  = ImageDraw.Draw(img)
    H, W = out.shape[:2]
    fn  = _font(max(18, W // 50))
    fn2 = _font(max(13, W // 70))
    # semi-transparent black bar at bottom
    bar = Image.new("RGBA", (W, 70), (0, 0, 0, 160))
    img.paste(Image.fromarray(np.zeros((70, W, 3), np.uint8)), (0, H - 70), bar)
    dr.text((16, H - 56), text, fill=(255, 255, 255), font=fn)
    if sub:
        dr.text((16, H - 28), sub, fill=(200, 200, 200), font=fn2)
    return np.array(img)


def _horizontal_wipe(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """Wipe from left: left portion shows b, right shows a."""
    H, W = a.shape[:2]
    cut  = int(W * t)
    out  = a.copy()
    if cut > 0:
        out[:, :cut] = b[:, :cut]
    return out


def _vertical_scan(base: np.ndarray, overlay: np.ndarray, t: float) -> np.ndarray:
    """
    Progressive top-down reveal of overlay on base.
    Simulates a brush sweeping down the canvas.
    """
    H, W = base.shape[:2]
    cut  = int(H * t)
    out  = base.copy()
    if cut > 0:
        out[:cut] = _lerp(base[:cut], overlay[:cut], min(1.0, t * 2))
    return out


def _stage_label(stages: list[dict], order: int, fallback_name: str, fallback_desc: str) -> tuple[str, str]:
    """Look up a medium's real stage name/description by order, or fall back
    to the generic label if no medium stage data was supplied."""
    stage = next((s for s in stages if s.get("order") == order), None)
    if stage is None:
        return fallback_name, fallback_desc
    return f"Step {order} — {stage['name']}", stage.get("description", fallback_desc)


def generate(
    reference: Image.Image,
    line_art:  Image.Image,
    notan:     Image.Image,
    color_blocking: Image.Image,
    output_path: str,
    fps: int = FPS,
    out_w: int = OUT_W,
    medium_stages: list[dict] | None = None,
    stage_images: dict[int, Image.Image] | None = None,
    stroke_frames: list[Image.Image] | None = None,
) -> dict:
    """
    Generate progressive painting tutorial video.

    Args:
        reference:      Original photo (used as first frame + final comparison).
        line_art:       Black-lines-on-white composite (from line_art processor).
        notan:          3-zone notan (from artist_breakdown.notan).
        color_blocking: Paint-by-number result (the hierarchy-based render).
        output_path:    Destination .mp4 path.
        fps:            Frames per second (default 24).
        out_w:          Output video width in pixels (height maintains aspect).
        medium_stages:  The selected medium's ordered teaching stages
                        (get_medium(medium)["stages"]) — used for real
                        on-screen labels instead of generic step text.
        stage_images:   {stage_order: PIL.Image} — the lesson_plan's best
                        resolved image per stage (e.g. that stage's own
                        detail-level outlines/values), substituted for the
                        generic classic asset in that phase when available.

    Returns:
        {"path": output_path, "chapters": [{"order", "name", "start_sec"}]}
    """
    stages = medium_stages or []
    stage_imgs = stage_images or {}
    stroke_seq = stroke_frames or []

    # ── standardise sizes ─────────────────────────────────────────────────
    W_ref, H_ref = reference.size
    aspect = H_ref / W_ref
    W = out_w
    H = int(W * aspect)
    size = (W, H)

    ref_arr   = _to_rgb(reference, size)
    la_arr    = _to_rgb(stage_imgs.get(2, line_art), size)         # gesture/lay-in overlay
    notan_arr = _to_rgb(stage_imgs.get(3, notan), size)            # value masses overlay
    color_arr = _to_rgb(stage_imgs.get(4, color_blocking), size)   # colour blocking overlay
    detail_src_img = stage_imgs.get(6, color_blocking)
    detail_arr = _to_rgb(detail_src_img, size)                     # final detail overlay

    # Canvas starts white
    canvas    = np.ones((H, W, 3), dtype=np.uint8) * 245

    # Line art as overlay: invert so transparent background, dark lines
    # lines are dark (near 0), background is light (near 255)
    la_mask = (la_arr.mean(axis=2) < 128).astype(np.float32)   # 1 where line is dark

    # "Line art painted onto canvas" — canvas with lines drawn in
    def apply_lines(base: np.ndarray, line_alpha: float = 1.0) -> np.ndarray:
        lines = la_mask[:, :, None] * line_alpha
        dark  = np.array([40, 40, 40], dtype=np.float32)
        return np.clip(base.astype(float) * (1 - lines) + dark * lines, 0, 255).astype(np.uint8)

    # ── video writer ──────────────────────────────────────────────────────
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (W, H))

    hold_n = int(HOLD_SECS * fps)
    anim_n = int(FADE_SECS * fps)

    frame_count = 0
    chapters: list[dict] = []

    def _write(frames: list[np.ndarray]) -> None:
        nonlocal frame_count
        for f in frames:
            writer.write(cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
        frame_count += len(frames)

    def _mark(order: int, name: str) -> None:
        chapters.append({"order": order, "name": name, "start_sec": round(frame_count / fps, 2)})

    # ── Phase 0: Reference photo ──────────────────────────────────────────
    _mark(0, "Reference Photo")
    f0 = _label_frame(ref_arr, "Reference Photo", "Study this before you pick up a brush")
    _write([f0] * hold_n)

    # ── Phase 1: Ground / construction (quick hold) ──────────────────────
    name1, desc1 = _stage_label(stages, 1, "Step 1 — Blank Canvas", "Start with a toned canvas (warm ivory)")
    _mark(1, name1)
    for t in np.linspace(0, 1, max(1, fps // 2)):
        _write([_lerp(f0, _label_frame(canvas, name1, desc1), t)])
    f1 = _label_frame(canvas, name1, desc1)
    _write([f1] * (fps // 2))

    # ── Phase 2: Lay-in / gesture (top-down scan) ────────────────────────
    name2, desc2 = _stage_label(stages, 2, "Step 2 — Gesture & Outlines", "Establish proportions and key edges first")
    _mark(2, name2)
    canvas_with_lines = apply_lines(canvas)
    for i in range(anim_n):
        t = i / max(1, anim_n - 1)
        frame = _vertical_scan(canvas, canvas_with_lines, t)
        frame = _label_frame(frame, name2, desc2)
        _write([frame])
    f2 = _label_frame(canvas_with_lines, name2, desc2)
    _write([f2] * (fps // 2))

    # ── Phase 3: Value masses (horizontal wipe) ──────────────────────────
    name3, desc3 = _stage_label(stages, 3, "Step 3 — Value Masses (Notan)", "Block in shadows, midtones, lights — no colour yet")
    _mark(3, name3)
    notan_on_canvas = apply_lines(notan_arr, line_alpha=0.6)
    for i in range(anim_n):
        t = i / max(1, anim_n - 1)
        frame = _horizontal_wipe(canvas_with_lines, notan_on_canvas, t)
        frame = _label_frame(frame, name3, desc3)
        _write([frame])
    f3 = _label_frame(notan_on_canvas, name3, desc3)
    _write([f3] * (fps // 2))

    # ── Phase 4: Colour — real stroke-by-stroke painting when available ───
    name4, desc4 = _stage_label(stages, 4, "Step 4 — Colour Blocking", "Fill flat colour zones — match your palette numbers")
    _mark(4, name4)
    if stroke_seq:
        # Actual oil strokes accumulating on the canvas (blank → painted),
        # big masses first — the "watch it painted" phase. Pace the frames so
        # the whole sequence spans roughly the same time as the old crossfade.
        stroke_arrs = [_to_rgb(s, size) for s in stroke_seq]
        hold_each = max(1, (2 * anim_n) // len(stroke_arrs))
        for arr in stroke_arrs:
            _write([_label_frame(arr, name4, "Paint the masses stroke by stroke — big shapes first")] * hold_each)
        color_on_canvas = stroke_arrs[-1]
        _write([_label_frame(color_on_canvas, name4, desc4)] * (fps // 2))
    else:
        color_on_canvas = apply_lines(color_arr, line_alpha=0.7)
        for i in range(anim_n):
            t = i / max(1, anim_n - 1)
            frame = _lerp(notan_on_canvas, color_on_canvas, t)
            frame = _label_frame(frame, name4, desc4)
            _write([frame])
        f4 = _label_frame(color_on_canvas, name4, desc4)
        _write([f4] * (fps // 2))

    # ── Phase 5a: Edge refinement (short hold, stage 5's own label) ───────
    name5, desc5 = _stage_label(stages, 5, "Step 5 — Edge Refinement", "Harden the edges that matter, soften the rest")
    _mark(5, name5)
    f5a = _label_frame(color_on_canvas, name5, desc5)
    _write([f5a] * (fps // 2))

    # ── Phase 5b: Detail & texture (re-apply crisp lines, stage 6 label) ──
    name6, desc6 = _stage_label(stages, 6, "Step 6 — Detail & Edges", "Sharpen edges, add final accents and highlights")
    _mark(6, name6)
    # With real strokes the finished painting IS the detail frame — don't
    # stamp line art back over the brushwork.
    detail = color_on_canvas if stroke_seq else apply_lines(detail_arr, line_alpha=1.0)
    for i in range(anim_n):
        t = i / max(1, anim_n - 1)
        frame = _lerp(color_on_canvas, detail, t)
        frame = _label_frame(frame, name6, desc6)
        _write([frame])
    f6 = _label_frame(detail, name6, desc6)
    _write([f6] * hold_n)

    # ── Phase 6: Split comparison (final vs reference) ────────────────────
    _mark(7, "Result")
    half = W // 2
    for i in range(anim_n):
        t = i / max(1, anim_n - 1)
        cut = int(half * t)
        comp = detail.copy()
        comp[:, :cut] = ref_arr[:, :cut]
        comp[:, cut:cut+3] = [255, 255, 0]   # yellow divider
        comp = _label_frame(comp, "Result — Follow these steps and you get this",
                            "Reference (left) vs your painting (right)")
        _write([comp])
    final_comp = detail.copy()
    final_comp[:, :half]      = ref_arr[:, :half]
    final_comp[:, half:half+3] = [255, 255, 0]
    final_comp = _label_frame(final_comp, "Result — Follow these steps and you get this",
                              "Reference (left) vs your painting (right)")
    _write([final_comp] * (hold_n * 2))

    writer.release()
    return {"path": output_path, "chapters": chapters}
