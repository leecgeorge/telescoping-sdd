"""Unit D (R3): the working-files contract.

This file starts with the repository `.gitignore` pins (design C2): the
scratch root and the posture-notice sentinel are ignored, the block's comment
cites no gitignored file (spec SEAL-28), and the two maintainer-only root
files stay ignored. Later Unit D tasks add the `## Working files` doctrine
pins below.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GITIGNORE = _REPO_ROOT / ".gitignore"

C2_BLOCK = """\
# Orchestrator scratch: drafts, snapshots, diffs, sweep/census output. One
# root and one naming rule (panel-review.md § Working files). Never committed.
/.sdd/scratch/
# Per-user marker: the one-time default-posture notice has been shown.
/.sdd/posture-notice
"""


def _lines() -> list[str]:
    return _GITIGNORE.read_text(encoding="utf-8").splitlines()


def _ignored_root_files() -> list[str]:
    """Root-level file names the .gitignore ignores (`/NAME.ext` entries)."""
    return [l[1:] for l in _lines() if re.fullmatch(r"/[A-Za-z0-9_.-]+\.[A-Za-z0-9]+", l)]


def test_gitignore_scratch_block_follows_panel_findings_block():
    text = _GITIGNORE.read_text(encoding="utf-8")
    assert text.count(C2_BLOCK) == 1
    lines = _lines()
    assert lines.index("/.sdd/panel-findings/") < lines.index("/.sdd/scratch/")


def test_gitignore_names_scratch_and_posture_notice():
    lines = _lines()
    assert lines.count("/.sdd/scratch/") == 1
    assert lines.count("/.sdd/posture-notice") == 1


def test_gitignore_scratch_comment_cites_no_ignored_file():
    comment = "\n".join(l for l in C2_BLOCK.splitlines() if l.startswith("#"))
    ignored = _ignored_root_files()
    assert "WORKING-NOTES.md" in ignored  # the leak SEAL-28 closed
    for name in ignored:
        stem = name.rsplit(".", 1)[0]
        assert name not in comment and stem not in comment, name


def test_gitignore_levers_and_outstanding_present():
    lines = _lines()
    assert "/PANEL-LOOP-LEVERS.md" in lines
    assert "/OUTSTANDING.md" in lines


# ---------------------------------------------------------------------------
# T24: producer/consumer symmetry of the snapshot name (DM7)
# ---------------------------------------------------------------------------

import sys  # noqa: E402

import pytest  # noqa: E402

_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import archive_pass as ap  # noqa: E402

_PANEL_REVIEW = {
    t: _REPO_ROOT / "telescoping-sdd" / "skills" / d / "references" / "panel-review.md"
    for t, d in (("sdd", "spec-driven-dev"), ("blueprint", "project-blueprint"))
}
_GRAMMAR_RE = re.compile(
    r"`<root>/\.sdd/scratch/<scope>/<artifact-stem>-<purpose>\[-p<PASS>\[-<n>\]\]\.<ext>`")


def working_files_section(tier: str) -> str:
    lines = _PANEL_REVIEW[tier].read_text(encoding="utf-8").split("\n")
    i = lines.index("## Working files")
    j = next(k for k in range(i + 1, len(lines)) if lines[k].startswith("## "))
    return "\n".join(lines[i:j]).rstrip("\n")


def _render_grammar(stem: str, purpose: str, pass_n: int, ext: str) -> str:
    """Instantiate the quoted grammar with no `-<n>` (a route's first file)."""
    return f"{stem}-{purpose}-p{pass_n}.{ext}"


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
@pytest.mark.parametrize("rel", ["specs/F3-x/02_design.md", "blueprint/01_SCOPE.md"])
def test_snapshot_name_form_matches_snapshot_path(tmp_path, tier, rel):
    section = working_files_section(tier)
    assert _GRAMMAR_RE.search(section), "the DM7 grammar must be quoted verbatim"
    assert "`md` for `draft` and `snapshot`" in section
    art = tmp_path / rel
    expected = ap._snapshot_path(tmp_path, art, 3).name
    assert _render_grammar(art.stem, "snapshot", 3, "md") == expected
