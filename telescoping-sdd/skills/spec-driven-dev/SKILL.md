---
name: spec-driven-dev
description: Guides spec-driven development workflow for Python and Java projects. Use when user says "create a spec", "design a feature", "break down tasks", "implement from spec", "spec-driven", or "SDD workflow". Walks through four phases — Specify, Design, Tasks, Implement — with human review gates between each phase.
metadata:
  status: stable
---

# Spec-Driven Development

> **Status: Stable** — ready for day-to-day use.

A structured workflow that produces specification documents before writing code, ensuring alignment between intent and implementation.

## Overview

Every feature follows four phases. **Always get user approval before moving to the next phase.**

1. **Specify** — Define what to build (`spec.md`) — drafted by the `telescoping-sdd:feature-spec-analyst` agent
2. **Design** — Decide how to build it (`design.md`) — drafted by the `telescoping-sdd:feature-architecture-analyst` agent
3. **Tasks** — Break it into atomic steps (`tasks.md`) — drafted by the `telescoping-sdd:feature-task-analyst` agent
4. **Implement** — Execute tasks with TDD (no delegation — the calling Claude implements directly)

All spec documents live in `specs/<feature-name>/` at the project root.

Read `references/workflow-overview.md` for a quick-reference diagram of the full process.

### Path placeholders

The commands in this skill reference two distinct script roots:

* `<script-path>` resolves to the skill's own `scripts/` directory — under the plugin install root at `skills/spec-driven-dev/scripts/` (e.g., `~/.claude/plugins/cache/<marketplace>/telescoping-sdd/<version>/skills/spec-driven-dev/scripts/` for marketplace installs, or `<plugin-dir>/skills/spec-driven-dev/scripts/` for `--plugin-dir` dev mode).
* `<shared-script-path>` resolves to `telescoping-sdd/scripts/` — the plugin-wide shared scripts directory, sibling of `telescoping-sdd/skills/`. `<shared-script-path>/archive_pass.py` is the cross-skill panel-archiving tool shared with `project-blueprint`.

Running `validate_spec.py` is **optional for fresh artifacts** (the panel-review step already catches most issues the validator would) **but required when entering or resuming a workflow with existing approved artifacts** — it detects post-approval edits made outside the current session that would otherwise leave the chain silently out of sync. (Edits Claude makes mid-session don't need the validator to detect them — Claude already knows it edited the file. Both flows feed into the same handling — see "Re-Approval After Edits.") Running `archive_pass.py` is **required** between panel passes — it maintains `### Trajectory`, promotes `### Sealed dispositions`, and clears `### Latest pass detail` so the next pass starts cleanly.

### Phase shape (Phases 1–3)

Phases 1–3 delegate document drafting to a specialist subagent via the Agent tool. The agent produces a draft and self-reviews it before returning (up to 5 passes — fixing issues it can resolve, flagging others with `[TBD]`). After the agent returns, you (the calling Claude) perform your own review, run any cross-document consistency check, then invoke a three-persona **panel review** to stress-test the artifact for blind-spot and quality issues. The panel runs a review loop (auto-fix or ask the user, up to 5 passes). When the panel exits — i.e., a pass returns zero HIGH-severity concerns — run validation and present the document to the user. The agent catches internal issues; the panel catches blind-spot and quality issues; you catch cross-document and conversation-context issues.

Phase 4 (implementation) is executed directly by the calling Claude with no delegation, since the TDD cycle benefits from interactive visibility and mid-task course correction; there is no panel review at Phase 4.

**The shared panel-review machinery — the loop, synthesizer self-check, halt-and-rescope exit, strict-bar convergence mode, format contract for `## Panel Review`, and when to skip the panel — lives in `references/panel-review.md`. Read that reference before running any phase's panel.**

## Language Detection

Before starting any phase, detect the project language:

- **Java** — Look for `pom.xml`, `build.gradle`, `build.gradle.kts`, or `src/main/java/` directory
- **Python** — Look for `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt`, or `src/` with `.py` files

State the detected language to the user at the start of the first phase you enter. If both are present or neither is detected, ask the user which language to use. Use the detected language to select the correct conventions, templates, and validation rules throughout all phases.

## Phase 1: Specify

Output: `specs/<feature-name>/spec.md`. Drafted by `telescoping-sdd:feature-spec-analyst`.

Required sections: Objective, Requirements, Acceptance Criteria, Project Structure, Boundaries, Success Criteria.

Panelists: `telescoping-sdd:user-advocate`, `telescoping-sdd:devils-advocate`, `telescoping-sdd:pragmatist`.

**Read `references/phase-specify.md` for the full Phase 1 workflow — drafting, self-review, panel, validation, and approval.**

## Phase 2: Design

Output: `specs/<feature-name>/design.md`. Drafted by `telescoping-sdd:feature-architecture-analyst`. Requires approved `spec.md`.

Required sections: Goals and Non-Goals, Architecture Decisions, Component Design, Data Models, Interfaces, Error Handling, Testing Strategy, File Structure, Dependencies, Integration Points, Risks, Implementation Sequence.

Panelists: `telescoping-sdd:architect`, `telescoping-sdd:testability-reviewer`, `telescoping-sdd:security-reviewer`.

**Read `references/phase-design.md` for the full Phase 2 workflow — drafting, self-review, spec-design consistency check, panel, validation, and approval.**

## Phase 3: Tasks

Output: `specs/<feature-name>/tasks.md`. Drafted by `telescoping-sdd:feature-task-analyst`. Requires approved `spec.md` and `design.md`.

Required per-task fields: Task ID, Requirement, Description, Files, Dependencies, Parallel, Acceptance Criteria, Tests, Verification.

Panelists: `telescoping-sdd:delivery-manager`, `telescoping-sdd:critic`, `telescoping-sdd:simplifier`.

**Read `references/phase-tasks.md` for the full Phase 3 workflow — drafting, sizing rules, self-review, spec-design-tasks consistency check, panel, validation, and approval. This is the last artifact phase; concerns cannot be deferred forward.**

## Phase 4: Implement

Execute tasks sequentially following this cycle for each task:

1. Read the task from tasks.md
2. Write tests first that encode the acceptance criteria
3. Implement the code to make tests pass
4. Run the full test suite to check for regressions
5. Update tasks.md immediately — do both of the following before moving to the next task:
   - Change the task's Status in the Summary table from `Not Started` to `Done`
   - Check off the task's checkbox in the heading (e.g., `### - [ ] T1:` becomes `### - [x] T1:`)

### Language Conventions

**Python**
- Use type hints on all function signatures
- Use pytest for tests, place in `tests/` directory mirroring `src/` structure
- Follow existing project conventions (check for pyproject.toml, setup.cfg, etc.)
- Run linters/formatters if configured (ruff, black, mypy)

**Java**
- Use explicit types on all method signatures and fields
- Use JUnit 5 for tests, place in `src/test/java/` mirroring `src/main/java/` package structure
- Follow existing project conventions (check for pom.xml, build.gradle, etc.)
- Run linters/formatters if configured (Checkstyle, SpotBugs, google-java-format)
- Build and test with `mvn test` or `gradle test` depending on the build tool

After completing all tasks, do a final check:
- All tests pass
- All acceptance criteria from spec.md are met
- All tasks in tasks.md are checked off and all summary table statuses are `Done` (or `Skipped` for invalidated tasks)
- **Re-stamp `tasks.md` once**: first run `python <script-path>/validate_spec.py specs/<feature-name>/` and confirm structural validity (no `[TBD]`, no `TODO`/`FIXME` leaked into task descriptions, all required sections present, `## Panel Review` populated). If any structural check fails, halt and fix before re-stamping — re-stamping a structurally broken `tasks.md` would silently approve known-bad content. Once structural checks pass, run `python <script-path>/validate_spec.py specs/<feature-name>/ --approve tasks`. This is the completion re-stamp called out in `references/hash-and-cascade.md` (intro paragraph: Phase 4 cadence) — it refreshes the hash that's been stale since the first tick. No cascade follows (tasks.md has no downstream).

<!-- The two sections below mention a Phase 4 carve-out / Phase 4 exception that is intentional asymmetry vs project-blueprint/SKILL.md. spec-driven-dev has a Phase 4 (Implement) where tasks.md is edited continuously; project-blueprint has no analogous phase. Do not "sync" these pointer paragraphs by removing the Phase 4 references — the full asymmetry rationale lives in references/hash-and-cascade.md (intro paragraph). -->

## Entering the Workflow Mid-Stream

If users already have artifacts (spec.md, design.md, and/or tasks.md), validate them before doing any phase work. The procedure — structural-validity check, auto-restamp on stale hashes (which then routes through the upstream panel re-review step before cascading, exactly as in "Re-Approval After Edits"), halt-and-ask on unchecked boxes, the Phase 4 carve-out for mid-Phase-4 resumption (task-tick edits suppress both the upstream panel re-review and the cascade), then routing to the right phase — lives in **`references/hash-and-cascade.md` § "Entering the Workflow Mid-Stream"**. Read it before resuming. A stale-hash mid-stream entry on an artifact OTHER than a task-ticked `tasks.md` is a top-level entry of the re-approval flow; the upstream panel re-review step fires unless the diff is visibly trivial.

## Re-Approval After Edits

When an approved document is edited (by Claude at the user's request, by the user directly, or via a `git` operation), the response is automatic: (1) verify structural validity, (2) re-stamp the edited document silently, (3) **run the upstream panel re-review step** to decide whether to stress-test the edited document itself before its changes propagate, then (4) run the consistency-check cascade against approved downstream artifacts. **Do not prompt for permission to re-stamp** — the user has already authorized the edit by making it. Step 3 (upstream panel re-review) is **mandatory unless the diff is visibly trivial**: it fires on every top-level entry, and only visibly-trivial edits (whitespace / punctuation / comment-only, per the four-criterion test) skip silently — every other edit produces a recommendation+ask. Going straight from re-stamp to cascade without running step 3 is a flow violation. **Phase 4 (Implement) has an exception**: normal task-tick edits to `tasks.md` do not trigger this flow (re-stamping after every tick would be noise) — see the Phase 4 cadence in the intro of `references/hash-and-cascade.md`. The full flow — structural-validity precondition, source-tag determination, four-criterion triviality test, lean-yes/lean-no recommendation prompts, halt-on-substantive-divergence behavior, resolution paths (revise or accept), and the downstream optional panel re-review recommendation — lives in **`references/hash-and-cascade.md` § "Re-Approval After Edits"**.

## See also

- `references/hash-and-cascade.md` — full hash-handling flow: mid-stream entry, re-approval after edits, the cascade, the halt-on-substantive-divergence rule, the optional panel re-review recommendation, and the Phase 4 (Implement) cadence. Read this whenever an approved document changes.
- `references/panel-review.md` — the shared panel-review loop, synthesizer self-check, halt-and-rescope exit, strict-bar convergence mode, format contract, and panel-skip rules. Read before running any phase's panel.
- `references/strict-bar-prompts.md` — per-phase prompt additions for strict-bar passes. Loaded only when a strict-bar pass runs.
- `references/phase-specify.md`, `references/phase-design.md`, `references/phase-tasks.md` — full per-phase workflows.
- `references/workflow-overview.md` — quick-reference diagram of the full process.
- `references/spec-template-python.md`, `references/spec-template-java.md` — document templates the spec drafting agent must follow exactly. Equivalent `design-template-*` and `tasks-template-*` files exist for Phases 2 and 3.
- `references/examples.md` — end-to-end walkthroughs for common entry points (new spec, resuming, tasks-only, implementation).
- `references/troubleshooting.md` — failure modes and recovery (validation failures, requirement drift, panel non-convergence, etc.).
