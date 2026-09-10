"""
file: test_cut_tools.py
version: 1.0
author: Sam Cao
created: 2026-09-10
last_updated: 2026-09-10
description: Kerf presets by cutting tool: preset fill, explicit kerf winning, the CNC router having no preset, unit independence, per-rod tool override, and profile defaults.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import pytest

from cutsheet.layout import build_layout
from cutsheet.model import CUT_TOOL_KERF, JobError, job_from_dict

PART = [{"id": "A", "width": 4, "height": 4, "quantity": 2}]


def _job(**over):
    raw = {"job_name": "kt", "sheet": "laser_24x18", "outer_edge_margin": 0.25,
           "cutting_method": "free", "nest_mode": "bounding-box", "parts": PART}
    raw.update(over)
    return job_from_dict(raw)


def test_tool_fills_kerf_and_records_the_source():
    job = _job(cut_tool="table_saw")
    assert job.kerf == pytest.approx(0.125)
    assert job.kerf_source == "preset:table_saw"
    assert job.cut_tool == "table_saw"


def test_entered_kerf_beats_the_preset():
    """Measuring your own blade is the correct behavior, so it wins without complaint."""
    job = _job(cut_tool="table_saw", kerf=0.102)
    assert job.kerf == pytest.approx(0.102)
    assert job.kerf_source == "entered"
    assert job.cut_tool == "table_saw"


def test_zero_kerf_is_entered_not_missing():
    job = _job(cut_tool="table_saw", kerf=0)
    assert job.kerf == 0 and job.kerf_source == "entered"


def test_cnc_router_has_no_preset_because_the_kerf_is_the_bit():
    with pytest.raises(JobError) as e:
        _job(cut_tool="cnc_router")
    assert "bit" in str(e.value)
    assert _job(cut_tool="cnc_router", kerf=0.25).kerf == pytest.approx(0.25)


def test_missing_kerf_without_a_tool_still_errors_and_points_at_cut_tool():
    with pytest.raises(JobError) as e:
        _job()
    msg = str(e.value)
    assert "kerf" in msg and "cut_tool" in msg


def test_unknown_tool_is_rejected():
    with pytest.raises(JobError) as e:
        _job(cut_tool="sawzall")
    assert "sawzall" in str(e.value)


def test_preset_is_an_absolute_length_not_scaled_by_input_units():
    """A 1/8 in blade is 1/8 in whatever the job types its numbers in."""
    job = _job(cut_tool="table_saw", units={"input": "mm", "display": "mm"},
               outer_edge_margin=6, parts=[{"id": "A", "width": 100, "height": 100, "quantity": 2}])
    assert job.kerf == pytest.approx(0.125)  # base units are inches


def test_every_preset_is_positive_or_deliberately_absent():
    for name, kerf in CUT_TOOL_KERF.items():
        assert kerf is None or kerf > 0, name


def test_rod_tool_overrides_the_job_kerf():
    job = _job(cut_tool="table_saw",
               rods=[{"id": "tube", "length": 10, "quantity": 4, "cut_tool": "band_saw"},
                     {"id": "bar", "length": 10, "quantity": 4}])
    tube, bar = (r for r in job.rods)
    assert tube.kerf == pytest.approx(0.025) and bar.kerf is None

    rods = build_layout(job).rod_result["rods"]
    by_id = {r["id"]: r for r in rods}
    # 4 pieces take 3 kerfs: the band saw eats less stock than the table saw.
    assert by_id["tube"]["kerf"] == pytest.approx(0.025)
    assert by_id["tube"]["continuous_length"] == pytest.approx(40 + 3 * 0.025)
    assert by_id["bar"]["kerf"] == pytest.approx(0.125)
    assert by_id["bar"]["continuous_length"] == pytest.approx(40 + 3 * 0.125)
    assert by_id["tube"]["cut_tool"] == "band_saw"


def test_rod_kerf_can_be_entered_directly():
    job = _job(kerf=0.125, rods=[{"id": "r", "length": 10, "quantity": 2, "kerf": 0.04}])
    assert job.rods[0].kerf == pytest.approx(0.04)


def test_profile_can_carry_the_tool(tmp_path):
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "shop.json").write_text('{"cut_tool": "jigsaw"}', encoding="utf-8")
    raw = {"job_name": "kt", "sheet": "laser_24x18", "outer_edge_margin": 0.25,
           "cutting_method": "free", "nest_mode": "bounding-box", "parts": PART, "profile": "shop"}
    job = job_from_dict(raw, base_dir=str(tmp_path))
    assert job.cut_tool == "jigsaw" and job.kerf == pytest.approx(0.060)


def test_job_kerf_still_reaches_the_cut_list():
    job = _job(cut_tool="miter_saw")
    from cutsheet.report import cut_list_md
    md = cut_list_md(build_layout(job), "cut_list_v1.0.md", [])
    assert "preset for miter_saw" in md


# CHANGELOG
# v1.0 (2026-09-10): Initial release.
