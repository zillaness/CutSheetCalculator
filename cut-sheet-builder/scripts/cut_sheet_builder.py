#!/usr/bin/env python3
"""
file: cut_sheet_builder.py
version: 1.0
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: CLI for the cut-sheet-builder skill. `echo` confirms parsed parts, `build` nests, renders, verifies, and writes versioned artifacts, `deps` reports which engines are available.
ai_update: Update last_updated and version. Append changelog at bottom.

Usage:
  python cut_sheet_builder.py deps
  python cut_sheet_builder.py presets
  python cut_sheet_builder.py echo  job.json [--out DIR]
  python cut_sheet_builder.py build job.json [--out DIR] [--no-determinism] [--no-dxf]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cutsheet import units as U  # noqa: E402
from cutsheet.model import SHEET_PRESETS, JobError, load_job, parts_table  # noqa: E402
from cutsheet.importers import ImportError_  # noqa: E402


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "job"


def cmd_deps(_args) -> int:
    rows = []
    for mod, role in [("shapely", "geometry + verification (required)"), ("ezdxf", "DXF import/export (required for DXF)"),
                      ("svgelements", "SVG import (required for SVG)"), ("rectpack", "bounding-box engine (optional; bundled MaxRects otherwise)"),
                      ("pynest2d", "true-outline engine (optional; bundled shapely nester otherwise)")]:
        try:
            m = __import__(mod)
            rows.append((mod, "available " + str(getattr(m, "__version__", "")), role))
        except Exception:
            rows.append((mod, "MISSING", role))
    for mod, status, role in rows:
        print(f"{mod:12s} {status:22s} {role}")
    return 0


def cmd_presets(_args) -> int:
    for k, (w, h, u) in SHEET_PRESETS.items():
        print(f"{k:14s} {w:g} x {h:g} {u}")
    return 0


def _print_table(rows: list[dict]) -> None:
    cols = ["id", "width", "height", "true_area", "bbox_fill", "quantity", "rotation", "engrave", "group", "nest_mode", "source", "notes"]
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    print(" | ".join(c.ljust(widths[c]) for c in cols))
    print("-+-".join("-" * widths[c] for c in cols))
    for r in rows:
        print(" | ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


def cmd_echo(args) -> int:
    from cutsheet.render import render_parts_echo_svg
    job = load_job(args.job)
    out_dir = args.out or os.path.join(os.path.dirname(os.path.abspath(args.job)), "out", slug(job.name))
    os.makedirs(out_dir, exist_ok=True)
    du = job.display_unit
    print(f"Job: {job.name}   sheet {U.fmt(job.sheet_width, du)} x {U.fmt(job.sheet_height, du)}   kerf {U.fmt(job.kerf, du)}   "
          f"margin {U.fmt(job.outer_edge_margin, du)}   spacing {job.part_spacing_mode} (gap {U.fmt(job.gap, du)})   cutting {job.cutting_method}   nest {job.nest_mode}")
    _print_table(parts_table(job))
    for r in job.rods:
        print(f"rod {r.id}: {r.quantity} x {U.fmt(r.length, du)}" + (f" from {U.fmt(r.stock_length, du)} stock" if r.stock_length else ""))
    fname = f"{slug(job.name)}_parts_echo_v{job.version}.svg"
    path = os.path.join(out_dir, fname)
    if job.parts:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_parts_echo_svg(job, fname))
        print(f"\nPreview: {path}")
    print("Confirm these dimensions before building. Fix the job file and re-run echo if anything is off.")
    return 0


def cmd_build(args) -> int:
    from cutsheet.layout import build_layout
    from cutsheet.render import render_reference_svg, render_cut_svg, write_cut_dxf
    from cutsheet.report import cut_list_md, validation_md, validation_json, layout_json
    from cutsheet.verify import verify

    job = load_job(args.job)
    out_dir = args.out or os.path.join(os.path.dirname(os.path.abspath(args.job)), "out", slug(job.name))
    os.makedirs(out_dir, exist_ok=True)
    base = slug(job.name)
    V = job.version
    outputs = []

    layout = build_layout(job)

    ref_text = None
    if layout.placements:
        ref_name = f"{base}_reference_v{V}.svg"
        ref_text = render_reference_svg(layout, ref_name)
        with open(os.path.join(out_dir, ref_name), "w", encoding="utf-8") as fh:
            fh.write(ref_text)
        outputs.append(ref_name)
        for s in layout.sheets:
            tag = f"sheet{s.index + 1:02d}" + ("_deferred" if s.deferred else "")
            cut_name = f"{base}_{tag}_cut_v{V}.svg"
            with open(os.path.join(out_dir, cut_name), "w", encoding="utf-8") as fh:
                fh.write(render_cut_svg(layout, s, cut_name))
            outputs.append(cut_name)
            if not args.no_dxf:
                dxf_name = f"{base}_{tag}_cut_v{V}.dxf"
                if write_cut_dxf(layout, s, os.path.join(out_dir, dxf_name)):
                    outputs.append(dxf_name)

    rep = verify(layout, ref_text, determinism=not args.no_determinism)

    lay_name = f"{base}_layout_v{V}.json"
    with open(os.path.join(out_dir, lay_name), "w", encoding="utf-8") as fh:
        fh.write(layout_json(layout, lay_name))
    outputs.append(lay_name)
    val_name = f"{base}_validation_v{V}.md"
    val_json = f"{base}_validation_v{V}.json"
    with open(os.path.join(out_dir, val_json), "w", encoding="utf-8") as fh:
        fh.write(validation_json(layout, rep, val_json))
    outputs.append(val_json)
    outputs.append(val_name)
    cl_name = f"{base}_cut_list_v{V}.md"
    with open(os.path.join(out_dir, cl_name), "w", encoding="utf-8") as fh:
        fh.write(cut_list_md(layout, cl_name, outputs))
    outputs.append(cl_name)
    with open(os.path.join(out_dir, val_name), "w", encoding="utf-8") as fh:
        fh.write(validation_md(layout, rep, val_name))

    du = job.display_unit
    print(f"Job: {job.name}  ->  {out_dir}")
    print(f"Sheets: {len(layout.sheets)}" + (f" ({sum(1 for s in layout.sheets if s.deferred)} deferred)" if job.deferred_groups else ""))
    if layout.rod_result:
        for r in layout.rod_result["rods"]:
            line = f"Rod {r['id']}: {U.fmt(r['continuous_length'], du)} continuous"
            if r.get("stock_length"):
                line += f", {r['bars_needed']} bar(s) of {U.fmt(r['stock_length'], du)}"
            print(line)
    print("Engines: " + ("; ".join(f"{m}: {e}" for m, e in layout.engines_used.items()) or "n/a"))
    for fb in layout.fallbacks:
        print(f"FALLBACK: {fb}")
    print("\nValidation:")
    for c in rep.checks:
        tag = "PASS" if c.passed else "FAIL"
        if c.flagged:
            tag += "*"
        print(f"  [{tag}] {c.name}: {c.detail}")
    print("\nFiles:")
    for o in outputs:
        print(f"  {o}")
    if not rep.all_passed:
        print("\nVALIDATION FAILED. Do not cut from this layout.")
        return 2
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="cut-sheet-builder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("deps").set_defaults(fn=cmd_deps)
    sub.add_parser("presets").set_defaults(fn=cmd_presets)
    e = sub.add_parser("echo")
    e.add_argument("job")
    e.add_argument("--out")
    e.set_defaults(fn=cmd_echo)
    b = sub.add_parser("build")
    b.add_argument("job")
    b.add_argument("--out")
    b.add_argument("--no-determinism", action="store_true", help="skip the re-run determinism check (halves runtime)")
    b.add_argument("--no-dxf", action="store_true")
    b.set_defaults(fn=cmd_build)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (JobError, ImportError_) as ex:
        print(f"JOB ERROR: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
