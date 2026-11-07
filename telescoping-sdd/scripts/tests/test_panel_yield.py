"""Tests for the read-only `panel_yield.py` aggregator — Unit C, T9.

Design CP6, AD10, AD18, DM4, DM7, I10, `[SEAL-09]`, `[SEAL-26]`; spec R6.
"""

from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"
_PANEL_YIELD = _SCRIPTS / "panel_yield.py"

_PINNED = [
    ("MED_LOW_CAVEAT", "not equal-confidence"),
    ("MED_LOW_CAVEAT", "under-merging inflates"),
    ("MED_LOW_CAVEAT", "omission deflates"),
    ("MED_LOW_CAVEAT", "slightly high"),
    ("MED_LOW_CAVEAT", "bidirectional"),
    ("MED_LOW_CAVEAT", "re-grade"),
    ("MED_LOW_CAVEAT", "indistinguishable from a quiet panelist"),
    ("MED_LOW_CAVEAT", "never order-checked"),
    ("MED_LOW_CAVEAT", "suppressed by a roster"),
    ("MED_LOW_CAVEAT", "later duplicate seat"),
    ("MED_LOW_CAVEAT", "under-represented"),
    ("YIELD_NOT_COST", "yield only, not cost"),
    ("YIELD_NOT_COST", "tool-call count"),
    ("YIELD_NOT_COST", "counted by hand"),
    ("YIELD_NOT_COST", "destroyed at archive"),
]
_ROSTER_NAMES = ["user-advocate", "devils-advocate", "pragmatist", "architect",
                 "testability-reviewer", "security-reviewer", "ops-reviewer",
                 "delivery-manager", "critic", "simplifier"]


def _load():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    if "panel_yield" in sys.modules:
        return importlib.reload(sys.modules["panel_yield"])
    return importlib.import_module("panel_yield")


_HDR = ("| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n")


def _row(p, notes, addressed="0"):
    return f"| {p} | 2026-11-07 | 0 | 0 | {addressed} | 0 | 0 | {notes} |\n"


def _art(rows: str) -> str:
    return ("# Doc\n\n## Objective\n\nx\n\n## Panel Review\n\n### Trajectory\n\n"
            + _HDR + rows +
            "\n### Sealed dispositions\n\n_None yet._\n\n### Latest pass detail\n\n"
            "| Severity | Source | Concern | Disposition | Notes |\n"
            "|----------|--------|---------|-------------|-------|\n\n"
            "## Approval\n\n- [ ] Approved\n- **Content Hash:** `pending`\n")


_PROV = "prov=0123456789abcdef"
_CASE_A = (
    _row(1, f"panel=2.1.0,0.0.1,1.3.2; {_PROV}")
    + _row(2, f"converged (0 HIGH); panel=0.1.0,2.0.1,0.0.0; {_PROV}")
    + _row(3, "skipped (mechanical: typo)")
)


def _write(tmp_path: Path, name: str, text: str, sub: str = "a") -> Path:
    d = tmp_path / sub
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_PANEL_YIELD), *args],
                          capture_output=True, text=True, check=False)


def test_case_a_renders_groups_and_no_data_rows(tmp_path):
    py = _load()
    p = _write(tmp_path, "01_spec.md", _art(_CASE_A))
    res = py.read_artifact_yield(p)
    assert res.status == "ok" and res.tier == "sdd" and res.phase == 1 and res.elided == 0
    assert [x.pass_label for x in res.passes] == ["1", "2", "3"]
    assert res.passes[0].seats == [(2, 1, 0), (0, 0, 1), (1, 3, 2)]
    assert res.passes[2].seats is None and res.passes[2].note == "archived --skip"
    text = py.render_text([res])
    assert f"{p} (sdd phase 1, 3 passes, nothing elided)" in text
    assert re.search(r"pass\s+seat 1\s+seat 2\s+seat 3", text)
    assert re.search(r"1\s+2\.1\.0\s+0\.0\.1\s+1\.3\.2", text)
    line3 = next(ln for ln in text.splitlines() if ln.strip().startswith("3 "))
    assert line3.count("— no data —") == 3 and "(archived --skip)" in line3


def test_tokenless_normal_row_is_no_data_not_zero(tmp_path):
    py = _load()
    p = _write(tmp_path, "02_design.md", _art(
        _row(1, f"tags=d0u0c1; {_PROV}") + _row(2, f"panel=0.0.0,0.0.0,0.0.0; {_PROV}")))
    res = py.read_artifact_yield(p)
    assert res.passes[0].seats is None and res.passes[0].note == "no panel= token"
    assert res.passes[1].seats == [(0, 0, 0)] * 3 and res.passes[1].note == ""
    text = py.render_text([res])
    assert "— no data —" in text and "0.0.0" in text


def _elided_fixture() -> str:
    sys.path.insert(0, str(_SCRIPTS))
    import trajectory as tr

    rows = "".join(_row(i, f"panel=1.0.0,0.0.0,0.0.{i}; {_PROV}") for i in range(1, 19))
    return tr.trim_trajectory_table(_art(rows))


def test_elided_trajectory_reported_partially_elided_with_count(tmp_path):
    py = _load()
    text_in = _elided_fixture()
    assert "3 earlier passes elided" in text_in
    p = _write(tmp_path, "02_design.md", text_in)
    res = py.read_artifact_yield(p)
    assert res.elided == 3
    text = py.render_text([res])
    assert f"{p} (sdd phase 2, 18 passes recorded, 3 earlier passes elided)" in text
    body = [ln for ln in text.splitlines() if ln.startswith("  ")][1:]
    assert body[0].lstrip().startswith("…") and "— elided —" in body[0]
    assert "(3 earlier passes elided)" in body[0]
    assert body[1].split()[0] == "4"


def test_escaped_pipe_in_notes_parsed_via_split_table_row(tmp_path):
    py = _load()
    p = _write(tmp_path, "01_spec.md", _art(
        _row(1, rf"a \| b; panel=1.2.3,0.0.0,0.0.1; {_PROV}")))
    res = py.read_artifact_yield(p)
    assert res.passes[0].seats == [(1, 2, 3), (0, 0, 0), (0, 0, 1)]


def test_legacy_rows_without_prov_decode_alongside_stamped_rows(tmp_path):
    py = _load()
    p = _write(tmp_path, "01_spec.md", _art(
        _row(1, "panel=1.0.0,0.0.0,0.0.0") + _row(2, f"panel=0.1.0,0.0.0,0.0.0; {_PROV}")))
    res = py.read_artifact_yield(p)
    assert [x.seats[0] for x in res.passes] == [(1, 0, 0), (0, 1, 0)]


def test_ragged_and_over_long_rows_are_skipped(tmp_path):
    py = _load()
    ragged = "| 2 | 2026-11-07 | 0 | 0 | 0 | panel=9.9.9,9.9.9,9.9.9 |\n"
    over = f"| 3 | 2026-11-07 | 0 | 0 | 0 | 0 | 0 | panel=8.8.8,8.8.8,8.8.8 | extra |\n"
    p = _write(tmp_path, "01_spec.md", _art(
        _row(1, f"panel=1.0.0,0.0.0,0.0.0; {_PROV}") + ragged + over))
    res = py.read_artifact_yield(p)
    assert [x.pass_label for x in res.passes] == ["1"]
    text = py.render_text([res])
    js = py.render_json([res])
    assert "(sdd phase 1, 1 passes, nothing elided)" in text
    for out in (text, js):
        assert "9.9.9" not in out and "8.8.8" not in out


def test_ragged_skip_row_is_dropped_by_arity_rule(tmp_path):
    py = _load()
    ragged_skip = "| 2 | 2026-11-07 | skipped (mechanical: x) |\n"
    text_in = _elided_fixture()
    text_in = text_in.replace(_row(18, f"panel=1.0.0,0.0.0,0.0.18; {_PROV}"),
                              _row(18, f"panel=1.0.0,0.0.0,0.0.18; {_PROV}")
                              + ragged_skip + _row(19, "skipped (mechanical: y)"))
    p = _write(tmp_path, "02_design.md", text_in)
    res = py.read_artifact_yield(p)
    labels = [x.pass_label for x in res.passes]
    assert labels[0] == "…" and "19" in labels and "2" not in labels
    assert res.passes[-1].note == "archived --skip"


def test_non_integer_addressed_row_is_skipped(tmp_path):
    py = _load()
    p = _write(tmp_path, "01_spec.md", _art(
        _row(1, f"panel=1.0.0,0.0.0,0.0.0; {_PROV}")
        + _row(2, f"panel=7.7.7,7.7.7,7.7.7; {_PROV}", addressed="many")))
    res = py.read_artifact_yield(p)
    assert [x.pass_label for x in res.passes] == ["1"]
    assert "7.7.7" not in py.render_text([res])


def test_all_rows_arity_skipped_renders_header_with_zero_passes(tmp_path):
    py = _load()
    p = _write(tmp_path, "01_spec.md", _art(
        "| 1 | 2026-11-07 | 0 | panel=1.0.0,0.0.0,0.0.0 |\n"))
    res = py.read_artifact_yield(p)
    assert res.status == "ok" and res.passes == []
    text = py.render_text([res])
    block = text.split("\n\n")[0]
    assert block == f"{p} (sdd phase 1, 0 passes, nothing elided)"
    assert "seat" not in block
    assert "trajectory omitted." not in text
    data = json.loads(py.render_json([res]))
    assert data["artifacts"][0]["status"] == "ok" and data["artifacts"][0]["passes"] == []


def test_json_output_is_valid_and_matches_text_data(tmp_path):
    p = _write(tmp_path, "01_spec.md", _art(_CASE_A))
    proc = _run(str(p), "--json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    a = data["artifacts"][0]
    assert a["path"] == str(p) and a["tier"] == "sdd" and a["phase"] == 1 and a["elided"] == 0
    assert [x["pass_label"] for x in a["passes"]] == ["1", "2", "3"]
    assert a["passes"][0]["seats"] == [[2, 1, 0], [0, 0, 1], [1, 3, 2]]
    assert a["passes"][2]["seats"] is None
    assert set(data["caveats"]) == {"med_low_confidence", "yield_not_cost"}


@pytest.mark.parametrize("const,phrase", _PINNED)
@pytest.mark.parametrize("fmt", ["text", "json"])
def test_outputs_carry_every_pinned_caveat_phrase(tmp_path, const, phrase, fmt):
    py = _load()
    assert phrase in getattr(py, const)
    p = _write(tmp_path, "01_spec.md", _art(_CASE_A))
    proc = _run(str(p), *(["--json"] if fmt == "json" else []))
    assert proc.returncode == 0
    out = json.dumps(json.loads(proc.stdout)) if fmt == "json" else proc.stdout
    haystack = json.loads(proc.stdout)["caveats"] if fmt == "json" else out
    if fmt == "json":
        assert any(phrase in v for v in haystack.values())
    else:
        assert phrase in out


def test_run_mutates_nothing_and_creates_no_sdd(tmp_path):
    files = [_write(tmp_path, "01_spec.md", _art(_CASE_A)),
             _write(tmp_path, "notes.md", "# no panel\n", sub="b")]
    before = {f: (f.read_bytes(), f.stat().st_mtime_ns) for f in files}
    for extra in ([], ["--json"]):
        assert _run(str(tmp_path), *extra).returncode == 0
    assert {f: (f.read_bytes(), f.stat().st_mtime_ns) for f in files} == before
    assert not list(tmp_path.rglob(".sdd"))


def test_missing_path_exits_one_and_reports_others(tmp_path):
    p = _write(tmp_path, "01_spec.md", _art(_CASE_A))
    missing = tmp_path / "nope.md"
    proc = _run(str(missing), str(p))
    assert proc.returncode == 1
    assert str(missing) in proc.stderr
    assert f"{p} (sdd phase 1, 3 passes, nothing elided)" in proc.stdout


def test_non_utf8_file_reported_unreadable_and_walk_continues(tmp_path):
    py = _load()
    bad = tmp_path / "a" / "02_design.md"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"\xff\xfe\x00 not utf-8 \x80")
    good = _write(tmp_path, "01_spec.md", _art(_CASE_A))
    assert py.read_artifact_yield(bad).status == "unreadable"
    proc = _run(str(tmp_path))
    assert proc.returncode == 0
    assert f"{bad} (unreadable)" in proc.stdout
    assert f"{good} (sdd phase 1" in proc.stdout


def test_files_without_panel_review_omitted_with_count_line(tmp_path):
    _write(tmp_path, "x.md", "# just notes\n", sub="n")
    _write(tmp_path, "y.md", "# more notes\n", sub="n")
    good = _write(tmp_path, "01_spec.md", _art(_CASE_A))
    proc = _run(str(tmp_path))
    assert proc.returncode == 0
    assert "2 file(s) with no ## Panel Review trajectory omitted." in proc.stdout
    assert "x.md" not in proc.stdout and "y.md" not in proc.stdout
    proc2 = _run(str(good))
    assert "trajectory omitted." not in proc2.stdout


def test_aggregator_imports_match_allow_list_and_never_reference_canonical_rosters():
    tree = ast.parse(_PANEL_YIELD.read_text(encoding="utf-8"))
    stdlib = set(sys.stdlib_module_names)
    non_std = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] in stdlib, a.name
                assert a.name != "CANONICAL_ROSTERS"
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            for a in node.names:
                assert a.name != "CANONICAL_ROSTERS" and a.asname != "CANONICAL_ROSTERS"
            if mod not in stdlib:
                non_std.setdefault(mod, set()).update(a.name for a in node.names)
        elif isinstance(node, ast.Name):
            assert node.id != "CANONICAL_ROSTERS"
        elif isinstance(node, ast.Attribute):
            assert node.attr != "CANONICAL_ROSTERS"
    assert non_std == {
        "archive_pass": {"parse_panel_summary", "ARTIFACT_STEMS"},
        "trajectory": {"parse_trajectory_rows", "TRAJECTORY_ELIDED_NOTES_RE",
                       "STAMP_STRICT_BAR", "STAMP_CROSS_CHECK", "_strip_numeric_prefix"},
    }, non_std
    src = _PANEL_YIELD.read_text(encoding="utf-8")
    assert "panel-log.jsonl" not in src
    assert "archive_pass.CANONICAL_ROSTERS" in ast.get_docstring(tree)


def test_aggregator_output_names_no_roster_member(tmp_path):
    p = _write(tmp_path, "01_spec.md", _art(_CASE_A))
    for extra in ([], ["--json"]):
        out = _run(str(p), *extra).stdout
        for name in _ROSTER_NAMES:
            assert not re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", out), name
