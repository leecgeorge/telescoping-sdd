<!--
SHARED REFERENCE — keep in sync with the project-blueprint copy at
skills/project-blueprint/references/examples.md. Edits to shared walkthrough structure must be mirrored in BOTH copies.

Intentional asymmetries vs the sibling (do NOT "sync" these away):
- spec-driven-dev's Example 1 has a language-detection step + language-specific template; blueprint has neither.
- Architecture/Design panel's middle seat differs: telescoping-sdd:ops-reviewer (blueprint) vs telescoping-sdd:testability-reviewer (spec-driven-dev).
- Example 3's terminal Phase-3 artifact differs: PLAN.md (blueprint) vs tasks.md (spec-driven-dev), with matching analyst names.
- Example 4 differs by design: blueprint hands off to /spec-driven-dev (no artifact Phase 4); spec-driven-dev runs the Implement/TDD loop with a task tick.
Otherwise the copies differ only cosmetically (skill name in intro, section titles, example user prompts, terminology mapping).
-->

# Examples

End-to-end walkthroughs of the spec-driven-dev workflow.

> **Artifact filenames:** these walkthroughs use the bare names (`spec.md`, `design.md`, `tasks.md`) as shorthand. The skill emits the `NN_`-prefixed form (`01_spec.md`, `02_design.md`, `03_tasks.md`) by default; both forms resolve on read.

## Example 1: Starting Fresh

User says: "Create a spec for a CLI todo app"

Actions:
1. Detect project language and state it to the user
2. Create `specs/cli-todo-app/` directory
3. Invoke the `feature-spec-analyst` subagent to draft `spec.md` from the language-specific template, passing the user's requirements and the required sections
4. Read the agent-written `spec.md` from disk (`specs/cli-todo-app/spec.md`) — the agent already wrote it; confirm non-empty before self-review
5. Self-review spec.md for inconsistencies, inaccuracies, and gaps (up to 5 passes)
6. Run the spec panel (`telescoping-sdd:user-advocate`, `telescoping-sdd:devils-advocate`, `telescoping-sdd:pragmatist`) against spec.md following the loop in `references/panel-review.md` (synthesize, dispose, populate `### Latest pass detail`, run Synthesizer Self-Check, invoke `archive_pass.py`, halt-trigger check, exit on zero unresolved HIGHs — HIGHs other than those dismissed with a recorded `Defense:`)
7. Run validate_spec.py on the spec
8. Present spec.md for review
9. Wait for approval before the design phase

## Example 2: Resuming Work

User says: "I have a spec, help me design it"

Actions:
1. Read the existing spec.md
2. Validate it has all required sections and is approved
3. Invoke the `feature-architecture-analyst` subagent to draft `design.md`, passing spec.md as authoritative upstream context
4. Read the agent-written `design.md` from disk (`specs/F<n>-<slug>/design.md`) — the agent already wrote it; confirm non-empty before self-review
5. Self-review design.md (up to 5 passes)
6. Cross-reference design.md against spec.md for consistency
7. Run the design panel (`telescoping-sdd:architect`, `telescoping-sdd:testability-reviewer`, `telescoping-sdd:security-reviewer`) against design.md following the loop in `references/panel-review.md`
8. Run validate_spec.py
9. Present design.md for review

## Example 3: Creating Tasks

User says: "Break the design into tasks"

Actions:
1. Read spec.md and design.md
2. Invoke the `feature-task-analyst` subagent to draft `tasks.md`, passing spec.md and design.md as authoritative upstream context
3. Read the agent-written `tasks.md` from disk (`specs/F<n>-<slug>/tasks.md`) — the agent already wrote it; confirm non-empty before self-review
4. Self-review tasks.md (up to 5 passes)
5. Cross-reference tasks.md against spec.md and design.md for consistency
6. Run the tasks panel (`telescoping-sdd:delivery-manager`, `telescoping-sdd:critic`, `telescoping-sdd:simplifier`) against tasks.md following the loop in `references/panel-review.md`. Concerns cannot be deferred forward at this phase — they must land on `Addressed`, `Sealed`, or `Accepted as risk`.
7. Run validate_spec.py
8. Present tasks.md for review

## Example 4: Implementation Phase

User says: "Implement task T3 from the spec"

Actions:
1. Read tasks.md, find T3
2. Check T3's dependencies are complete (status is `Done` in the summary table)
3. Write tests for T3's acceptance criteria
4. Implement code to pass tests
5. Run full test suite
6. Update tasks.md: set T3's status to `Done` in the summary table and check off its checkbox
