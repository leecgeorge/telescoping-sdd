# Examples

End-to-end walkthroughs of the spec-driven-dev workflow.

## Example 1: Starting Fresh

User says: "Create a spec for a CLI todo app"

Actions:
1. Detect project language and state it to the user
2. Create `specs/cli-todo-app/` directory
3. Invoke the `feature-spec-analyst` subagent to draft `spec.md` from the language-specific template, passing the user's requirements and the required sections
4. Write the returned draft to `specs/cli-todo-app/spec.md`
5. Self-review spec.md for inconsistencies, inaccuracies, and gaps (up to 5 passes)
6. Run the spec panel (`user-advocate`, `devils-advocate`, `pragmatist`) against spec.md following the loop in `references/panel-review.md` (synthesize, dispose, populate `### Latest pass detail`, run Synthesizer Self-Check, invoke `archive_pass.py`, halt-trigger check, exit on zero HIGHs)
7. Run validate_spec.py on the spec
8. Present spec.md for review
9. Wait for approval before the design phase

## Example 2: Resuming Work

User says: "I have a spec, help me design it"

Actions:
1. Read the existing spec.md
2. Validate it has all required sections and is approved
3. Invoke the `feature-architecture-analyst` subagent to draft `design.md`, passing spec.md as authoritative upstream context
4. Write the returned draft to `specs/<feature-name>/design.md`
5. Self-review design.md (up to 5 passes)
6. Cross-reference design.md against spec.md for consistency
7. Run the design panel (`architect`, `testability-reviewer`, `security-reviewer`) against design.md following the loop in `references/panel-review.md`
8. Run validate_spec.py
9. Present design.md for review

## Example 3: Creating Tasks

User says: "Break the design into tasks"

Actions:
1. Read spec.md and design.md
2. Invoke the `feature-task-analyst` subagent to draft `tasks.md`, passing spec.md and design.md as authoritative upstream context
3. Write the returned draft to `specs/<feature-name>/tasks.md`
4. Self-review tasks.md (up to 5 passes)
5. Cross-reference tasks.md against spec.md and design.md for consistency
6. Run the tasks panel (`delivery-manager`, `critic`, `simplifier`) against tasks.md following the loop in `references/panel-review.md`. Concerns cannot be deferred forward at this phase — they must land on `Addressed`, `Sealed`, or `Accepted as risk`.
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
