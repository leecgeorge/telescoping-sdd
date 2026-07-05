# Changelog — v1.x archive

Archived `1.x` release notes for the **telescoping-sdd** plugin, moved out of the main `CHANGELOG.md` to keep it focused on current releases. Newest first. For `2.0.0` and later, see [CHANGELOG.md](CHANGELOG.md).

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
