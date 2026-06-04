---
name: spec-driven-dev
description: Guides spec-driven development workflow for Python, Java, or architecture-neutral (generic) projects — including infrastructure, static sites, and Claude-skill authoring. Use when user says "create a spec", "design a feature", "break down tasks", "implement from spec", "spec-driven", or "SDD workflow". Walks through four phases — Specify, Design, Tasks, Implement — with human review gates between each phase.
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

All spec documents live in the feature's spec directory at the project root (see **Spec directory naming** below).

Read `references/workflow-overview.md` for a quick-reference diagram of the full process.

### Spec directory naming

A spec directory's name takes one of three forms, and it MUST agree with the `**PLAN feature identifier:**` line inside `spec.md`:

- **Bound** — `specs/F<n>-<slug>/` (uppercase `F`, a positive feature number with no leading zero, then a lowercase-kebab `<slug>` of ≤ 50 chars). Use this for a feature that appears in `blueprint/PLAN.md`; its in-file identifier is `` `F<n>` ``. Example: directory `specs/F3-checkout-flow/` pairs with the line `**PLAN feature identifier:** `F3``.
- **Standalone** — `specs/<slug>/` (a bare lowercase-kebab slug, no `F<n>-` prefix). Use this for a feature with no PLAN; its in-file identifier is `` `n/a` ``. Example: directory `specs/checkout-flow/` pairs with `**PLAN feature identifier:** `n/a``.
- **Derived** — `specs/<project>--F<n>-<slug>/` (a lowercase-kebab master-project alias, the `--` sentinel, then a bound-style `F<n>-<slug>`). Use this for a feature that implements **another repo's** master PLAN feature (Cross-Project Derivation). Its in-file identifier is `` `n/a` `` (the feature is standalone within THIS repo), and provenance lives on two extra lines instead: `**Derived from:** `<project>:F<n>`` (the master qualified id) and `**Master contract hash:**` (the master feature's contract hash at bind time, or the literal `` `unbound` `` until the first reconcile). Example: directory `specs/residents--F7-resident-sync/` pairs with `**PLAN feature identifier:** `n/a``, `**Derived from:** `residents:F7``, and `**Master contract hash:** `a1b2c3…``. See `references/phase-specify.md` and `references/workflow-overview.md § Cross-Project Derivation`.

`validate_spec.py` enforces this agreement as a **blocking FAIL** — it owns the authoring gate, so a bare `specs/F<n>/` directory (missing slug), an invalid name, or a directory↔identifier mismatch refuses both validation and `--approve`. For a **derived** directory it cross-checks the `<project>--F<n>` prefix against the spec's `**Derived from:** `<project>:F<n>`` line (requiring `**PLAN feature identifier:** `n/a``) instead of a local PLAN, FAILing `derived-provenance-mismatch` on any disagreement; it also exempts derived specs from the `n/a`-standalone CFC-coherence WARNs. `validate_blueprint.py` is deliberately more lenient: a bare `specs/F<n>/` still resolves to its feature for CFC coverage but earns only a `malformed-spec-dirname` **WARN**, and a **derived** directory is excluded from the local PLAN coverage walk altogether (derived features belong to `reconcile`, not this repo's PLAN) — sibling-gated, else an informational `derived-dir-no-sibling` WARN. Same root cause, different severity — blueprint stays non-blocking so older projects keep resolving coverage, while the spec owns the authoring gate.

To generate a slug from a feature title, run (by file path, not `-m`):

```bash
python telescoping-sdd/scripts/spec_dirname.py slugify "My Feature Title"
```

**Migration (pre-1.7.0 → 1.7.0):** rename any bare `specs/F<n>/` directory to `specs/F<n>-<slug>/`. Renaming a spec directory is **hash-safe** — it never invalidates any existing approval or content hash. Lowercase `specs/f<digits>-…/` directories are already valid standalone slugs (the bound form is uppercase-`F` only) and need **no** migration.

### When to use this — and when a lighter path fits

The full four-phase loop is calibrated for **substantial, long-lived features** — code other features build against, specs that will be re-entered and amended. For a **small one-off feature, a throwaway prototype, or an exploratory spike**, that's disproportionate. If the user says the work is small/throwaway and asks for a lighter review, run the panel in **lightweight mode** (one pass, dispose, self-check, archive, exit — no convergence loop, no strict-bar/halt/cross-check). Default stays the full loop; lightweight mode is opt-in only. See `references/panel-review.md` § "Lightweight Mode (single-pass panel)".

### Path placeholders

The commands in this skill reference two distinct script roots:

* `<script-path>` resolves to the skill's own `scripts/` directory — under the plugin install root at `skills/spec-driven-dev/scripts/` (e.g., `~/.claude/plugins/cache/<marketplace>/telescoping-sdd/<version>/skills/spec-driven-dev/scripts/` for marketplace installs, or `<plugin-dir>/skills/spec-driven-dev/scripts/` for `--plugin-dir` dev mode).
* `<shared-script-path>` resolves to `telescoping-sdd/scripts/` — the plugin-wide shared scripts directory, sibling of `telescoping-sdd/skills/`. `<shared-script-path>/archive_pass.py` is the cross-skill panel-archiving tool shared with `project-blueprint`.

Running `validate_spec.py` is **optional for fresh artifacts** (the panel-review step already catches most issues the validator would) **but required when entering or resuming a workflow with existing approved artifacts** — it detects post-approval edits made outside the current session that would otherwise leave the chain silently out of sync. (Edits Claude makes mid-session don't need the validator to detect them — Claude already knows it edited the file. Both flows feed into the same handling — see "Re-Approval After Edits.") Running `archive_pass.py` is **required** between panel passes — it maintains `### Trajectory`, promotes `### Sealed dispositions`, and clears `### Latest pass detail` so the next pass starts cleanly.

### Phase shape (Phases 1–3)

Phases 1–3 delegate document drafting to a specialist subagent via the Agent tool. The agent writes its draft to the artifact's target path using the `Write` tool and self-reviews it (up to 5 passes — fixing issues it can resolve, flagging others with `[TBD]`), returning a manifest. You (the calling Claude) then `Read` the artifact from disk, confirm it is non-empty, perform your own review, run any cross-document consistency check, then invoke a three-persona **panel review** to stress-test the artifact for blind-spot and quality issues. The panel runs a review loop (auto-fix or ask the user, up to 5 passes). When the panel exits — i.e., a pass returns zero HIGH-severity concerns — run validation and present the document to the user. The agent catches internal issues; the panel catches blind-spot and quality issues; you catch cross-document and conversation-context issues.

Phase 4 (implementation) is executed directly by the calling Claude with no delegation, since the TDD cycle benefits from interactive visibility and mid-task course correction; there is no panel review at Phase 4.

**The shared panel-review machinery — the loop, synthesizer self-check, halt-and-rescope exit, strict-bar convergence mode, format contract for `## Panel Review`, and when to skip the panel — lives in `references/panel-review.md`. Read that reference before running any phase's panel.**

## Language / Architecture Detection

Before starting any phase, detect the project's stack:

- **Java** — Look for `pom.xml`, `build.gradle`, `build.gradle.kts`, or `src/main/java/` directory
- **Python** — Look for `pyproject.toml`, `setup.py`, `setup.cfg`, or `requirements.txt`
- **Generic (architecture-neutral)** — Anything else: infrastructure / IaC (Terraform, Ansible, Docker Compose, nginx config), static sites (HTML/CSS), frontend projects without a recognized Python/Java marker, Claude-skill authoring, etc.

**Resolution order (the validator and you must agree — use the same precedence):**

1. **Explicit override** — an explicit per-run choice (the validator's `--language` flag; for you, an instruction from the user this session) wins over everything below.
2. **Persisted store** — otherwise, if `.sdd/architecture.json` exists at the project root, it is authoritative. Read it and use its `language`; do not re-derive. (The validator does the same: persisted config wins over auto-detection.)
3. **Detect** — otherwise detect from markers (above). If both Python and Java markers are present, ask the user which to use. **If neither is detected, use `generic` — do NOT default to Python.**

`generic` is the architecture-neutral profile: the full structural skeleton (required sections, GIVEN/WHEN/THEN acceptance criteria, `[CFC-N]` tags, the hash block) still applies, but the two language-specific advisory checks (type annotations, test-function names) are skipped because they don't fit a non-code or non-Python/Java deliverable.

**Persist the decision once.** As soon as the stack is known (especially after resolving a Python-vs-Java ambiguity, or confirming `generic` for an infra / static-site / skill project), persist it so it stops being re-derived and can't drift between runs:

```bash
python <script-path>/validate_spec.py specs/F<n>-<slug>/ --set-language {python|java|generic}
```

This writes `.sdd/architecture.json` (the declare-once store) at the project root and exits. It touches no content hash and is independent of `--approve`, so it never interacts with the CFC cascade. It is the single explicit write path — nothing writes this file silently. Commit the file; it is project state, like other config. Thereafter every validate run resolves the stack from it (`Language: … (from config)`), and you should too. State the resolved stack to the user at the start of the first phase you enter.

> **Blueprint→SDD seam.** When a project has a `blueprint/`, the stack is declared there once via the `**Architecture token:**` field in `ARCHITECTURE.md § Technology Choices` and persisted with `validate_blueprint.py blueprint/ --write-arch-config`, which writes the same `.sdd/architecture.json` this skill reads. So a blueprint-driven project arrives here with the store already populated (`source: blueprint`) — just resolve from it. For a standalone SDD project with no blueprint, populate the store SDD-side with `--set-language` as above.

## Phase 1: Specify

Output: `specs/F<n>-<slug>/spec.md`. Drafted by `telescoping-sdd:feature-spec-analyst`.

Required sections: Objective, Requirements (with per-requirement **Acceptance Criteria** sub-labels), Project Structure, Boundaries, Success Criteria.

Panelists: `telescoping-sdd:user-advocate`, `telescoping-sdd:devils-advocate`, `telescoping-sdd:pragmatist`.

**Read `references/phase-specify.md` for the full Phase 1 workflow — drafting, self-review, panel, validation, and approval.**

## Phase 2: Design

Output: `specs/F<n>-<slug>/design.md`. Drafted by `telescoping-sdd:feature-architecture-analyst`. Requires approved `spec.md`.

Required sections: Goals and Non-Goals, Architecture Decisions, Component Design, Data Models, Interfaces, Error Handling, Testing Strategy, File Structure, Dependencies, Integration Points, Risks, Implementation Sequence.

Panelists: `telescoping-sdd:architect`, `telescoping-sdd:testability-reviewer`, `telescoping-sdd:security-reviewer`.

**Read `references/phase-design.md` for the full Phase 2 workflow — drafting, self-review, spec-design consistency check, panel, validation, and approval.**

## Phase 3: Tasks

Output: `specs/F<n>-<slug>/tasks.md`. Drafted by `telescoping-sdd:feature-task-analyst`. Requires approved `spec.md` and `design.md`.

Required per-task fields: Task ID, Requirement, Description, Files, Dependencies, Parallel, Acceptance Criteria, Verification (the validator FAILs if any is missing from a task), plus Tests (advisory — the validator warns rather than fails, since specific test names are often refined during implementation).

Panelists: `telescoping-sdd:delivery-manager`, `telescoping-sdd:critic`, `telescoping-sdd:simplifier`.

**Read `references/phase-tasks.md` for the full Phase 3 workflow — drafting, sizing rules, self-review, spec-design-tasks consistency check, panel, validation, and approval. This is the last artifact phase; concerns cannot be deferred forward.**

## Phase 4: Implement

Execute tasks sequentially following this cycle for each task:

1. Read the task from tasks.md
2. Establish the check first: for a stack with a test harness, write the tests that encode the acceptance criteria (they fail initially); for a `generic`/architecture-neutral stack with no harness, write down the task's concrete Verification check (the runnable assertion, manual step, or review step) before doing the work
3. Do the work to satisfy the acceptance criteria — implement the code (and make the tests pass), or produce the config / page / infra / doc / skill artifact
4. Run the check: the full test suite for a code stack (watch for regressions); the task's Verification command or the stated manual/review check for a `generic` stack
5. Update tasks.md immediately — do both of the following before moving to the next task:
   - Change the task's Status in the Summary table from `Not Started` to `Done`
   - Check off the task's checkbox in the heading (e.g., `### - [ ] T1:` becomes `### - [x] T1:`)

### Stack Conventions

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

**Generic (architecture-neutral — infra, static sites, config, docs, skill authoring)**
- There is usually no unit-test harness; verify with the stack's real tooling instead of inventing one
- Use each task's Verification check: a runnable assertion (`nginx -t`, `terraform validate`, `docker compose config`, `grep`/`test -f`), a reproducible manual step, or a visual/review check
- Follow existing project conventions and any linters/validators the stack provides (e.g. `hadolint`, `ansible-lint`, an HTML/markdown linter, `claude plugin validate`)
- "Run the full test suite" means "re-run the relevant checks and confirm nothing previously passing now fails"

After completing all tasks, do a final check:
- All verification passes — the full test suite for a code stack; every task's Verification check (and any stack linters/validators) for a `generic` stack
- All acceptance criteria from spec.md are met
- All tasks in tasks.md are checked off and all summary table statuses are `Done` (or `Skipped` for invalidated tasks)
- **Re-stamp `tasks.md` once**: first run `python <script-path>/validate_spec.py specs/F<n>-<slug>/` and confirm structural validity (no `[TBD]`, no `TODO`/`FIXME` leaked into task descriptions, all required sections present, `## Panel Review` populated). If any structural check fails, halt and fix before re-stamping — re-stamping a structurally broken `tasks.md` would silently approve known-bad content. Once structural checks pass, run `python <script-path>/validate_spec.py specs/F<n>-<slug>/ --approve tasks`. This is the completion re-stamp called out in `references/hash-and-cascade.md` (intro paragraph: Phase 4 cadence) — it refreshes the hash that's been stale since the first tick. No cascade follows (tasks.md has no downstream).

<!-- The two sections below mention a Phase 4 carve-out / Phase 4 exception that is intentional asymmetry vs project-blueprint/SKILL.md. spec-driven-dev has a Phase 4 (Implement) where tasks.md is edited continuously; project-blueprint has no analogous phase. Do not "sync" these pointer paragraphs by removing the Phase 4 references — the full asymmetry rationale lives in references/hash-and-cascade.md (intro paragraph). -->

## Entering the Workflow Mid-Stream

If users already have artifacts (spec.md, design.md, and/or tasks.md), validate them before doing any phase work. The procedure — structural-validity check, auto-restamp on stale hashes (which then routes through the upstream panel re-review step before cascading, exactly as in "Re-Approval After Edits"), halt-and-ask on unchecked boxes, the Phase 4 carve-out for mid-Phase-4 resumption (task-tick edits suppress both the upstream panel re-review and the cascade), then routing to the right phase — lives in **`references/hash-and-cascade.md` § "Entering the Workflow Mid-Stream"**. Read it before resuming. A stale-hash mid-stream entry on an artifact OTHER than a task-ticked `tasks.md` is a top-level entry of the re-approval flow; the upstream panel re-review step fires unless the diff is visibly trivial.

## Re-Approval After Edits

When an approved document is edited (by Claude at the user's request, by the user directly, or via a `git` operation), the response is automatic: (1) verify structural validity, (2) re-stamp the edited document silently, (3) **run the upstream panel re-review step** to decide whether to stress-test the edited document itself before its changes propagate, then (4) run the consistency-check cascade against approved downstream artifacts. **Do not prompt for permission to re-stamp** — the user has already authorized the edit by making it. Step 3 (upstream panel re-review) is **mandatory unless the diff is visibly trivial**: it fires on every top-level entry, and only visibly-trivial edits (whitespace / punctuation / comment-only, per the four-criterion test) skip silently — every other edit produces a recommendation+ask. Going straight from re-stamp to cascade without running step 3 is a flow violation. **Phase 4 (Implement) has an exception**: normal task-tick edits to `tasks.md` do not trigger this flow (re-stamping after every tick would be noise) — see the Phase 4 cadence in the intro of `references/hash-and-cascade.md`. The full flow — structural-validity precondition, source-tag determination, four-criterion triviality test, lean-yes/lean-no recommendation prompts, halt-on-substantive-divergence behavior, resolution paths (revise or accept), and the downstream optional panel re-review recommendation — lives in **`references/hash-and-cascade.md` § "Re-Approval After Edits"**.

> **WARNING:** Re-stamping is silent; **The panel-review DECISION is not.** The "do not prompt to re-stamp" momentum of steps 1–2 must NOT carry past step 3: going straight from re-stamp → cascade without running the upstream panel re-review on a non-trivial edit is a **flow violation**. The git-ignored `.sdd/pending-review.json` marker turns a skipped step 3 into a later validation FAIL, and `--decline-pending` / `--task-tick` are **doctrine-classified, auditable acts** (a user-surfaced decline; the Phase-4 task-tick carve-out) — never agent convenience skips to dodge a panel it judged "unnecessary".

## See also

- `references/hash-and-cascade.md` — full hash-handling flow: mid-stream entry, re-approval after edits, the cascade, the halt-on-substantive-divergence rule, the optional panel re-review recommendation, and the Phase 4 (Implement) cadence. Read this whenever an approved document changes.
- `references/panel-review.md` — the shared panel-review loop, synthesizer self-check, halt-and-rescope exit, strict-bar convergence mode, format contract, and panel-skip rules. Read before running any phase's panel. See its `## Autonomy Boundary` for what Claude runs autonomously vs. the real gates (loop continuation is not a user decision).
- `references/strict-bar-prompts.md` — per-phase prompt additions for strict-bar passes. Loaded only when a strict-bar pass runs.
- `references/phase-specify.md`, `references/phase-design.md`, `references/phase-tasks.md` — full per-phase workflows.
- `references/workflow-overview.md` — quick-reference diagram of the full process.
- `references/spec-template-python.md`, `references/spec-template-java.md` — document templates the spec drafting agent must follow exactly. Equivalent `design-template-*` and `tasks-template-*` files exist for Phases 2 and 3.
- `references/examples.md` — end-to-end walkthroughs for common entry points (new spec, resuming, tasks-only, implementation).
- `references/troubleshooting.md` — failure modes and recovery (validation failures, requirement drift, panel non-convergence, etc.).
