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
- **Revise the downstream** — Claude drafts the change, user approves it. That revision is itself an edit, so it re-enters this flow at step 1 (cascading further downstream if applicable).
- **Accept the divergence** — Claude drafts a rationale entry and adds it to a `## Accepted Divergences` section in the downstream (not the upstream — the divergence is the downstream's choice to deviate). Each entry has Date, Upstream change, Consistency check item, Divergence, Rationale, Re-evaluate trigger. User approves the text before it's added, then re-stamp the downstream. That re-stamp is itself an edit, so it re-enters this flow at step 1 (cascading further downstream if applicable). This section isn't in the templates; the validator only checks for required sections, so extras don't FAIL.

**Net effect.** Cosmetic edits ripple silently — one re-stamp note, one consistency-verified note per downstream. Substantive edits halt exactly where they matter. Downstreams never get re-stamped just because an upstream changed.
