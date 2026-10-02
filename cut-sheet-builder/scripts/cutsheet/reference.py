"""
file: reference.py
version: 1.0
author: Sam Cao
created: 2026-10-02
last_updated: 2026-10-02
description: Assigns parts that asked for a known-straight reference edge or corner to the factory edges of a sheet, flush to the stock edge, per material_model PRD v1.2.1 section 7.3.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shapely import affinity

from . import edges
from .model import Part, rotated_normalized, transform_like

TOL = 1e-6

# Corners, as the two sides that meet there, in a fixed order so assignment is deterministic.
CORNERS = (("left", "top"), ("top", "right"), ("right", "bottom"), ("bottom", "left"))


@dataclass
class Assignment:
    """One reference part, placed flush to the stock edge(s) it was given."""
    inst: object          # layout.Instance
    angle: float
    x: float              # sheet coordinates, bbox top-left
    y: float
    w: float
    h: float
    sides: tuple          # stock sides this placement sits against
    corner: bool


def edge_side_at_angle(part: Part, edge_name: str, angle: float) -> Optional[str]:
    """Which side of the part's bounding box the named edge lies on, once rotated.

    Worked out from the geometry rather than from rotation-sign reasoning: the edge is put
    through the exact transform the part gets, then compared against the rotated bounding box.
    An edge that is interior to the bbox at this angle (an L-bracket's inner edge, say) returns
    None, which is how a request that cannot sit flush gets rejected."""
    seg = edges.part_edges(part).get(str(edge_name).strip().lower())
    if seg is None:
        return None
    moved = transform_like(seg, part.base_polygon(), angle, 0.0, 0.0)
    _, _, pw, ph = rotated_normalized(part.base_polygon(), angle).bounds
    sx0, sy0, sx1, sy1 = moved.bounds
    if abs(sx0) < TOL and abs(sx1) < TOL:
        return "left"
    if abs(sx0 - pw) < TOL and abs(sx1 - pw) < TOL:
        return "right"
    if abs(sy0) < TOL and abs(sy1) < TOL:
        return "top"
    if abs(sy0 - ph) < TOL and abs(sy1 - ph) < TOL:
        return "bottom"
    return None


def _anchor(side: str, along: float, pw: float, ph: float, sheet_w: float, sheet_h: float,
            fm: float) -> tuple[float, float]:
    """Top-left of a part sitting flush against <side>, <along> units down or across the sheet."""
    if side == "left":
        return fm, along
    if side == "right":
        return sheet_w - pw - fm, along
    if side == "top":
        return along, fm
    return along, sheet_h - ph - fm   # bottom


def _free_positions(taken: list, side: str, sheet_w: float, sheet_h: float, gap: float) -> list[float]:
    """Candidate offsets along a side: the start, plus just past everything already placed."""
    axis_end = sheet_h if side in ("left", "right") else sheet_w
    out = [0.0]
    for (x, y, w, h) in taken:
        out.append((y + h + gap) if side in ("left", "right") else (x + w + gap))
    return sorted({round(v, 9) for v in out if -TOL <= v < axis_end})


def _overlaps(cand: tuple, taken: list, gap: float) -> bool:
    cx, cy, cw, ch = cand
    for (x, y, w, h) in taken:
        if (cx < x + w + gap - TOL and x < cx + cw + gap - TOL and
                cy < y + h + gap - TOL and y < cy + ch + gap - TOL):
            return True
    return False


def _order(insts: list) -> list:
    """Corners first, since a sheet has only four and they are the scarcer resource; then the
    biggest parts, which are hardest to re-home; then by id and copy so a rerun matches."""
    return sorted(insts, key=lambda i: (not i.part.reference.corner,
                                        -i.part.bbox_area, i.part.id, i.index))


def plan_sheet(job, stock, insts: list, gap: float) -> tuple[list[Assignment], list]:
    """Give as many of <insts> a factory edge on this sheet as will fit. Returns the
    assignments and the instances that did not get one."""
    factory = job.stock_factory_edges(stock)
    if not factory:
        return [], list(insts)
    fm = job.factory_edge_margin
    sheet_w, sheet_h = stock.width, stock.height
    stock_grain = job.stock_grain(stock)

    taken: list[tuple] = []          # (x, y, w, h) already committed on this sheet
    corners_left = [c for c in CORNERS if c[0] in factory and c[1] in factory]
    assigned: list[Assignment] = []
    leftover: list = []

    for inst in _order(insts):
        part = inst.part
        ref = part.reference
        want = ref.edges
        hit = None

        for angle in part.allowed_angles(job.rotation_step, job.part_mode(part), stock_grain):
            sides = [edge_side_at_angle(part, n, angle) for n in want]
            if any(sd is None for sd in sides):
                continue                      # these edges cannot lie flat at this angle
            if len(set(sides)) != len(sides):
                continue                      # two requested edges mapped to the same side
            _, _, pw, ph = rotated_normalized(part.base_polygon(), angle).bounds
            if pw > sheet_w - 2 * fm + TOL or ph > sheet_h - 2 * fm + TOL:
                continue

            if ref.corner:
                for corner in corners_left:
                    if set(sides) != set(corner):
                        continue
                    sx, sy = _corner_anchor(corner, pw, ph, sheet_w, sheet_h, fm)
                    if not _overlaps((sx, sy, pw, ph), taken, gap):
                        hit = Assignment(inst, angle, sx, sy, pw, ph, tuple(corner), True)
                        corners_left.remove(corner)
                        break
            else:
                side = sides[0]
                if side not in factory:
                    continue
                for along in _free_positions(taken, side, sheet_w, sheet_h, gap):
                    sx, sy = _anchor(side, along, pw, ph, sheet_w, sheet_h, fm)
                    if sx < -TOL or sy < -TOL or sx + pw > sheet_w + TOL or sy + ph > sheet_h + TOL:
                        continue
                    if not _overlaps((sx, sy, pw, ph), taken, gap):
                        hit = Assignment(inst, angle, sx, sy, pw, ph, (side,), False)
                        break
            if hit:
                break

        if hit:
            taken.append((hit.x, hit.y, hit.w, hit.h))
            assigned.append(hit)
        else:
            leftover.append(inst)
    return assigned, leftover


def _corner_anchor(corner: tuple, pw: float, ph: float, sheet_w: float, sheet_h: float,
                   fm: float) -> tuple[float, float]:
    sides = set(corner)
    x = fm if "left" in sides else sheet_w - pw - fm
    y = fm if "top" in sides else sheet_h - ph - fm
    return x, y


def would_fit_on_one_more_sheet(job, stock, insts: list, gap: float) -> int:
    """How many of the leftovers a fresh sheet of this stock could take. Drives the
    recommendation under the use-available policy, which never opens a sheet by itself."""
    if not insts:
        return 0
    got, _ = plan_sheet(job, stock, insts, gap)
    return len(got)


# CHANGELOG
# v1.0 (2026-10-02): Initial release.
