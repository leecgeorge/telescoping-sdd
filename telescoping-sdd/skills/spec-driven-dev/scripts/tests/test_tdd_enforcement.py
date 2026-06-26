"""Tests for the Force-TDD-in-Phase-4 enforcement in validate_spec.py.

Covers the R3 (code-touching test-name FAIL), R4 (test-exempt override),
AD2 (Create/Modify verb scoping), AD8 (no-parens test-name matching), and
AD10 (sibling cross-reference delegation) machinery added in T1, plus the
migration regression net over the real in-repo spec corpus.

R5 (`--completion-gate`) tests are added by T4 in this same file.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _load_validate_spec():
    scripts_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(scripts_dir))
    if "validate_spec" in sys.modules:
        return importlib.reload(sys.modules["validate_spec"])
    return importlib.import_module("validate_spec")


vs = _load_validate_spec()

# Repo root: tests/ -> scripts/ -> spec-driven-dev/ -> skills/ -> telescoping-sdd/ -> repo
_REPO_ROOT = Path(__file__).resolve().parents[5]

# The migration regression test scans this feature's OWN author-side artifacts
# under specs/, which is gitignored and therefore ABSENT in a clean CI checkout.
# Skip (don't fail) when the corpus isn't present locally — the synthetic
# multi-line tests below are the real CI net.
_SPECS_ABSENT_REASON = "author-side specs/ artifacts are gitignored, absent in a clean checkout (CI)"


# ---------------------------------------------------------------------------
# Fixtures — a thin task builder that states each test's intent explicitly
# ---------------------------------------------------------------------------

_OMIT = "\x00OMIT\x00"  # sentinel: omit the **Tests:** field entirely


def _task(tid: str = "T1", *, files: str = "  - Create: `src/x.py`",
          tests: str = _OMIT, req: str = "R1") -> str:
    """Build one task body.

    `files`: the raw sub-bullet block under **Files:** (multi-line allowed).
    `tests`: the full `- **Tests:** ...` bullet text (multi-line allowed), or
             the `_OMIT` sentinel to leave the **Tests:** field out entirely.
    """
    lines = [
        f"### - [ ] {tid}: Title {tid}",
        "",
        f"- **Requirement:** {req}",
        f"- **Description:** do {tid}",
        "- **Files:**",
        files,
        "- **Dependencies:** None",
        "- **Parallel:** No",
        "- **Acceptance Criteria:**",
        "  - GIVEN a precondition",
        "    WHEN an action occurs",
        "    THEN a result holds",
    ]
    if tests != _OMIT:
        lines.append(tests)
    lines.append("- **Verification:** `pytest -q`")
    lines.append("")
    return "\n".join(lines)


def _doc(*task_blocks: str) -> str:
    head = (
        "# Tasks: TDD Enforcement Demo\n\n## Summary\n\n"
        "| Task | Description | Requirement | Dependencies | Parallel | Status |\n"
        "|------|-------------|-------------|--------------|----------|--------|\n"
        "| T1 | demo | R1 | None | No | Not Started |\n\n"
        "## Phase 1\n\n"
    )
    return head + "\n".join(task_blocks) + "\n"


def _check(result, name_substr: str):
    """Return (severity, detail) for the first check whose name contains the
    substring, or None if no such check was emitted."""
    for name, sev, detail in result.checks:
        if name_substr in name:
            return sev, detail
    return None


def _run(tmp_path, *task_blocks, language="python"):
    (tmp_path / "tasks.md").write_text(_doc(*task_blocks), encoding="utf-8")
    return vs.validate_tasks(tmp_path, language=language)


# ---------------------------------------------------------------------------
# R3 — code-touching task must name a test (FAIL, not WARN)
# ---------------------------------------------------------------------------

def test_code_touching_python_task_missing_test_fails(tmp_path):
    res = _run(tmp_path, _task("T1", files="  - Create: `src/x.py`"))
    sev, detail = _check(res, "names test functions/methods")
    assert sev == "FAIL"
    assert "T1" in detail


def test_code_touching_java_task_missing_test_fails(tmp_path):
    res = _run(tmp_path, _task("T1", files="  - Modify: `src/main/java/Foo.java`"),
               language="java")
    sev, detail = _check(res, "names test functions/methods")
    assert sev == "FAIL"
    assert "T1" in detail


def test_non_code_task_missing_test_auto_passes(tmp_path):
    res = _run(tmp_path, _task("T1", files="  - Modify: `docs/readme.md`"))
    sev, _ = _check(res, "names test functions/methods")
    assert sev == "PASS"


def test_generic_profile_check_skipped_entirely(tmp_path):
    res = _run(tmp_path, _task("T1", files="  - Create: `src/x.py`"),
               language="generic")
    assert _check(res, "names test functions/methods") is None


# ---------------------------------------------------------------------------
# R4 — test-exempt override (mandatory non-empty reason)
# ---------------------------------------------------------------------------

def test_r4_override_with_reason_passes(tmp_path):
    res = _run(tmp_path, _task(
        "T1", files="  - Create: `src/__init__.py`",
        tests="- **Tests:** none — pure re-export, no logic to test"))
    sev, _ = _check(res, "names test functions/methods")
    assert sev == "PASS"


def test_r4_override_empty_reason_fails(tmp_path):
    res = _run(tmp_path, _task(
        "T1", files="  - Create: `src/x.py`",
        tests="- **Tests:** none — "))
    sev, detail = _check(res, "R4 override requires non-empty reason")
    assert sev == "FAIL"
    assert "T1" in detail


def test_r4_override_with_test_name_passes(tmp_path):
    # A real test name AND the override-shaped prose: the name wins, no FAIL.
    res = _run(tmp_path, _task(
        "T1", files="  - Create: `src/x.py`",
        tests="- **Tests:** `test_x` — and none — extra prose"))
    sev, _ = _check(res, "names test functions/methods")
    assert sev == "PASS"
    assert _check(res, "R4 override requires non-empty reason") is None


def test_r4_overrides_surfaced_in_result(tmp_path):
    res = _run(tmp_path, _task(
        "T1", files="  - Create: `src/__init__.py`",
        tests="- **Tests:** none — pure re-export, no logic"))
    sev, detail = _check(res, "R4 test-exempt overrides")
    assert sev == "PASS"
    assert "Count: 1" in detail and "T1" in detail


# ---------------------------------------------------------------------------
# Classifier — _is_code_touching (AD2)
# ---------------------------------------------------------------------------

def test_mixed_files_md_and_py_is_code_touching():
    body = _task("T1", files="  - Modify: `docs/x.md`\n  - Create: `src/x.py`")
    assert vs._is_code_touching(body) is True


def test_sh_only_files_is_not_code_touching():
    body = _task("T1", files="  - Create: `infra/deploy.sh`\n  - Modify: `Dockerfile`")
    assert vs._is_code_touching(body) is False


def test_empty_files_field_is_not_code_touching():
    body = _task("T1", files="  - none")
    assert vs._is_code_touching(body) is False


def test_read_only_py_ref_is_not_code_touching():
    # AD2: a task that only Reads a .py for context but Creates/Modifies .md only.
    body = _task("T1", files="  - Read: `src/engine.py`\n  - Modify: `docs/x.md`")
    assert vs._is_code_touching(body) is False


# ---------------------------------------------------------------------------
# AD8 — no-parens test-name matching
# ---------------------------------------------------------------------------

def test_test_name_pattern_matches_with_and_without_parens():
    pat = vs.LANGUAGE_PROFILES["python"]["test_name_pattern"]
    assert pat.search("- `test_foo` — checks foo")      # no parens (real convention)
    assert pat.search("- `test_foo()` — checks foo")    # with parens (legacy)


# ---------------------------------------------------------------------------
# Field-scope + multi-line capture
# ---------------------------------------------------------------------------

def test_multiline_tests_field_extracted_passes_r3(tmp_path):
    # The by-name token is on an indented sub-bullet UNDER the **Tests:** line —
    # extraction must span the whole field block, not just the **Tests:** line.
    res = _run(tmp_path, _task(
        "T1", files="  - Create: `src/x.py`",
        tests="- **Tests:**\n  - `test_x` — checks x"))
    sev, _ = _check(res, "names test functions/methods")
    assert sev == "PASS"


def test_r4_override_on_subbullet_not_recognized_fails(tmp_path):
    # Override is first-line-only (AD1): `none — reason` on a sub-bullet (not the
    # **Tests:** line) is NOT a valid override → R3 FAIL.
    res = _run(tmp_path, _task(
        "T1", files="  - Create: `src/x.py`",
        tests="- **Tests:**\n  - none — reason on a sub-bullet"))
    sev, detail = _check(res, "names test functions/methods")
    assert sev == "FAIL"
    assert "T1" in detail


def test_r3_test_token_in_description_not_field_still_fails(tmp_path):
    # Field-scoped, not body-wide: a decoy `test_foo` token in Description prose
    # with an EMPTY **Tests:** field must still FAIL.
    body = _task("T1", files="  - Create: `src/x.py`",
                 tests="- **Tests:**")
    body = body.replace("- **Description:** do T1",
                        "- **Description:** do T1, see `test_decoy` in prose")
    res = _run(tmp_path, body)
    sev, _ = _check(res, "names test functions/methods")
    assert sev == "FAIL"


def test_tests_field_extracted_from_bullet_not_prose_mention(tmp_path):
    # Field extraction is anchored to the real `- **Tests:**` bullet: a task whose
    # Description prose literally mentions the `**Tests:**` field with a DECOY token
    # must extract the REAL field, not the prose. Real field declares `test_real`;
    # the prose decoy is `test_prose_decoy`. R3 passes via the real token; R5 must
    # existence-check `test_real`, never `test_prose_decoy`.
    body = _task("T1", files="  - Create: `src/x.py`",
                 tests="- **Tests:**\n  - `test_real` — the real declaration")
    body = body.replace(
        "- **Description:** do T1",
        "- **Description:** do T1; the `**Tests:**` field here mentions `test_prose_decoy`")
    pat = vs.LANGUAGE_PROFILES["python"]["test_name_pattern"]
    names = vs._extract_test_names(body, pat)
    assert names == ["test_real"]
    res = _run(tmp_path, body)
    sev, _ = _check(res, "names test functions/methods")
    assert sev == "PASS"


# ---------------------------------------------------------------------------
# AD10 — sibling cross-reference delegation
# ---------------------------------------------------------------------------

def test_cross_reference_tests_field_passes_r3(tmp_path):
    # T2 is code-touching and names a real test; T1 cross-references T2.
    t2 = _task("T2", files="  - Create: `src/y.py`",
               tests="- **Tests:**\n  - `test_y` — checks y", req="R1")
    t1 = _task("T1", files="  - Create: `src/x.py`",
               tests="- **Tests:** Groups 1–3 from T2 (run red → green)")
    res = _run(tmp_path, t1, t2)
    sev, _ = _check(res, "names test functions/methods")
    assert sev == "PASS"
    sev_x, detail_x = _check(res, "cross-reference test delegations")
    assert sev_x == "PASS"
    assert "T1" in detail_x


def test_cross_reference_referent_multiline_resolves(tmp_path):
    # The referent (T2) declares its by-name token on sub-bullets — still resolves.
    t2 = _task("T2", files="  - Create: `src/y.py`",
               tests="- **Tests:**\n  - `test_y_one`, `test_y_two` — checks y")
    t1 = _task("T1", files="  - Create: `src/x.py`",
               tests="- **Tests:** All of Groups from T2")
    res = _run(tmp_path, t1, t2)
    sev, _ = _check(res, "names test functions/methods")
    assert sev == "PASS"


def test_cross_reference_to_nonexistent_task_fails(tmp_path):
    t1 = _task("T1", files="  - Create: `src/x.py`",
               tests="- **Tests:** Groups from T99")
    res = _run(tmp_path, t1)
    sev, detail = _check(res, "names test functions/methods")
    assert sev == "FAIL"
    assert "T1" in detail


def test_cross_reference_self_reference_fails(tmp_path):
    t1 = _task("T1", files="  - Create: `src/x.py`",
               tests="- **Tests:** see T1 itself")
    res = _run(tmp_path, t1)
    sev, _ = _check(res, "names test functions/methods")
    assert sev == "FAIL"


def test_cross_reference_to_non_by_name_task_fails(tmp_path):
    # T2 exists and is code-touching but names NO test → invalid referent.
    t2 = _task("T2", files="  - Create: `src/y.py`")  # no Tests field
    t1 = _task("T1", files="  - Create: `src/x.py`",
               tests="- **Tests:** delegated to T2")
    res = _run(tmp_path, t1, t2)
    sev, detail = _check(res, "names test functions/methods")
    assert sev == "FAIL"
    # T2 also fails (it is code-touching, names no test) — both surface.
    assert "T1" in detail


def test_cross_reference_to_non_code_by_name_task_fails(tmp_path):
    # T2 names `test_phantom` but touches only .md → non-code decoy → R5 would
    # skip it, so delegating to it is invalid.
    t2 = _task("T2", files="  - Modify: `notes.md`",
               tests="- **Tests:**\n  - `test_phantom` — never existence-checked")
    t1 = _task("T1", files="  - Create: `src/x.py`",
               tests="- **Tests:** delegated to T2")
    res = _run(tmp_path, t1, t2)
    sev, detail = _check(res, "names test functions/methods")
    assert sev == "FAIL"
    assert "T1" in detail


def test_cross_reference_to_crossref_only_task_fails(tmp_path):
    # A→B where B passes R3 only via its OWN cross-ref to C (B is not by-name).
    # Resolution is against the by-name set, not all R3-passers (one-hop only).
    tc = _task("T3", files="  - Create: `src/c.py`",
               tests="- **Tests:**\n  - `test_c` — checks c")
    tb = _task("T2", files="  - Create: `src/b.py`",
               tests="- **Tests:** delegated to T3")
    ta = _task("T1", files="  - Create: `src/a.py`",
               tests="- **Tests:** delegated to T2")
    res = _run(tmp_path, ta, tb, tc)
    sev, detail = _check(res, "names test functions/methods")
    assert sev == "FAIL"
    assert "T1" in detail
    assert "T2" not in detail  # T2 is a valid cross-ref to by-name T3


# ---------------------------------------------------------------------------
# Migration regression — no unexpected new FAIL over the real spec corpus
# ---------------------------------------------------------------------------

_REAL_TASKS = sorted(_REPO_ROOT.glob("specs/*/03_tasks.md"))


@pytest.mark.parametrize(
    "tasks_path", _REAL_TASKS or [None],
    ids=[p.parent.name for p in _REAL_TASKS] or ["no-corpus"],
)
def test_real_repo_specs_no_unexpected_new_fail(tasks_path):
    if tasks_path is None:
        pytest.skip(_SPECS_ABSENT_REASON)
    res = vs.validate_tasks(tasks_path.parent, language="python")
    name_hit = _check(res, "names test functions/methods")
    assert name_hit is not None
    assert name_hit[0] != "FAIL", (
        f"{tasks_path.parent.name}: code-touching task declared no test: {name_hit[1]}"
    )
    bad_override = _check(res, "R4 override requires non-empty reason")
    if bad_override is not None:
        assert bad_override[0] != "FAIL", f"{tasks_path.parent.name}: {bad_override[1]}"


# ---------------------------------------------------------------------------
# R5 — Phase-4 completion-gate test-existence cross-check (--completion-gate)
# ---------------------------------------------------------------------------

def _gate_setup(tmp_path, *task_blocks):
    """Create a spec dir under a tmp project root; return (spec_dir, project_root)."""
    spec_dir = tmp_path / "specs" / "feat"
    spec_dir.mkdir(parents=True)
    (spec_dir / "tasks.md").write_text(_doc(*task_blocks), encoding="utf-8")
    return spec_dir, tmp_path


def test_r5_named_test_exists_passes(tmp_path):
    spec_dir, root = _gate_setup(tmp_path, _task(
        "T1", files="  - Create: `src/x.py`",
        tests="- **Tests:**\n  - `test_foo` — checks foo"))
    (root / "test_x.py").write_text("def test_foo():\n    assert True\n", encoding="utf-8")
    res = vs.validate_completion_gate(spec_dir, project_root=root, language="python")
    sev, _ = _check(res, "test function exists — T1/test_foo")
    assert sev == "PASS"
    assert res.passed


def test_r5_named_test_absent_warns(tmp_path):
    spec_dir, root = _gate_setup(tmp_path, _task(
        "T1", files="  - Create: `src/x.py`",
        tests="- **Tests:**\n  - `test_missing` — checks"))
    res = vs.validate_completion_gate(spec_dir, project_root=root, language="python")
    sev, detail = _check(res, "test function exists — T1/test_missing")
    assert sev == "WARN"
    assert res.passed  # WARN is the default — exit 0


def test_r5_named_test_absent_strict_fails(tmp_path):
    spec_dir, root = _gate_setup(tmp_path, _task(
        "T1", files="  - Create: `src/x.py`",
        tests="- **Tests:**\n  - `test_missing` — checks"))
    res = vs.validate_completion_gate(spec_dir, project_root=root, language="python",
                                      strict_r5=True)
    sev, _ = _check(res, "test function exists — T1/test_missing")
    assert sev == "FAIL"
    assert not res.passed


def test_r5_non_code_task_not_checked(tmp_path):
    spec_dir, root = _gate_setup(tmp_path, _task(
        "T1", files="  - Modify: `docs/x.md`",
        tests="- **Tests:**\n  - `test_foo`"))
    res = vs.validate_completion_gate(spec_dir, project_root=root, language="python")
    assert _check(res, "test function exists") is None


def test_r5_generic_profile_skipped(tmp_path):
    spec_dir, root = _gate_setup(tmp_path, _task("T1", files="  - Create: `src/x.py`"))
    res = vs.validate_completion_gate(spec_dir, project_root=root, language="generic")
    sev, _ = _check(res, "completion-gate skipped")
    assert sev == "PASS"
    assert _check(res, "test function exists") is None


def test_r5_r4_override_task_not_checked(tmp_path):
    spec_dir, root = _gate_setup(tmp_path, _task(
        "T1", files="  - Create: `src/__init__.py`",
        tests="- **Tests:** none — pure re-export, no logic"))
    res = vs.validate_completion_gate(spec_dir, project_root=root, language="python")
    assert _check(res, "test function exists") is None  # zero by-name names → skip
    sev, _ = _check(res, "R4 test-exempt overrides")
    assert sev == "PASS"  # the override audit surfaces at the gate (R4 AC#4)


def test_r5_java_task_method_found(tmp_path):
    spec_dir, root = _gate_setup(tmp_path, _task(
        "T1", files="  - Create: `src/main/java/Foo.java`",
        tests="- **Tests:**\n  - `testFooBar` — checks"))
    (root / "FooTest.java").write_text(
        "class FooTest {\n  void testFooBar() {}\n}\n", encoding="utf-8")
    res = vs.validate_completion_gate(spec_dir, project_root=root, language="java")
    sev, _ = _check(res, "test function exists — T1/testFooBar")
    assert sev == "PASS"


def test_r5_test_in_nonstandard_layout_warns(tmp_path):
    # AD7/RISK-6: a real test in a non-`test_*.py` file is outside the search
    # scope → missed → surfaced WARN (documents the boundary, does not block).
    spec_dir, root = _gate_setup(tmp_path, _task(
        "T1", files="  - Create: `src/x.py`",
        tests="- **Tests:**\n  - `test_hidden`"))
    (root / "helpers.py").write_text("def test_hidden(): pass\n", encoding="utf-8")
    res = vs.validate_completion_gate(spec_dir, project_root=root, language="python")
    sev, _ = _check(res, "test function exists — T1/test_hidden")
    assert sev == "WARN"


def test_r5_override_field_yields_zero_names_skipped(tmp_path):
    # Field-scoped: an override field yields zero names → R5 skips that task; a
    # declaring field → R5 checks. No body-wide both-present bypass.
    t_override = _task("T1", files="  - Create: `src/a.py`",
                       tests="- **Tests:** none — no logic to test")
    t_declare = _task("T2", files="  - Create: `src/b.py`",
                      tests="- **Tests:**\n  - `test_present`")
    spec_dir, root = _gate_setup(tmp_path, t_override, t_declare)
    (root / "test_b.py").write_text("def test_present(): pass\n", encoding="utf-8")
    res = vs.validate_completion_gate(spec_dir, project_root=root, language="python")
    assert _check(res, "test function exists — T1/") is None  # override task skipped
    sev, _ = _check(res, "test function exists — T2/test_present")
    assert sev == "PASS"


def test_cross_reference_audit_surfaced_both_gates(tmp_path):
    # AD10: a valid cross-ref surfaces the delegations PASS count at BOTH the
    # Phase-3 gate (validate_tasks) and the --completion-gate run.
    t2 = _task("T2", files="  - Create: `src/y.py`",
               tests="- **Tests:**\n  - `test_y`")
    t1 = _task("T1", files="  - Create: `src/x.py`",
               tests="- **Tests:** Groups from T2")
    spec_dir, root = _gate_setup(tmp_path, t1, t2)
    (root / "test_y.py").write_text("def test_y(): pass\n", encoding="utf-8")
    res3 = vs.validate_tasks(spec_dir, language="python")
    sev3, _ = _check(res3, "cross-reference test delegations")
    assert sev3 == "PASS"
    res5 = vs.validate_completion_gate(spec_dir, project_root=root, language="python")
    sev5, _ = _check(res5, "cross-reference test delegations")
    assert sev5 == "PASS"


# --- CLI argument guards (AD3) -------------------------------------------------

def test_completion_gate_requires_project_root(tmp_path, monkeypatch):
    (tmp_path / "tasks.md").write_text(_doc(_task()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv",
                        ["validate_spec.py", str(tmp_path), "--completion-gate"])
    with pytest.raises(SystemExit) as exc:
        vs.main()
    assert exc.value.code == 2


def test_strict_r5_requires_completion_gate(tmp_path, monkeypatch):
    (tmp_path / "tasks.md").write_text(_doc(_task()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv",
                        ["validate_spec.py", str(tmp_path), "--strict-r5",
                         "--project-root", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        vs.main()
    assert exc.value.code == 2
