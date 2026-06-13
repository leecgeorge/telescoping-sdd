# Changelog

All notable changes to the **telescoping-sdd** plugin — the two-tier methodology of `project-blueprint` (project tier) and `spec-driven-dev` (feature tier). Newest first.

## 2.5.0 — Audit remediation (correctness, installed-product, and prose fixes)
Remediation of an external codebase audit, in two waves. Every fix ships with tests; the suite is now CI-gated (see below).

**Wave 1 — correctness & installed-product breakage:**
- **R10 parity restored (R1.2):** `validate_spec` carried a pre-R10 fork of `validate_panel_review`, so `spec.md`/`design.md`/`tasks.md` never surfaced orphaned `### Trajectory` rows (including the load-bearing FAIL case). It now imports the canonical `blueprint_common` implementation; the parity test that was supposed to catch this — it looped over both validator modules but called the shared function both times — now drives each module's own `validate_panel_review`.
- **Approval gate on the SDD side (R1.4):** `validate_spec --approve` previously stamped anything that passed only the directory↔identifier cross-check. It now runs the matching phase validator first and refuses to stamp on FAIL (Decision E, ported from `validate_blueprint`), with a `--force` override; because the design/tasks validators run `check_previous_phase_approved`, this also enforces Specify→Design→Tasks ordering on the approve path. Skipped under `--task-tick` (the Phase-4 carve-out).
- **Failed approvals are loud (R1.5):** `approve_document` now returns a status; a missing `## Approval` section or a checkbox/Content-Hash substitution that doesn't land exits non-zero with nothing written, instead of printing a false `Approved:` on exit 0. Applied to both validators.
- **`archive_pass` durability (R1.3):** the one writer of approval-bearing artifacts that was neither atomic nor encoding-pinned now writes via temp-file + `os.replace` and reads/writes UTF-8 explicitly (it emits non-ASCII — the Deferred arrow, em dash, ellipsis — which a non-UTF-8 locale would mojibake or fail to encode after truncating the file).
- **Windows never-raises contract (R1.8):** `safe_read_sibling` used a bare `os.O_NOFOLLOW` (Unix-only), raising `AttributeError` on Windows; it now `getattr`s the flag and falls back to a pre-open `lstat` symlink refusal.
- **CFC referential integrity (R1.6):** a CFC naming a feature with no `### F<n>:` entry in PLAN (a typo, or a deleted feature) silently bound nothing. `validate_cfc_section` now FAILs when a Participating/Enforcement feature id is not defined in the Feature Breakdown.
- **Duplicate feature numbers (R1.7):** two `### F<n>:` blocks with the same number — which the two CPD consumers resolved oppositely (first-block-wins vs last-block-wins) — now FAIL `validate_plan`.
- **Executor-agent discipline loads (I1.1):** all six drafting agents told the spawned subagent to `Read ../agent-references/…`, a path unresolvable at runtime, so the detailed self-review and memory disciplines silently never loaded. The load-bearing content is now inlined into each agent body; `agent-references/` remains the canonical maintainer source.

**Wave 2 — installed-path correctness & prose consistency:**
- **Runnable script paths (I1.2, I1.3):** SKILL.md and `phase-specify.md` hard-coded `python telescoping-sdd/scripts/…` in command blocks (resolvable only from this repo's root); they now use the `<shared-script-path>` placeholder. The `SLUGIFY_CLI_HINT` and mixed-prefix WARN strings derive their path from `Path(__file__)` so the printed command is runnable from the user's environment.
- **Synthesizer-owned tags (I2.1, I2.2):** the `[contract]`/`[detail]`/`[upstream]` routing tags and the `[HIGH]`/`[MED]`/`[LOW]` severity tags were attributed inconsistently across `panel-review.md`, `CLAUDE.md`, and `delivery-manager.md`. Routing tags are now uniformly synthesizer-owned; severity tags are emitted by the panelist per § The Loop and recorded by the synthesizer.
- **Prose consistency (I2.3–I2.6, I1.4):** removed a per-task Phase-4 approval gate that contradicted SKILL.md; updated the File Layout trees and examples to the `NN_`-prefixed emit default (bare still resolves); corrected stale "Plan phase"/"feature-level plan" vocabulary in two agent descriptions to "Design"; reconciled "three phases" vs four items in `project-blueprint` SKILL.md; removed a dangling `PROCESS-NOTE.md` citation.
- **CLI mode flags are mutually exclusive (I3.2):** both validators group their mode flags (`--approve`, `--decline-pending`, `--restore-anchor`, `--set-language`/`--write-arch-config`) so argparse rejects any combination (exit 2) instead of silently dropping one by if-ordering.
- **Polyglot detect notice (I3.3):** `detect_language` prints a one-line notice when markers for more than one stack match the same directory, naming both and recommending `--set-language`, instead of silently resolving by declaration order.
- **BOM consistency (R2.5):** artifact reads that feed a content hash now use `utf-8-sig` (matching `render_business_brief`), so a BOM'd artifact no longer hashes differently on the producer and consumer sides and wedges at 'stale hash'. Writes stay plain UTF-8, so the first approve/archive normalizes any BOM away.

**Tooling:**
- **CI (R1.1):** a GitHub Actions workflow runs the full suite (`pytest telescoping-sdd/ -q`) on push to `main` and every PR, across Python 3.9 (supported floor) and 3.12. Reconciled the README Python floor (3.10+ → 3.9+) with reality and with CLAUDE.md.

## 2.4.0 — Pending-review churn fix (hash-basis v2)
- **Convergence-only re-approval no longer churns a pending-review marker (R1–R3):** the approval content-hash basis moves from v1 to **v2** — the `### Trajectory` table is now excluded from the hash (it is panel bookkeeping written by `archive_pass.py`, not contract content). Recording a converged panel pass no longer moves the hash, so a convergence-only re-approval writes no `.sdd/pending-review.json` marker and prints no `REAPPROVAL_REMINDER`. Eliminates the routine, doctrine-eroding reach for `--decline-pending` after every genuine panel convergence. Substantive edits (anywhere outside `### Trajectory`, including `### Latest pass detail`, `### Sealed`/`### Deferred dispositions`, and `Defense:` rationales) still write a marker (R7).
- **Non-silent, batch-safe hash-basis migration (R4):** every newly-approved artifact stamps a `- **Hash basis:** v2` line in `## Approval` (neutralized in the hash). An artifact still on the old basis reports a distinct `HASH-BASIS-MIGRATION:` FAIL (textually distinguishable from `Pending-review: FAILED`), resolved by re-approving once; a pure basis migration writes no marker, a concurrent substantive edit writes one clearable marker.
- **Obligation no longer re-anchors (R9, folds in the F47 marker bug):** an open pending-review obligation now survives every intervening re-stamp **verbatim** (unconditional preserve — the open/closed state is the sole discriminator, no content classifier) until it is satisfied by the `upstream-panel` tag or declined. A legacy re-anchored marker whose genuine tag sits at-or-below its anchor surfaces a distinct `UNSATISFIABLE-OBLIGATION:` diagnostic, cleared by the new content-attested `--restore-anchor` flag (clears only when the real tag is present).
- **Scoped approval rewrites (R8):** `validate_spec.approve_document` now scopes the Approved-checkbox and Content-Hash rewrites to the `## Approval` section via the shared `approval_section_bounds` (matching `validate_blueprint`), so approving a self-documenting artifact never corrupts a body-prose example of those lines.
- **Orphaned-Trajectory-row detection (R10):** a `### Trajectory` data row stranded below the table's blank-line terminator is surfaced with an `ORPHANED-TRAJECTORY-ROW:` diagnostic — blocking FAIL when load-bearing (Pass > max, or carries an `upstream-panel` tag), non-blocking WARN otherwise — plus an `archive_pass.py` guard that refuses to strand a row by its own write and surfaces (never blocks on) a pre-existing one. Detect-and-surface only; never auto-heals.
- **Single-source + parity:** all hash logic lives in `blueprint_common.py`; both validators and both `hash-and-cascade.md` copies (new `### Close-Path Selection Guidance` subsection, narrowed `--decline-pending` meaning) stay in lockstep, guarded by `test_hash_and_cascade_parity.py`. No `.sdd/pending-review.json` schema change.

## 2.3.0 — Mid-implementation discovery backport
- **Phase-4 triage gate:** `spec-driven-dev/SKILL.md` gains a `### Mid-implementation discovery` subsection. On a Phase-4 deviation, Claude triages by an observable always-major list (changes an acceptance criterion / external interface-contract / external dependency / affects a remaining task / touches a security-or-privacy surface; "when in doubt → major"). **Major →** halt and backport into the single highest-affected upstream via the existing *Re-Approval After Edits* flow; **minor →** log a `pending` row and continue. Closes the two failure modes where Claude either never propagated a discovery upstream or batch-edited the whole chain to force consistency.
- **No-batch-edit rule + upstream-backport pointer:** both `hash-and-cascade.md` copies gain `### Single-entry-point rule: no batch edits` and `### Upstream backport — same-repo discovery` (in `## Deferred Dispositions`) — naming "backport" as the existing Re-Approval After Edits flow (no new mechanism) and prohibiting simultaneous chain edits. Generic cascade discipline, mirrored to `project-blueprint`.
- **Implementation-deviations ledger + completion gate:** a `## Implementation Deviations` ledger is seeded into both tasks templates; the Phase-4 Final Check gains a per-entry completion gate (backport, or record an `## Accepted Divergences` entry) plus a pre-gate check that no `declined` row is left without a paired entry. The SDD-only Phase-4 carve-out is extended so a `minor` ledger append is task-tick-silent, while status transitions and out-of-section edits still trip the substantive path.
- **Regime boundary, caught-late troubleshooting, feedback arrow:** SKILL.md states the in-flight vs shipped boundary (amend in place while in-flight; post-ship record an Accepted Divergence and route the fix to a new feature); the five discovery `troubleshooting.md` entries (both tiers) are rewritten to lead with the caught-late path; both `workflow-overview.md` diagrams gain a backport feedback arrow.
- **Regression guard:** `test_hash_and_cascade_parity.py` gains 8 functions / 11 invocations pinning the new doctrine with backtick-safe anchors, including SDD-only leak guards for the blueprint copy.

## 2.2.0 — Artifact ordering prefix
- **Additive `NN_` ordinal-prefix resolution:** generated artifacts may carry a two-digit ordinal prefix (`01_spec.md`, `02_design.md`, `03_tasks.md`, `01_SCOPE.md`, …) so a directory listing sorts in phase order. Resolution is additive — both the bare and the prefixed form resolve everywhere. New `strip_artifact_prefix` / `resolve_artifact` / `_detect_prefix_state` helpers plus `ArtifactAmbiguityError` and `KNOWN_ARTIFACTS` in `blueprint_common.py` are the single resolution chokepoint (raise only on a bare+prefixed coexistence; soft-absence preserved, fail-closed on ambiguity). ~50 call sites across both validators, `archive_pass.py`, `reconcile.py`, and `render_business_brief.py` were converted.
- **Hash-safe renamer:** new `artifact_prefix.py` renames a project's bare artifacts to the prefixed form without touching content (so content hashes stay valid and no approval is invalidated); refuses fail-closed on a corrupt or in-flight `.sdd/pending-review.json` obligation, a pre-existing ambiguity, or a symlinked/escaping artifact. A `--check` subcommand prints `OFFER` / `SUPPRESS` as the interactive-offer gate.
- **Mixed-state surfacing:** both validators emit a non-blocking WARN only on a mixed (bare+prefixed) directory, pointing to the renamer.
- **Regression guard:** new `test_artifact_prefix.py` (resolver + renamer + grep-gate + integration tests) plus additions to `test_archive_pass.py` and `test_blueprint_common.py`.

## 2.1.0 — Security exposure seam
- **Exposure-triage gate (1a):** Added a `## Network Exposure Triage` step to `phase-specify.md` (SDD) and `phase-scope.md` (blueprint) — a bright-line screening question with an objective deliverables-trigger list, branch-(a)/branch-(b) structure, and FINDING obligations. The `devils-advocate` now independently audits every Specify/Scope artifact against the trigger list, including an unconditional obligation that fires on a PASS-blessing acceptance criterion or an omitted triage declaration.
- **Exposure Doctrine + response rule (2b):** Added a mirrored `## Exposure Doctrine` section to both tier files; doctrine back-links from `phase-plan.md` and `phase-tasks.md` carrying the required response (raise an `[upstream]`-tagged concern or reorder/mitigate — a recognized exposure edge may not be dispositioned away as a soft MED); and an `## Exposure Doctrine Cross-Check` backstop in the `security-reviewer` brief for Design-phase artifacts.
- **Exposure sequencing check (2a-lite):** Added a `## Exposure Sequencing Check` to the `delivery-manager` brief — a Plan-tier (cross-feature) and Tasks-tier (intra-feature) check that surfaces a surface-exposed-before-hardening edge.
- **Regression guard:** Added `telescoping-sdd/scripts/tests/test_exposure_seam.py` (21 tests) asserting the structural anchors, two-tier mirror invariants, back-link presence and resolution, the three-panelist invariant (set-equality), version lockstep, and the em-dash changelog heading.

## 2.0.1 — Write-inversion for drafting subagents
- Drafting subagents now `Write` their artifact straight to disk and return a short **manifest** (path, line count, section headings, open questions) instead of returning the full body — eliminating truncation of large (30–70 KB) drafts through the size-capped tool-result channel.
- Applied across all 6 phase reference files, all 6 drafting agents, the shared self-review discipline, both `examples.md`, and both `SKILL.md`.
- Added `test_write_inversion.py`, a 15-case regression guard so the pattern can't silently revert.

## 2.0.0 — Cross-Project Derivation (CPD)
- Link a feature in one repo to a **master PLAN feature in another repo**: derived spec directories `specs/<project>--F<n>-<slug>/` carry `Derived from:` and `Master contract hash:` provenance.
- New `reconcile.py` binds/refreshes the master↔derived link and flags master-contract drift.
- Major bump: introduces the cross-repo derived-spec grammar.

## 1.8.0 — Re-approval gate hardening + panel autonomy boundary
- Hardened the re-approval-after-edits flow: a git-ignored `pending-review.json` marker turns a skipped upstream panel re-review into a later validation FAIL; resolve via the auditable `--decline-pending` or Phase-4 `--task-tick` acts.
- Added the panel-review **Autonomy Boundary** — what Claude runs without asking vs. the real user gates (phase approval, halt-and-rescope, 5-pass cap, strict-bar entry).

## 1.7.0 — Spec-directory filename grammar
- Spec dirs follow `specs/F<n>-<slug>/` (PLAN-bound) or `specs/<slug>/` (standalone), and must agree with the in-file `PLAN feature identifier` — a blocking FAIL in `validate_spec.py`.
- Added `spec_dirname.py slugify`; renaming a spec directory is hash-safe (never invalidates an approval).
- Fixed `archive_pass.py` corruption when reassembling Sealed + Deferred dispositions.

## 1.6.0 — Architecture-neutral `generic` stack profile
- New `generic` profile for infrastructure, static sites, config, docs, and Claude-skill authoring (skips the two Python/Java-specific advisory checks).
- Declare-once stack config `.sdd/architecture.json` with fixed precedence: explicit flag > persisted config > marker auto-detect (never silently defaults to Python).

## 1.5.1 — Skills-review remediation
- Added `documentation/CFC.md` and fixed assorted doc / script / agent gaps surfaced by a full skills review.

## 1.5.0 — Mid-stream upstream panel re-review
- Entering a workflow with an approved-but-stale artifact now routes through an upstream panel re-review before the downstream consistency cascade runs.

## 1.4.0 — Business Brief phase + mid-stream upstream panel
- Added an optional `project-blueprint` **Business Brief** render phase.
- Introduced the mid-stream upstream-panel machinery.

## 1.3.0 — Deferred dispositions
- Panel review gained a `### Deferred dispositions` sub-section with `[DEF-NN]` tracking, so panelists don't re-raise concerns already routed to a downstream artifact.

## 1.2.0 — Cross-Feature Contracts + phase-dependent panel triggers
- PLAN's `## Cross-Feature Contracts` (`CFC-N`) bind invariants that span multiple features, surfaced via `[CFC-N]` tags on spec acceptance criteria and enforcement tasks.
- Panel-review triggers became phase-dependent (distinct convergence/concern handling for Specify vs. Design vs. Tasks).

## 1.1.1 — Cascade hardening
- Hardened the downstream consistency-check cascade.

## 1.1.0 — Automatic re-approval cascade
- Editing an approved blueprint/spec document now auto-runs: structural check → silent re-stamp → downstream consistency cascade that halts only on substantive divergence. Cosmetic edits ripple silently; real decisions still gate the user.

## 1.0.0 — Initial release
- Two-tier **Telescoping Spec-Driven Development**: `project-blueprint` (Scope → Architecture → Plan) and `spec-driven-dev` (Specify → Design → Tasks → Implement).
- Three-persona **panel reviews** per phase, content-hash **approval gates** between phases, and Python / Java stack profiles.
