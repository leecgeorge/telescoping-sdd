"""Unit D (R4): every executor agent carries the canonical write-location rule.

`agent-references/agent-write-location-instructions.md` is the maintainer-
facing source of truth (design C3, DM11). Agent files are system prompts and
cannot `Read` a relative path at runtime, so the rule is inlined into each
`agents/*.md` as a `## Write Location` section whose body must be
byte-identical to the canonical body.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[2]
_AGENTS = _PLUGIN / "agents"
_CANONICAL = _PLUGIN / "agent-references" / "agent-write-location-instructions.md"
_HEADING = "## Write Location"

_AGENT_STEMS = sorted(p.stem for p in _AGENTS.glob("*.md"))

def canonical_body() -> str:
    """The canonical text: everything after the file's `#` title line."""
    lines = _CANONICAL.read_text(encoding="utf-8").split("\n")
    assert lines[0].startswith("# "), "canonical file must open with a # title"
    return "\n".join(lines[1:]).strip("\n")


def section_body(text: str, heading: str = _HEADING):
    """The body of `heading` up to the next `## ` heading or EOF, or None."""
    lines = text.split("\n")
    try:
        start = lines.index(heading)
    except ValueError:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
               len(lines))
    return "\n".join(lines[start + 1:end]).strip("\n")


def test_agent_glob_finds_at_least_18_files():
    assert len(_AGENT_STEMS) >= 18


@pytest.mark.parametrize("stem", _AGENT_STEMS)
def test_agent_carries_canonical_write_location(stem):
    text = (_AGENTS / f"{stem}.md").read_text(encoding="utf-8")
    assert text.split("\n").count(_HEADING) == 1, f"{stem}: needs exactly one {_HEADING}"
    assert section_body(text) == canonical_body(), f"{stem}: {_HEADING} drifted"


_DRAFTERS = [
    "project-spec-analyst", "project-architecture-analyst", "project-plan-analyst",
    "feature-spec-analyst", "feature-architecture-analyst", "feature-task-analyst",
]


@pytest.mark.parametrize("stem", _DRAFTERS)
def test_drafter_write_location_directly_after_iteration(stem):
    lines = (_AGENTS / f"{stem}.md").read_text(encoding="utf-8").split("\n")
    heads = [l for l in lines if l.startswith("## ")]
    assert heads[heads.index("## Iteration") + 1] == _HEADING


def test_write_location_parity_catches_drift_and_missing_section():
    good = f"# agent\n\n## Role\n\nx\n\n{_HEADING}\n\n{canonical_body()}\n\n## Last\n\ny\n"
    assert section_body(good) == canonical_body()
    drifted = good.replace("do not choose a path", "pick any path")
    assert section_body(drifted) != canonical_body()
    missing = "# agent\n\n## Role\n\nx\n"
    assert section_body(missing) is None
