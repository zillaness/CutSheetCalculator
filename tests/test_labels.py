"""
file: test_labels.py
version: 1.0
author: Sam Cao
created: 2026-09-05
last_updated: 2026-09-05
description: Piece labeling acceptance tests (PRD piece_labeling v1.1 section 12): router beside-cutout with spacing bump, laser on-piece outline and single-line, fallback disclosure, plasma refusal, backward compatibility, determinism, profiles, outputs selection, hand jobs.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import json
import os

import ezdxf
import pytest

from conftest import EXAMPLES, ROOT
from cutsheet.layout import build_layout
from cutsheet.model import JobError, job_from_dict, load_job
from cutsheet.pipeline import build_job
from cutsheet.render import render_cut_svg, write_cut_dxf
from cutsheet.verify import verify

LB = os.path.join(EXAMPLES, "l_bracket_v1.0.svg")


def _job(**over):
    raw = {"job_name": "lab", "sheet": "laser_24x18", "outer_edge_margin": 0.25, "kerf": 0.125,
           "cutting_method": "free", "nest_mode": "bounding-box",
           "parts": [{"id": "A", "width": 6, "height": 4, "quantity": 12}]}
    raw.update(over)
    return job_from_dict(raw)


def _checks(lay):
    return {c.name: c for c in verify(lay, determinism=False).checks}


# 1. Router, beside-cutout, spacing bump
def test_router_beside_cutout_bumps_spacing_and_labels_every_part():
    job = _job(machine="router", marking_tool_diameter=0.125, labels={"mode": "beside-cutout"})
    assert job.label_font == "single-line"
    mn, basis = job.label_min_height()
    assert mn == pytest.approx(0.625) and "5 x tool" in basis
    assert job.spacing_bump is not None and job.spacing_bump[0] == pytest.approx(0.125)
    assert job.gap > 0.625 + 0.12  # cap + descent + 2 x pad
    lay = build_layout(job)
    lr = lay.label_report
    assert lr.enabled and lr.counts.get("beside-cutout") == 12 and not lr.events, (lr.counts, lr.events)
    ch = _checks(lay)
    assert ch["labels clear of cuts and each other"].passed
    assert ch["labels: spacing bump"].flagged
    assert ch["no overlaps"].passed
    svg = render_cut_svg(lay, lay.sheets[0], "x.svg")
    eng = svg.split('id="ENGRAVE"')[1]
    assert eng.count('<g id="label-') == len(lay.sheets[0].placements)
    assert 'fill="#0000ff"' not in eng  # single-line: strokes, not fills


# 2. Laser, on-piece, outline and single-line
@pytest.mark.parametrize("font,filled", [("outline", True), ("single-line", False)])
def test_laser_on_piece_lbracket(tmp_path, font, filled):
    job = job_from_dict({"job_name": "lb", "sheet": "laser_24x18", "outer_edge_margin": 0.25, "kerf": 0.125,
                         "cutting_method": "free", "nest_mode": "true-outline", "rotation_step": 90,
                         "machine": "laser", "labels": {"mode": "on-piece", "font": font, "cap_height": 0.3},
                         "parts": [{"id": "L", "quantity": 12, "source": {"type": "file", "path": LB}}]})
    lay = build_layout(job)
    lr = lay.label_report
    assert lr.counts.get("on-piece") == 12 and not lr.events, (lr.counts, lr.events)
    assert all(pl.label.angle in (0.0, 90.0) for pl in lay.placements)  # upright, even on R180 copies
    ch = _checks(lay)
    assert ch["labels inside their part"].passed
    svg = render_cut_svg(lay, lay.sheets[0], "x.svg")
    eng = svg.split('id="ENGRAVE"')[1]
    assert eng.count('<g id="label-') == 12
    assert ('fill="#0000ff"' in eng) == filled
    out = tmp_path / "x.dxf"
    write_cut_dxf(lay, lay.sheets[0], str(out))
    ents = [e for e in ezdxf.readfile(str(out)).modelspace() if e.dxf.layer == "ENGRAVE"]
    assert ents
    assert all(e.closed == filled for e in ents)  # outline glyphs closed, single-line strokes open
    if filled:
        assert any(e.dxf.layer == "ENGRAVE" for e in ents)


# 3. Fallback disclosure
def test_fallbacks_are_disclosed_not_silent():
    small = {"id": "tiny", "width": 0.5, "height": 0.5, "quantity": 3}
    # on-piece cannot fit a 0.625 in label; falls to beside-cutout (spacing was bumped for it? no: mode is on-piece so no bump)
    job = _job(machine="router", marking_tool_diameter=0.125, labels={"mode": "on-piece"}, parts=[small])
    lay = build_layout(job)
    lr = lay.label_report
    # Three tiny parts in a row: none can hold the label; the first drops to the waste below, the rest
    # collide with that label and drop. Every outcome is an event with a reason; none is silent.
    assert lr.counts.get("on-piece") is None
    assert lr.counts.get("downgraded", 0) >= 1 and lr.counts.get("downgraded", 0) + lr.counts.get("dropped", 0) == 3, (lr.counts, lr.events)
    assert len(lr.events) == 3 and all(e.requested == "on-piece" and "does not fit" in e.reason for e in lr.events)
    ch = _checks(lay)
    assert ch["labels: placement per part"].flagged and ch["labels: placement per part"].passed
    assert ch["labels clear of cuts and each other"].passed
    # with kerf-gap, auto_spacing off and fallback drop: dropped with reasons, still a passing build
    job2 = _job(machine="router", marking_tool_diameter=0.125,
                labels={"mode": "beside-cutout", "auto_spacing": False, "fallback": "drop"}, parts=[small])
    lay2 = build_layout(job2)
    lr2 = lay2.label_report
    # One label fits in the waste below the row; the other two would collide with it and drop, each with a reason.
    assert lr2.counts.get("beside-cutout") == 1 and lr2.counts.get("dropped") == 2, lr2.counts
    assert all(e.result == "dropped" and "no clear waste strip" in e.reason for e in lr2.events)
    assert all((pl.label is None) == bool(pl.label_reason) for pl in lay2.placements)
    assert verify(lay2, determinism=False).all_passed


# 4. Refusal
def test_plasma_and_waterjet_refuse_labels():
    for m in ("plasma", "waterjet"):
        with pytest.raises(JobError, match="cannot mark"):
            _job(machine=m, labels={"mode": "on-piece"})
        _job(machine=m, labels={"mode": "none"})  # fine without labels
    with pytest.raises(JobError, match="machine"):
        _job(labels={"mode": "on-piece"})
    with pytest.raises(JobError, match="marking_tool_diameter"):
        _job(machine="router", labels={"mode": "on-piece"})


# 5. Backward compatibility
def test_unlabeled_jobs_are_unchanged(tmp_path):
    for name in ("trophy_job_v1.0.json", "l_bracket_job_v1.0.json"):
        job = load_job(os.path.join(EXAMPLES, name))
        assert not job.labels_enabled and job.machine is None and job.outputs is None
        res = build_job(job, str(tmp_path / name[:6]), dxf=True, determinism=False)
        assert res.ok
        assert res.layout.label_report is not None and not res.layout.label_report.enabled
        svg = open(os.path.join(res.out_dir, [o for o in res.outputs if o.endswith("sheet01_cut_v1.0.svg")][0])).read()
        assert "No labels." in svg and "label-" not in svg


# 6. Determinism
def test_labels_are_deterministic():
    job = _job(machine="router", marking_tool_diameter=0.125, labels={"mode": "beside-cutout"})
    a = [(p.key, p.label.x, p.label.y, p.label.angle) for p in build_layout(job).placements]
    b = [(p.key, p.label.x, p.label.y, p.label.angle) for p in build_layout(job).placements]
    assert a == b


# 7. Profiles
def test_profile_defaults_and_job_overrides():
    job = job_from_dict({"job_name": "p", "profile": "router_1_8", "cutting_method": "free",
                         "parts": [{"id": "A", "width": 6, "height": 4, "quantity": 2}]})
    assert job.machine == "router" and job.marking_tool_diameter == pytest.approx(0.125)
    assert job.kerf == pytest.approx(0.25) and job.part_spacing_mode == "custom-margin"
    assert job.labels.font == "single-line" and job.labels.cap_height == pytest.approx(0.75)
    assert job.outputs == ["reference", "dxf", "pdf"] and job.sheet_preset == "plywood_4x8"
    job2 = job_from_dict({"job_name": "p", "profile": "router_1_8", "cutting_method": "free", "kerf": 0.1,
                          "labels": {"mode": "on-piece"}, "parts": [{"id": "A", "width": 6, "height": 4, "quantity": 2}]})
    assert job2.kerf == pytest.approx(0.1) and job2.labels.mode == "on-piece" and job2.labels.cap_height == pytest.approx(0.75)
    with pytest.raises(JobError, match="available"):
        job_from_dict({"job_name": "p", "profile": "nope", "cutting_method": "free", "parts": [{"id": "A", "width": 1, "height": 1, "quantity": 1}]})


def test_profile_in_job_folder_wins_over_shipped(tmp_path):
    os.makedirs(tmp_path / "profiles")
    json.dump({"machine": "laser", "sheet": "laser_24x18", "kerf": 0.02, "outer_edge_margin": 0.3}, open(tmp_path / "profiles" / "router_1_8.json", "w"))
    job = job_from_dict({"job_name": "p", "profile": "router_1_8", "cutting_method": "free",
                         "parts": [{"id": "A", "width": 6, "height": 4, "quantity": 1}]}, base_dir=str(tmp_path))
    assert job.machine == "laser" and job.kerf == pytest.approx(0.02)


# 8. Outputs
def test_outputs_selection(tmp_path):
    job = _job(outputs=["dxf"])
    res = build_job(job, str(tmp_path), dxf=True, determinism=False, pdf=True)
    names = res.outputs
    assert any(n.endswith(".dxf") for n in names)
    assert not any(n.endswith("_cut_v1.0.svg") or n.endswith("_reference_v1.0.svg") or n.endswith(".pdf") for n in names)
    assert any(n.endswith("_cut_list_v1.0.md") for n in names) and any(n.endswith("_validation_v1.0.md") for n in names)
    assert res.ok


# 9. Hand
def test_hand_labels_reference_only(tmp_path):
    base = _job()
    res0 = build_job(base, str(tmp_path / "a"), dxf=True, determinism=False)
    job = _job(machine="hand", labels={"mode": "on-piece", "cap_height": 0.6})
    res1 = build_job(job, str(tmp_path / "b"), dxf=True, determinism=False)
    assert res1.ok and res1.layout.label_report.render_only
    assert res1.layout.label_report.counts.get("on-piece") == 12
    cut0 = open(tmp_path / "a" / "lab_sheet01_cut_v1.0.svg").read()
    cut1 = open(tmp_path / "b" / "lab_sheet01_cut_v1.0.svg").read()
    assert cut0 == cut1  # cut file untouched by hand-job labels
    assert res1.reference_svg.count('class="label"') >= 12
    assert 'class="label"' not in res0.reference_svg


# per-part overrides and text
def test_per_part_mode_and_text_override():
    job = _job(machine="laser", labels={"mode": "on-piece", "cap_height": 0.3},
               parts=[{"id": "A", "width": 6, "height": 4, "quantity": 2, "label": {"text": "SHELF-L"}},
                      {"id": "B", "width": 6, "height": 4, "quantity": 2, "label": {"mode": "none"}}])
    lay = build_layout(job)
    a = [p for p in lay.placements if p.part_id == "A"]
    b = [p for p in lay.placements if p.part_id == "B"]
    assert all(p.label.text == "SHELF-L" for p in a)
    assert all(p.label is None and p.label_reason == "mode none" for p in b)
    job2 = _job(machine="laser", labels={"mode": "on-piece", "text": "id+copy", "cap_height": 0.3},
                parts=[{"id": "A", "width": 6, "height": 4, "quantity": 2}])
    assert sorted(p.label.text for p in build_layout(job2).placements) == ["A#1", "A#2"]


# CHANGELOG
# v1.0 (2026-09-05): Initial release.
