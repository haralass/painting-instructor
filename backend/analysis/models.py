from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class Region(BaseModel):
    id: int
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
    variations: dict[str, tuple[int, int, int]] = {}


class ColourFamily(BaseModel):
    id: int
    name: str
    base_rgb: tuple[int, int, int]
    base_lab: tuple[float, float, float]
    area_fraction: float
    linked_region_ids: list[int] = []
    variations: dict[str, tuple[int, int, int]] = {}


class ValueZone(BaseModel):
    id: int
    label: str          # "shadow", "midtone", "light", etc.
    l_min: float
    l_max: float
    grey_value: int
    region_ids: list[int] = []


class Edge(BaseModel):
    id: int
    region_a: int
    region_b: Optional[int] = None
    type: str           # "primary" | "secondary" | "decorative" | "texture"
    strength: float
    hardness: float
    importance: float
    path: list[list[float]] = []


class DetailLevel(BaseModel):
    level: int
    label: str
    region_ids: list[int] = []
    edge_ids: list[int] = []
    outlines: str = ""       # path to outlines PNG
    regions: str = ""        # path to coloured regions PNG
    values: str = ""         # path to value map PNG
    colours: str = ""        # path to flat colour PNG


class AnalysisManifest(BaseModel):
    job_id: str
    input: dict
    image: dict
    palette: list[PaletteEntry] = []
    colour_families: list[ColourFamily] = []
    value_zones: list[ValueZone] = []
    detail_levels: dict[str, DetailLevel] = {}
    video: Optional[str] = None
    pdf: Optional[str] = None
