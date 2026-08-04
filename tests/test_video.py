"""
Guards on the tutorial video's *motion*, not just its existence.

The recurring failure here is a phase whose label advances while the picture
does not: the stroke sequence was handed entirely to the colour phase, so the
detail phase had nothing left to animate and lerped the finished painting with
itself — several seconds of a frozen frame under changing captions.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

cv2 = pytest.importorskip("cv2")

from backend.pipeline.video.processor import generate


SIZE = (160, 160)


def _img(color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", SIZE, color)


def _stroke_sequence(n: int = 20) -> list[Image.Image]:
    """Blank canvas → finished, each frame covering one more horizontal band.

    Stands in for stroke_paint's real output: strictly accumulating, and every
    frame differs from the one before it.
    """
    frames = []
    W, H = SIZE
    canvas = np.full((H, W, 3), 245, dtype=np.uint8)
    for i in range(n):
        canvas = canvas.copy()
        band = H // n
        canvas[i * band : (i + 1) * band] = (30 + 9 * i, 60, 200 - 8 * i)
        frames.append(Image.fromarray(canvas))
    return frames


def _read_frames(path: str) -> list[np.ndarray]:
    cap = cv2.VideoCapture(path)
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


def _generate(tmp_path, **kw) -> tuple[str, dict]:
    out = str(tmp_path / "tutorial.mp4")
    result = generate(
        reference=_img((200, 120, 80)),
        line_art=_img((255, 255, 255)),
        notan=_img((90, 90, 90)),
        color_blocking=_img((60, 140, 190)),
        output_path=out,
        out_w=SIZE[0],
        **kw,
    )
    return out, result


def _chapter_start(chapters: list[dict], order: int) -> float:
    return next(c["start_sec"] for c in chapters if c["order"] == order)


class TestStrokePhasesAnimate:
    def test_detail_phase_keeps_painting(self, tmp_path):
        """Step 6 must show new brushwork, not a frozen finished painting."""
        path, result = _generate(tmp_path, stroke_frames=_stroke_sequence())
        frames = _read_frames(path)
        assert frames, "video produced no decodable frames"

        fps = 24
        start = int(_chapter_start(result["chapters"], 6) * fps)
        end = int(_chapter_start(result["chapters"], 7) * fps)
        window = frames[start:end]
        assert len(window) > fps // 2, "detail phase is too short to teach anything"

        # Ignore the burnt-in caption bar at the bottom; compare the picture.
        h = window[0].shape[0]
        picture = [f[: int(h * 0.9)] for f in window]
        changed = sum(
            1 for a, b in zip(picture, picture[1:]) if np.abs(a.astype(int) - b.astype(int)).mean() > 0.5
        )
        assert changed >= 3, (
            f"detail phase is frozen: only {changed} frame-to-frame changes across "
            f"{len(window)} frames — the picture must keep developing while the caption says so"
        )

    def test_no_long_freeze_between_first_and_last_stroke_phase(self, tmp_path):
        """No multi-second stall anywhere from colour blocking to the result."""
        path, result = _generate(tmp_path, stroke_frames=_stroke_sequence())
        frames = _read_frames(path)
        fps = 24
        start = int(_chapter_start(result["chapters"], 4) * fps)
        end = int(_chapter_start(result["chapters"], 7) * fps)
        window = [f[: int(f.shape[0] * 0.9)] for f in frames[start:end]]

        longest = run = 0
        for a, b in zip(window, window[1:]):
            run = run + 1 if np.abs(a.astype(int) - b.astype(int)).mean() <= 0.5 else 0
            longest = max(longest, run)

        # The only intentional stillness here is the 2s hold on the finished
        # painting before the split comparison. The bug this guards produced a
        # 5.5s freeze (0.5s edge-refinement hold + 3s self-lerp + 2s hold).
        assert longest < int(fps * 2.5), (
            f"video freezes for {longest / fps:.1f}s during the painting phases "
            f"(limit 2.5s) — a phase is advancing its label without advancing the picture"
        )

    def test_without_strokes_still_produces_a_video(self, tmp_path):
        """The crossfade fallback must keep working when stroke_paint is absent."""
        path, result = _generate(tmp_path, stroke_frames=None)
        frames = _read_frames(path)
        assert frames, "fallback video produced no decodable frames"
        assert [c["order"] for c in result["chapters"]] == [0, 1, 2, 3, 4, 5, 6, 7]
