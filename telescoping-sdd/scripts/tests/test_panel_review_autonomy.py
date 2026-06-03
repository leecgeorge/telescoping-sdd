"""R5 presence tests for the `## Autonomy Boundary` section in both
`panel-review.md` copies.

Presence-grade (NOT full structural parity): asserts the heading + the four
load-bearing, vocabulary-neutral phrases appear in BOTH copies, the section
sits between `## The Loop` and `## Panel Review section format`, and the PB copy
carries no SDD-only vocabulary. Shares `_panel_doc_helpers` with
`test_hash_and_cascade_parity.py` (one definition, no drift).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from _panel_doc_helpers import PB_FORBIDDEN_SDD_VOCABULARY, extract_section

SDD = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/panel-review.md"
PB = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/panel-review.md"
BOTH = [pytest.param(SDD, id="sdd"), pytest.param(PB, id="pb")]

HEADING = "## Autonomy Boundary"

# The four load-bearing phrases, authored vocabulary-neutral so ONE constant
# matches both copies (AD10). (a)-(c) are verbatim; (d) is the representative
# substring of the pre-flight contract.
PHRASE_A = "running the next pass is not a user decision"
PHRASE_B_FRAGMENT = "no doctrine-shortcut menus"
PHRASE_C_FRAGMENT = "operational concerns never override doctrine"
PHRASE_D_FRAGMENT = "run the loop to convergence autonomously"
PHRASES = [
    pytest.param(PHRASE_A, id="a"),
    pytest.param(PHRASE_B_FRAGMENT, id="b"),
    pytest.param(PHRASE_C_FRAGMENT, id="c"),
    pytest.param(PHRASE_D_FRAGMENT, id="d"),
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", BOTH)
def test_autonomy_boundary_heading(path: Path) -> None:
    assert HEADING in _read(path), f"`{HEADING}` missing from {path}"


@pytest.mark.parametrize("phrase", PHRASES)
def test_phrase_in_both_copies(phrase: str) -> None:
    assert phrase in _read(SDD), f"phrase {phrase!r} missing from SDD panel-review.md"
    assert phrase in _read(PB), f"phrase {phrase!r} missing from PB panel-review.md"


@pytest.mark.parametrize("path", BOTH)
def test_section_anchor(path: Path) -> None:
    """`## Autonomy Boundary` sits between `## The Loop` and `## Panel Review section format`."""
    content = _read(path)
    i_loop = content.index("## The Loop")
    i_auto = content.index(HEADING)
    i_fmt = content.index("## Panel Review section format")
    assert i_loop < i_auto < i_fmt, f"`{HEADING}` is mis-anchored in {path}"


def test_pb_section_no_sdd_vocab() -> None:
    """The PB `## Autonomy Boundary` section carries no SDD-only vocabulary
    (catches a botched blueprint vocabulary swap the phrase pins cannot)."""
    section = extract_section(_read(PB), HEADING)
    found = [t for t in PB_FORBIDDEN_SDD_VOCABULARY if t in section]
    assert not found, f"SDD-only vocabulary in PB `{HEADING}` section: {found}"
