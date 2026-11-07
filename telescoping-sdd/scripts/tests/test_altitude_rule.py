"""Unit D (R8, R9): upstream artifacts constrain a lower altitude, never decide for it.

Modelled on `test_downstream_ref_guard.py`'s `_PREVENTION_FILES`: a fixed list
of doctrine sites, each pinned to carry the rule wording. The four templates
that today have only a gating `## Open Questions` gain a non-gating
`## Decision Points` section (design AD16), which no validator reads.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[2]
_SKILLS = _PLUGIN / "skills"
_AGENTS = _PLUGIN / "agents"

# Spec R8, verbatim.
RULE = ("each artifact decides only what its altitude owns; it may constrain a "
        "lower altitude, never decide for it")
LITMUS = ("would this sentence still be true if the next phase chose a different, "
          "equally valid implementation?")
PROJECT_STRUCTURE_CLAUSE = (
    "Keep `Project Structure` a file list that says what changes in each file, not how."
)

# Each artifact's owns / does-not-own line (the altitude table, transcribed
# once here and at the eight sites) and the next phase its redirect names.
_OWNS = {
    "scope": (
        "SCOPE owns the problem, users, outcomes, non-goals, hard constraints and "
        "measurable success. It does not own components, modules, mechanisms or "
        "write orders, which belong to ARCHITECTURE.",
        "Architecture",
    ),
    "architecture": (
        "ARCHITECTURE owns components, boundaries, technology and data flow. It does "
        "not own the feature breakdown and its order, which belong to PLAN, or "
        "function- and file-level structure, which belongs to the feature design.",
        "the Plan",
    ),
    "spec": (
        "`spec.md` owns the observable behaviour at the feature's boundary, its "
        "acceptance criteria, and where the feature touches the codebase (the file "
        "list). It does not own which function or module holds the logic, internal "
        "algorithms, or data layouts not visible at the boundary, which belong to "
        "`design.md`.",
        "Design",
    ),
    "design": (
        "`design.md` owns structure, interfaces, error handling and test strategy. "
        "It does not own the task breakdown, which belongs to `tasks.md`.",
        "Tasks",
    ),
}

# The eight sites (spec R8's first criterion): (path, altitude).
_SITES = {
    "phase-scope": (_SKILLS / "project-blueprint/references/phase-scope.md", "scope"),
    "phase-architecture": (_SKILLS / "project-blueprint/references/phase-architecture.md", "architecture"),
    "phase-specify": (_SKILLS / "spec-driven-dev/references/phase-specify.md", "spec"),
    "phase-design": (_SKILLS / "spec-driven-dev/references/phase-design.md", "design"),
    "project-spec-analyst": (_AGENTS / "project-spec-analyst.md", "scope"),
    "project-architecture-analyst": (_AGENTS / "project-architecture-analyst.md", "architecture"),
    "feature-spec-analyst": (_AGENTS / "feature-spec-analyst.md", "spec"),
    "feature-architecture-analyst": (_AGENTS / "feature-architecture-analyst.md", "design"),
}

def altitude_paragraph(site: str) -> str:
    path, _alt = _SITES[site]
    paras = path.read_text(encoding="utf-8").split("\n\n")
    hits = [p for p in paras if p.startswith("**Altitude rule.**")]
    assert len(hits) == 1, f"{site}: expected one **Altitude rule.** paragraph"
    return " ".join(hits[0].split())

# (template path, the next phase its stub names) — design AD16.
_TEMPLATES = {
    "spec-driven-dev/references/design-template-python.md": "Tasks must decide",
    "spec-driven-dev/references/design-template-java.md": "Tasks must decide",
    "project-blueprint/references/scope-template.md": "Architecture must decide",
    "project-blueprint/references/architecture-template.md": "the Plan must decide",
}


def _headings(text: str) -> list[str]:
    return [l for l in text.split("\n") if l.startswith("## ")]


def _section(text: str, heading: str) -> str:
    lines = text.split("\n")
    i = lines.index(heading)
    j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
    return "\n".join(lines[i + 1:j])


@pytest.mark.parametrize("rel", sorted(_TEMPLATES))
def test_template_has_decision_points_after_open_questions(rel):
    text = (_SKILLS / rel).read_text(encoding="utf-8")
    heads = _headings(text)
    assert heads.count("## Decision Points") == 1, rel
    assert heads[heads.index("## Open Questions") + 1] == "## Decision Points", rel
    assert _TEMPLATES[rel] in _section(text, "## Decision Points"), rel


def test_no_validator_module_reads_decision_points():
    modules = [*(_PLUGIN / "scripts").glob("*.py"), *_SKILLS.glob("*/scripts/*.py")]
    assert modules
    readers = [p.name for p in modules if "Decision Points" in p.read_text(encoding="utf-8")]
    assert readers == []


@pytest.mark.parametrize("site", list(_SITES))
def test_altitude_rule_site_carries_rule_litmus_and_owns_line(site):
    para = altitude_paragraph(site)
    owns, next_phase = _OWNS[_SITES[site][1]]
    assert RULE in para
    assert LITMUS in para
    assert owns in para
    assert (f'write "{next_phase} must decide X" under `## Decision Points`, never in '
            "the body and never as an unchecked Open Question") in para


@pytest.mark.parametrize("site", ["phase-specify", "feature-spec-analyst"])
def test_spec_sites_carry_project_structure_clause(site):
    assert PROJECT_STRUCTURE_CLAUSE in altitude_paragraph(site)


@pytest.mark.parametrize("stem", [
    "project-spec-analyst", "project-architecture-analyst",
    "feature-spec-analyst", "feature-architecture-analyst",
])
def test_drafter_altitude_rule_directly_after_write_location(stem):
    text = (_AGENTS / f"{stem}.md").read_text(encoding="utf-8")
    heads = [l for l in text.split("\n") if l.startswith("## ")]
    i = heads.index("## Iteration")
    assert heads[i + 1:i + 3] == ["## Write Location", "## Altitude Rule"]


# Spec R9: the identical sentence in both panel-review.md step 3 `Deferred` bullets.
_PANEL_REVIEW = {
    "sdd": _SKILLS / "spec-driven-dev/references/panel-review.md",
    "blueprint": _SKILLS / "project-blueprint/references/panel-review.md",
}
R9_SENTENCE = (
    "A finding whose fix would be content a lower altitude owns (the altitude rule in "
    "this phase's reference) is not written into this artifact but disposed "
    "`Deferred → <downstream artifact>`, priced per step 8, except on a `--terminal` "
    "artifact, whose archive rejects `Deferred` rows."
)


def _deferred_bullet(tier: str) -> str:
    lines = _PANEL_REVIEW[tier].read_text(encoding="utf-8").split("\n")
    return next(l for l in lines if l.startswith("   - **Deferred → `<TARGET.md>`** — "))


def test_r9_sentence_present_with_required_elements_and_identical():
    found = {}
    for tier in _PANEL_REVIEW:
        bullet = _deferred_bullet(tier)
        hits = [s for s in re.split(r"(?<=\.) (?=[A-Z])", bullet) if "lower altitude" in s]
        assert len(hits) == 1, (tier, hits)
        s = hits[0]
        assert "`Deferred → <downstream artifact>`" in s, tier
        assert "step 8" in s, tier
        assert "`--terminal`" in s, tier
        found[tier] = s
    assert found["sdd"] == found["blueprint"] == R9_SENTENCE
