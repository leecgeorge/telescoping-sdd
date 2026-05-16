# Phase 1: Specify

Drafts `specs/<feature-name>/spec.md` — what to build and why. This is the first artifact; design and tasks depend on its approval.

## Drafting

Delegate drafting to the `telescoping-sdd:feature-spec-analyst` subagent via the Agent tool (`subagent_type: telescoping-sdd:feature-spec-analyst`).

When invoking the agent, provide:
- The detected project language (Python or Java) and the matching template path:
  - Python: `references/spec-template-python.md`
  - Java: `references/spec-template-java.md`
- The required sections (below) — the agent must produce exactly these
- Everything the user has told you about the feature so far
- Any prior artifacts in `specs/<feature-name>/` if the user is resuming mid-stream
- A clear instruction to self-review the draft before returning (up to 5 passes, but stop immediately after the first pass that finds no issues — do not keep reviewing once clean), and to return a complete, clean draft of `spec.md` (not a partial or diff)
- A clear instruction to reproduce the template's exact formatting for structural sections — in particular: Success Criteria must use `- [ ]` checkboxes (not numbered lists), Open Questions must use `- [ ] Q1:` checkbox format, and the Approval section must be exactly `- [ ] Approved to proceed to next phase` followed by `- **Content Hash:** \`pending\`` (not a table or other format). The agent must read the template file and match its syntax precisely.

Required sections:
- **Objective** — One paragraph on what and why
- **Requirements** — User stories in format: "As a [role], I want [action], so that [benefit]"
- **Acceptance Criteria** — GIVEN/WHEN/THEN for each requirement
- **Project Structure** — Where new code fits in the existing codebase
- **Boundaries** — "Always do", "Ask first", "Never do" lists
- **Success Criteria** — Measurable conditions for done

After the agent returns the draft, write it to `specs/<feature-name>/spec.md` and perform the self-review yourself before presenting it to the user.

## Spec Self-Review

Review the spec.md you just wrote, checking for:

1. **Inconsistencies** — Do requirements contradict each other? Do acceptance criteria match their corresponding requirements? Are terms used consistently throughout?
2. **Inaccuracies** — Do file paths, module names, or API references match the actual codebase? Are assumptions about existing code correct?
3. **Gaps** — Is every requirement covered by at least one acceptance criterion? Are there edge cases or error scenarios not addressed? Are boundaries (Always/Ask/Never) complete?

For each issue found:
- **Fix it directly** if the correct resolution is clear (e.g., a typo, a wrong file path, a missing edge case you can infer)
- **Stop and ask the user** if the resolution requires a judgment call (e.g., conflicting requirements where you don't know which takes priority, ambiguous scope, or missing domain knowledge)

If any issues were fixed, repeat the self-review on the updated spec — fixes can introduce new issues. If a pass finds no issues, stop immediately. Do not exceed 5 review passes total.

## Spec Panel Review

After the spec self-review is complete, run the spec panel against `specs/<feature-name>/spec.md` following the loop described in `references/panel-review.md`.

Panelists: `user-advocate`, `devils-advocate`, `pragmatist`.

There are no upstream approved artifacts at this phase — pass the current spec.md only. Deferred concerns from this panel can target `design.md` or `tasks.md`.

## Validation and approval

After the panel review is complete, run validation:

```bash
python <script-path>/validate_spec.py specs/<feature-name>/
```

Where `<script-path>` is the path to the skill's `scripts/` directory (either relative from the project, e.g. `specs/<feature-name>/../../spec-driven-dev/scripts`, or the global install location).

**Stop and ask the user to review spec.md before proceeding.**

When the user approves, run:

```bash
python <script-path>/validate_spec.py specs/<feature-name>/ --approve spec
```

This marks the spec as approved with a content hash. If the spec is edited after approval, the hash will no longer match — the skill detects this on next entry (or immediately, if Claude made the edit) and triggers the auto-cascade flow described in `hash-and-cascade.md` § "Re-Approval After Edits": structural validity is checked, the hash is re-stamped silently, and the consistency check ripples downstream. Cosmetic edits proceed without interruption; substantive edits halt at the consistency-check boundary so the user can decide whether to revise the downstream artifacts.
