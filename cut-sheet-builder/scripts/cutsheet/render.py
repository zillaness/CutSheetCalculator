"""
file: render.py
version: 1.4
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Renders the to-scale labeled reference SVG (one uniform px-per-inch constant), per-sheet cut-ready SVG and DXF files with CUT/ENGRAVE layers, and the parts-echo preview.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

import datetime as _dt
import math
from typing import Optional

from shapely.geometry import Polygon

from . import units as U
from .layout import Layout, Placement, Sheet
from .model import Job, Part

TODAY = _dt.date.today().isoformat()


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _fmtnum(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def polygon_path(poly: Polygon, ox: float, oy: float, k: float, flip_h: Optional[float] = None) -> str:
    """SVG path data for a polygon (outer ring + holes) in px = origin + coordinate * k."""
    def ring(coords):
        pts = []
        for (x, y) in coords:
            yy = (flip_h - y) if flip_h is not None else y
            pts.append(f"{_fmtnum(ox + x * k)},{_fmtnum(oy + yy * k)}")
        return "M" + " L".join(pts) + " Z"
    d = ring(poly.exterior.coords[:-1])
    for hole in poly.interiors:
        d += " " + ring(hole.coords[:-1])
    return d


def geometry_path(geom, ox: float, oy: float, k: float) -> str:
    """SVG path data for a Polygon, LineString, or Multi* geometry (open paths stay open)."""
    def pts(coords, close):
        d = "M" + " L".join(f"{_fmtnum(ox + x * k)},{_fmtnum(oy + y * k)}" for (x, y) in coords)
        return d + (" Z" if close else "")
    t = geom.geom_type
    if t == "Polygon":
        return polygon_path(geom, ox, oy, k)
    if t == "LineString":
        return pts(geom.coords, False)
    if t == "LinearRing":
        return pts(geom.coords[:-1], True)
    if t.startswith("Multi") or t == "GeometryCollection":
        return " ".join(geometry_path(g, ox, oy, k) for g in geom.geoms)
    return ""


def _metadata_comment(filename: str, version: str, author: str, description: str) -> str:
    return (f"<!--\n  file: {filename}\n  version: {version}\n  author: {author}\n  created: {TODAY}\n"
            f"  last_updated: {TODAY}\n  description: {description}\n"
            f"  ai_update: Update last_updated and version. Append changelog comment at bottom.\n-->\n")


def _changelog_comment(version: str) -> str:
    return f"<!-- CHANGELOG\n  v{version} ({TODAY}): Initial release.\n-->\n"


def pick_scale(job: Job) -> float:
    """One px-per-inch constant for the whole reference render."""
    if job.raw.get("render", {}).get("px_per_unit"):
        return float(job.px_per_unit)
    widest = max([st.width for st in job.stocks] or [job.sheet_width])
    return min(40.0, 1200.0 / widest)


# ---------------------------------------------------------------------------
# Reference SVG (labeled, colored, to scale)
# ---------------------------------------------------------------------------

def _ruler_step(job: Job) -> tuple[float, str]:
    du = job.display_unit
    step = {"in": 1.0, "ft": 12.0, "mm": 10.0 / 25.4, "cm": 1.0 / 2.54}[du]
    return step, du


def render_reference_svg(layout: Layout, filename: str, only_sheets=None, with_table: bool = False) -> str:
    """only_sheets: optional list of sheet indices to draw (one page per sheet for printing).
    with_table: append a placement table (x, y, size, rotation per part) under the legend, for hand layout."""
    job = layout.job
    sheets = [s for s in layout.sheets if only_sheets is None or s.index in set(only_sheets)]
    table_rows = sum(len(s.placements) for s in sheets) + len(sheets) if with_table else 0
    k = pick_scale(job)
    du = job.display_unit
    PAD = 40.0
    HEADER = 96.0
    TITLE = 26.0
    RULER = 22.0
    GAP = 48.0
    legend_row = 18.0
    legend_h = 40 + legend_row * (len(job.parts) + 1)
    table_h = (30 + 15 * (table_rows + 1)) if with_table else 0
    total_w = PAD * 2 + RULER + max([sh.width for sh in sheets] or [job.sheet_width]) * k
    total_w = max(total_w, 720.0)
    total_h = HEADER + sum(TITLE + RULER + sh.height * k + GAP for sh in sheets) + legend_h + table_h + PAD

    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{_fmtnum(total_w)}" height="{_fmtnum(total_h)}" '
               f'viewBox="0 0 {_fmtnum(total_w)} {_fmtnum(total_h)}" data-scale-px-per-in="{_fmtnum(k)}" '
               f'data-job="{_esc(job.name)}" font-family="Helvetica, Arial, sans-serif">\n')
    out.append(_metadata_comment(filename, job.version, job.author,
               f"To-scale reference layout for job '{job.name}': {len(layout.sheets)} sheet(s), one uniform scale of {_fmtnum(k)} px per inch."))
    out.append('<defs><pattern id="deferredHatch" patternUnits="userSpaceOnUse" width="12" height="12" patternTransform="rotate(45)">'
               '<line x1="0" y1="0" x2="0" y2="12" stroke="#c0392b" stroke-width="2" opacity="0.35"/></pattern></defs>\n')
    out.append(f'<rect x="0" y="0" width="{_fmtnum(total_w)}" height="{_fmtnum(total_h)}" fill="#ffffff"/>\n')

    # Header
    engines = "; ".join(f"{m}: {e}" for m, e in layout.engines_used.items())
    spacing = job.part_spacing_mode + (f" ({U.fmt(job.custom_margin, du)})" if job.part_spacing_mode == "custom-margin" else "")
    stock_desc = ", ".join(f"{U.fmt(st.width, du)} x {U.fmt(st.height, du)}" + (f" (x{st.quantity})" if st.quantity else "") for st in job.stocks)
    lines = [
        (f"{job.name}  v{job.version}  {TODAY}", 18, "bold"),
        (f"Stock {stock_desc}   |   kerf {U.fmt(job.kerf, du)}   |   outer edge margin {U.fmt(job.outer_edge_margin, du)}   |   part spacing {spacing}   |   cutting {job.cutting_method}", 12, "normal"),
        (f"Scale: {_fmtnum(k)} px per inch, identical in x and y on every sheet. Engine: {engines}", 12, "normal"),
        ("Coordinates: x from the left edge, y from the TOP edge of the sheet. Rotation shown on labels as (R<deg>).", 11, "normal"),
    ]
    y = PAD - 10
    for text, size, weight in lines:
        out.append(f'<text x="{PAD}" y="{_fmtnum(y)}" font-size="{size}" font-weight="{weight}" fill="#111">{_esc(text)}</text>\n')
        y += size + 6

    step, unit_name = _ruler_step(job)
    y_cursor = HEADER
    for sheet in sheets:
        W, H = sheet.width, sheet.height
        sheet_px_w, sheet_px_h = W * k, H * k
        ox = PAD + RULER
        oy = y_cursor + TITLE + RULER
        title = f"{sheet.label} of {len(layout.sheets)}   {U.fmt(W, du)} x {U.fmt(H, du)}"
        if sheet.group:
            title += f"   group: {sheet.group}"
        title += f"   parts on sheet: {len(sheet.placements)}"
        out.append(f'<g class="sheet" data-sheet="{sheet.index}" data-ox="{_fmtnum(ox)}" data-oy="{_fmtnum(oy)}">\n')
        out.append(f'<text x="{PAD}" y="{_fmtnum(y_cursor + 17)}" font-size="14" font-weight="bold" fill="#111">{_esc(title)}</text>\n')
        if sheet.deferred:
            out.append(f'<text x="{_fmtnum(ox + sheet_px_w)}" y="{_fmtnum(y_cursor + 17)}" font-size="14" font-weight="bold" fill="#c0392b" text-anchor="end">DEFERRED - CUT LATER</text>\n')
        # sheet
        out.append(f'<rect x="{_fmtnum(ox)}" y="{_fmtnum(oy)}" width="{_fmtnum(sheet_px_w)}" height="{_fmtnum(sheet_px_h)}" fill="#f7f3e9" stroke="#111" stroke-width="1.5"/>\n')
        m = job.outer_edge_margin
        if m > 0:
            out.append(f'<rect x="{_fmtnum(ox + m * k)}" y="{_fmtnum(oy + m * k)}" width="{_fmtnum((W - 2 * m) * k)}" height="{_fmtnum((H - 2 * m) * k)}" fill="none" stroke="#888" stroke-width="1" stroke-dasharray="6,4"/>\n')
        # rulers
        n = int(math.floor(W / step + 1e-9))
        for i in range(n + 1):
            x = ox + i * step * k
            major = (i % 2 == 0)
            out.append(f'<line x1="{_fmtnum(x)}" y1="{_fmtnum(oy - (10 if major else 5))}" x2="{_fmtnum(x)}" y2="{_fmtnum(oy)}" stroke="#444" stroke-width="1"/>\n')
            if major:
                out.append(f'<text x="{_fmtnum(x)}" y="{_fmtnum(oy - 12)}" font-size="9" fill="#444" text-anchor="middle">{_fmtnum(U.from_base(i * step, du))}</text>\n')
        n = int(math.floor(H / step + 1e-9))
        for i in range(n + 1):
            yy = oy + i * step * k
            major = (i % 2 == 0)
            out.append(f'<line x1="{_fmtnum(ox - (10 if major else 5))}" y1="{_fmtnum(yy)}" x2="{_fmtnum(ox)}" y2="{_fmtnum(yy)}" stroke="#444" stroke-width="1"/>\n')
            if major:
                out.append(f'<text x="{_fmtnum(ox - 12)}" y="{_fmtnum(yy + 3)}" font-size="9" fill="#444" text-anchor="end">{_fmtnum(U.from_base(i * step, du))}</text>\n')
        out.append(f'<text x="{_fmtnum(ox + sheet_px_w + 16)}" y="{_fmtnum(oy - 12)}" font-size="9" fill="#444" text-anchor="start">{unit_name}</text>\n')
        # parts
        for pl in sheet.placements:
            part = job.part_by_id(pl.part_id)
            d = polygon_path(pl.polygon, ox, oy, k)
            out.append(f'<g class="part" data-part="{_esc(pl.part_id)}" data-copy="{pl.index}" data-x="{_fmtnum(pl.x)}" data-y="{_fmtnum(pl.y)}" '
                       f'data-w="{_fmtnum(pl.w)}" data-h="{_fmtnum(pl.h)}" data-angle="{_fmtnum(pl.angle)}" data-area="{_fmtnum(pl.polygon.area)}">\n')
            out.append(f'<path d="{d}" fill="{_esc(part.color)}" fill-opacity="0.85" fill-rule="evenodd" stroke="#222" stroke-width="1"/>\n')
            for g in pl.engrave:
                out.append(f'<path class="engrave" d="{geometry_path(g, ox, oy, k)}" fill="none" stroke="#111" stroke-width="0.8" stroke-dasharray="3,2"/>\n')
            # Label anchor must sit inside the outline (an L-bracket's bbox center is empty space).
            anchor = pl.polygon.centroid
            if not pl.polygon.contains(anchor):
                anchor = pl.polygon.representative_point()
            cx = ox + anchor.x * k
            cy = oy + anchor.y * k
            label = pl.part_id
            if pl.angle % 360 != 0:
                label += f" (R{_fmtnum(pl.angle)})"
            px_h = pl.h * k
            px_w = pl.w * k
            fs = 12 if min(px_w, px_h) >= 26 else (9 if min(px_w, px_h) >= 16 else 7)
            out.append(f'<text x="{_fmtnum(cx)}" y="{_fmtnum(cy + (fs / 3 if px_h < 44 else -1))}" font-size="{fs}" font-weight="bold" fill="#111" text-anchor="middle">{_esc(label)}</text>\n')
            if px_h >= 44 and px_w >= 60:
                dims = f"{_fmtnum(U.from_base(part.width, du))} x {_fmtnum(U.from_base(part.height, du))}"
                out.append(f'<text x="{_fmtnum(cx)}" y="{_fmtnum(cy + 12)}" font-size="9" fill="#222" text-anchor="middle">{_esc(dims)}</text>\n')
            out.append('</g>\n')
        if sheet.deferred:
            out.append(f'<rect x="{_fmtnum(ox)}" y="{_fmtnum(oy)}" width="{_fmtnum(sheet_px_w)}" height="{_fmtnum(sheet_px_h)}" fill="url(#deferredHatch)" pointer-events="none"/>\n')
        out.append('</g>\n')
        y_cursor += TITLE + RULER + sheet_px_h + GAP

    # Legend
    ly = y_cursor
    out.append(f'<text x="{PAD}" y="{_fmtnum(ly + 14)}" font-size="14" font-weight="bold" fill="#111">Legend</text>\n')
    cols = [("", 0), ("id", 30), ("size (w x h)", 90), ("true area", 230), ("qty", 320), ("per sheet", 360), ("rotation", 470), ("engrave", 560), ("group", 620), ("source", 680)]
    hy = ly + 34
    for name, dx in cols:
        out.append(f'<text x="{_fmtnum(PAD + dx)}" y="{_fmtnum(hy)}" font-size="10" font-weight="bold" fill="#333">{_esc(name)}</text>\n')
    counts_by_sheet = {}
    for s in layout.sheets:
        for pl in s.placements:
            counts_by_sheet.setdefault(pl.part_id, {}).setdefault(s.index + 1, 0)
            counts_by_sheet[pl.part_id][s.index + 1] += 1
    for i, part in enumerate(job.parts):
        ry = hy + (i + 1) * legend_row
        out.append(f'<rect x="{PAD}" y="{_fmtnum(ry - 10)}" width="14" height="12" fill="{_esc(part.color)}" stroke="#222" stroke-width="0.8"/>\n')
        per = ", ".join(f"S{s}:{c}" for s, c in sorted(counts_by_sheet.get(part.id, {}).items()))
        area = U.from_base(U.from_base(part.true_area, du), du)
        vals = ["", part.id, f"{_fmtnum(U.from_base(part.width, du))} x {_fmtnum(U.from_base(part.height, du))} {du}",
                f"{area:.2f} {du}^2", str(part.quantity), per,
                "auto" if part.rotation == "auto" else f"locked {_fmtnum(part.locked_angle)}",
                "yes" if part.engrave else "", part.group or "", part.source]
        for (name, dx), v in zip(cols, vals):
            if name == "":
                continue
            out.append(f'<text x="{_fmtnum(PAD + dx)}" y="{_fmtnum(ry)}" font-size="10" fill="#111">{_esc(v)}</text>\n')
    if with_table:
        ty = hy + (len(job.parts) + 1) * legend_row + 30
        out.append(f'<text x="{PAD}" y="{_fmtnum(ty)}" font-size="13" font-weight="bold" fill="#111">Placements (x, y from the top-left corner to the part\'s bounding box)</text>\n')
        tcols = [("#", 0), ("part", 30), ("copy", 90), ("x", 130), ("y", 260), ("placed w x h", 390), ("rotation", 520)]
        ty += 16
        for name, dx in tcols:
            out.append(f'<text x="{_fmtnum(PAD + dx)}" y="{_fmtnum(ty)}" font-size="10" font-weight="bold" fill="#333">{_esc(name)}</text>\n')
        for sheet in sheets:
            ty += 15
            out.append(f'<text x="{PAD}" y="{_fmtnum(ty)}" font-size="10" font-weight="bold" fill="#111">{_esc(sheet.label)}{" (DEFERRED)" if sheet.deferred else ""}</text>\n')
            for i, pl in enumerate(sheet.placements, 1):
                ty += 15
                xs = U.fmt(pl.x, du) + (f" ({U.fmt_fraction(pl.x)})" if du == "in" else "")
                ys = U.fmt(pl.y, du) + (f" ({U.fmt_fraction(pl.y)})" if du == "in" else "")
                vals = [str(i), pl.part_id, str(pl.index), xs, ys, f"{_fmtnum(U.from_base(pl.w, du))} x {_fmtnum(U.from_base(pl.h, du))}", f"{_fmtnum(pl.angle)} deg" if pl.angle % 360 else "0"]
                for (name, dx), v in zip(tcols, vals):
                    out.append(f'<text x="{_fmtnum(PAD + dx)}" y="{_fmtnum(ty)}" font-size="10" fill="#111">{_esc(v)}</text>\n')
    out.append(_changelog_comment(job.version))
    out.append('</svg>\n')
    return "".join(out)


# ---------------------------------------------------------------------------
# Cut-ready SVG (real units, hairline, layers)
# ---------------------------------------------------------------------------

def render_cut_svg(layout: Layout, sheet: Sheet, filename: str) -> str:
    job = layout.job
    du = job.display_unit
    # SVG accepts in, mm, cm, and pt/px; feet are expressed in inches.
    svg_unit = "in" if du == "ft" else du
    kk = 1.0 / U.TO_BASE[svg_unit]  # inches -> svg_unit
    W, H = sheet.width * kk, sheet.height * kk
    out = ['<?xml version="1.0" encoding="UTF-8"?>\n']
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
               f'width="{_fmtnum(W)}{svg_unit}" height="{_fmtnum(H)}{svg_unit}" viewBox="0 0 {_fmtnum(W)} {_fmtnum(H)}">\n')
    out.append(_metadata_comment(filename, job.version, job.author,
               f"Cut-ready {sheet.label} for job '{job.name}': 1 user unit = 1 {svg_unit}, hairline strokes, no labels."
               + (" DEFERRED sheet." if sheet.deferred else "")))
    out.append(f'<g id="CUT" inkscape:groupmode="layer" inkscape:label="CUT" fill="none" stroke="#ff0000" stroke-width="0.001">\n')
    for pl in sheet.placements:
        d = polygon_path(pl.polygon, 0.0, 0.0, kk)
        out.append(f'<path id="{_esc(pl.key)}" d="{d}"/>\n')
    out.append('</g>\n')
    out.append(f'<g id="ENGRAVE" inkscape:groupmode="layer" inkscape:label="ENGRAVE" fill="none" stroke="#0000ff" stroke-width="0.001">\n')
    n_eng = 0
    for pl in sheet.placements:
        for i, g in enumerate(pl.engrave):
            out.append(f'<path id="engrave-{_esc(pl.key)}-{i}" d="{geometry_path(g, 0.0, 0.0, kk)}"/>\n')
            n_eng += 1
    if job.engrave_layer == "outline-guide":
        for pl in sheet.placements:
            if job.part_by_id(pl.part_id).engrave:
                out.append(f'<path id="guide-{_esc(pl.key)}" d="{polygon_path(pl.polygon, 0.0, 0.0, kk)}"/>\n')
    elif not n_eng:
        out.append('<!-- Paste engrave artwork here. Empty on purpose: no engrave/score layer was found in the imports. -->\n')
    out.append('</g>\n')
    out.append(_changelog_comment(job.version))
    out.append('</svg>\n')
    return "".join(out)


def write_cut_dxf(layout: Layout, sheet: Sheet, path: str) -> Optional[str]:
    try:
        import ezdxf
    except ImportError:
        return None
    job = layout.job
    du = job.display_unit
    unit = "in" if du == "ft" else du
    kk = 1.0 / U.TO_BASE[unit]
    H = sheet.height
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = U.UNIT_TO_DXF_INSUNITS[unit]
    doc.layers.add("CUT", color=1)
    doc.layers.add("ENGRAVE", color=5)
    msp = doc.modelspace()

    def add_ring(coords, layer):
        pts = [((x) * kk, (H - y) * kk) for (x, y) in coords]  # DXF is y-up
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})

    def add_geom(g, layer):
        t = g.geom_type
        if t == "Polygon":
            add_ring(g.exterior.coords[:-1], layer)
            for hole in g.interiors:
                add_ring(hole.coords[:-1], layer)
        elif t == "LineString":
            msp.add_lwpolyline([(x * kk, (H - y) * kk) for (x, y) in g.coords], close=False, dxfattribs={"layer": layer})
        elif t.startswith("Multi") or t == "GeometryCollection":
            for sub in g.geoms:
                add_geom(sub, layer)

    for pl in sheet.placements:
        add_ring(pl.polygon.exterior.coords[:-1], "CUT")
        for hole in pl.polygon.interiors:
            add_ring(hole.coords[:-1], "CUT")
        for g in pl.engrave:
            add_geom(g, "ENGRAVE")
        if job.engrave_layer == "outline-guide" and job.part_by_id(pl.part_id).engrave:
            add_ring(pl.polygon.exterior.coords[:-1], "ENGRAVE")
    doc.saveas(path)
    return path


# ---------------------------------------------------------------------------
# Parts echo (confirmation preview)
# ---------------------------------------------------------------------------

def render_parts_echo_svg(job: Job, filename: str) -> str:
    k = pick_scale(job)
    du = job.display_unit
    PAD = 30.0
    cell_gap = 24.0
    max_w = max(p.width for p in job.parts) * k
    cols = max(1, int((1100 - PAD) // (max_w + cell_gap)))
    col_w = max_w + cell_gap
    rows = []
    x = PAD
    y = PAD + 40
    row_h = 0.0
    items = []
    for i, p in enumerate(job.parts):
        if i and i % cols == 0:
            y += row_h + cell_gap + 30
            x = PAD
            row_h = 0.0
        items.append((p, x, y))
        row_h = max(row_h, p.height * k)
        x += col_w
    total_h = y + row_h + PAD + 30
    total_w = PAD * 2 + cols * col_w
    out = ['<?xml version="1.0" encoding="UTF-8"?>\n']
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{_fmtnum(total_w)}" height="{_fmtnum(total_h)}" viewBox="0 0 {_fmtnum(total_w)} {_fmtnum(total_h)}" '
               f'data-scale-px-per-in="{_fmtnum(k)}" font-family="Helvetica, Arial, sans-serif">\n')
    out.append(_metadata_comment(filename, job.version, job.author, f"Parsed-parts preview for job '{job.name}' at {_fmtnum(k)} px per inch; confirm before nesting."))
    out.append(f'<rect width="{_fmtnum(total_w)}" height="{_fmtnum(total_h)}" fill="#fff"/>\n')
    out.append(f'<text x="{PAD}" y="{PAD}" font-size="14" font-weight="bold">Parts echo: {_esc(job.name)} (scale {_fmtnum(k)} px/in, uniform)</text>\n')
    for p, x, y in items:
        out.append(f'<g class="part" data-part="{_esc(p.id)}" data-w="{_fmtnum(p.width)}" data-h="{_fmtnum(p.height)}">\n')
        out.append(f'<path d="{polygon_path(p.base_polygon(), x, y, k)}" fill="{_esc(p.color)}" fill-opacity="0.85" fill-rule="evenodd" stroke="#222" stroke-width="1"/>\n')
        for g in p.engrave_geoms:
            out.append(f'<path class="engrave" d="{geometry_path(g, x, y, k)}" fill="none" stroke="#111" stroke-width="0.8" stroke-dasharray="3,2"/>\n')
        out.append(f'<text x="{_fmtnum(x)}" y="{_fmtnum(y + p.height * k + 14)}" font-size="11" fill="#111">{_esc(p.id)}: {_fmtnum(U.from_base(p.width, du))} x {_fmtnum(U.from_base(p.height, du))} {du}, qty {p.quantity}, {p.source}</text>\n')
        out.append('</g>\n')
    out.append(_changelog_comment(job.version))
    out.append('</svg>\n')
    return "".join(out)


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
# v1.1 (2026-09-04): only_sheets option for per-sheet pages.
# v1.2 (2026-09-04): with_table placement table for printed pages.
# v1.3 (2026-09-04): Engrave geometry on the ENGRAVE layer (SVG/DXF) and in the reference/echo renders.
# v1.4 (2026-09-04): Per-sheet sizes (multiple stock sizes).
