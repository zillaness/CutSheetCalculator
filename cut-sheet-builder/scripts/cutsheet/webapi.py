"""
file: webapi.py
version: 1.2
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: JSON-in, JSON-out entry points for the static web page (runs under Pyodide). Uploaded files arrive base64-encoded inside the request; outputs come back as text.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import traceback

from . import units as U
from .model import JobError, job_from_dict, parts_table
from .pipeline import build_job, echo_job, slug


def _materialize(request: dict) -> tuple[dict, str]:
    """Write uploaded files into a fresh work dir; return (job_dict, work_dir)."""
    work = tempfile.mkdtemp(prefix="csb_")
    for name, b64 in (request.get("files") or {}).items():
        safe = os.path.basename(name)
        with open(os.path.join(work, safe), "wb") as fh:
            fh.write(base64.b64decode(b64))
    job = dict(request.get("job") or {})
    return job, work


def echo(request_json: str) -> str:
    try:
        req = json.loads(request_json)
        job_raw, work = _materialize(req)
        job = job_from_dict(job_raw, base_dir=work)
        path = echo_job(job, os.path.join(work, "out"))
        with open(path, encoding="utf-8") as fh:
            svg = fh.read()
        du = job.display_unit
        return json.dumps({
            "ok": True,
            "parts": parts_table(job),
            "rods": [{"id": r.id, "length": U.fmt(r.length, du), "quantity": r.quantity,
                      "stock_length": U.fmt(r.stock_length, du) if r.stock_length else ""} for r in job.rods],
            "summary": {
                "sheet": "; ".join(f"{U.fmt(st.width, du)} x {U.fmt(st.height, du)}" + (f" x{st.quantity}" if st.quantity else "") for st in job.stocks),
                "kerf": U.fmt(job.kerf, du), "margin": U.fmt(job.outer_edge_margin, du),
                "gap": U.fmt(job.gap, du), "spacing": job.part_spacing_mode,
                "cutting": job.cutting_method, "nest_mode": job.nest_mode,
                "rotation_step": job.rotation_step,
            },
            "echo_svg": svg,
        })
    except (JobError, ValueError) as ex:
        return json.dumps({"ok": False, "error": str(ex)})
    except Exception as ex:  # surface anything else with a trace for the status line
        return json.dumps({"ok": False, "error": f"{ex}", "trace": traceback.format_exc()})


def build(request_json: str) -> str:
    try:
        req = json.loads(request_json)
        job_raw, work = _materialize(req)
        job = job_from_dict(job_raw, base_dir=work)
        out_dir = os.path.join(work, "out")
        res = build_job(job, out_dir, dxf=bool(req.get("dxf", True)),
                        determinism=bool(req.get("determinism", True)), per_sheet_svgs=True)
        files = {}
        for name in res.outputs:
            with open(os.path.join(out_dir, name), encoding="utf-8", errors="replace") as fh:
                files[name] = fh.read()
        lay = res.layout
        du = job.display_unit
        rods = []
        if lay.rod_result:
            for r in lay.rod_result["rods"]:
                rods.append({"id": r["id"], "continuous": U.fmt(r["continuous_length"], du),
                             "bars": r.get("bars_needed"), "stock": U.fmt(r["stock_length"], du) if r.get("stock_length") else ""})
        parts_area = sum(p.polygon.area for p in lay.placements)
        total = sum(s.area for s in lay.sheets)
        return json.dumps({
            "ok": True,
            "all_passed": res.ok,
            "checks": [{"name": c.name, "passed": c.passed, "flagged": c.flagged, "detail": c.detail} for c in res.report.checks],
            "sheets": [{"index": s.index, "label": s.label, "group": s.group, "deferred": s.deferred, "stock": s.stock,
                        "width": s.width, "height": s.height,
                        "count": len(s.placements), "reference_svg": res.sheet_svgs.get(s.index, "")} for s in lay.sheets],
            "summary": {"sheets": len(lay.sheets), "deferred": sum(1 for s in lay.sheets if s.deferred),
                        "utilization": (100 * parts_area / total) if total else 0.0, "rods": rods,
                        "engines": lay.engines_used, "fallbacks": lay.fallbacks,
                        "labels": ({"enabled": True, "font": lr.font, "effective_height": lr.effective_height, "min_height": lr.min_height,
                                    "basis": lr.basis, "spacing_bump": lr.spacing_bump, "counts": lr.counts,
                                    "events": [{"key": e.key, "requested": e.requested, "result": e.result, "reason": e.reason} for e in lr.events]}
                                   if (lr := lay.label_report) is not None and lr.enabled else {"enabled": False})},
            "files": files,
            "base": slug(job.name),
        })
    except (JobError, ValueError) as ex:
        return json.dumps({"ok": False, "error": str(ex)})
    except Exception as ex:
        return json.dumps({"ok": False, "error": f"{ex}", "trace": traceback.format_exc()})


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
# v1.1 (2026-09-04): Stock list in summaries; per-sheet sizes.
# v1.2 (2026-09-05): Label outcomes in the build summary.
