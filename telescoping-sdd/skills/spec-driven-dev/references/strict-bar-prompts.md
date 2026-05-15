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

> **Excluded from this pass:** requirement-level questions (those are sealed in `spec.md` — if a requirement is genuinely wrong, that is a `Halt and re-scope` vote, not a strict-bar concern), task breakdown / sizing / ordering (those are `tasks.md`).
>
> **Required to clear the bar:** the concern must call for an architecture-decision change, a component-design change, an interface / contract change, a data-model change, a dependency change, or an implementation-sequence change — and must cite the specific `design.md` passage it attaches to, with a one-line statement of why it cannot be resolved downstream.

## Phase 3 — Tasks (`tasks.md`)

> **Excluded from this pass:** requirement-level questions (sealed in `spec.md`), design-level questions (sealed in `design.md`).
>
> **Required to clear the bar:** the concern must call for a task-breakdown change, a task-sizing correction, or a task-dependency / implementation-order change — and must cite the specific `tasks.md` passage it attaches to. Tasks is the last phase: there is no downstream artifact to defer to, so the "cannot be resolved downstream" test collapses to "cannot be resolved without changing the task list's structure."

## Recording a strict-bar pass

Strict-bar concerns are written into `### Latest pass detail` exactly like normal-pass concerns and disposed normally — `Addressed`, `Deferred → <target>`, `Sealed`, `Accepted as risk`, `User input needed`, or `Halt and re-scope`. Concerns that clear the strict bar are spec/design/tasks-shaped by construction and frequently warrant `Sealed` or `Accepted as risk` (both promote to `### Sealed dispositions`).

Archive a strict-bar pass with `python <shared-script-path>/archive_pass.py <artifact> --strict-bar` — this stamps the `### Trajectory` Notes column so the trajectory records the mode. See `panel-review.md` for the exit cross-check that runs once a strict-bar pass returns zero HIGHs.
