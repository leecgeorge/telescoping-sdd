# Spec Template (Java)

Use this template when creating `spec.md` for a Java project.

---

# Feature: [Feature Name]

**PLAN feature identifier:** `F<n>` (matches the feature entry in `blueprint/PLAN.md`'s Feature Breakdown — e.g. `F1`, `F11`). If no upstream PLAN exists, write `n/a`.

## Objective

[One paragraph describing what this feature does and why it's needed.]

## Requirements

### R1: [Requirement Name]

As a [role], I want [action], so that [benefit].

**Acceptance Criteria:**

- GIVEN [precondition]
  WHEN [action]
  THEN [expected result]

- GIVEN [precondition]
  WHEN [action]
  THEN [expected result]

### R2: [Requirement Name]

As a [role], I want [action], so that [benefit].

**Acceptance Criteria:**

- GIVEN [precondition]
  WHEN [action]
  THEN [expected result]

## Project Structure

```
project-root/
├── src/
│   ├── main/java/[package]/
│   │   └── [where new classes go]
│   └── test/java/[package]/
│       └── [where new tests go]
├── pom.xml or build.gradle
└── [other relevant paths]
```

### New Files
- `src/main/java/[package]/[Class].java` — [purpose]
- `src/test/java/[package]/[Class]Test.java` — [what it tests]

### Modified Files
- `src/main/java/[package]/[Existing].java` — [what changes]

## Commands

```bash
# How to run the project
mvn exec:java -Dexec.mainClass="[main class]"

# How to run tests
mvn test

# How to lint/format
mvn checkstyle:check
```

## Boundaries

### Always Do
- [Convention or constraint to follow]
- [Another convention]

### Ask First
- [Decisions that need user input]
- [Ambiguous areas]

### Never Do
- [Hard constraints]
- [Things explicitly out of scope]

## Open Questions

> All questions must be resolved before proceeding to the next phase.

- [ ] Q1: [Question about requirements or scope]
- [ ] Q2: [Another question]

## Decision Points

- [Area where the design must make a choice, e.g., "Whether to support bulk operations or single-item only"]
- [Another decision point for the design phase]

## Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R1 | [What could go wrong] | Low/Med/High | Low/Med/High | [How to handle] |

## Success Criteria

- [ ] [Measurable condition 1]
- [ ] [Measurable condition 2]
- [ ] [Measurable condition 3]
- [ ] All tests pass
- [ ] No regressions in existing functionality

## Panel Review

<!-- Populated by the skill across panel-review passes. archive_pass.py manages
     Trajectory and Sealed dispositions automatically; the synthesizer populates
     Latest pass detail per pass.

     Disposition vocabulary: Addressed / Deferred → <TARGET.md> / Sealed /
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
