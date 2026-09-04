"""
file: test_acceptance.py
version: 1.1
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: PRD section 13 acceptance tests: trophy regression (rectangles, bounding-box mode) and irregular outline (true-outline mode), run through the full CLI pipeline.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import json
import os
import subprocess
import sys

import pytest

from conftest import EXAMPLES, SCRIPTS

CLI = os.path.join(SCRIPTS, "cut_sheet_builder.py")


def run_build(job_file, out_dir):
    r = subprocess.run([sys.executable, CLI, "build", job_file, "--out", str(out_dir)], capture_output=True, text=True)
    return r


def load_validation(out_dir, base):
    with open(os.path.join(out_dir, f"{base}_validation_v1.0.json")) as fh:
        return json.load(fh)


def test_trophy_regression(tmp_path):
    r = run_build(os.path.join(EXAMPLES, "trophy_job_v1.0.json"), tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    val = load_validation(tmp_path, "trophy")
    assert val["all_passed"], [c for c in val["checks"] if not c["passed"]]
    names = {c["name"] for c in val["checks"]}
    for required in ["single scale constant", "aspect ratio / outline fidelity", "cross-part consistency",
                     "no overlaps", "inside outer_edge_margin boundary", "counts match requested quantities",
                     "rod/bar stock math re-derived", "area accounting closes", "nesting engine", "deterministic",
                     "group isolation and deferral"]:
        assert required in names
    # Rod calc from PRD 7.4
    assert "161.1250 in" in next(c["detail"] for c in val["checks"] if c["name"].startswith("rod"))
    layout = json.load(open(tmp_path / "trophy_layout_v1.0.json"))
    assert layout["rods"]["rods"][0]["continuous_length"] == pytest.approx(161.125)
    # C isolated on its own deferred sheet(s), numbered last
    sheets = layout["sheets"]
    c_sheets = [s for s in sheets if s["group"] == "C"]
    assert c_sheets and all(s["deferred"] for s in c_sheets)
    assert all(not s["deferred"] for s in sheets[: len(sheets) - len(c_sheets)])
    for s in sheets:
        parts = {p["part"] for p in s["placements"]}
        assert ("C" in parts) == (s["group"] == "C")
    # Locked part never rotated
    assert all(p["angle"] == 0 for s in sheets for p in s["placements"] if p["part"] == "C")
    # Every output file exists with a versioned name
    for f in ["trophy_reference_v1.0.svg", "trophy_sheet01_cut_v1.0.svg", "trophy_sheet01_cut_v1.0.dxf",
              "trophy_cut_list_v1.0.md", "trophy_validation_v1.0.md", "trophy_layout_v1.0.json"]:
        assert (tmp_path / f).exists(), f
    assert any(f.name.endswith("_deferred_cut_v1.0.svg") for f in tmp_path.iterdir())
    assert (tmp_path / "trophy_sheet01_reference_v1.0.svg").exists() and (tmp_path / "trophy_sheet03_deferred_reference_v1.0.svg").exists()


def test_irregular_outline(tmp_path):
    r = run_build(os.path.join(EXAMPLES, "l_bracket_job_v1.0.json"), tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    val = load_validation(tmp_path, "l_bracket")
    assert val["all_passed"], [c for c in val["checks"] if not c["passed"]]
    engine = next(c for c in val["checks"] if c["name"] == "nesting engine")
    assert "true-outline" in engine["detail"]
    overlaps = next(c for c in val["checks"] if c["name"] == "no overlaps")
    assert "polygon intersection" in overlaps["detail"]
    layout = json.load(open(tmp_path / "l_bracket_layout_v1.0.json"))
    pls = [p for s in layout["sheets"] for p in s["placements"]]
    assert len(pls) == 12
    # Real outline rendered: L has 1 hole and more than 4 vertices; some copies rotated by autorotate.
    assert all(len(p["holes"]) == 1 and len(p["outline"]) > 6 for p in pls)
    assert any(p["angle"] != 0 for p in pls)
    # Cut-ready SVG is in real units with hairline strokes and no labels.
    svg = open(tmp_path / "l_bracket_sheet01_cut_v1.0.svg").read()
    assert 'width="24in"' in svg and 'viewBox="0 0 24 18"' in svg
    assert 'stroke-width="0.001"' in svg and "<text" not in svg
    assert svg.count("<path") == 12
    assert 'id="CUT"' in svg and 'id="ENGRAVE"' in svg


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
# v1.1 (2026-09-04): Per-sheet reference files asserted.
