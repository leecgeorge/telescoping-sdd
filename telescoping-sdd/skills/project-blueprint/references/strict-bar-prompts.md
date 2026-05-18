# Strict-Bar Prompts

This reference holds the per-phase prompt additions that turn a normal panel pass into a **strict-bar** pass. The strict-bar mode itself — when to enter it, the exit cross-check, and cap accounting — is defined in `references/panel-review.md` under `## Strict-Bar Convergence Mode`. This file is loaded only when a pass is run in strict-bar mode (whether reached via the fire-and-ask auto-detection or via the user typing "strict bar").

## What a strict-bar pass changes

A strict-bar pass uses the **same panelists** as the phase's normal pass (see `panel-review.md` § Panelists per phase) and the **same loop**. Only the invocation prompt changes: each panelist additionally receives the core filter rule, the phase's exclusion/required lists, and the inspectability instruction below.

## Core filter rule (all phases)

Append to every strict-bar panelist prompt:

> **Strict bar.** Raise a concern only if it would still matter even after every downstream phase were re-run from scratch — i.e., it requires a decision at *this* phase and **cannot** be resolved by deferring it to a downstream artifact. Concerns that a downstream phase would absorb are out of scope for this pass, however real they are. Apply the phase-specific excluded/required lists below.

## Inspectability instruction (all phases)

Append to every strict-bar panelist prompt:

> If you considered a concern and declined to raise it at this bar, state it explicitly and cite which exclusion category it falls under (UX surface, feature AC, ARCH pattern, test strategy, etc.). This list need not be exhaustive, but name your strongest 2–3 declined candidates. If you raise no concerns at all, still produce this declined list — `No new concerns` with an empty declined list is not a valid strict-bar response.

The synthesizer reads each panelist's declined list and checks whether any "declined" item is actually shaped for *this* phase and should have cleared the bar. The declined lists also seed downstream-phase re-runs without re-running the full panel.

## Phase 1 — Scope

> **Excluded from this pass:** UX surfaces ("add a banner to F22"), feature acceptance criteria, architectural component design, test-strategy / test-coverage choices, implementation-cost concerns that don't change a scope rule.
>
> **Required to clear the bar:** the concern must call for a new Goal, a new Non-Goal, a new Constraint, a new Success Criterion, or a fundamental rule change to existing scope text — and must cite the specific `SCOPE.md` passage it attaches to, with a one-line statement of why it cannot be resolved downstream.

## Phase 2 — Architecture

> **Excluded from this pass:** feature acceptance criteria, test-strategy / test-coverage choices, scope-level questions. If a concern is shaped like a SCOPE decision that `SCOPE.md` doesn't commit, do NOT raise it as a strict-bar concern — tag it `[upstream]` and let `archive_pass.py` route it to a halt vote so the user can update `SCOPE.md`. Strict-bar is "find concerns at *this* phase"; `[upstream]` concerns belong at an earlier phase.
>
> **Required to clear the bar:** the concern must call for a new component, a component-boundary change, an interaction-contract change, a data-architecture decision, a dependency change, or a fundamental risk that changes the architecture itself (the NORMAL-pass analogue is the `[contract]` tag) — and must cite the specific `ARCHITECTURE.md` passage it attaches to, with a one-line statement of why it cannot be resolved downstream.

## Phase 3 — Implementation Plan

> **Excluded from this pass:** single-feature SDD-cycle concerns — naming nitpicks, regex tuning, runbook authoring, CI-workflow scoping, CODEOWNERS edits, migration version numbering inside one feature, and other implementation-time concerns (the NORMAL-pass analogue is the `[detail]` tag). These will be caught in the relevant feature's spec-driven-dev design/tasks phase. Also excluded: scope-level questions and architectural-pattern questions — if a concern is shaped like a SCOPE or ARCH decision that the respective artifact doesn't commit, do NOT raise it as a strict-bar concern. Tag it `[upstream]` (in a NORMAL pass) or surface it as `Halt and re-scope` (in a strict-bar pass) so the user can update the upstream artifact.
>
> **Required to clear the bar:** the concern must be a cross-feature contract decision (the NORMAL-pass analogue is the `[contract]` tag) — an FQCN that another feature's ArchUnit rule references; an env-var naming convention shared across features; dependency-order sequencing across multiple features; a cross-feature port pattern; a cross-feature migration ordering decision; or another decision that a single feature's SDD cycle would NOT naturally surface. Must cite the specific `PLAN.md` passage it attaches to.
>
> **CFC self-check.** A `[contract]`-tagged finding should produce a proposed `### CFC-N` entry in PLAN's `## Cross-Feature Contracts` section, naming the participating features and the rule (per the four-field format in `references/plan-template.md`). If the finding does not naturally fit a CFC-shaped commitment — i.e., you can't write a Participating-features list, a Contract clause, a Per-feature AC, and an Enforcement description for it — reconsider whether it is genuinely `[contract]` or should be re-tagged `[detail]` (single-feature) / `[upstream]` (earlier-phase gap). The check is: if you can't write the CFC entry, the tag is probably wrong.

## Recording a strict-bar pass

Strict-bar concerns are written into `### Latest pass detail` exactly like normal-pass concerns and disposed normally — `Addressed`, `Deferred → <target>`, `Sealed`, `Accepted as risk`, `User input needed`, or `Halt and re-scope`. Concerns that clear the strict bar are scope/architecture/plan-shaped by construction and frequently warrant `Sealed` or `Accepted as risk` (both promote to `### Sealed dispositions`).

Archive a strict-bar pass with `python <shared-script-path>/archive_pass.py <artifact> --phase <N> --strict-bar` — this stamps the `### Trajectory` Notes column so the trajectory records the mode. See `panel-review.md` for the exit cross-check that runs once a strict-bar pass returns zero HIGHs.
