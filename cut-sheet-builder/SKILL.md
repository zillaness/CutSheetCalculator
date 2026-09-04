---
name: cut-sheet-builder
description: >
  Build accurate, to-scale nesting layouts, stock calculations, and cut-ready files from a
  parts list. Handles typed rectangles and true irregular outlines imported from DXF/SVG,
  nests them onto sheets (laser 24x18, 4x8 plywood, or any size), packs rod/bar stock with
  kerf, and emits a labeled reference SVG, per-sheet cut-ready SVG/DXF, a cut list, and a
  validation report that proves the layout is geometrically trustworthy. Interview-first.
  Trigger on: "lay out parts for cutting", "make a cut sheet", "nest these on a sheet",
  "how much stock do I need", "how many sheets", "cutting layout for", "nest this DXF",
  "nest this SVG", "cut list for", "how much rod/bar/tube do I need", "breakdown plan for
  plywood", or any request to figure out where parts go on a sheet or how much material
  to buy, even if the word "nest" never appears.
metadata:
  version: "1.0"
  author: Samuel Cao
  created: "2026-09-04"
  last_updated: "2026-09-04"
  ai_update: Update last_updated and version under metadata. Append changelog at bottom.
---

# Cut-Sheet-Builder

Computes where every part sits on every sheet, how much stock to buy, and produces files a
student can cut from. Nothing is placed or sized by hand.

```
interview -> job JSON -> echo (confirm parts) -> build (nest + render + verify) -> deliver
```

---

## Why this skill exists (do not relearn)

1. **Compute, then render.** A packing function assigns every part an exact position and
   rotation. The renderer only draws computed positions. The trophy session's layout was
   hand-placed and came out off-scale with overlapping, inconsistent rectangles.
2. **One scale constant.** The reference render uses a single px-per-inch value for width
   and height, on every sheet. A rotated part is the same part transposed. The verifier
   re-measures the rendered SVG against that one constant, so a bad render fails loudly.
3. **A layout that fails validation is not delivered.** Someone may cut from it. The build
   command exits non-zero and the report says "DO NOT CUT" when any check fails.
4. **Never invent a default for cutting_method or sheet size.** Both are asked every job.
   A guillotine layout on a laser wastes material; a free layout on a table saw cannot be
   cut. The wrong sheet size makes every number wrong.
5. **Engrave does not mean locked.** `rotation` is its own toggle. Ask it per part.

---

## Dependencies

- `user-input-protocol` (intake), `revision-control` (naming), `sam-cao-style-guide` and
  `ai-tropes` (any prose in the summary handed back)
- Python: `shapely` (required), `ezdxf` (DXF in/out), `svgelements` (SVG in)
- Optional engines: `rectpack` (bounding-box), `pynest2d` (true-outline). When either is
  missing the bundled engine runs and the validation report flags it. Check with
  `python scripts/cut_sheet_builder.py deps`. See `references/engine_notes_v1.0.md` before
  promising packing density.

```bash
pip install shapely ezdxf svgelements
```

---

## Bundled assets

```bash
SKILL_DIR=/mnt/skills/user/cut-sheet-builder
[ -d "$SKILL_DIR/scripts" ] || \
  SKILL_DIR=$(dirname "$(find / -name SKILL.md -path '*cut-sheet-builder*' 2>/dev/null | head -1)")
CSB="python3 $SKILL_DIR/scripts/cut_sheet_builder.py"
```

| Asset | Path |
|---|---|
| CLI (echo, build, deps, presets) | `scripts/cut_sheet_builder.py` |
| Engine package | `scripts/cutsheet/` |
| Job file schema | `references/job_schema_v1.0.md` |
| Intake question set | `references/intake_questions_v1.0.md` |
| Engine and fallback notes | `references/engine_notes_v1.0.md` |
| Trophy regression job | `assets/examples/trophy_job_v1.0.json` |
| Irregular-outline job + SVG | `assets/examples/l_bracket_job_v1.0.json`, `l_bracket_v1.0.svg` |

---

## Workflow

### 1. Interview (always)

Run `user-input-protocol` with the question set in `references/intake_questions_v1.0.md`.
Ask in that order. `cutting_method` and sheet size are never defaulted; everything else has
a sensible default the file names, but confirm anything that changes material use (kerf,
margin, spacing mode, rotation policy for engraved or grained parts).

If the user pastes a parts table or uploads DXF/SVG files, extract what you can from the
conversation first and ask only the gaps.

### 2. Write the job JSON

Write `<job>_job_v1.0.json` following `references/job_schema_v1.0.md`. Keep imported
outline files next to it (relative `source.path`). Units: set `units.input` to whatever
the user typed in; the engine stores inches internally and converts back for display.

### 3. Echo and confirm

```bash
$CSB echo <job>_job_v1.0.json --out <outdir>
```

Show the printed parts table and the `_parts_echo_v1.0.svg` preview. For imports, point at
the `notes` column: it reports detected units, chained loops, cutouts, and any disjoint
outline that was ignored. Get a yes before nesting. A wrong dimension caught here costs
one message; caught at the laser it costs a sheet.

### 4. Build

```bash
$CSB build <job>_job_v1.0.json --out <outdir>
```

The command nests, renders, verifies, and writes every artifact. Read the validation block
it prints. If anything is FAIL, do not hand over the layout; fix the job or report the
defect. `PASS*` means passed but flagged (usually a fallback engine): say so in the summary.

`--no-determinism` halves runtime on big true-outline jobs by skipping the re-run check.
Use it only for iteration, never for the delivered build.

### 5. Deliver

Hand back, in this order: the reference SVG, the per-sheet cut files, the cut list, the
validation report. Summarize in prose: sheets needed (now vs deferred), rod length and bar
count, waste percentage, which engine ran and whether it was a fallback, and anything the
echo notes warned about. Write the summary in Sam's voice; no filler, no em dashes.

---

## Outputs (all versioned, all carry metadata + changelog)

| File | What it is |
|---|---|
| `<job>_reference_v1.0.svg` | To-scale, labeled, colored layout of every sheet with rulers, legend, rotation tags `(R90)`, deferred sheets hatched and titled DEFERRED |
| `<job>_sheetNN_cut_v1.0.svg` | Cut-ready: real units (`width="24in"`), hairline strokes, CUT and ENGRAVE layers, no labels or fills. `_deferred` in the name for deferred sheets |
| `<job>_sheetNN_cut_v1.0.dxf` | Same geometry as DXF (R2010, `$INSUNITS` set, y-up), layers CUT / ENGRAVE |
| `<job>_cut_list_v1.0.md` | Settings, stock summary, parts table, per-sheet placement table (x, y in decimals and nearest 1/16"), rod bars and offcuts |
| `<job>_validation_v1.0.md` / `.json` | Every check with pass/fail and detail, engine used, fallback flag |
| `<job>_layout_v1.0.json` | Machine-readable placements and outlines in inches |
| `<job>_parts_echo_v1.0.svg` | Confirmation preview (from `echo`) |

Coordinates in every file: x from the sheet's left edge, y from its TOP edge, to the part's
bounding-box corner. The DXF flips to y-up internally so it overlays the SVG correctly.

---

## Model in one screen

- **Two spacing dials, independent.** `outer_edge_margin` (sheet edge to nearest part) and
  `part_spacing.mode`: `kerf-gap` (one kerf between parts, the trophy model), `shared-edge`
  (zero gap, one shared cut line), `custom-margin` (a stated value).
- **Rod math.** n pieces of L need `n*L + (n-1)*kerf`. Trophy regression: 30 x 5.25 with
  1/8 kerf = 161.125 in. Bars via first-fit-decreasing; offcut excludes the final freeing cut.
- **Nest modes.** `bounding-box` packs rectangles (fast; MaxRects, or guillotine when
  `cutting_method` is guillotine). `true-outline` packs the real polygon with a rotation
  search and kerf-buffered overlap checks. Per-part `nest_mode` overrides are honored.
  Typed rectangles only ever rotate 0/90 (tilted rectangles help nothing and cannot be
  table-sawn). Guillotine cutting always packs bounding boxes; outlines still render.
- **Rotation.** `rotation: auto | locked` with `locked_angle`. `rotation_step` sets the
  search granularity for outlines (90 default; 15 packs tighter, slower).
- **Groups.** `group` on a part; `isolated_groups` get their own sheets; `deferred_groups`
  are isolated and numbered last, hatched and titled in the render, `_deferred` in filenames.
- **Determinism.** Fixed ordering (area desc, id, copy). Same input, same layout, checked.

---

## What the validation report proves

single scale constant (re-measured from the rendered SVG), outline fidelity (drawn area
equals real area / k^2), cross-part consistency (identical parts identical), no overlaps
(bbox or kerf-buffered polygon), inside the margin boundary, counts, area accounting,
sheet count, rod math re-derived independently, guillotine cut sequence exists (when
guillotine), group isolation and deferral order, determinism, and which engine ran.

---

## When to say no, or point elsewhere

- Density matters more than convenience (production runs, expensive stock) and the
  bundled outline nester ran: recommend Deepnest for the nest, then bring its result back
  for the cut list if useful. Say this plainly; do not oversell the fallback.
- Toolpaths, feeds/speeds, laser power, engraving artwork, cost optimization: out of scope.
- DTF gang sheets: raster artwork, not this skill.
- Multiple stock sizes in one run, mixed rod+sheet as one deliverable, engrave/cut layer
  detection on import: v1.x. Do the job in two passes today and say so.

---

## Edge cases worth remembering

- SVG with no physical `width`/`height` (viewBox only): units are ambiguous. Set
  `source.units` and confirm in the echo.
- DXF without `$INSUNITS`: assumed inches, flagged in the echo notes. Confirm.
- A file with several disjoint outlines: the largest is kept, the rest reported. If the
  user wanted a different one, split the file.
- Open paths that do not close within tolerance are skipped. If the echo shows no outline,
  the source path is not closed; ask for a closed export from Onshape.
- The reference SVG for a 4x8 sheet is large. Send it as a file, never inline.

---

## CHANGELOG
- v1.0 (2026-09-04): Initial release per cut_sheet_builder_prd_v1.1. Both nest modes, DXF/SVG import, two-dial spacing, rod packing, per-sheet cut files, validation report, acceptance tests.
