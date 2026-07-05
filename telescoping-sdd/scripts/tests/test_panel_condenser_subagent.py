"""Reference-prose + parity guard for the panel-condenser loop rewrite (T5).

Pins, in BOTH `panel-review.md` copies, the context-window-inflow-reduction
Milestone-A loop rewrite: the findings-to-disk panelist contract, the
`panel-condenser` dispatch + compact-table return, the per-anchor AD7
reconciliation + fallback, the DM2→`### Latest pass detail` projection formula,
the `## Concern tagging` proposal/confirm edit, the new `## Pass summary surface`
section (incl. the LOW-5 `[upstream]` scope-mismatch surfacing), and the
0-new-HIGH-but-non-empty-manifest reconciliation boundary. Also pins the R4
invariants (disposition vocabulary / Self-Check / Autonomy Boundary /
`### Latest pass detail` layout) present-unchanged, and byte-identity of the new
shared blocks across the two copies (asymmetries allow-listed).

Mirrors `test_panel_input_disk_read.py` / `test_write_inversion.py` (self-
contained; no shared-helper import). See specs/context-window-inflow-reduction/
{01_spec.md,02_design.md,03_tasks.md} (design C3, C4, AD6, AD7, AD10, AD11,
AD12, DM2, Q6; R1, R2, R4, R5).
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
SDD = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/panel-review.md"
PB = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/panel-review.md"
BOTH = [pytest.param(SDD, id="sdd"), pytest.param(PB, id="pb")]


# --- Frozen phrases (couple this guard to the T5 prose) --------------------
FINDINGS_TO_DISK_PHRASE = "return only a manifest"
FINDINGS_PATH_PHRASE = ".sdd/panel-findings/<findings_scope>/"
NO_INLINE_BODIES_PHRASE = "no prose bodies and no MED/LOW detail inline"
CLEAR_REENTRY_PHRASE = "clear the prior pass's findings within *this run's*"
CONDENSER_DISPATCH_PHRASE = "telescoping-sdd:panel-condenser"
COMPACT_TABLE_COLUMNS = (
    "ROW | ANCHOR-REFS | SEVERITY | SOURCE | SCOPE | CONCERN "
    "| DISPOSITION-PROPOSAL | FIX-INSTRUCTION"
)
RECONCILE_PHRASE = "Reconcile the returned table by identity, per anchor"
FALLBACK_PHRASE = "Fall back on failure"
GRAMMAR_HELPER_PHRASE = "compact_table.validate_compact_table"
PROJECTION_FORMULA = (
    '`Severity ← SEVERITY`; `Source ← SOURCE`; '
    '`Concern ← SCOPE + " " + CONCERN` for Phase 2/3 HIGH rows '
    '(else `Concern ← CONCERN`)'
)
CONCERN_PROPOSE_CONFIRM_PHRASE = "Condenser proposes, you confirm"
UPSTREAM_CONFIRM_PHRASE = "confirm any `[upstream]` tag semantically"
PASS_SUMMARY_HEADING = "## Pass summary surface"
SCOPE_MISMATCH_PHRASE = "scope mismatch"
ZERO_HIGH_BOUNDARY_PHRASE = "do not short-circuit on the trajectory HIGH count"

# R4 invariants (must remain present and unchanged).
DISPOSITION_VOCAB = ["Addressed", "Deferred", "Sealed", "Accepted as risk",
                     "User input needed", "Halt and re-scope"]
SELF_CHECK_HEADING = "## Synthesizer Self-Check"
AUTONOMY_HEADING = "## Autonomy Boundary"
LATEST_DETAIL_HEADER = "| Severity | Source | Concern | Disposition | Notes |"


# --- Section-scoped extraction ---------------------------------------------
class SectionMissingError(AssertionError):
    def __init__(self, path: Path, target: str) -> None:
        super().__init__(f"{path}: expected section or block not found: {target!r}")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_section(content: str, heading: str, path: Path) -> str:
    pattern = re.compile(rf"({re.escape(heading)}\n.*?)(?=\n## |\Z)", re.DOTALL)
    m = pattern.search(content)
    if not m:
        raise SectionMissingError(path, heading)
    return m.group(1)


def _extract_loop_step2(content: str, path: Path) -> str:
    """Step 2 of '## The Loop' — condenser dispatch + reconcile + projection."""
    section = _extract_section(content, "## The Loop", path)
    pattern = re.compile(
        r"(2\. \*\*Synthesize in-thread\*\*.*?)"
        r"(?=\n3\. For each remaining concern)",
        re.DOTALL,
    )
    m = pattern.search(section)
    if not m:
        raise SectionMissingError(path, "step 2 of ## The Loop")
    return m.group(1)


# --- Presence: findings-to-disk contract -----------------------------------
@pytest.mark.parametrize("path", BOTH)
def test_findings_to_disk_contract_present_both_copies(path: Path) -> None:
    section = _extract_section(_read(path), "## The Loop", path)
    assert FINDINGS_TO_DISK_PHRASE in section, path
    assert FINDINGS_PATH_PHRASE in section, path
    assert NO_INLINE_BODIES_PHRASE in section, path


@pytest.mark.parametrize("path", BOTH)
def test_prior_pass_findings_cleared_at_reentry(path: Path) -> None:
    section = _extract_section(_read(path), "## The Loop", path)
    assert CLEAR_REENTRY_PHRASE in section, path


@pytest.mark.parametrize("path", BOTH)
def test_condenser_dispatch_and_compact_table_return_present(path: Path) -> None:
    block = _extract_loop_step2(_read(path), path)
    assert CONDENSER_DISPATCH_PHRASE in block, path
    assert COMPACT_TABLE_COLUMNS in block, path


@pytest.mark.parametrize("path", BOTH)
def test_per_anchor_reconciliation_and_fallback_present(path: Path) -> None:
    block = _extract_loop_step2(_read(path), path)
    assert RECONCILE_PHRASE in block, path
    assert FALLBACK_PHRASE in block, path
    assert GRAMMAR_HELPER_PHRASE in block, path


@pytest.mark.parametrize("path", BOTH)
def test_dm2_projection_formula_present_verbatim(path: Path) -> None:
    block = _extract_loop_step2(_read(path), path)
    assert PROJECTION_FORMULA in block, (
        f"{path}: DM2 projection formula not present verbatim in Loop step 2"
    )


@pytest.mark.parametrize("path", BOTH)
def test_concern_tagging_proposal_confirm_edit_present(path: Path) -> None:
    section = _extract_section(_read(path), "## Concern tagging (Phase 2 and 3)", path)
    assert CONCERN_PROPOSE_CONFIRM_PHRASE in section, path
    assert UPSTREAM_CONFIRM_PHRASE in section, path


@pytest.mark.parametrize("path", BOTH)
def test_pass_summary_surface_present(path: Path) -> None:
    section = _extract_section(_read(path), PASS_SUMMARY_HEADING, path)
    assert section.strip(), f"{path}: '{PASS_SUMMARY_HEADING}' empty/absent"


@pytest.mark.parametrize("path", BOTH)
def test_upstream_hint_vs_proposed_mismatch_surfaced(path: Path) -> None:
    """LOW-5: a distinct assertion that the pass-summary block surfaces a
    scope_hint-vs-proposed-SCOPE mismatch (not folded into the general
    pass-summary presence check)."""
    section = _extract_section(_read(path), PASS_SUMMARY_HEADING, path)
    assert SCOPE_MISMATCH_PHRASE in section, path
    assert "scope_hint" in section, path


@pytest.mark.parametrize("path", BOTH)
def test_zero_new_high_nonempty_manifest_reconcile_covered(path: Path) -> None:
    block = _extract_loop_step2(_read(path), path)
    assert ZERO_HIGH_BOUNDARY_PHRASE in block, path


@pytest.mark.parametrize("path", BOTH)
def test_panel_review_r4_invariants_unchanged(path: Path) -> None:
    content = _read(path)
    for label in DISPOSITION_VOCAB:
        assert label in content, f"{path}: disposition vocabulary '{label}' missing"
    assert SELF_CHECK_HEADING in content, path
    assert AUTONOMY_HEADING in content, path
    assert LATEST_DETAIL_HEADER in content, path


# --- Parity: new shared blocks byte-identical across copies -----------------
def _assert_byte_identical(block_pb: str, block_sdd: str, label: str) -> None:
    if block_pb != block_sdd:
        diff = "".join(
            difflib.unified_diff(
                block_pb.splitlines(keepends=True),
                block_sdd.splitlines(keepends=True),
                fromfile=str(PB),
                tofile=str(SDD),
            )
        )
        pytest.fail(f"{label} not byte-identical across copies:\n{diff}")


def test_shared_loop_blocks_byte_identical_across_copies() -> None:
    """R5: the new shared blocks (Loop step 2, Pass summary surface) are
    byte-identical across both copies; documented asymmetries live elsewhere."""
    _assert_byte_identical(
        _extract_loop_step2(_read(PB), PB),
        _extract_loop_step2(_read(SDD), SDD),
        "Loop step 2 (condenser dispatch + reconcile + projection)",
    )
    _assert_byte_identical(
        _extract_section(_read(PB), PASS_SUMMARY_HEADING, PB),
        _extract_section(_read(SDD), PASS_SUMMARY_HEADING, SDD),
        "## Pass summary surface",
    )
