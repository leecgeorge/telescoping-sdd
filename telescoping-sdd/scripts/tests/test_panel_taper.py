"""Unit D (R5, R6): the tapered panel roster — record, width hold, engine.

Unit section first: the `seats=` Notes token (DM1, AD11) and the Trajectory
header-width hold (AD12) in `trajectory.py` (I1). Later Unit D tasks add the
archive-side, advisory and posture sections below.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
_TESTS = _SCRIPTS / "tests"
for _p in (_SCRIPTS, _TESTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import archive_pass as ap  # noqa: E402
import trajectory as tj  # noqa: E402

_GOLDEN = _TESTS / "fixtures" / "render_table_pre_unit_d_golden.txt"

# The row set the golden was captured from (before any Unit D edit).
_GOLDEN_ROWS = [
    {"Pass": "1", "Date": "2026-11-07", "HIGHs": "2", "Regressions": "0", "Addressed": "5",
     "Deferred": "1", "Sealed": "0",
     "Notes": "panel=1.2.0,0.1.1,1.0.0; tags=d1u0c1; prov=0123456789abcdef"},
    {"Pass": "2", "Date": "2026-11-07", "HIGHs": "1", "Regressions": "1", "Addressed": "3",
     "Deferred": "0", "Sealed": "1",
     "Notes": "panel=1.0.0,0.1.0; seats=1,3; tags=d1u0c0; a deliberately widest Notes cell "
              "so it sets the column; prov=fedcba9876543210"},
    {"Pass": "3", "Date": "2026-11-08", "HIGHs": "0", "Regressions": "0", "Addressed": "0",
     "Deferred": "0", "Sealed": "0", "Notes": "converged (0 HIGH)"},
]


def _row(notes: str, n: str = "2") -> dict:
    return {"Pass": n, "Date": "2026-11-07", "HIGHs": "0", "Regressions": "0",
            "Addressed": "1", "Deferred": "0", "Sealed": "0", "Notes": notes}


# ---------------------------------------------------------------------------
# I1 unit section
# ---------------------------------------------------------------------------

def test_render_table_measure_none_matches_golden():
    out = (tj.render_table(tj.TRAJECTORY_COLS, _GOLDEN_ROWS) + [""]
           + tj.render_table(tj.TRAJECTORY_COLS, []))
    assert "\n".join(out) + "\n" == _GOLDEN.read_text(encoding="utf-8")


@pytest.mark.parametrize("positions", [(1,), (2,), (3,), (1, 2), (1, 3), (2, 3)])
def test_parse_seats_record_round_trips_format_seats_record(positions):
    groups = ",".join(["1.0.0"] * len(positions))
    notes = f"panel={groups}; {tj.format_seats_record(positions)}; tags=d1u0c0"
    assert tj.format_seats_record(positions) == "seats=" + ",".join(map(str, positions))
    assert tj.parse_seats_record(notes) == positions


def test_parse_seats_record_does_not_consume_adjacent_tokens():
    notes = "panel=1.0.0,0.1.0; seats=1,3; tags=d1u0c0; prov=0123456789abcdef"
    assert tj.parse_seats_record(notes) == (1, 3)
    start, end = tj._seats_token_span(notes)
    assert notes[start:end] == "; seats=1,3"
    assert tj._strip_seats_for_width(notes) == "panel=1.0.0,0.1.0; tags=d1u0c0; prov=0123456789abcdef"


@pytest.mark.parametrize("notes", [
    "panel=1.0.0,0.1.0; tags=d1u0c0",
    "panel=1.0.0,0.1.0,0.0.0",
    "converged (0 HIGH)",
    "",
    "tags=d1u0c0; seats=1,3",          # no panel= before it
])
def test_parse_seats_record_none_when_token_absent(notes):
    assert tj.parse_seats_record(notes) is None


@pytest.mark.parametrize("notes", [
    "panel=1.0.0,0.1.0; seats=2,1",          # not increasing
    "panel=1.0.0,0.1.0; seats=1,4",          # beyond the roster length
    "panel=1.0.0,0.1.0,0.0.1; seats=1,2,3",  # a full roster carries no seats=
    "panel=1.0.0; seats=1,3",                # count differs from panel= groups
    "panel=1.0.0,0.1.0; seats=1,1",          # repeated
])
def test_parse_seats_record_rejects_invalid_records(notes):
    assert tj.parse_seats_record(notes) is None


def test_seats_token_present_true_for_invalid_token():
    assert tj.seats_token_present("panel=1.0.0,0.1.0; seats=2,1") is True
    assert tj.seats_token_present("panel=1.0.0,0.1.0; seats=1,3") is True
    assert tj.seats_token_present("panel=1.0.0,0.1.0; tags=d1u0c0") is False


@pytest.mark.parametrize("bad", [(), (2, 1), (1, 1), (0,), (10,), (1, 3, 2)])
def test_format_seats_record_rejects_invalid_positions(bad):
    with pytest.raises(ValueError):
        tj.format_seats_record(bad)


def test_seats_in_halt_text_ignored_and_width_unchanged():
    notes = "panel=1.0.0,0.1.0; halt vote 1: seats=1,3 must go"
    assert tj.parse_seats_record(notes) is None
    assert tj.seats_token_present(notes) is False
    assert tj.trajectory_measure("Notes", notes) == len(notes)


def test_multi_halt_title_with_forged_panel_seats_ignored():
    notes = ("tags=d1u0c0; halt vote 2: panel=1.0.0,0.1.0; seats=1,3; "
             "halt vote 3: panel=1.0.0; seats=2")
    assert tj.parse_seats_record(notes) is None
    assert tj._strip_seats_for_width(notes) == notes


def test_empty_piece_before_seats_still_found():
    notes = "panel=1.0.0,0.1.0;  ; seats=1,3; tags=d1u0c0"
    assert tj.parse_seats_record(notes) == (1, 3)
    assert tj._strip_seats_for_width(notes) == "panel=1.0.0,0.1.0;  ; tags=d1u0c0"


def test_trailing_upstream_panel_tag_after_prov_does_not_shift_span():
    notes = "panel=1.0.0,0.1.0; seats=1,3; prov=0123456789abcdef; upstream-panel 0a1b2c3d"
    start, end = tj._seats_token_span(notes)
    assert notes[start:end] == "; seats=1,3"
    assert tj.parse_seats_record(notes) == (1, 3)


def test_seats_group_pattern_equals_unit_c_panel_token_re():
    assert tj._G == rf"{ap._N}\.{ap._N}\.{ap._N}"
    assert ap.PANEL_TOKEN_RE.pattern == rf"panel=({tj._G}(?:,{tj._G})*)"
    assert tj.PANEL_TOKEN_FULL_RE.pattern == rf"panel={tj._G}(?:,{tj._G})*"


def test_seats_max_position_matches_canonical_roster_lengths():
    # [DEF-02]: the hardcoded roster length 3 equals every canonical roster.
    assert {len(r) for r in ap.CANONICAL_ROSTERS.values()} == {tj.SEATS_ROSTER_LENGTH}
    assert tj.SEATS_ROSTER_LENGTH == 3


def test_trajectory_measure_strips_only_seats_token():
    notes = "panel=1.0.0,0.1.0; seats=1,3; tags=d1u0c0"
    assert tj.trajectory_measure("Notes", notes) == len(notes) - len("; seats=1,3")
    assert tj.trajectory_measure("Date", "; seats=1,3") == len("; seats=1,3")
    assert tj.trajectory_measure("Notes", "tags=d1u0c0") == len("tags=d1u0c0")


@pytest.mark.parametrize("widest_has_seats", [True, False])
def test_render_trajectory_table_header_independent_of_seats_tokens(widest_has_seats):
    long = "a deliberately widest Notes cell, wider than any other in the table"
    with_seats = [
        _row("panel=1.0.0,0.1.0,0.0.0; tags=d0u0c0", "1"),
        _row(f"panel=1.0.0,0.1.0; seats=1,3; {long}" if widest_has_seats
             else "panel=1.0.0,0.1.0; seats=1,3", "2"),
    ]
    without = [dict(r, Notes=tj._strip_seats_for_width(r["Notes"])) for r in with_seats]
    a = tj.render_trajectory_table(with_seats)
    b = tj.render_trajectory_table(without)
    assert a[:2] == b[:2]
    assert with_seats[1]["Notes"] in a[3]  # data row written in full


def test_render_trajectory_table_headers_kwarg_renders_on_disk_header():
    on_disk = ["Pass", "Date", "HIGHs", "Regressions", "Addressed", "Deferred", "Sealed", "Notez"]
    rows = [dict(_row("panel=1.0.0,0.1.0; seats=1,3"), Notez="panel=1.0.0,0.1.0; seats=1,3")]
    out = tj.render_trajectory_table(rows, headers=on_disk)
    assert out[0].split("|")[8].strip() == "Notez"
    assert tj.render_trajectory_table(rows)[0].split("|")[8].strip() == "Notes"


# ---------------------------------------------------------------------------
# T18 (AD11, C5): tapered --panel-roster acceptance and the seats= stamp
# ---------------------------------------------------------------------------

import subprocess  # noqa: E402

import _fixtures as fx  # noqa: E402
import content_hash as ch  # noqa: E402

_ARCHIVE = _SCRIPTS / "archive_pass.py"


def _staged(tmp_path, name="spec.md", rows=None):
    p = tmp_path / name
    fx.stamp_then_stage_pass(
        p, "sdd",
        latest_rows=rows or ["| [MED] | user-advocate | a concern | Addressed | fixed |"],
        mode="normal",
    )
    return p


def _archive(p, phase, *flags):
    return subprocess.run([sys.executable, str(_ARCHIVE), str(p), "--phase", str(phase), *flags],
                          capture_output=True, text=True)


def _traj(text):
    lines = text.split("\n")
    i = lines.index("### Trajectory")
    h = next(k for k in range(i + 1, len(lines)) if lines[k].startswith("|"))
    end = next(k for k in range(h, len(lines)) if not lines[k].startswith("|"))
    return lines, h, end


def _newest_notes(text):
    lines, h, end = _traj(text)
    return lines[end - 1].split("|")[8].strip()


def _recordless(text):
    """The same file with the seats= span removed and the table re-rendered by
    the pre-feature renderer (no width hold)."""
    lines, h, end = _traj(text)
    header = [c.strip() for c in lines[h].strip("|").split("|")]
    rows = [dict(zip(header, (c.strip() for c in ln.strip("|").split("|"))))
            for ln in lines[h + 2:end]]
    rows = [dict(r, Notes=tj._strip_seats_for_width(r["Notes"])) for r in rows]
    return "\n".join(lines[:h] + tj.render_table(header, rows) + lines[end:])


def test_seats_widest_notes_header_matches_recordless_render(tmp_path):
    p = _staged(tmp_path)
    proc = _archive(p, 1, "--panel-roster", "user-advocate,pragmatist")
    assert proc.returncode == 0, proc.stderr
    text = p.read_text(encoding="utf-8")
    assert "; seats=1,3" in _newest_notes(text)
    lines, h, end = _traj(text)
    widest = max(lines[h + 2:end], key=len)
    assert "seats=" in widest
    assert lines[h:h + 2] == _recordless(text).split("\n")[h:h + 2]


def test_seats_record_leaves_content_hash_and_convergence_verdict_unchanged(tmp_path):
    p = _staged(tmp_path)
    assert _archive(p, 1, "--panel-roster", "user-advocate,pragmatist").returncode == 0
    text = p.read_text(encoding="utf-8")
    assert "seats=1,3" in text
    bare = _recordless(text)
    # Load-bearing: v2 hashes header padding, so it moves without AD12.
    assert ch.compute_content_hash_v2(text) == ch.compute_content_hash_v2(bare)
    assert ch.compute_content_hash(text) == ch.compute_content_hash(bare)
    assert tj.evaluate_convergence(text) == tj.evaluate_convergence(bare)


@pytest.mark.parametrize("roster,seats", [
    ("user-advocate,pragmatist", "seats=1,3"),
    ("devils-advocate", "seats=2"),
    ("user-advocate,devils-advocate", "seats=1,2"),
])
def test_subset_roster_stamps_panel_and_seats_no_stderr(tmp_path, roster, seats):
    names = roster.split(",")
    p = _staged(tmp_path, rows=[f"| [MED] | {names[0]} | a concern | Addressed | fixed |"])
    proc = _archive(p, 1, "--panel-roster", roster)
    assert proc.returncode == 0 and proc.stderr == "", proc.stderr
    notes = _newest_notes(p.read_text(encoding="utf-8"))
    groups = ",".join(["0.1.0"] + ["0.0.0"] * (len(names) - 1))
    assert f"panel={groups}; {seats}" in notes
    assert tj.parse_seats_record(notes) == tuple(int(x) for x in seats[6:].split(","))


def test_full_roster_stamps_no_seats_token(tmp_path):
    p = _staged(tmp_path)
    proc = _archive(p, 1, "--panel-roster", "user-advocate,devils-advocate,pragmatist")
    assert proc.returncode == 0 and proc.stderr == "", proc.stderr
    notes = _newest_notes(p.read_text(encoding="utf-8"))
    assert "panel=0.1.0,0.0.0,0.0.0" in notes and "seats=" not in notes


@pytest.mark.parametrize("roster", [
    "pragmatist,user-advocate",          # transposed subset
    "user-advocate,user-advocate",       # duplicated
    "user-advocate,critic",              # unrecognised for phase 1
])
def test_transposed_or_duplicated_subset_warns_and_stamps_neither(tmp_path, roster):
    p = _staged(tmp_path)
    proc = _archive(p, 1, "--panel-roster", roster)
    assert proc.returncode == 0
    assert "warning: panel= not stamped" in proc.stderr
    notes = _newest_notes(p.read_text(encoding="utf-8"))
    assert "panel=" not in notes and "seats=" not in notes


@pytest.mark.parametrize("roster,seats", [
    ("architect,security-reviewer", "seats=1,3"),
    ("architect,ops-reviewer", "seats=1,2"),
    ("testability-reviewer", "seats=2"),
    ("testability-reviewer,ops-reviewer", None),
])
def test_unknown_stem_phase_2_union_lookup_positions(tmp_path, roster, seats):
    names = roster.split(",")
    p = _staged(tmp_path, name="notes.md",
                rows=[f"| [HIGH] | {names[0]} | [contract] c | Addressed | fixed |"])
    proc = _archive(p, 2, "--panel-roster", roster)
    assert proc.returncode == 0, proc.stderr
    notes = _newest_notes(p.read_text(encoding="utf-8"))
    if seats is None:
        assert "warning: panel= not stamped" in proc.stderr
        assert "panel=" not in notes and "seats=" not in notes
    else:
        assert proc.stderr == "", proc.stderr
        assert f"; {seats}" in notes


def test_roster_seat_positions_proper_subsequence_only():
    rsp = ap.roster_seat_positions
    assert rsp(["architect", "security-reviewer"], "sdd", 2) == (1, 3)
    assert rsp(["ops-reviewer"], "blueprint", 2) == (2,)
    assert rsp(["user-advocate", "pragmatist"], None, 1) == (1, 3)
    assert rsp(["critic", "simplifier"], "sdd", 3) == (2, 3)
    assert rsp(["architect", "ops-reviewer"], None, 2) == (1, 2)
    # Not proper (full roster), not a subsequence, or unresolvable -> None.
    assert rsp(list(ap.CANONICAL_ROSTERS[("sdd", 2)]), "sdd", 2) is None
    assert rsp(["security-reviewer", "architect"], "sdd", 2) is None
    assert rsp(["architect", "architect"], "sdd", 2) is None
    assert rsp(["architect", "ops-reviewer"], "sdd", 2) is None
    assert rsp(["testability-reviewer", "ops-reviewer"], None, 2) is None
    assert rsp([], "sdd", 1) is None


# ---------------------------------------------------------------------------
# T19 (I5, DM2, DM6, AD15): --posture, --posture-report, --no-notice
# ---------------------------------------------------------------------------

import json  # noqa: E402

import _flag_matrix  # noqa: E402

_VS_PATH = _SCRIPTS.parent / "skills" / "spec-driven-dev" / "scripts" / "validate_spec.py"
_VB_PATH = _SCRIPTS.parent / "skills" / "project-blueprint" / "scripts" / "validate_blueprint.py"
_NOTICE_LEAD = ("PANEL-POSTURE-NOTICE: standard is now the default — passes after a "
                "loop's first may run fewer panelists. Persist critical to keep every "
                "pass at three: ")


def _project(tmp_path, rel="specs/feat-x/01_spec.md", text="# x\n\n## Panel Review\n"):
    (tmp_path / ".git").mkdir(exist_ok=True)
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _persist(tmp_path, value):
    cfg = tmp_path / ".sdd" / "architecture.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"schemaVersion": 1, "language": "python", "posture": value}),
                   encoding="utf-8")
    return cfg


def _report(p, *flags, phase=1):
    return _archive(p, phase, "--posture-report", *flags)


def _cmd(validator, d):
    import shlex
    return f"python {shlex.quote(str(validator))} {shlex.quote(str(d))} --set-posture critical"


def test_posture_report_sources_flag_config_default(tmp_path):
    p = _project(tmp_path)
    r = _report(p, "--no-notice")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0] == "PANEL-POSTURE: standard (source: default)"
    _persist(tmp_path, "vibe")
    assert _report(p).stdout.splitlines()[0] == "PANEL-POSTURE: vibe (source: config)"
    r = _report(p, "--posture", "critical")
    assert r.stdout.splitlines()[0] == "PANEL-POSTURE: critical (source: flag)"


def test_posture_notice_printed_once_then_sentinel_suppresses(tmp_path):
    p = _project(tmp_path)
    first = _report(p).stdout.splitlines()
    assert first[1].startswith(_NOTICE_LEAD)
    assert (tmp_path / ".sdd" / "posture-notice").is_file()
    second = _report(p).stdout.splitlines()
    assert not any(l.startswith("PANEL-POSTURE-NOTICE:") for l in second)


@pytest.mark.parametrize("rel,expected", [
    ("specs/feat-x/01_spec.md", "sdd"),
    ("blueprint/01_SCOPE.md", "blueprint"),
    ("notes/odd.md", "both"),
])
def test_posture_notice_full_text_pinned_per_tier(tmp_path, rel, expected):
    p = _project(tmp_path, rel)
    notice = _report(p).stdout.splitlines()[1]
    d = p.parent
    if expected == "sdd":
        assert notice == _NOTICE_LEAD + _cmd(_VS_PATH, d)
    elif expected == "blueprint":
        assert notice == _NOTICE_LEAD + _cmd(_VB_PATH, d)
    else:
        assert notice == _NOTICE_LEAD + _cmd(_VS_PATH, d) + ", or " + _cmd(_VB_PATH, d)


def test_no_notice_when_source_flag_or_config(tmp_path):
    p = _project(tmp_path)
    r = _report(p, "--posture", "standard")
    assert not any(l.startswith("PANEL-POSTURE-NOTICE:") for l in r.stdout.splitlines())
    _persist(tmp_path, "standard")
    r = _report(p)
    assert not any(l.startswith("PANEL-POSTURE-NOTICE:") for l in r.stdout.splitlines())
    assert not (tmp_path / ".sdd" / "posture-notice").exists()


def test_no_notice_flag_suppresses_notice_and_sentinel(tmp_path):
    p = _project(tmp_path)
    r = _report(p, "--no-notice")
    assert r.returncode == 0
    assert not any(l.startswith("PANEL-POSTURE-NOTICE:") for l in r.stdout.splitlines())
    assert not (tmp_path / ".sdd" / "posture-notice").exists()


def test_panel_scratch_line_prints_root_and_dir(tmp_path):
    p = _project(tmp_path)
    root = tmp_path.resolve()
    last = _report(p, "--no-notice").stdout.splitlines()[-1]
    assert last == f"PANEL-SCRATCH: root={root} dir={root}/.sdd/scratch/sdd/feat-x/"
    bp = _project(tmp_path, "blueprint/01_SCOPE.md")
    assert _report(bp, "--no-notice").stdout.splitlines()[-1] == \
        f"PANEL-SCRATCH: root={root} dir={root}/.sdd/scratch/blueprint/"


def test_panel_scratch_dir_unresolved_for_unknown_stem(tmp_path):
    p = _project(tmp_path, "notes/odd.md")
    root = tmp_path.resolve()
    assert _report(p, "--no-notice").stdout.splitlines()[-1] == \
        f"PANEL-SCRATCH: root={root} dir=unresolved"


def test_posture_rejected_value_warns_on_stderr(tmp_path):
    p = _project(tmp_path)
    cfg = _persist(tmp_path, "yolo")
    r = _report(p, "--no-notice")
    assert r.returncode == 0
    assert r.stderr == (
        f"warning: ignoring posture 'yolo' in {cfg.resolve()} (not one of critical, "
        "standard, vibe); using 'standard' (default). Persist a valid one with "
        "--set-posture.\n"
    )


def test_posture_multiline_ansi_value_gives_one_bounded_line(tmp_path):
    p = _project(tmp_path)
    _persist(tmp_path, "evil\n\x1b[31mred\x1b[0m" + "x" * 80)
    r = _report(p, "--no-notice")
    lines = r.stderr.splitlines()
    assert len(lines) == 1 and lines[0].startswith("warning: ignoring posture '")
    assert "\x1b" not in r.stderr
    quoted = lines[0].split("'")[1]
    assert len(quoted) <= 40


@pytest.mark.parametrize("value", [7, ["vibe"], None])
def test_posture_non_string_value_gives_non_echoing_warning(tmp_path, value):
    p = _project(tmp_path)
    cfg = _persist(tmp_path, value)
    r = _report(p, "--no-notice")
    assert r.stderr == (
        f"warning: ignoring non-text posture value in {cfg.resolve()}; using "
        "'standard' (default). Persist a valid one with --set-posture.\n"
    )


def test_check_and_skip_print_no_posture_warning(tmp_path):
    p = _staged(tmp_path)
    _persist(tmp_path, "yolo")
    r = _archive(p, 1, "--check")
    assert "posture" not in r.stderr
    r = _archive(p, 1, "--skip", "mechanical")
    assert r.returncode == 0 and "posture" not in r.stderr


def test_normal_archive_prints_rejected_posture_warning(tmp_path):
    p = _staged(tmp_path)
    _persist(tmp_path, "yolo")
    r = _archive(p, 1)
    assert r.returncode == 0, r.stderr
    assert "warning: ignoring posture 'yolo'" in r.stderr
    assert r.stderr.count("warning: ignoring posture") == 1


def test_posture_report_works_on_terminal_artifact_without_terminal_flag(tmp_path):
    p = _project(tmp_path, "specs/feat-x/03_tasks.md")
    r = _report(p, "--no-notice", phase=3)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0].startswith("PANEL-POSTURE: ")


def test_nested_layout_one_root_for_posture_scratch_notice(tmp_path):
    # Posture, scratch and the notice resolve against the ONE marker root
    # (Unit C AD15): with a nested `.sdd/` nearer the artifact, all three use
    # it, and the outer config is not mixed in.
    p = _project(tmp_path, "specs/feat-x/01_spec.md")
    _persist(tmp_path, "critical")
    inner = tmp_path / "specs" / "feat-x"
    (inner / ".sdd").mkdir()
    (inner / ".sdd" / "architecture.json").write_text(
        json.dumps({"schemaVersion": 1, "posture": "vibe"}), encoding="utf-8")
    import blueprint_common as bc
    root = Path(bc._resolve_marker_root_and_key(p, None)[0]).resolve()
    assert root == inner.resolve()
    out = _report(p).stdout.splitlines()
    assert out[0] == "PANEL-POSTURE: vibe (source: config)"
    assert out[-1].startswith(f"PANEL-SCRATCH: root={root} ")
    # Remove the inner posture: the default resolves, and the notice sentinel
    # lands under the same inner root.
    (inner / ".sdd" / "architecture.json").unlink()
    out = _report(p).stdout.splitlines()
    assert out[0] == "PANEL-POSTURE: standard (source: default)"
    assert (inner / ".sdd" / "posture-notice").is_file()
    assert not (tmp_path / ".sdd" / "posture-notice").exists()


def test_posture_notice_sentinel_write_failure_warns_exit_0(tmp_path):
    p = _project(tmp_path)
    (tmp_path / ".sdd").mkdir()
    (tmp_path / ".sdd" / "posture-notice").mkdir()  # a directory: the write fails
    r = _report(p)
    assert r.returncode == 0
    assert any(l.startswith("PANEL-POSTURE-NOTICE:") for l in r.stdout.splitlines())
    assert "warning: could not record the posture notice" in r.stderr


_MATRIX = _flag_matrix.cases()


@pytest.mark.parametrize("flags", [f for k, f in _MATRIX if k in ("refused", "refused-alone")],
                         ids=lambda f: "+".join(f))
def test_flag_matrix_refused_case_exits_1(tmp_path, flags):
    missing = tmp_path / "specs" / "feat-x" / "01_spec.md"  # never created
    r = subprocess.run([sys.executable, str(_ARCHIVE), str(missing), "--phase", "1",
                        *_flag_matrix.argv(flags)], capture_output=True, text=True)
    assert r.returncode == 1, (r.stdout, r.stderr)
    assert r.stderr.startswith("error: ") and "artifact not found" not in r.stderr


@pytest.mark.parametrize("flags", [f for k, f in _MATRIX if k == "ignored"],
                         ids=lambda f: "+".join(f))
def test_flag_matrix_ignored_pair_matches_mode_alone(tmp_path, flags):
    p = _project(tmp_path, "specs/feat-x/01_spec.md")
    mode = next(f for f in flags if f in _flag_matrix.MODES)
    quiet = _flag_matrix.QUIET[mode]
    alone = _archive(p, 1, *_flag_matrix.argv([mode], draft=str(p)), *quiet)
    both = _archive(p, 1, *_flag_matrix.argv(flags, draft=str(p)), *quiet)
    assert alone.returncode == 0, alone.stderr
    assert (both.returncode, both.stdout, both.stderr) == (alone.returncode, alone.stdout, alone.stderr)


@pytest.mark.parametrize("flags", [f for k, f in _MATRIX if k == "allowed"],
                         ids=lambda f: "+".join(f))
def test_flag_matrix_allowed_combination_exits_0(tmp_path, flags):
    p = _project(tmp_path)
    r = _archive(p, 1, *_flag_matrix.argv(flags))
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0] == "PANEL-POSTURE: critical (source: flag)"


def test_flag_matrix_symmetric_no_ordered_duplicates():
    refused = [f for k, f in _MATRIX if k == "refused"]
    assert len(refused) == len(set(refused)) == 2 * len(_flag_matrix.REFUSED_PAIRS)
    for a, b in refused:
        assert (b, a) in refused
    assert len({frozenset(p) for p in _flag_matrix.REFUSED_PAIRS}) == len(_flag_matrix.REFUSED_PAIRS)
    assert all(a != b for a, b in _flag_matrix.REFUSED_PAIRS)


# ---------------------------------------------------------------------------
# T21 (AD9, DM3, DM7): change measurement and size classes
# ---------------------------------------------------------------------------

_BODY = "# Design\n\n## Objective\n\n" + "".join(f"line {i}\n" for i in range(40)) + "\n"
_TAIL = ("## Panel Review\n\n### Trajectory\n\n"
         "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
         "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
         "| 1 | 2026-11-07 | 1 | 0 | 1 | 0 | 0 | panel=1.0.0,0.0.0,0.0.0 |\n\n"
         "### Sealed dispositions\n\n_None yet._\n\n### Latest pass detail\n\n"
         "| Severity | Source | Concern | Disposition | Notes |\n"
         "|----------|--------|---------|-------------|-------|\n\n"
         "## Approval\n\n- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`\n")


def _addr(n, sev="MED"):
    return [{"Severity": f"[{sev}]", "Source": "architect", "Concern": f"c{i}",
             "Disposition": "Addressed", "Notes": "fixed"} for i in range(n)]


def _taper_fixture(tmp_path, *, live_body=_BODY, snapshot=_BODY, draft_present=True,
                   pass_n=2, rel="specs/F1-x/02_design.md", tail=_TAIL, snap_bytes=None):
    (tmp_path / ".git").mkdir(exist_ok=True)
    art = tmp_path / rel
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(live_body + tail, encoding="utf-8")
    snap = ap._snapshot_path(tmp_path, art, pass_n)
    if snap is not None:
        snap.parent.mkdir(parents=True, exist_ok=True)
        if snap_bytes is not None:
            snap.write_bytes(snap_bytes)
        elif snapshot is not None:
            snap.write_text(snapshot + tail, encoding="utf-8")
        if draft_present:
            (snap.parent / f"{art.stem}-draft-p{pass_n}.md").write_text("draft\n", encoding="utf-8")
    return art


def _changed(n):
    return _BODY.replace("".join(f"line {i}\n" for i in range(n)),
                         "".join(f"LINE {i}\n" for i in range(n)), 1)


def _size(tmp_path, art, rows, pass_n=2):
    cs = ap.measure_change(art, tmp_path, rows, pass_n)
    return cs, ap.classify_change(cs)


def test_size_small_at_12_diff_lines(tmp_path):
    art = _taper_fixture(tmp_path, live_body=_changed(6))  # 6 removed + 6 added
    cs, cls = _size(tmp_path, art, _addr(1))
    assert (cs.body_lines, cs.reason, cls) == (12, "measured", "small")


def test_size_large_at_13_diff_lines(tmp_path):
    body = _changed(6).replace("line 39\n", "line 39\nextra\n")
    art = _taper_fixture(tmp_path, live_body=body)
    cs, cls = _size(tmp_path, art, _addr(1))
    assert (cs.body_lines, cls) == (13, "large")


def test_size_small_at_3_addressed(tmp_path):
    art = _taper_fixture(tmp_path, live_body=_changed(1))
    assert _size(tmp_path, art, _addr(3))[1] == "small"


def test_size_large_at_4_addressed(tmp_path):
    art = _taper_fixture(tmp_path, live_body=_changed(1))
    assert _size(tmp_path, art, _addr(4))[1] == "large"


def test_size_boundary_counts_horizontal_rule_and_frontmatter_fence(tmp_path):
    body = "---\ntitle: x\n---\n" + _BODY
    live = body.replace("line 0\n", "---\nline 0\n", 1)   # a body rule added
    art = _taper_fixture(tmp_path, live_body=live.replace("---\ntitle: x\n---\n",
                                                          "---\ntitle: y\n---\n", 1),
                         snapshot=body)
    cs, _cls = _size(tmp_path, art, _addr(1))
    # +--- (the rule) and -title: x / +title: y: 3 changed lines.
    assert cs.body_lines == 3


def test_zero_addressed_with_leftover_snapshot_is_zero(tmp_path):
    art = _taper_fixture(tmp_path, live_body=_changed(20))
    rows = [{"Severity": "[MED]", "Source": "critic", "Concern": "c",
             "Disposition": "Accepted as risk", "Notes": "Defense: x"}]
    cs, cls = _size(tmp_path, art, rows)
    assert (cs.addressed, cs.reason, cls) == (0, "no-edit", "zero")


def test_addressed_with_promote_and_zero_changed_lines_is_small(tmp_path):
    art = _taper_fixture(tmp_path)
    cs, cls = _size(tmp_path, art, _addr(1))
    assert (cs.body_lines, cls) == (0, "small")


def test_zero_byte_snapshot_is_large_snapshot_empty(tmp_path):
    art = _taper_fixture(tmp_path, snap_bytes=b"")
    cs, cls = _size(tmp_path, art, _addr(1))
    assert (cs.body_lines, cs.reason, cls) == (None, "snapshot-empty", "large")


def test_snapshot_without_draft_is_large_no_promote(tmp_path):
    art = _taper_fixture(tmp_path, draft_present=False)
    cs, cls = _size(tmp_path, art, _addr(1))
    assert (cs.body_lines, cs.reason, cls) == (None, "no-promote", "large")


def test_addressed_without_snapshot_is_large_snapshot_absent(tmp_path):
    art = _taper_fixture(tmp_path, snapshot=None, draft_present=False)
    cs, cls = _size(tmp_path, art, _addr(1))
    assert (cs.body_lines, cs.reason, cls) == (None, "snapshot-absent", "large")


def test_addressed_high_forces_large(tmp_path):
    art = _taper_fixture(tmp_path)
    cs, cls = _size(tmp_path, art, _addr(1, "HIGH"))
    assert (cs.addressed_high, cs.body_lines, cls) == (1, 0, "large")


def test_live_without_panel_review_diffs_whole_file_large(tmp_path):
    art = _taper_fixture(tmp_path)
    art.write_text(_BODY, encoding="utf-8")  # lost its ## Panel Review
    cs, cls = _size(tmp_path, art, _addr(1))
    assert cs.body_lines == 0  # the cut bodies match ...
    art.write_text(_BODY + "## Approval\n\n- [ ] x\n", encoding="utf-8")
    cs, cls = _size(tmp_path, art, _addr(1))
    assert cs.body_lines == 3 and cls == "small"
    art.write_text(_BODY + "".join(f"tail {i}\n" for i in range(20)), encoding="utf-8")
    assert _size(tmp_path, art, _addr(1))[1] == "large"


def test_bom_live_file_measures_same_as_without_bom(tmp_path):
    art = _taper_fixture(tmp_path)
    art.write_bytes(b"\xef\xbb\xbf" + art.read_bytes())
    assert _size(tmp_path, art, _addr(1))[0].body_lines == 0


def test_crlf_live_against_lf_snapshot_counts_zero(tmp_path):
    art = _taper_fixture(tmp_path)
    art.write_bytes(art.read_bytes().replace(b"\n", b"\r\n"))
    assert _size(tmp_path, art, _addr(1))[0].body_lines == 0


@pytest.mark.parametrize("where", ["body", "tail"])
def test_fenced_panel_review_quote_not_a_cut_point(tmp_path, where):
    fence = "```\n## Panel Review\nquoted\n```\n"
    if where == "body":
        snap = _BODY.replace("line 5\n", "line 5\n" + fence, 1)
        live = snap.replace("line 30\n", "LINE 30\n", 1)  # an edit after the fence
    else:
        snap = _BODY + fence
        live = snap.replace("line 30\n", "LINE 30\n", 1)
    art = _taper_fixture(tmp_path, live_body=live, snapshot=snap)
    assert _size(tmp_path, art, _addr(1))[0].body_lines == 2


def test_unsuffixed_snapshot_measured_when_suffixed_present(tmp_path):
    art = _taper_fixture(tmp_path)
    snap = ap._snapshot_path(tmp_path, art, 2)
    (snap.parent / f"{art.stem}-snapshot-p2-2.md").write_text(_changed(30) + _TAIL, encoding="utf-8")
    assert _size(tmp_path, art, _addr(1))[0].body_lines == 0


def test_snapshot_path_same_stem_two_spec_dirs_separate_scopes(tmp_path):
    a = tmp_path / "specs" / "F1-a" / "02_design.md"
    b = tmp_path / "specs" / "F2-b" / "02_design.md"
    pa, pb = ap._snapshot_path(tmp_path, a, 3), ap._snapshot_path(tmp_path, b, 3)
    assert pa == tmp_path / ".sdd" / "scratch" / "sdd" / "F1-a" / "02_design-snapshot-p3.md"
    assert pb == tmp_path / ".sdd" / "scratch" / "sdd" / "F2-b" / "02_design-snapshot-p3.md"
    bp = ap._snapshot_path(tmp_path, tmp_path / "blueprint" / "01_SCOPE.md", 2)
    assert bp == tmp_path / ".sdd" / "scratch" / "blueprint" / "01_SCOPE-snapshot-p2.md"


def test_snapshot_path_none_for_unknown_tier(tmp_path):
    assert ap._snapshot_path(tmp_path, tmp_path / "notes" / "odd.md", 2) is None


# ---------------------------------------------------------------------------
# T22 (AD10, DM2-DM4): roster advisory, seat priority, main() wiring
# ---------------------------------------------------------------------------

_ADV_RE = re.compile(
    r"^PANEL-ROSTER-ADVISORY: pass (\d+) roster=([123])/3 survivors=(\S+) "
    r"\(class=(zero|small|large); reason=([a-z-]+); body-lines=(\d+|\?); "
    r"addressed=(\d+|\?); addressed-high=(\d+|\?)\)$")


def _adv_lines(out):
    return [l for l in out.splitlines() if l.startswith("PANEL-ROSTER-ADVISORY:")]


def _adv(out):
    lines = _adv_lines(out)
    assert len(lines) == 1, out
    m = _ADV_RE.match(lines[0])
    assert m, lines[0]
    return m.groups()


def _archived(tmp_path, rows, *flags, rel="01_spec.md", phase=1):
    # stamp_then_stage_pass marks the artifact's own directory as the project
    # root (.git), so the artifact sits at tmp_path for _persist to reach it.
    (tmp_path / ".git").mkdir(exist_ok=True)
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fx.stamp_then_stage_pass(p, "sdd", latest_rows=rows, mode="normal")
    return p, _archive(p, phase, *flags)


_MED_ADDR = ["| [MED] | devils-advocate | c | Addressed | fixed |"]
_ACCEPT = ["| [MED] | devils-advocate | c | Accepted as risk | Defense: fine |"]


def test_advisory_printed_on_normal_standard_archive(tmp_path):
    _p, r = _archived(tmp_path, _MED_ADDR)
    assert r.returncode == 0, r.stderr
    g = _adv(r.stdout)
    assert g[0] == "3" and g[1] == "3"  # no snapshot: large / snapshot-absent
    assert g[4] == "snapshot-absent"


def test_advisory_printed_on_exit_pass(tmp_path):
    _p, r = _archived(tmp_path, _ACCEPT)
    g = _adv(r.stdout)
    assert (g[1], g[3], g[4]) == ("1", "zero", "size")


def test_advisory_printed_on_dry_run_artifact_unchanged(tmp_path):
    (tmp_path / ".git").mkdir()
    p = tmp_path / "specs/F1-x/01_spec.md"
    p.parent.mkdir(parents=True)
    fx.stamp_then_stage_pass(p, "sdd", latest_rows=_ACCEPT, mode="normal")
    before = p.read_bytes()
    r = _archive(p, 1, "--dry-run")
    assert r.returncode == 0, r.stderr
    _adv(r.stdout)
    assert p.read_bytes() == before


@pytest.mark.parametrize("posture", ["critical", "vibe"])
def test_advisory_absent_under_posture_flag_critical_and_vibe(tmp_path, posture):
    _p, r = _archived(tmp_path, _MED_ADDR, "--posture", posture)
    assert r.returncode == 0 and _adv_lines(r.stdout) == []


@pytest.mark.parametrize("posture", ["critical", "vibe"])
def test_advisory_absent_under_persisted_critical_and_vibe(tmp_path, posture):
    _persist(tmp_path, posture)
    _p, r = _archived(tmp_path, _MED_ADDR)
    assert r.returncode == 0 and _adv_lines(r.stdout) == []


@pytest.mark.parametrize("flags", [["--strict-bar"], ["--cross-check"],
                                   ["--skip", "mechanical"], ["--check"]])
def test_advisory_absent_on_strict_bar_cross_check_skip_check(tmp_path, flags):
    _p, r = _archived(tmp_path, _MED_ADDR, *flags)
    assert _adv_lines(r.stdout) == []


def test_advisory_literal_prefix_and_format():
    size = ap.ChangeSize(2, 0, 7, "measured")
    adv = ap.RosterAdvisory(next_pass=4, roster=2, survivors=("architect", "security-reviewer"),
                            size_class="small", reason="size", size=size)
    assert ap.format_roster_advisory(adv) == (
        "PANEL-ROSTER-ADVISORY: pass 4 roster=2/3 survivors=architect,security-reviewer "
        "(class=small; reason=size; body-lines=7; addressed=2; addressed-high=0)")
    full = ap.RosterAdvisory(4, 3, None, "large", "snapshot-absent",
                             ap.ChangeSize(1, 0, None, "snapshot-absent"))
    assert ap.format_roster_advisory(full).endswith(
        "roster=3/3 survivors=all (class=large; reason=snapshot-absent; body-lines=?; "
        "addressed=1; addressed-high=0)")


def _compute(tmp_path, art, rows, *, notes="panel=0.1.0,0.0.0,0.0.0", highs="0",
             phase=1, tier="sdd", pass_n=2):
    row = {"Pass": str(pass_n), "HIGHs": highs, "Notes": notes}
    return ap.compute_roster_advisory(art=art, root=tmp_path, tier=tier, phase=phase,
                                      pass_n=pass_n, latest_rows=rows, new_row=row)


def test_advisory_reason_precedence_order():
    assert ap.ADVISORY_REASONS == (
        "error", "high-on-tapered-pass", "high-unknown-roster", "addressed-high",
        "unknown-tier", "snapshot-absent", "snapshot-empty", "no-promote", "size")


def test_no_addressed_rows_gives_roster_1(tmp_path):
    art = _taper_fixture(tmp_path, rel="specs/F1-x/01_spec.md")
    adv = _compute(tmp_path, art, [])
    assert (adv.roster, adv.size_class, adv.reason, adv.survivors) == (
        1, "zero", "size", ("devils-advocate",))


def test_tapered_pass_with_high_gives_full_roster(tmp_path):
    art = _taper_fixture(tmp_path, rel="specs/F1-x/01_spec.md")
    adv = _compute(tmp_path, art, [], notes="panel=1.0.0; seats=2", highs="1")
    assert (adv.roster, adv.reason, adv.survivors) == (3, "high-on-tapered-pass", None)
    adv = _compute(tmp_path, art, [], notes="panel=1.0.0,0.0.0", highs="1")
    assert adv.reason == "high-on-tapered-pass"


def test_unknown_roster_with_high_gives_full_roster(tmp_path):
    art = _taper_fixture(tmp_path, rel="specs/F1-x/01_spec.md")
    adv = _compute(tmp_path, art, [], notes="converged (0 HIGH)", highs="1")
    assert (adv.roster, adv.reason) == (3, "high-unknown-roster")


def test_duplicate_name_roster_with_high_reads_unknown_gives_3(tmp_path):
    rows = ["| [HIGH] | user-advocate | c | Accepted as risk | Defense: fine |"]
    p, r = _archived(tmp_path, rows, "--panel-roster", "user-advocate,user-advocate,pragmatist")
    assert "warning: panel= not stamped" in r.stderr
    g = _adv(r.stdout)
    assert (g[1], g[4]) == ("3", "high-unknown-roster")


def test_suppressed_subset_roster_reads_as_unknown_not_tapered(tmp_path):
    rows = ["| [HIGH] | user-advocate | c | Accepted as risk | Defense: fine |"]
    _p, r = _archived(tmp_path, rows, "--panel-roster", "pragmatist,user-advocate")
    assert "warning: panel= not stamped" in r.stderr
    assert _adv(r.stdout)[4] == "high-unknown-roster"


@pytest.mark.parametrize("phase", [1, 2, 3])
def test_unknown_stem_with_addressed_gives_unknown_tier_every_phase(tmp_path, phase):
    art = tmp_path / "notes" / "odd.md"
    adv = _compute(tmp_path, art, _addr(1), phase=phase, tier=None)
    assert (adv.roster, adv.reason, adv.size.body_lines) == (3, "unknown-tier", None)


@pytest.mark.parametrize("phase", [1, 2, 3])
def test_unknown_stem_zero_addressed_gives_size_zero_roster_1(tmp_path, phase):
    adv = _compute(tmp_path, tmp_path / "notes" / "odd.md", [], phase=phase, tier=None)
    assert (adv.roster, adv.size_class, adv.reason) == (1, "zero", "size")


def test_unknown_stem_phase_2_names_survivors_for_roster_1_only(tmp_path):
    art = tmp_path / "notes" / "odd.md"
    # Zero Addressed gives roster 1, named; any Addressed row gives
    # unknown-tier and the full roster, so roster 2 is never advised here.
    assert _compute(tmp_path, art, [], phase=2, tier=None).survivors == ("architect",)
    for n in (1, 2, 5):
        adv = _compute(tmp_path, art, _addr(n), phase=2, tier=None)
        assert (adv.roster, adv.survivors) == (3, None)


def test_full_roster_prints_survivors_all(tmp_path):
    art = _taper_fixture(tmp_path, rel="specs/F1-x/01_spec.md")
    adv = _compute(tmp_path, art, _addr(4))
    assert adv.roster == 3 and "survivors=all" in ap.format_roster_advisory(adv)


def test_survivors_match_seat_priority_with_named_anchors():
    assert ap.TAPER_SEAT_PRIORITY == {1: (2, 1, 3), 2: (1, 3, 2), 3: (2, 1, 3)}
    assert ap.name_survivors(1, "sdd", 1) == ("devils-advocate",)
    assert ap.name_survivors(2, "sdd", 1) == ("user-advocate", "devils-advocate")
    assert ap.name_survivors(1, "sdd", 2) == ("architect",)
    assert ap.name_survivors(2, "blueprint", 2) == ("architect", "security-reviewer")
    assert ap.name_survivors(1, "blueprint", 3) == ("critic",)
    assert ap.name_survivors(2, "sdd", 3) == ("delivery-manager", "critic")
    assert ap.name_survivors(3, "sdd", 1) is None


def test_omission_path_persisted_standard_prints_advisory(tmp_path):
    # DK10: the loop-start statement said critical, but the archive is called
    # without --posture and the persisted posture is standard.
    _persist(tmp_path, "standard")
    _p, r = _archived(tmp_path, _MED_ADDR)
    _adv(r.stdout)


def test_forced_exception_gives_reason_error_exit_0(tmp_path, monkeypatch, capsys):
    (tmp_path / ".git").mkdir()
    p = tmp_path / "specs/F1-x/01_spec.md"
    p.parent.mkdir(parents=True)
    fx.stamp_then_stage_pass(p, "sdd", latest_rows=_MED_ADDR, mode="normal")

    def boom(**_k):
        raise RuntimeError("simulated")

    monkeypatch.setattr(ap, "compute_roster_advisory", boom)
    monkeypatch.setattr(sys, "argv", ["archive_pass.py", str(p), "--phase", "1"])
    with pytest.raises(SystemExit) as exc:
        ap.main()
    assert exc.value.code == 0
    g = _adv(capsys.readouterr().out)
    assert (g[1], g[2], g[4]) == ("3", "all", "error")
