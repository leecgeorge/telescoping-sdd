"""T1/T2/T3/T10/T11/T12 — approval guard, dep guard, path validation, CLI integration, R6 grep targets, validate_blueprint import safety.

Split from the original test_render_business_brief.py per P3-15. Shared
helpers and constants live in `common.py`; shared fixtures (tiny PNG path,
approved-triple fixtures, panel-review fixture) live in `conftest.py`.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

import base64
import hashlib
from common import (  # type: ignore[import-not-found]
    _build_doc,
    _doc_with_hash,
    _independent_hash,
    _FROZEN_ARCH_BODY,
    _FROZEN_PLAN_BODY,
    _FROZEN_SCOPE_BODY,
    _make_absent_hash_dir,
    _make_stale_hash_dir,
    _make_unapproved_dir,
    _read_phase_doc,
    _read_skill_md,
)

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(_SCRIPTS_DIR))

import render_business_brief  # noqa: E402


def test_independent_hash_oracle_parity():
    """P2-10: the truth-table tests rely on `_independent_hash` being a genuine
    independent oracle for `blueprint_common.compute_content_hash`. If
    blueprint_common adds a third neutralisation step, the test helper here
    would silently drift and the truth-table would pass on stale logic.

    Converts that silent-drift class into a loud failure: run both functions
    over a fixed input and assert byte-equality.
    """
    sys.path.append(
        str(_SCRIPTS_DIR.resolve().parents[2] / "scripts")
    )
    from blueprint_common import compute_content_hash

    sample = (
        "# Sample Artifact\n\n"
        "Some body text with **bold** and `code`.\n\n"
        "## Approval\n\n"
        "- [x] Approved to proceed\n"
        "- **Content Hash:** `deadbeefcafef00d`\n"
    )
    assert _independent_hash(sample) == compute_content_hash(sample), (
        "_independent_hash has drifted from blueprint_common.compute_content_hash"
    )


# NOTE: fixture_approved_triple_frozen is now defined in conftest.py
# (shared across test_filter / test_render / test_cli_integration).


# ---------------------------------------------------------------------------
# T1 — approval guard truth table
# ---------------------------------------------------------------------------


def _build_doc(body: str, *, ticked: bool, hash_mode: str) -> str:
    """hash_mode: 'matching' | 'mismatching' | 'absent'"""
    if hash_mode == "absent":
        box = "x" if ticked else " "
        return f"{body}\n\n## Approval\n\n- [{box}] Approved to proceed\n"
    if hash_mode == "matching":
        # Compute hash using the independent oracle so the doc has the right
        # stamp; this still tests check_upstream_approvals against the SUT's
        # imported helpers.
        scaffold = _doc_with_hash(body, ticked=ticked, stored_hash="X" * 16)
        real_hash = _independent_hash(scaffold)
        return _doc_with_hash(body, ticked=ticked, stored_hash=real_hash)
    if hash_mode == "mismatching":
        return _doc_with_hash(body, ticked=ticked, stored_hash="0" * 16)
    raise ValueError(hash_mode)


_TRUTH_TABLE_CASES = [
    # (ticked, hash_mode, expect_pass, expected_fragment)
    (True, "matching", True, None),
    (True, "mismatching", False, "stale hash"),
    (True, "absent", False, "absent hash"),
    (False, "matching", False, "unapproved"),
    (False, "mismatching", False, "unapproved"),
    (False, "absent", False, "unapproved"),
]


@pytest.mark.parametrize(
    "ticked,hash_mode,expect_pass,fragment", _TRUTH_TABLE_CASES
)
def test_check_upstream_approvals_truth_table(
    ticked, hash_mode, expect_pass, fragment, capsys
):
    """Spans {ticked, unticked} × {matching, mismatching, absent} for SCOPE.

    SCOPE is the first artifact in the fail-fast order, so any rejection
    fires the SCOPE-specific message regardless of the state of the other
    two artifacts. We hold ARCH and PLAN at a passing baseline.
    """
    scope = _build_doc(_FROZEN_SCOPE_BODY, ticked=ticked, hash_mode=hash_mode)
    arch = _build_doc(_FROZEN_ARCH_BODY, ticked=True, hash_mode="matching")
    plan = _build_doc(_FROZEN_PLAN_BODY, ticked=True, hash_mode="matching")

    if expect_pass:
        render_business_brief.check_upstream_approvals(scope, arch, plan)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
    else:
        with pytest.raises(SystemExit) as exc:
            render_business_brief.check_upstream_approvals(scope, arch, plan)
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "SCOPE.md" in captured.err
        assert fragment in captured.err


def test_check_upstream_approvals_truth_table_per_artifact(capsys):
    """Each artifact reports under its own filename when it is the failing one."""
    cases = [
        # (failing_index, expected_filename, expected_phase)
        (0, "SCOPE.md", "scope"),
        (1, "ARCHITECTURE.md", "architecture"),
        (2, "PLAN.md", "plan"),
    ]
    bodies = [_FROZEN_SCOPE_BODY, _FROZEN_ARCH_BODY, _FROZEN_PLAN_BODY]
    for failing, expected_name, expected_phase in cases:
        docs = [
            _build_doc(bodies[0], ticked=True, hash_mode="matching"),
            _build_doc(bodies[1], ticked=True, hash_mode="matching"),
            _build_doc(bodies[2], ticked=True, hash_mode="matching"),
        ]
        docs[failing] = _build_doc(
            bodies[failing], ticked=False, hash_mode="matching"
        )
        with pytest.raises(SystemExit) as exc:
            render_business_brief.check_upstream_approvals(*docs)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert err.startswith(f"{expected_name}: unapproved")
        assert f"for {expected_phase}" in err


def test_check_upstream_approvals_frozen_hash_smoke(
    fixture_approved_triple_frozen, capsys
):
    """Happy-path against hardcoded hash literals — catches drift in
    blueprint_common.compute_content_hash.

    NOTE: the regeneration runbook on the fixture's docstring is a CODE
    REVIEW requirement, not a test assertion (pinning docstring content via
    a test is a "test-of-comment" anti-pattern). See design.md §Fixtures.
    """
    scope, arch, plan = fixture_approved_triple_frozen
    render_business_brief.check_upstream_approvals(scope, arch, plan)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_check_upstream_approvals_uses_imported_helpers():
    """The SUT imports the three canonical helpers from `validate_blueprint`
    and `blueprint_common` (not re-implemented locally).

    NOTE: this used to assert `is`-identity, but the wider test suite
    reloads `validate_blueprint` during `test_validate_blueprint.py`, which
    creates new function objects and breaks identity. The textual import
    contract is the load-bearing property; assert that instead.

    `content_for_hashing` was previously imported as a marker; per P2-5 it
    was removed because the truth-table tests already verify the behaviour
    of `verify_content_hash` (which calls `content_for_hashing` internally),
    and asserting the literal import text pins import shape rather than
    behaviour.
    """
    src = inspect.getsource(render_business_brief)
    assert "from validate_blueprint import" in src
    assert "has_approval" in src
    assert "approval_hash" in src
    assert "from blueprint_common import" in src
    assert "verify_content_hash" in src
    # Sanity: the three names are bound on the module namespace and callable.
    for name in (
        "has_approval",
        "approval_hash",
        "verify_content_hash",
    ):
        assert callable(getattr(render_business_brief, name)), (
            f"{name} not bound on render_business_brief"
        )


def test_sys_path_append_not_insert():
    """The SUT must use `sys.path.append`, not `sys.path.insert`.

    Textual contract: `sys.path.append` appears twice; `sys.path.insert`
    does not appear at all. The textual property is what we care about;
    runtime `sys.path[0]` state is unreliable in the wider suite because
    other tests mutate it (inserting at position 0 without restoring).
    """
    src = inspect.getsource(render_business_brief)
    assert src.count("sys.path.append") == 2
    assert "sys.path.insert" not in src
    # Runtime presence (not position) — the two appended paths are visible
    # to subsequent imports.
    shared = str(render_business_brief._SHARED_SCRIPTS)
    validate = str(render_business_brief._VALIDATE_DIR)
    assert shared in sys.path
    assert validate in sys.path


def test_shared_scripts_path_regression():
    """`_SHARED_SCRIPTS` must resolve to a directory containing blueprint_common.py."""
    shared = render_business_brief._SHARED_SCRIPTS
    assert shared.is_dir(), f"_SHARED_SCRIPTS not a directory: {shared}"
    assert (shared / "blueprint_common.py").exists(), (
        f"blueprint_common.py missing under _SHARED_SCRIPTS: {shared}"
    )


def test_validate_dir_path_regression():
    """`_VALIDATE_DIR` must resolve to the local scripts/ dir holding validate_blueprint.py."""
    vdir = render_business_brief._VALIDATE_DIR
    assert vdir.is_dir(), f"_VALIDATE_DIR not a directory: {vdir}"
    assert (vdir / "validate_blueprint.py").exists(), (
        f"validate_blueprint.py missing under _VALIDATE_DIR: {vdir}"
    )


def test_check_markdown_dependency_happy_path(capsys):
    """Happy path: real installed markdown>=3.4 and bleach>=6; no exit."""
    render_business_brief.check_markdown_dependency(
        "render_business_brief.py", "/tmp/blueprint"
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_check_markdown_dependency_version_below_floor(monkeypatch, capsys):
    """`_installed_markdown_version` patched to '3.3' triggers exit-1 with
    actionable message; script_path and blueprint_dir interpolated."""
    monkeypatch.setattr(
        render_business_brief, "_installed_markdown_version", lambda: "3.3"
    )
    with pytest.raises(SystemExit) as exc:
        render_business_brief.check_markdown_dependency(
            "/abs/path/render_business_brief.py", "/abs/path/blueprint"
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "/abs/path/render_business_brief.py" in captured.err
    assert "/abs/path/blueprint" in captured.err
    assert "pip install" in captured.err
    assert "markdown>=3.4" in captured.err
    # P1-1: bleach and requirements.txt now appear in every dep-error path.
    assert "bleach" in captured.err
    assert "requirements.txt" in captured.err


def test_check_markdown_dependency_bleach_import_failure(monkeypatch, capsys):
    """`bleach` set to None in sys.modules → exit 1 with the committed error
    shape: names BOTH packages, points at requirements.txt, and includes the
    script and blueprint args. P1-1 tightening: a user with markdown already
    installed but missing bleach must NOT be told to `pip install markdown`."""
    monkeypatch.setitem(sys.modules, "bleach", None)
    with pytest.raises(SystemExit) as exc:
        render_business_brief.check_markdown_dependency(
            "render_business_brief.py", "/tmp/blueprint"
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    # Both packages and the requirements.txt path are present:
    assert "markdown" in captured.err
    assert "bleach" in captured.err
    assert "requirements.txt" in captured.err
    # And the legacy floors are still mentioned (back-compat with older
    # documentation that prescribes `markdown>=3.4`):
    assert "markdown>=3.4" in captured.err


def test_check_markdown_dependency_bleach_upper_bound_assertion():
    """Defense-in-depth (AD13): `style` is NOT in _ALLOWED_ATTRS;
    `bleach.__version__` starts with `"6."`.

    The _ALLOWED_ATTRS check defers to T5 (its definition is added then) —
    here we only confirm the bleach pin is in the 6.x major.
    """
    import bleach

    assert bleach.__version__.startswith("6.")


def test_check_markdown_dependency_bleach_below_floor(monkeypatch, capsys):
    """P2-4: `_installed_bleach_version` patched to '5.0.0' triggers exit 1
    with the dep-error message. Closes the honor-system gap where bleach
    versions were only `import`-checked, not version-checked."""
    monkeypatch.setattr(
        render_business_brief, "_installed_bleach_version", lambda: "5.0.0"
    )
    with pytest.raises(SystemExit) as exc:
        render_business_brief.check_markdown_dependency(
            "render_business_brief.py", "/tmp/blueprint"
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "bleach" in captured.err


def test_check_markdown_dependency_bleach_above_ceiling(monkeypatch, capsys):
    """P2-4: bleach 7.0 (above the ceiling) is also rejected — defense
    against a future bleach release that removes a security guarantee
    AD13 relies on."""
    monkeypatch.setattr(
        render_business_brief, "_installed_bleach_version", lambda: "7.0.0"
    )
    with pytest.raises(SystemExit) as exc:
        render_business_brief.check_markdown_dependency(
            "render_business_brief.py", "/tmp/blueprint"
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "bleach" in captured.err


def test_check_markdown_dependency_packaging_missing(monkeypatch, capsys):
    """P3-5: missing `packaging` library should produce the friendly dep-error,
    not an unhandled ModuleNotFoundError traceback."""
    monkeypatch.setitem(sys.modules, "packaging.version", None)
    with pytest.raises(SystemExit) as exc:
        render_business_brief.check_markdown_dependency(
            "render_business_brief.py", "/tmp/blueprint"
        )
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "requirements.txt" in captured.err


def test_check_markdown_dependency_shell_quotes_blueprint_arg(
    monkeypatch, capsys
):
    """P3-2: `blueprint_dir_arg` is shell-quoted in the dep-error message so
    a copy-pasteable command can't be injected by a hostile path argument."""
    monkeypatch.setattr(
        render_business_brief, "_installed_markdown_version", lambda: "3.3"
    )
    with pytest.raises(SystemExit):
        render_business_brief.check_markdown_dependency(
            "script.py", "/tmp/foo; rm -rf /"
        )
    captured = capsys.readouterr()
    # shlex.quote wraps in single quotes when the input has shell metacharacters.
    assert "'/tmp/foo; rm -rf /'" in captured.err


@pytest.mark.parametrize(
    "version_or_module",
    [
        ("version_below", "3.3"),
        ("bleach_missing", None),
    ],
)
def test_stdout_empty_on_dependency_error_paths(
    version_or_module, monkeypatch, capsys
):
    """Both dep-error paths must keep stdout clean (everything to stderr)."""
    mode, value = version_or_module
    if mode == "version_below":
        monkeypatch.setattr(
            render_business_brief, "_installed_markdown_version", lambda: value
        )
    else:
        monkeypatch.setitem(sys.modules, "bleach", None)
    with pytest.raises(SystemExit):
        render_business_brief.check_markdown_dependency("script.py", "/dir")
    captured = capsys.readouterr()
    assert captured.out == ""


def test_validate_blueprint_dir_not_found(tmp_path, capsys):
    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as exc:
        render_business_brief.validate_blueprint_dir(str(missing))
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"{missing}: not found\n"


def test_validate_blueprint_dir_not_a_directory(tmp_path, capsys):
    f = tmp_path / "file.txt"
    f.write_text("hi", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        render_business_brief.validate_blueprint_dir(str(f))
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"{f}: not a directory\n"


_ARTIFACT_NAMES = ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md")


@pytest.mark.parametrize(
    "present",
    [
        (),  # all missing
        ("SCOPE.md",),
        ("ARCHITECTURE.md",),
        ("PLAN.md",),
        ("SCOPE.md", "ARCHITECTURE.md"),
        ("SCOPE.md", "PLAN.md"),
        ("ARCHITECTURE.md", "PLAN.md"),
    ],
)
def test_validate_blueprint_dir_missing_artifacts_parametrized(
    present, tmp_path, capsys
):
    for name in present:
        (tmp_path / name).write_text("x", encoding="utf-8")
    expected_missing = [n for n in _ARTIFACT_NAMES if n not in present]
    with pytest.raises(SystemExit) as exc:
        render_business_brief.validate_blueprint_dir(str(tmp_path))
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    expected_line = (
        f"{tmp_path}: missing required artifacts: " + ", ".join(expected_missing)
    )
    assert captured.err.rstrip("\n") == expected_line


def test_validate_blueprint_dir_success(tmp_path):
    for name in _ARTIFACT_NAMES:
        (tmp_path / name).write_text("x", encoding="utf-8")
    result = render_business_brief.validate_blueprint_dir(str(tmp_path))
    assert result == tmp_path.resolve()


@pytest.mark.parametrize("bad", ["/tmp/a\nb", "/tmp/a\rb", "x\n\r"])
def test_validate_blueprint_dir_rejects_newline_chars(bad, capsys):
    """P3-3: a path argument containing newline characters is rejected with
    a clear error before any filesystem call. Closes the `print(p)`-with-
    embedded-newline footgun that would split the stdout output across
    multiple lines and corrupt downstream pipelines."""
    with pytest.raises(SystemExit) as exc:
        render_business_brief.validate_blueprint_dir(bad)
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "newline" in captured.err


@pytest.mark.parametrize("failure_mode", ["not_found", "not_a_dir", "missing"])
def test_stdout_empty_on_path_validation_error_paths(
    failure_mode, tmp_path, capsys
):
    if failure_mode == "not_found":
        target = tmp_path / "nope"
    elif failure_mode == "not_a_dir":
        target = tmp_path / "file.txt"
        target.write_text("hi", encoding="utf-8")
    else:
        target = tmp_path  # empty dir
    with pytest.raises(SystemExit):
        render_business_brief.validate_blueprint_dir(str(target))
    captured = capsys.readouterr()
    assert captured.out == ""


@pytest.fixture
def fixture_approved_triple(tmp_path):
    """Three artifact files with ticked approval checkboxes AND correct
    content hashes (computed via blueprint_common.compute_content_hash).
    Returns the blueprint directory path.
    """
    # Ensure the blueprint_common helper is importable for hash calculation
    shared = str(_SCRIPTS_DIR.resolve().parents[2] / "scripts")
    if shared not in sys.path:
        sys.path.append(shared)
    from blueprint_common import compute_content_hash

    bodies = {
        "SCOPE.md": "# My Project\n\nScope body content.\n",
        "ARCHITECTURE.md": "# Arch\n\nArchitecture body content.\n",
        "PLAN.md": "# Plan\n\nPlan body content.\n",
    }
    for fname, body in bodies.items():
        scaffold = (
            f"{body}\n\n"
            f"## Approval\n\n"
            f"- [x] Approved to proceed\n"
            f"- **Content Hash:** `{'0' * 16}`\n"
        )
        real_hash = compute_content_hash(scaffold)
        final = (
            f"{body}\n\n"
            f"## Approval\n\n"
            f"- [x] Approved to proceed\n"
            f"- **Content Hash:** `{real_hash}`\n"
        )
        (tmp_path / fname).write_text(final, encoding="utf-8")
    return tmp_path



def test_requirements_txt_exists_and_contains_deps():
    req_path = _SCRIPTS_DIR / "requirements.txt"
    assert req_path.exists(), f"requirements.txt missing at {req_path}"
    content = req_path.read_text(encoding="utf-8")
    import re as _re

    assert _re.search(r"^markdown>=3\.4$", content, _re.MULTILINE)
    assert _re.search(r"^bleach>=6\.0,<7\.0$", content, _re.MULTILINE)
    assert _re.search(r"^packaging>=21\.0$", content, _re.MULTILINE)



_ERROR_PATH_SCENARIOS = [
    "path_not_found",
    "not_a_directory",
    "missing_artifacts",
    "markdown_below_floor",
    "bleach_missing",
    "unapproved",
    "absent_hash",
    "stale_hash",
]


def _make_unapproved_dir(tmp_path):
    for name in ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md"):
        (tmp_path / name).write_text("# Body\n\nbody\n", encoding="utf-8")
    return tmp_path


def _make_absent_hash_dir(tmp_path):
    for name in ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md"):
        (tmp_path / name).write_text(
            "# B\n\nbody\n\n## Approval\n\n- [x] Approved to proceed\n",
            encoding="utf-8",
        )
    return tmp_path


def _make_stale_hash_dir(tmp_path):
    for name in ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md"):
        (tmp_path / name).write_text(
            "# B\n\nbody\n\n"
            "## Approval\n\n"
            "- [x] Approved to proceed\n"
            f"- **Content Hash:** `{'0' * 16}`\n",
            encoding="utf-8",
        )
    return tmp_path


@pytest.mark.parametrize("scenario", _ERROR_PATH_SCENARIOS)
def test_stdout_empty_on_all_error_paths_parametrized(
    scenario, monkeypatch, tmp_path, capsys
):
    """Every error path must keep stdout clean (everything to stderr)."""
    if scenario == "path_not_found":
        target = tmp_path / "nope"
        monkeypatch.setattr(sys, "argv", ["rbb.py", str(target)])
    elif scenario == "not_a_directory":
        f = tmp_path / "file.txt"
        f.write_text("hi", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["rbb.py", str(f)])
    elif scenario == "missing_artifacts":
        monkeypatch.setattr(sys, "argv", ["rbb.py", str(tmp_path)])
    elif scenario == "markdown_below_floor":
        d = _make_unapproved_dir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["rbb.py", str(d)])
        monkeypatch.setattr(
            render_business_brief,
            "_installed_markdown_version",
            lambda: "3.3",
        )
    elif scenario == "bleach_missing":
        d = _make_unapproved_dir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["rbb.py", str(d)])
        monkeypatch.setitem(sys.modules, "bleach", None)
    elif scenario == "unapproved":
        d = _make_unapproved_dir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["rbb.py", str(d)])
    elif scenario == "absent_hash":
        d = _make_absent_hash_dir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["rbb.py", str(d)])
    elif scenario == "stale_hash":
        d = _make_stale_hash_dir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["rbb.py", str(d)])

    with pytest.raises(SystemExit):
        render_business_brief.main()
    captured = capsys.readouterr()
    assert captured.out == "", f"{scenario}: stdout leak: {captured.out!r}"
    assert captured.err != "", f"{scenario}: stderr should carry the error"



def test_render_ts_single_call_at_main_boundary(
    monkeypatch, fixture_approved_triple, fixture_tiny_png_path
):
    """`main()` captures `render_ts` ONCE at startup — not per-file."""
    import itertools

    counter = itertools.count(start=1)

    def counting_ts():
        return f"ts-{next(counter)}"

    monkeypatch.setattr(render_business_brief, "_get_render_ts", counting_ts)
    monkeypatch.setattr(
        render_business_brief, "_LOGO_ASSET_PATH", fixture_tiny_png_path
    )
    monkeypatch.setattr(
        sys, "argv", ["rbb.py", str(fixture_approved_triple)]
    )
    render_business_brief.main()
    # Counter advances exactly once → first call returns "ts-1"; if main()
    # called _get_render_ts more than once, the counter would have advanced
    # further by program end. Probe with one more call:
    next_value = counting_ts()
    assert next_value == "ts-2", (
        f"_get_render_ts called more than once: next would be {next_value}"
    )



_EXPECTED_OUTPUT_FILES = ("scope.html", "architecture.html", "plan.html")


def _run_main_against_fixture(monkeypatch, blueprint_dir, png_path):
    """Shared setup: monkeypatch timestamp + logo, set argv, run main().
    Returns the output directory path."""
    monkeypatch.setattr(
        render_business_brief, "_get_render_ts", lambda: "2026-05-21 00:00 UTC"
    )
    monkeypatch.setattr(
        render_business_brief, "_LOGO_ASSET_PATH", png_path
    )
    monkeypatch.setattr(sys, "argv", ["rbb.py", str(blueprint_dir)])
    render_business_brief.main()
    return blueprint_dir / "business-brief"


def test_integration_structural_output_integrity(
    monkeypatch, fixture_approved_triple, fixture_tiny_png_path, capsys
):
    """P2-8 (a) — structural integrity slice. Each rendered file must have a
    doctype, a closing </html>, the project name, and the rendered timestamp."""
    out_dir = _run_main_against_fixture(
        monkeypatch, fixture_approved_triple, fixture_tiny_png_path
    )
    capsys.readouterr()  # drain stdout/stderr; covered by (b)
    for fname in _EXPECTED_OUTPUT_FILES:
        p = out_dir / fname
        assert p.exists(), f"{fname} not written"
        text = p.read_text(encoding="utf-8")
        assert text.startswith("<!DOCTYPE html>"), f"{fname}: missing doctype"
        assert text.rstrip().endswith("</html>"), f"{fname}: missing </html>"
        assert "My Project" in text, f"{fname}: project name not in output"
        assert "2026-05-21 00:00 UTC" in text, f"{fname}: timestamp not in output"


def test_integration_provenance_and_identity_invariants(
    monkeypatch, fixture_approved_triple, fixture_tiny_png_path, capsys
):
    """P2-8 (b) — provenance & identity slice. The brand-logo <img> tag must
    be byte-identical across all three files, its base64 payload must decode
    to the fixture PNG bytes, and stdout/stderr discipline must hold (3 paths
    on stdout, nothing on stderr)."""
    import re as _re

    out_dir = _run_main_against_fixture(
        monkeypatch, fixture_approved_triple, fixture_tiny_png_path
    )

    logo_tags = {}
    for fname in _EXPECTED_OUTPUT_FILES:
        text = (out_dir / fname).read_text(encoding="utf-8")
        m = _re.search(
            r'<img alt="Neon Ghost" class="brand-logo" src="data:image/png;base64,([^"]+)">',
            text,
        )
        assert m, f"{fname}: brand-logo <img> tag missing"
        logo_tags[fname] = m.group(0)

    distinct = set(logo_tags.values())
    assert len(distinct) == 1, "brand-logo <img> tag differs across files"
    sample_payload = next(iter(distinct)).split("base64,", 1)[1].rstrip('">')
    assert base64.b64decode(sample_payload) == fixture_tiny_png_path.read_bytes()

    captured = capsys.readouterr()
    stdout_lines = [ln for ln in captured.out.split("\n") if ln]
    assert len(stdout_lines) == 3, f"expected 3 stdout paths, got: {captured.out!r}"
    for ln in stdout_lines:
        assert ln.endswith(".html")
    assert captured.err == "", f"stderr leak: {captured.err!r}"


def test_main_dry_run_writes_no_files(
    monkeypatch, fixture_approved_triple, fixture_tiny_png_path, capsys
):
    """P3-7: `--dry-run` runs the full approval gate and resolution chain
    but writes nothing. The three would-be output paths are printed to
    stdout (one per line) — useful for previewing on read-only filesystems
    or in CI."""
    monkeypatch.setattr(
        render_business_brief, "_LOGO_ASSET_PATH", fixture_tiny_png_path
    )
    monkeypatch.setattr(
        sys, "argv", ["rbb.py", str(fixture_approved_triple), "--dry-run"]
    )
    render_business_brief.main()
    captured = capsys.readouterr()
    stdout_lines = [ln for ln in captured.out.split("\n") if ln]
    assert len(stdout_lines) == 3
    for ln in stdout_lines:
        assert ln.endswith(".html")
    # No business-brief/ directory created
    assert not (fixture_approved_triple / "business-brief").exists()


def test_main_logo_flag_overrides_default(
    monkeypatch, fixture_approved_triple, fixture_tiny_png_path, capsys, tmp_path
):
    """P3-7: `--logo PATH` overrides the default brand-logo PNG. Verified by
    setting the module default to a missing file (so the default load would
    warn) and pointing `--logo` at a valid PNG — rendered output must contain
    the brand-logo <img> with no stderr warning."""
    # Default points at a missing file
    monkeypatch.setattr(
        render_business_brief,
        "_LOGO_ASSET_PATH",
        tmp_path / "no-such-default.png",
    )
    monkeypatch.setattr(
        render_business_brief, "_get_render_ts", lambda: "2026-05-21 00:00 UTC"
    )
    monkeypatch.setattr(
        sys, "argv",
        [
            "rbb.py", str(fixture_approved_triple),
            "--logo", str(fixture_tiny_png_path),
        ],
    )
    render_business_brief.main()
    out_dir = fixture_approved_triple / "business-brief"
    for fname in ("scope.html", "architecture.html", "plan.html"):
        text = (out_dir / fname).read_text(encoding="utf-8")
        assert '<img alt="Neon Ghost" class="brand-logo"' in text
    captured = capsys.readouterr()
    assert "WARNING" not in captured.err


def test_integration_idempotent_re_run(
    monkeypatch, fixture_approved_triple, fixture_tiny_png_path, capsys
):
    """P2-8 (c) — idempotency slice. Running main() twice against the same
    fixture must produce byte-identical content."""
    out_dir = _run_main_against_fixture(
        monkeypatch, fixture_approved_triple, fixture_tiny_png_path
    )
    capsys.readouterr()
    first = {
        fname: (out_dir / fname).read_text(encoding="utf-8")
        for fname in _EXPECTED_OUTPUT_FILES
    }
    render_business_brief.main()
    capsys.readouterr()
    for fname, first_text in first.items():
        new_text = (out_dir / fname).read_text(encoding="utf-8")
        assert new_text == first_text, (
            f"{fname}: idempotent re-run produced different content"
        )



def _read_skill_md() -> str:
    skill_md_path = _SCRIPTS_DIR.parent / "SKILL.md"
    return skill_md_path.read_text(encoding="utf-8")


def test_r6_skill_md_phase4_heading():
    text = _read_skill_md()
    assert text.count("## Phase 4: Business Brief") == 1


def test_r6_skill_md_reentry_sentence():
    text = _read_skill_md()
    sentence = (
        "If all three phase artifacts (SCOPE.md, ARCHITECTURE.md, PLAN.md) "
        "are already approved on entry, offer the Phase 4 prompt directly "
        "rather than re-entering Phase 1."
    )
    assert text.count(sentence) == 1


def test_r6_skill_md_see_also_link():
    text = _read_skill_md()
    assert "references/phase-business-brief.md" in text



def _read_phase_doc() -> str:
    p = (
        _SCRIPTS_DIR.parent
        / "references"
        / "phase-business-brief.md"
    )
    return p.read_text(encoding="utf-8")


def test_r6_phase_doc_rerunning_section():
    text = _read_phase_doc()
    assert text.count("## Re-running Phase 4") == 1


def test_r6_phase_doc_zero_external_links():
    text = _read_phase_doc()
    assert "http://" not in text
    assert "https://" not in text


def test_r6_phase_doc_no_img_tags():
    text = _read_phase_doc()
    assert "<img" not in text


def test_validate_blueprint_import_safety():
    """`import validate_blueprint` in a clean subprocess must be silent.

    AD10 elevates validate_blueprint.py from CLI script to imported library.
    Any future top-level side effect (argparse, print, sys.exit, network I/O
    at import time) would break render_business_brief.py and is caught here.
    """
    vdir = render_business_brief._VALIDATE_DIR
    shared = render_business_brief._SHARED_SCRIPTS
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(vdir), str(shared)]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import validate_blueprint"],
        cwd=str(vdir),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"import validate_blueprint failed: stderr={result.stderr!r}"
    )
    assert result.stdout == "", f"unexpected stdout: {result.stdout!r}"
