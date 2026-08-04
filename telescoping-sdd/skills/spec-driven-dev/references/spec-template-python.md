# Spec Template (Python)

Use this template when creating `spec.md` for a Python project.

---

# Feature: [Feature Name]

**PLAN feature identifier:** `F<n>` (matches the feature entry in `blueprint/03_PLAN.md`'s Feature Breakdown — e.g. `F1`, `F11`; the bare `blueprint/PLAN.md` is also accepted). If no upstream PLAN exists, write `n/a`.

> **Authoring convention — point rather than restate.** This template is
> multi-view by construction: `Success Criteria` mirror the acceptance criteria,
> `Boundaries` mirror them, `Modified Files` mirrors what the ACs commit to, and
> `Risks` mitigations restate ACs. Every fact therefore has three or four
> legitimate homes, and an incremental edit desyncs the copies it did not touch.
>
> **Where a fact has an authoritative home, other sites point to it rather than
> restating it.** This is conditional, never absolute — it does not mean every
> restatement must become a pointer. `Success Criteria` reduced to bare index
> pointers lose their standalone checklist function, which is a real cost.
>
> **A pointer names a location and a role; it never describes what the target
> says.** `See R2's third acceptance criterion` cannot be wrong about that
> criterion's content. `See R2's third acceptance criterion, which requires a
> hard cap` can — the gloss is a restatement smuggled into the pointer, and it can
> be false from the moment it is written, not only when the target drifts. The
> unglossed form makes the defect impossible rather than merely detectable.
>
> **The authoritative home is the most *durable* site, not merely the most
> complete one.** Completeness alone is the wrong tiebreak: choosing "the more
> specific copy" once made an *open question* the home for a doctrine quotation,
> and an open question gets answered and rewritten, orphaning every pointer aimed
> at it. An acceptance criterion outlives an open question.
>
> This is a **consistency** measure. De-duplicating by pointer typically makes a
> document slightly *longer*; it is not a length, verbosity or word-count
> reduction, and must not be applied as one. (Distinct from the PLAN-driven thin
> Objective below, which is about inherited framing, not about cross-site copies.)

## Objective

[One paragraph describing what this feature does and why it's needed.]

> **PLAN-driven thin form (sanctioned default).** If this feature is PLAN-driven —
> it carries a bound `F<n>` `**PLAN feature identifier:**` OR a `**Derived from:**`
> line — you MAY thin this section instead of re-deriving the problem/users/goals
> that PLAN already fixes at project altitude. Keep the `## Objective` heading (it
> is still a required section) and, under it, write:
>
> - `**From PLAN F<n>:** <pointer into the PLAN entry>` — the human provenance
>   pointer for framing inheritance. This is distinct from the top-of-document
>   `**PLAN feature identifier:**` (the machine identifier / spec-dir agreement
>   key); as authoring discipline (not a validator check) the pointer's `F<n>`
>   should match that identifier.
> - one one-line gloss sentence paraphrasing the PLAN framing, so a gate reviewer
>   gets the local "why" without opening PLAN.
>
> **What a good gloss looks like.** *Legitimate:* "This feature is the first to
> write to the shared cache, so its failure mode is a stale read no other feature
> can produce" — a fact about THIS feature that PLAN, writing at project altitude,
> does not state. *Not legitimate:* "Operators need faster dashboards because slow
> queries erode trust" — that is PLAN's problem statement re-derived in local
> words. The test is not length or tone: **does this sentence say something PLAN
> does not already say?**
>
> For a CPD-derived feature (`**PLAN feature identifier:** n/a` with a
> `**Derived from:** <project>:F<n>` line), the existing `**Derived from:**`
> line *is* the provenance pointer — do not add a second pointer line — and the
> one-line gloss still accompanies it as the local fallback for the "why" when the
> master hash is `unbound` or unreachable.
>
> The thin form is the sanctioned default for a PLAN-driven feature,
> author-declinable only to add genuinely feature-specific framing PLAN does not
> cover — never to re-derive PLAN's framing. A standalone feature (`n/a`, no
> `**Derived from:**`) is NOT eligible: keep the full Objective narrative above.

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
│   └── [where new modules go]
├── tests/
│   └── [where new tests go]
└── [other relevant paths]
```

### New Files
- `src/[module].py` — [purpose]
- `tests/test_[module].py` — [what it tests]

### Modified Files
- `src/[existing].py` — [what changes]

## Commands

```bash
# How to run the project
[command]

# How to run tests
pytest

# How to lint/format
ruff check . && ruff format .
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
