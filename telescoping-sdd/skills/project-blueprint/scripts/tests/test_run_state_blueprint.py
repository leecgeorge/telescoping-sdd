"""Blueprint-tier CLI tests for `validate_blueprint.py --run-state` (C3).

A straight mirror of the SDD tier's CLI tests (test_run_state_spec.py): because
`_handle_run_state` is DUPLICATED per validator (only the run_state.py
derivation/format is shared), these tests MIRROR the SDD tier's coverage
granularity so copy-paste divergence between the two handlers is caught. Adds
the blueprint-only CFC-descope note as a checked contract. All failure-injection
tests run in-process; the ONE real subprocess is the byte-level read-only proof.
"""

from __future__ import annotations

import argparse
import importlib
import json
import pathlib
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SHARED_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"
_SHARED_TESTS = _SHARED_SCRIPTS / "tests"
_BP_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts"
_VB_PATH = _BP_SCRIPTS / "validate_blueprint.py"


def _load_validate_blueprint():
    for p in (_SHARED_SCRIPTS, _BP_SCRIPTS):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    if "validate_blueprint" in sys.modules:
        return importlib.reload(sys.modules["validate_blueprint"])
    return importlib.import_module("validate_blueprint")


def _load_content_hash():
    if str(_SHARED_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SHARED_SCRIPTS))
    return importlib.import_module("content_hash")


def _load_snapshot():
    if str(_SHARED_TESTS) not in sys.path:
        sys.path.insert(0, str(_SHARED_TESTS))
    return importlib.import_module("run_state_snapshot")


vb = _load_validate_blueprint()
ch = _load_content_hash()
snap = _load_snapshot()

_ARCH_JSON = '{"schemaVersion": 1, "language": "python", "source": "user"}\n'


# --- fixture builders -------------------------------------------------------


def _doc(*, body="Do a thing.", checked, hash_val, basis):
    s = f"# Doc\n\n## Objective\n\n{body}\n\n## Approval\n\n"
    box = "[x]" if checked else "[ ]"
    s += f"- {box} Approved to proceed\n- **Content Hash:** `{hash_val}`\n"
    if basis is not None:
        s += f"- **Hash basis:** {basis}\n"
    return s


def _write_matches_v2(path: Path, body="Do a thing."):
    content = _doc(body=body, checked=True, hash_val="pending", basis="v2")
    h = ch.compute_content_hash(content)
    path.write_text(content.replace("`pending`", f"`{h}`"), encoding="utf-8")
    return h


def _write_stale_v2(path: Path, body="Do a thing."):
    _write_matches_v2(path, body=body)
    content = path.read_text(encoding="utf-8")
    path.write_text(content + "\n\nExtra substantive prose that drifts the hash.\n", encoding="utf-8")


def _bp_dir(root: Path) -> Path:
    d = Path(root) / "blueprint"
    d.mkdir(parents=True)
    return d


def _write_marker(root: Path, payload):
    sdd = Path(root) / ".sdd"
    sdd.mkdir(exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (sdd / "pending-review.json").write_text(text, encoding="utf-8")


def _open_marker(doc_rel="blueprint/SCOPE.md"):
    return {
        "schemaVersion": 1,
        "pending": {
            doc_rel: {"hash": "0123456789abcdef", "stamped_at": "2026-07-04T00:00:00Z", "stamped_at_pass": 1}
        },
    }


def _args(output="text"):
    return argparse.Namespace(output=output)


def _run_vb(*args):
    return subprocess.run([sys.executable, str(_VB_PATH), *args], capture_output=True, text=True)


# --- in-process handler tests -----------------------------------------------


def test_run_state_output_categories_present(tmp_path, capsys):
    bp_dir = _bp_dir(tmp_path)
    _write_matches_v2(bp_dir / "SCOPE.md")
    _write_stale_v2(bp_dir / "ARCHITECTURE.md")
    _write_marker(tmp_path, _open_marker("blueprint/ARCHITECTURE.md"))
    rc = vb._handle_run_state(_args(), bp_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "current phase" in out.lower()
    assert "ARCHITECTURE.md" in out
    assert "STALE" in out
    assert "obligations" in out


def test_run_state_all_clear_contains_cfc_note(tmp_path, capsys):
    bp_dir = _bp_dir(tmp_path)
    _write_matches_v2(bp_dir / "SCOPE.md")
    _write_matches_v2(bp_dir / "ARCHITECTURE.md")
    _write_matches_v2(bp_dir / "PLAN.md")
    rc = vb._handle_run_state(_args(), bp_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "all clear" in out.lower()
    # The documented CFC-descope boundary is a checked contract, not just prose.
    assert "CFC" in out and "full validator" in out


def test_run_state_mutual_exclusion_with_approve_exit2(tmp_path, monkeypatch):
    bp_dir = _bp_dir(tmp_path)
    (bp_dir / "SCOPE.md").write_text("# x\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["validate_blueprint.py", str(bp_dir), "--run-state", "--approve", "scope"])
    with pytest.raises(SystemExit) as exc:
        vb.main()
    assert exc.value.code == 2


def test_run_state_mutual_exclusion_with_write_arch_config_exit2(tmp_path, monkeypatch):
    bp_dir = _bp_dir(tmp_path)
    (bp_dir / "SCOPE.md").write_text("# x\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["validate_blueprint.py", str(bp_dir), "--run-state", "--write-arch-config"])
    with pytest.raises(SystemExit) as exc:
        vb.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("extra", [["--decline-pending"], ["--restore-anchor"]])
def test_run_state_mutual_exclusion_other_mode_flags_exit2(tmp_path, monkeypatch, extra):
    bp_dir = _bp_dir(tmp_path)
    (bp_dir / "SCOPE.md").write_text("# x\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["validate_blueprint.py", str(bp_dir), "--run-state", *extra])
    with pytest.raises(SystemExit) as exc:
        vb.main()
    assert exc.value.code == 2


def test_run_state_corrupt_marker_exit0_with_next_action(tmp_path, capsys):
    bp_dir = _bp_dir(tmp_path)
    _write_matches_v2(bp_dir / "SCOPE.md")
    _write_marker(tmp_path, "{ fuzzed garbage bytes, not json")
    rc = vb._handle_run_state(_args(), bp_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "marker-unreadable" in out
    assert "pending-review.json" in out


def test_run_state_layer2_backstop_and_broken_pipe_exit0_no_sentinel(tmp_path, capsys, monkeypatch):
    bp_dir = _bp_dir(tmp_path)
    _write_matches_v2(bp_dir / "SCOPE.md")
    sentinel = "ZZZ_SENTINEL_TOKEN_4471"

    def _raise(**kwargs):
        raise ValueError(sentinel)

    monkeypatch.setattr(vb, "derive_run_state", _raise)
    rc = vb._handle_run_state(_args(), bp_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert sentinel not in out
    assert "run-state:" in out

    class _BrokenStdout:
        def write(self, *a, **k):
            raise BrokenPipeError()

        def flush(self, *a, **k):
            raise BrokenPipeError()

        def fileno(self):
            return 1

        def close(self):
            pass

    monkeypatch.setattr(sys, "stdout", _BrokenStdout())
    rc = vb._handle_run_state(_args(), bp_dir, tmp_path)
    assert rc == 0


def test_run_state_output_json_notice_still_text_exit0(tmp_path, capsys):
    bp_dir = _bp_dir(tmp_path)
    _write_matches_v2(bp_dir / "SCOPE.md")
    rc = vb._handle_run_state(_args(output="json"), bp_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "text only" in out
    assert "current phase" in out.lower()


def test_run_state_ambiguity_exit0_phase_header_ambiguous(tmp_path, capsys):
    bp_dir = _bp_dir(tmp_path)
    (bp_dir / "SCOPE.md").write_text(_doc(checked=False, hash_val="pending", basis=None), encoding="utf-8")
    (bp_dir / "01_SCOPE.md").write_text(_doc(checked=False, hash_val="pending", basis=None), encoding="utf-8")
    rc = vb._handle_run_state(_args(), bp_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    header = out.splitlines()[0]
    assert "(ambiguous)" in header
    assert "(not started)" not in header
    assert "degraded-read" in out


def test_run_state_multi_signal_stacking_non_implement(tmp_path, capsys, monkeypatch):
    bp_dir = _bp_dir(tmp_path)
    _write_stale_v2(bp_dir / "SCOPE.md")            # approved but STALE
    _write_matches_v2(bp_dir / "ARCHITECTURE.md")   # forced DEGRADED below
    _write_marker(tmp_path, _open_marker("blueprint/ARCHITECTURE.md"))
    orig = pathlib.Path.read_text

    def boom(self, *a, **k):
        if self.name == "ARCHITECTURE.md":
            raise PermissionError("denied")
        return orig(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", boom)
    rc = vb._handle_run_state(_args(), bp_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Architecture (degraded)" in out
    assert "STALE" in out
    assert "degraded-read" in out
    assert "pending-review" in out
    assert "task-tick ticks" not in out  # blueprint never sets tick_hint


def test_run_state_degraded_read_exit0_with_next_action(tmp_path, capsys, monkeypatch):
    bp_dir = _bp_dir(tmp_path)
    _write_matches_v2(bp_dir / "SCOPE.md")
    orig = pathlib.Path.read_text

    def boom(self, *a, **k):
        if self.name == "SCOPE.md":
            raise PermissionError("denied")
        return orig(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", boom)
    rc = vb._handle_run_state(_args(), bp_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "- degraded-read:" in l)
    assert "→" in line and line.split("→", 1)[1].strip()


def test_run_state_in_process_no_write_complement(tmp_path):
    bp_dir = _bp_dir(tmp_path)
    _write_matches_v2(bp_dir / "SCOPE.md")
    _write_stale_v2(bp_dir / "ARCHITECTURE.md")
    _write_marker(tmp_path, _open_marker("blueprint/ARCHITECTURE.md"))
    snap.assert_no_stray_cruft(tmp_path)
    before = snap.snapshot_tree(tmp_path)
    rc = vb._handle_run_state(_args(), bp_dir, tmp_path)
    assert rc == 0
    assert snap.snapshot_tree(tmp_path) == before


# --- flagship byte-level read-only proof (real subprocess) ------------------


def test_run_state_byte_level_readonly_subprocess(tmp_path):
    bp_dir = _bp_dir(tmp_path)
    _write_matches_v2(bp_dir / "SCOPE.md")
    _write_stale_v2(bp_dir / "ARCHITECTURE.md")
    _write_marker(tmp_path, _open_marker("blueprint/ARCHITECTURE.md"))
    (tmp_path / ".sdd" / "architecture.json").write_text(_ARCH_JSON, encoding="utf-8")

    snap.assert_no_stray_cruft(tmp_path)
    before = snap.snapshot_tree(tmp_path)
    cp = _run_vb(str(bp_dir), "--run-state", "--project-root", str(tmp_path))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert snap.snapshot_tree(tmp_path) == before
    snap.assert_no_stray_cruft(tmp_path)

    # A subsequent --approve behaves identically to a control run that never ran
    # --run-state.
    def _fresh(root):
        root.mkdir()
        d = root / "blueprint"
        d.mkdir(parents=True)
        (d / "SCOPE.md").write_text(_doc(checked=False, hash_val="pending", basis=None), encoding="utf-8")
        return d

    a_root = tmp_path / "a"
    b_root = tmp_path / "b"
    a_dir = _fresh(a_root)
    b_dir = _fresh(b_root)
    _run_vb(str(a_dir), "--run-state", "--project-root", str(a_root))
    ra = _run_vb(str(a_dir), "--approve", "scope", "--force", "--project-root", str(a_root))
    rb = _run_vb(str(b_dir), "--approve", "scope", "--force", "--project-root", str(b_root))
    assert ra.returncode == 0, ra.stdout + ra.stderr
    assert rb.returncode == 0, rb.stdout + rb.stderr
    assert (a_dir / "SCOPE.md").read_bytes() == (b_dir / "SCOPE.md").read_bytes()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
