"""
file: test_fonts.py
version: 1.0
author: Sam Cao
created: 2026-09-05
last_updated: 2026-09-05
description: Label text layout: both fonts produce geometry at the requested cap height, widths scale linearly, unsupported characters are substituted and reported, outline glyphs carry counters as holes.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import pytest

from cutsheet.fonts import layout_text, text_width, CHARSET


@pytest.mark.parametrize("font", ["single-line", "outline"])
def test_cap_height_is_honored(font):
    lay = layout_text("H", 1.0, font)
    ys = [y for g in lay.geoms for (x, y) in (g.coords if g.geom_type == "LineString" else g.exterior.coords)]
    assert min(ys) == pytest.approx(-1.0, abs=0.03)   # cap line one inch above the baseline (y down)
    assert max(ys) == pytest.approx(0.0, abs=0.03)    # sits on the baseline


@pytest.mark.parametrize("font", ["single-line", "outline"])
def test_width_scales_linearly(font):
    w1 = text_width("SHELF-12", 0.5, font)
    w2 = text_width("SHELF-12", 1.0, font)
    assert w2 == pytest.approx(2 * w1, rel=1e-6)
    assert w1 > 0.5 * 4  # eight glyphs are wider than four cap heights


def test_single_line_is_open_strokes():
    lay = layout_text("A1", 0.5, "single-line")
    assert lay.geoms and all(g.geom_type == "LineString" for g in lay.geoms)


def test_outline_has_filled_glyphs_with_counters():
    lay = layout_text("B8o", 0.5, "outline")
    assert lay.geoms and all(g.geom_type == "Polygon" for g in lay.geoms)
    assert sum(len(g.interiors) for g in lay.geoms) >= 4  # B has 2 counters, 8 has 2, o has 1
    assert all(g.is_valid for g in lay.geoms)


def test_substitution_is_reported():
    lay = layout_text("A&B", 0.5, "single-line")
    assert lay.text == "A?B" and lay.substituted == ["&"]


def test_every_charset_glyph_exists_in_both_fonts():
    for font in ("single-line", "outline"):
        lay = layout_text(CHARSET, 0.3, font)
        assert lay.substituted == []
        assert lay.width > 0


def test_geometry_starts_at_x_zero_and_is_y_down():
    lay = layout_text("L", 1.0, "outline")
    minx = min(x for g in lay.geoms for (x, y) in g.exterior.coords)
    assert minx >= -0.05
    assert lay.bbox[1] == pytest.approx(-1.0)


# CHANGELOG
# v1.0 (2026-09-05): Initial release.
