"""Unit D (T31, C1, C8): both `SKILL.md` files stay within CLAUDE.md's
5,000-word budget, and their swept sites carry the taper and posture text.

The budget is measured the `wc -w` way (`len(text.split())`). It is
persistent: a later edit that pushes either file over 5,000 fails here.
Never raise the limit to make this pass; cut or move text instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILLS = Path(__file__).resolve().parents[2] / "skills"
SKILL_MD = {
    "sdd": _SKILLS / "spec-driven-dev" / "SKILL.md",
    "blueprint": _SKILLS / "project-blueprint" / "SKILL.md",
}
WORD_BUDGET = 5000

_TIERS = ["sdd", "blueprint"]


def _text(tier: str) -> str:
    return SKILL_MD[tier].read_text(encoding="utf-8")


def _paragraph(tier: str, needle: str) -> str:
    return next(p for p in _text(tier).split("\n\n") if needle in p)


@pytest.mark.parametrize("tier", _TIERS)
def test_skill_md_within_word_budget(tier):
    n = len(_text(tier).split())
    assert n <= WORD_BUDGET, f"{SKILL_MD[tier]}: {n} words > {WORD_BUDGET}"


@pytest.mark.parametrize("tier", _TIERS)
def test_skill_md_lightweight_paragraph_names_persisted_vibe(tier):
    p = _paragraph(tier, "run the panel in **lightweight mode**")
    assert ("lightweight mode is opt-in, or selected by a persisted `vibe` posture "
            "(`references/panel-review.md` § Rigour posture)") in p
    assert "opt-in only" not in p


@pytest.mark.parametrize("tier", _TIERS)
def test_skill_md_panel_review_phrase_names_taper(tier):
    p = _paragraph(tier, "via the Agent tool, both the initial drafting AND")
    assert "three-persona" not in p
    assert ("**panel review** (three personas; passes after a loop's first may run fewer"
            " — `references/panel-review.md` § Tapered roster)") in p
    # The delegation sentence: trivial carve-out is out-of-loop only, and the
    # in-loop branch points at the tier home.
    assert "Trivial out-of-loop edits stay orchestrator-direct;" in p
    assert "`references/panel-review.md` § Applying a pass's fixes" in p
