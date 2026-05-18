# Hash handling and the cascade

When an approved blueprint document changes — Claude edits it, the user edits it, or `git pull`/`merge` brings in someone else's change — two things must happen automatically:

1. **Re-stamp the changed document** so its approval hash matches its new content.
2. **Check downstream consistency** so an out-of-date upstream doesn't silently invalidate the artifacts approved against it.

Do both without prompting for permission — the user has already authorized the edit. Real decisions surface only at the consistency-check boundary.

## Entering the Workflow Mid-Stream

Run `python <script-path>/validate_blueprint.py blueprint/`. Output lines are `  [<SEVERITY>] <name> — <detail>`.

1. **Fix structural FAILs first** (missing sections, `[TBD]`/`TODO`/`FIXME`, unchecked open questions). Self-correct trivial breaks; escalate when content judgment is needed. Re-run the validator to confirm before continuing. Do not re-stamp a structurally broken document.
2. **Then handle approval-state FAILs:**
   - Stale hash or missing hash → auto-restamp with `--approve <phase>` (`scope`, `architecture`, or `plan`) and note it in one line ("SCOPE.md hash refreshed: abc123 → def456"). Then run the cascade (step 3 in "Re-Approval After Edits" below).
   - Checkbox unchecked → **halt and ask the user.** An unchecked box is ambiguous (deliberate "needs revision" vs. accidental).
   - If the edit came from `git pull`/`merge`/branch switch rather than the user's keystrokes, auto-restamp still applies; mention the source in the note ("…hash refreshed after merge from main: …").
3. **`Previous phase approved` FAILs** are propagated — fix the upstream named in the FAIL line and they clear automatically.
4. **Then route to the right phase:**
   - SCOPE.md clean → proceed to Architecture (self-review, scope-architecture consistency, panel).
   - ARCHITECTURE.md clean → proceed to Plan (self-review, scope-architecture-plan consistency, panel).
   - PLAN.md clean → blueprint complete; suggest spec-driven-dev.

## Re-Approval After Edits

When an approved document changes, run this flow against it:

1. **Verify structural validity.** Run the validator. If a structural check fails on the edited document, self-correct trivial breaks; escalate when content judgment is needed. Do not re-stamp until structural checks pass.
2. **Re-stamp silently.** `python <script-path>/validate_blueprint.py blueprint/ --approve <phase>` for the edited document. One-line note ("SCOPE.md re-approved, hash abc123 → def456"). No prompt.
3. **Cascade the consistency check to approved downstream artifacts.** This is the cross-doc consistency check only — no re-drafting, no panel review, no full validation. Use the named sections:
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


## Deferred Dispositions: Staleness and First Re-Entry

This section documents two operator-facing behaviours of the `### Deferred dispositions` mechanism: staleness cleanup when downstream artifacts have absorbed a deferred concern, and natural-fill behaviour when re-entering a legacy artifact that predates the feature.

### Staleness cleanup (operator-driven, pre-dispatch advisory)

**When**: Re-entering an approved artifact for a new panel-review loop (loop re-entry, mid-stream amendment, convergence-test re-run, etc.). Apply this advisory BEFORE step 1 of the panel loop (before dispatching panelists).

**What to check**: Each `[DEF-NN]` entry in `### Deferred dispositions` has a `→ <TARGET.md>` clause. Compare the entry's title and rationale against the current state of `<TARGET.md>`. If the downstream artifact has visibly absorbed the concern (a section, requirement, task, or feature now addresses it), the `[DEF-NN]` entry is **stale**.

**What to do with stale entries**: Ask the user — remove the entry, or annotate it inline as `(absorbed — resolved in <TARGET.md> §X.Y)`. No automation enforces this; the synthesizer is the verification agent. Removal keeps the suppression list lean; annotation preserves audit trail.

**Why pre-dispatch**: A stale `[DEF-NN]` entry that's no longer load-bearing still suppresses re-raises in the panelist prompt. If new evidence arises that would warrant a fresh concern in the same area, the stale entry can cause the panel to suppress it inappropriately. Cleaning up before dispatch keeps the suppression list aligned with actual current state.

### Natural fill on first re-entry (legacy artifacts predating this feature)

**Scenario**: An artifact approved before the deferred-dispositions feature landed is being re-entered for a new panel pass. It does NOT contain a `### Deferred dispositions` sub-section (the section was added by this feature).

**What happens automatically**:

1. `archive_pass.py` detects the missing section on first archive (any flag: normal, `--skip`, `--strict-bar`, `--cross-check`, `--dry-run`) and auto-inserts the empty `### Deferred dispositions` header between `### Sealed dispositions` and `### Latest pass detail`. This is a **cosmetic edit** (no semantic content), handled by the existing auto-re-stamp flow described above — no operator prompt fires.

2. The first panel pass after re-entry lacks a populated suppression list. If panelists re-raise concerns that were previously disposed `Deferred` (whose `[DEF-NN]` entries vanished under the pre-feature behaviour), the synthesizer disposes them normally — `Deferred → <TARGET>` with a fresh `Routed because:` rationale — and `archive_pass.py` promotes them into the freshly-inserted section with `[DEF-01]`, `[DEF-02]`, etc.

3. Subsequent passes have the populated list and suppress re-raises correctly per the marker-based discipline.

**Operator escape hatch (optional)**: Operators with a reconstructed list of prior deferrals (from memory, notes, or downstream artifacts) can paste them directly into `### Deferred dispositions` BEFORE the first re-entry archive. The entry format is:

```
- `[DEF-NN]` **<title>** → <TARGET.md> (pass <N>) — Routed because: <rationale>.
```

`NN` is sequential, zero-padded to two digits. `<TARGET.md>` is a plain markdown filename (no path-traversal segments). `<rationale>` is one sentence.
