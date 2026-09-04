"""
file: verify.py
version: 1.0
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Post-nesting assertions. Re-parses the rendered reference SVG to confirm one uniform scale and outline fidelity, then checks overlaps, boundary, counts, stock math, area accounting, guillotine feasibility, grouping, determinism, and which engine ran.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import Polygon, box
from shapely.strtree import STRtree

from .layout import Layout, build_layout
from .model import Job
from .pack_rect import is_guillotine_cuttable
from .pack_poly import _inflate, AREA_TOL


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    flagged: bool = False  # passed, but the reader should notice (e.g. fallback engine)


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, name, passed, detail, flagged=False):
        self.checks.append(Check(name, bool(passed), detail, flagged))


_PATH_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _parse_path_points(d: str) -> list[list[tuple[float, float]]]:
    rings = []
    for chunk in d.split("Z"):
        chunk = chunk.strip()
        if not chunk:
            continue
        nums = [float(n) for n in _PATH_NUM.findall(chunk)]
        pts = list(zip(nums[0::2], nums[1::2]))
        if len(pts) >= 3:
            rings.append(pts)
    return rings


def check_reference_svg(svg_text: str, layout: Layout, rep: Report):
    """Independent re-derivation from the rendered file: one scale, correct geometry, identical parts identical."""
    job = layout.job
    m = re.search(r'data-scale-px-per-in="([^"]+)"', svg_text)
    if not m:
        rep.add("single scale constant", False, "reference SVG has no data-scale-px-per-in attribute")
        return
    k = float(m.group(1))
    sheet_head = re.compile(r'^ data-sheet="(\d+)" data-ox="([^"]+)" data-oy="([^"]+)">')
    part_re = re.compile(r'<g class="part" data-part="([^"]+)" data-copy="(\d+)" data-x="([^"]+)" data-y="([^"]+)" data-w="([^"]+)" data-h="([^"]+)" data-angle="([^"]+)" data-area="([^"]+)">\n<path d="([^"]+)"', re.S)
    tol = 1e-3 * k + 1e-4  # px tolerance from 4-decimal formatting
    n_checked = 0
    scale_ok = True
    shape_ok = True
    consistency: dict[tuple[str, float], list] = {}
    consistent = True
    worst = 0.0
    expected = {pl.key: pl for pl in layout.placements}
    seen_keys = set()
    chunks = svg_text.split('<g class="sheet"')[1:]  # one chunk per sheet group, up to the next sheet or the legend
    for chunk in chunks:
        sm = sheet_head.match(chunk)
        if not sm:
            scale_ok = False
            continue
        ox, oy = float(sm.group(2)), float(sm.group(3))
        for pm in part_re.finditer(chunk):
            pid, copy = pm.group(1), int(pm.group(2))
            x, y, w, h, ang = (float(pm.group(i)) for i in range(3, 8))
            d = pm.group(9)
            rings = _parse_path_points(d)
            if not rings:
                shape_ok = False
                continue
            allpts = [p for r in rings for p in r]
            minx = min(p[0] for p in allpts); maxx = max(p[0] for p in allpts)
            miny = min(p[1] for p in allpts); maxy = max(p[1] for p in allpts)
            # Drawn bbox must equal origin + real coordinates * k, using the ONE k from the root.
            errs = [abs(minx - (ox + x * k)), abs(miny - (oy + y * k)), abs((maxx - minx) - w * k), abs((maxy - miny) - h * k)]
            worst = max(worst, max(errs))
            if max(errs) > tol:
                scale_ok = False
            # Outline fidelity: drawn polygon area / k^2 == real area.
            drawn = Polygon(rings[0], rings[1:]) if len(rings) > 1 else Polygon(rings[0])
            real = expected.get(f"{pid}#{copy}")
            if real is None:
                shape_ok = False
            else:
                seen_keys.add(real.key)
                if abs(drawn.area / (k * k) - real.polygon.area) > 1e-3 * max(1.0, real.polygon.area):
                    shape_ok = False
            # Cross-part consistency: same part at the same angle -> identical relative path.
            rel_pts = [(px - minx, py - miny) for (px, py) in allpts]
            key = (pid, round(ang % 360, 6))
            ref = consistency.get(key)
            if ref is None:
                consistency[key] = rel_pts
            elif len(ref) != len(rel_pts) or max(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(ref, rel_pts)) > 2e-3:
                consistent = False
            n_checked += 1
    rep.add("single scale constant", scale_ok and n_checked == len(layout.placements),
            f"{n_checked} drawn parts re-measured against k = {k:g} px/in (same k for width and height); worst error {worst:.4f} px")
    rep.add("aspect ratio / outline fidelity", shape_ok and seen_keys == set(expected),
            "drawn polygon area equals real outline area / k^2 for every part" if shape_ok else "a drawn outline does not match its real geometry")
    rep.add("cross-part consistency", consistent, f"{len(consistency)} (part, angle) signatures; identical parts render identically")


def check_geometry(layout: Layout, rep: Report):
    job = layout.job
    gap = job.gap
    half = gap / 2
    m = job.outer_edge_margin
    usable = box(m, m, job.sheet_width - m, job.sheet_height - m).buffer(1e-7)

    # Boundary
    outside = [pl.key for pl in layout.placements if not usable.covers(pl.polygon)]
    rep.add("inside outer_edge_margin boundary", not outside,
            f"all {len(layout.placements)} parts within {m:g} in of no sheet edge" if not outside else f"outside: {outside[:10]}")

    # Overlaps, per sheet
    overlaps = []
    checked_pairs = 0
    for s in layout.sheets:
        pls = s.placements
        if not pls:
            continue
        if job.cutting_method == "guillotine" or all(job.part_mode(job.part_by_id(p.part_id)) == "bounding-box" for p in pls):
            geoms = [box(p.x - half, p.y - half, p.x + p.w + half, p.y + p.h + half) for p in pls]
        else:
            geoms = [_inflate(p.polygon, half) for p in pls]
        tree = STRtree(geoms)
        for i, g in enumerate(geoms):
            for j in tree.query(g):
                j = int(j)
                if j <= i:
                    continue
                checked_pairs += 1
                if g.intersection(geoms[j]).area > AREA_TOL * 10:
                    overlaps.append((pls[i].key, pls[j].key, s.label))
    mode_desc = "kerf-buffered polygon intersection" if any(job.part_mode(p) == "true-outline" for p in job.parts) and job.cutting_method != "guillotine" else "bounding-box overlap"
    rep.add("no overlaps", not overlaps,
            f"{mode_desc}, spacing {gap:g} in, {checked_pairs} candidate pairs tested" if not overlaps else f"overlapping: {overlaps[:10]}")

    # Counts
    counts = {}
    for pl in layout.placements:
        counts[pl.part_id] = counts.get(pl.part_id, 0) + 1
    bad = {p.id: (counts.get(p.id, 0), p.quantity) for p in job.parts if counts.get(p.id, 0) != p.quantity}
    rep.add("counts match requested quantities", not bad,
            ", ".join(f"{p.id}={p.quantity}" for p in job.parts) if not bad else f"mismatch (placed, requested): {bad}")

    # Area accounting
    parts_area = sum(pl.polygon.area for pl in layout.placements)
    expected_area = sum(p.true_area * p.quantity for p in job.parts)
    total = job.sheet_width * job.sheet_height * len(layout.sheets)
    waste = total - parts_area
    closes = abs(parts_area - expected_area) < 1e-6 * max(1, expected_area) and waste >= -1e-9
    rep.add("area accounting closes", closes,
            f"parts {parts_area:.3f} + waste {waste:.3f} = {total:.3f} in^2 over {len(layout.sheets)} sheet(s); utilization {100 * parts_area / total:.1f}%")

    # Sheet math
    n_sheets = len(layout.sheets)
    max_idx = max((pl.sheet for pl in layout.placements), default=-1) + 1
    empty = [s.label for s in layout.sheets if not s.placements]
    rep.add("sheet count re-derived", n_sheets == max_idx and not empty,
            f"{n_sheets} sheet(s), every sheet non-empty, highest placement index + 1 = {max_idx}")

    # Guillotine feasibility
    if job.cutting_method == "guillotine":
        ok = all(is_guillotine_cuttable([p.bbox for p in s.placements]) for s in layout.sheets)
        rep.add("guillotine cut sequence exists", ok, "every sheet separable by full edge-to-edge cuts" if ok else "a sheet is not guillotine-cuttable")

    # Grouping / deferral
    grp_ok = True
    for s in layout.sheets:
        groups = {job.part_by_id(p.part_id).group for p in s.placements}
        if s.group is not None and groups != {s.group}:
            grp_ok = False
        if s.group is None and groups & set(job.isolated_groups):
            grp_ok = False
    deferred_last = all(not a.deferred or b.deferred for a, b in zip(layout.sheets, layout.sheets[1:]))
    if job.isolated_groups:
        rep.add("group isolation and deferral", grp_ok and deferred_last,
                f"isolated: {job.isolated_groups}; deferred: {job.deferred_groups}; deferred sheets numbered last")


def check_rods(layout: Layout, rep: Report):
    job = layout.job
    if not layout.rod_result:
        return
    ok = True
    details = []
    for r in layout.rod_result["rods"]:
        n, L, kerf = r["quantity"], r["piece_length"], r["kerf"]
        expect = n * L + (n - 1) * kerf
        if abs(expect - r["continuous_length"]) > 1e-9:
            ok = False
        d = f"{r['id']}: {n} x {L:g} + {n - 1} x {kerf:g} kerf = {expect:.4f} in"
        if r.get("stock_length"):
            per_bar = int(math.floor((r["stock_length"] + kerf) / (L + kerf) + 1e-9))
            bars = int(math.ceil(n / per_bar)) if per_bar else float("inf")
            if bars != r["bars_needed"]:
                ok = False
            d += f"; {per_bar} per {r['stock_length']:g} in bar -> {bars} bars (packer: {r['bars_needed']})"
        details.append(d)
    rep.add("rod/bar stock math re-derived", ok, "; ".join(details))


def check_engine(layout: Layout, rep: Report):
    used = "; ".join(f"{m}: {e}" for m, e in layout.engines_used.items()) or "none (rods only)"
    if layout.fallbacks:
        rep.add("nesting engine", True, f"{used}. FALLBACK: " + " | ".join(layout.fallbacks), flagged=True)
    else:
        rep.add("nesting engine", True, used)


def check_determinism(layout: Layout, rep: Report):
    job = layout.job
    again = build_layout(job)
    a = [(p.key, p.sheet, round(p.x, 6), round(p.y, 6), round(p.angle, 6)) for p in layout.placements]
    b = [(p.key, p.sheet, round(p.x, 6), round(p.y, 6), round(p.angle, 6)) for p in again.placements]
    rep.add("deterministic", sorted(a) == sorted(b), "re-running the same job reproduced every placement")


def verify(layout: Layout, reference_svg: Optional[str] = None, determinism: bool = True) -> Report:
    rep = Report()
    if reference_svg is not None:
        check_reference_svg(reference_svg, layout, rep)
    if layout.placements:
        check_geometry(layout, rep)
    check_rods(layout, rep)
    check_engine(layout, rep)
    if determinism and layout.placements:
        check_determinism(layout, rep)
    return rep


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
