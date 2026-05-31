<!--
SHARED REFERENCE — keep in sync with the project-blueprint copy at
skills/project-blueprint/references/workflow-overview.md. Edits to shared content must be mirrored in BOTH copies.

Intentional asymmetries vs the sibling (do NOT "sync" these away):
- Phase model is skill-specific: blueprint has 3 phases (Scope/Architecture/Plan); spec-driven-dev has 4 (Specify/Design/Tasks/Implement) — diagram, headings, and phase count differ by design.
- spec-driven-dev's Phase 4 (Implement) is SDD-only: extra Phase-Summary row, "Phase 4 executed directly" note, a 4th review gate, and the "Implement task" quick command have no blueprint counterpart.
- Terminal Phase-3 artifact differs: PLAN.md (blueprint) vs tasks.md (spec-driven-dev), along with the File Layout tree (flat blueprint/ vs specs/feature-name/).
- Blueprint-only doctrine sections (Handoff to Feature Development, Bound-Spec Immutability, Closed-Feature-Row Immutability) are PLAN/CFC-producer rules, intentionally absent from spec-driven-dev (the consumer).
Otherwise the copies differ only cosmetically (phase names, filenames, example feature names, quick-command phrasing, Principles wording).
-->

# Spec-Driven Development — Workflow Overview

## The Four Phases

```
  SPECIFY          DESIGN          TASKS           IMPLEMENT
 ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────────┐
 │ spec.md │──>│design.md│──>│ tasks.md│──>│ Code + Tests│
 └─────────┘    └─────────┘    └─────────┘    └─────────────┘
      │              │              │               │
   REVIEW         REVIEW         REVIEW          REVIEW
   GATE           GATE           GATE            GATE
```

## Phase Summary

| Phase | Input | Output | Drafted By | Key Question |
|-------|-------|--------|------------|-------------|
| Specify | User requirements | `spec.md` | `feature-spec-analyst` subagent | **What** are we building and why? |
| Design | Approved spec | `design.md` | `feature-architecture-analyst` subagent | **How** will we build it? |
| Tasks | Approved design | `tasks.md` | `feature-task-analyst` subagent | **What steps** in what order? |
| Implement | Approved tasks | Working code + tests | Calling Claude (no delegation) | **Does it work** as specified? |

Phases 1–3 delegate document drafting to the corresponding subagent via the Agent tool. The agent self-reviews its draft before returning. The calling Claude then performs its own review, runs cross-document consistency checks, validation, and approval gates. Phase 4 is executed directly by the calling Claude.

## File Layout

```
project-root/
└── specs/
    └── feature-name/
        ├── spec.md      # Phase 1 output
        ├── design.md    # Phase 2 output
        └── tasks.md     # Phase 3 output
```

## Review Gates

Between each phase, stop and ask the user:

1. After Specify: "Here's the spec. Does this capture what you want to build?"
2. After Design: "Here's the design. Does this architecture make sense?"
3. After Tasks: "Here are the tasks. Is this the right breakdown and order?"
4. After each task in Implement: "Task T[n] is complete. Ready for the next one?"

## Validation Before Approval

Each document must pass validation before approval:

- All required sections present
- No `[TBD]`, `TODO`, `FIXME`, `???` markers
- No unchecked open questions (`- [ ] Q1:`)
- Previous phase approved (for Design and Tasks)

## Quick Commands

| User Says | Start At |
|-----------|----------|
| "Create a spec for X" | Phase 1 — Specify |
| "Design this feature" | Phase 2 — Design (needs spec) |
| "Break this into tasks" | Phase 3 — Tasks (needs design) |
| "Implement task T1" | Phase 4 — Implement (needs tasks) |
| "Start SDD for X" | Phase 1 — Specify |

## Principles

- **Specs are the source of truth.** Code follows specs, not the other way around.
- **Changes flow forward.** If requirements change, update spec.md first, then cascade to design and tasks.
- **Tasks are atomic.** Each task should be independently verifiable.
- **Tests come first.** Write tests before implementation (TDD).
- **Human decides.** Claude proposes, the user approves.
