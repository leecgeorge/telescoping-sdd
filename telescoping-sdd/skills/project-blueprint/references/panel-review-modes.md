# Panel Review — Modes (lightweight, panel skip, gate change requests)

> **Loaded on demand.** A situational sub-reference of `panel-review.md`. Load it only when: the user opts into a single-pass review (lightweight mode), a change is mechanical enough to skip the panel (when to skip the panel), or a change request arrives at the review gate (handling change requests at the review gate). A NORMAL panel pass never needs it — the normal loop, panelists, format contract, and Synthesizer Self-Check all live in `panel-review.md`.

## Lightweight Mode (single-pass panel)

The default loop — drafting subagent (≤5 self-review passes) plus a ≤5-pass convergence panel of three personas, with strict-bar, halt-and-rescope, and the exit cross-check layered on — is calibrated for **substantial, long-lived, multi-feature work**: a blueprint other people will build a whole project against, that will be re-entered and amended, where a missed contradiction or unmet goal is expensive to discover late. On a small single-component project, a throwaway prototype, or an exploratory spike, that machinery is disproportionate — the strict-bar/halt/cross-check apparatus exists to *reach* convergence on rich documents, and there is little to converge on.

For those cases the user may opt into **lightweight mode**: one panel pass, then exit. This is distinct from `## When to Skip the Panel` below — skip is gated on *mechanical re-edits* of an already-reviewed artifact and explicitly cannot apply to a fresh draft; lightweight mode is the opposite, a single *genuine* panel pass on a fresh small artifact. The default stays the full loop; lightweight mode is **opt-in only** and never auto-selected.

**When it fits (the user says so):** the user describes the work as small, throwaway, exploratory, a prototype/spike, or a single-component project, and explicitly asks for a lighter review (e.g. "this is a throwaway prototype, do a light review", "single-pass panel", "lightweight mode"). If the user hasn't said the work is small, run the full loop. If you believe a nominally-small project is actually load-bearing (it will spawn many features, it commits a Cross-Feature Contract, it is the foundation other work depends on), say so and recommend the full loop before accepting the opt-in.

**The single pass:**

1. Run **one** NORMAL panel pass exactly as `## The Loop` steps 1–4 describe — same three panelists, dispatched together, synthesized in-thread, each concern disposed (`Addressed` / `Deferred → <target>` / `Sealed` / `Accepted as risk` / `User input needed`), every row written to `### Latest pass detail`. Phase 2/3 concern tagging still applies.
2. Run the **Synthesizer Self-Check** (`panel-review.md § Synthesizer Self-Check`) against the fixes — this is *not* skipped; it is the cheap catch for synthesizer-introduced regressions and stays mandatory in lightweight mode.
3. Archive the pass with `python <shared-script-path>/archive_pass.py <artifact> --phase <N>` (add `--terminal` for the terminal Phase-3 artifact `PLAN.md`). No special flag exists for lightweight mode — it is an ordinary NORMAL archive; the single Trajectory row is the audit trail.
4. **Exit to validation regardless of remaining HIGHs.** Do not loop. Before exiting, surface any unresolved HIGH concerns to the user in one line each so the lighter bar is an informed choice ("Lightweight pass left 2 HIGH concerns unresolved: … — proceed to approval, or switch to the full loop?"). `User input needed` rows must still be resolved before validation can pass — lightweight mode does not relax the validator.

**What lightweight mode turns off:** the convergence loop (no second pass to drive HIGHs to zero), the strict-bar trigger and STRICT-BAR mode, the exit cross-check, and the 5-pass cap (there is only one pass). The `STRICT-BAR-SIGNAL:` advisory `archive_pass.py` may emit after the archive is informational only here — do not act on it.

**What it keeps:** the drafting subagent and its self-review, your own re-review and any cross-doc consistency check, the full disposition vocabulary, the Synthesizer Self-Check, the format contract for `## Panel Review`, validation, and the human approval gate. The halt-and-rescope *disposition* is still available on the single pass — if the one pass surfaces a fundamentally-wrong scope (or an `[upstream]` tag in Phase 2/3), present the halt summary from `## Halt and Re-scope Exit` rather than waving it through; a project too big to review lightly is exactly the signal lightweight mode must not suppress.

**Mid-stream and re-approval interaction:** lightweight mode governs only the *fresh-artifact* panel. Re-Approval After Edits and mid-stream entry (their upstream panel re-review step) are governed by their own flow in `references/hash-and-cascade.md` and are unaffected; a small artifact's later edits still route through that flow normally.

## When to Skip the Panel

If the only edits since the last panel pass are **mechanical** — string substitutions, file moves, validator-driven changes, or removed-already-decided content with no new semantic content — replace the panel with an automated lint check. Lint-class work doesn't need a design review; running a full panel on a sed cleanup wastes cycles and risks the panel objecting to phrasing artifacts of the cleanup itself.

**Mechanical vs. not:**

| ✅ Mechanical (eligible to skip)                     | ❌ Not mechanical (run panel)                  |
|------------------------------------------------------|------------------------------------------------|
| Rename throughout the doc                            | Add or remove a goal / constraint              |
| Fix typos, formatting, table alignment               | Reword to change intent                        |
| Drop sections already deferred to a later artifact   | Restructure features (split / merge / collapse) |
| Apply validator-flagged edits                        | Change a dep-table edge or milestone scope     |
| Cross-reference cleanup after a rename               | Add or remove a feature                        |

**Skip flow (no user gate; the Trajectory row is the audit trail):**

1. Synthesizer applies the fix and declares the change category: `Mechanical: <reason>` (e.g., "rename F26 → F26.1, 15 occurrences").
2. **Lint runs automatically:**
   - Run the validator (`<script-path>/validate_blueprint.py`) — must pass.
   - `grep` for sed-damage patterns: tautologies (e.g., `F26 + F26`, `F26/F26`), orphaned references (`see §X` where §X has been removed), unbalanced markers.
   - Synthesizer self-reads the diff — every changed line must be traceable to the declared rule. If any line introduces new semantic content, the change isn't mechanical; abort the skip and run a panel.
   - Cross-doc consistency — references in sibling artifacts (e.g., `SCOPE.md`, `ARCHITECTURE.md`, `PLAN.md`) still resolve.
3. **If lint fails:** auto-fall-back to a normal panel pass. The lint failure means the declaration was wrong.
4. **If lint passes:** invoke `python <shared-script-path>/archive_pass.py <artifact> --phase <N> --skip "<reason>"` to record a skipped row in `### Trajectory` (all count columns dashed; Notes set to `skipped (mechanical: <reason>)`). No confirm prompt — the trajectory row is the audit trail. (For the terminal Phase-3 artifact `PLAN.md`, add `--terminal` to the command above — `archive_pass.py` hard-rejects that filename without it; see the Terminal-archive invocation in `## The Loop`, step 6.) Proceed to the next pass (or to validation if convergence is met).

**User override (out-of-band, optional):**
- *Pre-empt:* user instructs "run a panel even though this is mechanical" before the pass starts (e.g., for fragile areas where they want extra eyes).
- *Retro-challenge:* user questions a recorded skip after the fact and requests a panel pass on the affected change.

**What the synthesizer must NOT do:**
- Skip without declaring the change category (no silent skips).
- Skip when the change is partly mechanical and partly semantic — split into two passes (mechanical first, semantic second).
- Skip when the synthesizer self-check flagged a new issue that wasn't fixed.
- Skip without lint actually running.

## Handling change requests at the review gate

The phase docs end with **"Stop and ask the user to review `<artifact>` before proceeding"** (`phase-{scope,architecture,plan}.md` § Validation and approval). The common case at that gate is the user reading the presented artifact and saying *"no, change X"* **before** approving. This is still a panel-relevant change, so it routes back into the loop above — it does **not** get applied silently and re-presented.

The artifact has **not been approved yet**, so it has no content hash. This is the load-bearing difference from `hash-and-cascade.md § "Re-Approval After Edits"` (which fires only on an *already-approved* document): there is **no re-stamp and no downstream cascade** at the pre-approval gate. You just incorporate the change, re-converge the panel, and re-present. (`Re-Approval After Edits` is the post-approval analogue — same idea, but it adds the hash re-stamp and the consistency-check cascade because approved downstreams may now be measured against stale upstream content.)

**Route by the size of the requested change** (the same trivial-vs-substantive cut the loop already uses):

| Requested change | Route | Records a Trajectory pass? |
|---|---|---|
| **Substantive** — adds/removes/reshapes a goal, constraint, requirement, AC, scope boundary, component, dependency edge, or any intent-bearing content | Treat as a new panel-relevant change. Re-enter the loop: apply the change (**re-drafting via the phase's analyst agent — mandatory for all substantive gate-change requests**, per the delegation brief in `references/hash-and-cascade.md` § "Revise the downstream"; the scope-verify + content-preservation check applies before re-stamp), then run a fresh panel pass (§ The Loop). | **Yes** — a normal NORMAL pass via `archive_pass.py <artifact> --phase <N>`. |
| **Trivial wording** — typo, phrasing, formatting, or other change with no new semantic content | Apply as a synthesizer fix, then run the **Synthesizer Self-Check** (`panel-review.md § Synthesizer Self-Check`) against it. If the Self-Check stays clean (nothing in (a)/(b)), it is mechanical and **panel-skip-eligible** under `## When to Skip the Panel` — record a skipped Trajectory row, do not run a full panel. | **Yes** — either a NORMAL pass or a `--skip` row; never a silent edit. |

**Rule of thumb:** if the change could alter what a panelist would say (a goal, a constraint, a component, a contract, a boundary), re-run the panel. If it only changes how existing intent is *worded*, it is a candidate for the panel skip — but the Synthesizer Self-Check decides: a "wording" change that the Self-Check finds touches a contract or an implementability claim is no longer trivial, and the skip aborts to a full panel (per `## When to Skip the Panel`, "abort the skip and run a normal panel pass").

**Either way, the change is recorded as a Trajectory pass** — it is another panel-relevant change to a not-yet-approved artifact, so it counts against the 5-pass cap exactly like any other pass (a skip is still a loop iteration). Dispose any concerns it surfaces with the normal vocabulary (`Addressed` / `Deferred` / `Sealed` / `Accepted as risk`). Then re-present the updated artifact at the same gate. Only when the user approves does the phase run its validator (`validate_blueprint.py --approve <phase>`) and stamp the first content hash — at which point any *later* edit becomes a `Re-Approval After Edits` event, not a gate change request.

**What the synthesizer must not do:** apply a gate change request silently without a Trajectory row (no audit trail); re-stamp or run a cascade (no hash exists yet — those belong to the post-approval flow); or treat a substantive scope/requirement change as trivial to avoid a panel pass.
