"""
file: report.py
version: 1.2
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Writes the cut list / stock summary markdown, the validation report (markdown + JSON), and the layout JSON, all with revision-control metadata and changelogs.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

import datetime as _dt
import json

from . import units as U
from .layout import Layout
from .verify import Report

TODAY = _dt.date.today().isoformat()


def _front(filename: str, version: str, author: str, description: str) -> str:
    return (f"---\nfile: {filename}\nversion: {version}\nauthor: {author}\ncreated: {TODAY}\nlast_updated: {TODAY}\n"
            f"description: {description}\nai_update: Update last_updated and version. Rename file to match. Append changelog at bottom.\n---\n\n")


def _changelog(version: str) -> str:
    return f"\n## CHANGELOG\n- v{version} ({TODAY}): Initial release.\n"


def _pos(v: float, du: str) -> str:
    s = U.fmt(v, du)
    if du == "in":
        s += f" ({U.fmt_fraction(v)})"
    return s


def cut_list_md(layout: Layout, filename: str, outputs: list[str]) -> str:
    job = layout.job
    du = job.display_unit
    L = []
    L.append(_front(filename, job.version, job.author, f"Cut list and stock summary for job '{job.name}'."))
    L.append(f"# Cut list: {job.name}\n\n")
    spacing = job.part_spacing_mode + (f" = {U.fmt(job.custom_margin, du)}" if job.part_spacing_mode == "custom-margin" else "")
    L.append("| Setting | Value |\n|---|---|\n")
    stock_desc = "; ".join(f"{U.fmt(st.width, du)} x {U.fmt(st.height, du)}" + (f" ({st.preset})" if st.preset else "") + (f" x{st.quantity} available" if st.quantity else "") for st in job.stocks)
    L.append(f"| Stock | {stock_desc}" + (" (used in this order)" if job.multi_stock else "") + " |\n")
    L.append(f"| Kerf | {U.fmt(job.kerf, du)} |\n")
    L.append(f"| Outer edge margin | {U.fmt(job.outer_edge_margin, du)} |\n")
    L.append(f"| Part spacing | {spacing} (gap {U.fmt(job.gap, du)}) |\n")
    L.append(f"| Cutting method | {job.cutting_method} |\n")
    L.append(f"| Nest mode | {job.nest_mode} |\n")
    L.append(f"| Engine | {'; '.join(f'{m}: {e}' for m, e in layout.engines_used.items()) or 'n/a'} |\n")
    L.append(f"| Coordinates | x from left edge, y from top edge, to the part's bounding-box corner |\n\n")

    # Stock summary
    n_sheets = len(layout.sheets)
    n_def = sum(1 for s in layout.sheets if s.deferred)
    parts_area = sum(pl.polygon.area for pl in layout.placements)
    total = sum(s.area for s in layout.sheets)
    L.append("## Stock summary\n\n")
    if n_sheets:
        L.append(f"- Sheets needed: **{n_sheets}**" + (f" ({n_sheets - n_def} now, {n_def} deferred)" if n_def else "") + "\n")
        if job.multi_stock:
            counts = {}
            for s in layout.sheets:
                counts[s.stock] = counts.get(s.stock, 0) + 1
            L.append("- By size: " + ", ".join(f"{k}: {v}" for k, v in counts.items()) + "\n")
        L.append(f"- Utilization: {100 * parts_area / total:.1f}% of sheet area used, {100 * (1 - parts_area / total):.1f}% waste\n")
    if layout.rod_result:
        for r in layout.rod_result["rods"]:
            line = f"- Rod {r['id']}: {r['quantity']} x {U.fmt(r['piece_length'], du)} with {U.fmt(r['kerf'], du)} kerf = **{U.fmt(r['continuous_length'], du)}** continuous"
            if r.get("stock_length"):
                line += f"; **{r['bars_needed']} bar(s)** of {U.fmt(r['stock_length'], du)}, waste {100 * r['waste_fraction']:.1f}%"
            L.append(line + "\n")
    L.append("\n")

    # Parts
    L.append("## Parts\n\n| Part | Size (w x h) | True area | Qty | Rotation | Engrave | Group | Source |\n|---|---|---|---|---|---|---|---|\n")
    for p in job.parts:
        rot = "auto" if p.rotation == "auto" else f"locked {p.locked_angle:g}"
        area = U.from_base(U.from_base(p.true_area, du), du)
        L.append(f"| {p.id} | {U.fmt(p.width, du)} x {U.fmt(p.height, du)} | {area:.2f} {du}^2 | {p.quantity} | {rot} | {'yes' if p.engrave else ''} | {p.group or ''} | {p.source} |\n")
    L.append("\n")

    # Per sheet
    for s in layout.sheets:
        title = f"## {s.label} of {n_sheets} ({U.fmt(s.width, du)} x {U.fmt(s.height, du)})"
        if s.group:
            title += f" (group {s.group})"
        if s.deferred:
            title += " DEFERRED"
        L.append(title + "\n\n")
        counts = {}
        for pl in s.placements:
            counts[pl.part_id] = counts.get(pl.part_id, 0) + 1
        L.append("Contents: " + ", ".join(f"{k} x{v}" for k, v in sorted(counts.items())) + "\n\n")
        L.append("| # | Part | Copy | x | y | Placed w x h | Rotation |\n|---|---|---|---|---|---|---|\n")
        for i, pl in enumerate(s.placements, 1):
            rot = f"{pl.angle:g} deg" if pl.angle % 360 else "0"
            L.append(f"| {i} | {pl.part_id} | {pl.index} | {_pos(pl.x, du)} | {_pos(pl.y, du)} | {U.fmt(pl.w, du)} x {U.fmt(pl.h, du)} | {rot} |\n")
        L.append("\n")

    if layout.rod_result:
        L.append("## Rods\n\n")
        for r in layout.rod_result["rods"]:
            L.append(f"### {r['id']}\n\n")
            if r["bars"]:
                L.append("| Bar | Pieces | Used | Offcut |\n|---|---|---|---|\n")
                for i, b in enumerate(r["bars"], 1):
                    L.append(f"| {i} | {len(b['pieces'])} x {U.fmt(b['pieces'][0], du)} | {U.fmt(b['used'], du)} | {U.fmt(b['offcut'], du)} |\n")
                L.append("\nOffcut is stock minus pieces minus the kerfs between pieces; the final cut that frees the offcut is not counted (PRD 7.4 convention).\n\n")
            else:
                L.append(f"Continuous length required: {U.fmt(r['continuous_length'], du)} (no stock length given).\n\n")

    lr = layout.label_report
    if lr is not None and lr.enabled:
        L.append("## Labels\n\n")
        L.append(f"- Machine: {lr.machine}" + (f" (profile {job.profile})" if job.profile else "") +
                 (f", marking tool {U.fmt(job.marking_tool_diameter, du)}" if job.marking_tool_diameter else "") + "\n")
        L.append(f"- Font: {lr.font}; requested cap height {U.fmt(lr.requested_height, du)}, minimum {U.fmt(lr.min_height, du)} ({lr.basis}), effective {U.fmt(lr.effective_height, du)}\n")
        if lr.render_only:
            L.append("- Hand cutting: labels appear on the reference sheets and PDF only; cut files carry none.\n")
        elif job.machine == "laser":
            L.append(f"- Laser setup: set the ENGRAVE layer to **{'fill (raster)' if lr.font == 'outline' else 'line (score)'}**.\n")
        elif job.machine == "router":
            L.append(f"- Router setup: run layer {job.labels.dxf_layer} as an engraving toolpath with the {U.fmt(job.marking_tool_diameter, du)} tool before the profile pass.\n")
        if lr.spacing_bump:
            L.append(f"- Part spacing raised from {U.fmt(lr.spacing_bump[0], du)} to {U.fmt(lr.spacing_bump[1], du)} so beside-cutout labels fit in the waste.\n")
        L.append("- Outcome: " + ", ".join(f"{k} {v}" for k, v in sorted(lr.counts.items())) + "\n")
        for ev in lr.events:
            L.append(f"  - {ev.key} (sheet {ev.sheet + 1}): requested {ev.requested}, result {ev.result}: {ev.reason}\n")
        for key, orig, laid in lr.substitutions:
            L.append(f"  - {key}: text '{orig}' written as '{laid}' (unsupported characters)\n")
        L.append("\n")
    L.append("## Files\n\n")
    for o in outputs:
        L.append(f"- `{o}`\n")
    L.append(_changelog(job.version))
    return "".join(L)


def validation_md(layout: Layout, rep: Report, filename: str) -> str:
    job = layout.job
    L = [_front(filename, job.version, job.author, f"Validation report for job '{job.name}': every post-nesting check and its result.")]
    status = "ALL CHECKS PASSED" if rep.all_passed else "CHECKS FAILED - DO NOT CUT FROM THIS LAYOUT"
    L.append(f"# Validation: {job.name}\n\n**{status}**\n\n")
    if any(c.flagged for c in rep.checks):
        L.append("Flagged (passed, but read the note): " + "; ".join(c.name for c in rep.checks if c.flagged) + "\n\n")
    L.append("| Check | Result | Detail |\n|---|---|---|\n")
    for c in rep.checks:
        res = "PASS" if c.passed else "FAIL"
        if c.flagged:
            res += " (flagged)"
        L.append(f"| {c.name} | {res} | {c.detail} |\n")
    L.append(_changelog(job.version))
    return "".join(L)


def validation_json(layout: Layout, rep: Report, filename: str) -> str:
    job = layout.job
    data = {
        "_metadata": {"file": filename, "version": job.version, "author": job.author, "created": TODAY, "last_updated": TODAY,
                      "description": f"Validation results for job '{job.name}'.",
                      "ai_update": "Update last_updated and version. Append to _changelog array."},
        "_changelog": [{"version": job.version, "date": TODAY, "note": "Initial release."}],
        "job": job.name,
        "all_passed": rep.all_passed,
        "engines_used": layout.engines_used,
        "fallbacks": layout.fallbacks,
        "checks": [{"name": c.name, "passed": c.passed, "flagged": c.flagged, "detail": c.detail} for c in rep.checks],
    }
    return json.dumps(data, indent=2)


def layout_json(layout: Layout, filename: str) -> str:
    job = layout.job
    data = {
        "_metadata": {"file": filename, "version": job.version, "author": job.author, "created": TODAY, "last_updated": TODAY,
                      "description": f"Computed placements for job '{job.name}' in inches (x right, y down, bbox corner).",
                      "ai_update": "Update last_updated and version. Append to _changelog array."},
        "_changelog": [{"version": job.version, "date": TODAY, "note": "Initial release."}],
        "job": job.name,
        "units": "in",
        "sheet": {"width": job.sheet_width, "height": job.sheet_height, "preset": job.sheet_preset},
        "stocks": [{"width": st.width, "height": st.height, "quantity": st.quantity, "preset": st.preset} for st in job.stocks],
        "kerf": job.kerf, "outer_edge_margin": job.outer_edge_margin, "part_spacing_mode": job.part_spacing_mode, "gap": job.gap,
        "cutting_method": job.cutting_method, "nest_mode": job.nest_mode,
        "engines_used": layout.engines_used, "fallbacks": layout.fallbacks,
        "machine": job.machine, "marking_tool_diameter": job.marking_tool_diameter, "profile": job.profile, "outputs": job.outputs,
        "labels": ({"enabled": True, "font": layout.label_report.font, "effective_height": layout.label_report.effective_height,
                    "min_height": layout.label_report.min_height, "basis": layout.label_report.basis,
                    "spacing_bump": layout.label_report.spacing_bump, "counts": layout.label_report.counts,
                    "events": [vars(e) for e in layout.label_report.events]}
                   if layout.label_report is not None and layout.label_report.enabled else {"enabled": False}),
        "sheets": [
            {"index": s.index, "group": s.group, "deferred": s.deferred, "width": s.width, "height": s.height, "stock": s.stock,
             "placements": [{"part": p.part_id, "copy": p.index, "x": p.x, "y": p.y, "angle": p.angle, "w": p.w, "h": p.h,
                             "outline": [list(c) for c in p.polygon.exterior.coords[:-1]],
                             "holes": [[list(c) for c in h.coords[:-1]] for h in p.polygon.interiors],
                             "label": ({"mode": p.label.mode, "text": p.label.text, "font": p.label.font, "cap_height": p.label.cap_height,
                                        "x": p.label.x, "y": p.label.y, "angle": p.label.angle, "render_only": p.label.render_only}
                                       if p.label is not None else None),
                             "label_reason": p.label_reason}
                            for p in s.placements]}
            for s in layout.sheets
        ],
        "rods": layout.rod_result,
    }
    return json.dumps(data, indent=1)


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
# v1.1 (2026-09-04): Per-sheet sizes and stock list in reports.
# v1.2 (2026-09-05): Labels section in the cut list; label fields in the layout JSON.
