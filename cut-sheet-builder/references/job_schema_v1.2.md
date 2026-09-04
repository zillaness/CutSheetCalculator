---
file: job_schema_v1.0.md
version: 1.2
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
| `sheet` | **yes, no default** | preset name, `{ "preset": "..." }`, or `{ "width", "height", "units"? }` | Presets: `laser_24x18`, `plywood_4x8` (96 x 48), `plywood_4x4` |
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
