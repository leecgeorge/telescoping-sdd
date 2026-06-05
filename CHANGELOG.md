# Changelog

All notable changes to the **telescoping-sdd** plugin — the two-tier methodology of `project-blueprint` (project tier) and `spec-driven-dev` (feature tier). Newest first.

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
