"""
Tests for the 36-band spectral colour module (``backend.analysis.spectral``).

These cover the four public functions:
  * sRGB <-> reflectance round-trip accuracy (white/black/primaries/mixed),
  * the classic subtractive test that RGB averaging fails: blue + yellow -> green,
  * spectral similarity ordering,
  * luminance-weighted mixing (a dark strong pigment dominates).
"""
from __future__ import annotations

import numpy as np
import pytest

from backend.analysis.spectral import (
    N_BANDS,
    mix_reflectances,
    reflectance_to_rgb,
    rgb_to_reflectance,
    spectral_similarity,
)


def _round_trip(rgb):
    return reflectance_to_rgb(rgb_to_reflectance(rgb))


# ---------------------------------------------------------------------------
# Basic shape / range invariants.
# ---------------------------------------------------------------------------

def test_reflectance_shape_and_range():
    refl = rgb_to_reflectance((123, 200, 45))
    assert refl.shape == (36,)
    assert N_BANDS == 36
    assert np.all(refl > 0.0) and np.all(refl < 1.0)


def test_accepts_both_scales():
    # 0-255 ints and 0-1 floats for the same colour give the same curve.
    a = rgb_to_reflectance((128, 64, 200))
    b = rgb_to_reflectance((128 / 255.0, 64 / 255.0, 200 / 255.0))
    assert np.allclose(a, b, atol=1e-9)


# ---------------------------------------------------------------------------
# 1 + 2. Round-trip accuracy.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rgb",
    [
        (255, 255, 255),   # white
        (0, 0, 0),         # black
        (255, 0, 0),       # red
        (0, 255, 0),       # green
        (0, 0, 255),       # blue
        (128, 128, 128),   # mid grey
        (200, 120, 40),    # warm brown
        (30, 90, 160),     # muted blue
    ],
)
def test_round_trip_within_tolerance(rgb):
    out = _round_trip(rgb)
    diff = np.abs(np.asarray(out, dtype=float) - np.asarray(rgb, dtype=float))
    # A few ΔRGB is plenty; Jakob2019 typically lands within ~1.
    assert diff.max() <= 4, f"{rgb} -> {out} (max Δ={diff.max()})"


def test_round_trip_returns_ints_0_255():
    out = _round_trip((77, 133, 201))
    assert isinstance(out, tuple) and len(out) == 3
    for v in out:
        assert isinstance(v, int) and 0 <= v <= 255


# ---------------------------------------------------------------------------
# 3. Subtractive mixing: blue + yellow -> GREEN (fails in RGB space).
# ---------------------------------------------------------------------------

def test_blue_plus_yellow_is_green():
    blue = (25, 60, 200)
    yellow = (240, 225, 25)
    blue_refl = rgb_to_reflectance(blue)
    yellow_refl = rgb_to_reflectance(yellow)

    mixed_refl = mix_reflectances([blue_refl, yellow_refl], [1.0, 1.0])
    r, g, b = reflectance_to_rgb(mixed_refl)

    # The green channel must dominate the spectral mix.
    assert g > r and g > b, f"expected green-dominant, got {(r, g, b)}"

    # And it must NOT be the naive per-channel RGB average, which for these two
    # colours is a muddy grey ((~132, ~142, ~112)) with no green dominance.
    naive = tuple((np.asarray(blue) + np.asarray(yellow)) / 2.0)
    spectral = np.asarray([r, g, b], dtype=float)
    assert np.linalg.norm(spectral - np.asarray(naive)) > 25.0, (
        f"spectral mix {spectral} too close to naive avg {naive}"
    )
    # Naive average has no strong green dominance; spectral does.
    naive_g_lead = naive[1] - max(naive[0], naive[2])
    spectral_g_lead = g - max(r, b)
    assert spectral_g_lead > naive_g_lead


# ---------------------------------------------------------------------------
# 4. Spectral similarity.
# ---------------------------------------------------------------------------

def test_similarity_identity_is_one():
    a = rgb_to_reflectance((90, 140, 200))
    assert spectral_similarity(a, a) == pytest.approx(1.0, abs=1e-9)


def test_similarity_orders_curves():
    base = rgb_to_reflectance((120, 120, 120))
    near = rgb_to_reflectance((130, 125, 118))   # perceptually close grey
    far = rgb_to_reflectance((250, 20, 20))      # saturated red, very different

    s_near = spectral_similarity(base, near)
    s_far = spectral_similarity(base, far)
    assert 0.0 <= s_far <= s_near <= 1.0
    assert s_near > s_far


# ---------------------------------------------------------------------------
# Luminance weighting: a tiny amount of a dark strong pigment dominates.
# ---------------------------------------------------------------------------

def test_dark_strong_pigment_shifts_more_than_naive_ratio():
    white = rgb_to_reflectance((245, 245, 240))
    black = rgb_to_reflectance((20, 18, 18))     # dark, strong tinter

    # A small amount of black against a lot of white: 4 parts white : 1 black.
    mixed_refl = mix_reflectances([white, black], [4.0, 1.0])
    mixed_rgb = np.asarray(reflectance_to_rgb(mixed_refl), dtype=float)

    white_rgb = np.asarray(reflectance_to_rgb(white), dtype=float)
    black_rgb = np.asarray(reflectance_to_rgb(black), dtype=float)

    # A naive per-part RGB average sits 4/5 of the way from black toward white,
    # i.e. still quite light. The spectral K-M mix (with the black's low
    # luminance and huge K/S pulling per band) must land noticeably DARKER than
    # that naive average — the dark pigment tints far harder than its raw ratio.
    naive_avg = (4.0 * white_rgb + 1.0 * black_rgb) / 5.0
    assert mixed_rgb.mean() < naive_avg.mean() - 10.0, (
        f"mixed {mixed_rgb} not meaningfully darker than naive {naive_avg}"
    )
    # And it must still be lighter than the pure black pigment.
    assert mixed_rgb.mean() > black_rgb.mean()

    # The dark pigment's dominance should also grow as its ratio grows: a 2:1
    # mix must be clearly darker than a 4:1 mix.
    mix_2to1 = np.asarray(
        reflectance_to_rgb(mix_reflectances([white, black], [2.0, 1.0])), dtype=float
    )
    assert mix_2to1.mean() < mixed_rgb.mean()
