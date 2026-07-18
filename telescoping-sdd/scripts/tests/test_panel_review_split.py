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
CONV_SECTIONS = [
    "## Halt and Re-scope Exit",
    "## Strict-Bar Convergence Mode",
    "## Terminal Compression Check",
]
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
    # v2.24.0: the strict-bar Exit cross-check now points to the terminal compression
    # check at its proceed-to-validation step (Finding-1 wiring); the pre-split golden
    # predates that section, so the pointer is a tolerated addition to the pinned body.
    (
        "**Cross-check returns 0 HIGHs** → exit the loop. Proceed to validation.",
        "**Cross-check returns 0 HIGHs** → exit the loop. Proceed to validation. "
        "**First run the terminal compression check** (`## Terminal Compression Check` in this file — "
        "the same pass the NORMAL step-8 exit runs; it applies before validation on every exit path, "
        "this one included).",
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


# --------------------------------------------------------------------------- #
# Terminal Compression Check (spec-verbosity-reduction) — R1/R3 sentinel-span
# byte-pins across the two panel-review.md copies + the R2 section/pointer wiring.
# --------------------------------------------------------------------------- #
SENTINEL_IDS = ("bake-resolution",)


def extract_sentinel_block(text: str, sid: str) -> str:
    """Return the bytes strictly between a SHARED-DOCTRINE id's open and close
    sentinels. Raises AssertionError — distinct from a span-divergence failure —
    when either sentinel is absent or unbalanced (the boundary case in I8)."""
    open_tag = f"<!-- SHARED-DOCTRINE:{sid} -->"
    close_tag = f"<!-- /SHARED-DOCTRINE:{sid} -->"
    oi = text.find(open_tag)
    ci = text.find(close_tag)
    assert oi != -1 and ci != -1 and ci > oi, (
        f"missing or unbalanced SHARED-DOCTRINE sentinel for {sid!r}"
    )
    return text[oi + len(open_tag):ci]


def test_r1_r3_shared_prose_mirrored():
    # (a) each R1/R3 sentinel span byte-identical across the two panel-review.md copies
    sdd = _read(SDD / "panel-review.md")
    bp = _read(BP / "panel-review.md")
    for sid in SENTINEL_IDS:
        a = extract_sentinel_block(sdd, sid)  # distinct AssertionError if a sentinel is missing
        b = extract_sentinel_block(bp, sid)
        assert a == b, f"SHARED-DOCTRINE span diverges across copies: {sid!r}"
    # (b) the whole ## Terminal Compression Check section byte-identical across the two convergence
    # copies — exact compare (no rstrip; tail-whitespace / trailing blank-line drift between the
    # mirrored copies is real divergence and must fail).
    ta = extract_section(_read(SDD / "panel-review-convergence.md"), "## Terminal Compression Check")
    tb = extract_section(_read(BP / "panel-review-convergence.md"), "## Terminal Compression Check")
    assert ta == tb, "## Terminal Compression Check diverges across the convergence copies"


def test_terminal_check_pointer_present():
    for skill in ("sdd", "blueprint"):
        core = _read(SKILLDIRS[skill] / "panel-review.md")
        conv = _read(SKILLDIRS[skill] / "panel-review-convergence.md")
        # (a) NORMAL-path step-8 reminder: the read-pointer must live ON the step-8 line itself,
        # not merely somewhere file-wide (the § Situational modes / See-also bullets also name the
        # file + "every convergence", so a file-wide `in core` check would false-green on a dropped pointer).
        step8 = next(
            (ln for ln in core.split("\n") if "Terminal compression check (every convergence)" in ln),
            None,
        )
        assert step8 is not None, f"{skill}: step-8 terminal-check reminder missing"
        assert "Read `panel-review-convergence.md" in step8 and "every convergence" in step8, (
            f"{skill}: step-8 reminder line missing its read-pointer / every-convergence phrasing"
        )
        # (b) both-exit-path invariant inside the ## Terminal Compression Check section
        tsec = extract_section(conv, "## Terminal Compression Check")
        assert "before Phase validation" in tsec and "any exit path" in tsec, (
            f"{skill}: terminal-check section missing the before-validation / any-exit-path invariant"
        )
        # (c) every-convergence load-note in § Situational panel modes AND the convergence blockquote
        modes = extract_section(core, "## Situational panel modes (loaded on demand)")
        assert "Not situational — loads at every convergence" in modes and "Terminal Compression Check" in modes, (
            f"{skill}: § Situational panel modes missing the every-convergence load-note"
        )
        assert "Exception — the terminal compression check is not situational" in conv, (
            f"{skill}: convergence blockquote missing the every-convergence exception note"
        )


def test_exception_blockquotes_mirrored():
    # The two new exception blockquotes must be byte-identical across tiers, like every other new
    # span this feature added — presence-per-copy alone would let the two copies silently diverge.
    def line_with(text: str, needle: str) -> str | None:
        return next((ln for ln in text.split("\n") if needle in ln), None)

    csdd = line_with(_read(SDD / "panel-review-convergence.md"), "Exception — the terminal compression check is not situational")
    cbp = line_with(_read(BP / "panel-review-convergence.md"), "Exception — the terminal compression check is not situational")
    assert csdd is not None and csdd == cbp, "convergence exception blockquote diverges across tiers"

    msdd = line_with(_read(SDD / "panel-review.md"), "Not situational — loads at every convergence")
    mbp = line_with(_read(BP / "panel-review.md"), "Not situational — loads at every convergence")
    assert msdd is not None and msdd == mbp, "§ Situational panel modes exception blockquote diverges across tiers"


# --------------------------------------------------------------------------- #
# Per-requirement doctrine-presence guards (R1–R4)
# --------------------------------------------------------------------------- #
AGENTS_DIR = _REPO / "telescoping-sdd" / "agents"
DRAFTER_AGENTS = (
    "feature-spec-analyst",
    "feature-architecture-analyst",
    "feature-task-analyst",
    "project-spec-analyst",
    "project-architecture-analyst",
    "project-plan-analyst",
)
R4_HOMES = (
    AGENTS_DIR / "feature-spec-analyst.md",
    SDD / "phase-specify.md",
    SDD / "spec-template-python.md",
    SDD / "spec-template-java.md",
)


def extract_bake_bullet(text: str) -> str:
    """Return the drafter's bake-resolution list item — from the '- **Bake the
    resolution' line up to (not including) the next top-level '- ' sibling or the
    blank line ending the item (the test-M01 extraction boundary)."""
    started = False
    out = []
    for ln in text.split("\n"):
        if not started:
            if ln.lstrip().startswith("- **Bake the resolution"):
                started = True
                out.append(ln)
            continue
        if ln.strip() == "" or ln.lstrip().startswith("- "):
            break
        out.append(ln)
    assert started, "bake-resolution bullet not found"
    return "\n".join(out)


def test_r1_canonical_and_guardrail_present():
    # R1 (terminal-only-subtraction): the two subtractive SHARED-DOCTRINE blocks
    # (canonical-section-rule + under-doc-guardrail) were REMOVED from step 3 of
    # ## The Loop. This guard is INVERTED from its pre-removal form — the
    # identifier is retained per design ("identifier may stay, but its assertions
    # flip") — and now asserts both sentinels are ABSENT from both copies.
    for skill in ("sdd", "blueprint"):
        core = _read(SKILLDIRS[skill] / "panel-review.md")
        assert "SHARED-DOCTRINE:canonical-section-rule" not in core, (
            f"{skill}: canonical-section-rule block must be removed (R1)"
        )
        assert "SHARED-DOCTRINE:under-doc-guardrail" not in core, (
            f"{skill}: under-doc-guardrail block must be removed (R1)"
        )


def test_r2_terminal_check_markers_present():
    for skill in ("sdd", "blueprint"):
        sec = extract_section(_read(SKILLDIRS[skill] / "panel-review-convergence.md"), "## Terminal Compression Check")
        for marker in (
            "**Charter.**",
            "**When it runs.**",
            "**Operator.**",
            "**Clearly-safe cut.**",
            "**Cross-reference audit.**",
            "**Relationship to the exit cross-check.**",
        ):
            assert marker in sec, f"{skill}: terminal-check fact-marker {marker!r} missing"
        # purely-subtractive / no-reopen / no-restore / no-load-bearing-deletion charter
        for phrase in ("purely subtractive", "never re-opens", "never restores", "never deletes load-bearing content"):
            assert phrase in sec, f"{skill}: charter phrase {phrase!r} missing"
        # I5 recorded-cuts rail: before→after list + declined-not-re-run
        assert "before → after" in sec and "not re-run" in sec, f"{skill}: recorded-cuts rail missing"
        # SEAL-03's always-on cross-reference audit (decoupled from the cut gate)
        assert "whether or not" in sec and "any cut is proposed" in sec, (
            f"{skill}: cross-reference-audit always-on wording missing"
        )


def test_r3_bake_resolution_present():
    for skill in ("sdd", "blueprint"):
        core = _read(SKILLDIRS[skill] / "panel-review.md")
        bake = extract_sentinel_block(core, "bake-resolution")
        assert "**Bake the resolution, not the debate.**" in bake, f"{skill}: synthesizer bake-resolution marker"
        # R2 (terminal-only-subtraction): the synth block carries the target-state
        # modality worked pair — two fixed labels IN ORDER, each followed by
        # non-empty example text. DEF-05: the labels + non-emptiness are the
        # structural anchor; semantic adequacy stays a human-review concern.
        nc = bake.find("**Non-compliant (already-true):**")
        cc = bake.find("**Compliant (target-voice):**")
        assert nc != -1 and cc != -1 and nc < cc, (
            f"{skill}: bake-resolution missing the ordered modality worked-pair labels"
        )
        between = bake[nc + len("**Non-compliant (already-true):**"):cc].strip()
        after = bake[cc + len("**Compliant (target-voice):**"):].strip()
        assert between, f"{skill}: no example text between the modality labels"
        assert after, f"{skill}: no example text after the Compliant label"
    # R2 (terminal-only-subtraction): each drafter carries the terse micro-cue
    # WITHIN its bake-resolution bullet span (not merely somewhere file-wide).
    for name in DRAFTER_AGENTS:
        bullet = extract_bake_bullet(_read(AGENTS_DIR / f"{name}.md"))
        assert "Bake the resolution, not the debate" in bullet, f"{name}: R3 drafter bullet missing"
        assert "target voice" in bullet and "already-true" in bullet, (
            f"{name}: drafter bullet missing the target-state modality micro-cue"
        )


def test_bake_resolution_bullet_six_way_parity():
    # R2 (terminal-only-subtraction): the drafter bake-resolution bullet — the whole
    # list item incl. the appended micro-cue — is byte-identical across all six drafters.
    bullets = {name: extract_bake_bullet(_read(AGENTS_DIR / f"{name}.md")) for name in DRAFTER_AGENTS}
    assert len(set(bullets.values())) == 1, (
        "drafter bake-resolution bullets diverge across the six agents"
    )


def test_convergence_retired_phrases_absent():
    # R3 / I5 (terminal-only-subtraction): the two phrases R1 made dangling are gone
    # from both convergence copies; the Terminal Check's own legitimate "purely
    # subtractive" self-description survives (the I5 substring must not catch it).
    for skill in ("sdd", "blueprint"):
        conv = _read(SKILLDIRS[skill] / "panel-review-convergence.md")
        assert "subtractive `Addressed`" not in conv, (
            f"{skill}: retired 'subtractive `Addressed`' reference still present"
        )
        assert "under-documentation guardrail" not in conv, (
            f"{skill}: retired 'under-documentation guardrail' reference still present"
        )
        assert "purely subtractive" in conv, (
            f"{skill}: legitimate 'purely subtractive' self-description missing"
        )


def test_r4_plainer_form_present():
    for home in R4_HOMES:
        text = _read(home)
        assert "**Internal/mechanical requirements:**" in text, f"{home.name}: plainer-form marker missing"
        assert "**User-facing vs internal.**" in text, f"{home.name}: observable-stakeholder heuristic missing"
        assert "GIVEN/WHEN/THEN acceptance-criteria grammar" in text and "stays mandatory and unchanged" in text, (
            f"{home.name}: GWT-stays-mandatory guardrail missing"
        )
