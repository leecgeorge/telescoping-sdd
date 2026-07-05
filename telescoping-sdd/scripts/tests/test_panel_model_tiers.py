"""Regression guard for the '## Model tiers' panel-review doctrine (v2.18.0).

Pins, in BOTH `panel-review.md` copies, the model/effort tier assignments
(panelists -> Sonnet 5 / high, drafters -> Opus / medium) and the
"Announce tiers at dispatch" directive, plus byte-identity of the section
across the two copies (parity catches asymmetric drift; the presence checks
catch a symmetric deletion from both). Self-contained (mirrors
`test_panel_input_disk_read.py`'s AD3 stance — no shared-helper import).
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import pytest

# Repo root is parents[3]:
#   telescoping-sdd/scripts/tests/test_panel_model_tiers.py
_REPO_ROOT = Path(__file__).resolve().parents[3]
SDD = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/panel-review.md"
PB = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/panel-review.md"
BOTH = [pytest.param(SDD, id="sdd"), pytest.param(PB, id="pb")]

HEADING = "## Model tiers"
ANNOUNCE_PHRASE = "Announce tiers at dispatch"
SELF_REPORT_PHRASE = "cannot reliably report its own model"
PANELIST_TIER = "Sonnet 5, `effort: high`"
DRAFTER_TIER = "Opus, `effort: medium`"


class SectionMissingError(AssertionError):
    def __init__(self, path: Path, target: str) -> None:
        super().__init__(f"{path}: expected section not found: {target!r}")


def _extract_section(content: str, heading: str, path: Path) -> str:
    """Return the body of a ## section from heading until the next ## heading."""
    pattern = re.compile(rf"({re.escape(heading)}\n.*?)(?=\n## |\Z)", re.DOTALL)
    m = pattern.search(content)
    if not m:
        raise SectionMissingError(path, heading)
    return m.group(1)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", BOTH)
def test_model_tiers_section_present(path: Path) -> None:
    section = _extract_section(_read(path), HEADING, path)
    assert section.strip(), f"'{HEADING}' is empty in {path}"


@pytest.mark.parametrize("path", BOTH)
def test_tier_assignments_present(path: Path) -> None:
    section = _extract_section(_read(path), HEADING, path)
    assert PANELIST_TIER in section, (
        f"Panelist tier {PANELIST_TIER!r} missing from '{HEADING}' in {path}"
    )
    assert DRAFTER_TIER in section, (
        f"Drafter tier {DRAFTER_TIER!r} missing from '{HEADING}' in {path}"
    )


@pytest.mark.parametrize("path", BOTH)
def test_announce_directive_present(path: Path) -> None:
    section = _extract_section(_read(path), HEADING, path)
    assert ANNOUNCE_PHRASE in section, (
        f"Announce directive {ANNOUNCE_PHRASE!r} missing from '{HEADING}' in {path}; "
        f"the orchestrator will not surface which model each agent runs"
    )
    assert SELF_REPORT_PHRASE in section, (
        f"Self-report caveat {SELF_REPORT_PHRASE!r} missing from '{HEADING}' in {path}; "
        f"the config-over-self-report rule is unstated"
    )


def test_model_tiers_byte_identical_across_copies() -> None:
    pb_block = _extract_section(_read(PB), HEADING, PB)
    sdd_block = _extract_section(_read(SDD), HEADING, SDD)
    if pb_block != sdd_block:
        diff = "".join(
            difflib.unified_diff(
                pb_block.splitlines(keepends=True),
                sdd_block.splitlines(keepends=True),
                fromfile=str(PB),
                tofile=str(SDD),
            )
        )
        pytest.fail(
            f"'{HEADING}' is not byte-identical across both panel-review.md copies; "
            f"the tier doctrine has drifted:\n{diff}"
        )


# ---------------------------------------------------------------------------
# Per-agent frontmatter tier pinning (context-window-inflow-reduction Q2/AD14):
# the two new thin agents are pinned to Sonnet/high in their own frontmatter.
# ---------------------------------------------------------------------------

_AGENTS_DIR = _REPO_ROOT / "telescoping-sdd" / "agents"


def _frontmatter(path: Path) -> dict:
    """Parse the leading `---`-delimited YAML frontmatter into a flat dict.

    Only the flat `key: value` scalars this repo's agent files use are parsed;
    values are stripped of surrounding quotes.
    """
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: no frontmatter fence"
    end = text.index("\n---", 4)
    out: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip().strip("'\"")
    return out


def test_panel_condenser_frontmatter_model_effort() -> None:
    """AD14: panel-condenser.md pins model: sonnet / effort: high; name matches file."""
    path = _AGENTS_DIR / "panel-condenser.md"
    assert path.is_file(), f"missing thin agent file: {path}"
    fm = _frontmatter(path)
    assert fm.get("name") == "panel-condenser", fm
    assert fm.get("model") == "sonnet", fm
    assert fm.get("effort") == "high", fm


def test_panel_condenser_model_tier_bullet_present() -> None:
    """T5/AD14: '## Model tiers' names panel-condenser at Sonnet/high in BOTH
    copies (byte-identity is already guarded by
    test_model_tiers_byte_identical_across_copies)."""
    for path in (SDD, PB):
        section = _extract_section(_read(path), HEADING, path)
        assert "panel-condenser" in section, f"{path}: condenser tier bullet absent"
        assert PANELIST_TIER in section  # 'Sonnet 5, `effort: high`'


def test_consistency_reader_frontmatter_model_effort() -> None:
    """AD14/T7: consistency-reader.md pins model: sonnet / effort: high; name matches."""
    path = _AGENTS_DIR / "consistency-reader.md"
    assert path.is_file(), f"missing thin agent file: {path}"
    fm = _frontmatter(path)
    assert fm.get("name") == "consistency-reader", fm
    assert fm.get("model") == "sonnet", fm
    assert fm.get("effort") == "high", fm


def test_consistency_reader_model_tier_bullet_present_both_copies() -> None:
    """T9/AD14: '## Model tiers' names consistency-reader at Sonnet/high in BOTH copies."""
    for path in (SDD, PB):
        section = _extract_section(_read(path), HEADING, path)
        assert "consistency-reader" in section, f"{path}: consistency-reader tier bullet absent"
        assert PANELIST_TIER in section  # 'Sonnet 5, `effort: high`'


def test_model_tiers_section_byte_identical_after_consistency_reader() -> None:
    """R5: the '## Model tiers' section stays byte-identical across copies after
    both the panel-condenser (T5) and consistency-reader (T9) bullets land."""
    pb_block = _extract_section(_read(PB), HEADING, PB)
    sdd_block = _extract_section(_read(SDD), HEADING, SDD)
    assert "consistency-reader" in pb_block and "consistency-reader" in sdd_block
    assert pb_block == sdd_block, "Model tiers section drifted across copies"
