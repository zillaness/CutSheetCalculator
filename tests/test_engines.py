"""
file: test_engines.py
version: 1.0
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Unit tests for the packing engines, spacing dials, guillotine feasibility, units, importers, and job-file validation.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import os

import pytest
from shapely.geometry import box

from cutsheet import units as U
from cutsheet.importers import import_dxf, import_svg
from cutsheet.layout import build_layout, expand_instances
from cutsheet.model import JobError, job_from_dict
from cutsheet.pack_1d import pack_rods, total_length
from cutsheet.pack_rect import is_guillotine_cuttable, pack_rectangles
from cutsheet.render import render_reference_svg
from cutsheet.verify import verify
from cutsheet.model import Rod


def base_job(**over):
    raw = {
        "job_name": "t", "sheet": "laser_24x18", "outer_edge_margin": 0.25, "kerf": 0.125,
        "cutting_method": "free", "nest_mode": "bounding-box",
        "parts": [{"id": "A", "width": 6, "height": 4, "quantity": 6}, {"id": "B", "width": 3, "height": 2, "quantity": 9}],
    }
    raw.update(over)
    return job_from_dict(raw)


def min_gap(layout):
    """Smallest edge-to-edge distance between any two placed parts on the same sheet."""
    best = float("inf")
    for s in layout.sheets:
        pls = s.placements
        for i in range(len(pls)):
            for j in range(i + 1, len(pls)):
                best = min(best, pls[i].polygon.distance(pls[j].polygon))
    return best


def test_rod_formula_prd():
    assert total_length([5.25] * 30, 0.125) == pytest.approx(161.125)
    res = pack_rods([Rod("r", 5.25, 30, 36.0)], 0.125)["rods"][0]
    assert res["bars_needed"] == 5
    assert res["bars"][0]["offcut"] == pytest.approx(3.875)


def test_rod_without_stock_length_reports_continuous_only():
    res = pack_rods([Rod("r", 5.25, 30, None)], 0.125)["rods"][0]
    assert res["continuous_length"] == pytest.approx(161.125)
    assert res["bars"] == []


@pytest.mark.parametrize("mode,value,expected_gap", [("kerf-gap", None, 0.125), ("shared-edge", None, 0.0), ("custom-margin", 0.5, 0.5)])
def test_spacing_modes_bbox(mode, value, expected_gap):
    spacing = {"mode": mode}
    if value is not None:
        spacing["value"] = value
    job = base_job(part_spacing=spacing)
    assert job.gap == pytest.approx(expected_gap)
    lay = build_layout(job)
    rep = verify(lay, determinism=False)
    assert rep.all_passed, [c for c in rep.checks if not c.passed]
    assert min_gap(lay) == pytest.approx(expected_gap, abs=1e-6)


@pytest.mark.parametrize("mode,value,expected_gap", [("kerf-gap", None, 0.125), ("shared-edge", None, 0.0), ("custom-margin", 0.4, 0.4)])
def test_spacing_modes_true_outline(mode, value, expected_gap):
    spacing = {"mode": mode}
    if value is not None:
        spacing["value"] = value
    job = base_job(part_spacing=spacing, nest_mode="true-outline")
    lay = build_layout(job)
    rep = verify(lay, determinism=False)
    assert rep.all_passed, [c for c in rep.checks if not c.passed]
    assert min_gap(lay) >= expected_gap - 1e-6


def test_outer_margin_is_independent_of_spacing():
    job = base_job(outer_edge_margin=1.0, part_spacing={"mode": "shared-edge"})
    lay = build_layout(job)
    for p in lay.placements:
        assert p.x >= 1.0 - 1e-9 and p.y >= 1.0 - 1e-9
        assert p.x + p.w <= 23.0 + 1e-9 and p.y + p.h <= 17.0 + 1e-9


def test_guillotine_layout_is_cuttable():
    job = base_job(cutting_method="guillotine", parts=[
        {"id": "A", "width": 6, "height": 4, "quantity": 10}, {"id": "B", "width": 5, "height": 3, "quantity": 10},
        {"id": "C", "width": 2, "height": 7, "quantity": 6}])
    lay = build_layout(job)
    rep = verify(lay, determinism=False)
    assert rep.all_passed, [c for c in rep.checks if not c.passed]
    assert any(c.name.startswith("guillotine") for c in rep.checks)


def test_guillotine_checker_rejects_pinwheel():
    pinwheel = [(0, 0, 2, 1), (2, 0, 3, 2), (1, 2, 3, 3), (0, 1, 1, 3)]
    assert not is_guillotine_cuttable(pinwheel)
    assert is_guillotine_cuttable([(0, 0, 1, 1), (1, 0, 2, 1), (0, 1, 2, 2)])


def test_locked_rotation_respected():
    job = base_job(parts=[{"id": "A", "width": 6, "height": 4, "quantity": 6, "rotation": "locked", "locked_angle": 90},
                          {"id": "B", "width": 3, "height": 2, "quantity": 4, "rotation": "auto"}])
    lay = build_layout(job)
    for p in lay.placements:
        if p.part_id == "A":
            assert p.angle == 90 and p.w == pytest.approx(4) and p.h == pytest.approx(6)


def test_engrave_flag_does_not_lock_rotation():
    job = base_job(parts=[{"id": "A", "width": 6, "height": 4, "quantity": 6, "engrave": True}])
    assert job.parts[0].rotation == "auto"
    assert set(job.parts[0].allowed_angles(90, "bounding-box")) == {0, 90}


def test_deterministic_across_runs():
    job = base_job(nest_mode="true-outline")
    a = [(p.key, p.sheet, p.x, p.y, p.angle) for p in build_layout(job).placements]
    b = [(p.key, p.sheet, p.x, p.y, p.angle) for p in build_layout(job).placements]
    assert a == b


def test_reference_svg_single_scale_and_consistency():
    job = base_job()
    lay = build_layout(job)
    svg = render_reference_svg(lay, "t_reference_v1.0.svg")
    rep = verify(lay, svg, determinism=False)
    names = {c.name: c for c in rep.checks}
    assert names["single scale constant"].passed
    assert names["cross-part consistency"].passed
    assert svg.count('data-scale-px-per-in=') == 1


def test_metric_job_round_trips():
    job = job_from_dict({
        "job_name": "mm", "units": {"input": "mm", "display": "mm"}, "sheet": {"width": 600, "height": 400},
        "outer_edge_margin": 5, "kerf": 0.2, "cutting_method": "free", "nest_mode": "bounding-box",
        "parts": [{"id": "P", "width": 100, "height": 50, "quantity": 10}]})
    assert job.sheet_width == pytest.approx(600 / 25.4)
    assert job.parts[0].width == pytest.approx(100 / 25.4)
    lay = build_layout(job)
    assert verify(lay, determinism=False).all_passed
    assert U.fmt(job.kerf, "mm") == "0.2 mm"


def test_sheet_and_cutting_method_have_no_defaults():
    with pytest.raises(JobError):
        job_from_dict({"job_name": "x", "outer_edge_margin": 0.25, "kerf": 0.1, "cutting_method": "free",
                       "parts": [{"id": "A", "width": 1, "height": 1, "quantity": 1}]})
    with pytest.raises(JobError):
        job_from_dict({"job_name": "x", "sheet": "laser_24x18", "outer_edge_margin": 0.25, "kerf": 0.1,
                       "parts": [{"id": "A", "width": 1, "height": 1, "quantity": 1}]})


def test_part_too_big_is_rejected():
    with pytest.raises(JobError):
        base_job(parts=[{"id": "A", "width": 30, "height": 4, "quantity": 1}])


def test_deferred_group_must_exist():
    with pytest.raises(JobError):
        base_job(deferred_groups=["Z"])


def test_import_svg_and_dxf_agree(tmp_path):
    import ezdxf
    svg = tmp_path / "l.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="4in" height="4in" viewBox="0 0 4 4">'
                   '<path d="M0,0 H4 V1 H1 V4 H0 Z"/><circle cx="0.5" cy="0.5" r="0.15"/></svg>')
    ps, _ = import_svg(str(svg))
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 1
    msp = doc.modelspace()
    pts = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)]
    for i in range(6):
        msp.add_line(pts[i], pts[(i + 1) % 6])
    msp.add_circle((0.5, 0.5), 0.15)
    dxf = tmp_path / "l.dxf"
    doc.saveas(str(dxf))
    pd, note = import_dxf(str(dxf))
    assert "chained" in note
    assert ps.area == pytest.approx(pd.area, rel=1e-3)
    assert ps.bounds == pytest.approx(pd.bounds, abs=1e-6)
    assert len(ps.interiors) == len(pd.interiors) == 1


def test_dxf_mm_units_converted(tmp_path):
    import ezdxf
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.modelspace().add_lwpolyline([(0, 0), (254, 0), (254, 127), (0, 127)], close=True)
    f = tmp_path / "r.dxf"
    doc.saveas(str(f))
    p, _ = import_dxf(str(f))
    assert p.bounds == pytest.approx((0, 0, 10, 5))


def test_bbox_mode_uses_bbox_of_imported_outline(tmp_path):
    svg = tmp_path / "l.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="4in" height="4in" viewBox="0 0 4 4">'
                   '<path d="M0,0 H4 V1 H1 V4 H0 Z"/></svg>')
    job = base_job(parts=[{"id": "L", "quantity": 4, "source": {"type": "file", "path": str(svg)}}], nest_mode="bounding-box")
    lay = build_layout(job)
    assert min_gap(lay) >= 0.125 - 1e-6
    # bbox mode keeps 4x4 footprints apart even though true outlines could interlock
    for p in lay.placements:
        assert p.w == pytest.approx(4) and p.h == pytest.approx(4)
        assert len(p.polygon.exterior.coords) == 7  # true outline still rendered (6 vertices + closing)


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
