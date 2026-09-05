"""
file: model.py
version: 1.4
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Data model for a cut-sheet job (parts, rods, sheet, spacing dials, options) and the JSON loader that builds it, including DXF/SVG outline import.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from shapely.geometry import Polygon, box
from shapely import affinity

from . import units as U

SHEET_PRESETS = {
    # name: (width, height, unit)
    "laser_24x18": (24.0, 18.0, "in"),
    "plywood_4x8": (96.0, 48.0, "in"),
    "plywood_4x4": (48.0, 48.0, "in"),
}

SPACING_MODES = ("kerf-gap", "shared-edge", "custom-margin")
CUTTING_METHODS = ("free", "guillotine")
NEST_MODES = ("bounding-box", "true-outline")
ROTATION_POLICIES = ("auto", "locked")
MACHINES = ("laser", "router", "plasma", "waterjet", "hand")
LABEL_MODES = ("none", "on-piece", "beside-cutout")
LABEL_FONTS = ("single-line", "outline")
LABEL_TEXTS = ("id", "id+copy")
LABEL_ORIENTATIONS = ("upright", "follow-part")
LABEL_FALLBACKS = ("on-piece", "drop")
OUTPUT_KINDS = ("reference", "svg", "dxf", "pdf")
PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "profiles")
FREE_ROTATION = "free"
FREE_COARSE_STEP = 15.0   # coarse grid searched before the fine pass in free mode
FREE_REFINE_SPAN = 7.0    # degrees either side of the best coarse angle
FREE_REFINE_STEP = 1.0

DEFAULT_PALETTE = [
    "#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
    "#1f77b4", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
]


class JobError(ValueError):
    """Raised for anything wrong with the job definition that a human must fix."""


def normalize_polygon(poly: Polygon) -> Polygon:
    """Translate a polygon so its bounding box starts at (0, 0)."""
    minx, miny, _, _ = poly.bounds
    return affinity.translate(poly, -minx, -miny)


def rotated_normalized(poly: Polygon, angle_deg: float) -> Polygon:
    """Rotate about the origin then re-normalize so the bbox min corner is (0, 0)."""
    if angle_deg % 360 == 0:
        return normalize_polygon(poly)
    return normalize_polygon(affinity.rotate(poly, angle_deg, origin=(0, 0)))


def transform_like(geom, base_poly: Polygon, angle_deg: float, dx: float = 0.0, dy: float = 0.0):
    """Apply to <geom> the exact rotation + normalization that rotated_normalized applies to base_poly,
    then translate by (dx, dy). Used so engrave geometry moves with its part."""
    rp = affinity.rotate(base_poly, angle_deg, origin=(0, 0)) if angle_deg % 360 else base_poly
    minx, miny, _, _ = rp.bounds
    g = affinity.rotate(geom, angle_deg, origin=(0, 0)) if angle_deg % 360 else geom
    return affinity.translate(g, dx - minx, dy - miny)


@dataclass
class LabelSettings:
    """Job-level label settings (PRD piece_labeling v1.1, section 7.9). Lengths in base units (inches)."""
    mode: str = "none"
    font: Optional[str] = None            # None = derived from machine (router: single-line, laser: outline)
    text: str = "id"                      # id | id+copy
    cap_height: Optional[float] = None    # None = machine default
    orientation: str = "upright"
    auto_spacing: bool = True
    min_spacing: float = 0.0
    clearance_pad: float = 0.06
    on_piece_inset: Optional[float] = None  # None = one tool diameter (router) / one kerf (laser), min 0.05
    legibility_factor: float = 5.0
    laser_min_height: float = 0.12
    fallback: str = "on-piece"
    dxf_layer: str = "ENGRAVE"


@dataclass
class Part:
    id: str
    quantity: int
    width: float  # base units (inches), bbox of the base outline at angle 0
    height: float
    rotation: str = "auto"  # "auto" | "locked"
    locked_angle: float = 0.0
    engrave: bool = False
    group: Optional[str] = None
    color: Optional[str] = None
    nest_mode: Optional[str] = None  # per-part override
    rotation_step: Optional[object] = None  # per-part override: degrees or "free"
    outline: Optional[Polygon] = None  # base outline in inches, normalized, None for typed rectangles
    engrave_geoms: list = field(default_factory=list)  # shapely geometries (same frame as outline) from engrave/score layers
    label_mode: Optional[str] = None   # per-part override of labels.mode
    label_text: Optional[str] = None   # per-part text on the piece (defaults to the id)
    source: str = "typed"
    notes: str = ""

    @property
    def is_rectangle(self) -> bool:
        return self.outline is None

    def base_polygon(self) -> Polygon:
        if self.outline is not None:
            return self.outline
        return box(0, 0, self.width, self.height)

    @property
    def true_area(self) -> float:
        return self.base_polygon().area

    @property
    def bbox_area(self) -> float:
        return self.width * self.height

    def effective_step(self, job_step) -> object:
        """Per-part rotation_step wins over the job's. Returns a float (degrees) or "free"."""
        return self.rotation_step if self.rotation_step is not None else job_step

    def allowed_angles(self, rotation_step, mode: str) -> list[float]:
        """Coarse angles the packer may try for this part. Locked parts get exactly one.
        "free" returns the 15-degree grid; the outline nester refines around the best hit."""
        if self.rotation == "locked":
            return [float(self.locked_angle) % 360]
        if mode == "bounding-box" or self.is_rectangle:
            # A rectangle gains nothing from angles other than 0/90, and tilted rectangles
            # are useless on a table saw, so keep them axis-aligned in every mode.
            base = float(self.locked_angle) % 360
            return [base, (base + 90) % 360]
        step = self.effective_step(rotation_step)
        if step == FREE_ROTATION:
            step = FREE_COARSE_STEP
        step = float(step) if step and float(step) > 0 else 90.0
        n = int(round(360.0 / step))
        return [(i * step) % 360 for i in range(max(n, 1))]

    def free_rotation(self, job_step) -> bool:
        return self.rotation == "auto" and not self.is_rectangle and self.effective_step(job_step) == FREE_ROTATION


@dataclass
class Stock:
    """One sheet size available to the job. quantity None = unlimited (only the last stock may be unlimited)."""
    width: float
    height: float
    quantity: Optional[int] = None
    preset: Optional[str] = None

    @property
    def label(self) -> str:
        return self.preset or f"{self.width:g}x{self.height:g}in"


@dataclass
class Rod:
    id: str
    length: float  # base units
    quantity: int
    stock_length: Optional[float] = None  # None = report total continuous length only


@dataclass
class Job:
    name: str
    sheet_width: float
    sheet_height: float
    outer_edge_margin: float
    kerf: float
    part_spacing_mode: str
    cutting_method: str
    nest_mode: str
    parts: list[Part]
    rods: list[Rod] = field(default_factory=list)
    stocks: list[Stock] = field(default_factory=list)  # priority order; sheet_width/height mirror stocks[0]
    custom_margin: float = 0.0
    rotation_step: object = 90.0  # degrees, or "free"
    seed: int = 0
    display_unit: str = "in"
    input_unit: str = "in"
    sheet_preset: Optional[str] = None
    isolated_groups: list[str] = field(default_factory=list)
    deferred_groups: list[str] = field(default_factory=list)
    engine_2d: str = "auto"  # auto | rectpack | bundled | nest2d | shapely
    version: str = "1.0"
    author: str = "Sam Cao"
    px_per_unit: float = 40.0  # reference render: pixels per inch
    engrave_layer: str = "none"  # none | outline-guide
    machine: Optional[str] = None
    marking_tool_diameter: Optional[float] = None  # base units
    outputs: Optional[list] = None  # None = everything available
    profile: Optional[str] = None
    labels: LabelSettings = field(default_factory=LabelSettings)
    spacing_bump: Optional[tuple] = None  # (configured gap, effective gap) when labels raised the spacing
    raw: dict = field(default_factory=dict)

    @property
    def configured_gap(self) -> float:
        """Gap between adjacent parts, from the part_spacing_mode dial alone."""
        if self.part_spacing_mode == "kerf-gap":
            return self.kerf
        if self.part_spacing_mode == "shared-edge":
            return 0.0
        return self.custom_margin

    @property
    def gap(self) -> float:
        """Effective gap: the configured gap, raised when beside-cutout labels need the corridor."""
        if self.spacing_bump is not None:
            return self.spacing_bump[1]
        return self.configured_gap

    # ---- labels -------------------------------------------------------------------------
    @property
    def labels_enabled(self) -> bool:
        return self.labels.mode != "none" or any(p.label_mode not in (None, "none") for p in self.parts)

    @property
    def label_font(self) -> str:
        if self.labels.font:
            return self.labels.font
        return "single-line" if self.machine == "router" else "outline"

    def label_min_height(self) -> tuple[float, str]:
        """(minimum cap height in inches, basis text) per PRD 7.3."""
        L = self.labels
        if self.machine == "router":
            d = self.marking_tool_diameter or 0.0
            if self.label_font == "outline":
                return 8.0 * d, f"router, outline font: 8 x tool diameter {d:.4g} in (discouraged: endmill fill)"
            return L.legibility_factor * d, f"router, single-line: {L.legibility_factor:g} x tool diameter {d:.4g} in"
        if self.machine == "laser":
            if self.label_font == "outline":
                return L.laser_min_height, f"laser, outline (raster): {L.laser_min_height:.3g} in floor"
            return max(0.10, L.laser_min_height - 0.02), "laser, single-line (score): 0.10 in floor"
        if self.machine == "hand":
            return 0.25, "hand: printed reference must survive a photocopy"
        return 0.0, "no machine"

    def label_cap_height(self) -> float:
        """Requested cap height, or the machine default when unset (inches)."""
        if self.labels.cap_height is not None:
            return self.labels.cap_height
        mn, _ = self.label_min_height()
        if self.machine == "router":
            return max(0.35, mn)
        if self.machine == "hand":
            return 0.35
        return max(0.20, mn)

    def default_on_piece_inset(self) -> float:
        d = self.marking_tool_diameter if self.machine == "router" and self.marking_tool_diameter else self.kerf
        return max(0.05, d)

    @property
    def usable_width(self) -> float:
        return self.sheet_width - 2 * self.outer_edge_margin

    @property
    def usable_height(self) -> float:
        return self.sheet_height - 2 * self.outer_edge_margin

    def usable(self, stock: "Stock") -> tuple[float, float]:
        return (stock.width - 2 * self.outer_edge_margin, stock.height - 2 * self.outer_edge_margin)

    @property
    def multi_stock(self) -> bool:
        return len(self.stocks) > 1

    def part_mode(self, part: Part) -> str:
        return part.nest_mode or self.nest_mode

    def part_by_id(self, pid: str) -> Part:
        for p in self.parts:
            if p.id == pid:
                return p
        raise KeyError(pid)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _req(d: dict, key: str, ctx: str):
    if key not in d:
        raise JobError(f"{ctx}: missing required field '{key}'")
    return d[key]


def _parse_one_stock(sheet, input_unit: str, ctx: str) -> Stock:
    qty = None
    if isinstance(sheet, str):
        preset = sheet
        if preset not in SHEET_PRESETS:
            raise JobError(f"{ctx}: preset '{preset}' unknown; presets: {sorted(SHEET_PRESETS)}")
        w, h, u = SHEET_PRESETS[preset]
        return Stock(U.to_base(w, u), U.to_base(h, u), None, preset)
    if isinstance(sheet, dict):
        if sheet.get("quantity") is not None:
            qty = int(sheet["quantity"])
            if qty < 1:
                raise JobError(f"{ctx}: quantity must be >= 1 (omit it for unlimited)")
        if "preset" in sheet:
            preset = sheet["preset"]
            if preset not in SHEET_PRESETS:
                raise JobError(f"{ctx}: preset '{preset}' unknown; presets: {sorted(SHEET_PRESETS)}")
            w, h, u = SHEET_PRESETS[preset]
            return Stock(U.to_base(w, u), U.to_base(h, u), qty, preset)
        su = U.normalize_unit(sheet.get("units", input_unit))
        w = U.to_base(float(_req(sheet, "width", ctx)), su)
        h = U.to_base(float(_req(sheet, "height", ctx)), su)
        if w <= 0 or h <= 0:
            raise JobError(f"{ctx}: sheet dimensions must be positive")
        return Stock(w, h, qty, None)
    raise JobError(f"{ctx}: must be a preset name or an object with width/height")


def _parse_stocks(raw: dict, input_unit: str) -> list[Stock]:
    if raw.get("sheets") is not None:
        lst = raw["sheets"]
        if not isinstance(lst, list) or not lst:
            raise JobError("'sheets' must be a non-empty list of sheet sizes in the order to use them")
        stocks = [_parse_one_stock(x, input_unit, f"sheets[{i}]") for i, x in enumerate(lst)]
        for st in stocks[:-1]:
            if st.quantity is None:
                raise JobError("only the last entry in 'sheets' may be unlimited (omit quantity); earlier entries need a quantity")
        return stocks
    if raw.get("sheet") is None:
        raise JobError("job: 'sheet' (or 'sheets') is required; use a preset name or explicit width/height. There is no default sheet size")
    return [_parse_one_stock(raw["sheet"], input_unit, "sheet")]


def _parse_outputs(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = [value]
    outs = []
    for v in value:
        outs.append(_choice(v, OUTPUT_KINDS, "outputs"))
    return outs


def _validate_labels(job: "Job") -> None:
    """Machine rules from PRD 7.1 and the spacing bump from 7.5. Only when labels are on."""
    if not job.labels_enabled:
        return
    if job.machine is None:
        raise JobError("labels are on, so 'machine' is required (laser, router, plasma, waterjet, hand); it has no default")
    if job.machine in ("plasma", "waterjet"):
        raise JobError(f"machine '{job.machine}' cannot mark pieces reliably; set labels.mode to 'none' or change the machine")
    if job.machine == "router" and not job.marking_tool_diameter:
        raise JobError("machine 'router' with labels on requires 'marking_tool_diameter' (no default)")
    if job.labels.font == "outline" and job.machine == "router":
        pass  # allowed, discouraged; the echo warns and the minimum is 8 x tool
    modes = {p.label_mode or job.labels.mode for p in job.parts}
    if "beside-cutout" in modes and job.machine != "hand":
        from .fonts import layout_text
        cap = max(job.label_cap_height(), job.label_min_height()[0])
        th = layout_text("Hg", cap, job.label_font).height
        clearance = th + 2 * job.labels.clearance_pad + job.kerf  # the cut eats kerf/2 into the waste on each side
        need = max(job.labels.min_spacing, clearance)
        if job.labels.auto_spacing:
            if need > job.configured_gap + 1e-9:
                job.spacing_bump = (job.configured_gap, need)
        elif job.configured_gap <= 1e-9:
            raise JobError("beside-cutout labels with shared-edge spacing and auto_spacing off: there is no waste to write in")


def _parse_rotation_step(value, ctx: str):
    """Degrees (a positive divisor of 360) or the string "free"."""
    if isinstance(value, str) and value.strip().lower() == FREE_ROTATION:
        return FREE_ROTATION
    try:
        step = float(value)
    except (TypeError, ValueError):
        raise JobError(f"{ctx}: '{value}' must be a number of degrees or \"free\"")
    if step <= 0 or abs(360 / step - round(360 / step)) > 1e-9:
        raise JobError(f"{ctx}: must be a positive divisor of 360 (e.g. 90, 45, 30, 15, 10, 5) or \"free\"")
    return step


def _choice(value: str, allowed: tuple, ctx: str) -> str:
    v = str(value).strip().lower()
    if v not in allowed:
        raise JobError(f"{ctx}: '{value}' is not one of {list(allowed)}")
    return v


def load_job(path: str) -> Job:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return job_from_dict(raw, base_dir=os.path.dirname(os.path.abspath(path)))


def _load_profile(name: str, base_dir: str) -> dict:
    """Find <name>.json in the job's profiles/ folder or the shipped assets/profiles folder."""
    candidates = [os.path.join(base_dir, "profiles", f"{name}.json"), os.path.join(PROFILES_DIR, f"{name}.json")]
    for c in candidates:
        if os.path.exists(c):
            with open(c, encoding="utf-8") as fh:
                data = json.load(fh)
            return {k: v for k, v in data.items() if not k.startswith("_") and k != "name"}
    available = sorted(os.path.splitext(f)[0] for d in (os.path.join(base_dir, "profiles"), PROFILES_DIR)
                       if os.path.isdir(d) for f in os.listdir(d) if f.endswith(".json"))
    raise JobError(f"profile '{name}' not found; available: {available}")


def _merge_profile(raw: dict, profile: dict) -> dict:
    """Profile fields are defaults; job fields win. labels and part_spacing merge key by key."""
    merged = dict(profile)
    for k, v in raw.items():
        if k in ("labels", "part_spacing") and isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged


def _parse_labels(raw: dict, L) -> LabelSettings:
    d = raw.get("labels") or {}
    if isinstance(d, str):
        d = {"mode": d}
    ls = LabelSettings()
    ls.mode = _choice(d.get("mode", "none"), LABEL_MODES, "labels.mode")
    if d.get("font") is not None:
        ls.font = _choice(d["font"], LABEL_FONTS, "labels.font")
    ls.text = _choice(d.get("text", "id"), LABEL_TEXTS, "labels.text")
    ls.cap_height = L(d["cap_height"]) if d.get("cap_height") is not None else None
    ls.orientation = _choice(d.get("orientation", "upright"), LABEL_ORIENTATIONS, "labels.orientation")
    ls.auto_spacing = bool(d.get("auto_spacing", True))
    ls.min_spacing = L(d.get("min_spacing", 0.0))
    ls.clearance_pad = L(d.get("clearance_pad", 0.06))
    ls.on_piece_inset = L(d["on_piece_inset"]) if d.get("on_piece_inset") is not None else None
    ls.legibility_factor = float(d.get("legibility_factor", 5.0))
    ls.laser_min_height = L(d.get("laser_min_height", 0.12))
    ls.fallback = _choice(d.get("fallback", "on-piece"), LABEL_FALLBACKS, "labels.fallback")
    ls.dxf_layer = str(d.get("dxf_layer", "ENGRAVE"))
    for k in ("cap_height", "min_spacing", "clearance_pad", "laser_min_height"):
        if getattr(ls, k) is not None and getattr(ls, k) < 0:
            raise JobError(f"labels.{k} must be >= 0")
    return ls


def job_from_dict(raw: dict, base_dir: str = ".") -> Job:
    from . import importers  # local import so shapely-only users can import model cheaply

    profile_name = raw.get("profile")
    if profile_name:
        raw = _merge_profile(raw, _load_profile(str(profile_name), base_dir))

    name = raw.get("job_name") or raw.get("name")
    if not name:
        raise JobError("job: missing 'job_name'")

    units = raw.get("units", {}) or {}
    input_unit = U.normalize_unit(units.get("input", "in"))
    display_unit = U.normalize_unit(units.get("display", input_unit))
    if display_unit not in U.DISPLAY_UNITS:
        raise JobError(f"units.display must be one of {U.DISPLAY_UNITS}")

    def L(v):  # length in input units -> base
        return U.to_base(float(v), input_unit)

    # Sheet stock: "sheet" (one size) or "sheets" (priority-ordered list, e.g. offcuts first). Never defaulted.
    stocks = _parse_stocks(raw, input_unit)
    sheet_w, sheet_h, preset = stocks[0].width, stocks[0].height, stocks[0].preset

    if "cutting_method" not in raw:
        raise JobError("job: 'cutting_method' is required ('free' or 'guillotine'); it is always asked per job and has no default")
    cutting_method = _choice(raw["cutting_method"], CUTTING_METHODS, "cutting_method")

    kerf = L(_req(raw, "kerf", "job"))
    margin = L(_req(raw, "outer_edge_margin", "job"))
    if kerf < 0 or margin < 0:
        raise JobError("kerf and outer_edge_margin must be >= 0")

    spacing = raw.get("part_spacing", {"mode": "kerf-gap"})
    if isinstance(spacing, str):
        spacing = {"mode": spacing}
    spacing_mode = _choice(spacing.get("mode", "kerf-gap"), SPACING_MODES, "part_spacing.mode")
    custom_margin = 0.0
    if spacing_mode == "custom-margin":
        if "value" not in spacing:
            raise JobError("part_spacing.mode=custom-margin requires part_spacing.value")
        custom_margin = L(spacing["value"])
        if custom_margin < 0:
            raise JobError("part_spacing.value must be >= 0")

    nest_mode = _choice(raw.get("nest_mode", "true-outline"), NEST_MODES, "nest_mode")
    rotation_step = _parse_rotation_step(raw.get("rotation_step", 90), "rotation_step")

    parts_raw = raw.get("parts", []) or []
    rods_raw = raw.get("rods", []) or []
    if not parts_raw and not rods_raw:
        raise JobError("job needs at least one part or rod")

    parts: list[Part] = []
    seen = set()
    for i, pr in enumerate(parts_raw):
        ctx = f"parts[{i}]"
        pid = str(_req(pr, "id", ctx))
        if pid in seen:
            raise JobError(f"{ctx}: duplicate part id '{pid}'")
        seen.add(pid)
        qty = int(_req(pr, "quantity", ctx))
        if qty <= 0:
            raise JobError(f"{ctx}: quantity must be >= 1")
        rotation = _choice(pr.get("rotation", "auto"), ROTATION_POLICIES, f"{ctx}.rotation")
        locked_angle = float(pr.get("locked_angle", pr.get("angle", 0.0)))
        pmode = pr.get("nest_mode")
        if pmode is not None:
            pmode = _choice(pmode, NEST_MODES, f"{ctx}.nest_mode")
        pstep = pr.get("rotation_step")
        if pstep is not None:
            pstep = _parse_rotation_step(pstep, f"{ctx}.rotation_step")
        plabel = pr.get("label") or {}
        if isinstance(plabel, str):
            plabel = {"text": plabel}
        p_label_mode = _choice(plabel["mode"], LABEL_MODES, f"{ctx}.label.mode") if plabel.get("mode") is not None else None
        p_label_text = str(plabel["text"]) if plabel.get("text") is not None else None

        outline = None
        engrave_geoms = []
        source = "typed"
        notes = ""
        src = pr.get("source")
        if src and isinstance(src, dict) and src.get("type", "typed") != "typed":
            fpath = _req(src, "path", f"{ctx}.source")
            if not os.path.isabs(fpath):
                fpath = os.path.join(base_dir, fpath)
            file_unit = src.get("units")  # None = trust the file
            outline, notes, engrave_geoms = importers.import_outline(fpath, file_unit=file_unit, tolerance=src.get("tolerance"))
            source = os.path.basename(fpath)
            if src.get("scale"):
                k = float(src["scale"])
                outline = affinity.scale(outline, k, k, origin=(0, 0))
                engrave_geoms = [affinity.scale(g, k, k, origin=(0, 0)) for g in engrave_geoms]
            ominx, ominy, _, _ = outline.bounds
            outline = normalize_polygon(outline)
            engrave_geoms = [affinity.translate(g, -ominx, -ominy) for g in engrave_geoms]
            minx, miny, maxx, maxy = outline.bounds
            width, height = maxx - minx, maxy - miny
        else:
            width = L(_req(pr, "width", ctx))
            height = L(_req(pr, "height", ctx))
            if width <= 0 or height <= 0:
                raise JobError(f"{ctx}: width and height must be positive")

        if rotation == "locked" and pmode is None and nest_mode == "bounding-box":
            pass  # any locked angle is fine; bbox is computed from the rotated outline

        parts.append(Part(
            id=pid, quantity=qty, width=width, height=height, rotation=rotation,
            locked_angle=locked_angle, engrave=bool(pr.get("engrave", False)) or bool(engrave_geoms),
            group=pr.get("group"), color=pr.get("color"), nest_mode=pmode, rotation_step=pstep,
            label_mode=p_label_mode, label_text=p_label_text,
            outline=outline, engrave_geoms=engrave_geoms, source=source, notes=notes,
        ))

    for i, p in enumerate(parts):
        if not p.color:
            p.color = DEFAULT_PALETTE[i % len(DEFAULT_PALETTE)]

    rods: list[Rod] = []
    for i, rr in enumerate(rods_raw):
        ctx = f"rods[{i}]"
        stock = rr.get("stock_length")
        rods.append(Rod(
            id=str(_req(rr, "id", ctx)),
            length=L(_req(rr, "length", ctx)),
            quantity=int(_req(rr, "quantity", ctx)),
            stock_length=L(stock) if stock is not None else None,
        ))

    isolated = list(raw.get("isolated_groups", []) or [])
    deferred = list(raw.get("deferred_groups", []) or [])
    for g in deferred:
        if g not in isolated:
            isolated.append(g)  # a deferred group must sit on its own sheet(s)
    known_groups = {p.group for p in parts if p.group}
    for g in isolated:
        if g not in known_groups:
            raise JobError(f"group '{g}' is listed in isolated/deferred_groups but no part carries that group")

    out = raw.get("output", {}) or {}
    render = raw.get("render", {}) or {}

    # Sanity: every part must fit on the usable sheet in at least one allowed orientation.
    job = Job(
        name=str(name), sheet_width=sheet_w, sheet_height=sheet_h,
        outer_edge_margin=margin, kerf=kerf, part_spacing_mode=spacing_mode,
        cutting_method=cutting_method, nest_mode=nest_mode, parts=parts, rods=rods, stocks=stocks,
        custom_margin=custom_margin, rotation_step=rotation_step,
        seed=int(raw.get("seed", 0)), display_unit=display_unit, input_unit=input_unit,
        sheet_preset=preset, isolated_groups=isolated, deferred_groups=deferred,
        engine_2d=str(raw.get("engine", "auto")).lower(),
        version=str(out.get("version", "1.0")), author=str(out.get("author", "Sam Cao")),
        px_per_unit=float(render.get("px_per_unit", 40.0)),
        engrave_layer=str(out.get("engrave_layer", "none")),
        machine=_choice(raw["machine"], MACHINES, "machine") if raw.get("machine") else None,
        marking_tool_diameter=L(raw["marking_tool_diameter"]) if raw.get("marking_tool_diameter") is not None else None,
        outputs=_parse_outputs(raw.get("outputs")),
        profile=str(profile_name) if profile_name else None,
        labels=_parse_labels(raw, L),
        raw=raw,
    )
    _validate_labels(job)
    for st in stocks:
        uw, uh = job.usable(st)
        if uw <= 0 or uh <= 0:
            raise JobError(f"outer_edge_margin leaves no usable area on sheet {st.label}")
    for p in parts:
        fits = False
        for st in stocks:
            uw, uh = job.usable(st)
            for a in p.allowed_angles(job.rotation_step, job.part_mode(p)):
                rp = rotated_normalized(p.base_polygon(), a)
                _, _, w, h = rp.bounds
                if w <= uw + 1e-9 and h <= uh + 1e-9:
                    fits = True
                    break
            if fits:
                break
        if not fits:
            raise JobError(
                f"part '{p.id}' ({p.width:.3f} x {p.height:.3f} in) does not fit inside the usable area of any sheet "
                f"({', '.join(f'{st.label}: {job.usable(st)[0]:.3f} x {job.usable(st)[1]:.3f} in' for st in stocks)}) in any allowed orientation")
    return job


def _step_label(step) -> str:
    return "free" if step == FREE_ROTATION else f"{float(step):g} deg steps"


def parts_table(job: Job) -> list[dict[str, Any]]:
    """Rows for the confirmation echo, in display units."""
    du = job.display_unit
    rows = []
    for p in job.parts:
        rows.append({
            "id": p.id,
            "source": p.source,
            "width": U.fmt(p.width, du),
            "height": U.fmt(p.height, du),
            "true_area": f"{U.from_base(U.from_base(p.true_area, du), du):.3f} {du}^2",
            "bbox_fill": f"{100 * p.true_area / p.bbox_area:.0f}%",
            "quantity": p.quantity,
            "rotation": (f"auto ({_step_label(p.effective_step(job.rotation_step))})" if p.rotation == "auto" and not p.is_rectangle
                         else "auto (0/90)" if p.rotation == "auto" else f"locked @ {p.locked_angle:g} deg"),
            "engrave": "yes" if p.engrave else "no",
            "group": p.group or "",
            "nest_mode": job.part_mode(p),
            "notes": p.notes,
        })
    return rows


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
# v1.1 (2026-09-04): rotation_step accepts "free" and a per-part override.
# v1.2 (2026-09-04): engrave geometry from import travels with the part (transform_like).
# v1.3 (2026-09-04): Stock list ('sheets') with quantities, priority order.
# v1.4 (2026-09-05): machine, marking_tool_diameter, outputs, profile, labels (job and per part), spacing bump.
