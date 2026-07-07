"""
Subject / background separation — the first tier of optional local ML.

A tiny bundled U²-Netp ONNX model (~4.6 MB, Apache-2.0) gives a real
foreground-subject mask that runs on CPU in a fraction of a second, with no
external download and no paid API. It replaces the heavy, optional `rembg`
dependency the line-art step used to reach for (and silently do without —
falling back to "the whole frame is the subject" — when it wasn't installed).

Everything here degrades gracefully: if `onnxruntime` is missing or the model
file isn't present, `subject_mask` returns None and the pipeline carries on
exactly as before. That keeps the install light for anyone who doesn't want
the ML tier.

Model: U²-Net (Qin et al., 2020), small `u2netp` variant, standard ONNX export.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

# backend/analysis/subject.py -> backend/models/u2netp.onnx
_DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "models" / "u2netp.onnx"

_INPUT_SIZE = 320  # U²-Net trains and infers at 320×320
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Lazily created and cached; (session, input_name) or the sentinel False once
# we've determined the model can't be loaded (so we don't retry every image).
_session: object | None = None


def _model_path() -> Path:
    return Path(os.getenv("U2NET_MODEL_PATH", str(_DEFAULT_MODEL)))


def _get_session():
    """Return a cached onnxruntime session, or None if unavailable."""
    global _session
    if _session is not None:
        return _session or None  # False -> None

    path = _model_path()
    if not path.exists():
        log.info("subject_mask: model not found at %s, skipping ML subject mask", path)
        _session = False
        return None
    try:
        import onnxruntime as ort
    except Exception:
        log.info("subject_mask: onnxruntime not installed, skipping ML subject mask")
        _session = False
        return None

    try:
        sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        _session = (sess, sess.get_inputs()[0].name)
        return _session
    except Exception:
        log.warning("subject_mask: failed to load %s, skipping", path, exc_info=True)
        _session = False
        return None


def _preprocess(img: Image.Image) -> np.ndarray:
    """Image -> normalised NCHW float32 tensor at 320×320 (U²-Net convention)."""
    small = img.convert("RGB").resize((_INPUT_SIZE, _INPUT_SIZE), Image.BILINEAR)
    arr = np.asarray(small, dtype=np.float32)
    peak = float(arr.max())
    arr = arr / peak if peak > 0 else arr           # U²-Net divides by max, not 255
    arr = (arr - _MEAN) / _STD                        # ImageNet stats, per channel
    arr = arr.transpose(2, 0, 1)[None]                # HWC -> 1CHW
    return np.ascontiguousarray(arr, dtype=np.float32)


def subject_mask(img: Image.Image) -> np.ndarray | None:
    """
    Foreground-subject probability mask for ``img``.

    Returns a float32 array of shape (H, W) in [0, 1] at the image's own
    resolution — high where the salient subject is, low on background — or
    None if the ML tier is unavailable (no onnxruntime / no model file).
    Never raises.
    """
    sess = _get_session()
    if sess is None:
        return None
    try:
        session, input_name = sess  # type: ignore[misc]
        tensor = _preprocess(img)
        out = session.run(None, {input_name: tensor})[0]  # (1, 1, 320, 320)
        pred = np.asarray(out, dtype=np.float32).squeeze()  # (320, 320)

        # U²-Net's map is already ~[0,1]; stretch to full contrast so the
        # threshold-free consumers (focal blends) use the whole range.
        lo, hi = float(pred.min()), float(pred.max())
        pred = (pred - lo) / (hi - lo) if hi > lo else np.zeros_like(pred)

        # Back to the original resolution.
        w, h = img.size
        mask = np.asarray(
            Image.fromarray((pred * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR),
            dtype=np.float32,
        ) / 255.0
        return mask
    except Exception:
        log.warning("subject_mask: inference failed, skipping", exc_info=True)
        return None


def subject_mask_binary(img: Image.Image, threshold: float = 0.5) -> np.ndarray | None:
    """Convenience: uint8 {0,1} mask from :func:`subject_mask`, or None."""
    m = subject_mask(img)
    if m is None:
        return None
    return (m >= threshold).astype(np.uint8)
