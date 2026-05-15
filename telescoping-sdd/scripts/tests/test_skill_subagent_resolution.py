"""Skill subagent resolution test.

For every SKILL.md under `telescoping-sdd/skills/`, run all extractors over
the file and assert that each detected name resolves to an agent definition.
The negative-space scan catches new invocation shapes that slip past the
extractors.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.append(str(_TESTS))

from _subagent_extractors import (  # noqa: E402
    extract_all,
    resolve_locations,
    scan_undetected_names,
)


def _skill_md_files() -> list[Path]:
    """All SKILL.md files under telescoping-sdd/skills/, sorted for determinism."""
    return sorted((_REPO_ROOT / "telescoping-sdd" / "skills").glob("*/SKILL.md"))


def _name_universe() -> set[str]:
    """Every agent/persona name resolvable today (slug = filename stem)."""
    universe: set[str] = set()
    for root in (
        _REPO_ROOT / "telescoping-sdd" / "agents",
        _REPO_ROOT / "agents",
        _REPO_ROOT / "personas",
    ):
        if root.is_dir():
            for p in root.glob("*.md"):
                universe.add(p.stem)
    return universe


def test_skill_subagent_resolution():
    """Every name extracted from any SKILL.md resolves to exactly one
    location across (telescoping-sdd/agents, agents, personas).
    """
    skills = _skill_md_files()
    assert skills, "No SKILL.md files found under telescoping-sdd/skills/"

    unresolvable: list[str] = []
    ambiguous: list[str] = []
    for skill in skills:
        for match in extract_all(skill):
            locations = resolve_locations(match.name, _REPO_ROOT)
            if len(locations) == 0:
                unresolvable.append(
                    f"{skill.relative_to(_REPO_ROOT)}:{match.line} "
                    f"({match.extractor}) -> '{match.name}'"
                )
            elif len(locations) > 1:
                paths = ", ".join(str(p.relative_to(_REPO_ROOT)) for p in locations)
                ambiguous.append(
                    f"{skill.relative_to(_REPO_ROOT)}:{match.line} "
                    f"({match.extractor}) -> '{match.name}' resolves to: {paths}"
                )

    msg_parts = []
    if unresolvable:
        msg_parts.append(
            "Unresolvable subagent names (zero matching files):\n  "
            + "\n  ".join(unresolvable)
        )
    if ambiguous:
        msg_parts.append(
            "Ambiguous subagent names (shadowed across roots):\n  "
            + "\n  ".join(ambiguous)
        )
    assert not msg_parts, "\n\n".join(msg_parts)


def test_skill_subagent_invocation_shapes_complete():
    """Negative-space scan: any agent/persona slug appearing in a SKILL.md
    that the four extractors miss is a sign of a new invocation shape that
    needs a fifth extractor.
    """
    skills = _skill_md_files()
    universe = _name_universe()
    assert universe, "Empty agent/persona name universe — repo state broken?"

    findings: list[str] = []
    for skill in skills:
        detected = {m.name for m in extract_all(skill)}
        misses = scan_undetected_names(skill, detected, universe)
        for name, line, snippet in misses:
            findings.append(
                f"{skill.relative_to(_REPO_ROOT)}:{line} -> '{name}' in: "
                f"{snippet[:120]}"
            )

    assert not findings, (
        "Subagent names appear in SKILL.md text but are not detected by "
        "any of the four extractors. Update _subagent_extractors.py with a "
        "fifth extractor matching the new shape:\n  "
        + "\n  ".join(findings)
    )
