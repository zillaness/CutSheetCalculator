---
file: piece_labeling_prd_v1.0.md
version: 1.0
author: Sam Cao
created: 2026-09-05
last_updated: 2026-09-05
description: PRD for piece labeling in cut-sheet-builder cut-ready files. Marks each piece with its id so identical parts can be told apart at assembly, with text size derived from the cutting machine, on-piece and beside-cutout placement, spacing coupling, explicit fallbacks, and validation. Draft for sign-off; nothing built.
ai_update: Update last_updated and version. Rename file to match. Append changelog at bottom.
---

# Piece labeling for assembly (cut-sheet-builder) — PRD v1.0, draft for sign-off

## 1. Problem

The reference SVG labels every part, but the cut-ready SVG/DXF files carry no labels (their
header comment says "no labels"). Once a sheet is broken down, forty similar plywood pieces
are anonymous. Sorting them at assembly means measuring each one against the cut list.

Goal: the cut files mark each piece with its id, sized so the marking is legible on the
machine that will make it, placed where it will not mar a visible face, and never colliding
with a cut or another label. Anything the tool cannot deliver is disclosed in the validation
report, not silently dropped.

## 2. What exists today (verified in the repo, not to be rediscovered)

- `render_cut_svg` (render.py:258) emits a red CUT layer and a blue ENGRAVE layer as Inkscape
  layers; `write_cut_dxf` (render.py:294) emits the same on DXF layers CUT and ENGRAVE.
- The ENGRAVE layer already carries real geometry: engrave/score paths detected on import
  travel with the part through rotation and placement as shapely Polygons and LineStrings
  (`Placement.engrave`), and are written as SVG paths and open or closed LWPOLYLINEs. Open
  polylines on ENGRAVE are exactly the primitive a single-line label needs.
- `Job.engrave_layer` is `none | outline-guide` (model.py:178). `outline-guide` copies
  engrave-flagged part outlines onto ENGRAVE as an alignment aid. When no engrave geometry
  exists the layer holds the comment "Paste engrave artwork here. Empty on purpose"
  (render.py:287). Text labels would be the first artwork this skill generates. That is a
  deliberate scope change, stated here so it is signed off rather than slipped in.
- `Part` has `id`, `engrave` (bool; informational, or auto-set when an engrave layer is
  imported), `notes`, `group`, `color`, `rotation`, `locked_angle`, `rotation_step`.
- The reference render builds its label at render.py:191 as `part_id` plus `(R<deg>)` when
  rotated, plus `w x h` when the box is big enough. That string builder gets factored into one
  function used by both renders; the cut-file label uses the id part only by default.
- Spacing is two independent dials: `outer_edge_margin` and `part_spacing` (`kerf-gap`,
  `shared-edge`, `custom-margin`). Nesting inflates every outline by gap/2; verification
  checks the same buffered geometry.
- Validation already discloses which engine ran and every fallback. Label reporting follows
  the same pattern.
- `cutting_method` is `free | guillotine`. It is cut topology. Nothing in the job says what
  machine does the cutting.

Verified at PRD time: ezdxf 1.4.4 ships no font files. Asking its font API for a stroke font
(`txt.shx`) silently falls back to a system TrueType outline font. So single-line text is
not available from any current dependency; it has to be bundled.

## 3. What already exists elsewhere, and why not use it

- DXF `TEXT`/`MTEXT` entities: the CAM program renders them with its own font at cut time.
  Rendering differs per program, single-line vs outline is out of our control, and the
  verifier could not measure what will be cut. Rejected. Labels are emitted as explicit
  polylines, same as every other line in the file.
- ezdxf `text2path` (outline text via fontTools): works, but produces filled outline glyphs,
  the wrong shape for a router and heavier for a laser. Kept as the v1.x outline-font option
  when someone wants nicer laser text.
- Hershey fonts (public domain, 1967 US NBS): the standard single-line vector fonts used by
  CNC and plotter software. The Simplex (sans, one stroke) glyph set is about 95 printable
  ASCII glyphs of short polylines, roughly 12 KB as Python data. Chosen for v1.
- LightBurn, VCarve, Fusion: all can add text at the machine. Manual, per job, per machine,
  not versioned, and the operator has to know which piece is which. The whole point is to
  not do that forty times.

## 4. Goals and success criteria

- Every placed piece carries its id in the cut file, or the report says exactly why not.
- Text height is derived from the machine and marking tool, never a bare default. The
  report states the height, the minimum, and the assumption that produced the minimum.
- On-piece labels sit inside the outline with a stated inset; beside-cutout labels sit in
  waste, clear of every part and every other label by at least the kerf buffer. Both are
  verified geometrically in the report, the same way overlaps are today.
- Beside-cutout never silently collides or clips: spacing is raised to fit when allowed, and
  otherwise the label follows a documented fallback with the reason listed.
- Existing jobs (trophy, L-bracket, every test) build unchanged when `labels` is absent.
- The web page gets the same controls (machine, tool, label mode) with no separate logic.
- Determinism holds: same job, same labels, same coordinates.

## 5. Non-goals (v1)

- Any artwork other than id text: no logos, no decoration, no dims, no arrows.
- Outline (filled) fonts. v1.x via ezdxf text2path if wanted for lasers.
- Two-sided operations (marking the down face by flipping the sheet). See 7.6; v1.x.
- Barcodes or QR. A laser could do it; nobody scans plywood at assembly.
- Choosing feeds, depths, or power for the marking pass.

## 6. Users and cases

- Sam, cutting forty-odd similar plywood parts on a CNC router with a 1/8 in bit, sorting
  them into assemblies afterwards.
- Laser jobs with many near-identical acrylic or plywood parts.
- Students reading a piece off a bench and matching it to the cut list by id.

## 7. Design

### 7.1 Machine model (the gap that matters most)

New job field `machine`, additive:

| value | marks with | label support |
|---|---|---|
| `laser` | vector engrave (or score) pass on ENGRAVE | yes |
| `router` | the marking tool on ENGRAVE, needs `marking_tool_diameter` | yes |
| `plasma` | no reliable marking | labels refused |
| `waterjet` | no reliable marking | labels refused |
| `hand` | pencil from the printed reference; the cut file is not read by a machine | labels drawn in the reference render only, cut files unchanged |

Rules:

- `machine` is required whenever `labels.mode` is anything but `none`. It has no default.
  When `labels` is absent (every existing job), `machine` is optional and unused by the
  engine, so nothing breaks. This matches the cutting_method convention where it matters
  (labels cannot be sized without it) without invalidating existing job files.
- Intake asks `machine` on every job from now on. It also improves the rotation-step
  guidance, which today is derived from a tool question the intake already asks.
- `router` with labels on requires `marking_tool_diameter` (job units). No default; a wrong
  guess produces mush at the machine.
- `plasma` and `waterjet` with labels on is a JobError naming the reason. Set `labels.mode`
  to `none` or change the machine. Refusing is the honest answer per the brief.

Recommendation on the convention question: do not make `machine` required for every job.
It would break backward compatibility (constraint) for a field that only matters to labels,
kerf hints, and rotation guidance. Ask it every time; require it in the schema only when a
feature depends on it.

### 7.2 Text engine

- Single-line font: Hershey Simplex, vendored as a Python glyph table
  (`cutsheet/fonts/hershey_simplex.py`), public domain, about 95 glyphs. One layout function
  turns a string and a cap height into a list of polylines in inches; the renderer places
  them exactly like imported engrave LineStrings. Same code path feeds SVG, DXF, the
  reference render, and the browser page (pure Python, no new dependency, runs in Pyodide).
- Character set: A-Z, a-z, 0-9, space, `- _ . / # :`. Any other character in a label is
  replaced by `?` and the substitution is listed in the report. Ids are already free-form,
  so this is disclosure, not a new restriction.
- Stroke width is the tool: hairline in the file, cut with the marking tool. The text engine
  never fills.
- Orientation: `upright` (readable from the sheet's top edge, default) or `follow-part`
  (rotates with the part). Assembly reads a loose piece, so upright is enough; follow-part
  exists for parts with a natural "up".

Cost of requiring single-line for v1 (the open question): vendoring one glyph table plus
the layout function is roughly 200 lines and one test file, zero dependencies, and the
output primitive already exists on the ENGRAVE layer. Outline text would cost more (a
bundled TTF or a system-font dependency, curve flattening, fill semantics per machine) and
would be wrong for routers. Requiring single-line is the cheaper path, and it makes laser
and router share one code path. Recommendation: single-line only in v1, outline fonts v1.x.

### 7.3 Minimum text height

Derived, then reported. `cap_height` is what the user may set; the engine raises it to the
minimum when it is too small and says so.

| machine | minimum cap height | basis |
|---|---|---|
| laser | 0.10 in (2.5 mm) | thinnest single-line text that reads on plywood at arm's length; tunable `labels.laser_min_height` |
| router | `legibility_factor` x `marking_tool_diameter`, default factor 5 | one stroke is one tool width; a glyph needs at least four tool widths of interior clearance to read. Your 4x figure is the floor; 5 is the default because `8` and `B` need the extra. Tunable |

Defaults for `cap_height` when unset: laser 0.15 in, router max(0.35 in, minimum). Width of
a label = cap_height x 0.85 x character count (Simplex advance), reported per label.

### 7.4 Placement modes

Job default `labels.mode`, per-part override `parts[].label.mode`:

1. `on-piece`: inside the outline. Anchor at the same interior point the reference render
   uses (centroid, or a representative interior point when the centroid is outside, as with
   an L). Try orientation 0 then 90. The text box inset by `on_piece_inset` (default = one
   tool diameter on a router, one kerf on a laser, minimum 0.05 in) must be covered by the
   part polygon minus its holes. If it does not fit at the requested height, shrink toward
   the minimum in 10% steps; if it does not fit at the minimum, apply the fallback.
2. `beside-cutout`: in the waste next to the part. Candidate strips in order: below, right,
   above, left of the part's bounding box, each `gap` wide (see 7.5), text run along the
   strip. The text box buffered by gap/2 must not intersect any placed part's buffered
   outline, any other label's box, or the outer margin. First fit wins. No fit: fallback.
3. `none`.

Per-part `show_face`: `none` (default) | `up` | `down` | `both`. Meaning: which face of
this part is visible in the finished thing, with `up` being the face that is up on the
sheet as cut. Effect on `on-piece`: `up` or `both` downgrades the label to `beside-cutout`
(a permanent mark would show), listed in the report as a downgrade with the reason; `down`
or `none` keeps `on-piece`. Marking the down face directly needs a flip operation and a
mirrored `ENGRAVE_BACK` layer with registration; that is v1.x (7.6), not silently attempted.

### 7.5 Coupling to spacing (the resource labels and kerf share)

A beside-cutout label lives in the corridor between parts. The corridor width is `gap`
from `part_spacing`. So:

- `label_clearance = cap_height + 2 x clearance_pad` (pad default 0.06 in, tunable). This is
  the corridor a beside-cutout label needs.
- `labels.min_spacing` (tunable, default 0): a floor the user can set on the effective gap
  regardless of text.
- `labels.auto_spacing` (default `true`): when mode is `beside-cutout` for any part, the
  effective gap becomes `max(gap, min_spacing, label_clearance)` before nesting. The echo
  step prints the bump ("part spacing raised from 0.125 in to 0.42 in for beside-cutout
  labels"), and the report repeats it with the utilization it cost. Nothing is raised when
  every part is `on-piece` or `none`.
- `auto_spacing: false`: spacing stays as set; labels that do not fit follow the fallback.
  For a user who would rather lose a label than a sheet.
- Shared-edge spacing (gap 0) with beside-cutout and auto_spacing off is a JobError with
  the reason: there is no waste to write in.

Density cost is real: on the trophy job a 0.42 in gap instead of 0.125 in is roughly one
extra sheet in five. The report shows the number so the choice is visible.

### 7.6 Fallback policy (never silent)

| situation | default fallback | override |
|---|---|---|
| beside-cutout does not fit | try on-piece; if that fails, drop | `labels.fallback: drop` to skip on-piece |
| on-piece does not fit at minimum height | try beside-cutout; if that fails, drop | `labels.fallback: drop` |
| show_face up or both with on-piece | beside-cutout | none; this one is a safety rule |
| plasma / waterjet | JobError | none |
| unsupported character | substitute `?` | none |

Every fallback or drop produces one report line: part, copy, sheet, requested mode, result,
reason. The build still passes validation when labels are dropped; the label section is
flagged (PASS*) like the engine fallback is today, because the layout is still safe to cut.
A label that overlaps a cut is a FAIL.

v1.x: `face: back` emits a mirrored `ENGRAVE_BACK` layer for a second pass with the sheet
flipped about its vertical axis, plus two registration marks in the waste. Needs a design
pass on registration before it is worth building.

### 7.7 Outputs

- Cut-ready SVG: label polylines on the ENGRAVE layer, `id="label-<part>#<copy>"`, hairline,
  no fill. Header comment changes from "no labels" to state the label mode and text height.
- Cut-ready DXF: same polylines as open LWPOLYLINEs on layer ENGRAVE. Optional
  `labels.dxf_layer` (default `ENGRAVE`) for CAM setups that want a separate `LABEL` layer.
- Reference SVG: the actual label polylines drawn thin and dark on each part, in addition
  to the existing text label (which keeps rotation and dims). What you see is what marks.
- PDF cut sheet: inherits the reference render.
- Layout JSON: per placement, `label: {mode, text, cap_height, x, y, angle, face}` or
  `label: null` with `label_reason`.
- Cut list: a Labels section: mode, machine, tool, derived minimum, count by outcome.

### 7.8 Validation report additions

- `labels: machine and minimum height`: machine, tool diameter, factor, derived minimum,
  requested height, effective height.
- `labels: placement per part`: counts by outcome (on-piece, beside-cutout, downgraded,
  dropped) with the per-part list of downgrades and drops and their reasons. PASS* when
  anything was downgraded or dropped.
- `labels inside their part` (on-piece): every label box, inset, covered by its part polygon
  minus holes. FAIL otherwise.
- `labels clear of cuts and each other` (beside-cutout): every label box buffered by gap/2
  is disjoint from every part's buffered outline, every other label, and the margin. FAIL
  otherwise.
- `label spacing bump`: effective gap vs configured gap, and utilization delta, when
  auto_spacing raised it.
- `label charset`: substitutions, if any.

### 7.9 Schema additions (all additive)

```json
{
  "machine": "router",
  "marking_tool_diameter": 0.125,
  "labels": {
    "mode": "beside-cutout",
    "text": "id",
    "cap_height": 0.5,
    "orientation": "upright",
    "auto_spacing": true,
    "min_spacing": 0,
    "clearance_pad": 0.06,
    "on_piece_inset": 0.125,
    "legibility_factor": 5,
    "fallback": "on-piece",
    "dxf_layer": "ENGRAVE"
  },
  "parts": [
    { "id": "shelf", "width": 30, "height": 11.25, "quantity": 6,
      "show_face": "up",
      "label": { "mode": "beside-cutout", "text": "shelf-L" } }
  ]
}
```

`labels.text`: `id` (default) | `id+copy` | custom string per part via `parts[].label.text`.
`id+copy` labels identical pieces `A#1`, `A#2` for jobs where copies differ later (drilling,
finish). Reference-render extras like `(R90)` never go on the piece.

## 8. Scope by phase

v1

- `machine`, `marking_tool_diameter`, `labels` job fields and `parts[].label`, `show_face`.
- Vendored Hershey Simplex single-line font and text layout.
- Minimum height derivation, on-piece and beside-cutout placement, spacing bump, fallbacks.
- ENGRAVE output on SVG and DXF, reference render, layout JSON, cut list section.
- Validation checks in 7.8.
- Web page: machine select, tool diameter, label mode, cap height; per-part label mode.
- Intake question set: machine always asked; tool diameter and label questions when
  relevant; skill docs and schema reference updated.
- Acceptance tests in section 12.

v1.x

- Outline text via ezdxf text2path for lasers.
- `ENGRAVE_BACK` mirrored layer with registration marks for down-face labels.
- Separate `LABEL` layer default if CAM workflows prefer it.

## 9. Constraints

- Revision-control conventions on every new and touched file.
- Job schema stays backward compatible; every new field is additive and optional unless a
  label feature is on.
- Trophy and L-bracket acceptance jobs and the full pytest suite pass unchanged when
  `labels` is absent.
- No artwork beyond text. No new runtime dependency (the font is vendored data).
- The web page must keep working under Pyodide, so no compiled dependency.

## 10. Risks and mitigations

- Router legibility factor is a judgment number. Mitigation: it is tunable, reported, and
  the first real router job should cut one test label before forty.
- Beside-cutout on true-outline nests: an interlocked neighbor may occupy the strip below a
  bounding box. Mitigation: placement checks real buffered geometry, not boxes, and falls
  back per policy with the reason listed.
- Spacing bump surprises the user with an extra sheet. Mitigation: echo prints the bump
  before nesting; the report shows the utilization cost; `auto_spacing: false` exists.
- Hershey glyph quality is plain. Mitigation: it is the industry norm for engraving; outline
  fonts are v1.x for anyone who wants pretty.
- The label anchor for odd outlines lands in a thin region. Mitigation: shrink-then-fallback
  with disclosure; never a label crossing a cut, because that is a FAIL.

## 11. Skill and page changes

- Intake: ask machine on every job; ask tool diameter when router; ask label mode, show
  faces for visible parts, and text height only when labels are on.
- SKILL.md: the "no artwork" rule becomes "no artwork except id labels, and only when asked".
- job_schema and engine_notes references gain the fields and the derivation table.
- Web page: three new controls in Options, one per-part select, one per-part show-face
  select. The engine bundle carries the font.

## 12. Acceptance tests

1. Router, beside-cutout: 12 rectangles, 1/8 in tool, kerf-gap 0.125. Effective gap is
   raised to 0.745 in (0.625 min height + 2 x 0.06), the echo and report say so, every part
   gets a label in a strip, and the clearance check passes.
2. Laser, on-piece, L-bracket x 12 at 90 deg steps: every label sits inside its L, labels on
   R180 copies stay upright, the inside-part check passes, and the ENGRAVE layer of the cut
   SVG and DXF holds one polyline group per copy.
3. Fallback disclosure: a 0.5 x 0.5 in part on a router with a 1/8 in tool cannot hold a
   0.625 in label; on-piece falls back to beside-cutout; with `auto_spacing: false` and
   kerf-gap it falls to drop; the report lists both with reasons and flags PASS*.
4. Refusal: `machine: plasma` with labels on is a JobError; the same job with
   `labels.mode: none` builds.
5. Backward compatibility: trophy and L-bracket jobs produce byte-identical outputs to
   today's (except header date) with no `labels` field; full suite green.
6. Determinism: the labeled router job re-runs to identical label coordinates.

## 13. Decisions needed for sign-off

1. Single-line only in v1 (recommended, cheaper than the alternative), outline fonts v1.x.
2. `machine` required only when labels are on (recommended, keeps old jobs valid); ask it
   at intake every time regardless.
3. Legibility factor 5 by default for routers (your 4 as the floor), laser minimum 0.10 in.
4. Default fallback chain beside-cutout -> on-piece -> drop, with `fallback: drop` to
   short-circuit; `show_face: up | both` always pushes on-piece to beside-cutout.
5. `auto_spacing` on by default, with the bump printed at echo time.
6. Default label text = id only; `id+copy` opt-in.
7. Down-face labels via a flipped `ENGRAVE_BACK` pass deferred to v1.x.

## CHANGELOG
- v1.0 (2026-09-05): Initial draft for sign-off.
