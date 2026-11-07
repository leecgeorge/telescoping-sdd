"""Tests for the panel-log sidecar (`.sdd/panel-log.jsonl`) — Unit C, T8.

Design CP5, AD13–AD17, DM3, DM5, I7; spec R7, R8. Self-contained per the
per-file convention (`scripts/tests/` is not a package): a module-local
`_load_archive_pass()` copied from `test_archive_pass.py`.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"
_ARCHIVE_PASS = _SCRIPTS / "archive_pass.py"
_CONFTEST = Path(__file__).resolve().parent / "conftest.py"
_SDD1 = "user-advocate,devils-advocate,pragmatist"


def _load_archive_pass():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    if "archive_pass" in sys.modules:
        return importlib.reload(sys.modules["archive_pass"])
    return importlib.import_module("archive_pass")


def _doc(latest: str, *, deferred: bool = True, traj_rows: str = "") -> str:
    d = (
        "### Deferred dispositions\n\n"
        "<!-- Auto-populated by archive_pass.py when a Deferred-disposed row is "
        "promoted; remains empty until first deferral. -->\n\n"
    ) if deferred else ""
    return (
        "# Doc\n\n## Objective\n\nBody.\n\n## Panel Review\n\n### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        f"{traj_rows}\n"
        "### Sealed dispositions\n\n_None yet._\n\n"
        f"{d}"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        f"{latest}\n## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )


_ROWS = (
    "| [HIGH] | user-advocate | the objective omits the operator | Addressed | added |\n"
    "| [MED] [REGRESSION] | devils-advocate | criterion two is loose | Deferred → design.md | Routed because: design owns it |\n"
    "| [LOW] | [SELF-CHECK] (b) | citation drift | Addressed | re-cited |\n"
)


def _spec(root: Path, latest: str = _ROWS, name: str = "01_spec.md", **kw) -> Path:
    d = root / "specs" / "F1-x"
    d.mkdir(parents=True, exist_ok=True)
    art = d / name
    art.write_text(_doc(latest, **kw), encoding="utf-8")
    return art


def _run(art: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_ARCHIVE_PASS), str(art), *flags],
        capture_output=True, text=True, check=False,
    )


def _log(root: Path) -> Path:
    return root / ".sdd" / "panel-log.jsonl"


def _records(root: Path) -> list:
    return [json.loads(ln) for ln in _log(root).read_text(encoding="utf-8").splitlines()]


def _last_traj_cells(art: Path) -> list:
    rows = [ln for ln in art.read_text(encoding="utf-8").splitlines()
            if re.match(r"^\| \d+\s+\|", ln)]
    return [c.strip() for c in rows[-1].strip()[1:-1].split("|")]


_DM3_FIELDS = ["schema", "artifact", "pass", "phase", "date", "mode", "severity",
               "regression", "source", "concern", "disposition", "notes", "shape"]


# --- AD17: basetemp isolation fixture ------------------------------------

def _conftest():
    spec = importlib.util.spec_from_file_location("_sdd_conftest_under_test", _CONFTEST)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_panel_log_basetemp_guard_removes_sdd_created_during_test(tmp_path):
    guard = _conftest().panel_log_basetemp_guard
    with guard(tmp_path):
        (tmp_path / ".sdd").mkdir()
        (tmp_path / ".sdd" / "panel-log.jsonl").write_text("{}\n")
    assert not (tmp_path / ".sdd").exists()


def test_panel_log_basetemp_guard_keeps_preexisting_sdd(tmp_path):
    guard = _conftest().panel_log_basetemp_guard
    (tmp_path / ".sdd").mkdir()
    (tmp_path / ".sdd" / "keep.txt").write_text("x")
    with guard(tmp_path):
        (tmp_path / ".sdd" / "panel-log.jsonl").write_text("{}\n")
    assert (tmp_path / ".sdd" / "keep.txt").exists()


def test_marker_less_archive_writes_sidecar_under_basetemp_fallback(tmp_path):
    ap = _load_archive_pass()
    art = tmp_path / "spec.md"
    art.write_text(_doc(_ROWS), encoding="utf-8")
    root, _ = ap._resolve_marker_root_and_key(art, None)
    if Path(root).resolve() != tmp_path.parent.resolve():
        pytest.skip("a marker-bearing ancestor exists above tmp_path "
                    "(design AD17 stated limitation (b))")
    assert _run(art, "--phase", "1").returncode == 0
    assert _log(tmp_path.parent).is_file()
    assert not _log(_REPO_ROOT).exists() or _REPO_ROOT.resolve() != Path(root).resolve()


# --- Records -------------------------------------------------------------

def test_archive_appends_one_record_per_row_with_all_fields(tmp_path):
    art = _spec(tmp_path)
    proc = _run(art, "--phase", "1")
    assert proc.returncode == 0, proc.stderr
    raw = _log(tmp_path).read_bytes()
    assert raw.isascii()
    recs = _records(tmp_path)
    assert len(recs) == 3
    for r in recs:
        assert list(r) == _DM3_FIELDS
        assert r["schema"] == 1
        assert r["artifact"] == "specs/F1-x/01_spec.md"
        assert r["phase"] == 1 and r["mode"] == "normal"
    assert [r["severity"] for r in recs] == ["HIGH", "MED", "LOW"]
    assert [r["regression"] for r in recs] == [False, True, False]
    assert recs[0]["source"] == "user-advocate"
    assert recs[1]["disposition"] == "Deferred → design.md"
    assert recs[1]["notes"] == "Routed because: design owns it"


def test_record_pass_and_date_match_new_trajectory_row(tmp_path):
    art = _spec(tmp_path)
    assert _run(art, "--phase", "1").returncode == 0
    cells = _last_traj_cells(art)
    for r in _records(tmp_path):
        assert r["pass"] == int(cells[0])
        assert r["date"] == cells[1]


def test_record_round_trips_escaped_pipe_non_ascii_backslash_and_quote(tmp_path):
    concern = r"a \| pipe, café, back\slash and a \"quote\""
    art = _spec(tmp_path, f"| [LOW] | pragmatist | {concern} | Addressed | n |\n")
    assert _run(art, "--phase", "1").returncode == 0
    assert _log(tmp_path).read_bytes().isascii()
    rec = _records(tmp_path)[0]
    ap = _load_archive_pass()
    parsed = ap.split_table_row(f"| [LOW] | pragmatist | {concern} | Addressed | n |")
    assert rec["concern"] == parsed[2].strip()
    assert "|" in rec["concern"] and "\\|" not in rec["concern"]
    assert "é" in rec["concern"]


def test_record_line_separator_chars_written_as_ascii_escapes(tmp_path):
    ap = _load_archive_pass()
    rows = [{"Severity": "[LOW]", "Source": "critic",
             "Concern": f"a{ch}b", "Disposition": "Addressed", "Notes": f"n{ch}m"}
            for ch in (" ", " ", "\u0085")]
    recs = ap.build_panel_log_records(rows, artifact_key="specs/F1-x/03_tasks.md",
                                      pass_n=4, phase=3, date_iso="2026-11-07", mode="normal")
    ap.append_panel_log(tmp_path, recs)
    raw = _log(tmp_path).read_bytes()
    assert raw.isascii()
    lines = raw.split(b"\n")
    assert lines[-1] == b"" and len(lines) == 4  # three physical lines + final newline
    back = [json.loads(ln) for ln in lines[:-1]]
    assert [b["concern"] for b in back] == [r["Concern"] for r in rows]
    assert [b["notes"] for b in back] == [r["Notes"] for r in rows]


def test_record_notes_keep_raw_rerouted_marker(tmp_path):
    rows = (
        "| [MED] | critic | rerouted item | Sealed | Defense: rerouted [DEF-01] |\n"
    )
    art = _spec(tmp_path, rows)
    text = art.read_text(encoding="utf-8").replace(
        "<!-- Auto-populated by archive_pass.py when a Deferred-disposed row is "
        "promoted; remains empty until first deferral. -->",
        "- `[DEF-01]` **rerouted item** → design.md (pass 1) — Routed because: "
        "design owns it.")
    art.write_text(text, encoding="utf-8")
    proc = _run(art, "--phase", "1")
    assert proc.returncode == 0, proc.stderr
    assert _records(tmp_path)[0]["notes"] == "Defense: rerouted [DEF-01]"


# --- Shape (AD16) --------------------------------------------------------

def _shape(**row):
    ap = _load_archive_pass()
    base = {"Severity": "[MED]", "Source": "critic", "Concern": "c",
            "Disposition": "Addressed", "Notes": "n"}
    base.update(row)
    return ap.derive_defect_shape(base)


def test_shape_derivation_per_marker_kind():
    assert _shape() == []
    assert _shape(Concern="[contract] c") == ["scope:contract"]
    assert _shape(Concern="  [detail] c") == ["scope:detail"]
    assert _shape(Concern="[upstream] c") == ["scope:upstream"]
    assert _shape(Source="[SELF-CHECK] (c)") == ["self-check:c"]
    assert _shape(Severity="[HIGH] [REGRESSION]") == ["regression"]
    assert _shape(Concern="[upstream] c", Source="[SELF-CHECK] (a)",
                  Severity="[REGRESSION] [HIGH]") == [
        "scope:upstream", "self-check:a", "regression"]


def test_shape_self_check_letters_e_and_f_emit_markers():
    assert _shape(Source="[SELF-CHECK] (e)") == ["self-check:e"]
    assert _shape(Source="[SELF-CHECK] (f)") == ["self-check:f"]


def test_shape_self_check_letter_outside_a_to_f_emits_no_marker():
    assert _shape(Source="[SELF-CHECK] (g)") == []


# --- Write gate (AD13, AD14) ---------------------------------------------

def test_dry_run_writes_no_sidecar(tmp_path):
    art = _spec(tmp_path)
    assert _run(art, "--phase", "1", "--dry-run").returncode == 0
    assert not _log(tmp_path).exists()


def test_orphan_refused_write_leaves_sidecar_unchanged(tmp_path, monkeypatch):
    ap = _load_archive_pass()
    art = _spec(tmp_path)
    _log(tmp_path).parent.mkdir(parents=True)
    _log(tmp_path).write_text('{"pre": 1}\n', encoding="utf-8")
    before = _log(tmp_path).read_bytes()

    def refuse(path, old, new, dry_run=False):
        raise SystemExit(1)

    monkeypatch.setattr(ap, "_orphan_guard", refuse)
    monkeypatch.setattr(sys, "argv", ["archive_pass.py", str(art), "--phase", "1"])
    with pytest.raises(SystemExit) as exc:
        ap.main()
    assert exc.value.code == 1
    assert _log(tmp_path).read_bytes() == before


def test_check_mode_writes_no_sidecar(tmp_path):
    art = _spec(tmp_path)
    assert _run(art, "--phase", "1", "--check").returncode == 0
    assert not _log(tmp_path).exists()


def test_skip_with_rows_appends_nothing(tmp_path):
    art = _spec(tmp_path)
    assert _run(art, "--phase", "1", "--skip", "mechanical").returncode == 0
    assert not _log(tmp_path).exists()


@pytest.mark.parametrize("mode", ["--strict-bar", "--cross-check"])
def test_empty_mode_pass_appends_nothing(tmp_path, mode):
    art = _spec(tmp_path, "")
    assert _run(art, "--phase", "1", mode).returncode == 0
    assert not _log(tmp_path).exists()


def test_provenance_mismatch_exit_appends_nothing(tmp_path, monkeypatch):
    ap = _load_archive_pass()
    art = _spec(tmp_path)
    before = art.read_bytes()

    def boom(build, hasher):
        raise RuntimeError("divergent render")

    monkeypatch.setattr(ap, "stamp_provenance", boom)
    monkeypatch.setattr(sys, "argv", ["archive_pass.py", str(art), "--phase", "1"])
    with pytest.raises(SystemExit) as exc:
        ap.main()
    assert exc.value.code == 1
    assert art.read_bytes() == before
    assert not _log(tmp_path).exists()


@pytest.mark.parametrize("flag,mode", [("--strict-bar", "strict-bar"),
                                       ("--cross-check", "cross-check")])
def test_record_mode_reflects_strict_bar_and_cross_check(tmp_path, flag, mode):
    art = _spec(tmp_path, "| [LOW] | pragmatist | c | Addressed | n |\n")
    assert _run(art, "--phase", "1", flag).returncode == 0
    assert [r["mode"] for r in _records(tmp_path)] == [mode]


def test_empty_normal_archive_appends_nothing(tmp_path):
    art = _spec(tmp_path, "")
    assert _run(art, "--phase", "1").returncode == 0
    assert not _log(tmp_path).exists()


# --- Append integrity ----------------------------------------------------

def _refill(art: Path, rows: str) -> None:
    sep = "|----------|--------|---------|-------------|-------|\n"
    text = art.read_text(encoding="utf-8")
    assert text.count(sep) == 1
    art.write_text(text.replace(sep, sep + rows), encoding="utf-8")


def test_consecutive_archives_append_both_passes_without_duplicates(tmp_path):
    art = _spec(tmp_path, "| [LOW] | pragmatist | first | Addressed | n |\n")
    assert _run(art, "--phase", "1").returncode == 0
    _refill(art, "| [MED] | critic | second | Addressed | n |\n")
    assert _run(art, "--phase", "1").returncode == 0
    recs = _records(tmp_path)
    assert [(r["pass"], r["concern"]) for r in recs] == [(1, "first"), (2, "second")]


def test_append_after_record_missing_trailing_newline_starts_new_line(tmp_path):
    _log(tmp_path).parent.mkdir(parents=True)
    _log(tmp_path).write_text('{"schema": 1, "torn": false}', encoding="utf-8")
    art = _spec(tmp_path, "| [LOW] | pragmatist | after | Addressed | n |\n")
    assert _run(art, "--phase", "1").returncode == 0
    lines = _log(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert [json.loads(ln) for ln in lines][1]["concern"] == "after"


# --- Failure isolation ---------------------------------------------------

def _archive_bytes_with_failing_sidecar(tmp_path, latest=_ROWS) -> bytes:
    root = tmp_path / "failing"
    art = _spec(root, latest)
    (root / ".sdd").write_text("not a directory", encoding="utf-8")
    proc = _run(art, "--phase", "1")
    assert proc.returncode == 0
    return art.read_bytes()


def _norm_date(b: bytes) -> bytes:
    return re.sub(rb"\d{4}-\d{2}-\d{2}", b"<DATE>", b)


def test_sidecar_write_failure_warns_and_archive_succeeds(tmp_path):
    root = tmp_path / "failing"
    art = _spec(root)
    (root / ".sdd").write_text("not a directory", encoding="utf-8")
    # --posture critical: no Unit D roster advisory on stdout.
    proc = _run(art, "--phase", "1", "--posture", "critical")
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert proc.stderr.startswith("warning: panel-log append to ")
    assert "failed (" in proc.stderr
    assert proc.stderr.rstrip().endswith("; the artifact archive itself succeeded.")
    ok = _spec(tmp_path / "ok")
    assert _run(ok, "--phase", "1").returncode == 0
    assert art.read_bytes() == ok.read_bytes()


def test_record_building_exception_warns_and_exits_zero(tmp_path, monkeypatch, capsys):
    ap = _load_archive_pass()
    art = _spec(tmp_path)

    def boom(*a, **k):
        raise ValueError("record build failed")

    monkeypatch.setattr(ap, "build_panel_log_records", boom)
    monkeypatch.setattr(sys, "argv", ["archive_pass.py", str(art), "--phase", "1",
                                      "--posture", "critical"])
    with pytest.raises(SystemExit) as exc:
        ap.main()
    assert exc.value.code == 0
    out = capsys.readouterr()
    assert out.out == ""
    assert "warning: panel-log append to " in out.err
    assert "ValueError: record build failed" in out.err
    assert not _log(tmp_path).exists()
    ok = _spec(tmp_path / "ok")
    assert _run(ok, "--phase", "1").returncode == 0
    assert art.read_bytes() == ok.read_bytes()


def test_sidecar_append_creates_no_pending_review_marker(tmp_path):
    art = _spec(tmp_path)
    assert _run(art, "--phase", "1").returncode == 0
    assert not list(tmp_path.rglob("pending-review.json"))


def test_sidecar_append_changes_no_hash_and_writes_no_other_file(tmp_path):
    _load_archive_pass()
    import content_hash as ch

    art = _spec(tmp_path / "ok")
    before = {p for p in (tmp_path / "ok").rglob("*")}
    assert _run(art, "--phase", "1").returncode == 0
    after = {p for p in (tmp_path / "ok").rglob("*")}
    written = after - before
    assert written == {tmp_path / "ok" / ".sdd", _log(tmp_path / "ok")}
    failing = _archive_bytes_with_failing_sidecar(tmp_path)
    assert art.read_bytes() == failing
    assert ch.compute_content_hash(art.read_text(encoding="utf-8")) == \
        ch.compute_content_hash(failing.decode("utf-8"))


def test_panel_log_has_no_consumer_outside_archive_pass():
    root = _REPO_ROOT / "telescoping-sdd"
    hits = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if "tests" not in p.relative_to(root).parts
        and "panel-log.jsonl" in p.read_text(encoding="utf-8")
    )
    assert hits == ["scripts/archive_pass.py"], hits
