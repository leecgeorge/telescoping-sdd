<!--
SHARED REFERENCE — keep in sync with the spec-driven-dev copy at
skills/spec-driven-dev/references/workflow-overview.md. Edits to shared content must be mirrored in BOTH copies.

Intentional asymmetries vs the sibling (do NOT "sync" these away):
- Phase model is skill-specific: blueprint has 3 phases (Scope/Architecture/Plan); spec-driven-dev has 4 (Specify/Design/Tasks/Implement) — diagram, headings, and phase count differ by design.
- spec-driven-dev's Phase 4 (Implement) is SDD-only: extra Phase-Summary row, "Phase 4 executed directly" note, a 4th review gate, and the "Implement task" quick command have no blueprint counterpart.
- Terminal Phase-3 artifact differs: PLAN.md (blueprint) vs tasks.md (spec-driven-dev), along with the File Layout tree (flat blueprint/ vs specs/F<n>-<slug>/).
- Blueprint-only doctrine sections (Handoff to Feature Development, Bound-Spec Immutability, Closed-Feature-Row Immutability) are PLAN/CFC-producer rules, intentionally absent from spec-driven-dev (the consumer).
Otherwise the copies differ only cosmetically (phase names, filenames, example feature names, quick-command phrasing, Principles wording).
-->

# Project Blueprint — Workflow Overview

## The Three Phases

```
  SCOPE             ARCHITECTURE       IMPLEMENTATION PLAN
 ┌──────────┐     ┌────────────────┐    ┌──────────┐
 │ SCOPE.md │────>│ARCHITECTURE.md │───>│ PLAN.md  │───> Feature Development
 └──────────┘     └────────────────┘    └──────────┘     (spec-driven-dev)
      │                  │                   │
   REVIEW             REVIEW              REVIEW
   GATE               GATE                GATE
```

**Discoveries flow back, too.** `Architecture/Plan ⤴ Scope — discovery → upstream edit`: a discovery during a later phase that contradicts an approved upstream is reconciled by editing the upstream *first* (the single highest-affected document) and letting the cascade reconcile downstream — not by editing forward only, and never by co-editing the chain. See `references/hash-and-cascade.md` § "Upstream backport — same-repo discovery".

## Phase Summary

| Phase | Input | Output | Drafted By | Key Question |
|-------|-------|--------|------------|-------------|
| Scope | User's project idea | `SCOPE.md` | `project-spec-analyst` subagent | **What** are we building and why? |
| Architecture | Approved scope | `ARCHITECTURE.md` | `project-architecture-analyst` subagent | **How** does it fit together? |
| Implementation Plan | Approved architecture | `PLAN.md` | `project-plan-analyst` subagent | **What** features, in what order? |

Each phase delegates document drafting to the corresponding subagent via the Agent tool. The agent self-reviews its draft before returning. The calling Claude then performs its own review, runs cross-document consistency checks, validation, and approval gates.

## File Layout

```
project-root/
└── blueprint/
    ├── SCOPE.md          # Phase 1 output
    ├── ARCHITECTURE.md   # Phase 2 output
    └── PLAN.md           # Phase 3 output
```

## Review Gates

Between each phase, stop and ask the user:

1. After Scope: "Here's the scope. Does this capture the project you want to build?"
2. After Architecture: "Here's the architecture. Does this structure make sense?"
3. After Implementation Plan: "Here's the plan. Is this the right set of features and build order?"

## Validation Before Approval

Each document must pass validation before approval:

- All required sections present
- No `[TBD]`, `TODO`, `FIXME`, `???` markers
- No unchecked open questions (`- [ ] Q1:`)
- Previous phase approved (for Architecture and Plan)

## Quick Commands

| User Says | Start At |
|-----------|----------|
| "Plan a new project" | Phase 1 — Scope |
| "Create a blueprint for X" | Phase 1 — Scope |
| "Design the architecture" | Phase 2 — Architecture (needs scope) |
| "Create an implementation plan" | Phase 3 — Plan (needs architecture) |
| "What features should I build first?" | Phase 3 — Plan (needs architecture) |

## Handoff to Feature Development

Once the blueprint is complete:

```
PLAN.md Feature List          spec-driven-dev
┌─────────────────────┐      ┌─────────────────────┐
│ F1: User Auth       │─────>│ specs/F1-user-auth/  │
│ F2: Data Models     │─────>│ specs/F2-data-models/│
│ F3: API Endpoints   │─────>│ specs/F3-api-endpoints/ │
│ F4: Dashboard       │─────>│ specs/F4-dashboard/  │
└─────────────────────┘      └─────────────────────┘
```

Each feature becomes a candidate for `/spec-driven-dev`, following the implementation order from PLAN.md.

## Bound-Spec Immutability — Implications of PLAN Edits

Once a feature has **shipped** (Phase 4 complete in `spec-driven-dev`: all phases approved, all task boxes ticked, and `tasks.md`'s `## Approval` hash matches current content), its `spec.md` becomes a **historical commitment** to the PLAN state at ship time. When you edit PLAN.md mid-stream and the edit affects a feature whose spec has shipped, you must NOT plan for that shipped spec to be edited in-place to absorb your change — that would falsify the audit trail (the spec would claim to have committed to text it didn't commit to) and break load-bearing tag-binding semantics (`[CFC-N]` tags point at "the contract this feature shipped against," not "the contract as it now reads").

**Before Phase 4 completes**, the feature is *in flight* — its spec, design, and tasks can all be amended in place via SDD's existing hash-and-cascade flow, because no code has shipped yet and amendment is cheap. The immutability rule applies only after the feature ships.

### Remediation paths for shipped features

When a PLAN edit creates drift on a shipped feature, choose one of:

1. **Create a new feature** in `## Feature Breakdown` scoped to the remediation work. Example: a Cross-Feature Contract's text is tightened after F11 shipped against the old version; PLAN gains a new `F37: <CFC-N> remediation for F11` feature whose scope is "bring F11's code paths into compliance with the updated contract." F37 runs through its own SDD cycle binding to the updated PLAN state.
2. **Fold the remediation into an in-flight unbound spec.** If an in-progress feature whose Phase 4 has not yet completed can reasonably absorb the remediation work, expand that spec's scope to include it.

The shipped spec conventionally receives an `## Accepted Divergences` entry at the bottom documenting the drift and pointing at the chosen remediation. Authors who fix typos in non-commitment-content sections (`## Objective`, `## Out of Scope`, `## Open Questions`, `## Accepted Divergences`, comments, `## Approval`) do so at their own discretion — v1 does not mechanically distinguish typo fixes from substantive amendments on a shipped spec. Substantive edits to commitment-content sections (`## Requirements`, acceptance criteria, design decisions) on a shipped spec are immutability violations by doctrine; v1 detects the *consequence* (orphan-tag drift on a re-stamped spec) but not the violation directly. The per-artifact structured-content hash that would mechanically distinguish typo fixes from amendments is deferred to v2.

### What this means at PLAN-edit time

When you edit PLAN.md, consider downstream impact **at edit time**, not at validation time. The validator will flag mechanically-detectable drift (currently: Cross-Feature Contract content drift, via the `orphaned-stale-content` orphan-tag scan in `validate_blueprint.py`), but most PLAN edits don't have explicit tag-binding and so rely on author discipline.

Edits that may create drift on shipped features:

- Cross-Feature Contract content edits (mechanically detected — the validator will surface affected specs and offer to scaffold a remediation feature)
- Feature Dependencies graph changes (no mechanical detection in v1 — author discipline)
- Milestone reassignment (no mechanical detection in v1 — author discipline)
- MVP / Post-MVP boundary moves (no mechanical detection in v1 — author discipline)
- Implementation Order changes affecting features whose design assumed a prior order (no mechanical detection in v1 — author discipline)
- Promotion of an `## Acknowledged Risk` to a feature (no mechanical detection in v1 — author discipline)

For each affected shipped feature, plan the remediation work as part of your PLAN edit. Don't defer to "the validator will catch it" — for the non-CFC cases, the validator won't.

### Mechanical detection is opportunistic

Cross-Feature Contracts are the only PLAN element with explicit tag-binding in v1 (`[CFC-N]` tags carried by feature specs). The orphan-tag scan in `validate_blueprint.py` mechanically detects three drift subtypes on CFC tags: `orphaned-missing` (CFC removed), `orphaned-departed` (feature removed from Participating list), and `orphaned-stale-content` (CFC contents changed since the spec's last approval). Future tag-binding classes can extend mechanical coverage incrementally (dependency tags, milestone tags, etc.) if real projects surface drift evidence at those levels — the doctrine doesn't change.

### Doctrine is producer-only

This rule constrains PLAN-author behavior at edit time — it is not enforced by `spec-driven-dev`. SDD does not refuse to edit a bound spec; within an SDD cycle the author has full edit control over their artifacts and SDD's hash-and-cascade flow handles whatever the author does. The "don't amend shipped specs to absorb PLAN drift" rule is a PLAN-author discipline, surfaced by `validate_blueprint.py`'s `orphaned-stale-content` WARN at validation time (not by `validate_spec.py`). v1 detects drift mechanically; remediation is author-driven — the user reads the WARN, chooses a remediation path (new feature, fold into an in-flight unbound spec, or `## Accepted Divergences` entry), and applies it by hand. Interactive remediation prompts and validator-driven scaffolding are deferred to v2 of the CFC spec; see `documentation/CFC.md § Deferred to v2`.

## Closed-Feature-Row Immutability — PLAN-row analog of bound-spec immutability

Bound-Spec Immutability (above) governs *shipped feature artifacts* downstream of PLAN (`spec.md`, `design.md`, `tasks.md`). Closed-Feature-Row Immutability is the same doctrine one altitude up: the **`### F<n>:` row inside PLAN.md itself** — its title and its bullet content — is byte-frozen once F<n>'s milestone checkbox in `## Milestones` flips to `[x]`. The row is a historical commitment to the feature as it was authored at milestone-close time.

**The two altitudes:**

| Altitude | What's immutable | Trigger | Detection |
|---|---|---|---|
| `spec.md` / `design.md` / `tasks.md` | Phase-4 complete (shipped) | All tasks ticked + content hash matches | `validate_blueprint.py orphaned-stale-content` WARN (CFC tag binding only) |
| PLAN `### F<n>:` row + bullets | Milestone checkbox `[x]` | `^- \[[ xX]\] F<n>\b` in `## Milestones` (closed iff the matched checkbox is `[x]`) | None — author + synthesizer discipline |

The remediation pattern is identical at both altitudes: when a PLAN update (or a CFC content edit, or a panelist proposal at panel-review time) creates an obligation that *would* require editing a closed feature, route the obligation to a new amending feature in `## Feature Breakdown`, or to an in-flight unbound feature that can absorb it, or to the relevant `M*N Deliverable` narrative explaining who actually ships the artefact. Never edit a `[x]`-bound feature row in place — not even to add a single AC bullet that cross-references a CFC. The deferred-amendment-avoidance pattern preserves the audit trail.

### Why this lives here

A panel-review synthesizer pass on a project with `[x]`-checked features can be tempted to apply a panelist-proposed fix that edits a closed feature row, especially under cap-pressure. The synthesizer self-check in `references/panel-review.md` carries the operational gate (check (e), Phase 3 only) — but the *doctrine* lives here because it also governs hand-edits to PLAN.md outside the panel loop. Any author editing PLAN.md is bound by this rule; the panel-review check is one enforcement site, not the source of truth.

### Lookup mechanic for the panel-review synthesizer

When the synthesizer is deciding whether a proposed fix may edit content under an `### F<n>:` heading, locate F<n>'s milestone checkbox deterministically: search `## Milestones` for a line matching `^- \[[ xX]\] F<n>\b` (the row that lists F<n> as a deliverable of a milestone, regardless of which `### Milestone N:` block contains it). If F<n> appears in multiple milestone blocks, take the latest by milestone number. If the matched checkbox is `[x]`, the fix is editing a closed feature — halt and re-route per the remediation paths above. If F<n> is not found in any milestone block, the feature has not been milestoned yet and the row remains editable; proceed.

### Producer-only — same as Bound-Spec Immutability

Closed-Feature-Row Immutability constrains PLAN-author and panel-review-synthesizer behaviour at edit time. There is no validator gate in v1 — no per-feature-row content-hash tracking, no `--approve plan` check that compares row content against a prior approval baseline. A per-feature-row hash check (mirroring `cfc_parser.py`'s `structured_content_hash` machinery) is deferred and would only be built if doctrine-miss recurs after the instruction-document fixes land. The instruction-document gates (panelist prompt constraint, synthesizer self-check (e), and the cap-pressure caveat in panel-review.md's loop documentation) catch the violation at proposal/disposition time, before any edit lands; a downstream validator would only catch it after the fact.

<!-- CPD-START -->
## Cross-Project Derivation

Most projects are single-repo: one `blueprint/PLAN.md` drives one `specs/` tree. **Cross-Project Derivation (CPD)** is the exception — it binds one repo's *master feature* to its *derived implementation* in a **different** repo, stretching the `PLAN → spec` handoff across a repo boundary. A *master* project (e.g. `residents`) defines a feature whose work is delegated to a *derived* project (e.g. `vps-edge`): the master `### F<n>` row carries `**Implemented by:** <derived-project>`, and the derived repo implements it as a normal SDD cycle in a specially-named directory.

**Derived directory form.** A derived feature lives in `specs/<project>--F<n>-<slug>/`, where `<project>` is the master-project alias, `F<n>` is the master's own feature number, and `--` is the unambiguous sentinel (the slug grammar forbids consecutive hyphens). Example: `specs/residents--F7-resident-sync/`. Its `spec.md` carries `**PLAN feature identifier:** ` + `` `n/a` `` (it is not a native feature of the derived repo's PLAN) plus two provenance fields: `**Derived from:** ` + `` `<project>:F<n>` `` (the master qualified id, the authoritative join key) and `**Master contract hash:** ` + `` `<hash>` `` (the master feature's contract hash at bind time, or the literal `` `unbound` `` until the first reconcile stamps it). The derived directory is excluded from the derived repo's own local PLAN coverage walk — it belongs to `reconcile`, not to that repo's PLAN.

**Reconcile beats.** `reconcile` is the only cross-repo checker; standalone validation in each repo never reaches across the boundary. It runs only when both repos are present (located via `.sdd/projects.json`) and checks bijection (every master `Implemented by` has exactly one matching derived dir and vice-versa), contract drift (the master feature's current contract hash vs. the derived spec's stored `**Master contract hash:**`), and surfaces open Upstream Change Requests. A missing or unconfigured sibling is a WARN-skip, never a FAIL. Prompt the user to run `reconcile` at two deterministic beats: **after the master's `--approve plan`** (the master feature may have changed) and **after a derived feature ships** (stamp its first real hash if still `unbound`; confirm the bijection). A shipped feature still on `unbound` gets a distinct, louder WARN, since it has no drift detection until stamped.

**UCR flow (soft-halt).** When a derived feature discovers the *master* feature is wrong, it does not hard-halt (no atomic two-repo edit exists, and the master may be owned by someone else). Instead: (1) **record** an Upstream Change Request as a `## Upstream Change Requests` stanza entry in the derived `spec.md` — id, `**Target:**` (the master qualified id), `**Status:**` (`open`/`applied`/`withdrawn`), `**Proposed change:**`, `**Rationale:**`; this is the single source of truth, no separate marker file in v1; (2) **proceed** against the current master with an `## Accepted Divergences`-style note rather than blocking; (3) **surface** the open UCR at the next reconcile, against the master; (4) the master author **applies** the change through the master's normal approve cycle (producing a new contract hash) and marks the UCR `applied`; (5) the next reconcile sees the derived spec's stored hash is now stale → drift WARN → the derived author **re-specs and re-stamps**, closing the loop. This mirrors the same-repo PLAN→spec cascade, one altitude up.

<!-- CPD-END -->

## Principles

- **Scope before structure.** Define what you're building before deciding how.
- **Architecture before features.** Understand the system before breaking it into parts.
- **Decisions are explicit.** Every choice is documented with rationale.
- **Risks surface early.** Identify what could go wrong before committing to a build order.
- **Features feed into specs.** The blueprint's output is the input for spec-driven development.
- **Human decides.** Claude proposes, the user approves.
