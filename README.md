---
file: README.md
version: 1.3
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Repository overview and quickstart for the cut-sheet-builder skill.
ai_update: Update last_updated and version. Append changelog at bottom.
---

# CutSheetCalculator

Home of the `cut-sheet-builder` Claude skill: to-scale nesting layouts, stock math, and
cut-ready files from a parts list, with a validation report that proves the layout is safe
to cut from. Built to the PRD in `docs/cut_sheet_builder_prd_v1.1.md`.

## Layout

```
cut-sheet-builder/          the skill (drop into ~/.claude/skills or /mnt/skills/user)
  SKILL.md
  scripts/cut_sheet_builder.py    CLI: deps | presets | echo | build
  scripts/cutsheet/               engine package
  references/                     job schema, intake questions, engine notes
  assets/examples/                acceptance-test jobs (trophy, L-bracket)
web/                        static page: template.html + build_web.py -> index.html (self-contained)
tests/                      pytest suite (acceptance, engine, web API, browser smoke)
docs/                       PRD
```

## Static web page

`web/index.html` is a single file. Open it in a browser (or host it on GitHub Pages): upload SVG/DXF
files or type rectangles, set quantities and options, check the parsed parts, build, download the
cut-ready SVG/DXF and reports, and print the cut sheet to PDF (one page per sheet plus the cut list).
It runs the same Python engine in the browser through Pyodide, so the first load downloads roughly
15 MB from cdn.jsdelivr.net and pypi.org; after that the browser caches it. Rebuild the page after any
engine change:

```bash
python web/build_web.py
```

The test suite fails if `index.html` is stale.

### Deploying to GitHub Pages

One-time: in the repository, Settings -> Pages -> Build and deployment -> Source: **GitHub Actions**.
After that, every push to the default branch runs `.github/workflows/pages.yml`: it installs the
requirements, rebuilds `web/index.html` from the engine, fails if the committed page was stale, runs
the full test suite (including the headless-browser smoke test), and publishes the `web/` folder.
The page is served at `https://zillaness.github.io/CutSheetCalculator/`. Pull requests run the
test job only. The page loads Pyodide from cdn.jsdelivr.net and ezdxf/svgelements from pypi.org
at runtime, so those hosts must be reachable from the viewer's browser.

## Quickstart

```bash
pip install -r requirements.txt
python cut-sheet-builder/scripts/cut_sheet_builder.py deps
python cut-sheet-builder/scripts/cut_sheet_builder.py echo  cut-sheet-builder/assets/examples/trophy_job_v1.0.json --out out/trophy
python cut-sheet-builder/scripts/cut_sheet_builder.py build cut-sheet-builder/assets/examples/trophy_job_v1.0.json --out out/trophy
python -m pytest -q tests
```

`build` writes the reference SVG, per-sheet cut-ready SVG and DXF, cut list, layout JSON,
and validation report, and exits non-zero if any check fails.

## Piece labels and profiles

Turn on `labels` in a job to mark each piece with its id: on the piece (engraved inside the
outline) or beside the cutout (in the waste). Text size follows the machine (`machine` plus
`marking_tool_diameter` for routers) and the font follows it too: filled outline glyphs for
laser raster, single-line strokes for routers. Labels that cannot fit fall back and the
validation report lists every one. Machine profiles in `cut-sheet-builder/assets/profiles/`
hold shop defaults; reference one with `"profile": "router_1_8"`. Details:
`cut-sheet-builder/references/job_schema_v1.4.md` and `docs/piece_labeling_prd_v1.2.md`.

## Engines

Bounding-box packing uses `rectpack` when importable, otherwise a bundled MaxRects or
guillotine packer. True-outline nesting uses `pynest2d` when importable, otherwise a bundled
shapely greedy nester. The validation report always says which one ran. See
`cut-sheet-builder/references/engine_notes_v1.3.md`.

## CHANGELOG
- v1.0 (2026-09-04): Initial release.
- v1.0.1 (2026-09-04): Reference link bump.
- v1.1 (2026-09-04): Static web page section.
- v1.2 (2026-09-04): GitHub Pages deployment section.
- v1.3 (2026-09-05): Piece labels and profiles section.
