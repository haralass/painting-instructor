from __future__ import annotations
from .oil import OIL
from .watercolor import WATERCOLOR
from .acrylic import ACRYLIC
from .pencil import PENCIL
from .charcoal import CHARCOAL
from .digital import DIGITAL

MEDIUMS: dict[str, dict] = {
    "oil":       OIL,
    "watercolor":WATERCOLOR,
    "acrylic":   ACRYLIC,
    "pencil":    PENCIL,
    "charcoal":  CHARCOAL,
    "digital":   DIGITAL,
}


def get_medium(medium: str) -> dict:
    return MEDIUMS.get(medium, OIL)
