"""Pins the shared severity definition and the unresolved-HIGH exit predicate
(severity-definition-and-exit-predicate, R1-R7).

Two regions, per AD9:

* **Region A - Doctrine** (parts #1-#3 and R7) pins the prose: the step-1
  severity definition and review-scope blocks, the persona domain lenses, the
  CFC cost clause, the step-8 exit rule, and the lockstep restatement set.
* **Region B - Predicate** (part #4, R4-R6) pins the behaviour: the
  `high_disposition_counts` helper and the sealed-exit stamp `archive_pass.py`
  emits.

**Region boundary (AD9).** Every fixture, helper and constant Region B needs is
defined *inside* Region B's banner, and Region A references nothing defined
below its own banner. The banners are a reading aid; the no-upward-reference
rule is what actually keeps the two regions separable, and it is what makes the
one-module choice equivalent to two files for every purpose except file count.

Assertions pin load-bearing **fragments**, never whole paragraphs and never mere
heading presence: a check that a rule "is present" passes against text thinned
to nothing.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import pytest

# =============================================================================
# Region A - Doctrine (parts #1-#3, R7)
# =============================================================================

_REPO = Path(__file__).resolve().parents[3]
SDD_REFS = _REPO / "telescoping-sdd" / "skills" / "spec-driven-dev" / "references"
BP_REFS = _REPO / "telescoping-sdd" / "skills" / "project-blueprint" / "references"
AGENTS = _REPO / "telescoping-sdd" / "agents"

SDD_PANEL = SDD_REFS / "panel-review.md"
BP_PANEL = BP_REFS / "panel-review.md"

PANEL_COPIES = {"sdd": SDD_PANEL, "blueprint": BP_PANEL}
BOTH_PANELS = [(SDD_PANEL, "sdd"), (BP_PANEL, "blueprint")]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _step_1(content: str) -> str:
    """Return `## The Loop` step 1, from its lead-in to the step-2 marker.

    Scoped deliberately: the severity definition and the review scope must sit
    inside the step that composes the dispatch prompt (AD1/AD18), not merely
    somewhere in the file.
    """
    start = content.index("1. **Dispatch all three panelists")
    end = content.index("2. **Synthesize in-thread**")
    return content[start:end]


# --- C1: the shared severity definition (R1) ---------------------------------
#
# One hardcoded committed-text constant, checked by containment. No block
# extraction: the point is that these exact words reach a panelist, so the test
# must fail when any load-bearing fragment is reworded away.

C1_LABEL = (
    "**Severity definition — include this text verbatim in every panelist's "
    "dispatch prompt**"
)
C1_HIGH = (
    "`[HIGH]` — the artifact is **wrong as written**: it contradicts itself or "
    "an approved upstream artifact, regresses a decision already made, or "
    "commits to something that cannot be implemented as stated. Shipping it "
    "downstream produces rework."
)
C1_MED = (
    "`[MED]` — the artifact is correct as written but **could be better**: a "
    "clearer structure, a stronger criterion, a missing nice-to-have. \"Could "
    "be better\" is MED, never HIGH."
)
C1_LOW = (
    "`[LOW]` — cosmetic or editorial: naming, wording, ordering, a "
    "documentation gap with no downstream consequence."
)
C1_NOT_A_SYSTEM = (
    "You are reviewing a spec, a design, or a task list — a document, not a "
    "running system."
)
C1_GRADE_THE_DOCUMENT = (
    "Grade what the **document** commits to, not the production harm a "
    "hypothetical implementation might cause."
)
C1_INSTRUCTION_CARVE_OUT = (
    "Prose that reads as an instruction to whoever reads the artifact next is a "
    "defect **in the document**, and is graded on the axis above like any other."
)

C1_FRAGMENTS = (
    C1_LABEL,
    C1_HIGH,
    C1_MED,
    C1_LOW,
    C1_NOT_A_SYSTEM,
    C1_GRADE_THE_DOCUMENT,
    C1_INSTRUCTION_CARVE_OUT,
)


def _assert_c1_in_step_1(tier: str) -> None:
    step1 = _step_1(_read(PANEL_COPIES[tier]))
    for fragment in C1_FRAGMENTS:
        assert fragment in step1, (
            f"{tier} copy: `## The Loop` step 1 is missing a load-bearing "
            f"fragment of the C1 severity definition:\n  {fragment!r}"
        )


def test_c1_definition_present_sdd():
    """The severity definition sits inside step 1 of the spec-driven-dev copy."""
    _assert_c1_in_step_1("sdd")


def test_c1_definition_present_blueprint():
    """The severity definition sits inside step 1 of the project-blueprint copy."""
    _assert_c1_in_step_1("blueprint")


def test_c1_definition_identical_across_copies():
    """Both copies carry the same committed text, with no semantic difference.

    Asserted on the block itself rather than on the two files, so a divergence
    introduced inside the block cannot hide behind the copies' intentional
    asymmetries elsewhere.
    """
    blocks = {}
    for tier, path in PANEL_COPIES.items():
        content = _read(path)
        start = content.index(C1_LABEL)
        end = content.index("**Review scope —", start)
        blocks[tier] = content[start:end]
    assert blocks["sdd"] == blocks["blueprint"], (
        "The C1 severity-definition block differs between the two "
        "`panel-review.md` copies; AD1 requires them identical."
    )


def test_c1_definition_carries_the_verbatim_dispatch_obligation():
    """The label carries the obligation, so it travels with the text (AD19)."""
    for tier, path in PANEL_COPIES.items():
        step1 = _step_1(_read(path))
        assert "include this text verbatim in every panelist's dispatch prompt" in step1, (
            f"{tier} copy: the severity definition must state that it is "
            "dispatched verbatim — a file reference will not do."
        )
        assert "a file reference will not do" in step1, (
            f"{tier} copy: the parenthetical ruling out a pointer is missing."
        )


# --- C11: review scope and the `## Panel Review` carve-out (R1) --------------
#
# One named test per obligation in C11's committed text. The rationale and the
# R6-preserving clause are deliberately SEPARATE tests: they sit in the same
# bullet, so a trim of the second would otherwise pass on the first.


def _assert_fragments(tier: str, path: Path, obligation: str, fragments) -> None:
    step1 = _step_1(_read(path))
    for fragment in fragments:
        assert fragment in step1, (
            f"{tier} copy: the C11 review-scope block has lost a load-bearing "
            f"fragment of its {obligation} obligation:\n  {fragment!r}"
        )


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_c11_scope_declaration(path, tier):
    """What is under review: content sections, not the loop's own audit record."""
    _assert_fragments(tier, path, "scope-declaration", (
        "You are reviewing the artifact's **content** sections.",
        "### Trajectory",
        "### Sealed dispositions",
        "### Deferred dispositions",
        "### Latest pass detail",
        "It is **not itself under review.**",
        "Defects there are **Synthesizer Self-Check** territory",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_c11_record_not_commitment(path, tier):
    """The rationale: it is a record, not a commitment."""
    _assert_fragments(tier, path, "record-not-a-commitment", (
        "Because it is a **record, not a commitment.**",
        "a panelist cannot improve a `### Trajectory` row, because the row "
        "reports what a past pass did",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_c11_preserves_r6_audit_record(path, tier):
    """Out of review scope is NOT out of scope — R6's audit record is untouched.

    Named separately from the rationale above on purpose: both live in the
    `**Why.**` bullet, and this is the half a later trim reads as redundant.
    """
    _assert_fragments(tier, path, "R6-preserving", (
        "*\"out of review scope\"* is not *\"out of scope\"*",
        "those columns are the loop's only durable audit record and nothing "
        "here weakens them",
        "this says what you are **grading**, not what you are reading",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_c11_the_one_exception(path, tier):
    """Exactly two narrative fields are carved out, and both are named."""
    _assert_fragments(tier, path, "bounded-exception", (
        "Exactly two fields inside `## Panel Review` are **narrative**",
        "`Routed because:` on a `[DEF-NN]` entry",
        "`Defense:` on a `[SEAL-NN]` entry",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_c11_med_cap(path, tier):
    """The cap itself, both field names, and the counter-intuitive format case."""
    _assert_fragments(tier, path, "[MED]-cap", (
        "may be raised, but **never above `[MED]`.**",
        "a format violation that would make `archive_pass.py` reject the artifact",
        "buys nothing a validator does not already enforce",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_c11_flag_vs_audit_pair(path, tier):
    """The permitted/prohibited pair, and why the archive check is presence-only."""
    _assert_fragments(tier, path, "flag-vs-audit", (
        "**permitted** is that the text *misstates what was decided*",
        "**Prohibited** is that the decision was *wrong or insufficiently "
        "justified*",
        "check is deliberately **presence-only** for exactly that reason",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_c11_decidable_test(path, tier):
    """The decidable comparison test, with both worked examples."""
    _assert_fragments(tier, path, "decidable-test", (
        "the claim is permitted if and only if you can settle it by comparing "
        "the `Defense:` text against the row it defends, without forming any "
        "view on whether that decision was right",
        "resolvable by reading two cells",
        "requires re-deciding the disposition",
        "A claim that needs you to re-litigate the call is the prohibited one",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_c1_c11_precedence_in_both_blocks(path, tier):
    """The uncapped instruction-like-prose rule is stated in BOTH blocks.

    A panelist meeting either block alone must reach the same answer, so C1
    carries the pointer and C11 carries the rule with its worked example
    (C11's precedence note).
    """
    step1 = _step_1(_read(path))
    # C1's half: the pointer into C11's last bullet.
    assert (
        "including inside the two narrative fields the review-scope block "
        "below caps — see its last bullet"
    ) in step1, f"{tier} copy: C1's block does not point at C11's carve-out."
    # C11's half: the rule, its reason, and the boundary that stops it
    # swallowing the sealed-item suppression rule.
    for fragment in (
        "**instruction-like prose aimed at whoever reads it next**",
        "**the `[MED]` cap does not apply.**",
        "these two fields are dispatched into passes that have not happened yet",
        "Raising this is **not** a re-raise of a sealed item",
        "If removing the sentence would change what a later panelist *does* "
        "rather than what it *knows*, it is an instruction.",
    ):
        assert fragment in step1, (
            f"{tier} copy: C11's uncapped-instruction carve-out has lost:\n"
            f"  {fragment!r}"
        )


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_c11_named_recourse(path, tier):
    """Dissent has a named channel, so it need not become a HIGH."""
    _assert_fragments(tier, path, "named-recourse", (
        "unless you have new substantive evidence that did not appear in the "
        "prior disposition",
        "`## Assessment (human)` block",
        "Dissent has a channel; it is not the severity tag.",
    ))


# Seed list, NOT a derived pattern set (design `[DEF-02]`): this negative guards
# against throttle language THIS feature might author into step 1 itself, not
# against phrasings already in the tree, so AD24's derive-and-broaden discipline
# does not apply. Extend it if a new throttle phrasing is ever proposed.
_READING_THROTTLE_SEEDS = (
    "read less",
    "skim only",
    "only read",
    "do not read",
    "don't read",
    "need not read",
    "no need to read",
    "read just",
    "limit your reading",
    "rather than reading",
    "instead of reading",
)


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step1_has_no_reading_throttle(path, tier):
    """Step 1 never tells a panelist to read less (RK11).

    C11 narrows what a panelist *grades*; it must never narrow what a panelist
    *reads*. The read-from-disk-in-full discipline is load-bearing elsewhere in
    the loop, and a scope block is exactly where an erosion of it would land.
    """
    step1 = _step_1(_read(path)).lower()
    hits = [seed for seed in _READING_THROTTLE_SEEDS if seed in step1]
    assert not hits, (
        f"{tier} copy: step 1 contains reading-throttle language {hits!r}. "
        "C11 scopes grading, never reading."
    )


# --- C3: persona rubrics as domain lenses (R2) -------------------------------

SHARED_CLOSING_SENTENCE = (
    "The axis is the shared one: `[HIGH]` means the artifact is **wrong as "
    "written** and shipping it downstream produces rework, while \"could be "
    "better\" is `[MED]` -- see `references/panel-review.md` § The Loop step 1, "
    "whose severity definition is dispatched to you verbatim and governs."
)

# (file stem, rubric-block start marker, rubric-block end marker). The block
# bounds matter: the negatives below are scoped to the rubric, NOT to the file.
# `delivery-manager.md`'s `## Output Format` legitimately keeps prose
# High/Medium/Low labels and the phrase this rubric no longer uses.
RUBRIC_SITES = (
    ("devils-advocate", "## Severity Classification", "## Output Format"),
    ("security-reviewer", "## Severity Classification", "## Output Format"),
    ("critic", "3. Categorize risks by severity", "\n4. For each risk"),
    ("delivery-manager", "4. For each, judge severity", "\n5. Rank the concerns"),
)
RUBRIC_IDS = [site[0] for site in RUBRIC_SITES]

# Old production-harm axis, quoted by R2 as what the rubrics used to say. These
# frame a running system's failure modes, which a document has no referent for.
PRODUCTION_HARM_PHRASINGS = (
    "data loss",
    "Security vulnerability",
    "Privilege escalation",
    "injection vulnerability",
    "sensitive data exposure",
    "Remote code execution",
    "authentication bypass",
    "data breach",
    "effort underestimate",
    "paint the team into a corner",
    "paints the team into a corner",
)

_OPENER_SPLIT = re.compile(r"- \*\*High\*\*|`\[HIGH\]`")
_OPENER_MARKER = "what counts here is"

# Distinctness bound (Q2, user-decided at the Tasks gate): DERIVED from the real
# openers, not picked in advance — the smallest round value strictly above the
# observed maximum pair, under a committed ceiling of 0.30.
#
# Observed at authoring time (2026-07-26), pairwise Jaccard over content tokens:
#     critic          vs delivery-manager   0.1875
#     critic          vs devils-advocate    0.2000
#     critic          vs security-reviewer  0.1818
#     delivery-mgr    vs devils-advocate    0.2353   <- max
#     delivery-mgr    vs security-reviewer  0.1154
#     devils-advocate vs security-reviewer  0.1200
#
# A later drift above this bound means REWRITE THE OPENER. Never raise the
# constant — raising it is how four distinct lenses quietly converge into one,
# which is the recall diversity RK2 and R2's distinctness AC exist to protect.
# 0.30 is a ceiling, not a target.
OPENER_MAX_OVERLAP = 0.25


def _agent_text(stem: str) -> str:
    return _read(AGENTS / f"{stem}.md")


def _rubric_block(stem: str, start: str, end: str) -> str:
    s = _agent_text(stem)
    i = s.index(start)
    j = s.index(end, i)
    return s[i:j]


def _opener(stem: str, start: str, end: str) -> str:
    """The persona-specific scenario, from the lens marker to the first tier."""
    block = _rubric_block(stem, start, end)
    return _OPENER_SPLIT.split(block[block.index(_OPENER_MARKER):])[0]


def _content_tokens(text: str) -> set:
    """Lowercase, split on non-alphanumerics, drop tokens of <=3 chars and every
    token of the shared closing sentence (which by construction all four share).
    """
    shared = {
        t for t in re.split(r"[^a-z0-9]+", SHARED_CLOSING_SENTENCE.lower())
        if len(t) > 3
    }
    return {
        t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 3
    } - shared


@pytest.mark.parametrize("stem,start,end", RUBRIC_SITES, ids=RUBRIC_IDS)
def test_shared_closing_sentence_in_every_rubric(stem, start, end):
    """Every reconciled rubric closes with the one shared sentence (AD6).

    Pinned on what the sentence SAYS, not merely that the four agree: four
    identical-but-wrong sentences would satisfy an equality check.
    """
    block = _rubric_block(stem, start, end)
    assert SHARED_CLOSING_SENTENCE in block, (
        f"{stem}.md: the rubric does not close with the shared sentence."
    )
    for fragment in (
        "**wrong as written**",
        "shipping it downstream produces rework",
        "\"could be better\" is `[MED]`",
        "`references/panel-review.md` § The Loop step 1",
    ):
        assert fragment in block, (
            f"{stem}.md: the shared closing sentence has lost {fragment!r}."
        )


def test_persona_openers_pairwise_distinct():
    """The four opening scenarios stay four lenses, not one (AD6 / RK2)."""
    openers = {stem: _opener(stem, start, end) for stem, start, end in RUBRIC_SITES}
    tokens = {stem: _content_tokens(text) for stem, text in openers.items()}

    for a, b in itertools.combinations(sorted(tokens), 2):
        overlap = len(tokens[a] & tokens[b]) / len(tokens[a] | tokens[b])
        assert overlap < OPENER_MAX_OVERLAP, (
            f"Openers for {a} and {b} overlap at Jaccard={overlap:.4f}, at or "
            f"above OPENER_MAX_OVERLAP={OPENER_MAX_OVERLAP}. The remedy is to "
            f"REWRITE ONE OPENER so the lenses stay distinct — never to raise "
            f"the constant. Shared tokens: {sorted(tokens[a] & tokens[b])}"
        )

    # Floor: the ratio alone can be satisfied by two very short openers, so each
    # must also carry its own vocabulary.
    for stem, own in tokens.items():
        others = set().union(*[t for s, t in tokens.items() if s != stem])
        unique = own - others
        assert len(unique) >= 2, (
            f"{stem}.md's opener carries only {len(unique)} token(s) present in "
            f"no other opener; it is not a distinct lens."
        )


def test_no_critical_tier_in_agents():
    """`security-reviewer`'s orphan `Critical` tier is folded into `[HIGH]` (AD7).

    File-scoped, and swept across every agent so the tier cannot reappear
    elsewhere: the severity vocabulary is exactly `[HIGH]`/`[MED]`/`[LOW]`.
    """
    offenders = [
        p.name for p in sorted(AGENTS.glob("*.md"))
        if "**Critical**" in _read(p)
    ]
    assert not offenders, (
        f"A `Critical` severity tier survives in {offenders}; the bracketed "
        "vocabulary has exactly three tiers."
    )


@pytest.mark.parametrize("stem,start,end", RUBRIC_SITES, ids=RUBRIC_IDS)
def test_production_harm_phrasings_absent_from_rubric(stem, start, end):
    """The old running-system axis is gone from the RUBRIC — not from the file.

    Deliberately block-scoped: `delivery-manager.md` keeps "paints the team into
    a corner" in its `## Output Format` prose labels, which are for standalone,
    non-panel use and are out of scope for this feature.
    """
    block = _rubric_block(stem, start, end)
    hits = [p for p in PRODUCTION_HARM_PHRASINGS if p.lower() in block.lower()]
    assert not hits, (
        f"{stem}.md's rubric still grades on the production-harm axis {hits!r}. "
        "The panel reviews documents, which have no runtime."
    )


def test_no_rubric_added_to_rubricless_personas():
    """The personas with no rubric today gain none (C3 / AD20).

    Derived, not enumerated: any agent outside the four rubric-bearing files
    must carry neither a `## Severity Classification` heading nor the shared
    closing sentence.
    """
    reconciled = {stem for stem, _s, _e in RUBRIC_SITES}
    offenders = []
    for path in sorted(AGENTS.glob("*.md")):
        if path.stem in reconciled:
            continue
        text = _read(path)
        if "## Severity Classification" in text or SHARED_CLOSING_SENTENCE in text:
            offenders.append(path.name)
    assert not offenders, (
        f"{offenders} gained rubric content; C3 reconciles exactly the four "
        "files that already had one and touches no others."
    )


def test_no_med_cap_clause_in_any_persona_file():
    """The `[MED]` cap is stated ONCE, in `panel-review.md` step 1 (AD20).

    Restating it in a persona body is how a ceiling turns into a licence to
    raise, and how the two copies drift.
    """
    offenders = [
        p.name for p in sorted(AGENTS.glob("*.md"))
        if "never above `[MED]`" in _read(p)
    ]
    assert not offenders, (
        f"{offenders} restate the `[MED]` cap; it belongs only to C11's nested "
        "tier in both `panel-review.md` copies."
    )


# --- C4: the CFC cost-claim correction (R3) ----------------------------------
#
# Spec-driven-dev only. The `## Panel rubric on Per-feature AC alignment`
# paragraph is a recorded intentional asymmetry (the CFC consumer check); no
# blueprint counterpart exists and none is invented.

CFC_RUBRIC_MARKER = "**Panel rubric on Per-feature AC alignment.**"


def _cfc_rubric_paragraph() -> str:
    content = _read(SDD_PANEL)
    start = content.index(CFC_RUBRIC_MARKER)
    return content[start:content.index("\n\n", start)]


def test_c4_cost_clause_states_real_cost():
    """The false positive is priced at the exit boundary, not as one table row.

    The old text said a false-positive concern "is one Disposition row" full
    stop. That is true on an ordinary pass and false on the terminal one, where
    an unresolved HIGH buys a whole extra three-panelist pass — the cost this
    feature exists to stop paying.
    """
    para = _cfc_rubric_paragraph()
    for fragment in (
        "one Disposition row on an ordinary pass",
        "on what would otherwise be the terminal pass an unresolved HIGH costs "
        "a full additional three-panelist pass",
    ):
        assert fragment in para, (
            f"The CFC cost clause has lost its corrected cost:\n  {fragment!r}"
        )


def test_c4_keeps_raise_if_unsure_default():
    """Correcting the cost must not invert the guidance (the other direction).

    Pinned separately from the cost fact: a rewrite that priced the false
    positive honestly but quietly turned "raise it" into "think twice" would
    pass a cost-only assertion while reversing the rubric's intent.
    """
    para = _cfc_rubric_paragraph()
    for fragment in (
        "If unsure whether a change is substantive, raise it",
        "a false negative is a silently weakened contract, and that is the "
        "expensive error",
        "Raise it, and dispose it honestly.",
    ):
        assert fragment in para, (
            f"The CFC rubric has lost its raise-if-unsure default:\n  {fragment!r}"
        )


def test_c4_paragraph_absent_from_blueprint():
    """The asymmetry is recorded and preserved: no counterpart is invented."""
    assert CFC_RUBRIC_MARKER not in _read(BP_PANEL), (
        "The project-blueprint copy gained a `Panel rubric on Per-feature AC "
        "alignment` paragraph. The CFC consumer check is spec-driven-dev only "
        "— a recorded intentional asymmetry, not an omission to fix."
    )


# --- Structural skimmability for the step-1 clauses (R1) ---------------------

# Each committed clause that must begin its own list item under step 1. Inlining
# any of these into a neighbouring paragraph is the failure R1's skimmability
# criterion names, and it is invisible to a containment assertion.
STEP1_LIST_CLAUSES = (
    "`[HIGH]` — the artifact is **wrong as written**",
    "`[MED]` — the artifact is correct as written",
    "`[LOW]` — cosmetic or editorial",
    "**What is under review.**",
    "**Why.**",
    "**The one exception.**",
    "**If you are convinced a seal was wrong anyway.**",
    "A genuine problem in one of those two fields",
    "On a `Defense:`, the line between flagging and auditing",
    "The test, so the two do not blur",
    "**What the cap does not cover.**",
)


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step1_clauses_are_separately_listed(path, tier):
    """Every committed C1/C11 clause begins its own list item.

    This is the STRUCTURAL half of R1's skimmability criterion only. The
    judgment half — whether the rendered step still reads as a four-line skim
    path rather than run-on prose — cannot be asserted and is review-gated at
    T28, per the design's § Verification categories.
    """
    step1 = _step_1(_read(path))
    for clause in STEP1_LIST_CLAUSES:
        line = next(
            (ln for ln in step1.splitlines() if clause in ln),
            None,
        )
        assert line is not None, (
            f"{tier} copy: clause not found in step 1:\n  {clause!r}"
        )
        assert line.lstrip().startswith("- "), (
            f"{tier} copy: the clause {clause!r} does not begin its own list "
            f"item — it is embedded mid-paragraph, which is the run-on failure "
            f"R1's skimmability criterion names. Line was:\n  {line[:120]!r}"
        )


# --- R7: the both-polarity sweep, derived not transcribed (AD24) -------------
#
# DERIVATION (AD24), run at authoring time 2026-07-26. The pattern sets below
# are the SURVIVORS of a grep -> classify -> broaden -> re-run loop, not a
# transcription of R7's seed lists. Per-round tallies, kept as an audit trail —
# no count here is a criterion, and none is asserted anywhere (`[DEF-17]`):
#
#   round 1  seeds from R7 (zero/0 HIGHs)                    26 hits
#   round 2  + word-order reversal, bare-HIGHs, count forms  +23   <- seeds alone
#   round 3  + convergence synonyms, hyphenated compounds    +16      missed ~half
#   round 4  + quantifier/plural variants, lifted phrasings  +19
#   round 5  + negation/absence forms                        +14, 0 exit-rule
#   round 6  + stamp/trajectory vocabulary                    +6, 0 exit-rule
#   round 7  + pass-ordinal/cap vocabulary                   +24, 0 exit-rule  QUIET
#   round 8  + imperative exit directives                     +4, 0 exit-rule  QUIET
#
# Rounds 7 and 8 were genuine broadenings by `[DEF-20]` (each used an unused
# axis AND matched real lines) and each returned no unclassified exit-rule
# statement — the two consecutive quiet rounds AD24 requires. The restate set
# had been stable since round 4. The persisted patterns below are narrowed to
# the exit-rule vocabulary the loop actually found; the broad discovery patterns
# were scaffolding and are deliberately not shipped.

SWEEP_ROOTS = (
    "telescoping-sdd/skills/*/SKILL.md",
    "telescoping-sdd/skills/*/references/*.md",
)

EXIT_PATTERNS = (
    r"zero HIGHs?\b",
    r"\b0 HIGHs?\b",
    r"zero HIGH-severity concerns",
    r"no new HIGH(?:-severity)? concerns",
    r"returns? no HIGH",
    r"no HIGH-severity concerns",
    r"HIGH-count",
)
CONTINUE_PATTERNS = (
    r"HIGHs? remain",
    r"HIGH concerns? remain",
    r"while any HIGH concern remains",
    r"returns? HIGH concerns",
    r"strict-bar pass returns HIGHs",
    r"remaining HIGHs?\b",
)

# A line already restated in unresolved-HIGH terms carries one of these.
RESTATEMENT_QUALIFIERS = (
    "unresolved",
    "other than those dismissed",
    "Defense:",
)

# AD10 entry shape: (relpath, phrase, context, reason). Never line numbers —
# they churn on every unrelated edit above them. Each entry must match EXACTLY
# one line: the lower bound stops the list rotting into a permanent waiver, the
# upper bound stops one entry silently excusing a second, genuinely-stale hit.
SWEEP_ALLOW = (
    (
        "spec-driven-dev/references/hash-and-cascade.md",
        "0 HIGHs",
        "lean-no",
        "AD15: a CONDITION gating an emitted `no issues found` message, not a "
        "statement of the exit rule. Broadening it would make that message "
        "false on a sealed convergence, and the string is verbatim-pinned by "
        "test_hash_and_cascade_parity.py. Recorded out-of-scope exception.",
    ),
    (
        "project-blueprint/references/hash-and-cascade.md",
        "0 HIGHs",
        "lean-no",
        "AD15: blueprint mirror of the same condition-gated message.",
    ),
    (
        "spec-driven-dev/references/panel-review-modes.md",
        "remaining HIGHs",
        "Exit to validation regardless",
        "AD23: `## Lightweight Mode` is the mode in which the convergence loop "
        "is switched OFF, so the exit predicate has no referent here — the "
        "phrase describes a disabled mechanism rather than stating the rule. "
        "Recorded out-of-scope exception; user-settled ([SEAL-12]).",
    ),
    (
        "project-blueprint/references/panel-review-modes.md",
        "remaining HIGHs",
        "Exit to validation regardless",
        "AD23: blueprint mirror of the lightweight-mode exception.",
    ),
    (
        "spec-driven-dev/references/panel-review-convergence.md",
        "remaining HIGHs",
        "5-pass cap gate",
        "Cap-gate accounting, not the exit predicate: this row describes the "
        "user CHOOSING to stop with HIGHs outstanding, which is a different "
        "exit from convergence and is unaffected by R4.",
    ),
    (
        "project-blueprint/references/panel-review-convergence.md",
        "remaining HIGHs",
        "5-pass cap gate",
        "Cap-gate accounting; blueprint mirror.",
    ),
    (
        "spec-driven-dev/references/panel-review-convergence.md",
        "HIGH-count",
        "not meaningfully dropping",
        "The STRICT-BAR TRIGGER, which R6 requires unchanged. Its question is "
        "'is the panel still finding things', a RAISED-count question, not an "
        "exit question. Deliberately not restated.",
    ),
    (
        "project-blueprint/references/panel-review-convergence.md",
        "HIGH-count",
        "not meaningfully dropping",
        "Strict-bar trigger; blueprint mirror.",
    ),
    (
        "spec-driven-dev/references/panel-review.md",
        "zero HIGH",
        "still returns the path",
        "The PANELIST MANIFEST contract — what an individual panelist reports "
        "for its own pass, not the loop's exit test. Unaffected by R4.",
    ),
    (
        "project-blueprint/references/panel-review.md",
        "zero HIGH",
        "still returns the path",
        "Panelist manifest contract; blueprint mirror.",
    ),
    (
        "spec-driven-dev/references/panel-review.md",
        "0 new HIGH",
        "still reconcile",
        "A reconciliation instruction (do not short-circuit the anchor check on "
        "a quiet pass), not the exit test.",
    ),
    (
        "project-blueprint/references/panel-review.md",
        "0 new HIGH",
        "still reconcile",
        "Reconciliation instruction; blueprint mirror.",
    ),
    (
        "spec-driven-dev/references/panel-review-convergence.md",
        "HIGH-count",
        "Panel skip",
        "Describes what a SKIPPED pass contributes to the TRIGGER's read, not "
        "the exit rule. Same trigger exemption as the entry above.",
    ),
    (
        "project-blueprint/references/panel-review-convergence.md",
        "HIGH-count",
        "Panel skip",
        "Panel-skip trigger read; blueprint mirror.",
    ),
    (
        "spec-driven-dev/references/troubleshooting.md",
        "remaining HIGH concerns",
        "accept remaining HIGH concerns as known risks",
        "One of the three options offered AT THE CAP GATE, not a statement of "
        "the convergence exit rule.",
    ),
    (
        "project-blueprint/references/troubleshooting.md",
        "remaining HIGH concerns",
        "accept remaining HIGH concerns as known risks",
        "Cap-gate option; blueprint mirror.",
    ),
)


# The BANNED paraphrase and its variants (R7 prohibits the paraphrase "and its
# variants" in as many words, so a fixed three-string hand list under-delivers).
# Derived on the same broaden-and-re-run loop: the failure mode is any wording
# that makes the non-blocking set turn on WHETHER A CHANGE WAS MADE, which is
# false for `Deferred` — it makes no edit and still blocks.
PROHIBITED_PARAPHRASES = (
    r"HIGHs? that required (?:a )?change",
    r"HIGHs? requiring (?:a )?change",
    r"HIGHs? that needed (?:a )?change",
    r"HIGHs? that (?:were )?(?:fixed|edited|changed)",
    r"HIGHs? resulting in (?:an )?edit",
    r"unfixed HIGHs?",
    r"HIGHs? left unfixed",
)

# Every site the derivation classified `restate`, as (relpath, site label).
#
# Labels, not locators: several of these sites are SUBSTANTIALLY rewritten by
# the restatement (`:104` becomes a three-way branch), so any pre-edit phrase
# used to find the line stops resolving the moment the edit lands. T20 pairs
# each label with the substring the restated site must carry and asserts it as
# a POSITIVE pin against the file — which needs no locator at all.
#
# Every file here is named in the design's `## File Structure`, so the sweep
# triggered no Ask-First confirmation.
RESTATEMENT_SITES = tuple(
    (f"{tier}/{rel}", label)
    for tier in ("spec-driven-dev", "project-blueprint")
    for rel, label in (
        ("SKILL.md", "skill-body exit clause"),
        ("references/examples.md", "walkthrough exit clause"),
        ("references/panel-review-convergence.md", "halt exit-identity clause"),
        ("references/panel-review-convergence.md", "strict-bar dispose directive"),
        ("references/panel-review-convergence.md", "cross-check lead-in"),
        ("references/panel-review-convergence.md", "cross-check converged branch"),
        ("references/panel-review-convergence.md", "exit-paths NORMAL exit row"),
        ("references/panel-review-convergence.md", "exit-paths NORMAL continue row"),
        ("references/panel-review-convergence.md", "exit-paths STRICT-BAR exit row"),
        ("references/panel-review-convergence.md", "exit-paths STRICT-BAR continue row"),
        ("references/panel-review.md", "digest step 5"),
        ("references/panel-review.md", "step 8 exit test"),
        ("references/panel-review.md", "autonomy continue row"),
        ("references/panel-review.md", "autonomy cross-check row"),
        ("references/panel-review.md", "autonomy rule (a)"),
        ("references/strict-bar-prompts.md", "cross-check cross-reference"),
        ("references/troubleshooting.md", "5-pass-cap heading"),
        ("references/troubleshooting.md", "5-pass-cap cause line"),
    )
)


def _sweep_lines():
    """Yield (relpath, lineno, line) for every line under SWEEP_ROOTS.

    SCOPE (AD11). `telescoping-sdd/skills/*/scripts/**` is excluded: its
    `0 HIGH` hits are literal `### Trajectory` fixture rows carrying the
    `converged (0 HIGH)` stamp — a fixture asserting the old stamp is SUPPOSED
    to contain it. Excluding by directory is stable; allow-listing individual
    fixture lines is not.

    DECLARED LIMITATION (AD11): because that tree sits outside SWEEP_ROOTS,
    this derivation can never verify the exclusion — it is ASSERTED, NOT SWEPT.
    Spot-checked once at implementation time (T9, 2026-07-26): all 5
    both-polarity hits under the excluded tree were confirmed to be literal
    `### Trajectory` fixture rows carrying `converged (0 HIGH)`, in
    test_cfc_cli_integration.py and test_phase_tasks_characterization.py.
    Not re-verified per run.
    """
    base = _REPO / "telescoping-sdd" / "skills"
    for path in sorted(base.glob("*/SKILL.md")) + sorted(base.glob("*/references/*.md")):
        rel = str(path.relative_to(base))
        for num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            yield rel, num, line


def _sweep_hits():
    pattern = re.compile("|".join(EXIT_PATTERNS + CONTINUE_PATTERNS), re.I)
    return [(rel, num, line) for rel, num, line in _sweep_lines() if pattern.search(line)]


def _entry_matches(entry, rel, line):
    _relpath, phrase, context, _reason = entry
    return rel == _relpath and phrase.lower() in line.lower() and context in line


def test_sweep_allowlist_entry_matches_exactly_one_hit():
    """Upper bound: one entry must not silently excuse a second, stale hit."""
    hits = _sweep_hits()
    for entry in SWEEP_ALLOW:
        matched = [(rel, num) for rel, num, line in hits if _entry_matches(entry, rel, line)]
        assert len(matched) == 1, (
            f"SWEEP_ALLOW entry {entry[0]} / {entry[1]!r} / {entry[2]!r} matched "
            f"{len(matched)} hits, expected exactly 1: {matched}. An entry that "
            f"matches more than one line excuses an occurrence nobody classified."
        )


def test_sweep_allowlist_has_no_unused_entry():
    """Lower bound: an entry whose hit was reworded away must not linger."""
    hits = _sweep_hits()
    unused = [
        (entry[0], entry[1], entry[2])
        for entry in SWEEP_ALLOW
        if not any(_entry_matches(entry, rel, line) for rel, _num, line in hits)
    ]
    assert not unused, (
        f"SWEEP_ALLOW entries match nothing and have rotted into permanent "
        f"waivers: {unused}"
    )


def test_sweep_allowlist_is_order_independent():
    """The classification must not depend on entry order (`[DEF-15]`).

    Asserted rather than reasoned about: the exactly-one-occurrence bound is
    what makes order irrelevant, and this is what proves it stayed that way.
    """
    hits = _sweep_hits()

    def classify(entries):
        out = {}
        for rel, num, line in hits:
            out[(rel, num)] = next(
                (i for i, e in enumerate(entries) if _entry_matches(e, rel, line)),
                None,
            )
        return {k: (v is not None) for k, v in out.items()}

    forward = classify(SWEEP_ALLOW)
    reverse = classify(tuple(reversed(SWEEP_ALLOW)))
    assert forward == reverse, (
        "Allow-list classification differs under reversed entry order; some "
        "entry must be matching a line another entry also matches."
    )


# --- C2: the step-8 exit rule, one named test per clause (R4, R7) ------------
#
# Coverage is derived from C2's clause list, not from a subset restated here:
# every clause in that list has its own named test in both copies. No clause is
# covered only as part of a disjunction, and none only by the committed-
# formulation substring — a trim of any one must fail on its own test.
#
# No assertion in this module counts clauses (AD2).

COMMITTED_FORMULATION = (
    "no HIGH concerns other than those dismissed with a recorded `Defense:`"
)


def _step_8(content: str) -> str:
    start = content.index("8. **Exit when the pass leaves")
    end = content.index("   **Handling re-raised deferred concerns.**", start)
    return content[start:end]


def _assert_step8(tier: str, path: Path, clause: str, fragments) -> None:
    step8 = _step_8(_read(path))
    for fragment in fragments:
        assert fragment in step8, (
            f"{tier} copy: step 8 has lost its {clause} clause:\n  {fragment!r}"
        )


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step8_exit_test(path, tier):
    """The committed formulation itself."""
    _assert_step8(tier, path, "exit-test", (COMMITTED_FORMULATION,))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step8_unresolved_gloss(path, tier):
    """`unresolved` != `unfixed`. Named separately: a later trim reads it as
    redundant with the exit test, and it is the single most misreadable word
    in the rule."""
    _assert_step8(tier, path, "unresolved-gloss", (
        '**`unresolved` here means "carrying no `Defense:`-backed disposition", '
        'not "unfixed".**',
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step8_terminology_note(path, tier):
    """R7's carve-out for `panel-review-modes.md`'s ordinary-English usage.

    Also named separately, and for the same reason as the gloss above.
    """
    _assert_step8(tier, path, "terminology-note", (
        "uses the words *\"unresolved HIGH concerns\"* in their ordinary-English "
        "sense",
        "is **not** to be \"reconciled\" with it",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step8_disposition_sets(path, tier):
    """Both sets, named explicitly, so neither can be inferred wrongly."""
    _assert_step8(tier, path, "disposition-sets", (
        "**Non-blocking:** `Sealed`, `Accepted as risk`.",
        "**Blocking:** `Addressed`, `Deferred → <target>`, `Halt and re-scope`, "
        "`User input needed`.",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step8_addressed_rationale(path, tier):
    """`Addressed` blocks because an EDIT was made — not because change was
    required. The banned paraphrase inverts exactly this."""
    _assert_step8(tier, path, "Addressed-rationale", (
        "**an edit was made and nobody has reviewed it**",
        "*not* because a change was required",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step8_deferred_rationale(path, tier):
    """`Deferred` blocks because it feeds a SECOND predicate."""
    _assert_step8(tier, path, "Deferred-rationale", (
        "It feeds the strict-bar deferral-rate trigger",
        "would silently move a second predicate",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step8_seal_suppression_crossref(path, tier):
    """The confirming pass could not audit the seal anyway."""
    _assert_step8(tier, path, "seal-suppression", (
        "Step 1 instructs the next pass not to re-raise a sealed item without "
        "new substantive evidence",
        "could not audit the seal anyway",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step8_forfeited_reread(path, tier):
    """What the skip actually costs — stated so it is accepted knowingly."""
    _assert_step8(tier, path, "forfeited-re-read", (
        "One additional independent read of the whole artifact by three fresh "
        "panelists",
        "not merely the seal re-examination",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step8_defense_is_presence_only(path, tier):
    """Stated as the check actually behaves, including that it grades nothing."""
    _assert_step8(tier, path, "presence-only-Defense", (
        "requires the literal token `Defense:` to appear in the row's Notes and "
        "grades **nothing** after it",
        "not even that any text follows the colon",
        "Accountability comes from the defense being permanent, on-disk and "
        "panelist-visible",
    ))


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step8_both_stamp_literals(path, tier):
    """Both literals, and why the HIGHs column may disagree with them."""
    _assert_step8(tier, path, "stamp-literals", (
        "`converged (0 HIGH)`",
        "`converged (0 unresolved HIGH); sealed=<N>`",
        "keeps recording HIGHs *raised*",
    ))


STEP8_LIST_CLAUSES = (
    "**The exit test.**",
    "**Terminology note.**",
    "**Disposition sets.**",
    "**Why `Addressed` blocks.**",
    "**Why `Deferred` blocks.**",
    "**Seal suppression is already in force.**",
    "**What the skip forfeits.**",
    "**`Defense:` is checked for presence only.**",
    "**The two stamp literals.**",
)


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_step8_clauses_are_separately_listed(path, tier):
    """Structural half of skimmability for step 8 (the judgment half is
    review-gated at T28, per § Verification categories)."""
    step8 = _step_8(_read(path))
    for clause in STEP8_LIST_CLAUSES:
        line = next((ln for ln in step8.splitlines() if clause in ln), None)
        assert line is not None, f"{tier} copy: step 8 clause missing: {clause!r}"
        assert line.lstrip().startswith("- "), (
            f"{tier} copy: {clause!r} does not begin its own list item."
        )


def test_no_site_states_predicate_as_change_required():
    """The banned paraphrase, over the derived pattern set.

    R7 prohibits the paraphrase "and its variants" in as many words, so this
    runs `PROHIBITED_PARAPHRASES` — produced by AD24's broaden-and-re-run loop
    — rather than a fixed hand list. Round-1 strings were labelled seeds.

    Why it is banned: "HIGHs that required change" is FALSE for `Deferred`,
    which makes no edit and still blocks. The predicate turns on whether a
    `Defense:` was recorded, never on whether a change was made.
    """
    offenders = []
    pattern = re.compile("|".join(PROHIBITED_PARAPHRASES), re.I)
    for rel, num, line in _sweep_lines():
        m = pattern.search(line)
        if m:
            offenders.append(f"{rel}:{num}: {m.group(0)!r}")
    assert not offenders, (
        "Prohibited paraphrase of the exit predicate found — it states the rule "
        "in terms of whether a CHANGE was made, which is false for `Deferred`:\n"
        + "\n".join(offenders)
    )


# --- R7: per-site positive pins + the standing sweep -------------------------
#
# C6's promotion rule: EVERY site the discovery step classified `restate` gets
# its own positive per-site assertion. This is a hard rule, not a default —
# the two verification strengths are not interchangeable. The per-site case is
# a POSITIVE pin (this file must contain this substring); the sweep's same-line
# qualifier heuristic only checks that a hit LOOKS restated, so a site left to
# the heuristic alone can be reworded past the patterns and fail nothing (RK9).

# label -> the substring the restated site must carry.
REQUIRED_SUBSTRING = {
    "skill-body exit clause":
        "no HIGH-severity concerns other than those dismissed with a recorded "
        "`Defense:`",
    "walkthrough exit clause":
        "exit on zero unresolved HIGHs",
    "halt exit-identity clause":
        "distinct from the unresolved-HIGH exit",
    "strict-bar dispose directive":
        "**Every HIGH this pass is disposed `Sealed` or `Accepted as risk`**",
    "cross-check lead-in":
        "When a STRICT-BAR pass returns **zero unresolved HIGHs**",
    "cross-check converged branch":
        "- **Cross-check returns 0 unresolved HIGHs** → exit the loop.",
    "exit-paths NORMAL exit row":
        "| NORMAL | 0 unresolved HIGHs |",
    "exit-paths NORMAL continue row":
        "| NORMAL | unresolved HIGHs remain |",
    "exit-paths STRICT-BAR exit row":
        "| STRICT-BAR | 0 unresolved HIGHs |",
    "exit-paths STRICT-BAR continue row":
        "| STRICT-BAR | unresolved HIGHs remain |",
    "digest step 5":
        "Exit when a pass returns no HIGH concerns other than those disposed "
        "`Sealed` / `Accepted as risk`",
    "step 8 exit test":
        COMMITTED_FORMULATION,
    "autonomy continue row":
        "| Running the next pass while any unresolved HIGH concern remains |",
    "autonomy cross-check row":
        "when a STRICT-BAR pass returns 0 unresolved HIGH",
    "autonomy rule (a)":
        "When a pass returns unresolved HIGH concerns, the next pass is required",
    "cross-check cross-reference":
        "once a strict-bar pass returns zero unresolved HIGHs",
    "5-pass-cap heading":
        "## Panel review hits the 5-pass cap with unresolved HIGH concerns remaining",
    "5-pass-cap cause line":
        "the loop exits on zero *unresolved* HIGHs",
}


@pytest.mark.parametrize(
    "relpath,label", RESTATEMENT_SITES,
    ids=[f"{r.split('/')[0][:2]}:{lbl}" for r, lbl in RESTATEMENT_SITES],
)
def test_restatement_site_carries_committed_formulation(relpath, label):
    """Every discovered `restate` site states the predicate in unresolved terms."""
    required = REQUIRED_SUBSTRING[label]
    text = _read(_REPO / "telescoping-sdd" / "skills" / relpath)
    assert required in text, (
        f"{relpath} ({label}) does not carry its restated form:\n  {required!r}"
    )


def test_both_polarity_sweep_leaves_no_unclassified_hit():
    """The standing net (AD24).

    Every both-polarity hit under SWEEP_ROOTS must either carry a restatement
    qualifier on the same line or match exactly one SWEEP_ALLOW entry. This is
    what catches a site nobody enumerated — including one added by a future
    edit — and it is the check that four hand-built enumerations failed.
    """
    unclassified = []
    for rel, num, line in _sweep_hits():
        if any(q in line for q in RESTATEMENT_QUALIFIERS):
            continue
        if any(_entry_matches(e, rel, line) for e in SWEEP_ALLOW):
            continue
        unclassified.append(f"{rel}:{num}: {line.strip()[:110]}")
    assert not unclassified, (
        "Exit-rule hits that are neither restated nor allow-listed. Either "
        "restate them, or add a SWEEP_ALLOW entry carrying the reason:\n"
        + "\n".join(unclassified)
    )


# --- C7 / C8: the disclosure and the troubleshooting entry (R5) --------------

CUMULATIVE_CAVEAT = "cumulative across passes and severities"


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_autonomy_rule_e_present(path, tier):
    """Rule (e) exists and the lead-in was re-counted with it."""
    content = _read(path)
    assert "Five load-bearing rules:" in content, (
        f"{tier} copy: the `## Autonomy Boundary` lead-in still says four rules."
    )
    assert "- **(e) Sealed-exit disclosure.**" in content, (
        f"{tier} copy: rule (e) is missing."
    )


@pytest.mark.parametrize("path,tier", BOTH_PANELS)
def test_rule_e_disclosure_fragments(path, tier):
    """Pinned on the load-bearing FRAGMENTS, not merely on rule (e) existing.

    A rule (e) trimmed to its heading would satisfy a presence check while
    telling the synthesizer nothing.
    """
    content = _read(path)
    for fragment in (
        "the last `### Trajectory` row's Notes carry `sealed=<N>`",
        "after the validation output, immediately before the approval question",
        "**sealed rather than fixed**",
        "each carries a recorded `Defense:` in `### Sealed dispositions`",
        "A `converged` row may *also* carry halt-vote text",
    ):
        assert fragment in content, (
            f"{tier} copy: rule (e) has lost:\n  {fragment!r}"
        )


@pytest.mark.parametrize("tier", ["spec-driven-dev", "project-blueprint"])
def test_sealed_exit_troubleshooting_entry(tier):
    """C8's entry: heading, Cause fragments, Solution fragments."""
    path = _REPO / "telescoping-sdd" / "skills" / tier / "references" / "troubleshooting.md"
    content = _read(path)
    assert "## The loop exited but the last Trajectory row still shows a HIGH" in content, (
        f"{tier}: the sealed-exit troubleshooting entry is missing."
    )
    for fragment in (
        "**Cause:** A sealed exit.",
        "keeps recording HIGHs *raised*, which is why the two disagree — by design",
        "**Solution:** No action required; this is expected behaviour.",
        "**new substantive evidence**",
        "simply running another pass will not re-litigate it",
    ):
        assert fragment in content, f"{tier}: C8 entry has lost:\n  {fragment!r}"


def test_cumulative_caveat_literal_at_every_site():
    """One literal, asserted at every site that states it.

    Cross-consistency: the caveat explains why `### Sealed dispositions` may
    list more entries than the stamp's `sealed=<N>`. If one site drifts, an
    operator comparing two of them reaches contradictory conclusions.
    """
    sites = [
        _REPO / "telescoping-sdd" / "skills" / tier / "references" / name
        for tier in ("spec-driven-dev", "project-blueprint")
        for name in ("panel-review.md", "troubleshooting.md")
    ]
    missing = [str(p.relative_to(_REPO)) for p in sites
               if CUMULATIVE_CAVEAT not in _read(p)]
    assert not missing, (
        f"The literal {CUMULATIVE_CAVEAT!r} is absent from: {missing}"
    )


# =============================================================================
# Region B - Predicate (part #4, R4-R6)
# =============================================================================
#
# AD9 region boundary: everything Region B needs is defined BELOW this banner.
# Region A above references nothing from here.

import subprocess  # noqa: E402
import sys as _sys  # noqa: E402

_SCRIPTS = _REPO / "telescoping-sdd" / "scripts"
_ARCHIVE_PASS = _SCRIPTS / "archive_pass.py"

if str(_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS))

import archive_pass  # noqa: E402


def _row(severity, disposition, notes="", concern="c", source="architect"):
    """A parsed `### Latest pass detail` row, in the shape the call site sees."""
    return {
        "Severity": severity,
        "Source": source,
        "Concern": concern,
        "Disposition": disposition,
        "Notes": notes,
    }


def _counts(rows):
    """Call the helper and assert its postcondition on every case.

    `raised == sealed_high + unresolved` is an invariant of the contract, so it
    is checked here once rather than restated in each test below.
    """
    raised, sealed_high, unresolved = archive_pass.high_disposition_counts(rows)
    assert raised == sealed_high + unresolved, (
        f"postcondition violated: raised={raised} != sealed_high={sealed_high} "
        f"+ unresolved={unresolved}"
    )
    assert min(raised, sealed_high, unresolved) >= 0
    return raised, sealed_high, unresolved


# --- the unit table ----------------------------------------------------------

def test_all_sealed_highs_are_resolved():
    rows = [_row("[HIGH]", "Sealed", "Defense: user-directed"),
            _row("[HIGH]", "Sealed", "Defense: settled at design")]
    assert _counts(rows) == (2, 2, 0)


def test_sealed_and_accepted_as_risk_mixed():
    """Both defended dispositions in ONE HIGH set — the mixed case."""
    rows = [_row("[HIGH]", "Sealed", "Defense: a"),
            _row("[HIGH]", "Accepted as risk", "Defense: b")]
    assert _counts(rows) == (2, 2, 0)


def test_addressed_high_is_unresolved():
    """An edit was made and nobody reviewed it — still blocks."""
    assert _counts([_row("[HIGH]", "Addressed")]) == (1, 0, 1)


def test_deferred_high_is_unresolved():
    """Deliberately NOT in the non-blocking set: it feeds the strict-bar
    deferral-rate trigger, so moving it would move a second predicate."""
    assert _counts([_row("[HIGH]", "Deferred → tasks.md")]) == (1, 0, 1)


def test_halt_high_is_unresolved():
    assert _counts([_row("[HIGH]", "Halt and re-scope")]) == (1, 0, 1)


def test_user_input_needed_high_is_unresolved():
    assert _counts([_row("[HIGH]", "User input needed")]) == (1, 0, 1)


def test_sealed_med_low_do_not_move_the_predicate():
    """Sealing a non-HIGH can never move the exit test (R4 AC).

    The boundary case: one HIGH `Addressed` plus sealed MED/LOW must still
    leave the pass unconverged.
    """
    rows = [_row("[HIGH]", "Addressed"),
            _row("[MED]", "Sealed", "Defense: m"),
            _row("[LOW]", "Accepted as risk", "Defense: l")]
    assert _counts(rows) == (1, 0, 1)


def test_no_high_rows_is_all_zero():
    rows = [_row("[MED]", "Addressed"), _row("[LOW]", "Addressed")]
    assert _counts(rows) == (0, 0, 0)


def test_regression_tagged_high_classified_on_high_substring():
    """`[HIGH] [REGRESSION]` is still a HIGH — classification is by substring,
    exactly as the HIGHs column already counts it."""
    assert _counts([_row("[HIGH] [REGRESSION]", "Sealed", "Defense: r")]) == (1, 1, 0)


def test_every_disposition_in_the_vocabulary_has_a_case():
    """Coverage derived from `DISPOSITION_LABELS`, not from a list restated here.

    A disposition added to the vocabulary later fails this until it is
    classified — which is the point.
    """
    defended = set(archive_pass.DEFENDED_DISPOSITIONS)
    for disposition in sorted(archive_pass.DISPOSITION_LABELS):
        notes = "Defense: x" if disposition in defended else ""
        raised, sealed_high, unresolved = _counts(
            [_row("[HIGH]", disposition, notes)]
        )
        assert raised == 1
        if disposition in defended:
            assert (sealed_high, unresolved) == (1, 0), (
                f"{disposition!r} is a defended disposition and must resolve"
            )
        else:
            assert (sealed_high, unresolved) == (0, 1), (
                f"{disposition!r} carries no `Defense:` guarantee and must block"
            )


# --- end-to-end stamp behaviour (subprocess level) ---------------------------
#
# Every stamp-behaviour criterion in R4 and R5 gets a subprocess-level case:
# the unit table above cannot catch a call-site error or a stamp-assembly
# error, which is where a two-part tag can go wrong.

def _run_archive(args):
    return subprocess.run(
        [_sys.executable, str(_ARCHIVE_PASS), *args],
        capture_output=True, text=True,
    )


def _artifact(tmp_path, latest_rows, name="spec.md"):
    artifact = tmp_path / name
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "\n"
        "### Sealed dispositions\n\n"
        "_None yet._\n\n"
        "### Deferred dispositions\n\n"
        "<!-- Auto-populated by archive_pass.py when a Deferred-disposed row is promoted; remains empty until first deferral. -->\n\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        f"{latest_rows}"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    return artifact


def _notes_cell(artifact):
    """The Notes cell of the single archived `### Trajectory` row."""
    for line in artifact.read_text(encoding="utf-8").splitlines():
        if line.startswith("| 1 ") or line.startswith("| 1\t"):
            return [c.strip() for c in line.strip("|").split("|")][-1]
    raise AssertionError("no archived trajectory row found")


def _trajectory_cells(artifact):
    for line in artifact.read_text(encoding="utf-8").splitlines():
        if line.startswith("| 1 "):
            return [c.strip() for c in line.strip("|").split("|")]
    raise AssertionError("no archived trajectory row found")


SEALED_HIGH = "| [HIGH] | architect | c1 | Sealed | Defense: user-directed |\n"
SEALED_HIGH_2 = "| [HIGH] | critic | c2 | Accepted as risk | Defense: known risk |\n"
ADDRESSED_HIGH = "| [HIGH] | architect | c3 | Addressed | fixed inline |\n"


def test_sealed_only_pass_stamps_unresolved_convergence(tmp_path):
    art = _artifact(tmp_path, SEALED_HIGH + SEALED_HIGH_2)
    proc = _run_archive([str(art), "--phase", "1"])
    assert proc.returncode == 0, proc.stderr
    assert "converged (0 unresolved HIGH); sealed=2" in _notes_cell(art)


def test_sealed_exit_does_not_stamp_zero_high(tmp_path):
    """RK4's negative pin: the sealed exit must NOT claim zero HIGH."""
    art = _artifact(tmp_path, SEALED_HIGH)
    _run_archive([str(art), "--phase", "1"])
    assert "converged (0 HIGH)" not in _notes_cell(art)


def test_addressed_high_blocks_convergence(tmp_path):
    art = _artifact(tmp_path, ADDRESSED_HIGH)
    _run_archive([str(art), "--phase", "1"])
    assert "converged" not in _notes_cell(art)


def test_deferred_high_blocks_convergence(tmp_path):
    art = _artifact(tmp_path, "| [HIGH] | critic | c | Deferred → tasks.md | Routed because: later. |\n")
    _run_archive([str(art), "--phase", "1"])
    assert "converged" not in _notes_cell(art)


def test_halt_high_blocks_convergence(tmp_path):
    art = _artifact(tmp_path, "| [HIGH] | critic | c | Halt and re-scope | scope shifted |\n")
    _run_archive([str(art), "--phase", "1"])
    assert "converged" not in _notes_cell(art)


def test_sealed_med_with_addressed_high_blocks_convergence(tmp_path):
    """Sealing a non-HIGH cannot move the exit test."""
    art = _artifact(tmp_path, ADDRESSED_HIGH + "| [MED] | critic | m | Sealed | Defense: m |\n")
    _run_archive([str(art), "--phase", "1"])
    assert "converged" not in _notes_cell(art)


def test_zero_high_pass_still_stamps_converged_zero_high(tmp_path):
    """The clean exit keeps its original literal exactly."""
    art = _artifact(tmp_path, "| [MED] | critic | m | Addressed | tightened |\n")
    _run_archive([str(art), "--phase", "1"])
    notes = _notes_cell(art)
    assert "converged (0 HIGH)" in notes and "unresolved" not in notes


def test_strict_bar_sealed_exit_tag_order(tmp_path):
    """Mode tag first, then the two-part convergence stamp."""
    art = _artifact(tmp_path, SEALED_HIGH)
    _run_archive([str(art), "--phase", "1", "--strict-bar"])
    notes = _notes_cell(art)
    assert notes.index("strict-bar pass") < notes.index("converged (0 unresolved HIGH)")
    assert "converged (0 unresolved HIGH); sealed=1" in notes


def test_cross_check_sealed_exit_tag_order(tmp_path):
    art = _artifact(tmp_path, SEALED_HIGH)
    _run_archive([str(art), "--phase", "1", "--cross-check"])
    notes = _notes_cell(art)
    assert notes.index("cross-check pass") < notes.index("converged (0 unresolved HIGH)")


def test_tags_token_renders_last_on_a_sealed_exit(tmp_path):
    """Phase 2/3 stashes `tags=dXuYcZ`; it must stay the LAST tag part."""
    art = _artifact(tmp_path, "| [HIGH] | architect | [contract] c | Sealed | Defense: d |\n")
    _run_archive([str(art), "--phase", "2"])
    notes = _notes_cell(art)
    assert notes.index("converged (0 unresolved HIGH)") < notes.index("tags=")
    assert notes.rstrip().endswith(notes[notes.index("tags="):].rstrip())


def test_sealed_token_recoverable_by_regex(tmp_path):
    """`sealed=(\\d+)` is the published machine contract a later gate reads."""
    art = _artifact(tmp_path, SEALED_HIGH + SEALED_HIGH_2)
    _run_archive([str(art), "--phase", "1"])
    m = re.search(r"sealed=(\d+)", _notes_cell(art))
    assert m and m.group(1) == "2"


def test_upstream_sealed_high_stamps_convergence_and_halt_vote(tmp_path):
    """AD25, pinned as INTENDED rather than asserted never to co-occur.

    A Phase-2 `[upstream]`-tagged HIGH auto-routes to a halt vote regardless of
    disposition. Sealing it converges the pass, so one Notes cell legitimately
    carries both the convergence stamp and the halt-vote text. A gate reading
    the stamp must read the whole cell.
    """
    art = _artifact(tmp_path, "| [HIGH] | architect | [upstream] c | Sealed | Defense: d |\n")
    _run_archive([str(art), "--phase", "2"])
    notes = _notes_cell(art)
    assert "converged (0 unresolved HIGH); sealed=1" in notes
    assert "halt vote" in notes.lower()


def test_sealed_high_without_defense_fails_archive_and_writes_no_stamp(tmp_path):
    """The existing FormatViolation guard is what backs the whole exit."""
    art = _artifact(tmp_path, "| [HIGH] | architect | c | Sealed | no defense here |\n")
    before = art.read_text(encoding="utf-8")
    proc = _run_archive([str(art), "--phase", "1"])
    assert proc.returncode != 0
    assert art.read_text(encoding="utf-8") == before, "a rejected archive wrote to the artifact"


def test_highs_column_still_records_raised(tmp_path):
    """R6: the HIGHs column is the durable audit record and keeps counting
    HIGHs RAISED, so a converged row may show a non-zero HIGHs count."""
    art = _artifact(tmp_path, SEALED_HIGH + SEALED_HIGH_2)
    _run_archive([str(art), "--phase", "1"])
    cells = _trajectory_cells(art)
    assert cells[2] == "2", f"HIGHs column should record 2 raised, got {cells[2]!r}"
    assert "converged" in cells[-1]


def test_sealed_column_may_differ_from_sealed_token(tmp_path):
    """The Sealed COLUMN counts every severity; `sealed=<N>` counts HIGHs only."""
    art = _artifact(tmp_path, SEALED_HIGH + "| [MED] | critic | m | Sealed | Defense: m |\n")
    _run_archive([str(art), "--phase", "1"])
    cells = _trajectory_cells(art)
    assert cells[6] == "2", f"Sealed column counts all severities, got {cells[6]!r}"
    assert "sealed=1" in cells[-1], "the token counts HIGH-severity seals only"


def test_sealed_exit_row_is_normal(tmp_path):
    """`_is_normal_pass_row` must still classify a sealed-exit row NORMAL.

    The new stamp contains none of `strict-bar pass`, `cross-check pass`,
    `earlier passes elided` and does not start with `skipped` — so the
    classifier is unaffected. If it were not, the strict-bar trigger would
    silently stop seeing these passes.
    """
    art = _artifact(tmp_path, SEALED_HIGH)
    _run_archive([str(art), "--phase", "1"])
    notes = _notes_cell(art)
    assert "converged (0 unresolved HIGH); sealed=1" in notes
    assert archive_pass._is_normal_pass_row({"Notes": notes}) is True


def test_strict_bar_signal_unchanged_across_sealed_exits():
    """R6: the trigger reads RAISED HIGHs, and the new stamp does not move it.

    Two consecutive sealed-exit rows carry the new stamp AND a non-zero HIGHs
    column. The trigger's verdict must be identical to the same rows carrying
    the old-style Notes, because it reads the HIGHs column — which R4 leaves
    alone — not the stamp.
    """
    def row(notes):
        return {"Pass": "1", "Date": "2026-07-26", "HIGHs": "3", "Regressions": "0",
                "Addressed": "0", "Deferred": "2", "Sealed": "3", "Notes": notes}

    class _Args:
        phase = 1
        strict_bar = False
        cross_check = False
        skip = False
        terminal = False

    sealed_prior = [row("converged (0 unresolved HIGH); sealed=3")]
    plain_prior = [row("")]
    current = row("converged (0 unresolved HIGH); sealed=3")

    sealed_verdict = archive_pass.detect_strict_bar_signal(sealed_prior, current, _Args())
    plain_verdict = archive_pass.detect_strict_bar_signal(plain_prior, row(""), _Args())
    assert sealed_verdict == plain_verdict, (
        "the sealed-exit stamp changed the strict-bar trigger's verdict; it "
        "must read the HIGHs column, not the Notes stamp"
    )


# --- C5: the module docstring as the published contract (R5, R6) -------------
#
# AD5 makes this docstring the contract of record that a later approval-gate
# reader consumes for the `sealed=(\d+)` grammar. It sits outside AD11's
# SWEEP_ROOTS, so nothing else in this feature would catch it going stale.

def test_module_docstring_documents_both_stamps_and_contract():
    doc = archive_pass.__doc__ or ""
    for fragment in (
        "converged (0 HIGH)",
        "converged (0 unresolved HIGH); sealed=<N>",
        "no HIGH concerns other than those dismissed with a recorded `Defense:`",
        "presence",
        "sealed=(\\d+)",
        "licenses observation, not enforcement",
        "Sealed column",
    ):
        assert fragment in doc, (
            f"archive_pass.py's module docstring does not document:\n  {fragment!r}"
        )


def test_module_docstring_stale_exit_clause_removed():
    """The old clause is DELETED, not merely supplemented.

    Its own named negative test: a docstring that documents the new exit test
    while still asserting the old one is worse than one documenting neither,
    and a positive-only assertion would pass with both present.
    """
    doc = archive_pass.__doc__ or ""
    stale = "the loop's exit decision still reads the HIGHs column directly"
    assert stale not in doc, (
        f"the stale exit clause survives in the module docstring: {stale!r}"
    )
