# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repo serves two purposes:

1. **A Claude Code plugin** at `telescoping-sdd/` — its skills are invoked as `/telescoping-sdd:<skill-name>` (e.g., `/telescoping-sdd:project-blueprint`). The plugin manifest is `telescoping-sdd/.claude-plugin/plugin.json` (name: `telescoping-sdd`).
2. **A Claude Code marketplace** defined by `.claude-plugin/marketplace.json` (name: `neonghost-marketplace`) that publishes the `telescoping-sdd` plugin.

**Telescoping Spec-Driven Development.** `project-blueprint` and `spec-driven-dev` compose into one methodology at two altitudes: `project-blueprint` emits `blueprint/PLAN.md` (which decomposes the project into ordered features), and `spec-driven-dev` consumes one feature from `PLAN.md` to drive its Specify → Design → Tasks → Implement loop. `PLAN.md` is the seam between the two tiers — a sequential handoff, not containment.

## Repository Layout

| Path | Purpose |
|---|---|
| `.claude-plugin/marketplace.json` | Marketplace manifest; lists `telescoping-sdd` at `./telescoping-sdd` |
| `telescoping-sdd/.claude-plugin/plugin.json` | Plugin manifest |
| `telescoping-sdd/skills/<name>/SKILL.md` | Plugin skills (`project-blueprint`, `spec-driven-dev`) — invoked as `/telescoping-sdd:<name>` |
| `telescoping-sdd/agents/*.md` | Every executor + persona invoked by a skill (auto-discovered by Claude Code at plugin tier 4) |
| `telescoping-sdd/agents/references/` | Shared discipline files read by agents at runtime |
| `telescoping-sdd/scripts/` | Shared validators (`archive_pass.py`, `blueprint_common.py`) and their tests |

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
python telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py specs/<feature>/
python telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py blueprint/

# Run the test suite (python/pip are NOT on PATH — use the venv directly)
.venv/bin/pytest telescoping-sdd/ -q                                 # full suite
.venv/bin/pytest telescoping-sdd/scripts/tests/ -q                   # shared-script tests only
.venv/bin/pytest telescoping-sdd/scripts/tests/test_archive_pass.py::test_mode_flags_are_mutually_exclusive -q  # single test
```

Tests live in two places: `telescoping-sdd/scripts/tests/` covers shared scripts (`archive_pass.py`, `blueprint_common.py`), fixture-manifest consistency, and skill→subagent resolution. Per-skill tests live under `telescoping-sdd/skills/project-blueprint/scripts/tests/`. There is no pytest config file and no CI — tests are run manually.

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

## Panel Review: Strict-Bar Convergence Mode

Both skills share a panel-review loop. On rich documents the panel keeps surfacing real-but-downstream-deferrable HIGH concerns and never converges. **Strict-bar mode** recalibrates the panel to *this-phase* concerns once the trajectory shows convergence-shaped spinning (HIGH-count stable ±2 across two passes AND >50% of concerns deferred downstream); an **exit cross-check** runs one normal pass to audit the filter before exiting.

Status: implemented in both skills, manual invocation only (auto-triggering on the trajectory signal is deferred). The shared `telescoping-sdd/scripts/archive_pass.py` carries `--strict-bar` / `--cross-check` flags that stamp the `### Trajectory` Notes column.

The **authoritative operational spec** is each skill's `references/panel-review.md` (`## Strict-Bar Convergence Mode`) plus `references/strict-bar-prompts.md`.
