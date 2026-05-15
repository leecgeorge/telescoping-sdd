# Project Blueprint — Workflow Overview

## The Three Phases

```
  SCOPE             ARCHITECTURE       IMPLEMENTATION PLAN
 ┌──────────┐     ┌────────────────┐    ┌──────────┐
 │ SCOPE.md │────>│ARCHITECTURE.md │───>│ PLAN.md  │───> Feature Development
 └──────────┘     └────────────────┘    └──────────┘     (spec-driven-dev)
      │                  │                   │
   REVIEW             REVIEW              REVIEW
   GATE               GATE                GATE
```

## Phase Summary

| Phase | Input | Output | Drafted By | Key Question |
|-------|-------|--------|------------|-------------|
| Scope | User's project idea | `SCOPE.md` | `project-spec-analyst` subagent | **What** are we building and why? |
| Architecture | Approved scope | `ARCHITECTURE.md` | `project-architecture-analyst` subagent | **How** does it fit together? |
| Implementation Plan | Approved architecture | `PLAN.md` | `project-plan-analyst` subagent | **What** features, in what order? |

Each phase delegates document drafting to the corresponding subagent via the Agent tool. The agent self-reviews its draft before returning. The calling Claude then performs its own review, runs cross-document consistency checks, validation, and approval gates.

## File Layout

```
project-root/
└── blueprint/
    ├── SCOPE.md          # Phase 1 output
    ├── ARCHITECTURE.md   # Phase 2 output
    └── PLAN.md           # Phase 3 output
```

## Review Gates

Between each phase, stop and ask the user:

1. After Scope: "Here's the scope. Does this capture the project you want to build?"
2. After Architecture: "Here's the architecture. Does this structure make sense?"
3. After Implementation Plan: "Here's the plan. Is this the right set of features and build order?"

## Validation Before Approval

Each document must pass validation before approval:

- All required sections present
- No `[TBD]`, `TODO`, `FIXME`, `???` markers
- No unchecked open questions (`- [ ] Q1:`)
- Previous phase approved (for Architecture and Plan)

## Quick Commands

| User Says | Start At |
|-----------|----------|
| "Plan a new project" | Phase 1 — Scope |
| "Create a blueprint for X" | Phase 1 — Scope |
| "Design the architecture" | Phase 2 — Architecture (needs scope) |
| "Create an implementation plan" | Phase 3 — Plan (needs architecture) |
| "What features should I build first?" | Phase 3 — Plan (needs architecture) |

## Handoff to Feature Development

Once the blueprint is complete:

```
PLAN.md Feature List          spec-driven-dev
┌─────────────────────┐      ┌─────────────────────┐
│ F1: User Auth       │─────>│ specs/user-auth/     │
│ F2: Data Models     │─────>│ specs/data-models/   │
│ F3: API Endpoints   │─────>│ specs/api-endpoints/  │
│ F4: Dashboard       │─────>│ specs/dashboard/      │
└─────────────────────┘      └─────────────────────┘
```

Each feature becomes a candidate for `/spec-driven-dev`, following the implementation order from PLAN.md.

## Principles

- **Scope before structure.** Define what you're building before deciding how.
- **Architecture before features.** Understand the system before breaking it into parts.
- **Decisions are explicit.** Every choice is documented with rationale.
- **Risks surface early.** Identify what could go wrong before committing to a build order.
- **Features feed into specs.** The blueprint's output is the input for spec-driven development.
- **Human decides.** Claude proposes, the user approves.
