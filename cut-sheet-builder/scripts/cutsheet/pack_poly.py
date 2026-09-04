"""
file: pack_poly.py
version: 1.2
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: True-outline nesting. Tries the nest2D (libnest2d) bindings first; otherwise runs a bundled shapely greedy placer with a stepped rotation search, bottom-left gravity sliding, and kerf-buffered overlap checks.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

import math
from typing import Optional

from shapely.geometry import Polygon, box
from shapely.prepared import prep
from shapely import affinity
from shapely.strtree import STRtree

from .layout import Instance, Placement
from .model import (FREE_REFINE_SPAN, FREE_REFINE_STEP, FREE_ROTATION, FREE_COARSE_STEP,
                    Job, rotated_normalized)

EPS = 1e-9
AREA_TOL = 1e-7  # in^2; intersections smaller than this count as touching, not overlapping
SLIDE_TOP_N = 6  # how many best-scoring candidate anchors get the gravity slide before choosing (measured: 6 beats 1 and 3)


def _inflate(poly: Polygon, half_gap: float) -> Polygon:
    if half_gap <= 0:
        return poly
    # Mitre joins are conservative (never smaller than the true offset), capped to stop spikes.
    return poly.buffer(half_gap, join_style="mitre", mitre_limit=4.0)


class _SheetState:
    def __init__(self, usable: Polygon):
        self.usable = usable
        self.usable_prepared = prep(usable)
        self.placed: list[Polygon] = []  # inflated polygons
        self.bboxes: list[tuple[float, float, float, float]] = []
        self.tree: Optional[STRtree] = None
        self.dirty = False

    def add(self, infl: Polygon):
        self.placed.append(infl)
        self.bboxes.append(infl.bounds)
        self.dirty = True

    def _tree(self):
        if self.dirty or self.tree is None:
            self.tree = STRtree(self.placed) if self.placed else None
            self.dirty = False
        return self.tree

    def collides(self, infl: Polygon) -> bool:
        tree = self._tree()
        if tree is None:
            return False
        for i in tree.query(infl):
            other = self.placed[int(i)]
            if infl.intersection(other).area > AREA_TOL:
                return True
        return False


def _valid(state: _SheetState, poly: Polygon, infl: Polygon) -> bool:
    if not state.usable_prepared.contains(poly) and not state.usable_prepared.covers(poly):
        return False
    return not state.collides(infl)


def _slide(state: _SheetState, base: Polygon, base_infl: Polygon, x: float, y: float, usable_bounds) -> tuple[float, float]:
    """Gravity toward the top-left (y-down coordinates): slide up, then left, repeat until stuck."""
    minx, miny, _, _ = usable_bounds

    def ok(px, py):
        p = affinity.translate(base, px, py)
        q = affinity.translate(base_infl, px, py)
        return _valid(state, p, q)

    moved = True
    iters = 0
    while moved and iters < 6:
        moved = False
        iters += 1
        # up (decreasing y)
        lo, hi = 0.0, y - miny
        if hi > EPS and ok(x, y - hi):
            y = y - hi
            moved = True
        elif hi > EPS:
            for _ in range(14):
                mid = (lo + hi) / 2
                if ok(x, y - mid):
                    lo = mid
                else:
                    hi = mid
            if lo > 1e-4:
                y = y - lo
                moved = True
        # left (decreasing x)
        lo, hi = 0.0, x - minx
        if hi > EPS and ok(x - hi, y):
            x = x - hi
            moved = True
        elif hi > EPS:
            for _ in range(14):
                mid = (lo + hi) / 2
                if ok(x - mid, y):
                    lo = mid
                else:
                    hi = mid
            if lo > 1e-4:
                x = x - lo
                moved = True
    return x, y


def _frange(lo: float, hi: float, step: float):
    n = int(round((hi - lo) / step))
    return [lo + i * step for i in range(n + 1)]


def _nest_shapely(job: Job, instances: list[Instance]) -> list[Placement]:
    gap = job.gap
    half = gap / 2.0
    m = job.outer_edge_margin
    usable = box(m, m, job.sheet_width - m, job.sheet_height - m)
    ub = usable.bounds
    sheets: list[_SheetState] = []
    placements: list[Placement] = []

    # Cache rotated base outlines per (part, angle).
    cache: dict[tuple[str, float], tuple[Polygon, Polygon]] = {}

    def variant(inst: Instance, a: float):
        a = round(a % 360, 6)
        key = (inst.part.id, a)
        if key not in cache:
            base = rotated_normalized(inst.part.base_polygon(), a)
            cache[key] = (base, _inflate(base, half))
        base, infl = cache[key]
        _, _, w, h = base.bounds
        if w <= job.usable_width + EPS and h <= job.usable_height + EPS:
            return (a, base, infl, w, h, infl.bounds)
        return None

    def variants(inst: Instance, angles=None):
        out = []
        for a in (angles if angles is not None else inst.part.allowed_angles(job.rotation_step, "true-outline")):
            v = variant(inst, a)
            if v is not None:
                out.append(v)
        return out

    def try_place(st, vars_, cands, top_n: int = 1):
        """Best (score, angle, base, infl, w, h, cx, cy) over variants x candidate anchors, or None.
        With top_n > 1 the best few anchors are each slid first and the best post-slide result wins."""
        found = []
        for (a, base, infl, w, h, ib) in vars_:
            for (cx, cy) in cands:
                cx = max(cx, ub[0])
                cy = max(cy, ub[1])
                if cx + w > ub[2] + EPS or cy + h > ub[3] + EPS:
                    continue
                # cheap bbox reject against placed inflated bboxes, using the buffered outline's real
                # bounds (a mitre buffer reaches farther than gap/2 at a sharp tip)
                ix0, iy0 = cx + ib[0], cy + ib[1]
                ix1, iy1 = cx + ib[2], cy + ib[3]
                hit = False
                for (bx0, by0, bx1, by1) in st.bboxes:
                    if ix0 < bx1 - 1e-7 and ix1 > bx0 + 1e-7 and iy0 < by1 - 1e-7 and iy1 > by0 + 1e-7:
                        hit = True
                        break
                if hit:
                    # bboxes overlap; a true-outline check may still pass (nesting into a notch)
                    p = affinity.translate(base, cx, cy)
                    q = affinity.translate(infl, cx, cy)
                    if not _valid(st, p, q):
                        continue
                score = (cy + h, cx + w, a)
                found.append((score, a, base, infl, w, h, cx, cy))
        if not found:
            return None
        found.sort(key=lambda t: t[0])
        if top_n <= 1:
            return found[0]
        best = None
        for (_, a, base, infl, w, h, cx, cy) in found[:top_n]:
            sx, sy = _slide(st, base, infl, cx, cy, ub)
            sc = (sy + h, sx + w, a)
            if best is None or sc < best[0]:
                best = (sc, a, base, infl, w, h, sx, sy)
        return best

    for inst in instances:
        vars_ = variants(inst)
        if not vars_:
            raise ValueError(f"part {inst.part.id} does not fit the usable sheet in any allowed orientation")
        placed_ok = False
        for si in range(len(sheets) + 1):
            if si == len(sheets):
                sheets.append(_SheetState(usable))
            st = sheets[si]
            # Candidate anchor points: sheet corner plus corners derived from placed bboxes.
            cands = {(ub[0], ub[1])}
            for (bx0, by0, bx1, by1) in st.bboxes:
                cands.add((bx1 + half, by0 - half))
                cands.add((bx0 - half, by1 + half))
                cands.add((bx1 + half, ub[1]))
                cands.add((ub[0], by1 + half))
            best = try_place(st, vars_, cands, SLIDE_TOP_N)
            if best is None:
                continue
            _, a, base, infl, w, h, cx, cy = best
            cx, cy = _slide(st, base, infl, cx, cy, ub)  # no-op when already slid; cheap
            if inst.part.free_rotation(job.rotation_step):
                # Free mode: refine the angle around the best coarse hit, re-sliding each candidate,
                # and keep whichever lands highest/leftmost after the slide.
                best_score = (cy + h, cx + w)
                fine = [a + d for d in _frange(-FREE_REFINE_SPAN, FREE_REFINE_SPAN, FREE_REFINE_STEP) if abs(d) > 1e-9]
                anchors = {(cx, cy)} | set(cands)
                for cand in variants(inst, fine):
                    hit = try_place(st, [cand], anchors)
                    if hit is None:
                        continue
                    _, a2, base2, infl2, w2, h2, cx2, cy2 = hit
                    cx2, cy2 = _slide(st, base2, infl2, cx2, cy2, ub)
                    sc = (cy2 + h2, cx2 + w2)
                    if sc < best_score:
                        best_score = sc
                        a, base, infl, w, h, cx, cy = a2, base2, infl2, w2, h2, cx2, cy2
            poly = affinity.translate(base, cx, cy)
            st.add(affinity.translate(infl, cx, cy))
            placements.append(Placement(inst.part.id, inst.index, si, cx, cy, a, w, h, poly))
            placed_ok = True
            break
        if not placed_ok:
            raise ValueError(f"could not place part {inst.part.id} on any sheet")
    return placements


def _nest_nest2d(job: Job, instances: list[Instance]) -> list[Placement]:
    """libnest2d via the pynest2d bindings. Coordinates are integers, so work in 1/10000 in."""
    import pynest2d as n2d  # noqa

    S = 10000
    gap = job.gap
    m = job.outer_edge_margin
    items = []
    metas = []
    for inst in instances:
        base = rotated_normalized(inst.part.base_polygon(), inst.part.locked_angle if inst.part.rotation == "locked" else 0.0)
        pts = [n2d.Point(int(round(x * S)), int(round(-y * S))) for (x, y) in base.exterior.coords[:-1]]
        item = n2d.Item(pts)
        items.append(item)
        metas.append((inst, base))
    bin_ = n2d.Box(int(round(job.usable_width * S)), int(round(job.usable_height * S)))
    cfg = n2d.NfpConfig()
    cfg.alignment = n2d.NfpConfig.Alignment.BOTTOM_LEFT
    cfg.starting_point = n2d.NfpConfig.Alignment.BOTTOM_LEFT
    if all(i.part.rotation == "locked" for i in instances):
        cfg.rotations = [0.0]
    else:
        # libnest2d takes one rotation list for the whole job: the finest step any part asked for.
        steps = [i.part.effective_step(job.rotation_step) for i in instances if i.part.rotation == "auto"]
        deg = 5.0 if any(st == FREE_ROTATION for st in steps) else min(float(st) for st in steps)
        step = math.radians(deg)
        cfg.rotations = [k * step for k in range(int(round(2 * math.pi / step)))]
    n2d.nest(items, bin_, int(round(gap * S)), cfg)
    placements = []
    for item, (inst, base) in zip(items, metas):
        b = item.binId()
        if b < 0:
            raise RuntimeError(f"nest2d failed to place {inst.key}")
        rot = math.degrees(item.rotation())
        tr = item.translation()
        # Reconstruct the placed polygon from nest2d's transformed vertices to avoid sign conventions.
        n = item.vertexCount()
        pts = [(item.vertex(i).x() / S, -item.vertex(i).y() / S) for i in range(n)]
        poly = Polygon(pts)
        minx, miny, maxx, maxy = poly.bounds
        # Shift from bin coordinates (bin centered at origin) to sheet coordinates.
        dx = m + job.usable_width / 2
        dy = m + job.usable_height / 2
        poly = affinity.translate(poly, dx, dy)
        minx, miny, maxx, maxy = poly.bounds
        angle = (inst.part.locked_angle if inst.part.rotation == "locked" else 0.0) - rot
        placements.append(Placement(inst.part.id, inst.index, b, minx, miny, angle % 360, maxx - minx, maxy - miny, poly))
    return placements


def nest_outlines(job: Job, instances: list[Instance], engine: str = "auto") -> tuple[list[Placement], str, Optional[str]]:
    fallback = None
    if engine in ("auto", "nest2d"):
        try:
            pl = _nest_nest2d(job, instances)
            return pl, "nest2d (libnest2d no-fit-polygon)", None
        except ImportError:
            if engine == "nest2d":
                raise
            fallback = "nest2d/libnest2d is not importable in this runtime; used the bundled shapely greedy nester (lower packing density than nest2d or Deepnest)"
        except Exception as ex:
            if engine == "nest2d":
                raise
            fallback = f"nest2d failed ({ex}); used the bundled shapely greedy nester (lower packing density)"
    pl = _nest_shapely(job, instances)
    label = "free (15 deg grid + 1 deg refine)" if job.rotation_step == FREE_ROTATION else f"{float(job.rotation_step):g} deg"
    if any(i.part.rotation_step is not None for i in instances):
        label += ", per-part overrides"
    return pl, f"bundled shapely greedy (bottom-left, rotation {label})", fallback


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
# v1.1 (2026-09-04): Free-rotation refinement pass and per-part rotation steps.
# v1.2 (2026-09-04): Slide the top 6 candidate anchors before choosing (denser packing).
