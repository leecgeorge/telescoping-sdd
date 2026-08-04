"""Prose-presence and parity guard for the Unit B authoring conventions.

Fails CI when any guarded discipline surface drops or desyncs a convention this
feature installs, when a paired surface falls out of parity, or when any of
R10's prohibited clause shapes appears.

See specs/unit-b-spec-thinning-doctrine-and-archive-fix/{01_spec,02_design}.md —
component C6. Placement per AD9: this file reads surfaces from BOTH plugin tiers
(spec-driven-dev and project-blueprint), so it lives in the shared
`telescoping-sdd/scripts/tests/` rather than under either skill.

Imports no production module; reads nine committed repo files from disk. No
fixtures, no tmp dirs — it runs identically in a clean CI checkout.

NOT IN SCOPE (spec R7 ¶3): R11's doctrine sentences. `test_r11_concern_bullet_corrected`
lives in `test_archive_pass.py` with the rest of R11's coverage, even though this
file does read both tiers' panel-review.md for R12's step-8 rule and C7c's
pointer/count.
"""

from __future__ import annotations

import re
from pathlib import Path

# tests/ -> scripts/ -> telescoping-sdd/ -> repo root (AD9; the same idiom as
# the sibling test_panel_review_split.py in this directory).
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]

SPEC_TEMPLATE_PY = "telescoping-sdd/skills/spec-driven-dev/references/spec-template-python.md"
SPEC_TEMPLATE_JAVA = "telescoping-sdd/skills/spec-driven-dev/references/spec-template-java.md"
PHASE_SPECIFY = "telescoping-sdd/skills/spec-driven-dev/references/phase-specify.md"
SPEC_ANALYST = "telescoping-sdd/agents/feature-spec-analyst.md"
SELF_REVIEW_CANON = "telescoping-sdd/agent-references/agent-self-review-instructions.md"
MODES_SDD = "telescoping-sdd/skills/spec-driven-dev/references/panel-review-modes.md"
MODES_BP = "telescoping-sdd/skills/project-blueprint/references/panel-review-modes.md"
PANEL_SDD = "telescoping-sdd/skills/spec-driven-dev/references/panel-review.md"
PANEL_BP = "telescoping-sdd/skills/project-blueprint/references/panel-review.md"

BOTH_TEMPLATES = [SPEC_TEMPLATE_PY, SPEC_TEMPLATE_JAVA]
BOTH_MODES = [MODES_SDD, MODES_BP]
BOTH_PANELS = [PANEL_SDD, PANEL_BP]
# C1-C4: every surface that carries thin-form guidance (DM4 / R2 tripwire).
THIN_FORM_SURFACES = [SPEC_TEMPLATE_PY, SPEC_TEMPLATE_JAVA, PHASE_SPECIFY, SPEC_ANALYST]

# ---------------------------------------------------------------------------
# Marker sets (DM4, DM6, DM7, DM9, DM10)
# ---------------------------------------------------------------------------

THIN_FORM_MARKERS = ["**From PLAN F<n>:**", "one-line gloss", "PLAN-driven"]

R9_MARKERS = [
    "point rather than restate",
    # The leading "Where" is deliberately excluded: it is sentence-initial and
    # bolded in DM6, and _missing is case-sensitive.
    "a fact has an authoritative home",
    "names a location and a role",
    "durable",
    "consistency",
    "conditional, never absolute",  # R9 AC-2 / RK6 — see DM6
]
R9_LENGTH_VOCABULARY = ["shorter", "word count", "verbosity reduction"]

R10_MARKERS = [
    "self-select depth",
    "Changed since pass",
    "already holds",
    "context reset",
    "scope",
    "Strict-Bar Convergence Mode",
    "Synthesizer Self-Check",
]
R10_OBLIGATION_MARKERS = ["obligation test", "removes work"]
R10_FORBIDDEN = [
    "at full depth",
    "read-through floor",
    "read through the remainder",
    "tool-call budget",
    "tool call budget",
    "needs-verification",
]

R12_MARKERS = [
    "per pass, not per fix",
    "blocking set",
    "exit-capable",
    "re-grade",
    "name the downstream artifact",
    "User input needed",
    "never spawn a new item",
]

# The single shared-doctrine sentence C10d adds to the Cap-pressure caveat.
# Asserted present in each tier and NOTHING more — the caveat's role-specific
# examples are a documented intentional asymmetry ([DEF-10] / R7's last AC).
CAP_PRESSURE_ADDED_SENTENCE = (
    "On a pass that is already non-terminal the marginal cost of a further fix "
    "is zero, so the inverted bias applies only to an exit-capable pass."
)

# ---------------------------------------------------------------------------
# DM5 region anchors
# ---------------------------------------------------------------------------

ANCHOR_OBJECTIVE_BULLET = "- **Objective**"
ANCHOR_THIN_FORM = "**PLAN-driven thin Objective (drafting).**"
ANCHOR_SPECIFY_PANEL = "## Spec Panel Review"
ANCHOR_ANALYST_GAPS = "- **Gaps**"
ANCHOR_CANON_GAPS = "### 3. Gaps"
ANCHOR_MODES_SCOPED = "## Scoped late pass (manually scoped)"
ANCHOR_MODES_PROHIBITIONS = "### What must never be added (the obligation test)"
ANCHOR_PANEL_STEP8 = "8. **Exit when the pass leaves no unresolved HIGH concern**"
ANCHOR_SITUATIONAL_MODES = "## Situational panel modes (loaded on demand)"
ANCHOR_R9_BLOCK = "**Authoring convention — point rather than restate.**"

# The exact unconditional line C3b must rewrite (whole-line, stripped).
STALE_OBJECTIVE_LINE = "- **Objective** — One paragraph on what and why"

# The reverted v2.24.0 heuristic. A literal-token tripwire; it cannot catch a
# paraphrased reintroduction (RISK-7 — that class is the human gate's).
REVERTED_TRIGGER_TOKEN = "observable-stakeholder"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(rel_path: str) -> str:
    """Read a repo-relative discipline surface as UTF-8 text.

    A missing file is a failure the guard reports, never swallows — a moved or
    renamed surface must not read as a silently-passing test.
    """
    path = _REPO_ROOT / rel_path
    assert path.is_file(), f"guarded surface missing: {rel_path}"
    return path.read_text(encoding="utf-8")


def _norm(text: str) -> str:
    """Normalize a slice for substring matching.

    Strips markdown blockquote prefixes, then collapses every whitespace run to
    a single space. Load-bearing, not cosmetic: every convention this feature
    inserts ships as a *wrapped blockquote*, so a multi-word marker can straddle
    a line break and carry an embedded "\\n> " in the raw text.

    Bounded, not universal: a wrap falling INSIDE a hyphenated token still
    defeats a literal match ("read-" / "through" collapses to "read- through",
    not "read-through"). Normalization is never worse than raw matching, only
    sometimes not enough; the residual sits on RISK-11.

    Case is deliberately NOT normalized here: `**From PLAN F<n>:**` is an
    Ask-First literal label whose casing is part of the convention.
    """
    text = re.sub(r"(?m)^\s*>\s?", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _missing(text: str, markers: list[str]) -> list[str]:
    """Return the markers absent from `_norm(text)`, order-preserving.

    Empty result == all present. Case-sensitive by design — see `_norm`.
    """
    norm = _norm(text)
    return [m for m in markers if m not in norm]


def _region(text: str, start: str, end_prefixes: tuple[str, ...] = ("#",),
            allow_eof: bool = False) -> str:
    """Return the DM5 heading-region slice.

    From the line containing `start` up to (but not including) the next line
    whose lstrip begins with any of `end_prefixes`.

    `allow_eof=True` permits a region that runs to end-of-file. Required by
    exactly three call sites (DM5): `modes.scoped`, `modes.scoped.prohibitions`
    and `panel.situational-modes`. Granting it to fewer is not a soft failure —
    the omitted region raises here and its test cannot execute at all.
    """
    lines = text.splitlines()
    begin = None
    for i, line in enumerate(lines):
        if start in line:
            begin = i
            break
    assert begin is not None, f"region anchor not found: {start!r}"
    for j in range(begin + 1, len(lines)):
        if any(lines[j].lstrip().startswith(p) for p in end_prefixes):
            return "\n".join(lines[begin:j])
    assert allow_eof, (
        f"region {start!r} ran to EOF without hitting {end_prefixes!r} and "
        f"allow_eof is False — the region is under-granted (DM5)"
    )
    return "\n".join(lines[begin:])


def _bullet(text: str, anchor: str) -> str:
    """Return the DM5 bullet block.

    The line starting with `anchor` plus any wrapped continuation, stopping at
    the first following line that is blank, starts with "- " (next bullet), or
    starts with "#" (heading). Handles a last-in-list bullet.

    Authoring constraint this encodes (C3b/C4b): added marker prose MUST be a
    continuation of the anchor bullet with no intervening blank line, or the
    extractor truncates before it and the test reddens.
    """
    lines = text.splitlines()
    begin = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith(anchor):
            begin = i
            break
    assert begin is not None, f"bullet anchor not found: {anchor!r}"
    block = [lines[begin]]
    for line in lines[begin + 1:]:
        stripped = line.lstrip()
        if not line.strip() or stripped.startswith("- ") or stripped.startswith("#"):
            break
        block.append(line)
    return "\n".join(block)


def _forbidden(text: str, phrases: list[str]) -> list[str]:
    """Return the phrases present in `_norm(text)`, case-insensitively.

    Empty result == clean. Normalizes for the same reason the presence helpers
    do — a prohibited clause split across a line break must still be caught, or
    the R10 blocklist is trivially evadable by re-wrapping. Case-insensitive
    here (unlike `_missing`) because the blocklist targets operative
    vocabulary, not a literal label.
    """
    norm = _norm(text).lower()
    return [p for p in phrases if p.lower() in norm]


def _assert_fragment_parity(rel_paths: list[str], region_fn, markers: list[str]) -> None:
    """Assert every marker is present in each path's region.

    Reports per-path missing sets, so the DIRECTION of a desync is visible
    rather than just its existence.
    """
    report = {}
    for rel in rel_paths:
        gone = _missing(region_fn(_read(rel)), markers)
        if gone:
            report[rel] = gone
    assert not report, "marker(s) missing — " + "; ".join(
        f"{rel}: {gone}" for rel, gone in report.items()
    )


def _assert_added_sentence(rel_paths: list[str], sentence: str) -> None:
    """Assert one sentence is present in each path — and nothing more.

    Used ONLY for the Cap-pressure caveat, whose role-specific examples are a
    documented intentional asymmetry ([DEF-10] / R7's last AC). Never call
    `_assert_fragment_parity` on that site: doing so would force a sync the
    file's own sync header forbids.
    """
    for rel in rel_paths:
        assert sentence in _norm(_read(rel)), (
            f"{rel}: the C10d shared-doctrine sentence is absent:\n  {sentence}"
        )


# Region accessors, so each test names its DM5 region rather than re-deriving it.
def _r_thin_form(text: str) -> str:
    return _region(text, ANCHOR_THIN_FORM)


def _r_specify_panel(text: str) -> str:
    return _region(text, ANCHOR_SPECIFY_PANEL)


def _r_modes_scoped(text: str) -> str:
    return _region(text, ANCHOR_MODES_SCOPED, allow_eof=True)


def _r_modes_prohibitions(text: str) -> str:
    return _region(text, ANCHOR_MODES_PROHIBITIONS, allow_eof=True)


def _r_step8(text: str) -> str:
    return _region(text, ANCHOR_PANEL_STEP8)


def _r_situational(text: str) -> str:
    return _region(text, ANCHOR_SITUATIONAL_MODES, allow_eof=True)


def _r_r9_block(text: str) -> str:
    return _region(text, ANCHOR_R9_BLOCK)


def _scoped_minus_prohibitions(text: str) -> str:
    """The R10 absence slice (AD12): the sanction section MINUS its own
    prohibitions subsection, which necessarily quotes the forbidden vocabulary
    in order to forbid it. Unexcised, the blocklist self-fires on day one.
    """
    scoped = _r_modes_scoped(text)
    prohibitions = _r_modes_prohibitions(text)
    return scoped.replace(prohibitions, "")


# ===========================================================================
# R1 / R2 / R4 / R5 — the thin-form convention (C1-C4)
# ===========================================================================

def test_python_template_carries_thin_form():
    """R7 AC-a — the Python spec template sanctions the thin Objective."""
    gone = _missing(_read(SPEC_TEMPLATE_PY), THIN_FORM_MARKERS)
    assert not gone, f"{SPEC_TEMPLATE_PY}: thin-form marker(s) missing: {gone}"


def test_java_template_carries_thin_form():
    """R7 AC-a — the Java template carries the identical sanction."""
    gone = _missing(_read(SPEC_TEMPLATE_JAVA), THIN_FORM_MARKERS)
    assert not gone, f"{SPEC_TEMPLATE_JAVA}: thin-form marker(s) missing: {gone}"


def test_templates_in_parity():
    """R7 AC-a (parity) + AC-b (locating) — the two templates must not drift.

    A convention edited in one profile's template and not the other is the
    desync this pair exists to catch.
    """
    _assert_fragment_parity(
        BOTH_TEMPLATES, lambda t: t, THIN_FORM_MARKERS + ["**Derived from:**"]
    )


def test_phase_specify_carries_thin_form():
    """R7 AC-a — region-scoped to `specify.thin-form`.

    Region-scoped, not whole-file: several of these tokens legitimately occur
    elsewhere in phase-specify.md, so a whole-file check would pass vacuously.
    """
    gone = _missing(_r_thin_form(_read(PHASE_SPECIFY)), THIN_FORM_MARKERS)
    assert not gone, f"{PHASE_SPECIFY} [specify.thin-form]: marker(s) missing: {gone}"


def test_analyst_carries_thin_form():
    """R7 AC-a — the drafter agent emits the thin form."""
    gone = _missing(_read(SPEC_ANALYST), THIN_FORM_MARKERS)
    assert not gone, f"{SPEC_ANALYST}: thin-form marker(s) missing: {gone}"


def test_derived_variant_documented():
    """R5 — the CPD-derived variant is documented in BOTH places.

    Cross-surface by construction: the `**Derived from:**` provenance prose must
    appear inside phase-specify.md's thin-form region (NOT whole-file — the
    token pre-exists elsewhere in that file) AND as DM1's CPD sub-shape in both
    templates. It therefore only goes green once T4 and T5 have both landed.
    """
    region = _r_thin_form(_read(PHASE_SPECIFY))
    assert "**Derived from:**" in _norm(region), (
        f"{PHASE_SPECIFY} [specify.thin-form]: CPD provenance-pointer prose absent"
    )
    _assert_fragment_parity(BOTH_TEMPLATES, lambda t: t, ["**Derived from:**"])


def test_cpd_no_second_pointer():
    """R5 AC-1 (negative) — a CPD-derived feature adds no second pointer line.

    Its existing `**Derived from:**` line already IS the provenance pointer.
    """
    _assert_fragment_parity(
        BOTH_TEMPLATES, lambda t: t, ["do not add a second pointer line"]
    )


def test_standalone_rule_present():
    """R4 / DM3 — a standalone (`n/a`, no `**Derived from:**`) feature is NOT
    eligible for the thin form and keeps the full Objective narrative.

    Guards Boundaries' "never relax this for a standalone spec".
    """
    _assert_fragment_parity(BOTH_TEMPLATES, lambda t: t, ["standalone", "NOT eligible"])


def test_gloss_worked_contrast_present():
    """[DEF-04] — the worked legitimate/not-legitimate gloss contrast ships.

    Without it "write a one-line gloss" is advice nobody can apply consistently;
    the contrast is what makes the rule checkable.
    """
    _assert_fragment_parity(
        BOTH_TEMPLATES,
        lambda t: t,
        ["does this sentence say something PLAN does not already say"],
    )


def test_dispatch_carries_plan_drivenness():
    """[DEF-07] — the drafting dispatch must carry more than the bare identifier.

    A drafter handed only `F7` cannot write `**From PLAN F7:** <ref>`, nor gloss
    framing it has never seen: it needs the PLAN-driven-ness verdict AND the
    PLAN entry reference.
    """
    region = _norm(_r_thin_form(_read(PHASE_SPECIFY)))
    assert "PLAN entry reference" in region, (
        f"{PHASE_SPECIFY} [specify.thin-form]: the dispatch-content statement "
        f"([DEF-07]) does not name the PLAN entry reference"
    )


def test_trigger_is_plan_driven_not_stakeholder():
    """R2 — the trigger is PLAN-driven-ness, and nothing else.

    Two halves. (i) A literal-token tripwire: the reverted v2.24.0
    observable-stakeholder heuristic must not reappear on ANY thin-form surface
    (C1-C4). This half is green pre-edit by nature — the token is absent today —
    and exists to stay green. (ii) The positive, pinned sole-trigger assertion
    inside `specify.thin-form`, which is what actually goes red pre-edit.
    """
    for rel in THIN_FORM_SURFACES:
        assert REVERTED_TRIGGER_TOKEN not in _norm(_read(rel)).lower(), (
            f"{rel} re-introduced the reverted observable-stakeholder trigger"
        )
    region = _norm(_r_thin_form(_read(PHASE_SPECIFY)))
    assert "sole trigger" in region, (
        f"{PHASE_SPECIFY} [specify.thin-form]: the pinned literal 'sole trigger' "
        f"is absent"
    )
    assert "PLAN-driven" in region, (
        f"{PHASE_SPECIFY} [specify.thin-form]: 'sole trigger' is not co-located "
        f"with 'PLAN-driven'"
    )


# ===========================================================================
# R6 / R7 — the self-review carve-out and its canonical breadcrumb
# ===========================================================================

def test_analyst_has_r6_carveout():
    """R7 AC-c — the carve-out lives inside the `- **Gaps**` bullet itself.

    Bullet-scoped, not whole-file: a broadened reword that moves the phrase out
    of the Gaps bullet must fail, because the carve-out only works where the
    self-review actually reads it.
    """
    bullet = _norm(_bullet(_read(SPEC_ANALYST), ANCHOR_ANALYST_GAPS))
    gone = [m for m in ("treated as substantive", "PLAN-driven") if m not in bullet]
    assert not gone, (
        f"{SPEC_ANALYST} [analyst.gaps]: carve-out marker(s) missing: {gone}\n"
        f"bullet was:\n  {bullet}"
    )


def test_phase_specify_line41_qualified():
    """R7 AC-d — the Required-sections Objective bullet is qualified.

    Dual assertion, and both halves are load-bearing. The positive half is
    BULLET-scoped because `PLAN-driven` (absent today) will occur elsewhere in
    this file once C3a and C3c land, so a whole-file positive check would pass
    vacuously. The negative half is whole-file: the unconditional line must be
    gone, not merely duplicated somewhere better.
    """
    text = _read(PHASE_SPECIFY)
    bullet = _norm(_bullet(text, ANCHOR_OBJECTIVE_BULLET))
    assert "PLAN-driven" in bullet, (
        f"{PHASE_SPECIFY} [specify.objective-bullet]: the Objective bullet is "
        f"not qualified for the PLAN-driven thin form:\n  {bullet}"
    )
    stale = [ln for ln in text.splitlines() if ln.strip() == STALE_OBJECTIVE_LINE]
    assert not stale, (
        f"{PHASE_SPECIFY}: the stale unconditional line survives verbatim: "
        f"{STALE_OBJECTIVE_LINE!r}"
    )


def test_phase_specify_panel_locus_sanctions_thin():
    """R7 AC-e / R8 — the sanction must ACTIVELY reach a Specify panelist.

    AD5: a passive note in the panel section would never be dispatched, so the
    region must carry an append-to-each-panelist's-prompt directive. The
    sanction is also deliberately NARROW — it sanctions brevity only, and must
    not suppress gloss-fidelity scrutiny.
    """
    region = _norm(_r_specify_panel(_read(PHASE_SPECIFY)))
    assert "append" in region.lower() and "prompt" in region.lower(), (
        f"{PHASE_SPECIFY} [specify.panel]: no active dispatch-injection "
        f"instruction — a passive note never reaches a panelist (AD5)"
    )
    assert "merely because it is brief" in region, (
        f"{PHASE_SPECIFY} [specify.panel]: the brevity-vs-fidelity scoping is absent"
    )
    assert "paraphrase" in region, (
        f"{PHASE_SPECIFY} [specify.panel]: gloss-fidelity scrutiny is not preserved"
    )


def test_self_review_canon_breadcrumb():
    """R7 AC-f — the canonical self-review instructions carry the breadcrumb.

    AD6 / RISK-5: without it, a future diff-based resync from source-of-truth
    silently reverts the C4b divergence. This is the CI backstop for that.
    """
    region = _norm(_region(_read(SELF_REVIEW_CANON), ANCHOR_CANON_GAPS))
    assert "feature-spec-analyst.md" in region, (
        f"{SELF_REVIEW_CANON} [canon.gaps]: the breadcrumb naming the sanctioned "
        f"feature-spec-analyst.md divergence is absent"
    )


# ===========================================================================
# R9 — point rather than restate
# ===========================================================================

def test_r9_convention_in_both_templates():
    """R7 AC-g / R9 — the convention is present and in parity."""
    _assert_fragment_parity(BOTH_TEMPLATES, _r_r9_block, R9_MARKERS)


def test_r9_not_framed_as_length_reduction():
    """R9 AC-5 — the convention must never be framed as a length reduction.

    De-duplicating by pointer typically makes a document slightly LONGER. Framed
    as brevity it becomes the reverted v2.24 compression rule wearing a new name.
    """
    for rel in BOTH_TEMPLATES:
        hits = _forbidden(_r_r9_block(_read(rel)), R9_LENGTH_VOCABULARY)
        assert not hits, (
            f"{rel}: the R9 convention is framed as a length reduction: {hits}"
        )


# ===========================================================================
# R10 — the scoped late pass sanction (both tiers)
# ===========================================================================

def test_r10_sanction_in_both_tiers():
    """R7 AC-h / R10 — the sanction ships in both tiers, in parity."""
    _assert_fragment_parity(BOTH_MODES, _r_modes_scoped, R10_MARKERS)


def test_r10_prohibited_clauses_absent():
    """R7 AC-i / R10 AC-2 — no guard clause may rebuild the cost R10 removes.

    Asserted over the sanction section MINUS its own prohibitions subsection
    (AD12), which necessarily quotes this vocabulary in order to forbid it.

    RISK-10 is the failure this guards: a well-meaning safety clause added later
    is exactly what killed the mechanized predecessor.
    """
    for rel in BOTH_MODES:
        hits = _forbidden(_scoped_minus_prohibitions(_read(rel)), R10_FORBIDDEN)
        assert not hits, (
            f"{rel} [modes.scoped]: prohibited clause shape(s) present: {hits} — "
            f"a clause that creates an obligation rebuilds the cost this mode removes"
        )


def test_r10_obligation_test_stated():
    """R10 AC-3 — the discriminator ships INSIDE the guidance.

    It is the editor's own test: a clause that removes work is admissible; a
    clause that creates an obligation is not. Shipping it in the section is what
    makes the section self-defending against a future well-meaning edit.
    """
    _assert_fragment_parity(BOTH_MODES, _r_modes_prohibitions, R10_OBLIGATION_MARKERS)


def test_r10_read_pointer_and_count_in_both_tiers():
    """C7c — panel-review.md must not lie about its own contents.

    Once the new section lands, "Five panel behaviours" is factually false. No
    pre-existing test pinned that count or the bullet list, so this feature adds
    the guard rather than shipping the convention unchecked.
    """
    for rel in BOTH_PANELS:
        region = _norm(_r_situational(_read(rel)))
        assert "Scoped late pass (manually scoped)" in region, (
            f"{rel} [panel.situational-modes]: no Read-pointer bullet for the new section"
        )
        assert "Six panel behaviours" in region, (
            f"{rel} [panel.situational-modes]: lead-in count was not updated to six"
        )
        assert "Five panel behaviours" not in region, (
            f"{rel} [panel.situational-modes]: the stale five-count survives"
        )


# ===========================================================================
# R12 — the free-ride rule (both tiers)
# ===========================================================================

def test_r12_free_ride_rule_in_both_tiers():
    """R7 AC-j / R12 — the free-ride rule ships in step 8, in parity.

    The subtlest committed point is the discriminator: it keys on a HIGH landing
    in the BLOCKING set, not on a HIGH being raised. Getting that wrong would
    create the extra pass this rule exists to remove.
    """
    _assert_fragment_parity(BOTH_PANELS, _r_step8, R12_MARKERS)


def test_r12_cap_pressure_added_sentence_only():
    """R7 AC-k / [DEF-10] — added-sentence parity, never whole-paragraph identity.

    The Cap-pressure caveat's role-specific examples diverge between tiers BY
    DESIGN (the file's own sync header says so). This asserts only that the one
    shared-doctrine sentence C10d adds is present in each copy.
    """
    _assert_added_sentence(BOTH_PANELS, CAP_PRESSURE_ADDED_SENTENCE)
