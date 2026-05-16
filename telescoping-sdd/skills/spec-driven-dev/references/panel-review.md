# Panel Review

This reference defines the shared panel-review mechanism used by Phases 1–3 of the spec-driven-dev workflow. The same loop runs in Phase 1 (Specify), Phase 2 (Design), and Phase 3 (Tasks) — only the panelists change. Phase 4 (Implement) does not use the panel.

The agent's self-review catches internal issues. The cross-doc consistency check catches conversation-context issues. The panel catches blind-spot and quality issues. Run this loop after the self-review and any cross-doc check, before validation and the human review gate.

## Path placeholders

This reference uses two script-root placeholders defined in the main `SKILL.md` Overview:

* `<script-path>` — the skill's own `scripts/` directory.
* `<shared-script-path>` — the plugin-wide `telescoping-sdd/scripts/` directory containing `archive_pass.py`.

## Panelists per phase

- **Specify:** `telescoping-sdd:user-advocate`, `telescoping-sdd:devils-advocate`, `telescoping-sdd:pragmatist`
- **Design:** `telescoping-sdd:architect`, `telescoping-sdd:testability-reviewer`, `telescoping-sdd:security-reviewer`
- **Tasks:** `telescoping-sdd:delivery-manager`, `telescoping-sdd:critic`, `telescoping-sdd:simplifier`

> Always invoke panelists by their `telescoping-sdd:` prefix so the plugin's customised persona resolves rather than the built-in of the same name.

## The Loop

1. **Dispatch all three panelists in a single message.** Issue three Agent tool calls in the same response block — not three separate responses with waits between them. If you find yourself reading Panelist 1's output before Panelist 2 and 3 are invoked, you've serialized; abort and re-dispatch all three at once. The synthesis in step 2 must wait until all three have returned. Pass each panelist the current artifact and any upstream approved artifacts as context. The invocation prompt must explicitly include the contents of the artifact's `### Sealed dispositions` sub-section followed by the instruction: *"Do not re-raise items in the Sealed dispositions list unless you have new substantive evidence that did not appear in the prior disposition."* Without this instruction, panelists tend to re-raise sealed items each pass; the format change in `### Sealed dispositions` only helps if the prompt actively suppresses re-raise. Ask each panelist for a ranked list of concerns, each with a severity tag (`[HIGH]`, `[MED]`, or `[LOW]` — bracketed exactly as written), a one-line description, and a brief rationale. Regressions caught this pass should be additionally tagged `[REGRESSION]`.
2. **Synthesize in-thread** — read the three outputs, dedupe overlapping concerns, drop concerns the self-review or cross-doc check already resolved, and rank the remainder by severity.
3. For each remaining concern, apply one of these dispositions:
   - **Addressed** — the fix is clear and stays within the current phase's scope. Apply the fix to the artifact and note what changed.
   - **Deferred → `<TARGET.md>`** — the concern belongs in a later phase (e.g., `architect` raises a task-ordering concern during Design). Record it without resolving in-phase; the downstream phase reads deferrals as input.
   - **Sealed** — a user-directed decision the panel should not re-raise (e.g., user chose 2-feature split over 3). Notes must include `Defense: <reason>` so `archive_pass.py` can promote it to `### Sealed dispositions`.
   - **Accepted as risk** — the concern is valid but the user, after being asked, explicitly accepts it as a known risk. Notes must include `Defense: <reason>` (same promotion path as Sealed).
   - **User input needed** — the concern requires a judgment call you cannot make alone. Stop, ask the user, apply the resolution, and update the disposition to one of the others.
   - **Halt and re-scope** — fundamental scope-shaped concern (see `## Halt and Re-scope Exit` below). Two consecutive passes with this disposition fires the halt-trigger.
4. Write every concern and its disposition as a row in `### Latest pass detail` of the artifact's `## Panel Review` section (format below). Self-check entries from step 5 also land here, with `Source` set to `[SELF-CHECK] (a|b|c)`.
5. Run the **Synthesizer Self-Check** (see § below) against the just-applied fixes. If issues are found, fix them and re-run the checklist; only proceed when every item is answered with cited evidence and any issues found are fixed.
6. Run `python <shared-script-path>/archive_pass.py <artifact>` to archive this pass — promotes any newly-sealed items into `### Sealed dispositions`, appends a row to `### Trajectory` (with HIGH / regression / disposition counts; halt votes recorded in Notes), and clears `### Latest pass detail`. If the script exits 1, 2, or 3, fix the reported issue and re-invoke; do not proceed with unresolved violations.
7. **Halt-trigger check.** Read the last two rows of `### Trajectory`. If both rows' Notes column contains "halt vote" (case-insensitive substring match), the halt-trigger has fired — see `## Halt and Re-scope Exit` below for what to do. Otherwise proceed to step 8.
8. If this pass returned no new HIGH-severity concerns, exit the loop and proceed to validation (the trajectory row gets `converged (0 HIGH)` stamped in Notes by `archive_pass.py` to mark convergence in the historical record) — **unless this was a STRICT-BAR pass, which exits through the cross-check in `## Strict-Bar Convergence Mode` instead of exiting directly.** MEDIUM and LOW concerns from the final pass are still synthesized, disposed, and recorded in `### Latest pass detail` before archive — they just do not block exit. Rationale: HIGH issues are convergence-blocking (contradictions, regressions, unimplementable claims); MEDIUM/LOW are polish that surfaces in PR and implementation review anyway, so looping for them has diminishing value. **Cap: 5 passes.** If HIGH concerns remain after 5 passes, stop and ask the user: continue reviewing, or move on. Otherwise (HIGHs remain, cap not yet reached), repeat from step 1 against the updated artifact. Each new pass reads the full doc fresh — including the cleared `### Latest pass detail` and the cumulative `### Sealed dispositions` list (panelists are instructed not to re-raise sealed items unless they have new substantive evidence).

**Mode.** The loop runs in NORMAL mode by default. When the trajectory shows the panel spinning on downstream-deferrable findings, `archive_pass.py` emits a `STRICT-BAR-SIGNAL:` advisory and the synthesizer asks the user whether to switch the next pass to STRICT-BAR mode — see `## Strict-Bar Convergence Mode` below. Mode changes the panelist prompts and adds an exit cross-check; it does not change the step sequence above. When counting passes against the 5-pass cap, count NORMAL, STRICT-BAR, and skipped passes; **exclude** cross-check passes (their `### Trajectory` Notes contain `cross-check pass`).

## Panel Review section format

Each artifact ends with a `## Panel Review` section placed immediately before the Approval section. The section has three sub-sections, in this order:

```
## Panel Review

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|

### Sealed dispositions

(bullet list of `[SEAL-NN]` entries; empty until the first sealed item)

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|
```

`archive_pass.py` is built to this layout — it parses, promotes, and clears these sub-sections. The format below is normative; the script will reject violations.

**Trajectory** — one row per archived pass. `Pass` and `Date` are filled in by `archive_pass.py`; the count columns come from parsing the latest pass detail at archive time. For skipped passes (`archive_pass.py --skip`), all count columns are dashed (`—`) and `Notes` is `skipped (mechanical: <reason>)`.

**Sealed dispositions** — durable decisions that survive across passes. Each entry has the form:

```
- `[SEAL-NN]` **<Title>** (pass <N>, <user-directed | accepted-as-risk>) — Defense: <reason>.
```

`[SEAL-NN]` is sequential, two-digit zero-padded, assigned by `archive_pass.py` when it promotes an entry from Latest pass detail. Panelist prompts in subsequent passes include this list with the instruction *"do not re-raise sealed items unless you have new substantive evidence."*

**Latest pass detail** — the most recent panel pass's concerns + dispositions. `archive_pass.py` clears this table at the start of each new pass; the synthesizer (you) populates it as the panel raises concerns. Format contract:

- `Severity` — exactly one of `[HIGH]`, `[MED]`, `[LOW]`. Optionally followed by `[REGRESSION]` for regressions caught this pass (e.g. `[HIGH] [REGRESSION]`).
- `Source` — panelist name (e.g. `devils-advocate`) or `[SELF-CHECK] (a|b|c)` for synthesizer self-check entries.
- `Concern` — one-line concern text.
- `Disposition` — exactly one of: `Addressed`, `Deferred → <target>`, `Sealed`, `Accepted as risk`, `User input needed`, `Halt and re-scope`.
- `Notes` — rationale, fix description, target. For `Sealed` and `Accepted as risk`, **must include** `Defense: <reason>` — `archive_pass.py` lifts this verbatim into `### Sealed dispositions`.

Example rows:

| Severity            | Source              | Concern                                                | Disposition          | Notes                                                                              |
|---------------------|---------------------|--------------------------------------------------------|----------------------|------------------------------------------------------------------------------------|
| [HIGH]              | devils-advocate     | R7 has no testable acceptance criterion                | Addressed            | Added AC7c with measurable threshold                                               |
| [HIGH] [REGRESSION] | [SELF-CHECK] (b)    | RETURNING returns post-UPDATE on SQLite                | Addressed            | Reverted to SELECT-then-UPDATE in §4.2                                             |
| [MED]               | testability-reviewer| No fixture strategy for retarget detection             | Deferred → tasks.md  | Pick up in T7-fixtures                                                             |
| [MED]               | simplifier          | Drop R8, ship R7 only                                  | Sealed               | Defense: User explicitly directed to keep R8 in scope; R7+R8 ship together for v1. |

An artifact with any concern still in `User input needed` disposition fails validation — every concern must land on `Addressed`, `Deferred`, `Sealed`, or `Accepted as risk` before approval (`Halt and re-scope` disposition rows do not survive into approved artifacts — `archive_pass.py` clears them with the rest of `### Latest pass detail`; the Trajectory may still carry historical `halt vote` notes from passes the user chose to override, which is intentional and does not block approval). `archive_pass.py` blocks archiving any pass with unresolved `User input needed` rows. For `tasks.md` (the last artifact phase), concerns cannot be deferred forward; they must land on `Addressed`, `Sealed`, or `Accepted as risk`.

## Synthesizer Self-Check

After applying fixes from a pass and **before triggering the next panel pass**, you (the calling Claude — the synthesizer) must verify your own work against three categories of regression that the panel caught after-the-fact in prior real-world cycles. The panel is an effective independent reviewer for design issues, but it is wasteful to use a full panel cycle to catch bugs your own fixes just introduced. Run the self-check first; the panel can then focus on what only it can catch.

**Why this exists:** in observed cycles, three classes of synthesizer-introduced regressions were the load-bearing convergence blockers — claims that turned out to be unimplementable on the target stack, fixes that silently broke contracts elsewhere in the doc, and bulk-substitution edits that left tautologies and orphaned references. Each one burned a full panel cycle to catch. Self-check would have caught all three at synthesizer time.

**Three checks:**

**(a) Contract preservation** — for each fix you applied, did it change an interface, schema, return value, error code, configuration shape, or invariant referenced elsewhere in the artifact (or a sibling artifact like `design.md` / `tasks.md`)? If yes, are all references still valid? Did your fix contradict a previously sealed disposition (`Accepted as risk` or user-directed decision)?

**(b) Implementability** — for each new technical claim you added, is it actually true on the target stack / language / library version / SQL dialect / framework? Cite the source (docs URL, grep result against the codebase, code reference). Do not rely on training-data recall for stack-specific behavior.

**(c) String-substitution hygiene** — after any rename / sed-class change / bulk edit: are there tautologies (e.g., `F26 + F26`, `F26/F26`, "F26 were merged")? Orphaned cross-references (`see §X` where §X has been removed)? Unbalanced markers (e.g., `[BEGIN ...]` without `[END ...]`)? Run `grep` and cite the result.

**Forcing function (structured checklist):** answer this checklist explicitly, citing evidence for every item. Do not write "looks fine" — show your work.

```
For each fix applied this pass:
  1. What did it change? (1-line description)
  2. (a) Is it referenced elsewhere in the doc or in sibling artifacts?
     `grep` proves yes/no. If yes, does each reference still hold?
     List each reference and its status.
  3. (b) Does it make a technical claim about the target stack? If yes,
     verify against the stack's docs and cite the source (URL, file path,
     or grep result).
  4. (c) Did it involve string substitution / rename / bulk edit? If yes,
     run pattern-match for tautologies, orphans, and unbalanced markers,
     and cite the grep results.

For each issue found: apply the fix and re-run the checklist from step 1.

Only proceed to the next panel pass when the checklist runs clean
on every fix from this pass.
```

**Recording:** write each self-check finding into `### Latest pass detail` as a separate row, with `Source` set to `[SELF-CHECK] (a)`, `(b)`, or `(c)` matching the check it came from:

| Severity | Source                | Concern                                                              | Disposition | Notes                            |
|----------|-----------------------|----------------------------------------------------------------------|-------------|----------------------------------|
| [HIGH]   | [SELF-CHECK] (b)      | RETURNING returns post-UPDATE on SQLite — claim unimplementable      | Addressed   | Reverted to SELECT-then-UPDATE   |
| [MED]    | [SELF-CHECK] (a)      | Global 422 handler would override per-endpoint contracts at /users   | Addressed   | Scoped handler to /jira/* prefix |
| [LOW]    | [SELF-CHECK] (c)      | Found 3 `F26/F26` tautologies after collapse                         | Addressed   | Cleaned up                       |

**What self-check does not replace:**
- The panel review — self-check catches synthesizer regressions; the panel catches design-level and blind-spot issues. Different failure modes.
- The validator — self-check is per-fix, the validator checks the artifact globally. Both still run.

**Interaction with panel skip (When to Skip the Panel, below):** self-check runs *before* the skip decision. If self-check finds a semantic issue (anything in (a) or (b)), the change is no longer purely mechanical — abort the skip and run a normal panel pass. The (c) hygiene check overlaps with the lint step in panel skip; that redundancy is cheap and intentional — same checks at different stages.

## Halt and Re-scope Exit

The panel can signal that an artifact's problems are scope-shaped — that iterating the panel won't help because the feature is fundamentally the wrong size or boundary. When that signal fires across two consecutive passes, the spec loop halts and routes to the project-blueprint amendment workflow to re-decide feature boundaries. The original spec stays in its current state with the halt recorded in its Trajectory; the amendment workflow produces new boundaries; the spec loop restarts on each re-scoped artifact.

This is the **scope-pivot exit** — distinct from the soft pass budget (a fallback for general convergence failure) and distinct from the HIGH-count exit (which fires on successful convergence).

**When to use the `Halt and re-scope` disposition.** When a panelist raises a scope-shaped concern, judge:

- *Tightening-shaped* (e.g., "this AC could be sharper", "narrow this requirement") → `Addressed`
- *Defer-shaped* (e.g., "this concern belongs in M3 not M2") → `Deferred → <target>`
- *Fundamental* (e.g., "this is 7 PRs in a trench coat", "feature spans separate release windows") → `Halt and re-scope`

The third disposition is a **vote**, not a final decision. A single halt vote does not halt the loop. **Two consecutive passes**, each with at least one `Halt and re-scope` disposition, fires the trigger. Multiple halt votes within a single pass count as one halt vote for trigger purposes.

**Halt-trigger check (loop step 7).** After `archive_pass.py` runs, read the last two rows of `### Trajectory`. If both rows' Notes column contains "halt vote" (case-insensitive substring match), the halt-trigger has fired. Stop — do **not** invoke the next panel pass.

**Halt summary and user confirmation.** Draft a brief halt summary citing both halt votes (Pass numbers, source panelists, concern titles) and what re-scoping is needed. Present to the user:

```
Halt-and-rescope triggered. Two consecutive passes voted halt:
  - Pass <N>:   <source> — <concern>
  - Pass <N+1>: <source> — <concern>
Route to project-blueprint amendment workflow? [y/n]
```

- **On user confirmation:** stop the spec-driven-dev workflow on this artifact. Invoke the project-blueprint amendment workflow on the affected feature(s). After re-scoping, restart the spec loop on each re-scoped artifact (it will start with a fresh Trajectory).
- **On user override:** continue the spec loop. The user has out-of-band context (e.g., "this feature must ship together for compliance"). The trigger will re-fire if halt votes keep coming on subsequent passes — each pass is a fresh opportunity to halt.

**Why two consecutive (not one):** a single panelist having a bad day shouldn't blow up the workflow. Two consecutive passes saying "halt" is durable signal that scope, not phrasing, is the problem. The synthesizer can manually halt for non-consecutive patterns (e.g., halt votes at passes 3 and 6 with intervening passes that disposed unrelated concerns) — present the halt summary to the user even if `archive_pass.py` hasn't auto-detected the trigger.

**Interaction with skipped passes (panel skip, below):** the trigger check reads the last two trajectory rows literally. A skipped row (`skipped (mechanical: ...)` in Notes) breaks the consecutive-halt sequence — the auto-detection won't fire if a halt-voted pass is followed by a skipped pass. If you see a halt pattern interrupted by a skip and believe scope is still the issue, manually present the halt summary to the user even though `archive_pass.py` didn't auto-trigger.

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
- **AND >50% of disposed concerns across those two passes are `Deferred → <DOWNSTREAM>`** — i.e. the panel is mostly producing downstream work, not this-phase fixes. In Phase 3 (Tasks, the last phase) concerns cannot be deferred forward, so the signal reduces to "HIGH-count not dropping and most concerns are requirement-level or design-level — i.e. belong upstream — rather than task-level."

### Auto-detection (fire-and-ask) and manual invocation

After every NORMAL archive, `archive_pass.py` checks both trigger conditions against the last two NORMAL trajectory rows (the just-archived row plus the most recent prior NORMAL row, stepping over any intervening strict-bar / cross-check / skipped rows). When both conditions are met, the script emits a `STRICT-BAR-SIGNAL:` line on stdout summarising the HIGH delta and the deferred-downstream percentage. The synthesizer reads that advisory and **asks the user**:

> "Strict-bar trigger fired (HIGH delta ..., XX% deferred downstream). Switch the next pass to strict-bar mode? (yes / no)"

- **User says yes** — the next pass runs in STRICT-BAR mode.
- **User says no** — the next pass stays NORMAL. If the trigger fires again on the following pass, ask again; the advisory is never silently auto-applied.

The user can also request strict-bar without waiting for the trigger — saying "strict bar" at any time switches the next pass, including before the trigger has fired (e.g. for an artifact the user already believes is converged).

### Running a strict-bar pass

Same panelists, same loop steps 1–7. The only change is the invocation prompt: load `references/strict-bar-prompts.md` and append the core filter rule, the current phase's excluded/required lists, and the inspectability instruction to every panelist's prompt. Synthesize, dispose, self-check, and archive as normal — but archive with `python <shared-script-path>/archive_pass.py <artifact> --strict-bar` so the Trajectory Notes record the mode.

If a strict-bar pass returns HIGHs, those are genuine this-phase decisions — dispose them normally (often `Sealed`, `Accepted as risk`, or `User input needed`) and run another pass. Mode stays STRICT-BAR.

### Exit cross-check

When a STRICT-BAR pass returns **zero HIGHs**, do not exit directly. Run **one** final NORMAL panel pass as an audit, and archive it with `--cross-check` (this pass does **not** count toward the 5-pass cap). Then judge its HIGHs:

- **Cross-check returns 0 HIGHs** → exit the loop. Proceed to validation.
- **Cross-check returns HIGHs, but all of them match the exclusion categories** the strict-bar prompt declined (design choices, task breakdown, test strategy, etc.) → exit the loop, validated. The cross-check confirmed the strict bar filtered correctly; the cross-check is itself a normal pass, so record and dispose its concerns exactly as a normal pass would (§ The Loop, step 3) before archiving.
- **Cross-check returns HIGHs that do *not* all match the excluded categories** → the strict bar over-filtered. Set mode back to NORMAL, dispose the cross-check's concerns normally, and continue the loop from step 1. **The 5-pass cap counter does NOT reset** — something unusual is happening, so the user-decision gate stays where it is.

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

## When to Skip the Panel

If the only edits since the last panel pass are **mechanical** — string substitutions, file moves, validator-driven changes, or removed-already-decided content with no new semantic content — replace the panel with an automated lint check. Lint-class work doesn't need a design review; running a full panel on a sed cleanup wastes cycles and risks the panel objecting to phrasing artifacts of the cleanup itself.

**Mechanical vs. not:**

| ✅ Mechanical (eligible to skip)                     | ❌ Not mechanical (run panel)                  |
|------------------------------------------------------|------------------------------------------------|
| Rename throughout the doc                            | Add or remove a requirement                    |
| Fix typos, formatting, table alignment               | Reword to change intent                        |
| Drop sections already deferred to a later artifact   | Restructure features (split / merge / collapse) |
| Apply validator-flagged edits                        | Change a dep-table edge                        |
| Cross-reference cleanup after a rename               | Add or remove acceptance criteria              |

**Skip flow (no user gate; the Trajectory row is the audit trail):**

1. Synthesizer applies the fix and declares the change category: `Mechanical: <reason>` (e.g., "rename F26 → F26.1, 15 occurrences").
2. **Lint runs automatically:**
   - Run the validator (`<script-path>/validate_spec.py`) — must pass.
   - `grep` for sed-damage patterns: tautologies (e.g., `F26 + F26`, `F26/F26`), orphaned references (`see §X` where §X has been removed), unbalanced markers.
   - Synthesizer self-reads the diff — every changed line must be traceable to the declared rule. If any line introduces new semantic content, the change isn't mechanical; abort the skip and run a panel.
   - Cross-doc consistency — references in sibling artifacts (e.g., `tasks.md`, `design.md`) still resolve.
3. **If lint fails:** auto-fall-back to a normal panel pass. The lint failure means the declaration was wrong.
4. **If lint passes:** invoke `python <shared-script-path>/archive_pass.py <artifact> --skip "<reason>"` to record a skipped row in `### Trajectory` (all count columns dashed; Notes set to `skipped (mechanical: <reason>)`). No confirm prompt — the trajectory row is the audit trail. Proceed to the next pass (or to validation if convergence is met).

**User override (out-of-band, optional):**
- *Pre-empt:* user instructs "run a panel even though this is mechanical" before the pass starts (e.g., for fragile areas where they want extra eyes).
- *Retro-challenge:* user questions a recorded skip after the fact and requests a panel pass on the affected change.

**What the synthesizer must NOT do:**
- Skip without declaring the change category (no silent skips).
- Skip when the change is partly mechanical and partly semantic — split into two passes (mechanical first, semantic second).
- Skip when the synthesizer self-check flagged a new issue that wasn't fixed.
- Skip without lint actually running.
