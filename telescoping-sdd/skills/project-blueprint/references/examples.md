# Examples

End-to-end walkthroughs of the project-blueprint workflow.

## Example 1: Starting a New Project

User says: "I want to plan a new project for a task management API"

Actions:
1. Create `blueprint/` directory
2. Invoke the `project-spec-analyst` subagent to draft `SCOPE.md` from the template, passing the user's requirements and the required sections
3. Write the returned draft to `blueprint/SCOPE.md`
4. Self-review SCOPE.md for inconsistencies, inaccuracies, and gaps (up to 5 passes)
5. Run the scope panel (`user-advocate`, `devils-advocate`, `pragmatist`) against SCOPE.md following the loop in `references/panel-review.md` (synthesize, dispose, populate `### Latest pass detail`, run Synthesizer Self-Check, invoke `archive_pass.py`, halt-trigger check, exit on zero HIGHs)
6. Run validate_blueprint.py on the scope
7. Present SCOPE.md for review
8. Wait for approval before proceeding to architecture

## Example 2: Resuming Work

User says: "I have a scope document, help me design the architecture"

Actions:
1. Read the existing SCOPE.md
2. Validate it has all required sections and is approved
3. Invoke the `project-architecture-analyst` subagent to draft `ARCHITECTURE.md`, passing SCOPE.md as authoritative upstream context
4. Write the returned draft to `blueprint/ARCHITECTURE.md`
5. Self-review ARCHITECTURE.md (up to 5 passes)
6. Cross-reference ARCHITECTURE.md against SCOPE.md for consistency
7. Run the architecture panel (`architect`, `ops-reviewer`, `security-reviewer`) against ARCHITECTURE.md following the loop in `references/panel-review.md`
8. Run validate_blueprint.py
9. Present ARCHITECTURE.md for review

## Example 3: Creating the Implementation Plan

User says: "Architecture looks good, let's plan the features"

Actions:
1. Read SCOPE.md and ARCHITECTURE.md
2. Invoke the `project-plan-analyst` subagent to draft `PLAN.md`, passing SCOPE.md and ARCHITECTURE.md as authoritative upstream context
3. Write the returned draft to `blueprint/PLAN.md`
4. Self-review PLAN.md (up to 5 passes)
5. Cross-reference PLAN.md against SCOPE.md and ARCHITECTURE.md for consistency
6. Run the plan panel (`delivery-manager`, `critic`, `simplifier`) against PLAN.md following the loop in `references/panel-review.md`. Concerns cannot be deferred forward at this phase — they must land on `Addressed`, `Sealed`, or `Accepted as risk`.
7. Run validate_blueprint.py
8. Present PLAN.md for review

## Example 4: Blueprint Complete

User says: "The blueprint is done, what's next?"

Actions:
1. Verify all three documents exist and are approved
2. Identify the first feature from PLAN.md implementation order
3. Suggest using `/spec-driven-dev` to begin feature development
