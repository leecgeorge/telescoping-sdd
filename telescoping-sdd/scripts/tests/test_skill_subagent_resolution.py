"""Skill subagent resolution test.

For every SKILL.md under `telescoping-sdd/skills/`, run all extractors over
the file and assert that each detected name resolves to an agent definition.
The negative-space scan catches new invocation shapes that slip past the
extractors.
"""

from __future__ import annotations

import re
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


# Panel persona slugs (the names that collide with built-in agents of the same
# name if invoked without the `telescoping-sdd:` prefix).
_PANEL_PERSONAS = {
    "user-advocate",
    "devils-advocate",
    "pragmatist",
    "architect",
    "ops-reviewer",
    "security-reviewer",
    "testability-reviewer",
    "delivery-manager",
    "critic",
    "simplifier",
}

_BACKTICK_TOKEN = re.compile(r"`([A-Za-z0-9:_-]+)`")


def _reference_panelist_lines():
    """(file, lineno, line) for reference-doc lines that *invoke/list* panelists:
    `Panelists:` lines (phase-*.md), the `## Panelists per phase` roster bullets
    (panel-review.md), and the `panel (...)` parentheticals (examples.md).

    Deliberately excludes prose mentions like "`ops-reviewer` raises a concern"
    — those legitimately use a bare slug as an illustration, not an invocation.
    """
    out = []
    refs = sorted(
        (_REPO_ROOT / "telescoping-sdd" / "skills").glob("*/references/*.md")
    )
    for f in refs:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if (
                stripped.startswith("Panelists:")
                or re.search(r"\bpanel \(`", line)
                or re.match(r"- \*\*[A-Za-z][A-Za-z ]*:\*\* `", line)
            ):
                out.append((f, i, line))
    return out


def test_reference_docs_panelist_names_carry_prefix():
    """Panelist persona slugs in the reference docs (Panelists: lines, the
    panel-review roster, examples 'panel (...)') must use the `telescoping-sdd:`
    prefix so the plugin's customised persona resolves rather than the built-in
    of the same name. The pre-existing resolution test only scans SKILL.md;
    this guards the reference files where the bare-name regression actually
    occurred (review finding Agents D1-2 / H2).
    """
    universe = _name_universe()
    offenders = []
    for f, lineno, line in _reference_panelist_lines():
        for tok in _BACKTICK_TOKEN.findall(line):
            base = tok.split(":")[-1]
            if base in _PANEL_PERSONAS:
                if not tok.startswith("telescoping-sdd:"):
                    offenders.append(
                        f"{f.relative_to(_REPO_ROOT)}:{lineno} -> bare `{tok}` "
                        "(missing telescoping-sdd: prefix)"
                    )
                elif base not in universe:
                    offenders.append(
                        f"{f.relative_to(_REPO_ROOT)}:{lineno} -> `{tok}` "
                        "resolves to no agent definition"
                    )
    assert not offenders, (
        "Panelist persona references in reference docs are bare or unresolved "
        "(the built-in persona would shadow the plugin's):\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# New thin agents (context-window-inflow-reduction) resolve at plugin tier 4:
# each must map to exactly ONE file under telescoping-sdd/agents/ (no shadow).
# ---------------------------------------------------------------------------


def test_panel_condenser_resolves_at_plugin_tier():
    """`panel-condenser` resolves to exactly one location under the plugin's
    agents/ dir (design C1/AD14, T4)."""
    locations = resolve_locations("panel-condenser", _REPO_ROOT)
    assert len(locations) == 1, (
        f"panel-condenser must resolve to exactly one file, got: {locations}"
    )
    assert locations[0] == _REPO_ROOT / "telescoping-sdd" / "agents" / "panel-condenser.md"


def test_consistency_reader_resolves_at_plugin_tier():
    """`consistency-reader` resolves to exactly one location under the plugin's
    agents/ dir (design C2/AD14, T7)."""
    locations = resolve_locations("consistency-reader", _REPO_ROOT)
    assert len(locations) == 1, (
        f"consistency-reader must resolve to exactly one file, got: {locations}"
    )
    assert locations[0] == _REPO_ROOT / "telescoping-sdd" / "agents" / "consistency-reader.md"
