"""
file: test_webapi.py
version: 1.0
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Tests the JSON web API that the static page calls under Pyodide, using the real engine.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import base64
import json
import os

from conftest import EXAMPLES
from cutsheet import webapi


def _lbracket_request():
    with open(os.path.join(EXAMPLES, "l_bracket_v1.0.svg"), "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    job = json.load(open(os.path.join(EXAMPLES, "l_bracket_job_v1.0.json")))
    job = {k: v for k, v in job.items() if not k.startswith("_")}
    return {"job": job, "files": {"l_bracket_v1.0.svg": b64}, "determinism": False}


def test_echo_returns_parts_and_preview():
    res = json.loads(webapi.echo(json.dumps(_lbracket_request())))
    assert res["ok"], res
    assert res["parts"][0]["id"] == "L" and res["parts"][0]["source"] == "l_bracket_v1.0.svg"
    assert res["echo_svg"].startswith("<?xml")
    assert res["summary"]["cutting"] == "free"


def test_build_returns_files_checks_and_per_sheet_svgs():
    res = json.loads(webapi.build(json.dumps(_lbracket_request())))
    assert res["ok"] and res["all_passed"], res.get("error") or [c for c in res["checks"] if not c["passed"]]
    names = set(res["files"])
    assert "l_bracket_reference_v1.0.svg" in names
    assert "l_bracket_sheet01_cut_v1.0.svg" in names and "l_bracket_sheet01_cut_v1.0.dxf" in names
    assert "l_bracket_cut_list_v1.0.md" in names and "l_bracket_validation_v1.0.md" in names
    assert "SECTION" in res["files"]["l_bracket_sheet01_cut_v1.0.dxf"][:60]
    assert len(res["sheets"]) == 1 and res["sheets"][0]["reference_svg"].startswith("<?xml")
    assert res["summary"]["sheets"] == 1


def test_bad_job_reports_error_not_trace():
    req = {"job": {"job_name": "x", "sheet": "laser_24x18", "kerf": 0.1, "outer_edge_margin": 0.2,
                   "parts": [{"id": "A", "width": 1, "height": 1, "quantity": 1}]}}  # no cutting_method
    res = json.loads(webapi.build(json.dumps(req)))
    assert not res["ok"] and "cutting_method" in res["error"] and "trace" not in res


def test_typed_rectangles_without_files():
    req = {"job": {"job_name": "rects", "sheet": "laser_24x18", "kerf": 0.125, "outer_edge_margin": 0.25,
                   "cutting_method": "free", "nest_mode": "bounding-box",
                   "parts": [{"id": "A", "width": 6, "height": 4, "quantity": 5}]}, "determinism": False}
    res = json.loads(webapi.build(json.dumps(req)))
    assert res["ok"] and res["all_passed"]


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
