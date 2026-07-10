# Panel Review — Convergence (strict-bar + halt-and-rescope)

> **Loaded on demand.** A situational sub-reference of `panel-review.md`. Load it only when a convergence trigger fires: `archive_pass.py` emits a `STRICT-BAR-SIGNAL:` advisory, or an `[upstream]` tag / two consecutive halt votes appear. A NORMAL panel pass never needs it — the normal loop, panelists, format contract, concern tagging, and Synthesizer Self-Check all live in `panel-review.md`.
>
> **Exception — the terminal compression check is not situational.** The `## Terminal Compression Check` section in this file runs at every convergence (on any exit path, immediately before validation), so a NORMAL pass *does* reach it. It is homed here only for co-location with the exit cross-check it is contrasted against; it is not trigger-gated.

## Halt and Re-scope Exit

The panel can signal that an artifact's problems are scope-shaped — that iterating the panel won't help because the feature is fundamentally the wrong size or boundary. When that signal fires across two consecutive passes, the spec loop halts and routes to the project-blueprint amendment workflow to re-decide feature boundaries. The original spec stays in its current state with the halt recorded in its Trajectory; the amendment workflow produces new boundaries; the spec loop restarts on each re-scoped artifact.

This is the **scope-pivot exit** — distinct from the soft pass budget (a fallback for general convergence failure) and distinct from the HIGH-count exit (which fires on successful convergence).

**When to use the `Halt and re-scope` disposition.** When a panelist raises a scope-shaped concern, judge:

- *Tightening-shaped* (e.g., "this AC could be sharper", "narrow this requirement") → `Addressed`
- *Defer-shaped* (e.g., "this concern belongs in M3 not M2") → `Deferred → <target>`
- *Fundamental* (e.g., "this is 7 PRs in a trench coat", "feature spans separate release windows") → `Halt and re-scope`

The third disposition is a **vote**, not a final decision. A single halt vote does not halt the loop. **Two consecutive passes**, each with at least one halt vote, fires the trigger. Multiple halt votes within a single pass count as one halt vote for trigger purposes.

**A halt vote is recorded when EITHER:**
- a panelist disposes a finding as `Halt and re-scope` (the explicit case), OR
- a panelist tags a finding `[upstream]` in Phase 2 or Phase 3 (auto-routed by `archive_pass.py` regardless of the panelist's chosen disposition — per `## Concern tagging (Phase 2 and 3)`).

The `[upstream]` auto-route exists because the explicit `Halt and re-scope` disposition is rare in practice — panelists default to `Addressed` (which silently papers over the upstream gap by forcing a fix in the current artifact that pretends the upstream artifact committed the decision) or `Accepted as risk` (which seals the gap as deliberate). Neither response surfaces the upstream gap to the user. Auto-routing on `[upstream]` catches the pattern even when the panelist doesn't choose the disposition explicitly.

**Halt-trigger check (loop step 7).** After `archive_pass.py` runs, read the last two rows of `### Trajectory`. If both rows' Notes column contains "halt vote" (case-insensitive substring match), the halt-trigger has fired. Stop — do **not** invoke the next panel pass.

**Halt summary and user confirmation.** Draft a brief halt summary citing both halt votes (Pass numbers, source panelists, concern titles, and whether each was an explicit `Halt and re-scope` disposition or an auto-routed `[upstream]` tag) and what re-scoping is needed. Present to the user.

For an explicit-disposition halt (scope-shaped framing problem at the feature level):

```
Halt-and-rescope triggered. Two consecutive passes voted halt:
  - Pass <N>:   <source> — <concern>
  - Pass <N+1>: <source> — <concern>
The panel believes this feature's framing is fundamentally wrong.
Route to project-blueprint amendment workflow? [y/n]
```

For an `[upstream]`-tag halt (Phase 2 or 3 panel surfacing earlier-phase gaps in this feature's own artifacts):

```
Halt-and-rescope triggered. Two consecutive passes raised [upstream]
concerns indicating the <PHASE> panel is exposing gaps in <UPSTREAM>:
  - Pass <N>:   <source> — <concern>
  - Pass <N+1>: <source> — <concern>
Update <UPSTREAM> to commit these decisions, then re-cascade and
restart this phase. [acknowledge / override]
```

`<UPSTREAM>` is `spec.md` (for a Phase-2 halt) or `spec.md` and/or `design.md` (for a Phase-3 halt — the `[upstream]` tag's concern should indicate which).

- **On user confirmation (explicit Halt):** stop the spec-driven-dev workflow on this artifact. Invoke the project-blueprint amendment workflow on the affected feature(s). After re-scoping, restart the spec loop on each re-scoped artifact (it will start with a fresh Trajectory).
- **On user confirmation (`[upstream]` halt):** stop the current phase. The user updates the upstream artifact (`spec.md` or `design.md`), the cascade machinery (see `references/hash-and-cascade.md`) re-stamps it, then this phase restarts with a fresh Trajectory.
- **On user override:** continue the spec loop. The user has out-of-band context (e.g., "this feature must ship together for compliance"). The trigger will re-fire if halt votes keep coming on subsequent passes — each pass is a fresh opportunity to halt.

**Why two consecutive (not one):** a single panelist having a bad day shouldn't blow up the workflow. Two consecutive passes saying "halt" is durable signal that scope, not phrasing, is the problem. The synthesizer can manually halt for non-consecutive patterns (e.g., halt votes at passes 3 and 6 with intervening passes that disposed unrelated concerns) — present the halt summary to the user even if `archive_pass.py` hasn't auto-detected the trigger.

**Interaction with skipped passes (`panel-review-modes.md § When to Skip the Panel`):** the trigger check reads the last two trajectory rows literally. A skipped row (`skipped (mechanical: ...)` in Notes) breaks the consecutive-halt sequence — the auto-detection won't fire if a halt-voted pass is followed by a skipped pass. If you see a halt pattern interrupted by a skip and believe scope is still the issue, manually present the halt summary to the user even though `archive_pass.py` didn't auto-trigger.

**What the synthesizer must not do:**
- Auto-execute the re-scope without user confirmation.
- Manually clear halt votes from the Trajectory to suppress the trigger.
- Treat halt votes as `Addressed` without a real fix that changes the underlying scope problem.

## Strict-Bar Convergence Mode

On a moderately rich artifact, the panel reliably finds 2–4 HIGH concerns per pass even after many iterations — but past a certain point most of what it raises is real *and* legitimately belongs in a later phase (a Specify-phase panelist surfacing an interface-design concern that belongs in `design.md`; a Design-phase panelist surfacing a task-sizing concern that belongs in `tasks.md`). Each such concern gets disposed `Deferred → <DOWNSTREAM>` and the doc never converges. The panel is doing honest work; the loop just can't tell "still finding *this-phase* concerns" from "fully converged, grinding on downstream-deferrable items."

Strict-bar mode recalibrates the panel from "find concerns" to "find concerns that need a decision at *this* phase." It is a **convergence tool, not a default** — the early NORMAL passes are where the panel earns its keep (contradictions, missing requirements, untestable ACs, ambiguities). Switching too early suppresses real findings.

### Trigger condition (the signal to watch for)

The synthesizer watches `### Trajectory` for this two-part signal:

- **HIGH-count not meaningfully dropping (delta ≥ -1) across the last two NORMAL passes** — i.e. the panel isn't making real progress closing HIGH concerns. A drop of 2 or more is genuine convergence and the trigger does *not* fire there; only stable or rising HIGH-count qualifies as the spinning pattern this mode is for.
- **AND a phase-dependent ratio condition exceeds 0.5 across those two passes:**
  - **Phase 1 and Phase 2:** >50% of disposed concerns are `Deferred → <DOWNSTREAM>` — i.e. the panel is mostly producing downstream work, not this-phase fixes.
  - **Phase 3 (Tasks, the last artifact phase):** >50% of disposed concerns are tagged `[detail]` (per `## Concern tagging (Phase 2 and 3)`). Phase 3 has no further artifact phase — Phase 4 is implementation, not a panel — and concerns cannot be deferred forward. `[detail]` is the Phase-3 analogue of "belongs in a later phase" (it identifies implementation-time concerns that the Implement phase will naturally surface). `archive_pass.py` reads `[detail]` counts from the `tags=dXuYcZ` substring it stashes in the Trajectory Notes at archive time.

**`[upstream]` tags do NOT contribute to the strict-bar trigger.** They route to the halt-and-rescope trigger instead (see § Halt and Re-scope Exit). Strict-bar is "find concerns at *this* phase" — `[upstream]` concerns belong at an *earlier* phase, so filtering them in strict-bar would silently let the upstream gap persist. The two triggers are deliberately disjoint.


> **Worked example (R7).** A Phase-1 pass shows: 4 Addressed, 0 literal Deferred, 3 Sealed — 2 of those 3 Sealed rows were expanded by `archive_pass.py` from `Defense: rerouted [DEF-NN]` markers (i.e., they are re-routed-deferral rows, each beginning `Defense: already routed to …`). Trajectory's Sealed column records 3. Trigger's deferred-equivalent for this pass = 2 (the `rerouted_def_count`). Pooled over two passes where the previous pass had 4 literal Deferred (and 4 Addressed, 0 Sealed): `pooled_deferred = 4 + 2 = 6`; `pooled_total = (4+4+0) + (4+0+3) = 15`; `ratio = 6/15 = 40%`, below the >50% threshold — trigger does not fire. If the previous pass had 6 literal Deferred (and 1 Addressed, 0 Sealed) and the current has 2 rerouted + 1 Addressed: `pooled_deferred = 6 + 2 = 8`; `pooled_total = (1+6+0) + (1+0+2) = 10`; `ratio = 8/10 = 80%` — trigger fires.

### Auto-detection (fire-and-ask) and manual invocation

After every NORMAL archive, `archive_pass.py` checks both trigger conditions against the last two NORMAL trajectory rows (the just-archived row plus the most recent prior NORMAL row, stepping over any intervening strict-bar / cross-check / skipped rows). When both conditions are met, the script emits a `STRICT-BAR-SIGNAL:` line on stdout summarising the HIGH delta and the phase-appropriate ratio (deferred-downstream percentage for Phase 1/2; `[detail]`-tag percentage for Phase 3). The synthesizer reads that advisory and **asks the user**, citing the same ratio:

> Phase 1 or 2:
> "Strict-bar trigger fired (HIGH delta ..., XX% deferred downstream). Switch the next pass to strict-bar mode? (yes / no)"

> Phase 3:
> "Strict-bar trigger fired (HIGH delta ..., XX% of disposed concerns tagged [detail]). The panel is finding real concerns but most are implementation-time and will be caught in Phase 4 (Implement). Switch the next pass to strict-bar mode? (yes / no)"

- **User says yes** — the next pass runs in STRICT-BAR mode.
- **User says no** — the next pass stays NORMAL. If the trigger fires again on the following pass, ask again; the advisory is never silently auto-applied.

The user can also request strict-bar without waiting for the trigger — saying "strict bar" at any time switches the next pass, including before the trigger has fired (e.g. for an artifact the user already believes is converged).

### Running a strict-bar pass

Same panelists, same loop steps 1–7. The only change is the invocation prompt: load `references/strict-bar-prompts.md` and append the core filter rule, the current phase's excluded/required lists, and the inspectability instruction to every panelist's prompt. Synthesize, dispose, self-check, and archive as normal — but archive with `python <shared-script-path>/archive_pass.py <artifact> --phase <N> --strict-bar` so the Trajectory Notes record the mode. (For the terminal Phase-3 artifact `tasks.md`, add `--terminal` as well — `archive_pass.py` hard-rejects that filename without it; see the Terminal-archive invocation in `## The Loop`, step 6.)

If a strict-bar pass returns HIGHs, those are genuine this-phase decisions — dispose them normally (often `Sealed`, `Accepted as risk`, or `User input needed`) and run another pass. Mode stays STRICT-BAR.

### Exit cross-check

When a STRICT-BAR pass returns **zero HIGHs**, do not exit directly. Run **one** final NORMAL panel pass as an audit, and archive it with `--cross-check` (this pass does **not** count toward the 5-pass cap). Then judge its HIGHs:

- **Cross-check returns 0 HIGHs** → exit the loop. Proceed to validation. **First run the terminal compression check** (`## Terminal Compression Check` in this file — the same pass the NORMAL step-8 exit runs; it applies before validation on every exit path, this one included).
- **Cross-check returns HIGHs that all match the strict-bar prompt's exclusion categories** (Phase 1/2: design choices, task breakdown, test strategy, etc.; Phase 3: all tagged `[detail]` per `## Concern tagging (Phase 2 and 3)`) → exit the loop, validated. The cross-check confirmed the strict bar filtered correctly; record and dispose its concerns exactly as a normal pass would (§ The Loop, step 3) before archiving.
- **Cross-check returns any `[upstream]`-tagged HIGH** (Phase 2 or 3 only) → halt-and-rescope. `archive_pass.py` auto-routes the `[upstream]` row to a halt vote; the cross-check trajectory row will carry "halt vote" in Notes. Surface this to the user using the `[upstream]`-tag halt prompt in `## Halt and Re-scope Exit`. Do not silently filter `[upstream]` concerns as "strict-bar exclusion match."
- **Cross-check returns HIGHs that do *not* match the excluded categories** (Phase 1/2: a real at-this-phase concern slipped past strict bar; Phase 3: a `[contract]`-tagged concern slipped past) → the strict bar over-filtered. Set mode back to NORMAL, dispose the cross-check's concerns normally, and continue the loop from step 1. **The 5-pass cap counter does NOT reset** — something unusual is happening, so the user-decision gate stays where it is.

### Exit paths by mode

| Mode | Pass result | Path |
|---|---|---|
| NORMAL | 0 HIGHs | Exit directly (strict bar never ran, so no cross-check needed) |
| NORMAL | HIGHs remain | At the 5-pass cap → stop at the cap gate (ask user: continue or move on). Under cap → stay NORMAL, or (trigger fired and user confirms / user requested) switch the next pass to STRICT-BAR |
| STRICT-BAR | 0 HIGHs | Run the exit cross-check (above) before exiting |
| STRICT-BAR | HIGHs remain | At the 5-pass cap → stop at the cap gate (ask user: continue or move on). Under cap → dispose the strict HIGHs and stay STRICT-BAR |

### Cap accounting

| Pass type | Counts toward 5-pass cap? |
|---|---|
| NORMAL pass | Yes |
| STRICT-BAR pass | Yes — same single counter; mode-switching mid-loop must not buy extra cycles |
| Cross-check pass | No — exit ceremony, not a convergence attempt |
| Skipped pass (`--skip`) | Yes — a skip is still a loop iteration |

| Event | Counter resets? |
|---|---|
| Mode switch NORMAL → STRICT-BAR | No |
| Cross-check kickback STRICT-BAR → NORMAL (filter over-fired) | No |
| Halt-and-rescope confirmed by user (routes to project-blueprint amendment) | Yes — the spec loop restarts on each re-scoped artifact with a fresh Trajectory |
| User confirms "continue" at the 5-pass cap gate | Yes — cost already accepted; don't re-ask every pass |
| User chooses "move on" / accepts remaining HIGHs at the 5-pass cap gate | N/A — the loop exits |

Because cross-check passes still get a `Pass` number from `archive_pass.py`, the synthesizer counts against the cap by reading Trajectory Notes — count every row *except* those whose Notes contain `cross-check pass`.

### Interaction with other exits

- **Halt-and-rescope** takes priority over everything — the step-7 halt-trigger check runs every pass regardless of mode. A strict-bar panelist that sees a feature whose boundary is fundamentally wrong still votes `Halt and re-scope` (which routes to the project-blueprint amendment workflow, per `## Halt and Re-scope Exit`).
- **Panel skip** is orthogonal — a mechanical-only change can be skipped in either mode. A skipped pass does not change the current mode. Its `### Trajectory` row carries dashed counts, so it contributes nothing to the trigger's HIGH-count or deferral-rate read; the synthesizer judges the trigger from the last two *panel* passes, stepping over any `skipped` rows.

## Terminal Compression Check

A single, purely-subtractive compression pass that runs once when the panel converges, as the loop's last act before validation. It is the backstop for the redundancy the per-pass subtractive `Addressed` obligation (`panel-review.md § The Loop` step 3) did not catch — the accretion the loop added across its passes, compressed in one place before the human reviews the artifact.

**Loads at every convergence.** Unlike the strict-bar and halt-and-rescope behaviours in this file — which load only when their trigger fires — this check is **not** situational: it runs at every convergence, whichever exit path the loop took. It is homed here for co-location with the exit cross-check it is contrasted against, not because it is trigger-gated.

**Charter.** "What is restated, or bigger than the feature needs?" — the compression lens borrowed from the `simplifier` agent's charter. It looks only for prose to remove (restated facts and filler), never for anything to add. The check is **purely subtractive**: it applies clearly-safe cuts, declines the rest, and never re-opens a converged or sealed concern, never restores or re-adds content, and never deletes load-bearing content — it only removes restatement and filler, and every applied cut stays reversible by the user at the approval gate.

**When it runs.** Once, at each phase's convergence — independently at every phase that runs a panel, on that phase's own artifact, never once across the whole feature. It runs **immediately before Phase validation, on any exit path the loop took** — the NORMAL 0-HIGH exit (`panel-review.md § The Loop` step 8) or the strict-bar exit cross-check's proceed-to-validation step (`§ Strict-Bar Convergence Mode § Exit cross-check`). It does **not** count toward the 5-pass cap.

**Operator.** The calling Claude (the synthesizer/orchestrator) runs the check and applies the clearly-safe cuts itself. There is no panelist seat and no second automated reviewer: the human gate is the phase's existing approval gate, at which the user reviews the already-compressed artifact before approving. The safety of every cut therefore rests on that review of the final artifact, not on an intermediate actor.

**Clearly-safe cut.** A cut is clearly-safe — and only then is it applied — iff ALL hold: (i) it removes a restatement whose canonical assertion survives intact **and the operator can quote that surviving assertion verbatim** in the applied-cut record, OR it removes pure filler (redundant preamble, transcribed debate) carrying no load-bearing fact, acceptance criterion, interface, data, or boundary content; (ii) it touches no GIVEN/WHEN/THEN clause, numbered requirement or acceptance criterion, interface signature, sealed or deferred disposition, or the `## Approval` / `## Panel Review` machinery; (iii) after the cut every requirement still maps to at least one acceptance criterion and every cross-reference still resolves. Anything else → **decline**: record it, leave the artifact unchanged, and do not re-run. Ties resolve toward decline — the same when-in-doubt-keep-it bias as the under-documentation guardrail.

**Cross-reference audit.** Independently of any cut, the check runs one **always-on, read-only** whole-artifact pass — it runs at every convergence *whether or not* any cut is proposed — verifying that every cross-reference resolves to a section that fully states the referenced fact. Any dangling or under-stated cross-reference is **surfaced to the user at the approval gate**; the check never restores, edits, or re-opens to fix it. This audit is the active defense for the residual risk that a converging pass's subtractive `Addressed` fix over-suppressed a fact into a cross-reference: the user, reading the whole converged artifact at the gate, is the re-read.

**Recorded cuts.** Every applied cut is recorded as an itemized **before → after** entry, surfaced at the approval gate so the user has a diff to catch over-cutting; each restatement-removal quotes the surviving canonical assertion verbatim (the forcing function proving the fact still lives at its home). Operator-declined cuts are noted (judged unsafe, never applied) and not re-run. If the user, seeing the applied-cuts list at the gate, wants a cut restored, that is an ordinary approval-gate revision request handled by the existing gate change-request path — not a bespoke mechanism.

**Relationship to the exit cross-check.** This check and the strict-bar exit cross-check (`§ Strict-Bar Convergence Mode § Exit cross-check`) share exactly **one** property: neither counts toward the 5-pass cap. They differ on both other axes. **Trigger:** this check is *unconditional*, running on every convergence; the cross-check is *conditional*, running only when leaving strict-bar mode. **Scope:** this check is a *single-agent* orchestrator-run compression pass; the cross-check is a *full-panel* audit pass. It is not a mirror of the cross-check — it is a distinct terminal step that merely shares the cap-exclusion.
