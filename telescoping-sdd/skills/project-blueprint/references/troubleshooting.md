<!--
SHARED REFERENCE — keep in sync with the spec-driven-dev copy at
skills/spec-driven-dev/references/troubleshooting.md. Edits to shared entries must be mirrored in BOTH copies.

Intentional asymmetries vs the sibling (do NOT "sync" these away):
- Troubleshooting topics are skill-specific: each copy lists problems for its own phases (blueprint: scope/architecture/feature-sizing; spec-driven-dev: tasks/design/acceptance-criteria/requirement-coverage) — extra or differently-named sections are expected.
- Phase names + artifact filenames swap per skill (Scope/SCOPE.md/validate_blueprint.py vs Specify/spec.md/validate_spec.py, etc.).
- The "Validator shows warnings" entry lists spec-driven-dev-only advisory categories (type hints, test names, unresolved markers); blueprint intentionally has none.
- The shared "concern belongs in a later phase" entry cites each skill's real panelist (ops-reviewer for blueprint, testability-reviewer for spec-driven-dev; delivery-manager in both).
- The no-deferral fallback names the terminal Phase-3 artifact: PLAN.md / "last blueprint phase" vs tasks.md / "last artifact phase".
Otherwise the copies differ only cosmetically (terminology mapping, example wording).
-->

# Troubleshooting

## Scope validation fails

- **Cause:** Missing required sections in SCOPE.md
- **Solution:** Run `validate_blueprint.py` to see which sections are missing, then add them

## Architecture doesn't align with scope

- **Cause:** Scope was too vague or architecture introduces unscoped concerns
- **Solution:** Edit `SCOPE.md` (tighten or add missing goals) — the single highest-affected upstream — and run *Re-Approval After Edits*; the cascade re-stamps and runs the Scope–Architecture consistency check. **Catch-early** (preferred) when you notice before drafting further; **caught-late** (already deep into Architecture/Plan when the gap shows) is the same motion — edit `SCOPE.md` and let the cascade reconcile downstream, never hand-editing the lower artifacts ahead of it. Edit only the highest-affected document — never co-edit the chain (`hash-and-cascade.md` § "Single-entry-point rule").

## Features are too large for spec-driven-dev

- **Cause:** Feature breakdown is too coarse
- **Solution:** Split large features into smaller ones in PLAN.md. Each feature should be implementable as a single spec-driven-dev cycle.

## Scope keeps changing

- **Cause:** Requirements are not yet well understood
- **Solution:** Spend more time in Phase 1. Use the Open Questions section to capture unknowns. Do not move to Architecture until the user confirms the core scope is stable.

## Risk discovered during architecture that invalidates scope

- **Cause:** Technical feasibility issue found during architecture design
- **Solution:** Edit `SCOPE.md` to reflect the new reality — the single highest-affected upstream — and run *Re-Approval After Edits*; the cascade re-stamps and surfaces the architectural divergence for reconciliation. Whether caught early or only after drafting downstream, it is the same motion: edit `SCOPE.md`, then let the cascade carry the change down — never co-edit the chain (`hash-and-cascade.md` § "Single-entry-point rule").

## Validator shows warnings but no failures

- **Cause:** Advisory checks found issues that don't block progress
- **Solution:** Review each WARN item. Fix if easy, otherwise note as a follow-up. Warnings don't block approval but may indicate incomplete thinking.

## Panel keeps raising the same concern across passes

- **Cause:** The auto-fix didn't actually resolve the concern — the panel sees the same issue on the next pass.
- **Solution:** Stop the loop and ask the user. Either the fix was too shallow (apply a deeper one), or the concern is a judgment call that needs user input, or the concern should be `Accepted as risk`.

## Panel review hits the 5-pass cap with unresolved HIGH concerns remaining

- **Cause:** The panel and auto-fix loop is producing new HIGH-severity concerns every pass without converging. MEDIUM/LOW concerns alone do not trigger this — the loop exits on zero *unresolved* HIGHs — HIGHs other than those dismissed with a recorded `Defense:` — even if MEDIUM/LOW polish remains.
- **Solution:** Ask the user to decide: continue reviewing (relaxes the cap for this phase), accept remaining HIGH concerns as known risks, or defer remaining concerns to a later phase if valid. Do not silently extend past 5 passes.

## The loop exited but the last Trajectory row still shows a HIGH

- **Cause:** A sealed exit. Every HIGH that pass was disposed `Sealed` or `Accepted as risk` with a recorded `Defense:`, so none was unresolved and the loop exited. The Notes cell reads `converged (0 unresolved HIGH); sealed=<N>`. The HIGHs column keeps recording HIGHs *raised*, which is why the two disagree — by design.
- **Solution:** No action required; this is expected behaviour. To see why each was sealed, read the `Defense:` text in `### Sealed dispositions` (cumulative across passes and severities; each entry names its pass). To dispute a seal, re-open the panel loop and raise it with **new substantive evidence** — that is the one route step 1's suppression instruction leaves open; simply running another pass will not re-litigate it.

## Panel raises a concern that belongs in a later phase

- **Cause:** Expected — reviewers like `ops-reviewer` or `delivery-manager` sometimes surface concerns that belong downstream.
- **Solution:** Record the concern in `### Latest pass detail` with disposition `Deferred → <TARGET.md>` and move on. The downstream phase's panelists will see the deferral when they read the upstream artifact. For `PLAN.md` (the last blueprint phase), deferral is not available — mark the concern as `Addressed` in-phase, `Sealed` (user-directed), or `Accepted as risk` (with `Defense:` in Notes).

## Downstream identifier in upstream artifact

You ran the validator on `SCOPE.md` or `ARCHITECTURE.md` and saw a finding such as `SCOPE.md must not contain a downstream feature-identifier heading (F3 at line 12)` — a **FAIL** that blocks `--approve` — or `ARCHITECTURE.md has a bare downstream feature-identifier reference (F2 at line 47)` — a non-blocking **WARN**.

- **Why it fires:** feature numbers (`F<n>`) are assigned *downstream*, in `03_PLAN.md`'s Feature Breakdown — not in a scope or architecture document. Numbering a feature in an upstream doc points at a breakdown that does not exist yet; when the plan later renumbers features, the upstream doc silently goes stale. The guard catches that early.
- **Why a heading blocks but a bare token only warns:** a line-start heading like `### F3: Auth` has no innocent reading in an upstream doc — it *is* a feature breakdown, so it FAILs. A bare `F3` in running prose is often something else (a version string, a label, an example), so it only WARNs and never blocks approval.
- **Tier asymmetry:** the blueprint tier flags only `F<n>` (feature IDs); the SDD tier (`spec.md` / `design.md`) flags only `T<n>` (task IDs). Neither flags the other's letter, and `03_PLAN.md` itself is never scanned — it legitimately mints `### F<n>:` headings.
- **What "backtick" means:** wrapping a token in backticks — `` `F3` `` — marks it as an inline code example, and the guard skips it. Use this only when you genuinely need to *show* the token as an example.
- **How to fix — pair the fix to what you have:**
  - A **heading** (`### F3: Auth`) → rename it in place and drop the number (`### Authentication`); or, if the section really is the feature breakdown, move it to `03_PLAN.md`. A line-start heading cannot be backticked away.
  - A **bare reference** to a real downstream feature → name the plan or phase instead of the number (e.g. "see the Implementation Plan").
  - An **example token**, or your document's own local label → backtick it (`` `F3` ``).
