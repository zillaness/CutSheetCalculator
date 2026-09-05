"""
file: test_web_page.py
version: 1.2
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Checks web/index.html is built from the current template and engine, and drives the page in headless Chromium with a stubbed engine that returns real webapi output.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import base64
import glob
import json
import os
import re
import sys

import pytest

from conftest import EXAMPLES, ROOT
from cutsheet import webapi

WEB = os.path.join(ROOT, "web")
sys.path.insert(0, WEB)
import build_web  # noqa: E402


def test_index_html_is_current():
    with open(os.path.join(WEB, "index.html"), encoding="utf-8") as fh:
        current = fh.read()
    m = re.search(r"last_updated: (\d{4}-\d{2}-\d{2})", current)
    assert m, "index.html has no metadata block"
    assert build_web.build(date=m.group(1)) == current, "web/index.html is stale: run python web/build_web.py"


def _chromium():
    """Explicit binary when the sandbox ships one; otherwise None lets Playwright use its own install."""
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome", "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


@pytest.fixture(scope="module")
def canned():
    with open(os.path.join(EXAMPLES, "l_bracket_v1.0.svg"), "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    job = {k: v for k, v in json.load(open(os.path.join(EXAMPLES, "l_bracket_job_v1.0.json"))).items() if not k.startswith("_")}
    req = json.dumps({"job": job, "files": {"l_bracket_v1.0.svg": b64}, "determinism": False})
    return {"echo": webapi.echo(req), "build": webapi.build(req)}


@pytest.fixture(scope="module")
def page(canned):
    pw = pytest.importorskip("playwright.sync_api")
    exe = _chromium()
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        except Exception as ex:  # no browser installed anywhere: skip rather than fail
            pytest.skip(f"no chromium available for the smoke test: {ex}")
        pg = browser.new_page()
        # No network in CI: serve an empty stub for the Pyodide script and inject a fake engine that
        # records the request the page built and answers with real engine output.
        pg.route("**/pyodide.js", lambda route: route.fulfill(status=200, content_type="application/javascript", body="function loadPyodide(){}"))
        pg.add_init_script(f"""
          window.__requests = [];
          window.CSB_ENGINE_STUB = {{
            echo: (j) => {{ window.__requests.push(['echo', j]); return {json.dumps(canned['echo'])}; }},
            build: (j) => {{ window.__requests.push(['build', j]); return {json.dumps(canned['build'])}; }},
          }};
          window.print = () => {{ window.__printed = true; }};
        """)
        pg.goto("file://" + os.path.join(WEB, "index.html"))
        yield pg
        browser.close()


def test_page_loads_with_stub_engine(page):
    page.wait_for_function("document.querySelector('#status').textContent.includes('Engine')")
    assert "test stub" in page.text_content("#status")
    assert not page.is_disabled("#btn-build")


def test_requires_cutting_method(page):
    page.click("#add-rect")
    page.fill("#parts tbody tr:last-child .w", "6")
    page.fill("#parts tbody tr:last-child .h", "4")
    page.click("#btn-build")
    page.wait_for_function("document.querySelector('#run-status').textContent.includes('cutting method')")


def test_example_echo_and_build_flow(page):
    page.reload()
    page.wait_for_function("document.querySelector('#status').textContent.includes('Engine')")
    page.click("#ex-lbracket")
    assert page.text_content("#parts tbody tr:last-child td:nth-child(2)").strip() == "l_bracket_v1.0.svg"
    page.click("#btn-echo")
    page.wait_for_selector("#echo-section:not([hidden])")
    assert "l_bracket_v1.0.svg" in page.text_content("#echo-table")
    assert page.query_selector("#echoview svg") is not None
    page.click("#btn-build")
    page.wait_for_selector("#results-section:not([hidden])")
    assert "ALL CHECKS PASSED" in page.text_content("#banner")
    links = page.eval_on_selector_all("#downloads a", "els => els.map(e => e.download)")
    assert "l_bracket_sheet01_cut_v1.0.svg" in links and "l_bracket_sheet01_cut_v1.0.dxf" in links
    assert page.query_selector("#sheets .sheetview svg") is not None
    # The page built a correct job request from the form.
    reqs = page.evaluate("window.__requests")
    kinds = [r[0] for r in reqs]
    assert kinds[-2:] == ["echo", "build"]
    job = json.loads(reqs[-1][1])["job"]
    assert job["cutting_method"] == "free" and job["nest_mode"] == "true-outline"
    assert job["parts"][0]["source"]["path"] == "l_bracket_v1.0.svg" and job["parts"][0]["quantity"] == 12
    assert "l_bracket_v1.0.svg" in json.loads(reqs[-1][1])["files"]
    # Print builds one page per sheet plus cut list and validation pages, then calls print().
    page.click("#btn-print")
    assert page.evaluate("window.__printed") is True
    assert page.evaluate("document.querySelectorAll('#print-pages .page').length") == 3


def test_profile_and_label_controls_build_a_labeled_job(page):
    page.reload()
    page.wait_for_function("document.querySelector('#status').textContent.includes('Engine')")
    page.select_option("#profile", "router_1_8")
    page.click("#apply-profile")
    assert page.input_value("#machine") == "router" and page.input_value("#tool-dia") == "0.125"
    page.click("#add-rect")
    page.fill("#parts tbody tr:last-child .w", "30")
    page.fill("#parts tbody tr:last-child .h", "11.25")
    page.fill("#parts tbody tr:last-child .ltext", "SHELF-L")
    page.select_option("#label-mode", "beside-cutout")
    page.check("input[name=cutting][value=free]")
    job = json.loads(page.evaluate("JSON.stringify(window.CSB.collectJob())"))["job"]
    assert job["machine"] == "router" and job["marking_tool_diameter"] == 0.125
    assert job["labels"]["mode"] == "beside-cutout" and job["labels"]["font"] == "single-line"
    assert job["parts"][0]["label"]["text"] == "SHELF-L"
    assert job["outputs"] == ["reference", "dxf", "pdf"]
    # labels on without a machine is refused by the form
    page.select_option("#machine", "")
    page.evaluate("document.querySelector('#run-status').textContent=''")
    page.click("#btn-build")
    page.wait_for_function("document.querySelector('#run-status').textContent.includes('pick the machine')")


def test_trophy_example_populates_rods_and_deferred(page):
    page.reload()
    page.wait_for_function("document.querySelector('#status').textContent.includes('Engine')")
    page.click("#ex-trophy")
    assert page.evaluate("document.querySelectorAll('#parts tbody tr').length") == 5
    assert page.evaluate("document.querySelectorAll('#rods tbody tr').length") == 1
    req = page.evaluate("JSON.stringify(window.CSB.collectJob())")
    job = json.loads(req)["job"]
    assert job["deferred_groups"] == ["C"] and job["rods"][0]["stock_length"] == 36
    c = next(p for p in job["parts"] if p["id"] == "C")
    assert c["rotation"] == "locked" and c["engrave"] is True and c["group"] == "C"


def test_offcut_rows_become_sheets_list(page):
    page.reload()
    page.wait_for_function("document.querySelector('#status').textContent.includes('Engine')")
    page.click("#ex-trophy")
    page.click("#add-stock")
    page.fill("#stocks tbody tr:last-child .sw", "12")
    page.fill("#stocks tbody tr:last-child .sh", "12")
    page.fill("#stocks tbody tr:last-child .sq", "2")
    job = json.loads(page.evaluate("JSON.stringify(window.CSB.collectJob())"))["job"]
    assert "sheet" not in job
    assert job["sheets"][0] == {"width": 12, "height": 12, "quantity": 2, "units": "in"}
    assert job["sheets"][-1] == "laser_24x18"


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
# v1.1 (2026-09-04): Fall back to Playwright's own Chromium (CI).
# v1.2 (2026-09-05): Profile and label control test.
# v1.1 (2026-09-04): Offcut rows test.
