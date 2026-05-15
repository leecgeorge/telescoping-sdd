#!/usr/bin/env python3
"""Validate and approve project blueprint artifacts.

Checks that SCOPE.md, ARCHITECTURE.md, and PLAN.md have required sections,
no unresolved questions or decisions, and follow the expected structure.
Can also approve documents for phase transitions using content hashes
to detect post-approval edits.

Usage:
    python validate_blueprint.py <blueprint-directory>
    python validate_blueprint.py blueprint/ --phase scope
    python validate_blueprint.py blueprint/ --approve scope
    python validate_blueprint.py blueprint/ --output json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

# Locate shared helpers at telescoping-sdd/scripts/ — sibling of telescoping-sdd/skills/.
# Use sys.path.append (not insert) so this module never displaces the
# caller's sys.path[0].
_SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.append(str(_SHARED_SCRIPTS))

from blueprint_common import (  # noqa: E402
    PANEL_UNRESOLVED_DISPOSITION,
    Severity,
    UnresolvedMarker,
    ValidationResult,
    compute_content_hash,
    content_for_hashing,
    extract_panel_section,
    has_section,
    scan_unresolved_markers,
    section_has_content,
    validate_panel_review,
    verify_content_hash,
)


# ---------------------------------------------------------------------------
# Required sections per phase
# ---------------------------------------------------------------------------

SCOPE_REQUIRED_SECTIONS = [
    "Problem Statement",
    "Target Users",
    "Goals",
    "Non-Goals",
    "Constraints",
    "Success Criteria",
    "Panel Review",
]

ARCHITECTURE_REQUIRED_SECTIONS = [
    "System Overview",
    "Components",
    "Component Interactions",
    "Technology Choices",
    "Data Architecture",
    "External Dependencies",
    "Risks",
    "Panel Review",
]

PLAN_REQUIRED_SECTIONS = [
    "Feature Breakdown",
    "MVP Definition",
    "Feature Dependencies",
    "Implementation Order",
    "Milestones",
    "Panel Review",
]

# Regex to match feature entries like "### F1:" or "### F2:"
FEATURE_ENTRY_PATTERN = re.compile(r"^###\s+F\d+:", re.MULTILINE)

# Regex to match component entries like "### Component Name"
COMPONENT_ENTRY_PATTERN = re.compile(r"^###\s+\S+", re.MULTILINE)

# Regex to match feature IDs referenced in dependency/order tables
FEATURE_ID_PATTERN = re.compile(r"\bF(\d+)\b")

# Regex to match component references in feature breakdown
FEATURE_COMPONENT_REF = re.compile(r"\*\*Component:\*\*\s*(.+)")

# Regex to match acceptance criteria in features
FEATURE_ACCEPTANCE_CRITERIA = re.compile(r"\*\*Acceptance Criteria:\*\*", re.IGNORECASE)

# Regex to match risk entries in tables
RISK_ENTRY_PATTERN = re.compile(r"\|\s*R\d+\s*\|")


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------


def read_file(path: Path) -> Optional[str]:
    """Read file contents or return None if it doesn't exist."""
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return None


def validate_resolved(content: str, filename: str, result: ValidationResult) -> None:
    """Check that all questions, decisions, and markers are resolved."""
    by_kind: dict[str, list[str]] = {}
    for hit in scan_unresolved_markers(content):
        by_kind.setdefault(hit.kind, []).append(hit.text)

    unchecked = by_kind.get("unchecked_question", [])
    result.add(
        f"{filename} has no unresolved open questions",
        len(unchecked) == 0,
        f"{len(unchecked)} unchecked question(s) found" if unchecked else "",
    )

    tbds = by_kind.get("tbd", [])
    result.add(
        f"{filename} has no [TBD] decisions",
        len(tbds) == 0,
        f"{len(tbds)} [TBD] marker(s) found" if tbds else "",
    )

    markers = by_kind.get("unresolved_general", [])
    result.add(
        f"{filename} has no unresolved markers (TODO/FIXME/???)",
        len(markers) == 0,
        f"Found: {', '.join(markers)}" if markers else "",
        warn_only=True,
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


def check_approval(content: str, filename: str, result: ValidationResult) -> bool:
    """Check if a document is approved and the approval is still valid.

    Returns True if the document is approved and hash matches.
    """
    has_sect = bool(APPROVAL_SECTION_PATTERN.search(content))
    if not has_sect:
        result.add(
            f"{filename} has Approval section", False, "Missing ## Approval section"
        )
        return False

    result.add(f"{filename} has Approval section", True)

    checkbox_match = APPROVAL_CHECKBOX_PATTERN.search(content)
    is_approved = checkbox_match is not None and checkbox_match.group(1) == "x"
    result.add(f"{filename} is approved", is_approved)

    if not is_approved:
        return False

    hash_match = APPROVAL_HASH_PATTERN.search(content)
    if not hash_match:
        result.add(
            f"{filename} approval hash present", False, "No content hash found"
        )
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
    blueprint_dir: Path,
    current_phase: str,
    result: ValidationResult,
) -> None:
    """Verify the previous phase's document is approved before validating the current one."""
    phase_order = {
        "architecture": "SCOPE.md",
        "plan": "ARCHITECTURE.md",
    }
    prev_file = phase_order.get(current_phase)
    if prev_file is None:
        return  # scope has no previous phase

    prev_path = blueprint_dir / prev_file
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

def validate_scope(blueprint_dir: Path) -> ValidationResult:
    """Validate SCOPE.md for required sections and resolved questions."""
    result = ValidationResult()
    scope_path = blueprint_dir / "SCOPE.md"
    content = read_file(scope_path)

    result.add("SCOPE.md exists", content is not None, str(scope_path))
    if content is None:
        return result

    # Check all required sections exist
    for section in SCOPE_REQUIRED_SECTIONS:
        result.add(
            f"SCOPE.md has '{section}' section",
            has_section(content, section),
        )

    # Check for success criteria checkboxes
    has_checkboxes = bool(re.search(r"- \[[ x]\]", content))
    result.add(
        "SCOPE.md has success criteria checkboxes",
        has_checkboxes,
    )

    # Check for at least one target user defined
    user_sections = re.findall(r"^###\s+.+", content, re.MULTILINE)
    # Filter to only user sections (within Target Users)
    target_users_match = re.search(
        r"## Target Users\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if target_users_match:
        user_block = target_users_match.group(1)
        user_entries = re.findall(r"^###\s+.+", user_block, re.MULTILINE)
        result.add(
            "SCOPE.md defines at least one target user",
            len(user_entries) > 0,
            f"Found {len(user_entries)} user type(s)" if user_entries else "No user types defined",
        )
    else:
        result.add(
            "SCOPE.md defines at least one target user",
            False,
            "Target Users section not found or empty",
        )

    # Check for at least one goal
    goals_match = re.search(r"## Goals\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if goals_match:
        goals_block = goals_match.group(1)
        goal_items = re.findall(r"^-\s+.+", goals_block, re.MULTILINE)
        result.add(
            "SCOPE.md has at least one goal",
            len(goal_items) > 0,
        )
    else:
        result.add("SCOPE.md has at least one goal", False)

    # Check for at least one non-goal
    nongoals_match = re.search(
        r"## Non-Goals\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if nongoals_match:
        nongoals_block = nongoals_match.group(1)
        nongoal_items = re.findall(r"^-\s+.+", nongoals_block, re.MULTILINE)
        result.add(
            "SCOPE.md has at least one non-goal",
            len(nongoal_items) > 0,
        )
    else:
        result.add("SCOPE.md has at least one non-goal", False)

    # Check for at least one constraint
    constraints_match = re.search(
        r"## Constraints\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if constraints_match:
        constraints_block = constraints_match.group(1)
        # Look for table rows (pipe-delimited) beyond the header
        table_rows = re.findall(
            r"^\|[^|]+\|[^|]+\|", constraints_block, re.MULTILINE
        )
        # Subtract header and separator rows
        has_constraint_data = len(table_rows) > 2
        result.add(
            "SCOPE.md has at least one constraint defined",
            has_constraint_data,
            warn_only=True,
        )

    validate_resolved(content, "SCOPE.md", result)
    validate_panel_review(content, "SCOPE.md", result)

    return result


def validate_architecture(blueprint_dir: Path) -> ValidationResult:
    """Validate ARCHITECTURE.md for required sections and resolved questions."""
    result = ValidationResult()

    check_previous_phase_approved(blueprint_dir, "architecture", result)

    arch_path = blueprint_dir / "ARCHITECTURE.md"
    content = read_file(arch_path)

    result.add("ARCHITECTURE.md exists", content is not None, str(arch_path))
    if content is None:
        return result

    # Check all required sections exist
    for section in ARCHITECTURE_REQUIRED_SECTIONS:
        result.add(
            f"ARCHITECTURE.md has '{section}' section",
            has_section(content, section),
        )

    # Check for at least one component defined (### heading within Components section)
    components_match = re.search(
        r"## Components\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if components_match:
        component_block = components_match.group(1)
        component_entries = re.findall(r"^###\s+.+", component_block, re.MULTILINE)
        result.add(
            "ARCHITECTURE.md defines at least one component",
            len(component_entries) > 0,
            f"Found {len(component_entries)} component(s)"
            if component_entries
            else "No components defined",
        )
    else:
        result.add(
            "ARCHITECTURE.md defines at least one component",
            False,
            "Components section not found",
        )

    # Check for at least one technology choice in table
    tech_match = re.search(
        r"## Technology Choices\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if tech_match:
        tech_block = tech_match.group(1)
        table_rows = re.findall(r"^\|[^|]+\|", tech_block, re.MULTILINE)
        has_tech_data = len(table_rows) > 2  # header + separator + at least one row
        result.add(
            "ARCHITECTURE.md has at least one technology choice",
            has_tech_data,
        )
    else:
        result.add(
            "ARCHITECTURE.md has at least one technology choice",
            False,
        )

    # Check for at least one risk identified
    has_risks = bool(RISK_ENTRY_PATTERN.search(content))
    result.add(
        "ARCHITECTURE.md identifies at least one risk",
        has_risks,
    )

    # Check for component interaction details (table or diagram)
    interactions_match = re.search(
        r"## Component Interactions\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if interactions_match:
        interaction_block = interactions_match.group(1)
        has_diagram = bool(re.search(r"```", interaction_block))
        has_table = bool(re.search(r"\|.*\|.*\|", interaction_block))
        result.add(
            "ARCHITECTURE.md has component interaction details (diagram or table)",
            has_diagram or has_table,
            warn_only=True,
        )

    validate_resolved(content, "ARCHITECTURE.md", result)
    validate_panel_review(content, "ARCHITECTURE.md", result)

    return result


def validate_plan(blueprint_dir: Path) -> ValidationResult:
    """Validate PLAN.md for required sections and resolved questions."""
    result = ValidationResult()

    check_previous_phase_approved(blueprint_dir, "plan", result)

    plan_path = blueprint_dir / "PLAN.md"
    content = read_file(plan_path)

    result.add("PLAN.md exists", content is not None, str(plan_path))
    if content is None:
        return result

    # Check all required sections exist
    for section in PLAN_REQUIRED_SECTIONS:
        result.add(
            f"PLAN.md has '{section}' section",
            has_section(content, section),
        )

    # Check for feature entries (### F1:, F2:, etc.)
    features = FEATURE_ENTRY_PATTERN.findall(content)
    result.add(
        "PLAN.md has feature entries (### F1:, F2:, ...)",
        len(features) > 0,
        f"Found {len(features)} feature(s)" if features else "No features found",
    )

    # Check that features have acceptance criteria
    has_ac = bool(FEATURE_ACCEPTANCE_CRITERIA.search(content))
    result.add(
        "PLAN.md features have acceptance criteria",
        has_ac,
    )

    # Check that features reference architecture components
    has_component_refs = bool(FEATURE_COMPONENT_REF.search(content))
    result.add(
        "PLAN.md features reference architecture components",
        has_component_refs,
        warn_only=True,
    )

    # Check MVP definition contains feature references
    mvp_match = re.search(
        r"## MVP Definition\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if mvp_match:
        mvp_block = mvp_match.group(1)
        mvp_features = FEATURE_ID_PATTERN.findall(mvp_block)
        result.add(
            "PLAN.md MVP definition references specific features",
            len(mvp_features) > 0,
            f"MVP references {len(mvp_features)} feature(s)"
            if mvp_features
            else "No feature references in MVP definition",
        )
    else:
        result.add(
            "PLAN.md MVP definition references specific features",
            False,
        )

    # Check implementation order has entries
    order_match = re.search(
        r"## Implementation Order\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if order_match:
        order_block = order_match.group(1)
        order_features = FEATURE_ID_PATTERN.findall(order_block)
        result.add(
            "PLAN.md implementation order references features",
            len(order_features) > 0,
        )

        # Check that all defined features appear in implementation order
        defined_features = set(
            re.findall(r"^###\s+F(\d+):", content, re.MULTILINE)
        )
        ordered_features = set(order_features)
        unordered = defined_features - ordered_features
        if unordered:
            missing_labels = ", ".join(
                f"F{f}" for f in sorted(unordered, key=int)
            )
            result.add(
                "PLAN.md all features appear in implementation order",
                False,
                f"Missing from order: {missing_labels}",
                warn_only=True,
            )
        else:
            result.add(
                "PLAN.md all features appear in implementation order",
                True,
            )
    else:
        result.add(
            "PLAN.md implementation order references features",
            False,
        )

    # Check feature dependency coverage
    deps_match = re.search(
        r"## Feature Dependencies\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if deps_match:
        deps_block = deps_match.group(1)
        dep_features = set(FEATURE_ID_PATTERN.findall(deps_block))
        defined_features = set(
            re.findall(r"^###\s+F(\d+):", content, re.MULTILINE)
        )
        missing_deps = defined_features - dep_features
        if missing_deps:
            missing_labels = ", ".join(
                f"F{f}" for f in sorted(missing_deps, key=int)
            )
            result.add(
                "PLAN.md all features appear in dependency graph",
                False,
                f"Missing from dependencies: {missing_labels}",
                warn_only=True,
            )
        else:
            result.add(
                "PLAN.md all features appear in dependency graph",
                True,
            )

    # Check milestones have feature references
    milestones_match = re.search(
        r"## Milestones\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if milestones_match:
        milestones_block = milestones_match.group(1)
        milestone_entries = re.findall(
            r"^###\s+Milestone\s+\d+:", milestones_block, re.MULTILINE
        )
        milestone_features = FEATURE_ID_PATTERN.findall(milestones_block)
        result.add(
            "PLAN.md has milestones with feature assignments",
            len(milestone_entries) > 0 and len(milestone_features) > 0,
        )
    else:
        result.add(
            "PLAN.md has milestones with feature assignments",
            False,
        )

    validate_resolved(content, "PLAN.md", result)
    validate_panel_review(content, "PLAN.md", result)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Validate project blueprint artifacts.",
        epilog="Example: python validate_blueprint.py blueprint/",
    )
    parser.add_argument(
        "blueprint_dir",
        type=Path,
        help="Path to the blueprint directory (e.g., blueprint/)",
    )
    parser.add_argument(
        "--phase",
        choices=["scope", "architecture", "plan", "all"],
        default="all",
        help="Which phase to validate (default: all existing files)",
    )
    parser.add_argument(
        "--approve",
        choices=["scope", "architecture", "plan"],
        help="Approve a phase document (marks it approved with content hash)",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

    blueprint_dir = args.blueprint_dir.resolve()
    if not blueprint_dir.is_dir():
        print(f"Error: {blueprint_dir} is not a directory")
        sys.exit(2)

    # Handle --approve
    if args.approve:
        file_map = {
            "scope": "SCOPE.md",
            "architecture": "ARCHITECTURE.md",
            "plan": "PLAN.md",
        }
        target = blueprint_dir / file_map[args.approve]
        if not target.is_file():
            print(f"Error: {target} does not exist")
            sys.exit(2)
        approve_document(target)
        sys.exit(0)

    use_json = args.output == "json"

    if not use_json:
        print(f"Validating: {blueprint_dir}\n")

    all_passed = True
    has_any_warnings = False
    json_output: dict = {
        "blueprint_dir": str(blueprint_dir),
        "phases": {},
    }

    phase_file_map = {
        "scope": "SCOPE.md",
        "architecture": "ARCHITECTURE.md",
        "plan": "PLAN.md",
    }

    validators = {
        "scope": ("Scope (SCOPE.md)", lambda d: validate_scope(d)),
        "architecture": (
            "Architecture (ARCHITECTURE.md)",
            lambda d: validate_architecture(d),
        ),
        "plan": ("Plan (PLAN.md)", lambda d: validate_plan(d)),
    }

    for phase_key, (label, validator) in validators.items():
        if args.phase not in ("all", phase_key):
            continue

        # In "all" mode, skip phases whose files don't exist yet
        expected_file = blueprint_dir / phase_file_map[phase_key]
        if args.phase == "all" and not expected_file.exists():
            continue

        result = validator(blueprint_dir)

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
