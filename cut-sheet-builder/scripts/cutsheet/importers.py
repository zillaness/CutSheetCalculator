"""
file: importers.py
version: 1.1
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Extracts a real closed outline (outer ring plus holes) from a DXF or SVG file as a shapely Polygon in inches, flattening curves to a stated tolerance.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

import math
import os
import re
from typing import Iterable, Optional

from shapely.geometry import Polygon, LinearRing, LineString
from shapely.validation import make_valid

from . import units as U

DEFAULT_TOLERANCE_IN = 0.005  # chord error when flattening curves, inches
MIN_RING_AREA_IN2 = 1e-6
ENGRAVE_LAYER_RE = re.compile(r"engrav|score|etch|mark|raster", re.I)  # layer/group names that mean "engrave, do not cut"


class ImportError_(ValueError):
    pass


# ---------------------------------------------------------------------------
# Ring assembly (shared by both importers)
# ---------------------------------------------------------------------------

def _clean_ring(pts: list[tuple[float, float]]) -> Optional[list[tuple[float, float]]]:
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or (abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9):
            out.append((float(p[0]), float(p[1])))
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-9 and abs(out[0][1] - out[-1][1]) < 1e-9:
        out.pop()
    if len(out) < 3:
        return None
    return out


def assemble_polygon(rings: Iterable[list[tuple[float, float]]]) -> tuple[Polygon, str]:
    """Largest ring is the outer boundary; rings inside it are holes; other rings are reported and ignored."""
    polys = []
    for r in rings:
        r = _clean_ring(r)
        if r is None:
            continue
        try:
            lr = LinearRing(r)
        except Exception:
            continue
        poly = Polygon(lr)
        if not poly.is_valid:
            poly = make_valid(poly)
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda g: g.area)
            elif poly.geom_type != "Polygon":
                continue
        if poly.area < MIN_RING_AREA_IN2:
            continue
        polys.append(poly)
    if not polys:
        raise ImportError_("no closed outline found in file (need at least one closed path/polyline/circle, or lines+arcs that chain into a loop)")
    polys.sort(key=lambda p: p.area, reverse=True)
    outer = polys[0]
    holes = []
    ignored = 0
    for p in polys[1:]:
        if outer.contains(p.representative_point()) and outer.buffer(1e-6).contains(p):
            holes.append(p.exterior.coords[:-1])
        else:
            ignored += 1
    result = Polygon(outer.exterior.coords[:-1], holes)
    if not result.is_valid:
        result = make_valid(result)
        if result.geom_type == "MultiPolygon":
            result = max(result.geoms, key=lambda g: g.area)
    notes = ""
    if holes:
        notes += f"{len(holes)} interior cutout(s). "
    if ignored:
        notes += f"WARNING: {ignored} disjoint outline(s) ignored (largest outline kept). "
    return result, notes.strip()


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

def _svg_rings(fpath: str, tol_px: float) -> tuple[list[list[tuple[float, float]]], float]:
    """Return rings in svgelements px (96 ppi) and the factor to convert px -> raw user units."""
    from svgelements import SVG, Path, Shape, Move, Close, Line, Arc, CubicBezier, QuadraticBezier

    svg = SVG.parse(fpath, reify=True, ppi=96.0)
    # px -> raw user units factor (used only when the caller overrides the file's units)
    raw_factor = 1.0
    try:
        vb = svg.viewbox
        if vb is not None and svg.width and vb.width:
            raw_factor = float(vb.width) / float(svg.width)
    except Exception:
        raw_factor = 1.0

    rings: list[list[tuple[float, float]]] = []
    engrave: list[tuple[list[tuple[float, float]], bool]] = []  # (points, closed)
    for el in svg.elements():
        if not isinstance(el, Shape):
            continue
        try:
            path = Path(el)
        except Exception:
            continue
        is_engrave = _svg_in_engrave_group(el)
        for sub in path.as_subpaths():
            pts: list[tuple[float, float]] = []
            closed = False
            for seg in sub:
                if isinstance(seg, Move):
                    if seg.end is not None:
                        pts.append((seg.end.x, seg.end.y))
                elif isinstance(seg, Close):
                    closed = True
                elif isinstance(seg, Line):
                    pts.append((seg.end.x, seg.end.y))
                elif isinstance(seg, (Arc, CubicBezier, QuadraticBezier)):
                    try:
                        length = seg.length(error=1e-4)
                    except Exception:
                        length = 0.0
                    n = max(8, int(math.ceil(length / max(tol_px * 4, 1e-6))))
                    n = min(n, 2000)
                    for i in range(1, n + 1):
                        p = seg.point(i / n)
                        pts.append((p.x, p.y))
            if not pts:
                continue
            coincident = abs(pts[0][0] - pts[-1][0]) <= tol_px and abs(pts[0][1] - pts[-1][1]) <= tol_px
            if is_engrave:
                engrave.append((pts, closed or coincident))
                continue
            if not closed and not coincident:
                continue  # open cut path: skipped (outlines must close)
            rings.append(pts)
    return rings, raw_factor, engrave


def _svg_in_engrave_group(el) -> bool:
    """True when the element or any ancestor group is named like an engrave layer (id, label, class)."""
    node = el
    while node is not None:
        vals = getattr(node, "values", {}) or {}
        for key in ("id", "inkscape:label", "{http://www.inkscape.org/namespaces/inkscape}label", "class", "label", "data-name"):
            v = vals.get(key)
            if v and ENGRAVE_LAYER_RE.search(str(v)):
                return True
        node = getattr(node, "parent", None) if hasattr(node, "parent") else None
        if node is None:
            # svgelements stores inherited attributes on values; also check inherited group names
            break
    return False


def _engrave_geoms(engrave: list, k: float) -> list:
    out = []
    for pts, closed in engrave:
        pts_in = [(x * k, y * k) for (x, y) in pts]
        if closed:
            r = _clean_ring(pts_in)
            if r:
                poly = Polygon(r)
                if poly.is_valid and poly.area > MIN_RING_AREA_IN2:
                    out.append(poly)
                    continue
        if len(pts_in) >= 2:
            out.append(LineString(pts_in))
    return out


def import_svg(fpath: str, file_unit: Optional[str] = None, tolerance_in: float = DEFAULT_TOLERANCE_IN) -> tuple[Polygon, str, list]:
    tol_px = tolerance_in * 96.0
    rings, raw_factor, engrave = _svg_rings(fpath, tol_px)
    if file_unit:
        # Interpret the file's raw user units as <file_unit>.
        k = raw_factor * U.TO_BASE[U.normalize_unit(file_unit)]
        note = f"SVG user units read as {U.normalize_unit(file_unit)} (override). "
    else:
        k = 1.0 / 96.0  # svgelements px at 96 ppi -> inches
        note = "SVG physical size from file width/height (96 px/in). "
    rings_in = [[(x * k, y * k) for (x, y) in r] for r in rings]
    poly, n2 = assemble_polygon(rings_in)
    eg = _engrave_geoms(engrave, k)
    if eg:
        n2 += f" {len(eg)} engrave path(s) from an engrave/score group."
    return poly, (note + n2).strip(), eg


# ---------------------------------------------------------------------------
# DXF
# ---------------------------------------------------------------------------

def _flatten_path(p, distance: float) -> list[tuple[float, float]]:
    return [(v.x, v.y) for v in p.flattening(distance)]


def _expand_inserts(entities):
    for e in entities:
        if e.dxftype() == "INSERT":
            try:
                yield from _expand_inserts(e.virtual_entities())
            except Exception:
                continue
        else:
            yield e


def import_dxf(fpath: str, file_unit: Optional[str] = None, tolerance_in: float = DEFAULT_TOLERANCE_IN) -> tuple[Polygon, str, list]:
    import ezdxf
    from ezdxf import path as ezpath, edgeminer, edgesmith

    doc = ezdxf.readfile(fpath)
    ins = doc.header.get("$INSUNITS", 0)
    detected = U.DXF_INSUNITS.get(int(ins), None)
    if file_unit:
        unit = U.normalize_unit(file_unit)
        note = f"DXF units read as {unit} (override; file says {detected or 'unitless'}). "
    elif detected:
        unit = detected
        note = f"DXF $INSUNITS = {unit}. "
    else:
        unit = "in"
        note = "WARNING: DXF has no $INSUNITS; assumed inches. Set source.units if wrong. "
    k = U.TO_BASE[unit]
    tol_file = tolerance_in / k  # flattening distance in file units

    msp = doc.modelspace()
    ents = list(_expand_inserts(msp))
    closed_rings: list[list[tuple[float, float]]] = []
    open_ents = []
    engrave: list[tuple[list[tuple[float, float]], bool]] = []
    for e in ents:
        t = e.dxftype()
        if t in ("LWPOLYLINE", "POLYLINE", "CIRCLE", "ELLIPSE", "SPLINE", "ARC", "LINE", "HATCH"):
            if t == "HATCH":
                continue
            try:
                layer = str(e.dxf.layer) if e.dxf.hasattr("layer") else ""
                if ENGRAVE_LAYER_RE.search(layer):
                    closed = edgesmith.is_closed_entity(e)
                    engrave.append((_flatten_path(ezpath.make_path(e), tol_file), closed))
                    continue
                if edgesmith.is_closed_entity(e):
                    closed_rings.append(_flatten_path(ezpath.make_path(e), tol_file))
                else:
                    open_ents.append(e)
            except Exception:
                continue
    chained = 0
    if open_ents:
        gap_tol = max(tol_file, 1e-6)
        try:
            edges = list(edgesmith.edges_from_entities_2d(open_ents, gap_tol=gap_tol))
            deposit = edgeminer.Deposit(edges, gap_tol=gap_tol)
            chains = edgeminer.find_all_simple_chains(deposit)
            for chain in chains:
                if not chain:
                    continue
                if _chain_closed(chain, gap_tol):
                    p = edgesmith.path2d_from_chain(chain)
                    closed_rings.append(_flatten_path(p, tol_file))
                    chained += 1
        except Exception as ex:  # chaining is best-effort; closed entities still count
            note += f"(edge chaining failed: {ex}) "
    if chained:
        note += f"{chained} loop(s) chained from lines/arcs. "
    rings_in = [[(x * k, y * k) for (x, y) in r] for r in closed_rings]
    poly, n2 = assemble_polygon(rings_in)
    eg = _engrave_geoms(engrave, k)
    if eg:
        n2 += f" {len(eg)} engrave path(s) from an engrave/score layer."
    return poly, (note + n2).strip(), eg


def _chain_closed(chain, gap_tol: float) -> bool:
    s = chain[0].start
    e = chain[-1].end
    return s.distance(e) <= gap_tol


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def import_outline(fpath: str, file_unit: Optional[str] = None, tolerance=None) -> tuple[Polygon, str, list]:
    """Returns (outline polygon in inches, notes, engrave geometries in the same frame)."""
    if not os.path.exists(fpath):
        raise ImportError_(f"outline file not found: {fpath}")
    tol = float(tolerance) if tolerance else DEFAULT_TOLERANCE_IN
    ext = os.path.splitext(fpath)[1].lower()
    if ext == ".svg":
        return import_svg(fpath, file_unit, tol)
    if ext == ".dxf":
        return import_dxf(fpath, file_unit, tol)
    raise ImportError_(f"unsupported outline format '{ext}' (use .svg or .dxf)")


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
# v1.1 (2026-09-04): Engrave/score layer detection (DXF layer names, SVG group names).
