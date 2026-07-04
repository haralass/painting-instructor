from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel, Field


@dataclass
class MediumStrategy:
    """
    Rendering strategy derived from the selected painting medium.
    Passed into render_detail_levels to alter visual output.
    """
    # Colour rendering
    colour_alpha: float      # how saturated the flat-colour render is (0=white, 1=full)
    greyscale_colours: bool  # True for pencil/charcoal — use grey tones instead of hue

    # Value rendering
    compress_values: bool    # True for charcoal — compress zones into fewer grey steps
    value_contrast: float    # multiply zone grey values by this (>1 = higher contrast)

    # Edge rendering
    emphasise_primary: bool  # True for pencil — make primary edges thicker/darker
    soften_secondary: bool   # True for oil/watercolour — reduce secondary edge opacity
    include_texture_edges: bool  # False for watercolour — skip texture clutter

    # Watercolour-specific
    preserve_whites: bool    # True for watercolour — lighter regions stay near-white


_MEDIUM_STRATEGIES: dict[str, MediumStrategy] = {
    "oil": MediumStrategy(
        colour_alpha=0.80,
        greyscale_colours=False,
        compress_values=False,
        value_contrast=1.2,
        emphasise_primary=False,
        soften_secondary=True,
        include_texture_edges=True,
        preserve_whites=False,
    ),
    "watercolor": MediumStrategy(
        colour_alpha=0.55,
        greyscale_colours=False,
        compress_values=False,
        value_contrast=0.9,
        emphasise_primary=False,
        soften_secondary=True,
        include_texture_edges=False,   # watercolour avoids texture clutter
        preserve_whites=True,
    ),
    "acrylic": MediumStrategy(
        colour_alpha=0.85,
        greyscale_colours=False,
        compress_values=False,
        value_contrast=1.1,
        emphasise_primary=False,
        soften_secondary=False,
        include_texture_edges=True,
        preserve_whites=False,
    ),
    "pencil": MediumStrategy(
        colour_alpha=0.40,
        greyscale_colours=True,        # pencil shows value, not hue
        compress_values=False,
        value_contrast=1.3,
        emphasise_primary=True,        # strong structural lines
        soften_secondary=False,
        include_texture_edges=True,
        preserve_whites=False,
    ),
    "charcoal": MediumStrategy(
        colour_alpha=0.30,
        greyscale_colours=True,        # charcoal = tonal, not colour
        compress_values=True,          # compress to fewer tonal masses
        value_contrast=1.4,
        emphasise_primary=True,
        soften_secondary=False,
        include_texture_edges=False,   # charcoal = mass, not texture
        preserve_whites=False,
    ),
}


def _get_medium_strategy(medium: str) -> MediumStrategy:
    return _MEDIUM_STRATEGIES.get(medium, _MEDIUM_STRATEGIES["oil"])


class Region(BaseModel):
    id: int
    source_label: int = 0      # the SLIC / merge-tree label value in that scale's label_map
    scale: str = ""            # "l1".."l5" (merge tree) or "coarse"/"medium"/"fine"/"micro"
    parent_id: Optional[int] = None
    level: int
    area: int
    centroid: tuple[float, float]
    bbox: tuple[int, int, int, int]   # x_min, y_min, x_max, y_max
    mean_lab: tuple[float, float, float]
    mean_rgb: tuple[int, int, int]
    value_zone: int
    colour_family_id: int
    importance: float
    texture_score: float
    mask_path: str = ""


class PaletteEntry(BaseModel):
    id: int
    name: str
    base_rgb: tuple[int, int, int]
    base_lab: tuple[float, float, float]
    area_fraction: float
    variations: dict[str, tuple[int, int, int]] = Field(default_factory=dict)


class ColourFamily(BaseModel):
    id: int
    name: str
    base_rgb: tuple[int, int, int]
    base_lab: tuple[float, float, float]
    area_fraction: float
    linked_region_ids: list[int] = Field(default_factory=list)
    variations: dict[str, tuple[int, int, int]] = Field(default_factory=dict)


class ValueZone(BaseModel):
    id: int
    label: str          # "shadow", "midtone", "light", etc.
    l_min: float
    l_max: float
    grey_value: int
    region_ids: list[int] = Field(default_factory=list)


class Edge(BaseModel):
    id: int
    region_a: Optional[int] = None   # None means no region context available
    region_b: Optional[int] = None
    type: str           # "primary" | "secondary" | "decorative" | "texture"
    strength: float
    hardness: float
    importance: float
    path: list[list[float]] = Field(default_factory=list)


class DetailLevel(BaseModel):
    level: int
    label: str
    region_ids: list[int] = Field(default_factory=list)
    edge_ids: list[int] = Field(default_factory=list)
    outlines: str = ""       # path to outlines PNG
    regions: str = ""        # path to coloured regions PNG
    values: str = ""         # path to value map PNG
    colours: str = ""        # path to flat colour PNG
    # Level-aware outline sublayers (primary/secondary/decorative/texture),
    # already filtered to this level's own ancestor-divergent edge set — NOT
    # the same as the global (non-level-filtered) edge_maps at the top of the
    # manifest. Only present for types that have at least one edge at this level.
    edge_maps: dict[str, str] = Field(default_factory=dict)


class AnalysisManifest(BaseModel):
    job_id: str
    input: dict = Field(default_factory=dict)
    image: dict = Field(default_factory=dict)
    palette: list[PaletteEntry]             = Field(default_factory=list)
    colour_families: list[ColourFamily]     = Field(default_factory=list)
    value_zones: list[ValueZone]            = Field(default_factory=list)
    detail_levels: dict[str, DetailLevel]   = Field(default_factory=dict)
    video: Optional[str] = None
    pdf:   Optional[str] = None
