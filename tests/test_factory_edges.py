"""
file: test_factory_edges.py
version: 1.0
author: Sam Cao
created: 2026-10-02
last_updated: 2026-10-02
description: Factory-edge reference placement: flush anchoring, corner allocation, orientation mapping, the use-available and open-sheets policies, downgrades, and the paths that are refused in v1.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import pytest

from cutsheet.layout import build_layout
from cutsheet.model import JobError, Part, job_from_dict
from cutsheet.reference import edge_side_at_angle
from cutsheet.verify import verify

PLY = {"id": "ply", "kind": "sheet"}


def _job(parts, sheets=None, **over):
    raw = {"job_name": "fe", "outer_edge_margin": 0.5, "kerf": 0.125,
           "cutting_method": "free", "nest_mode": "bounding-box",
           "materials": [PLY], "parts": parts,
           "sheets": sheets or [{"width": 48, "height": 48, "material": "ply", "factory_edges": "all"}]}
    raw.update(over)
    return job_from_dict(raw)


def _flush_sides(pl, sheet, tol=1e-6):
    out = set()
    if abs(pl.x) < tol:
        out.add("left")
    if abs(pl.y) < tol:
        out.add("top")
    if abs(pl.x + pl.w - sheet.width) < tol:
        out.add("right")
    if abs(pl.y + pl.h - sheet.height) < tol:
        out.add("bottom")
    return out


# ------------------------------------------------- orientation mapping

def test_named_edges_rotate_as_one_cycle():
    p = Part(id="R", quantity=1, width=30, height=10)
    assert {n: edge_side_at_angle(p, n, 0) for n in ("left", "top")} == {"left": "left", "top": "top"}
    assert edge_side_at_angle(p, "bottom", 90) == "left"
    assert edge_side_at_angle(p, "bottom", 180) == "top"
    assert edge_side_at_angle(p, "bottom", 270) == "right"


def test_an_interior_edge_cannot_lie_flat(tmp_path):
    """An L-bracket's inner edges are not on its bounding box, so no angle makes them flush."""
    import os
    from conftest import EXAMPLES
    from cutsheet import edges
    job = job_from_dict({"job_name": "x", "sheet": "plywood_4x8", "outer_edge_margin": 0.25,
                         "kerf": 0.125, "cutting_method": "free", "nest_mode": "bounding-box",
                         "parts": [{"id": "L", "quantity": 1, "source": {
                             "type": "file", "path": os.path.join(EXAMPLES, "l_bracket_v1.0.svg")}}]})
    part = job.parts[0]
    names = list(edges.part_edges(part))
    on_box = {n for n in names if any(edge_side_at_angle(part, n, a) for a in (0, 90, 180, 270))}
    assert on_box and len(on_box) < len(names)   # some sides are flush-able, some are interior


# ------------------------------------------------- placement

def test_a_reference_part_sits_flush_not_inside_the_margin():
    job = _job([{"id": "REF", "width": 20, "height": 6, "quantity": 1, "material": "ply",
                 "reference": {"edges": ["bottom"]}},
                {"id": "FILL", "width": 7, "height": 7, "quantity": 4}])
    lay = build_layout(job)
    sheet = lay.sheets[0]
    ref = next(pl for pl in sheet.placements if pl.part_id == "REF")
    assert "bottom" in _flush_sides(ref, sheet)
    for pl in sheet.placements:
        if pl.part_id == "FILL":
            assert pl.x >= job.outer_edge_margin - 1e-9 and pl.y >= job.outer_edge_margin - 1e-9


def test_a_corner_request_lands_on_two_adjacent_edges():
    job = _job([{"id": "C", "width": 10, "height": 10, "quantity": 1, "material": "ply",
                 "reference": {"edges": ["left", "top"], "corner": True}}])
    lay = build_layout(job)
    pl = lay.placements[0]
    assert _flush_sides(pl, lay.sheets[0]) >= {"left", "top"}
    assert job.reference_result["satisfied"][0]["corner"] is True


def test_a_sheet_has_four_corners_and_no_more():
    """Six corner requests, one sheet: four get a corner, two are downgraded but still cut.
    A featureless rectangle can reach any of the four by turning, which is why all four count."""
    job = _job([{"id": "C", "width": 8, "height": 8, "quantity": 6, "material": "ply",
                 "reference": {"edges": ["left", "top"], "corner": True}}])
    lay = build_layout(job)
    rr = job.reference_result
    assert len(rr["satisfied"]) == 4
    assert len(rr["downgraded"]) == 2
    assert len(lay.placements) == 6
    corners = {tuple(sorted(e["sides"])) for e in rr["satisfied"]}
    assert len(corners) == 4                 # four distinct corners, not one reused


def test_several_parts_share_one_long_edge():
    job = _job([{"id": "REF", "width": 10, "height": 4, "quantity": 4, "material": "ply",
                 "reference": {"edges": ["bottom"]}}])
    lay = build_layout(job)
    sheet = lay.sheets[0]
    flush = [pl for pl in sheet.placements if "bottom" in _flush_sides(pl, sheet)]
    assert len(flush) >= 2                   # a 48 in edge holds several 10 in parts
    assert len(job.reference_result["satisfied"]) == 4


def test_the_requested_edge_drives_the_angle():
    """A part whose 'bottom' must touch the left sheet edge has to turn 90 degrees."""
    job = _job([{"id": "REF", "width": 20, "height": 6, "quantity": 1, "material": "ply",
                 "reference": {"edges": ["bottom"]}}],
               sheets=[{"width": 48, "height": 48, "material": "ply", "factory_edges": ["left"]}])
    build_layout(job)
    got = job.reference_result["satisfied"][0]
    assert got["sides"] == ["left"] and got["angle"] == 90.0


# ------------------------------------------------- policy

def test_use_available_does_not_open_a_sheet_for_an_edge():
    job = _job([{"id": "C", "width": 8, "height": 8, "quantity": 6, "material": "ply",
                 "reference": {"edges": ["left", "top"], "corner": True}}])
    lay = build_layout(job)
    assert len(lay.sheets) == 1              # six 8 in squares fit one sheet; no extra opened
    assert len(job.reference_result["downgraded"]) == 2


def test_open_sheets_opens_them():
    """Same job, other policy: the sheet count rises until every request has a corner."""
    parts = [{"id": "C", "width": 8, "height": 8, "quantity": 6, "material": "ply",
              "reference": {"edges": ["left", "top"], "corner": True}}]
    stay = build_layout(_job(parts))
    job = _job(parts, factory_edge_policy="open-sheets")
    spend = build_layout(job)
    assert len(stay.sheets) == 1 and len(spend.sheets) == 2
    assert len(job.reference_result["satisfied"]) == 6
    assert job.reference_result["downgraded"] == []


def test_stock_with_no_factory_edges_satisfies_nothing():
    job = _job([{"id": "REF", "width": 10, "height": 4, "quantity": 2, "material": "ply",
                 "reference": {"edges": ["bottom"]}}],
               sheets=[{"width": 48, "height": 48, "material": "ply", "factory_edges": "none"}])
    lay = build_layout(job)
    assert len(lay.placements) == 2            # still cut
    m = job.outer_edge_margin
    for pl in lay.placements:                  # and all inside the normal margin
        assert pl.x >= m - 1e-9 and pl.y >= m - 1e-9


# ------------------------------------------------- verification and refusals

def test_the_verifier_proves_flushness_and_the_margin_check_still_holds():
    job = _job([{"id": "REF", "width": 20, "height": 6, "quantity": 3, "material": "ply",
                 "reference": {"edges": ["bottom"]}},
                {"id": "FILL", "width": 7, "height": 7, "quantity": 8}])
    rep = verify(build_layout(job))
    names = {c.name: c for c in rep.checks}
    assert names["factory edges"].passed
    assert names["inside outer_edge_margin boundary"].passed
    assert "checked flush instead" in names["inside outer_edge_margin boundary"].detail
    assert rep.all_passed


def test_counts_are_not_inflated_by_seeding():
    """Regression: a seeded part was once packed a second time as an ordinary item."""
    job = _job([{"id": "REF", "width": 20, "height": 6, "quantity": 3, "material": "ply",
                 "reference": {"edges": ["bottom"]}},
                {"id": "FILL", "width": 7, "height": 7, "quantity": 8}])
    lay = build_layout(job)
    counts = {}
    for pl in lay.placements:
        counts[pl.part_id] = counts.get(pl.part_id, 0) + 1
    assert counts == {"REF": 3, "FILL": 8}


def test_guillotine_with_a_reference_request_is_refused_for_now():
    with pytest.raises(JobError) as e:
        _job([{"id": "REF", "width": 20, "height": 6, "quantity": 1, "material": "ply",
               "reference": {"edges": ["bottom"]}}], cutting_method="guillotine")
    assert "guillotine" in str(e.value)


def test_rectpack_cannot_be_forced_on_a_reference_job():
    job = _job([{"id": "REF", "width": 20, "height": 6, "quantity": 1, "material": "ply",
                 "reference": {"edges": ["bottom"]}}], engine="rectpack")
    with pytest.raises(ValueError) as e:
        build_layout(job)
    assert "rectpack" in str(e.value)


def test_a_missed_edge_waits_for_the_next_sheet_instead_of_being_buried():
    """Regression: reference parts used to be placed as ordinary the moment one sheet ran out
    of edges, so a later sheet opening with four pristine edges never got to host them."""
    job = _job([{"id": "REF", "width": 20, "height": 6, "quantity": 6, "material": "ply",
                 "reference": {"edges": ["bottom"]}},
                {"id": "FILL", "width": 20, "height": 20, "quantity": 8}],
               sheets=[{"width": 48, "height": 30, "quantity": 1, "material": "ply",
                        "factory_edges": ["top"]},
                       {"width": 48, "height": 48, "material": "ply", "factory_edges": "all"}])
    lay = build_layout(job)
    assert len(lay.sheets) >= 2
    # The 48 in top edge of sheet 1 holds two 20 in parts; the rest must come off later sheets'
    # edges rather than being stranded mid-sheet.
    assert len(job.reference_result["satisfied"]) > 2
    assert verify(lay).all_passed


def test_the_recommendation_counts_what_one_more_sheet_would_fix():
    job = _job([{"id": "C", "width": 8, "height": 8, "quantity": 6, "material": "ply",
                 "reference": {"edges": ["left", "top"], "corner": True}}])
    build_layout(job)
    rr = job.reference_result
    assert len(rr["downgraded"]) == 2
    # a fresh sheet has four free corners, so both leftovers would get one
    assert rr["one_more_sheet_would_satisfy"] == 2


def test_reference_placement_is_deterministic():
    def run():
        job = _job([{"id": "REF", "width": 12, "height": 5, "quantity": 5, "material": "ply",
                     "reference": {"edges": ["bottom"]}},
                    {"id": "FILL", "width": 6, "height": 6, "quantity": 10}])
        lay = build_layout(job)
        return sorted((pl.key, pl.sheet, round(pl.x, 6), round(pl.y, 6), pl.angle) for pl in lay.placements)
    assert run() == run()


# CHANGELOG
# v1.0 (2026-10-02): Initial release.
