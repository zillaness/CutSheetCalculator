"""
file: pack_1d.py
version: 1.0
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: First-fit-decreasing rod/bar packing with one kerf between adjacent cuts; reports bars needed, per-bar contents, and offcuts.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

from __future__ import annotations

from .model import Rod


def total_length(pieces: list[float], kerf: float) -> float:
    """n pieces need sum(L) + (n-1)*kerf of continuous stock (PRD 7.4)."""
    n = len(pieces)
    if n == 0:
        return 0.0
    return sum(pieces) + (n - 1) * kerf


def pack_rods(rods: list[Rod], kerf: float) -> dict:
    """Pack every rod spec separately (different stock lengths are different materials)."""
    results = []
    for rod in rods:
        pieces = [rod.length] * rod.quantity
        continuous = total_length(pieces, kerf)
        entry = {
            "id": rod.id,
            "piece_length": rod.length,
            "quantity": rod.quantity,
            "kerf": kerf,
            "continuous_length": continuous,
            "stock_length": rod.stock_length,
            "bars": [],
        }
        if rod.stock_length is not None:
            if rod.length > rod.stock_length + 1e-9:
                raise ValueError(f"rod '{rod.id}': piece length {rod.length} exceeds stock length {rod.stock_length}")
            bars: list[list[float]] = []
            for L in sorted(pieces, reverse=True):  # FFD
                placed = False
                for bar in bars:
                    if total_length(bar + [L], kerf) <= rod.stock_length + 1e-9:
                        bar.append(L)
                        placed = True
                        break
                if not placed:
                    bars.append([L])
            entry["bars"] = [
                {"pieces": b, "used": total_length(b, kerf), "offcut": rod.stock_length - total_length(b, kerf)}
                for b in bars
            ]
            entry["bars_needed"] = len(bars)
            entry["waste_fraction"] = 1 - sum(pieces) / (len(bars) * rod.stock_length)
        results.append(entry)
    return {"rods": results}


# CHANGELOG
# v1.0 (2026-09-04): Initial release.
