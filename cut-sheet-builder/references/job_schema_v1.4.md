---
file: job_schema_v1.0.md
version: 1.4
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Field-by-field reference for the cut-sheet-builder job JSON file.
ai_update: Update last_updated and version. Rename file to match. Append changelog at bottom.
---

# Job file schema

A job is one JSON object. Lengths are in `units.input` unless a field says otherwise. Keys
starting with `_` (metadata, changelog) are ignored by the engine.

## Top level

| Field | Required | Values | Notes |
|---|---|---|---|
| `job_name` | yes | string | Used for output filenames (slugged) |
| `units` | no | `{ "input": "in", "display": "in" }` | `in`, `ft`, `mm`, `cm`. Display drives reports and cut files |
| `sheet` | **yes (or `sheets`), no default** | preset name, `{ "preset": "..." }`, or `{ "width", "height", "units"? }` | Presets: `laser_24x18`, `plywood_4x8` (96 x 48), `plywood_4x4` |
| `sheets` | alternative to `sheet` | list of the above, each with optional `quantity` | Used in list order: offcuts first, full sheets last. Every entry except the last needs a `quantity`; the last is unlimited. A part too big for an early stock falls through to a later one. Running out of stock is an error |
| `outer_edge_margin` | yes | number >= 0 | Sheet boundary to nearest part |
| `kerf` | yes | number >= 0 | Cut width |
| `part_spacing` | no | `{ "mode": "kerf-gap" }` (default), `{ "mode": "shared-edge" }`, `{ "mode": "custom-margin", "value": 0.5 }` | Gap between adjacent parts; independent of `outer_edge_margin` |
| `cutting_method` | **yes, no default** | `free` or `guillotine` | Guillotine packs bounding boxes so every sheet separates with full cuts |
| `nest_mode` | no | `true-outline` (default) or `bounding-box` | Per-part override via `parts[].nest_mode` |
| `rotation_step` | no | divisor of 360 (90, 45, 30, 15, 10, 5) or `"free"`, default 90 | Angle increment for outline nesting. `"free"` searches a 15 deg grid then refines to 1 deg around the best hit. Per-part override via `parts[].rotation_step`. Typed rectangles ignore it (always 0/90) |
| `seed` | no | int | Reserved; engines are ordered deterministically anyway |
| `engine` | no | `auto` (default), `rectpack`, `bundled`, `nest2d`, `shapely` | Force an engine; a forced engine that is missing is an error |
| `parts` | yes (or rods) | array | See below |
| `rods` | no | array | See below |
| `isolated_groups` | no | array of group names | Each gets its own sheet(s) |
| `deferred_groups` | no | array of group names | Implies isolated; sheets numbered last and marked DEFERRED |
| `output` | no | `{ "version": "1.0", "author": "Sam Cao", "engrave_layer": "none" }` | `engrave_layer`: `none` or `outline-guide` (puts engrave-flagged outlines on the ENGRAVE layer as an alignment aid) |
| `render` | no | `{ "px_per_unit": 40 }` | Pixels per inch for the reference SVG. Default 40, reduced automatically so a sheet is at most 1200 px wide |
| `profile` | no | name of a JSON file in `profiles/` beside the job or in `assets/profiles/` | Its fields become the job's defaults (machine, tool, kerf, margin, spacing, rotation, labels, outputs, sheet); job fields win. Unknown name lists the available ones |
| `machine` | required when labels are on | `laser`, `router`, `plasma`, `waterjet`, `hand` | Sets legible text size and default font. Asked every job at intake; no default |
| `marking_tool_diameter` | required for `router` with labels on | number > 0 | The engraving bit; single-line minimum = 5 x this |
| `outputs` | no | list of `reference`, `svg`, `dxf`, `pdf` | Which files to write. Absent = everything available. Validation, cut list, and layout JSON are always written |
| `labels` | no | object, see below | Piece labels. Default mode `none`: a job without it produces exactly the files it did before |

## `labels`

| Field | Default | Notes |
|---|---|---|
| `mode` | `none` | `on-piece` engraves the id inside the outline; `beside-cutout` marks the waste next to the part |
| `font` | from machine | `outline` (filled, laser raster) or `single-line` (Hershey strokes, router or laser score) |
| `text` | `id` | `id+copy` writes `A#1`, `A#2` |
| `cap_height` | machine default | Raised to the derived minimum when too small; the report says so |
| `orientation` | `upright` | or `follow-part` |
| `auto_spacing` | `true` | Raise part spacing so beside-cutout labels fit (text + 2 pads + kerf). The echo prints the bump |
| `min_spacing` | 0 | Floor on the effective gap |
| `clearance_pad` | 0.06 | Waste kept between a beside-cutout label and the cut |
| `on_piece_inset` | tool diameter (router) / kerf (laser), min 0.05 | Text box kept inside the outline by this much |
| `legibility_factor` | 5 | Router single-line minimum = factor x tool diameter |
| `laser_min_height` | 0.12 | Laser outline minimum (score uses 0.10) |
| `fallback` | `on-piece` | Chain: beside-cutout -> on-piece -> drop. `drop` skips the middle step |
| `dxf_layer` | `ENGRAVE` | Layer for labels in the DXF |

Machine rules: `plasma` and `waterjet` refuse labels. `hand` draws labels on the reference and PDF only.
Every downgrade or drop is listed in the validation report with its reason.

Per part: `parts[].label` = `{ "mode": "...", "text": "..." }` overrides the job mode or the text
written on that piece.

## `parts[]`

| Field | Required | Values | Notes |
|---|---|---|---|
| `id` | yes | unique string | Label on the render |
| `quantity` | yes | int >= 1 | |
| `width`, `height` | yes for typed parts | number > 0 | Ignored when `source` is a file |
| `source` | for imports | `{ "type": "file", "path": "bracket.dxf", "units"?: "mm", "tolerance"?: 0.005, "scale"?: 1.0 }` | Path relative to the job file. `units` overrides what the file declares. `tolerance` is the curve-flattening chord error in inches. DXF layers or SVG groups named engrave/score/etch/mark/raster become engrave geometry on the ENGRAVE layer of the cut files |
| `rotation` | no | `auto` (default) or `locked` | Explicit. Not inferred from `engrave` |
| `locked_angle` | no | degrees, default 0 | Orientation when locked; base orientation when auto |
| `engrave` | no | bool | Shown in legend and cut list. Set automatically when the imported file has an engrave/score layer |
| `group` | no | string | For isolation/deferral |
| `color` | no | CSS color | Reference render only; palette assigned otherwise |
| `nest_mode` | no | `true-outline` / `bounding-box` | Per-part override |
| `rotation_step` | no | degrees or `"free"` | Per-part override of the job's step. Use it to keep one hand-cut part on 90s while the rest nest freely |

Typed rectangles rotate only 0/90 in every mode.

## `rods[]`

| Field | Required | Notes |
|---|---|---|
| `id` | yes | |
| `length` | yes | Piece length |
| `quantity` | yes | |
| `stock_length` | no | Bar length to buy. Omit to get continuous length only |

Rod math: `n * length + (n - 1) * kerf`. Bars packed first-fit-decreasing.

## Minimal example

```json
{
  "job_name": "gussets",
  "units": { "input": "in", "display": "in" },
  "sheet": "laser_24x18",
  "outer_edge_margin": 0.25,
  "kerf": 0.125,
  "part_spacing": { "mode": "kerf-gap" },
  "cutting_method": "free",
  "nest_mode": "true-outline",
  "rotation_step": 15,
  "parts": [
    { "id": "G", "quantity": 20, "rotation": "auto", "source": { "type": "file", "path": "gusset_v1.0.dxf" } },
    { "id": "spacer", "width": 1.5, "height": 1.5, "quantity": 40 }
  ]
}
```

## CHANGELOG
- v1.0 (2026-09-04): Initial release.
- v1.1 (2026-09-04): rotation_step accepts "free"; per-part rotation_step override.
- v1.2 (2026-09-04): engrave layer detection note.
- v1.3 (2026-09-04): sheets list (multiple stock sizes).
- v1.4 (2026-09-05): profile, machine, marking_tool_diameter, outputs, labels, parts[].label.
