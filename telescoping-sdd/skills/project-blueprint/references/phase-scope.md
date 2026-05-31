# Phase 1: Scope

Drafts `blueprint/SCOPE.md` — what we're building and why. This is the first blueprint artifact; the architecture and plan phases depend on its approval.

## Drafting

Delegate drafting to the `telescoping-sdd:project-spec-analyst` subagent via the Agent tool (`subagent_type: telescoping-sdd:project-spec-analyst`).

When invoking the agent, provide:
- The template path: `references/scope-template.md`
- The required sections (below) — the agent must produce exactly these
- Everything the user has told you about the project so far
- Any prior artifacts in `blueprint/` if the user is resuming mid-stream
- A clear instruction to self-review the draft before returning (up to 5 passes, but stop immediately after the first pass that finds no issues — do not keep reviewing once clean), and to return a complete, clean draft of `SCOPE.md` (not a partial or diff)
- A clear instruction to reproduce the template's exact formatting for structural sections — in particular: Success Criteria must use `- [ ]` checkboxes (not numbered lists), Open Questions must use `- [ ] Q1:` checkbox format, and the Approval section must be exactly `- [ ] Approved to proceed to next phase` followed by `- **Content Hash:** \`pending\`` (not a table or other format). The agent must read the template file and match its syntax precisely.

Required sections:
- **Problem Statement** — What problem exists and why it needs solving
- **Target Users** — Who will use this and what are their needs
- **Goals** — What success looks like for this project
- **Non-Goals** — What is explicitly out of scope
- **Constraints** — Technical, timeline, team, budget, or regulatory constraints
- **Success Criteria** — Measurable conditions that define "done"

After the agent returns the draft, write it to `blueprint/SCOPE.md` and perform the self-review yourself before presenting it to the user.

## Scope Self-Review

Review the SCOPE.md you just wrote, checking for:

1. **Inconsistencies** — Do goals contradict non-goals? Do constraints conflict with success criteria? Are terms used consistently throughout?
2. **Inaccuracies** — Are assumptions about the target users, technical environment, or constraints correct based on what the user has told you?
3. **Gaps** — Is every goal measurable via at least one success criterion? Are there obvious user needs not addressed? Are constraints complete (technical, timeline, team, budget, regulatory)?

For each issue found:
- **Fix it directly** if the correct resolution is clear (e.g., a missing success criterion for a stated goal, a constraint that contradicts itself)
- **Stop and ask the user** if the resolution requires a judgment call (e.g., conflicting goals where you don't know which takes priority, unclear target user needs)

If any issues were fixed, repeat the self-review on the updated scope — fixes can introduce new issues. If a pass finds no issues, stop immediately. Do not exceed 5 review passes total.

## Scope Panel Review

After the scope self-review is complete, run the scope panel against `blueprint/SCOPE.md` following the loop described in `references/panel-review.md`.

Panelists: `telescoping-sdd:user-advocate`, `telescoping-sdd:devils-advocate`, `telescoping-sdd:pragmatist`.

There are no upstream approved artifacts at this phase — pass the current SCOPE.md only. Deferred concerns from this panel can target `ARCHITECTURE.md` or `PLAN.md`.

## Validation and approval

After the panel review is complete, run validation:

```bash
python <script-path>/validate_blueprint.py blueprint/
```

**Stop and ask the user to review SCOPE.md before proceeding.**

If the user requests a change at this gate (before approving), do not apply it silently — route it through `references/panel-review.md § "Handling change requests at the review gate"` (substantive change re-enters the panel loop; trivial wording is a synthesizer fix + Self-Check, panel-skip-eligible), then re-present. No hash exists yet, so there is no re-stamp or cascade.

When the user approves, run:

```bash
python <script-path>/validate_blueprint.py blueprint/ --approve scope
```

This marks the scope as approved with a content hash. If the scope is edited after approval, the hash will no longer match — the skill detects this on next entry (or immediately, if Claude made the edit) and triggers the auto-cascade flow described in `hash-and-cascade.md` § "Re-Approval After Edits": structural validity is checked, the hash is re-stamped silently, and the consistency check ripples downstream. Cosmetic edits proceed without interruption; substantive edits halt at the consistency-check boundary so the user can decide whether to revise the downstream artifacts.
