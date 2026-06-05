#!/usr/bin/env python3
"""Validate and approve spec-driven development artifacts.

Checks that spec.md, design.md, and tasks.md have required sections
and follow the expected structure. Can also approve documents for
phase transitions using content hashes to detect post-approval edits.

Supports Python and Java projects via --language flag, plus an
architecture-neutral "generic" profile for everything else (infra,
static sites, Claude-skill authoring, etc.). If --language is omitted,
auto-detects by looking for pom.xml/build.gradle (Java) or
pyproject.toml/setup.py (Python) in the project root; when no recognized
language marker is found it resolves to "generic" rather than assuming
Python. The "generic" profile disables the two language-specific advisory
checks (type annotations, test-function names) so they do not misfire on
non-code or non-Python/Java deliverables.

Usage:
    python validate_spec.py <spec-directory>
    python validate_spec.py specs/F1-checkout-flow/ --phase spec
    python validate_spec.py specs/F1-checkout-flow/ --approve spec
    python validate_spec.py specs/F1-checkout-flow/ --language java
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Locate shared helpers at telescoping-sdd/scripts/ — sibling of telescoping-sdd/skills/.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.append(str(_SHARED_SCRIPTS))

from blueprint_common import (  # noqa: E402
    APPROVAL_HASH_LINE_STRICT,
    REAPPROVAL_REMINDER,
    MarkerCorruptError,
    Severity,
    ValidationResult,
    changed_since_stamp,
    clear_pending_entries_for_prefix,
    compute_content_hash,
    content_for_hashing,
    mixed_state_warning,
    now_iso_utc,
    read_stored_hash,
    reconcile_to_result,
    resolve_artifact,
    run_cli_failclosed,
    stamped_at_pass_from_content,
    trim_trajectory_table,
    upsert_pending_entry,
    verify_content_hash,
)
from cfc_parser import (  # noqa: E402
    CFC_HEADER_PATTERN as CFC_HEADER_RE,
    CFC_TAG_PATTERN as CFC_TAG_RE,
    FEATURE_ID_WORD_PATTERN as FEATURE_ID_WORD_RE,
    extract_cfc_section,
    extract_cfc_tags,
    find_misplaced_cfc_tags,
    parse_cfc_entries,
)
from arch_config import (  # noqa: E402
    find_project_root as arch_find_project_root,
    resolve_language,
    write_arch_config,
)
from spec_dirname import (  # noqa: E402
    SLUGIFY_CLI_HINT,
    classify_dirname,
    display_safe,
    is_derived_spec,
    parse_bound,
    parse_feature_number,
)
from project_link import (  # noqa: E402
    DERIVED_FROM_LINE_RE,
    MASTER_CONTRACT_HASH_LINE_RE,
    MASTER_HASH_UNBOUND,
    MASTER_HASH_VALUE_RE,
    parse_derived_dirname,
    parse_qualified_id,
)
from ucr import parse_ucr_stanza  # noqa: E402


# ---------------------------------------------------------------------------
# Language profiles — add new languages here
# ---------------------------------------------------------------------------

LANGUAGE_PROFILES: dict[str, dict] = {
    "python": {
        "label": "Python",
        "project_markers": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"],
        "dir_markers": [],  # no directory-based detection needed
        "type_pattern": re.compile(r":\s*(str|int|float|bool|list|dict|Optional)"),
        "test_name_pattern": re.compile(r"`test_\w+\(\)`"),
        "test_framework": "pytest",
        "test_command": "pytest tests/ -v",
        "source_layout": "src/",
        "test_layout": "tests/",
    },
    "java": {
        "label": "Java",
        "project_markers": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "dir_markers": ["src/main/java"],
        "type_pattern": re.compile(
            r"\b(String|int|Integer|long|Long|boolean|Boolean|double|Double|float|Float"
            r"|List|Map|Set|Optional|void|byte|short|char)\b"
        ),
        "test_name_pattern": re.compile(
            r"`test[a-zA-Z0-9]+\(\)`|`[a-zA-Z0-9]+Test\(\)`"
        ),
        "test_framework": "JUnit 5",
        "test_command": "mvn test / gradle test",
        "source_layout": "src/main/java/",
        "test_layout": "src/test/java/",
    },
    # Architecture-neutral fallback for stacks that are neither Python nor Java
    # (infrastructure, static sites, Claude-skill authoring, TypeScript before a
    # dedicated profile exists, etc.). It carries NO marker lists, so it is never
    # auto-detected — it is only ever selected as the explicit fallback when no
    # recognized language marker is found, or via `--language generic`. Its
    # `type_pattern`/`test_name_pattern` are None, which the two advisory checks
    # treat as "skip this check" rather than misfiring a Python/Java regex against
    # a stack that has neither type annotations nor xUnit-style test names.
    "generic": {
        "label": "generic (architecture-neutral)",
        "project_markers": [],
        "dir_markers": [],
        "type_pattern": None,
        "test_name_pattern": None,
        "test_framework": None,
        "test_command": None,
        "source_layout": None,
        "test_layout": None,
    },
}

# The language key used when auto-detection finds no recognized marker. A
# neutral profile, NOT "python" — defaulting an unknown stack to Python stamps a
# wrong "Language: python" banner and fires two spurious advisory warnings.
NEUTRAL_LANGUAGE = "generic"


# ---------------------------------------------------------------------------
# Required sections per phase
# ---------------------------------------------------------------------------

SPEC_REQUIRED_SECTIONS = [
    "Objective",
    "Requirements",
    "Acceptance Criteria",
    "Project Structure",
    "Boundaries",
    "Success Criteria",
    "Panel Review",
]

DESIGN_REQUIRED_SECTIONS = [
    "Goals and Non-Goals",
    "Architecture Decisions",
    "Component Design",
    "Data Models",
    "Interfaces",
    "Error Handling",
    "Testing Strategy",
    "File Structure",
    "Dependencies",
    "Integration Points",
    "Risks",
    "Implementation Sequence",
    "Panel Review",
]

# Regex to match task entries like "### T1:", "### - [ ] T1:", or "### - [x] T1:"
TASK_ENTRY_PATTERN = re.compile(r"^###\s+(?:- \[[ x]\] )?T\d+:", re.MULTILINE)

# Regex to match GIVEN/WHEN/THEN patterns
GWT_PATTERN = re.compile(
    r"GIVEN\s+.+\n\s*(?:[-*]\s+)?WHEN\s+.+\n\s*(?:[-*]\s+)?THEN\s+.+", re.MULTILINE
)

# Regex to match unchecked open questions (e.g., "- [ ] Q1: ...")
UNCHECKED_QUESTION_PATTERN = re.compile(r"^-\s*\[ \]\s*Q\d+:", re.MULTILINE)

# Regex to match [TBD] markers, including variants like [TBD — needs input]
TBD_PATTERN = re.compile(r"\[TBD[^\]]*\]", re.IGNORECASE)

# Regex to match general unresolved markers
UNRESOLVED_MARKERS = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b|\?\?\?", re.IGNORECASE)

# Regex to extract requirement IDs (R1, R2, etc.)
REQUIREMENT_ID_PATTERN = re.compile(r"^###\s+R(\d+):", re.MULTILINE)

# Regex to extract requirement references from task Requirement lines (supports comma-separated like "R1, R3")
TASK_REQUIREMENT_REF_PATTERN = re.compile(r"\*\*Requirement:\*\*\s*((?:R\d+(?:,\s*)?)+)")

# Regex to match panel concerns still awaiting user input (disposition column
# in `### Latest pass detail`, or in the legacy single Panel Review table).
# A concern in this disposition must be resolved before validation passes.
PANEL_UNRESOLVED_DISPOSITION = re.compile(
    r"\|\s*User input needed\s*\|", re.IGNORECASE
)

# Regex to match a valid final disposition in `### Latest pass detail` (new
# format) or the legacy single `## Panel Review` table. The trailing `—` form
# is the legacy "Panel ran clean" marker, kept for backwards compatibility.
PANEL_RESOLVED_DISPOSITION = re.compile(
    r"\|\s*(Addressed|Deferred(?:\s*→[^|]*)?|Sealed|Accepted as risk|Halt and re-scope|—)\s*\|",
    re.IGNORECASE,
)

# New-format evidence (post-#5 layout): a row in `### Trajectory` starts with a
# numeric Pass and ISO-8601 Date. archive_pass.py appends one per archived pass,
# so any presence indicates the panel has run at least once.
PANEL_TRAJECTORY_ROW = re.compile(
    r"^\|\s*\d+\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|", re.MULTILINE
)

# New-format evidence: a `[SEAL-NN]` entry in `### Sealed dispositions`
# represents a durable user-directed or accepted-as-risk decision.
PANEL_SEAL_ENTRY = re.compile(r"^-\s+`\[SEAL-\d+\]`", re.MULTILINE)

# New-format evidence: a row in `### Latest pass detail` starts with a
# bracketed severity tag in the Severity column. The bracket disambiguates
# data rows from the column-name header (where `Addressed`, `Deferred`,
# `Sealed` etc. appear as column labels in `### Trajectory`).
PANEL_LATEST_DETAIL_ROW = re.compile(
    r"^\|\s*\[(?:HIGH|MED|LOW)\]", re.MULTILINE
)


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def detect_language(spec_dir: Path, project_root: Optional[Path] = None) -> str:
    """Auto-detect project language from project root markers.

    If project_root is given, checks only that directory.
    Otherwise walks up from spec_dir looking for markers.
    """
    if project_root is not None:
        for lang, profile in LANGUAGE_PROFILES.items():
            if any((project_root / f).exists() for f in profile["project_markers"]):
                return lang
            if any((project_root / d).is_dir() for d in profile["dir_markers"]):
                return lang
        return NEUTRAL_LANGUAGE  # neutral fallback — not "python"

    search_dir = spec_dir.resolve()
    for _ in range(10):  # max 10 levels up
        for lang, profile in LANGUAGE_PROFILES.items():
            if any((search_dir / f).exists() for f in profile["project_markers"]):
                return lang
            if any((search_dir / d).is_dir() for d in profile["dir_markers"]):
                return lang
        parent = search_dir.parent
        if parent == search_dir:
            break
        search_dir = parent
    return NEUTRAL_LANGUAGE  # neutral fallback — not "python"


def get_profile(language: str) -> dict:
    """Get the language profile, falling back to the neutral 'generic' profile.

    An unknown key resolves to 'generic' (advisory checks disabled), NOT to
    'python' — falling back to Python is what silently mislabels a non-Python
    project and fires spurious advisory warnings against it.
    """
    return LANGUAGE_PROFILES.get(language, LANGUAGE_PROFILES[NEUTRAL_LANGUAGE])


# Severity and ValidationResult are imported from blueprint_common (above)
# to avoid the prior duplicate definitions. Same interface, same behaviour;
# both validators now share one canonical implementation.

# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def read_file(path: Path) -> Optional[str]:
    """Read file contents or return None if it doesn't exist."""
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return None


def has_section(content: str, section_name: str) -> bool:
    """Check if content contains the section name as a heading or bold label."""
    heading = re.compile(rf"^#+\s+.*{re.escape(section_name)}", re.MULTILINE | re.IGNORECASE)
    bold = re.compile(rf"\*\*{re.escape(section_name)}", re.IGNORECASE)
    return bool(heading.search(content) or bold.search(content))


def validate_resolved(content: str, filename: str, result: ValidationResult) -> None:
    """Check that all questions, decisions, and markers are resolved."""
    # Unchecked open questions
    unchecked = UNCHECKED_QUESTION_PATTERN.findall(content)
    result.add(
        f"{filename} has no unresolved open questions",
        len(unchecked) == 0,
        f"{len(unchecked)} unchecked question(s) found" if unchecked else "",
    )

    # TBD decisions
    tbds = TBD_PATTERN.findall(content)
    result.add(
        f"{filename} has no [TBD] decisions",
        len(tbds) == 0,
        f"{len(tbds)} [TBD] marker(s) found" if tbds else "",
    )

    # General unresolved markers (TODO, FIXME, XXX, HACK, ???)
    markers = UNRESOLVED_MARKERS.findall(content)
    result.add(
        f"{filename} has no unresolved markers (TODO/FIXME/???)",
        len(markers) == 0,
        f"Found: {', '.join(markers)}" if markers else "",
        warn_only=True,
    )


def _extract_panel_section(content: str) -> str:
    """Return the body of the '## Panel Review' section with HTML comments
    stripped, or an empty string if the section is missing.

    Stripping comments prevents false positives from example disposition text
    inside `<!-- ... -->` instructions embedded in the template.
    """
    match = re.search(
        r"^##\s+Panel Review\s*\n(.*?)(?=\n^##\s+|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return ""
    body = match.group(1)
    return re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)


def validate_panel_review(content: str, filename: str, result: ValidationResult) -> None:
    """Check that the Panel Review section is present, has real content, and
    has no unresolved concerns still in the 'User input needed' disposition.

    The Panel Review section is the output of the three-persona pre-gate
    stress test. Two formats are accepted:

    * **New format:** three sub-sections —
      `### Trajectory`, `### Sealed dispositions`, `### Latest pass detail`.
      `archive_pass.py` maintains the Trajectory table; sealed items move into
      Sealed dispositions; Latest pass detail is cleared between passes.
    * **Legacy format:** a single `## Panel Review` table with one row per
      concern, plus an optional `| — | — | No concerns raised | — |
      Panel ran clean |` row when the panel raised nothing.

    Evidence the panel has run is any of: a resolved-disposition row, a
    Trajectory row, or a `[SEAL-NN]` entry. An artifact lacking all three —
    the template state — fails validation.
    """
    panel_body = _extract_panel_section(content)

    # Check the section has substantive content. Presence is already covered
    # by the per-phase required-sections check for spec/design; tasks does not
    # use a required-sections list, so this also acts as the presence check
    # for tasks.md.
    has_body = bool(panel_body.strip())
    result.add(
        f"{filename} 'Panel Review' section has content",
        has_body,
        "Panel Review section is missing, empty, or contains only placeholder text"
        if not has_body
        else "",
    )
    if not has_body:
        return

    # Check for any unresolved panel concerns (disposition 'User input needed')
    unresolved = PANEL_UNRESOLVED_DISPOSITION.findall(panel_body)
    result.add(
        f"{filename} has no unresolved panel concerns",
        len(unresolved) == 0,
        f"{len(unresolved)} concern(s) still in 'User input needed' disposition"
        if unresolved
        else "",
    )

    # Evidence the panel has run depends on which format the artifact uses.
    # We detect new format by the presence of `### Trajectory`. For new format,
    # PANEL_RESOLVED_DISPOSITION is not used because `Addressed`, `Deferred`,
    # and `Sealed` appear as column-name labels in the Trajectory header row
    # and would produce false positives.
    is_new_format = "### Trajectory" in panel_body
    if is_new_format:
        has_trajectory = bool(PANEL_TRAJECTORY_ROW.search(panel_body))
        has_seal = bool(PANEL_SEAL_ENTRY.search(panel_body))
        has_latest = bool(PANEL_LATEST_DETAIL_ROW.search(panel_body))
        panel_ran = has_trajectory or has_seal or has_latest
        missing_msg = (
            "No evidence found — panel has not run or its results were not "
            "written. Expected at least one of: a Trajectory row "
            "(numeric Pass + ISO date), a `[SEAL-NN]` entry, or a row in "
            "Latest pass detail with a bracketed severity tag."
        )
    else:
        # Legacy single-table format: resolved disposition row or "Panel ran
        # clean" marker.
        panel_ran = bool(PANEL_RESOLVED_DISPOSITION.search(panel_body))
        missing_msg = (
            "No resolved dispositions found — panel has not run or results "
            "were not written"
        )
    result.add(
        f"{filename} 'Panel Review' shows the panel has run",
        panel_ran,
        missing_msg if not panel_ran else "",
    )


# ---------------------------------------------------------------------------
# Approval helpers
# ---------------------------------------------------------------------------

# Canonical approval-detection constants. APPROVAL_HEADER / APPROVAL_CHECKBOX
# are kept identical to validate_blueprint.py's so the two skills' validators
# interpret the approval format identically (`- [x]` / `- [X]`, a `## Approval`
# header with flexible surrounding whitespace). The narrow content-hash line is
# the SHARED `blueprint_common.APPROVAL_HASH_LINE_STRICT` (imported as
# APPROVAL_HASH_LINE) — both validators key on ONE object so the approval-hash
# grammar cannot drift between them. Hash comparison routes through the shared
# blueprint_common.verify_content_hash (case-insensitive); `content_for_hashing`
# / `compute_content_hash` are likewise imported from blueprint_common, sharing
# the producer-side implementation for hash coherence across both validators.
APPROVAL_HEADER = re.compile(r"^##\s+Approval\s*$", re.MULTILINE)
APPROVAL_CHECKBOX = re.compile(r"- \[[xX]\] Approved to proceed")
APPROVAL_HASH_LINE = APPROVAL_HASH_LINE_STRICT


def check_approval(content: str, filename: str, result: ValidationResult) -> bool:
    """Check if a document is approved and the approval is still valid.

    Returns True if the document is approved and hash matches.
    """
    if not APPROVAL_HEADER.search(content):
        result.add(f"{filename} has Approval section", False, "Missing ## Approval section")
        return False

    result.add(f"{filename} has Approval section", True)

    is_approved = bool(APPROVAL_CHECKBOX.search(content))
    result.add(f"{filename} is approved", is_approved)

    if not is_approved:
        return False

    hash_match = APPROVAL_HASH_LINE.search(content)
    if not hash_match:
        result.add(f"{filename} approval hash present", False, "No content hash found")
        return False

    stored_hash = hash_match.group(1)
    hashes_match = stored_hash != "pending" and verify_content_hash(content, stored_hash)
    result.add(
        f"{filename} has not been modified since approval",
        hashes_match,
        f"Stored: {stored_hash}, Current: {compute_content_hash(content)}"
        if not hashes_match
        else "",
    )
    return hashes_match


def _resolve_marker_root_and_key(
    path: Path, project_root: Optional[Path]
) -> "tuple[Path, str]":
    """Resolve the `.sdd/` marker root and `path`'s project-root-relative key.

    Uses `project_root` when given, else the aliased `arch_find_project_root`
    (NOT the local `find_project_root`, which targets blueprint/PLAN.md — AD3).
    Write-side containment guard: if `path` is NOT under the resolved root (a
    misconfigured `--project-root` that isn't an ancestor would otherwise yield a
    `../…` key that reconcile permanently rejects -> stuck-pending deadlock),
    fall back to walking up from `path` (guaranteed an ancestor) and WARN.
    """
    start = path if path.is_dir() else path.parent
    root = (
        project_root
        if project_root is not None
        else arch_find_project_root(start)
    )
    rel = Path(os.path.relpath(path.resolve(), Path(root).resolve())).as_posix()
    if rel.startswith("..") or os.path.isabs(rel):
        print(
            f"WARNING: project root {root} is not an ancestor of {path}; "
            f"resolving the .sdd/ marker root by walking up from the document "
            f"instead (ignoring the supplied root for the marker).",
            file=sys.stderr,
        )
        root = arch_find_project_root(start)
        rel = Path(os.path.relpath(path.resolve(), Path(root).resolve())).as_posix()
    return Path(root), rel


def approve_document(
    file_path: Path,
    *,
    task_tick: bool = False,
    project_root: Optional[Path] = None,
) -> None:
    """Mark a document as approved by checking the box and writing the content hash.

    Writes are atomic (temp-file + os.replace) to guard against partial-state
    corruption on Ctrl-C / disk-full / process kill mid-write.

    On a CHANGED-document re-stamp (R1/R2 — the freshly-computed hash differs
    from the stored one on a previously-approved doc) this prints the
    REAPPROVAL_REMINDER and writes a `.sdd/pending-review.json` marker entry,
    UNLESS ``task_tick`` is set (the Phase-4 task-tick carve-out, which
    suppresses both and prints a stdout audit line). Keyword-only params with
    safe defaults keep existing 1-arg callers unaffected.
    """
    original_content = file_path.read_text(encoding="utf-8")
    # Read the prior stored hash BEFORE the trim/rewrite mutates the file (DEF-06).
    stored_hash = read_stored_hash(original_content)

    # Trim the `### Trajectory` table to the latest 15 data rows BEFORE
    # computing the document hash — the trimmed table is part of the
    # approved content. Older rows are replaced with a single elided
    # summary row at the top of the data section; re-approval merges
    # the existing elided count with new elisions.
    content = trim_trajectory_table(original_content)

    # Compute hash before modifying approval section
    content_hash = compute_content_hash(content)

    # Update the checkbox
    content = re.sub(
        r"- \[ \] Approved to proceed",
        "- [x] Approved to proceed",
        content,
    )

    # Update the hash
    content = re.sub(
        r"\*\*Content Hash:\*\*\s*`[^`]*`",
        f"**Content Hash:** `{content_hash}`",
        content,
    )

    # Atomic write: temp-file then os.replace. The temp file lives in the
    # same directory as the target so os.replace is atomic on POSIX. On
    # failure the temp file is removed; the original target stays intact.
    # The temp-file path is appended to the re-raised exception so
    # cross-mount (EXDEV) or permission errors point at a real artifact
    # (per the light-touch verification pass, critic finding #3).
    tmp = file_path.with_suffix(file_path.suffix + ".tmp")
    tmp_removed = False
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, file_path)
    except Exception as exc:
        try:
            tmp.unlink(missing_ok=True)
            tmp_removed = True
        except Exception:
            pass
        tmp_status = "removed" if tmp_removed else f"left at {tmp}"
        exc.args = (
            *exc.args,
            f"atomic write to {file_path} failed; temp file {tmp_status}",
        )
        raise
    print(f"Approved: {file_path} (hash: {content_hash})")

    # R1/R2: changed-document re-stamp handling (printed AFTER the Approved line).
    if task_tick:
        # Phase-4 task-tick carve-out (DEF-01/RI-11): suppress reminder + marker.
        # v1-posture: the bypass is stdout-audited + fail-closed (absent flag ->
        # the gate fires). A git-durable Trajectory tag is a v2 enhancement, out
        # of v1 scope.
        print(
            f"task-tick: pending-review suppressed for {file_path} "
            f"(Phase-4 carve-out)"
        )
        return
    if changed_since_stamp(content_hash, stored_hash, original_content):
        root, doc_rel = _resolve_marker_root_and_key(file_path, project_root)
        upsert_pending_entry(
            root,
            doc_rel,
            content_hash,
            now_iso_utc(),
            stamped_at_pass_from_content(original_content),
        )
        print(REAPPROVAL_REMINDER)


def check_previous_phase_approved(
    spec_dir: Path, current_phase: str, result: ValidationResult,
) -> None:
    """Verify the previous phase's document is approved before validating the current one."""
    phase_order = {"design": "spec.md", "tasks": "design.md"}
    prev_file = phase_order.get(current_phase)
    if prev_file is None:
        return  # spec has no previous phase

    prev_path = resolve_artifact(spec_dir, prev_file)
    prev_content = read_file(prev_path)
    if prev_content is None:
        result.add(f"Previous phase ({prev_file}) exists", False)
        return

    approved = check_approval(prev_content, f"previous phase ({prev_file})", result)
    if not approved:
        result.add(
            f"Previous phase ({prev_file}) approved before this phase",
            False,
            f"{prev_file} must be approved before proceeding",
        )


def _read_plan_identifier(
    spec_dir: Path, spec_content: Optional[str] = None
) -> Optional[str]:
    """Return the in-file PLAN feature identifier ('F<n>' or 'n/a') from
    spec.md, or None if spec.md is absent/unreadable or has no identifier line.

    If ``spec_content`` (already-read spec.md text) is supplied, it is parsed
    directly — avoiding a redundant disk read on the ``validate_spec()`` path,
    which already holds the content. When reading from disk it uses
    encoding='utf-8' with an `except (OSError, UnicodeDecodeError)` guard — a
    non-UTF-8 spec.md is treated as unreadable (None), NOT decoded with
    errors='replace' (which could let the identifier line parse as garbage and
    produce a wrong result instead of cannot-cross-check). Never raises.
    """
    if spec_content is None:
        try:
            with open(resolve_artifact(spec_dir, "spec.md"), encoding="utf-8") as fh:
                spec_content = fh.read()
        except (OSError, UnicodeDecodeError):
            return None
    m = PLAN_FEATURE_ID_LINE_RE.search(spec_content)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Cross-Project Derivation (CPD) field grammar
# ---------------------------------------------------------------------------
#
# A derived spec.md carries two CPD provenance fields plus an optional UCR
# stanza. The two fields are validated by `_check_cpd_fields` (I5); the
# `**Derived from:**` value also feeds `check_dir_identifier`'s derived branch
# (I4). The four field constants below (`DERIVED_FROM_LINE_RE`,
# `MASTER_CONTRACT_HASH_LINE_RE`, `MASTER_HASH_VALUE_RE`, `MASTER_HASH_UNBOUND`)
# are imported from `project_link` — the single CPD-grammar owner — so this
# authoring gate and `reconcile` (the integrator) can never drift on the field
# shapes (the value captures are loose `[^`]*`; well-formedness is decided
# downstream, so a malformed-but-present field is still detected as present).


def _extract_cpd_field_values(
    content: str,
) -> "tuple[bool, bool, Optional[str], Optional[str]]":
    """Return (has_derived_from, has_master_hash, derived_from_value,
    master_hash_value) for the CPD provenance fields in spec.md.

    A value of None means the field's line is absent; an empty string means the
    line is present with an empty backtick value (still "present"). Never raises.
    """
    df = DERIVED_FROM_LINE_RE.search(content)
    mh = MASTER_CONTRACT_HASH_LINE_RE.search(content)
    derived_from_value = df.group(1) if df else None
    master_hash_value = mh.group(1) if mh else None
    return (df is not None, mh is not None, derived_from_value, master_hash_value)


def _check_cpd_fields(
    spec_dir: Path, content: str, result: ValidationResult
) -> None:
    """Validate the `**Derived from:**` + `**Master contract hash:**` fields (I5).

    SOLE owner of the malformed-value, co-occurrence, and non-derived-dir FAILs.
    Runs BEFORE `check_dir_identifier` so well-formedness is established first.
    Implements the precedence ladder — first match wins, at most one FAIL — so a
    value that is both malformed AND mismatched yields exactly one FAIL (the
    malformed one; `check_dir_identifier`'s derived branch then short-circuits on
    the same `parse_qualified_id is None`). Never raises.

    Ladder:
      1. A CPD field present on a non-`derived` dir -> `derived-fields-on-non-derived-dir`
         (stop — the other checks are moot off a non-derived dir).
      2. Exactly one of the two fields present -> `derived-fields-incomplete`.
      3. `**Derived from:**` malformed (not a backtick-wrapped qualified id)
         -> `derived-from-malformed`.
      4. `**Master contract hash:**` neither 64-hex nor `unbound`
         -> `master-hash-malformed`.
      Both fields absent -> PASS (non-derived spec, no CPD fields expected).
    """
    (
        has_derived_from,
        has_master_hash,
        derived_from_value,
        master_hash_value,
    ) = _extract_cpd_field_values(content)

    # Both absent: nothing to validate (non-derived spec).
    if not has_derived_from and not has_master_hash:
        return

    escaped = display_safe(spec_dir.name)

    # Step 1: a CPD field on a non-derived directory. Off a non-derived dir the
    # remaining CPD checks are moot, so this is the sole FAIL.
    if not is_derived_spec(spec_dir):
        result.add(
            "derived-fields-on-non-derived-dir", False,
            f"spec directory '{escaped}' carries a CPD provenance field "
            f"(`**Derived from:**` and/or `**Master contract hash:**`) but its "
            f"name is not a derived-form directory (`<project>--F<n>-<slug>`). "
            f"Either rename the directory to the derived form, or remove the "
            f"CPD fields if this is not a cross-project derived spec.",
        )
        return

    # Step 2: co-occurrence — both fields must appear together.
    if has_derived_from != has_master_hash:
        result.add(
            "derived-fields-incomplete", False,
            "`**Derived from:**` and `**Master contract hash:**` must appear "
            "together. Add the missing field; use `unbound` for the hash if not "
            "yet reconciled against the master project.",
        )
        return

    # Step 3: `Derived from` well-formedness (backtick-wrapped qualified id).
    if parse_qualified_id(derived_from_value or "") is None:
        result.add(
            "derived-from-malformed", False,
            "`**Derived from:**` value is malformed — must be a backtick-wrapped "
            "qualified id like `project:F7` (lowercase project alias, `F`, a "
            "positive feature number with no leading zero).",
        )
        return

    # Step 4: `Master contract hash` well-formedness (64-hex or `unbound`).
    value = master_hash_value or ""
    if value != MASTER_HASH_UNBOUND and not MASTER_HASH_VALUE_RE.match(value):
        result.add(
            "master-hash-malformed", False,
            "`**Master contract hash:**` value is malformed — must be 64 "
            "lowercase hex characters (a SHA-256 digest) or the literal "
            "`unbound` if not yet reconciled against the master project.",
        )
        return


def _validate_ucr_stanza(content: str, result: ValidationResult) -> None:
    """Validate the `## Upstream Change Requests` stanza if present (I6).

    Delegates parsing to the shared `ucr.parse_ucr_stanza` (so `validate_spec.py`
    and `reconcile.py` can never drift on the grammar) and emits a FAIL for each
    structural problem: malformed UCR id, duplicate id, invalid status, missing
    required field, or a malformed `Target` qualified id. A no-op when the stanza
    is absent. The stanza's presence never causes a FAIL and never hard-halts
    validation; an `## Accepted Divergences` section may coexist. Never raises.
    """
    parsed = parse_ucr_stanza(content)
    if not parsed.present:
        return

    # Malformed ids (leading zero / `0`) — rejected at parse time, never entries.
    for raw_id in parsed.malformed_ids:
        result.add(
            "ucr-id-malformed", False,
            f"`### UCR-{display_safe(raw_id)}` has a malformed id — UCR ids use "
            f"the same canonical-decimal grammar as `### CFC-N` (a positive "
            f"integer with no leading zero).",
        )

    # Duplicate ids within this spec.
    for num in parsed.duplicate_ids:
        result.add(
            "duplicate-ucr-id", False,
            f"`### UCR-{num}` appears more than once. Each UCR id must be unique "
            f"within a single spec.",
        )

    # Missing required fields.
    for num, field_name in parsed.missing_field_ids:
        result.add(
            "ucr-missing-field", False,
            f"`### UCR-{num}` is missing the required `**{field_name}:**` field. "
            f"Each UCR entry needs Target, Status, Proposed change, and Rationale.",
        )

    # Invalid status values.
    for num in parsed.invalid_status_ids:
        result.add(
            "ucr-invalid-status", False,
            f"`### UCR-{num}` has an invalid status. Status must be one of "
            f"`open`, `applied`, or `withdrawn`.",
        )

    # Malformed `Target` qualified ids — only for entries whose Target is present
    # (a missing Target is already covered by ucr-missing-field above). The raw
    # value is backtick-wrapped on disk; strip the wrapping before the parse.
    for entry in parsed.entries:
        target = entry.target()
        if target is None:
            continue
        unwrapped = target.strip()
        if unwrapped.startswith("`") and unwrapped.endswith("`") and len(unwrapped) >= 2:
            unwrapped = unwrapped[1:-1]
        if parse_qualified_id(unwrapped) is None:
            result.add(
                "ucr-target-malformed", False,
                f"`### UCR-{entry.number}` has a malformed `**Target:**` value — "
                f"must be a backtick-wrapped qualified id like `project:F7`.",
            )


def check_dir_identifier(
    spec_dir: Path, spec_content: Optional[str] = None
) -> ValidationResult:
    """Cross-check the spec directory name against the in-file PLAN feature
    identifier (R2). Returns a ValidationResult with zero checks (PASS) or one
    FAIL check. Never raises.

    Dispatches through `classify_dirname`; the bound (number, slug) pair comes
    from `spec_dirname.parse_bound` — the single grammar-owned decomposition, so
    no second interpretation of the bound form lives here. Names embedded in
    messages are escaped via `spec_dirname.display_safe` so a control char in a
    directory name cannot spoof the validator's stdout. Feature-number
    comparison is numeric (so a non-canonical `F03` identifier vs an `F3`
    directory is not a false mismatch). If `spec_content` (already-read spec.md
    text) is supplied, the identifier is parsed from it instead of re-reading
    the file. FAIL codes: dir-identifier-mismatch / missing-slug / invalid-slug
    / cannot-cross-check / derived-provenance-mismatch.
    """
    result = ValidationResult()
    name = spec_dir.name
    escaped = display_safe(name)
    category = classify_dirname(name)
    hash_safe = (
        "Renaming a spec directory does not invalidate any existing approval or "
        "content hash."
    )

    if category == "derived":
        # Derived form `<project>--F<n>-<slug>` (I4). Coherence between the
        # directory's encoded provenance and the in-file `**Derived from:**`
        # line. The directory decomposition is grammar-owned by
        # `project_link.parse_derived_dirname`; the malformed-value, co-occurrence
        # and non-derived-dir FAILs are owned by `_check_cpd_fields` (I5), so this
        # branch never re-emits them.
        content = spec_content
        if content is None:
            content = read_file(resolve_artifact(spec_dir, "spec.md")) or ""
        dir_parsed = parse_derived_dirname(name)
        # Classification (`classify_dirname` -> "derived") and decomposition
        # (`parse_derived_dirname`) now share ONE compiled grammar
        # (`spec_dirname.DERIVED_DIRNAME_PATTERN`), so a "derived" category
        # implies a non-None parse. Guard the unpack anyway: defence-in-depth so
        # any future grammar skew surfaces as a clean FAIL instead of a
        # `TypeError` raised mid-validation.
        if dir_parsed is None:
            result.add(
                "derived-provenance-mismatch", False,
                f"spec directory '{escaped}' classifies as derived but cannot be "
                f"decomposed into `<project>--F<n>-<slug>`. {hash_safe}",
            )
            return result
        dir_project, dir_number, _dir_slug = dir_parsed

        (
            has_derived_from,
            _has_master_hash,
            derived_from_value,
            _master_hash_value,
        ) = _extract_cpd_field_values(content)

        # Step 1 — well-formedness short-circuit. A malformed (or absent-value)
        # `**Derived from:**` is already FAILed by `_check_cpd_fields`
        # (`derived-from-malformed` / `derived-fields-incomplete`); this branch
        # returns WITHOUT a second FAIL so a both-malformed-and-mismatched value
        # yields exactly one FAIL through the full `validate_spec()` path (I5).
        parsed_from = (
            parse_qualified_id(derived_from_value)
            if has_derived_from and derived_from_value is not None
            else None
        )

        # Step 2 — presence: the `**Derived from:**` line is absent entirely.
        if not has_derived_from:
            result.add(
                "derived-provenance-mismatch", False,
                f"spec directory '{escaped}' uses the derived form but the "
                f"`**Derived from:**` line is missing. A derived spec records its "
                f"master-project provenance on a `**Derived from:** "
                f"`<project>:F<n>`` line. {hash_safe}",
            )
            return result

        # Malformed value -> owned by `_check_cpd_fields`; do not double-FAIL.
        if parsed_from is None:
            return result

        from_project, from_number = parsed_from

        # Step 3 — identifier must be `n/a` (provenance is on the Derived from line).
        identifier = _read_plan_identifier(spec_dir, content)
        if identifier is not None and identifier != "n/a":
            result.add(
                "derived-provenance-mismatch", False,
                f"spec directory '{escaped}' uses the derived form, so its "
                f"`**PLAN feature identifier:**` must be `n/a` (provenance lives on "
                f"the `**Derived from:**` line), but it is '{display_safe(identifier)}'. "
                f"Set the identifier to `n/a`. {hash_safe}",
            )
            return result

        # Step 4 — project mismatch.
        if from_project != dir_project:
            result.add(
                "derived-provenance-mismatch", False,
                f"spec directory '{escaped}' encodes master project "
                f"'{display_safe(dir_project)}' but `**Derived from:**` names "
                f"'{display_safe(from_project)}'. Make the directory project prefix "
                f"and the Derived from project match. {hash_safe}",
            )
            return result

        # Step 5 — number mismatch.
        if from_number != dir_number:
            result.add(
                "derived-provenance-mismatch", False,
                f"spec directory '{escaped}' encodes feature F{dir_number} but "
                f"`**Derived from:**` names F{from_number}. Make the directory "
                f"feature number and the Derived from feature number match. "
                f"{hash_safe}",
            )
            return result

        # Step 6 — all checks clear -> PASS (no check added).
        return result

    if category == "bare":
        # Bare token F<n>. Suggest the CANONICAL bound rename: parse_feature_number
        # strips a leading zero (F03 -> 3). Feature 0 (F0/F00) has no valid bound
        # form (the bound grammar is F[1-9]\d*), so steer those to n>=1 or a bare
        # standalone slug rather than the impossible 'F0-<slug>'.
        num = parse_feature_number(name)
        if num and num >= 1:
            result.add(
                "missing-slug", False,
                f"spec directory '{escaped}' is missing a slug. Rename it to "
                f"'F{num}-<slug>' (e.g. 'F{num}-checkout-flow'). To generate a "
                f"slug from the feature title, run:\n  {SLUGIFY_CLI_HINT}\n{hash_safe}",
            )
        else:
            result.add(
                "missing-slug", False,
                f"spec directory '{escaped}' is missing a slug and implies feature "
                f"number 0, which is not a valid feature number (bound names start "
                f"at F1). Rename it to 'F<n>-<slug>' with n >= 1 for a PLAN-bound "
                f"feature, or to a bare '<slug>' for a standalone feature. To "
                f"generate a slug, run:\n  {SLUGIFY_CLI_HINT}\n{hash_safe}",
            )
        return result
    if category == "invalid":
        result.add(
            "invalid-slug", False,
            f"spec directory '{escaped}' is not a valid name. Valid forms are "
            f"'F<n>-<slug>' (bound, e.g. 'F3-checkout-flow') or '<slug>' "
            f"(standalone, e.g. 'cli-notes-app') where <slug> is lowercase "
            f"kebab-case, max 50 characters. To generate a slug, run:\n  {SLUGIFY_CLI_HINT}\n"
            f"{hash_safe}",
        )
        return result

    # "bound" or "standalone": the decision depends on the in-file identifier.
    identifier = _read_plan_identifier(spec_dir, spec_content)
    if identifier is None:
        result.add(
            "cannot-cross-check", False,
            "cannot read the PLAN feature identifier from spec.md. Ensure spec.md "
            "has a '**PLAN feature identifier:**' line with its value filled in — "
            "`F<n>` for a PLAN-bound feature or `n/a` for a standalone feature. "
            "The spec template ships with the literal placeholder `F<n>`; replace "
            "it with your feature number or `n/a`. (If spec.md is missing "
            "entirely, approve the spec phase first.)",
        )
        return result

    if category == "bound":
        dir_num, slug = parse_bound(name)  # name is classified bound -> never None
        if identifier == "n/a":
            result.add(
                "dir-identifier-mismatch", False,
                f"spec directory '{escaped}' uses the bound form (implying PLAN "
                f"feature F{dir_num}) but the in-file identifier is 'n/a'. "
                f"Decision: if this feature is part of a blueprint/PLAN.md, set "
                f"the in-file identifier to `F{dir_num}`; if it is standalone, "
                f"rename the directory to the bare slug '{slug}'. {hash_safe}",
            )
        else:
            id_num = int(identifier[1:])  # identifier is 'F<digits>' (n/a handled above)
            if id_num != dir_num:
                result.add(
                    "dir-identifier-mismatch", False,
                    f"spec directory '{escaped}' implies feature F{dir_num} but the "
                    f"in-file identifier is '{identifier}'. Rename the directory to "
                    f"'F{id_num}-{slug}' or correct the in-file identifier. {hash_safe}",
                )
            # else same feature number -> PASS (no check added)
        return result

    # category == "standalone"
    if identifier != "n/a":
        id_num = int(identifier[1:])
        result.add(
            "dir-identifier-mismatch", False,
            f"spec directory '{escaped}' uses the standalone form but the in-file "
            f"identifier is '{identifier}'. Decision: if this feature is part of a "
            f"blueprint/PLAN.md, rename the directory to 'F{id_num}-{escaped}'; "
            f"if it is standalone, change the in-file identifier to `n/a`. {hash_safe}",
        )
    return result


# ---------------------------------------------------------------------------
# Phase validators
# ---------------------------------------------------------------------------

def validate_spec(spec_dir: Path) -> ValidationResult:
    """Validate spec.md for required sections.

    Note: the R2 pending-review gate is NOT checked here — it is reconciled ONCE
    at dispatch level in main() (so it fires under every --phase, and an absent
    spec.md does not make the obligation vanish). See main().
    """
    result = ValidationResult()
    spec_path = resolve_artifact(spec_dir, "spec.md")
    content = read_file(spec_path)

    result.add("spec.md exists", content is not None, str(spec_path))
    if content is None:
        return result

    for section in SPEC_REQUIRED_SECTIONS:
        result.add(
            f"spec.md has '{section}' section",
            has_section(content, section),
        )

    # Check for at least one GIVEN/WHEN/THEN block
    has_gwt = bool(GWT_PATTERN.search(content))
    result.add(
        "spec.md has GIVEN/WHEN/THEN acceptance criteria",
        has_gwt,
        "At least one GIVEN/WHEN/THEN block expected" if not has_gwt else "",
    )

    # Check for success criteria checkboxes
    has_checkboxes = bool(re.search(r"- \[[ x]\]", content))
    result.add(
        "spec.md has success criteria checkboxes",
        has_checkboxes,
    )

    validate_resolved(content, "spec.md", result)
    validate_panel_review(content, "spec.md", result)

    # CFC consumer-side checks. Run after standard validation so a structurally
    # broken spec.md fails for the right reason first. See
    # documentation/CFC.md § Validator for the full ruleset.
    validate_cfc_consumer(spec_dir, content, "spec", result)

    # Cross-Project Derivation field well-formedness (I5). Runs BEFORE
    # check_dir_identifier so the malformed-value / co-occurrence / non-derived-dir
    # FAILs are established first and the derived branch never double-FAILs a
    # value it already rejected (exactly-one-FAIL precedence ladder).
    _check_cpd_fields(spec_dir, content, result)

    # UCR stanza structural validation (I6). A no-op when the
    # `## Upstream Change Requests` stanza is absent; never hard-halts.
    _validate_ucr_stanza(content, result)

    # Directory<->identifier cross-check (R2). Runs AFTER the spec.md-exists
    # early-return above, so a missing spec.md does not reach cannot-cross-check
    # via this path — only the --approve path (which has no such guard) can.
    result.checks.extend(check_dir_identifier(spec_dir, spec_content=content).checks)

    return result


def validate_design(spec_dir: Path, language: str = NEUTRAL_LANGUAGE) -> ValidationResult:
    """Validate design.md for required sections."""
    result = ValidationResult()
    profile = get_profile(language)

    check_previous_phase_approved(spec_dir, "design", result)

    design_path = resolve_artifact(spec_dir, "design.md")
    content = read_file(design_path)

    result.add("design.md exists", content is not None, str(design_path))
    if content is None:
        return result

    for section in DESIGN_REQUIRED_SECTIONS:
        result.add(
            f"design.md has '{section}' section",
            has_section(content, section),
        )

    # Check for type annotations (language-aware, advisory). Skipped entirely
    # for profiles with no type_pattern (e.g. "generic") — an architecture-neutral
    # deliverable need not contain language type annotations, so the check would
    # only emit noise.
    if profile["type_pattern"] is not None:
        has_types = bool(profile["type_pattern"].search(content))
        result.add(
            f"design.md includes {profile['label']} type annotations in models/interfaces",
            has_types,
            "Expected type annotations in code blocks" if not has_types else "",
            warn_only=True,
        )

    validate_resolved(content, "design.md", result)
    validate_panel_review(content, "design.md", result)

    return result


def validate_tasks(spec_dir: Path, language: str = NEUTRAL_LANGUAGE) -> ValidationResult:
    """Validate tasks.md for proper task entries."""
    result = ValidationResult()
    profile = get_profile(language)

    check_previous_phase_approved(spec_dir, "tasks", result)

    tasks_path = resolve_artifact(spec_dir, "tasks.md")
    content = read_file(tasks_path)

    result.add("tasks.md exists", content is not None, str(tasks_path))
    if content is None:
        return result

    # Count task entries
    task_matches = list(TASK_ENTRY_PATTERN.finditer(content))
    result.add(
        "tasks.md has task entries (### T1:, T2:, ...)",
        len(task_matches) > 0,
        f"Found {len(task_matches)} task(s)" if task_matches else "No tasks found",
    )

    # Check for summary table
    has_summary = bool(re.search(r"\|\s*Task\s*\|.*Status\s*\|", content, re.IGNORECASE))
    result.add(
        "tasks.md has summary table with status",
        has_summary,
    )

    # Per-task field checks. These run PER TASK rather than document-wide: a
    # document-wide `re.search` passes when ANY single task carries the field,
    # silently masking other tasks that omit it. Each task body spans its
    # `### T<n>:` heading to the next task heading or the next `## ` section,
    # whichever comes first; a failing check names the offending task IDs.
    section_break = re.compile(r"^## ", re.MULTILINE)
    task_bodies: list[tuple[str, str]] = []
    for i, m in enumerate(task_matches):
        id_match = re.search(r"T\d+", content[m.start() : m.end()])
        task_id = id_match.group(0) if id_match else f"task#{i + 1}"
        body_end = (
            task_matches[i + 1].start() if i + 1 < len(task_matches) else len(content)
        )
        sec = section_break.search(content, m.end(), body_end)
        if sec:
            body_end = sec.start()
        task_bodies.append((task_id, content[m.start() : body_end]))

    def _tasks_missing(pattern):
        return [tid for tid, body in task_bodies if not pattern.search(body)]

    # Required per-task fields (FAIL). Mirrors the tasks template and the
    # "Required per-task fields" list in SKILL.md / phase-tasks.md. (Test
    # function names are checked separately, below, as an advisory warning.)
    required_task_fields = [
        ("Requirement", re.compile(r"\*\*Requirement:\*\*\s*R\d+")),
        ("Description", re.compile(r"\*\*Description:\*\*")),
        ("Files", re.compile(r"\*\*Files:\*\*")),
        ("Dependencies", re.compile(r"\*\*Dependencies:\*\*")),
        ("Parallel", re.compile(r"\*\*Parallel:\*\*")),
        ("Verification", re.compile(r"\*\*Verification:\*\*")),
    ]
    for field_name, field_pattern in required_task_fields:
        missing = _tasks_missing(field_pattern) if task_bodies else []
        result.add(
            f"tasks.md every task has **{field_name}:**",
            not missing,
            f"Missing in: {', '.join(missing)}" if missing else "",
        )

    # Acceptance Criteria + GIVEN/WHEN/THEN, per task.
    ac_missing = (
        _tasks_missing(re.compile(r"\*\*Acceptance Criteria")) if task_bodies else []
    )
    result.add(
        "tasks.md every task has **Acceptance Criteria**",
        not ac_missing,
        f"Missing in: {', '.join(ac_missing)}" if ac_missing else "",
    )
    gwt_missing = _tasks_missing(GWT_PATTERN) if task_bodies else []
    result.add(
        "tasks.md every task's acceptance criteria use GIVEN/WHEN/THEN format",
        not gwt_missing,
        f"Missing GIVEN/WHEN/THEN in: {', '.join(gwt_missing)}" if gwt_missing else "",
    )

    # Test function/method names (language-aware) — advisory (warn), per task.
    # Skipped for profiles with no test_name_pattern (e.g. "generic"): a static
    # site, infra, or skill-authoring task is verified by a command/manual check,
    # not an xUnit-style test function, so this check would only emit noise.
    if profile["test_name_pattern"] is not None:
        test_missing = _tasks_missing(profile["test_name_pattern"]) if task_bodies else []
        result.add(
            "tasks.md every task names test functions/methods",
            not test_missing,
            f"Missing in: {', '.join(test_missing)}" if test_missing else "",
            warn_only=True,
        )

    # Requirement coverage — check all spec R-numbers are covered by tasks
    has_req = bool(TASK_REQUIREMENT_REF_PATTERN.search(content))
    spec_content = read_file(resolve_artifact(spec_dir, "spec.md"))
    if spec_content is not None and has_req:
        spec_reqs = set(REQUIREMENT_ID_PATTERN.findall(spec_content))
        # Extract individual R-numbers from Requirement lines (e.g., "R1, R2, R3")
        task_reqs = set()
        for match in TASK_REQUIREMENT_REF_PATTERN.finditer(content):
            for r_num in re.findall(r"R(\d+)", match.group(1)):
                task_reqs.add(r_num)
        uncovered = spec_reqs - task_reqs
        if uncovered:
            missing_labels = ", ".join(f"R{r}" for r in sorted(uncovered, key=int))
            result.add(
                "tasks.md covers all requirements from spec.md",
                False,
                f"Missing tasks for: {missing_labels}",
                warn_only=True,
            )
        else:
            result.add(
                "tasks.md covers all requirements from spec.md",
                True,
                f"All {len(spec_reqs)} requirement(s) covered",
            )

    validate_resolved(content, "tasks.md", result)
    validate_panel_review(content, "tasks.md", result)

    # CFC consumer-side checks for tasks.md (Phase 3): if this feature is named
    # as the owning feature in any CFC's Enforcement prose, tasks.md must
    # contain a `[CFC-N]`-tagged task. See documentation/CFC.md.
    validate_cfc_consumer(spec_dir, content, "tasks", result)

    return result


# ---------------------------------------------------------------------------
# CFC consumer-side validation
# ---------------------------------------------------------------------------
#
# Reads `blueprint/PLAN.md`'s `## Cross-Feature Contracts` section (if present)
# and applies:
#   - Identifier-line skip rule (5 cases per CFC.md M5/P7)
#   - Spec.md THEN-line CFC tag presence (if feature is in CFC's Participating)
#   - Tasks.md checkbox CFC tag presence (if feature is in CFC's Enforcement owners)
#   - Mid-stream drift WARN (tag references CFC that no longer exists or
#     no longer lists this feature)
#
# Parser primitives — extract_cfc_section, parse_cfc_entries, CFC tag regex,
# feature-ID matcher — are imported from telescoping-sdd/scripts/cfc_parser.py
# (shared with validate_blueprint.py). The producer/consumer split for the
# cascade machinery is preserved (no `cfc_consistency.py` in v1); only the
# file-format parser is shared.

PLAN_FEATURE_ID_LINE_RE = re.compile(
    r"^\*\*PLAN feature identifier:\*\*\s*`(F\d+|n/a)`", re.MULTILINE
)
# Accept optional leading whitespace so indented sub-task checkboxes count
# alongside top-level ones (per P2-6 from the post-implementation review).
TASKS_CHECKBOX_WITH_CFC_RE = re.compile(
    r"^[ \t]*-\s+\[[ xX]\]\s+[^\n]*?\[CFC-(\d+)\]", re.MULTILINE
)
PLAN_FEATURE_BREAKDOWN_RE = re.compile(
    r"^###\s+F(\d+):", re.MULTILINE
)


def find_project_root(spec_dir: Path) -> Optional[Path]:
    """Walk upward from spec_dir looking for a sibling `blueprint/` directory."""
    for candidate in (spec_dir.parent, spec_dir.parent.parent):
        if candidate is None:
            continue
        if resolve_artifact(candidate / "blueprint", "PLAN.md").is_file():
            return candidate
    return None


def _parse_cfc_section(plan_content: str) -> list[dict]:
    """Return a list of CFC dicts with keys: number, participating, enforcement.

    Wraps the shared `parse_cfc_entries` from `cfc_parser` to produce the
    dict shape the consumer-side validator works with. Returns an empty list
    if no `## Cross-Feature Contracts` section is present.
    """
    section = extract_cfc_section(plan_content)
    if section is None:
        return []
    _start, _end, body = section
    entries: list[dict] = []
    for entry in parse_cfc_entries(body):
        entries.append(
            {
                "number": entry.number,
                "participating": entry.participating_features(),
                "enforcement_text": entry.fields.get("Enforcement") or "",
                "enforcement_owners": entry.enforcement_owners(),
            }
        )
    return entries


def _spec_then_line_cfc_tags(spec_content: str) -> list[int]:
    """Extract CFC numbers from `[CFC-N]` tags on THEN lines in spec.md."""
    return extract_cfc_tags(spec_content)


def _tasks_checkbox_cfc_tags(tasks_content: str) -> list[int]:
    """Extract CFC numbers from `[CFC-N]` tags on tasks.md checkbox lines."""
    return [int(m.group(1)) for m in TASKS_CHECKBOX_WITH_CFC_RE.finditer(tasks_content)]


def validate_cfc_consumer(
    spec_dir: Path,
    artifact_content: str,
    phase: str,
    result: ValidationResult,
) -> None:
    """Apply consumer-side CFC checks based on the artifact phase.

    phase ∈ {"spec", "tasks"}. The "design" phase has no validator-level CFC
    checks (design fidelity is panel-side judgement per CFC.md).
    """
    # Parse the identifier line from spec.md, which is the binding signal.
    spec_path = resolve_artifact(spec_dir, "spec.md")
    spec_content = read_file(spec_path)
    if spec_content is None:
        return

    # Derived-spec exemption (I7). A derived-form directory is exempt from ALL
    # `n/a`-standalone CFC-coherence behaviors (the `n/a`+active-CFC WARN AND the
    # `n/a`+stale-`[CFC-N]`-tag WARN) and from local-PLAN feature-id resolution:
    # its provenance lives in the master project's PLAN, not the local one. Gate
    # on the SHARED `is_derived_spec` predicate (NOT the identifier value) so this
    # exemption and the I4 derived branch can never drift on what "derived" means.
    # A derived spec legitimately carries `identifier == "n/a"`.
    if is_derived_spec(spec_dir):
        return

    id_match = PLAN_FEATURE_ID_LINE_RE.search(spec_content)
    identifier = id_match.group(1) if id_match else None

    project_root = find_project_root(spec_dir)
    plan_content = (
        read_file(resolve_artifact(project_root / "blueprint", "PLAN.md")) if project_root else None
    )
    has_cfc_section = bool(plan_content and CFC_HEADER_RE.search(plan_content))

    # M5 / P7 / Q11 skip rule.
    if identifier is None:
        # Line absent entirely → FAIL.
        result.add(
            "spec.md PLAN feature identifier line",
            False,
            "spec.md missing required `**PLAN feature identifier:**` line; "
            "use `n/a` for standalone",
        )
        return
    if identifier == "n/a":
        if has_cfc_section:
            # Q11 — silent opt-out vector guard. passed=False+warn_only emits WARN.
            result.add(
                "spec.md PLAN feature identifier coherence",
                False,
                "spec declares `n/a` but blueprint/PLAN.md has an active "
                "Cross-Feature Contracts section. If this feature should "
                "bind to one or more CFCs, set the identifier to `F<n>`; "
                "if standalone is correct, no action needed.",
                warn_only=True,
            )
        # Decision B — n/a + stale [CFC-N] tags in spec.md guard.
        # A user downgrading from F<n> to n/a (intentional or accidental) may
        # leave stale tags in spec.md. Without this WARN the binding silently
        # dies until the producer-side orphan-tag scan picks it up at the next
        # PLAN re-approval. Emit a per-CFC WARN naming the orphaned tags.
        stale_tags = sorted(set(_spec_then_line_cfc_tags(spec_content)))
        if stale_tags:
            tag_list = ", ".join(f"[CFC-{n}]" for n in stale_tags)
            result.add(
                "spec.md `n/a` identifier with stale CFC tags",
                False,
                f"spec declares `n/a` but carries {tag_list} on THEN lines. "
                "Either restore the `F<n>` identifier so binding-checks run, "
                "or remove the stale tags. Tags on an `n/a` spec are silently "
                "ignored by the binding validator otherwise.",
                warn_only=True,
            )
        return  # n/a → skip CFC binding checks regardless of PLAN presence

    # identifier is F<n> here.
    feature_number = int(identifier[1:])

    if not plan_content:
        result.add(
            "spec.md PLAN feature identifier resolves",
            False,
            f"spec claims {identifier} binding but no blueprint/PLAN.md exists",
        )
        return

    # Check identifier resolves to a feature in PLAN's Feature Breakdown.
    # Per P1-2 from the post-implementation code review: scope the scan to
    # the `## Feature Breakdown` section body. Without scoping, a `### F<n>:`
    # heading anywhere else in PLAN.md (inside `## Open Questions`, an
    # illustrative quote, a code block, etc.) would silently satisfy the
    # resolver and accept a feature ID that's not actually a real feature.
    fb_match = re.search(
        r"## Feature Breakdown\s*\n(.*?)(?=\n## |\Z)", plan_content, re.DOTALL
    )
    feature_breakdown_body = fb_match.group(1) if fb_match else ""
    plan_feature_ids = {
        int(g) for g in PLAN_FEATURE_BREAKDOWN_RE.findall(feature_breakdown_body)
    }
    if feature_number not in plan_feature_ids:
        result.add(
            "spec.md PLAN feature identifier resolves",
            False,
            f"PLAN feature identifier {identifier} not found in "
            f"blueprint/PLAN.md Feature Breakdown",
        )
        return

    if not has_cfc_section:
        # PLAN exists but has no CFC section → no checks to run.
        return

    # CFC binding checks.
    cfc_entries = _parse_cfc_section(plan_content)
    binding_cfcs = [
        e for e in cfc_entries if feature_number in e["participating"]
    ]
    spec_tags = _spec_then_line_cfc_tags(spec_content)

    # Phase-1 checks: every binding CFC must have a corresponding [CFC-N] tag
    # on a THEN line in spec.md.
    if phase == "spec":
        # Per P2-3 from the post-implementation review: surface "tag in
        # wrong location" distinctly from "missing tag". A `[CFC-N]` on a
        # GIVEN/WHEN line, in a requirement header, or in body prose outside
        # an AC block is a different bug from "the author never wrote the
        # tag" and deserves its own diagnostic.
        misplaced = find_misplaced_cfc_tags(spec_content)
        # A misplaced tag still counts as "present" for the purposes of the
        # binding check below — but ALSO emit a FAIL pointing the author at
        # the correct location.
        for n, line in misplaced:
            result.add(
                f"spec.md [CFC-{n}] tag location",
                False,
                f"[CFC-{n}] appears outside an acceptance criterion THEN line "
                f"(offending line: {line!r}). Move the tag to the THEN line "
                f"of the AC that materially implements the contract, e.g. "
                f"`THEN <assertion> [CFC-{n}]`. Tags on GIVEN/WHEN lines, "
                f"requirement headers, body prose, or single-line GWT "
                f"compressions are not recognised as bindings.",
            )

        for entry in binding_cfcs:
            n = entry["number"]
            if n in spec_tags:
                result.add(
                    f"spec.md carries [CFC-{n}] binding tag",
                    True,
                )
            else:
                result.add(
                    f"spec.md carries [CFC-{n}] binding tag",
                    False,
                    f"feature {identifier} appears in CFC-{n}'s Participating "
                    f"features; required: `[CFC-{n}]` on a THEN line within "
                    f"**Acceptance Criteria:**",
                )

        # Mid-stream drift WARN: tags present in spec.md that no longer
        # resolve cleanly in current PLAN.
        for n in set(spec_tags):
            entry = next((e for e in cfc_entries if e["number"] == n), None)
            if entry is None:
                result.add(
                    f"spec.md [CFC-{n}] tag still resolves",
                    False,
                    f"spec.md carries `[CFC-{n}]` but CFC-{n} no longer "
                    f"exists in current PLAN.md (mid-stream drift). "
                    f"Remove the tag, or restore CFC-{n} to PLAN.md.",
                    warn_only=True,
                )
            elif feature_number not in entry["participating"]:
                result.add(
                    f"spec.md [CFC-{n}] tag still resolves",
                    False,
                    f"spec.md carries `[CFC-{n}]` but {identifier} is no "
                    f"longer in CFC-{n}'s Participating features. "
                    f"Remove the tag, or restore {identifier} to "
                    f"CFC-{n}'s Participating list.",
                    warn_only=True,
                )

    # Phase-3 checks: if this feature is an Enforcement owner of any CFC,
    # tasks.md must contain a [CFC-N]-tagged task.
    if phase == "tasks":
        # artifact_content is tasks.md here.
        tasks_tags = _tasks_checkbox_cfc_tags(artifact_content)
        owning_cfcs = [
            e for e in cfc_entries
            if feature_number in e["enforcement_owners"]
        ]
        for entry in owning_cfcs:
            n = entry["number"]
            if n in tasks_tags:
                result.add(
                    f"tasks.md carries [CFC-{n}] enforcement task",
                    True,
                )
            else:
                result.add(
                    f"tasks.md carries [CFC-{n}] enforcement task",
                    False,
                    f"feature {identifier} is named in CFC-{n}'s Enforcement "
                    f"prose as artifact owner; tasks.md must contain a "
                    f"`[CFC-{n}]`-tagged task implementing the verifying "
                    f"artifact named in that Enforcement field",
                )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Validate spec-driven development artifacts.",
        epilog="Example: python validate_spec.py specs/F1-checkout-flow/",
    )
    parser.add_argument(
        "spec_dir",
        type=Path,
        help="Path to the spec directory (e.g., specs/F1-checkout-flow/)",
    )
    parser.add_argument(
        "--phase",
        choices=["spec", "design", "tasks", "all"],
        default="all",
        help="Which phase to validate (default: all existing files)",
    )
    parser.add_argument(
        "--approve",
        choices=["spec", "design", "tasks"],
        help="Approve a phase document (marks it approved with content hash)",
    )
    parser.add_argument(
        "--task-tick",
        action="store_true",
        help="Phase-4 task-tick re-stamp of tasks.md: suppress the re-approval "
        "reminder + pending-review marker (only valid with --approve tasks).",
    )
    parser.add_argument(
        "--decline-pending",
        action="store_true",
        help="Clear this spec dir's pending-review obligations — an explicit, "
        "auditable decision to skip the upstream panel re-review.",
    )
    parser.add_argument(
        "--language",
        choices=list(LANGUAGE_PROFILES.keys()),
        default=None,
        help="Project language for THIS run (default: persisted config, else "
        "auto-detect). Does not persist; use --set-language to persist.",
    )
    parser.add_argument(
        "--set-language",
        choices=list(LANGUAGE_PROFILES.keys()),
        default=None,
        help="Persist the project's stack to .sdd/architecture.json (the "
        "declare-once store) and exit. The single, explicit write path.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory for language detection (default: walk up from spec_dir)",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

    spec_dir = args.spec_dir.resolve()
    if not spec_dir.is_dir():
        print(f"Error: {spec_dir} is not a directory")
        sys.exit(2)

    # R7 mixed-state surfacing: a non-blocking nudge ONLY when a mixed dir is
    # actually renamer-fixable (the helper suppresses the nudge on a same-artifact
    # collision, where the validator is about to FAIL with the ambiguity detail).
    _warn = mixed_state_warning(str(args.spec_dir), spec_dir)
    if _warn:
        print(_warn)

    project_root = args.project_root.resolve() if args.project_root else None
    if project_root is not None and not project_root.is_dir():
        print(f"Error: --project-root {project_root} is not a directory")
        sys.exit(2)

    # --task-tick is the Phase-4 carve-out; it is meaningful ONLY on a tasks
    # re-stamp. Reject it anywhere else (fail-closed; Never-Do).
    if args.task_tick and args.approve != "tasks":
        print("Error: --task-tick is only valid with --approve tasks")
        sys.exit(2)

    # Handle --decline-pending: clear this spec dir's pending obligations. An
    # auditable user decision (logged to stdout), the validator-owned lifecycle
    # for the marker (no hand-edited JSON).
    # DEF-01 / RI-11 v1-posture: the bypass trace is stdout-audited + fail-closed
    # (the gate fires by default). A git-durable Trajectory tag for declines is a
    # recorded v2 enhancement, deliberately out of v1 scope.
    if args.decline_pending:
        root, spec_rel = _resolve_marker_root_and_key(spec_dir, project_root)
        try:
            removed = clear_pending_entries_for_prefix(root, spec_rel)
        except MarkerCorruptError as exc:
            print(
                f"Cannot decline: {exc}. The marker is corrupt; inspect or delete "
                f".sdd/pending-review.json manually."
            )
            sys.exit(1)
        if removed:
            noun = "entry" if len(removed) == 1 else "entries"
            print(
                f"Declined upstream panel re-review; cleared {len(removed)} pending "
                f"{noun}: {', '.join(removed)}"
            )
        else:
            print(f"No pending-review entries found for {spec_dir}.")
        sys.exit(0)

    # Handle --approve
    if args.approve:
        file_map = {"spec": "spec.md", "design": "design.md", "tasks": "tasks.md"}
        target = resolve_artifact(spec_dir, file_map[args.approve])
        if not target.is_file():
            print(f"Error: {target} does not exist")
            sys.exit(2)
        # Directory<->identifier cross-check gates ALL three approve targets
        # (spec/design/tasks). It reads the identifier from spec.md, so it runs
        # for design/tasks approvals too; a mismatch blocks approval before any
        # file is written.
        dir_check = check_dir_identifier(spec_dir)
        if not dir_check.passed:
            print(dir_check.summary())
            print(
                f"Refusing to approve {target.name}: spec-directory cross-check "
                f"FAILed. Fix the directory name or in-file identifier above."
            )
            sys.exit(1)
        approve_document(target, task_tick=args.task_tick, project_root=project_root)
        sys.exit(0)

    # Handle --set-language: the single, explicit write path for the declare-once
    # store. Deliberately separate from --approve — it touches NO content hash and
    # does NOT run during approval, so it cannot collide with the CFC cascade.
    if args.set_language:
        root = arch_find_project_root(spec_dir, project_root)
        written = write_arch_config(
            root,
            args.set_language,
            list(LANGUAGE_PROFILES.keys()),
            source="user",
        )
        print(f"Persisted stack '{args.set_language}' to {written}")
        sys.exit(0)

    # Resolve the stack via the shared resolver: explicit flag > persisted config
    # > marker auto-detect (which itself falls back to the neutral profile). This
    # is the SAME code path any other consumer uses, so the prose layer and the
    # script layer cannot drift to different answers.
    language, language_source = resolve_language(
        spec_dir,
        explicit=args.language,
        detector=detect_language,
        known_languages=list(LANGUAGE_PROFILES.keys()),
        project_root=project_root,
    )
    use_json = args.output == "json"

    if not use_json:
        print(f"Validating: {spec_dir}")
        print(f"Language:   {language} (from {language_source})\n")

    all_passed = True
    has_any_warnings = False
    json_output: dict = {
        "spec_dir": str(spec_dir),
        "language": language,
        "language_source": language_source,
        "phases": {},
    }
    validators = {
        "spec": ("Spec (spec.md)", lambda d: validate_spec(d)),
        "design": ("Design (design.md)", lambda d: validate_design(d, language)),
        "tasks": ("Tasks (tasks.md)", lambda d: validate_tasks(d, language)),
    }

    for phase_key, (label, validator) in validators.items():
        if args.phase not in ("all", phase_key):
            continue

        # In "all" mode, skip phases whose files don't exist yet
        _bare = "spec.md" if phase_key == "spec" else f"{phase_key}.md"
        expected_file = resolve_artifact(spec_dir, _bare)
        if args.phase == "all" and not expected_file.exists():
            continue

        result = validator(spec_dir)

        if not result.passed:
            status = "FAILED"
        elif result.has_warnings:
            status = "PASSED (with warnings)"
        else:
            status = "PASSED"

        if use_json:
            json_output["phases"][phase_key] = {
                "status": status,
                "checks": result.to_dict(),
            }
        else:
            print(f"{label}: {status}")
            print(result.summary())
            print()

        if not result.passed:
            all_passed = False
        if result.has_warnings:
            has_any_warnings = True

    # R2 (dispatch-level): reconcile pending-review ONCE for this spec dir,
    # regardless of --phase (so --phase design/tasks can't bypass the gate, and
    # an absent spec.md doesn't make a design/tasks obligation vanish). Surfaced
    # as a top-level `pending_review` result — uniform with validate_blueprint.
    root, spec_rel = _resolve_marker_root_and_key(spec_dir, project_root)
    pending_result = reconcile_to_result(
        root, spec_rel, decline_cmd=f"validate_spec.py {spec_dir} --decline-pending"
    )
    if pending_result.checks:
        if use_json:
            json_output["pending_review"] = pending_result.to_dict()
        else:
            print(
                f"Pending-review: "
                f"{'FAILED' if not pending_result.passed else 'PASSED'}"
            )
            print(pending_result.summary())
            print()
        if not pending_result.passed:
            all_passed = False

    if use_json:
        if all_passed and not has_any_warnings:
            json_output["result"] = "passed"
        elif all_passed:
            json_output["result"] = "passed_with_warnings"
        else:
            json_output["result"] = "failed"
        print(json.dumps(json_output, indent=2))
    else:
        if all_passed and not has_any_warnings:
            print("All validations passed.")
        elif all_passed and has_any_warnings:
            print("All validations passed with warnings. Review WARN items above.")
        else:
            print("Some validations failed. See FAIL items above.")

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    # Fail-closed (design.md:349): an uncaught ArtifactAmbiguityError from any
    # resolve_artifact site — including the no-`result` soft gates
    # (find_project_root, expected_file) and the --approve target — exits
    # non-zero BEFORE any content hash is stamped. The boundary is shared so a
    # new entrypoint can't forget it.
    run_cli_failclosed(main)
