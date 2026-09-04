---
file: README.md
version: 1.0.1
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
tests/                      pytest suite (acceptance + engine unit tests)
docs/                       PRD
```

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

## Engines

Bounding-box packing uses `rectpack` when importable, otherwise a bundled MaxRects or
guillotine packer. True-outline nesting uses `pynest2d` when importable, otherwise a bundled
shapely greedy nester. The validation report always says which one ran. See
`cut-sheet-builder/references/engine_notes_v1.1.md`.

## CHANGELOG
- v1.0 (2026-09-04): Initial release.
- v1.0.1 (2026-09-04): Reference link bump.
