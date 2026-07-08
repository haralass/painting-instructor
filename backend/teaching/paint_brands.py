"""
Curated real-paint tube sets for brand-specific mixing recipes.

Each entry is a real, commercially-sold artist line (Winsor & Newton, Gamblin,
Daniel Smith, Golden, etc.) reduced to its standard "core palette": a white, a
black, warm/cool yellows, an orange, cadmium/quinacridone reds, an earth-red
and earth-browns, warm/cool blues and a green or two, plus a violet where the
line ships one. That lets the mixer answer "mix this from YOUR actual set"
instead of from the generic default palette.

IMPORTANT: the sRGB values here are OUR OWN masstone approximations — eyeballed
from how each named pigment reads out of the tube, not copied from any brand
colour chart, datasheet, or third-party data file. Pigment/product NAMES are
factual (they are the names printed on the tubes); the numbers are ours and are
deliberately coarse. They exist to seed the Kubelka-Munk search, not to
reproduce anyone's colour data. No paywalled or proprietary source was used.

Public data model only:
    BRANDS: dict[brand_id -> {"name", "medium", "tubes": [(tube_name, (r,g,b)), ...]}]
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# OILS
# ---------------------------------------------------------------------------
_WINSOR_NEWTON_OIL = [
    ("Titanium White",        (247, 246, 240)),
    ("Ivory Black",           (34, 32, 30)),
    ("Winsor Lemon",          (250, 222, 22)),
    ("Cadmium Yellow",        (251, 199, 14)),
    ("Yellow Ochre",          (198, 150, 55)),
    ("Cadmium Orange",        (238, 118, 26)),
    ("Cadmium Red",           (215, 52, 38)),
    ("Permanent Alizarin Crimson", (120, 26, 42)),
    ("Permanent Rose",        (188, 34, 92)),
    ("Burnt Sienna",          (126, 62, 40)),
    ("Burnt Umber",           (72, 50, 38)),
    ("French Ultramarine",    (30, 46, 130)),
    ("Winsor Blue (Green Shade)", (12, 58, 100)),
    ("Winsor Green (Blue Shade)", (12, 102, 82)),
]

_GAMBLIN_OIL = [
    ("Titanium White",        (247, 246, 241)),
    ("Ivory Black",           (33, 31, 30)),
    ("Cadmium Lemon",         (252, 224, 20)),
    ("Cadmium Yellow Medium", (250, 195, 12)),
    ("Yellow Ochre",          (196, 148, 52)),
    ("Cadmium Orange",        (237, 116, 24)),
    ("Cadmium Red Medium",    (214, 50, 36)),
    ("Alizarin Permanent",    (122, 28, 44)),
    ("Quinacridone Red",      (180, 30, 74)),
    ("Burnt Sienna",          (124, 60, 39)),
    ("Burnt Umber",           (70, 49, 37)),
    ("Ultramarine Blue",      (31, 47, 128)),
    ("Phthalo Blue",          (12, 56, 98)),
    ("Phthalo Green",         (12, 100, 80)),
    ("Sap Green",             (66, 92, 46)),
]

_OLD_HOLLAND_OIL = [
    ("Titanium White",        (246, 245, 239)),
    ("Ivory Black",           (35, 33, 31)),
    ("Cadmium Yellow Lemon",  (250, 221, 24)),
    ("Cadmium Yellow Medium", (249, 193, 12)),
    ("Yellow Ochre Light",    (200, 152, 58)),
    ("Cadmium Orange",        (236, 116, 26)),
    ("Cadmium Red Medium",    (213, 50, 36)),
    ("Alizarin Crimson Lake", (118, 24, 40)),
    ("Scheveningen Rose Deep",(176, 30, 82)),
    ("Burnt Sienna",          (128, 63, 41)),
    ("Burnt Umber",           (73, 51, 39)),
    ("Ultramarine Blue Deep", (28, 43, 126)),
    ("Prussian Blue",         (18, 42, 56)),
    ("Old Holland Green",     (40, 96, 66)),
]

# ---------------------------------------------------------------------------
# WATERCOLOURS
# ---------------------------------------------------------------------------
_DANIEL_SMITH_WC = [
    ("Titanium White",        (248, 247, 242)),
    ("Ivory Black",           (36, 34, 32)),
    ("Hansa Yellow Medium",   (250, 205, 25)),
    ("New Gamboge",           (245, 176, 20)),
    ("Yellow Ochre",          (197, 149, 54)),
    ("Pyrrol Scarlet",        (222, 58, 40)),
    ("Permanent Alizarin Crimson", (121, 27, 43)),
    ("Quinacridone Rose",     (192, 36, 96)),
    ("Burnt Sienna",          (125, 61, 39)),
    ("Burnt Umber",           (71, 50, 38)),
    ("French Ultramarine",    (29, 45, 129)),
    ("Phthalo Blue (Green Shade)", (12, 57, 99)),
    ("Phthalo Green (Blue Shade)", (12, 101, 81)),
    ("Sap Green",             (66, 92, 46)),
]

_WINSOR_NEWTON_WC = [
    ("Chinese White",         (249, 248, 243)),
    ("Lamp Black",            (30, 30, 32)),
    ("Winsor Lemon",          (250, 223, 24)),
    ("Winsor Yellow",         (249, 200, 18)),
    ("Yellow Ochre",          (199, 151, 56)),
    ("Winsor Orange",         (238, 120, 28)),
    ("Scarlet Lake",          (216, 54, 40)),
    ("Permanent Alizarin Crimson", (120, 26, 42)),
    ("Permanent Rose",        (190, 34, 94)),
    ("Burnt Sienna",          (126, 62, 40)),
    ("Burnt Umber",           (72, 50, 38)),
    ("French Ultramarine",    (30, 46, 130)),
    ("Winsor Blue (Green Shade)", (12, 58, 100)),
    ("Winsor Green (Blue Shade)", (12, 102, 82)),
]

_SENNELIER_WC = [
    ("Chinese White",         (249, 248, 244)),
    ("Ivory Black",           (35, 33, 31)),
    ("Sennelier Yellow Light",(251, 219, 26)),
    ("Yellow Deep",           (247, 182, 18)),
    ("Yellow Ochre",          (198, 150, 55)),
    ("Sennelier Orange",      (237, 118, 27)),
    ("Sennelier Red",         (214, 52, 40)),
    ("Alizarin Crimson",      (120, 26, 42)),
    ("Rose Madder Lake",      (186, 40, 96)),
    ("Burnt Sienna",          (127, 62, 40)),
    ("Raw Umber",             (88, 72, 48)),
    ("French Ultramarine Blue", (28, 44, 127)),
    ("Phthalo Blue",          (12, 57, 99)),
    ("Phthalo Green Light",   (16, 106, 84)),
]

# ---------------------------------------------------------------------------
# ACRYLICS
# ---------------------------------------------------------------------------
_GOLDEN_ACRYLIC = [
    ("Titanium White",        (247, 246, 240)),
    ("Carbon Black",          (30, 29, 28)),
    ("Hansa Yellow Light",    (251, 224, 30)),
    ("Hansa Yellow Medium",   (250, 202, 18)),
    ("Yellow Ochre",          (197, 149, 54)),
    ("Pyrrole Orange",        (236, 110, 24)),
    ("Pyrrole Red",           (210, 46, 34)),
    ("Quinacridone Crimson",  (140, 24, 52)),
    ("Quinacridone Magenta",  (176, 30, 86)),
    ("Burnt Sienna",          (124, 60, 39)),
    ("Burnt Umber",           (70, 49, 37)),
    ("Ultramarine Blue",      (31, 47, 128)),
    ("Phthalo Blue (Green Shade)", (12, 56, 98)),
    ("Phthalo Green (Blue Shade)", (12, 100, 80)),
]

_LIQUITEX_ACRYLIC = [
    ("Titanium White",        (247, 246, 241)),
    ("Mars Black",            (30, 29, 28)),
    ("Cadmium Yellow Light Hue", (251, 221, 26)),
    ("Cadmium Yellow Medium Hue", (250, 196, 14)),
    ("Yellow Oxide",          (196, 148, 53)),
    ("Cadmium Orange Hue",    (237, 116, 24)),
    ("Cadmium Red Medium Hue",(214, 51, 37)),
    ("Alizarin Crimson Hue",  (122, 28, 44)),
    ("Quinacridone Magenta",  (178, 30, 88)),
    ("Burnt Sienna",          (125, 61, 40)),
    ("Burnt Umber",           (71, 50, 38)),
    ("Ultramarine Blue",      (30, 46, 128)),
    ("Phthalocyanine Blue",   (12, 57, 99)),
    ("Phthalocyanine Green",  (12, 101, 81)),
]

_WINSOR_NEWTON_ACRYLIC = [
    ("Titanium White",        (247, 246, 240)),
    ("Mars Black",            (31, 30, 29)),
    ("Cadmium Lemon",         (251, 223, 22)),
    ("Cadmium Yellow Medium", (250, 197, 14)),
    ("Yellow Ochre",          (198, 150, 55)),
    ("Cadmium Orange",        (237, 117, 25)),
    ("Cadmium Red Medium",    (214, 51, 37)),
    ("Permanent Alizarin Crimson", (120, 26, 42)),
    ("Quinacridone Magenta",  (177, 30, 87)),
    ("Burnt Sienna",          (126, 62, 40)),
    ("Burnt Umber",           (72, 50, 38)),
    ("Ultramarine Blue",      (30, 46, 130)),
    ("Phthalo Blue",          (12, 58, 100)),
    ("Phthalo Green (Blue Shade)", (12, 102, 82)),
]


BRANDS: dict[str, dict] = {
    "winsor_newton_oil": {
        "name": "Winsor & Newton Artists' Oil",
        "medium": "oil",
        "tubes": _WINSOR_NEWTON_OIL,
    },
    "gamblin_oil": {
        "name": "Gamblin Artist Oil",
        "medium": "oil",
        "tubes": _GAMBLIN_OIL,
    },
    "old_holland_oil": {
        "name": "Old Holland Classic Oil",
        "medium": "oil",
        "tubes": _OLD_HOLLAND_OIL,
    },
    "daniel_smith_wc": {
        "name": "Daniel Smith Extra Fine Watercolor",
        "medium": "watercolor",
        "tubes": _DANIEL_SMITH_WC,
    },
    "winsor_newton_wc": {
        "name": "Winsor & Newton Professional Watercolour",
        "medium": "watercolor",
        "tubes": _WINSOR_NEWTON_WC,
    },
    "sennelier_wc": {
        "name": "Sennelier l'Aquarelle",
        "medium": "watercolor",
        "tubes": _SENNELIER_WC,
    },
    "golden_acrylic": {
        "name": "Golden Heavy Body Acrylic",
        "medium": "acrylic",
        "tubes": _GOLDEN_ACRYLIC,
    },
    "liquitex_acrylic": {
        "name": "Liquitex Heavy Body Acrylic",
        "medium": "acrylic",
        "tubes": _LIQUITEX_ACRYLIC,
    },
    "winsor_newton_acrylic": {
        "name": "Winsor & Newton Professional Acrylic",
        "medium": "acrylic",
        "tubes": _WINSOR_NEWTON_ACRYLIC,
    },
}


def tubes_tuple(brand_id: str) -> tuple[tuple[str, tuple[int, int, int]], ...]:
    """Hashable ((name, (r,g,b)), ...) for a brand, for the mixer's cache."""
    brand = BRANDS.get(brand_id)
    if brand is None:
        raise KeyError(f"unknown brand_id {brand_id!r}")
    return tuple((name, tuple(int(c) for c in rgb)) for name, rgb in brand["tubes"])
