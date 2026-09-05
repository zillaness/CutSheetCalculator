---
file: piece_labeling_prd_v1.2.md
version: 1.2
author: Sam Cao
created: 2026-09-05
last_updated: 2026-09-05
description: PRD for piece labeling in cut-sheet-builder cut-ready files. Marks each piece with its id so identical parts can be told apart at assembly, with font and text size derived from a savable machine profile, output formats chosen separately from the machine, on-piece and beside-cutout placement, spacing coupling, explicit fallbacks, and validation. Signed off 2026-09-05; built in cut-sheet-builder v1.4.
ai_update: Update last_updated and version. Rename file to match. Append changelog at bottom.
---

# Piece labeling for assembly (cut-sheet-builder) — PRD v1.2, signed off and built

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
- Outline (filled) glyphs from a TrueType font via fontTools: the right shape for a laser
  raster pass (the laser fills the glyph). fontTools is already installed as an ezdxf
  dependency, pure Python, and runs under Pyodide. It needs a bundled font file because
  system fonts differ per machine and do not exist in the browser. Chosen for lasers in v1:
  one SIL-OFL sans font subset to the label character set (roughly 25 KB).
- Hershey fonts (public domain, 1967 US NBS): the standard single-line vector fonts used by
  CNC and plotter software. The Simplex (sans, one stroke) glyph set is about 95 printable
  ASCII glyphs of short polylines, roughly 12 KB as Python data. Chosen for routers in v1
  and as the laser "score" option.
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
- G-code or any toolpath output. A router job goes DXF (or SVG) into CAM (VCarve, Fusion,
  Carbide Create), which owns tool selection, depths, and post-processing. Direct G-code is a
  separate PRD, not a label feature. Same for a 3D file: the 2.5D work lives in its own
  project.
- Two-sided operations and the show-face concept (marking the down face by flipping the
  sheet, or steering labels off a visible face). Deferred with the whole outward-facing-face
  idea; v1.x.
- Barcodes or QR. A laser could do it; nobody scans plywood at assembly.
- Choosing feeds, depths, or power for the marking pass.

## 6. Users and cases

- Sam, cutting forty-odd similar plywood parts on a CNC router with a 1/8 in bit, sorting
  them into assemblies afterwards.
- Laser jobs with many near-identical acrylic or plywood parts.
- Students reading a piece off a bench and matching it to the cut list by id.

## 7. Design

### 7.1 Machine, outputs, and profiles

Machine and output format are different questions and are asked separately. The machine
sets what a legible mark is; the outputs are what files leave the build. A router job may
want DXF only (into CAM); a laser job SVG only; a hand job PDF only; any job can ask for all.

**Machine** (new job field `machine`, additive):

| value | marks with | label font default | label support |
|---|---|---|---|
| `laser` | raster fill or vector score on ENGRAVE | `outline` (raster) | yes |
| `router` | the marking tool on ENGRAVE, needs `marking_tool_diameter` | `single-line` | yes |
| `plasma` | no reliable marking | none | labels refused |
| `waterjet` | no reliable marking | none | labels refused |
| `hand` | pencil, from the printed cut sheet | reference render text | labels appear in the reference SVG and PDF only; cut files unchanged |

- `machine` is required whenever `labels.mode` is anything but `none`, and has no default.
  When `labels` is absent (every existing job) it is optional and unused, so nothing breaks.
- Intake asks `machine` on every job. It also drives the rotation-step guidance the intake
  already gives from a tool question.
- `router` with labels on requires `marking_tool_diameter`. No default.
- `plasma` and `waterjet` with labels on is a JobError naming the reason.
- `hand`: the reference render already labels every part; for hand jobs the label size
  follows `labels.cap_height` so it prints large enough to read on the sheet.

**Outputs** (new job field `outputs`, additive): list of `reference`, `svg`, `dxf`, `pdf`.
Default when absent is today's behavior (everything the environment can produce), so
existing jobs are unchanged. Intake asks which outputs the user wants; the answer is
recorded in the job, not inferred from the machine. Validation, layout JSON, and the cut
list are always written.

**Profiles** (new, additive): a machine profile is a named JSON object holding the fields
that describe a machine and its shop defaults, so they are entered once and reused:

```json
{
  "name": "shop_router_1_8",
  "machine": "router",
  "marking_tool_diameter": 0.125,
  "kerf": 0.25,
  "outer_edge_margin": 0.5,
  "part_spacing": { "mode": "custom-margin", "value": 0.25 },
  "rotation_step": 90,
  "labels": { "mode": "beside-cutout", "font": "single-line", "cap_height": 0.75 },
  "outputs": ["dxf", "pdf"]
}
```

A job references one with `"profile": "shop_router_1_8"`. Profile fields are the job's
defaults; any field set directly on the job overrides the profile. Profiles are looked up
in `cut-sheet-builder/assets/profiles/` (a few shipped examples: laser 24x18 raster, router
1/8 in, hand) and in a `profiles/` folder next to the job file. The web page lists shipped
profiles, applies one to the form, and can save the current form as a named profile in the
browser (localStorage) and export it as a JSON file for the repo folder. Same shape as the
2.5D project's savable profiles so the two stay familiar.

### 7.2 Text engine

Two fonts, one layout function, one output primitive. `labels.font` is `single-line` or
`outline`; the default comes from the machine (router: single-line, laser: outline) and can
be overridden per job (a laser can score single-line text when raster time matters).

- `single-line`: Hershey Simplex, vendored as a Python glyph table
  (`cutsheet/fonts/hershey_simplex.py`), public domain, about 95 glyphs. Layout returns open
  polylines in inches. Written as open paths on ENGRAVE (SVG) and open LWPOLYLINEs (DXF),
  exactly like imported engrave LineStrings today. Stroke width is the tool; the file is
  hairline.
- `outline`: one bundled SIL-OFL sans TrueType font, subset to the label character set
  (`cutsheet/fonts/label_sans_subset.ttf`, roughly 25 KB, license file alongside). Glyph
  outlines come out through fontTools, are flattened to the same chord tolerance the DXF
  importer uses, and become filled shapely Polygons (holes for counters). Written as filled
  closed paths on ENGRAVE (SVG, `fill` set so LightBurn and Glowforge treat them as raster
  fill) and closed LWPOLYLINEs on DXF (LightBurn fills closed shapes in fill mode; the cut
  list states which layer to set to fill). Text is never emitted as a `<text>` element or a
  DXF TEXT entity, so the verifier can measure exactly what will engrave.
- Both fonts share the layout code: string, cap height, letter spacing, orientation, anchor.
  Same code path feeds SVG, DXF, the reference render, and the browser page (pure Python plus
  fontTools, which Pyodide already installs as an ezdxf dependency).
- Character set: A-Z, a-z, 0-9, space, `- _ . / # :`. Other characters become `?` and the
  substitution is listed in the report.
- Orientation: `upright` (default) or `follow-part`.

Cost. Single-line: about 200 lines plus tests, no dependency. Outline: about 150 more lines,
one bundled font file with its license, and a subset step documented in build notes. Both
in v1 is roughly a day and a half of build. Raster-engraved outline text is what makes this
useful on the laser, and single-line is what makes it usable on the router, so v1 needs
both; neither is bolted on later.

### 7.3 Minimum text height

Derived, then reported. `cap_height` is what the user may set; the engine raises it to the
minimum when it is too small and says so.

| machine and font | minimum cap height | basis |
|---|---|---|
| laser, outline (raster) | 0.12 in (3 mm) | counters in `8`, `a`, `e` close up below this at typical raster line spacing; tunable `labels.laser_min_height` |
| laser, single-line (score) | 0.10 in (2.5 mm) | thinnest scored text that reads on plywood at arm's length; same tunable |
| router, single-line | `legibility_factor` x `marking_tool_diameter`, default factor 5 | one stroke is one tool width; a glyph needs at least four tool widths of interior clearance to read. Your 4x figure is the floor; 5 is the default because `8` and `B` need the extra. Tunable |
| router, outline | 8 x `marking_tool_diameter` | allowed but discouraged: filling glyphs with an endmill is slow and the counters need room. The echo warns when chosen |
| hand | 0.25 in | printed reference at the auto scale; must survive a photocopy |

Defaults for `cap_height` when unset: laser 0.20 in, router max(0.35 in, minimum), hand
0.35 in. Label width = cap_height x advance x character count (Simplex advance 0.85, the
outline font's own advances), reported per label.

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

Per-part visible-face handling (`show_face`, and the flipped `ENGRAVE_BACK` pass) is
deferred to v1.x with the outward-facing-face idea. In v1 the per-part override is the
tool for it: set `parts[].label.mode` to `beside-cutout` or `none` on any part whose up face
will show.

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
| plasma / waterjet | JobError | none |
| unsupported character | substitute `?` | none |

Every fallback or drop produces one report line: part, copy, sheet, requested mode, result,
reason. The build still passes validation when labels are dropped; the label section is
flagged (PASS*) like the engine fallback is today, because the layout is still safe to cut.
A label that overlaps a cut is a FAIL.

v1.x: `show_face` per part, and `face: back` emitting a mirrored `ENGRAVE_BACK` layer for a
second pass with the sheet flipped about its vertical axis, plus two registration marks in
the waste. Needs a design pass on registration before it is worth building.

### 7.7 Outputs

- Cut-ready SVG: labels on the ENGRAVE layer, `id="label-<part>#<copy>"`. Single-line as
  hairline open paths; outline as filled closed paths (`fill="#0000ff"`, no stroke) so laser
  software rasters them. Header comment changes from "no labels" to state the label mode,
  font, and text height.
- Only the formats in `outputs` are written (default: all available).
- Cut-ready DXF: same polylines as open LWPOLYLINEs on layer ENGRAVE. Optional
  `labels.dxf_layer` (default `ENGRAVE`) for CAM setups that want a separate `LABEL` layer.
- Reference SVG: the actual label polylines drawn thin and dark on each part, in addition
  to the existing text label (which keeps rotation and dims). What you see is what marks.
- PDF cut sheet: inherits the reference render.
- Layout JSON: per placement, `label: {mode, text, cap_height, x, y, angle, face}` or
  `label: null` with `label_reason`.
- Cut list: a Labels section: profile, machine, tool, font, derived minimum, count by
  outcome, and for lasers the instruction "set layer ENGRAVE to fill (raster)" or "to line
  (score)" matching the font.

### 7.8 Validation report additions

- `labels: machine, font, and minimum height`: profile name, machine, tool diameter, font,
  factor, derived minimum, requested height, effective height.
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
  "profile": "shop_router_1_8",
  "machine": "router",
  "marking_tool_diameter": 0.125,
  "outputs": ["dxf", "pdf"],
  "labels": {
    "mode": "beside-cutout",
    "font": "single-line",
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
      "label": { "mode": "beside-cutout", "text": "SHELF-L" } }
  ]
}
```

`labels.text`: `id` (default) | `id+copy`. `parts[].label.text` replaces the text for one
part (edit the id on the piece without renaming the part everywhere). `id+copy` labels
identical pieces `A#1`, `A#2` for jobs where copies differ later (drilling, finish).
Reference-render extras like `(R90)` never go on the piece. Profile fields listed in 7.1 are
all valid job fields too; the job wins on conflict.

## 8. Scope by phase

v1

- `machine`, `marking_tool_diameter`, `outputs`, `profile`, `labels` job fields and
  `parts[].label`.
- Machine profiles: shipped examples, job-folder lookup, override rules, web page apply/save/export.
- Vendored Hershey Simplex single-line font, bundled OFL sans subset for outline text, one
  text layout function.
- Minimum height derivation, on-piece and beside-cutout placement, spacing bump, fallbacks.
- ENGRAVE output on SVG and DXF, reference render, layout JSON, cut list section.
- Validation checks in 7.8.
- Web page: profile picker, machine select, tool diameter, outputs checkboxes, label mode,
  font, cap height; per-part label mode and text; save/export profile.
- Intake question set: machine and outputs always asked; tool diameter, font, and label
  questions when relevant; skill docs and schema reference updated.
- Acceptance tests in section 12.

v1.x

- `show_face` per part and the `ENGRAVE_BACK` mirrored layer with registration marks.
- Separate `LABEL` layer default if CAM workflows prefer it.
- More shipped profiles as machines get used.

## 9. Constraints

- Revision-control conventions on every new and touched file.
- Job schema stays backward compatible; every new field is additive and optional unless a
  label feature is on.
- Trophy and L-bracket acceptance jobs and the full pytest suite pass unchanged when
  `labels` is absent.
- No artwork beyond text. No new runtime dependency: the single-line font is vendored data
  and the outline font is read with fontTools, which ezdxf already requires.
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
2. Laser, on-piece, outline font, L-bracket x 12 at 90 deg steps: every label sits inside
   its L, labels on R180 copies stay upright, the inside-part check passes, the ENGRAVE layer
   of the cut SVG holds filled closed paths (counters as holes) and the DXF holds closed
   LWPOLYLINEs, one group per copy. The same job with `font: single-line` produces open
   paths instead and the same placements.
3. Fallback disclosure: a 0.5 x 0.5 in part on a router with a 1/8 in tool cannot hold a
   0.625 in label; on-piece falls back to beside-cutout; with `auto_spacing: false` and
   kerf-gap it falls to drop; the report lists both with reasons and flags PASS*.
4. Refusal: `machine: plasma` with labels on is a JobError; the same job with
   `labels.mode: none` builds.
5. Backward compatibility: trophy and L-bracket jobs produce byte-identical outputs to
   today's (except header date) with no `labels` field; full suite green.
6. Determinism: the labeled router job re-runs to identical label coordinates.
7. Profiles: a job with `profile: shop_router_1_8` and no machine fields builds with the
   profile's tool, kerf, spacing, font, and outputs; setting `kerf` on the job overrides the
   profile's; an unknown profile name is a JobError listing the available names.
8. Outputs: `outputs: ["dxf"]` writes the DXF, layout JSON, cut list, and validation, and no
   SVG or PDF; `outputs` absent writes everything as today.
9. Hand: `machine: hand` with labels on leaves cut files byte-identical to unlabeled output
   and enlarges the reference-render labels to the requested cap height.

## 13. Decisions

Resolved in Sam's v1.0 review (2026-09-05):

1. Fonts: both in v1. Outline (raster) for lasers, single-line for routers, overridable.
2. Machine and output format are separate questions, both asked at intake. `outputs` is a
   job field. G-code and 3D output are out of scope for this PRD.
3. Router legibility factor 5 with 4 as the floor; laser minimums per 7.3.
4. Fallback chain beside-cutout -> on-piece -> drop, each disclosed. (Taken as accepted; see
   the one confirmation below.)
5. Auto spacing on by default, bump printed at echo time. Savable machine profiles added.
6. Default label text is the id; per-part text override to edit what goes on a piece.
7. Show-face and down-face marking deferred to v1.x with the outward-facing-face idea.

Closed at go (2026-09-05): labels are opt-in (`labels.mode` defaults to `none`; use them only
when parts are similar enough to confuse and a mark is acceptable); fallback chain as stated;
outline font is a subset of Liberation Sans renamed Label Sans (SIL OFL); starter profiles
`laser_24x18_raster`, `router_1_8`, `hand` shipped with placeholder numbers marked as such.

Built as specified with one refinement found in testing: the beside-cutout corridor is text
height + 2 pads + kerf (the cut eats kerf/2 into the waste on each side), and the clearance
check grows the label box by pad + kerf/2 against raw outlines. Section 7.5's formula is
superseded by that.

## CHANGELOG
- v1.0 (2026-09-05): Initial draft for sign-off.
- v1.1 (2026-09-05): After Sam's review. Outline font for laser raster added to v1 beside single-line for routers; machine and outputs decoupled with an `outputs` job field; savable machine profiles; per-part label text; hand jobs label the reference/PDF only; G-code and 3D output named as out of scope; show_face and ENGRAVE_BACK deferred to v1.x; acceptance tests 7-9 added.
- v1.2 (2026-09-05): Signed off. Decisions closed; corridor formula corrected to include the kerf; marked as built.
