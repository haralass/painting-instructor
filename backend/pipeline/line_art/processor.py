from __future__ import annotations
import cv2
import numpy as np
import PIL.ImageOps
from PIL import Image

_lineart_det = None


def _patch_mediapipe() -> None:
    """
    mediapipe 0.10+ removed the .solutions API that controlnet_aux still uses.
    Inject a dynamic stub that returns a no-op module for any attribute access.
    Must run BEFORE any controlnet_aux import.
    """
    try:
        import mediapipe as mp, types

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


def process(img: Image.Image, resolution: int = 1024) -> Image.Image:
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

    # ── Layer 2: interior detail ──────────────────────────────────────────
    det     = _get_detector()
    raw_la  = det(img, detect_resolution=resolution, image_resolution=resolution, coarse=False)
    interior = np.array(raw_la.convert("L"))   # white lines on black

    # ── Subject mask ──────────────────────────────────────────────────────
    fg_mask = None
    try:
        from rembg import remove, new_session
        sess    = new_session("birefnet-portrait")
        rgba    = remove(img, session=sess)
        alpha   = np.array(rgba)[:, :, 3]
        fg_mask = (alpha > 128).astype(np.uint8)
    except Exception:
        fg_mask = np.ones((H, W), dtype=np.uint8)

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

    return Image.fromarray(closed).convert("RGB")


def detect_raw(img: Image.Image, resolution: int = 1024) -> Image.Image:
    """Raw informative-drawings output (white lines on black) — for WVS density."""
    return _get_detector()(img, detect_resolution=resolution, image_resolution=resolution, coarse=False)
