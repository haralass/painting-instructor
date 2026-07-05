from __future__ import annotations
import cv2
import numpy as np
import PIL.ImageOps
from PIL import Image

_lineart_det  = None
_rembg_sess   = None


def _patch_mediapipe() -> None:
    """
    mediapipe 0.10+ removed the .solutions API that controlnet_aux still uses.
    Inject a dynamic stub that returns a no-op module for any attribute access.
    Must run BEFORE any controlnet_aux import.
    """
    try:
        import types
        import mediapipe as mp

        class _Stub(types.ModuleType):
            def __getattr__(self, name: str):
                child = _Stub(name)
                object.__setattr__(self, name, child)
                return child
            def __call__(self, *a, **kw): return _Stub("call_result")
            def __iter__(self): return iter([])

        if not hasattr(mp, 'solutions') or not hasattr(mp.solutions, 'face_detection'):
            mp.solutions = _Stub('solutions')
    except ImportError:
        pass


def _get_detector():
    global _lineart_det
    if _lineart_det is None:
        _patch_mediapipe()
        from controlnet_aux import LineartDetector
        _lineart_det = LineartDetector.from_pretrained("lllyasviel/Annotators")
    return _lineart_det


def _xdog(img_gray: np.ndarray, sigma: float = 0.4,
          k: float = 4.5, p: float = 19.0, eps: float = -0.1, phi: float = 10.0) -> np.ndarray:
    """
    eXtended Difference of Gaussians — produces clean artistic ink lines.
    Better than Canny for backgrounds; natural stroke quality.
    """
    g1 = cv2.GaussianBlur(img_gray.astype(float), (0, 0), sigma)
    g2 = cv2.GaussianBlur(img_gray.astype(float), (0, 0), sigma * k)
    diff = g1 - p * g2
    result = np.where(diff < eps, 1.0, 1.0 + np.tanh(phi * diff))
    result = np.clip(result / result.max(), 0, 1)
    return (result * 255).astype(np.uint8)


def _dog_line_strength(g: np.ndarray, s1: float, s2: float, gain: float) -> np.ndarray:
    """Band-pass magnitude as line strength — |DoG| picks up both sides of an
    edge, which reads as a soft graphite stroke rather than a hard ink line."""
    d = cv2.GaussianBlur(g, (0, 0), s1) - cv2.GaussianBlur(g, (0, 0), s2)
    return np.clip(np.abs(d) * gain, 0.0, 1.0)


def _classical_line_art(img_rgb: np.ndarray) -> Image.Image:
    """
    No-ML line art fallback. Previously a missing controlnet_aux meant NO
    line art at all (the step just failed with a warning) — the lesson's
    most-referenced guide simply didn't exist unless multi-GB torch weights
    were installed. Two-scale |DoG| over a bilateral-smoothed grey gives a
    convincing pencil sketch from pure OpenCV: the fine scale draws interior
    detail, the coarse scale weights the structural contours.
    """
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    gs = cv2.bilateralFilter(gray, 9, 40, 9).astype(np.float32) / 255.0

    fine   = _dog_line_strength(gs, 0.8, 1.6, 14.0)
    coarse = _dog_line_strength(gs, 2.0, 4.0, 18.0)
    sketch = 1.0 - np.clip(fine * 0.7 + coarse * 1.0, 0.0, 1.0)

    out = (sketch * 255).astype(np.uint8)
    out = cv2.medianBlur(out, 3)   # drop salt specks without eating strokes
    return Image.fromarray(out).convert("RGB")


def _process_internal(img: Image.Image, resolution: int = 1024) -> tuple[Image.Image, np.ndarray | None]:
    """
    Professional-grade composite line art for artists.

    3 layers (Gurney/illustration standard):
      Layer 1 — Silhouette (3-4px thick)
                rembg subject mask boundary → thick outer contour
                "This object, not background" — most important line in illustration
      Layer 2 — Interior detail (1px thin)
                LineartDetector(coarse=False) × foreground mask
                Facial structure, fur direction, fabric folds
      Layer 3 — Background (30% opacity)
                XDoG on background region — aerial perspective in line weight

    All layers composited in multiply mode → black lines on white.
    Gap closure: morphological CLOSE kernel=(2,2).
    """
    W, H    = img.size
    img_rgb = np.array(img.convert("RGB"))

    # ── Subject mask ──────────────────────────────────────────────────────
    global _rembg_sess
    fg_mask = None
    try:
        from rembg import remove, new_session
        if _rembg_sess is None:
            _rembg_sess = new_session("birefnet-portrait")
        rgba    = remove(img, session=_rembg_sess)
        alpha   = np.array(rgba)[:, :, 3]
        fg_mask = (alpha > 128).astype(np.uint8)
    except Exception:
        fg_mask = np.ones((H, W), dtype=np.uint8)

    # ── Layer 2: interior detail ──────────────────────────────────────────
    try:
        det     = _get_detector()
        raw_la  = det(img, detect_resolution=resolution, image_resolution=resolution, coarse=False)
        interior = np.array(raw_la.convert("L"))   # white lines on black
    except Exception:
        # ML detector unavailable — classical XDoG sketch instead of failing.
        return _classical_line_art(img_rgb), fg_mask

    # ── Layer 1: silhouette ───────────────────────────────────────────────
    sil = np.zeros((H, W), dtype=np.uint8)
    if fg_mask is not None:
        _, binary   = cv2.threshold(
            (fg_mask * 255).astype(np.uint8), 128, 255, cv2.THRESH_BINARY
        )
        boundary    = cv2.Canny(binary, 50, 150)
        sil         = cv2.dilate(boundary, np.ones((4, 4), np.uint8))

    # ── Layer 3: background XDoG ──────────────────────────────────────────
    bg_mask = 1 - fg_mask if fg_mask is not None else np.zeros((H, W), dtype=np.uint8)
    gray    = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    xdog    = _xdog(gray)
    bg_line = np.where(bg_mask.astype(bool), xdog, 0).astype(np.uint8)

    # ── Resize all layers to match original image size ────────────────────
    interior = cv2.resize(interior, (W, H), interpolation=cv2.INTER_LINEAR)

    # ── Composite ─────────────────────────────────────────────────────────
    interior_masked = interior if fg_mask is None else (interior * fg_mask).astype(np.uint8)

    interior_weighted = (interior_masked * 1.0).astype(np.uint8)
    sil_weighted      = np.clip(sil.astype(float) * 1.0, 0, 255).astype(np.uint8)
    bg_weighted       = np.clip(bg_line.astype(float) * 0.30, 0, 255).astype(np.uint8)

    composite = np.maximum(interior_weighted,
                np.maximum(sil_weighted, bg_weighted))

    # ── Invert → black lines on white ─────────────────────────────────────
    inverted = 255 - composite

    # ── Gap closure ───────────────────────────────────────────────────────
    kernel   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    closed   = cv2.morphologyEx(inverted, cv2.MORPH_CLOSE, kernel)

    return Image.fromarray(closed).convert("RGB"), fg_mask


def process(img: Image.Image, resolution: int = 1024) -> Image.Image:
    """Public API — returns only the line art image (fg_mask discarded)."""
    result, _ = _process_internal(img, resolution)
    return result


def process_with_mask(img: Image.Image, resolution: int = 1024) -> tuple[Image.Image, np.ndarray | None]:
    """Returns (line_art_image, fg_mask) — use when dot_to_dot needs the mask."""
    return _process_internal(img, resolution)


def detect_raw(img: Image.Image, resolution: int = 1024) -> Image.Image:
    """Raw informative-drawings output (white lines on black) — for WVS density."""
    return _get_detector()(img, detect_resolution=resolution, image_resolution=resolution, coarse=False)
