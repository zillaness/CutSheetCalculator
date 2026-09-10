---
file: next_prds_backlog_v1.0.md
version: 1.0
author: Sam Cao
created: 2026-09-10
last_updated: 2026-09-10
description: Scope notes for the two PRDs queued behind the material model: 1D upgrades (miters, bevels, cross-section symmetry, end pieces) and quantity intelligence (max fit, minimum counts with spares, per-part priority).
ai_update: Update last_updated and version. Rename file to match. Append changelog at bottom.
---

# Backlog: PRD 2 and PRD 3

Holding pen so these do not get rediscovered. Neither is signed off. Neither is being built.
PRD 1 is `material_model_prd_v1.1.md`.

## PRD 2: 1D upgrades

Today `rods[]` is `id`, `length`, `quantity`, `stock_length`, and `pack_1d.py` treats every cut
as square: `n * length + (n - 1) * kerf`, first-fit-decreasing into bars. Kerf in 1D already
works. What is missing:

**Cross-section symmetry is the governing variable, not the miter angle.** An angled cut on bar
stock may or may not cost material, depending entirely on whether the offcut can be rotated
into the next piece's mating face:

- Round tube, infinite rotational symmetry: any miter nests. The offcut is the next piece.
- Square tube, symmetry order 4: a 45 degree miter nests by flipping alternate pieces.
- Triangular stock, symmetry order 3: a miter across two of the three axes cannot be flipped
  into its mate. The angled offcut is scrap. This is the trophy job that did not work.

So the model needs `cross_section` with a symmetry order (or `round`), not just a length.

**Miter and bevel are two separate rotations** and both may apply to the same end. Miter is the
angle in plan, bevel is the angle in section. Each end of a piece needs its own pair.

**Long point versus short point.** Once an end is angled, `length` is ambiguous, and that
ambiguity is the most likely cause of the trophy failure. The schema must state which one it
means, with no default, and the cut list must print both.

**End pieces.** Some pieces must come from the end of a bar (a finished factory end, or a
feature that only exists at the end). Same shape as the factory-edge mechanic in PRD 1, one
dimension down, and worth building after that one so it reuses the pattern.

**Kerf on an angled cut** consumes more length than a square cut: roughly `kerf / cos(angle)`
along the bar axis. Small, real, and currently unmodeled.

## PRD 3: Quantity intelligence

All three of these are the same feature seen from different sides: the packer currently only
answers "fit exactly these," and the questions worth asking are inverse.

**Max fit.** How many of one part fit on a sheet. Today you must guess a quantity and read the
sheet count.

**Minimum counts plus spares.** Declare the minimum of each part the job actually needs, then
enumerate what else fits: how many spare sets, and the ratio frontier between competing parts.
The output is a small set of options to choose between, not a single layout. This is the one
with the most design in it, because "what is a good answer" is a user judgment.

**Per-part priority.** Rank which parts must land on this sheet and which can slide to the next
run. Partly exists: `sheets` is a priority-ordered stock list, and `deferred_groups` pushes a
whole group to the last sheets marked DEFERRED. What is missing is a per-part rank and a
minimum count guarantee, so a high-priority part is never bumped by packing convenience.

Note the overlap with PRD 1: a part with a factory-edge requirement is competing for a scarce
resource, and priority is how that competition should be resolved. If PRD 3 lands after PRD 1,
the factory-edge over-subscription ordering should be replaced by the real priority rank rather
than the interim sort documented in PRD 1 section 7.3.

## CHANGELOG
- v1.0 (2026-09-10): Initial capture.
