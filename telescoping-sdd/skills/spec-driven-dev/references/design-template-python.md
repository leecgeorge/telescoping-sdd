# Design Template (Python)

Use this template when creating `design.md` for a Python project after an approved spec.

---

# Design: [Feature Name]

**Spec:** `specs/[feature-name]/spec.md`

## Goals and Non-Goals

**Goals:**
- [What this design aims to achieve — can be brief, overlaps with spec objective]

**Non-Goals:**
- [Things that could reasonably be goals but are explicitly excluded]
- [Prevents scope creep during implementation]

## Architecture Decisions

| Decision | Choice | Alternatives Rejected | Rationale | Consequences |
|----------|--------|-----------------------|-----------|--------------|
| [What needed deciding] | [What was chosen] | [What was considered and why not] | [Why this choice] | [What follows from this choice] |

## Component Design

### [Component/Module Name]

**Responsibility:** [What this component does]

**Location:** `src/[path].py`

**Key classes/functions:**
- `ClassName` — [purpose]
- `function_name()` — [purpose]

### [Component/Module Name]

**Responsibility:** [What this component does]

**Location:** `src/[path].py`

## Data Models

| Model | Field | Type | Constraints | Description |
|-------|-------|------|-------------|-------------|
| [ModelName] | field_name | str | Required, non-empty | [What this field represents] |
| [ModelName] | other_field | int | Range: 1-100 | [What this field represents] |
| [ModelName] | created_at | datetime | Auto-set | [What this field represents] |

**Relationships:**
- [ModelA] has many [ModelB]
- [ModelB] belongs to [ModelA]

**Persistence:** [dataclass with JSON serialization / SQLAlchemy / Pydantic / etc.]

## Interfaces

```python
def function_name(param: str, count: int = 10) -> list[ResultType]:
    """[What this function does].

    Args:
        param: [description]
        count: [description]

    Returns:
        [What is returned]

    Raises:
        ValueError: [when]
    """
    ...
```

**Contracts:**
- [Preconditions: what must be true before calling]
- [Postconditions: what is guaranteed after calling]
- [Side effects: what external state changes, if any]

## Error Handling

- **Strategy:** [exceptions / result types / error codes]
- **Custom exceptions:** [list any project-specific exception classes needed]
- **Logging:** [stdlib logging / structlog / etc.]
- **User-facing errors:** [how errors are communicated to the user]

## Testing Strategy

- **Framework:** pytest
- **Test location:** `tests/` mirroring `src/` structure
- **Mocking approach:** [unittest.mock / pytest-mock / monkeypatch]
- **Coverage expectations:** [what must be covered]
- **Fixtures / test data:** [shared fixtures or test data needed]

## File Structure

```
project-root/
├── src/
│   ├── [new_module].py        — [purpose]
│   └── [existing_module].py   — [what changes]
├── tests/
│   └── test_[new_module].py   — [what it tests]
└── [other relevant paths]
```

## Dependencies

| Package | Purpose |
|---------|---------|
| [package-name] | [why needed] |

## Integration Points

| Existing Module | Direction | Change Required | Details |
|-----------------|-----------|-----------------|---------|
| `src/[module].py` | Calls into | No | [How new code uses this module] |
| `src/[module].py` | Called by | Yes — add import | [How existing code will call new code] |

## Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R1 | [What could go wrong] | Low/Med/High | Low/Med/High | [Concrete action — reference a component or decision above] |

## Implementation Sequence

1. [Core data models / foundational layer] — [rationale for going first]
2. [Business logic] — [rationale]
3. [Interface / CLI layer] — [rationale]
4. [Integration tests] — [rationale]

## Open Questions

> All questions must be resolved before proceeding to the next phase.

- [ ] Q1: [Architecture or design question]
  - **Resolution:** [To be filled when answered]
- [ ] Q2: [Another question]
  - **Resolution:** [To be filled when answered]

## Panel Review

<!-- Populated by the skill across panel-review passes. archive_pass.py manages
     Trajectory and Sealed dispositions automatically; the synthesizer populates
     Latest pass detail per pass.

     Disposition vocabulary: Addressed / Deferred → tasks.md / Sealed /
     Accepted as risk / User input needed / Halt and re-scope. Sealed and
     Accepted as risk must include "Defense: <reason>" in Notes. Severity tags
     in Latest pass detail are bracketed: [HIGH] / [MED] / [LOW], optionally
     [REGRESSION].

     See SKILL.md "Panel Review section format" for the normative spec. -->

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|

### Sealed dispositions

### Deferred dispositions

<!-- Auto-populated by archive_pass.py when a Deferred-disposed row is promoted; remains empty until first deferral. -->

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [ ] Approved to proceed to next phase
- **Content Hash:** `pending`
