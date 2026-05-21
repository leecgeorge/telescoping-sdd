#!/usr/bin/env python3
"""Validate and approve spec-driven development artifacts.

Checks that spec.md, design.md, and tasks.md have required sections
and follow the expected structure. Can also approve documents for
phase transitions using content hashes to detect post-approval edits.

Supports Python and Java projects via --language flag. If omitted,
auto-detects by looking for pom.xml/build.gradle (Java) or
pyproject.toml/setup.py (Python) in the project root.

Usage:
    python validate_spec.py <spec-directory>
    python validate_spec.py specs/my-feature/ --phase spec
    python validate_spec.py specs/my-feature/ --approve spec
    python validate_spec.py specs/my-feature/ --language java
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
    Severity,
    ValidationResult,
    compute_content_hash,
    content_for_hashing,
    trim_trajectory_table,
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
}


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
GWT_PATTERN = re.compile(r"GIVEN\s+.+\n\s*WHEN\s+.+\n\s*THEN\s+.+", re.MULTILINE)

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
        return "python"  # default fallback

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
    return "python"  # default fallback


def get_profile(language: str) -> dict:
    """Get the language profile, falling back to Python."""
    return LANGUAGE_PROFILES.get(language, LANGUAGE_PROFILES["python"])


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

APPROVAL_SECTION_PATTERN = re.compile(
    r"^## Approval\s*\n.*?(?=\n^## |\Z)",
    re.MULTILINE | re.DOTALL,
)
APPROVAL_HASH_PATTERN = re.compile(r"\*\*Content Hash:\*\*\s*`([a-f0-9]+|pending)`")
APPROVAL_CHECKBOX_PATTERN = re.compile(r"- \[( |x)\] Approved to proceed")


# `content_for_hashing` and `compute_content_hash` are imported from
# blueprint_common (above). They share the same implementation as the
# producer side, ensuring hash coherence across both validators.


def check_approval(content: str, filename: str, result: ValidationResult) -> bool:
    """Check if a document is approved and the approval is still valid.

    Returns True if the document is approved and hash matches.
    """
    has_sect = bool(APPROVAL_SECTION_PATTERN.search(content))
    if not has_sect:
        result.add(f"{filename} has Approval section", False, "Missing ## Approval section")
        return False

    result.add(f"{filename} has Approval section", True)

    checkbox_match = APPROVAL_CHECKBOX_PATTERN.search(content)
    is_approved = checkbox_match is not None and checkbox_match.group(1) == "x"
    result.add(f"{filename} is approved", is_approved)

    if not is_approved:
        return False

    hash_match = APPROVAL_HASH_PATTERN.search(content)
    if not hash_match:
        result.add(f"{filename} approval hash present", False, "No content hash found")
        return False

    stored_hash = hash_match.group(1)
    current_hash = compute_content_hash(content)
    hashes_match = stored_hash == current_hash
    result.add(
        f"{filename} has not been modified since approval",
        hashes_match,
        f"Stored: {stored_hash}, Current: {current_hash}" if not hashes_match else "",
    )
    return hashes_match


def approve_document(file_path: Path) -> None:
    """Mark a document as approved by checking the box and writing the content hash.

    Writes are atomic (temp-file + os.replace) to guard against partial-state
    corruption on Ctrl-C / disk-full / process kill mid-write.
    """
    content = file_path.read_text(encoding="utf-8")

    # Trim the `### Trajectory` table to the latest 15 data rows BEFORE
    # computing the document hash — the trimmed table is part of the
    # approved content. Older rows are replaced with a single elided
    # summary row at the top of the data section; re-approval merges
    # the existing elided count with new elisions.
    content = trim_trajectory_table(content)

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


def check_previous_phase_approved(
    spec_dir: Path, current_phase: str, result: ValidationResult,
) -> None:
    """Verify the previous phase's document is approved before validating the current one."""
    phase_order = {"design": "spec.md", "tasks": "design.md"}
    prev_file = phase_order.get(current_phase)
    if prev_file is None:
        return  # spec has no previous phase

    prev_path = spec_dir / prev_file
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


# ---------------------------------------------------------------------------
# Phase validators
# ---------------------------------------------------------------------------

def validate_spec(spec_dir: Path) -> ValidationResult:
    """Validate spec.md for required sections."""
    result = ValidationResult()
    spec_path = spec_dir / "spec.md"
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

    return result


def validate_design(spec_dir: Path, language: str = "python") -> ValidationResult:
    """Validate design.md for required sections."""
    result = ValidationResult()
    profile = get_profile(language)

    check_previous_phase_approved(spec_dir, "design", result)

    design_path = spec_dir / "design.md"
    content = read_file(design_path)

    result.add("design.md exists", content is not None, str(design_path))
    if content is None:
        return result

    for section in DESIGN_REQUIRED_SECTIONS:
        result.add(
            f"design.md has '{section}' section",
            has_section(content, section),
        )

    # Check for type annotations (language-aware, advisory)
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


def validate_tasks(spec_dir: Path, language: str = "python") -> ValidationResult:
    """Validate tasks.md for proper task entries."""
    result = ValidationResult()
    profile = get_profile(language)

    check_previous_phase_approved(spec_dir, "tasks", result)

    tasks_path = spec_dir / "tasks.md"
    content = read_file(tasks_path)

    result.add("tasks.md exists", content is not None, str(tasks_path))
    if content is None:
        return result

    # Count task entries
    tasks = TASK_ENTRY_PATTERN.findall(content)
    result.add(
        "tasks.md has task entries (### T1:, T2:, ...)",
        len(tasks) > 0,
        f"Found {len(tasks)} task(s)" if tasks else "No tasks found",
    )

    # Check for summary table
    has_summary = bool(re.search(r"\|\s*Task\s*\|.*Status\s*\|", content, re.IGNORECASE))
    result.add(
        "tasks.md has summary table with status",
        has_summary,
    )

    # Check for requirement traceability
    has_req = bool(re.search(r"\*\*Requirement:\*\*\s*R\d+", content))
    result.add(
        "tasks.md tasks have requirement traceability (R1, R2, ...)",
        has_req,
    )

    # Requirement coverage — check all spec R-numbers are covered by tasks
    spec_content = read_file(spec_dir / "spec.md")
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

    # Check that tasks have acceptance criteria
    has_ac = bool(re.search(r"Acceptance Criteria", content, re.IGNORECASE))
    result.add(
        "tasks.md tasks have acceptance criteria",
        has_ac,
    )

    # Check for GIVEN/WHEN/THEN in acceptance criteria
    has_gwt = bool(GWT_PATTERN.search(content))
    result.add(
        "tasks.md acceptance criteria use GIVEN/WHEN/THEN format",
        has_gwt,
        "At least one GIVEN/WHEN/THEN block expected" if not has_gwt else "",
    )

    # Check for dependency information
    has_deps = bool(re.search(r"Dependenc", content, re.IGNORECASE))
    result.add(
        "tasks.md tasks have dependency info",
        has_deps,
    )

    # Check for verification commands
    has_verify = bool(re.search(r"\*\*Verification:\*\*", content))
    result.add(
        "tasks.md tasks have verification commands",
        has_verify,
    )

    # Check for test function/method names (language-aware, advisory)
    has_test_names = bool(profile["test_name_pattern"].search(content))
    result.add(
        "tasks.md tasks have specific test function/method names",
        has_test_names,
        warn_only=True,
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
        if (candidate / "blueprint" / "PLAN.md").is_file():
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
    spec_path = spec_dir / "spec.md"
    spec_content = read_file(spec_path)
    if spec_content is None:
        return

    id_match = PLAN_FEATURE_ID_LINE_RE.search(spec_content)
    identifier = id_match.group(1) if id_match else None

    project_root = find_project_root(spec_dir)
    plan_content = (
        read_file(project_root / "blueprint" / "PLAN.md") if project_root else None
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
        epilog="Example: python validate_spec.py specs/my-feature/",
    )
    parser.add_argument(
        "spec_dir",
        type=Path,
        help="Path to the spec directory (e.g., specs/my-feature/)",
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
        "--language",
        choices=list(LANGUAGE_PROFILES.keys()),
        default=None,
        help="Project language (default: auto-detect from project files)",
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

    project_root = args.project_root.resolve() if args.project_root else None
    if project_root is not None and not project_root.is_dir():
        print(f"Error: --project-root {project_root} is not a directory")
        sys.exit(2)

    # Handle --approve
    if args.approve:
        file_map = {"spec": "spec.md", "design": "design.md", "tasks": "tasks.md"}
        target = spec_dir / file_map[args.approve]
        if not target.is_file():
            print(f"Error: {target} does not exist")
            sys.exit(2)
        approve_document(target)
        sys.exit(0)

    # Detect or use specified language
    language = args.language or detect_language(spec_dir, project_root)
    use_json = args.output == "json"

    if not use_json:
        print(f"Validating: {spec_dir}")
        print(f"Language:   {language}\n")

    all_passed = True
    has_any_warnings = False
    json_output: dict = {
        "spec_dir": str(spec_dir),
        "language": language,
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
        expected_file = spec_dir / f"{phase_key}.md" if phase_key != "spec" else spec_dir / "spec.md"
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
    main()
