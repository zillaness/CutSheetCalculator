"""
file: edges.py
version: 1.0
author: Sam Cao
created: 2026-09-10
last_updated: 2026-09-10
description: Segment addressing for part edges. Names the straight runs of a part outline so a job can say which edges must land on factory stock or carry banding, per material_model PRD v1.1 section 7.2.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

from shapely.geometry import LineString, Polygon

# Part coordinates run x from the left and y from the top, the same frame the reference render
# and the cut list use. So "top" is the low-y side, not the high-y one.
SIDES = ("left", "right", "top", "bottom")
COLLINEAR_TOL = 1e-7   # cross-product area below this merges two runs into one
MIN_SEGMENT = 1e-6     # shorter than this is a vertex artifact, not an edge

# Sides that meet. A corner request naming two sides that are not here cannot be satisfied.
ADJACENT_SIDES = {
    ("left", "top"), ("top", "left"),
    ("top", "right"), ("right", "top"),
    ("right", "bottom"), ("bottom", "right"),
    ("bottom", "left"), ("left", "bottom"),
}


class EdgeError(ValueError):
    """Raised when a job names an edge the part does not have."""


def rectangle_sides(w: float, h: float) -> dict[str, LineString]:
    """The four sides of a typed rectangle in its base orientation."""
    return {
        "top": LineString([(0.0, 0.0), (w, 0.0)]),
        "right": LineString([(w, 0.0), (w, h)]),
        "bottom": LineString([(w, h), (0.0, h)]),
        "left": LineString([(0.0, h), (0.0, 0.0)]),
    }


def _ring_points(poly: Polygon) -> list[tuple[float, float]]:
    """Exterior ring, duplicate closing point dropped, started at the vertex nearest the
    top-left corner so numbering does not move when an importer reorders the ring."""
    pts = list(poly.exterior.coords)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not pts:
        return []
    start = min(range(len(pts)), key=lambda i: (pts[i][1], pts[i][0]))
    return pts[start:] + pts[:start]


def _cross(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def outline_segments(poly: Polygon) -> list[LineString]:
    """Straight runs of the outline, collinear neighbours merged, numbered from the vertex
    nearest the top-left and walked in the ring's stored direction."""
    pts = _ring_points(poly)
    if len(pts) < 2:
        return []
    closed = pts + [pts[0]]
    runs: list[list[tuple[float, float]]] = [[closed[0], closed[1]]]
    for nxt in closed[2:]:
        run = runs[-1]
        if abs(_cross(run[0], run[-1], nxt)) <= COLLINEAR_TOL:
            run[-1] = nxt  # still straight: extend rather than start a new edge
        else:
            runs.append([run[-1], nxt])
    # The walk can end collinear with where it started; fold that tail into the first run.
    if len(runs) > 2 and abs(_cross(runs[-1][0], runs[-1][-1], runs[0][-1])) <= COLLINEAR_TOL:
        runs[0][0] = runs[-1][0]
        runs.pop()
    return [LineString(r) for r in runs if LineString(r).length > MIN_SEGMENT]


def part_edges(part) -> dict[str, LineString]:
    """Every addressable edge of a part, keyed by the name a job may use.

    A typed rectangle answers to left/right/top/bottom. An imported outline answers to the
    index of a straight run ("0", "1", ...), because a shape with no top side has nothing
    honest to call "top"."""
    if part.is_rectangle:
        return rectangle_sides(part.width, part.height)
    return {str(i): seg for i, seg in enumerate(outline_segments(part.base_polygon()))}


def resolve(part, name: str, ctx: str) -> LineString:
    """Look up one named edge, or say plainly what the part does have."""
    edges = part_edges(part)
    key = str(name).strip().lower()
    if key in edges:
        return edges[key]
    if part.is_rectangle:
        raise EdgeError(f"{ctx}: '{name}' is not an edge of rectangle '{part.id}'; use one of {list(SIDES)}")
    raise EdgeError(f"{ctx}: '{name}' is not an edge of outline '{part.id}'; it has "
                    f"{len(edges)} straight segments, numbered 0 to {len(edges) - 1}")


def touching(a: LineString, b: LineString) -> bool:
    """Two edges meet at a shared endpoint."""
    ends_a = [a.coords[0], a.coords[-1]]
    ends_b = [b.coords[0], b.coords[-1]]
    return any(abs(p[0] - q[0]) < MIN_SEGMENT and abs(p[1] - q[1]) < MIN_SEGMENT
               for p in ends_a for q in ends_b)


def adjacent(part, name_a: str, name_b: str) -> bool:
    """Can these two edges form a corner? Named sides of a rectangle have a fixed answer;
    outline segments have to actually touch."""
    a, b = str(name_a).strip().lower(), str(name_b).strip().lower()
    if part.is_rectangle:
        return (a, b) in ADJACENT_SIDES
    edges = part_edges(part)
    if a not in edges or b not in edges:
        return False
    return a != b and touching(edges[a], edges[b])


# CHANGELOG
# v1.0 (2026-09-10): Initial release.
