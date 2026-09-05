"""
file: fonts/__init__.py
version: 1.0
author: Sam Cao
created: 2026-09-05
last_updated: 2026-09-05
description: Text layout for piece labels. One function turns a string and a cap height into shapely geometry in inches (y down, baseline at y=0, left at x=0) using either the vendored Hershey Simplex single-line font (open LineStrings) or the bundled Label Sans outline font (filled Polygons).
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry

from . import hershey_simplex as HS

FONTS = ("single-line", "outline")
CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -_./#:"
SUBSTITUTE = "?"
OUTLINE_TTF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "label_sans_subset.ttf")
LETTER_SPACING = 0.08  # fraction of cap height added between glyphs
SPACE_ADVANCE = 0.6    # fraction of cap height for a space in single-line


@dataclass
class TextLayout:
    text: str            # text actually laid out (after substitution)
    font: str
    cap_height: float
    width: float         # inches, left edge to right edge of the advance
    height: float        # inches, cap height plus descender allowance below the baseline
    descent: float       # inches below the baseline (positive number)
    geoms: list          # shapely geometries in inches, y down, baseline at y=0, x from 0
    substituted: list    # characters replaced by SUBSTITUTE

    @property
    def bbox(self):
        """(minx, miny, maxx, maxy) in inches; miny is negative (above the baseline)."""
        return (0.0, -self.cap_height, self.width, self.descent)


def sanitize(text: str) -> tuple[str, list]:
    out, subs = [], []
    for ch in text:
        if ch in CHARSET:
            out.append(ch)
        else:
            out.append(SUBSTITUTE)
            subs.append(ch)
    return "".join(out), subs


# ---------------------------------------------------------------------------
# Single-line (Hershey Simplex)
# ---------------------------------------------------------------------------

def _layout_single_line(text: str, cap_height: float) -> tuple[list, float, float]:
    k = cap_height / HS.CAP_HEIGHT
    x = 0.0
    geoms = []
    gap = LETTER_SPACING * cap_height
    for i, ch in enumerate(text):
        left, right, strokes = HS.GLYPHS[ch]
        if ch == " ":
            x += SPACE_ADVANCE * cap_height
            continue
        # glyph coordinates: baseline at HS.BASE_LINE, left side at 'left' (negative)
        for stroke in strokes:
            pts = [((px - left) * k + x, (py - HS.BASE_LINE) * k) for (px, py) in stroke]
            if len(pts) >= 2:
                geoms.append(LineString(pts))
        x += (right - left) * k
        if i < len(text) - 1:
            x += gap
    descent = 0.25 * cap_height  # Simplex lowercase descenders reach about 7 units below a 21-unit cap
    return geoms, x, descent


# ---------------------------------------------------------------------------
# Outline (Label Sans, TrueType via fontTools)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _ttf():
    from fontTools.ttLib import TTFont
    font = TTFont(OUTLINE_TTF)
    upem = font["head"].unitsPerEm
    os2 = font["OS/2"]
    cap = getattr(os2, "sCapHeight", 0) or 0
    if not cap:
        cap = int(0.72 * upem)
    descender = abs(font["hhea"].descent)
    return font, upem, cap, descender


def _glyph_rings(font, glyph_name: str, tol_units: float) -> list[list[tuple[float, float]]]:
    """Flatten a TrueType glyph's contours to point rings in font units (y up)."""
    from fontTools.pens.recordingPen import RecordingPen
    gs = font.getGlyphSet()
    pen = RecordingPen()
    gs[glyph_name].draw(pen)
    rings, cur, start = [], [], None
    for op, args in pen.value:
        if op == "moveTo":
            if len(cur) >= 3:
                rings.append(cur)
            cur, start = [args[0]], args[0]
        elif op == "lineTo":
            cur.append(args[0])
        elif op == "qCurveTo":
            # TrueType quadratic spline; implied on-curve points between consecutive off-curve points.
            pts = list(args)
            if pts[-1] is None:  # closed spline with no on-curve point; rare
                pts[-1] = ((pts[0][0] + pts[-2][0]) / 2, (pts[0][1] + pts[-2][1]) / 2)
            p0 = cur[-1]
            ctrls, end = pts[:-1], pts[-1]
            for j, c in enumerate(ctrls):
                nxt = ctrls[j + 1] if j + 1 < len(ctrls) else end
                p2 = nxt if j + 1 == len(ctrls) else ((c[0] + nxt[0]) / 2, (c[1] + nxt[1]) / 2)
                n = max(3, int(((abs(p2[0] - p0[0]) + abs(p2[1] - p0[1])) / max(tol_units * 8, 1e-9)) ** 0.5) + 2)
                for s in range(1, n + 1):
                    t = s / n
                    cur.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p2[0],
                                (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p2[1]))
                p0 = p2
        elif op == "curveTo":
            p0 = cur[-1]
            c1, c2, p3 = args
            n = 12
            for s in range(1, n + 1):
                t = s / n
                cur.append(((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * c1[0] + 3 * (1 - t) * t * t * c2[0] + t ** 3 * p3[0],
                            (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * c1[1] + 3 * (1 - t) * t * t * c2[1] + t ** 3 * p3[1]))
        elif op in ("closePath", "endPath"):
            if len(cur) >= 3:
                rings.append(cur)
            cur = []
    if len(cur) >= 3:
        rings.append(cur)
    return rings


def _rings_to_polygons(rings: list) -> list[Polygon]:
    """Outer rings become polygons; rings inside exactly one outer become its holes."""
    polys = []
    for r in rings:
        p = Polygon(r)
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_empty or p.area < 1e-12:
            continue
        polys.append(p)
    polys.sort(key=lambda p: p.area, reverse=True)
    outers, holes = [], {}
    for p in polys:
        parent = None
        for i, o in enumerate(outers):
            if o.contains(p.representative_point()):
                parent = i
                break
        if parent is None:
            outers.append(p)
            holes[len(outers) - 1] = []
        else:
            holes[parent].append(p)
    out = []
    for i, o in enumerate(outers):
        poly = Polygon(o.exterior.coords, [h.exterior.coords for h in holes[i]])
        if not poly.is_valid:
            poly = poly.buffer(0)
        out.append(poly)
    return out


def _layout_outline(text: str, cap_height: float, tolerance_in: float) -> tuple[list, float, float]:
    font, upem, cap_units, desc_units = _ttf()
    k = cap_height / cap_units  # inches per font unit
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    x = 0.0
    geoms = []
    gap = LETTER_SPACING * cap_height
    tol_units = tolerance_in / k
    for i, ch in enumerate(text):
        gname = cmap.get(ord(ch))
        if gname is None:
            gname = cmap.get(ord(SUBSTITUTE))
        adv, lsb = hmtx[gname]
        if ch != " ":
            for poly in _rings_to_polygons(_glyph_rings(font, gname, tol_units)):
                geoms.append(_transform(poly, k, x))
        x += adv * k
        if i < len(text) - 1:
            x += gap
    return geoms, x, desc_units * k


def _transform(poly: Polygon, k: float, dx: float) -> Polygon:
    def conv(coords):
        return [(px * k + dx, -py * k) for (px, py) in coords]  # font y up -> sheet y down
    return Polygon(conv(poly.exterior.coords), [conv(h.coords) for h in poly.interiors])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def layout_text(text: str, cap_height: float, font: str = "single-line", tolerance_in: float = 0.002) -> TextLayout:
    """Lay out <text> at <cap_height> inches. Returns geometry in inches, y down, baseline y=0, x from 0."""
    if font not in FONTS:
        raise ValueError(f"font must be one of {FONTS}")
    if cap_height <= 0:
        raise ValueError("cap_height must be positive")
    clean, subs = sanitize(text)
    if font == "single-line":
        geoms, width, descent = _layout_single_line(clean, cap_height)
    else:
        geoms, width, descent = _layout_outline(clean, cap_height, tolerance_in)
    return TextLayout(clean, font, cap_height, width, cap_height + descent, descent, geoms, subs)


def text_width(text: str, cap_height: float, font: str = "single-line") -> float:
    return layout_text(text, cap_height, font).width


# CHANGELOG
# v1.0 (2026-09-05): Initial release.
