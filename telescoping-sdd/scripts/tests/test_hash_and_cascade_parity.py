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

# Locate the repo root so the test runs from any cwd.
_REPO_ROOT = Path(__file__).resolve().parents[3]
SDD_PATH = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/hash-and-cascade.md"
PB_PATH = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/hash-and-cascade.md"

BOTH_FILES = [
    pytest.param(SDD_PATH, "sdd", id="sdd"),
    pytest.param(PB_PATH, "pb", id="pb"),
]

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

C4_REGEX_PATTERN = r"^- \[xX\] F\d+\b"

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

PB_FORBIDDEN_SDD_VOCABULARY = (
    "spec.md",
    "design.md",
    "tasks.md",
    "Specify",
    "Design phase",
    "Tasks phase",
)

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


# ============================================================================
# Helpers
# ============================================================================

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_section(content: str, heading: str) -> str:
    """Return the section starting at `heading` until the next `## ` heading."""
    pattern = re.compile(
        rf"({re.escape(heading)}\n.*?)(?=\n## |\Z)", re.DOTALL
    )
    m = pattern.search(content)
    if not m:
        pytest.fail(f"Section heading not found: {heading!r}")
    return m.group(1)


def _extract_step_3_block(section: str) -> str:
    """Return the step-3 (Upstream panel re-review) block content."""
    pattern = re.compile(
        r"(3\. \*\*Upstream panel re-review\.?\*\*.*?)(?=\n4\. \*\*)", re.DOTALL
    )
    m = pattern.search(section)
    if not m:
        pytest.fail("Step 3 (Upstream panel re-review) block not found")
    return m.group(1)


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
