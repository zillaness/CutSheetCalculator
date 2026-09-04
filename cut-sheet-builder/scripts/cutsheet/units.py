"""
file: units.py
version: 1.0
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Unit conversion for the cutsheet package. Every length is stored internally in inches; display units are applied only at input and output.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

from fractions import Fraction

BASE_UNIT = "in"

# Multiply a value in <unit> by this to get inches.
TO_BASE = {
    "in": 1.0,
    "inch": 1.0,
    "inches": 1.0,
    "ft": 12.0,
    "feet": 12.0,
    "mm": 1.0 / 25.4,
    "cm": 1.0 / 2.54,
    "m": 1000.0 / 25.4,
    "px": 1.0 / 96.0,  # CSS/SVG user unit
    "pt": 1.0 / 72.0,
}

DISPLAY_UNITS = ("in", "ft", "mm", "cm")

# DXF $INSUNITS codes -> unit name
DXF_INSUNITS = {0: None, 1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}
UNIT_TO_DXF_INSUNITS = {"in": 1, "ft": 2, "mm": 4, "cm": 5}


def normalize_unit(unit: str | None) -> str:
    if unit is None:
        return BASE_UNIT
    u = unit.strip().lower()
    if u not in TO_BASE:
        raise ValueError(f"Unknown unit '{unit}'. Use one of: {sorted(TO_BASE)}")
    return u


def to_base(value: float, unit: str | None) -> float:
    """Convert <value> expressed in <unit> to the internal base unit (inches)."""
    return float(value) * TO_BASE[normalize_unit(unit)]


def from_base(value: float, unit: str | None) -> float:
    """Convert an internal (inch) value to <unit>."""
    return float(value) / TO_BASE[normalize_unit(unit)]


def fmt(value_in_base: float, unit: str = "in", places: int = 3) -> str:
    """Format an internal value for display in <unit>, trimming trailing zeros."""
    v = from_base(value_in_base, unit)
    s = f"{v:.{places}f}".rstrip("0").rstrip(".")
    if s in ("", "-0"):
        s = "0"
    return f"{s} {normalize_unit(unit)}"


def fmt_fraction(value_in_base: float, denominator: int = 16) -> str:
    """Nearest-1/16 fractional-inch string (for hand-tool cut lists). Only meaningful for inches."""
    fr = Fraction(value_in_base).limit_denominator(denominator)
    whole = fr.numerator // fr.denominator
    rem = fr - whole
    if rem == 0:
        return f'{whole}"'
    if whole == 0:
        return f'{rem.numerator}/{rem.denominator}"'
    return f'{whole} {rem.numerator}/{rem.denominator}"'


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
