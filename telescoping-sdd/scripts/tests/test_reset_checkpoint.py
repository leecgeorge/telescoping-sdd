"""Tests for reset_checkpoint.py (the C1 shared leaf) and the emit wiring (C2/C3).

Covers:
  T1 — the pure `build_reset_checkpoint_advisory` builder + `reread_list_for`
       accessor (R3, R4).
  T2 — the guarded `emit_reset_checkpoint` printer's R9 isolation.
  T3 — static-table guards: R7 dangling-ref, leaf import-guard (source + clean
       subprocess), and `next_step_label`/`_GATE_DISPLAY` consistency vs the
       validators' phase constants (R3 no-drift).
  T4 — shared spawn-and-capture helper functions (module-level, below imports).
  T5/T6 — end-to-end emission at the real `--approve` / `--completion-gate`
       call sites (R1, R2).
  T9 — R8 hash-neutrality / inertness (stub-vs-live equivalence, in-process).

The module is loaded via the importlib + sys.path pattern used across the
shared-script suite (mirrors test_run_state.py / test_reapproval_gate.py).
"""

from __future__ import annotations

import argparse
import ast
import builtins
import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"
_VS_DIR = _SCRIPTS.parent / "skills" / "spec-driven-dev" / "scripts"
_VB_DIR = _SCRIPTS.parent / "skills" / "project-blueprint" / "scripts"
_VS = _VS_DIR / "validate_spec.py"
_VB = _VB_DIR / "validate_blueprint.py"


def _load_reset_checkpoint():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    if "reset_checkpoint" in sys.modules:
        return importlib.reload(sys.modules["reset_checkpoint"])
    return importlib.import_module("reset_checkpoint")


def _load_validate_spec():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    if str(_VS_DIR) not in sys.path:
        sys.path.insert(0, str(_VS_DIR))
    sys.modules.pop("validate_spec", None)  # avoid cross-tier shadowing (DEF-03)
    return importlib.import_module("validate_spec")


def _load_validate_blueprint():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    if str(_VB_DIR) not in sys.path:
        sys.path.insert(0, str(_VB_DIR))
    sys.modules.pop("validate_blueprint", None)  # avoid cross-tier shadowing
    return importlib.import_module("validate_blueprint")


def _load_content_hash():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    return importlib.import_module("content_hash")


rc = _load_reset_checkpoint()


# ---------------------------------------------------------------------------
# T4 — shared spawn-and-capture helpers (DEF-20; used by the T5/T6 emission
# tests). Test-only, no independent behavior — a wrong helper fails T5/T6.
# ---------------------------------------------------------------------------

_RESET_LINE_PREFIX = "RESET-CHECKPOINT:"


def _spawn_validator(script: Path, *args):
    """Run a validator as a subprocess on the venv python; return
    (stdout, stderr, returncode)."""
    result = subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True
    )
    return result.stdout, result.stderr, result.returncode


def _has_reset_checkpoint(stdout: str) -> bool:
    """True iff stdout carries a RESET-CHECKPOINT: advisory line (not the
    -DEBUG stderr trace)."""
    return any(
        ln.startswith(_RESET_LINE_PREFIX) for ln in stdout.splitlines()
    )


def _reset_checkpoint_line(stdout: str):
    """Return the single RESET-CHECKPOINT: line, or None if absent."""
    lines = [ln for ln in stdout.splitlines() if ln.startswith(_RESET_LINE_PREFIX)]
    return lines[0] if lines else None


# ---------------------------------------------------------------------------
# T1 — build_reset_checkpoint_advisory (pure) + reread_list_for (R3, R4)
# ---------------------------------------------------------------------------


def test_advisory_sdd_spec_names_gate_next_and_reread_paths():
    """spec→Design row: gate name, next step, exact three paths (R4 AC1)."""
    msg = rc.build_reset_checkpoint_advisory("sdd", "spec")
    assert msg.startswith("RESET-CHECKPOINT: ")
    assert "Specify gate approved" in msg
    assert "Design" in msg
    # Skill-qualified, `skills/` prefix stripped, comma-separated, in order.
    assert (
        "spec-driven-dev/references/phase-design.md, "
        "spec-driven-dev/references/hash-and-cascade.md, "
        "spec-driven-dev/references/panel-review.md" in msg
    )
    # No raw `skills/` prefix leaks into the rendered advisory.
    assert "skills/spec-driven-dev" not in msg


def test_advisory_sdd_design_and_tasks_rows_have_correct_next_phase():
    design = rc.build_reset_checkpoint_advisory("sdd", "design")
    assert "Design gate approved" in design
    assert "Tasks" in design
    assert "spec-driven-dev/references/phase-tasks.md" in design

    tasks = rc.build_reset_checkpoint_advisory("sdd", "tasks")
    assert "Tasks gate approved" in tasks
    assert "Implement" in tasks
    # The Implement row lists only hash-and-cascade.md + workflow-overview.md.
    assert "spec-driven-dev/references/hash-and-cascade.md" in tasks
    assert "spec-driven-dev/references/workflow-overview.md" in tasks
    assert "phase-tasks.md" not in tasks
    assert "panel-review.md" not in tasks


def test_advisory_blueprint_rows_name_correct_next_step():
    scope = rc.build_reset_checkpoint_advisory("blueprint", "scope")
    assert "Scope gate approved" in scope
    assert "Architecture" in scope
    assert "project-blueprint/references/phase-architecture.md" in scope

    arch = rc.build_reset_checkpoint_advisory("blueprint", "architecture")
    assert "Architecture gate approved" in arch
    assert "Plan" in arch
    assert "project-blueprint/references/phase-plan.md" in arch


def test_completion_gate_variant_is_terminal_and_listless():
    """completion_gate=True: caveat present, no `references/` path (R1 AC3)."""
    msg = rc.build_reset_checkpoint_advisory("sdd", "tasks", completion_gate=True)
    assert msg.startswith("RESET-CHECKPOINT: ")
    assert "Implement completion gate passed" in msg
    assert "not an assertion of overall feature completion" in msg
    assert "housekeeping" in msg
    # Terminal → carries NO re-read list.
    assert "references/" not in msg


def test_blueprint_plan_carries_terminal_framing_and_handoff_list():
    """H02 special case: plan carries terminal framing AND its handoff list."""
    msg = rc.build_reset_checkpoint_advisory("blueprint", "plan")
    assert msg.startswith("RESET-CHECKPOINT: ")
    assert "Plan gate approved" in msg
    assert "terminal blueprint gate" in msg
    assert "highest-value blueprint reset point" in msg.lower()
    # Still carries the two handoff re-read paths.
    assert "spec-driven-dev/references/phase-specify.md" in msg
    assert "spec-driven-dev/references/workflow-overview.md" in msg


def test_non_terminal_gate_omits_highest_value_framing():
    """Pins the H02 framing to exactly the plan row."""
    msg = rc.build_reset_checkpoint_advisory("sdd", "spec")
    assert "highest-value blueprint reset point" not in msg.lower()


def test_builder_raises_keyerror_on_unknown_gate():
    with pytest.raises(KeyError):
        rc.build_reset_checkpoint_advisory("sdd", "nonexistent")


def test_reread_list_for_returns_label_and_paths():
    """Accessor contract (DEF-01 keeps it public)."""
    label, paths = rc.reread_list_for("sdd", "spec")
    assert label == "Design"
    assert paths == [
        "skills/spec-driven-dev/references/phase-design.md",
        "skills/spec-driven-dev/references/hash-and-cascade.md",
        "skills/spec-driven-dev/references/panel-review.md",
    ]
    with pytest.raises(KeyError):
        rc.reread_list_for("sdd", "bogus")


# ---------------------------------------------------------------------------
# T2 — emit_reset_checkpoint (guarded printer, R9 isolation)
# ---------------------------------------------------------------------------


def test_emit_prints_exactly_one_reset_checkpoint_line(capsys):
    result = rc.emit_reset_checkpoint("sdd", "spec")
    assert result is None
    out = capsys.readouterr()
    lines = [ln for ln in out.out.splitlines() if ln.startswith("RESET-CHECKPOINT:")]
    assert len(lines) == 1
    assert out.err == ""


def test_emit_swallows_builder_exception_returns_none_no_stdout_traces_type_to_stderr(
    monkeypatch, capsys
):
    """R9 AC4: injected builder exception → None, no stdout, exact stderr trace."""

    def _raise(*args, **kwargs):
        raise KeyError("boom")

    monkeypatch.setattr(rc, "build_reset_checkpoint_advisory", _raise)
    result = rc.emit_reset_checkpoint("sdd", "spec")
    out = capsys.readouterr()
    assert result is None
    assert out.out == ""
    assert out.err.strip() == "RESET-CHECKPOINT-DEBUG: KeyError"


def test_emit_swallows_broken_pipe_on_stdout_write(monkeypatch, capsys):
    """R9 AC3: a BrokenPipeError on the stdout write is swallowed."""

    def _raise_broken_pipe(*args, **kwargs):
        raise BrokenPipeError("pipe gone")

    monkeypatch.setattr(builtins, "print", _raise_broken_pipe)
    # print() is now broken for both stdout and the stderr trace attempt; the
    # emitter must still return None with no traceback escaping.
    result = rc.emit_reset_checkpoint("sdd", "spec")
    assert result is None


def test_emit_survives_double_failure_builder_and_stderr_raise(monkeypatch):
    """R9 innermost-guard: builder raises AND the stderr write also raises."""

    def _raise_builder(*args, **kwargs):
        raise ValueError("builder down")

    def _raise_print(*args, **kwargs):
        raise OSError("stderr down")

    monkeypatch.setattr(rc, "build_reset_checkpoint_advisory", _raise_builder)
    monkeypatch.setattr(builtins, "print", _raise_print)
    result = rc.emit_reset_checkpoint("sdd", "spec")
    assert result is None


# ---------------------------------------------------------------------------
# T3 — static-table guards: R7 dangling-ref, import-guard, label consistency
# ---------------------------------------------------------------------------


def test_every_reread_path_exists_on_disk():
    """R7: every path in every RESET_READ_LISTS row resolves to a real file."""
    missing = []
    for (tier, gate), (_label, paths) in rc.RESET_READ_LISTS.items():
        for path in paths:
            if not (rc._PLUGIN_ROOT / path).is_file():
                missing.append(f"({tier!r}, {gate!r}): {path}")
    assert not missing, "dangling re-read path(s): " + "; ".join(missing)


def test_reset_checkpoint_source_imports_no_validator():
    """R3/AD2: leaf source references no validator (static AST check)."""
    src = (_SCRIPTS / "reset_checkpoint.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(n.name.split(".")[0] for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "validate_spec" not in imported
    assert "validate_blueprint" not in imported


def test_reset_checkpoint_pulls_in_no_validator_from_clean_subprocess():
    """R3/AD2 leaf — collection-order-independent proof.

    A clean subprocess with only `scripts/` on PYTHONPATH imports
    reset_checkpoint and asserts neither validator was transitively pulled in.
    Inherit the parent env, override only PYTHONPATH (never a from-scratch env
    that drops PATH/HOME/LANG).
    """
    code = (
        "import sys\n"
        "import reset_checkpoint\n"
        "bad = [m for m in ('validate_spec', 'validate_blueprint') "
        "if m in sys.modules]\n"
        "sys.exit('LEAKED:' + ','.join(bad) if bad else 0)\n"
    )
    env = {**os.environ, "PYTHONPATH": str(_SCRIPTS)}
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"reset_checkpoint pulled in a validator: {result.stdout}{result.stderr}"
    )


def _gate_index_map(phases):
    """Map each phase's artifact-filename stem (lowercased) to its index."""
    return {
        Path(filename).stem.lower(): i for i, (_label, filename) in enumerate(phases)
    }


def test_next_step_label_matches_validator_phase_constants():
    """arch-H01 / R3 no-drift: each phase-name next_step_label equals the
    validators' canonical next-phase label; a stale label FAILs naming the row."""
    vs = _load_validate_spec()
    vb = _load_validate_blueprint()

    tier_constants = {
        "sdd": (vs.SDD_RUN_STATE_PHASES, vs.SDD_RUN_STATE_TERMINAL),
        "blueprint": (vb.BLUEPRINT_RUN_STATE_PHASES, vb.BLUEPRINT_RUN_STATE_TERMINAL),
    }
    # ("blueprint","plan")'s label is the prose handoff string (its tier's
    # terminal is None), so it is allowlisted — H02 test covers its framing.
    allowlist = {("blueprint", "plan")}

    for (tier, gate), (next_label, _paths) in rc.RESET_READ_LISTS.items():
        if (tier, gate) in allowlist:
            continue
        phases, terminal = tier_constants[tier]
        idx_map = _gate_index_map(phases)
        i = idx_map[gate]
        expected = phases[i + 1][0] if i + 1 < len(phases) else terminal
        assert next_label == expected, (
            f"next_step_label drift at ({tier!r}, {gate!r}): "
            f"table={next_label!r} vs validator={expected!r}"
        )


def test_gate_display_matches_validator_phase_constants():
    """R3 no-drift: each `_GATE_DISPLAY` label equals the validators'
    canonical display label for that gate; a stale label FAILs naming the
    key. Mirrors `test_next_step_label_matches_validator_phase_constants`
    above, closing the same drift risk for the "<X> gate approved" clause."""
    vs = _load_validate_spec()
    vb = _load_validate_blueprint()

    all_phases = list(vs.SDD_RUN_STATE_PHASES) + list(vb.BLUEPRINT_RUN_STATE_PHASES)
    label_by_stem = {
        Path(filename).stem.lower(): label for label, filename in all_phases
    }

    for gate, display in rc._GATE_DISPLAY.items():
        expected = label_by_stem[gate]
        assert display == expected, (
            f"_GATE_DISPLAY drift at {gate!r}: "
            f"table={display!r} vs validator={expected!r}"
        )


# ---------------------------------------------------------------------------
# T5 — emission at the real validate_spec.py call sites (R1). Subprocess via
# the T4 helper. Fixtures below are the empirically-verified minimal shapes.
# ---------------------------------------------------------------------------

_VALID_SPEC_MD = """\
# Spec: Demo Feature

**PLAN feature identifier:** `n/a`

## Objective

Provide a demonstrable behavior for testing the approval gate.

## Requirements

### R1: Do the thing

The system does the thing.

**Acceptance Criteria:**
- GIVEN a request
  WHEN it arrives
  THEN the thing happens.

## Project Structure

- `src/demo.py` — the thing.

## Boundaries

In scope: the thing. Out of scope: everything else.

## Success Criteria

- [ ] The thing happens reliably.

## Panel Review

### Trajectory

| Pass | Date       | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------------|-------|-------------|-----------|----------|--------|-------|
| 1    | 2026-07-05 | 0     | 0           | 1         | 0        | 0      | converged (0 HIGH) |

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [ ] Approved to proceed to next phase
- **Content Hash:** `pending`
"""

# A minimal spec.md — just enough to satisfy the dir↔identifier cross-check that
# runs on every SDD approve (it reads spec.md's identifier), for design/tasks.
_SPEC_STUB_MD = "# Spec\n\n**PLAN feature identifier:** `n/a`\n\n## Objective\n\nx\n"


def _approvable_doc(title: str) -> str:
    """A minimal --force-approvable doc (Approval section + standalone id)."""
    return (
        f"# {title}\n\n**PLAN feature identifier:** `n/a`\n\n"
        "## Approval\n\n- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )


def _spec_dir(tmp_path: Path, name: str = "demo") -> Path:
    d = tmp_path / "specs" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _generic_tasks_doc() -> str:
    return (
        "# Tasks: Feat\n\n## Summary\n\n"
        "| Task | Description | Requirement | Dependencies | Parallel | Status |\n"
        "|------|-------------|-------------|--------------|----------|--------|\n"
        "| T1 | demo | R1 | None | No | Done |\n\n"
        "## Phase 1\n\n"
        "### - [x] T1: Title T1\n\n"
        "- **Requirement:** R1\n"
        "- **Description:** do T1\n"
        "- **Files:**\n"
        "  - Create: `infra/x.tf`\n"
        "- **Dependencies:** None\n"
        "- **Parallel:** No\n"
        "- **Acceptance Criteria:**\n"
        "  - GIVEN a precondition\n"
        "    WHEN an action occurs\n"
        "    THEN a result holds\n"
        "- **Verification:** `terraform validate`\n"
    )


def _python_missing_test_tasks_doc() -> str:
    return (
        "# Tasks: Feat\n\n## Summary\n\n"
        "| Task | Description | Requirement | Dependencies | Parallel | Status |\n"
        "|------|-------------|-------------|--------------|----------|--------|\n"
        "| T1 | demo | R1 | None | No | Done |\n\n"
        "## Phase 1\n\n"
        "### - [x] T1: Title T1\n\n"
        "- **Requirement:** R1\n"
        "- **Description:** do T1\n"
        "- **Files:**\n"
        "  - Create: `src/x.py`\n"
        "- **Dependencies:** None\n"
        "- **Parallel:** No\n"
        "- **Acceptance Criteria:**\n"
        "  - GIVEN a precondition\n"
        "    WHEN an action occurs\n"
        "    THEN a result holds\n"
        "- **Tests:**\n"
        "  - `test_definitely_absent` — checks the thing\n"
        "- **Verification:** `pytest -q`\n"
    )


def test_approve_spec_emits_reset_checkpoint_and_exits_zero(tmp_path):
    d = _spec_dir(tmp_path)
    (d / "spec.md").write_text(_VALID_SPEC_MD, encoding="utf-8")
    out, _err, code = _spawn_validator(
        _VS, str(d), "--approve", "spec", "--project-root", str(tmp_path)
    )
    assert code == 0, out
    line = _reset_checkpoint_line(out)
    assert line is not None
    assert "Specify gate approved" in line
    assert "Design" in line


def test_approve_design_and_tasks_emit_correct_next_phase(tmp_path):
    d = _spec_dir(tmp_path)
    (d / "spec.md").write_text(_SPEC_STUB_MD, encoding="utf-8")
    (d / "design.md").write_text(_approvable_doc("Design"), encoding="utf-8")
    (d / "tasks.md").write_text(_approvable_doc("Tasks"), encoding="utf-8")

    out, _e, code = _spawn_validator(
        _VS, str(d), "--approve", "design", "--force", "--project-root", str(tmp_path)
    )
    assert code == 0, out
    dline = _reset_checkpoint_line(out)
    assert dline is not None and "Design gate approved" in dline and "Tasks" in dline

    out, _e, code = _spawn_validator(
        _VS, str(d), "--approve", "tasks", "--force", "--project-root", str(tmp_path)
    )
    assert code == 0, out
    tline = _reset_checkpoint_line(out)
    assert tline is not None and "Tasks gate approved" in tline and "Implement" in tline


def test_refused_approve_emits_no_reset_checkpoint(tmp_path):
    d = _spec_dir(tmp_path)
    # Structurally invalid spec (missing required sections), no --force → refused.
    (d / "spec.md").write_text(
        "# Spec\n\n**PLAN feature identifier:** `n/a`\n\n## Objective\n\nx\n",
        encoding="utf-8",
    )
    out, _e, code = _spawn_validator(
        _VS, str(d), "--approve", "spec", "--project-root", str(tmp_path)
    )
    assert code == 1, out
    assert not _has_reset_checkpoint(out)


def test_task_tick_restamp_emits_no_reset_checkpoint(tmp_path):
    d = _spec_dir(tmp_path)
    (d / "spec.md").write_text(_SPEC_STUB_MD, encoding="utf-8")
    (d / "tasks.md").write_text(_approvable_doc("Tasks"), encoding="utf-8")
    out, _e, code = _spawn_validator(
        _VS, str(d), "--approve", "tasks", "--task-tick", "--project-root", str(tmp_path)
    )
    assert code == 0, out
    assert not _has_reset_checkpoint(out)


def test_passing_completion_gate_emits_listless_reset_checkpoint(tmp_path):
    d = _spec_dir(tmp_path, name="feat")
    (d / "tasks.md").write_text(_generic_tasks_doc(), encoding="utf-8")
    out, _e, code = _spawn_validator(
        _VS, str(d), "--completion-gate", "--language", "generic",
        "--project-root", str(tmp_path),
    )
    assert code == 0, out
    line = _reset_checkpoint_line(out)
    assert line is not None
    assert "Implement completion gate passed" in line
    # Terminal / list-free — no re-read paths.
    assert "references/" not in line


def test_failing_completion_gate_emits_no_reset_checkpoint(tmp_path):
    d = _spec_dir(tmp_path, name="feat")
    (d / "tasks.md").write_text(_python_missing_test_tasks_doc(), encoding="utf-8")
    out, _e, code = _spawn_validator(
        _VS, str(d), "--completion-gate", "--language", "python", "--strict-r5",
        "--project-root", str(tmp_path),
    )
    assert code == 1, out
    assert not _has_reset_checkpoint(out)


def test_forced_past_fail_approve_still_emits_reset_checkpoint(tmp_path):
    d = _spec_dir(tmp_path)
    # Invalid spec (would FAIL the gate) but --force stamps anyway → still emits.
    (d / "spec.md").write_text(
        "# Spec\n\n**PLAN feature identifier:** `n/a`\n\n## Objective\n\nx\n\n"
        "## Approval\n\n- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    out, _e, code = _spawn_validator(
        _VS, str(d), "--approve", "spec", "--force", "--project-root", str(tmp_path)
    )
    assert code == 0, out
    assert _has_reset_checkpoint(out)


def test_post_stamp_marker_corrupt_emits_no_reset_checkpoint(tmp_path):
    """test-M01: a post-stamp MarkerCorruptError returns 1 without emitting."""
    d = _spec_dir(tmp_path)
    spec = d / "spec.md"
    spec.write_text(_VALID_SPEC_MD, encoding="utf-8")
    # Seed a clean first approval in-process (no obligation recorded).
    vs = _load_validate_spec()
    vs.approve_document(spec, project_root=tmp_path)
    # Edit the approved content so a re-approval must record an obligation.
    # Append (preserving the stamped Content Hash) — a full rewrite would reset
    # the hash to `pending` and be read as a first approval (no marker touched).
    stamped = spec.read_text(encoding="utf-8")
    spec.write_text(
        stamped + "\n\nExtra prose that drifts the hash.\n", encoding="utf-8"
    )
    # ...then corrupt the marker so the obligation write raises MarkerCorruptError.
    sdd = tmp_path / ".sdd"
    sdd.mkdir(exist_ok=True)
    (sdd / "pending-review.json").write_text("{not valid json", encoding="utf-8")

    out, _e, code = _spawn_validator(
        _VS, str(d), "--approve", "spec", "--project-root", str(tmp_path)
    )
    assert code == 1, out
    assert not _has_reset_checkpoint(out)


# ---------------------------------------------------------------------------
# T6 — emission at the real validate_blueprint.py call site (R2). Subprocess.
# ---------------------------------------------------------------------------


def _bp_dir(tmp_path: Path) -> Path:
    d = tmp_path / "blueprint"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bp_doc(title: str) -> str:
    return (
        f"# {title}\n\n## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )


def test_blueprint_approve_scope_arch_plan_emit_reset_checkpoint(tmp_path):
    d = _bp_dir(tmp_path)
    (d / "SCOPE.md").write_text(_bp_doc("SCOPE"), encoding="utf-8")
    (d / "ARCHITECTURE.md").write_text(_bp_doc("ARCHITECTURE"), encoding="utf-8")
    (d / "PLAN.md").write_text(_bp_doc("PLAN"), encoding="utf-8")

    cases = [
        ("scope", "Scope gate approved", "Architecture"),
        ("architecture", "Architecture gate approved", "Plan"),
        ("plan", "Plan gate approved", "hand off"),
    ]
    for gate, gate_phrase, next_phrase in cases:
        out, _e, code = _spawn_validator(
            _VB, str(d), "--approve", gate, "--force", "--project-root", str(tmp_path)
        )
        assert code == 0, out
        line = _reset_checkpoint_line(out)
        assert line is not None, f"no line for gate {gate}"
        assert gate_phrase in line
        assert next_phrase in line


def test_blueprint_refused_approve_emits_no_reset_checkpoint(tmp_path):
    d = _bp_dir(tmp_path)
    # Structurally invalid SCOPE (missing required sections), no --force → refused.
    (d / "SCOPE.md").write_text(_bp_doc("SCOPE"), encoding="utf-8")
    out, _e, code = _spawn_validator(
        _VB, str(d), "--approve", "scope", "--project-root", str(tmp_path)
    )
    assert code == 1, out
    assert not _has_reset_checkpoint(out)


def test_blueprint_forced_past_fail_still_emits(tmp_path):
    d = _bp_dir(tmp_path)
    # Would FAIL the gate, but --force stamps anyway → still emits (R2 force AC).
    (d / "SCOPE.md").write_text(_bp_doc("SCOPE"), encoding="utf-8")
    out, _e, code = _spawn_validator(
        _VB, str(d), "--approve", "scope", "--force", "--project-root", str(tmp_path)
    )
    assert code == 0, out
    assert _has_reset_checkpoint(out)


def test_blueprint_plan_approval_emits_terminal_framing_with_list(tmp_path):
    d = _bp_dir(tmp_path)
    (d / "PLAN.md").write_text(_bp_doc("PLAN"), encoding="utf-8")
    out, _e, code = _spawn_validator(
        _VB, str(d), "--approve", "plan", "--force", "--project-root", str(tmp_path)
    )
    assert code == 0, out
    line = _reset_checkpoint_line(out)
    assert line is not None
    assert "terminal blueprint gate" in line
    assert "highest-value blueprint reset point" in line.lower()
    # Still carries its handoff re-read paths.
    assert "spec-driven-dev/references/phase-specify.md" in line
    assert "spec-driven-dev/references/workflow-overview.md" in line


# ---------------------------------------------------------------------------
# T9 — R8 hash-neutrality / inertness. IN-PROCESS at the emit call-site handler
# (_handle_approve / _handle_completion_gate — NOT approve_document, NOT
# subprocess: a subprocess is a fresh interpreter that would not see the
# monkeypatch, making the live-vs-stubbed comparison vacuous). Each sub-test
# also asserts an emit-reached canary via capsys (live stdout HAS the line, the
# stubbed run does NOT) so a Namespace slip can't yield a vacuous pass.
# ---------------------------------------------------------------------------

# Real one-CFC PLAN (modeled on SOC_COACH_PLAN; inlined, NOT cross-imported from
# the blueprint skill's test dir). Its `--approve plan` writes a per-CFC hash
# baseline into `## Approval`, which the emitter must not perturb (R8 AC3).
_CFC_PLAN = """\
# Implementation Plan: demo

## Feature Breakdown

### F11: Lock-order phase-1

- **Description:** first
- **Acceptance Criteria:**
  - Acquires locks in canonical order

### F13: Lock-order phase-2

- **Description:** second
- **Acceptance Criteria:**
  - Acquires locks in canonical order

### F36: Enforcement owner

- **Description:** owns rules
- **Acceptance Criteria:**
  - Ships LockOrderCheck

## Cross-Feature Contracts

### CFC-1: Six-table lock order

- **Participating features:** F11, F13
- **Contract:** Locks acquired in canonical order A->B->C to prevent deadlock, committed at PLAN level.
- **Per-feature AC:** WHEN this feature acquires locks, THEN it uses canonical order A->B->C.
- **Enforcement:** F36 owns the ArchUnit rule LockOrderCheck that verifies order in CI.

## Approval

- [ ] Approved to proceed to feature development
- **Content Hash:** `pending`
"""

# ISO-8601 timestamps (e.g. a `.sdd/pending-review.json` stamped_at) would differ
# by wall clock between the two stamp runs; normalize them so the tree diff
# isolates emitter-caused divergence, not clock skew (critic pass-1).
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\s\"']*")


def _norm_bytes(raw: bytes) -> bytes:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    return _TS_RE.sub("<TS>", text).encode("utf-8")


def _tree_snapshot(root: Path) -> dict:
    """relpath -> normalized bytes for every file under `root`."""
    return {
        str(p.relative_to(root)): _norm_bytes(p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _stamped_hash(doc_text: str):
    m = re.search(r"\*\*Content Hash:\*\*\s*`([0-9a-f]+)`", doc_text)
    return m.group(1) if m else None


def _has_reset_line(stdout: str) -> bool:
    return any(ln.startswith("RESET-CHECKPOINT:") for ln in stdout.splitlines())


def test_approve_hash_and_tree_identical_live_vs_stubbed_emitter(
    tmp_path, monkeypatch, capsys
):
    """R8 AC1 + structural + DEF-06 full-tree diff, from ONE live-vs-stubbed pair."""
    vs = _load_validate_spec()
    ch = _load_content_hash()
    args = argparse.Namespace(approve="spec", force=True, task_tick=False, language=None)

    # LIVE run (real emitter).
    live_tree = tmp_path / "live"
    live_spec = live_tree / "specs" / "demo"
    live_spec.mkdir(parents=True)
    (live_spec / "spec.md").write_text(_VALID_SPEC_MD, encoding="utf-8")
    rc_live = vs._handle_approve(args, live_spec, live_tree)
    out_live = capsys.readouterr().out
    assert rc_live == 0
    assert _has_reset_line(out_live)  # canary: live actually reached the emit

    # STUBBED run (emitter monkeypatched to a no-op in the validator namespace).
    monkeypatch.setattr(vs, "emit_reset_checkpoint", lambda *a, **k: None)
    stub_tree = tmp_path / "stub"
    stub_spec = stub_tree / "specs" / "demo"
    stub_spec.mkdir(parents=True)
    (stub_spec / "spec.md").write_text(_VALID_SPEC_MD, encoding="utf-8")
    rc_stub = vs._handle_approve(args, stub_spec, stub_tree)
    out_stub = capsys.readouterr().out
    assert rc_stub == 0
    assert not _has_reset_line(out_stub)  # canary: stub did NOT emit

    live_hash = _stamped_hash((live_spec / "spec.md").read_text(encoding="utf-8"))
    stub_hash = _stamped_hash((stub_spec / "spec.md").read_text(encoding="utf-8"))
    # (a) stamped content-hashes byte-identical live vs stubbed.
    assert live_hash == stub_hash
    # (b) structural: live stamp hash == compute_content_hash(fixture) directly.
    assert live_hash == ch.compute_content_hash(_VALID_SPEC_MD)
    # (c) full resulting file trees byte-identical (timestamps normalized).
    assert _tree_snapshot(live_tree) == _tree_snapshot(stub_tree)


def test_completion_gate_tasks_md_bytes_identical_live_vs_stubbed(
    tmp_path, monkeypatch, capsys
):
    """R8 AC2/AC4: a passing --completion-gate writes no file, live vs stubbed."""
    vs = _load_validate_spec()
    args = argparse.Namespace(language="generic", strict_r5=False)

    live_tree = tmp_path / "live"
    live_feat = live_tree / "specs" / "feat"
    live_feat.mkdir(parents=True)
    (live_feat / "tasks.md").write_text(_generic_tasks_doc(), encoding="utf-8")
    rc_live = vs._handle_completion_gate(args, live_feat, live_tree)
    out_live = capsys.readouterr().out
    assert rc_live == 0
    assert _has_reset_line(out_live)  # canary

    monkeypatch.setattr(vs, "emit_reset_checkpoint", lambda *a, **k: None)
    stub_tree = tmp_path / "stub"
    stub_feat = stub_tree / "specs" / "feat"
    stub_feat.mkdir(parents=True)
    (stub_feat / "tasks.md").write_text(_generic_tasks_doc(), encoding="utf-8")
    rc_stub = vs._handle_completion_gate(args, stub_feat, stub_tree)
    out_stub = capsys.readouterr().out
    assert rc_stub == 0
    assert not _has_reset_line(out_stub)  # canary

    assert (live_feat / "tasks.md").read_bytes() == (stub_feat / "tasks.md").read_bytes()
    assert _tree_snapshot(live_tree) == _tree_snapshot(stub_tree)


def test_cfc_baseline_identical_live_vs_stubbed_on_blueprint_plan(
    tmp_path, monkeypatch, capsys
):
    """R8 AC3: a CFC-bound blueprint --approve plan's per-CFC baseline (written
    into PLAN.md's ## Approval) + any .sdd marker are byte-identical, live vs
    stubbed."""
    vb = _load_validate_blueprint()
    args = argparse.Namespace(approve="plan", force=True)

    live_tree = tmp_path / "live"
    live_bp = live_tree / "blueprint"
    live_bp.mkdir(parents=True)
    (live_bp / "PLAN.md").write_text(_CFC_PLAN, encoding="utf-8")
    rc_live = vb._handle_approve(args, live_bp, live_tree)
    out_live = capsys.readouterr().out
    assert rc_live == 0
    assert _has_reset_line(out_live)  # canary

    monkeypatch.setattr(vb, "emit_reset_checkpoint", lambda *a, **k: None)
    stub_tree = tmp_path / "stub"
    stub_bp = stub_tree / "blueprint"
    stub_bp.mkdir(parents=True)
    (stub_bp / "PLAN.md").write_text(_CFC_PLAN, encoding="utf-8")
    rc_stub = vb._handle_approve(args, stub_bp, stub_tree)
    out_stub = capsys.readouterr().out
    assert rc_stub == 0
    assert not _has_reset_line(out_stub)  # canary

    # Sanity: the per-CFC baseline actually wrote (else the diff is vacuous).
    assert "CFC-1: `" in (live_bp / "PLAN.md").read_text(encoding="utf-8")
    assert (live_bp / "PLAN.md").read_bytes() == (stub_bp / "PLAN.md").read_bytes()
    assert _tree_snapshot(live_tree) == _tree_snapshot(stub_tree)
