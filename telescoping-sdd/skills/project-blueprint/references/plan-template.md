# Implementation Plan Template

Use this template when creating `PLAN.md` after an approved architecture.

---

# Implementation Plan: [Project Name]

**Scope:** `blueprint/SCOPE.md`
**Architecture:** `blueprint/ARCHITECTURE.md`

## Feature Breakdown

### F1: [Feature Name]

- **Description:** [What this feature does in 2-3 sentences]
- **Component:** [Which architecture component this belongs to]
- **Acceptance Criteria:**
  - [Criterion 1 — observable behavior when this feature is complete]
  - [Criterion 2]
  - [Criterion 3]

### F2: [Feature Name]

- **Description:** [What this feature does]
- **Component:** [Which architecture component]
- **Acceptance Criteria:**
  - [Criterion 1]
  - [Criterion 2]

### F3: [Feature Name]

- **Description:** [What this feature does]
- **Component:** [Which architecture component]
- **Acceptance Criteria:**
  - [Criterion 1]
  - [Criterion 2]

### F4: [Feature Name]

- **Description:** [What this feature does]
- **Component:** [Which architecture component]
- **Acceptance Criteria:**
  - [Criterion 1]
  - [Criterion 2]

## MVP Definition

**MVP includes:** F1, F2, F3
**Post-MVP:** F4, F5

| Phase | Features | Goal |
|-------|----------|------|
| MVP | F1, F2, F3 | [What MVP delivers — the minimum viable product] |
| Phase 2 | F4, F5 | [What Phase 2 adds] |
| Phase 3 | F6, F7 | [What Phase 3 adds] |

## Feature Dependencies

```
[ASCII dependency graph]

Example:
F1 ──> F3 ──> F5
  \         /
   └> F2 ─┘
      │
      └──> F4 ──> F6
```

| Feature | Depends On | Reason |
|---------|-----------|--------|
| F1 | None | [Foundation — no dependencies] |
| F2 | F1 | [Why F2 needs F1 to be complete] |
| F3 | F1 | [Why F3 needs F1] |
| F4 | F2 | [Why F4 needs F2] |
| F5 | F2, F3 | [Why F5 needs both] |

## Implementation Order

| Order | Feature | Rationale |
|-------|---------|-----------|
| 1 | F1: [Name] | [Why this goes first — e.g., foundational, unblocks others, reduces risk] |
| 2 | F2: [Name] | [Why this is next] |
| 3 | F3: [Name] | [Can be parallel with F2 if independent, or why it follows] |
| 4 | F4: [Name] | [Why this order] |
| 5 | F5: [Name] | [Why this is last] |

## Milestones

### Milestone 1: [Name] — [Target Date or Relative Timing]

- [ ] F1: [Feature Name]
- [ ] F2: [Feature Name]
- **Deliverable:** [What is usable/demonstrable at this point]

### Milestone 2: [Name] — [Target Date or Relative Timing]

- [ ] F3: [Feature Name]
- [ ] F4: [Feature Name]
- **Deliverable:** [What is usable/demonstrable at this point]

### Milestone 3: [Name] — [Target Date or Relative Timing]

- [ ] F5: [Feature Name]
- **Deliverable:** [What is usable/demonstrable at this point]

## Open Questions

> All questions must be resolved before proceeding to feature development.

- [ ] Q1: [Question about feature scope, ordering, or dependencies]
  - **Resolution:** [To be filled when answered]
- [ ] Q2: [Another question]
  - **Resolution:** [To be filled when answered]

## Panel Review

<!-- Populated by the skill across panel-review passes. archive_pass.py manages
     Trajectory and Sealed dispositions automatically; the synthesizer populates
     Latest pass detail per pass.

     This is the last blueprint phase; concerns cannot be deferred forward.
     Disposition vocabulary: Addressed / Sealed / Accepted as risk /
     User input needed / Halt and re-scope. Sealed and Accepted as risk must
     include "Defense: <reason>" in Notes. Severity tags in Latest pass detail
     are bracketed: [HIGH] / [MED] / [LOW], optionally [REGRESSION].

     See SKILL.md "Panel Review section format" for the normative spec. -->

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|

### Sealed dispositions

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [ ] Approved to proceed to feature development
- **Content Hash:** `pending`
