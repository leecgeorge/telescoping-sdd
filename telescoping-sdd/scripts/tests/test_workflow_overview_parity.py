"""R5/R6 parity guard for the reset-at-gate doctrine (AD6).

A sibling to `test_hash_and_cascade_parity.py` (NOT an extension — that module is
scoped to the two `hash-and-cascade.md` content contracts; the reset-offer
doctrine lives in `workflow-overview.md` + `SKILL.md`). It reuses the shared
section-extraction helpers from `_panel_doc_helpers.py` and mirrors the
precedent's LOCAL `_excise` / vocab-swap idiom (those symbols are defined
locally in `test_hash_and_cascade_parity.py`, not exported — the pattern is
reproduced here, not imported).

Asserts:
  * the five DM2 named-presence anchors appear in BOTH `workflow-overview.md`;
  * `SKILL_ACTIVE_ANCHOR` appears in BOTH `SKILL.md` reset paragraphs and
    `SKILL_PASSIVE_ABSENT` appears in NEITHER;
  * after excising the DM3 per-tier fragments and applying the
    `validate_spec.py`→`validate_blueprint.py` / `<spec-dir>`→`blueprint/`
    vocab swap, the shared prose is equal for both the `workflow-overview.md`
    pair and the `SKILL.md` pair.

The anchor constants byte-match the strings T7/T8 wrote.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))
from _panel_doc_helpers import extract_section as _extract_section  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
SDD_WO = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/workflow-overview.md"
PB_WO = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/workflow-overview.md"
SDD_SKILL = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/SKILL.md"
PB_SKILL = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/SKILL.md"

RESET_SECTION_HEADING = "## Context Management — Resetting at Gates"

# --- DM2 named-presence anchors (byte-match T7's prose) ---------------------
ACTIVE_OFFER_ANCHOR = "offers a context reset at each approval gate"
CLEAR_VS_COMPACT_ANCHOR = "reloads it verbatim"
CLEAR_VS_COMPACT_LOSSY = "lossy summary"
ESCALATION_ANCHOR = "gate-triggered always"
READ_ADVISORY_ANCHOR = "RESET-CHECKPOINT"
PLAIN_LANGUAGE_ANCHOR = "plain-language, non-blocking conversational suggestion"

WO_ANCHORS = [
    ACTIVE_OFFER_ANCHOR,
    CLEAR_VS_COMPACT_ANCHOR,
    CLEAR_VS_COMPACT_LOSSY,
    ESCALATION_ANCHOR,
    READ_ADVISORY_ANCHOR,
    PLAIN_LANGUAGE_ANCHOR,
]

# --- SKILL.md anchors -------------------------------------------------------
SKILL_ACTIVE_ANCHOR = "offers a context reset"
SKILL_PASSIVE_ABSENT = "opt-in and advisory — never automatic, never forced"
SKILL_RESET_PARAGRAPH_PREFIX = (
    "**Each approval gate is a safe context-reset checkpoint.**"
)

# --- DM3 per-tier excision fragments ----------------------------------------
WO_SDD_EXCISION_ANCHOR = "**Phase-4 / Implement completion-gate offer.**"
WO_PB_EXCISION_ANCHOR = "**Plan is the terminal blueprint gate.**"
# The SKILL.md SDD-only parenthetical is INLINE (not a paragraph), so it is
# removed by exact substring (leading space included so no double space remains).
SKILL_SDD_PARENTHETICAL = " (and, for Phase 4, after the completion checklist)"

VOCABULARY_SWAP_MAP = {
    "validate_spec.py": "validate_blueprint.py",
    "<spec-dir>": "blueprint/",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _excise(text: str, anchor: str) -> str:
    """Remove the paragraph/block starting at `anchor` until the next blank line
    (mirrors the local helper in test_hash_and_cascade_parity.py)."""
    idx = text.find(anchor)
    if idx == -1:
        return text
    rest = text[idx:]
    end_match = re.search(r"\n\n", rest)
    end_idx = idx + (end_match.end() if end_match else len(rest))
    return text[:idx] + text[end_idx:]


def _apply_swap(text: str, mapping: dict) -> str:
    for src in sorted(mapping.keys(), key=len, reverse=True):
        text = text.replace(src, mapping[src])
    return text


def _reset_paragraph(path: Path) -> str:
    for line in _read(path).splitlines():
        if line.startswith(SKILL_RESET_PARAGRAPH_PREFIX):
            return line
    pytest.fail(f"reset-summary paragraph not found in {path}")


def test_workflow_overview_anchors_present_in_both_tiers():
    sdd_section = _extract_section(_read(SDD_WO), RESET_SECTION_HEADING)
    pb_section = _extract_section(_read(PB_WO), RESET_SECTION_HEADING)
    for anchor in WO_ANCHORS:
        assert anchor in sdd_section, f"SDD workflow-overview missing anchor: {anchor!r}"
        assert anchor in pb_section, f"PB workflow-overview missing anchor: {anchor!r}"


def test_skill_md_active_anchor_present_and_passive_absent():
    sdd_para = _reset_paragraph(SDD_SKILL)
    pb_para = _reset_paragraph(PB_SKILL)
    assert SKILL_ACTIVE_ANCHOR in sdd_para
    assert SKILL_ACTIVE_ANCHOR in pb_para
    assert SKILL_PASSIVE_ABSENT not in sdd_para
    assert SKILL_PASSIVE_ABSENT not in pb_para


def test_workflow_overview_shared_prose_equal_after_excision():
    sdd_section = _extract_section(_read(SDD_WO), RESET_SECTION_HEADING)
    pb_section = _extract_section(_read(PB_WO), RESET_SECTION_HEADING)
    # Guard: the per-tier excision anchors must actually be present.
    assert WO_SDD_EXCISION_ANCHOR in sdd_section, "SDD excision anchor missing"
    assert WO_PB_EXCISION_ANCHOR in pb_section, "PB excision anchor missing"

    sdd_excised = _excise(sdd_section, WO_SDD_EXCISION_ANCHOR)
    pb_excised = _excise(pb_section, WO_PB_EXCISION_ANCHOR)
    sdd_normalized = _apply_swap(sdd_excised, VOCABULARY_SWAP_MAP)
    assert sdd_normalized == pb_excised, (
        "workflow-overview shared prose diverged after DM3 excision + vocab swap"
    )


def test_skill_md_shared_prose_equal_after_vocab_swap():
    sdd_para = _reset_paragraph(SDD_SKILL)
    pb_para = _reset_paragraph(PB_SKILL)
    assert SKILL_SDD_PARENTHETICAL in sdd_para, "SDD parenthetical fragment missing"
    sdd_excised = sdd_para.replace(SKILL_SDD_PARENTHETICAL, "")
    sdd_normalized = _apply_swap(sdd_excised, VOCABULARY_SWAP_MAP)
    assert sdd_normalized == pb_para, (
        "SKILL.md shared prose diverged after per-tier excision + vocab swap"
    )


def test_parity_module_lives_in_shared_scripts_tests():
    """R6 AC4: this guard lives in telescoping-sdd/scripts/tests/."""
    assert _TESTS == _REPO_ROOT / "telescoping-sdd" / "scripts" / "tests"
