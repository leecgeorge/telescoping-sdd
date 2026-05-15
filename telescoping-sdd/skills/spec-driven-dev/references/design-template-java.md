# Design Template (Java)

Use this template when creating `design.md` for a Java project after an approved spec.

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

**Location:** `src/main/java/[package]/[Class].java`

**Key classes/methods:**
- `ClassName` — [purpose]
- `methodName()` — [purpose]

### [Component/Module Name]

**Responsibility:** [What this component does]

**Location:** `src/main/java/[package]/[Class].java`

## Data Models

| Model | Field | Type | Constraints | Description |
|-------|-------|------|-------------|-------------|
| [ModelName] | fieldName | String | Required, non-empty | [What this field represents] |
| [ModelName] | otherField | int | Range: 1-100 | [What this field represents] |
| [ModelName] | createdAt | LocalDateTime | Auto-set | [What this field represents] |

**Relationships:**
- [ModelA] has many [ModelB]
- [ModelB] belongs to [ModelA]

**Persistence:** [JPA/Hibernate / JDBC / record classes / etc.]

## Interfaces

```java
/**
 * [What this method does].
 *
 * @param param [description]
 * @param count [description]
 * @return [What is returned]
 * @throws IllegalArgumentException [when]
 */
public List<ResultType> methodName(String param, int count) {
    ...
}
```

**Contracts:**
- [Preconditions: what must be true before calling]
- [Postconditions: what is guaranteed after calling]
- [Side effects: what external state changes, if any]

## Error Handling

- **Strategy:** [checked exceptions / unchecked exceptions / Result types]
- **Custom exceptions:** [list any project-specific exception classes needed]
- **Logging:** [SLF4J / Log4j2 / java.util.logging]
- **User-facing errors:** [how errors are communicated to the user]

## Testing Strategy

- **Framework:** JUnit 5
- **Test location:** `src/test/java/` mirroring `src/main/java/` package structure
- **Mocking approach:** [Mockito / mock beans / test doubles]
- **Coverage expectations:** [what must be covered]
- **Fixtures / test data:** [shared fixtures, @BeforeEach setup, or test data builders]

## File Structure

```
project-root/
├── src/
│   ├── main/java/[package]/
│   │   ├── [NewClass].java        — [purpose]
│   │   └── [ExistingClass].java   — [what changes]
│   └── test/java/[package]/
│       └── [NewClass]Test.java    — [what it tests]
├── pom.xml or build.gradle
└── [other relevant paths]
```

## Dependencies

| Package | Purpose |
|---------|---------|
| [groupId:artifactId] | [why needed] |

## Integration Points

| Existing Module | Direction | Change Required | Details |
|-----------------|-----------|-----------------|---------|
| `[package].[Class]` | Calls into | No | [How new code uses this module] |
| `[package].[Class]` | Called by | Yes — add dependency | [How existing code will call new code] |

## Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R1 | [What could go wrong] | Low/Med/High | Low/Med/High | [Concrete action — reference a component or decision above] |

## Implementation Sequence

1. [Core data models / foundational layer] — [rationale for going first]
2. [Business logic] — [rationale]
3. [Controller / API layer] — [rationale]
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

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [ ] Approved to proceed to next phase
- **Content Hash:** `pending`
