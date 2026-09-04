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
- 01:42 ✅ README web section
- 02:05 ✅ unit 2: PDF cut sheet (one page per sheet, placement table under each sheet) via cairosvg + pypdf, CLI --no-pdf flag, tests (44 total)
- 02:35 ✅ unit 3: engrave/score layer detection (DXF layer names, SVG group names), transported through rotation/placement, ENGRAVE layer in cut SVG/DXF, drawn on reference/echo, verify check, 3 tests (47 total)
- 02:55 ✅ unit 4: nester slides top-6 anchors (L-bracket column 14.75->12.5 in, gusset 17.6->16.8 in); all-rectangle jobs routed to MaxRects even in true-outline mode (trophy sheet 1: 12->19 parts); engine notes updated
- 03:05 ✅ unit 5: renderer edge-case tests (mm cut file, ft rulers + 12.5 px/in on 4x8, custom sheet + slugged/deferred filenames, shared-edge touching, echo, locked 90) (53 total); GitHub Pages workflow (main only, needs Pages enabled)
- 03:35 ✅ unit 6a: multiple stock sizes, engine side. job "sheets" list in priority order with quantities (last may be unlimited); engines take sheet size + cap and return unplaced; stock loop in build_layout; Sheet carries width/height/stock; 6 tests (59 total)
- 04:05 ✅ unit 6b: per-sheet sizes everywhere (reference/cut SVG/DXF, verify boundary+area per sheet, stock-quantity check, cut list by size, layout json stocks), web page offcut rows -> job.sheets, docs (schema v1.3, intake v1.2, SKILL v1.3); 2 tests (61 total)
- 04:15 ✅ unit 7: per-sheet reference SVG files always written (PRD v1.x split files); SKILL outputs table updated
- 04:40 ✅ unit 8 (Sam asked): GitHub Pages prep: CI+deploy workflow gated on the default branch with page rebuild + staleness check + full tests, Pages self-enablement attempt, Pyodide 0.27.7 (verified on npm), favicon/description/noscript, .nojekyll, README deploy section
- 04:50 ✅ Pages run 33854981884: test job green on the runner (rebuild, staleness check, 61 tests); deploy job failed at configure-pages: 'Create Pages site failed: Resource not accessible by integration'. Needs Sam: Settings -> Pages -> Source: GitHub Actions, then re-run the workflow. CI fixes pushed (libcairo2, Playwright browser fallback).
- 04:51 ▶ NEXT (wake-up 05:16): list workflow runs; if Sam enabled Pages and a deploy succeeded, note the URL and stop. If not, stop; nothing else to do without Sam. Then: re-run suite, confirm push, then STOP unless Sam queues more. Candidate only if asked: Deepnest import (needs PRD), pynest2d verification (needs a machine where it installs).

## Handoff (04:16)
Done tonight: static web page (Pyodide, single file, Playwright-tested against real engine output), shared pipeline + JSON web API, PDF cut sheet with placement tables, engrave/score layer import through to ENGRAVE layers, denser nesting (top-6 slide, rectangles to MaxRects), multiple stock sizes end to end (offcuts first), per-sheet reference files, 25 new tests (61 total). All pushed to claude/cut-sheet-builder-prd-7sgek3.
Not verified: the page's live Pyodide load (CDN blocked in this sandbox). First thing for Sam: open web/index.html in a browser with internet and watch the status line reach "Engine ready". If micropip cannot install ezdxf, DXF import in the page fails while SVG still works; the CLI is unaffected.
Open for Sam: real trophy A-E dimensions; enable GitHub Pages (source: GitHub Actions) if hosting is wanted; pynest2d still untested.
