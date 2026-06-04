# Cross-Project Derivation (CPD)

> **Provenance note.** Unlike `CFC.md` (which was *reconstructed from shipped code*), this document is a **forward design spec authored before implementation**. Nothing described here is built yet: every regex literal, field name, file path, command name, and message string below is a **proposal** to be refined and finalized by the `spec-driven-dev` cycle that consumes this document. Treat mechanical specifics as design intent, not observed fact. Where a detail is deliberately deferred to the SDD Design phase it is marked *(design-phase)*.

> **Specification-phase update (decisions locked).** The `spec-driven-dev` cycle that consumed this document (`specs/cross-project-derivation/`) locked four v1 deltas that supersede the matching prose below; the inline sections (notably `## The master-update flow` and `## Deferred to v2`) are fully reconciled to these at implementation time (tracked by the spec's Success Criteria):
> 1. **UCR is stanza-only.** The Upstream Change Request lives solely in the derived `spec.md` `## Upstream Change Requests` stanza (single source of truth); the collectable `.sdd/` UCR marker is **deferred to v2**.
> 2. **Drift detection is deterministic-prompt-only.** v1 relies on the skills prompting `reconcile` at defined beats (after master `--approve plan`, after a derived ship); a **durable cross-repo staleness signal is deferred to v2** (see `## Topology and scaling` for why this becomes load-bearing at scale).
> 3. **`unbound` bootstrap sentinel.** `**Master contract hash:**` accepts the literal `unbound` so a derived spec validates before its sibling is reachable; the first real hash is stamped from `reconcile --print-link`.
> 4. **Topology boundary made explicit** — see the new `## Topology and scaling` section and **CPD-D11**.

A **Cross-Project Derivation** binds a single **master feature** (defined in one repo's `blueprint/PLAN.md`) to its **derived implementation** (an SDD cycle in a *different* repo). It exists because the two-tier methodology (`project-blueprint` → `spec-driven-dev`) assumes one repo, one PLAN, one `specs/` tree — and real programs span repos: a *master* project (e.g. `residents`) defines features whose implementation is *delegated* to a *derived* project (e.g. `vps-edge`). CPD is the same `PLAN → spec` handoff stretched across a repo boundary, plus a reciprocal back-pointer so neither side is blind.

CPD is **mechanical drift/link detection across an eventually-consistent repo boundary, not cascade** — the same v1 doctrine CFC chose, here *forced* by the fact that two git repos have no atomic cross-repo commit.

---

## Motivation

The driving case (codenamed the **residents↔vps-edge** relationship): `residents` is the single "plan driver." Some `residents` features are not implemented in `residents` at all — they drive work in `vps-edge`. Two failure modes today:

1. **The derived side is blind.** A `vps-edge` SDD cycle that implements a `residents` feature has no way to record *where the feature came from*. Its `**PLAN feature identifier:**` can only resolve against a *local* PLAN, or be `n/a`.
2. **The master side is blind.** A `residents` `### F<n>` entry has no way to record *who is implementing it*.

The requirement, stated by the project owner: cross-project should *feel like* same-project. Inside one repo, when an SDD phase discovers the PLAN is wrong it suggests a PLAN edit and cascades forward; the panel's `[upstream]` tag halts rather than papering over an upstream problem. CPD must reproduce that reflex **across the repo boundary** — when the derived spec finds the master feature wrong, it suggests a *master update*.

### Why this is CFC one altitude up

CFC's definition is "an invariant committed at PLAN time that spans multiple features whose individual SDD cycles never see the whole set." Replace *features* → *repos* and the spec is verbatim. The doctrinal answers CFC already settled therefore transfer:

- **Detect, don't cascade.** Two separate git repos cannot be edited atomically; a master change and its derived catch-up land in different PRs at different times. Synchronous cascade is not merely out of scope — it is *impossible*. The eventually-consistent reality makes "detect drift, remediate by hand" the only correct model, not a compromise.
- **Copy verbatim + hash the copy.** CFC makes each feature copy the `Per-feature AC` line verbatim and detects drift via a content hash. CPD replicates the master-feature *contract hash* into the derived spec, so each repo validates **standalone** and a separate reconcile step compares hashes only when both repos are present.
- **Advisory, out-of-band store.** `.sdd/architecture.json` (single shared module, single writer, defensive reads, *deliberately kept out of the hash machinery*) is the precedent for the cross-repo project registry.

---

## The single-root obstacle

Three load-bearing assumptions bake in "one repo, one plan"; CPD must work around each without breaking single-repo behaviour:

| Assumption | Where | CPD response |
|---|---|---|
| `find_project_root` walks **up** to the nearest `blueprint/PLAN.md` | `validate_spec.py` | Cross-repo references are never resolved by walking up; the derived spec carries a *replicated* master-contract hash and the qualified id, and `.sdd/projects.json` locates the sibling for reconcile. |
| `F<n>` is **repo-local** (resolved only against the local `## Feature Breakdown`, P7) | consumer | A new qualified id `<project>:F<n>` and a dedicated `**Derived from:**` line carry provenance, orthogonal to the local identifier (which stays `n/a` on a derived spec). |
| CFC participants are repo-local `F<n>` lists (`^F\d+(, F\d+)*$`) | `cfc_parser.py` | CPD does **not** extend CFC's participant grammar; it is a separate, simpler 1:1 link carried by dedicated fields, not by `[CFC-N]`-style tags. |

---

## Concepts and vocabulary

- **Master project** — the single plan driver (e.g. `residents`). Owns the **what** (feature definition + acceptance criteria).
- **Derived project** — implements a delegated feature via its own SDD cycle (e.g. `vps-edge`). Owns the **how** (design / tasks / code).
- **Master feature** — a `### F<n>` entry in the master's `PLAN.md` carrying `**Implemented by:** <derived-project>`.
- **Derived feature** — a `specs/<master>--F<n>-<slug>/` SDD cycle in the derived project, carrying `**Derived from:** <master>:F<n>`.
- **Derivation link** — the reciprocal (master `Implemented by` ↔ derived `Derived from`) 1:1 pair.
- **Single-master constraint (CPD-D1).** There is exactly one plan driver per derivation link. CPD models master→derived delegation with a back-reference; it does **not** model peer-to-peer contract negotiation between two co-equal masters. (A feature needing work in *both* repos is modelled as two master features — one local, one delegated — keeping every link 1:1.)

---

## Data model

### Master side (`residents/blueprint/PLAN.md`, per feature — optional)

```
### F7: Resident sync contract
- **Description:** …
- **Component:** …
- **Acceptance Criteria:**
  - …
- **Implemented by:** vps-edge
```

`**Implemented by:**` names only the **derived project alias** — *not* a derived feature number (CPD-D4). The derived feature's number is the master's own `F<n>`; naming a separate derived number would falsely imply the feature is native to the derived project. Absence of the line = implemented locally (the normal case). v1 permits exactly one project (one-to-one).

### Derived side (`vps-edge/specs/residents--F7-resident-sync/spec.md`)

```
- **PLAN feature identifier:** `n/a`         ← not a native vps-edge feature
- **Derived from:** `residents:F7`           ← the upstream/provenance pointer
- **Master contract hash:** `a1b2c3…`        ← residents F7's contract hash at bind time (the replicated copy)
```

- **`**Derived from:**`** — backtick-wrapped `<project>:F<n>`, mirroring the existing `**PLAN feature identifier:**` line style. This is the join key's authoritative source.
- **`**Master contract hash:**`** — SHA-256 (64-hex) over the master feature's *contract* — proposed *(design-phase)*: `json.dumps({"feature": n, "description": <norm>, "acceptance_criteria": [<norm>, …]}, sort_keys=True)` using `cfc_parser.normalize_for_hash`, **excluding** title, `Component`, and the `Implemented by` line (so adding/removing the pointer never self-triggers drift). This is the replicated bind-time baseline reconcile compares against. **Bootstrap sentinel (locked v1).** The literal `` `unbound` `` is also an accepted value, so a derived spec validates before its sibling is reachable; the first real 64-hex hash is stamped from `reconcile --print-link`. A *shipped* feature still on `unbound` has no drift detection and earns reconcile's louder `shipped-but-unbound` WARN.

### The join key

The derived directory name `residents--F7-*` **is** the join key. `**Implemented by:** vps-edge` tells reconcile *which repo* to look in; the dir name + `**Derived from:**` line identify *which feature*. **1:1 falls out for free:** master feature numbers are unique within a PLAN, so two delegated features can never produce the same `<master>--F<n>` prefix; reconcile confirms exactly one matching derived dir exists.

### Shared qualified-id grammar (CPD-D9)

A new dependency-free module (working name `scripts/project_link.py`) owns the `<project>:F<n>` and `<project>--F<n>-<slug>` grammars and the link data model, so the master validator, the derived validator, and reconcile cannot drift on format — the same anti-drift discipline `cfc_parser.py`, `arch_config.py`, and `spec_dirname.py` already apply. A contract test pins producer/consumer/reconcile symmetry. Project alias grammar = lowercase kebab `[a-z0-9]+(-[a-z0-9]+)*` (same as a slug).

---

## The directory grammar — a third form (CPD-D3)

`spec_dirname.py` today recognizes two forms: **bound** `F<n>-<slug>` and **standalone** `<slug>` (`classify_dirname` → `bound | bare | standalone | invalid`). CPD adds a third: **`derived`**.

```
residents--F7-resident-sync
└───┬────┘ │└┬┘ └─────┬────┘
 master    │ master    local slug
 project   │ feature #
        sentinel "--"
```

Proposed grammar *(design-phase)*: `^([a-z0-9]+(?:-[a-z0-9]+)*)--F([1-9]\d*)-([a-z0-9]+(?:-[a-z0-9]+)*)$`.

- **Why `--` is an unambiguous sentinel.** The slug grammar `[a-z0-9]+(-[a-z0-9]+)*` forbids consecutive hyphens, so `--` can appear in neither a project alias nor a slug. The parse is unambiguous even when the master project alias itself contains single hyphens (`vps-edge--F7-…`).
- **`classify_dirname` gains a `derived` branch.** `check_dir_identifier` gains a derived branch that cross-checks the dir's `<project>--F<n>` against the spec's `**Derived from:** <project>:F<n>` line (requiring local `**PLAN feature identifier:** n/a`), instead of the local PLAN. New FAIL code: `derived-provenance-mismatch`.
- **Out-of-band from every content hash (preserved).** Like the existing forms, the derived directory name is a naming contract only — renaming never invalidates an approval or content hash.
- **Collision-proof.** `residents--F7-resident-sync` cannot collide with a native `vps-edge` feature (`F7-…` or a bare slug), which is the concrete bug a plain `F7-` or bare-slug derived name would cause.

### Coverage-walk exclusion (CPD-D8)

The derived project's **own** `validate_blueprint.py` coverage walk (`walk_specs` / `classify_dirname`) must **exclude** `derived` dirs from local PLAN coverage — derived features belong to reconcile, not to the derived project's PLAN. (Today a `--`-containing name classifies as `invalid` and earns a stray WARN; the `derived` category must be filtered out of the local walk.)

---

## The project registry — `.sdd/projects.json` (CPD-D7)

Extends the `.sdd/` store precedent. Proposed shape *(design-phase)*:

```json
{
  "schemaVersion": 1,
  "thisProject": "vps-edge",
  "role": "derived",
  "siblings": [
    { "name": "residents", "role": "master", "path": "../residents" }
  ]
}
```

- Paths are **relative** (resolved from the project root) and overridable by flag/env, because absolute paths differ per machine and per CI.
- **Defensive reads, never fatal.** A missing/unparseable/unknown-schema registry yields "no sibling configured"; standalone validation does not require it. Mirrors `arch_config.read_arch_config`.
- **Advisory and out-of-band** from all content hashes and both `--approve` gates.

---

## Reconcile (CPD-D2)

A new shared command (working name `scripts/reconcile.py`) runs **only when both repos are present**, located via `.sdd/projects.json`. It is the *only* cross-repo checker; standalone validation in each repo never reaches across. Checks:

1. **Reciprocity / bijection.** Every master `**Implemented by:** <derived>` has exactly one matching derived dir `<master>--F<n>-*` whose `**Derived from:**` points back; every derived dir resolves to an existing master feature that names this project. Dangling or one-sided links → FAIL.
2. **Contract drift.** Recompute the master feature's current contract hash; compare to the derived spec's stored `**Master contract hash:**`. Mismatch → WARN *"master feature `residents:F7` changed since `vps-edge` bound to it"* — the cross-repo twin of CFC's `orphaned-stale-content`.
3. **Open upstream-change requests** (see below) surfaced against the master.

**Degradation (CPD-D7).** A missing/unconfigured sibling → WARN-skip with a deferred reminder, never FAIL. **Triggering.** Both skills *prompt* to run reconcile at natural beats — after master `--approve plan`, after a derived ship — when a sibling is configured and present; reconcile is never silently skipped when it could have run.

---

## The master-update flow — soft-halt (CPD-D5)

The reflex "derived spec finds master wrong → suggest a master update" cannot be literal across repos: there is no atomic two-repo edit, the master repo may be absent or owned by someone else. A *hard* halt of the derived SDD (the literal same-project behaviour) would stall all derived work on the master's schedule — operationally hostile. **The locked decision is soft-halt:**

1. **Record (stanza-only in v1).** The derived SDD raises an `[upstream]`-class concern targeting the master and records an **Upstream Change Request (UCR-N)** as a `## Upstream Change Requests` stanza in the derived `spec.md` (audit trail, travels in git): id, target `residents:F7`, proposed change, rationale, status (`open` / `applied` / `withdrawn`). This stanza is the **single source of truth**; reconcile reads UCRs directly from it. (Per the locked v1 decision above: the collectable `.sdd/` UCR marker that would mirror the stanza is **deferred to v2** — see `## v1 scope vs Deferred to v2`.)
2. **Proceed, with a divergence note.** The derived author is **not blocked**. They proceed against the *current* master with an explicit `## Accepted Divergences`-style note: *"specced against `residents:F7` @ `<hash>`; UCR-1 open."*
3. **Surface at reconcile.** With both repos present, reconcile reports open UCRs against the master: *"`vps-edge` has an open change request against your `F7`."*
4. **Apply in the master.** The human edits `residents` `F7` through its normal panel/approve cycle (new contract hash) and marks the UCR `applied`.
5. **Re-sync the derived side.** Next reconcile sees the derived `**Master contract hash:**` is stale → drift WARN → derived author re-specs / re-stamps → UCR closed. Symmetric with same-project PLAN→spec cascade.

> **Caveat.** Hash drift cannot distinguish "master changed *because of* this UCR" from "master changed for an unrelated reason" — both correctly trigger a re-check; the UCR only carries the rationale trail.

---

## Bound-spec immutability across the seam

The existing **Bound-Spec Immutability** doctrine extends across the repo boundary: once a derived spec (`residents--F7-*`) has *shipped*, the master must not silently rewrite `F7` to absorb a change. Cross-repo this is worse than in-repo — the master author may not know the derived feature shipped — so reconcile's drift WARN is the *only* detector, and the remediation is the same: a new amending master feature delegating a **new** derived feature (`residents--F12-*`), never an in-place edit of the shipped derived spec. Same doctrine, new instances.

**"Shipped" is the full three-artifact signal.** Whether a derived feature has *shipped* — and therefore whether a still-`unbound` master contract hash escalates to the louder `shipped-but-unbound` WARN rather than the quiet "needs first stamp" — is decided by `blueprint_common.is_shipped(spec_dir)`: `spec.md`, `design.md`, and `tasks.md` all approved (checkbox + matching hash) AND every task checkbox ticked. This predicate is relocated into the shared `blueprint_common.py` so `validate_blueprint.classify_spec` and `reconcile` both call the one definition (a shared script must not import a skill validator); `test_is_shipped_symmetry` pins the invariant that `is_shipped(spec_dir)` is true IFF `classify_spec` reaches `STATE_SHIPPED`, over the full three-artifact matrix.

---

## v1 scope vs Deferred to v2

**v1 ships** (detection + suggestion, mirroring CFC's detection-first staging):

- the shared `<project>:F<n>` / `<project>--F<n>-<slug>` grammar module + symmetry test;
- the `derived` directory form (`classify_dirname` + `check_dir_identifier` branch + local-coverage exclusion);
- the master `**Implemented by:**` field + standalone well-formedness;
- the derived `**Derived from:**` + `**Master contract hash:**` fields + standalone well-formedness;
- `.sdd/projects.json` + defensive resolution;
- `reconcile` (bijection + contract-drift + open-UCR surfacing);
- the soft-halt UCR record/proceed/re-sync loop.

**Deferred to v2:**

- **Auto-scaffolding** the derived spec stub when a master feature is delegated (provenance pre-filled).
- **Auto-applying** a master edit / auto-closing a UCR (v1 is author-driven, like CFC remediation).
- **Live filesystem dereference** (read the master PLAN directly instead of the replicated hash).
- **One-to-many** delegation (one master feature → several derived features/projects). v1 is strictly 1:1. (One of the *qualitative* limits in `## Topology and scaling`, distinct from the star topology v1 *does* scale to.)
- **A durable cross-repo staleness signal** — a `reconcile`-written record plus a `validate_spec` WARN when a derived spec's stored master hash is stale or was never reconciled. v1 relies on deterministic reconcile prompts instead; this is the lever that restores detection *coverage* at large fan-out (see `## Topology and scaling`).
- **The `.sdd/` UCR marker cache** — a collectable marker mirroring the derived spec's stanza. v1 is stanza-only (single source of truth).
- **A "portfolio" tier** — a third altitude above `project-blueprint` that decomposes a multi-repo program into per-repo blueprints and owns the cross-repo plan natively. The north star if cross-repo becomes the normal mode rather than a residents↔vps-edge special case.

---

## Topology and scaling

CPD's primitives are **per-link, not per-repo-pair**, and that single fact determines how it scales. Three topologies, three outcomes:

### Star — one master → N derived repos (v1 scales natively)

Each link stays 1:1 (`residents:F7→vps-edge`, `residents:F8→edge-cdn`, …); N derived repos is just N independent 1:1 links. Every primitive already absorbs N with no shape change:

- **Registry** — `.sdd/projects.json` carries a `siblings` **array** (CPD-D7); N siblings is the native shape, not a retrofit.
- **Directory grammar** — `<master>--F<n>-<slug>` is namespaced by the master project, so one derived repo can hold dirs from several different masters without collision (CPD-D3).
- **Drift** — each derived spec stores its own bind-time `**Master contract hash:**`; N links → N independent comparisons, no shared state.
- **Bijection** — `**Implemented by:** <project>` plus the prefix join key make each link independently checkable; a stray or duplicate derived dir surfaces as a one-sided link (CPD-D4).
- **UCR / master-update** — a per-derived-spec stanza; N repos → N independent UCR sets, each surfaced against the master.

**The one thing that weakens with N is detection *coverage*.** `reconcile` only checks siblings that are *present* (CPD-D7 WARN-skips the rest). At large N you rarely have all repos checked out at once, so a *complete* bijection/drift sweep is rare — the design never lies (it WARN-skips and states nothing was checked), but the "neither side is blind" guarantee gets proportionally softer. The **deferred durable staleness signal** (`## Deferred to v2`) is the lever that restores it at scale; until then, large fan-out also carries an operational tax (N registries to keep mutually consistent; orchestrating who runs reconcile with what checked out). At N≈1–2 this is immaterial; by N≈10 the v2 signal is load-bearing rather than optional.

### Fan-out — one master feature → N implementations (v2)

`**Implemented by:**` names exactly one project and the join key is 1:1, so one-feature-to-many is out of v1 by construction. The hard part is not the pointer but the **cascade**: one master edit would have to fan out to N stale derived specs — precisely the propagation v1 deliberately omits (CPD-D10). Deferred.

### Chains & mesh — transitive or multi-master (v2 / portfolio tier)

The producer role (`validate_blueprint.py` parsing `**Implemented by:**`) and the consumer role (`validate_spec.py` handling derived dirs) are orthogonal, so a single repo *can* mechanically be both a master and a derived project at once — each link validates independently. But CPD has **no transitive integrity**: `reconcile` never composes `X → me → Y`, so drift does not propagate along a chain, and an arbitrary multi-master mesh is outside the single-master constraint (CPD-D1). Modelling transitivity is portfolio-tier work (`## Deferred to v2`).

### Summary

| Topology | In v1? | Why |
|---|---|---|
| **Star** — 1 master → N derived repos, each link 1:1 | **Yes** | every primitive is per-link; `siblings` is already a list. Detection *coverage* softens with N — the v2 durable-staleness signal is the fix. |
| **Fan-out** — 1 master feature → N implementations | No (v2) | needs the edit-cascade v1 omits (CPD-D10). |
| **Chains / mesh** — transitive or multi-master | No (v2) | no transitive integrity; beyond the single-master constraint (CPD-D1) — portfolio-tier. |

---

## Decision log

| ID | Title | What it commits |
|---|---|---|
| **CPD-D1** | Single-master constraint | One plan driver per link; master→derived delegation with a back-reference, never peer-to-peer negotiation. A both-repos feature = two master features. |
| **CPD-D2** | Replication over dereference | Each repo validates standalone against a replicated master-contract hash; `reconcile` compares only when both repos are present. CI-safe, no hard filesystem coupling. |
| **CPD-D3** | Third dir form `derived` | `<project>--F<n>-<slug>`; `--` sentinel (slug grammar forbids `--`); out-of-band from every content hash; collision-proof against native features. |
| **CPD-D4** | Master points at the project | `**Implemented by:** <project>` names only the project; the derived dir + `**Derived from:**` carry the feature number. 1:1 from master-number uniqueness + reconcile bijection. |
| **CPD-D5** | Soft-halt master-update flow | Record a UCR + proceed with a divergence note + surface at reconcile + re-sync via drift; **not** a hard halt — no atomic two-repo edit exists. |
| **CPD-D6** | Master hash is advisory | `**Master contract hash:**` is plain content reconcile *compares*; never wired into either repo's `--approve` gate (avoids entangling two approval chains). |
| **CPD-D7** | Defensive degradation | Missing/unconfigured/absent sibling → WARN-skip with deferred reminder, never FAIL. Standalone validation never requires `.sdd/projects.json`. |
| **CPD-D8** | Local-coverage exclusion | The derived project's own `validate_blueprint.py` coverage walk excludes `derived` dirs (they belong to reconcile, not the local PLAN). |
| **CPD-D9** | Shared grammar module | One module owns the qualified-id + derived-dir grammar and the link model; a contract test pins master/derived/reconcile symmetry. |
| **CPD-D10** | Detect, don't cascade | v1 stops at detection + suggestion; the cascade/auto-apply machinery is deferred — inherited from CFC and *forced* by the two-repo reality. |
| **CPD-D11** | Per-link scaling boundary | The star topology (one master → N derived repos, each link 1:1) scales natively because every primitive is per-link; detection *coverage* softens with N (the v2 durable-staleness signal is the fix). Fan-out (one feature → N implementations), chains, and mesh are v2. See `## Topology and scaling`. |

---

## Relationship to CFC and the `.sdd` store

| Reused | From | How |
|---|---|---|
| `normalize_for_hash` + structured-content hashing | `cfc_parser.py` | master-feature contract hash |
| `.sdd/` store pattern (single writer, defensive reads, out-of-band) | `arch_config.py` | `.sdd/projects.json` |
| `[upstream]` concern tag + halt routing | `references/panel-review.md` | the UCR trigger (soft-halt variant) |
| Bound-Spec Immutability doctrine + remediation paths | `references/workflow-overview.md` | cross-seam immutability |
| Anti-drift shared-grammar module + symmetry contract test | `cfc_parser.py` / `spec_dirname.py` | `project_link.py` |

CPD is intentionally **not** an extension of the CFC participant grammar: the relationship is strictly 1:1 master→derived and is carried by dedicated fields, not by THEN-line `[CFC-N]` tags. The two subsystems share *doctrine and infrastructure*, not format.
