"""Drawing-construction analysis (Phase 3): structured, ordered, honest."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from backend.analysis.drawing import build_drawing_analysis
from backend.analysis.edge_cause import attach_edge_causes
from backend.analysis.preprocessing import prepare
from backend.schemas.drawing import DrawingAnalysis


def _synthetic():
    """A centred dark ellipse on a light ground → a clear subject with a real
    silhouette, so bounds/axis/envelope are deterministic to assert on."""
    H, W = 200, 160
    rgb = np.full((H, W, 3), 235, np.uint8)
    yy, xx = np.mgrid[0:H, 0:W]
    ell = (((xx - W / 2) / 45) ** 2 + ((yy - H / 2) / 80) ** 2) <= 1.0
    rgb[ell] = (70, 60, 55)
    img = Image.fromarray(rgb)
    cache = prepare(img)
    mask = ell.astype(np.float32)          # perfect subject mask
    return cache, mask, H, W


def _build():
    cache, mask, H, W = _synthetic()
    d = build_drawing_analysis(cache=cache, regions=[], edges=[], subj_mask=mask,
                               depth_lbl=None, zone_map=None, job_id="t")
    return d, H, W


def test_returns_a_valid_drawing_analysis():
    d, H, W = _build()
    assert isinstance(d, DrawingAnalysis)
    assert d.coord_space == "analysis_px"
    assert (d.image_width, d.image_height) == (W, H)
    # round-trips through JSON (what the pipeline serialises)
    assert DrawingAnalysis.model_validate_json(d.model_dump_json()) == d


def test_subject_bounds_come_from_the_mask():
    d, H, W = _build()
    assert d.subject_bounds.source == "subject_mask"
    # ellipse is centred and ~90×160 px → occupies well under the whole frame
    assert 0.2 < d.subject_bounds.occupied_fraction < 0.7
    b = d.subject_bounds
    assert b.x_min > 20 and b.x_max < W - 20    # not touching the sides
    assert b.y_min > 5 and b.y_max < H - 5


def test_has_the_four_limits_and_an_axis():
    d, _, _ = _build()
    cats = {lm.category for lm in d.landmarks}
    for req in ("subject_top", "subject_bottom", "subject_left", "subject_right"):
        assert req in cats, req
    assert d.main_axis is not None
    # a tall ellipse → near-vertical axis (90°)
    assert 70 < d.main_axis.orientation_deg < 110


def test_envelope_and_silhouette_are_distinct_and_both_present():
    d, _, _ = _build()
    assert d.envelope is not None and d.silhouette is not None
    # envelope is coarse (few segments), silhouette is finer
    assert d.envelope.segment_count <= len(d.silhouette.points)
    assert d.envelope.vertices != d.silhouette.points   # not overwritten


def test_construction_order_is_pedagogical_not_geometric():
    d, _, _ = _build()
    ids = [s.id for s in d.construction_order]
    # canvas/placement/bounds come before silhouette; silhouette before internal;
    # a checkpoint is last.
    assert ids.index("bounds") < ids.index("silhouette")
    assert ids.index("envelope") < ids.index("silhouette")
    assert ids.index("silhouette") < ids.index("internal_divisions")
    assert ids[-1] == "checkpoint"
    assert d.construction_order[-1].is_checkpoint


def test_no_subject_mask_falls_back_honestly():
    cache, _, H, W = _synthetic()
    d = build_drawing_analysis(cache=cache, regions=[], edges=[], subj_mask=None,
                               depth_lbl=None, zone_map=None)
    # with no mask and no regions, it must say 'whole_frame', not invent a subject
    assert d.subject_bounds.source == "whole_frame"
    assert d.subject_bounds.confidence < 0.3


def test_edge_cause_is_a_distribution_with_confidence():
    cache, mask, H, W = _synthetic()
    d = build_drawing_analysis(cache=cache, regions=[], edges=[], subj_mask=mask,
                               depth_lbl=None, zone_map=None)
    attach_edge_causes(d, cache, depth_lbl=None)
    assert d.silhouette.edge_cause is not None
    ec = d.silhouette.edge_cause
    assert abs(sum(ec.scores.values()) - 1.0) < 0.02        # normalised
    assert 0.0 <= ec.confidence <= 1.0
    # the dark ellipse on light ground is a strong luminance boundary
    assert ec.scores.get("object_boundary", 0) > 0 or ec.scores.get("illumination", 0) > 0


def test_lesson_order_follows_stages():
    cache, mask, H, W = _synthetic()
    # give it one internal edge so a path gets an internal stage
    class E:
        type = "primary"; path = [[80, 40], [80, 160]]; importance = 0.8
        region_a = None; region_b = None
    d = build_drawing_analysis(cache=cache, regions=[], edges=[E()], subj_mask=mask,
                               depth_lbl=None, zone_map=None)
    # silhouette's lesson_order precedes internal paths'
    if d.internal_paths:
        assert d.silhouette.lesson_order <= max(p.lesson_order for p in d.internal_paths)
