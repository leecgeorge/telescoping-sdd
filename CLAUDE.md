# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repo serves two purposes:

1. **A Claude Code plugin** at `telescoping-sdd/` — its skills are invoked as `/telescoping-sdd:<skill-name>` (e.g., `/telescoping-sdd:project-blueprint`). The plugin manifest is `telescoping-sdd/.claude-plugin/plugin.json` (name: `telescoping-sdd`).
2. **A Claude Code marketplace** defined by `.claude-plugin/marketplace.json` (name: `neonghost-marketplace`) that publishes the `telescoping-sdd` plugin.

**Telescoping Spec-Driven Development.** `project-blueprint` and `spec-driven-dev` compose into one methodology at two altitudes: `project-blueprint` emits `blueprint/PLAN.md` (which decomposes the project into ordered features), and `spec-driven-dev` consumes one feature from `PLAN.md` to drive its Specify → Design → Tasks → Implement loop. `PLAN.md` is the seam between the two tiers — a sequential handoff, not containment. A secondary seam runs through **Cross-Feature Contracts** (PLAN's optional `## Cross-Feature Contracts` section): each `### CFC-N` entry binds multiple features at PLAN time and surfaces in each participating feature's SDD cycle via `[CFC-N]` tags on acceptance criteria (spec.md) and enforcement tasks (tasks.md). The shared `scripts/cfc_parser.py` enforces format symmetry between producer and consumer; full design in `telescoping-sdd/documentation/CFC.md`.

**Stack profiles and the architecture-config seam.** `spec-driven-dev` selects a stack *profile* — `python`, `java`, or the architecture-neutral `generic` (for infra, static sites, Claude-skill authoring, and anything without a Python/Java marker; it disables the two language-specific advisory checks). The profile is resolved once via the precedence `explicit --language flag > persisted .sdd/architecture.json > marker auto-detect` (auto-detect falls back to `generic`, never silently to `python`) and persisted by an explicit op: `validate_spec.py --set-language` (SDD side) or `validate_blueprint.py --write-arch-config`, which reads the `**Architecture token:**` from `ARCHITECTURE.md` and writes the same store (blueprint side). The shared `scripts/arch_config.py` owns the read/write/resolve logic and the token grammar so the prose layer and both validators can't drift; `scripts/tests/test_arch_config.py` asserts the round-trip + producer/consumer vocabulary symmetry. The store is deliberately advisory-only and out-of-band from every content hash, so it never interacts with the `--approve`/CFC cascade.

## Repository Layout

| Path | Purpose |
|---|---|
| `.claude-plugin/marketplace.json` | Marketplace manifest; lists `telescoping-sdd` at `./telescoping-sdd` |
| `telescoping-sdd/.claude-plugin/plugin.json` | Plugin manifest |
| `telescoping-sdd/skills/<name>/SKILL.md` | Plugin skills (`project-blueprint`, `spec-driven-dev`) — invoked as `/telescoping-sdd:<name>` |
| `telescoping-sdd/agents/*.md` | Every executor + persona invoked by a skill (auto-discovered by Claude Code at plugin tier 4) |
| `telescoping-sdd/agent-references/` | Canonical source for the shared self-review + memory discipline. The load-bearing content is **inlined into each executor agent body** (agent files are system prompts and cannot resolve a relative `Read` path at runtime); these files are the maintainer-facing source of truth — keep the inlined copies in sync with them. Kept OUT of `agents/` so the plugin loader does not mis-discover them as subagents. |
| `telescoping-sdd/scripts/` | Shared validators (`archive_pass.py`, `blueprint_common.py`, `trajectory.py`, `content_hash.py`, `artifact_resolution.py`, `pending_review.py`, `cfc_parser.py`, `arch_config.py`) and their tests. The God-module split (audit R3.1) extracted four concerns out of `blueprint_common` (2,153 → 771 lines): `trajectory.py` (the `### Trajectory` table machinery — a leaf), `content_hash.py` (the versioned content-hash basis + `## Approval` grammar — a layer over trajectory), `artifact_resolution.py` (the `NN_`-prefix-aware artifact resolver + `run_cli_failclosed` — a leaf), and `pending_review.py` (the `.sdd/pending-review.json` marker lifecycle). `blueprint_common` imports the leaves/layers at the top and `pending_review` at the bottom, and re-exports all of them, so `from blueprint_common import resolve_artifact` / `compute_content_hash` / `trim_trajectory_table` / `upsert_pending_entry` still resolve. Layering (no cycles): `{trajectory, artifact_resolution}` ← `content_hash` ← `blueprint_common` ← `pending_review`. `check_approval` stays in `blueprint_common` (it builds a `ValidationResult`). |
| `telescoping-sdd/documentation/CFC.md` | Cross-Feature Contracts design spec (shared between the two skills) |

## Skill Structure

Every skill folder under `telescoping-sdd/skills/` follows this layout:

```
<skill-name>/
├── SKILL.md            # Required - main skill file with YAML frontmatter
├── scripts/            # Optional - executable code (Python, Bash, etc.)
├── references/         # Optional - documentation loaded as needed
└── assets/             # Optional - templates, fonts, icons
```

## Naming Conventions

- **Skill folders:** kebab-case only (`my-cool-skill`). No spaces, underscores, or capitals.
- **SKILL.md:** Must be exactly `SKILL.md` (case-sensitive). No variations.
- **No README.md** inside skill folders. All documentation goes in SKILL.md or `references/`.
- Skill and plugin names must not contain "claude" or "anthropic" (reserved).
- The `name` field in SKILL.md frontmatter must match the folder name.

## SKILL.md Format

Every SKILL.md requires YAML frontmatter with `---` delimiters:

```yaml
---
name: skill-name-in-kebab-case
description: What it does and when to use it. Include specific trigger phrases users would say.
---
```

- `description` must include BOTH what the skill does AND when to use it (trigger phrases), under 1024 characters
- No XML angle brackets (`<` `>`) anywhere in frontmatter
- Optional fields: `license`, `compatibility`, `allowed-tools`, `metadata` (author, version, mcp-server, tags, status)
- `metadata.status` is `stable` (ready for day-to-day use), `beta` (feature-complete and in regular use, but still hardening), or `experimental` (usable but in development). The README skill table mirrors this in a Status column.

After frontmatter, write instructions in Markdown following this structure: Instructions/Steps, Examples, Troubleshooting.

## Progressive Disclosure

Skills use three levels to minimize token usage:

1. **YAML frontmatter** — always in Claude's system prompt (trigger info only)
2. **SKILL.md body** — loaded when Claude determines the skill is relevant
3. **Linked files** (`references/`, `scripts/`, `assets/`) — loaded only as needed

Keep SKILL.md under 5,000 words. Move detailed docs to `references/` and link to them.

## Subagent Priority (load-bearing)

Claude Code resolves `subagent_type` invocations by priority, highest to lowest: CLI `--agents` → project `.claude/agents/` → user `~/.claude/agents/` → plugin `agents/` → built-in.

Every executor and panel persona invoked by the skills lives at `telescoping-sdd/agents/` and is auto-discovered at plugin tier 4 — no separate install step is required. Skills call them with the namespaced form (`subagent_type: "telescoping-sdd:architect"`, etc.), which resolves directly via the plugin tier.

Skills relying on this are the per-phase drafting + panel-review steps inside `project-blueprint` and `spec-driven-dev`.

## Common Commands

```bash
# Validate the marketplace and plugin
claude plugin validate .
claude plugin validate ./telescoping-sdd

# When releasing: bump `version` in BOTH telescoping-sdd/.claude-plugin/plugin.json
# AND .claude-plugin/marketplace.json's plugin entry; keep them in lockstep.
# plugin.json is authoritative — the marketplace entry mirror exists for metadata display.

# Validate skill-specific artifacts (end-user facing)
python telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py specs/F1-<slug>/
python telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py blueprint/

# Run the test suite (python/pip are NOT on PATH — use the venv directly).
# One-time setup (the .venv is gitignored, so a fresh clone must create it; Python 3.9+):
#   python3 -m venv .venv && .venv/bin/pip install pytest -r telescoping-sdd/skills/project-blueprint/scripts/requirements.txt
.venv/bin/pytest telescoping-sdd/ -q                                 # full suite
.venv/bin/pytest telescoping-sdd/scripts/tests/ -q                   # shared-script tests only
.venv/bin/pytest telescoping-sdd/scripts/tests/test_archive_pass.py::test_mode_flags_are_mutually_exclusive -q  # single test
```

Tests live in three places: `telescoping-sdd/scripts/tests/` covers shared scripts (`archive_pass.py`, `blueprint_common.py`), fixture-manifest consistency, and skill→subagent resolution; per-skill tests live under `telescoping-sdd/skills/project-blueprint/scripts/tests/` **and** `telescoping-sdd/skills/spec-driven-dev/scripts/tests/`. There is no pytest config file. CI runs the full suite on Python 3.9 + 3.12 via `.github/workflows/tests.yml`; you can also run it manually with the `.venv/bin/pytest telescoping-sdd/ -q` invocation above.

## Loading the Plugin

**Dev mode (edits propagate live, session only):**
```bash
# from the repo root:
claude --plugin-dir "$(pwd)/telescoping-sdd"
```
Or use an absolute path to the plugin folder. Run `/reload-plugins` after edits.

**Persistent install (cache-backed, edits require reinstall to take effect):**
```
/plugin marketplace add /absolute/path/to/telescoping-sdd
/plugin install telescoping-sdd@neonghost-marketplace
```

## Panel Review: Phase-Dependent Triggers and Strict-Bar Convergence Mode

Both skills share a panel-review loop. On rich documents the panel keeps surfacing real-but-downstream-deferrable HIGH concerns and never converges. **Strict-bar mode** recalibrates the panel to *this-phase* concerns once the trajectory shows convergence-shaped spinning; an **exit cross-check** runs one normal pass to audit the filter before exiting.

`archive_pass.py` requires `--phase {1,2,3}` and drives phase-dependent trigger logic:
- **Phase 1:** existing `Deferred → DOWNSTREAM` accumulation drives the strict-bar signal; no tag mechanism.
- **Phase 2 / 3:** the synthesizer prefixes every HIGH `Concern` with `[contract]`, `[detail]` (Phase 3 only), or `[upstream]` when recording it (the tags are synthesizer-owned advisory labels — see `panel-review.md` § Concern tagging). `[upstream]` auto-routes to halt votes regardless of disposition. Phase 3's strict-bar signal switches from `Deferred → DOWNSTREAM` accumulation to `[detail]`-tag accumulation (Phase 3 has no further phase to defer to). The script stashes a `tags=dXuYcZ` substring in the `### Trajectory` Notes so subsequent passes can compare.

Auto-detection is live: after every NORMAL archive `archive_pass.py` emits a `STRICT-BAR-SIGNAL:` advisory on stdout when both trigger conditions are met. The synthesizer reads the advisory and asks the user before switching mode.

The shared `telescoping-sdd/scripts/archive_pass.py` carries `--strict-bar` / `--cross-check` flags that stamp the `### Trajectory` Notes column.

The **authoritative operational spec** is each skill's `references/panel-review.md` (`## Strict-Bar Convergence Mode`, `## Concern tagging (Phase 2 and 3)`) plus `references/strict-bar-prompts.md`.

## Cross-Feature Contracts (CFC)

PLAN's optional `## Cross-Feature Contracts` section commits invariants that span multiple features. Each `### CFC-N` entry has four required fields (Participating features, Contract, Per-feature AC, Enforcement) and is bound mechanically:
- **Producer** (`validate_blueprint.py`) parses the section. On `--approve plan` it refreshes a per-CFC content-hash sub-block before computing the document hash; on PLAN validation (`--phase plan` / default) it emits `orphaned-stale-content` WARNs when a previously-bound spec drifts from the current CFC text.
- **Consumer** (`validate_spec.py`) parses participating-feature membership and enforces that each participating feature's `spec.md` carries the `Per-feature AC` line with a `[CFC-N]` tag on a THEN clause; for features named in `Enforcement` prose (bare `F<n>` token, word-boundary), `tasks.md` must carry a `[CFC-N]`-tagged enforcement task.
- **Shared parser** (`scripts/cfc_parser.py`) owns all CFC regexes and the four-field `CFCEntry` so producer and consumer can never drift in format interpretation. The parser-contract test suite (`scripts/tests/test_cfc_parser_contract.py`) asserts the symmetry.

Authoring discipline lives in `skills/project-blueprint/references/plan-template.md` (`## Cross-Feature Contracts` section), with consumer-side obligations in `skills/spec-driven-dev/references/phase-{specify,design,tasks}.md`. The full design rationale and v1/v2 split is in `telescoping-sdd/documentation/CFC.md`.
