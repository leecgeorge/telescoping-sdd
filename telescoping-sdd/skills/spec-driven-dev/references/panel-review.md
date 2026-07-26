<!--
SHARED REFERENCE — keep in sync with the project-blueprint copy at
skills/project-blueprint/references/panel-review.md. Edits to the shared panel-review machinery must be mirrored in BOTH copies.

Intentional asymmetries vs the sibling (do NOT "sync" these away):
- Phase names differ (Scope/Architecture/Plan vs Specify/Design/Tasks); spec-driven-dev also has a panel-less Phase 4 (Implement) that blueprint lacks.
- Terminal Phase-3 artifact is PLAN.md (blueprint) vs tasks.md (spec-driven-dev); the three --terminal archive-command sites differ ONLY in that filename.
- Synthesizer Self-Check is (a)-(f) in blueprint (adds (e) closed-feature-row integrity and (f) CFC authoring fidelity — the CFC PRODUCER role) vs (a)-(d) in spec-driven-dev; the [SELF-CHECK] (a|b|c|d|e|f) vs (a|b|c|d) Source tags follow.
- The "## CFC Compliance Check" section and "Per-feature AC alignment" rubric are spec-driven-dev-only (the CFC CONSUMER check against PLAN.md); blueprint has no counterpart.
- Architecture/Design middle panelist differs: telescoping-sdd:ops-reviewer (blueprint) vs telescoping-sdd:testability-reviewer (spec-driven-dev), including in example tables.
- Halt-and-rescope routes to the user revising project scope/phase boundary (blueprint) vs to the project-blueprint amendment workflow then a spec-loop restart (spec-driven-dev).
- Upstream-halt / sibling-artifact targets are SCOPE.md / ARCHITECTURE.md (blueprint) vs spec.md / design.md (spec-driven-dev).
- The two-paragraph "Cap-pressure caveat" inside `## The Loop` carries shared skill-agnostic doctrine (resist cap-pressure bias toward applying every finding; accept-as-risk is first-class; the verbatim-quote forcing function) but its examples diverge by role: blueprint leans on Self-Check (e)/(f) and CFC-**producer** authoring; spec-driven-dev leans on Self-Check (a)–(d) and the CFC-**consumer** surface (`[CFC-N]` tags + enforcement tasks). Keep the shared doctrine in sync; the role-specific examples are an intentional asymmetry.
Otherwise the copies differ only cosmetically (phase-vocabulary mapping, filenames, illustrative example values).
-->

# Panel Review

This reference defines the shared panel-review mechanism used by Phases 1–3 of the spec-driven-dev workflow. The same loop runs in Phase 1 (Specify), Phase 2 (Design), and Phase 3 (Tasks) — only the panelists change. Phase 4 (Implement) does not use the panel.

The agent's self-review catches internal issues. The cross-doc consistency check catches conversation-context issues. The panel catches blind-spot and quality issues. Run this loop after the self-review and any cross-doc check, before validation and the human review gate.

## Path placeholders

This reference uses two script-root placeholders defined in the main `SKILL.md` Overview:

* `<script-path>` — the skill's own `scripts/` directory.
* `<shared-script-path>` — the plugin-wide `telescoping-sdd/scripts/` directory containing `archive_pass.py`.

## Minimum to run the NORMAL loop

First-pass digest — the rest of this file loads when a trigger fires. To run one normal panel pass:

1. Pick the three panelists for this phase (`## Panelists per phase` below) and dispatch all three in one message, by their `telescoping-sdd:` prefix; pass each the on-disk file path of the artifact under review (and paths of any upstream approved artifacts) with an instruction to read those file(s) from disk in full — see `## The Loop` step 1 for the complete dispatch mechanics. Each panelist **Writes** its findings to `.sdd/panel-findings/<findings_scope>/…` and **returns only a manifest** (path + severity census + one anchor per HIGH), not prose.
2. Ask each for a ranked list of concerns, each tagged `[HIGH]` / `[MED]` / `[LOW]` with a one-line description and rationale (in its findings file). Then dispatch `telescoping-sdd:panel-condenser` `[sonnet/high]` with the findings-file paths + artifact path + phase; it returns one compact disposition-proposal table.
3. Reconcile the table by identity per anchor (fall back to the raw findings on any malformed / empty / unmatched table), then dispose each concern as `Addressed` / `Deferred → <target>` / `Sealed` / `Accepted as risk` / `User input needed`. (Phase 2/3: each HIGH Concern carries a condenser-proposed `[contract]` / `[detail]` / `[upstream]` tag you confirm — see `## Concern tagging`.)
4. Run the **Synthesizer Self-Check** (§ below), then `python <shared-script-path>/archive_pass.py <artifact> --phase <N>` (add `--terminal` for `tasks.md`).
5. Exit when a pass returns no new HIGH concerns; otherwise loop (cap 5 passes).

Load on demand: **strict-bar** mode (only when `archive_pass.py` emits `STRICT-BAR-SIGNAL:`), **halt-and-rescope** (only on `[upstream]` tags / two consecutive halt votes), the **exit cross-check** (only when leaving strict-bar), **lightweight mode** and **panel skip** (only when the user opts in / the change is mechanical).

## Panelists per phase

- **Specify:** `telescoping-sdd:user-advocate`, `telescoping-sdd:devils-advocate`, `telescoping-sdd:pragmatist`
- **Design:** `telescoping-sdd:architect`, `telescoping-sdd:testability-reviewer`, `telescoping-sdd:security-reviewer`
- **Tasks:** `telescoping-sdd:delivery-manager`, `telescoping-sdd:critic`, `telescoping-sdd:simplifier`

> Always invoke panelists by their `telescoping-sdd:` prefix so the plugin's customised persona resolves rather than the built-in of the same name.

## Model tiers

Panelists and drafters run at **pinned** model/effort tiers (set in each agent's frontmatter), so panel behavior is deterministic regardless of the session's effort. This is a deliberate placement — strong model where content is *authored* and *judged*, cheap-but-deep diverse critique in between — **not a quality cut**:

- **Panelists → Sonnet 5, `effort: high`.** The panel is a *recall* mechanism: three diverse personas surfacing concerns, with 3× redundancy. A cheaper model at high reasoning effort suffices here, backstopped by the strong synthesizer and the exit cross-check.
- **Drafters → Opus, `effort: medium`.** The strong model authors the artifact — the highest-quality base is what everything downstream reviews. Medium effort because drafting is generative, not deep multi-step reasoning, and the drafter makes no irreversible call (the panel, the synthesizer, and your approval gate catch misses).
- **Synthesizer / orchestrator (you) → the session model.** All the *precision* work — synthesis, disposition, the self-check, strict-bar recalibration, the convergence decision, and the exit cross-check — stays on the strong model, exactly where the irreversible gate judgments are made.
- **`panel-condenser` → Sonnet 5, `effort: high`.** The condenser is a *recall/compression* step — it reads the panelists' findings files off-thread and folds them into one compact table; it authors nothing and makes no irreversible call (you reconcile by identity and own every disposition). Same cheap-but-deep placement as the panel.
- **`consistency-reader` → Sonnet 5, `effort: high`.** The consistency-reader is the same *recall/locate* placement — it reads a checklist definition and the artifact chain off-thread and returns only located discrepancies; it authors nothing and makes no halt/classification/routing call (you own those).

**Announce tiers at dispatch.** State each agent's model/effort tier in your dispatch message when you fire the panel (and when you delegate a draft) — e.g. `Dispatching panel: architect [sonnet/high], security-reviewer [sonnet/high], …`. Read the tier from this pinned config, never from the agent: a subagent cannot reliably report its own model (the resolved model is not in its context), so an agent's self-identification is not authoritative.

## The Loop

1. **Dispatch all three panelists in a single message.** Issue three Agent tool calls in the same response block — not three separate responses with waits between them. If you find yourself reading Panelist 1's output before Panelist 2 and 3 are invoked, you've serialized; abort and re-dispatch all three at once. The synthesis in step 2 must wait until all three have returned. Pass each panelist the on-disk file path of the artifact under review and the paths of any upstream approved artifacts, and direct each panelist to read those file(s) from disk in full before reviewing (the `### Sealed dispositions` and `### Deferred dispositions` list contents reach each panelist via that disk read); do not paste the body of the content under review (the artifact or any upstream approved artifact) inline in the dispatch prompt, and do not summarize or paraphrase that content for panelists. Include in the dispatch prompt the suppression instruction for the `### Sealed dispositions` list the panelist just read from disk: *"Do not re-raise items in the Sealed dispositions list unless you have new substantive evidence that did not appear in the prior disposition."* Without this instruction, panelists tend to re-raise sealed items each pass; the format change in `### Sealed dispositions` only helps if the prompt actively suppresses re-raise. Also include the suppression instruction for the `### Deferred dispositions` list the panelist just read from disk: *"For items in Deferred dispositions: the concern has already been routed to the named downstream artifact. If you have no new evidence, do not raise it again. If you believe the prior routing was wrong or your evidence is genuinely new, raise it and flag explicitly in your rationale why this is not a duplicate of `[DEF-NN]`."* **Note on `Routed because:` visibility:** the rationale text on each `[DEF-NN]` entry reaches panelists via the on-disk `### Deferred dispositions` list they read; synthesizers must treat the `Routed because:` field as panelist-visible content (factual, one sentence, no embedded instructions). Ask each panelist for a ranked list of concerns, each with a severity tag (`[HIGH]`, `[MED]`, or `[LOW]` — bracketed exactly as written), a one-line description, and a brief rationale. Regressions caught this pass should be additionally tagged `[REGRESSION]`. **Findings to disk, manifest in-thread.** Direct each panelist to **Write** its full findings to `.sdd/panel-findings/<findings_scope>/<artifact-stem>-p<PASS>-<panelist>.md` (`<findings_scope>` = `sdd/<spec-dir-basename>/` for the SDD tier, `blueprint/` for the blueprint tier) as two on-disk sections — a `## Machine findings` ranked list (each line `- [SEVERITY] <one-line concern> — <one-line rationale>`) and a `## Assessment (human)` prose block — and to **return only a manifest**: the findings-file path, a one-line **severity census** (`counts: <H> HIGH / <M> MED / <L> LOW`), plus one anchor per `[HIGH]` it raised (`{id, gist — ≤120 chars, single line, optional scope_hint}`), and nothing else. The panelist returns **no prose bodies and no MED/LOW detail inline** — those live only in the findings file on disk. **A pass that raises zero HIGH still returns the path and the census, with `anchors: (none)`** — the census is what a quiet pass reports, so a panelist never has to choose between saying nothing and substituting prose. (Without it the contract had no compliant form for a zero-HIGH pass, and an observed panelist leaked four MED concerns inline rather than return a bare path.) At **loop re-entry** (each new pass) first clear the prior pass's findings within *this run's* `.sdd/panel-findings/<findings_scope>/` subtree only — never a sibling feature's subtree or the other tier (defense-in-depth; the validator's exit sweep is the backstop).
2. **Synthesize in-thread** — **manifest-presence check first.** Before dispatching the condenser, confirm each panelist actually returned a manifest: a findings-file path that exists on disk, a **severity census**, and one anchor per HIGH the census declares. **The census is what makes a quiet pass verifiable** — `counts: 0 HIGH / …` with `anchors: (none)` is a complete, compliant manifest, whereas a *missing* census is the signal that something went wrong. Anchors alone cannot carry this check: it iterates the manifest anchors, of which a zero-HIGH pass and a prose-returning panelist both supply none, so on anchors alone it passes vacuously and the two are indistinguishable. Treat a missing census, or a census whose HIGH count does not match the anchors supplied, as the degraded mode: dispose from the prose you were handed, and disclose it in the pass summary. Then dispatch the `telescoping-sdd:panel-condenser` subagent (one Agent call, `[sonnet/high]`), passing it the N findings-file paths, the artifact-under-review path, and the phase number — **never** the findings bodies. It reads the findings files from disk, dedupes/merges overlapping concerns across panelists (a merged row names every contributing anchor in `ANCHOR-REFS` and panelist in `SOURCE`), proposes a `SCOPE` tag per Phase 2/3 HIGH row and a disposition per row, and returns **one compact table** — columns `ROW | ANCHOR-REFS | SEVERITY | SOURCE | SCOPE | CONCERN | DISPOSITION-PROPOSAL | FIX-INSTRUCTION` — and nothing else. **Reconcile the returned table by identity, per anchor:** for every `[HIGH]` anchor id in the panelist manifests, confirm exactly one table row's `ANCHOR-REFS` names it (a merged row may name several), its `SEVERITY` was not silently downgraded, and its `CONCERN` matches the manifest gist. **Fall back on failure — read the raw findings files from disk yourself, dispose from them directly, and disclose the degraded mode in the pass summary — whenever** the table is *syntactically* malformed (wrong/reordered headers, any row's cell-count ≠ 8, an out-of-vocab `DISPOSITION-PROPOSAL` base after stripping any `→ <target>`, a missing `SCOPE` on a Phase 2/3 HIGH row, or an embedded newline in `CONCERN`/`FIX-INSTRUCTION` — the grammar `compact_table.validate_compact_table(text, *, phase)` pins), *structurally* off (an empty table when the manifests carried ≥1 HIGH, or no return / a hang), or *fidelity*-off (an anchor left unmatched, a same-id row silently downgraded, or a row whose `CONCERN` contradicts its manifest gist). The condenser **proposes**; you **dispose** — it makes no disposition, self-check, `[upstream]`-confirmation, or vote. **Projection to `### Latest pass detail` (mechanical columns only):** `Severity ← SEVERITY`; `Source ← SOURCE`; `Concern ← SCOPE + " " + CONCERN` for Phase 2/3 HIGH rows (else `Concern ← CONCERN`); `Disposition` and `Notes` are your own judgment (never mechanically copied from `DISPOSITION-PROPOSAL`/`FIX-INSTRUCTION`), and `ROW`/`ANCHOR-REFS` are reconciliation-only, never written on disk. Then drop concerns the self-review or cross-doc check already resolved, and rank the remainder by severity. **When a pass raises 0 new HIGH but the manifests are non-empty, still reconcile the manifest anchors you carry against the table — do not short-circuit on the trajectory HIGH count.**
3. For each remaining concern, apply one of these dispositions:
   - **Addressed** — the fix is clear and stays within the current phase's scope. Apply the fix to the artifact and note what changed. **In-loop per-concern fixes are applied by the orchestrator directly**, not delegated to an analyst: analyst delegation applies at loop *re-entry* on a substantive change (cascade, gate-change re-draft, or backport), not per concern mid-loop. Why this is sound: an in-loop fix is re-reviewed by the very next pass of the same panel loop, so it gets the same stress-test an out-of-loop edit would otherwise lack — whereas a cascade/backport/gate-change edit gets no automatic re-pass, which is exactly why those are delegated. Observable boundary: "in-loop" means *inside an active multi-pass panel loop, disposing a concern this pass raised*; cascade and backport are never in-loop (no panel loop is running when they fire), so they cannot be reframed as in-loop per-concern fixes.
   - **Deferred → `<TARGET.md>`** — the concern belongs in a later phase (e.g., `architect` raises a task-ordering concern during Design). Record it without resolving in-phase; the downstream phase reads deferrals as input.
   - **Sealed** — a user-directed decision the panel should not re-raise (e.g., user chose 2-feature split over 3). Notes must include `Defense: <reason>` so `archive_pass.py` can promote it to `### Sealed dispositions`.
   - **Accepted as risk** — the concern is valid but the user, after being asked, explicitly accepts it as a known risk. Notes must include `Defense: <reason>` (same promotion path as Sealed).
   - **User input needed** — the concern requires a judgment call you cannot make alone. Stop, ask the user, apply the resolution, and update the disposition to one of the others.
   - **Halt and re-scope** — fundamental scope-shaped concern (see `panel-review-convergence.md § Halt and Re-scope Exit`). Two consecutive passes with this disposition fires the halt-trigger.
4. Write every concern and its disposition as a row in `### Latest pass detail` of the artifact's `## Panel Review` section (format below). Self-check entries from step 5 also land here, with `Source` set to `[SELF-CHECK] (a|b|c|d)`. **Phase 2 and Phase 3 only:** prefix the Concern text of every HIGH row with one of `[contract]`, `[detail]` (Phase 3 only), or `[upstream]` — see `## Concern tagging (Phase 2 and 3)` below.
5. Run the **Synthesizer Self-Check** (see § below) against the just-applied fixes. If issues are found, fix them and re-run the checklist; only proceed when every item is answered with cited evidence and any issues found are fixed.
6. Run `python <shared-script-path>/archive_pass.py <artifact> --phase <N>` (where `<N>` is `1`, `2`, or `3` matching the current phase) to archive this pass — promotes any newly-sealed items into `### Sealed dispositions`, appends a row to `### Trajectory` (with HIGH / regression / disposition counts; halt votes recorded in Notes), and clears `### Latest pass detail`. For Phase 2 and 3, the script also stashes a `tags=dXuYcZ` substring in the Notes column recording the count of `[detail]`/`[upstream]`/`[contract]` tags in the just-archived Latest. If the script exits 1, 2, or 3, fix the reported issue and re-invoke; do not proceed with unresolved violations.

   **Terminal-archive invocation.** For tasks.md (the terminal Phase-3 artifact), invoke `python <shared-script-path>/archive_pass.py specs/F<n>-<slug>/03_tasks.md --phase 3 --terminal` (use the artifact's actual filename — bare or `NN_`-prefixed; the validators and `archive_pass.py` resolve either). The `--terminal` flag suppresses `### Deferred dispositions` auto-insert and row promotion, rejects any Deferred-disposed row in Latest as a format violation, and suppresses the strict-bar trigger.
7. **Halt-trigger check.** Read the last two rows of `### Trajectory`. If both rows' Notes column contains "halt vote" (case-insensitive substring match), the halt-trigger has fired — see `panel-review-convergence.md § Halt and Re-scope Exit` for what to do. Otherwise proceed to step 8.
8. If this pass returned no new HIGH-severity concerns, exit the loop and proceed to validation (the trajectory row gets `converged (0 HIGH)` stamped in Notes by `archive_pass.py` to mark convergence in the historical record) — **unless this was a STRICT-BAR pass, which exits through the cross-check in `panel-review-convergence.md § Strict-Bar Convergence Mode` instead of exiting directly.** MEDIUM and LOW concerns from the final pass are still synthesized, disposed, and recorded in `### Latest pass detail` before archive — they just do not block exit. Rationale: HIGH issues are convergence-blocking (contradictions, regressions, unimplementable claims); MEDIUM/LOW are polish that surfaces in PR and implementation review anyway, so looping for them has diminishing value. **Cap: 5 passes.** If HIGH concerns remain after 5 passes, stop and ask the user: continue reviewing, or move on. Otherwise (HIGHs remain, cap not yet reached), repeat from step 1 against the updated artifact. Each new pass reads the full doc fresh — including the cleared `### Latest pass detail` and the cumulative `### Sealed dispositions` list (panelists are instructed not to re-raise sealed items unless they have new substantive evidence).

   **Handling re-raised deferred concerns.** When a panelist raises a concern that substantively matches an existing `[DEF-NN]` entry in `### Deferred dispositions`:

   - **If no new evidence is presented:** dispose as **Sealed** with Notes containing **exactly** `Defense: rerouted [DEF-NN]` (substituting the zero-padded two-digit ID, e.g., `Defense: rerouted [DEF-07]`). No other text in the Notes field. `archive_pass.py` recognises this marker at archive time via `MARKER_STRICT_PAT` and expands it to canonical Defense prose; do not write the canonical prose by hand. The marker must match exactly — case-sensitive `Defense: rerouted`, no hyphen in `rerouted`, two-digit zero-padded ID in square brackets. Near-miss forms (`re-routed`, `defense: rerouted`, single-digit ID `[DEF-1]`, smart-quote brackets) cause a hard-fail at archive time.
   - **If genuinely new evidence is presented:** dispose normally — `Addressed` if fixable in-phase, or `Deferred → <TARGET>` with Notes `Routed because: <new rationale>. See also [DEF-NN].` The Trajectory's Deferred count increments if re-deferred.

   *Positive example.* Panelist: "spec.md logging section has no structured-field spec." Check `### Deferred dispositions`: `[DEF-03]` **Logging structure detail** → tasks.md (pass 2) — Routed because: structured-log field design belongs in tasks. No new evidence. Synthesizer writes: `Disposition = Sealed`, `Notes = Defense: rerouted [DEF-03]`. Archive expands to: `Defense: already routed to tasks.md as [DEF-03]; no new evidence presented this pass.`

   *Negative example.* Same concern, but panelist cites a new regulatory requirement making the omission a compliance gap. The cite is genuinely new. Correct disposition: `Deferred → tasks.md` with `Notes = Routed because: compliance gap not present at pass 2; escalate in tasks. See also [DEF-03].` The concern re-enters `### Deferred dispositions` as `[DEF-04]`; the Trajectory Deferred column increments.

**Mode.** The loop runs in NORMAL mode by default. When the trajectory shows the panel spinning on downstream-deferrable findings, `archive_pass.py` emits a `STRICT-BAR-SIGNAL:` advisory and the synthesizer asks the user whether to switch the next pass to STRICT-BAR mode — see `panel-review-convergence.md § Strict-Bar Convergence Mode`. Mode changes the panelist prompts and adds an exit cross-check; it does not change the step sequence above. When counting passes against the 5-pass cap, count NORMAL, STRICT-BAR, and skipped passes; **exclude** cross-check passes (their `### Trajectory` Notes contain `cross-check pass`).

**Cap-pressure caveat.** In re-entered loops (after `--skip`, after a re-stamp cascade, or any restart that does not reset the cap counter), the 5-pass cap counter advances quickly and may bias the synthesizer toward "address every panelist finding with prose" in pursuit of convergence. **Resist this.** The synthesizer's job is to *judge* each panelist proposal against existing doctrine (seals, sealed dispositions, CFC-consumer obligations, the Self-Check (a)–(d) categories), not to apply every proposal. **Accepting-as-risk** a finding with a documented `Defense:` is a first-class disposition; it is often the *correct* outcome when accepting prevents a regression cascade (the panelist's proposal would introduce a new bug, or contradict an existing invariant or a previously sealed decision). The 5-pass cap is a stopping point, not a deadline. If the cap is about to be reached and HIGH concerns remain, the right move is to stop, escalate to the user, and accept the un-converged state — not to pattern-match on a panelist's proposed-fix wording and apply it without examining the doctrinal premise. A `[CFC-N]`-tagged consumer obligation is one of the most common doctrinal premises to lose under cap pressure: a panelist proposes loosening or re-wording a `[CFC-N]` acceptance criterion (or dropping its enforcement task) to clear a finding; the doctrinal-correct response is that the per-feature AC is fixed by the PLAN's CFC text — re-route to an Upstream Change Request, do not silently weaken the contract.

Cap-pressure also tilts toward **domain ignorance**: authoring spec/design/tasks prose that names commitments about other artifacts (e.g., "PLAN F7's contract requires X", "design.md already defines this interface", "sibling spec F3 owns the writer") without grep-verifying each named feature or mechanism against the source text. Sharpened Self-Check (b) extends to claims about the project's own approved artifacts (`blueprint/PLAN.md`, `design.md`, `tasks.md`, sibling specs); for cross-artifact claims, "the citation exists" is not sufficient — the cited text must literally support the specific claim. When in doubt under cap pressure: **quote the source verbatim in the self-check record before applying the fix**. The verbatim quote is the forcing function — without it, the synthesizer can pattern-match on adjacency; with it, the source text is physically in front of the synthesizer and the gap (e.g., a `[CFC-N]` AC whose THEN clause does not match the PLAN's stated per-feature AC) becomes visible. The CFC consumer surface — `[CFC-N]` tags on spec.md acceptance criteria and the matching enforcement task in tasks.md — is the most drift-prone surface for this class; cross-check it against the PLAN's `### CFC-N` block (see `## CFC Compliance Check`) rather than against adjacency.

## Pass summary surface

After each pass's reconciliation (`## The Loop` step 2) and before the archive (step 6), emit a short **pass summary** to the operator — the human-facing channel for what happened off-thread this pass, since the panelists' full findings never entered the main thread. It states:

- The **findings-file paths** written this pass (one per panelist), so the operator can open any panelist's full findings on disk.
- Any **degraded-mode disclosure** — when the condenser output was malformed / empty / non-returning and you fell back to reading the raw findings directly, say so plainly (which panelist(s), and why).
- Any **`[upstream]` scope mismatch** — when a panelist's `scope_hint` and the condenser's proposed `SCOPE` for the same anchor disagree, name the anchor and both values so the `[upstream]` confirmation is auditable.

The summary is plain prose (no structured logger), consistent with existing loop notes (e.g. `Upstream panel re-review: skipped …`). It never blocks the pass — it is disclosure only.

## Autonomy Boundary

The panel loop is mostly Claude's to run without asking. The most common way the loop gets silently skipped is by **re-routing a mandated step through a fake approval gate** — pausing to "ask permission" to run a pass that doctrine already requires. This section draws the line between what Claude executes autonomously and the narrow set that genuinely needs the user.

| Execute autonomously (never ask) | Stop and ask the user |
|----------------------------------|------------------------|
| Running the next pass while any HIGH concern remains | The phase-boundary approval gate (e.g. approve spec.md before Design) |
| Archiving between passes (`archive_pass.py`) | A single concern whose disposition is a genuine judgment call (architecture choice, ambiguous requirement, scope change) |
| The mechanical dispositions doctrine can assign (Addressed / Deferred / Sealed) | `Halt and re-scope` |
| The cross-check EXIT pass (the one NORMAL pass run when a STRICT-BAR pass returns 0 HIGH) | The 5-pass cap gate ("continue reviewing, or move on?" when HIGH remain after 5 passes) |
| | The STRICT-BAR ENTRY mode-switch (the `STRICT-BAR-SIGNAL` is fire-and-**ask**: put the yes/no to the user before switching modes) |

Phase-name examples above use this skill's phases (Specify / Design / Tasks); the rules are identical across phases.

**STRICT-BAR ENTRY belongs on the stop-and-ask side; only the cross-check EXIT pass is autonomous.** Conflating the two — treating "strict-bar transitions" as autonomous — would hand a future Claude a lever to skip a real user consultation, the precise prose-drift this boundary exists to prevent.

Four load-bearing rules:

- **(a) Loop continuation is mechanical: `running the next pass is not a user decision`.** When a pass returns HIGH concerns, the next pass is required by the loop, not chosen by the user. Do not pause to ask whether to continue.
- **(b) `no doctrine-shortcut menus`.** Never present a doctrine-MANDATED step as an optional choice — in particular, never offer an "approve now vs. run the next pass" menu. This does NOT ban the doctrine's own sanctioned prompts (the phase-gate approval, the STRICT-BAR yes/no, the 5-pass cap continue/move-on, the Halt acknowledge/override), which are REQUIRED prompts, not banned menus. (The single-concern judgment-call gate is an ad-hoc question, not a recurring mandated-step menu, so it is intentionally not in that exception list.)
- **(c) `operational concerns never override doctrine`.** Token budget, session length, and time are never grounds to interrupt or truncate the loop. If the user wants to stop, they interrupt; Claude does not pre-emptively offer to cut doctrine-mandated work. This does NOT override the sanctioned 5-pass cap gate, which is a doctrine-internal stop, not an operational concession.
- **(d) Pre-flight contract.** At the start of a phase, state the contract once: you will `run the loop to convergence autonomously`, pausing only at the real gates enumerated above (the phase gate, a genuine judgment call, Halt, the 5-pass cap, the STRICT-BAR entry).

## Panel Review section format

Each artifact ends with a `## Panel Review` section placed immediately before the Approval section. The section has four sub-sections, in this order (the terminal Phase-3 artifact `tasks.md` omits `### Deferred dispositions` — the `--terminal` archive suppresses it, since a terminal artifact has no later phase to defer to):

```
## Panel Review

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|

### Sealed dispositions

(bullet list of `[SEAL-NN]` entries; empty until the first sealed item)

### Deferred dispositions

(bullet list of `[DEF-NN]` entries; empty until the first deferred item — omitted on terminal Phase-3 `tasks.md`)

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|
```

`archive_pass.py` is built to this layout — it parses, promotes, and clears these sub-sections. The format below is normative; the script will reject violations.

**Trajectory** — one row per archived pass. `Pass` and `Date` are filled in by `archive_pass.py`; the count columns come from parsing the latest pass detail at archive time. For skipped passes (`archive_pass.py --skip`), all count columns are dashed (`—`) and `Notes` is `skipped (mechanical: <reason>)`.

**Trajectory trim on every archive.** On **every** archive pass — `archive_pass.py` in any mode (NORMAL, `--strict-bar`, `--cross-check`, `--skip`), not only at approval — the Trajectory table is trimmed to the latest 15 data rows, so a long-lived loop's table stays bounded mid-loop instead of growing until the approval pass. Older rows are replaced with a single elided summary row at the top of the data section:

```
| … | … | — | — | — | — | — | N earlier passes elided |
```

`N` is the count of rows that were elided; the trim merges the existing elided count with new elisions, so it is cumulative across passes and approvals. The trim is skipped only for a genuine **committed-v1** artifact (an approved document whose stored content hash predates the v2 hash basis — trimming its Trajectory would invalidate that committed hash). For a never-yet-approved artifact (the common mid-loop case) and for every v2-approved artifact, the trim runs and is **hash-neutral**: the content hash is computed over a trajectory-stripped document, so trimming rows never moves the hash. Documents with ≤ 15 data rows are unchanged. The motivation is long-lived specs (re-entered loops, multi-phase amendments) whose trajectory tables grow unboundedly and dominate the rendered panel-review section; the trim preserves the audit-trail headline via the elided count without losing the recent context the synthesizer actually reads (halt-trigger, strict-bar trigger, cap counting all read the latest 1–2 rows). Because there is no per-pass commit, per-pass detail elided beyond the latest 15 rows is not automatically retained — it is recoverable only if an intermediate archive state was committed to version control; the elided-count headline and the never-trimmed `### Sealed dispositions` / `### Deferred dispositions` lists survive on disk regardless.

**Sealed dispositions** — durable decisions that survive across passes. Each entry has the form:

```
- `[SEAL-NN]` **<Title>** (pass <N>, <user-directed | accepted-as-risk>) — Defense: <reason>.
```

`[SEAL-NN]` is sequential, two-digit zero-padded, assigned by `archive_pass.py` when it promotes an entry from Latest pass detail. Panelist prompts in subsequent passes include this list with the instruction *"do not re-raise sealed items unless you have new substantive evidence."*

**Deferred dispositions** — concerns routed to a named downstream artifact, surviving across passes so panelists do not re-raise them. Each entry has the form `` `[DEF-NN]` **<Title>** → <TARGET.md> (pass <N>) — Routed because: <reason>. `` `[DEF-NN]` is sequential, two-digit zero-padded, assigned by `archive_pass.py` when it promotes a `Deferred → <target>` row from Latest pass detail. Panelist prompts in subsequent passes include this list with the re-raise-suppression instruction (see § The Loop, step 1). On a legacy non-terminal artifact missing the sub-section, `archive_pass.py` auto-inserts the heading. The terminal Phase-3 artifact `tasks.md` does not carry this sub-section — `--terminal` suppresses both the auto-insert and promotion, and rejects any `Deferred`-disposed row in Latest.

**Latest pass detail** — the most recent panel pass's concerns + dispositions. `archive_pass.py` clears this table at the start of each new pass; the synthesizer (you) populates it as the panel raises concerns. Format contract:

- `Severity` — exactly one of `[HIGH]`, `[MED]`, `[LOW]`. Optionally followed by `[REGRESSION]` for regressions caught this pass (e.g. `[HIGH] [REGRESSION]`).
- `Source` — panelist name (e.g. `devils-advocate`) or `[SELF-CHECK] (a|b|c|d)` for synthesizer self-check entries.
- `Concern` — one-line concern text. Escape any literal pipe as `\|` — an unescaped `|` adds a phantom cell, and `archive_pass.py`'s `parse_table` silently drops a row whose cell count differs from the header.
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

## Concern tagging (Phase 2 and 3)

For NORMAL passes in Phase 2 (Design) and Phase 3 (Tasks), each HIGH-severity row in `### Latest pass detail` must prefix its `Concern` text with one of three scope tags. Phase 1 (Specify) does not use tags — its existing `User input needed` and `Deferred → DOWNSTREAM` dispositions handle every routing case it needs.

The tags are advisory labels chosen by the synthesizer (you) based on what the finding actually is. They are **orthogonal** to dispositions: a `[contract]` finding can be `Addressed` or `Accepted as risk`; an `[upstream]` finding can be `Addressed` or `Halt and re-scope`. Tags affect routing of triggers (halt and strict-bar); dispositions remain the panel's response to each individual concern.

**Condenser proposes, you confirm.** When the `panel-condenser` runs (the NORMAL loop, step 2), it **proposes** each HIGH row's scope tag in the compact table's `SCOPE` column, using cross-panelist context an individual panelist lacks — so a proposed tag may differ from any single panelist's `scope_hint`, which is expected. The proposal is a candidate only; you (the synthesizer) remain the owner. Validate that every Phase 2/3 HIGH row carries a well-formed `[contract]` / `[detail]` (Phase 3 only) / `[upstream]` tag, and **confirm any `[upstream]` tag semantically before it lands** — it is halt-gate input. When a panelist's `scope_hint` and the condenser's proposed `SCOPE` disagree, surface that mismatch in the pass summary and resolve it as part of the `[upstream]` confirmation.

- **`[contract]`** — this finding is an at-this-phase cross-task or cross-component decision. In Phase 2 (design.md): an interface signature an implementation must respect; a shared error-handling contract; a cross-component invariant. In Phase 3 (tasks.md): a cross-task ordering dependency; an interface contract another task's tests will assert against; a shared fixture pattern multiple tasks depend on.
- **`[detail]`** — Phase 3 only: this finding is an implementation-time concern the Implement phase would naturally surface (single-task naming, intra-task structure, fixture details inside one task, edge-case enumeration that materialises while writing the code). Phase 2 does not use `[detail]`; its existing `Deferred → DOWNSTREAM` disposition handles the "belongs in a later phase" case directly.
- **`[upstream]`** — this finding exposes a gap in an earlier-phase artifact. In Phase 2: shaped like a requirement or acceptance criterion that `spec.md` doesn't commit. In Phase 3: shaped like a requirement, AC, or design decision that `spec.md` or `design.md` doesn't commit.

**Tagging affects two triggers:**

1. **Halt-and-rescope trigger.** A `[upstream]`-tagged row auto-routes to a halt vote, alongside the existing `Halt and re-scope` disposition. Two consecutive NORMAL passes with at least one halt vote each fires the halt-trigger — see `panel-review-convergence.md § Halt and Re-scope Exit`.
2. **Strict-bar trigger.** In Phase 3, the strict-bar signal switches from `Deferred → DOWNSTREAM` accumulation to `[detail]`-tag accumulation (Phase 3 has no further artifact phase — Phase 4 is implementation, not an artifact panel — so `[detail]` is the Phase-3 analogue). Phase 1 and Phase 2 keep the deferred-based signal — see `panel-review-convergence.md § Strict-Bar Convergence Mode`.

`[contract]`-tagged findings contribute to neither trigger. They are the legitimate work product of an at-this-phase panel and flow through the disposition vocabulary normally.

**Tag format.** The tag is the first thing in the `Concern` cell, in lowercase, square-bracketed. Examples:

```
| [HIGH] | architect           | [contract] RetryPort interface must accept idempotency key in v2     | Addressed | added in §4.2 |
| [HIGH] | critic              | [detail] T7 doesn't enumerate the off-by-one fixture variants       | Addressed | named in T7   |
| [HIGH] | testability-reviewer| [upstream] Spec R4 doesn't define behavior under partial failure    | Halt and re-scope | escalate |
```

`archive_pass.py` parses the leading tag substring; missing or malformed tags are silently uncounted (the synthesizer self-check verifies their presence — see § Synthesizer Self-Check check (d)).

## CFC Compliance Check

When `blueprint/PLAN.md` exists at the project root and contains a `## Cross-Feature Contracts` section, every spec / design / tasks panel includes a CFC-compliance check. Append the following to each panelist's invocation prompt:

> Cross-check this feature's artifact against every `### CFC-N` in `blueprint/PLAN.md` whose `**Participating features:**` list includes this feature (the spec carries its identifier on the `**PLAN feature identifier:**` line). Raise a HIGH concern if:
>
> - The artifact contradicts the CFC's `Contract` clause or its `Per-feature AC`.
> - Phase 1 (Specify): the spec's acceptance criteria omit the CFC's `Per-feature AC` line tagged `[CFC-N]` on a THEN line.
> - Phase 2 (Design): the design proposes a code path that violates a binding CFC, OR this feature is named (as bare token `F<n>`, word-boundary) in the CFC's `Enforcement` prose but the design does not specify how the verifying artifact will be implemented and where it lives.
> - Phase 3 (Tasks): this feature is named in the CFC's `Enforcement` prose as artifact owner, but `tasks.md` contains no `[CFC-N]`-tagged task whose deliverable is the named artifact.
>
> If the CFC itself looks wrong (the Participating-features list is mistaken, the Per-feature AC text is unworkable as written, the Enforcement is infeasible), tag the finding `[upstream]` and you **MUST** name the affected `CFC-<M>` in the concern text verbatim (the literal token `CFC-N` where N is the integer). The halt prompt will name `spec.md` / `design.md` as the local target; recognise from the concern text that the gap is actually in PLAN.md and the right remediation is via the project-blueprint amendment workflow.

**Panel rubric on Per-feature AC alignment.** When comparing a spec's tagged THEN line to the CFC's `Per-feature AC`, treat as substantive (raise as HIGH): changes to the entities named, the obligation verb (must/should/may), the trigger condition, or the assertion target. Treat as non-substantive (do not raise): tense, voice, subject pronouns, definite/indefinite articles, and minor punctuation. If unsure whether a change is substantive, raise it — a false-positive panel concern is one Disposition row; a false-negative is a silently weakened contract.

## Synthesizer Self-Check

After applying fixes from a pass and **before triggering the next panel pass**, you (the calling Claude — the synthesizer) must verify your own work against three categories of regression that the panel caught after-the-fact in prior real-world cycles. The panel is an effective independent reviewer for design issues, but it is wasteful to use a full panel cycle to catch bugs your own fixes just introduced. Run the self-check first; the panel can then focus on what only it can catch.

**Why this exists:** in observed cycles, three classes of synthesizer-introduced regressions were the load-bearing convergence blockers — claims that turned out to be unimplementable on the target stack, fixes that silently broke contracts elsewhere in the doc, and bulk-substitution edits that left tautologies and orphaned references. Each one burned a full panel cycle to catch. Self-check would have caught all three at synthesizer time.

**Five checks:**

**(a) Contract preservation** — for each fix you applied, did it change an interface, schema, return value, error code, configuration shape, or invariant referenced elsewhere in the artifact (or a sibling artifact like `design.md` / `tasks.md`)? If yes, are all references still valid? Did your fix contradict a previously sealed disposition (`Accepted as risk` or user-directed decision)?

**(b-i) Implementability AND intra-artifact fidelity** — for each new technical claim you added — whether about external stack / language / library version / SQL dialect / framework OR about content in approved project artifacts (`blueprint/PLAN.md`, `blueprint/SCOPE.md`, `blueprint/ARCHITECTURE.md`, sibling feature specs) — verify the cited source actually supports the *specific* claim, not just adjacent text. **Quote the supporting passage verbatim in the self-check record.** "Citation exists" is not sufficient — the cited text must literally say what your claim says. For intra-artifact claims, run `grep` and paste the matching line(s) in the self-check entry's Notes. For external claims, paste the docs URL or code reference plus the specific sentence or code-shape that supports the claim. Do not rely on training-data recall for stack-specific behaviour or paraphrased recall for artifact content. The verbatim-quote requirement is a forcing function: without a quote, the check can't pass cleanly; with a quote, the synthesizer is physically confronted with the cited text and can't pattern-match on adjacency. (Per the post-implementation field observation in `documentation/CFC.md § Domain-Ignorance in CFC Authoring`.)

**(b-ii) Symmetric application** (recorded under the same `[SELF-CHECK] (b)` Source tag as (b-i)) — when a fix excludes, drops, differentiates, or otherwise treats one item differently from others in a list, set, or enumeration based on cited evidence, apply the same source-check to every other item in the same list before archiving. Example: if a requirement is removed from this spec because grepping its acceptance criteria shows it overlaps with a sibling spec's commitment, run the same grep against every other requirement in the same list and either (i) remove them too, or (ii) record a verbatim quote in the self-check Notes showing why their evidence shape *is* different. Per-claim verbatim quotes prove individual claims; symmetric application prevents the most common residual error — rigorous evidence for the items the synthesizer questioned, casual acceptance of the items the synthesizer didn't think to question. (Per the v2 acceptance-test residual finding recorded in `documentation/CFC.md § Domain-Ignorance in CFC Authoring`.)

**(c) String-substitution hygiene** — after any rename / sed-class change / bulk edit: are there tautologies (e.g., `F26 + F26`, `F26/F26`, "F26 were merged")? Orphaned cross-references (`see §X` where §X has been removed)? Unbalanced markers (e.g., `[BEGIN ...]` without `[END ...]`)? Run `grep` and cite the result.

**(d) Tag presence (Phase 2 and 3 only)** — for each HIGH row from a panelist source in `### Latest pass detail` this pass, verify the `Concern` text begins with one of `[contract]`, `[detail]` (Phase 3 only), or `[upstream]` (per `## Concern tagging (Phase 2 and 3)`). `[SELF-CHECK]` rows are exempt — they describe synthesizer-side self-check findings (any of categories a/b/c/d), not at-this-phase panelist routing decisions, and `archive_pass.py` does not count their tags for halt/strict-bar routing. MED and LOW rows are also exempt (they don't block convergence). Missing or wrong-format tags on HIGH panel rows silently break the halt-and-rescope and strict-bar triggers; fix any missing tag before archiving. Cite each tagged row.

Additionally, **when `blueprint/PLAN.md` contains a `## Cross-Feature Contracts` section**, you (the synthesizer, as part of this self-check — `archive_pass.py` has no CFC awareness and does not perform this scan) scan every `[upstream]` HIGH row's concern text for the regex `\bCFC-\d+\b`. If a CFC-related concern is plausible (at least one CFC in PLAN names this feature in its Participating features) AND any `[upstream]` HIGH row's concern lacks the `CFC-<M>` token, surface a soft WARN yourself: "Panelist `<source>`'s `[upstream]` concern at row `<row-id>` does not name a `CFC-<M>` token. If this concern is about a Cross-Feature Contract, edit the concern text to name the affected CFC so the user knows to look in PLAN.md." Informational; does not block archiving. The CFC-routing premise (panelists name `CFC-<M>` in concern text → user reads concern → user edits PLAN) depends on this discipline; the synthesizer-emitted WARN is the cheap reminder.

**Forcing function (structured checklist):** answer this checklist explicitly, citing evidence for every item. Do not write "looks fine" — show your work.

```
For each fix applied this pass:
  1. What did it change? (1-line description)
  2. (a) Is it referenced elsewhere in the doc or in sibling artifacts?
     `grep` proves yes/no. If yes, does each reference still hold?
     List each reference and its status.
  3. (b) Does it make a technical claim about the target stack OR a claim
     about content in approved project artifacts (blueprint/PLAN.md,
     blueprint/SCOPE.md, blueprint/ARCHITECTURE.md, sibling feature
     specs)? If yes, verify against the actual source (docs / file path /
     grep result) AND **quote the supporting passage verbatim** in the
     self-check record. "Citation exists" is not sufficient — the cited
     text must literally say what the claim says.
  3a. (b-ii) Symmetric application: does the fix exclude, drop, or
      differentiate one item from a list/set based on cited evidence?
      If yes, run the same source-check on every other item in the
      same list before archiving. Drop them too, or record a verbatim
      quote showing why their evidence shape is different.
  4. (c) Did it involve string substitution / rename / bulk edit? If yes,
     run pattern-match for tautologies, orphans, and unbalanced markers,
     and cite the grep results.

Phase 2 and 3 only — for every HIGH row in Latest pass detail:
  5. (d) Does the Concern text begin with [contract], [detail] (Phase 3
     only), or [upstream]? List each row + tag, or "no tag" with the row.

For each issue found: apply the fix and re-run the checklist from step 1.

Only proceed to the next panel pass when the checklist runs clean
on every fix from this pass.
```

**Recording:** write each self-check finding into `### Latest pass detail` as a separate row, with `Source` set to `[SELF-CHECK] (a)`, `(b)`, `(c)`, or `(d)` matching the check it came from:

| Severity | Source                | Concern                                                              | Disposition | Notes                            |
|----------|-----------------------|----------------------------------------------------------------------|-------------|----------------------------------|
| [HIGH]   | [SELF-CHECK] (b)      | RETURNING returns post-UPDATE on SQLite — claim unimplementable      | Addressed   | Reverted to SELECT-then-UPDATE   |
| [MED]    | [SELF-CHECK] (a)      | Global 422 handler would override per-endpoint contracts at /users   | Addressed   | Scoped handler to /jira/* prefix |
| [LOW]    | [SELF-CHECK] (c)      | Found 3 `F26/F26` tautologies after collapse                         | Addressed   | Cleaned up                       |

**What self-check does not replace:**
- The panel review — self-check catches synthesizer regressions; the panel catches design-level and blind-spot issues. Different failure modes.
- The validator — self-check is per-fix, the validator checks the artifact globally. Both still run.

**Interaction with panel skip (`panel-review-modes.md § When to Skip the Panel`):** self-check runs *before* the skip decision. If self-check finds a semantic issue (anything in (a) or (b)), the change is no longer purely mechanical — abort the skip and run a normal panel pass. The (c) hygiene check overlaps with the lint step in panel skip; that redundancy is cheap and intentional — same checks at different stages.

## Situational panel modes (loaded on demand)

Five panel behaviours live in two sibling references, loaded only when a specific trigger fires — a NORMAL pass never needs them:

- **Strict-Bar Convergence Mode** — Read `panel-review-convergence.md` when `archive_pass.py` emits a `STRICT-BAR-SIGNAL:` advisory (the panel keeps finding real-but-downstream-deferrable HIGHs and won't converge).
- **Halt and Re-scope Exit** — Read `panel-review-convergence.md` when a concern is fundamentally scope-shaped — an `[upstream]` tag (Phase 2/3) or two consecutive halt votes.
- **Lightweight Mode (single-pass panel)** — Read `panel-review-modes.md` when the user opts into a single-pass review for small / throwaway / exploratory work.
- **When to Skip the Panel** — Read `panel-review-modes.md` when the only change since the last pass is mechanical (a rename, a formatting-only edit) and the Synthesizer Self-Check stays clean.
- **Handling change requests at the review gate** — Read `panel-review-modes.md` when the user asks for a change after the artifact is presented at the review gate (before approval).
