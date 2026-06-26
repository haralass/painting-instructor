from __future__ import annotations
"""
Progressive painting tutorial video generator.

Produces a time-lapse style video showing how to build up a painting from
scratch, phase by phase — the way a real instructor would demonstrate:

  Phase 0 — Reference photo (2s hold)
  Phase 1 — Blank canvas
  Phase 2 — Gesture / line art fades in   (outlines only)
  Phase 3 — Value masses (Notan)           (shadow/midtone/light blocks)
  Phase 4 — Color blocking                 (paint-by-number flat fills)
  Phase 5 — Detail & edge refinement       (line art overlay re-applied)
  Phase 6 — Final comparison (split: left=reference, right=painting)

Each phase transition is animated so strokes/fills appear progressively.
The video is MP4, default 1080px wide, 24 fps.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

FPS       = 24
OUT_W     = 1080          # output video width (height derived from aspect)
HOLD_SECS = 2.0           # hold time for static frames (reference, final)
FADE_SECS = 3.0           # transition duration for animated phases


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in ["/System/Library/Fonts/HelveticaNeue.ttc",
              "/System/Library/Fonts/Helvetica.ttc",
              "/System/Library/Fonts/Arial.ttf"]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


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


def _build_notan_overlay(notan_arr: np.ndarray, canvas: np.ndarray,
                         alpha: float = 0.75) -> np.ndarray:
    """Blend notan value map over canvas at given alpha."""
    return _lerp(canvas, notan_arr, alpha)


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


def _write_frames(writer: cv2.VideoWriter, frames: list[np.ndarray]) -> None:
    for f in frames:
        writer.write(cv2.cvtColor(f, cv2.COLOR_RGB2BGR))


def generate(
    reference: Image.Image,
    line_art:  Image.Image,
    notan:     Image.Image,
    color_blocking: Image.Image,
    output_path: str,
    fps: int = FPS,
    out_w: int = OUT_W,
) -> str:
    """
    Generate progressive painting tutorial video.

    Args:
        reference:      Original photo (used as first frame + final comparison).
        line_art:       Black-lines-on-white composite (from line_art processor).
        notan:          3-zone notan (from artist_breakdown.notan).
        color_blocking: Paint-by-number result (from color_by_number processor).
        output_path:    Destination .mp4 path.
        fps:            Frames per second (default 24).
        out_w:          Output video width in pixels (height maintains aspect).

    Returns:
        output_path on success.
    """
    # ── standardise sizes ─────────────────────────────────────────────────
    W_ref, H_ref = reference.size
    aspect = H_ref / W_ref
    W = out_w
    H = int(W * aspect)
    size = (W, H)

    ref_arr   = _to_rgb(reference, size)
    la_arr    = _to_rgb(line_art,  size)    # black lines on white
    notan_arr = _to_rgb(notan,     size)
    color_arr = _to_rgb(color_blocking, size)

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

    # ── Phase 0: Reference photo ──────────────────────────────────────────
    f0 = _label_frame(ref_arr, "Reference Photo", "Study this before you pick up a brush")
    _write_frames(writer, [f0] * hold_n)

    # ── Phase 1: Blank canvas (quick hold) ───────────────────────────────
    for t in np.linspace(0, 1, max(1, fps // 2)):
        _write_frames(writer, [_lerp(f0, _label_frame(canvas, "Step 1 — Blank Canvas", "Start with a toned canvas (warm ivory)"), t)])
    f1 = _label_frame(canvas, "Step 1 — Blank Canvas", "Start with a toned canvas (warm ivory)")
    _write_frames(writer, [f1] * (fps // 2))

    # ── Phase 2: Line art / gesture drawing (top-down scan) ──────────────
    canvas_with_lines = apply_lines(canvas)
    for i in range(anim_n):
        t = i / max(1, anim_n - 1)
        frame = _vertical_scan(canvas, canvas_with_lines, t)
        frame = _label_frame(frame, "Step 2 — Gesture & Outlines",
                             "Establish proportions and key edges first")
        _write_frames(writer, [frame])
    f2 = _label_frame(canvas_with_lines, "Step 2 — Gesture & Outlines",
                      "Establish proportions and key edges first")
    _write_frames(writer, [f2] * (fps // 2))

    # ── Phase 3: Value masses / Notan (horizontal wipe) ──────────────────
    # Blend notan into the lined canvas
    notan_on_canvas = apply_lines(notan_arr, line_alpha=0.6)
    for i in range(anim_n):
        t = i / max(1, anim_n - 1)
        frame = _horizontal_wipe(canvas_with_lines, notan_on_canvas, t)
        frame = _label_frame(frame, "Step 3 — Value Masses (Notan)",
                             "Block in shadows, midtones, lights — no colour yet")
        _write_frames(writer, [frame])
    f3 = _label_frame(notan_on_canvas, "Step 3 — Value Masses (Notan)",
                      "Block in shadows, midtones, lights — no colour yet")
    _write_frames(writer, [f3] * (fps // 2))

    # ── Phase 4: Colour blocking (fade in over notan) ─────────────────────
    color_on_canvas = apply_lines(color_arr, line_alpha=0.7)
    for i in range(anim_n):
        t = i / max(1, anim_n - 1)
        frame = _lerp(notan_on_canvas, color_on_canvas, t)
        frame = _label_frame(frame, "Step 4 — Colour Blocking",
                             "Fill flat colour zones — match your palette numbers")
        _write_frames(writer, [frame])
    f4 = _label_frame(color_on_canvas, "Step 4 — Colour Blocking",
                      "Fill flat colour zones — match your palette numbers")
    _write_frames(writer, [f4] * (fps // 2))

    # ── Phase 5: Detail & edge refinement (re-apply crisp lines) ─────────
    detail = apply_lines(color_arr, line_alpha=1.0)
    for i in range(anim_n):
        t = i / max(1, anim_n - 1)
        frame = _lerp(color_on_canvas, detail, t)
        frame = _label_frame(frame, "Step 5 — Detail & Edges",
                             "Sharpen edges, add final accents and highlights")
        _write_frames(writer, [frame])
    f5 = _label_frame(detail, "Step 5 — Detail & Edges",
                      "Sharpen edges, add final accents and highlights")
    _write_frames(writer, [f5] * hold_n)

    # ── Phase 6: Split comparison (final vs reference) ────────────────────
    half = W // 2
    for i in range(anim_n):
        t = i / max(1, anim_n - 1)
        cut = int(half * t)
        comp = detail.copy()
        comp[:, :cut] = ref_arr[:, :cut]
        comp[:, cut:cut+3] = [255, 255, 0]   # yellow divider
        comp = _label_frame(comp, "Result — Follow these steps and you get this",
                            "← Reference  |  Your painting →")
        _write_frames(writer, [comp])
    final_comp = detail.copy()
    final_comp[:, :half]      = ref_arr[:, :half]
    final_comp[:, half:half+3] = [255, 255, 0]
    final_comp = _label_frame(final_comp, "Result — Follow these steps and you get this",
                              "← Reference  |  Your painting →")
    _write_frames(writer, [final_comp] * (hold_n * 2))

    writer.release()
    return output_path
