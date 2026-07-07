"""Subject-mask (local ML tier) tests — real inference and graceful fallback."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from backend.analysis import subject


def _reset_session_cache():
    """The module caches the onnx session globally; clear it between cases."""
    subject._session = None


@pytest.fixture(autouse=True)
def _clean_session():
    _reset_session_cache()
    yield
    _reset_session_cache()


def _subject_image(w: int = 96, h: int = 96) -> Image.Image:
    """Light background with a dark centred blob — a trivially salient subject."""
    arr = np.full((h, w, 3), 230, dtype=np.uint8)
    arr[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] = [40, 60, 90]
    return Image.fromarray(arr)


def test_returns_none_when_model_missing(monkeypatch):
    monkeypatch.setenv("U2NET_MODEL_PATH", "/nonexistent/u2netp.onnx")
    _reset_session_cache()
    assert subject.subject_mask(_subject_image()) is None
    assert subject.subject_mask_binary(_subject_image()) is None


def test_mask_shape_and_range_with_bundled_model():
    pytest.importorskip("onnxruntime")
    if not subject._model_path().exists():
        pytest.skip("bundled u2netp.onnx not present")

    img = _subject_image()
    mask = subject.subject_mask(img)
    assert mask is not None, "model present but inference returned None"
    assert mask.shape == (img.height, img.width)
    assert mask.dtype == np.float32
    assert 0.0 <= float(mask.min()) and float(mask.max()) <= 1.0
    # contrast was stretched to the full range
    assert float(mask.max()) > 0.9


def test_binary_mask_isolates_the_central_subject():
    pytest.importorskip("onnxruntime")
    if not subject._model_path().exists():
        pytest.skip("bundled u2netp.onnx not present")

    img = _subject_image(96, 96)
    binary = subject.subject_mask_binary(img)
    assert binary is not None
    assert set(np.unique(binary)).issubset({0, 1})

    # the centre (the blob) should be foreground more often than the corners
    centre = binary[36:60, 36:60].mean()
    corners = np.concatenate([
        binary[:16, :16].ravel(), binary[:16, -16:].ravel(),
        binary[-16:, :16].ravel(), binary[-16:, -16:].ravel(),
    ]).mean()
    assert centre > corners
