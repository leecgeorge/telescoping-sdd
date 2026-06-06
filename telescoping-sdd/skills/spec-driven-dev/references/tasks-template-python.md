# Tasks Template (Python)

Use this template when creating `tasks.md` for a Python project after an approved design.

---

# Tasks: [Feature Name]

**Spec:** `specs/[feature-name]/spec.md`
**Design:** `specs/[feature-name]/design.md`

## Summary

| Task | Description | Requirement | Dependencies | Parallel | Status |
|------|-------------|-------------|--------------|----------|--------|
| T1 | [Short description] | R1 | None | No | Not Started |
| T2 | [Short description] | R1 | T1 | Yes (with T3) | Not Started |
| T3 | [Short description] | R2 | T1 | Yes (with T2) | Not Started |
| T4 | [Short description] | R2 | T2, T3 | No | Not Started |

## Phase 1: Foundation

### - [ ] T1: [Short description]

- **Requirement:** R1
- **Description:** [What to do in 1-2 sentences]
- **Files:**
  - Read: `src/[existing].py` — [what to understand from this file]
  - Create: `src/[module].py`
  - Modify: `src/[existing].py`
- **Dependencies:** None
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN [precondition]
    WHEN [action]
    THEN [expected result]
- **Tests:**
  - `test_example_one()` — [what this test verifies]
  - `test_example_two()` — [what this test verifies]
  - File: `tests/test_[module].py`
- **Verification:** `pytest tests/test_[module].py -v`

### - [ ] T2: [Short description]

- **Requirement:** R1
- **Description:** [What to do]
- **Files:**
  - Read: `src/[module].py` — [context needed from T1's output]
  - Create: `src/[module].py`
- **Dependencies:** T1
- **Parallel:** Yes (with T3) — both depend only on T1 and touch separate files
- **Acceptance Criteria:**
  - GIVEN [precondition]
    WHEN [action]
    THEN [expected result]
- **Tests:**
  - `test_example_scenario()` — [what this test verifies]
  - File: `tests/test_[module].py`
- **Verification:** `pytest tests/test_[module].py -v`

## Phase 2: Core Logic

### - [ ] T3: [Short description]

- **Requirement:** R2
- **Description:** [What to do]
- **Files:**
  - Read: `src/[module].py` — [context needed]
  - Modify: `src/[module].py`
- **Dependencies:** T1
- **Parallel:** Yes (with T2) — both depend only on T1 and touch separate files
- **Acceptance Criteria:**
  - GIVEN [precondition]
    WHEN [action]
    THEN [expected result]
- **Tests:**
  - `test_example_scenario()` — [what this test verifies]
  - File: `tests/test_[module].py`
- **Verification:** `pytest tests/test_[module].py -v`

### - [ ] T4: [Short description]

- **Requirement:** R2
- **Description:** [What to do]
- **Files:**
  - Read: `src/[module].py` — [context needed]
  - Modify: `src/[module].py`
- **Dependencies:** T2, T3
- **Acceptance Criteria:**
  - GIVEN [precondition]
    WHEN [action]
    THEN [expected result]
- **Tests:**
  - `test_integration_example()` — [what this test verifies]
  - File: `tests/test_[module].py`
- **Verification:** `pytest tests/ -v`

## Implementation Order

1. T1 — [rationale for going first]
2. T2, T3 — [can run in parallel, rationale]
3. T4 — [rationale, depends on T2 and T3]

## Implementation Deviations

> Phase-4 minor-deviation ledger — populated by the triage gate's minor path (`SKILL.md` § "Mid-implementation discovery"). Append-only during Phase 4; resolved at the Final-Check completion gate. Leave empty until a deviation is logged.

| Date | Task | What spec/design said | What was actually done | Why | Classification | Backport status |
|------|------|-----------------------|------------------------|-----|----------------|-----------------|

## Open Questions

> All questions must be resolved before proceeding to implementation.

- [ ] Q1: [Task breakdown or ordering question]
  - **Resolution:** [To be filled when answered]

## Panel Review


<!-- Terminal Phase: must NOT contain a ### Deferred dispositions sub-section. archive_pass.py rejects --terminal archives with Deferred rows; validate_blueprint.py hard-fails for PLAN.md specifically. -->
<!-- Populated by the skill across panel-review passes. archive_pass.py manages
     Trajectory and Sealed dispositions automatically; the synthesizer populates
     Latest pass detail per pass.

     This is the last artifact phase before implementation; concerns cannot be
     deferred forward. Disposition vocabulary: Addressed / Sealed / Accepted as
     risk / User input needed / Halt and re-scope. Sealed and Accepted as risk
     must include "Defense: <reason>" in Notes. Severity tags in Latest pass
     detail are bracketed: [HIGH] / [MED] / [LOW], optionally [REGRESSION].

     See SKILL.md "Panel Review section format" for the normative spec. -->

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|

### Sealed dispositions

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [ ] Approved to proceed to implementation
- **Content Hash:** `pending`
