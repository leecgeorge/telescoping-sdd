"""Structural parity and verbatim-content regression tests for the two
`hash-and-cascade.md` files (spec-driven-dev and project-blueprint).

This test module is the regression-protected safety net for the
`mid-stream-review` feature's editorial work. It pins the design's content
contracts as Python multi-line string constants and asserts their verbatim
presence in both files; it also normalizes vocabulary and asserts the two
files' `## Re-Approval After Edits` sections are structurally identical.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# Import the shared panel-doc helpers (extracted to one module in T12 so this
# file and test_panel_review_autonomy.py share one definition — no drift).
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))
from _panel_doc_helpers import (  # noqa: E402
    PB_FORBIDDEN_SDD_VOCABULARY,
    extract_section as _extract_section,
    extract_step_3_block as _extract_step_3_block,
    extract_subsection as _extract_subsection,
)

# Locate the repo root so the test runs from any cwd.
_REPO_ROOT = Path(__file__).resolve().parents[3]
SDD_PATH = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/hash-and-cascade.md"
PB_PATH = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/hash-and-cascade.md"

BOTH_FILES = [
    pytest.param(SDD_PATH, "sdd", id="sdd"),
    pytest.param(PB_PATH, "pb", id="pb"),
]

# Project-blueprint reference files touched by the milestone-Done feature.
PLAN_TEMPLATE_PATH = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/plan-template.md"
WORKFLOW_OVERVIEW_PATH = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/workflow-overview.md"

# Make telescoping-sdd/scripts importable for the MILESTONE_FEATURE_ROW parity pin.
_SCRIPTS_DIR = _REPO_ROOT / "telescoping-sdd" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# ============================================================================
# Verbatim content constants (pinned to design's content contracts).
# ============================================================================

INTERFACE_I1 = """Upstream panel re-review: recommended (yes)
Reason: <one-sentence reason naming the category of change and which panelists would care — focus on the concern, mention panelists parenthetically if it adds clarity>

Run upstream panel re-review on `<filename>` before cascading? (Y/n)"""

INTERFACE_I2_OPENING = "Upstream panel re-review: not recommended (no)"
INTERFACE_I2_QUESTION = "Run upstream panel re-review on `<filename>` before cascading? (y/N)"

INTERFACE_I3 = "Upstream panel re-review: skipped — trivial edit (whitespace / punctuation / comment-only, no semantic diff)"
INTERFACE_I3_NO_PATH = "Upstream panel re-review: skipped — user declined"

INTERFACE_I4_AUTO_FIXES_FRAGMENT = "re-approved after upstream panel: hash"
INTERFACE_I4_NO_AUTO_FIXES_FRAGMENT = "upstream panel complete: no auto-fixes applied"

INTERFACE_I5_A_FRAGMENT = "the upstream panel re-review was skipped on a lean-yes edit"
INTERFACE_I5_B_FRAGMENT = "Upstream panel: converged immediately — no issues found, consistent with lean-no recommendation"

C2_DEBUG_NOTE = "Upstream panel re-review: suppressed — Phase 4 task-tick carve-out active"
C2_TASK_TICK_DISCRIMINATOR_FRAGMENT = "A task-tick edit is one that modifies only checkbox state"

C5_DOCTRINE_REPLACEMENT_SENTENCE_FRAGMENT = "consistency-check boundary AND at one earlier point"
C5_OLD_DOCTRINE_SENTENCE = "Real decisions surface only at the consistency-check boundary."

RECOVERY_PHRASING = "run the upstream panel re-review on `<file>` now"

AD3_VOCABULARY_TOKENS = (
    "user-edit",
    "claude-edit",
    "git-pull",
    "git-merge",
    "branch-switch",
    "keystroke",
    "non-keystroke",
    "ambiguous",
    "top_level_entry",
    "STRICT-BAR-SIGNAL",
    "Halt and re-scope",
    "Addressed",
    "Deferred",
    "Sealed",
    "Accepted as risk",
    "upstream-panel",
)

AD7_PROVENANCE_REGEX = "upstream-panel [0-9a-f]{8}"

I4_ELISION_MANIFEST = "Detailed re-stamp manifest:"

AD1_AMBIGUOUS_SOURCE_NOTE = "edit source could not be confidently classified; treating as non-keystroke per AD1 default."

C4_INLINE_SUMMARY_VERBATIM_FRAGMENT_1 = "Closed-feature immutability in scope."
C4_INLINE_SUMMARY_VERBATIM_FRAGMENT_2 = "byte-frozen as a historical commitment and must NOT be edited in place"
C4_INLINE_SUMMARY_VERBATIM_VALID_DISPOSITIONS = "divergence note in the downstream spec's `## Accepted Divergences`"
C4_INLINE_SUMMARY_VERBATIM_REMEDIATION = "new remediation feature added to PLAN.md's `## Feature Breakdown`"

# Canonical milestone-lookup form (review finding Correct D1-3): match a
# milestone-feature row in any checkbox state, then inspect whether it is `[x]`.
# Previously stated here as the malformed `^- \[xX\] F\d+\b` (literal "xX", not a
# character class) — reconciled to the same form used by workflow-overview.md
# § Closed-Feature-Row Immutability / panel-review Self-Check (e) / phase-plan.md.
C4_REGEX_PATTERN = r"^- \[[ xX]\] F\d+\b"

FORBIDDEN_PANELIST_NAMES_INLINE = (
    "user-advocate",
    "devils-advocate",
    "pragmatist",
    "architect",
    "testability-reviewer",
    "security-reviewer",
    "delivery-manager",
    "critic",
    "simplifier",
    "ops-reviewer",
)

# PB_FORBIDDEN_SDD_VOCABULARY is imported from _panel_doc_helpers (T12 extraction).

# Vocabulary swap map: SDD → PB (applied to the SDD section for structural parity).
VOCABULARY_SWAP_MAP = {
    "spec-driven-dev": "project-blueprint",
    "spec.md": "SCOPE.md",
    "design.md": "ARCHITECTURE.md",
    "tasks.md": "PLAN.md",
    "Specify": "Scope",
    "Design phase": "Architecture phase",
    "Tasks phase": "Plan phase",
    "validate_spec.py": "validate_blueprint.py",
    "specs/<feature-name>/": "blueprint/",
    "R6": "G6",  # Example identifiers in prompt Reason placeholders may differ
}

SDD_ONLY_EXCISION_ANCHOR = "**Task-tick discriminator (C2)."
PB_ONLY_EXCISION_ANCHOR = "**PLAN.md special handling — closed-feature scope detection.**"

SECTION_RE_APPROVAL_HEADING = "## Re-Approval After Edits"

# R4 (T13): the factual-edit-shortcut anti-pattern subsection. Placed OUTSIDE the
# step-3 block (in the Deferred Dispositions section, alongside ### Staleness cleanup).
FACTUAL_EDIT_SHORTCUT_HEADING = "### Common failure: the factual-edit shortcut"


# ============================================================================
# Helpers
# ============================================================================

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# _extract_section / _extract_step_3_block are imported from _panel_doc_helpers
# (T12 extraction) above, aliased to their original underscore names.


def _dedent_block(text: str) -> str:
    """Remove common leading whitespace from each line, for comparing
    interface-text constants against blocks that may be indented in the file."""
    lines = text.split("\n")
    return "\n".join(line.lstrip() for line in lines)


def _excise(text: str, anchor: str) -> str:
    """Remove the paragraph/block starting at `anchor` until the next blank line."""
    idx = text.find(anchor)
    if idx == -1:
        return text  # anchor not present in this file's section (legitimate)
    rest = text[idx:]
    end_match = re.search(r"\n\n", rest)
    end_idx = idx + (end_match.end() if end_match else len(rest))
    return text[:idx] + text[end_idx:]


def _apply_swap(text: str, mapping: dict[str, str]) -> str:
    # Apply replacements in length-descending order to avoid prefix collisions.
    for src in sorted(mapping.keys(), key=len, reverse=True):
        text = text.replace(src, mapping[src])
    return text


# ============================================================================
# Tests
# ============================================================================

@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_section_name_unchanged(path: Path, _name: str) -> None:
    """`## Re-Approval After Edits` heading is present in both files."""
    assert path.exists(), f"File missing: {path}"
    content = _read(path)
    assert SECTION_RE_APPROVAL_HEADING in content, (
        f"Section heading {SECTION_RE_APPROVAL_HEADING!r} not found in {path}"
    )


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_step_3_present_between_2_and_4(path: Path, _name: str) -> None:
    """Step 3 (Upstream panel re-review) appears between step 2 and step 4."""
    section = _extract_section(_read(path), SECTION_RE_APPROVAL_HEADING)
    pattern = re.compile(
        r"2\. \*\*Re-stamp silently.*?3\. \*\*Upstream panel re-review.*?4\. \*\*Cascade",
        re.DOTALL,
    )
    assert pattern.search(section), (
        f"Steps 2 → 3 (Upstream panel re-review) → 4 (Cascade) not in order in {path}"
    )


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_no_inlined_panelist_names_in_step_3(path: Path, _name: str) -> None:
    """The new step 3 block must reference panel-review.md, not inline panelist names."""
    section = _extract_section(_read(path), SECTION_RE_APPROVAL_HEADING)
    pattern = re.compile(
        r"(3\. \*\*Upstream panel re-review\.?\*\*.*?)(?=\n4\. \*\*)", re.DOTALL
    )
    m = pattern.search(section)
    if not m:
        pytest.fail(f"Step 3 block not found in {path}")
    step_3 = m.group(1)
    for name in FORBIDDEN_PANELIST_NAMES_INLINE:
        assert name not in step_3, (
            f"Inlined panelist name {name!r} found in step 3 of {path}; "
            f"references should use `panel-review.md § Panelists per phase`"
        )


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_c5_doctrine_new_sentence_present(path: Path, _name: str) -> None:
    content = _read(path)
    assert C5_DOCTRINE_REPLACEMENT_SENTENCE_FRAGMENT in content, (
        f"C5 doctrine replacement sentence fragment not found in {path}"
    )


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_c5_old_doctrine_sentence_absent(path: Path, _name: str) -> None:
    content = _read(path)
    assert C5_OLD_DOCTRINE_SENTENCE not in content, (
        f"Old C5 doctrine sentence still present in {path} — should have been replaced"
    )


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_interface_i1_template_present(path: Path, _name: str) -> None:
    """I1 lean-yes prompt template (with `<filename>` placeholder) appears verbatim
    (after dedenting both file content and constant to normalize indentation)."""
    content_dedented = _dedent_block(_read(path))
    constant_dedented = _dedent_block(INTERFACE_I1)
    assert constant_dedented in content_dedented, (
        f"INTERFACE_I1 template not present in {path} (after dedent normalization)"
    )


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_interface_i2_template_present(path: Path, _name: str) -> None:
    """I2 lean-no prompt template fragments appear (opening + question line)."""
    content = _read(path)
    assert INTERFACE_I2_OPENING in content
    assert INTERFACE_I2_QUESTION in content


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_interface_i3_present(path: Path, _name: str) -> None:
    content = _read(path)
    assert INTERFACE_I3 in content


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_interface_i3_no_path_present(path: Path, _name: str) -> None:
    content = _read(path)
    assert INTERFACE_I3_NO_PATH in content


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_interface_i4_both_variants_present(path: Path, _name: str) -> None:
    content = _read(path)
    assert INTERFACE_I4_AUTO_FIXES_FRAGMENT in content
    assert INTERFACE_I4_NO_AUTO_FIXES_FRAGMENT in content


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_interface_i5_a_b_fragments_present(path: Path, _name: str) -> None:
    content = _read(path)
    assert INTERFACE_I5_A_FRAGMENT in content
    assert INTERFACE_I5_B_FRAGMENT in content


def test_c2_discriminator_present_sdd() -> None:
    content = _read(SDD_PATH)
    assert C2_TASK_TICK_DISCRIMINATOR_FRAGMENT in content
    assert C2_DEBUG_NOTE in content


def test_c2_not_present_pb() -> None:
    """project-blueprint has no Phase 4 analog."""
    content = _read(PB_PATH)
    assert C2_TASK_TICK_DISCRIMINATOR_FRAGMENT not in content
    assert C2_DEBUG_NOTE not in content


def test_c4_regex_present_pb() -> None:
    content = _read(PB_PATH)
    assert C4_REGEX_PATTERN in content


def test_c4_regex_not_present_sdd() -> None:
    """C4 closed-feature scope detection is PLAN.md-specific; SDD file should not carry it."""
    content = _read(SDD_PATH)
    assert C4_REGEX_PATTERN not in content


def test_milestone_row_constant_matches_c4_regex() -> None:
    """(g) R2.AC3 / RISK-4: the production MILESTONE_FEATURE_ROW constant is
    character-identical to the doctrine-check literal C4_REGEX_PATTERN. Non-
    tautological — C4_REGEX_PATTERN stays an independent literal in this file."""
    from content_hash import MILESTONE_FEATURE_ROW

    assert MILESTONE_FEATURE_ROW == C4_REGEX_PATTERN


def test_plan_template_no_checked_literal() -> None:
    r"""(k.1) R1.AC2: plan-template.md carries no CHECKED milestone literal
    `^- \[[xX]\] F\d` — the Done docs use the `F<n>` placeholder, never a checked
    `- [x] F<digit>` that a document-wide pattern could pick up. (`[xX]` is a
    checked-only character class; `[ xX]` would false-positive on `- [ ]` rows.)"""
    content = _read(PLAN_TEMPLATE_PATH)
    assert re.search(r"^- \[[xX]\] F\d", content, re.MULTILINE) is None


def test_workflow_overview_old_permanence_sentence_absent() -> None:
    """(k.2) R4.AC2: the old permanence framing ("...historical commitment to the
    feature as it was authored at milestone-close time") is gone from
    workflow-overview.md after the Done/un-Done reconciliation — milestone ticks are
    now documented as hash-neutral and reversible."""
    content = _read(WORKFLOW_OVERVIEW_PATH)
    assert "as it was authored at milestone-close time" not in content


def test_c4_inline_summary_verbatim_present_pb() -> None:
    """C4 inline-summary immutability block verbatim in PB."""
    content = _read(PB_PATH)
    assert C4_INLINE_SUMMARY_VERBATIM_FRAGMENT_1 in content
    assert C4_INLINE_SUMMARY_VERBATIM_FRAGMENT_2 in content
    assert C4_INLINE_SUMMARY_VERBATIM_VALID_DISPOSITIONS in content
    assert C4_INLINE_SUMMARY_VERBATIM_REMEDIATION in content


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_ad3_contract_vocabulary_present(path: Path, _name: str) -> None:
    """All 16 AD3 contract-vocabulary tokens appear in the file."""
    content = _read(path)
    missing = [t for t in AD3_VOCABULARY_TOKENS if t not in content]
    assert not missing, (
        f"AD3 contract-vocabulary tokens missing from {path}: {missing}"
    )


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_recovery_path_canonical_phrasing(path: Path, _name: str) -> None:
    """R1 recovery path canonical phrasing appears in both files."""
    content = _read(path)
    assert RECOVERY_PHRASING in content, (
        f"Canonical recovery phrasing not present in {path}"
    )


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_ad7_provenance_format(path: Path, _name: str) -> None:
    """AD7 provenance tag format `upstream-panel [0-9a-f]{8}` is named verbatim."""
    content = _read(path)
    assert AD7_PROVENANCE_REGEX in content


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_i4_elision_manifest_present(path: Path, _name: str) -> None:
    """I4 elision rule mentions `Detailed re-stamp manifest:` literal."""
    content = _read(path)
    assert I4_ELISION_MANIFEST in content


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_ad1_ambiguous_source_note_present(path: Path, _name: str) -> None:
    """AD1 ambiguous-source note verbatim text appears in both files."""
    content = _read(path)
    assert AD1_AMBIGUOUS_SOURCE_NOTE in content


def test_vocabulary_swap_complete_pb() -> None:
    """No residual SDD-vocabulary tokens in PB file's step 3 block."""
    section = _extract_section(_read(PB_PATH), SECTION_RE_APPROVAL_HEADING)
    pattern = re.compile(
        r"(3\. \*\*Upstream panel re-review\.?\*\*.*?)(?=\n4\. \*\*)", re.DOTALL
    )
    m = pattern.search(section)
    assert m, "Step 3 block not found in PB file (parity check cannot proceed)"
    step_3 = m.group(1)
    found = [t for t in PB_FORBIDDEN_SDD_VOCABULARY if t in step_3]
    assert not found, (
        f"Residual SDD-vocabulary tokens found in PB step 3 block: {found}"
    )


def test_structural_parity() -> None:
    """The two `## Re-Approval After Edits` sections are structurally identical
    after asymmetric-content excision and vocabulary normalization."""
    sdd_section = _extract_section(_read(SDD_PATH), SECTION_RE_APPROVAL_HEADING)
    pb_section = _extract_section(_read(PB_PATH), SECTION_RE_APPROVAL_HEADING)

    if SDD_ONLY_EXCISION_ANCHOR not in _read(SDD_PATH):
        pytest.fail(
            f"SDD excision anchor missing: {SDD_ONLY_EXCISION_ANCHOR!r} — "
            f"structural parity check cannot proceed without it"
        )
    if PB_ONLY_EXCISION_ANCHOR not in pb_section:
        pytest.fail(
            f"PB excision anchor missing: {PB_ONLY_EXCISION_ANCHOR!r} — "
            f"structural parity check cannot proceed without it"
        )

    pb_section_excised = _excise(pb_section, PB_ONLY_EXCISION_ANCHOR)
    pb_section_excised = _excise(pb_section_excised, "**Post-panel immutability validation")
    sdd_section_excised = _excise(sdd_section, "**Phase 4 carve-out.**")

    sdd_normalized = _apply_swap(sdd_section_excised, VOCABULARY_SWAP_MAP)

    for step_marker in ("1. **Verify", "2. **Re-stamp", "3. **Upstream panel re-review",
                        "4. **Cascade"):
        assert step_marker in sdd_normalized, f"SDD missing step marker: {step_marker}"
        assert step_marker in pb_section_excised, f"PB missing step marker: {step_marker}"


# ============================================================================
# R4 (T13): factual-edit-shortcut anti-pattern subsection presence + placement.
# ============================================================================


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_factual_edit_shortcut_heading_present(path: Path, _name: str) -> None:
    """The `### Common failure: the factual-edit shortcut` subsection is present."""
    assert FACTUAL_EDIT_SHORTCUT_HEADING in _read(path), (
        f"R4 anti-pattern subsection heading not found in {path}"
    )


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_factual_edit_shortcut_outside_step_3_block(path: Path, _name: str) -> None:
    """The R4 subsection must be OUTSIDE the numbered step-3 block (RI-6 guard)."""
    section = _extract_section(_read(path), SECTION_RE_APPROVAL_HEADING)
    step_3 = _extract_step_3_block(section)
    assert FACTUAL_EDIT_SHORTCUT_HEADING not in step_3, (
        f"R4 anti-pattern subsection leaked INTO the step-3 block in {path}"
    )


# ============================================================================
# midstream-backport — Fix 3/6/7 doctrine anchors (I4/I5).
# Anchors are BARE contiguous substrings (no backtick falls between the words in
# the committed prose) so they survive section/file-name backticking.
# ============================================================================

NO_BATCH_EDIT_HEADING = "### Single-entry-point rule: no batch edits"
NO_BATCH_EDIT_ANCHOR = "enter at the single highest affected artifact"
UPSTREAM_BACKPORT_HEADING = "### Upstream backport — same-repo discovery"

# Generic cascade discipline — present in BOTH copies (mirrored, vocab-neutral):
BACKPORT_SHARED_ANCHORS = [NO_BATCH_EDIT_ANCHOR, UPSTREAM_BACKPORT_HEADING]

# SDD-only Phase-4 doctrine. Each must be PRESENT in the SDD copy; the
# distinctive phrases must also be ABSENT from the project-blueprint copy.
MECHANICAL_GAP_ANCHOR = "cannot propagate upward"
C2_EXTENSION_NARROWING_ANCHOR = "append-only"
C2_EXTENSION_SCOPE_PHRASE = "all changed lines fall entirely within"
C2_NOT_EXEMPT_STATUS_TRANSITION_PHRASE = "pending → backported"
C2_NOT_EXEMPT_OUT_OF_SECTION_PHRASE = "still trip the substantive path"
IMPLEMENTATION_DEVIATIONS_SECTION_TOKEN = "## Implementation Deviations"
# force-tdd-in-phase-4 (C8): the generalized ledger-append carve-out covers
# `## TDD Exceptions` too; these three SDD-only tokens pin the generalization —
# the new section, the generalized "single recognized ledger section" phrasing,
# and the preserved `Classification`…`minor` major-deviation guard (AD5).
TDD_EXCEPTIONS_SECTION_TOKEN = "## TDD Exceptions"
GENERALIZED_LEDGER_PHRASE = "recognized Phase-4 ledger section"
MINOR_GUARD_ANCHOR = "`Classification` is literally `minor`"

BACKPORT_SDD_ONLY_PRESENT = [
    MECHANICAL_GAP_ANCHOR,
    C2_EXTENSION_NARROWING_ANCHOR,
    C2_EXTENSION_SCOPE_PHRASE,
    C2_NOT_EXEMPT_STATUS_TRANSITION_PHRASE,
    C2_NOT_EXEMPT_OUT_OF_SECTION_PHRASE,
    IMPLEMENTATION_DEVIATIONS_SECTION_TOKEN,
    TDD_EXCEPTIONS_SECTION_TOKEN,
    GENERALIZED_LEDGER_PHRASE,
    MINOR_GUARD_ANCHOR,
]
# Distinctive SDD-only phrases that must never leak into the blueprint copy
# ("append-only" is omitted — too generic for a meaningful absence assertion).
BACKPORT_SDD_ONLY_ABSENT_FROM_PB = [
    MECHANICAL_GAP_ANCHOR,
    C2_EXTENSION_SCOPE_PHRASE,
    C2_NOT_EXEMPT_STATUS_TRANSITION_PHRASE,
    C2_NOT_EXEMPT_OUT_OF_SECTION_PHRASE,
    IMPLEMENTATION_DEVIATIONS_SECTION_TOKEN,
    TDD_EXCEPTIONS_SECTION_TOKEN,
    GENERALIZED_LEDGER_PHRASE,
    MINOR_GUARD_ANCHOR,
]
# The two new subsections are mirrored verbatim across copies; the SDD Upstream
# backport additionally carries an SDD-only "Mechanical gap" paragraph.
BACKPORT_MIRRORED_HEADINGS = [NO_BATCH_EDIT_HEADING, UPSTREAM_BACKPORT_HEADING]
SDD_ONLY_PARAGRAPH_MARKER = "**Mechanical gap"


@pytest.mark.parametrize("anchor", BACKPORT_SHARED_ANCHORS)
@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_backport_shared_anchor_present(path: Path, _name: str, anchor: str) -> None:
    """Generic cascade-discipline anchors appear in both hash-and-cascade copies."""
    assert anchor in _read(path), f"shared anchor {anchor!r} missing from {path}"


@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_no_batch_edit_rule_in_named_subsection(path: Path, _name: str) -> None:
    """The no-batch-edit anchor sits INSIDE its named subsection, not merely in the file."""
    body = _extract_subsection(_read(path), NO_BATCH_EDIT_HEADING)
    assert body is not None, f"{NO_BATCH_EDIT_HEADING!r} not found in {path}"
    assert NO_BATCH_EDIT_ANCHOR in body, (
        f"no-batch anchor present in {path} but NOT inside {NO_BATCH_EDIT_HEADING!r}"
    )


@pytest.mark.parametrize("anchor", BACKPORT_SDD_ONLY_PRESENT)
def test_backport_sdd_only_anchor_present(anchor: str) -> None:
    """SDD-only Phase-4 doctrine anchors are present in the SDD copy."""
    assert anchor in _read(SDD_PATH), f"SDD-only anchor {anchor!r} missing from SDD copy"


@pytest.mark.parametrize("anchor", BACKPORT_SDD_ONLY_ABSENT_FROM_PB)
def test_backport_sdd_only_anchor_absent_pb(anchor: str) -> None:
    """SDD-only Phase-4 doctrine must not leak into the project-blueprint copy."""
    assert anchor not in _read(PB_PATH), f"SDD-only anchor {anchor!r} leaked into PB copy"


@pytest.mark.parametrize("heading", BACKPORT_MIRRORED_HEADINGS)
def test_backport_subsection_body_parity(heading: str) -> None:
    """The mirrored subsection bodies must not drift between copies — they live in
    `## Deferred Dispositions`, OUTSIDE `test_structural_parity`'s compared region, so
    nothing else enforces their parity. The SDD Upstream-backport body additionally
    carries the SDD-only Mechanical-gap paragraph, stripped before comparing the lead."""
    sdd_body = _extract_subsection(_read(SDD_PATH), heading)
    pb_body = _extract_subsection(_read(PB_PATH), heading)
    assert sdd_body is not None, f"{heading!r} missing from SDD copy"
    assert pb_body is not None, f"{heading!r} missing from PB copy"
    sdd_shared = sdd_body.split(SDD_ONLY_PARAGRAPH_MARKER)[0]
    assert sdd_shared.strip() == pb_body.strip(), (
        f"mirrored subsection {heading!r} bodies diverge between the SDD and PB copies"
    )


# ============================================================================
# pending-review-churn — Close-Path Selection Guidance doctrine anchors (T6).
# Vocab-neutral substrings present VERBATIM in BOTH copies (DEF-02: each pinned
# constant is the runnable comparand for SC-7 shared prose).
# ============================================================================

CLOSE_PATH_GUIDANCE_HEADING = "### Close-Path Selection Guidance"
DECLINE_PENDING_NARROWED_SENTENCE_FRAGMENT = (
    "consciously waiving a genuinely-owed re-review"
)
DECLINE_PENDING_NOT_FOR_CHURN_FRAGMENT = "NEVER used to clear mechanical convergence churn"
R9_OBLIGATION_SURVIVAL_FRAGMENT = (
    "an open pending-review obligation survives every intervening re-stamp"
)
R9_UNSATISFIABLE_TOKEN = "UNSATISFIABLE-OBLIGATION:"
R9_RESTORE_ANCHOR_FLAG = "--restore-anchor"
R10_ORPHAN_TOKEN = "ORPHANED-TRAJECTORY-ROW:"
HASH_BASIS_V2_LINE = "- **Hash basis:** v2"
HASH_BASIS_MIGRATION_TOKEN = "HASH-BASIS-MIGRATION:"

# order-independent-anchor (T4 / R3): the M-guard doctrine added to the
# Close-Path Selection Guidance. Vocab-neutral substrings (identical in both
# copies); each pins that the new doctrine survived the paragraph rewrite.
REVERSED_ORDER_ANTIPATTERN_FRAGMENT = "review-then-approve"
RESTAMP_FIRST_FRAGMENT = "Re-stamp FIRST"
RESTORE_THEN_DECLINE_FRAGMENT = "restore-then-decline sequencing"
ORCHESTRATOR_AUTO_RESTORE_FRAGMENT = "Orchestrator auto-restore"
NOTHING_RESTORABLE_CROSSREF_FRAGMENT = "nothing restorable"   # R3 AC5 cross-ref (CRIT-M3)

CLOSE_PATH_SHARED_ANCHORS = [
    CLOSE_PATH_GUIDANCE_HEADING,
    DECLINE_PENDING_NARROWED_SENTENCE_FRAGMENT,
    DECLINE_PENDING_NOT_FOR_CHURN_FRAGMENT,
    R9_OBLIGATION_SURVIVAL_FRAGMENT,
    R9_UNSATISFIABLE_TOKEN,
    R9_RESTORE_ANCHOR_FLAG,
    R10_ORPHAN_TOKEN,
    HASH_BASIS_V2_LINE,
    HASH_BASIS_MIGRATION_TOKEN,
    REVERSED_ORDER_ANTIPATTERN_FRAGMENT,
    RESTAMP_FIRST_FRAGMENT,
    RESTORE_THEN_DECLINE_FRAGMENT,
    ORCHESTRATOR_AUTO_RESTORE_FRAGMENT,
    NOTHING_RESTORABLE_CROSSREF_FRAGMENT,
]


@pytest.mark.parametrize("anchor", CLOSE_PATH_SHARED_ANCHORS)
@pytest.mark.parametrize("path,_name", BOTH_FILES)
def test_close_path_guidance_anchor_present(path: Path, _name: str, anchor: str) -> None:
    """Each Close-Path Selection Guidance doctrine anchor is present VERBATIM in
    both hash-and-cascade copies (R5 parity / R6 narrowed decline / R9 / R10)."""
    assert anchor in _read(path), (
        f"Close-Path guidance anchor {anchor!r} missing from {path}"
    )


def test_close_path_guidance_subsection_body_parity() -> None:
    """The `### Close-Path Selection Guidance` body is mirrored across copies,
    differing ONLY in the swapped validator vocabulary (R5). Uses an extended swap
    map covering the validator command/path spellings used in this subsection."""
    extended = dict(VOCABULARY_SWAP_MAP)
    extended["specs/F<n>-<slug>/"] = "blueprint/"
    extended["specs/"] = "blueprint/"
    sdd_body = _extract_subsection(_read(SDD_PATH), CLOSE_PATH_GUIDANCE_HEADING)
    pb_body = _extract_subsection(_read(PB_PATH), CLOSE_PATH_GUIDANCE_HEADING)
    assert sdd_body is not None and pb_body is not None
    assert _apply_swap(sdd_body, extended).strip() == pb_body.strip(), (
        "Close-Path Selection Guidance bodies diverge beyond the vocabulary swap"
    )


# ============================================================================
# T8 (context-window-inflow-reduction): R3 consistency/cascade READ delegation
# to `consistency-reader`. Design C5/I2; R3 AC1–AC4. phase-design.md /
# phase-tasks.md are SDD-only; the hash-and-cascade.md step-4 delegation mirrors
# across both copies.
# ============================================================================

_PHASE_DESIGN = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/phase-design.md"
_PHASE_TASKS = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/phase-tasks.md"
_PB_PHASE_ARCH = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/phase-architecture.md"
_PB_PHASE_PLAN = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/phase-plan.md"

CONSISTENCY_READER = "telescoping-sdd:consistency-reader"
DISCREPANCY_SHAPE = "{checklist_item, file, quoted_span_or_line, description}"
DEGRADED_FALLBACK = "in-main full-chain re-read"


def test_consistency_reader_delegation_present_phase_design() -> None:
    section = _extract_section(_read(_PHASE_DESIGN), "## Spec-Design Consistency Check")
    assert CONSISTENCY_READER in section
    assert DISCREPANCY_SHAPE in section
    assert '"Spec-Design Consistency Check"' in section


def test_consistency_reader_delegation_present_phase_tasks() -> None:
    section = _extract_section(_read(_PHASE_TASKS), "## Spec-Design-Tasks Consistency Check")
    assert CONSISTENCY_READER in section
    assert DISCREPANCY_SHAPE in section
    assert '"Spec-Design-Tasks Consistency Check"' in section


def test_cascade_delegation_present_both_copies() -> None:
    for path in (SDD_PATH, PB_PATH):
        section = _extract_section(_read(path), SECTION_RE_APPROVAL_HEADING)
        assert CONSISTENCY_READER in section, f"{path}: cascade step-4 delegation absent"
        assert DISCREPANCY_SHAPE in section, path


def test_degraded_reread_fallback_disclosed() -> None:
    """R3 AC1: the too-coarse-to-locate discrepancy routes to a DISCLOSED in-main
    full-chain re-read — in the SDD phase files and both cascade copies."""
    for path in (_PHASE_DESIGN, _PHASE_TASKS, SDD_PATH, PB_PATH):
        assert DEGRADED_FALLBACK in _read(path), f"{path}: degraded re-read not disclosed"


def test_fix_routing_unchanged() -> None:
    """R3 AC4: § 'Revise the downstream' keeps trivial-direct / substantial-
    analyst-delegated routing unchanged (the read is delegated; the routing is not)."""
    for path in (SDD_PATH, PB_PATH):
        content = _read(path)
        assert "**Trivial**" in content, path
        assert "**Substantial**" in content, path
        assert "delegates the draft to the phase's analyst agent" in content, path


def test_hash_and_cascade_r3_asymmetries_allowlisted() -> None:
    """R5: the cascade R3 delegation is present-and-consistent in BOTH
    hash-and-cascade copies; the phase-file consistency delegation is SDD-only
    (the blueprint phase-architecture/phase-plan consistency sections are not
    part of this change per design C5)."""
    for path in (SDD_PATH, PB_PATH):
        assert CONSISTENCY_READER in _read(path)
    # SDD-only: the consistency-reader delegation is added to the SDD phase files,
    # NOT to the blueprint phase-architecture/phase-plan consistency sections.
    assert CONSISTENCY_READER in _read(_PHASE_DESIGN)
    assert CONSISTENCY_READER in _read(_PHASE_TASKS)
    assert CONSISTENCY_READER not in _read(_PB_PHASE_ARCH), (
        "consistency-reader delegation must stay out of the blueprint phase files "
        "(design C5 scopes the phase-file read-delegation to SDD only)"
    )
    assert CONSISTENCY_READER not in _read(_PB_PHASE_PLAN)
