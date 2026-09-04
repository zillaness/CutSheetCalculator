---
file: engine_notes_v1.0.md
version: 1.2
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: What each packing engine does, when the bundled fallbacks run, what was verified at build time, and how to talk about packing density honestly.
ai_update: Update last_updated and version. Rename file to match. Append changelog at bottom.
---

# Engine notes

`python scripts/cut_sheet_builder.py deps` prints what is importable. The validation report
names the engine that actually ran and flags any fallback. Repeat that flag in the summary.

## 1D rod/bar

First-fit-decreasing with one kerf between adjacent pieces. Exact for identical pieces
(verified against `ceil(n / floor((stock + kerf) / (L + kerf)))`). Continuous length is
`n*L + (n-1)*kerf`.

## 2D bounding-box

| Engine | When | Notes |
|---|---|---|
| `rectpack` MaxRectsBssf / GuillotineBafSas | importable, and every part shares one rotation policy | External, well tested |
| bundled MaxRects (best-short-side-fit) | rectpack missing, or mixed locked/auto parts | Deterministic, per-item rotation |
| bundled guillotine (best-area-fit, larger-leftover split) | `cutting_method: guillotine` without rectpack | Layout is guillotine-cuttable by construction; the verifier proves it anyway |

Build-time status (2026-09-04): `rectpack` did not build in the skill runtime (old
setup.py against a new setuptools). The bundled packer ran for every acceptance test. Both
paths are wired; install rectpack if you want it and the report will say so.

## 2D true-outline

| Engine | When | Notes |
|---|---|---|
| `pynest2d` (libnest2d, no-fit-polygon) | importable | Wrapper is written but could not be exercised at build time (no wheel for this Python). The verification pass still runs on its output, so a wrong placement fails loudly rather than silently |
| bundled shapely greedy | pynest2d missing or failing | Largest-first, bottom-left candidate anchors, rotation search at `rotation_step`, the six best anchors each get a gravity slide toward the top-left and the best result wins, kerf applied as a mitre buffer of gap/2 on every polygon, STRtree overlap queries |
| rectangle packer (see above) | every part in the run is a typed rectangle | A box's outline is its bbox and MaxRects packs boxes better than the greedy nester (trophy: 19 vs 12 parts on sheet 1), so all-rectangle jobs are routed there even in true-outline mode |

### Rotation search

`rotation_step` is per job with a per-part override. Steps: 90, 45, 30, 15, 10, 5, or
`free`. Free mode runs the 15 deg grid, then re-tries the best hit at 1 deg increments
within 7 deg either side (re-sliding each), and keeps whichever lands highest and leftmost.
It is a fine-angle search around a greedy choice, not a global optimizer: on a 30-gusset
test it matched 15 deg (28 parts on sheet 1 vs 23 at 90 deg) at about 1.6x the runtime.
pynest2d, when present, receives one rotation list for the whole job: the finest step any
part asked for, 5 deg for free.

The kerf buffer uses mitre joins, so at a sharp tip the buffered outline reaches farther
than gap/2 (about 0.23 in at a 31 deg tip with a 1/8 in kerf). That is conservative: sharp
tips keep a little extra clearance. The nester's bbox pre-check uses the buffered outline's
real bounds for that reason.

The bundled nester interlocks parts (an L-bracket rotated 180 drops into its neighbor's
notch) but it is a greedy heuristic. Expect lower density than nest2D or Deepnest. Say so
whenever the report flags it, and recommend Deepnest when the job is dense or the stock is
expensive.

Runtime reference (this machine): 30 gussets at 15 deg, about 4 s; 24 L-brackets at 90 deg,
about 1.5 s. `--no-determinism` halves any of these for iteration. Measured effect of sliding
the top 6 anchors instead of 1: L-bracket column height 14.75 -> 12.5 in, gusset 17.6 -> 16.8 in,
runtime x1.4 to x1.8.

## Spacing model, mechanically

- Bounding-box: each item is inflated by `gap` on w and h and packed into a bin of
  `usable + gap`; neighbors end up exactly `gap` apart and the margin is exact.
- True-outline: each polygon is buffered by `gap/2`; two buffered polygons may touch but
  not overlap (intersection area under 1e-6 in^2). The un-buffered polygon must lie inside
  the sheet minus `outer_edge_margin`.

## Determinism

Instances are ordered by bbox area desc, then id, then copy number. No randomness anywhere
in the bundled engines. The verifier re-runs the job and compares every placement.

## CHANGELOG
- v1.0 (2026-09-04): Initial release.
- v1.1 (2026-09-04): Rotation search section: free mode, per-part steps, mitre buffer note.
- v1.2 (2026-09-04): Top-6 slide, all-rectangle routing, new runtime numbers.
