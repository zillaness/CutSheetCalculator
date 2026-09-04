"""
file: layout.py
version: 1.3
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Placement and sheet records shared by every packing engine, plus the sheet-level orchestration (group isolation, deferral, engine selection).
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import Polygon
from shapely import affinity

from .model import Job, Part, rotated_normalized, transform_like


@dataclass
class Instance:
    """One physical copy of a part, before placement."""
    part: Part
    index: int  # 1-based copy number

    @property
    def key(self) -> str:
        return f"{self.part.id}#{self.index}"


@dataclass
class Placement:
    part_id: str
    index: int
    sheet: int  # 0-based sheet index within the job
    x: float  # bbox min corner on the sheet, inches, y-down
    y: float
    angle: float  # degrees applied to the base outline
    w: float  # placed bbox size
    h: float
    polygon: Polygon  # placed outline in sheet coordinates
    engrave: list = field(default_factory=list)  # placed engrave geometries in sheet coordinates

    @property
    def key(self) -> str:
        return f"{self.part_id}#{self.index}"

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)


@dataclass
class Sheet:
    index: int
    group: Optional[str] = None
    deferred: bool = False
    placements: list[Placement] = field(default_factory=list)
    engine: str = ""
    width: float = 0.0   # this sheet's stock size (inches)
    height: float = 0.0
    stock: str = ""      # stock label (preset name or WxH)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def label(self) -> str:
        return f"Sheet {self.index + 1}"


@dataclass
class Layout:
    job: Job
    sheets: list[Sheet]
    engines_used: dict = field(default_factory=dict)  # mode -> engine name
    fallbacks: list[str] = field(default_factory=list)  # human-readable fallback notes
    rod_result: Optional[dict] = None

    @property
    def placements(self) -> list[Placement]:
        return [p for s in self.sheets for p in s.placements]


def placed_polygon(part: Part, x: float, y: float, angle: float) -> Polygon:
    poly = rotated_normalized(part.base_polygon(), angle)
    return affinity.translate(poly, x, y)


def placed_engrave(part: Part, x: float, y: float, angle: float) -> list:
    return [transform_like(g, part.base_polygon(), angle, x, y) for g in part.engrave_geoms]


def attach_engrave(job: Job, placements: list) -> None:
    """Fill Placement.engrave for every placement (engines only compute outlines)."""
    for pl in placements:
        part = job.part_by_id(pl.part_id)
        if part.engrave_geoms:
            pl.engrave = placed_engrave(part, pl.x, pl.y, pl.angle)


def expand_instances(parts: list[Part]) -> list[Instance]:
    """Deterministic ordering: larger bbox area first, then id, then copy number."""
    inst = [Instance(p, i + 1) for p in parts for i in range(p.quantity)]
    inst.sort(key=lambda it: (-it.part.bbox_area, it.part.id, it.index))
    return inst




# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_layout(job: Job) -> Layout:
    """Pack every part, honoring group isolation and deferral, then number the sheets."""
    from .pack_rect import pack_rectangles
    from .pack_poly import nest_outlines
    from .pack_1d import pack_rods

    layout = Layout(job=job, sheets=[])

    # Partition parts: each isolated group alone; everything else together.
    buckets: list[tuple[Optional[str], list[Part]]] = []
    rest = [p for p in job.parts if p.group not in job.isolated_groups]
    if rest:
        buckets.append((None, rest))
    for g in job.isolated_groups:
        members = [p for p in job.parts if p.group == g]
        if members:
            buckets.append((g, members))
    # Non-deferred buckets first so deferred sheets come last.
    buckets.sort(key=lambda b: (b[0] in job.deferred_groups, b[0] or ""))

    sheet_offset = 0
    stock_left = [st.quantity for st in job.stocks]  # None = unlimited; shared across groups
    for group, parts in buckets:
        # Mode is a job-level choice; a per-part override to bounding-box is honored inside the same run
        # by giving that part its bbox as the outline. Guillotine cutting always packs bounding boxes.
        modes = {job.part_mode(p) for p in parts}
        use_outline = ("true-outline" in modes) and job.cutting_method != "guillotine"
        all_rects = all(p.is_rectangle for p in parts)
        if use_outline and all_rects:
            # A rectangle's outline is its bounding box, and the MaxRects packer beats the greedy
            # outline nester at boxes, so route all-rectangle jobs there; the result is identical geometry.
            use_outline = False
        run_parts = parts
        if use_outline and "bounding-box" in modes:
            run_parts = []
            for p in parts:
                if job.part_mode(p) == "bounding-box" and p.outline is not None:
                    q = Part(**{**p.__dict__, "outline": None})
                    run_parts.append(q)
                else:
                    run_parts.append(p)
        remaining = expand_instances(run_parts)
        used = ""
        # Walk the stock list in order: fill the first stock's sheets (up to its quantity), then the next.
        for si_stock, stock in enumerate(job.stocks):
            if not remaining:
                break
            cap = stock_left[si_stock]
            if cap is not None and cap <= 0:
                continue
            if use_outline:
                engine = job.engine_2d if job.engine_2d in ("auto", "nest2d", "shapely") else "auto"
                placements, used, fb, remaining = nest_outlines(job, remaining, engine, stock.width, stock.height, cap)
                layout.engines_used["true-outline"] = used
            else:
                engine = job.engine_2d if job.engine_2d in ("auto", "rectpack", "bundled") else "auto"
                placements, used, fb, remaining = pack_rectangles(job, remaining, engine, stock.width, stock.height, cap)
                if "true-outline" in modes and all_rects and job.cutting_method != "guillotine":
                    used += " (all parts are rectangles, so true-outline mode used the rectangle packer)"
                layout.engines_used["bounding-box"] = used
                if job.cutting_method == "guillotine" and "true-outline" in modes:
                    note = "guillotine cutting packs bounding boxes; true outlines are still rendered inside them"
                    if note not in layout.fallbacks:
                        layout.fallbacks.append(note)
            if fb and fb not in layout.fallbacks:
                layout.fallbacks.append(fb)
            attach_engrave(job, placements)
            n_sheets = max((pl.sheet for pl in placements), default=-1) + 1
            if cap is not None:
                stock_left[si_stock] = cap - n_sheets
            sheets = [Sheet(index=sheet_offset + i, group=group, deferred=(group in job.deferred_groups), engine=used,
                            width=stock.width, height=stock.height, stock=stock.label)
                      for i in range(n_sheets)]
            for pl in placements:
                pl.sheet = sheet_offset + pl.sheet
                sheets[pl.sheet - sheet_offset].placements.append(pl)
            for sh in sheets:
                sh.placements.sort(key=lambda p: (p.y, p.x, p.part_id, p.index))
            layout.sheets.extend(sheets)
            sheet_offset += n_sheets
        if remaining:
            raise ValueError(
                "ran out of sheet stock: " + ", ".join(sorted({i.part.id for i in remaining})) +
                f" ({len(remaining)} piece(s)) could not be placed. Add quantity to a stock entry or add an unlimited last entry.")

    if job.rods:
        layout.rod_result = pack_rods(job.rods, job.kerf)
    return layout


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
# v1.1 (2026-09-04): Placements carry placed engrave geometry.
# v1.2 (2026-09-04): All-rectangle jobs use the rectangle packer even in true-outline mode.
# v1.3 (2026-09-04): Stock list loop; sheets carry their own size and stock label.
