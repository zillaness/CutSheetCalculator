"""
file: test_multi_stock.py
version: 1.0
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Multiple sheet sizes in one run: stock priority order, quantities, unplaced parts falling through to larger stock, and the out-of-stock error.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import os

import pytest

from conftest import EXAMPLES
from cutsheet.layout import build_layout
from cutsheet.model import JobError, job_from_dict


def _job(sheets, parts, **over):
    raw = {"job_name": "ms", "sheets": sheets, "outer_edge_margin": 0.25, "kerf": 0.125,
           "cutting_method": "free", "nest_mode": "bounding-box", "parts": parts}
    raw.update(over)
    return job_from_dict(raw)


def test_offcuts_used_first_then_full_sheets():
    job = _job([{"width": 12, "height": 12, "quantity": 2}, "laser_24x18"],
               [{"id": "A", "width": 5, "height": 5, "quantity": 12}])
    assert job.multi_stock and job.sheet_width == 12  # first stock mirrors sheet_width
    lay = build_layout(job)
    sizes = [(s.width, s.height) for s in lay.sheets]
    assert sizes[:2] == [(12, 12), (12, 12)]
    assert all(sz == (24, 18) for sz in sizes[2:]) and len(sizes) == 3
    assert sum(len(s.placements) for s in lay.sheets[:2]) == 8  # 4 per 12x12 offcut
    assert lay.sheets[2].stock == "laser_24x18" and lay.sheets[0].stock == "12x12in"


def test_part_too_big_for_offcut_falls_through_to_big_sheet():
    job = _job([{"width": 12, "height": 12, "quantity": 5}, "laser_24x18"],
               [{"id": "big", "width": 20, "height": 10, "quantity": 2}, {"id": "small", "width": 4, "height": 4, "quantity": 4}])
    lay = build_layout(job)
    for s in lay.sheets:
        ids = {p.part_id for p in s.placements}
        if "big" in ids:
            assert (s.width, s.height) == (24, 18)
    assert any((s.width, s.height) == (12, 12) for s in lay.sheets)


def test_true_outline_respects_stock_caps():
    svg = os.path.join(EXAMPLES, "l_bracket_v1.0.svg")
    job = _job([{"width": 10, "height": 10, "quantity": 1}, "laser_24x18"],
               [{"id": "L", "quantity": 10, "source": {"type": "file", "path": svg}}], nest_mode="true-outline")
    lay = build_layout(job)
    small = [s for s in lay.sheets if (s.width, s.height) == (10, 10)]
    assert len(small) == 1 and 0 < len(small[0].placements) < 10
    assert sum(len(s.placements) for s in lay.sheets) == 10


def test_running_out_of_stock_is_an_error():
    job = _job([{"width": 12, "height": 12, "quantity": 1}], [{"id": "A", "width": 5, "height": 5, "quantity": 12}])
    with pytest.raises(ValueError, match="ran out of sheet stock"):
        build_layout(job)


def test_only_last_stock_may_be_unlimited():
    with pytest.raises(JobError):
        _job(["laser_24x18", {"width": 12, "height": 12}], [{"id": "A", "width": 5, "height": 5, "quantity": 1}])


def test_single_sheet_job_unchanged():
    job = job_from_dict({"job_name": "one", "sheet": "laser_24x18", "outer_edge_margin": 0.25, "kerf": 0.125,
                         "cutting_method": "free", "nest_mode": "bounding-box",
                         "parts": [{"id": "A", "width": 6, "height": 4, "quantity": 3}]})
    assert len(job.stocks) == 1 and job.stocks[0].quantity is None
    lay = build_layout(job)
    assert lay.sheets[0].width == 24 and lay.sheets[0].stock == "laser_24x18"



def test_multi_stock_full_pipeline_verifies_and_renders(tmp_path):
    from cutsheet.pipeline import build_job
    job = _job([{"width": 12, "height": 12, "quantity": 2}, "laser_24x18"],
               [{"id": "A", "width": 5, "height": 5, "quantity": 12}], deferred_groups=[])
    res = build_job(job, str(tmp_path), dxf=True, determinism=True)
    assert res.ok, [c for c in res.report.checks if not c.passed]
    names = {c.name for c in res.report.checks}
    assert "stock quantities honored" in names
    s1 = open(tmp_path / "ms_sheet01_cut_v1.0.svg").read()
    s3 = open(tmp_path / "ms_sheet03_cut_v1.0.svg").read()
    assert 'width="12in" height="12in"' in s1 and 'width="24in" height="18in"' in s3
    ref = res.reference_svg
    assert "12 in x 12 in" in ref and "24 in x 18 in" in ref
    cl = open(tmp_path / "ms_cut_list_v1.0.md").read()
    assert "By size: 12x12in: 2, laser_24x18: 1" in cl


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
