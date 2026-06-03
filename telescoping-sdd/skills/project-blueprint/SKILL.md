---
name: project-blueprint
description: Guides project planning from scope through architecture to implementation plan. Use when user says "plan a project", "create a blueprint", "project blueprint", "scope a project", "architect a project", or "plan a new project". Walks through three phases — Scope, Architecture, Implementation Plan — with human review gates between each phase.
metadata:
  status: stable
---

# Project Blueprint

> **Status: Stable** — ready for day-to-day use.

A structured workflow that produces project planning documents before any feature development begins. Defines what the project is, how it's structured, and what order to build it in.

## Overview

Every project blueprint follows three phases. **Always get user approval before moving to the next phase.**

1. **Scope** — Define what we're building and why (`SCOPE.md`) — drafted by the `telescoping-sdd:project-spec-analyst` agent
2. **Architecture** — Design how it fits together (`ARCHITECTURE.md`) — drafted by the `telescoping-sdd:project-architecture-analyst` agent
3. **Implementation Plan** — Break it into features and sequence them (`PLAN.md`) — drafted by the `telescoping-sdd:project-plan-analyst` agent
4. **Business Brief** — Optional. After PLAN approval, offer to render the three approved documents as self-contained HTML for stakeholder consumption.

All blueprint documents live in `blueprint/` at the project root.

Read `references/workflow-overview.md` for a quick-reference diagram of the full process.

### When to use this — and when a lighter path fits

The full three-phase loop is calibrated for **substantial, long-lived, multi-feature projects** — a blueprint that spawns many features and gets re-entered and amended. For a **small single-component project, a throwaway prototype, or an exploratory spike**, that's disproportionate. If the user says the work is small/throwaway and asks for a lighter review, run the panel in **lightweight mode** (one pass, dispose, self-check, archive, exit — no convergence loop, no strict-bar/halt/cross-check). Default stays the full loop; lightweight mode is opt-in only. See `references/panel-review.md` § "Lightweight Mode (single-pass panel)".

### Path placeholders

The commands in this skill reference two distinct script roots:

* `<script-path>` resolves to the skill's own `scripts/` directory — under the plugin install root at `skills/project-blueprint/scripts/` (e.g., `~/.claude/plugins/cache/<marketplace>/telescoping-sdd/<version>/skills/project-blueprint/scripts/` for marketplace installs, or `<plugin-dir>/skills/project-blueprint/scripts/` for `--plugin-dir` dev mode).
* `<shared-script-path>` resolves to `telescoping-sdd/scripts/` — the plugin-wide shared scripts directory, sibling of `telescoping-sdd/skills/`. `<shared-script-path>/archive_pass.py` is the cross-skill panel-archiving tool shared with `spec-driven-dev`.

Running `validate_blueprint.py` is **optional for fresh artifacts** (the panel-review step already catches most issues the validator would) **but required when entering or resuming a workflow with existing approved artifacts** — it detects post-approval edits made outside the current session that would otherwise leave the chain silently out of sync. (Edits Claude makes mid-session don't need the validator to detect them — Claude already knows it edited the file. Both flows feed into the same handling — see "Re-Approval After Edits.") Running `archive_pass.py` is **required** between panel passes — it maintains `### Trajectory`, promotes `### Sealed dispositions`, and clears `### Latest pass detail` so the next pass starts cleanly.

### Phase shape (same every phase)

Each phase delegates document drafting to a specialist subagent via the Agent tool. The agent produces a draft and self-reviews it before returning (up to 5 passes — fixing issues it can resolve, flagging others with `[TBD]`). After the agent returns, you (the calling Claude) perform your own review, run any cross-document consistency check, then invoke a three-persona **panel review** to stress-test the artifact for blind-spot and quality issues. The panel runs a review loop (auto-fix or ask the user, up to 5 passes). When the panel exits — i.e., a pass returns zero HIGH-severity concerns — run validation and present the document to the user. The agent catches internal issues; the panel catches blind-spot and quality issues; you catch cross-document and conversation-context issues.

**The shared panel-review machinery — the loop, synthesizer self-check, halt-and-rescope exit, strict-bar convergence mode, format contract for `## Panel Review`, and when to skip the panel — lives in `references/panel-review.md`. Read that reference before running any phase's panel.**

## Phase 1: Scope

Output: `blueprint/SCOPE.md`. Drafted by `telescoping-sdd:project-spec-analyst`.

Required sections: Problem Statement, Target Users, Goals, Non-Goals, Constraints, Success Criteria.

Panelists: `telescoping-sdd:user-advocate`, `telescoping-sdd:devils-advocate`, `telescoping-sdd:pragmatist`.

**Read `references/phase-scope.md` for the full Phase 1 workflow — drafting, self-review, panel, validation, and approval.**

## Phase 2: Architecture

Output: `blueprint/ARCHITECTURE.md`. Drafted by `telescoping-sdd:project-architecture-analyst`. Requires approved `SCOPE.md`.

Required sections: System Overview, Components, Component Interactions, Technology Choices, Data Architecture, External Dependencies, Risks.

Panelists: `telescoping-sdd:architect`, `telescoping-sdd:ops-reviewer`, `telescoping-sdd:security-reviewer`.

**Read `references/phase-architecture.md` for the full Phase 2 workflow — drafting, self-review, scope-architecture consistency check, panel, validation, and approval.**

## Phase 3: Implementation Plan

Output: `blueprint/PLAN.md`. Drafted by `telescoping-sdd:project-plan-analyst`. Requires approved `SCOPE.md` and `ARCHITECTURE.md`.

Required sections: Feature Breakdown, MVP Definition, Feature Dependencies, Implementation Order, Milestones.

Panelists: `telescoping-sdd:delivery-manager`, `telescoping-sdd:critic`, `telescoping-sdd:simplifier`.

**Read `references/phase-plan.md` for the full Phase 3 workflow — drafting, self-review, scope-architecture-plan consistency check, panel, validation, and approval. This is the last blueprint phase; concerns cannot be deferred forward.**

## Phase 4: Business Brief

Output: `blueprint/business-brief/scope.html`, `architecture.html`, `plan.html`. Requires approved `SCOPE.md`, `ARCHITECTURE.md`, AND `PLAN.md`.

**Optional and re-runnable.** Phase 4 renders the three approved blueprint documents as self-contained HTML for business-stakeholder consumption. After the user approves PLAN.md, present a clear yes/no prompt to the user: `Generate a Business Brief for stakeholders? [y/n]`. If the user answers `y`/`yes` (case-insensitive, whitespace tolerated), invoke the script below and report the three output paths. If the user answers `n`/`no`, exit Phase 4 gracefully and confirm the brief was skipped. For any other response, re-prompt.

If all three phase artifacts (SCOPE.md, ARCHITECTURE.md, PLAN.md) are already approved on entry, offer the Phase 4 prompt directly rather than re-entering Phase 1.

**First-time setup.** Phase 4 needs two pip packages — `markdown>=3.4` and `bleach>=6.0,<7.0` — that the rest of the skill does not. Install them once into the Python environment that will invoke the script:

```bash
pip install -r <script-path>/requirements.txt
```

Invocation:

```bash
python <script-path>/render_business_brief.py blueprint/
# Optional overrides:
python <script-path>/render_business_brief.py blueprint/ --project-name "Acme Q3 Initiative"
python <script-path>/render_business_brief.py blueprint/ --dry-run          # preview paths, write nothing
python <script-path>/render_business_brief.py blueprint/ --logo /path/to/logo.png  # custom branding
```

The script filters workflow-internal content (YAML frontmatter, Panel Review, Approval blocks, inline tags like `[SEAL-NN]`, content-hash stamps), renders the remaining markdown to clean HTML with inline CSS, embeds the Neon Ghost brand logo as a base64 data URL in each file's footer, and writes three self-contained files to `blueprint/business-brief/`. The output files are email-able / SharePoint-droppable / offline-openable — no external CSS, JS, fonts, or images.

**Read `references/phase-business-brief.md` for the full Phase 4 workflow — the prompt, re-running behaviour, the upstream approval guard, and the brand-logo asset.**

## Validation Rules

Before any document can be approved, it must pass validation:

1. **All required sections present** — Every section listed for the phase must exist in the document, including `## Panel Review`
2. **No unresolved items** — No `[TBD]`, `TODO`, `FIXME`, `???`, unchecked open questions (`- [ ] Q1:`), or panel concerns still in `User input needed` disposition
3. **No empty sections** — Each section must contain substantive content (including `## Panel Review` — populated `### Trajectory`, plus any `### Sealed dispositions` and `### Latest pass detail` rows produced during panel cycles)
4. **Previous phase approved** — Architecture requires approved scope; Plan requires approved architecture
5. **Hash integrity** — If a document is edited after approval, the hash is invalidated

## Handoff to Feature Development

Once the implementation plan is approved, each feature (F1, F2, etc.) in PLAN.md is ready to be developed using the spec-driven-dev workflow. Follow the implementation order defined in PLAN.md:

1. Pick the next feature from the implementation order
2. Use `/spec-driven-dev` to create a spec, plan, and tasks for that feature
3. Implement the feature
4. Move to the next feature

**Carry the declared stack across the seam (once, before the first feature).** `ARCHITECTURE.md` declares the project's stack via its `**Architecture token:**` field (`python` / `java` / `generic`). Persist it so spec-driven-dev resolves it instead of re-detecting the language per feature:

```bash
python <script-path>/validate_blueprint.py blueprint/ --write-arch-config
```

This reads the token and writes `<project-root>/.sdd/architecture.json` (the declare-once store spec-driven-dev reads). It is a standalone step — it touches no content hash and is independent of `--approve`, so it never interacts with the PLAN approval or the CFC cascade. Commit the file. Re-run it only if the token changes.

The blueprint documents remain the source of truth for project direction. If scope changes, update SCOPE.md first and cascade changes through ARCHITECTURE.md and PLAN.md.

## Entering the Workflow Mid-Stream

If users already have artifacts (SCOPE.md, ARCHITECTURE.md, and/or PLAN.md), validate them before doing any phase work. The procedure — structural-validity check, auto-restamp on stale hashes (which then routes through the upstream panel re-review step before cascading, exactly as in "Re-Approval After Edits"), halt-and-ask on unchecked boxes, then routing to the right phase — lives in **`references/hash-and-cascade.md` § "Entering the Workflow Mid-Stream"**. Read it before resuming. A stale-hash mid-stream entry is a top-level entry of the re-approval flow; the upstream panel re-review step fires unless the diff is visibly trivial.

## Re-Approval After Edits

When an approved document is edited (by Claude at the user's request, by the user directly, or via a `git` operation), the response is automatic: (1) verify structural validity, (2) re-stamp the edited document silently, (3) **run the upstream panel re-review step** to decide whether to stress-test the edited document itself before its changes propagate, then (4) run the consistency-check cascade against approved downstream artifacts. **Do not prompt for permission to re-stamp** — the user has already authorized the edit by making it. Step 3 (upstream panel re-review) is **mandatory unless the diff is visibly trivial**: it fires on every top-level entry, and only visibly-trivial edits (whitespace / punctuation / comment-only, per the four-criterion test) skip silently — every other edit produces a recommendation+ask. Going straight from re-stamp to cascade without running step 3 is a flow violation. The full flow — structural-validity precondition, source-tag determination, four-criterion triviality test, lean-yes/lean-no recommendation prompts, halt-on-substantive-divergence behavior, resolution paths (revise or accept), and the downstream optional panel re-review recommendation — lives in **`references/hash-and-cascade.md` § "Re-Approval After Edits"**.

> **WARNING:** Re-stamping is silent; **The panel-review DECISION is not.** The "do not prompt to re-stamp" momentum of steps 1–2 must NOT carry past step 3: going straight from re-stamp → cascade without running the upstream panel re-review on a non-trivial edit is a **flow violation**. The git-ignored `.sdd/pending-review.json` marker turns a skipped step 3 into a later validation FAIL, and `--decline-pending` is a **doctrine-classified, auditable act** (a user-surfaced decline) — never an agent convenience skip to dodge a panel it judged "unnecessary". (project-blueprint has no Phase-4 task-tick carve-out.)

## See also

- `references/hash-and-cascade.md` — full hash-handling flow: mid-stream entry, re-approval after edits, the cascade, the halt-on-substantive-divergence rule, and the optional panel re-review recommendation. Read this whenever an approved document changes.
- `references/panel-review.md` — the shared panel-review loop, synthesizer self-check, halt-and-rescope exit, strict-bar convergence mode, format contract, and panel-skip rules. Read before running any phase's panel. See its `## Autonomy Boundary` for what Claude runs autonomously vs. the real gates (loop continuation is not a user decision).
- `references/strict-bar-prompts.md` — per-phase prompt additions for strict-bar passes. Loaded only when a strict-bar pass runs.
- `references/phase-scope.md`, `references/phase-architecture.md`, `references/phase-plan.md` — full per-phase workflows.
- `references/phase-business-brief.md` — optional Phase 4 workflow: render the three approved blueprint documents as self-contained HTML for stakeholders.
- `references/workflow-overview.md` — quick-reference diagram of the full process.
- `references/scope-template.md`, `references/architecture-template.md`, `references/plan-template.md` — document templates the drafting agents must follow exactly.
- `references/examples.md` — end-to-end walkthroughs for common entry points (new project, resuming, plan-only, blueprint complete).
- `references/troubleshooting.md` — failure modes and recovery (validation failures, scope drift, panel non-convergence, etc.).
