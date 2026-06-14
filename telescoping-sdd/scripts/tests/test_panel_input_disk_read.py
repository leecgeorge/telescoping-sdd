"""Regression guard for the panel-input disk-read mandate (v2.12.0).

Pins, in BOTH `panel-review.md` copies, the "## The Loop" step-1 amendment and the
"## Minimum to run the NORMAL loop" digest dispatch-step amendment that require the
synthesizer to pass each panelist the artifact's on-disk PATH and have them read it
from disk in full — instead of pasting/summarizing the artifact body inline. This
mirrors the v2.0.1 write-inversion guard on the panel-INPUT side.

Frozen constants and section-scoped extraction are copied verbatim from the
approved design (specs/panel-input-disk-read-mandate/02_design.md §§ Data Models,
Interfaces I3). Self-contained per AD3 — does NOT import or extend
`_panel_doc_helpers.py`.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import pytest

# Repo root is parents[3] from this file:
#   telescoping-sdd/scripts/tests/test_panel_input_disk_read.py
#   parents[0]=tests/ [1]=scripts/ [2]=telescoping-sdd/ [3]=<repo-root>/
_REPO_ROOT = Path(__file__).resolve().parents[3]
SDD = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/panel-review.md"
PB = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/panel-review.md"
BOTH = [pytest.param(SDD, id="sdd"), pytest.param(PB, id="pb")]

# --- Frozen constants (design § Data Models) -------------------------------
MANDATE_PATH_PHRASE = "on-disk file path of the artifact under review"
IN_FULL_PHRASE = "read those file(s) from disk in full"
PROHIBITION_PHRASE = "do not paste the body of the content under review"
ORIGINAL_PHRASE = (
    "Pass each panelist the current artifact and any upstream approved "
    "artifacts as context"
)
FORBIDDEN_INLINE_CONTENTS = "include the contents of the artifact's"
SEALED_SUPPRESSION_PHRASE = "Do not re-raise items in the Sealed dispositions list"
DEFERRED_SUPPRESSION_PHRASE = "why this is not a duplicate of"


# --- Section-scoped extraction helpers (design I3) -------------------------
class SectionMissingError(AssertionError):
    def __init__(self, path: Path, target: str) -> None:
        super().__init__(f"{path}: expected section or block not found: {target!r}")


def _extract_section(content: str, heading: str, path: Path) -> str:
    """Return the body of a ## section from heading until the next ## heading."""
    pattern = re.compile(rf"({re.escape(heading)}\n.*?)(?=\n## |\Z)", re.DOTALL)
    m = pattern.search(content)
    if not m:
        raise SectionMissingError(path, heading)
    return m.group(1)


def _extract_loop_step1(content: str, path: Path) -> str:
    """Extract step 1 of '## The Loop', section-scoped (two-level)."""
    section = _extract_section(content, "## The Loop", path)
    pattern = re.compile(
        r"(1\. \*\*Dispatch all three panelists in a single message\.\*\*.*?)"
        r"(?=\n2\. \*\*Synthesize in-thread\*\*)",
        re.DOTALL,
    )
    m = pattern.search(section)
    if not m:
        raise SectionMissingError(path, "step 1 of ## The Loop")
    return m.group(1)


def _extract_digest_step1(content: str, path: Path) -> str:
    """Extract step 1 of '## Minimum to run the NORMAL loop', section-scoped."""
    section = _extract_section(content, "## Minimum to run the NORMAL loop", path)
    pattern = re.compile(r"(1\. Pick the three panelists.*?)(?=\n2\. Ask each)", re.DOTALL)
    m = pattern.search(section)
    if not m:
        raise SectionMissingError(path, "step 1 of ## Minimum to run the NORMAL loop")
    return m.group(1)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- T1–T11 (design § Testing Strategy) ------------------------------------
@pytest.mark.parametrize("path", BOTH)
def test_step1_mandate_path_phrase_present(path: Path) -> None:
    block = _extract_loop_step1(_read(path), path)
    assert MANDATE_PATH_PHRASE in block, (
        f"Disk-read mandate phrase {MANDATE_PATH_PHRASE!r} missing from step 1 of "
        f"'## The Loop' in {path}; the path-passing mandate is absent"
    )


@pytest.mark.parametrize("path", BOTH)
def test_step1_in_full_phrase_present(path: Path) -> None:
    block = _extract_loop_step1(_read(path), path)
    assert IN_FULL_PHRASE in block, (
        f"'In full' qualifier {IN_FULL_PHRASE!r} missing from step 1 of "
        f"'## The Loop' in {path}; panelists may read only a partial excerpt"
    )


@pytest.mark.parametrize("path", BOTH)
def test_step1_prohibition_phrase_present(path: Path) -> None:
    block = _extract_loop_step1(_read(path), path)
    assert PROHIBITION_PHRASE in block, (
        f"Inline-paste prohibition {PROHIBITION_PHRASE!r} missing from step 1 of "
        f"'## The Loop' in {path}; synthesizers may rationalize pasting artifact body"
    )


@pytest.mark.parametrize("path", BOTH)
def test_step1_original_phrase_absent(path: Path) -> None:
    block = _extract_loop_step1(_read(path), path)
    assert ORIGINAL_PHRASE not in block, (
        f"Original phrase {ORIGINAL_PHRASE!r} still present in step 1 of "
        f"'## The Loop' in {path}; the disk-read amendment may be missing or reverted"
    )


def test_step1_byte_identical_across_copies() -> None:
    pb_block = _extract_loop_step1(_read(PB), PB)
    sdd_block = _extract_loop_step1(_read(SDD), SDD)
    if pb_block != sdd_block:
        diff = "".join(
            difflib.unified_diff(
                pb_block.splitlines(keepends=True),
                sdd_block.splitlines(keepends=True),
                fromfile=str(PB),
                tofile=str(SDD),
            )
        )
        pytest.fail(
            f"Step 1 of '## The Loop' is not byte-identical across both "
            f"panel-review.md copies; amendment has introduced an asymmetry:\n{diff}"
        )


@pytest.mark.parametrize("path", BOTH)
def test_digest_step_mandate_path_phrase_present(path: Path) -> None:
    block = _extract_digest_step1(_read(path), path)
    assert MANDATE_PATH_PHRASE in block, (
        f"Disk-read mandate phrase {MANDATE_PATH_PHRASE!r} absent from the digest "
        f"dispatch step in {path}; the most-read surface does not name the mandate"
    )


@pytest.mark.parametrize("path", BOTH)
def test_digest_step_in_full_phrase_present(path: Path) -> None:
    block = _extract_digest_step1(_read(path), path)
    assert IN_FULL_PHRASE in block, (
        f"'In full' qualifier {IN_FULL_PHRASE!r} absent from the digest dispatch "
        f"step in {path}"
    )


def test_digest_step_byte_identical_across_copies() -> None:
    pb_block = _extract_digest_step1(_read(PB), PB)
    sdd_block = _extract_digest_step1(_read(SDD), SDD)
    if pb_block != sdd_block:
        diff = "".join(
            difflib.unified_diff(
                pb_block.splitlines(keepends=True),
                sdd_block.splitlines(keepends=True),
                fromfile=str(PB),
                tofile=str(SDD),
            )
        )
        pytest.fail(
            f"Digest dispatch step is not byte-identical across both "
            f"panel-review.md copies; amendment has introduced an asymmetry:\n{diff}"
        )


@pytest.mark.parametrize("path", BOTH)
def test_step1_no_inline_sealed_contents(path: Path) -> None:
    # Secondary / defense-in-depth (design T9): pins absence of the old
    # inline-include pattern. NOT the behavioral guarantee.
    block = _extract_loop_step1(_read(path), path)
    assert FORBIDDEN_INLINE_CONTENTS not in block, (
        f"Forbidden inline-contents phrase {FORBIDDEN_INLINE_CONTENTS!r} found in "
        f"step 1 of '## The Loop' in {path}; the old inline-include pattern for "
        f"the artifact's Sealed/Deferred list contents may have been reintroduced"
    )


@pytest.mark.parametrize("path", BOTH)
def test_step1_sealed_suppression_instruction_present(path: Path) -> None:
    # R4 guard: closes the symmetric-deletion gap parity (T5) cannot catch.
    block = _extract_loop_step1(_read(path), path)
    assert SEALED_SUPPRESSION_PHRASE in block, (
        f"Sealed re-raise suppression instruction {SEALED_SUPPRESSION_PHRASE!r} "
        f"missing from step 1 of '## The Loop' in {path}; R4 behavior (panelists "
        f"must not re-raise sealed items) was silently dropped"
    )


@pytest.mark.parametrize("path", BOTH)
def test_step1_deferred_suppression_instruction_present(path: Path) -> None:
    block = _extract_loop_step1(_read(path), path)
    assert DEFERRED_SUPPRESSION_PHRASE in block, (
        f"Deferred re-raise suppression instruction {DEFERRED_SUPPRESSION_PHRASE!r} "
        f"missing from step 1 of '## The Loop' in {path}; R4 behavior (Deferred-item "
        f"re-raise suppression) was silently dropped"
    )


# --- R7: Phase-4 completion re-stamp guard (T12/T13) -----------------------
SDD_SKILL = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/SKILL.md"
PB_SKILL = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/SKILL.md"
R7_TASKTICK_PHRASE = "--approve tasks --task-tick"


def _extract_finalcheck_restamp(content: str, path: Path) -> str:
    """Extract the SKILL.md Phase-4 Final-Check completion re-stamp bullet.

    The bullet begins `- **Re-stamp \`tasks.md\` once` and is the LAST item in
    the Final-Check list — it has no trailing `- **` bullet to anchor on (the next
    column-0 markdown is the `**In-flight …**` paragraph, then `## Entering …`).
    The bullet also carries indented `  - **…` sub-bullets that the capture must
    span (R7_TASKTICK_PHRASE lives inside the first sub-bullet). Hence the
    fallback terminator `(?=\n## |\n\*\*In-flight|\Z)`.
    """
    m = re.search(
        r"(- \*\*Re-stamp `tasks\.md` once.*?)(?=\n## |\n\*\*In-flight|\Z)",
        content,
        re.DOTALL,
    )
    if not m:
        raise SectionMissingError(path, "Phase-4 Final-Check re-stamp bullet")
    return m.group(1)


def test_skill_phase4_finalcheck_uses_tasktick() -> None:
    block = _extract_finalcheck_restamp(_read(SDD_SKILL), SDD_SKILL)
    assert R7_TASKTICK_PHRASE in block, (
        f"Phase-4 Final-Check completion re-stamp in {SDD_SKILL} does not name "
        f"{R7_TASKTICK_PHRASE!r}; the pure-tick branch may have reverted to plain "
        f"`--approve tasks`, reopening the spurious-pending-review-marker churn (R7)"
    )


def test_blueprint_skill_has_no_tasktick() -> None:
    # SDD-only asymmetry: the blueprint tier has a Phase 4 (Business Brief) but
    # no tasks.md / task-tick cadence. Pin the absence of the full command phrase
    # ONLY — NOT "Phase 4" (the blueprint has it) and NOT a bare "task-tick"
    # (the blueprint prose says "no Phase-4 task-tick carve-out").
    src = _read(PB_SKILL)
    assert R7_TASKTICK_PHRASE not in src, (
        f"{PB_SKILL} contains {R7_TASKTICK_PHRASE!r}; the SDD-only Phase-4 "
        f"completion cadence must not leak into the project-blueprint tier"
    )
