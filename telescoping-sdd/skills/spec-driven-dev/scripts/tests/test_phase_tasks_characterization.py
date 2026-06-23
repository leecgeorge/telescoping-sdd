"""DEF-01 characterization (routed from design [DEF-01]).

`validate_spec.py --phase tasks` (i.e. `validate_tasks`) checks the PREVIOUS phase
(`design.md`) approval + `tasks.md` STRUCTURE only — it never checks `tasks.md`'s own
approval or hash coherence. This pins the load-bearing fact behind `plan-template.md`'s
corrected DEF-03 "machine (partial assist)" confirmation prose: a green `--phase tasks`
does NOT mean the feature shipped. If a future `validate_tasks` change added a tasks.md
self-approval/hash check, this characterization fails — signalling the template prose
needs updating — rather than letting the prose silently rot.
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


_DESIGN_BODY = """# Design: Demo

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

- [x] Approved to proceed to next phase
- **Content Hash:** `pending`
- **Hash basis:** v2
"""

_TASKS_BODY = """# Tasks: Demo

## Summary

| Task | Description | Requirement | Dependencies | Parallel | Status |
|------|-------------|-------------|--------------|----------|--------|
| T1 | Do the thing | R1 | None | No | Not Started |

### - [ ] T1: Do the thing

- **Requirement:** R1
- **Description:** Implement the thing.
- **Files:**
  - Modify: `src/thing.py`
- **Dependencies:** None
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN the thing,
    WHEN it runs,
    THEN it works.
- **Verification:** `pytest`

## Panel Review

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|
| 1 | 2026-06-01 | 0 | 0 | 0 | 0 | 0 | converged (0 HIGH) |

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [ ] Approved to proceed to implementation
- **Content Hash:** `pending`
- **Hash basis:** v2
"""


def _make_fixture(tmp_path: Path) -> Path:
    """Spec dir with an APPROVED, hash-coherent design.md (the previous phase) and a
    structurally-present but UNAPPROVED tasks.md. No spec.md, so `validate_cfc_consumer`
    adds no checks. Standalone-slug dir name avoids bound-form identifier expectations.
    """
    spec_dir = tmp_path / "demo"
    spec_dir.mkdir()
    # Make design.md hash-coherent: compute_content_hash neutralizes the checkbox + the
    # Content-Hash value, so any embedded value yields the same hash; embed it.
    h = vs.compute_content_hash(_DESIGN_BODY)
    (spec_dir / "design.md").write_text(
        _DESIGN_BODY.replace("`pending`", f"`{h}`", 1), encoding="utf-8"
    )
    (spec_dir / "tasks.md").write_text(_TASKS_BODY, encoding="utf-8")
    return spec_dir


def test_phase_tasks_checks_design_approval_not_tasks_own(tmp_path):
    spec_dir = _make_fixture(tmp_path)
    checks = vs.validate_tasks(spec_dir, language="generic").checks  # (name, sev, detail)

    # (1) It DOES verify the previous phase (design.md) is approved — and that PASSES,
    #     proving the approval surface --phase tasks actually checks is design.md.
    prev = [(n, sev) for n, sev, _ in checks if "previous phase (design.md)" in n]
    assert prev, f"no previous-phase (design.md) check: {[n for n, _, _ in checks]}"
    assert all(sev == "PASS" for _, sev in prev), prev

    # (2) It NEVER checks tasks.md's OWN approval or hash coherence (no such check).
    assert not any(
        "tasks.md" in n and ("approv" in n.lower() or "hash" in n.lower())
        for n, _, _ in checks
    ), [n for n, _, _ in checks if "tasks.md" in n]

    # (3) The UNAPPROVED tasks.md (pending hash, `- [ ]` box) causes NO approval-related
    #     FAIL — i.e. --phase tasks PASSES the approval surface despite tasks.md being
    #     unapproved. This is the fact DEF-03's template prose depends on.
    approval_fails = [
        (n, d) for n, sev, d in checks if sev == "FAIL" and "approv" in n.lower()
    ]
    assert approval_fails == [], approval_fails
