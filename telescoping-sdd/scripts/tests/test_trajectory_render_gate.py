"""Unit D (AD12, DK1): `render_trajectory_table` is the only Trajectory renderer.

Persistent grep gate modelled on `test_artifact_prefix.py`'s
`test_grep_gate_catches_known_bad`: outside `trajectory.py`, every
`render_table(` call must render the Latest-pass table (`LATEST_COLS`). Any
other call would bypass the header-width hold and re-pad the Trajectory header
on a `seats=`-widened row.
"""

from __future__ import annotations

import re
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parents[2]
_CALL_RE = re.compile(r"\brender_table\(\s*([^,)\s]*)")


def _modules() -> list:
    mods = [*(_PLUGIN / "scripts").glob("*.py"), *(_PLUGIN / "skills").glob("*/scripts/*.py")]
    return [p for p in mods if p.name != "trajectory.py" and not p.name.startswith("test_")]


def flag_trajectory_render_calls(source: str) -> list:
    """Each `render_table(` call (not its definition) whose first argument is
    not `LATEST_COLS`."""
    hits = []
    for line in source.splitlines():
        code = line.split("#", 1)[0]
        if re.match(r"\s*def render_table\(", code):
            continue
        for m in _CALL_RE.finditer(code):
            if m.group(1) != "LATEST_COLS":
                hits.append(line.strip())
    return hits


def test_no_trajectory_render_table_call_outside_trajectory():
    mods = _modules()
    assert any(p.name == "archive_pass.py" for p in mods)
    found = {p.name: flag_trajectory_render_calls(p.read_text(encoding="utf-8")) for p in mods}
    assert {k: v for k, v in found.items() if v} == {}


def test_render_gate_catches_trajectory_cols_snippet():
    assert flag_trajectory_render_calls(
        "        traj_block = render_table(TRAJECTORY_COLS, rows)\n"
    ) == ["traj_block = render_table(TRAJECTORY_COLS, rows)"]


def test_render_gate_catches_header_rows_snippet():
    snippet = "        return render_table(header, rows)[:2]\n"
    assert flag_trajectory_render_calls(snippet) == ["return render_table(header, rows)[:2]"]
    # ...and the allowed Latest-pass call and the definition are not flagged:
    assert flag_trajectory_render_calls(
        "new = render_table(LATEST_COLS, [])\ndef render_table(headers, rows):\n") == []
