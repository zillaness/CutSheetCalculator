"""
file: test_materials.py
version: 1.0
author: Sam Cao
created: 2026-09-10
last_updated: 2026-09-10
description: Material model foundations: the materials block, stock factory-edge declarations, segment addressing for reference and banded edges, and grain as a rotation constraint.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import pytest

from cutsheet import edges
from cutsheet.layout import build_layout
from cutsheet.model import JobError, job_from_dict

PLY = {"id": "ply", "kind": "sheet", "grain": "width", "thickness": 0.75}


def _job(parts, materials=None, sheets=None, **over):
    raw = {"job_name": "mm", "outer_edge_margin": 0.25, "kerf": 0.125,
           "cutting_method": "free", "nest_mode": "bounding-box", "parts": parts}
    raw["sheets" if sheets else "sheet"] = sheets or "plywood_4x8"
    if materials:
        raw["materials"] = materials
    raw.update(over)
    return job_from_dict(raw)


# ---------------------------------------------------------------- additive

def test_a_job_with_no_materials_is_untouched():
    job = _job([{"id": "A", "width": 10, "height": 10, "quantity": 2}])
    assert job.materials == {} and job.uses_grain is False
    assert job.stock_grain(job.stocks[0]) == "none"
    assert job.parts[0].grain == "any" and job.parts[0].reference is None


def test_unknown_material_is_named():
    with pytest.raises(JobError) as e:
        _job([{"id": "A", "width": 10, "height": 10, "quantity": 1, "material": "oak"}])
    assert "oak" in str(e.value)


# ---------------------------------------------------------------- segment addressing

def test_rectangle_answers_to_its_four_sides():
    job = _job([{"id": "A", "width": 10, "height": 4, "quantity": 1,
                 "reference": {"edges": ["bottom"]}}])
    assert job.parts[0].reference.edges == ["bottom"]
    assert sorted(edges.part_edges(job.parts[0])) == ["bottom", "left", "right", "top"]


def test_top_is_the_low_y_side():
    """Part coordinates run y from the top, same as the cut list and the render."""
    sides = edges.rectangle_sides(10, 4)
    assert sides["top"].coords[0][1] == 0 and sides["bottom"].coords[0][1] == 4


def test_naming_an_edge_a_rectangle_does_not_have():
    with pytest.raises(JobError) as e:
        _job([{"id": "A", "width": 10, "height": 4, "quantity": 1, "reference": "diagonal"}])
    assert "diagonal" in str(e.value) and "'A'" in str(e.value)


def test_corner_needs_two_edges_that_meet():
    ok = _job([{"id": "A", "width": 10, "height": 4, "quantity": 1,
                "reference": {"edges": ["left", "top"], "corner": True}}])
    assert ok.parts[0].reference.corner is True
    with pytest.raises(JobError) as e:   # opposite sides can never form a corner
        _job([{"id": "A", "width": 10, "height": 4, "quantity": 1,
               "reference": {"edges": ["left", "right"], "corner": True}}])
    assert "do not touch" in str(e.value)


def test_corner_wants_exactly_two_edges():
    with pytest.raises(JobError) as e:
        _job([{"id": "A", "width": 10, "height": 4, "quantity": 1,
               "reference": {"edges": ["left"], "corner": True}}])
    assert "exactly two" in str(e.value)


def test_outline_segments_are_numbered_straight_runs():
    from shapely.geometry import Polygon
    L = Polygon([(0, 0), (6, 0), (6, 2), (2, 2), (2, 5), (0, 5)])
    segs = edges.outline_segments(L)
    assert len(segs) == 6
    assert sorted(round(s.length, 6) for s in segs) == [2.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_segment_numbering_does_not_move_when_the_ring_is_reordered():
    from shapely.geometry import Polygon
    pts = [(0, 0), (6, 0), (6, 2), (2, 2), (2, 5), (0, 5)]
    a = [tuple(round(c, 6) for c in s.coords[0]) for s in edges.outline_segments(Polygon(pts))]
    rolled = pts[3:] + pts[:3]
    b = [tuple(round(c, 6) for c in s.coords[0]) for s in edges.outline_segments(Polygon(rolled))]
    assert a == b


def test_collinear_runs_merge_into_one_edge():
    from shapely.geometry import Polygon
    split = Polygon([(0, 0), (3, 0), (6, 0), (6, 4), (0, 4)])  # top side given as two collinear pieces
    assert len(edges.outline_segments(split)) == 4


# ---------------------------------------------------------------- banding

def test_banding_is_rectangles_only_in_v1(tmp_path):
    from conftest import EXAMPLES
    import os
    with pytest.raises(JobError) as e:
        _job([{"id": "A", "quantity": 1, "banded_edges": ["top"],
               "source": {"type": "file", "path": os.path.join(EXAMPLES, "l_bracket_v1.0.svg")}}])
    assert "rectangles only" in str(e.value)


def test_banded_edges_must_exist():
    with pytest.raises(JobError) as e:
        _job([{"id": "A", "width": 10, "height": 4, "quantity": 1, "banded_edges": ["front"]}])
    assert "front" in str(e.value)


# ---------------------------------------------------------------- grain

def test_grain_along_keeps_only_zero_and_180():
    job = _job([{"id": "A", "width": 30, "height": 10, "quantity": 1, "material": "ply", "grain": "along"}],
               materials=[PLY], sheets=[{"width": 96, "height": 48, "material": "ply"}])
    p = job.parts[0]
    # A rectangle is only ever offered 0 and 90, so "along" leaves 0.
    assert sorted(p.allowed_angles(90, "bounding-box", "width")) == [0.0]


def test_grain_across_keeps_only_90_and_270():
    job = _job([{"id": "A", "width": 30, "height": 10, "quantity": 1, "material": "ply", "grain": "across"}],
               materials=[PLY], sheets=[{"width": 96, "height": 48, "material": "ply"}])
    assert sorted(job.parts[0].allowed_angles(90, "bounding-box", "width")) == [90.0]


def test_an_outline_keeps_the_end_for_end_flip_a_locked_rotation_would_deny():
    """The flip is real for an asymmetric outline. For a rectangle it is meaningless, and the
    packer never offers 180 there, so this is the case that proves the point."""
    import os
    from conftest import EXAMPLES
    job = _job([{"id": "A", "quantity": 1, "material": "ply", "grain": "along", "grain_axis": "width",
                 "source": {"type": "file", "path": os.path.join(EXAMPLES, "l_bracket_v1.0.svg")}}],
               materials=[PLY], sheets=[{"width": 96, "height": 48, "material": "ply"}],
               nest_mode="true-outline")
    assert sorted(job.parts[0].allowed_angles(90, "true-outline", "width")) == [0.0, 180.0]


def test_grain_axis_defaults_to_the_longer_side():
    job = _job([{"id": "wide", "width": 30, "height": 10, "quantity": 1},
                {"id": "tall", "width": 10, "height": 30, "quantity": 1}])
    assert job.parts[0].grain_axis_resolved == "width"
    assert job.parts[1].grain_axis_resolved == "height"


def test_a_square_must_say_which_way_its_grain_runs():
    with pytest.raises(JobError) as e:
        _job([{"id": "S", "width": 12, "height": 12, "quantity": 1, "material": "ply", "grain": "along"}],
             materials=[PLY], sheets=[{"width": 96, "height": 48, "material": "ply"}])
    assert "square" in str(e.value) and "grain_axis" in str(e.value)
    ok = _job([{"id": "S", "width": 12, "height": 12, "quantity": 1, "material": "ply",
                "grain": "along", "grain_axis": "width"}],
              materials=[PLY], sheets=[{"width": 96, "height": 48, "material": "ply"}])
    assert ok.parts[0].grain_axis_resolved == "width"


def test_locked_rotation_that_fights_the_grain_is_refused_by_name():
    with pytest.raises(JobError) as e:
        _job([{"id": "A", "width": 30, "height": 10, "quantity": 1, "material": "ply",
               "grain": "along", "rotation": "locked", "locked_angle": 90}],
             materials=[PLY], sheets=[{"width": 96, "height": 48, "material": "ply"}])
    msg = str(e.value)
    assert "locked" in msg and "grain" in msg


def test_grain_without_grained_stock_warns_rather_than_fails():
    job = _job([{"id": "A", "width": 30, "height": 10, "quantity": 1, "grain": "along"}])
    assert job.material_warnings and "no stock declares a grain" in job.material_warnings[0]


def test_grain_actually_constrains_the_layout():
    """Every placed piece must sit at an angle that keeps the grain running the long way."""
    job = _job([{"id": "A", "width": 30, "height": 10, "quantity": 6, "material": "ply", "grain": "along"}],
               materials=[PLY], sheets=[{"width": 96, "height": 48, "material": "ply"}])
    for pl in build_layout(job).placements:
        assert pl.angle % 180 == 0


def test_without_grain_the_packer_is_free_to_turn_the_part():
    job = _job([{"id": "A", "width": 30, "height": 10, "quantity": 20}])
    angles = {pl.angle % 180 for pl in build_layout(job).placements}
    assert angles != {0}  # at least one piece turned; that freedom is what grain gives up


# ---------------------------------------------------------------- factory edges on stock

def test_new_sheet_has_four_factory_edges_and_an_offcut_says_otherwise():
    job = _job([{"id": "A", "width": 10, "height": 10, "quantity": 1}],
               materials=[PLY],
               sheets=[{"width": 40, "height": 20, "quantity": 1, "material": "ply",
                        "factory_edges": ["left", "top"]},
                       {"width": 96, "height": 48, "material": "ply"}])
    assert job.stock_factory_edges(job.stocks[0]) == frozenset({"left", "top"})
    assert job.stock_factory_edges(job.stocks[1]) == frozenset(edges.SIDES)


def test_factory_edges_none_is_a_fully_sawn_offcut():
    job = _job([{"id": "A", "width": 10, "height": 10, "quantity": 1}],
               sheets=[{"width": 40, "height": 20, "quantity": 1, "factory_edges": "none"},
                       "plywood_4x8"])
    assert job.stock_factory_edges(job.stocks[0]) == frozenset()


def test_a_bad_stock_side_is_rejected():
    with pytest.raises(JobError) as e:
        _job([{"id": "A", "width": 10, "height": 10, "quantity": 1}],
             sheets=[{"width": 40, "height": 20, "quantity": 1, "factory_edges": ["north"]}, "plywood_4x8"])
    assert "north" in str(e.value)


# CHANGELOG
# v1.0 (2026-09-10): Initial release.
