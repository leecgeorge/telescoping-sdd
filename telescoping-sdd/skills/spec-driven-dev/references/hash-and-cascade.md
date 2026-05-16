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
- **Revise the downstream** — Claude drafts the change, user approves it. That revision is itself an edit, so it re-enters this flow at step 1 (cascading further downstream if applicable).
- **Accept the divergence** — Claude drafts a rationale entry and adds it to a `## Accepted Divergences` section in the downstream (not the upstream — the divergence is the downstream's choice to deviate). Each entry has Date, Upstream change, Consistency check item, Divergence, Rationale, Re-evaluate trigger. User approves the text before it's added, then re-stamp the downstream. That re-stamp is itself an edit, so it re-enters this flow at step 1 (cascading further downstream if applicable). This section isn't in the templates; the validator only checks for required sections, so extras don't FAIL.

**Net effect.** Cosmetic edits ripple silently — one re-stamp note, one consistency-verified note per downstream. Substantive edits halt exactly where they matter. Downstreams never get re-stamped just because an upstream changed.
