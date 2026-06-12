<!--
SHARED REFERENCE — keep in sync with the spec-driven-dev copy at
skills/spec-driven-dev/references/hash-and-cascade.md. Edits to the shared cascade machinery must be mirrored in BOTH copies.

Intentional asymmetries vs the sibling (do NOT "sync" these away):
- SDD-only: all Phase 4 (Implement) content — the Phase-4-exception note, the Task-tick discriminator (C2), and the task-tick carve-out that skips step 3 + the cascade. Blueprint has no artifact Phase 4; do not add it there.
- Blueprint-only: PLAN.md closed-feature scope detection, the verbatim closed-feature immutability panelist constraint, and the full 4-step post-panel immutability validation. The SDD copy carries only a stub pointer (it has no PLAN.md upstream); do not expand the stub.
- The yes-path re-stamp gate is conditioned on immutability validation passing in blueprint but unconditional in SDD — this tracks the blueprint-only validation above; do not "sync" the AND-clause.
- Terminal Phase-3 artifact differs: PLAN.md (blueprint) vs tasks.md (spec-driven-dev); the --terminal note and routing name PLAN.md vs tasks.md accordingly.
Otherwise the copies differ only cosmetically (phase-vocabulary mapping, filenames, example values).
-->

# Hash handling and the cascade

When an approved blueprint document changes — Claude edits it, the user edits it, or `git pull`/`merge` brings in someone else's change — two things must happen automatically:

1. **Re-stamp the changed document** so its approval hash matches its new content.
2. **Check downstream consistency** so an out-of-date upstream doesn't silently invalidate the artifacts approved against it.

Do both without prompting for permission — the user has already authorized the edit. Real decisions surface at the consistency-check boundary AND at one earlier point: between re-stamping and cascading, a brief upstream panel re-review step fires when the edit is substantive (lean-yes) or borderline non-trivial (lean-no but not visibly trivial under the four-criterion test in step 3). Visibly trivial edits skip silently with a one-line note. This exception exists because substantive new content in the upstream should be stress-tested before it becomes the baseline downstream documents are measured against.

## Entering the Workflow Mid-Stream

Run `python <script-path>/validate_blueprint.py blueprint/`. Output lines are `  [<SEVERITY>] <name> — <detail>`.

1. **Fix structural FAILs first** (missing sections, `[TBD]`/`TODO`/`FIXME`, unchecked open questions). Self-correct trivial breaks; escalate when content judgment is needed. Re-run the validator to confirm before continuing. Do not re-stamp a structurally broken document.
2. **Then handle approval-state FAILs:**
   - Stale hash or missing hash → auto-restamp with `--approve <phase>` (`scope`, `architecture`, or `plan`) and note it in the source-tagged format `<file> re-stamped after <source-tag>: hash <old> → <new>` where `<source-tag>` is one of `user-edit`, `claude-edit`, `git-pull`, `git-merge`, `branch-switch`. Then continue at **step 3 (Upstream panel re-review) in "Re-Approval After Edits" below** — a stale-hash mid-stream entry is a top-level entry of the re-approval flow, so step 3 fires unless the diff is visibly trivial under the four-criterion test. After step 3 completes via any exit path (trivial-skip, yes-path, or no-path), the flow proceeds to step 4 (cascade).
   - Checkbox unchecked → **halt and ask the user.** An unchecked box is ambiguous (deliberate "needs revision" vs. accidental).
   - If the edit came from `git pull`/`merge`/branch switch rather than the user's keystrokes, auto-restamp still applies; the `<source-tag>` in the note (`git-pull`, `git-merge`, or `branch-switch`) records the origin.
3. **`Previous phase approved` FAILs** are propagated — fix the upstream named in the FAIL line and they clear automatically.
4. **Then route to the right phase:**
   - SCOPE.md clean → proceed to Architecture (self-review, scope-architecture consistency, panel).
   - ARCHITECTURE.md clean → proceed to Plan (self-review, scope-architecture-plan consistency, panel).
   - PLAN.md clean → blueprint complete; suggest spec-driven-dev.

## Re-Approval After Edits

When an approved document changes, run this flow against it:

1. **Verify structural validity.** Run the validator. If a structural check fails on the edited document, self-correct trivial breaks; escalate when content judgment is needed. Do not re-stamp until structural checks pass.
2. **Re-stamp silently.** `python <script-path>/validate_blueprint.py blueprint/ --approve <phase>` for the edited document. Emit a one-line note in the source-tagged format: `<file> re-stamped after <source-tag>: hash <old> → <new>` where `<source-tag>` is one of `user-edit`, `claude-edit`, `git-pull`, `git-merge`, `branch-switch` (determined at step-2 emit time by inspecting the immediate trigger that brought the flow into Re-Approval After Edits). Example: `SCOPE.md re-stamped after user-edit: hash abc123 → def456`. No prompt. This is the **writer side** of the source-tag contract; the new step 3 (Upstream panel re-review) reads the tag to determine source classification per AD1.

   The re-stamp also writes a `- **Hash basis:** v2` line into the `## Approval` section. Under basis v2 the approval hash **excludes** both the `### Trajectory` table and that basis line, so recording a converged panel pass never moves the hash — a convergence-only re-approval writes no pending-review marker. An artifact still stamped under the old basis (no `- **Hash basis:** v2` line) reports a distinct `HASH-BASIS-MIGRATION:` FAIL until it is re-approved once (see `Close-Path Selection Guidance` below).
3. **Upstream panel re-review.** Before cascading, decide whether to stress-test the edited upstream itself with a panel pass. This step fires only on **top-level entries** of `Re-Approval After Edits` (a human keystroke edit, a Claude-drafted edit at the user's request, or a `git pull`/`merge`/branch-switch). When this flow is **re-entered** as a result of the downstream-revision recursion described in the "Resolution has two paths" block below, this step does NOT fire — the existing downstream optional panel re-review block at the end of this section remains the mechanism for stress-testing revised downstreams. When a single trigger (e.g., one `git pull`) brings new content into N approved documents simultaneously, each edited document is its own top-level entry; the step fires once per edited document, not once per pull.

   a. **Recommendation formation.** Determine edit source by deterministic precedence (highest first):
      1. **Step-2 source tag** — if step 2's re-stamp note carries a source tag (`user-edit`, `claude-edit`, `git-pull`, `git-merge`, `branch-switch`), that tag is authoritative.
      2. **Prior Claude Agent invocation** — if the most recent edit to the upstream came from an Agent tool call in this session before step 2 emitted, source = `claude-edit`.
      3. **User's typed prompt text** — examine the literal text the user typed at the prompt (NOT document content the message includes by reference, attached files, or pasted-from-elsewhere blocks). If it contains the literal edit (paste or diff) or a clear first-person edit instruction ("I'm going to add G6"), source = `keystroke`.
      4. **Ambiguous → non-keystroke** (lean-yes bar). When source = `ambiguous`, the user-facing prompt's Reason line states: `edit source could not be confidently classified; treating as non-keystroke per AD1 default.` so the user can correct.

      **Git-origin detection (stale-hash mid-stream entry, no in-session edit).** When the flow was entered because the validator reported a stale hash but no edit was made in this session (no step-2 source tag, no prior Agent edit, nothing in the user's typed prompt), determine the source from git before falling through to `ambiguous`: run `git log -1 --format=%s -- <file>` to read the most recent commit subject touching the file, and inspect `git reflog -n 5` (or `git reflog show HEAD -n 5`) for a recent `pull`/`merge`/`checkout`/`clone` entry. A reflog `pull`/`merge` immediately preceding the working state → `git-pull` / `git-merge`; a recent `checkout: moving from <A> to <B>` → `branch-switch`. If the git signals are inconclusive or conflict, tag the source `ambiguous` (which leans non-keystroke per sub-point 4). Never block on this — it is a best-effort classifier feeding the lean decision, not a gate.

   b. **Apply the four-criterion triviality test (AD3).** Visibly trivial if and only if the diff passes ALL FOUR criteria:
      1. **Diff content is whitespace-only OR punctuation-only OR comment-only** (after Unicode-NFC normalization) — characters that differ between pre and post must be members of `{whitespace, ASCII punctuation, content inside <!-- --> HTML comments}`. **AND** the diff does NOT touch: blank lines adjacent to fenced code blocks, blank lines adjacent to list items or headings, leading whitespace on any line, trailing whitespace on lines ending in two-or-more spaces, or any line matching `^#{1,6} `, `^\s*[-*+] `, `^\s*\d+\. ` (markdown-rendering-impactful patterns).
      2. **No change to checkbox state** on any content-bearing line.
      3. **No change to ANY content of a code block** (regardless of language tag — including YAML/JSON/config blocks).
      4. **No rename of any identifier** matching one of: `F\d+`, `T\d+`, `R\d+`, `CFC-\d+`, `AD\d+`, `DEF-\d+`, `SEAL-\d+`, OR a contract-vocabulary token from this enumerated list: `user-edit`, `claude-edit`, `git-pull`, `git-merge`, `branch-switch`, `keystroke`, `non-keystroke`, `ambiguous`, `top_level_entry`, `STRICT-BAR-SIGNAL`, `Halt and re-scope`, `Addressed`, `Deferred`, `Sealed`, `Accepted as risk`, `upstream-panel`. Examples: trivial = pure whitespace cleanup; non-trivial = `may`→`must`, `should`→`must`, `30s`→`60s`, any letter-content change (typo corrections do NOT qualify as trivial under this strict reading — they prompt with default-no).

      If the diff passes all four criteria → **trivial-skip**: emit `Upstream panel re-review: skipped — trivial edit (whitespace / punctuation / comment-only, no semantic diff)` and proceed directly to step 4 (cascade). No prompt.

   c. **Lean classification (for non-trivial diffs):**
      - For **non-keystroke** source (Claude-drafted, git pull/merge, branch-switch, or ambiguous): any non-trivial edit → **lean-yes** regardless of content category (source-aware bar per Q1/DP1).
      - For **keystroke** source: apply content categories. **Lean-yes** if the diff adds new goals, components, component interactions, technology choices, security/privacy surfaces, or external dependencies. **Lean-no** if the diff only restructures, rewords, or reformats existing content.

   d. **Prompt presentation.** Present the recommendation and ask the user explicitly. Use the panelist set defined in `panel-review.md § Panelists per phase` for the upstream's phase — do not inline the panelist names here.

      **Lean-yes prompt (I1)** — default-yes on Enter:
      ```
      Upstream panel re-review: recommended (yes)
      Reason: <one-sentence reason naming the category of change and which panelists would care — focus on the concern, mention panelists parenthetically if it adds clarity>

      Run upstream panel re-review on `<filename>` before cascading? (Y/n)
      ```

      **Lean-no (borderline) prompt (I2)** — default-no on Enter:
      ```
      Upstream panel re-review: not recommended (no)
      Reason: <one-sentence reason — e.g., "the revision restructures the Goals section without adding new behavior">

      Run upstream panel re-review on `<filename>` before cascading? (y/N)
      ```

      **Answer vocabulary:** `y`/`yes`/`Y`/`Yes`/`YES` → yes; `n`/`no`/`N`/`No`/`NO` → no; Enter (empty) → recommendation's default. Ambiguous responses re-ask once with `Please answer y or n (default on Enter: <Y or N>):` then apply the recommendation's default.

   e. **Yes-path execution.** Run the panel-review loop on the upstream document:
      - Use `panel-review.md § Panelists per phase` for the upstream's phase.
      - Determine the `--phase` argument from the upstream artifact: `SCOPE.md` → `--phase 1`; `ARCHITECTURE.md` → `--phase 2`; `PLAN.md` → `--phase 3`.
      - **PLAN.md special handling — closed-feature scope detection.** If the upstream is PLAN.md, before forming the recommendation, scan `## Milestones` for milestone-feature rows (regex `^- \[[ xX]\] F\d+\b`, the canonical lookup form) to determine `closed_feature_scope` — the list of features whose milestone checkbox is `[x]` (per `workflow-overview.md § Closed-Feature-Row Immutability` lookup mechanic). The scope is always re-computed at flow entry from PLAN.md on local disk (never from cached FlowState, panel-supplied payload, or in-flight content). Empty list when no closed-feature rows or `## Milestones` absent.

         **If `closed_feature_scope` is non-empty:** inject the following immutability constraint into the panelist prompt verbatim (substituting `<closed-list>` with the closed-feature identifiers, e.g., `F1, F3`):

         > **Closed-feature immutability in scope.** This PLAN.md edit is being reviewed while the following features have shipped (milestone checkbox `[x]`): `<closed-list>` (e.g., F1, F3).
         >
         > The following content is byte-frozen as a historical commitment and must NOT be edited in place:
         > 1. The `### F<n>:` row and all its bullet content for any F<n> in the closed list — per Closed-Feature-Row Immutability doctrine.
         > 2. Any `### CFC-N` entry whose `**Participating features:**` list includes one or more features from the closed list — per Bound-Spec Immutability doctrine (the shipped specs carry `[CFC-N]` tags whose `structured_content_hash` would be invalidated by a CFC edit).
         >
         > If you identify a concern about content under either category: the only valid dispositions are (i) a divergence note in the downstream spec's `## Accepted Divergences`, or (ii) a new remediation feature added to PLAN.md's `## Feature Breakdown`. Do not propose in-place text edits to the closed rows or their CFCs — such proposals will be rejected at synthesis time.

      - Compute the pre-panel content hash of the upstream; capture the most recent NORMAL row from the upstream's Trajectory (if any) and its provenance tag.
      - Run `python <shared-script-path>/archive_pass.py <upstream> --phase <N>` extending the upstream's existing `## Panel Review` Trajectory; when the upstream is the terminal Phase-3 artifact (`PLAN.md`), append `--terminal` (`archive_pass.py` hard-rejects that filename without it — see `panel-review.md` `## The Loop`, Terminal-archive invocation). After archiving, tag the new Trajectory row's Notes column with `upstream-panel <pre-panel-hash-short>` where `<pre-panel-hash-short>` is exactly the first 8 lowercase hex characters of the pre-panel content hash (format: regex `upstream-panel [0-9a-f]{8}` — no other content; the hash is derived from upstream content only, never from filenames or user input).
      - **Stale-baseline detection.** If `STRICT-BAR-SIGNAL:` fires and the prior NORMAL row's provenance hash does NOT exactly equal the current pre-panel hash, treat the baseline as stale. Surface a "stale baseline" note to the user and let them decide whether to switch to STRICT-BAR mode; do not auto-apply. For legacy rows lacking a provenance tag, treat the baseline as unconditionally stale. Any hash difference is stale; no "hash-refresh-only delta" carve-out.
      - **Post-panel immutability validation (PLAN.md only, when `closed_feature_scope` is non-empty) — deterministic 4-step procedure:**

         **(i) Pre-panel scope capture.** Before invoking the panel, for each F<n> in `closed_feature_scope`, capture every line of content belonging to that feature's `### F<n>:` scope. **Scope rule:** a line is "in heading H's scope" if it falls between H (inclusive of the heading line itself) and the next subsequent heading of equal-or-higher level (any `### `, `## `, or `# ` line). Sub-headings of strictly lower level (`####`+) and their content remain within the parent scope. Empty lines and fenced code blocks are included. The heading line `### F1: ...` IS part of F1's scope — edits to the heading text count as scope modifications. Also for each `### CFC-N` heading whose **pre-panel** Participating list includes any feature in `closed_feature_scope`, capture every line of that CFC's scope by the same rule. Each captured set is an ordered list of NFC-normalized, trailing-whitespace-stripped lines tagged with the scope identifier (e.g., `F1`, `CFC-3`).

         **(ii) Post-panel diff procedure.** After the panel runs, re-read the upstream file. For each captured scope identifier: locate the heading in the post-panel content by matching the F<n> or CFC-N token (case-sensitive); if absent (panel removed it), record as MODIFIED. If present, extract the post-panel scope content using the same scope rule, NFC-normalize, strip trailing whitespace. Compare pre-panel and post-panel scope sequences. Any difference (insertion, deletion, reorder, content change) → record as MODIFIED. Pure reorders ARE modifications (the byte-frozen commitment is order-preserving).

         **(iii) Abort on any MODIFIED.** Surface the hard error: `Panel auto-fix touched immutable closed-feature scope (F<n> or CFC-<m>); rejecting to preserve Bound-Spec hash invariants. Run validate_blueprint.py to confirm; manual intervention required.` Emit `Halt and re-scope` disposition in `### Latest pass detail` and exit the yes-path without cascading.

         **(iv) Pre-panel scope membership is authoritative (TOCTTOU mitigation).** The immutability check uses the **pre-panel** Participating list for each CFC and the **pre-panel** closed_feature_scope, not the post-panel values. This prevents a panel pass from removing a closed feature from a CFC's Participating list in the same pass it edits that CFC's contents — the pre-panel binding governs.

         The panel's other auto-fixes (those NOT touching any captured immutable scope) may be preserved manually by the user after reviewing the diff.

      - If panel auto-fixes were applied AND the post-panel immutability validation passed: re-stamp the upstream with `--approve <phase>` and emit the summary line: `<file> re-approved after upstream panel: hash <pre-panel-stamp> → <h1> → <h2> → ... → <post-fix-stamp> (<N> panel passes, <M> auto-fixes applied)` where intermediate hashes are listed in order. If more than 5 intermediates, elide with `...` and emit a separate `Detailed re-stamp manifest:` line listing every (pass-number, post-pass-hash) pair. If no auto-fixes: emit `<file> upstream panel complete: no auto-fixes applied (hash unchanged at <hash>)`.
      - **archive_pass.py failure.** If `archive_pass.py` exits non-zero or emits stderr indicating malformed Trajectory or file-permission errors, surface the error to the user, do not auto-cascade, do not auto-re-stamp; require explicit user confirmation to retry or proceed.
      - Then proceed to step 4 (cascade).

   f. **No-path execution.** Emit `Upstream panel re-review: skipped — user declined` and proceed to step 4 (cascade). If the user said "no" against a **lean-yes** recommendation (crossed-recommendation), emit this additional warning: `Note: the upstream panel re-review was skipped on a lean-yes edit. The revised content will cascade without panel stress-testing. To run the panel later: ask "run the upstream panel re-review on \`<file>\` now" or re-edit the upstream (any non-trivial change) to re-enter this flow.`

      If the user said "yes" against a **lean-no** recommendation and the panel converges immediately with 0 HIGHs, emit after the yes-path summary line (step e): `Upstream panel: converged immediately — no issues found, consistent with lean-no recommendation.`

   g. **Recovery path.** If the user later realizes they want a panel pass after declining, two affirmative options exist: (1) ask Claude in-session "run the upstream panel re-review on `<file>` now" — Claude re-runs the recommendation+ask cycle without requiring an edit; (2) re-edit the upstream (any non-trivial change to its content) re-enters `Re-Approval After Edits` and re-offers the upstream panel. Saying "no" does not mark the content as permanently un-reviewed.

4. **Cascade the consistency check to approved downstream artifacts.** This is the cross-doc consistency check only — no re-drafting, no panel review, no full validation. Use the named sections:
   - Scope ↔ Architecture: `phase-architecture.md` § "Scope-Architecture Consistency Check".
   - Scope+Architecture ↔ Plan: `phase-plan.md` § "Scope-Architecture-Plan Consistency Check".

   For each approved downstream:
   - Skip downstreams that are unapproved-in-progress (the in-progress work absorbs the change naturally).
   - If the check finds nothing, note it ("ARCHITECTURE.md still consistent with re-approved SCOPE.md") and continue. Do not re-stamp — the downstream's content didn't change.
   - If it finds substantive divergence, **halt** and quote the specific divergence by checklist item ("Goal coverage: G3 in revised SCOPE.md has no addressable component in ARCHITECTURE.md"). Do not cascade further down the chain until this link is resolved.

Resolution has two paths:
- **Revise the downstream** — Claude classifies the fix:
  - **Trivial** (typo, rename, formatting, single-sentence rewording, no behavior change) — Claude applies the fix directly; the user's "fix it" is the authorization.
  - **Substantial** (new goals, components, component interactions, technology choices, security/privacy surfaces, or external dependencies — same criteria as the panel re-review step below) — Claude describes the proposed approach in one or two sentences and asks explicitly: *"Proceed with this approach?"* On yes, Claude drafts and applies the fix. Only revert to the user mid-draft if Claude hits a genuine ambiguity that needs guidance (e.g., two reasonable interpretations, missing context, the draft would materially exceed the approved approach scope).

  Either way: verify structural validity, then re-stamp the downstream.
- **Accept the divergence** — Claude drafts a rationale entry and adds it to a `## Accepted Divergences` section in the downstream (not the upstream — the divergence is the downstream's choice to deviate). Each entry has Date, Upstream change, Consistency check item, Divergence, Rationale, Re-evaluate trigger. User approves the text before it's added, then re-stamp the downstream. This section isn't in the templates; the validator only checks for required sections, so extras don't FAIL.

**Optional panel re-review.** After the downstream is re-stamped (either path) and before the recursion runs:

1. **Form a recommendation** on whether to run a panel re-review of the revised content:
   - **Lean yes** if the revision adds new goals, components, component interactions, technology choices, security/privacy surfaces, or external dependencies.
   - **Lean no** if the revision restructures, clarifies, or rewords existing content without new behavior.
   - For Path 2 (`Accepted Divergences` entries): default **no** (documentation-only). Lean yes only if the deferred work is load-bearing — re-paneling then stress-tests the deferral decision rather than the content.
2. **Present the recommendation** with a one-sentence reason naming which panelists would care, e.g., *"Recommend panel re-review: yes — the revision adds a multi-tenant data layer, which `architect` and `security-reviewer` haven't yet evaluated."*
3. **Ask the user explicitly:** *"Run panel re-review on `<downstream>`?"* Wait for a yes or no. Do not proceed to step 4 without an explicit answer.
4. **If yes, run the panel-review loop** on the revised downstream — follow `panel-review.md` exactly, using the panelist set already defined for the downstream's phase (listed in SKILL.md § "Phase N" and the corresponding `phase-<name>.md`). If panel auto-fixes modify the downstream during the loop, re-stamp it a final time. Then re-enter this flow at step 1 (cascading further downstream if applicable).
5. **If no, skip the panel** and re-enter this flow at step 1 (cascading further downstream if applicable).

**Net effect.** Cosmetic edits ripple silently — one re-stamp note, one consistency-verified note per downstream. Substantive edits halt exactly where they matter. Downstreams never get re-stamped just because an upstream changed.

### Close-Path Selection Guidance

A pending-review obligation (the `upstream-panel [0-9a-f]{8}` marker) has exactly **two sanctioned close paths** — there is no third implicit closer:

1. **Run the panel and stamp the tag** (the doctrine-correct close, step 3e): run the upstream panel, let `archive_pass.py` append the pass, then stamp `upstream-panel <pre-panel-hash-short>` on that Trajectory row. The next validation reconciles and clears the obligation.
2. **`--decline-pending`**: `python <script-path>/validate_blueprint.py blueprint/ --decline-pending` — an explicit, auditable USER decision to waive a genuinely-owed re-review.

**Narrowed `--decline-pending` meaning.** `--decline-pending` signals *consciously waiving a genuinely-owed re-review* — it is NEVER used to clear mechanical convergence churn. Recording a converged panel pass no longer moves the approval hash (the `### Trajectory` table and the `- **Hash basis:** v2` line are excluded from it), so a convergence-only re-approval writes no marker at all — there is nothing to decline. Reserve `--decline-pending` for the case it audits: a real, owed panel re-review the user chooses to skip.

**Hash-basis migration.** An artifact approved under the old basis validates with a distinct `HASH-BASIS-MIGRATION:` FAIL (NOT the generic `Pending-review: FAILED`). Resolve it by re-approving once: `--approve <phase>`. A pure basis migration writes no pending-review marker; a concurrent substantive edit (or un-re-approved `### Trajectory` growth) writes one clearable marker. Discover every affected artifact with `grep -rlE '^### Trajectory' blueprint/ --include='*.md'` and re-approve each.

**Obligation survival (no re-anchoring).** Once created, an open pending-review obligation survives every intervening re-stamp until it is satisfied (by the tag) or declined — it is NOT re-anchored to a later hash or pass by the panel's auto-fix re-stamp, the tag-row edit, or any other edit made while it is open. The single open obligation already compels the owed panel re-review. One disclosed edge: an edit slipped in *after the panel pass but before the tag is stamped* is attested only against the pre-edit content and is re-examined on the next `--approve` cycle (it never ships silently — the obligation is cleared only by the operator consciously stamping the tag).

**Unsatisfiable (legacy) obligations.** A legacy marker left by older tooling can carry a genuine `upstream-panel` tag that sits on a pass at-or-below the recorded anchor, which the strictly-greater-than reconcile can never clear. The validator surfaces this as a distinct `UNSATISFIABLE-OBLIGATION:` diagnostic. Clear it with `--restore-anchor` — content-attested: it clears ONLY when the genuine tag is actually present on an archived row (never `--decline-pending`, which would falsely record the panel as skipped, and never marker-cache hand-editing).

**Orphaned Trajectory rows.** A `### Trajectory` data row stranded below the table's blank-line terminator is detected and surfaced with an `ORPHANED-TRAJECTORY-ROW:` diagnostic — never silently dropped. Make the row contiguous with the table (remove the intervening blank line) if it is a genuine entry, or delete it if it is not; let `archive_pass.py` own Trajectory row appends.


## Deferred Dispositions: Staleness and First Re-Entry (T11 / R6 / C10)

This section documents two operator-facing behaviours of the `### Deferred dispositions` mechanism: staleness cleanup when downstream artifacts have absorbed a deferred concern, and natural-fill behaviour when re-entering a legacy artifact that predates the feature.

### Staleness cleanup (operator-driven, pre-dispatch advisory)

**When**: Re-entering an approved artifact for a new panel-review loop (loop re-entry, mid-stream amendment, convergence-test re-run, etc.). Apply this advisory BEFORE step 1 of the panel loop (before dispatching panelists).

**What to check**: Each `[DEF-NN]` entry in `### Deferred dispositions` has a `→ <TARGET.md>` clause. Compare the entry's title and rationale against the current state of `<TARGET.md>`. If the downstream artifact has visibly absorbed the concern (a section, requirement, task, or feature now addresses it), the `[DEF-NN]` entry is **stale**.

**What to do with stale entries**: Ask the user — remove the entry, or annotate it inline as `(absorbed — resolved in <TARGET.md> §X.Y)`. No automation enforces this; the synthesizer is the verification agent. Removal keeps the suppression list lean; annotation preserves audit trail.

**Why pre-dispatch**: A stale `[DEF-NN]` entry that's no longer load-bearing still suppresses re-raises in the panelist prompt. If new evidence arises that would warrant a fresh concern in the same area, the stale entry can cause the panel to suppress it inappropriately. Cleaning up before dispatch keeps the suppression list aligned with actual current state.

### Natural fill on first re-entry (legacy artifacts predating this feature)

**Scenario**: An artifact approved before the deferred-dispositions feature landed is being re-entered for a new panel pass. It does NOT contain a `### Deferred dispositions` sub-section (the section was added by this feature).

**What happens automatically**:

1. `archive_pass.py` detects the missing section on first archive (any flag: normal, `--skip`, `--strict-bar`, `--cross-check`, `--dry-run`) and auto-inserts the empty `### Deferred dispositions` header between `### Sealed dispositions` and `### Latest pass detail`. This auto-insert happens on any NON-TERMINAL artifact; it is suppressed on terminal artifacts (`PLAN.md`, marked `--terminal`), which must not carry the section per R1. This is a **cosmetic edit** (no semantic content), handled by the existing auto-re-stamp flow described above — no operator prompt fires.

2. The first panel pass after re-entry lacks a populated suppression list. If panelists re-raise concerns that were previously disposed `Deferred` (whose `[DEF-NN]` entries vanished under the pre-feature behaviour), the synthesizer disposes them normally — `Deferred → <TARGET>` with a fresh `Routed because:` rationale — and `archive_pass.py` promotes them into the freshly-inserted section with `[DEF-01]`, `[DEF-02]`, etc.

3. Subsequent passes have the populated list and suppress re-raises correctly per the R5 marker-based discipline.

**Operator escape hatch (optional)**: Operators with a reconstructed list of prior deferrals (from memory, notes, or downstream artifacts) can paste them directly into `### Deferred dispositions` BEFORE the first re-entry archive. The entry format is:

```
- `[DEF-NN]` **<title>** → <TARGET.md> (pass <N>) — Routed because: <rationale>.
```

`NN` is sequential, zero-padded to two digits. `<TARGET.md>` is a plain markdown filename (no path-traversal segments). `<rationale>` is one sentence.

### Common failure: the factual-edit shortcut

A recurring, dangerous rationalization: *"this is just a factual name change / a one-line correction, so it's trivially safe — no panel."* That reasoning is a **content judgment**, and it is exactly the judgment Claude must NOT make about its own edits.

**The rule (AD1): `claude-edit + non-trivial → lean-yes regardless of content category`.** Source, not content, decides. A claude-authored edit that is not visibly-trivial (whitespace / punctuation / comment-only, per the four-criterion test) leans toward running the upstream panel re-review — even when the change "feels" like a mere factual fix. The category of the change ("just a rename", "just a fact", "just a tightening") is never the discriminator; the SOURCE (who authored it) and visible-triviality are.

**Why source beats content here:** Claude is unreliable at judging the blast radius of its own edits — the very change that feels like "just a factual correction" is the one that silently invalidated a downstream acceptance criterion in the real failure this discipline exists to prevent (`PROCESS-NOTE.md`). An author cannot see their own blind spot; the panel can. Leaning on source-classification removes the unreliable self-judgment from the loop.

**The flag is a doctrine-classified fact, never a convenience skip.** `--decline-pending` records that the USER decided to skip the panel for this obligation: a user decision the agent SURFACES and the user makes, never a self-serve shortcut the agent reaches for to dodge a panel it judged "unnecessary". (project-blueprint has no Phase-4 task-tick carve-out — there is no `--task-tick`.) Using `--decline-pending` to wave through a substantive re-stamp IS the factual-edit shortcut wearing a flag — the exact failure mode the pending-review marker (`upstream-panel [0-9a-f]{8}`) and the changed-document reminder make auditable.

### Upstream backport — same-repo discovery

A discovery made while working *downstream* can reveal that an already-approved **upstream** document is wrong. Reconciling it is not a new mechanism — it is a **backport**: edit the upstream document and run the existing *Re-Approval After Edits* flow above (re-stamp → upstream panel re-review → cascade back down). The motion's *application point* is the top of the chain even when its *origin* is the bottom; "backport" is the plain name for it (its cross-repo twin is the CPD Upstream Change Request flow). Enter at the single highest affected artifact and let the cascade carry the change down — never hand-edit the lower artifacts to match (see the single-entry-point rule below).

### Single-entry-point rule: no batch edits

When an edit to one approved artifact implies changes to others in the chain, **enter at the single highest affected artifact and edit only that one** — then let the cascade *produce* each downstream change, surfaced, classified, and gated one link at a time. Do **not** edit several chain artifacts simultaneously to force consistency: the cascade detects divergence by comparing a *changed* upstream against a *still-unchanged* downstream, so a batch edit that hand-aligns everything at once erases that signal — divergence detection, the halt-and-classify gate, and the downstream panel re-review all silently no-op. A batch edit is the factual-edit shortcut at chain scale.

The one sanctioned multi-document case is the opposite shape: when a single `git pull` / `merge` brings new content into N approved documents at once, each is handled as its **own independent top-level entry** (re-stamped, panel-decided, and cascaded separately) — never co-edited to look consistent. There is no sanctioned case for authoring simultaneous chain edits.
