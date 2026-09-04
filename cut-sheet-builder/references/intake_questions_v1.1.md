---
file: intake_questions_v1.0.md
version: 1.1
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: The standard interview for a cut-sheet job, in the order to ask it, with which answers have no default.
ai_update: Update last_updated and version. Rename file to match. Append changelog at bottom.
---

# Intake question set

Run through `user-input-protocol`. Pull answers from the conversation first (a pasted parts
table, uploaded DXF/SVG files, a stated machine) and ask only what is missing. Two answers
are never defaulted: sheet size and cutting method.

## Always asked

1. **Parts.** Typed dimensions (w x h, qty) or files (DXF/SVG) with quantities. For files:
   what unit the file is in if it is not embedded, and which outline if a file holds several.
2. **Sheet size.** Offer presets: 24 x 18 laser, 4 x 8 plywood (96 x 48), 4 x 4 half sheet,
   or custom. No default.
3. **Cutting method.** `free` (laser, CNC, jigsaw: any path) or `guillotine` (table saw,
   panel saw: full edge-to-edge cuts only). No default.
4. **Kerf.** Typical: 0.125 in table saw blade, 0.008 to 0.012 in laser on plywood/acrylic.
5. **Outer edge margin.** Sheet edge to nearest part. Typical 0.25 in laser, 0.5 in plywood
   with damaged edges.
6. **Part spacing mode.** `kerf-gap` (one kerf between parts; the trophy model),
   `shared-edge` (zero gap, shared cut line; only when the toolpath compensates kerf),
   `custom-margin` (state the value: clearance for heat spread or hand finishing).
7. **Rotation policy per part.** `auto` or `locked` (with the angle). Ask explicitly for
   engraved, grained, or oriented-text parts; do not assume engraved means locked.

## Asked when relevant

8. **Nest mode.** `true-outline` for imported outlines (default), `bounding-box` for speed or
   when parts are all rectangles. Per-part override possible.
9. **Rotation step** for outline nesting. Pick from how the parts will be cut, then confirm:

   | Cutting tool | Suggested `rotation_step` | Why |
   |---|---|---|
   | Laser, CNC router, plasma | `free` (or 15 if the job is large and slow) | The machine does not care about the angle; density is all that matters |
   | Jigsaw, bandsaw, hand tracing from a printed layout | 90 or 45 | Angles a person can mark with a square or a 45 template; odd angles are slow to lay out and easy to get wrong |
   | Table saw, panel saw | none (guillotine) | `cutting_method: guillotine` forces 0/90 bounding boxes |

   A single part can override the job's step (`parts[].rotation_step`) when one hand-cut
   piece shares a sheet with laser-cut ones. Typed rectangles always stay on 0/90.
10. **Groups and sequencing.** Any parts to isolate onto their own sheets or cut later?
11. **Rods/bars.** Piece length, quantity, stock bar length (or "just tell me the total").
12. **Units for display.** in/ft or mm/cm. Internal math is always inches.
13. **Output version and author** if not 1.0 / Sam Cao.

## Style/phrasing assumptions (do not ask)

- Reference render scale (40 px/in, auto-reduced for big sheets).
- Colors.
- Output directory (next to the job file under `out/<job>/` unless told otherwise).

## CHANGELOG
- v1.0 (2026-09-04): Initial release.
- v1.1 (2026-09-04): Rotation step guidance by cutting tool; free mode; per-part override.
