# Strict-Bar Prompts

This reference holds the per-phase prompt additions that turn a normal panel pass into a **strict-bar** pass. The strict-bar mode itself — when to enter it, the exit cross-check, and cap accounting — is defined in `references/panel-review.md` under `## Strict-Bar Convergence Mode`. This file is loaded only when a pass is run in strict-bar mode (whether reached via the fire-and-ask auto-detection or via the user typing "strict bar").

## What a strict-bar pass changes

A strict-bar pass uses the **same panelists** as the phase's normal pass (see `panel-review.md` § Panelists per phase) and the **same loop**. Only the invocation prompt changes: each panelist additionally receives the core filter rule, the phase's exclusion/required lists, and the inspectability instruction below.

## Core filter rule (all phases)

Append to every strict-bar panelist prompt:

> **Strict bar.** Raise a concern only if it would still matter even after every downstream phase were re-run from scratch — i.e., it requires a decision at *this* phase and **cannot** be resolved by deferring it to a downstream artifact. Concerns that a downstream phase would absorb are out of scope for this pass, however real they are. Apply the phase-specific excluded/required lists below.

## Inspectability instruction (all phases)

Append to every strict-bar panelist prompt:

> If you considered a concern and declined to raise it at this bar, state it explicitly and cite which exclusion category it falls under (design choice, task breakdown, test strategy, etc.). This list need not be exhaustive, but name your strongest 2–3 declined candidates. If you raise no concerns at all, still produce this declined list — `No new concerns` with an empty declined list is not a valid strict-bar response.

The synthesizer reads each panelist's declined list and checks whether any "declined" item is actually shaped for *this* phase and should have cleared the bar. The declined lists also seed downstream-phase re-runs without re-running the full panel.

## Phase 1 — Specify (`spec.md`)

> **Excluded from this pass:** component / interface / data-model design choices (those are `design.md`), task breakdown / sizing / ordering (those are `tasks.md`), test-fixture and testing-strategy choices (those are `design.md` Testing Strategy or `tasks.md`).
>
> **Required to clear the bar:** the concern must call for a new or removed Requirement, an acceptance-criterion change, a Boundary change, a Success-Criterion change, or an Objective change — and must cite the specific `spec.md` passage it attaches to, with a one-line statement of why it cannot be resolved downstream.

## Phase 2 — Design (`design.md`)

> **Excluded from this pass:** task breakdown / sizing / ordering (those are `tasks.md`); requirement-level questions. If a concern is shaped like a requirement or acceptance criterion that `spec.md` doesn't commit, do NOT raise it as a strict-bar concern — tag it `[upstream]` and let `archive_pass.py` route it to a halt vote so the user can update `spec.md`. Strict-bar is "find concerns at *this* phase"; `[upstream]` concerns belong at an earlier phase.
>
> **Required to clear the bar:** the concern must call for an architecture-decision change, a component-design change, an interface / contract change, a data-model change, a dependency change, or an implementation-sequence change (the NORMAL-pass analogue is the `[contract]` tag) — and must cite the specific `design.md` passage it attaches to, with a one-line statement of why it cannot be resolved downstream.

## Phase 3 — Tasks (`tasks.md`)

> **Excluded from this pass:** implementation-time concerns — single-task naming, intra-task structure, fixture details inside one task, edge-case enumeration that materialises while writing code (the NORMAL-pass analogue is the `[detail]` tag). These will be caught in Phase 4 (Implement) when the test/code is actually written. Also excluded: requirement-level and design-level questions — if a concern is shaped like a spec or design decision that the respective artifact doesn't commit, do NOT raise it as a strict-bar concern. Tag it `[upstream]` (in a NORMAL pass) or surface it as `Halt and re-scope` (in a strict-bar pass) so the user can update the upstream artifact.
>
> **Required to clear the bar:** the concern must be a cross-task contract decision (the NORMAL-pass analogue is the `[contract]` tag) — an ordering dependency between tasks; an interface contract another task's tests will assert against; a shared fixture pattern multiple tasks depend on; a cross-task implementation-sequence decision; or another concern that a single task's implementation pass would NOT naturally surface. Must cite the specific `tasks.md` passage it attaches to.

## Recording a strict-bar pass

Strict-bar concerns are written into `### Latest pass detail` exactly like normal-pass concerns and disposed normally — `Addressed`, `Deferred → <target>`, `Sealed`, `Accepted as risk`, `User input needed`, or `Halt and re-scope`. Concerns that clear the strict bar are spec/design/tasks-shaped by construction and frequently warrant `Sealed` or `Accepted as risk` (both promote to `### Sealed dispositions`).

Archive a strict-bar pass with `python <shared-script-path>/archive_pass.py <artifact> --phase <N> --strict-bar` — this stamps the `### Trajectory` Notes column so the trajectory records the mode. See `panel-review.md` for the exit cross-check that runs once a strict-bar pass returns zero HIGHs.
