"""
file: pack_rect.py
version: 1.1
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Bounding-box packing. Bundled deterministic MaxRects (free cutting) and guillotine packers with per-item rotation control, plus an optional rectpack wrapper used when that library is importable.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .layout import Instance, Placement, placed_polygon
from .model import Job, rotated_normalized

EPS = 1e-9


@dataclass
class Item:
    inst: Instance
    options: list[tuple[float, float, float]]  # (w, h, angle) already inflated by gap


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self):
        return self.x + self.w

    @property
    def y2(self):
        return self.y + self.h


def _fits(fr: Rect, w: float, h: float) -> bool:
    return w <= fr.w + EPS and h <= fr.h + EPS


# ---------------------------------------------------------------------------
# MaxRects (best short side fit), multiple bins, deterministic
# ---------------------------------------------------------------------------

class MaxRectsBin:
    def __init__(self, w: float, h: float):
        self.w, self.h = w, h
        self.free: list[Rect] = [Rect(0, 0, w, h)]
        self.used: list[Rect] = []

    def best(self, options):
        best = None
        for (w, h, a) in options:
            for fr in self.free:
                if _fits(fr, w, h):
                    short = min(fr.w - w, fr.h - h)
                    long_ = max(fr.w - w, fr.h - h)
                    score = (short, long_, fr.y, fr.x)
                    if best is None or score < best[0]:
                        best = (score, Rect(fr.x, fr.y, w, h), a)
        return best

    def place(self, r: Rect):
        new_free = []
        for fr in self.free:
            if r.x >= fr.x2 - EPS or r.x2 <= fr.x + EPS or r.y >= fr.y2 - EPS or r.y2 <= fr.y + EPS:
                new_free.append(fr)
                continue
            if r.x > fr.x + EPS:
                new_free.append(Rect(fr.x, fr.y, r.x - fr.x, fr.h))
            if r.x2 < fr.x2 - EPS:
                new_free.append(Rect(r.x2, fr.y, fr.x2 - r.x2, fr.h))
            if r.y > fr.y + EPS:
                new_free.append(Rect(fr.x, fr.y, fr.w, r.y - fr.y))
            if r.y2 < fr.y2 - EPS:
                new_free.append(Rect(fr.x, r.y2, fr.w, fr.y2 - r.y2))
        # prune contained
        pruned = []
        for i, a in enumerate(new_free):
            contained = False
            for j, b in enumerate(new_free):
                if i != j and a.x >= b.x - EPS and a.y >= b.y - EPS and a.x2 <= b.x2 + EPS and a.y2 <= b.y2 + EPS:
                    if (b.w > a.w + EPS or b.h > a.h + EPS) or j < i:
                        contained = True
                        break
            if not contained:
                pruned.append(a)
        self.free = pruned
        self.used.append(r)


# ---------------------------------------------------------------------------
# Guillotine (best area fit, split to keep the larger leftover), deterministic
# ---------------------------------------------------------------------------

class GuillotineBin:
    def __init__(self, w: float, h: float):
        self.w, self.h = w, h
        self.free: list[Rect] = [Rect(0, 0, w, h)]
        self.used: list[Rect] = []

    def best(self, options):
        best = None
        for (w, h, a) in options:
            for idx, fr in enumerate(self.free):
                if _fits(fr, w, h):
                    score = (fr.w * fr.h - w * h, min(fr.w - w, fr.h - h), fr.y, fr.x)
                    if best is None or score < best[0]:
                        best = (score, Rect(fr.x, fr.y, w, h), a, idx)
        return best

    def place(self, r: Rect, idx: int):
        fr = self.free.pop(idx)
        right_w, bottom_h = fr.w - r.w, fr.h - r.h
        # Two candidate splits; keep the one whose larger leftover is larger.
        horiz = [Rect(r.x2, fr.y, right_w, r.h), Rect(fr.x, r.y2, fr.w, bottom_h)]   # cut across the full width below the item
        vert = [Rect(r.x2, fr.y, right_w, fr.h), Rect(fr.x, r.y2, r.w, bottom_h)]    # cut down the full height right of the item
        h_max = max(a.w * a.h for a in horiz)
        v_max = max(a.w * a.h for a in vert)
        chosen = horiz if h_max >= v_max else vert
        for a in chosen:
            if a.w > EPS and a.h > EPS:
                self.free.append(a)
        self.used.append(r)


def _pack_bundled(items: list[Item], bin_w: float, bin_h: float, guillotine: bool, max_bins=None) -> tuple[list, list]:
    """Returns ([(item, bin_index, rect(inflated), angle)], unplaced_items). Opens a new bin only when nothing
    open fits, and never more than max_bins (None = unlimited); items that cannot be placed are returned."""
    bins = []
    out = []
    unplaced = []
    for it in items:
        if not it.options:
            unplaced.append(it)
            continue
        best = None
        for bi, b in enumerate(bins):
            cand = b.best(it.options)
            if cand is not None and (best is None or cand[0] < best[1][0]):
                best = (bi, cand)
        if best is None:
            if max_bins is not None and len(bins) >= max_bins:
                unplaced.append(it)
                continue
            b = GuillotineBin(bin_w, bin_h) if guillotine else MaxRectsBin(bin_w, bin_h)
            bins.append(b)
            cand = b.best(it.options)
            if cand is None:
                bins.pop()
                unplaced.append(it)
                continue
            best = (len(bins) - 1, cand)
        bi, cand = best
        b = bins[bi]
        if guillotine:
            _, r, a, idx = cand
            b.place(r, idx)
        else:
            _, r, a = cand
            b.place(r)
        out.append((it, bi, r, a))
    return out, unplaced


def _pack_rectpack(items: list[Item], bin_w: float, bin_h: float, guillotine: bool, max_bins=None):
    """Optional rectpack engine. Only valid when every item has the same rotation policy."""
    import rectpack  # noqa

    items = [it for it in items if it.options]
    rotation_all = all(len(it.options) == 2 for it in items)
    rotation_none = all(len(it.options) == 1 for it in items)
    if not (rotation_all or rotation_none):
        raise RuntimeError("rectpack cannot mix locked and auto-rotate parts")
    algo = rectpack.GuillotineBafSas if guillotine else rectpack.MaxRectsBssf
    packer = rectpack.newPacker(rotation=rotation_all, pack_algo=algo,
                                sort_algo=rectpack.SORT_NONE, bin_algo=rectpack.PackingBin.BFF)
    for it in items:
        w, h, a = it.options[0]
        packer.add_rect(w, h, rid=it.inst.key)
    packer.add_bin(bin_w, bin_h, count=max(1, len(items)) if max_bins is None else max_bins)
    packer.pack()
    by_key = {it.inst.key: it for it in items}
    out = []
    placed_keys = set()
    for (b, x, y, w, h, rid) in packer.rect_list():
        it = by_key[rid]
        w0, h0, a0 = it.options[0]
        if abs(w - w0) < 1e-6 and abs(h - h0) < 1e-6:
            a = a0
        else:
            a = it.options[1][2]
        out.append((it, b, Rect(x, y, w, h), a))
        placed_keys.add(rid)
    if len(out) != len(items) and max_bins is None:
        raise RuntimeError("rectpack left items unpacked")
    out.sort(key=lambda t: items.index(t[0]))
    return out, [it for it in items if it.inst.key not in placed_keys]


def pack_rectangles(job: Job, instances: list[Instance], engine: str = "auto", sheet_w=None, sheet_h=None,
                    max_sheets=None) -> tuple[list[Placement], str, Optional[str], list[Instance]]:
    """Bounding-box packing of instances onto sheets of (sheet_w, sheet_h) (default: the job's first stock),
    opening at most max_sheets. Returns (placements, engine_name, fallback_note, unplaced_instances)."""
    gap = job.gap
    guillotine = job.cutting_method == "guillotine"
    sheet_w = job.sheet_width if sheet_w is None else sheet_w
    sheet_h = job.sheet_height if sheet_h is None else sheet_h
    usable_w, usable_h = sheet_w - 2 * job.outer_edge_margin, sheet_h - 2 * job.outer_edge_margin
    items = []
    for inst in instances:
        opts = []
        seen = set()
        for a in inst.part.allowed_angles(job.rotation_step, "bounding-box"):
            rp = rotated_normalized(inst.part.base_polygon(), a)
            _, _, w, h = rp.bounds
            key = (round(w, 9), round(h, 9))
            if key in seen:
                continue
            seen.add(key)
            if w <= usable_w + EPS and h <= usable_h + EPS:
                opts.append((w + gap, h + gap, a))
        items.append(Item(inst, opts))  # no options -> reported as unplaced (may fit a later, larger stock)

    bin_w, bin_h = usable_w + gap, usable_h + gap
    fallback = None
    used = None
    result = None
    unplaced_items: list[Item] = []
    if engine in ("auto", "rectpack"):
        try:
            result, unplaced_items = _pack_rectpack(items, bin_w, bin_h, guillotine, max_sheets)
            used = "rectpack (" + ("GuillotineBafSas" if guillotine else "MaxRectsBssf") + ")"
        except ImportError:
            if engine == "rectpack":
                raise
            fallback = "rectpack is not importable in this runtime; used the bundled packer instead"
        except Exception as ex:
            if engine == "rectpack":
                raise
            fallback = f"rectpack could not handle this job ({ex}); used the bundled packer instead"
    if result is None:
        result, unplaced_items = _pack_bundled(items, bin_w, bin_h, guillotine, max_sheets)
        used = "bundled " + ("guillotine (best-area-fit, larger-leftover split)" if guillotine else "MaxRects (best-short-side-fit)")

    placements = []
    m = job.outer_edge_margin
    for (it, bi, r, a) in result:
        x, y = m + r.x, m + r.y
        w, h = r.w - gap, r.h - gap
        poly = placed_polygon(it.inst.part, x, y, a)
        placements.append(Placement(it.inst.part.id, it.inst.index, bi, x, y, a, w, h, poly))
    return placements, used, fallback, [it.inst for it in unplaced_items]


# ---------------------------------------------------------------------------
# Guillotine feasibility check (used by verification)
# ---------------------------------------------------------------------------

def is_guillotine_cuttable(rects: list[tuple[float, float, float, float]], tol: float = 1e-6) -> bool:
    """True if the set of axis-aligned rects can be separated by a sequence of full edge-to-edge cuts."""
    from functools import lru_cache

    idx = tuple(range(len(rects)))

    @lru_cache(maxsize=None)
    def rec(group: tuple) -> bool:
        if len(group) <= 1:
            return True
        rs = [rects[i] for i in group]
        # vertical cut at x = c: every rect entirely left or entirely right
        for c in sorted({r[2] for r in rs}):
            left = tuple(i for i in group if rects[i][2] <= c + tol)
            right = tuple(i for i in group if rects[i][0] >= c - tol)
            if left and right and len(left) + len(right) == len(group):
                if rec(left) and rec(right):
                    return True
        for c in sorted({r[3] for r in rs}):
            top = tuple(i for i in group if rects[i][3] <= c + tol)
            bottom = tuple(i for i in group if rects[i][1] >= c - tol)
            if top and bottom and len(top) + len(bottom) == len(group):
                if rec(top) and rec(bottom):
                    return True
        return False

    return rec(idx)


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
# v1.1 (2026-09-04): Sheet size and sheet cap parameters; unplaced instances returned instead of raising.
