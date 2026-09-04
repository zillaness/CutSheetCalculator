---
file: cut_sheet_builder_prd_v1.1.md
version: 1.1
author: Sam Cao
created: 2026-06-16
last_updated: 2026-06-16
description: PRD for the cut-sheet-builder skill. Generates accurate, to-scale nesting layouts, stock calculations, and cut-ready files from a parts list, including true irregular-outline nesting from DXF/SVG.
ai_update: Update last_updated and version. Rename file to match. Append changelog at bottom.
---

# Cut-Sheet-Builder Skill: PRD (Draft for sign-off)

## 1. Problem

Given a set of parts to fabricate and a stock material, Sam needs a layout that shows what gets cut where, how much stock is required, and how the pieces nest on each sheet. The layout has to be trustworthy enough to hand to a student to execute on the laser cutter, or to use as a breakdown plan for a 4x8' plywood sheet on hand tools or a table saw.

The current path produces layouts that are not dimensionally faithful. In the trophy session, two specific defects appeared:

1. Pieces were not to scale. A single uniform pixels-per-inch was not used. Width and height were scaled by different constants to fit the page, so every rectangle came out at the wrong aspect ratio.
2. Identical parts looked different. The D pieces were drawn in two orientations. Under a non-uniform scale, a rotated D and an unrotated D of the same real dimensions rendered as visibly different rectangles, so the layout read as if there were two different parts.

Both defects trace to the same cause: rectangles were placed and sized by hand instead of computed, and the drawing used more than one scale factor. A layout that is off-scale or internally inconsistent is worse than no layout, because someone may cut from it.

## 2. Current workflow and where it breaks

Reconstructed from the trophy session and the team's fabrication setup (laser cutter without built-in nesting today, possible nesting-capable laser in the future, hand tools and table saw for larger plywood breakdown, Onshape and DXF/SVG exports):

1. A part is designed, real outline known, usually exported from Onshape or drawn directly as DXF/SVG. Many parts are not simple rectangles (brackets, gussets, panels, rounded corners, cutouts).
2. A quantity is decided.
3. Someone needs three answers: how much stock to buy, where each true-shaped piece sits on each sheet, and a cut-ready file to actually run on the laser or mark up for hand cutting.
4. Today that is done by hand math, eyeballing a layout, manual nesting inside the laser software (no nesting feature currently), or asking Claude ad hoc.

Failure points:

* Hand math is error-prone on kerf, edge margins, and counts.
* Eyeballed layouts are not to scale, so they cannot be trusted or handed off.
* Claude hand-placing rectangles produces non-uniform scale, inconsistent piece sizes, possible overlaps, and nothing that can be verified.
* No single, versioned artifact to project, print, save, or hand to a student, and nothing cut-ready.
* Real part outlines (not just bounding boxes) are not accounted for, so a bracket or gusset with a notch or radius gets treated as if it were its full rectangular footprint, wasting material.

What this skill replaces: manual or eyeballed layout plus one-off Claude requests. What it produces instead: a deterministic, code-computed, to-scale, verifiable layout, a stock calculation and cut list, and a cut-ready file, all saved as versioned artifacts.

## 3. What already exists, and why a custom skill

* Deepnest / SVGnest (open source, MIT) do true irregular-shape nesting via no-fit-polygon geometry and a genetic-algorithm search. They are excellent, standalone GUI tools with years of dedicated engineering behind the packing quality. They do not produce a labeled planning reference, a cut list, a rod calculation, attribute-based sequencing, or anything tied to the team's versioning conventions. For jobs where packing density is the priority over convenience, Deepnest remains the better tool, and this skill should say so rather than pretend to match it.
* LightBurn and similar laser software sometimes include nesting. Manual, per-machine, not a versioned planning document, and the current laser doesn't have it.
* rectpack (Python) does solid rectangle packing. Used as the engine for the bounding-box nesting mode.
* nest2D / libnest2d (Python binding to a C++ nesting library used in PrusaSlicer) does real polygon nesting with rotation search. Proposed as the engine for true irregular-outline nesting, so this skill is not reimplementing no-fit-polygon geometry from scratch.
* shapely (Python) does robust polygon geometry: overlap checks, buffering for kerf, area math. Used both as a verification tool and as the fallback nesting engine if nest2D is not installable in the runtime.
* Onshape models the parts but does not nest.

This is a hybrid build: custom workflow, intake, sequencing, versioned outputs, and verification, on top of proven packing and geometry libraries rather than hand-placed shapes or a from-scratch nesting algorithm.

## 4. Goals and success criteria

* One uniform scale. A single units-per-pixel constant applied to width and height across the entire drawing and across all sheets.
* True aspect ratio and true outline. Rectangles render at their real proportions. Irregular parts render as their actual outline (not a placeholder box) at the computed position and rotation.
* Cross-part consistency. Two parts of equal real dimensions render identically regardless of sheet or rotation.
* No overlaps. Verified geometrically: bounding-box overlap checks in bounding-box mode, real polygon intersection checks (with kerf as a buffer) in true-nest mode.
* Inside the boundary. Every part sits within the sheet minus the outer edge margin.
* Correct counts. Rendered count per part equals requested quantity.
* Correct stock math. Sheet count and rod/bar length match an independent re-derivation, with waste percentage reported.
* Deterministic. Same input produces the same layout (fixed seed/ordering where the engine involves randomness, e.g. nest2D's search).
* Compliant outputs. Naming, metadata, and changelog conventions followed.
* Trust artifact. A validation report lists every check and its pass/fail result, including which nesting engine actually ran.

## 5. Non-goals (v1)

* Full CAM: toolpaths, feeds and speeds, laser power or pass settings.
* Automatic generation of engraving artwork or rasters.
* Material inventory and cost optimization.
* Grain or anisotropy databases.
* Matching Deepnest's packing density exactly. True-nest mode aims for correct, kerf-safe, reasonably efficient packing, not a from-scratch reimplementation of a mature nesting optimizer.

## 6. Users and primary use cases

* Sam, producing fabrication runs: trophies, brackets, gussets, mounting plates, panels, banner inserts, and larger plywood breakdown (4x8' sheets, hand tools or table saw).
* Students, executing a cut from a to-scale, labeled, cut-ready file.

The DTF gang-sheet workflow is raster artwork on film, not vector part cutting, and stays explicitly out of scope here.

## 7. Core design

### 7.1 Two principles that fix the original failures

1. Compute, then render. A packing function assigns every part an exact position and rotation. The renderer only draws computed positions, whether the part is a rectangle or a true outline.
2. Single uniform scale. The output is authored in real-world units multiplied by one constant k, used identically for width and height, across every sheet in a job. A rotated part is the same part transposed, never a differently sized shape.

### 7.2 Data model (input schema)

Parts (2D):

* id or name
* source: typed rectangle (width, height) or an imported outline (from DXF/SVG)
* quantity
* rotation_allowed (explicit toggle: autorotate, or locked to a specified orientation, not inferred from any other field)
* rotation_step (for true-nest mode: angle increment to search, e.g. 15 degrees; finer = better packing, slower)
* engraving flag (informational; does not by itself change rotation_allowed)
* group or tag (optional, for sequencing and sheet isolation)
* color (optional, for the reference render)

Stock (1D, rod or bar):

* id, length, quantity, stock_length

Job-level parameters:

* sheet_width, sheet_height (no default; presets offered, e.g. 24x18 laser, 4x8' plywood, selectable not automatic)
* outer_edge_margin (sheet boundary to nearest part)
* part_spacing_mode: kerf-gap (default within this mode) | shared-edge (zero gap, one shared cut line) | custom-margin (user value), independent of outer_edge_margin
* kerf
* cutting_method: free | guillotine, no system default, always asked per job
* nest_mode per job or per part: bounding-box | true-outline (both available; true-outline is the primary capability, bounding-box is the fast/simple option)
* units: base unit stored internally for consistent math; display unit selectable (in, ft, mm, cm)

Input is typed dimensions, a small table, or DXF/SVG import. The skill echoes a parsed parts table (dimensions, and for imports, a quick outline preview) back for confirmation before nesting or rendering, to catch dimension or import errors.

### 7.3 Packing engines

* 1D rod/bar: first-fit-decreasing with kerf between adjacent cuts. Reports bars needed and offcut per bar. (Lower priority going forward per your note that future work is primarily flat parts, but kept since rod jobs like the trophy still happen.)
* 2D bounding-box mode: rectpack, MaxRects heuristic by default. Fast, simple, used when true-outline nesting isn't needed or when speed matters more than density.
* 2D true-outline mode: nest2D (libnest2d) as the primary engine: real polygon geometry, rotation search, no-fit-polygon based placement. If nest2D is not installable in the runtime, falls back to a shapely-based greedy placer with a stepped rotation search and real overlap checks (kerf applied as a buffer). The validation report states which engine actually ran and flags the fallback explicitly, since packing density will be lower than nest2D or Deepnest.
* Both 2D engines are deterministic (fixed ordering / fixed seed) so re-running the same input reproduces the same layout.

### 7.4 Kerf and margin model (two independent dials)

* outer_edge_margin: distance from the stock boundary to the nearest part. One dial, applies uniformly around the sheet perimeter.
* part_spacing_mode: a separate dial governing the gap between adjacent parts:
   * kerf-gap (default choice within this mode): parts separated by exactly one kerf width, one shared cut line consumes material from both parts equally. This was the model used for the trophy job.
   * shared-edge: zero gap, a single vector line defines the boundary of both parts. Used when kerf compensation is handled in the toolpath itself rather than in the layout.
   * custom-margin: a user-specified value larger than kerf, for safety clearance, heat-affected-zone spread, or room for hand-finishing between parts.
* 1D rod: n pieces of length L need n·L plus (n-1)·kerf of material removed between pieces. Worked example from the trophy job, kept as a regression check: 30 pieces x 5.25 + 29 x 0.125 = 161.125 inches.

### 7.5 Rotation policy

* rotation_allowed is explicit per part: autorotate (engine may rotate to improve packing) or locked (engine must respect a specified orientation). Not derived automatically from the engraving flag or any other field, so an engraved part isn't silently assumed to need locking and a plain part isn't silently assumed to allow rotation.
* rotation_step controls search granularity in true-nest mode. Any rotated part is clearly marked in the render (rotation indicator on the label).

### 7.6 Sequencing and grouping

Parts carry an optional group or tag. The skill can isolate a tagged group onto its own sheet(s) and mark a sheet as deferred in the render (the "cut everything except C now, C later" case from the trophy job). If no groups are tagged, this has no effect, so it costs nothing to leave available on every job.

### 7.7 Verification pass

After nesting, code runs assertions and emits a validation report:

* single scale constant confirmed,
* aspect ratios / outline fidelity correct,
* no overlaps: bounding-box check in bounding-box mode, real polygon intersection check (kerf-buffered) in true-nest mode,
* all parts within the outer_edge_margin boundary,
* counts match requested quantities,
* stock math re-derived and matched,
* area accounting closes (parts + waste = sheet area),
* which nesting engine actually ran (primary or fallback), flagged if fallback.

### 7.8 Output artifacts

* v1: to-scale, labeled reference SVG (colored, legend, sheet-by-sheet), versioned.
* v1: cut-ready file (SVG, and DXF where the source was DXF): hairline strokes, real units, no labels or fills, separate layers for cut vs. engrave, true outlines placed and rotated exactly as computed, not placeholder rectangles.
* v1: cut list and stock summary (per-sheet contents, sheet/bar counts, waste percentage).
* v1: validation report.
* v1.x: per-sheet split files for sequencing (cut-now vs. deferred as separate files, not just visually marked).
* v2: interactive HTML viewer (toggle sheets, check off completed cuts, print, persistence), confirmed as a "nice to have later," not blocking v1.

### 7.9 Rendering path

The inline visualizer failed (400) on the trophy layout's element count. The SVG/DXF file artifact is the primary, reliable output channel for any real part count. The inline visualizer, if used at all, is for small previews only.

## 8. Inputs and file formats

* v1, primary: DXF and SVG import. Extracts real closed-path outlines (not just bounding boxes), used directly in true-outline nesting mode, or reduced to a bounding box when bounding-box mode is selected for that job or part.
* v1: typed dimensions or a small table, for parts without an existing file (e.g. simple stock rectangles like the trophy pieces).
* Still deferred: parsing DXF/SVG layers for engrave-vs-cut distinction on import (assume cut-only on import for v1; engrave layers added manually in the job setup). Revisit in v1.x if it becomes a bottleneck.

## 9. Scope by phase

### v1

* Typed and DXF/SVG parts input, with confirmation echo (dimensions or outline preview).
* 1D rod/bar packing.
* 2D bounding-box packing (rectpack).
* 2D true-outline packing (nest2D primary, shapely fallback), with rotation search and explicit rotation_allowed per part.
* Two-dial margin model: outer_edge_margin, part_spacing_mode (kerf-gap / shared-edge / custom-margin).
* cutting_method asked per job, no default.
* Sheet size presets offered (24x18, 4x8'), not defaulted.
* Units: in/ft primary, mm/cm selectable, one consistent internal base unit.
* Attribute-based sheet isolation and deferred-sheet marking.
* Verification pass and validation report, including which nesting engine ran.
* To-scale labeled reference SVG, cut-ready SVG/DXF, cut list, stock summary, all versioned.
* Trophy job (rectangles) reproduced correctly as one acceptance test; a second acceptance test using an irregular outline (e.g. an L-bracket or rounded-corner panel) validates true-nest mode.

### v1.x

* Per-sheet split files for sequencing.
* Multiple stock sizes in a single run.
* Mixed rod-plus-sheet jobs as one deliverable.
* Engrave/cut layer detection on DXF/SVG import.

### v2

* Interactive HTML viewer.

## 10. Constraints and dependencies

* Runs in the Python environment available to the skill.
* rectpack for bounding-box mode.
* nest2D (libnest2d bindings) for true-outline mode, verified installable at build time; shapely-based fallback if not, with the tradeoff disclosed in the validation report.
* shapely for geometry verification regardless of which nesting engine ran.
* Units explicit and consistent within a run; internal base unit fixed regardless of display unit.
* Determinism required (fixed ordering or seed) for both engines.
* Outputs follow the revision-control conventions in use.

## 11. Risks and mitigations

* True-outline nesting is a genuinely hard problem. Mitigation: use nest2D (a proven library) rather than reimplementing no-fit-polygon search; disclose in the validation report when the shapely fallback runs, since it will pack less densely; point to Deepnest as the better tool when density is the priority over convenience.
* Heuristic packing (either mode) is not globally optimal. Mitigation: report waste percentage, allow manual sheet-assignment overrides.
* Library unavailable offline. Mitigation: bundled fallback for both rectpack and nest2D paths; verified at build time.
* Large SVG payloads breaking the inline visualizer. Mitigation: file artifact as the primary channel (already adopted).
* DXF/SVG parsing edge cases (open paths, layers, units embedded in the file not matching job units). Mitigation: confirmation echo of parsed outlines before nesting; explicit unit selection at intake.
* Input typos in dimensions. Mitigation: parsed parts table echoed for confirmation before rendering.
* cutting_method has no default, so every job's intake must ask it. Mitigation: baked into the standard intake question set (7.6/12), not something to forget case by case.

## 12. Skill packaging

* Proposed name: `cut-sheet-builder`.
* Triggers (draft): "lay out parts for cutting", "make a cut sheet", "nest these on a sheet", "how much stock do I need", "cutting layout for", "how many sheets", "nest this DXF", rod/bar length questions.
* Interview-first: runs the user-input-protocol to gather parts (typed or imported), stock, kerf, outer_edge_margin, part_spacing_mode, cutting_method (always asked, no default), units, rotation policy per part, nest_mode, grouping, and output format before generating anything.
* Composes with: revision-control (naming, metadata, changelog), user-input-protocol (intake), sam-cao-style-guide and ai-tropes (any prose in the summary).

## 13. Acceptance tests

1. Trophy regression (rectangles, bounding-box mode). Parts A-E as before, 15 each, rod calc (161.125 in), 24x18 sheets, 1/4 outer margin, 1/8 kerf-gap spacing, C isolated to a deferred sheet. All verification checks pass.
2. Irregular outline (true-nest mode). A DXF or SVG import of a non-rectangular part (e.g. an L-bracket or a panel with a rounded corner or cutout), multiple quantity, autorotate enabled, nested on a sheet. Verification confirms: real outline rendered (not a bounding box) at the correct position and rotation, no polygon overlaps (kerf-buffered), correct count, within outer_edge_margin. Report states which nesting engine ran.

## 14. Open items

* cutting_method is asked per job by design; nothing further to resolve here.
* Nesting engine choice (nest2D primary, shapely fallback) is a recommendation, to be confirmed working at build time. Flagged here rather than gated behind another round of questions, since it's an implementation detail with a disclosed fallback rather than a product-level choice.

## CHANGELOG

* v1.0 (2026-06-16): Initial draft for sign-off.
* v1.1 (2026-06-16): Promoted DXF/SVG import and true irregular-outline nesting to core v1 (both true-nest and bounding-box modes available, per sign-off). Added cut-ready file to v1 deliverables. Made rotation_allowed an explicit per-part toggle, not derived from engraving flag. Split margin model into two independent dials (outer_edge_margin, part_spacing_mode with kerf-gap/shared-edge/custom-margin options). Removed system default for cutting_method, always asked per job. Sheet size now selectable with presets (24x18, 4x8') rather than defaulted. Added units dual-support (in/ft primary, metric selectable). Added nest2D/libnest2d and shapely as proposed dependencies for true-outline nesting, with disclosed fallback behavior. Added second acceptance test for irregular-outline nesting. Confirmed interactive HTML viewer stays in v2.
