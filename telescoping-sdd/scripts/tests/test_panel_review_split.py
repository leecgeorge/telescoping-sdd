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
# Divergences allowed between the pre-split golden body and the relocated sub-ref
# body. Two named lists, applied in sequence, because they are two different
# kinds of divergence with two different disciplines (AD16):
#
#   SPLIT_REWRITES           the positional cross-refs the SPLIT itself had to
#                            rewrite. Unscoped, all-occurrences — exactly as
#                            before; this half is unchanged.
#   POST_SPLIT_CONTENT_EDITS deliberate CONTENT edits landed after the split, by
#                            features that must touch a MOVED section. Each is
#                            section-scoped and must match EXACTLY ONE
#                            occurrence inside that heading's golden extract.
#
# The pattern is EXTEND THIS LIST, NEVER EDIT THE GOLDENS: `_wcr_goldens.py` is
# the pre-split provenance snapshot, and rewriting it would make the fidelity
# check compare the change against itself.
SPLIT_REWRITES = [
    ("(panel skip, below)", "(`panel-review-modes.md § When to Skip the Panel`)"),
    (
        "**Synthesizer Self-Check** (§ above)",
        "**Synthesizer Self-Check** (`panel-review.md § Synthesizer Self-Check`)",
    ),
]

# (heading, old, new) — `heading` scopes the substitution to one MOVED section.
POST_SPLIT_CONTENT_EDITS: list[tuple[str, str, str]] = [
    # severity-definition-and-exit-predicate (v2.25.0): the unresolved-HIGH
    # exit predicate. These land in the SAME commit as the prose edit — the
    # fidelity check goes red the instant the convergence prose changes.
    (
        '## Strict-Bar Convergence Mode',
        'If a strict-bar pass returns HIGHs, those are genuine this-phase decisions — dispose them normally (often `Sealed`, `Accepted as risk`, or `User input needed`) and run another pass. Mode stays STRICT-BAR.',
        'If a strict-bar pass returns HIGHs, those are genuine this-phase decisions. Which way the pass goes depends on how they are disposed — the same unresolved-HIGH test `## The Loop` step 8 states:\n\n- **Any HIGH is left unresolved** — disposed `Addressed`, `Deferred → <target>`, `User input needed`, `Halt and re-scope`, or not yet disposed — dispose them normally and run another pass. Mode stays STRICT-BAR. This is unchanged from before.\n- **Every HIGH this pass is disposed `Sealed` or `Accepted as risk`** (each carrying its recorded `Defense:`) — the pass **converged**. Do not run another pass for them. Because this is a STRICT-BAR pass, it exits through the **exit cross-check** below rather than exiting directly.\n- **No HIGH at all** — converged; likewise take the exit cross-check.\n\nThis and `### Exit paths by mode` state one rule between them: a STRICT-BAR pass with no *unresolved* HIGH routes to the cross-check; one with any unresolved HIGH loops.',
    ),
    (
        '## Strict-Bar Convergence Mode',
        '| NORMAL | 0 HIGHs | Exit directly (strict bar never ran, so no cross-check needed) |',
        '| NORMAL | 0 unresolved HIGHs | Exit directly (strict bar never ran, so no cross-check needed) |',
    ),
    (
        '## Strict-Bar Convergence Mode',
        '| NORMAL | HIGHs remain | At the 5-pass cap',
        '| NORMAL | unresolved HIGHs remain | At the 5-pass cap',
    ),
    (
        '## Strict-Bar Convergence Mode',
        '| STRICT-BAR | 0 HIGHs | Run the exit cross-check (above) before exiting |',
        '| STRICT-BAR | 0 unresolved HIGHs | Run the exit cross-check (above) before exiting |',
    ),
    (
        '## Strict-Bar Convergence Mode',
        '| STRICT-BAR | HIGHs remain | At the 5-pass cap',
        '| STRICT-BAR | unresolved HIGHs remain | At the 5-pass cap',
    ),
    (
        '## Halt and Re-scope Exit',
        'distinct from the HIGH-count exit (which fires on successful convergence).',
        'distinct from the unresolved-HIGH exit (which fires on successful convergence — a pass leaving no HIGH other than those dismissed with a recorded `Defense:`; see `## The Loop` step 8).',
    ),
    (
        '## Strict-Bar Convergence Mode',
        'When a STRICT-BAR pass returns **zero HIGHs**, do not exit directly.',
        'When a STRICT-BAR pass returns **zero unresolved HIGHs** — no HIGH other than those disposed `Sealed` / `Accepted as risk` — do not exit directly.',
    ),
    (
        '## Strict-Bar Convergence Mode',
        '- **Cross-check returns 0 HIGHs** → exit the loop. Proceed to validation.',
        '- **Cross-check returns 0 unresolved HIGHs** → exit the loop. Proceed to validation.',
    ),
]


def _apply_allowlists(golden_section: str, heading: str) -> str:
    """Apply both allow-lists to one extracted golden section.

    `SPLIT_REWRITES` keeps its historical unscoped, all-occurrences semantics.
    `POST_SPLIT_CONTENT_EDITS` is scoped to `heading` and bounded to exactly one
    occurrence — the bound is asserted here rather than left to `replace`, since
    an unbounded `replace` is precisely how one entry silently excuses a second,
    unclassified divergence.
    """
    for old, new in SPLIT_REWRITES:
        golden_section = golden_section.replace(old, new)
    for entry_heading, old, new in POST_SPLIT_CONTENT_EDITS:
        if entry_heading != heading:
            continue
        found = golden_section.count(old)
        assert found == 1, (
            f"POST_SPLIT_CONTENT_EDITS entry for {entry_heading!r} matched "
            f"{found} occurrences of {old[:60]!r}, expected exactly 1"
        )
        golden_section = golden_section.replace(old, new, 1)
    return golden_section


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
            g = _apply_allowlists(extract_section(golden, heading), heading)
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


# --------------------------------------------------------------------------- #
# POST_SPLIT_CONTENT_EDITS bounds (AD16 / AD10 discipline)
# --------------------------------------------------------------------------- #
def _golden_sections_for(heading: str) -> dict:
    return {skill: extract_section(golden, heading) for skill, golden in GOLDENS.items()}


def test_post_split_entry_matches_exactly_one_occurrence():
    """Upper bound: an entry must not silently excuse a second divergence.

    Asserted per tier, because an entry is applied to both and a phrase that is
    unique in one copy is not guaranteed unique in the other.
    """
    for heading, old, _new in POST_SPLIT_CONTENT_EDITS:
        assert heading in MOVED, (
            f"POST_SPLIT_CONTENT_EDITS entry names {heading!r}, which is not a "
            f"MOVED section; only MOVED sections are golden-checked."
        )
        for skill, section in _golden_sections_for(heading).items():
            found = section.count(old)
            assert found == 1, (
                f"{skill} {heading!r}: entry old-text {old[:60]!r} occurs "
                f"{found} times in the golden extract, expected exactly 1."
            )


def test_post_split_has_no_unused_entry():
    """Lower bound: an entry whose target was reworded away must not linger."""
    unused = []
    for heading, old, _new in POST_SPLIT_CONTENT_EDITS:
        if heading not in MOVED:
            continue
        if not any(old in sec for sec in _golden_sections_for(heading).values()):
            unused.append((heading, old[:60]))
    assert not unused, (
        f"POST_SPLIT_CONTENT_EDITS entries match nothing in the goldens and "
        f"have rotted into permanent waivers: {unused}"
    )


def test_post_split_substitution_is_order_independent():
    """Applying the entries in reverse must give the same result (`[DEF-15]`).

    The exactly-one-occurrence bound is what makes order irrelevant; this is
    what proves it stayed that way as entries accumulate.
    """
    global POST_SPLIT_CONTENT_EDITS
    original = POST_SPLIT_CONTENT_EDITS
    try:
        for skill, golden in GOLDENS.items():
            for heading in MOVED:
                POST_SPLIT_CONTENT_EDITS = original
                forward = _apply_allowlists(extract_section(golden, heading), heading)
                POST_SPLIT_CONTENT_EDITS = list(reversed(original))
                reverse = _apply_allowlists(extract_section(golden, heading), heading)
                assert forward == reverse, (
                    f"{skill} {heading!r}: allow-list substitution is "
                    f"order-dependent; two entries must be overlapping."
                )
    finally:
        POST_SPLIT_CONTENT_EDITS = original
