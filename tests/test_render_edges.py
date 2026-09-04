"""
file: test_render_edges.py
version: 1.0
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Renderer and pipeline edge cases: metric display, feet rulers on a 4x8 sheet, custom sheets, deferred filenames, shared-edge cut files, and the parts echo.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import os
import re

import pytest

from cutsheet.layout import build_layout
from cutsheet.model import job_from_dict
from cutsheet.pipeline import build_job
from cutsheet.render import render_cut_svg, render_parts_echo_svg, render_reference_svg
from cutsheet.verify import verify


def _job(**over):
    raw = {"job_name": "Edge Case Job", "sheet": "laser_24x18", "outer_edge_margin": 0.25, "kerf": 0.125,
           "cutting_method": "free", "nest_mode": "bounding-box",
           "parts": [{"id": "A", "width": 6, "height": 4, "quantity": 4}, {"id": "B", "width": 2, "height": 2, "quantity": 3, "group": "later"}]}
    raw.update(over)
    return job_from_dict(raw)


def test_mm_display_cut_svg_is_in_mm():
    job = _job(units={"input": "mm", "display": "mm"}, sheet={"width": 600, "height": 400}, outer_edge_margin=5, kerf=0.2,
               parts=[{"id": "P", "width": 100, "height": 50, "quantity": 6}])
    lay = build_layout(job)
    svg = render_cut_svg(lay, lay.sheets[0], "x.svg")
    assert 'width="600mm" height="400mm" viewBox="0 0 600 400"' in svg
    ref = render_reference_svg(lay, "r.svg")
    assert "600 mm x 400 mm" in ref and ">mm<" in ref
    assert verify(lay, ref, determinism=False).all_passed


def test_feet_display_rulers_and_scale_on_4x8():
    job = _job(units={"input": "in", "display": "ft"}, sheet="plywood_4x8", parts=[{"id": "P", "width": 30, "height": 20, "quantity": 5}])
    lay = build_layout(job)
    ref = render_reference_svg(lay, "r.svg")
    k = float(re.search(r'data-scale-px-per-in="([^"]+)"', ref).group(1))
    assert k == pytest.approx(12.5)  # 1200 px cap / 96 in
    assert ">ft<" in ref and "8 ft x 4 ft" in ref
    svg = render_cut_svg(lay, lay.sheets[0], "x.svg")
    assert 'width="96in" height="48in"' in svg  # feet are expressed in inches for SVG
    assert verify(lay, ref, determinism=False).all_passed


def test_custom_sheet_and_slugged_filenames(tmp_path):
    job = _job(sheet={"width": 20, "height": 12, "units": "in"}, deferred_groups=["later"])
    res = build_job(job, str(tmp_path), dxf=False, determinism=False)
    names = res.outputs
    assert "edge_case_job_reference_v1.0.svg" in names
    assert any(n.endswith("_deferred_cut_v1.0.svg") for n in names)
    assert res.layout.sheets[-1].deferred
    assert res.ok


def test_shared_edge_cut_file_has_touching_parts():
    job = _job(part_spacing={"mode": "shared-edge"}, parts=[{"id": "A", "width": 6, "height": 4, "quantity": 6}])
    lay = build_layout(job)
    pls = lay.sheets[0].placements
    touching = any(a.polygon.touches(b.polygon) for i, a in enumerate(pls) for b in pls[i + 1:])
    assert touching
    assert verify(lay, determinism=False).all_passed


def test_parts_echo_lists_every_part_at_one_scale():
    job = _job()
    svg = render_parts_echo_svg(job, "e.svg")
    assert svg.count('class="part"') == 2
    assert svg.count("data-scale-px-per-in=") == 1


def test_locked_angle_in_bbox_mode_reports_transposed_size():
    job = _job(parts=[{"id": "A", "width": 6, "height": 4, "quantity": 2, "rotation": "locked", "locked_angle": 90}])
    lay = build_layout(job)
    for pl in lay.placements:
        assert (pl.w, pl.h) == pytest.approx((4, 6)) and pl.angle == 90


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
