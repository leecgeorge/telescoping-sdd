# Implementation Plan Template

Use this template when creating `PLAN.md` after an approved architecture.

---

# Implementation Plan: [Project Name]

**Scope:** `blueprint/01_SCOPE.md`
**Architecture:** `blueprint/02_ARCHITECTURE.md`

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

<!--
Marking a feature **Done**: (a) flip its milestone checkbox here, `- [ ] F<n>` ->
`- [x] F<n>` — that flip IS "Done."

(b) Mark Done only once the feature's downstream SDD cycle has **shipped**: its
`specs/F<n>-*/` spec/design/tasks are all approved AND every task box in tasks.md
is ticked AND tasks.md's `## Approval` hash matches its content (the
`is_shipped` / `classify_spec` condition). That classifier is NOT CLI-exposed, so
**no single command confirms it** — confirm with two channels:
  - Machine (partial assist): `validate_spec.py specs/F<n>-*/ --phase tasks` —
    PASSED means design.md is approved/unmodified and tasks.md is structurally
    valid. It does NOT assert tasks.md's own approval, its hash coherence, or
    box-completeness. (If the glob matches more than one dir, use the full path
    `specs/F<n>-<slug>/`.)
  - Human read: in `specs/F<n>-*/`, confirm spec.md, design.md, AND tasks.md each
    show `- [x] Approved`, and every task box in tasks.md reads `- [x]` (no command
    asserts box-completeness). Residual: the machine step re-checks only design.md's
    hash coherence; spec.md's and tasks.md's own coherence are re-checked by neither
    channel (tasks.md is terminal). A substantive post-approval edit to any artifact
    is a re-review (re-run the SDD loop), never something to force by re-stamping.

(c) Flipping to `[x]` makes the `### F<n>:` row and its bullets byte-frozen
(Closed-Feature-Row Immutability) — route later substantive changes to a new or
in-flight amending feature, never an in-place edit of the closed row.

(d) A milestone tick requires NO PLAN re-approval — it is hash-neutral.

(e) If a feature was marked Done in error (or its cycle never actually shipped),
un-tick it (`- [x] F<n>` -> `- [ ] F<n>`); that is hash-neutral too and re-opens
the row (a row is closed only while its box reads `[x]`). Un-ticking is for the
marked-in-error case ONLY; a change to a genuinely-shipped Done feature goes through
an amending feature (the (c) path).

Examples use the `F<n>` placeholder (e.g. `- [x] F<n>: <name>`); never write a
checked `- [x] F<digit>` literal here.
-->

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

## Cross-Feature Contracts

PLAN-level commitments that span multiple features. Each contract here binds multiple features cooperatively and is referenced from the participating features' ACs so the contract surfaces during those features' SDD design phases. **This section is optional** — small projects may have no genuine cross-feature contracts. Omit it entirely if none apply.

Use this section for invariants that:

- Bind two or more features that ship in different milestones (early-shipping features' SDD cycles won't see the late-shipping feature's requirements; PLAN must commit the contract upfront so all features author against it).
- Cannot be expressed as a dependency-graph edge (the relationship is not "F1 needs F2 to ship first" but "F1 and F2 must agree on a shared rule").
- Are not captured by a single feature's ACs because more than one feature owns enforcement.

Do NOT use this section for:

- Per-feature implementation details (those belong in the feature's own SDD cycle).
- Scope-level invariants (those belong in SCOPE.md).
- Architectural patterns shared across components (those belong in ARCHITECTURE.md).
- Dependency-graph edges (those belong in the `## Feature Dependencies` table).

### Contract entry format

Each contract is a subsection with the heading `### CFC-N: <short title>` (CFC = Cross-Feature Contract). The body has four required fields in this order:

- **Participating features:** comma-separated list of `F<n>` identifiers, no backticks, no other prose on the line. Example: `**Participating features:** F1, F3, F5`.
- **Contract:** the rule itself in declarative-invariant language, plus one sentence on why this can't be a single-feature concern (typically: different shipping milestones, multi-feature enforcement, no single owner). Free prose, one paragraph.
- **Per-feature AC:** the exact AC line each participating feature must carry, verbatim. One line, written so it can be copied into every participating feature's `spec.md` acceptance criteria. Non-substantive editing for tense/voice agreement is permitted at the feature side; the panel covers semantic alignment, the validator covers tag presence only.
- **Enforcement:** how the contract is verified — ArchUnit rule, CI grep, integration test, runbook gate, etc. Free prose. If a participating feature owns the verifying artifact, name that feature's identifier as the bare token `F<n>` verbatim (so the consumer-side task-analyst can mechanically detect "I own enforcement"). If enforcement has no single owning feature (purely runbook/policy gate, or co-owned), say so explicitly — write `no owning feature` or `co-owned by F<n>, F<m>` rather than omitting all `F<n>` references. Include an `F<n>` token only when that feature *owns* the verifying artifact — do not name other features incidentally; named-but-not-owning features will produce duplicate task obligations downstream.

CFC numbers must be unique within the current PLAN.md. Do not renumber when removing or rewriting a CFC, and do not re-use a number after deletion — re-using an old number would silently re-target `[CFC-N]` back-references in any already-bound `spec.md` to a different contract.

<!-- Example CFC entry (delete this comment and replace with real CFCs when authoring):

### CFC-1: <short title>

- **Participating features:** F1, F3, F5
- **Contract:** <the rule in invariant language>. <Why this can't be a single-feature concern.>
- **Per-feature AC:** <verbatim AC line each participating feature must carry>
- **Enforcement:** <how this is verified, naming the owning feature F<n> if applicable>

-->

## Panel Review


<!-- Terminal Phase: must NOT contain a ### Deferred dispositions sub-section. archive_pass.py rejects --terminal archives with Deferred rows; validate_blueprint.py hard-fails for PLAN.md specifically. -->
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
