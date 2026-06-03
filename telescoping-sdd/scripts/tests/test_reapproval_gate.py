"""Tests for the Re-Approval Gate Hardening feature (R1 reminder + R2 marker).

This file is BORN here in T1 and APPENDED to by T2/T3 (and the validator-level
tests in T6/T7) per the Test-file ownership model in
`specs/reapproval-gate/tasks.md`. Each task's tests are grouped under a
`# --- T<n> ---` banner. All marker tests pass `project_root=tmp_path`
explicitly (sandbox discipline) so the real-repo `.sdd/` is never touched.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _p in (_SCRIPTS, _TESTS):
    if str(_p) not in sys.path:
        sys.path.append(str(_p))

import blueprint_common as bc


def _load_archive_pass():
    """Import archive_pass (a CLI script, but importable — no top-level side effects)."""
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    if "archive_pass" in sys.modules:
        return importlib.reload(sys.modules["archive_pass"])
    return importlib.import_module("archive_pass")


_VS_DIR = _SCRIPTS.parent / "skills" / "spec-driven-dev" / "scripts"
_VS = _VS_DIR / "validate_spec.py"


def _load_validate_spec():
    """Import validate_spec for direct (in-process) testing of approve/validate."""
    if str(_VS_DIR) not in sys.path:
        sys.path.insert(0, str(_VS_DIR))
    if "validate_spec" in sys.modules:
        return importlib.reload(sys.modules["validate_spec"])
    return importlib.import_module("validate_spec")


def _run_vs(*args):
    """Run validate_spec.py as a subprocess; return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(_VS), *args], capture_output=True, text=True
    )


def _seed_approved(root, key):
    """Create a doc and approve it once (first approval -> no reminder/marker)."""
    vs = _load_validate_spec()
    p = Path(root) / key
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_doc(hash_val="pending", checked=False), encoding="utf-8")
    vs.approve_document(p, project_root=Path(root))
    return p


def _minimal_spec_dir(root, name="specs/F1-x"):
    d = Path(root) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text("# Feature\n\n## Objective\n\nx\n", encoding="utf-8")
    return d


_VB_DIR = _SCRIPTS.parent / "skills" / "project-blueprint" / "scripts"
_VB = _VB_DIR / "validate_blueprint.py"


def _load_validate_blueprint():
    if str(_VB_DIR) not in sys.path:
        sys.path.insert(0, str(_VB_DIR))
    if "validate_blueprint" in sys.modules:
        return importlib.reload(sys.modules["validate_blueprint"])
    return importlib.import_module("validate_blueprint")


def _run_vb(*args):
    return subprocess.run(
        [sys.executable, str(_VB), *args], capture_output=True, text=True
    )


# --------------------------------------------------------------------------
# Shared fixture builders
# --------------------------------------------------------------------------

_TRAJ_HEADER = (
    "### Trajectory\n\n"
    "| Pass | Date       | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
    "|------|------------|-------|-------------|-----------|----------|--------|-------|\n"
)


def _doc(hash_val="abc1234567890def", checked=True):
    """A minimal approved-style doc with a checkbox + Content Hash line."""
    box = "[x]" if checked else "[ ]"
    return (
        "# Doc\n\n## Approval\n\n"
        f"- {box} Approved to proceed to next phase\n"
        f"- **Content Hash:** `{hash_val}`\n"
    )


def _traj_raw(rows):
    """A doc whose only table is a full 8-column Trajectory with the given rows."""
    return (
        "# Doc\n\n## Panel Review\n\n"
        + _TRAJ_HEADER
        + "".join(r + "\n" for r in rows)
        + "\n## Approval\n\n- [ ] Approved to proceed\n- **Content Hash:** `pending`\n"
    )


def _row(pass_num, notes="—"):
    return (
        f"| {pass_num}    | 2026-06-03 | 0     | 0           | 0         "
        f"| 0        | 0      | {notes} |"
    )


def _traj(pass_nums):
    return _traj_raw([_row(n) for n in pass_nums])


def _doc_with_tag(tag_pass, hash_short):
    """Trajectory doc with an `upstream-panel <hash_short>` tag on row `tag_pass`."""
    return _traj_raw([_row(tag_pass, notes=f"upstream-panel {hash_short}")])


def _write_corrupt(root):
    sdd = Path(root) / ".sdd"
    sdd.mkdir(parents=True, exist_ok=True)
    p = sdd / "pending-review.json"
    p.write_text("{not valid json", encoding="utf-8")
    return p


def _put_doc(root, key, content):
    p = Path(root) / key
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _marker_file(root):
    return Path(root) / ".sdd" / "pending-review.json"


# ==========================================================================
# --- T1 ---  REAPPROVAL_REMINDER, read_stored_hash, changed_since_stamp,
#             read/write/upsert/clear pending-review helpers.
# ==========================================================================


def test_reapproval_reminder_constant_phrases():
    for s in (
        "RE-APPROVAL REMINDER",
        "Step 3 (upstream panel re-review) is REQUIRED before cascade "
        "unless the diff is visibly trivial.",
        "lean=yes unless the diff is visibly trivial",
        "Classify the edit source per hash-and-cascade.md AD1 "
        "(claude-edit + non-trivial -> lean-yes).",
    ):
        assert s in bc.REAPPROVAL_REMINDER


def test_read_stored_hash_hex_value():
    assert bc.read_stored_hash(_doc(hash_val="abc1234567890def")) == "abc1234567890def"


def test_read_stored_hash_pending():
    assert bc.read_stored_hash("no content hash line here") == "pending"
    assert bc.read_stored_hash(_doc(hash_val="pending")) == "pending"


def test_read_stored_hash_malformed_verbatim():
    # A present-but-garbage value is returned VERBATIM (not collapsed to pending),
    # so changed_since_stamp can fail closed on it.
    assert bc.read_stored_hash(_doc(hash_val="zzz-not-hex")) == "zzz-not-hex"


def test_changed_since_stamp_fires_when_hash_differs():
    doc = _doc(hash_val="a" * 16, checked=True)
    assert bc.changed_since_stamp("b" * 16, "a" * 16, doc) is True


def test_changed_since_stamp_false_on_first_approval():
    doc = _doc(hash_val="pending", checked=False)
    assert bc.changed_since_stamp("b" * 16, "pending", doc) is False


def test_changed_since_stamp_false_unchecked_checkbox():
    doc = _doc(hash_val="a" * 16, checked=False)
    assert bc.changed_since_stamp("b" * 16, "a" * 16, doc) is False


def test_changed_since_stamp_malformed_hash_fires():
    # Present but not a valid 16-hex value (too short) -> fail closed -> True.
    doc = _doc(hash_val="abc123", checked=True)
    assert bc.changed_since_stamp("b" * 16, "abc123", doc) is True


def test_changed_since_stamp_case_insensitive_hex_comparison():
    # An uppercase-but-equal stored hash must compare equal (not spuriously fire).
    doc = _doc(hash_val="ABCDEF0123456789", checked=True)
    assert bc.changed_since_stamp("abcdef0123456789", "ABCDEF0123456789", doc) is False


def test_read_pending_review_absent_returns_empty(tmp_path):
    expected = {"schemaVersion": 1, "pending": {}}
    assert bc.read_pending_review(tmp_path) == expected
    assert bc.read_pending_review(tmp_path, strict=True) == expected


def test_read_pending_review_corrupt_strict_raises(tmp_path):
    _write_corrupt(tmp_path)
    with pytest.raises(bc.MarkerCorruptError):
        bc.read_pending_review(tmp_path, strict=True)


def test_read_pending_review_corrupt_permissive_empty(tmp_path):
    _write_corrupt(tmp_path)
    assert bc.read_pending_review(tmp_path, strict=False) == {
        "schemaVersion": 1,
        "pending": {},
    }


def test_write_pending_review_atomic(tmp_path):
    bc.write_pending_review(
        tmp_path, {"schemaVersion": 1, "pending": {"specs/f/spec.md": {"hash": "h"}}}
    )
    p = _marker_file(tmp_path)
    assert p.exists()
    assert json.loads(p.read_text())["pending"]["specs/f/spec.md"]["hash"] == "h"
    # no leftover temp artifacts
    assert not list((tmp_path / ".sdd").glob("*.tmp"))


def test_upsert_preserves_other_entries(tmp_path):
    bc.upsert_pending_entry(tmp_path, "specs/f/design.md", "d" * 16, "t", 1)
    bc.upsert_pending_entry(tmp_path, "specs/f/spec.md", "s" * 16, "t", 2)
    pending = bc.read_pending_review(tmp_path)["pending"]
    assert set(pending) == {"specs/f/design.md", "specs/f/spec.md"}
    assert pending["specs/f/design.md"]["hash"] == "d" * 16


def test_upsert_refuses_to_clobber_corrupt_marker(tmp_path):
    p = _write_corrupt(tmp_path)
    before = p.read_bytes()
    with pytest.raises(bc.MarkerCorruptError):
        bc.upsert_pending_entry(tmp_path, "specs/f/spec.md", "h" * 16, "t", 1)
    assert p.read_bytes() == before  # byte-identity: siblings not destroyed


def test_clear_pending_entries_removes_matching_prefix(tmp_path):
    bc.upsert_pending_entry(tmp_path, "specs/feat-a/spec.md", "a" * 16, "t", 1)
    bc.upsert_pending_entry(tmp_path, "specs/feat-b/spec.md", "b" * 16, "t", 1)
    removed = bc.clear_pending_entries_for_prefix(tmp_path, "specs/feat-a")
    assert removed == ["specs/feat-a/spec.md"]
    assert set(bc.read_pending_review(tmp_path)["pending"]) == {"specs/feat-b/spec.md"}


def test_decline_pending_prefix_no_bleed(tmp_path):
    # `specs/feat-a` must NOT clear `specs/feat-a-extra` (startswith(prefix + "/")).
    bc.upsert_pending_entry(tmp_path, "specs/feat-a/spec.md", "a" * 16, "t", 1)
    bc.upsert_pending_entry(tmp_path, "specs/feat-a-extra/spec.md", "x" * 16, "t", 1)
    removed = bc.clear_pending_entries_for_prefix(tmp_path, "specs/feat-a")
    assert removed == ["specs/feat-a/spec.md"]
    assert "specs/feat-a-extra/spec.md" in bc.read_pending_review(tmp_path)["pending"]


# ==========================================================================
# --- T2 ---  stamped_at_pass_from_content (AD5).
# ==========================================================================


def test_stamped_at_pass_no_trajectory():
    assert bc.stamped_at_pass_from_content("no trajectory at all") == 0


def test_stamped_at_pass_multi_row():
    assert bc.stamped_at_pass_from_content(_traj([1, 2, 5])) == 5


def test_stamped_at_pass_trimmed_trajectory():
    # 19 rows -> trim elides 1..4, keeps 5..19; highest surviving Pass is 19.
    content = _traj(list(range(1, 20)))
    assert bc.stamped_at_pass_from_content(content) == 19


def test_stamped_at_pass_skips_non_digit_cell():
    # middle row's Pass cell is empty -> skipped, not crashed
    rows = [_row(1), "|     | 2026-06-03 | 0 | 0 | 0 | 0 | 0 | stray |", _row(3)]
    content = _traj_raw(rows)
    assert bc.stamped_at_pass_from_content(content) == 3


def test_stamped_at_pass_skips_unicode_digit_cell():
    # '²'.isdigit() is True but int('²') raises — must be skipped, not crash.
    rows = [_row(1), "| ² | 2026-06-03 | 0 | 0 | 0 | 0 | 0 | unicode |", _row(3)]
    content = _traj_raw(rows)
    assert bc.stamped_at_pass_from_content(content) == 3


def test_stamped_at_pass_parity_with_archive_pass():
    ap = _load_archive_pass()
    for content in (_traj([1, 2, 5]), _traj(list(range(1, 20))), _traj([])):
        trimmed = bc.trim_trajectory_table(content)
        lines = trimmed.split("\n")
        rows, _table = ap.parse_table(lines, 0, len(lines))
        expected = max(
            (int(r["Pass"]) for r in rows if r["Pass"].strip().isdigit()), default=0
        )
        assert bc.stamped_at_pass_from_content(content) == expected


# ==========================================================================
# --- T3 ---  reconcile_pending_review (pass-monotonicity + AD12 containment).
# ==========================================================================


def test_clear_on_qualifying_upstream_panel_tag(tmp_path):
    key = "specs/f/spec.md"
    _put_doc(tmp_path, key, _doc_with_tag(2, "aaaaaaaa"))  # tag on Pass 2
    bc.upsert_pending_entry(tmp_path, key, "aaaaaaaa11111111", "t", 1)  # anchor 1
    still = bc.reconcile_pending_review(tmp_path, "specs/f")
    assert still == []  # 2 > 1 and hash matches -> cleared
    assert key not in bc.read_pending_review(tmp_path)["pending"]


def test_stale_earlier_pass_tag_does_not_clear(tmp_path):
    key = "specs/f/spec.md"
    _put_doc(tmp_path, key, _doc_with_tag(1, "aaaaaaaa"))  # tag on Pass 1
    bc.upsert_pending_entry(tmp_path, key, "aaaaaaaa11111111", "t", 1)  # anchor 1
    still = bc.reconcile_pending_review(tmp_path, "specs/f")
    assert still == [(key, "upstream-panel aaaaaaaa")]  # 1 not > 1 -> kept


def test_first_approval_zero_anchor_clears_on_pass_1(tmp_path):
    key = "specs/f/spec.md"
    _put_doc(tmp_path, key, _doc_with_tag(1, "bbbbbbbb"))  # tag on Pass 1
    bc.upsert_pending_entry(tmp_path, key, "bbbbbbbb22222222", "t", 0)  # anchor 0
    still = bc.reconcile_pending_review(tmp_path, "specs/f")
    assert still == []  # 1 > 0 -> cleared


def test_reconcile_skips_traversal_key(tmp_path):
    # A '..' key and an absolute key are both skipped (not read) and kept pending.
    bc.upsert_pending_entry(tmp_path, "../../../etc/passwd", "c" * 16, "t", 0)
    still = bc.reconcile_pending_review(tmp_path, "../../../etc/passwd")
    assert ("../../../etc/passwd", "upstream-panel cccccccc") in still

    bc.upsert_pending_entry(tmp_path, "/etc/passwd", "d" * 16, "t", 0)
    still2 = bc.reconcile_pending_review(tmp_path, "/etc/passwd")
    assert ("/etc/passwd", "upstream-panel dddddddd") in still2


def test_reconcile_skips_escape_without_dotdot(tmp_path):
    # A key with no literal '..' whose resolve() escapes root via an in-root symlink.
    outside = tmp_path.parent / "rg_outside_target"
    outside.mkdir(exist_ok=True)
    (tmp_path / "evil").symlink_to(outside, target_is_directory=True)
    key = "evil/x.md"
    bc.upsert_pending_entry(tmp_path, key, "e" * 16, "t", 0)
    still = bc.reconcile_pending_review(tmp_path, "evil")
    assert (key, "upstream-panel eeeeeeee") in still


def test_reconcile_keeps_entry_when_target_doc_missing(tmp_path):
    key = "specs/f/spec.md"  # no file written -> read fails -> kept pending
    bc.upsert_pending_entry(tmp_path, key, "f" * 16, "t", 0)
    still = bc.reconcile_pending_review(tmp_path, "specs/f")
    assert still == [(key, "upstream-panel ffffffff")]


def test_clear_writes_through_to_disk(tmp_path):
    key = "specs/f/spec.md"
    _put_doc(tmp_path, key, _doc_with_tag(2, "aaaaaaaa"))
    bc.upsert_pending_entry(tmp_path, key, "aaaaaaaa11111111", "t", 1)
    assert key in json.loads(_marker_file(tmp_path).read_text())["pending"]
    bc.reconcile_pending_review(tmp_path, "specs/f")
    # the only entry cleared -> pending empty -> file deleted (on-disk reflects clear)
    assert not _marker_file(tmp_path).exists()


# ==========================================================================
# --- T6 ---  validate_spec.py: approve (R1 reminder + R2 marker), validate
#             FAIL check, and the --task-tick / --decline-pending CLI flags.
#             (sandbox: direct calls pass project_root=tmp_path; subprocess
#             tests pass --project-root <tmp_path>.)
# ==========================================================================


def test_reminder_fires_on_changed_doc(tmp_path, capsys):
    vs = _load_validate_spec()
    p = _seed_approved(tmp_path, "specs/F1-x/spec.md")
    capsys.readouterr()  # drop the first-approval output
    p.write_text(p.read_text() + "\nchanged body\n", encoding="utf-8")
    vs.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    assert "RE-APPROVAL REMINDER" in out
    assert "lean=yes unless the diff is visibly trivial" in out
    assert "Classify the edit source per hash-and-cascade.md AD1" in out
    assert "specs/F1-x/spec.md" in bc.read_pending_review(tmp_path)["pending"]


def test_reminder_absent_on_unchanged_doc(tmp_path, capsys):
    vs = _load_validate_spec()
    p = _seed_approved(tmp_path, "specs/F1-x/spec.md")
    capsys.readouterr()
    vs.approve_document(p, project_root=tmp_path)  # re-approve, content unchanged
    out = capsys.readouterr().out
    assert "RE-APPROVAL REMINDER" not in out
    assert bc.read_pending_review(tmp_path)["pending"] == {}


def test_reminder_printed_after_approved_line(tmp_path, capsys):
    vs = _load_validate_spec()
    p = _seed_approved(tmp_path, "specs/F1-x/spec.md")
    capsys.readouterr()
    p.write_text(p.read_text() + "\nchanged\n", encoding="utf-8")
    vs.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    assert out.index("Approved:") < out.index("RE-APPROVAL REMINDER")


def test_marker_schema_on_write(tmp_path):
    vs = _load_validate_spec()
    p = _seed_approved(tmp_path, "specs/F1-x/spec.md")
    p.write_text(p.read_text() + "\nchanged\n", encoding="utf-8")
    vs.approve_document(p, project_root=tmp_path)
    data = json.loads(_marker_file(tmp_path).read_text())
    assert data["schemaVersion"] == 1
    entry = data["pending"]["specs/F1-x/spec.md"]
    assert set(entry) >= {"hash", "stamped_at", "stamped_at_pass"}
    assert bc._is_valid_16_hex(entry["hash"])
    assert isinstance(entry["stamped_at_pass"], int)
    datetime.fromisoformat(entry["stamped_at"])  # parseable; clock not pinned


def test_task_tick_suppresses_reminder_and_marker(tmp_path, capsys):
    vs = _load_validate_spec()
    p = _seed_approved(tmp_path, "specs/F1-x/tasks.md")
    capsys.readouterr()
    p.write_text(p.read_text() + "\nchanged tick\n", encoding="utf-8")
    vs.approve_document(p, task_tick=True, project_root=tmp_path)
    out = capsys.readouterr().out
    assert "RE-APPROVAL REMINDER" not in out
    assert bc.read_pending_review(tmp_path)["pending"] == {}


def test_task_tick_prints_audit_line(tmp_path, capsys):
    vs = _load_validate_spec()
    p = _seed_approved(tmp_path, "specs/F1-x/tasks.md")
    capsys.readouterr()
    p.write_text(p.read_text() + "\nchanged tick\n", encoding="utf-8")
    vs.approve_document(p, task_tick=True, project_root=tmp_path)
    out = capsys.readouterr().out
    assert "task-tick: pending-review suppressed for" in out
    assert "(Phase-4 carve-out)" in out


def test_task_tick_absent_fails_closed(tmp_path, capsys):
    vs = _load_validate_spec()
    p = _seed_approved(tmp_path, "specs/F1-x/tasks.md")
    capsys.readouterr()
    p.write_text(p.read_text() + "\nchanged tick\n", encoding="utf-8")
    vs.approve_document(p, task_tick=False, project_root=tmp_path)  # NO flag
    out = capsys.readouterr().out
    assert "RE-APPROVAL REMINDER" in out
    assert "specs/F1-x/tasks.md" in bc.read_pending_review(tmp_path)["pending"]


def test_validate_fails_on_uncleared_entry(tmp_path):
    # The gate is reconciled at DISPATCH level (main), so test via subprocess.
    d = _minimal_spec_dir(tmp_path)
    bc.upsert_pending_entry(tmp_path, "specs/F1-x/spec.md", "a" * 16, "t", 0)
    r = _run_vs(str(d), "--project-root", str(tmp_path))
    assert r.returncode == 1
    assert "pending-review" in r.stdout
    assert "--decline-pending" in r.stdout
    assert "upstream-panel" in r.stdout


def test_validate_fails_closed_on_corrupt_marker(tmp_path):
    d = _minimal_spec_dir(tmp_path)
    _write_corrupt(tmp_path)
    r = _run_vs(str(d), "--project-root", str(tmp_path))
    assert r.returncode == 1
    out = r.stdout.lower()
    assert "pending-review" in out
    assert "corrupt" in out or "unreadable" in out


def test_validate_fail_appears_in_json_output(tmp_path):
    d = _minimal_spec_dir(tmp_path)
    bc.upsert_pending_entry(tmp_path, "specs/F1-x/spec.md", "a" * 16, "t", 0)
    r = _run_vs(str(d), "--output", "json", "--project-root", str(tmp_path))
    assert r.returncode == 1
    data = json.loads(r.stdout)
    # uniform top-level `pending_review` key (matches validate_blueprint)
    fails = [
        c
        for c in data.get("pending_review", [])
        if c["name"] == "pending-review" and c["status"] == "FAIL"
    ]
    assert fails


def test_validate_gate_fires_under_phase_design(tmp_path):
    # Regression for the phase-scoping bypass: a pending obligation must surface
    # even under --phase design / --phase tasks (gate is now at dispatch level).
    d = _minimal_spec_dir(tmp_path)
    bc.upsert_pending_entry(tmp_path, "specs/F1-x/spec.md", "a" * 16, "t", 0)
    for phase in ("design", "tasks"):
        r = _run_vs(str(d), "--phase", phase, "--project-root", str(tmp_path))
        assert "pending-review" in r.stdout, f"gate bypassed under --phase {phase}"
        assert r.returncode == 1


def test_gate_fires_when_dir_is_project_root(tmp_path):
    # Regression for the prefix=="." bypass: spec_dir == project root -> relpath
    # ".", which must still match the bare-key marker entry.
    (tmp_path / ".git").mkdir()  # make tmp_path a recognizable project root
    (tmp_path / "spec.md").write_text("# F\n\n## Objective\n\nx\n", encoding="utf-8")
    bc.upsert_pending_entry(tmp_path, "spec.md", "a" * 16, "t", 0)
    r = _run_vs(str(tmp_path), "--project-root", str(tmp_path))
    assert "pending-review" in r.stdout
    assert r.returncode == 1


def test_task_tick_on_non_tasks_is_error(tmp_path):
    d = _minimal_spec_dir(tmp_path)
    r = _run_vs(
        str(d), "--approve", "spec", "--task-tick", "--project-root", str(tmp_path)
    )
    assert r.returncode == 2
    assert "--task-tick is only valid with --approve tasks" in (r.stdout + r.stderr)


def test_decline_pending_clears_dir_entries(tmp_path):
    d = _minimal_spec_dir(tmp_path)
    bc.upsert_pending_entry(tmp_path, "specs/F1-x/spec.md", "a" * 16, "t", 0)
    r = _run_vs(str(d), "--decline-pending", "--project-root", str(tmp_path))
    assert r.returncode == 0
    assert "Declined" in r.stdout
    assert bc.read_pending_review(tmp_path)["pending"] == {}


def test_decline_pending_no_op_message(tmp_path):
    d = _minimal_spec_dir(tmp_path)
    r = _run_vs(str(d), "--decline-pending", "--project-root", str(tmp_path))
    assert r.returncode == 0
    assert "No pending-review entries found" in r.stdout


# ==========================================================================
# --- T7 ---  validate_blueprint.py: mirrored reminder/marker + the
#             dispatch-level pending-review FAIL (incl. absent-phase doc).
# ==========================================================================


def test_blueprint_reminder_fires_on_changed_doc(tmp_path, capsys):
    vb = _load_validate_blueprint()
    p = tmp_path / "blueprint" / "SCOPE.md"
    p.parent.mkdir(parents=True)
    p.write_text(_doc(hash_val="pending", checked=False), encoding="utf-8")
    vb.approve_document(p, project_root=tmp_path)  # first approval
    capsys.readouterr()
    p.write_text(p.read_text() + "\nchanged scope\n", encoding="utf-8")
    vb.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    assert "RE-APPROVAL REMINDER" in out  # same constant as the SDD validator
    assert "blueprint/SCOPE.md" in bc.read_pending_review(tmp_path)["pending"]


def test_blueprint_dispatch_fail_for_absent_phase_doc(tmp_path):
    bp = tmp_path / "blueprint"
    bp.mkdir(parents=True)
    # A pending obligation for a PLAN.md that is ABSENT in this "all"-mode run.
    bc.upsert_pending_entry(tmp_path, "blueprint/PLAN.md", "a" * 16, "t", 0)
    r = _run_vb(str(bp), "--output", "json", "--project-root", str(tmp_path))
    assert r.returncode == 1
    data = json.loads(r.stdout)
    fails = [
        c
        for c in data.get("pending_review", [])
        if c["name"] == "pending-review" and c["status"] == "FAIL"
    ]
    assert len(fails) == 1  # exactly one — the absent-phase entry did not vanish
    assert "blueprint/PLAN.md" in fails[0]["detail"]


# ==========================================================================
# --- T11 ---  Cross-cutting INTEGRATION tests (no single impl task owns these)
#              + the by-NAME audit that the full union of declared tests exists.
# ==========================================================================


def test_no_collision_two_dirs(tmp_path):
    vs = _load_validate_spec()
    pa = _seed_approved(tmp_path, "specs/feat-a/spec.md")
    pb = _seed_approved(tmp_path, "specs/feat-b/spec.md")
    for p in (pa, pb):
        p.write_text(p.read_text() + "\nchanged\n", encoding="utf-8")
        vs.approve_document(p, project_root=tmp_path)
    pending = bc.read_pending_review(tmp_path)["pending"]
    assert "specs/feat-a/spec.md" in pending
    assert "specs/feat-b/spec.md" in pending  # distinct path-keyed entries, no collision


def test_fresh_clone_no_marker_no_fail(tmp_path):
    d = _minimal_spec_dir(tmp_path)
    r = _run_vs(str(d), "--project-root", str(tmp_path))  # no marker present
    assert "pending-review" not in r.stdout.lower()  # gate stays silent


def test_unchanged_doc_no_marker_entry(tmp_path):
    vs = _load_validate_spec()
    p = _seed_approved(tmp_path, "specs/F1-x/spec.md")
    vs.approve_document(p, project_root=tmp_path)  # re-approve, content unchanged
    assert bc.read_pending_review(tmp_path)["pending"] == {}


# --- Code-review remediations (regression tests for the /code-review findings) ---


def test_changed_since_stamp_empty_hash_fires():
    # Empty backticks on an approved doc -> fail-closed (fire), not first-approval.
    doc = _doc(hash_val="", checked=True)
    assert bc.changed_since_stamp("b" * 16, "", doc) is True


def test_read_pending_review_unknown_schema_version_strict_raises(tmp_path):
    sdd = tmp_path / ".sdd"
    sdd.mkdir(parents=True)
    (sdd / "pending-review.json").write_text(
        '{"schemaVersion": 2, "pending": {}}', encoding="utf-8"
    )
    with pytest.raises(bc.MarkerCorruptError):
        bc.read_pending_review(tmp_path, strict=True)
    assert bc.read_pending_review(tmp_path, strict=False) == {
        "schemaVersion": 1,
        "pending": {},
    }


def test_approve_misconfigured_project_root_warns_and_recovers(tmp_path, capsys):
    # A --project-root that is NOT an ancestor of the doc must not write a '..'
    # key (which reconcile would permanently reject); fall back to walking up
    # from the doc, write a clean key, and WARN.
    vs = _load_validate_spec()
    doc_root = tmp_path / "real_root"
    (doc_root / ".git").mkdir(parents=True)  # recognizable project root
    p = _seed_approved(doc_root, "specs/F1-x/spec.md")
    capsys.readouterr()
    p.write_text(p.read_text() + "\nchanged\n", encoding="utf-8")
    wrong_root = tmp_path / "wrong_root"
    wrong_root.mkdir()
    vs.approve_document(p, project_root=wrong_root)  # not an ancestor of p
    assert "not an ancestor" in capsys.readouterr().err
    pending = bc.read_pending_review(doc_root)["pending"]
    assert "specs/F1-x/spec.md" in pending  # clean key under the fallback root
    assert not any(k.startswith("..") for k in pending)
    assert not bc.read_pending_review(wrong_root)["pending"]  # nothing under wrong root


# The audit: the union of the `def test_` names declared across T1/T2/T3/T6/T7 +
# T11's 3 integration tests (the ownership model's single source of truth). The
# meta-test below FAILS by NAME on any missing one — never trusts a headline
# count (passes 2-5 of the tasks panel established this discipline).
_UNION_TEST_NAMES = (
    # T1
    "test_reapproval_reminder_constant_phrases",
    "test_read_stored_hash_hex_value",
    "test_read_stored_hash_pending",
    "test_read_stored_hash_malformed_verbatim",
    "test_changed_since_stamp_fires_when_hash_differs",
    "test_changed_since_stamp_false_on_first_approval",
    "test_changed_since_stamp_false_unchecked_checkbox",
    "test_changed_since_stamp_malformed_hash_fires",
    "test_changed_since_stamp_case_insensitive_hex_comparison",
    "test_read_pending_review_absent_returns_empty",
    "test_read_pending_review_corrupt_strict_raises",
    "test_read_pending_review_corrupt_permissive_empty",
    "test_write_pending_review_atomic",
    "test_upsert_preserves_other_entries",
    "test_upsert_refuses_to_clobber_corrupt_marker",
    "test_clear_pending_entries_removes_matching_prefix",
    "test_decline_pending_prefix_no_bleed",
    # T2
    "test_stamped_at_pass_no_trajectory",
    "test_stamped_at_pass_multi_row",
    "test_stamped_at_pass_trimmed_trajectory",
    "test_stamped_at_pass_skips_non_digit_cell",
    "test_stamped_at_pass_parity_with_archive_pass",
    # T3
    "test_clear_on_qualifying_upstream_panel_tag",
    "test_stale_earlier_pass_tag_does_not_clear",
    "test_first_approval_zero_anchor_clears_on_pass_1",
    "test_reconcile_skips_traversal_key",
    "test_reconcile_skips_escape_without_dotdot",
    "test_reconcile_keeps_entry_when_target_doc_missing",
    "test_clear_writes_through_to_disk",
    # T6
    "test_reminder_fires_on_changed_doc",
    "test_reminder_absent_on_unchanged_doc",
    "test_reminder_printed_after_approved_line",
    "test_marker_schema_on_write",
    "test_task_tick_suppresses_reminder_and_marker",
    "test_task_tick_prints_audit_line",
    "test_task_tick_absent_fails_closed",
    "test_validate_fails_on_uncleared_entry",
    "test_validate_fails_closed_on_corrupt_marker",
    "test_validate_fail_appears_in_json_output",
    "test_task_tick_on_non_tasks_is_error",
    "test_decline_pending_clears_dir_entries",
    "test_decline_pending_no_op_message",
    # T7
    "test_blueprint_reminder_fires_on_changed_doc",
    "test_blueprint_dispatch_fail_for_absent_phase_doc",
    # T11 integration
    "test_no_collision_two_dirs",
    "test_fresh_clone_no_marker_no_fail",
    "test_unchanged_doc_no_marker_entry",
    # Code-review remediations
    "test_validate_gate_fires_under_phase_design",
    "test_gate_fires_when_dir_is_project_root",
    "test_stamped_at_pass_skips_unicode_digit_cell",
    "test_changed_since_stamp_empty_hash_fires",
    "test_read_pending_review_unknown_schema_version_strict_raises",
    "test_approve_misconfigured_project_root_warns_and_recovers",
)

_AUDIT_TEST_NAME = "test_audit_union_test_names_present"


def test_audit_union_test_names_present():
    """By-NAME audit (T11): the union of declared test names and the file's
    actual `def test_` set must MATCH exactly. FAIL on any name missing (a test
    dropped/renamed) AND on any extra (a test added but not registered in the
    union) — so the ownership-model source of truth cannot silently drift."""
    import re as _re

    body = Path(__file__).read_text(encoding="utf-8")
    defined = set(_re.findall(r"^def (test_\w+)\(", body, _re.MULTILINE))
    union = set(_UNION_TEST_NAMES) | {_AUDIT_TEST_NAME}
    missing = sorted(union - defined)
    extra = sorted(defined - union)  # converse: defined but not registered
    assert not missing, f"audit: registered names with no test function: {missing}"
    assert not extra, f"audit: test functions not registered in _UNION_TEST_NAMES: {extra}"
