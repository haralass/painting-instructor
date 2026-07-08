"""Classical, CPU-only stroke-by-stroke oil-painting time-lapse renderer.

Reimplementation of the Im2Oil idea (ETF direction field + density anchor
sampling + oriented tapered brush stamps); no outline layer.
"""

from .processor import render_stroke_frames

__all__ = ["render_stroke_frames"]
