"""
file: test_engrave_layers.py
version: 1.0
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Engrave/score layer detection on DXF and SVG import, transport through rotation and placement, and emission on the ENGRAVE layer of cut files.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import ezdxf
import pytest

from cutsheet.importers import import_dxf, import_svg
from cutsheet.layout import build_layout
from cutsheet.model import job_from_dict
from cutsheet.render import render_cut_svg, write_cut_dxf
from cutsheet.verify import verify

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
       'width="4in" height="4in" viewBox="0 0 4 4">'
       '<g id="cut"><path d="M0,0 H4 V1 H1 V4 H0 Z"/></g>'
       '<g id="layer2" inkscape:label="Engrave"><path d="M1.5,0.3 L3.5,0.3"/><circle cx="2.5" cy="0.6" r="0.2"/></g></svg>')


def _dxf(path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 1
    doc.layers.add("CUT")
    doc.layers.add("SCORE")
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)], close=True, dxfattribs={"layer": "CUT"})
    msp.add_line((1.5, 0.3), (3.5, 0.3), dxfattribs={"layer": "SCORE"})
    msp.add_circle((2.5, 0.6), 0.2, dxfattribs={"layer": "SCORE"})
    doc.saveas(str(path))


def test_svg_engrave_group_detected(tmp_path):
    f = tmp_path / "e.svg"
    f.write_text(SVG)
    poly, note, eng = import_svg(str(f))
    assert poly.area == pytest.approx(7.0)
    assert sorted(g.geom_type for g in eng) == ["LineString", "Polygon"]
    assert "engrave" in note


def test_dxf_score_layer_detected(tmp_path):
    f = tmp_path / "e.dxf"
    _dxf(f)
    poly, note, eng = import_dxf(str(f))
    assert poly.area == pytest.approx(7.0)
    assert sorted(g.geom_type for g in eng) == ["LineString", "Polygon"]


def test_engrave_travels_with_rotation_and_lands_in_cut_files(tmp_path):
    f = tmp_path / "e.svg"
    f.write_text(SVG)
    job = job_from_dict({"job_name": "eng", "sheet": "laser_24x18", "outer_edge_margin": 0.25, "kerf": 0.125,
                         "cutting_method": "free", "nest_mode": "true-outline", "rotation_step": 90,
                         "parts": [{"id": "L", "quantity": 8, "source": {"type": "file", "path": str(f)}}]})
    assert job.parts[0].engrave is True  # auto-flagged from the import
    lay = build_layout(job)
    assert any(p.angle != 0 for p in lay.placements)
    rep = verify(lay, determinism=False)
    assert rep.all_passed, [c for c in rep.checks if not c.passed]
    assert any(c.name.startswith("engrave") and c.passed for c in rep.checks)
    for pl in lay.placements:
        assert len(pl.engrave) == 2
        for g in pl.engrave:
            assert pl.polygon.buffer(1e-6).covers(g)
    svg = render_cut_svg(lay, lay.sheets[0], "x.svg")
    eng_layer = svg.split('id="ENGRAVE"')[1]
    assert eng_layer.count("<path") == 16
    assert "Paste engrave artwork" not in svg
    out = tmp_path / "x.dxf"
    write_cut_dxf(lay, lay.sheets[0], str(out))
    doc = ezdxf.readfile(str(out))
    layers = {}
    for e in doc.modelspace():
        layers[e.dxf.layer] = layers.get(e.dxf.layer, 0) + 1
    assert layers["CUT"] == 8 and layers["ENGRAVE"] == 16


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
