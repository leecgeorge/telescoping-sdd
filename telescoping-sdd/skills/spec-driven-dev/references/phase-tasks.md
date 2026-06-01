# Phase 3: Tasks

Drafts `specs/<feature-name>/tasks.md` — atomic, testable, sequenced implementation steps. Requires approved `spec.md` and `design.md` as upstream context. This is the last artifact phase before implementation — concerns cannot be deferred forward.

## Drafting

Delegate drafting to the `telescoping-sdd:feature-task-analyst` subagent via the Agent tool (`subagent_type: telescoping-sdd:feature-task-analyst`).

When invoking the agent, provide:
- The resolved stack profile and the matching template path:
  - Python: `references/tasks-template-python.md`
  - Java: `references/tasks-template-java.md`
  - Generic (architecture-neutral — infra, static sites, config, docs, skill authoring): there is no `-generic` template; use `references/tasks-template-python.md` for the structural skeleton (task fields and formatting are identical across profiles), but instruct the agent to populate Tests/Verification with the stack's real checks (a runnable assertion like `nginx -t` / `terraform validate` / `grep` / `test -f`, or a precise manual/review step) rather than `pytest`/`mvn` test functions. The per-task field set, GIVEN/WHEN/THEN, and the hash/approval blocks are unchanged.
- The required per-task fields (below) — the agent must produce exactly these
- The approved `specs/<feature-name>/spec.md` and `specs/<feature-name>/design.md` as authoritative upstream context
- The task sizing rules (below) and the instruction that every spec requirement and every design component must be covered by at least one task
- If `blueprint/PLAN.md` exists and contains a `## Cross-Feature Contracts` section, pass its contents. The agent's CFC enforcement-task obligation (below) depends on this input.
- A clear instruction to self-review the draft before returning (up to 5 passes, but stop immediately after the first pass that finds no issues — do not keep reviewing once clean), and to return a complete, clean draft of `tasks.md`, including the summary table at the top and phase groupings if there are more than a few tasks
- A clear instruction to reproduce the template's exact formatting for structural sections — in particular: task headings must use `### - [ ] T1:` checkbox format, the summary table must use the exact column headers from the template, Open Questions must use `- [ ] Q1:` checkbox format, and the Approval section must be exactly `- [ ] Approved to proceed to implementation` followed by `- **Content Hash:** \`pending\`` (not a table or other format). The agent must read the template file and match its syntax precisely.

**CFC enforcement-task obligation.** For every `### CFC-N` in `blueprint/PLAN.md`'s Cross-Feature Contracts section whose `**Enforcement:**` prose names this feature as the owner (the feature's identifier `F<n>` appears as a bare token, word-boundary), `tasks.md` must contain a task whose deliverable is the verifying artifact named in that Enforcement field (ArchUnit rule, CI grep, integration test, runbook gate, etc.). The task description must include the binding tag `[CFC-N]`. Place the tag at the end of the task title on the checkbox line: `- [ ] <task title naming the artifact> [CFC-N]`. The validator checks for this tag with the whole-number regex `\[CFC-(\d+)\]` — substring matching is not used; `[CFC-1]` and `[CFC-10]` are distinct.

Each task must include:
- **Task ID** — Sequential (T1, T2, T3...)
- **Requirement** — Which spec requirement this implements (R1, R2, etc.)
- **Description** — What to do in one sentence
- **Files** — Which files to read (for context), create, or modify
- **Dependencies** — Which tasks must complete first
- **Parallel** — Whether this task can run concurrently with other tasks, and which ones (e.g., "Yes (with T3)")
- **Acceptance Criteria** — GIVEN/WHEN/THEN format, matching the spec style
- **Tests** (advisory — the validator warns, does not fail) — For a stack with a test harness, specific test function/method names and what they verify. For a `generic`/architecture-neutral stack with no unit-test surface (infra, static site, config, docs, skill authoring), name the concrete check instead (a runnable assertion, a manual step, or a review check) — don't invent test functions.
- **Verification** — A concrete way to prove the task is done. Prefer a runnable command — `pytest tests/test_X.py -v` (Python), `mvn test -Dtest=XTest` (Java), or for a `generic` stack `nginx -t` / `terraform validate` / `docker compose config` / a `grep`/`test -f` assertion. Where no automatable surface exists, a precise, repeatable manual or visual/review step is acceptable (never a vague "test manually").

Group tasks into phases (Foundation, Core Logic, etc.) when there are more than a few tasks.

Task status is tracked in two places — the summary table at the top and the checkbox on each task heading. Both must be kept in sync and updated as tasks are completed.

Task sizing rules:
- Each task should be completable in a single implementation pass
- A task should touch no more than 3-5 files
- If a task feels too large, split it

After the agent returns the draft, write it to `specs/<feature-name>/tasks.md` and perform the self-review yourself before presenting it to the user.

## Tasks Self-Review

Review the tasks.md you just wrote, checking for:

1. **Inconsistencies** — Do task dependencies form a valid DAG (no circular dependencies)? Do parallel annotations match the dependency graph? Does the summary table match the detailed task descriptions?
2. **Inaccuracies** — Do file paths in each task match the design's file structure? Are test/verification locations and commands correct for the project's tooling (build tool for a code stack; the stack's real check tooling — `nginx -t`, `terraform validate`, a `grep`/`test -f` assertion, or a manual/review step — for a `generic` stack)? Do task IDs in dependencies reference tasks that exist?
3. **Gaps** — Does every requirement from the spec have at least one task covering it? Does every component from the design have tasks to build and test it? Are there missing integration or wiring tasks between components?

For each issue found:
- **Fix it directly** if the correct resolution is clear (e.g., a wrong file path, a missing dependency, a summary table out of sync with task details)
- **Stop and ask the user** if the resolution requires a judgment call (e.g., how to split an oversized task, whether a requirement needs multiple tasks or one)

If any issues were fixed, repeat the self-review on the updated tasks — fixes can introduce new issues. If a pass finds no issues, stop immediately. Do not exceed 5 review passes total.

## Spec-Design-Tasks Consistency Check

After the tasks self-review is complete, cross-reference tasks.md against both spec.md and design.md:

1. **Requirement coverage** — Every requirement (R1, R2, etc.) in spec.md must be covered by at least one task. Flag any requirements with no corresponding task.
2. **Design alignment** — Every component, interface, and data model in design.md must have tasks that build and test it. The file paths in tasks must match the design's file structure.
3. **Acceptance criteria traceability** — Each spec acceptance criterion (GIVEN/WHEN/THEN) should be traceable to at least one task's acceptance criteria and tests.
4. **Boundary compliance** — No task should violate spec boundaries ("Never do" items). All "Always do" items should be reflected in relevant tasks.
5. **Implementation sequence** — The task ordering and dependencies should be consistent with the design's implementation sequence.

For each issue found:
- **Fix it directly** in tasks.md if the spec and design are clearly authoritative (e.g., a missing task for an uncovered requirement, a file path mismatch, a dependency ordering that contradicts the design)
- **Stop and ask the user** if the conflict is ambiguous (e.g., a design component that may not need its own task, or a spec requirement that could be covered by an existing task or may need a new one)

## Tasks Panel Review

After the spec-design-tasks consistency check is complete, run the tasks panel against `specs/<feature-name>/tasks.md` following the loop described in `references/panel-review.md`.

Panelists: `telescoping-sdd:delivery-manager`, `telescoping-sdd:critic`, `telescoping-sdd:simplifier`.

Pass the current tasks.md and the approved spec.md and design.md. This is the last artifact phase before implementation — concerns cannot be deferred forward. Concerns that would warrant deferral should instead be handled as `Addressed` in tasks.md, `Sealed` (user-directed), or `Accepted as risk` (with explicit user sign-off and `Defense:` text in Notes).

## Validation and approval

After the panel review is complete, run validation:

```bash
python <script-path>/validate_spec.py specs/<feature-name>/
```

**Stop and ask the user to review tasks.md before proceeding.**

If the user requests a change at this gate (before approving), do not apply it silently — route it through `references/panel-review.md § "Handling change requests at the review gate"` (substantive change re-enters the panel loop; trivial wording is a synthesizer fix + Self-Check, panel-skip-eligible), then re-present. No hash exists yet, so there is no re-stamp or cascade. (tasks.md is the terminal artifact — concerns surfaced by a re-run cannot be deferred forward; dispose them Addressed / Sealed / Accepted as risk.)

When the user approves, run:

```bash
python <script-path>/validate_spec.py specs/<feature-name>/ --approve tasks
```
