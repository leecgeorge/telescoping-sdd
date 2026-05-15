# Telescoping Spec-Driven Development

A Claude Code plugin that turns a vague idea into shipped code through two composed tiers of spec-driven planning — first at the project altitude, then at the feature altitude.

The `telescoping-sdd` plugin bundles two skills that compose into one methodology:

| Skill | Invocation | Status | What it does |
|---|---|---|---|
| `project-blueprint` | `/telescoping-sdd:project-blueprint` | Stable | Three-phase project planning (Scope → Architecture → Plan) with panel-review gates. Outputs `blueprint/PLAN.md` — an ordered feature list. |
| `spec-driven-dev` | `/telescoping-sdd:spec-driven-dev` | Stable | Four-phase feature workflow (Specify → Design → Tasks → Implement) with panel-review gates. Consumes one feature from `PLAN.md` per cycle. |

**Status** — *Stable*: ready for day-to-day use.

## How it works

The two skills aren't separate tools — they're one methodology at two altitudes.

- `project-blueprint` zooms **out** to plan the whole project: Scope → Architecture → `PLAN.md`.
- `spec-driven-dev` zooms **in** to build each feature `PLAN.md` names: Specify → Design → Tasks → Implement.

`PLAN.md` is the seam: the project tier's final artifact and the feature tier's input. Every feature listed there becomes one `spec-driven-dev` cycle.

### End-to-end flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        PROJECT-BLUEPRINT (project tier)                       │
│                                                                              │
│   Phase 1: SCOPE          Phase 2: ARCHITECTURE      Phase 3: PLAN           │
│   ┌────────────┐          ┌─────────────────┐        ┌──────────────┐        │
│   │ SCOPE.md   │ ───────> │ ARCHITECTURE.md │ ─────> │   PLAN.md    │        │
│   └────────────┘          └─────────────────┘        └──────────────┘        │
│        ▲                          ▲                         ▲                │
│   project-spec-           project-architecture-      project-plan-           │
│   analyst                 analyst                    analyst                 │
│                                                                              │
│   Panel:                  Panel:                     Panel:                  │
│   • user-advocate         • architect                • delivery-manager      │
│   • devils-advocate       • ops-reviewer             • critic                │
│   • pragmatist            • security-reviewer        • simplifier            │
│                                                                              │
│   HUMAN GATE              HUMAN GATE                 HUMAN GATE              │
│   --approve scope         --approve architecture     --approve plan          │
└──────────────────────────────────────────────────────────────────────────────┘
                                                             │
                                                             │  Features F1…Fn
                                                             │  become specs
                                                             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      SPEC-DRIVEN-DEV (feature tier, looped)                   │
│                                                                              │
│   Phase 1: SPECIFY    Phase 2: DESIGN     Phase 3: TASKS     Phase 4: IMPL   │
│   ┌──────────┐        ┌──────────┐        ┌──────────┐       ┌────────────┐  │
│   │ spec.md  │ ────>  │ design.md│ ────>  │ tasks.md │ ────> │   CODE +   │  │
│   └──────────┘        └──────────┘        └──────────┘       │   TESTS    │  │
│        ▲                    ▲                   ▲            └────────────┘  │
│   feature-spec-       feature-architecture- feature-task-    (calling Claude │
│   analyst             analyst               analyst           implements     │
│                                                               directly, TDD) │
│   Panel:              Panel:                Panel:                           │
│   • user-advocate     • architect           • delivery-manager               │
│   • devils-advocate   • testability-rev.    • critic                         │
│   • pragmatist        • security-reviewer   • simplifier                     │
│                                                                              │
│   HUMAN GATE          HUMAN GATE            HUMAN GATE       (no panel,      │
│   --approve spec      --approve design      --approve tasks   no gate —      │
│                                                               interactive)   │
└──────────────────────────────────────────────────────────────────────────────┘
                                                             │
                                                             └──> next feature
                                                                  from PLAN.md
```

### Per-phase loop (shared by both skills)

Every artifact phase above runs the same six-step loop. Only the drafting subagent and panelists change.

```
┌──────────────────────────────────────────────────────────────────┐
│  1. Delegate to specialist subagent (draft + self-review ≤5x)    │
│  2. Calling Claude re-reviews the returned draft  (≤5 passes)    │
│  3. Cross-document consistency check vs upstream approved docs   │
│  4. Panel review — 3 personas in parallel, loop ≤5 passes:       │
│        Addressed │ Deferred→ │ Accepted as risk │ User input     │
│  5. validate_{blueprint|spec}.py  (sections, hashes, no [TBD])   │
│  6. HUMAN REVIEW GATE → --approve <phase>  (content-hash locked) │
└──────────────────────────────────────────────────────────────────┘
```

Only `spec-driven-dev` Phase 4 (Implement) skips the panel and gate — the calling Claude executes TDD directly so course-correction stays interactive.

### Side-by-side

| Aspect | `project-blueprint` | `spec-driven-dev` |
|---|---|---|
| Scope | Whole project | Single feature |
| Output dir | `blueprint/` | `specs/<feature-name>/` |
| Phases with panels | 3 (Scope, Architecture, Plan) | 3 (Specify, Design, Tasks) |
| Implementation phase | — (hands off to `spec-driven-dev`) | Phase 4, no panel, interactive TDD |
| Hash-locked approval | Yes — cascades invalidate downstream | Yes — same mechanism |
| Validator | `validate_blueprint.py` | `validate_spec.py` |

### Cascading invalidation

If scope or architecture shifts mid-flight, content-hash invalidation cascades down the chain:

```
SCOPE.md → ARCHITECTURE.md → PLAN.md → spec.md → design.md → tasks.md → code
```

Any edit above the break re-invalidates everything below it until each phase is re-approved.

## Prerequisites

- [Claude Code](https://claude.com/product/claude-code) installed and authenticated
- A git repository to run the skills against (they rely on `git` commands)
- Python 3.10+ (only if you want to run the optional validators bundled with each skill)

## Install

Two modes. **Dev** for iterating on the skills in this repo; **production** for day-to-day use across all your projects. Pick one.

### Dev mode (edits propagate live, session-only)

Point Claude Code at the **plugin directory** with `--plugin-dir` — that's `<repo>/telescoping-sdd/`, the inner directory containing `.claude-plugin/plugin.json` (not the repo root). Source edits take effect after `/reload-plugins` — no install/uninstall cycle.

```bash
# from this repo's root:
claude --plugin-dir "$(pwd)/telescoping-sdd"
```

For a permanent dev setup, add an alias to `~/.bashrc` or `~/.zshrc`. Replace `<REPO_CLONE>` with the path to your clone (e.g. `~/projects/telescoping-sdd`) — the trailing `/telescoping-sdd` is the literal plugin sub-directory and stays as-is:

```bash
alias claude='claude --plugin-dir <REPO_CLONE>/telescoping-sdd'
```

Inside the session, verify:

```
/plugin list
```

Should show `telescoping-sdd` enabled. Run `/reload-plugins` after editing any `SKILL.md` or agent — no restart needed.

### Production install (persistent across sessions)

Register this repo as a marketplace once, then install the plugin. Plugin files get cached to `~/.claude/plugins/cache/` and are available in every future Claude Code session.

**Note on paths:** `marketplace add` points at the **repo root** (the dir containing `.claude-plugin/marketplace.json`), while `--plugin-dir` from dev mode pointed at the inner plugin sub-directory. They are different paths even though the same word `telescoping-sdd` appears in both — `/path/to/telescoping-sdd` below is the repo root.

From inside any Claude Code session:

```
/plugin marketplace add /absolute/path/to/telescoping-sdd
/plugin install telescoping-sdd@neonghost-marketplace
```

Or via CLI (non-interactive):

```bash
claude plugin marketplace add /absolute/path/to/telescoping-sdd
claude plugin install telescoping-sdd@neonghost-marketplace
```

Scope defaults to `user` (global, stored under `~/.claude/plugins/`). Pass `--scope project` to scope to the current project's `.claude/` directory, or `--scope local` for an untracked per-project install.

**Caveat:** cached plugin files don't reflect source edits until you bump `version` in `telescoping-sdd/.claude-plugin/plugin.json` and the marketplace entry, or uninstall and reinstall. **Use dev mode while iterating.**

### Reinstall after a skill change

**Versioned update (what to do when publishing a change):**

1. Bump `version` in `telescoping-sdd/.claude-plugin/plugin.json`.
2. Bump the matching `plugins[].version` in `.claude-plugin/marketplace.json` to the same value — the two must stay in lockstep.
3. Refresh the cached marketplace manifest, then pull the new plugin version:

   ```bash
   claude plugin marketplace update neonghost-marketplace
   claude plugin update telescoping-sdd@neonghost-marketplace
   ```
4. Restart Claude Code — `update` caches the new files but a running session keeps the old ones loaded.

**Quick reinstall (no version bump, e.g. iterating locally without cutting a release):**

```bash
claude plugin uninstall telescoping-sdd@neonghost-marketplace
claude plugin marketplace update neonghost-marketplace
claude plugin install telescoping-sdd@neonghost-marketplace
```

The `marketplace update` in the middle is only needed if you also edited `marketplace.json`; for plain skill edits inside `telescoping-sdd/`, the uninstall/install pair is enough. Restart Claude Code afterward.

## Verify

After installing (either mode):

```bash
claude plugin list                    # should show `telescoping-sdd` enabled
claude plugin validate ./telescoping-sdd    # manifest sanity check
```

Then start a real run inside any git repo:

```
/telescoping-sdd:project-blueprint
```

It walks you through Scope → Architecture → Plan, with a human-approval gate after each phase. When `PLAN.md` is approved, hand its first feature to:

```
/telescoping-sdd:spec-driven-dev
```

…which walks Specify → Design → Tasks → Implement for that one feature, then comes back for the next.

## Uninstall

**Dev mode:** remove the `--plugin-dir` flag or shell alias.

**Production:**

```
/plugin uninstall telescoping-sdd@neonghost-marketplace
/plugin marketplace remove neonghost-marketplace
```

Uninstall the plugin first, then remove the marketplace — the CLI doesn't guarantee cascade cleanup.

## Working on the skills

See [CLAUDE.md](CLAUDE.md) for repo conventions, subagent priority rules, and development commands.
