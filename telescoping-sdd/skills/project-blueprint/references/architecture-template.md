# Architecture Template

Use this template when creating `ARCHITECTURE.md` after an approved scope.

---

# Architecture: [Project Name]

**Scope:** `blueprint/01_SCOPE.md`

## System Overview

[High-level description of the system. What it does, who it serves, and how it fits into the broader context. One to two paragraphs.]

## Components

### [Component Name]

- **Responsibility:** [What this component does — single responsibility]
- **Boundary:** [What is inside vs. outside this component]
- **Key Concerns:** [Performance, security, scalability considerations specific to this component]

### [Component Name]

- **Responsibility:** [What this component does]
- **Boundary:** [What is inside vs. outside this component]
- **Key Concerns:** [Specific considerations]

### [Component Name]

- **Responsibility:** [What this component does]
- **Boundary:** [What is inside vs. outside this component]
- **Key Concerns:** [Specific considerations]

## Component Interactions

```
[ASCII diagram showing how components communicate]

Example:
┌──────────┐     HTTP/REST    ┌──────────┐     SQL      ┌──────────┐
│  Client   │───────────────>│   API    │────────────>│ Database │
└──────────┘                 └──────────┘              └──────────┘
                                   │
                                   │ Events
                                   v
                             ┌──────────┐
                             │  Queue   │
                             └──────────┘
```

| From | To | Protocol | Data | Purpose |
|------|----|----------|------|---------|
| [Component A] | [Component B] | [HTTP/gRPC/events/etc.] | [What is exchanged] | [Why they communicate] |
| [Component B] | [Component C] | [Protocol] | [What is exchanged] | [Why they communicate] |

## Technology Choices

| Area | Choice | Alternatives Considered | Rationale |
|------|--------|------------------------|-----------|
| Language | [Choice] | [What else was considered] | [Why this choice] |
| Framework | [Choice] | [Alternatives] | [Rationale] |
| Database | [Choice] | [Alternatives] | [Rationale] |
| Infrastructure | [Choice] | [Alternatives] | [Rationale] |

**Architecture token:** `generic`

<!-- A single controlled-vocabulary token that names the SDD stack profile for
     this project: `python`, `java`, or `generic` (architecture-neutral — use for
     infrastructure, static sites, frontend without a Python/Java marker, Claude-
     skill authoring, etc.). This is NOT free-form prose: it must be exactly one
     of those tokens. It exists so the stack declared here crosses the blueprint→
     SDD seam — run `validate_blueprint.py blueprint/ --write-arch-config` to
     persist it to `.sdd/architecture.json`, which spec-driven-dev then resolves
     instead of re-detecting. Keep it consistent with the Language/Infrastructure
     rows above. -->

## Data Architecture

### Data Models (High-Level)

| Entity | Description | Owned By | Storage |
|--------|-------------|----------|---------|
| [Entity name] | [What it represents] | [Which component] | [Where stored] |
| [Entity name] | [What it represents] | [Which component] | [Where stored] |

### Data Flow

[Describe how data moves through the system — from input to storage to output. Include key transformations.]

```
[ASCII diagram of data flow if helpful]

Example:
User Input ──> Validation ──> Processing ──> Storage
                                  │
                                  └──> Notification
```

## External Dependencies

| Dependency | Purpose | Risk if Unavailable | Fallback |
|-----------|---------|---------------------|----------|
| [Service/API name] | [Why needed] | [Impact] | [What happens if it's down] |
| [Library/framework] | [Why needed] | [Impact] | [Alternative approach] |

## Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R1 | [What could go wrong] | Low/Med/High | Low/Med/High | [Concrete mitigation strategy] |
| R2 | [What could go wrong] | Low/Med/High | Low/Med/High | [Concrete mitigation strategy] |
| R3 | [What could go wrong] | Low/Med/High | Low/Med/High | [Concrete mitigation strategy] |

## Open Questions

> All questions must be resolved before proceeding to the next phase.

- [ ] Q1: [Architecture or technology question]
  - **Resolution:** [To be filled when answered]
- [ ] Q2: [Another question]
  - **Resolution:** [To be filled when answered]

## Panel Review

<!-- Populated by the skill across panel-review passes. archive_pass.py manages
     Trajectory and Sealed dispositions automatically; the synthesizer populates
     Latest pass detail per pass.

     Disposition vocabulary: Addressed / Deferred → PLAN.md / Sealed /
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
