# Burndown — 2026-09-04 (5h window resets ~05:02 local; weekly resets 08:00 local)

Intake (00:55 local): 49% of 5h window, 37% weekly, 55% Fable. Sam asleep; nothing outward-facing.
Wake-up scheduled for ~05:05 local via send_later to resume from the ▶ NEXT line.
Phase 0 usage-mechanics experiment: pending (no meter readings available overnight).

## Queue (ranked, value per token)
1. Static web page (Pyodide runs the existing cutsheet package in the browser): upload SVG/DXF or type rectangles, quantities, options, build, download cut-ready SVG/DXF + print-to-PDF cut sheet.
2. CLI `--pdf`: per-sheet PDF pages of the reference render (cairosvg), plus cut list page.
3. Engrave/cut layer detection on DXF/SVG import (v1.x item).
4. Nester density: try sliding the top-3 candidates instead of only the best.
5. Renderer edge-case tests (mm display, 4x8 rulers, deferred filenames).

## Ledger
- 01:20 ✅ unit 1a: cutsheet.pipeline (shared build path), cutsheet.webapi (JSON in/out for the page), per-sheet reference renders, CLI refactored, 4 webapi tests (37 total)
- 01:40 ✅ unit 1b+1c: web/template.html + build_web.py -> single-file web/index.html (Pyodide loads engine zip); Playwright smoke test (5) + staleness test
- 01:41 ▶ NEXT: README web section + ledger; then queue item 2 (CLI --pdf via cairosvg)

## Handoff
(filled at soft-stop or limit)
