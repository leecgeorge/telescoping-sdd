<!--
SHARED REFERENCE — keep in sync with the spec-driven-dev copy at
skills/spec-driven-dev/references/examples.md. Edits to shared walkthrough structure must be mirrored in BOTH copies.

Intentional asymmetries vs the sibling (do NOT "sync" these away):
- spec-driven-dev's Example 1 has a language-detection step + language-specific template; blueprint has neither.
- Architecture/Design panel's middle seat differs: telescoping-sdd:ops-reviewer (blueprint) vs telescoping-sdd:testability-reviewer (spec-driven-dev).
- Example 3's terminal Phase-3 artifact differs: PLAN.md (blueprint) vs tasks.md (spec-driven-dev), with matching analyst names.
- Example 4 differs by design: blueprint hands off to /spec-driven-dev (no artifact Phase 4); spec-driven-dev runs the Implement/TDD loop with a task tick.
Otherwise the copies differ only cosmetically (skill name in intro, section titles, example user prompts, terminology mapping).
-->

# Examples

End-to-end walkthroughs of the project-blueprint workflow.

> **Artifact filenames:** these walkthroughs use the bare names (`SCOPE.md`, `ARCHITECTURE.md`, `PLAN.md`) as shorthand. The skill emits the `NN_`-prefixed form (`01_SCOPE.md`, `02_ARCHITECTURE.md`, `03_PLAN.md`) by default; both forms resolve on read.

## Example 1: Starting a New Project

User says: "I want to plan a new project for a task management API"

Actions:
1. Create `blueprint/` directory
2. Invoke the `project-spec-analyst` subagent to draft `SCOPE.md` from the template, passing the user's requirements and the required sections
3. Read the agent-written `SCOPE.md` from disk (`blueprint/SCOPE.md`) — the agent already wrote it; confirm non-empty before self-review
4. Self-review SCOPE.md for inconsistencies, inaccuracies, and gaps (up to 5 passes)
5. Run the scope panel (`telescoping-sdd:user-advocate`, `telescoping-sdd:devils-advocate`, `telescoping-sdd:pragmatist`) against SCOPE.md following the loop in `references/panel-review.md` (synthesize, dispose, populate `### Latest pass detail`, run Synthesizer Self-Check, invoke `archive_pass.py`, halt-trigger check, exit on zero unresolved HIGHs — HIGHs other than those dismissed with a recorded `Defense:` — and nothing disposed `Addressed`)
6. Run validate_blueprint.py on the scope
7. Present SCOPE.md for review
8. Wait for approval before proceeding to architecture

## Example 2: Resuming Work

User says: "I have a scope document, help me design the architecture"

Actions:
1. Read the existing SCOPE.md
2. Validate it has all required sections and is approved
3. Invoke the `project-architecture-analyst` subagent to draft `ARCHITECTURE.md`, passing SCOPE.md as authoritative upstream context
4. Read the agent-written `ARCHITECTURE.md` from disk (`blueprint/ARCHITECTURE.md`) — the agent already wrote it; confirm non-empty before self-review
5. Self-review ARCHITECTURE.md (up to 5 passes)
6. Cross-reference ARCHITECTURE.md against SCOPE.md for consistency
7. Run the architecture panel (`telescoping-sdd:architect`, `telescoping-sdd:ops-reviewer`, `telescoping-sdd:security-reviewer`) against ARCHITECTURE.md following the loop in `references/panel-review.md`
8. Run validate_blueprint.py
9. Present ARCHITECTURE.md for review

## Example 3: Creating the Implementation Plan

User says: "Architecture looks good, let's plan the features"

Actions:
1. Read SCOPE.md and ARCHITECTURE.md
2. Invoke the `project-plan-analyst` subagent to draft `PLAN.md`, passing SCOPE.md and ARCHITECTURE.md as authoritative upstream context
3. Read the agent-written `PLAN.md` from disk (`blueprint/PLAN.md`) — the agent already wrote it; confirm non-empty before self-review
4. Self-review PLAN.md (up to 5 passes)
5. Cross-reference PLAN.md against SCOPE.md and ARCHITECTURE.md for consistency
6. Run the plan panel (`telescoping-sdd:delivery-manager`, `telescoping-sdd:critic`, `telescoping-sdd:simplifier`) against PLAN.md following the loop in `references/panel-review.md`. Concerns cannot be deferred forward at this phase — they must land on `Addressed`, `Sealed`, or `Accepted as risk`.
7. Run validate_blueprint.py
8. Present PLAN.md for review

## Example 4: Blueprint Complete

User says: "The blueprint is done, what's next?"

Actions:
1. Verify all three documents exist and are approved
2. Identify the first feature from PLAN.md implementation order
3. Suggest using `/spec-driven-dev` to begin feature development
