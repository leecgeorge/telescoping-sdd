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

## Panel review hits the 5-pass cap with HIGH concerns remaining

- **Cause:** The panel and auto-fix loop is producing new HIGH-severity concerns every pass without converging. MEDIUM/LOW concerns alone do not trigger this — the loop exits on zero HIGHs even if MEDIUM/LOW polish remains.
- **Solution:** Ask the user to decide: continue reviewing (relaxes the cap for this phase), accept remaining HIGH concerns as known risks, or defer remaining concerns to a later phase if valid. Do not silently extend past 5 passes.

## Panel raises a concern that belongs in a later phase

- **Cause:** Expected — reviewers like `ops-reviewer` or `delivery-manager` sometimes surface concerns that belong downstream.
- **Solution:** Record the concern in `### Latest pass detail` with disposition `Deferred → <TARGET.md>` and move on. The downstream phase's panelists will see the deferral when they read the upstream artifact. For `PLAN.md` (the last blueprint phase), deferral is not available — mark the concern as `Addressed` in-phase, `Sealed` (user-directed), or `Accepted as risk` (with `Defense:` in Notes).
