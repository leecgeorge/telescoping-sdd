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


# ==========================================================================
# --- Pending-review churn feature: R1–R8 + R9 + R10 integration tests ---
#     (sandbox: in-process approve_document / reconcile pass project_root=tmp;
#      subprocess tests pass --project-root <tmp>.)
# ==========================================================================

_CHURN_TRAJ_HEADER = (
    "### Trajectory\n\n"
    "| Pass | Date       | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
    "|------|------------|-------|-------------|-----------|----------|--------|-------|\n"
)


def _crow(p, notes="—"):
    return (
        f"| {p}    | 2026-06-12 | 0     | 0           | 0         "
        f"| 0        | 0      | {notes} |"
    )


def _churn_doc(passes=(1,), sealed="", deferred="", latest="", body="Do a thing.",
               checked=False, hash_val="pending", basis=None):
    s = f"# Doc\n\n## Objective\n\n{body}\n\n## Panel Review\n\n" + _CHURN_TRAJ_HEADER
    s += "".join(_crow(p) + "\n" for p in passes)
    if deferred:
        s += "\n### Deferred dispositions\n\n" + deferred + "\n"
    if sealed:
        s += "\n### Sealed dispositions\n\n" + sealed + "\n"
    if latest:
        s += "\n### Latest pass detail\n\n" + latest + "\n"
    s += "\n## Approval\n\n"
    box = "[x]" if checked else "[ ]"
    s += f"- {box} Approved to proceed to next phase\n- **Content Hash:** `{hash_val}`\n"
    if basis is not None:
        s += f"- **Hash basis:** {basis}\n"
    return s


def _seed_churn_approved(root, key, passes=(1,), **kw):
    """Create a Trajectory-bearing doc and approve once (-> v2 basis, no marker)."""
    vs = _load_validate_spec()
    p = Path(root) / key
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_churn_doc(passes=passes, checked=False, hash_val="pending", **kw),
                 encoding="utf-8")
    vs.approve_document(p, project_root=Path(root))
    return p


def _v1_doc_text(passes=(1,), **kw):
    """A v1-basis approved doc (NO basis line) + its v1 stored hash."""
    base = _churn_doc(passes=passes, checked=True, hash_val="pending", basis=None, **kw)
    v1 = bc.compute_content_hash_v1(bc.trim_trajectory_table(base))
    return base.replace("**Content Hash:** `pending`", f"**Content Hash:** `{v1}`"), v1


def _seed_v1(root, key, passes=(1,), **kw):
    text, v1 = _v1_doc_text(passes=passes, **kw)
    p = Path(root) / key
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p, v1


def _add_traj_row(p, pass_n, notes="—"):
    """Append a contiguous Trajectory data row for `pass_n`."""
    lines = p.read_text().split("\n")
    sep_i = next(i for i, l in enumerate(lines) if bc.TRAJECTORY_SEP_RE.match(l))
    j = sep_i + 1
    while j < len(lines) and lines[j].strip().startswith("|") and lines[j].strip().endswith("|"):
        j += 1
    lines.insert(j, _crow(pass_n, notes))
    p.write_text("\n".join(lines), encoding="utf-8")


def _set_row_tag(p, pass_n, hash_short):
    """Set the Notes cell of the Trajectory row at `pass_n` to the upstream tag."""
    lines = p.read_text().split("\n")
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith("|") and s.endswith("|"):
            first = bc._row_first_cell(l)
            if bc._is_ascii_int(first) and int(first) == pass_n:
                lines[i] = _crow(pass_n, notes=f"upstream-panel {hash_short}")
                break
    p.write_text("\n".join(lines), encoding="utf-8")


def _substantive_edit(p, marker):
    """Insert visible body text (outside the Trajectory) — a real content edit."""
    txt = p.read_text()
    p.write_text(txt.replace("\n## Panel Review", f"\n{marker}\n\n## Panel Review", 1),
                 encoding="utf-8")


def _pending(root):
    return bc.read_pending_review(Path(root))["pending"]


def _check(mod, content, filename="spec.md"):
    r = bc.ValidationResult()
    mod.check_approval(content, filename, r)
    return r


def _detail_blob(result):
    return "\n".join(d for _n, _s, d in result.checks)


# --- R1/R3: convergence-only re-approval writes no marker -------------------


def test_convergence_only_no_marker_spec(tmp_path, capsys):
    vs = _load_validate_spec()
    p = _seed_churn_approved(tmp_path, "specs/F1-x/spec.md", passes=(1,))
    capsys.readouterr()
    _add_traj_row(p, 2, notes="converged (0 HIGH)")  # bookkeeping only
    vs.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    assert "RE-APPROVAL REMINDER" not in out
    assert _pending(tmp_path) == {}


def test_convergence_only_no_marker_blueprint(tmp_path, capsys):
    vb = _load_validate_blueprint()
    p = tmp_path / "blueprint" / "SCOPE.md"
    p.parent.mkdir(parents=True)
    p.write_text(_churn_doc(passes=(1,), checked=False, hash_val="pending"), encoding="utf-8")
    vb.approve_document(p, project_root=tmp_path)
    capsys.readouterr()
    _add_traj_row(p, 2, notes="converged (0 HIGH)")
    vb.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    assert "RE-APPROVAL REMINDER" not in out
    assert _pending(tmp_path) == {}


def test_convergence_only_unrelated_entry_undisturbed(tmp_path):
    vs = _load_validate_spec()
    p = _seed_churn_approved(tmp_path, "specs/F1-x/spec.md", passes=(1,))
    bc.upsert_pending_entry(tmp_path, "specs/other/spec.md", "a" * 16, "t", 1)
    _add_traj_row(p, 2)
    vs.approve_document(p, project_root=tmp_path)
    assert "specs/other/spec.md" in _pending(tmp_path)


# --- R2/R7: substantive edits still write a closeable marker ----------------


def test_substantive_edit_still_writes_marker_spec(tmp_path, capsys):
    vs = _load_validate_spec()
    p = _seed_churn_approved(tmp_path, "specs/F1-x/spec.md", passes=(1,))
    capsys.readouterr()
    _substantive_edit(p, "A real edit.")
    vs.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    assert "RE-APPROVAL REMINDER" in out
    entry = _pending(tmp_path)["specs/F1-x/spec.md"]
    assert bc._is_valid_16_hex(entry["hash"])


def test_substantive_edit_still_writes_marker_blueprint(tmp_path, capsys):
    vb = _load_validate_blueprint()
    p = tmp_path / "blueprint" / "SCOPE.md"
    p.parent.mkdir(parents=True)
    p.write_text(_churn_doc(passes=(1,), checked=False, hash_val="pending"), encoding="utf-8")
    vb.approve_document(p, project_root=tmp_path)
    capsys.readouterr()
    _substantive_edit(p, "A real edit.")
    vb.approve_document(p, project_root=tmp_path)
    assert "blueprint/SCOPE.md" in _pending(tmp_path)


def test_latest_pass_detail_edit_writes_marker(tmp_path):
    vs = _load_validate_spec()
    latest = "| [HIGH] | critic | concern | Addressed | original note |"
    p = _seed_churn_approved(tmp_path, "specs/F1-x/spec.md", passes=(1,), latest=latest)
    p.write_text(p.read_text().replace("original note", "TAMPERED decision"), encoding="utf-8")
    vs.approve_document(p, project_root=tmp_path)
    assert "specs/F1-x/spec.md" in _pending(tmp_path)


def test_defense_mutation_writes_marker(tmp_path):
    vs = _load_validate_spec()
    sealed = "- `[SEAL-01]` **Thing** (pass 1, sealed) — Defense: original rationale."
    p = _seed_churn_approved(tmp_path, "specs/F1-x/spec.md", passes=(1,), sealed=sealed)
    p.write_text(p.read_text().replace("original rationale", "weakened rationale"), encoding="utf-8")
    vs.approve_document(p, project_root=tmp_path)
    assert "specs/F1-x/spec.md" in _pending(tmp_path)


def test_deferred_dispositions_mutation_writes_marker(tmp_path):
    vs = _load_validate_spec()
    deferred = "- `[DEF-01]` **Thing** → tasks.md (pass 1) — Routed because: original."
    p = _seed_churn_approved(tmp_path, "specs/F1-x/spec.md", passes=(1,), deferred=deferred)
    p.write_text(p.read_text().replace("Routed because: original", "Routed because: CHANGED"),
                 encoding="utf-8")
    vs.approve_document(p, project_root=tmp_path)
    assert "specs/F1-x/spec.md" in _pending(tmp_path)


# --- R2: close path terminates ---------------------------------------------


def test_close_path_tag_stamp_terminates(tmp_path):
    vs = _load_validate_spec()
    key = "specs/F1-x/spec.md"
    p = _seed_churn_approved(tmp_path, key, passes=(1, 2, 3))
    _substantive_edit(p, "edit one")
    vs.approve_document(p, project_root=tmp_path)
    h = _pending(tmp_path)[key]["hash"]
    _add_traj_row(p, 4, notes=f"upstream-panel {h[:8]}")
    assert bc.reconcile_pending_review(tmp_path, "specs/F1-x") == []
    # second --approve does NOT re-open a marker, and no stale-hash FAIL
    vs.approve_document(p, project_root=tmp_path)
    assert _pending(tmp_path) == {}
    txt = p.read_text()
    assert bc.verify_content_hash(txt, bc.read_stored_hash(txt))


def test_close_path_fixture_hash_matches(tmp_path):
    vs = _load_validate_spec()
    key = "specs/F1-x/spec.md"
    p = _seed_churn_approved(tmp_path, key, passes=(1, 2, 3))
    _substantive_edit(p, "edit one")
    vs.approve_document(p, project_root=tmp_path)
    h = _pending(tmp_path)[key]["hash"]
    _add_traj_row(p, 4, notes=f"upstream-panel {h[:8]}")  # tag carries first 8 hex
    assert bc.reconcile_pending_review(tmp_path, "specs/F1-x") == []


# --- R4: migration FAIL + suppression --------------------------------------


def test_migration_fail_emitted_old_basis(tmp_path):
    content, _v1 = _v1_doc_text(passes=(1, 2))
    for mod in (_load_validate_spec(), _load_validate_blueprint()):
        blob = _detail_blob(_check(mod, content))
        assert "HASH-BASIS-MIGRATION:" in blob


def test_migration_fail_exit_code_nonzero(tmp_path):
    # Surfaced via the previous-phase check: a v1 spec.md checked while validating
    # design. Use a spec dir + subprocess so the exit code is real.
    d = tmp_path / "specs" / "F1-x"
    d.mkdir(parents=True)
    # Build the final content (incl. the identifier line) FIRST, then stamp the v1
    # hash over it — so it is a PURE basis migration (no concurrent edit), which is
    # the only case that now gets the HASH-BASIS-MIGRATION FAIL (a genuine edit
    # falls through to a normal stale FAIL after fix #2).
    base = _churn_doc(passes=(1, 2), checked=True, hash_val="pending")
    base = base.replace("# Doc\n", "# Doc\n\n**PLAN feature identifier:** `n/a`\n", 1)
    v1 = bc.compute_content_hash_v1(bc.trim_trajectory_table(base))
    text = base.replace("**Content Hash:** `pending`", f"**Content Hash:** `{v1}`")
    (d / "spec.md").write_text(text, encoding="utf-8")
    (d / "design.md").write_text("# Design\n\n## Goals and Non-Goals\n\nx\n", encoding="utf-8")
    r = _run_vs(str(d), "--phase", "design", "--project-root", str(tmp_path))
    assert r.returncode == 1
    assert "HASH-BASIS-MIGRATION:" in r.stdout


def test_migration_fail_distinguishable_from_pending_review(tmp_path):
    content, _v1 = _v1_doc_text(passes=(1, 2))
    blob = _detail_blob(_check(_load_validate_spec(), content))
    assert "HASH-BASIS-MIGRATION:" in blob
    assert "Pending-review: FAILED" not in blob


def test_migration_restamp_no_marker_spec(tmp_path, capsys):
    vs = _load_validate_spec()
    p, _v1 = _seed_v1(tmp_path, "specs/F1-x/spec.md", passes=(1, 2))
    capsys.readouterr()
    vs.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    assert _pending(tmp_path) == {}
    assert "RE-APPROVAL REMINDER" not in out
    assert "- **Hash basis:** v2" in p.read_text()


def test_migration_restamp_no_marker_blueprint(tmp_path):
    vb = _load_validate_blueprint()
    p = tmp_path / "blueprint" / "SCOPE.md"
    p.parent.mkdir(parents=True)
    text, _v1 = _v1_doc_text(passes=(1, 2))
    p.write_text(text, encoding="utf-8")
    vb.approve_document(p, project_root=tmp_path)
    assert _pending(tmp_path) == {}
    assert "- **Hash basis:** v2" in p.read_text()


def test_migration_concurrent_edit_writes_marker(tmp_path):
    vs = _load_validate_spec()
    p, _v1 = _seed_v1(tmp_path, "specs/F1-x/spec.md", passes=(1, 2))
    _substantive_edit(p, "a concurrent edit")  # changes the v1 hash too
    vs.approve_document(p, project_root=tmp_path)
    assert "specs/F1-x/spec.md" in _pending(tmp_path)
    assert "- **Hash basis:** v2" in p.read_text()


def test_migration_round_trip_idempotent(tmp_path, capsys):
    vs = _load_validate_spec()
    p, _v1 = _seed_v1(tmp_path, "specs/F1-x/spec.md", passes=(1, 2))
    vs.approve_document(p, project_root=tmp_path)  # migrate
    capsys.readouterr()
    vs.approve_document(p, project_root=tmp_path)  # second approve: clean
    out = capsys.readouterr().out
    assert _pending(tmp_path) == {}
    assert "hash-basis-migrated:" not in out  # already v2
    assert _detail_blob(_check(vs, p.read_text())).count("HASH-BASIS-MIGRATION:") == 0


def test_migration_grown_trajectory_writes_marker(tmp_path):
    vs = _load_validate_spec()
    p, _v1 = _seed_v1(tmp_path, "specs/F1-x/spec.md", passes=(1, 2, 3))
    _add_traj_row(p, 4)  # Trajectory grew since the v1 approval (never re-approved)
    vs.approve_document(p, project_root=tmp_path)
    assert "specs/F1-x/spec.md" in _pending(tmp_path)
    assert "- **Hash basis:** v2" in p.read_text()


def test_bare_archive_write_validation_clean(tmp_path):
    vs = _load_validate_spec()
    p = _seed_churn_approved(tmp_path, "specs/F1-x/spec.md", passes=(1,))
    stored = bc.read_stored_hash(p.read_text())
    _add_traj_row(p, 2, notes="converged (0 HIGH)")  # archive-style write, no --approve
    assert bc.verify_content_hash(p.read_text(), stored)  # still hash-coherent


def test_v1_v2_equal_no_migration_message(tmp_path, capsys):
    vs = _load_validate_spec()
    # Empty Trajectory: v1 hash == v2 hash (no rows to strip) -> no migration.
    p, _v1 = _seed_v1(tmp_path, "specs/F1-x/spec.md", passes=())
    assert "HASH-BASIS-MIGRATION:" not in _detail_blob(_check(vs, p.read_text()))
    vs.approve_document(p, project_root=tmp_path)
    assert _pending(tmp_path) == {}
    assert "- **Hash basis:** v2" in p.read_text()


def test_migration_severity_is_fail_not_warn(tmp_path):
    content, _v1 = _v1_doc_text(passes=(1, 2))
    r = _check(_load_validate_spec(), content)
    sev = [s for _n, s, d in r.checks if "HASH-BASIS-MIGRATION:" in d]
    assert sev == [bc.Severity.FAIL]


def test_migration_message_contains_basis_migration_token(tmp_path):
    content, _v1 = _v1_doc_text(passes=(1, 2))
    assert "HASH-BASIS-MIGRATION:" in _detail_blob(_check(_load_validate_spec(), content))


def test_migration_restamp_suppress_msg_token(tmp_path, capsys):
    vs = _load_validate_spec()
    p, _v1 = _seed_v1(tmp_path, "specs/F1-x/spec.md", passes=(1, 2))
    capsys.readouterr()
    vs.approve_document(p, project_root=tmp_path)
    assert "hash-basis-migrated:" in capsys.readouterr().out


def test_body_prose_basis_decoy_still_migration_fail(tmp_path):
    # A genuine-v1 artifact carrying a body-prose `**Hash basis:** v2` decoy still
    # reads as v1 (the decoy is outside ## Approval) -> migration FAIL, not stale.
    content, _v1base = _v1_doc_text(passes=(1, 2), body="see **Hash basis:** v2 in prose")
    # recompute the stored v1 hash for the doc INCLUDING the decoy body
    blob = _detail_blob(_check(_load_validate_spec(), content))
    assert "HASH-BASIS-MIGRATION:" in blob


def test_v2_basis_genuine_edit_stale_fail(tmp_path):
    # A v2-basis artifact later genuinely edited -> normal stale FAIL, not migration.
    vs = _load_validate_spec()
    p = _seed_churn_approved(tmp_path, "specs/F1-x/spec.md", passes=(1,))
    _substantive_edit(p, "later edit")  # not re-approved -> stored hash now stale
    blob = _detail_blob(_check(vs, p.read_text()))
    assert "HASH-BASIS-MIGRATION:" not in blob
    assert "has not been modified since approval" in "\n".join(n for n, _s, _d in _check(vs, p.read_text()).checks)


def test_genuine_v1_edit_is_stale_not_migration(tmp_path):
    # Code-review fix #2: a GENUINELY-edited v1 artifact (content changed after a
    # v1 approval, not re-approved) must NOT get the HASH-BASIS-MIGRATION message
    # (which promises no obligation) — only a PURE basis migration does. It falls
    # through to the normal stale FAIL.
    vs = _load_validate_spec()
    base, _v1 = _v1_doc_text(passes=(1, 2))
    edited = base.replace("Do a thing.", "Do a thing. GENUINELY EDITED.")  # keeps old v1 hash
    r = _check(vs, edited)
    assert "HASH-BASIS-MIGRATION:" not in _detail_blob(r)
    assert "has not been modified since approval" in "\n".join(n for n, _s, _d in r.checks)


def test_approve_no_approval_section_errors(tmp_path, capsys):
    # Code-review fix #4: --approve on a doc with no `## Approval` section errors
    # to stderr and leaves the file unchanged — it must NOT print a false "Approved".
    vs = _load_validate_spec()
    p = Path(tmp_path) / "specs/F1-x/spec.md"
    p.parent.mkdir(parents=True)
    p.write_text("# Doc\n\n## Objective\n\nx\n", encoding="utf-8")  # no ## Approval
    before = p.read_text()
    vs.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr()
    assert "Approved:" not in out.out
    assert "no `## Approval` section" in out.err
    assert p.read_text() == before


# --- R8: scoped approval rewrites ------------------------------------------


def test_approval_section_prose_decoy_bounds_correct(tmp_path):
    vs = _load_validate_spec()
    body = (
        "# Doc\n\n## Objective\n\nThis body quotes a `## Approval` line in prose.\n\n"
        "## Panel Review\n\n" + _CHURN_TRAJ_HEADER + _crow(1) + "\n\n"
        "## Approval\n\n- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    p = Path(tmp_path) / "specs/F1-x/spec.md"
    p.parent.mkdir(parents=True)
    p.write_text(body, encoding="utf-8")
    vs.approve_document(p, project_root=tmp_path)
    txt = p.read_text()
    assert bc.read_hash_basis(txt) == "v2"  # basis written into the REAL section
    assert bc.verify_content_hash(txt, bc.read_stored_hash(txt))


def test_approval_rewrite_scoped_body_prose_untouched(tmp_path):
    # A `## Notes` section AFTER ## Approval quotes an UNCHECKED checkbox + a
    # DISTINCT-sentinel Content-Hash line — the exact forms the OLD document-wide
    # re.sub would rewrite (flipping the box, restamping the sentinel). Placed
    # after ## Approval so the document-wide stored-hash READ still reads the real
    # section (the read is intentionally not scoped — see the authoring caution),
    # isolating the WRITE-scoping behaviour R8/AD10 fixes.
    decoy = (
        "## Notes\n\nExample in prose:\n- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `deadbeefdeadbeef`\n"
    )
    body = (
        "# Doc\n\n## Objective\n\nx\n\n## Panel Review\n\n"
        + _CHURN_TRAJ_HEADER + _crow(1) + "\n\n"
        "## Approval\n\n- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`\n\n"
        + decoy
    )
    for mod, sub in ((_load_validate_spec(), "specs/F1-x"), (_load_validate_blueprint(), "blueprint")):
        p = Path(tmp_path) / sub / "doc.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        mod.approve_document(p, project_root=tmp_path)
        txt = p.read_text()
        # decoy lines (in ## Notes) are byte-unchanged (old global re.sub corrupted them)
        assert "- [ ] Approved to proceed to next phase\n- **Content Hash:** `deadbeefdeadbeef`" in txt
        # the real ## Approval section is approved + coherent (no false stale FAIL)
        assert "- [x] Approved to proceed to next phase" in txt
        assert bc.verify_content_hash(txt, bc.read_stored_hash(txt))


# --- R9: obligation lifecycle (unconditional preserve) ---------------------


def test_r9_f47_six_step_repro_clears_via_doctrine_path(tmp_path):
    for mod, sub in ((_load_validate_spec(), "specs/F1-x"), (_load_validate_blueprint(), "blueprint")):
        root = tmp_path / sub.split("/")[0]  # distinct marker root per validator
        root.mkdir(exist_ok=True)
        key = f"{sub}/doc.md"
        p = Path(tmp_path) / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_churn_doc(passes=(1, 2, 3), checked=False, hash_val="pending"), encoding="utf-8")
        mod.approve_document(p, project_root=tmp_path)            # (1) approved, pass N=3
        _substantive_edit(p, "edit")
        mod.approve_document(p, project_root=tmp_path)            # (2) obligation (H1, N)
        entry = _pending(tmp_path)[key]
        h1, n = entry["hash"], entry["stamped_at_pass"]
        _add_traj_row(p, 4)                                       # (3) archive pass N+1
        _substantive_edit(p, "auto-fix")
        mod.approve_document(p, project_root=tmp_path)            # (4) auto-fix re-stamp
        after = _pending(tmp_path)[key]
        assert after["hash"] == h1 and after["stamped_at_pass"] == n  # NOT re-anchored
        _set_row_tag(p, 4, h1[:8])                                # (5) stamp the tag
        assert bc.reconcile_pending_review(tmp_path, sub) == []   # (6) cleared


def test_r9_post_archive_restamp_preserves_two_consecutive_restamps(tmp_path):
    vs = _load_validate_spec()
    key = "specs/F1-x/spec.md"
    p = _seed_churn_approved(tmp_path, key, passes=(1, 2, 3))
    _substantive_edit(p, "edit")
    vs.approve_document(p, project_root=tmp_path)
    h1 = _pending(tmp_path)[key]["hash"]
    for marker in ("fix one", "fix two"):
        _add_traj_row(p, 4 if marker == "fix one" else 5)
        _substantive_edit(p, marker)
        vs.approve_document(p, project_root=tmp_path)
        assert _pending(tmp_path)[key]["hash"] == h1  # byte-identical across BOTH


def test_r9_substantive_edit_while_open_preserves_not_second_marker(tmp_path, capsys):
    vs = _load_validate_spec()
    key = "specs/F1-x/spec.md"
    p = _seed_churn_approved(tmp_path, key, passes=(1, 2, 3),
                             sealed="- `[SEAL-01]` **X** (pass 1, sealed) — Defense: original.")
    _substantive_edit(p, "edit")
    vs.approve_document(p, project_root=tmp_path)
    h1 = _pending(tmp_path)[key]["hash"]
    capsys.readouterr()
    p.write_text(p.read_text().replace("Defense: original", "Defense: changed"), encoding="utf-8")
    vs.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    assert list(_pending(tmp_path)) == [key]          # exactly one obligation
    assert _pending(tmp_path)[key]["hash"] == h1      # held verbatim
    assert "RE-APPROVAL REMINDER" not in out


def test_r9_preserved_obligation_clears_on_doctrine_tag(tmp_path):
    key = "specs/F1-x/spec.md"
    p = Path(tmp_path) / key
    p.parent.mkdir(parents=True)
    p.write_text(_churn_doc(passes=(1, 2, 3), checked=True, hash_val="a" * 16), encoding="utf-8")
    bc.upsert_pending_entry(tmp_path, key, "a" * 16, "t", 3)  # already-preserved obligation
    _add_traj_row(p, 4, notes="upstream-panel aaaaaaaa")
    assert bc.reconcile_pending_review(tmp_path, "specs/F1-x") == []


def test_r9_reconcile_readout_corrupt_marker_still_fails_loud(tmp_path):
    _write_corrupt(tmp_path)
    # ONE fixture, BOTH behaviours: dispatch read fails open, reconcile stays strict.
    assert bc.read_open_obligation(marker_root=tmp_path, doc_rel="specs/F1-x/spec.md") is None
    res = bc.reconcile_to_result(tmp_path, "specs/F1-x", decline_cmd="x", restore_cmd="y")
    blob = _detail_blob(res).lower()
    assert ("corrupt" in blob or "unreadable" in blob) and not res.passed


def test_r9_corrupt_marker_on_approve_aborts_not_silent_create(tmp_path):
    import pytest
    vs = _load_validate_spec()
    p = _seed_churn_approved(tmp_path, "specs/F1-x/spec.md", passes=(1,))
    _write_corrupt(tmp_path)
    before = _marker_file(tmp_path).read_bytes()
    _substantive_edit(p, "edit on corrupt marker")
    with pytest.raises(bc.MarkerCorruptError):
        vs.approve_document(p, project_root=tmp_path)
    assert _marker_file(tmp_path).read_bytes() == before  # corrupt file not clobbered


def test_r9_tag_detection_uses_raw_not_hashed_text(tmp_path):
    key = "specs/F1-x/spec.md"
    p = Path(tmp_path) / key
    p.parent.mkdir(parents=True)
    p.write_text(_churn_doc(passes=(1, 2, 3), checked=True, hash_val="b" * 16), encoding="utf-8")
    bc.upsert_pending_entry(tmp_path, key, "b" * 16, "t", 3)
    _add_traj_row(p, 4, notes="upstream-panel bbbbbbbb")
    # raw reconcile clears; the hashed (stripped) form would have no tag at all
    assert bc._doc_has_any_qualifying_tag(bc.content_for_hashing(p.read_text()), "bbbbbbbb") is False
    assert bc.reconcile_pending_review(tmp_path, "specs/F1-x") == []


def test_r9_legacy_v1_obligation_surfaces_via_unsatisfiable_detector(tmp_path):
    vs = _load_validate_spec()
    key = "specs/F1-x/spec.md"
    # A legacy v1 obligation: marker hash = the v1 content hash, tag already on
    # pass N == anchor (the F47 corrupted state from pre-fix re-anchoring).
    p, v1 = _seed_v1(tmp_path, key, passes=(1, 2, 3))
    _set_row_tag(p, 3, v1[:8])
    bc.upsert_pending_entry(tmp_path, key, v1, "t", 3)  # anchor == tagged pass 3
    vs.approve_document(p, project_root=tmp_path)        # migrates doc to v2; preserves obligation
    assert _pending(tmp_path)[key]["hash"] == v1         # legacy v1 hash preserved, NOT re-derived
    res = bc.reconcile_to_result(tmp_path, "specs/F1-x", decline_cmd="x", restore_cmd="y")
    assert bc.UNSATISFIABLE_OBLIGATION_TOKEN in _detail_blob(res)


def test_r9_task_tick_restamp_does_not_enter_r9_branch(tmp_path, capsys):
    vs = _load_validate_spec()
    key = "specs/F1-x/tasks.md"
    p = _seed_churn_approved(tmp_path, key, passes=(1, 2, 3))
    bc.upsert_pending_entry(tmp_path, key, "c" * 16, "t", 3)  # an open obligation
    capsys.readouterr()
    p.write_text(p.read_text() + "\nchanged tick\n", encoding="utf-8")
    vs.approve_document(p, task_tick=True, project_root=tmp_path)
    out = capsys.readouterr().out
    assert "r9-preserve:" not in out  # task_tick early-return precedes the R9 branch
    assert _pending(tmp_path)[key]["hash"] == "c" * 16  # obligation untouched


def test_r9_convergence_only_restamp_mid_obligation_preserves(tmp_path, capsys):
    vs = _load_validate_spec()
    key = "specs/F1-x/spec.md"
    p = _seed_churn_approved(tmp_path, key, passes=(1, 2, 3))
    _substantive_edit(p, "edit")
    vs.approve_document(p, project_root=tmp_path)
    h1, n = _pending(tmp_path)[key]["hash"], _pending(tmp_path)[key]["stamped_at_pass"]
    capsys.readouterr()
    _add_traj_row(p, 4, notes="converged (0 HIGH)")  # convergence-only while open
    vs.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    assert _pending(tmp_path)[key]["hash"] == h1 and _pending(tmp_path)[key]["stamped_at_pass"] == n
    assert "RE-APPROVAL REMINDER" not in out


def test_r9_basis_migration_restamp_mid_obligation_preserves(tmp_path, capsys):
    vs = _load_validate_spec()
    key = "specs/F1-x/spec.md"
    p, v1 = _seed_v1(tmp_path, key, passes=(1, 2, 3))
    bc.upsert_pending_entry(tmp_path, key, "d" * 16, "t", 3)  # an open obligation on a v1 doc
    capsys.readouterr()
    vs.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    # R9-preserve governs (NOT R4 migrate-suppress): the obligation is held, no new marker.
    assert _pending(tmp_path)[key]["hash"] == "d" * 16
    assert "hash-basis-migrated:" not in out
    assert "r9-preserve:" in out


def test_r9_no_open_obligation_fresh_edit_creates_new(tmp_path, capsys):
    vs = _load_validate_spec()
    key = "specs/F1-x/spec.md"
    p = _seed_churn_approved(tmp_path, key, passes=(1,))
    capsys.readouterr()
    _substantive_edit(p, "fresh edit")
    vs.approve_document(p, project_root=tmp_path)
    assert key in _pending(tmp_path)
    assert "RE-APPROVAL REMINDER" in capsys.readouterr().out


def _setup_unsat(tmp_path, anchor, tag_pass):
    key = "specs/F1-x/spec.md"
    p = Path(tmp_path) / key
    p.parent.mkdir(parents=True)
    p.write_text(_churn_doc(passes=(1, 2, 3), checked=True, hash_val="e" * 16), encoding="utf-8")
    _set_row_tag(p, tag_pass, "eeeeeeee")
    bc.upsert_pending_entry(tmp_path, key, "e" * 16, "t", anchor)
    return key


def test_r9_unsatisfiable_detector_fires_when_tag_below_anchor(tmp_path):
    import pytest
    for anchor, tag_pass in ((3, 2), (3, 3)):  # tag < anchor AND tag == anchor (F47 boundary)
        sub = tmp_path / f"a{anchor}p{tag_pass}"
        sub.mkdir()
        key = _setup_unsat(sub, anchor, tag_pass)
        res = bc.reconcile_to_result(sub, "specs/F1-x", decline_cmd="x", restore_cmd="y")
        assert bc.UNSATISFIABLE_OBLIGATION_TOKEN in _detail_blob(res), (anchor, tag_pass)


def test_r9_unsatisfiable_detector_no_false_positive_no_tag_yet(tmp_path):
    key = "specs/F1-x/spec.md"
    p = Path(tmp_path) / key
    p.parent.mkdir(parents=True)
    p.write_text(_churn_doc(passes=(1, 2, 3), checked=True, hash_val="e" * 16), encoding="utf-8")
    bc.upsert_pending_entry(tmp_path, key, "e" * 16, "t", 3)  # no tag yet
    res = bc.reconcile_to_result(tmp_path, "specs/F1-x", decline_cmd="x", restore_cmd="y")
    blob = _detail_blob(res)
    assert bc.UNSATISFIABLE_OBLIGATION_TOKEN not in blob
    assert "upstream panel re-review pending" in blob


def test_r9_unsatisfiable_remedy_is_content_attested(tmp_path):
    # With a genuine tag -> restore clears; without -> it does not.
    key = _setup_unsat(tmp_path, anchor=3, tag_pass=3)
    assert bc.restore_anchor_for_prefix(tmp_path, "specs/F1-x") == [key]
    assert _pending(tmp_path) == {}
    # no-tag case: restore is a no-op
    tmp2 = tmp_path / "no_tag"
    tmp2.mkdir()
    p2 = tmp2 / key
    p2.parent.mkdir(parents=True)
    p2.write_text(_churn_doc(passes=(1, 2, 3), checked=True, hash_val="e" * 16), encoding="utf-8")
    bc.upsert_pending_entry(tmp2, key, "e" * 16, "t", 3)
    assert bc.restore_anchor_for_prefix(tmp2, "specs/F1-x") == []
    assert key in bc.read_pending_review(tmp2)["pending"]


def test_r9_unsatisfiable_diagnostic_distinct_from_generic_pending(tmp_path):
    unsat = tmp_path / "unsat"
    unsat.mkdir()
    _setup_unsat(unsat, anchor=3, tag_pass=3)
    unsat_blob = _detail_blob(bc.reconcile_to_result(unsat, "specs/F1-x", decline_cmd="x", restore_cmd="y"))
    generic = tmp_path / "generic"
    generic.mkdir()
    key = "specs/F1-x/spec.md"
    (generic / key).parent.mkdir(parents=True)
    (generic / key).write_text(_churn_doc(passes=(1,), checked=True, hash_val="e" * 16), encoding="utf-8")
    bc.upsert_pending_entry(generic, key, "e" * 16, "t", 0)
    generic_blob = _detail_blob(bc.reconcile_to_result(generic, "specs/F1-x", decline_cmd="x", restore_cmd="y"))
    assert bc.UNSATISFIABLE_OBLIGATION_TOKEN in unsat_blob
    assert bc.UNSATISFIABLE_OBLIGATION_TOKEN not in generic_blob


# --- R10: orphaned-row detection (integration) -----------------------------


def _orphan_spec(tmp_path, sub, orphan_row, passes=(1, 2, 3)):
    rows = "".join(_crow(p) + "\n" for p in passes)
    body = (
        "# F\n\n**PLAN feature identifier:** `n/a`\n\n## Objective\n\nx\n\n## Panel Review\n\n"
        + _CHURN_TRAJ_HEADER + rows + "\n" + orphan_row + "\n\n"
        "### Sealed dispositions\n\n_None yet._\n\n"
        "## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    d = Path(tmp_path) / sub
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(body, encoding="utf-8")
    return d


def test_r10_load_bearing_orphan_fails_both_validators(tmp_path):
    # A doc whose Trajectory has a stranded high-Pass (load-bearing) row.
    rows = "".join(_crow(p) + "\n" for p in (1, 2, 3))
    doc = (
        "# F\n\n## Panel Review\n\n" + _CHURN_TRAJ_HEADER + rows + "\n" + _crow(29) + "\n\n"
        "## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    )
    # Drive each validator module's OWN validate_panel_review, not the shared
    # blueprint_common one — that is the regression this guards against (a
    # validator that forks a pre-R10 local copy would pass the shared call but
    # fail here).
    for mod in (_load_validate_spec(), _load_validate_blueprint()):
        r = bc.ValidationResult()
        mod.validate_panel_review(doc, "spec.md", r)
        blob = _detail_blob(r)
        assert "ORPHANED-TRAJECTORY-ROW:" in blob, f"missing in {mod.__name__}"
        assert not r.passed, f"should block in {mod.__name__}"


def test_r10_non_load_bearing_orphan_warns_not_blocks(tmp_path):
    rows = "".join(_crow(p) + "\n" for p in (1, 2, 3))
    doc = (
        "# F\n\n## Panel Review\n\n" + _CHURN_TRAJ_HEADER + rows + "\n" + _crow(2) + "\n\n"
        "## Approval\n\n- [x] Approved\n- **Content Hash:** `h`\n"
    )
    r = bc.ValidationResult()
    bc.validate_panel_review(doc, "spec.md", r)
    assert "ORPHANED-TRAJECTORY-ROW:" in _detail_blob(r)
    assert r.passed and r.has_warnings  # WARN, not blocking


def test_r10_orphan_diagnostic_names_row(tmp_path):
    rows = "".join(_crow(p) + "\n" for p in (1, 2, 3))
    doc = (
        "# F\n\n## Panel Review\n\n" + _CHURN_TRAJ_HEADER + rows + "\n" + _crow(29) + "\n\n"
        "## Approval\n\n- [x] Approved\n- **Content Hash:** `h`\n"
    )
    r = bc.ValidationResult()
    bc.validate_panel_review(doc, "spec.md", r)
    blob = _detail_blob(r)
    assert "line " in blob and "| 29" in blob  # names the specific row
    assert "make the row contiguous" in blob.lower() or "contiguous" in blob.lower()
    assert "delet" in blob.lower()  # offers the delete remedy too


def test_r10_no_false_positive_body_prose_or_fenced(tmp_path):
    rows = "".join(_crow(p) + "\n" for p in (1, 2, 3))
    doc = (
        "# F\n\n## Panel Review\n\n" + _CHURN_TRAJ_HEADER + rows + "\n"
        "```\n| 88 | fenced |\n```\n\nsee `| 77 | prose |` inline\n\n"
        "| A | B |\n|---|---|\n| 99 | x |\n\n"
        "## Approval\n\n- [x] Approved\n- **Content Hash:** `h`\n"
    )
    r = bc.ValidationResult()
    bc.validate_panel_review(doc, "spec.md", r)
    assert "ORPHANED-TRAJECTORY-ROW:" not in _detail_blob(r)


def test_r10_warn_to_fail_transition_on_tag_gain(tmp_path):
    rows = "".join(_crow(p) + "\n" for p in (1, 2, 3))
    base = "# F\n\n## Panel Review\n\n" + _CHURN_TRAJ_HEADER + rows + "\n{ORPHAN}\n\n## Approval\n\n- [x] Approved\n- **Content Hash:** `h`\n"
    warn_doc = base.replace("{ORPHAN}", _crow(2))  # Pass <= max, no tag -> WARN
    r1 = bc.ValidationResult()
    bc.validate_panel_review(warn_doc, "spec.md", r1)
    assert r1.passed and r1.has_warnings
    fail_doc = base.replace("{ORPHAN}", _crow(2, notes="upstream-panel aaaaaaaa"))  # gains a tag
    r2 = bc.ValidationResult()
    bc.validate_panel_review(fail_doc, "spec.md", r2)
    assert not r2.passed  # escalated to blocking FAIL


def test_r10_detector_runs_before_r9_reconcile(tmp_path):
    # A genuine tag on an ORPHANED row: R9 reconcile can't see it (keeps the
    # obligation open) AND R10 raises an independent blocking FAIL.
    key = "specs/F1-x/spec.md"
    p = Path(tmp_path) / key
    p.parent.mkdir(parents=True)
    rows = "".join(_crow(pn) + "\n" for pn in (1, 2, 3))
    doc = (
        "# F\n\n## Panel Review\n\n" + _CHURN_TRAJ_HEADER + rows + "\n"
        + _crow(4, notes="upstream-panel ffffffff") + "\n\n"  # ORPHANED tag row
        "## Approval\n\n- [x] Approved\n- **Content Hash:** `" + "f" * 16 + "`\n"
    )
    p.write_text(doc, encoding="utf-8")
    bc.upsert_pending_entry(tmp_path, key, "f" * 16, "t", 3)
    # R9 reconcile cannot see the orphaned tag -> obligation stays open
    assert bc.reconcile_pending_review(tmp_path, "specs/F1-x") == [(key, "upstream-panel ffffffff")]
    # R10 independently FAILs on the orphan
    r = bc.ValidationResult()
    bc.validate_panel_review(doc, "spec.md", r)
    assert not r.passed and "ORPHANED-TRAJECTORY-ROW:" in _detail_blob(r)


def test_r10_detection_does_not_mutate_document(tmp_path):
    d = _orphan_spec(tmp_path, "specs/F1-x", _crow(29))
    before = (d / "spec.md").read_bytes()
    _run_vs(str(d), "--phase", "spec", "--project-root", str(tmp_path))
    assert (d / "spec.md").read_bytes() == before  # no auto-heal


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
    # --- Pending-review churn: R1–R8 (T5) ---
    "test_convergence_only_no_marker_spec",
    "test_convergence_only_no_marker_blueprint",
    "test_convergence_only_unrelated_entry_undisturbed",
    "test_substantive_edit_still_writes_marker_spec",
    "test_substantive_edit_still_writes_marker_blueprint",
    "test_latest_pass_detail_edit_writes_marker",
    "test_defense_mutation_writes_marker",
    "test_deferred_dispositions_mutation_writes_marker",
    "test_close_path_tag_stamp_terminates",
    "test_close_path_fixture_hash_matches",
    "test_migration_fail_emitted_old_basis",
    "test_migration_fail_exit_code_nonzero",
    "test_migration_fail_distinguishable_from_pending_review",
    "test_migration_restamp_no_marker_spec",
    "test_migration_restamp_no_marker_blueprint",
    "test_migration_concurrent_edit_writes_marker",
    "test_migration_round_trip_idempotent",
    "test_migration_grown_trajectory_writes_marker",
    "test_bare_archive_write_validation_clean",
    "test_v1_v2_equal_no_migration_message",
    "test_migration_severity_is_fail_not_warn",
    "test_migration_message_contains_basis_migration_token",
    "test_migration_restamp_suppress_msg_token",
    "test_body_prose_basis_decoy_still_migration_fail",
    "test_v2_basis_genuine_edit_stale_fail",
    "test_approval_section_prose_decoy_bounds_correct",
    "test_approval_rewrite_scoped_body_prose_untouched",
    # --- Pending-review churn: R9 (T12) ---
    "test_r9_f47_six_step_repro_clears_via_doctrine_path",
    "test_r9_post_archive_restamp_preserves_two_consecutive_restamps",
    "test_r9_substantive_edit_while_open_preserves_not_second_marker",
    "test_r9_preserved_obligation_clears_on_doctrine_tag",
    "test_r9_reconcile_readout_corrupt_marker_still_fails_loud",
    "test_r9_corrupt_marker_on_approve_aborts_not_silent_create",
    "test_r9_tag_detection_uses_raw_not_hashed_text",
    "test_r9_legacy_v1_obligation_surfaces_via_unsatisfiable_detector",
    "test_r9_task_tick_restamp_does_not_enter_r9_branch",
    "test_r9_convergence_only_restamp_mid_obligation_preserves",
    "test_r9_basis_migration_restamp_mid_obligation_preserves",
    "test_r9_no_open_obligation_fresh_edit_creates_new",
    "test_r9_unsatisfiable_detector_fires_when_tag_below_anchor",
    "test_r9_unsatisfiable_detector_no_false_positive_no_tag_yet",
    "test_r9_unsatisfiable_remedy_is_content_attested",
    "test_r9_unsatisfiable_diagnostic_distinct_from_generic_pending",
    # --- Pending-review churn: R10 integration (T14) ---
    "test_r10_load_bearing_orphan_fails_both_validators",
    "test_r10_non_load_bearing_orphan_warns_not_blocks",
    "test_r10_orphan_diagnostic_names_row",
    "test_r10_no_false_positive_body_prose_or_fenced",
    "test_r10_warn_to_fail_transition_on_tag_gain",
    "test_r10_detector_runs_before_r9_reconcile",
    "test_r10_detection_does_not_mutate_document",
    # --- Code-review remediations (medium-effort review of 5739d94) ---
    "test_genuine_v1_edit_is_stale_not_migration",
    "test_approve_no_approval_section_errors",
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
