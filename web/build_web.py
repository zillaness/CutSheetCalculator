#!/usr/bin/env python3
"""
file: build_web.py
version: 1.1
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Builds web/index.html from web/template.html by embedding the cutsheet engine (zipped, base64) and the example files, so the page is a single self-contained static file.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

import base64
import datetime as _dt
import io
import json
import os
import sys
import zipfile

PYODIDE_VERSION = "0.27.7"  # last 0.27.x release (checked against the npm registry 2026-09-04)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENGINE = os.path.join(ROOT, "cut-sheet-builder", "scripts", "cutsheet")
EXAMPLES = os.path.join(ROOT, "cut-sheet-builder", "assets", "examples")


def engine_zip_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(ENGINE)):
            if name.endswith(".py"):
                info = zipfile.ZipInfo(f"cutsheet/{name}", date_time=(2026, 1, 1, 0, 0, 0))  # stable zip -> stable html
                with open(os.path.join(ENGINE, name), "rb") as fh:
                    z.writestr(info, fh.read(), compress_type=zipfile.ZIP_DEFLATED)
    return base64.b64encode(buf.getvalue()).decode()


def engine_version() -> str:
    sys.path.insert(0, os.path.dirname(ENGINE))
    import cutsheet  # noqa
    return getattr(cutsheet, "__version__", "?")


def build(date: str | None = None) -> str:
    with open(os.path.join(HERE, "template.html"), encoding="utf-8") as fh:
        html = fh.read()
    with open(os.path.join(EXAMPLES, "l_bracket_v1.0.svg"), "rb") as fh:
        lb = base64.b64encode(fh.read()).decode()
    with open(os.path.join(EXAMPLES, "trophy_job_v1.0.json"), encoding="utf-8") as fh:
        trophy = {k: v for k, v in json.load(fh).items() if not k.startswith("_")}
    html = (html.replace("__PYODIDE_VERSION__", PYODIDE_VERSION)
                .replace("__ENGINE_ZIP_B64__", engine_zip_b64())
                .replace("__EXAMPLE_LBRACKET_SVG_B64__", lb)
                .replace("__EXAMPLE_TROPHY_JOB__", json.dumps(trophy))
                .replace("__ENGINE_VERSION__", engine_version())
                .replace("__BUILD_DATE__", date or _dt.date.today().isoformat()))
    return html


def main() -> int:
    out = os.path.join(HERE, "index.html")
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
