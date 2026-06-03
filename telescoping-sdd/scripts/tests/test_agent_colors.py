"""Every plugin agent must declare a `color` from Claude Code's supported palette.

Claude Code's subagent `color:` frontmatter field accepts exactly 8 named
colors. An unrecognized value (e.g. the `magenta`/`teal` that shipped before
1.8.0) is silently ignored, so the agent renders with no color. This guard keeps
every agent under `telescoping-sdd/agents/` declaring a valid, rendered color.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_AGENTS_DIR = Path(__file__).resolve().parents[2] / "agents"

# The 8 colors Claude Code supports for subagent frontmatter (per the official
# sub-agents docs). Anything else is silently ignored at load time.
_VALID_COLORS = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}

_COLOR_RE = re.compile(r"(?m)^color:\s*(\S+)\s*$")


def _agent_files() -> list[Path]:
    return sorted(_AGENTS_DIR.glob("*.md"))


def test_agents_dir_is_populated():
    assert _agent_files(), f"no agent .md files found under {_AGENTS_DIR}"


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
def test_agent_has_valid_color(path: Path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name}: no YAML frontmatter"
    # Frontmatter is the block between the first two '---\n' fences.
    frontmatter = text.split("---\n", 2)[1]
    m = _COLOR_RE.search(frontmatter)
    assert m, f"{path.name}: missing a 'color:' field in frontmatter"
    color = m.group(1)
    assert color in _VALID_COLORS, (
        f"{path.name}: color {color!r} is not a supported Claude Code color "
        f"(must be one of {sorted(_VALID_COLORS)}) — it would be silently ignored"
    )
