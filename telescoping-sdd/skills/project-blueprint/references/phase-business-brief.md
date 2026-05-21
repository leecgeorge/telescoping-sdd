# Phase 4: Business Brief

<!-- Zero-external-link policy: this is an internal Phase-4 reference doc.
     Do NOT add hyperlinks with absolute schemes or embedded images.
     Test enforcement: r6_phase_doc_zero_external_links and
     r6_phase_doc_no_img_tags pin these constraints. -->

Renders the three approved blueprint documents — `SCOPE.md`, `ARCHITECTURE.md`, `PLAN.md` — as self-contained HTML files (`scope.html`, `architecture.html`, `plan.html`) for business-stakeholder consumption.

This phase is **optional** and **re-runnable**. It does not modify the source markdown files and has no downstream phases.

## Workflow

After the user approves PLAN.md (the Phase 3 endpoint), present this prompt to the user:

```
Generate a Business Brief for stakeholders? [y/n]
```

Accept the response case-insensitively, trimming leading and trailing whitespace:

- `y` / `yes` — invoke `render_business_brief.py` (below), then report the three output paths.
- `n` / `no` — confirm the brief was skipped and exit Phase 4 gracefully; no output files are created.
- Any other response (including empty) — re-prompt; do not silently treat as decline.

The prompt is delivered by the LLM driving the skill, not by a Python `input()` call inside the script.

## First-time setup

Phase 4 needs two pip packages — `markdown>=3.4` and `bleach>=6.0,<7.0` — that the rest of the skill does not. Install them once, into the Python environment that will invoke the script:

```bash
pip install -r <script-path>/requirements.txt
```

A `requirements.txt` file is co-located with the script so the install command is self-contained and the pinned floors are honored.

If `markdown` or `bleach` is missing or below the floor when the script runs, the dependency guard fails fast with a message that names BOTH packages, points at `requirements.txt`, and quotes the re-run command. A user with `markdown` already installed but `bleach` missing gets a message that mentions both, not just markdown — so the second `pip install` round of the user's day is unambiguous.

> **Note for marketplace installs.** Plugin files live under `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, which may not be writable by your user. Install into the Python environment that will INVOKE the script (the same `python3` your shell resolves), not into the plugin cache.

## Invocation

The script is co-located with `validate_blueprint.py` in the project-blueprint scripts directory.

```bash
python <script-path>/render_business_brief.py blueprint/
```

To override the auto-resolved project name (recommended for externally-shared briefs where the source-of-truth blueprint directory name is internal-only):

```bash
python <script-path>/render_business_brief.py blueprint/ --project-name "Acme Q3 Initiative"
```

To preview the would-be output paths without writing anything (useful on read-only filesystems or in CI):

```bash
python <script-path>/render_business_brief.py blueprint/ --dry-run
```

To override the brand logo PNG (for third-party redistribution with different branding):

```bash
python <script-path>/render_business_brief.py blueprint/ --logo /path/to/your-logo.png
```

Output files are written to `blueprint/business-brief/`:

```
blueprint/
+- SCOPE.md
+- ARCHITECTURE.md
+- PLAN.md
+- business-brief/
   +- scope.html
   +- architecture.html
   +- plan.html
```

The script reports the three resolved output paths to stdout; errors go to stderr.

## Re-running Phase 4

Phase 4 can be invoked any time after PLAN.md approval. Re-runs:

- Are idempotent — running again with no source changes silently overwrites the existing output files with byte-equivalent content (timestamp aside).
- Do not require a prompt — invoke the script directly.
- Pick up any edits made to the source markdown files (`SCOPE.md`, `ARCHITECTURE.md`, `PLAN.md`) since the last render, provided those edits did not invalidate the approval state (the script's upstream approval guard rejects unapproved or stale-hashed sources).
- **Hand-edits made directly to the output HTML files between runs will be lost.** The HTML files are derived artifacts; the source-of-truth is the markdown. Each output file's head contains a generator comment AND a stakeholder-readable footer paragraph warning about hand-edit data loss.

## Project-name resolution

The script picks the human-readable project name shown in the rendered `<title>` and footer provenance line via a four-tier cascade (first match wins):

1. **`--project-name "..."` CLI argument** — explicit override.
2. **First H1 of `SCOPE.md`** — strips a leading `Project: ` prefix and `* _ \`` emphasis chars; rejects the literal placeholder `Project Name`.
3. **`blueprint_dir.resolve().parent.name`** — the basename of the blueprint directory's parent.
4. **`Untitled Project`** — last-resort fallback. The script prints a stderr warning that the source layout is unexpected.

Concurrent invocations against the same blueprint directory are not supported — output files race to overwrite each other and the final state is undefined. The expected pattern is single-engineer invocation per render.

## Upstream approval guard

Before any rendering work, the script verifies all three upstream artifacts are present, approved (checkbox ticked), and have a content hash matching their current content. On any failure, the script exits non-zero with a human-readable error identifying:

- which artifact failed (`SCOPE.md` / `ARCHITECTURE.md` / `PLAN.md`),
- the failure mode (`unapproved` / `absent hash` / `stale hash`),
- and the remediation command (e.g., `re-run validate_blueprint.py --approve <phase>`).

The guard composes the canonical helpers from `validate_blueprint` (sibling module) and `blueprint_common` (shared scripts directory). No regex is re-implemented locally — the helper imports are the single source of truth for what "approved" means.

## Self-contained output

The three output files are guaranteed to be self-contained:

- No `<link rel="stylesheet" href="...">` to external CSS,
- No `<script src="...">` references,
- No `@import url(...)` rules for fonts or stylesheets,
- No image elements referencing external URLs; only inline `data:image/png;base64,...` data URLs are permitted, used for the brand logo.

A file opened in isolation — no sibling files, no network — renders identically to a file opened with full context. This is the email-able / SharePoint-droppable / offline-openable contract.

## Brand-logo asset

A Neon Ghost brand logo (~200px wide, ~14 KB PNG) is committed at `<script-path>/assets/neon-ghost-logo.png`. The script reads the PNG, base64-encodes it, and embeds the result as an inline `data:image/png;base64,...` URL in each output file's footer (bottom-left). If the asset is missing, the script prints a stderr warning and renders without the logo — graceful degradation; the brief still renders.

## Authoring rules

A few conventions keep the rendered output clean:

- **Use inline links, not reference-style.** Write `[the doc](URL)` — not `[the doc][SCOPE-1]` plus a separate `[SCOPE-1]: URL` definition line. The content filter strips `[SCOPE-N]` / `[ARCH-N]` / `[CFC-N]` / `[SEAL-N]` / `[DEF-N]` tokens, including the key of a reference-link definition. Reference-style links keyed on those tag names produce a mutilated `: URL` line in the output; inline links are clean.
- **No raw image tags in author markdown.** External image URLs (and relative ones) are stripped by the HTML allowlist — the only image permitted in the rendered output is the brand logo, injected by the script. If you need a diagram in the brief, link to it instead, or include it as text/ASCII art.
- **Use ATX headings.** `## Heading`, not setext-style `Heading\n========`. The content filter's section-strip regex anchors on `## ` line starts; setext headings are silently treated as body text.

## Gitignore recommendation

The `blueprint/business-brief/` directory contains derived artifacts. Adding it to `.gitignore` is recommended but not enforced by the script — the user decides whether to commit the rendered HTML alongside the source markdown.
