"""Pins the progressive-disclosure split of both `panel-review.md` copies
(workflow-context-reduction R1/R2/R4).

Inventory, verbatim-relocation fidelity (against the pre-split goldens in
`_wcr_goldens.py`, modulo an enumerated allow-list), per-section Read-pointers,
positional-pointer hygiene, cross-copy symmetry, no-dangling-link, See-also
presence, the digest structural backstop, the R2 every-archive trim-prose
correction, and the SKILL-body stale-claim guard.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from _panel_doc_helpers import extract_section  # noqa: E402
from _wcr_goldens import BP_PRESPLIT, SDD_PRESPLIT  # noqa: E402

_REPO = Path(__file__).resolve().parents[3]
SDD = _REPO / "telescoping-sdd" / "skills" / "spec-driven-dev" / "references"
BP = _REPO / "telescoping-sdd" / "skills" / "project-blueprint" / "references"
SDD_SKILL = _REPO / "telescoping-sdd" / "skills" / "spec-driven-dev" / "SKILL.md"
BP_SKILL = _REPO / "telescoping-sdd" / "skills" / "project-blueprint" / "SKILL.md"

SKILLDIRS = {"sdd": SDD, "blueprint": BP}
GOLDENS = {"sdd": SDD_PRESPLIT, "blueprint": BP_PRESPLIT}

MOVED = {
    "## Halt and Re-scope Exit": "convergence",
    "## Strict-Bar Convergence Mode": "convergence",
    "## Lightweight Mode (single-pass panel)": "modes",
    "## When to Skip the Panel": "modes",
    "## Handling change requests at the review gate": "modes",
}
CORE_COMMON = [
    "## Path placeholders",
    "## Minimum to run the NORMAL loop",
    "## Panelists per phase",
    "## Model tiers",
    "## The Loop",
    "## Autonomy Boundary",
    "## Panel Review section format",
    "## Concern tagging (Phase 2 and 3)",
    "## Synthesizer Self-Check",
    "## Situational panel modes (loaded on demand)",
]
CONV_SECTIONS = ["## Halt and Re-scope Exit", "## Strict-Bar Convergence Mode"]
MODES_SECTIONS = [
    "## Lightweight Mode (single-pass panel)",
    "## When to Skip the Panel",
    "## Handling change requests at the review gate",
]
# The ONLY divergences allowed between the pre-split golden body and the relocated
# sub-ref body — the positional cross-refs the split had to rewrite.
ALLOWLIST = [
    ("(panel skip, below)", "(`panel-review-modes.md § When to Skip the Panel`)"),
    (
        "**Synthesizer Self-Check** (§ above)",
        "**Synthesizer Self-Check** (`panel-review.md § Synthesizer Self-Check`)",
    ),
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _h2(text: str) -> list[str]:
    return [ln.strip() for ln in text.split("\n") if ln.startswith("## ")]


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #
def _check_core_inventory(skill: str) -> None:
    heads = set(_h2(_read(SKILLDIRS[skill] / "panel-review.md")))
    for h in CORE_COMMON:
        assert h in heads, f"{skill} CORE missing {h!r}"
    # SDD-only delta: CFC Compliance Check
    if skill == "sdd":
        assert "## CFC Compliance Check" in heads
    else:
        assert "## CFC Compliance Check" not in heads
    for h in MOVED:
        assert h not in heads, f"{skill} CORE still contains moved section {h!r}"


def test_core_inventory_sdd():
    _check_core_inventory("sdd")


def test_core_inventory_blueprint():
    _check_core_inventory("blueprint")


def test_subref_inventory_convergence():
    for skill in ("sdd", "blueprint"):
        conv = _read(SKILLDIRS[skill] / "panel-review-convergence.md")
        assert _h2(conv) == CONV_SECTIONS, f"{skill} convergence: {_h2(conv)}"


def test_subref_inventory_modes():
    for skill in ("sdd", "blueprint"):
        modes = _read(SKILLDIRS[skill] / "panel-review-modes.md")
        assert _h2(modes) == MODES_SECTIONS, f"{skill} modes: {_h2(modes)}"


# --------------------------------------------------------------------------- #
# Verbatim relocation fidelity
# --------------------------------------------------------------------------- #
def test_moved_sections_verbatim_except_allowlist():
    for skill, golden in GOLDENS.items():
        base = SKILLDIRS[skill]
        subref = {
            "convergence": _read(base / "panel-review-convergence.md"),
            "modes": _read(base / "panel-review-modes.md"),
        }
        for heading, home in MOVED.items():
            g = extract_section(golden, heading)
            for old, new in ALLOWLIST:
                g = g.replace(old, new)
            s = extract_section(subref[home], heading)
            assert g.rstrip() == s.rstrip(), (
                f"{skill} {heading!r}: relocated body diverged from the pre-split "
                f"golden outside the allow-list"
            )


# --------------------------------------------------------------------------- #
# Per-section Read-pointers
# --------------------------------------------------------------------------- #
def test_per_section_read_pointer_present():
    for skill in ("sdd", "blueprint"):
        core = _read(SKILLDIRS[skill] / "panel-review.md")
        for heading, home in MOVED.items():
            title = heading[len("## "):]
            bold = f"**{title}**"
            read_ptr = f"Read `panel-review-{home}.md`"
            ok = any(
                bold in ln and read_ptr in ln and "when" in ln.lower()
                for ln in core.split("\n")
            )
            assert ok, f"{skill} CORE missing a Read-pointer for {title!r}"


# --------------------------------------------------------------------------- #
# Positional-pointer hygiene
# --------------------------------------------------------------------------- #
_POS_HEADING = re.compile(r"`## ([^`]+)`[^.\n]{0,50}?\b(?:above|below)\b")
_BAD_PROSE = (
    "panel skip, below",
    "panel skip, above",
    "When to Skip the Panel, below",
    "When to Skip the Panel, above",
)


def test_positional_pointer_hygiene():
    for skill in ("sdd", "blueprint"):
        base = SKILLDIRS[skill]
        for fname in ("panel-review.md", "panel-review-convergence.md", "panel-review-modes.md"):
            text = _read(base / fname)
            local = set(_h2(text))
            for m in _POS_HEADING.finditer(text):
                cited = "## " + m.group(1)
                assert cited in local, (
                    f"{skill}/{fname}: positional locator to {cited!r} whose target "
                    f"is not co-located in this file"
                )
            for bad in _BAD_PROSE:
                assert bad not in text, f"{skill}/{fname}: dangling positional prose {bad!r}"


# --------------------------------------------------------------------------- #
# Cross-copy symmetry
# --------------------------------------------------------------------------- #
def test_cross_copy_symmetry():
    sdd_core = set(_h2(_read(SDD / "panel-review.md")))
    bp_core = set(_h2(_read(BP / "panel-review.md")))
    # documented delta: SDD carries `## CFC Compliance Check`; blueprint does not
    assert sdd_core - {"## CFC Compliance Check"} == bp_core, (
        f"CORE section-set mismatch: sdd-only={sdd_core - bp_core}, "
        f"bp-only={bp_core - sdd_core}"
    )
    assert _h2(_read(SDD / "panel-review-convergence.md")) == _h2(
        _read(BP / "panel-review-convergence.md")
    )
    assert _h2(_read(SDD / "panel-review-modes.md")) == _h2(
        _read(BP / "panel-review-modes.md")
    )


# --------------------------------------------------------------------------- #
# No dangling link into a moved section (all citation styles, plugin-wide)
# --------------------------------------------------------------------------- #
_PR_TOK = re.compile(r"panel-review(?:-convergence|-modes)?\.md")


def _scan_files() -> list[Path]:
    files: list[Path] = []
    for base in (SDD, BP):
        files += list(base.glob("*.md"))
    files += [SDD_SKILL, BP_SKILL]
    for sub in ("agents", "agent-references"):
        files += list((_REPO / "telescoping-sdd" / sub).glob("*.md"))
    files += list((_REPO / "telescoping-sdd" / "scripts" / "tests").glob("*.py"))
    files.append(_REPO / "CLAUDE.md")
    # exclude the sub-ref homes (where the sections legitimately live) and the
    # pre-split golden snapshot (it embeds the old, pre-split cross-refs verbatim)
    excl = {"panel-review-convergence.md", "panel-review-modes.md", "_wcr_goldens.py"}
    return [f for f in files if f.name not in excl]


def test_no_dangling_link_into_moved_section():
    dangles: list[str] = []
    for f in _scan_files():
        for i, line in enumerate(_read(f).split("\n"), 1):
            for heading, home in MOVED.items():
                he = re.escape(heading[len("## "):])
                cite = re.compile(r'(§ "?%s"?|under ## %s|`## %s`)' % (he, he, he))
                for hm in cite.finditer(line):
                    before = [m for m in _PR_TOK.finditer(line) if m.start() < hm.start()]
                    if not before:
                        continue  # a moved-heading name without a panel-review file token
                    nearest = before[-1].group(0)
                    if nearest != f"panel-review-{home}.md":
                        dangles.append(f"{f.name}:{i}: {heading!r} -> {nearest}")
    assert not dangles, "dangling citations to moved sections:\n" + "\n".join(dangles)


# --------------------------------------------------------------------------- #
# See-also presence
# --------------------------------------------------------------------------- #
def test_see_also_names_both_subrefs():
    for skill_md in (SDD_SKILL, BP_SKILL):
        seealso = extract_section(_read(skill_md), "## See also")
        assert "panel-review-convergence.md" in seealso, f"{skill_md.name} See-also missing convergence"
        assert "panel-review-modes.md" in seealso, f"{skill_md.name} See-also missing modes"


# --------------------------------------------------------------------------- #
# Digest structural backstop
# --------------------------------------------------------------------------- #
def test_digest_structural_backstop():
    for skill in ("sdd", "blueprint"):
        core = _read(SKILLDIRS[skill] / "panel-review.md")
        core_heads = _h2(core)
        digest = extract_section(core, "## Minimum to run the NORMAL loop")
        for tok in re.findall(r"`(## [^`]+)`", digest):
            resolved = any(h == tok or h.startswith(tok) for h in core_heads)
            assert resolved, f"{skill} digest token {tok!r} does not resolve to a CORE section"


# --------------------------------------------------------------------------- #
# R2 every-archive trim-prose correction (the C1/AD6 anchor)
# --------------------------------------------------------------------------- #
def _panel_format_region(core: str) -> str:
    lines = core.split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "## Panel Review section format")
    end = next(i for i, ln in enumerate(lines) if ln.strip().startswith("## Concern tagging"))
    return "\n".join(lines[start:end])


def test_trajectory_trim_prose_updated_both_skills():
    for skill in ("sdd", "blueprint"):
        region = _panel_format_region(_read(SKILLDIRS[skill] / "panel-review.md"))
        assert "Trajectory trim on approval" not in region, (
            f"{skill}: stale 'Trajectory trim on approval' prose remains"
        )
        assert ("Trajectory trim on every archive" in region or "every archive pass" in region), (
            f"{skill}: every-archive trim-timing prose missing"
        )


# --------------------------------------------------------------------------- #
# SKILL-body stale-claim guard (informal prose complement to no-dangling)
# --------------------------------------------------------------------------- #
_PR_FILE = re.compile(r"panel-review(?:-convergence|-modes)?\.md")
_MOVED_ALIASES = (
    "halt-and-rescope",
    "strict-bar",
    "panel skip",
    "panel-skip",
    "lightweight mode",
    "when to skip",
)


def _machinery_and_seealso_spots(text: str) -> list[str]:
    spots = []
    for ln in text.split("\n"):
        if "shared panel-review machinery" in ln:
            spots.append(ln)
        elif ln.strip().startswith("- `references/panel-review.md`"):
            spots.append(ln)
    return spots


def test_skill_bodies_no_stale_panel_review_claim():
    for skill_md in (SDD_SKILL, BP_SKILL):
        for spot in _machinery_and_seealso_spots(_read(skill_md)):
            low = spot.lower()
            for alias in _MOVED_ALIASES:
                idx = low.find(alias)
                while idx != -1:
                    m = _PR_FILE.search(spot, idx)
                    assert not (m and m.group(0) == "panel-review.md"), (
                        f"{skill_md.name}: moved topic {alias!r} attributed to bare "
                        f"panel-review.md in: {spot[:90]!r}"
                    )
                    idx = low.find(alias, idx + len(alias))
