"""
file: pipeline.py
version: 1.1
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: One build path shared by the CLI and the web page: nest, render, verify, and write every versioned artifact for a job.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .layout import Layout, build_layout
from .model import Job
from .render import render_reference_svg, render_cut_svg, write_cut_dxf, render_parts_echo_svg
from .report import cut_list_md, validation_md, validation_json, layout_json
from .verify import Report, verify


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "job"


@dataclass
class BuildResult:
    layout: Layout
    report: Report
    out_dir: str
    outputs: list[str] = field(default_factory=list)  # filenames in write order
    reference_svg: str = ""
    sheet_svgs: dict[int, str] = field(default_factory=dict)  # per-sheet reference renders (for printing)

    @property
    def ok(self) -> bool:
        return self.report.all_passed


def echo_job(job: Job, out_dir: str) -> str:
    """Write the parts-echo preview; returns its path."""
    os.makedirs(out_dir, exist_ok=True)
    fname = f"{slug(job.name)}_parts_echo_v{job.version}.svg"
    path = os.path.join(out_dir, fname)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_parts_echo_svg(job, fname))
    return path


def write_pdf(sheet_svgs: dict[int, str], path: str) -> str | None:
    """One PDF page per sheet from the per-sheet reference SVGs. Needs cairosvg; pypdf merges pages.
    Returns the written path, or None when cairosvg is unavailable."""
    try:
        import cairosvg
    except ImportError:
        return None
    pages = [cairosvg.svg2pdf(bytestring=svg.encode("utf-8")) for _, svg in sorted(sheet_svgs.items())]
    if not pages:
        return None
    try:
        from pypdf import PdfWriter, PdfReader
        import io
        w = PdfWriter()
        for pg in pages:
            for page in PdfReader(io.BytesIO(pg)).pages:
                w.add_page(page)
        with open(path, "wb") as fh:
            w.write(fh)
    except ImportError:  # no merger: first page only is wrong, so write one file per sheet instead
        root, ext = os.path.splitext(path)
        for i, pg in enumerate(pages, 1):
            with open(f"{root}_p{i:02d}{ext}", "wb") as fh:
                fh.write(pg)
        return f"{root}_p01{ext}"
    return path


def build_job(job: Job, out_dir: str, dxf: bool = True, determinism: bool = True, per_sheet_svgs: bool = False, pdf: bool = False) -> BuildResult:
    os.makedirs(out_dir, exist_ok=True)
    base = slug(job.name)
    V = job.version
    outputs: list[str] = []

    def write(name: str, text: str):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        outputs.append(name)

    layout = build_layout(job)
    ref_text = None
    sheet_svgs: dict[int, str] = {}
    if layout.placements:
        ref_name = f"{base}_reference_v{V}.svg"
        ref_text = render_reference_svg(layout, ref_name)
        write(ref_name, ref_text)
        for s in layout.sheets:
            tag = f"sheet{s.index + 1:02d}" + ("_deferred" if s.deferred else "")
            cut_name = f"{base}_{tag}_cut_v{V}.svg"
            write(cut_name, render_cut_svg(layout, s, cut_name))
            if dxf:
                dxf_name = f"{base}_{tag}_cut_v{V}.dxf"
                if write_cut_dxf(layout, s, os.path.join(out_dir, dxf_name)):
                    outputs.append(dxf_name)
            if per_sheet_svgs or pdf:
                sheet_svgs[s.index] = render_reference_svg(layout, f"{base}_{tag}_reference_v{V}.svg", only_sheets=[s.index], with_table=True)
        if pdf and sheet_svgs:
            pdf_name = f"{base}_cut_sheet_v{V}.pdf"
            written = write_pdf(sheet_svgs, os.path.join(out_dir, pdf_name))
            if written:
                outputs.append(os.path.basename(written))

    rep = verify(layout, ref_text, determinism=determinism)

    write(f"{base}_layout_v{V}.json", layout_json(layout, f"{base}_layout_v{V}.json"))
    val_json = f"{base}_validation_v{V}.json"
    val_md = f"{base}_validation_v{V}.md"
    write(val_json, validation_json(layout, rep, val_json))
    outputs.append(val_md)
    cl = f"{base}_cut_list_v{V}.md"
    write(cl, cut_list_md(layout, cl, outputs))
    with open(os.path.join(out_dir, val_md), "w", encoding="utf-8") as fh:
        fh.write(validation_md(layout, rep, val_md))

    return BuildResult(layout=layout, report=rep, out_dir=out_dir, outputs=outputs,
                       reference_svg=ref_text or "", sheet_svgs=sheet_svgs)


# CHANGELOG
# v1.0 (2026-09-04): Initial release (extracted from cut_sheet_builder.py cmd_build).
# v1.1 (2026-09-04): PDF cut sheet export (cairosvg + pypdf).
