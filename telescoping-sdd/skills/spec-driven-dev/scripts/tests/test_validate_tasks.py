"""Tests for validate_tasks() per-task field enforcement in validate_spec.py.

These cover the per-task iteration: a required field present on only ONE task
must no longer satisfy the check for ALL tasks (the prior document-wide
`re.search` behaviour), and a failing check must name the offending task IDs.
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

ALL_FIELDS = (
    "Requirement",
    "Description",
    "Files",
    "Dependencies",
    "Parallel",
    "Tests",
    "Verification",
)


def _task(tid: str, fields=ALL_FIELDS) -> str:
    """Build one task body. Acceptance Criteria (+GWT) is always included; the
    other fields are present only if listed in `fields`."""
    lines = [f"### - [ ] {tid}: Title {tid}", ""]
    optional = {
        "Requirement": "- **Requirement:** R1",
        "Description": f"- **Description:** do {tid}",
        "Files": "- **Files:**\n  - Create: `src/x.py`",
        "Dependencies": "- **Dependencies:** None",
        "Parallel": "- **Parallel:** No",
    }
    for key in ("Requirement", "Description", "Files", "Dependencies", "Parallel"):
        if key in fields:
            lines.append(optional[key])
    lines += [
        "- **Acceptance Criteria:**",
        "  - GIVEN a precondition",
        "    WHEN an action occurs",
        "    THEN a result holds",
    ]
    if "Tests" in fields:
        lines.append("- **Tests:**\n  - `test_x()` — checks x")
    if "Verification" in fields:
        lines.append("- **Verification:** `pytest -q`")
    lines.append("")
    return "\n".join(lines)


def _doc(*task_blocks: str) -> str:
    head = (
        "# Tasks: Demo\n\n## Summary\n\n"
        "| Task | Description | Requirement | Dependencies | Parallel | Status |\n"
        "|------|-------------|-------------|--------------|----------|--------|\n"
        "| T1 | a | R1 | None | No | Not Started |\n\n"
        "## Phase 1\n\n"
    )
    return head + "\n".join(task_blocks) + "\n"


def _check(result, name_substr: str):
    for name, sev, detail in result.checks:
        if name_substr in name:
            return sev, detail
    raise AssertionError(f"no check matching {name_substr!r}")


def test_all_fields_present_passes_each_per_task_check(tmp_path):
    (tmp_path / "tasks.md").write_text(
        _doc(_task("T1"), _task("T2")), encoding="utf-8"
    )
    res = vs.validate_tasks(tmp_path)
    for field in ("Requirement", "Description", "Files", "Dependencies", "Parallel", "Verification"):
        sev, _ = _check(res, f"every task has **{field}:**")
        assert sev == "PASS", field
    assert _check(res, "every task has **Acceptance Criteria**")[0] == "PASS"
    assert _check(res, "GIVEN/WHEN/THEN")[0] == "PASS"


def test_missing_files_in_one_task_is_flagged_with_task_id(tmp_path):
    t2 = _task("T2", fields=[f for f in ALL_FIELDS if f != "Files"])
    (tmp_path / "tasks.md").write_text(_doc(_task("T1"), t2), encoding="utf-8")
    res = vs.validate_tasks(tmp_path)
    sev, detail = _check(res, "every task has **Files:**")
    assert sev == "FAIL"
    assert "T2" in detail and "T1" not in detail


def test_per_task_not_document_wide(tmp_path):
    # T1 carries every field; T2 carries only Requirement (+AC). A document-wide
    # search would PASS (T1 satisfies it); per-task iteration must FAIL on T2.
    t2 = _task("T2", fields=["Requirement"])
    (tmp_path / "tasks.md").write_text(_doc(_task("T1"), t2), encoding="utf-8")
    res = vs.validate_tasks(tmp_path)
    for field in ("Description", "Files", "Dependencies", "Parallel", "Verification"):
        sev, detail = _check(res, f"every task has **{field}:**")
        assert sev == "FAIL", field
        assert "T2" in detail


def test_missing_test_names_is_advisory_warn_not_fail(tmp_path):
    # Pass language="python" explicitly: the test-name advisory only runs for a
    # language profile with a test_name_pattern. The default profile is now the
    # neutral "generic" (which deliberately skips this advisory), so this test
    # states the python intent it is actually exercising.
    t1 = _task("T1", fields=[f for f in ALL_FIELDS if f != "Tests"])
    (tmp_path / "tasks.md").write_text(_doc(t1), encoding="utf-8")
    res = vs.validate_tasks(tmp_path, language="python")
    sev, _ = _check(res, "every task names test functions/methods")
    assert sev == "WARN"


def test_gwt_pattern_accepts_bulleted_form(tmp_path):
    """A bullet-style GIVEN/WHEN/THEN (which the CFC THEN-matcher accepts) must
    also satisfy the general GWT gate, so a spec is not failed for valid
    bulleted acceptance criteria (review finding Scripts D5-5)."""
    bulleted = "- GIVEN a precondition\n- WHEN an action occurs\n- THEN a result holds"
    plain = "GIVEN a precondition\n  WHEN an action occurs\n  THEN a result holds"
    assert vs.GWT_PATTERN.search(bulleted)
    assert vs.GWT_PATTERN.search(plain)


def _spec_with_requirements(*rnums: int) -> str:
    """A spec.md whose ## Requirements has one `### R<n>:` heading per number."""
    reqs = "\n\n".join(f"### R{n}: requirement {n}" for n in rnums)
    return f"# Spec\n\n## Requirements\n\n{reqs}\n"


def test_requirement_coverage_all_covered_passes(tmp_path):
    """R3.6: the requirement-coverage cross-check (tasks `**Requirement:**` R-nums
    vs spec `### R<n>:`) — previously never executed because fixtures wrote no
    sibling spec.md. Full coverage -> PASS."""
    (tmp_path / "tasks.md").write_text(_doc(_task("T1")), encoding="utf-8")  # references R1
    (tmp_path / "spec.md").write_text(_spec_with_requirements(1), encoding="utf-8")
    res = vs.validate_tasks(tmp_path)
    sev, detail = _check(res, "covers all requirements")
    assert sev == "PASS"
    assert "1 requirement(s) covered" in detail


def test_requirement_coverage_uncovered_warns(tmp_path):
    """An uncovered spec requirement -> WARN naming the missing R-number."""
    (tmp_path / "tasks.md").write_text(_doc(_task("T1")), encoding="utf-8")  # references R1 only
    (tmp_path / "spec.md").write_text(_spec_with_requirements(1, 2), encoding="utf-8")
    res = vs.validate_tasks(tmp_path)
    sev, detail = _check(res, "covers all requirements")
    assert sev == "WARN"
    assert "R2" in detail
