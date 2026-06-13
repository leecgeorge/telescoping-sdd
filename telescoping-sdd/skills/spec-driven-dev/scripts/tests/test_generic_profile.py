"""Tests for the obstacle-A fix: neutral 'generic' language profile + fallback.

Covers the behaviour added so that a non-Python/Java project (infrastructure,
static site, Claude-skill authoring, etc.) is no longer silently mislabelled as
Python and no longer fired the two language-specific advisory warnings:

  1. detect_language() resolves to the neutral fallback (not "python") when no
     recognized language marker is found.
  2. get_profile() falls back to the neutral profile for any unknown key.
  3. The "generic" profile disables the design type-annotation advisory check.
  4. The "generic" profile disables the tasks test-function-name advisory check.
  5. Python and Java profiles are unchanged (no regression): their advisory
     checks still run.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _load_validate_spec():
    scripts_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(scripts_dir))
    if "validate_spec" in sys.modules:
        return importlib.reload(sys.modules["validate_spec"])
    return importlib.import_module("validate_spec")


vs = _load_validate_spec()


def _check(result, name_substr: str):
    """Return (severity, detail) for the first check whose name contains the
    substring, or None if no such check exists (used to assert a check was
    SKIPPED, i.e. never emitted)."""
    for name, sev, detail in result.checks:
        if name_substr in name:
            return sev, detail
    return None


# --- design.md (type-annotation advisory) -------------------------------------

DESIGN_BODY = """# Design: Demo

**Spec:** `specs/demo/spec.md`

## Goals and Non-Goals
## Architecture Decisions
## Component Design
## Data Models
## Interfaces
## Error Handling
## Testing Strategy
## File Structure
## Dependencies
## Integration Points
## Risks
## Implementation Sequence

## Panel Review

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|
| 1 | 2026-06-01 | 0 | 0 | 0 | 0 | 0 | clean |

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [ ] Approved to proceed to next phase
- **Content Hash:** `pending`
"""


def _write_design(tmp_path: Path) -> Path:
    spec_dir = tmp_path / "demo"
    spec_dir.mkdir()
    (spec_dir / "design.md").write_text(DESIGN_BODY, encoding="utf-8")
    return spec_dir


def test_design_type_check_skipped_for_generic(tmp_path):
    spec_dir = _write_design(tmp_path)
    res = vs.validate_design(spec_dir, language="generic")
    # The type-annotation advisory must be ENTIRELY ABSENT, not a passing/failing row.
    assert _check(res, "type annotations") is None


def test_design_type_check_runs_for_python(tmp_path):
    spec_dir = _write_design(tmp_path)
    res = vs.validate_design(spec_dir, language="python")
    hit = _check(res, "type annotations")
    assert hit is not None, "python must still run the type-annotation advisory"
    # DESIGN_BODY has no type annotations, so it should WARN (advisory, not FAIL).
    assert hit[0] == "WARN"


def test_design_type_check_runs_for_java(tmp_path):
    spec_dir = _write_design(tmp_path)
    res = vs.validate_design(spec_dir, language="java")
    assert _check(res, "type annotations") is not None


# --- tasks.md (test-function-name advisory) -----------------------------------

TASKS_BODY = """# Tasks: Demo

## Summary

| Task | Description | Requirement | Dependencies | Parallel | Status |
|------|-------------|-------------|--------------|----------|--------|
| T1 | a | R1 | None | No | Not Started |

## Phase 1

### - [ ] T1: Do the thing

- **Requirement:** R1
- **Description:** do it
- **Files:**
  - Create: `infra/deploy.sh`
- **Dependencies:** None
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN a precondition
    WHEN an action occurs
    THEN a result holds
- **Verification:** `bash infra/deploy.sh && echo OK`

## Panel Review

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|
| 1 | 2026-06-01 | 0 | 0 | 0 | 0 | 0 | clean |

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [ ] Approved to proceed to implementation
- **Content Hash:** `pending`
"""


def _write_tasks(tmp_path: Path) -> Path:
    spec_dir = tmp_path / "demo"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_BODY, encoding="utf-8")
    return spec_dir


def test_tasks_test_name_check_skipped_for_generic(tmp_path):
    spec_dir = _write_tasks(tmp_path)
    res = vs.validate_tasks(spec_dir, language="generic")
    # The test-function-name advisory must be entirely absent for generic.
    assert _check(res, "names test functions/methods") is None


def test_tasks_test_name_check_runs_for_python(tmp_path):
    spec_dir = _write_tasks(tmp_path)
    res = vs.validate_tasks(spec_dir, language="python")
    hit = _check(res, "names test functions/methods")
    assert hit is not None, "python must still run the test-name advisory"
    # The single task names no `test_*()` function, so it should WARN.
    assert hit[0] == "WARN"


# --- detection / profile fallback ---------------------------------------------

def test_detect_language_falls_back_to_neutral_not_python(tmp_path):
    # An empty tree with no language markers anywhere up the chain.
    spec_dir = tmp_path / "specs" / "feature"
    spec_dir.mkdir(parents=True)
    assert vs.detect_language(spec_dir) == vs.NEUTRAL_LANGUAGE
    assert vs.NEUTRAL_LANGUAGE != "python"


def test_detect_language_project_root_falls_back_to_neutral(tmp_path):
    assert vs.detect_language(tmp_path, project_root=tmp_path) == vs.NEUTRAL_LANGUAGE


def test_detect_language_still_finds_python(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert vs.detect_language(tmp_path, project_root=tmp_path) == "python"


def test_detect_language_still_finds_java(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    assert vs.detect_language(tmp_path, project_root=tmp_path) == "java"


def test_detect_language_polyglot_tie_prints_notice(tmp_path, capsys):
    # Both Python and Java markers in the same dir: resolves to python (declaration
    # order) AND prints a one-line notice naming both, recommending --set-language.
    (tmp_path / "requirements.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    assert vs.detect_language(tmp_path, project_root=tmp_path) == "python"
    err = capsys.readouterr().err
    assert "multiple stacks" in err
    assert "python" in err and "java" in err
    assert "--set-language" in err


def test_detect_language_single_marker_is_silent(tmp_path, capsys):
    # No tie -> no notice (only fires when more than one stack matches).
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert vs.detect_language(tmp_path, project_root=tmp_path) == "python"
    assert capsys.readouterr().err == ""


def test_get_profile_unknown_key_falls_back_to_generic(tmp_path):
    # An as-yet-unsupported language (e.g. typescript) must NOT resolve to python.
    prof = vs.get_profile("typescript")
    assert prof is vs.LANGUAGE_PROFILES[vs.NEUTRAL_LANGUAGE]
    assert prof["type_pattern"] is None
    assert prof["test_name_pattern"] is None


def test_generic_profile_is_never_auto_detected(tmp_path):
    # generic carries no markers, so it can only be reached via the explicit
    # fallback, never matched as a positive detection.
    prof = vs.LANGUAGE_PROFILES["generic"]
    assert prof["project_markers"] == []
    assert prof["dir_markers"] == []
