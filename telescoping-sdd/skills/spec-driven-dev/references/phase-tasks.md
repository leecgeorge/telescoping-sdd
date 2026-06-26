# Phase 3: Tasks

Drafts `specs/F<n>-<slug>/03_tasks.md` — atomic, testable, sequenced implementation steps. Requires approved `spec.md` and `design.md` as upstream context. This is the last artifact phase before implementation — concerns cannot be deferred forward.

> **Artifact filenames.** This skill emits artifacts with an `NN_` ordinal prefix (`01_spec.md`, `02_design.md`, `03_tasks.md`; blueprint tier: `01_SCOPE.md`, `02_ARCHITECTURE.md`, `03_PLAN.md`) so a directory listing sorts in phase order. The prefixed form is the emit default; **both** the bare and the prefixed form are accepted on read (the validators and scripts resolve either). Wherever a path below names an artifact file — including an upstream existence check such as `blueprint/PLAN.md` — read it as "bare **or** `NN_`-prefixed" (`blueprint/PLAN.md` or `blueprint/03_PLAN.md`).

## Drafting

Delegate drafting to the `telescoping-sdd:feature-task-analyst` subagent via the Agent tool (`subagent_type: telescoping-sdd:feature-task-analyst`).

When invoking the agent, provide:
- The resolved stack profile and the matching template path:
  - Python: `references/tasks-template-python.md`
  - Java: `references/tasks-template-java.md`
  - Generic (architecture-neutral — infra, static sites, config, docs, skill authoring): there is no `-generic` template; use `references/tasks-template-python.md` for the structural skeleton (task fields and formatting are identical across profiles), but instruct the agent to populate Tests/Verification with the stack's real checks (a runnable assertion like `nginx -t` / `terraform validate` / `grep` / `test -f`, or a precise manual/review step) rather than `pytest`/`mvn` test functions. The per-task field set, GIVEN/WHEN/THEN, and the hash/approval blocks are unchanged.
- The required per-task fields (below) — the agent must produce exactly these
- The approved `specs/F<n>-<slug>/01_spec.md` and `specs/F<n>-<slug>/02_design.md` as authoritative upstream context
- The task sizing rules (below) and the instruction that every spec requirement and every design component must be covered by at least one task
- If `blueprint/PLAN.md` exists and contains a `## Cross-Feature Contracts` section, pass its contents. The agent's CFC enforcement-task obligation (below) depends on this input.
- A clear instruction to self-review the draft before returning (up to 5 passes, but stop immediately after the first pass that finds no issues — do not keep reviewing once clean), and to use the `Write` tool to write the complete `tasks.md`, including the summary table at the top and phase groupings if there are more than a few tasks, to `specs/F<n>-<slug>/03_tasks.md` and return only the canonical manifest: (1) the path written, (2) the line count, (3) the list of `##` section headings, (4) the open-questions / revision-points list — not the document body
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
- **Tests** — specific test function/method names and what they verify. **Severity is profile- and task-dependent (force-tdd-in-phase-4):**
  - **`generic`/architecture-neutral stack** (no unit-test surface — infra, static site, config, docs, skill authoring): **advisory (the validator WARNs, does not fail)**. Name the concrete check instead (a runnable assertion, a manual step, or a review check) — don't invent test functions.
  - **python/java stack, a code-touching task** (its `Files` **Create/Modify** a `.py`/`.java`): **required — the validator FAILs** if it names no test. Declare the test name(s) by-name (`` `test_foo` `` — parens optional), or by a valid sibling cross-reference (a `T<n>` whose task itself names a real code test, e.g. `Groups 1–3 from T6`).
  - **python/java stack, a non-code task** (touches only `.md`/docs/config, or only **Read**s code for context): **auto-passes** — no test name required, no override needed.
  - **R4 override — the rare code task that needs *no* test at all:** declare `**Tests:** none — <reason>` (mandatory non-empty reason; the override is surfaced as an audit count at both the Phase-3 and Phase-4 gates). Use this only for a code-touching task that legitimately has no unit to test (e.g. a pure re-export `__init__.py`).
  - **R2-vs-R4 decision rule (do not confuse them):** **R4** (`**Tests:** none — <reason>`) is for a code task that needs **no test at all**, declared up front at Phase 3. **R2** (a `## TDD Exceptions` ledger row) is for a **testable** task where the test-first *cycle* was **skipped at implementation time** (Phase 4) — the test still gets written. R4 is "no test"; R2 is "test, but not test-first."
- **Verification** — A concrete way to prove the task is done. Prefer a runnable command — `pytest tests/test_X.py -v` (Python), `mvn test -Dtest=XTest` (Java), or for a `generic` stack `nginx -t` / `terraform validate` / `docker compose config` / a `grep`/`test -f` assertion. Where no automatable surface exists, a precise, repeatable manual or visual/review step is acceptable (never a vague "test manually").

Group tasks into phases (Foundation, Core Logic, etc.) when there are more than a few tasks.

Task status is tracked in two places — the summary table at the top and the checkbox on each task heading. Both must be kept in sync and updated as tasks are completed.

Task sizing rules:
- Each task should be completable in a single implementation pass
- A task should touch no more than 3-5 files
- If a task feels too large, split it

The agent-written `tasks.md` is already on disk. `Read` `specs/F<n>-<slug>/03_tasks.md` (page with `offset`/`limit` as needed for large files), confirm the file is non-empty and its line count matches the manifest's reported line count before beginning self-review. If the file is missing or empty, treat it as a drafting failure and re-invoke the agent. On any re-invocation, re-`Read` `specs/F<n>-<slug>/03_tasks.md` before re-reviewing — do not reuse a stale in-context copy. Present the artifact to the user before approval.

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

After the spec-design-tasks consistency check is complete, run the tasks panel against `specs/F<n>-<slug>/03_tasks.md` following the loop described in `references/panel-review.md`.

Panelists: `telescoping-sdd:delivery-manager`, `telescoping-sdd:critic`, `telescoping-sdd:simplifier`.

Pass the current tasks.md and the approved spec.md and design.md. This is the last artifact phase before implementation — concerns cannot be deferred forward. Concerns that would warrant deferral should instead be handled as `Addressed` in tasks.md, `Sealed` (user-directed), or `Accepted as risk` (with explicit user sign-off and `Defense:` text in Notes).

**Exposure sequencing check.** When reviewing the task ordering, consult the Exposure Doctrine before approving the ordering; if any task exposes a surface before the task that installs/hardens/blocks it, the required response is ONE of: (i) raise it as an `[upstream]`-tagged concern (which routes to a halt vote via the existing Phase 2/3 concern-tagging machinery) when the missing gate lives in already-approved upstream content (e.g. an approved spec.md or design.md blesses the exposure), or (ii) resolve it in-phase by reordering the tasks or naming an interim mitigation — see `## Exposure Doctrine` in `phase-specify.md`. For intra-feature task edges within the CURRENT tasks.md, bias toward reorder; `[upstream]` is appropriate only when the gate is genuinely missing from approved spec.md or design.md. Filing it as a soft MED that is dispositioned away without a gate or reorder is NOT an acceptable response. Note: the Tasks tier is scoped to intra-feature task ordering; cross-feature exposure edges (e.g. F3→F4→F5) are a Plan-tier concern.

## Validation and approval

After the panel review is complete, run validation:

```bash
python <script-path>/validate_spec.py specs/F<n>-<slug>/
```

**Stop and ask the user to review tasks.md before proceeding.**

If the user requests a change at this gate (before approving), do not apply it silently — route it through `references/panel-review.md § "Handling change requests at the review gate"` (substantive change re-enters the panel loop; trivial wording is a synthesizer fix + Self-Check, panel-skip-eligible), then re-present. No hash exists yet, so there is no re-stamp or cascade. (tasks.md is the terminal artifact — concerns surfaced by a re-run cannot be deferred forward; dispose them Addressed / Sealed / Accepted as risk.)

When the user approves, run:

```bash
python <script-path>/validate_spec.py specs/F<n>-<slug>/ --approve tasks
```
