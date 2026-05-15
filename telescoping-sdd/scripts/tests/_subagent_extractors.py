"""Subagent-name extractors for SKILL.md files.

Extractors corresponding to the invocation shapes used across
telescoping-sdd/skills/:

  (a) `subagent_type: <name>` — Agent tool invocation parameter
  (b) `Panelists:` bullet/inline lines AND inline "panel (`a`, `b`, `c`)"
      parenthetical lists — backticked names listed for the panel-review step
  (c) Markdown table cell — `| # | Perspective | Focus alias | Subagent | … |`
      style table. The Subagent column may be prefixed with `telescoping-sdd:`;
      the prefix is stripped before capture.
  (d) Narrative invocations — "Delegate ... `<name>` (sub)agent",
      "Invoke ... `<name>` (sub)agent", "the `<name>` (sub)agent" anywhere.
  (e) Agent-resolution check section — backticked names under a header
      containing "Agent-resolution".

The negative-space scan (`scan_undetected_names`) is the regression guard
against new invocation shapes appearing without a matching extractor.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple


class SubagentMatch(NamedTuple):
    name: str
    skill: Path
    line: int
    extractor: str


# (a) subagent_type: <name> — the name may carry a `telescoping-sdd:` plugin-tier
# prefix (`subagent_type: telescoping-sdd:feature-spec-analyst`); strip it during
# capture so the captured value is the bare slug.
_RE_SUBAGENT_TYPE = re.compile(r"""\bsubagent_type:\s*["']?(?:telescoping-sdd:)?([a-z0-9-]+)""")

# (d) prose: narrative invocations. Three shapes are matched:
#   - "Delegate ... to (the) `<name>` (sub)agent"
#   - "Invoke (the) `<name>` (sub)agent"
#   - "the `<name>` (sub)agent" anywhere — catches back-references such as
#     "After the `testability-reviewer` subagent returns" and
#     "the `testability-reviewer` agent's invocation prompt".
# Also matches "Delegate to `<name>`." (no trailing "subagent") and
# "drafted by the `<name>` agent".
_RE_DELEGATE_PROSE = re.compile(
    r"(?:Delegate|Invoke)\b.*?(?:the\s+)?`([a-z0-9-]+)`\s+(?:sub)?agent"
    r"|drafted\s+by\s+the\s+`([a-z0-9-]+)`\s+(?:sub)?agent"
    r"|\bthe\s+`([a-z0-9-]+)`\s+(?:sub)?agent",
    re.IGNORECASE,
)

# (e) Agent-resolution check section: a backticked agent/persona name on
# its own line bullet under a header containing "Agent-resolution" or
# "agent resolution check". Claimed as detected so the negative-space
# scan doesn't fire on the resolution-check enumeration.
_RE_RESOLUTION_HEADER = re.compile(
    r"^#+\s+.*Agent[\s-]?resolution\b", re.MULTILINE | re.IGNORECASE
)

# (b) Panelists context: a header line `**Panelists` (per phase) opens a
# block of bullet lines like `- **Tasks:** \`a\`, \`b\`, \`c\``, OR an inline
# `Panelists: \`a\`, \`b\`, \`c\`.` line, OR an inline
# "<X> panel (\`a\`, \`b\`, \`c\`)" parenthetical list. All three shapes
# appear in the codebase.
_RE_BACKTICK_NAME = re.compile(r"`([a-z0-9-]+)`")
_RE_PANELISTS_INLINE = re.compile(r"\bPanelists?\s*:")
_RE_PANELISTS_HEADER = re.compile(r"\*\*Panelists\b", re.IGNORECASE)
_RE_PANEL_PARENTHETICAL = re.compile(r"\bpanel\s*\(([^)]+)\)", re.IGNORECASE)

# (c) markdown-table row: any row whose 4th cell looks like a subagent slug,
# optionally prefixed with `telescoping-sdd:` (the plugin tier-4 invocation form).
# Anchored to a table that has "Subagent" in its header so we don't pick up
# stray 5-column tables that happen to contain a slug-shaped value.
_RE_TABLE_ROW = re.compile(r"^\|\s*\d+\s*\|[^|]+\|[^|]+\|\s*(?:telescoping-sdd:)?([a-z][a-z0-9-]*)\s*\|")


def _line_of(text: str, offset: int) -> int:
    """1-indexed line number containing the given offset."""
    return text.count("\n", 0, offset) + 1


def extract_a_subagent_type(skill: Path, text: str) -> list[SubagentMatch]:
    out: list[SubagentMatch] = []
    for m in _RE_SUBAGENT_TYPE.finditer(text):
        out.append(SubagentMatch(m.group(1), skill, _line_of(text, m.start()), "subagent_type"))
    return out


def extract_b_panelists(skill: Path, text: str) -> list[SubagentMatch]:
    out: list[SubagentMatch] = []
    lines = text.splitlines(keepends=False)
    in_panelists_block = False
    for idx, line in enumerate(lines, start=1):
        is_inline = bool(_RE_PANELISTS_INLINE.search(line))
        is_header = bool(_RE_PANELISTS_HEADER.search(line))
        panel_parens_match = _RE_PANEL_PARENTHETICAL.search(line)

        if is_inline:
            for nm in _RE_BACKTICK_NAME.findall(line):
                out.append(SubagentMatch(nm, skill, idx, "panelists_inline"))
            continue

        if panel_parens_match:
            # "Run the plan panel (`a`, `b`, `c`)." — extract names from the
            # parenthetical only, so a non-panel parenthetical on the same line
            # doesn't contaminate.
            for nm in _RE_BACKTICK_NAME.findall(panel_parens_match.group(1)):
                out.append(SubagentMatch(nm, skill, idx, "panel_parenthetical"))
            continue

        if is_header:
            in_panelists_block = True
            continue

        if in_panelists_block:
            stripped = line.strip()
            if not stripped:
                # Blank line continues the block (markdown allows it between
                # the header and the bullet list).
                continue
            if stripped.startswith("-") or stripped.startswith("*"):
                for nm in _RE_BACKTICK_NAME.findall(line):
                    out.append(
                        SubagentMatch(nm, skill, idx, "panelists_bullet")
                    )
            else:
                # Anything else closes the block.
                in_panelists_block = False
    return out


def extract_c_table_subagent_column(skill: Path, text: str) -> list[SubagentMatch]:
    """Pick rows whose 4th column is a slug, but only if the enclosing table
    declares a `Subagent` header. Walks the file in order and tracks the
    current table's columns.
    """
    out: list[SubagentMatch] = []
    table_has_subagent = False
    saw_separator = False
    for idx, line in enumerate(text.splitlines(keepends=False), start=1):
        s = line.strip()
        if not s.startswith("|"):
            table_has_subagent = False
            saw_separator = False
            continue
        if not table_has_subagent:
            # Header row test: any table with a Subagent column qualifies.
            if "Subagent" in line:
                table_has_subagent = True
                saw_separator = False
            continue
        if not saw_separator:
            # Separator row e.g. `|---|---|---|---|---|`
            if set(s.replace("|", "").replace("-", "").replace(":", "").strip()) <= set():
                saw_separator = True
            continue
        m = _RE_TABLE_ROW.match(line)
        if m:
            out.append(
                SubagentMatch(m.group(1), skill, idx, "code_review_table")
            )
    return out


def extract_d_delegate_prose(skill: Path, text: str) -> list[SubagentMatch]:
    out: list[SubagentMatch] = []
    for m in _RE_DELEGATE_PROSE.finditer(text):
        # One of three branches fires:
        #   (1) "Delegate|Invoke ... `name` (sub)agent"
        #   (2) "drafted by the `name` (sub)agent"
        #   (3) "the `name` (sub)agent"
        name = m.group(1) or m.group(2) or m.group(3)
        if name:
            out.append(
                SubagentMatch(name, skill, _line_of(text, m.start()), "delegate_prose")
            )
    return out


def extract_e_resolution_check(skill: Path, text: str) -> list[SubagentMatch]:
    """Bullet-list backticked names under an 'Agent-resolution check'
    section. Brownfield SKILL.md uses this shape for the startup
    verification list.
    """
    out: list[SubagentMatch] = []
    lines = text.splitlines(keepends=False)
    in_resolution_block = False
    for idx, line in enumerate(lines, start=1):
        if _RE_RESOLUTION_HEADER.search(line):
            in_resolution_block = True
            continue
        if in_resolution_block:
            stripped = line.strip()
            if stripped.startswith("#"):
                # New section ends the block.
                in_resolution_block = False
                continue
            if stripped.startswith("*") or stripped.startswith("-"):
                for nm in _RE_BACKTICK_NAME.findall(line):
                    out.append(
                        SubagentMatch(nm, skill, idx, "resolution_check")
                    )
    return out


def extract_all(skill: Path) -> list[SubagentMatch]:
    text = skill.read_text(encoding="utf-8")
    return (
        extract_a_subagent_type(skill, text)
        + extract_b_panelists(skill, text)
        + extract_c_table_subagent_column(skill, text)
        + extract_d_delegate_prose(skill, text)
        + extract_e_resolution_check(skill, text)
    )


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_locations(name: str, repo_root: Path) -> list[Path]:
    """All files matching `<name>.md` across the three search roots."""
    candidates = (
        repo_root / "telescoping-sdd" / "agents" / f"{name}.md",
        repo_root / "agents" / f"{name}.md",
        repo_root / "personas" / f"{name}.md",
    )
    return [c for c in candidates if c.is_file()]


# ---------------------------------------------------------------------------
# Negative-space scan
# ---------------------------------------------------------------------------


def scan_undetected_names(
    skill: Path,
    detected: set[str],
    universe: set[str],
) -> list[tuple[str, int, str]]:
    """Find backticked agent/persona names mentioned in the SKILL.md that
    weren't detected by any extractor.

    Restricted to backticked occurrences (`<name>`) and to the 4th column of
    a `Subagent`-headed markdown table — the two shapes that signal
    invocation intent. Bare prose mentions of a slug-shaped word
    ("synthesizer") aren't flagged because natural language regularly reuses
    those tokens; only an invocation-shaped occurrence is a missed extractor.

    Returns (name, line_number, surrounding_text) tuples.
    """
    text = skill.read_text(encoding="utf-8")
    out: list[tuple[str, int, str]] = []

    # Backticked-name occurrences anywhere in the file.
    for m in _RE_BACKTICK_NAME.finditer(text):
        name = m.group(1)
        if name in detected or name not in universe:
            continue
        line_no = _line_of(text, m.start())
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line_end = line_end if line_end != -1 else len(text)
        out.append((name, line_no, text[line_start:line_end].strip()))

    # Subagent-column table rows (mirrors extractor (c) but checks for
    # undetected names — i.e., extractor (c) didn't pick them up for some
    # reason, e.g., a column-count drift).
    table_has_subagent = False
    saw_separator = False
    for idx, line in enumerate(text.splitlines(keepends=False), start=1):
        s = line.strip()
        if not s.startswith("|"):
            table_has_subagent = False
            saw_separator = False
            continue
        if not table_has_subagent:
            if "Subagent" in line:
                table_has_subagent = True
                saw_separator = False
            continue
        if not saw_separator:
            if set(s.replace("|", "").replace("-", "").replace(":", "").strip()) <= set():
                saw_separator = True
            continue
        m_row = _RE_TABLE_ROW.match(line)
        if m_row:
            name = m_row.group(1)
            if name in universe and name not in detected:
                out.append((name, idx, s[:120]))
    return out
