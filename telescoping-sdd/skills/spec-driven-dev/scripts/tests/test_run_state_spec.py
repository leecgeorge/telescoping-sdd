"""SDD-tier CLI tests for `validate_spec.py --run-state` (C2).

Per the design's Testing Strategy (G): every failure-injection CLI test runs
IN-PROCESS (monkeypatch cannot cross a subprocess boundary) by calling
`vs._handle_run_state` / `vs.main` with `sys.argv` patched. The ONE real
subprocess is the flagship byte-level read-only proof, which needs a real
interpreter exit so the shared `atexit sweep_sdd_cruft` actually fires and
read-only is proven end-to-end including the sweep interaction ([DEF-02], R5).
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
_SDD_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "skills" / "spec-driven-dev" / "scripts"
_VS_PATH = _SDD_SCRIPTS / "validate_spec.py"


def _load_validate_spec():
    for p in (_SHARED_SCRIPTS, _SDD_SCRIPTS):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    if "validate_spec" in sys.modules:
        return importlib.reload(sys.modules["validate_spec"])
    return importlib.import_module("validate_spec")


def _load_content_hash():
    if str(_SHARED_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SHARED_SCRIPTS))
    return importlib.import_module("content_hash")


def _load_snapshot():
    if str(_SHARED_TESTS) not in sys.path:
        sys.path.insert(0, str(_SHARED_TESTS))
    return importlib.import_module("run_state_snapshot")


vs = _load_validate_spec()
ch = _load_content_hash()
snap = _load_snapshot()

_ARCH_JSON = '{"schemaVersion": 1, "language": "python", "source": "user"}\n'


# --- fixture builders -------------------------------------------------------


def _doc(*, body="Do a thing.", checked, hash_val, basis, with_traj=False):
    s = f"# Doc\n\n## Objective\n\n{body}\n\n"
    if with_traj:
        s += (
            "## Panel Review\n\n### Trajectory\n\n"
            "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
            "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
            "| 1 | 2026-07-04 | 0 | 0 | 0 | 0 | 0 | — |\n\n"
        )
    s += "## Approval\n\n"
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


def _sdd_dir(root: Path) -> Path:
    d = Path(root) / "specs" / "feature"
    d.mkdir(parents=True)
    return d


def _write_marker(root: Path, payload):
    sdd = Path(root) / ".sdd"
    sdd.mkdir(exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (sdd / "pending-review.json").write_text(text, encoding="utf-8")


def _open_marker(doc_rel="specs/feature/spec.md"):
    return {
        "schemaVersion": 1,
        "pending": {
            doc_rel: {"hash": "0123456789abcdef", "stamped_at": "2026-07-04T00:00:00Z", "stamped_at_pass": 1}
        },
    }


def _args(output="text"):
    return argparse.Namespace(output=output)


def _run_vs(*args):
    return subprocess.run([sys.executable, str(_VS_PATH), *args], capture_output=True, text=True)


# --- in-process handler tests -----------------------------------------------


def test_run_state_output_categories_present(tmp_path, capsys):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    _write_stale_v2(spec_dir / "design.md")
    _write_marker(tmp_path, _open_marker("specs/feature/design.md"))
    rc = vs._handle_run_state(_args(), spec_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "current phase" in out.lower()
    assert "design.md" in out
    assert "STALE" in out
    assert "obligations" in out


@pytest.mark.parametrize(
    "extra",
    [
        ["--approve", "spec"],
        ["--set-language", "python"],
        ["--completion-gate"],
        ["--restore-anchor"],
        ["--decline-pending"],
    ],
)
def test_run_state_mutual_exclusion_all_sdd_mode_flags_exit2(tmp_path, monkeypatch, extra):
    spec_dir = _sdd_dir(tmp_path)
    (spec_dir / "spec.md").write_text("# x\n", encoding="utf-8")
    argv = ["validate_spec.py", str(spec_dir), "--run-state", *extra]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        vs.main()
    assert exc.value.code == 2


def test_run_state_corrupt_marker_layer1_exit0_with_next_action(tmp_path, capsys):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    _write_marker(tmp_path, "{ fuzzed garbage bytes, not json")
    rc = vs._handle_run_state(_args(), spec_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "marker-unreadable" in out
    assert "pending-review.json" in out  # the next-action text, not just the label


def test_run_state_layer2_backstop_and_broken_pipe_exit0_no_sentinel(tmp_path, capsys, monkeypatch):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    sentinel = "ZZZ_SENTINEL_TOKEN_9137"

    def _raise(**kwargs):
        raise ValueError(sentinel)

    # Part A: an UNMAPPED exception inside derive → the Layer-2 backstop fires,
    # returns 0, and NO exception-derived text (the sentinel) reaches stdout.
    monkeypatch.setattr(vs, "derive_run_state", _raise)
    rc = vs._handle_run_state(_args(), spec_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert sentinel not in out
    assert "run-state:" in out  # hardcoded backstop line present

    # Part B (compound, E): stdout raises BrokenPipeError on EVERY write, so the
    # single case covers BOTH the primary print AND the Layer-2 fallback print.
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
    rc = vs._handle_run_state(_args(), spec_dir, tmp_path)
    assert rc == 0


def test_run_state_ambiguity_exit0_phase_header_ambiguous(tmp_path, capsys):
    spec_dir = _sdd_dir(tmp_path)
    # A real mixed bare + NN_-prefixed dir → resolve_artifact raises
    # ArtifactAmbiguityError → caught → exists=False, DEGRADED.
    (spec_dir / "spec.md").write_text(_doc(checked=False, hash_val="pending", basis=None), encoding="utf-8")
    (spec_dir / "01_spec.md").write_text(_doc(checked=False, hash_val="pending", basis=None), encoding="utf-8")
    rc = vs._handle_run_state(_args(), spec_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    header = out.splitlines()[0]
    assert "(ambiguous)" in header
    assert "(not started)" not in header  # header agrees with the degraded obligation
    assert "degraded-read" in out


def test_run_state_multi_signal_stacking_non_implement(tmp_path, capsys, monkeypatch):
    spec_dir = _sdd_dir(tmp_path)
    _write_stale_v2(spec_dir / "spec.md")           # approved but STALE
    _write_matches_v2(spec_dir / "design.md")       # forced DEGRADED below
    _write_marker(tmp_path, _open_marker("specs/feature/design.md"))
    orig = pathlib.Path.read_text

    def boom(self, *a, **k):
        if self.name == "design.md":
            raise PermissionError("denied")
        return orig(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", boom)
    rc = vs._handle_run_state(_args(), spec_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Design (degraded)" in out          # phase pinned before Implement
    assert "STALE" in out                       # spec stale line
    assert "degraded-read" in out               # integrity obligation
    assert "pending-review" in out              # marker obligation
    assert "task-tick ticks" not in out         # no tick_hint at a non-Implement phase


def test_run_state_mid_phase4_tick_hint_and_marker(tmp_path, capsys):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    _write_matches_v2(spec_dir / "design.md")
    _write_stale_v2(spec_dir / "tasks.md")
    _write_marker(tmp_path, _open_marker("specs/feature/tasks.md"))
    rc = vs._handle_run_state(_args(), spec_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Implement" in out
    assert "task-tick ticks" in out
    assert "pending-review" in out


def test_run_state_degraded_read_exit0_with_next_action(tmp_path, capsys, monkeypatch):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    orig = pathlib.Path.read_text

    def boom(self, *a, **k):
        if self.name == "spec.md":
            raise PermissionError("denied")
        return orig(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", boom)
    rc = vs._handle_run_state(_args(), spec_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    # Match the OBLIGATION line ("  - degraded-read: …"), not the artifact line
    # (which also references the degraded-read obligation).
    line = next(l for l in out.splitlines() if "- degraded-read:" in l)
    assert "→" in line and line.split("→", 1)[1].strip()  # non-trivial next-action


def test_run_state_output_json_notice_still_text_exit0(tmp_path, capsys):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    rc = vs._handle_run_state(_args(output="json"), spec_dir, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "text only" in out       # the AD9/Q1 notice
    assert "current phase" in out.lower()  # text still emitted


def test_run_state_in_process_no_write_complement(tmp_path):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    _write_stale_v2(spec_dir / "design.md")
    _write_marker(tmp_path, _open_marker("specs/feature/design.md"))
    snap.assert_no_stray_cruft(tmp_path)
    before = snap.snapshot_tree(tmp_path)
    rc = vs._handle_run_state(_args(), spec_dir, tmp_path)
    assert rc == 0
    # The helper's OWN path writes nothing (no atexit sweep in play in-process).
    assert snap.snapshot_tree(tmp_path) == before


# --- flagship byte-level read-only proof (real subprocess) ------------------


def test_run_state_byte_level_readonly_subprocess(tmp_path):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    _write_stale_v2(spec_dir / "design.md")
    _write_marker(tmp_path, _open_marker("specs/feature/design.md"))
    (tmp_path / ".sdd" / "architecture.json").write_text(_ARCH_JSON, encoding="utf-8")

    snap.assert_no_stray_cruft(tmp_path)
    before = snap.snapshot_tree(tmp_path)
    cp = _run_vs(str(spec_dir), "--run-state", "--project-root", str(tmp_path))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    # Every workflow-state file is byte-for-byte unchanged after a REAL subprocess
    # (atexit sweep fired), and no stray cruft was left behind.
    assert snap.snapshot_tree(tmp_path) == before
    snap.assert_no_stray_cruft(tmp_path)

    # A subsequent --approve behaves identically to a control run that never ran
    # --run-state: build two identical fresh dirs, run --run-state on only one,
    # then --approve both, and assert the approved artifact is byte-identical.
    # Standalone dir name "feature" + a `n/a` PLAN identifier so the spec-dir
    # cross-check passes; --force stamps despite other structural FAILs.
    approvable = (
        "# Doc\n\n**PLAN feature identifier:** `n/a`\n\n## Objective\n\nx\n\n"
        "## Approval\n\n- [ ] Approved to proceed\n- **Content Hash:** `pending`\n"
    )

    def _fresh(root):
        root.mkdir()
        d = root / "specs" / "feature"
        d.mkdir(parents=True)
        (d / "spec.md").write_text(approvable, encoding="utf-8")
        return d

    a_root = tmp_path / "a"
    b_root = tmp_path / "b"
    a_dir = _fresh(a_root)
    b_dir = _fresh(b_root)
    _run_vs(str(a_dir), "--run-state", "--project-root", str(a_root))  # only A sees --run-state
    ra = _run_vs(str(a_dir), "--approve", "spec", "--force", "--project-root", str(a_root))
    rb = _run_vs(str(b_dir), "--approve", "spec", "--force", "--project-root", str(b_root))
    assert ra.returncode == 0, ra.stdout + ra.stderr
    assert rb.returncode == 0, rb.stdout + rb.stderr
    assert (a_dir / "spec.md").read_bytes() == (b_dir / "spec.md").read_bytes()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
