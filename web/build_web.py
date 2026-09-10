#!/usr/bin/env python3
"""
file: build_web.py
version: 1.5
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-10
description: Builds web/index.html from web/template.html by embedding the cutsheet engine (zipped, base64) and the example files, so the page is a single self-contained static file.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

import base64
import datetime as _dt
import io
import json
import os
import re
import sys
import zipfile

PYODIDE_VERSION = "0.27.7"  # last 0.27.x release (checked against the npm registry 2026-09-04)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENGINE = os.path.join(ROOT, "cut-sheet-builder", "scripts", "cutsheet")
EXAMPLES = os.path.join(ROOT, "cut-sheet-builder", "assets", "examples")
PROFILES = os.path.join(ROOT, "cut-sheet-builder", "assets", "profiles")


def engine_zip_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(ENGINE):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for name in sorted(files):
                if name.endswith((".py", ".ttf", ".txt")):
                    rel = os.path.relpath(os.path.join(root, name), os.path.dirname(ENGINE))
                    info = zipfile.ZipInfo(rel.replace(os.sep, "/"), date_time=(2026, 1, 1, 0, 0, 0))  # stable zip -> stable html
                    with open(os.path.join(root, name), "rb") as fh:
                        z.writestr(info, fh.read(), compress_type=zipfile.ZIP_DEFLATED)
    return base64.b64encode(buf.getvalue()).decode()


def engine_version() -> str:
    sys.path.insert(0, os.path.dirname(ENGINE))
    import cutsheet  # noqa
    return getattr(cutsheet, "__version__", "?")


def cut_tool_kerf() -> dict:
    """Read the preset table off the engine so the page and the engine cannot drift apart."""
    sys.path.insert(0, os.path.dirname(ENGINE))
    from cutsheet.model import CUT_TOOL_KERF
    return dict(CUT_TOOL_KERF)


def build(date: str | None = None) -> str:
    with open(os.path.join(HERE, "template.html"), encoding="utf-8") as fh:
        html = fh.read()
    with open(os.path.join(EXAMPLES, "l_bracket_v1.0.svg"), "rb") as fh:
        lb = base64.b64encode(fh.read()).decode()
    with open(os.path.join(EXAMPLES, "trophy_job_v1.0.json"), encoding="utf-8") as fh:
        trophy = {k: v for k, v in json.load(fh).items() if not k.startswith("_")}
    profiles = {}
    for name in sorted(os.listdir(PROFILES)):
        if name.endswith(".json"):
            with open(os.path.join(PROFILES, name), encoding="utf-8") as fh:
                data = json.load(fh)
            profiles[name[:-5]] = {k: v for k, v in data.items() if not k.startswith("_")}
    html = (html.replace("__PYODIDE_VERSION__", PYODIDE_VERSION)
                .replace("__SHIPPED_PROFILES__", json.dumps(profiles))
                .replace("__ENGINE_ZIP_B64__", engine_zip_b64())
                .replace("__EXAMPLE_LBRACKET_SVG_B64__", lb)
                .replace("__EXAMPLE_TROPHY_JOB__", json.dumps(trophy))
                .replace("__CUT_TOOL_KERF__", json.dumps(cut_tool_kerf()))
                .replace("__ENGINE_VERSION__", engine_version())
                .replace("__BUILD_DATE__", date or _dt.date.today().isoformat()))
    return html


_STAMPED_DATE = re.compile(r"^  last_updated: (\d{4}-\d{2}-\d{2})$", re.M)


def main() -> int:
    out = os.path.join(HERE, "index.html")
    if os.path.exists(out):
        with open(out, encoding="utf-8") as fh:
            prev = fh.read()
        stamped = _STAMPED_DATE.search(prev)
        # Rebuilding on a later day must not report the page as stale. Re-stamp the build
        # date only when the generated content actually changed, so the CI staleness check
        # tracks the engine instead of the calendar.
        if stamped and build(stamped.group(1)) == prev:
            print(f"{out} is current (kept build date {stamped.group(1)})")
            return 0
    html = build()
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {out} ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
# v1.1 (2026-09-04): Pyodide 0.27.7.
# v1.2 (2026-09-05): Engine zip includes subpackages and font files.
# v1.3 (2026-09-05): Shipped profiles embedded.
# v1.5 (2026-09-10): Embed the engine's cut-tool kerf presets in the page.
# v1.4 (2026-09-10): Keep the committed build date when regenerated content is identical,
#                    so the CI staleness check tracks the engine and not the calendar.
