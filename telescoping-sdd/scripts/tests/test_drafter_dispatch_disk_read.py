"""Pins the by-path drafter-dispatch rewording (workflow-context-reduction R3).

The four upstream-context bullets instruct the drafter to read the named upstream
artifact(s) from disk (no paste); the three SDD CFC bullets carry identical
by-path wording (path + `CFC-N` ids as orientation, read the whole section from
disk) with the old "pass the contents" wording gone; and each file's CFC
binding-obligation paragraph is preserved.
"""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
SDD = _REPO / "telescoping-sdd" / "skills" / "spec-driven-dev" / "references"
BP = _REPO / "telescoping-sdd" / "skills" / "project-blueprint" / "references"

# The four phase files whose upstream-context bullet was reworded to read-from-disk.
UPSTREAM_FILES = [
    SDD / "phase-design.md",
    SDD / "phase-tasks.md",
    BP / "phase-architecture.md",
    BP / "phase-plan.md",
]
# The three SDD phase files carrying the identical CFC-by-path bullet.
CFC_FILES = [
    SDD / "phase-specify.md",
    SDD / "phase-design.md",
    SDD / "phase-tasks.md",
]
# Distinctive CFC binding-obligation paragraph markers (must survive the reword).
CFC_OBLIGATION_MARKERS = {
    SDD / "phase-specify.md": "**CFC binding obligation.**",
    SDD / "phase-design.md": "**CFC obligation.**",
    SDD / "phase-tasks.md": "**CFC enforcement-task obligation.**",
}

UPSTREAM_PHRASES = (
    "from disk in full",
    "do not paste or summarize",
    "mirroring the panelist read-from-disk discipline",
)
CFC_BULLET_MARKER = "give the agent that **file path**"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _line_with(text: str, marker: str) -> str:
    matches = [ln for ln in text.split("\n") if marker in ln]
    assert len(matches) == 1, f"expected exactly one line with {marker!r}, found {len(matches)}"
    return matches[0]


def test_upstream_by_path_phrase_in_four_phase_files():
    for f in UPSTREAM_FILES:
        text = _read(f)
        for phrase in UPSTREAM_PHRASES:
            assert phrase in text, f"{f.name}: upstream bullet missing {phrase!r}"


def test_cfc_by_path_phrase_in_three_sdd_phase_files_identical():
    bullets = [_line_with(_read(f), CFC_BULLET_MARKER) for f in CFC_FILES]
    assert len(set(bullets)) == 1, (
        "the three SDD CFC dispatch bullets must be byte-identical (R4 symmetry); got:\n"
        + "\n".join(f"  {f.name}: {b!r}" for f, b in zip(CFC_FILES, bullets))
    )
    # sanity: the identical bullet actually conveys by-path + ids-as-orientation
    bullet = bullets[0]
    assert "read the entire `## Cross-Feature Contracts` section from disk" in bullet
    assert "`CFC-N` ids" in bullet
    assert "orientation aid" in bullet


def test_old_pass_the_contents_wording_absent():
    for f in CFC_FILES:
        text = _read(f)
        assert "pass the contents" not in text, f"{f.name}: stale 'pass the contents' wording"
        assert "pass its contents" not in text, f"{f.name}: stale 'pass its contents' wording"


def test_cfc_binding_obligation_prose_preserved():
    for f, marker in CFC_OBLIGATION_MARKERS.items():
        text = _read(f)
        assert marker in text, f"{f.name}: CFC binding-obligation paragraph {marker!r} missing"
        # the obligation must still bind on `### CFC-N` participation
        assert "### CFC-N" in text, f"{f.name}: CFC obligation lost its `### CFC-N` binding"
