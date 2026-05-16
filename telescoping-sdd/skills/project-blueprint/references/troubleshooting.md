# Troubleshooting

## Scope validation fails

- **Cause:** Missing required sections in SCOPE.md
- **Solution:** Run `validate_blueprint.py` to see which sections are missing, then add them

## Architecture doesn't align with scope

- **Cause:** Scope was too vague or architecture introduces unscoped concerns
- **Solution:** Edit SCOPE.md (tighten or add missing goals). The auto-cascade handles re-stamp and the Scope-Architecture consistency check — see `hash-and-cascade.md`.

## Features are too large for spec-driven-dev

- **Cause:** Feature breakdown is too coarse
- **Solution:** Split large features into smaller ones in PLAN.md. Each feature should be implementable as a single spec-driven-dev cycle.

## Scope keeps changing

- **Cause:** Requirements are not yet well understood
- **Solution:** Spend more time in Phase 1. Use the Open Questions section to capture unknowns. Do not move to Architecture until the user confirms the core scope is stable.

## Risk discovered during architecture that invalidates scope

- **Cause:** Technical feasibility issue found during architecture design
- **Solution:** Edit SCOPE.md to reflect the new reality. The auto-cascade handles re-stamp and surfaces the architectural divergence — see `hash-and-cascade.md`.

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
