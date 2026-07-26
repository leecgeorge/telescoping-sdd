<!--
SHARED REFERENCE — keep in sync with the project-blueprint copy at
skills/project-blueprint/references/troubleshooting.md. Edits to shared entries must be mirrored in BOTH copies.

Intentional asymmetries vs the sibling (do NOT "sync" these away):
- Troubleshooting topics are skill-specific: each copy lists problems for its own phases (blueprint: scope/architecture/feature-sizing; spec-driven-dev: tasks/design/acceptance-criteria/requirement-coverage) — extra or differently-named sections are expected.
- Phase names + artifact filenames swap per skill (Scope/SCOPE.md/validate_blueprint.py vs Specify/spec.md/validate_spec.py, etc.).
- The "Validator shows warnings" entry lists spec-driven-dev-only advisory categories (type hints, test names, unresolved markers); blueprint intentionally has none.
- The shared "concern belongs in a later phase" entry cites each skill's real panelist (ops-reviewer for blueprint, testability-reviewer for spec-driven-dev; delivery-manager in both).
- The no-deferral fallback names the terminal Phase-3 artifact: PLAN.md / "last blueprint phase" vs tasks.md / "last artifact phase".
Otherwise the copies differ only cosmetically (terminology mapping, example wording).
-->

# Troubleshooting

## Spec validation fails

- **Cause:** Missing required sections in spec.md
- **Solution:** Run `validate_spec.py` to see which sections are missing, then add them

## Tasks are too large

- **Cause:** Task touches too many files or has unclear boundaries
- **Solution:** Split into smaller tasks, each with a single clear outcome

## Requirements change mid-implementation

- **Cause:** New information or feedback during development
- **Solution:** **Triage first** (`SKILL.md` § "Mid-implementation discovery"): a *major* deviation halts and backports immediately; a *minor* one is logged and deferred. **Caught-late** (you already wrote deviating code): implement to a stable point, then **backport** — edit the single highest-affected upstream (`spec.md`) and run *Re-Approval After Edits*; the cascade reconciles `design.md`/`tasks.md` and *produces* the task reconcile (mark superseded tasks `Skipped`, add replacements) — don't hand-edit those ahead of it (a hand-edit races the cascade and silently no-ops it). **Catch-early** (preferred when achievable): notice before writing the deviating code, edit `spec.md` first, let it cascade, then implement. Either way edit only the highest-affected document — never co-edit the chain (`hash-and-cascade.md` § "Single-entry-point rule").

## Spec keeps changing before the design is written

- **Cause:** Requirements are not yet well understood
- **Solution:** Spend more time in Phase 1. Use the Open Questions section to capture unknowns. Do not move to Design until the user confirms the core requirements are stable.

## Design flaw discovered mid-implementation

- **Cause:** The design made an assumption that turned out wrong
- **Solution:** **Triage first** (`SKILL.md` § "Mid-implementation discovery"): a *major* deviation halts and backports immediately; a *minor* one is logged and deferred. **Caught-late** (the wrong assumption is already in code): implement to a stable point, then **backport** — edit the single highest-affected upstream (`design.md`) and run *Re-Approval After Edits*; the cascade surfaces the `tasks.md` mismatch and the reconcile (mark invalidated tasks `Skipped` in the summary table, check off their boxes, add replacement tasks) is *produced by the cascade*, not a pre-emptive hand-edit. **Catch-early** (preferred): edit `design.md` before building further on the wrong assumption, let it cascade, then implement. Edit only the highest-affected document — never co-edit the chain (`hash-and-cascade.md` § "Single-entry-point rule").

## Tests pass but acceptance criteria feel wrong

- **Cause:** Acceptance criteria in the spec don't fully capture the intended behavior
- **Solution:** **Triage first** (`SKILL.md` § "Mid-implementation discovery"): a *major* deviation halts and backports immediately; a *minor* one is logged and deferred. The fix is in the upstream, not the code: **backport** by refining the GIVEN/WHEN/THEN blocks in `spec.md` (the single highest-affected document) and running *Re-Approval After Edits* — the cascade ripples the change to `tasks.md` and *produces* the task/test revision as surfaced divergence, rather than you hand-editing `tasks.md`. Prefer catching this early (sharpen the AC before the tests encode it); when caught late, backport and then let the cascade reconcile. Never co-edit the chain (`hash-and-cascade.md` § "Single-entry-point rule").

## Validator shows warnings but no failures

- **Cause:** Advisory checks (type hints, test names, unresolved markers) found issues that don't block progress
- **Solution:** Review each WARN item. Fix if easy, otherwise note as a follow-up. Warnings don't block approval but may indicate incomplete work.

## Requirement not covered by any task

- **Cause:** A requirement from spec.md has no corresponding task in tasks.md
- **Solution:** The validator will warn about uncovered R-numbers. Add tasks to cover each missing requirement, or update the spec to remove requirements that are no longer needed.

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

- **Cause:** Expected — reviewers like `testability-reviewer` or `delivery-manager` sometimes surface concerns that belong downstream.
- **Solution:** Record the concern in `### Latest pass detail` with disposition `Deferred → <TARGET.md>` and move on. The downstream phase's panelists will see the deferral when they read the upstream artifact. For `tasks.md` (the last artifact phase), deferral is not available — mark the concern as `Addressed` in-phase, `Sealed` (user-directed), or `Accepted as risk` (with `Defense:` in Notes).

## Downstream identifier in upstream artifact

You ran the validator on `spec.md` or `design.md` and saw a finding such as `spec.md must not contain a downstream task-identifier heading (T5 at line 12)` — a **FAIL** that blocks `--approve` — or `design.md has a bare downstream task-identifier reference (T3 at line 47)` — a non-blocking **WARN**.

- **Why it fires:** task numbers (`T<n>`) are assigned *downstream*, in `03_tasks.md` — not in a spec or design document. Numbering a task in an upstream doc points at a breakdown that does not exist yet; when tasks are later renumbered, the upstream doc silently goes stale. The guard catches that early.
- **Why a heading blocks but a bare token only warns:** a line-start heading like `### T5: Setup` has no innocent reading in an upstream doc — it *is* a task breakdown, so it FAILs. A bare `T5` in running prose is often something else (a label, a local test-ID, an example), so it only WARNs and never blocks approval.
- **Tier asymmetry:** the SDD tier flags only `T<n>` (task IDs); the blueprint tier (`SCOPE.md` / `ARCHITECTURE.md`) flags only `F<n>` (feature IDs). The SDD tier never flags `F<n>` — your spec's own `**PLAN feature identifier:** F<n>` line is fine — and `03_tasks.md` itself is never scanned, since it legitimately mints `### T<n>:` headings.
- **What "backtick" means:** wrapping a token in backticks — `` `T5` `` — marks it as an inline code example, and the guard skips it. Use this only when you genuinely need to *show* the token as an example.
- **How to fix — pair the fix to what you have:**
  - A **heading** (`### T5: Setup`) → rename it in place and drop the number (`### Setup`); or, if the section really is the task breakdown, move it to `03_tasks.md`. A line-start heading cannot be backticked away.
  - A **bare reference** to a real downstream task → name the file or phase instead of the number (e.g. "see the Tasks phase" or "tasks.md").
  - An **example token**, or your document's own local label (e.g. a test-function ID) → backtick it (`` `T5` ``).
