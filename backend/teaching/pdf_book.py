from __future__ import annotations
from pathlib import Path

PAGE_W = 210  # A4 mm
MARGIN = 10
CONTENT_W = PAGE_W - 2 * MARGIN

_CHAR_MAP = {
    "—": "-",   # em dash
    "–": "-",   # en dash
    "‘": "'", "’": "'",
    "“": '"', "”": '"',
    "…": "...",
    "°": " deg",
}


def _safe_text(text: str) -> str:
    """
    fpdf2's built-in Helvetica core font only supports latin-1. Medium
    teaching copy uses typographic dashes/quotes that fall outside it, so
    normalise the common ones and replace anything else that still doesn't
    fit rather than letting FPDFUnicodeEncodingException crash PDF assembly.
    """
    for uni, ascii_eq in _CHAR_MAP.items():
        text = text.replace(uni, ascii_eq)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def build_tutorial_pdf(
    out_path: str,
    reference_path: str | None,
    medium: str,
    medium_cfg: dict,
    detail_levels: dict,
    lesson_plan: list[dict],
    palette: list[dict],
    value_zone_list: list[dict],
    classic_pages: list[str],
) -> str:
    """
    Assemble the tutorial book: cover, palette, value zones, level-by-level
    lesson, medium-specific step-by-step stages (backed by lesson_plan's
    resolved assets), then a classic-analysis appendix.

    All paths passed in must be real filesystem paths (absolute), not the
    outputs-relative paths used in manifest.json.
    """
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)

    def _heading(text: str, size: int = 16) -> None:
        pdf.set_font("Helvetica", "B", size)
        pdf.cell(CONTENT_W, 10, _safe_text(text))
        pdf.ln(size * 0.8)

    def _body(text: str) -> None:
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(CONTENT_W, 6, _safe_text(text))
        pdf.ln(1)

    def _image_page(title: str, subtitle: str, image_paths: list[str | None]) -> None:
        pdf.add_page()
        _heading(title)
        if subtitle:
            _body(subtitle)
        existing = [p for p in image_paths if p and Path(p).exists()]
        if not existing:
            pdf.set_font("Helvetica", "I", 10)
            pdf.cell(CONTENT_W, 8, "(no image available for this step)")
            return
        if len(existing) == 1:
            pdf.image(existing[0], x=MARGIN, w=CONTENT_W)
            return
        col_w = (CONTENT_W - 6) / 2
        y0 = pdf.get_y()
        max_h = 0.0
        for i, p in enumerate(existing[:2]):
            x = MARGIN + i * (col_w + 6)
            info = pdf.image(p, x=x, y=y0, w=col_w)
            max_h = max(max_h, getattr(info, "rendered_height", col_w))
        pdf.set_y(y0 + max_h + 4)

    # ── 1. Cover ───────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_xy(MARGIN, 20)
    pdf.cell(CONTENT_W, 12, "Painting Instructor", align="C")
    pdf.ln(16)
    pdf.set_font("Helvetica", "", 14)
    pdf.cell(CONTENT_W, 8, _safe_text(f"{medium_cfg.get('name', medium.title())} Tutorial"), align="C")
    pdf.ln(16)
    if reference_path and Path(reference_path).exists():
        pdf.image(reference_path, x=MARGIN + 30, w=CONTENT_W - 60)

    # ── 2. Palette ─────────────────────────────────────────────────────────
    if palette:
        pdf.add_page()
        _heading("Colour Palette")
        swatch, gap = 16, 4
        per_row = max(1, int(CONTENT_W // (swatch + gap)))
        x0, y0 = MARGIN, pdf.get_y()
        for i, c in enumerate(palette[:32]):
            col, row = i % per_row, i // per_row
            x = x0 + col * (swatch + gap)
            y = y0 + row * (swatch + gap + 5)
            r, g, b = c.get("base_rgb", (128, 128, 128))
            pdf.set_fill_color(r, g, b)
            pdf.rect(x, y, swatch, swatch, style="F")
            pdf.set_xy(x, y + swatch + 0.5)
            pdf.set_font("Helvetica", "", 7)
            pdf.cell(swatch, 4, _safe_text(str(c.get("name", ""))[:12]))

    # ── 3. Value zones ─────────────────────────────────────────────────────
    if value_zone_list:
        pdf.add_page()
        _heading("Value Zones")
        bar_h = 14
        y0 = pdf.get_y()
        for i, z in enumerate(value_zone_list):
            grey = z.get("grey_value", 128)
            pdf.set_fill_color(grey, grey, grey)
            pdf.rect(MARGIN, y0 + i * (bar_h + 2), CONTENT_W, bar_h, style="F")
            text_shade = 255 if grey < 128 else 0
            pdf.set_text_color(text_shade, text_shade, text_shade)
            pdf.set_xy(MARGIN + 2, y0 + i * (bar_h + 2) + 4)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(80, 6, _safe_text(str(z.get("label", ""))))
        pdf.set_text_color(0, 0, 0)

    # ── 4. Level-by-level lesson ───────────────────────────────────────────
    for lvl in range(1, 6):
        dl = detail_levels.get(str(lvl))
        if not dl:
            continue
        _image_page(
            f"Level {lvl} — {dl.get('label', '')}",
            "Values (left) and outlines (right) at this level of detail.",
            [dl.get("values"), dl.get("outlines")],
        )

    # ── 5. Medium-specific step-by-step stages ─────────────────────────────
    if lesson_plan:
        pdf.add_page()
        _heading(f"{medium_cfg.get('name', medium.title())} — Step by Step", size=18)
        for key, value in medium_cfg.get("instructions", {}).items():
            label = key.replace("_note", "").replace("_", " ").title()
            pdf.set_font("Helvetica", "B", 10)
            pdf.multi_cell(CONTENT_W, 5, f"{label}:")
            _body(value)

        for step in lesson_plan:
            asset_paths = list(step.get("assets", {}).values())
            _image_page(
                f"Step {step['order']} — {step['name']}",
                step.get("description", ""),
                asset_paths,
            )

    # ── 6. Classic analysis appendix ───────────────────────────────────────
    existing_classic = [p for p in classic_pages if p and Path(p).exists()]
    if existing_classic:
        pdf.add_page()
        _heading("Appendix — Classic Analysis")
        for p in existing_classic:
            pdf.add_page()
            pdf.image(p, x=MARGIN, w=CONTENT_W)

    pdf.output(out_path)
    return out_path
