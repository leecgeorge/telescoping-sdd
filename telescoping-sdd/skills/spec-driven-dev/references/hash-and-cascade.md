# Hash handling and the cascade

When an approved spec document changes — Claude edits it, the user edits it, or `git pull`/`merge` brings in someone else's change — two things must happen automatically:

1. **Re-stamp the changed document** so its approval hash matches its new content.
2. **Check downstream consistency** so an out-of-date upstream doesn't silently invalidate the artifacts approved against it.

Do both without prompting for permission — the user has already authorized the edit. Real decisions surface only at the consistency-check boundary.

**Phase 4 (Implement) is the exception.** `tasks.md` gets ticked continuously during implementation; re-stamping after every tick would be noise. The Phase 4 cadence is: re-stamp once on resumption (handled by mid-stream entry), stay silent through every tick, then re-stamp once at completion (driven by the Final Check in SKILL.md). Substantive mid-implementation edits to `tasks.md` (re-scoping, adding tasks because design proved incomplete) still follow the full flow below.

## Entering the Workflow Mid-Stream

Run `python <script-path>/validate_spec.py specs/<feature-name>/`. Output lines are `  [<SEVERITY>] <name> — <detail>`.

1. **Fix structural FAILs first** (missing sections, `[TBD]`/`TODO`/`FIXME`, unchecked open questions). Self-correct trivial breaks; escalate when content judgment is needed. Re-run the validator to confirm before continuing. Do not re-stamp a structurally broken document.
2. **Then handle approval-state FAILs:**
   - Stale hash or missing hash → auto-restamp with `--approve <phase>` (`spec`, `design`, or `tasks`) and note it in one line ("spec.md hash refreshed: abc123 → def456"). Then run the cascade (step 3 in "Re-Approval After Edits" below).
   - Checkbox unchecked → **halt and ask the user.** An unchecked box is ambiguous (deliberate "needs revision" vs. accidental).
   - If the edit came from `git pull`/`merge`/branch switch rather than the user's keystrokes, auto-restamp still applies; mention the source in the note ("…hash refreshed after merge from main: …").
   - **Phase 4 carve-out.** If you're resuming mid-Phase-4 (some tasks already ticked), the stale hash on `tasks.md` is expected — re-stamp silently and skip the cascade (`tasks.md` has no downstream). Structural FAILs on `tasks.md` still halt at step 1.
3. **`Previous phase approved` FAILs** are propagated — fix the upstream named in the FAIL line and they clear automatically.
4. **Then route to the right phase:**
   - spec.md clean → proceed to Design (self-review, spec-design consistency, panel).
   - design.md clean → proceed to Tasks (self-review, spec-design-tasks consistency, panel).
   - tasks.md clean → proceed to Implement.

## Re-Approval After Edits

When an approved document changes, run this flow against it:

1. **Verify structural validity.** Run the validator. If a structural check fails on the edited document, self-correct trivial breaks; escalate when content judgment is needed. Do not re-stamp until structural checks pass.
2. **Re-stamp silently.** `python <script-path>/validate_spec.py specs/<feature-name>/ --approve <phase>` for the edited document. One-line note ("spec.md re-approved, hash abc123 → def456"). No prompt.
3. **Cascade the consistency check to approved downstream artifacts.** This is the cross-doc consistency check only — no re-drafting, no panel review, no full validation. Use the named sections:
   - Spec ↔ Design: `phase-design.md` § "Spec-Design Consistency Check".
   - Spec+Design ↔ Tasks: `phase-tasks.md` § "Spec-Design-Tasks Consistency Check".

   For each approved downstream:
   - Skip downstreams that are unapproved-in-progress (the in-progress work absorbs the change naturally).
   - If the check finds nothing, note it ("design.md still consistent with re-approved spec.md") and continue. Do not re-stamp — the downstream's content didn't change.
   - If it finds substantive divergence, **halt** and quote the specific divergence by checklist item ("Requirement coverage: R4 in revised spec.md has no corresponding component in design.md"). Do not cascade further down the chain until this link is resolved.

Resolution has two paths:
- **Revise the downstream** — Claude classifies the fix:
  - **Trivial** (typo, rename, formatting, single-sentence rewording, no behavior change) — Claude applies the fix directly; the user's "fix it" is the authorization.
  - **Substantial** (new requirements, acceptance criteria, components, interface contracts, security/privacy surfaces, or external dependencies — same criteria as the panel re-review step below) — Claude describes the proposed approach in one or two sentences and asks explicitly: *"Proceed with this approach?"* On yes, Claude drafts and applies the fix. Only revert to the user mid-draft if Claude hits a genuine ambiguity that needs guidance (e.g., two reasonable interpretations, missing context, the draft would materially exceed the approved approach scope).

  Either way: verify structural validity, then re-stamp the downstream.
- **Accept the divergence** — Claude drafts a rationale entry and adds it to a `## Accepted Divergences` section in the downstream (not the upstream — the divergence is the downstream's choice to deviate). Each entry has Date, Upstream change, Consistency check item, Divergence, Rationale, Re-evaluate trigger. User approves the text before it's added, then re-stamp the downstream. This section isn't in the templates; the validator only checks for required sections, so extras don't FAIL.

**Optional panel re-review.** After the downstream is re-stamped (either path) and before the recursion runs:

1. **Form a recommendation** on whether to run a panel re-review of the revised content:
   - **Lean yes** if the revision adds new requirements, acceptance criteria, components, interface contracts, security/privacy surfaces, or external dependencies.
   - **Lean no** if the revision restructures, clarifies, or rewords existing content without new behavior.
   - For Path 2 (`Accepted Divergences` entries): default **no** (documentation-only). Lean yes only if the deferred work is load-bearing — re-paneling then stress-tests the deferral decision rather than the content.
2. **Present the recommendation** with a one-sentence reason naming which panelists would care, e.g., *"Recommend panel re-review: yes — the revision adds idempotent-retry semantics, which `architect` and `testability-reviewer` haven't yet evaluated."*
3. **Ask the user explicitly:** *"Run panel re-review on `<downstream>`?"* Wait for a yes or no. Do not proceed to step 4 without an explicit answer.
4. **If yes, run the panel-review loop** on the revised downstream — follow `panel-review.md` exactly, using the panelist set already defined for the downstream's phase (listed in SKILL.md § "Phase N" and the corresponding `phase-<name>.md`). If panel auto-fixes modify the downstream during the loop, re-stamp it a final time. Then re-enter this flow at step 1 (cascading further downstream if applicable).
5. **If no, skip the panel** and re-enter this flow at step 1 (cascading further downstream if applicable).

**Net effect.** Cosmetic edits ripple silently — one re-stamp note, one consistency-verified note per downstream. Substantive edits halt exactly where they matter. Downstreams never get re-stamped just because an upstream changed.
