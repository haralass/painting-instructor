"""
Monocular depth — the second tier of optional local ML.

Depth-Anything-V2 (Small, ONNX, ~99 MB, Apache-2.0) recovers a relative depth
map on CPU in ~0.3 s, which we band into foreground / middle-ground /
background planes for atmospheric-perspective teaching (push the distance
cooler, lighter, lower-contrast). Same graceful contract as
``analysis/subject.py``: returns None when onnxruntime or the model file is
absent, so the pipeline is unchanged for a light install.

The model is large, so it is NOT committed — fetch it with
``python scripts/fetch_models.py`` (or set ``DEPTH_MODEL_PATH``). The rest of
the app works without it.

Model: Depth-Anything-V2-Small, standard ONNX export (onnx-community).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

# backend/analysis/depth.py -> backend/models/depth_anything_v2_vits.onnx
_DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "models" / "depth_anything_v2_vits.onnx"

_INPUT_SIZE = 518  # DINOv2 patch size is 14; 518 = 37*14
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# (session, input_name) once loaded, or the sentinel False if it can't load.
_session: object | None = None


def _model_path() -> Path:
    return Path(os.getenv("DEPTH_MODEL_PATH", str(_DEFAULT_MODEL)))


def _get_session():
    """Return a cached onnxruntime session, or None if unavailable."""
    global _session
    if _session is not None:
        return _session or None

    path = _model_path()
    if not path.exists():
        log.info("depth_map: model not found at %s, skipping depth analysis", path)
        _session = False
        return None
    try:
        import onnxruntime as ort
    except Exception:
        log.info("depth_map: onnxruntime not installed, skipping depth analysis")
        _session = False
        return None
    try:
        sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        _session = (sess, sess.get_inputs()[0].name)
        return _session
    except Exception:
        log.warning("depth_map: failed to load %s, skipping", path, exc_info=True)
        _session = False
        return None


def _preprocess(img: Image.Image) -> np.ndarray:
    small = img.convert("RGB").resize((_INPUT_SIZE, _INPUT_SIZE), Image.BILINEAR)
    arr = np.asarray(small, dtype=np.float32) / 255.0
    arr = (arr - _MEAN) / _STD          # ImageNet stats, per channel
    arr = arr.transpose(2, 0, 1)[None]  # HWC -> 1CHW
    return np.ascontiguousarray(arr, dtype=np.float32)


def depth_map(img: Image.Image) -> np.ndarray | None:
    """
    Relative depth for ``img`` as a float32 (H, W) array in [0, 1], resized to
    the image's own resolution — **higher = nearer** (Depth-Anything predicts
    inverse-depth-like values). None if the ML tier is unavailable. Never raises.
    """
    sess = _get_session()
    if sess is None:
        return None
    try:
        session, input_name = sess  # type: ignore[misc]
        out = session.run(None, {input_name: _preprocess(img)})[0]
        depth = np.asarray(out, dtype=np.float32).squeeze()  # (518, 518)

        lo, hi = float(depth.min()), float(depth.max())
        depth = (depth - lo) / (hi - lo) if hi > lo else np.zeros_like(depth)

        w, h = img.size
        return np.asarray(
            Image.fromarray((depth * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR),
            dtype=np.float32,
        ) / 255.0
    except Exception:
        log.warning("depth_map: inference failed, skipping", exc_info=True)
        return None


def depth_planes(img: Image.Image, n: int = 3) -> np.ndarray | None:
    """
    Quantise the depth map into ``n`` distance bands by equal-area percentiles.
    Returns a uint8 (H, W) label array where 0 = farthest (background) and
    ``n-1`` = nearest (foreground), or None. Equal-area (percentile) banding
    keeps each plane a usable size regardless of the depth histogram's shape.
    """
    d = depth_map(img)
    if d is None:
        return None
    qs = [np.quantile(d, i / n) for i in range(1, n)]
    labels = np.zeros(d.shape, dtype=np.uint8)
    for thr in qs:
        labels += (d >= thr).astype(np.uint8)
    return labels  # 0..n-1, larger = nearer
