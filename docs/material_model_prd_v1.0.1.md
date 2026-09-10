---
file: material_model_prd_v1.0.1.md
version: 1.0.1
author: Sam Cao
created: 2026-09-10
last_updated: 2026-09-10
description: PRD for the material model in cut-sheet-builder: factory edges and corners as an assignable resource, grain direction as a rotation constraint, roll stock with run-length reporting, edge banding as a size convention, and kerf presets by cutting tool. Draft for sign-off; nothing built yet.
ai_update: Update last_updated and version. Rename file to match. Append changelog at bottom.
---

# Material model (factory edges, grain, roll, banding, kerf presets) — PRD v1.0, draft for sign-off

First of three PRDs. This one lands the material concept because the other two sit on top of
it. PRD 2 is 1D upgrades (miters, bevels, cross-section symmetry, end pieces). PRD 3 is
quantity intelligence (max fit, minimum counts with spare enumeration, per-part priority).

Priority within this PRD, per the requester: factory edge and corner first, grain second,
roll third, banding last. Banding stays in scope only because it reuses the factory-edge
per-edge mechanic and is close to free once that exists.

## 1. Problem

A job today is pure geometry. `sheet` is an anonymous rectangle. A part is an outline plus a
quantity plus a rotation policy. Nothing in the job says what the stock *is*, so four real
constraints have no way to be expressed, and all four fail for the same reason.

- **Factory edge.** A part that needs a genuinely straight or square reference edge (a face
  frame, a drawer side, anything that mates) should be assigned a factory edge of the sheet.
  Today the packer will happily bury it in the middle of the sheet, and every edge it gets is
  a saw cut whose squareness depends on the cut before it.
- **Grain.** Plywood and veneer have a long-grain direction. Rotating a part 90 degrees is
  free to the packer and wrong in the shop: it changes appearance and it changes stiffness.
  `rotation: "locked"` is the only lever, and it pins a part to one absolute angle rather than
  expressing "grain must run this way," so it also blocks the 180 degree flip that is always
  legal.
- **Roll stock.** Vinyl comes on a roll: fixed width, effectively open length. Stock is
  modeled as a closed rectangle, so a roll has to be faked as an arbitrarily long sheet, and
  the number that actually matters (linear yardage consumed) is never computed.
- **Edge banding.** A banded edge changes finished size by the banding thickness. There is no
  place to say which edges are banded, and no stated convention for whether a declared part
  size is the finished size or the cut size. Getting that wrong is a silent error on every
  part in the job.

Fifth, smaller, and unrelated to material but bundled here because it is a one-sitting change
to the same intake path: **kerf is a single hand-entered number with no tool presets.** A user
who says "table saw" should get 0.125 offered, not have to remember it.

## 2. What exists today (verified in the repo, not to be rediscovered)

- `Stock` (model.py:163) is `width`, `height`, `quantity`, `preset`. No edges, no grain, no
  kind, no thickness. `Job.stocks` is a priority-ordered list, last entry unlimited, and parts
  too big for an early stock fall through to a later one (model.py:483). Offcuts-first is
  already the idiom, and an offcut is exactly the case where some factory edges are gone.
- `Part` (model.py:99) carries `rotation` (`auto` / `locked`), `locked_angle`, and
  `rotation_step`. `Part.allowed_angles` (model.py:137) is the single choke point for rotation
  policy: locked returns exactly one angle, rectangles return base and base+90 in every mode,
  outlines return the step grid. **A grain constraint is a filter on the list this function
  returns and nothing more.** That is the cheapest correct place to put it.
- `outer_edge_margin` is one scalar applied to all four sides. It exists because the outside
  of a sheet may be damaged, which is the same physical question factory edges answer, from
  the opposite direction.
- `part_spacing` is an independent dial (`kerf-gap`, `shared-edge`, `custom-margin`). Nesting
  inflates every outline by gap/2 and verification re-checks the same buffered geometry.
- Packers: bundled deterministic MaxRects and guillotine (pack_rect.py:52, :103), a `rectpack`
  wrapper (pack_rect.py:173), a shapely greedy nester with slide-to-anchor (pack_poly.py:74),
  and `pynest2d`. `pack_rectangles` and `nest_outlines` both already accept `sheet_w`,
  `sheet_h` and a sheet cap and both already return unplaced instances.
- The validation report always names the engine that ran and lists every fallback
  (verify.py:311, layout.py:82). The labeling feature extended that into a full
  downgrade-and-disclose chain. **Every fallback in this PRD follows that same pattern: never
  silent, always in the report, with the reason.**
- `pack_1d.py` already charges one kerf between adjacent cuts and packs bars first-fit
  -decreasing. Kerf in 1D is done; only the presets are new.
- `machine` (`laser`, `router`, `plasma`, `waterjet`, `hand`) drives label legibility and font
  and nothing else. Nothing in the job says what tool makes the *cut*.
- `units.py` converts in / ft / mm / cm / m / px / pt to a base of inches; `DISPLAY_UNITS` is
  in / ft / mm / cm. There is no yard, and `m` is convertible but not a display unit.

## 3. What exists elsewhere, and why not use it

- **Cabinet optimizers (Cutlist Optimizer, OptiCut, CutList Plus).** These do have grain and
  banding, and for a straight cabinet BOM out of rectangular panels they are better than this
  tool and should be recommended as such. What they do not do: true-outline nesting of
  irregular parts, cut-ready SVG/DXF with engraved piece labels, rod math, or being driven
  from a versioned job file. Take the concepts, not the tool.
- **Deepnest / SVGnest.** Best-in-class irregular nesting, no material model at all. Still the
  right answer when raw density beats everything else, as PRD v1.1 section 3 already says.
- **Rolling our own geometry.** No. shapely is already the substrate and handles every
  operation this PRD needs.

## 4. Goals and success criteria

1. A part can require a factory edge, or a factory corner (two perpendicular factory edges),
   and the layout either satisfies it or says in the validation report exactly which pieces it
   could not satisfy and why.
2. Stock declares which of its own edges are factory, so an offcut is described truthfully and
   a new sheet is not.
3. A part can require grain along, across, or either, and no placement in the output violates
   it. A grain requirement that cannot be met with the part's rotation policy is a hard error
   at load time, not a silent pass.
4. Roll stock is a first-class kind: fixed width, open length, packed toward one end, with
   consumed run length reported in the display unit plus yards and meters.
5. Banded edges are declarable, and the job states without a default whether declared part
   sizes are finished or cut sizes.
6. Kerf can be filled from a cutting-tool preset and overridden by hand at any time, in 2D and
   in 1D.
7. **A job file that predates this PRD produces byte-identical output.** Enforced by test, not
   by intention. This is the same rule labeling shipped under (`labels.mode` default `none`).

## 5. Non-goals (v1)

- Cost, pricing, vendor SKUs, or inventory tracking of any kind. Material is a constraint
  model, not a purchasing system.
- Species, finish, or veneer libraries.
- Detecting grain from a photo, a scan, or a file.
- Structural analysis. Grain here is a placement constraint, not an engineering calculation,
  and the tool must not imply otherwise.
- Two-sided operations and the show-face concept. Still deferred with the labeling PRD. This
  PRD builds the per-edge and per-face plumbing show-face will need, and deliberately stops
  short of delivering it.
- Banding application: glue, trimming, ordering banding material, banding waste.
- Toolpath or cut-ordering optimization for roll cutters and plotters.
- Grain matching or sequencing across parts (bookmatching, running a veneer pattern across a
  set of doors). Real, out of scope, noted in v1.x.

## 6. Users and cases

- Sam breaking down a 4x8 sheet where the two factory edges are the only edges he trusts, and
  the first rip destroys one of them.
- Robotics and trophy parts where a mating edge has to be square to something else.
- Vinyl on a 24 inch roll, where the deliverable is "buy this many yards."
- Cabinet-adjacent parts with banding on the front edge only.

## 7. Design

### 7.1 The `materials` block

New optional top-level `materials`, a list of objects each with an `id`. Stock entries and
parts reference a material by id. Everything is optional; a job with no `materials` behaves
exactly as it does today.

| Field | Default | Notes |
|---|---|---|
| `id` | required | Referenced by `sheets[].material` and `parts[].material` |
| `kind` | `sheet` | `sheet`, `bar`, or `roll` |
| `grain` | `none` | `none`, `length`, or `width`. The axis in the stock's own frame |
| `thickness` | none | Informational in v1; consumed by PRD 2 and by show-face later |
| `banding_thickness` | none | Per-edge allowance when an edge is banded |
| `default_factory_edges` | `all` for `sheet` | `all`, `none`, or a list. The default for stock of this material that does not say otherwise |

Resolution order for any material-derived value: explicit field on the part or stock, then the
material, then the job, then the built-in default. Same precedence the `profile` mechanism
already uses.

### 7.2 The per-edge mechanic (shared by factory edge and banding)

Both features attach attributes to *an edge of a part*, so they share one addressing scheme.

Edges are named in the part's base (unrotated) orientation as `left`, `right`, `top`,
`bottom`. For a typed rectangle these are unambiguous. For an imported outline, v1 defines
them as the four sides of the part's bounding box, and an edge is only addressable when the
outline actually runs along that side of its bounding box within a tolerance. An outline with
no straight side there gets a load-time error naming the part and the edge, rather than a
guess. Curved or angled reference edges are a v1.x problem and are called out as such.

Stock gains `factory_edges`: which of its own four sides are known straight, as `all`, `none`,
or a list of `left` / `right` / `top` / `bottom`. A **factory corner** is not a separate
declaration; it is the intersection of two adjacent factory edges, and it is scarce: at most
one part can own a given corner. A brand new sheet has four factory edges and four factory
corners. An offcut ripped off one side has three and two.

A part declares what it needs:

```json
"reference": { "edges": ["bottom"], "corner": false }
```

or `"corner": true` with two adjacent edges named, meaning both must land on factory stock
edges that meet.

### 7.3 Factory-edge assignment and pre-placement

This is the only part of the PRD that touches packing, and it is the main risk.

Parts with a `reference` requirement are **pre-placed** before the general pack:

1. Collect every instance with a reference requirement, sorted deterministically by demand
   (corner requirements first, since corners are scarcer, then by descending area, then by id
   and copy index).
2. Assign each to an available factory edge or corner on the current stock, anchored flush to
   it. Margin on a factory edge defaults to `factory_edge_margin` (default 0, because the
   whole point is that the edge is already good), while every sawn edge keeps
   `outer_edge_margin`. So margin becomes per-edge internally, derived, not a new user dial.
3. Hand the remaining free region to the existing packers, which then fill around the
   pre-placed pieces.

Consequences to accept openly:

- The free region after pre-placement is not a rectangle. The bundled MaxRects and guillotine
  packers work from a free-rectangle list and can be seeded with the reduced set. `rectpack`
  cannot: it takes bin dimensions only. **When a job has reference requirements, `rectpack` is
  not eligible and the bundled engine runs instead**, disclosed in the report the same way
  every other engine fallback is. Forcing `engine: "rectpack"` on such a job is an error, not
  a silent downgrade.
- The shapely nester already places against a `usable` polygon and slides toward an anchor, so
  a reduced usable region and pre-occupied geometry are natural there.
- Guillotine plus factory edges interact. A guillotine job that pre-places on two opposite
  edges can become non-separable. Verification already has `is_guillotine_cuttable`
  (pack_rect.py:267); it runs after pre-placement and a failure is a hard error naming the
  conflict.

**Over-subscription** is the normal case, not the edge case: twelve parts want a factory edge
and the sheet has four. The chain, every step disclosed: satisfy in the sorted order above,
open a new sheet if stock allows and the remaining demand justifies it, then downgrade the
rest to ordinary placement and list every downgraded piece with its id, copy number, and the
reason. A `reference.required: true` flag turns the downgrade into an error for parts where an
ordinary edge is genuinely unacceptable.

### 7.4 Grain

Stock (through its material) declares a grain axis. A part declares
`grain: "along" | "across" | "any"`, meaning the part's own grain axis relative to the stock's.
The part's own axis in its base orientation defaults to its height (long dimension of a typed
rectangle in base orientation) and is overridable with `grain_axis`.

Implementation is a filter inside `Part.allowed_angles`:

- `along` keeps angles where part axis and stock axis coincide: 0 and 180.
- `across` keeps 90 and 270.
- `any` keeps everything, which is today's behavior.

Because 180 is always kept, a grained part still gets the free flip that `rotation: "locked"`
denies it today. That alone is worth the feature.

Interactions, all resolved at load time rather than at pack time:

- Grain plus `rotation: "locked"` where the locked angle violates grain: hard error naming
  both fields.
- Grain plus a `rotation_step` whose grid contains no compliant angle: hard error.
- Grain plus `rotation_step: "free"` on an outline: the free nester refines to 1 degree, which
  would quietly break grain. A `grain_tolerance` (default 0 degrees) bounds the refinement for
  grained parts. At the default, grained parts do not free-rotate, and the report says so.
- A grained part on ungrained stock is a warning, not an error, and it is reported.

**Cost disclosure** is the open question in 7.9: grain constrains rotation, so it can cost
sheets. Reporting "grain cost you one sheet" means packing twice and comparing, which doubles
the run for a nice-to-have number.

### 7.5 Roll stock

`kind: "roll"` stock has a `width` (the physical roll width, fixed) and no height. It may
declare `total_length` if the roll on hand is finite.

Packing: build a virtual sheet whose length is a computed upper bound (sum of part extents
plus margins and gaps, which is trivially sufficient), pack with the existing engines, then
report the consumed run as the maximum extent reached along the roll axis, plus
`outer_edge_margin` at the trailing end.

Packing to one end is the requirement, and it needs to be explicit rather than assumed. The
MaxRects score already tie-breaks on `fr.y` then `fr.x` (pack_rect.py:63), which biases toward
the origin, but "biases" is not "guarantees." Roll mode adds run length as the **primary**
score term so a placement that extends the roll always loses to one that does not, and
verification asserts that no gap along the roll axis exceeds the largest unplaced part.

Reporting: consumed length in the display unit, and always additionally in yards and meters,
because that is how roll goods are bought. This needs a display-only yard conversion in
`units.py`; `yd` does not become a job input unit.

Nap is grain. Directional vinyl reuses 7.4 with no new concept, which is the argument for
doing grain before roll.

A roll offcut is genuinely reusable, unlike a sheet drop, so when `total_length` is declared
the report states remaining length as well as consumed.

### 7.6 Edge banding

A part declares banded edges using the 7.2 addressing, and banding thickness comes from the
material.

The load-bearing decision is the size convention, and it gets **no default**, matching how
`sheet`, `cutting_method`, and `machine` are handled: a wrong guess here is a silent
per-part error of a millimetre or two that only surfaces at assembly. A job containing any
banded edge must declare:

```json
"size_convention": "finished" | "cut"
```

`finished` means declared sizes include the banding, so the cut size subtracts
`banding_thickness` on each banded edge. `cut` means declared sizes are what gets cut and
banding is added afterwards, so the layout is unchanged and banding is informational. The cut
list reports both numbers per part either way, plus total linear banding needed per material.

One observation worth recording rather than building: a banded edge does not need to be
straight off the saw, because the banding covers it. So a banded edge is a *good* candidate to
not spend a factory edge on. That is a real optimization and it is v1.x, not v1. In v1 the two
attributes are independent, and a part that asks for both on the same edge gets a warning.

### 7.7 Kerf presets

New optional `cut_tool`, deliberately separate from `machine`, because a job can be cut on a
table saw and labeled by hand, and conflating them would break the labeling model that just
shipped.

Selecting a `cut_tool` fills `kerf` if the job does not state one. An explicit `kerf` always
wins, silently and without complaint, because measuring your own blade is the correct
behavior. The report names the tool and whether kerf came from the preset or was entered.

Starting values, presented in the intake and in docs as **starting points to be measured, not
truth**:

| Tool | Kerf (in) |
|---|---|
| Table saw, full kerf | 0.125 |
| Table saw, thin kerf | 0.094 |
| Miter saw | 0.110 |
| Circular / track saw | 0.094 |
| Jigsaw | 0.060 |
| Band saw | 0.025 |
| CNC router | bit diameter, no default |
| Laser | 0.010 |
| Plasma | 0.060 |
| Waterjet | 0.030 |

CNC router has no default on purpose: the kerf is the bit, and guessing a bit is worse than
asking. Presets live in the same profile files machines already use, so a shop default is
saved once. `rods[]` gains an optional `cut_tool` override, since bar stock is frequently cut
on a different saw than sheet goods.

### 7.8 Validation report additions

- Factory edge: requested, satisfied, downgraded, failed, with per-piece reasons.
- Factory corner assignment per sheet, and which corners remain.
- Engine note when reference requirements forced the bundled engine off `rectpack`.
- Grain: compliant piece count, any ungrained-stock warnings, whether free rotation was
  restricted by `grain_tolerance`.
- Roll: consumed length in display unit, yards, meters; remaining length when known.
- Banding: convention in force, per-part cut versus finished sizes, total linear banding.
- Kerf: value, tool, and whether it came from a preset or was entered by hand.

### 7.9 Open questions for sign-off

1. **Grain cost disclosure.** Report "grain cost N extra sheets" by packing twice and
   comparing? It roughly doubles run time for a number that is informative but not actionable.
   Proposal: off by default, available as `report_constraint_cost: true`.
2. **Reference edges on curved outlines.** v1 errors when a named edge is not straight along
   the bounding box. Acceptable, or is a nearest-straight-segment heuristic wanted now?
3. **Roll width strictness.** If a part is wider than the roll, is that always a hard error, or
   should the tool suggest rotating it when grain permits?
4. **Banding on imported outlines.** Restrict banding to rectangles in v1? Subtracting a
   banding thickness from one side of an irregular outline is a real offset operation and is
   noticeably more work than the rectangle case.

## 8. Scope by phase

**v1 (this PRD, in build order)**

1. `materials` block, `Stock.factory_edges`, per-edge addressing, additive schema, no
   behavior change when absent.
2. Kerf presets and `cut_tool`. Small, self-contained, immediately useful, and it exercises
   the profile plumbing before the hard work starts. **Built 2026-09-10, ahead of sign-off on
   the rest of this PRD, because it commits nothing architecturally: it is purely additive,
   changes no existing job's output, and can be dropped without touching anything else.**
3. Factory edge and corner: pre-placement, per-edge margin, over-subscription chain, engine
   eligibility, guillotine interaction, report.
4. Grain: `allowed_angles` filter, load-time conflict errors, `grain_tolerance`, report.
5. Roll: stock kind, run-length scoring, trim, yard and meter reporting.
6. Banding: `size_convention` with no default, cut versus finished sizes, linear totals.
7. Web page controls and docs for all of the above.

**v1.x**

- Banded edges deprioritized for factory-edge assignment.
- Grain matching and sequencing across a set of parts.
- Reference edges on curved and angled outlines.
- Show-face and two-sided operations, reusing this per-edge and per-face plumbing.
- Material thickness consumed for real once PRD 2 lands.

## 9. Constraints

- **Additive only.** Every existing job file produces identical output. Test enforced.
- Deterministic: same input, same layout, every run. Pre-placement ordering is fully specified
  above for this reason.
- No new binary dependencies. The page runs the same engine in Pyodide and already pulls
  roughly 15 MB; nothing here needs more than shapely, which is present.
- `web/index.html` is generated by `web/build_web.py` and the suite fails when it is stale, so
  every change here ships with a rebuilt page.
- Everything is reported in the display unit, with roll length additionally in yards and
  meters.

## 10. Risks and mitigations

- **Pre-placement costs density.** Anchoring parts to edges before packing can strand area.
  Mitigation: measure it in the acceptance tests, report sheet count, and let the user drop the
  requirement to see the difference.
- **`rectpack` ineligibility surprises people.** Mitigation: disclose in the report, and make a
  forced `engine: "rectpack"` on a reference job an explicit error with a message that says
  why.
- **Grain plus free rotation is close to a contradiction.** Mitigation: `grain_tolerance`
  defaults to 0 and the restriction is stated in the report rather than inferred.
- **Silent banding unit error.** Mitigation: `size_convention` has no default and both numbers
  appear in the cut list.
- **Schema sprawl.** Five features, one job file. Mitigation: everything lives under
  `materials` or a single `reference` object per part, and profiles absorb the shop defaults so
  a normal job file stays short.

## 11. Acceptance tests

1. Every existing example job produces byte-identical output. Regression lock.
2. New sheet, four parts each requiring a factory corner: all four satisfied, corners exhausted,
   report lists them.
3. Same job with five corner-requiring parts: four satisfied, one downgraded, downgrade in the
   report with a reason. With `required: true`, the run fails instead.
4. Offcut stock declaring two factory edges: a corner request against a non-adjacent pair is a
   load-time error.
5. Reference job with `engine: "rectpack"` forced: error naming the incompatibility. Same job
   on `auto`: bundled engine runs, report says why.
6. Grained stock, part with `grain: "along"`: every placement at 0 or 180, none at 90.
7. Grain plus `rotation: "locked"` at 90: load-time error naming both fields.
8. Roll 24 in wide, mixed parts: consumed length matches the maximum extent, no placement
   beyond it, yards and meters both reported and mutually consistent.
9. Roll with `total_length` shorter than needed: out-of-stock error consistent with the
   existing sheet behavior.
10. Banding, `size_convention: "finished"`: cut sizes are smaller by the banding thickness on
    banded edges only; totals match hand math. Omitting `size_convention` with banded edges
    present is an error.
11. `cut_tool: "table_saw"` with no kerf: kerf resolves to 0.125 and the report says preset.
    Adding an explicit kerf overrides it and the report says entered.
12. Guillotine plus opposite-edge pre-placement that cannot separate: hard error.

## 12. Decisions taken into this draft

1. Three PRDs, material first. Confirmed 2026-09-10.
2. Feature priority factory edge, grain, roll, banding. Confirmed 2026-09-10.
3. Banding stays in v1 rather than being deferred, because it reuses the factory-edge per-edge
   mechanic and the incremental cost is small. Requester's observation.
4. `cut_tool` is separate from `machine` rather than an extension of it.
5. `size_convention` gets no default, matching `sheet`, `cutting_method`, and `machine`.
6. Grain is implemented as a filter on `Part.allowed_angles` and nowhere else.

## CHANGELOG
- v1.0 (2026-09-10): Initial draft for sign-off.
- v1.0.1 (2026-09-10): Mark build item 2 (kerf presets) as built; the rest still awaits sign-off.
