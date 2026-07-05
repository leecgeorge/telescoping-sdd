<!--
SHARED REFERENCE — keep in sync with the project-blueprint copy at
skills/project-blueprint/references/workflow-overview.md. Edits to shared content must be mirrored in BOTH copies.

Intentional asymmetries vs the sibling (do NOT "sync" these away):
- Phase model is skill-specific: blueprint has 3 phases (Scope/Architecture/Plan); spec-driven-dev has 4 (Specify/Design/Tasks/Implement) — diagram, headings, and phase count differ by design.
- spec-driven-dev's Phase 4 (Implement) is SDD-only: extra Phase-Summary row, "Phase 4 executed directly" note, a 4th review gate, and the "Implement task" quick command have no blueprint counterpart.
- Terminal Phase-3 artifact differs: PLAN.md (blueprint) vs tasks.md (spec-driven-dev), along with the File Layout tree (flat blueprint/ vs specs/F<n>-<slug>/).
- Blueprint-only doctrine sections (Handoff to Feature Development, Bound-Spec Immutability, Closed-Feature-Row Immutability) are PLAN/CFC-producer rules, intentionally absent from spec-driven-dev (the consumer).
Otherwise the copies differ only cosmetically (phase names, filenames, example feature names, quick-command phrasing, Principles wording).
-->

# Spec-Driven Development — Workflow Overview

## The Four Phases

```
  SPECIFY          DESIGN          TASKS           IMPLEMENT
 ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────────┐
 │ spec.md │──>│design.md│──>│ tasks.md│──>│ Code + Tests│
 └─────────┘    └─────────┘    └─────────┘    └─────────────┘
      │              │              │               │
   REVIEW         REVIEW         REVIEW          REVIEW
   GATE           GATE           GATE            GATE
```

**Discoveries flow back, too.** `Implement ⤴ Spec/Design — discovery → backport`: a discovery during implementation that contradicts an approved upstream is reconciled by editing the upstream *first* (the single highest-affected document) and letting the cascade reconcile downstream — not by editing forward only, and never by co-editing the chain. See `references/hash-and-cascade.md` § "Upstream backport — same-repo discovery".

## Phase Summary

| Phase | Input | Output | Drafted By | Key Question |
|-------|-------|--------|------------|-------------|
| Specify | User requirements | `spec.md` | `feature-spec-analyst` subagent | **What** are we building and why? |
| Design | Approved spec | `design.md` | `feature-architecture-analyst` subagent | **How** will we build it? |
| Tasks | Approved design | `tasks.md` | `feature-task-analyst` subagent | **What steps** in what order? |
| Implement | Approved tasks | Working code + tests | Calling Claude (no delegation) | **Does it work** as specified? |

Phases 1–3 delegate to the corresponding subagent both the initial drafting AND substantial revisions of each artifact, via the Agent tool. The agent self-reviews its draft before returning. The calling Claude then performs its own review, runs cross-document consistency checks, validation, and approval gates. Phase 4 is executed directly by the calling Claude.

**When to delegate vs. act directly.** The delegation rule is a three-way decision: *trivial* edits (typo, rename, formatting, single-sentence reword — no behavior change) stay orchestrator-direct; a *substantive in-loop per-concern fix* during an active panel pass stays orchestrator-direct (the next pass of the same loop re-reviews it); and a *substantial out-of-loop revision* — a cascade downstream fix, a panel-loop re-entry on a substantive gate-change, or an upstream backport — is delegated to the phase-correct analyst (the "Drafted By" analyst for the artifact being edited). See `references/hash-and-cascade.md` § "Revise the downstream" for the delegation brief the orchestrator supplies and the scope-verify check it runs before re-stamping.

## File Layout

```
project-root/
└── specs/
    └── F<n>-<slug>/
        ├── 01_spec.md      # Phase 1 output
        ├── 02_design.md    # Phase 2 output
        └── 03_tasks.md     # Phase 3 output
```

Artifacts emit with a two-digit `NN_` ordinal prefix by default (so a directory listing sorts in phase order). The bare form (`spec.md`, `design.md`, `tasks.md`) also resolves everywhere on read — the prose below uses the bare names as shorthand.

## Review Gates

Between each phase, stop and ask the user:

1. After Specify: "Here's the spec. Does this capture what you want to build?"
2. After Design: "Here's the design. Does this architecture make sense?"
3. After Tasks: "Here are the tasks. Is this the right breakdown and order?"

Implement (Phase 4) has **no per-task approval gate** — tasks run sequentially through the Phase-4 cycle (`SKILL.md` § Phase 4: Implement), reporting each task's completion inline and continuing to the next. Interactive TDD visibility is the course-correction surface; loop continuation is not a user decision (see `panel-review.md` § Autonomy Boundary).

## Context Management — Resetting at Gates

Long runs grow the context window until it hits involuntary compaction (the "compaction cliff"). You do not have to ride the window up to that cliff: the orchestrator **offers a context reset at each approval gate** — a `/clear`, `/compact`, or fresh session that drops the window back toward scaffolding size. This is not a passive option you might remember to reach for: at every gate the offer is **gate-triggered always** and surfaced to the user as a **plain-language, non-blocking conversational suggestion** they can accept or decline. It is never automatic, never forced, and never a validator gate that blocks anything.

**Read the gate advisory and act on it.** On every successful gate approval the validator prints a one-line `RESET-CHECKPOINT:` advisory to stdout naming the just-approved gate, the next step, and the exact files to re-read on resume. Read that advisory from your own CLI tool output, capture its re-read list, and translate it into the plain-language offer — do not echo the raw `RESET-CHECKPOINT:` token, the word "gate", or the file list verbatim at the user; speak it as a natural suggestion. (A companion `RESET-CHECKPOINT-DEBUG:` line may appear on **stderr** on the rare advisory-construction failure; it is a maintainer-facing trace, never surfaced to the user and never part of the offer.)

**1 — Gates are safe reset checkpoints.** Once a phase is approved, its decisions are captured in the artifact plus its content hash on disk. That is durable state, so the run can continue in a compacted or fresh session with **no state loss**.

**2 — The validator rehydrates you: `--run-state`.** After any reset (compaction, `/clear`, or a fresh session), run the validator to re-establish current run state: which artifacts exist and are approved vs pending, each approved artifact's content-hash status, the current phase, and any open obligations. `validate_spec.py <spec-dir> --run-state` is the purpose-built, single-command way to print exactly that as a compact one-screen summary — read-only, it changes nothing. **Honest boundary:** `--run-state` re-derives all *disk-durable* state, but it **cannot** recover conversational nuance that was never written into an artifact. So a reset mitigates the compaction cliff by making a *deliberate* reset safe and a post-compaction *recovery* fast — it does **not** undo the loss an *involuntary* mid-phase compaction has already caused.

**3 — The caveat: a reset drops un-written conversational nuance.** A reset loses any conversational state not yet written into an artifact. Concretely that includes: panel concerns raised in the current pass but **not yet archived** by `archive_pass.py`; a pending strict-bar or halt-vote decision **awaiting the user**; an in-flight cascade or re-approval obligation **not yet acted on**; a **dispatched-but-not-yet-returned** background subagent (e.g. a panelist `Agent` call still running when the reset lands); and any decision **discussed but not yet written** into an artifact. Because of this, the safe reset point is a **phase-approval gate** — a clean boundary with no open loop — and **NOT mid-panel-loop**.

**`/clear` vs `/compact`.** Prefer `/clear` when the on-disk artifacts already hold everything that matters: it clears the visible conversation history and the next `--run-state` **reloads it verbatim** from disk — the highest-fidelity resume. Reach for `/compact` instead when live, un-written conversational nuance is still in play — but know that `/compact` keeps only a **lossy summary** of the prior turns, so write anything load-bearing into the artifact first. Either way the reset is a user-consented conversational step: the orchestrator issues the `/clear` (or `/compact`) only after the user accepts the offer, then re-reads the advisory's named files and continues.

**Escalation — leaning harder on the offer.** The offer is **gate-triggered always**, but its *tone* scales with the pressure proxies the orchestrator can actually observe: this phase's accumulated pass/turn count, the approximate elapsed session length, and whether a `/compact` has already fired this session. A live context-percentage gauge is **not** reliably observable, so it never drives the logic — the gate event triggers the offer, and those proxies only modulate how strongly it is recommended.

**Pre-reset check (before resetting at a gate):** confirm the phase's `## Approval` checkbox is ticked, and that any decisions made in conversation are actually reflected in the artifact. Don't rely on memory — read the artifact.

**Phase-4 / Implement completion-gate offer.** The SDD reset points are the **Specify → Design → Tasks** approvals plus the **Phase-4 / Implement completion gate** — Implement is the longest, most context-hungry phase, so the reset offered the moment it completes is the highest-value one. Confirm Phase-4 completion with the manual completion checklist (all task checkboxes ticked; all Summary-table statuses `Done`; both the `## Implementation Deviations` and `## TDD Exceptions` ledgers resolved; the final `tasks.md` re-stamp coherent — plain `--approve tasks`, or `--approve tasks --task-tick` for a pure-tick completion), **not** the Tasks-phase `## Approval` checkbox, which was ticked before implementation began; mid-implementation is **not** a clean reset point. The completion-gate `RESET-CHECKPOINT:` advisory is deliberately list-free and framed as "gate checks passed, not overall completion": it confirms this run's checks, not that the feature is wholly done, and immediate post-completion housekeeping may still benefit from the current context — so weigh that before accepting. (The `--completion-gate` CLI flag is unrelated: it only audits that `**Tests:**`-named tests exist, the R5 test-existence audit.)

This section promotes the `references/hash-and-cascade.md` § "Entering the Workflow Mid-Stream" path into a **proactive, first-class context-management practice** you are told about in advance — not only a crash-recovery procedure.

## Validation Before Approval

Each document must pass validation before approval:

- All required sections present
- No `[TBD]`, `TODO`, `FIXME`, `???` markers
- No unchecked open questions (`- [ ] Q1:`)
- Previous phase approved (for Design and Tasks)

## Quick Commands

| User Says | Start At |
|-----------|----------|
| "Create a spec for X" | Phase 1 — Specify |
| "Design this feature" | Phase 2 — Design (needs spec) |
| "Break this into tasks" | Phase 3 — Tasks (needs design) |
| "Implement task T1" | Phase 4 — Implement (needs tasks) |
| "Start SDD for X" | Phase 1 — Specify |

<!-- CPD-START -->
## Cross-Project Derivation

Most projects are single-repo: one `blueprint/PLAN.md` drives one `specs/` tree. **Cross-Project Derivation (CPD)** is the exception — it binds one repo's *master feature* to its *derived implementation* in a **different** repo, stretching the `PLAN → spec` handoff across a repo boundary. A *master* project (e.g. `residents`) defines a feature whose work is delegated to a *derived* project (e.g. `vps-edge`): the master `### F<n>` row carries `**Implemented by:** <derived-project>`, and the derived repo implements it as a normal SDD cycle in a specially-named directory.

**Derived directory form.** A derived feature lives in `specs/<project>--F<n>-<slug>/`, where `<project>` is the master-project alias, `F<n>` is the master's own feature number, and `--` is the unambiguous sentinel (the slug grammar forbids consecutive hyphens). Example: `specs/residents--F7-resident-sync/`. Its `spec.md` carries `**PLAN feature identifier:** ` + `` `n/a` `` (it is not a native feature of the derived repo's PLAN) plus two provenance fields: `**Derived from:** ` + `` `<project>:F<n>` `` (the master qualified id, the authoritative join key) and `**Master contract hash:** ` + `` `<hash>` `` (the master feature's contract hash at bind time, or the literal `` `unbound` `` until the first reconcile stamps it). The derived directory is excluded from the derived repo's own local PLAN coverage walk — it belongs to `reconcile`, not to that repo's PLAN.

**Reconcile beats.** `reconcile` is the only cross-repo checker; standalone validation in each repo never reaches across the boundary. It runs only when both repos are present (located via `.sdd/projects.json`) and checks bijection (every master `Implemented by` has exactly one matching derived dir and vice-versa), contract drift (the master feature's current contract hash vs. the derived spec's stored `**Master contract hash:**`), and surfaces open Upstream Change Requests. A missing or unconfigured sibling is a WARN-skip, never a FAIL. Prompt the user to run `reconcile` at two deterministic beats: **after the master's `--approve plan`** (the master feature may have changed) and **after a derived feature ships** (stamp its first real hash if still `unbound`; confirm the bijection). A shipped feature still on `unbound` gets a distinct, louder WARN, since it has no drift detection until stamped.

**UCR flow (soft-halt).** When a derived feature discovers the *master* feature is wrong, it does not hard-halt (no atomic two-repo edit exists, and the master may be owned by someone else). Instead: (1) **record** an Upstream Change Request as a `## Upstream Change Requests` stanza entry in the derived `spec.md` — id, `**Target:**` (the master qualified id), `**Status:**` (`open`/`applied`/`withdrawn`), `**Proposed change:**`, `**Rationale:**`; this is the single source of truth, no separate marker file in v1; (2) **proceed** against the current master with an `## Accepted Divergences`-style note rather than blocking; (3) **surface** the open UCR at the next reconcile, against the master; (4) the master author **applies** the change through the master's normal approve cycle (producing a new contract hash) and marks the UCR `applied`; (5) the next reconcile sees the derived spec's stored hash is now stale → drift WARN → the derived author **re-specs and re-stamps**, closing the loop. This mirrors the same-repo PLAN→spec cascade, one altitude up.

<!-- CPD-END -->

## Principles

- **Specs are the source of truth.** Code follows specs, not the other way around.
- **Changes flow forward.** If requirements change, update spec.md first, then cascade to design and tasks.
- **Tasks are atomic.** Each task should be independently verifiable.
- **Tests come first.** On a **python/java stack** this is a hard MUST for every code-touching Phase-4 task: write the failing test first, run it red, then implement (green), then refactor — skipping the test-first cycle is permitted only when logged in the `## TDD Exceptions` ledger. On a **`generic`/architecture-neutral stack** (no test harness) the alternative applies: write the task's concrete Verification check first, then do the work. (The validator's R3 gate FAILs a code-touching python/java task that names no test; the R5 completion gate checks the named tests actually exist.)
- **Human decides.** Claude proposes, the user approves.
