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
import re
import sys
from pathlib import Path
from typing import Optional


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


# ---------------------------------------------------------------------------
# Validation result with severity levels
# ---------------------------------------------------------------------------

class Severity:
    FAIL = "FAIL"
    WARN = "WARN"
    PASS = "PASS"


class ValidationResult:
    def __init__(self):
        self.checks: list[tuple[str, str, str]] = []  # (name, severity, detail)

    def add(self, name: str, passed: bool, detail: str = "", warn_only: bool = False):
        """Add a check result.

        Args:
            name: Description of the check.
            passed: Whether the check passed.
            detail: Additional detail for failures/warnings.
            warn_only: If True, a failure is recorded as WARN instead of FAIL.
        """
        if passed:
            self.checks.append((name, Severity.PASS, detail))
        elif warn_only:
            self.checks.append((name, Severity.WARN, detail))
        else:
            self.checks.append((name, Severity.FAIL, detail))

    @property
    def passed(self) -> bool:
        """True if no FAIL-level checks exist (warnings are OK)."""
        return all(sev != Severity.FAIL for _, sev, _ in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(sev == Severity.WARN for _, sev, _ in self.checks)

    def summary(self) -> str:
        lines = []
        for name, severity, detail in self.checks:
            line = f"  [{severity}] {name}"
            if detail:
                line += f" — {detail}"
            lines.append(line)
        return "\n".join(lines)

    def to_dict(self) -> list[dict]:
        """Return checks as a list of dicts for JSON output."""
        return [
            {"name": name, "status": severity, "detail": detail}
            for name, severity, detail in self.checks
        ]


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


def _content_for_hashing(content: str) -> str:
    """Return document content with only the dynamic approval values neutralized.

    Replaces the checkbox state and hash value with fixed placeholders so that
    approving a document doesn't change its hash, but any other edit does.
    """
    result = re.sub(r"- \[[ x]\] Approved to proceed", "- [ ] Approved to proceed", content)
    result = re.sub(r"\*\*Content Hash:\*\*\s*`[^`]*`", "**Content Hash:** `pending`", result)
    return result.rstrip()


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of document content (excluding approval section)."""
    body = _content_for_hashing(content)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


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
    """Mark a document as approved by checking the box and writing the content hash."""
    content = file_path.read_text(encoding="utf-8")

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

    file_path.write_text(content, encoding="utf-8")
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

    return result


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
