"""
file: test_pdf.py
version: 1.0
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: PDF cut sheet export: one page per sheet, placement table present in the per-sheet render.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import os

import pytest

from conftest import EXAMPLES
from cutsheet.model import load_job
from cutsheet.pipeline import build_job
from cutsheet.render import render_reference_svg


def test_per_sheet_render_has_placement_table():
    job = load_job(os.path.join(EXAMPLES, "trophy_job_v1.0.json"))
    res = build_job(job, "/tmp/csb_pdf_test_a", dxf=False, determinism=False)
    svg = render_reference_svg(res.layout, "x.svg", only_sheets=[0], with_table=True)
    assert "Placements (x, y" in svg
    assert svg.count('class="sheet"') == 1
    assert "Sheet 1" in svg and "Sheet 2 of" not in svg


def test_pdf_has_one_page_per_sheet(tmp_path):
    pytest.importorskip("cairosvg")
    pypdf = pytest.importorskip("pypdf")
    job = load_job(os.path.join(EXAMPLES, "trophy_job_v1.0.json"))
    res = build_job(job, str(tmp_path), dxf=False, determinism=False, pdf=True)
    pdfs = [o for o in res.outputs if o.endswith(".pdf")]
    assert pdfs == ["trophy_cut_sheet_v1.0.pdf"]
    reader = pypdf.PdfReader(str(tmp_path / pdfs[0]))
    assert len(reader.pages) == len(res.layout.sheets) == 3
    text = reader.pages[2].extract_text()
    assert "DEFERRED" in text and "Placements" in text


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
