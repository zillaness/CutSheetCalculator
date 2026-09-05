"""
file: labels.py
version: 1.0
author: Sam Cao
created: 2026-09-05
last_updated: 2026-09-05
description: Piece labeling. Decides each placed part's label text, font, and size from the job and machine, places it on the piece or beside the cutout in the waste with geometric checks, applies the documented fallback chain, and records every downgrade or drop with its reason.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from shapely import affinity
from shapely.geometry import Polygon, box
from shapely.prepared import prep

from .fonts import layout_text, TextLayout
from .model import Job, Part, LABEL_MODES

EPS = 1e-9


@dataclass
class Label:
    mode: str                 # on-piece | beside-cutout
    text: str
    font: str
    cap_height: float         # inches, effective
    angle: float              # degrees applied to the text box (0 = reads left to right along +x)
    x: float                  # text box min corner on the sheet (inches, y down)
    y: float
    w: float
    h: float
    geoms: list               # shapely geometries in sheet coordinates
    box: Polygon              # text box polygon in sheet coordinates (rotated)
    render_only: bool = False  # hand machine: reference/PDF only, never in cut files
    shrunk: bool = False       # cap height was reduced from the requested size to fit


@dataclass
class LabelEvent:
    key: str
    sheet: int
    requested: str
    result: str               # on-piece | beside-cutout | dropped
    reason: str


@dataclass
class LabelReport:
    enabled: bool = False
    machine: Optional[str] = None
    font: Optional[str] = None
    requested_height: float = 0.0
    min_height: float = 0.0
    effective_height: float = 0.0
    basis: str = ""
    spacing_bump: Optional[tuple] = None   # (configured_gap, effective_gap)
    counts: dict = field(default_factory=dict)  # outcome -> count
    events: list = field(default_factory=list)  # downgrades and drops
    substitutions: list = field(default_factory=list)  # (key, original, laid out)
    render_only: bool = False

    @property
    def flagged(self) -> bool:
        return bool(self.events or self.substitutions or self.spacing_bump)


def _place_layout(lay: TextLayout, angle: float, cx: float, cy: float):
    """Rotate the text about its box center and move that center to (cx, cy). Returns (geoms, box, w, h)."""
    bx0, by0, bx1, by1 = lay.bbox
    ox, oy = (bx0 + bx1) / 2, (by0 + by1) / 2
    b = box(bx0, by0, bx1, by1)
    def tf(g):
        g = affinity.rotate(g, angle, origin=(ox, oy)) if angle % 360 else g
        return affinity.translate(g, cx - ox, cy - oy)
    bb = tf(b)
    minx, miny, maxx, maxy = bb.bounds
    return [tf(g) for g in lay.geoms], bb, maxx - minx, maxy - miny


def _mode_for(job: Job, part: Part) -> str:
    return part.label_mode or job.labels.mode


def _text_for(job: Job, pl, part: Part) -> str:
    if part.label_text:
        return part.label_text
    if job.labels.text == "id+copy":
        return f"{pl.part_id}#{pl.index}"
    return pl.part_id


def place_labels(job: Job, layout) -> LabelReport:
    rep = LabelReport()
    L = job.labels
    modes_in_use = {_mode_for(job, p) for p in job.parts}
    if L.mode == "none" and modes_in_use <= {"none"}:
        return rep
    rep.enabled = True
    rep.machine = job.machine
    rep.font = job.label_font
    rep.min_height, rep.basis = job.label_min_height()
    rep.requested_height = job.label_cap_height()
    rep.effective_height = max(rep.requested_height, rep.min_height)
    rep.spacing_bump = job.spacing_bump
    rep.render_only = job.machine == "hand"
    m = job.outer_edge_margin
    inset = L.on_piece_inset if L.on_piece_inset is not None else job.default_on_piece_inset()
    pad = L.clearance_pad

    for sheet in layout.sheets:
        usable = box(m, m, sheet.width - m, sheet.height - m)
        usable_p = prep(usable)
        # Clearance rule (one rule, shared with verify.check_labels): a label box grown by pad + kerf/2 must
        # miss every raw outline (the cut eats kerf/2 into the waste), and label boxes must not overlap.
        outlines = [pl.polygon for pl in sheet.placements]
        placed_boxes: list[Polygon] = []
        grow = pad + job.kerf / 2.0 - 1e-6

        def clear_of_parts(bb: Polygon, skip_index: int) -> bool:
            q = bb.buffer(grow) if grow > 0 else bb
            for poly in outlines:
                if q.intersects(poly) and q.intersection(poly).area > 1e-9:
                    return False
            for other in placed_boxes:
                if bb.intersects(other) and bb.intersection(other).area > 1e-9:
                    return False
            return usable_p.covers(bb)

        for idx, pl in enumerate(sheet.placements):
            part = job.part_by_id(pl.part_id)
            mode = _mode_for(job, part)
            if mode == "none":
                pl.label = None
                pl.label_reason = "mode none"
                rep.counts["none"] = rep.counts.get("none", 0) + 1
                continue
            text = _text_for(job, pl, part)
            requested = mode
            if rep.render_only:
                mode = "on-piece"
            chain = [mode]
            if L.fallback != "drop":
                chain.append("beside-cutout" if mode == "on-piece" else "on-piece")
            if rep.render_only:
                chain = ["on-piece"]
            result = None
            reasons = []
            for attempt in chain:
                if attempt == "on-piece":
                    result, why = _try_on_piece(job, pl, text, rep.effective_height, rep.min_height, inset, usable_p, sheet)
                else:
                    result, why = _try_beside(job, pl, text, rep.effective_height, pad, clear_of_parts, idx)
                if result is not None:
                    break
                reasons.append(f"{attempt}: {why}")
            if result is None:
                pl.label = None
                pl.label_reason = "; ".join(reasons)
                rep.counts["dropped"] = rep.counts.get("dropped", 0) + 1
                rep.events.append(LabelEvent(pl.key, sheet.index, requested, "dropped", pl.label_reason))
                continue
            result.render_only = rep.render_only
            pl.label = result
            pl.label_reason = ""
            if result.mode != requested and not rep.render_only:
                rep.counts["downgraded"] = rep.counts.get("downgraded", 0) + 1
                rep.events.append(LabelEvent(pl.key, sheet.index, requested, result.mode, "; ".join(reasons)))
            rep.counts[result.mode] = rep.counts.get(result.mode, 0) + 1
            if result.mode == "beside-cutout":
                placed_boxes.append(result.box)
            lay = layout_text(text, 1.0, rep.font)
            if lay.substituted:
                rep.substitutions.append((pl.key, text, lay.text))
    return rep


def _try_on_piece(job: Job, pl, text: str, cap: float, min_cap: float, inset: float, usable_p, sheet):
    poly = pl.polygon
    shrunk_poly = poly.buffer(-inset) if inset > 0 else poly
    if shrunk_poly.is_empty:
        return None, f"part too small for a {inset:.3f} in inset"
    anchor = poly.centroid
    if not poly.contains(anchor):
        anchor = poly.representative_point()
    angles = [pl.angle % 360] if job.labels.orientation == "follow-part" else [0.0, 90.0]
    h = cap
    tried = 0
    while h >= min_cap - EPS:
        lay = layout_text(text, h, job.label_font)
        for a in angles:
            geoms, bb, w, hh = _place_layout(lay, a, anchor.x, anchor.y)
            if shrunk_poly.covers(bb) and usable_p.covers(bb):
                minx, miny, _, _ = bb.bounds
                return Label("on-piece", lay.text, job.label_font, h, a, minx, miny, w, hh, geoms, bb, shrunk=(h < cap - EPS)), ""
        tried += 1
        h = h * 0.9
        if h < min_cap - EPS and tried:
            break
    return None, f"text does not fit inside the outline at the minimum height {min_cap:.3f} in with a {inset:.3f} in inset"


def _try_beside(job: Job, pl, text: str, cap: float, pad: float, clear_of_parts, idx: int):
    lay = layout_text(text, cap, job.label_font)
    tw, th = lay.width, lay.height
    x0, y0, x1, y1 = pl.bbox
    off = pad + job.kerf / 2.0 + th / 2  # box center sits pad + kerf/2 beyond the bounding box edge
    # candidate (angle, center) in order: below, right, above, left of the bounding box
    cands = [
        (0.0, ((x0 + x1) / 2, y1 + off)),
        (90.0, (x1 + off, (y0 + y1) / 2)),
        (0.0, ((x0 + x1) / 2, y0 - off)),
        (90.0, (x0 - off, (y0 + y1) / 2)),
    ]
    for a, (cx, cy) in cands:
        geoms, bb, w, h = _place_layout(lay, a, cx, cy)
        if clear_of_parts(bb, idx):
            minx, miny, _, _ = bb.bounds
            return Label("beside-cutout", lay.text, job.label_font, cap, a, minx, miny, w, h, geoms, bb), ""
    return None, f"no clear waste strip of {th + 2 * pad + job.kerf:.3f} in (text {th:.3f} + 2 x pad {pad:.3f} + kerf) around the part (gap {job.gap:.3f} in)"


# CHANGELOG
# v1.0 (2026-09-05): Initial release.
