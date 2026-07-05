"""Tests for best-effort `.sdd/` cruft cleanup (WORKING-NOTES Item 2).

Covers `sweep_sdd_cruft(marker_root)` in `pending_review.py`: the unified
non-blocking LOCK_EX|LOCK_NB gate that sweeps orphaned `*.tmp` atomic-write
temps and reclaims `pending-review.lock` in one held critical section, plus the
no-lock-platform unconditional branch and the safety-critical sweep-before-unlink
source ordering (Risk-1b).

T1 writes T-1..T-9, T-12, T-13, T-15, T-16 (the red phase — they error on the
absent `sweep_sdd_cruft` until T2 implements it). T3 appends the CLI subprocess
scenarios (T-10a/b/c, T-11a/c) and the T-14 validator-source check.

All scenarios are sandboxed to `tmp_path`; the real-repo `.sdd/` is never
touched. T-4/T-5 use a long-lived `Popen` child with a ready/release sentinel
handshake and `pytest.skip` when `fcntl` is unavailable.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Load order matters: blueprint_common must initialize before pending_review
# (pending_review imports primitives from it; blueprint_common re-exports the
# marker names from pending_review at its bottom). See pending_review.py header.
import blueprint_common  # noqa: E402,F401
import pending_review  # noqa: E402


# --------------------------------------------------------------------------
# Shared fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture
def sdd_dir(tmp_path):
    """Create `tmp_path/.sdd/` and return it; pre-places no non-cruft files."""
    d = tmp_path / ".sdd"
    d.mkdir()
    return d


def _wait_for(path: Path, timeout: float = 5.0) -> bool:
    """Poll until `path` exists or `timeout` elapses; return whether it appeared."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.01)
    return False


def _lock_path(sdd_dir: Path) -> Path:
    return sdd_dir / "pending-review.lock"


# --------------------------------------------------------------------------
# T-1 .. T-3: core sweep / reclaim / no-op
# --------------------------------------------------------------------------


def test_sweep_removes_orphan_tmp(sdd_dir, tmp_path):
    """T-1: orphaned `*.tmp` files are swept when the lock is free (R1 AC1)."""
    (sdd_dir / "tmpAAAA.tmp").write_text("a", encoding="utf-8")
    (sdd_dir / "tmpBBBB.tmp").write_text("b", encoding="utf-8")
    pending_review.sweep_sdd_cruft(tmp_path)
    assert not (sdd_dir / "tmpAAAA.tmp").exists()
    assert not (sdd_dir / "tmpBBBB.tmp").exists()


def test_lock_reclaimed_when_free(sdd_dir, tmp_path):
    """T-2: `pending-review.lock` is removed when uncontested (R2 AC1)."""
    _lock_path(sdd_dir).write_text("", encoding="utf-8")
    pending_review.sweep_sdd_cruft(tmp_path)
    assert not _lock_path(sdd_dir).exists()


def test_no_op_when_no_tmp_files(sdd_dir, tmp_path):
    """T-3: no `*.tmp` present -> no exception, intentional files untouched (R1 AC3).

    Also records R2 AC3 coverage: no `pending-review.lock` existed before the
    call, and none is left behind after (the locking-platform path may create it
    transiently to probe, but reclaims it in the same critical section)."""
    arch = sdd_dir / "architecture.json"
    arch.write_text('{"language": "python"}\n', encoding="utf-8")
    before = arch.read_bytes()
    assert not _lock_path(sdd_dir).exists()  # R2 AC3 precondition
    pending_review.sweep_sdd_cruft(tmp_path)  # must not raise
    assert arch.read_bytes() == before
    assert not _lock_path(sdd_dir).exists()  # R2 AC3: none left behind


# --------------------------------------------------------------------------
# T-4 / T-5: contention — cleanup skips while a peer holds the lock
# --------------------------------------------------------------------------


def test_lock_held_tmp_and_lock_survive(sdd_dir, tmp_path):
    """T-4: while a peer holds an exclusive lock, both `*.tmp` and the lock
    survive — cleanup's NB acquire fails and it skips both ops (R1 AC2, R2 AC2)."""
    if pending_review._fcntl is None:  # pragma: no cover - non-POSIX
        pytest.skip("fcntl unavailable")
    lock_path = _lock_path(sdd_dir)
    ready = tmp_path / "ready.sentinel"
    release = tmp_path / "release.sentinel"
    child_src = (
        "import fcntl, os, time\n"
        f"f = open({str(lock_path)!r}, 'a+')\n"
        "fcntl.flock(f.fileno(), fcntl.LOCK_EX)\n"
        f"open({str(ready)!r}, 'w').write('ready')\n"
        "deadline = time.time() + 30\n"
        f"while not os.path.exists({str(release)!r}) and time.time() < deadline:\n"
        "    time.sleep(0.01)\n"
        "fcntl.flock(f.fileno(), fcntl.LOCK_UN)\n"
        "f.close()\n"
    )
    child = subprocess.Popen([sys.executable, "-c", child_src])
    try:
        assert _wait_for(ready, 5), "child never acquired the lock / signaled ready"
        tmp_file = sdd_dir / "tmpHELD.tmp"
        tmp_file.write_text("x", encoding="utf-8")
        pending_review.sweep_sdd_cruft(tmp_path)
        # Under contention the NB acquire fails -> BOTH ops skipped.
        assert tmp_file.exists(), "sweep deleted a .tmp while a peer held the lock"
        assert lock_path.exists(), "sweep unlinked the lock while a peer held it"
    finally:
        release.write_text("go", encoding="utf-8")
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            child.kill()
            child.wait()


def test_concurrent_writer_obligation_not_dropped(sdd_dir, tmp_path):
    """T-5: a real in-flight `write_pending_review` (lock held + staged temp) is
    not disturbed by cleanup; the obligation lands once the writer completes
    (R1 AC2). The positive 'still present at the instant cleanup returns' assert
    is mandatory — without it the test passes vacuously via writer-finished-first."""
    if pending_review._fcntl is None:  # pragma: no cover - non-POSIX
        pytest.skip("fcntl unavailable")
    ready = tmp_path / "ready.sentinel"
    release = tmp_path / "release.sentinel"
    marker = pending_review._marker_path(tmp_path)
    child_src = (
        "import json, os, sys, tempfile, time\n"
        f"sys.path.insert(0, {str(_SCRIPTS)!r})\n"
        "import blueprint_common  # load order: must precede pending_review\n"
        "import pending_review as pr\n"
        "from pathlib import Path\n"
        f"root = Path({str(tmp_path)!r})\n"
        "with pr._marker_lock(root):\n"
        "    path = pr._marker_path(root)\n"
        "    path.parent.mkdir(parents=True, exist_ok=True)\n"
        "    data = pr._empty_marker()\n"
        "    data['pending']['specs/x/spec.md'] = "
        "{'hash': '0123456789abcdef', 'stamped_at': 't', 'stamped_at_pass': 1}\n"
        "    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix='.tmp')\n"
        "    with os.fdopen(fd, 'w', encoding='utf-8') as fh:\n"
        "        json.dump(data, fh, indent=2)\n"
        "        fh.write(chr(10))\n"
        f"    open({str(ready)!r}, 'w').write('ready')\n"
        "    deadline = time.time() + 30\n"
        f"    while not os.path.exists({str(release)!r}) and time.time() < deadline:\n"
        "        time.sleep(0.01)\n"
        "    os.replace(tmp_name, path)\n"
    )
    child = subprocess.Popen([sys.executable, "-c", child_src])
    try:
        assert _wait_for(ready, 5), "child never staged the in-flight write"
        assert list(sdd_dir.glob("*.tmp")), "child did not stage an in-flight .tmp"
        pending_review.sweep_sdd_cruft(tmp_path)
        # MANDATORY positive assertion BEFORE release: the in-flight temp must
        # survive, proving cleanup skipped under genuine contention.
        assert list(sdd_dir.glob("*.tmp")), (
            "sweep deleted a concurrent writer's in-flight temp (obligation drop!)"
        )
    finally:
        release.write_text("go", encoding="utf-8")
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            child.kill()
            child.wait()
    # After release the writer completed its os.replace -> obligation persisted.
    assert marker.exists(), "child did not complete its write_pending_review"
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert "specs/x/spec.md" in data["pending"], "obligation was dropped"


# --------------------------------------------------------------------------
# T-6 / T-7: intentional files are never touched (R3)
# --------------------------------------------------------------------------


def test_non_cruft_arch_json_untouched(sdd_dir, tmp_path):
    """T-6: `architecture.json` is byte-identical while a co-present `*.tmp` is
    swept (R3 AC1 — mixed cruft + intentional file in one pass)."""
    arch = sdd_dir / "architecture.json"
    arch.write_text('{"language": "java", "source": "blueprint"}\n', encoding="utf-8")
    before = arch.read_bytes()
    (sdd_dir / "tmpZZZZ.tmp").write_text("junk", encoding="utf-8")
    pending_review.sweep_sdd_cruft(tmp_path)
    assert arch.read_bytes() == before
    assert not (sdd_dir / "tmpZZZZ.tmp").exists()


def test_non_cruft_pending_review_json_untouched(sdd_dir, tmp_path):
    """T-7: `pending-review.json` is byte-identical while a co-present `*.tmp` is
    swept (R3 AC2)."""
    marker = sdd_dir / "pending-review.json"
    marker.write_text('{"schemaVersion": 1, "pending": {}}\n', encoding="utf-8")
    before = marker.read_bytes()
    (sdd_dir / "tmpYYYY.tmp").write_text("junk", encoding="utf-8")
    pending_review.sweep_sdd_cruft(tmp_path)
    assert marker.read_bytes() == before
    assert not (sdd_dir / "tmpYYYY.tmp").exists()


# --------------------------------------------------------------------------
# T-8 / T-9: best-effort — never raise, never mkdir
# --------------------------------------------------------------------------


def test_absent_sdd_no_exception(tmp_path):
    """T-8: no `.sdd/` present -> no exception, and `.sdd/` is NOT created (the
    helper must never `mkdir`) (R4 AC1)."""
    assert not (tmp_path / ".sdd").exists()
    pending_review.sweep_sdd_cruft(tmp_path)  # must not raise
    assert not (tmp_path / ".sdd").exists(), "sweep must not create .sdd/"


def test_unwritable_sdd_no_exception(sdd_dir, tmp_path, monkeypatch):
    """T-9: an unlink that raises `OSError` is swallowed; no exception reaches the
    caller (R4 AC2; satisfies spec [DEF-02]). Monkeypatches `Path.unlink` — the
    exact symbol the impl calls — NOT `os.unlink`."""
    (sdd_dir / "tmpQQQQ.tmp").write_text("x", encoding="utf-8")

    def _boom(self, *a, **k):
        raise OSError("simulated unwritable .sdd/")

    monkeypatch.setattr(Path, "unlink", _boom)
    pending_review.sweep_sdd_cruft(tmp_path)  # must not raise


# --------------------------------------------------------------------------
# T-12 / T-13: glob scope + partial-failure resilience
# --------------------------------------------------------------------------


def test_negative_glob_near_miss_filenames(sdd_dir, tmp_path):
    """T-12: near-miss names are NOT swept — only direct-child files whose suffix
    is exactly `.tmp` are removed (R1 scope, Risk R4)."""
    (sdd_dir / "notes.tmp.bak").write_text("a", encoding="utf-8")
    (sdd_dir / "keep.tmpx").write_text("b", encoding="utf-8")
    (sdd_dir / "x.tmp").mkdir()  # a directory named *.tmp — unlink can't remove it
    pending_review.sweep_sdd_cruft(tmp_path)
    assert (sdd_dir / "notes.tmp.bak").exists()
    assert (sdd_dir / "keep.tmpx").exists()
    assert (sdd_dir / "x.tmp").is_dir()


def test_partial_failure_single_unlink_does_not_stop_others(sdd_dir, tmp_path, monkeypatch):
    """T-13: a single failed unlink does not abort the rest — exactly one of two
    `*.tmp` survives (count-based; glob order is unspecified) and no exception
    propagates (R4 inner swallow)."""
    (sdd_dir / "tmp0001.tmp").write_text("a", encoding="utf-8")
    (sdd_dir / "tmp0002.tmp").write_text("b", encoding="utf-8")
    real_unlink = Path.unlink
    state = {"n": 0}

    def _flaky(self, *a, **k):
        state["n"] += 1
        if state["n"] == 1:
            raise OSError("first unlink fails")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", _flaky)
    pending_review.sweep_sdd_cruft(tmp_path)  # must not raise
    assert len(list(sdd_dir.glob("*.tmp"))) == 1


# --------------------------------------------------------------------------
# T-15: no-lock-platform unconditional branch (AD3)
# --------------------------------------------------------------------------


def test_no_lock_platform_unconditional_sweep(sdd_dir, tmp_path, monkeypatch):
    """T-15: with neither `fcntl` nor `msvcrt`, both ops run unconditionally —
    `*.tmp` and `pending-review.lock` are removed, no exception (AD3; R1, R2)."""
    monkeypatch.setattr(pending_review, "_fcntl", None)
    monkeypatch.setattr(pending_review, "_msvcrt", None)
    (sdd_dir / "tmpNOLK.tmp").write_text("x", encoding="utf-8")
    _lock_path(sdd_dir).write_text("", encoding="utf-8")
    pending_review.sweep_sdd_cruft(tmp_path)  # must not raise
    assert not (sdd_dir / "tmpNOLK.tmp").exists()
    assert not _lock_path(sdd_dir).exists()


# --------------------------------------------------------------------------
# T-16: sweep-before-unlink source-order guard (Risk-1b)
# --------------------------------------------------------------------------


def test_sweep_before_unlink_source_order():
    """T-16: executable guard for the safety-critical Risk-1b ordering. No
    behavioral test can reach it (single-process tests acquire cleanly; T-4/T-5
    skip the critical section), so this pins the SOURCE order: in BOTH branches
    (no-lock and locking) the `*.tmp` glob precedes `lock_path.unlink()`, and
    there are exactly two of each call site (a dropped/added branch fails loudly).

    Anchors on the actual call sites `.glob("*.tmp")` and `lock_path.unlink()`,
    NOT the bare `pending-review.lock` literal (it precedes the glob in the
    `with_name(...)` assignment) nor the load-bearing ordering comment (it names
    both tokens before the glob)."""
    src = inspect.getsource(pending_review.sweep_sdd_cruft)
    glob_token = '.glob("*.tmp")'
    unlink_token = "lock_path.unlink()"

    def _indices(hay: str, needle: str) -> list[int]:
        out, start = [], 0
        while True:
            i = hay.find(needle, start)
            if i == -1:
                return out
            out.append(i)
            start = i + len(needle)

    glob_idxs = _indices(src, glob_token)
    unlink_idxs = _indices(src, unlink_token)
    assert len(glob_idxs) == 2, f"expected exactly 2 `{glob_token}` call sites, got {len(glob_idxs)}"
    assert len(unlink_idxs) == 2, (
        f"expected exactly 2 `{unlink_token}` call sites, got {len(unlink_idxs)}"
    )

    # Split per-branch: the no-lock guard, then the no-lock branch's terminating
    # `return` separates the no-lock body from the locking body.
    guard = "if _fcntl is None and _msvcrt is None:"
    assert guard in src, "no-lock guard not found — branch structure changed"
    after_guard = src.split(guard, 1)[1]
    nolock_seg, locking_seg = after_guard.split("return", 1)
    for name, seg in (("no-lock", nolock_seg), ("locking", locking_seg)):
        g = seg.find(glob_token)
        u = seg.find(unlink_token)
        assert g != -1, f"{name} branch is missing the `*.tmp` glob"
        assert u != -1, f"{name} branch is missing `lock_path.unlink()`"
        assert g < u, (
            f"{name} branch must sweep `*.tmp` BEFORE unlinking the lock "
            f"(reversing reopens Risk-1b obligation-drop)"
        )


# ==========================================================================
# T3: CLI subprocess integration (T-10a/b/c, T-11a/c) + validator-source check
# (T-14). Added once the validator wiring (atexit.register) exists.
#
# Each CLI test passes `--project-root <tmp_path>` (short-circuiting the
# resolver walk-up so the swept `.sdd/` is provably the one holding the orphan),
# plants the orphan in exactly `<tmp_path>/.sdd/`, and asserts it is PRESENT
# immediately before `subprocess.run` (so "absent after" cannot pass vacuously
# on a failed plant) and ABSENT after the process exits.
# ==========================================================================

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

# Reuse the validator subprocess runners + the minimal (structurally-invalid)
# spec-dir builder from the re-approval-gate suite (sandbox discipline: explicit
# --project-root <tmp_path>), per tasks.md T3.
from test_reapproval_gate import (  # noqa: E402
    _minimal_spec_dir,
    _run_vb,
    _run_vs,
)

_VS_PATH = _SCRIPTS.parent / "skills" / "spec-driven-dev" / "scripts" / "validate_spec.py"
_VB_PATH = (
    _SCRIPTS.parent / "skills" / "project-blueprint" / "scripts" / "validate_blueprint.py"
)

# A structurally-COMPLETE standalone spec (all required sections + a non-empty
# Panel Review) so default validation exits 0 — `_minimal_spec_dir` is
# Objective-only and exits 1, so it cannot serve the exit-0 case.
_VALID_SPEC = (
    "# Feature: T\n\n"
    "**PLAN feature identifier:** `n/a`\n\n"
    "## Objective\n\nx\n\n"
    "## Requirements\n\nR1\n\n"
    "**Acceptance Criteria:**\n\n"
    "- GIVEN x\n  WHEN y\n  THEN z\n\n"
    "## Project Structure\n\nx\n\n"
    "## Boundaries\n\nx\n\n"
    "## Success Criteria\n\n- [ ] done\n\n"
    "## Panel Review\n\n"
    "### Trajectory\n\n"
    "| Pass | Date | Notes |\n|---|---|---|\n| 1 | 2026-06-26 | clean |\n"
)

_ARCH_WITH_TOKEN = (
    "# Architecture\n\n"
    "## Technology Choices\n\n"
    "**Architecture token:** `python`\n\n"
    "body\n"
)


def _plant_orphan(tmp_path: Path) -> Path:
    """Create `<tmp_path>/.sdd/` and plant an orphaned `*.tmp` in it; return it."""
    sdd = tmp_path / ".sdd"
    sdd.mkdir(parents=True, exist_ok=True)
    orphan = sdd / "tmpCLI0001.tmp"
    orphan.write_text("orphan", encoding="utf-8")
    return orphan


def _valid_spec_dir(root: Path) -> Path:
    d = Path(root) / "specs" / "cleanup-ok"
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(_VALID_SPEC, encoding="utf-8")
    return d


def test_validate_spec_exit0_cleanup_fires(tmp_path):
    """T-10a: a PASSING (valid, structurally-complete) spec exits 0 and the
    atexit hook still sweeps the orphaned `*.tmp` (R4 AC4, R5 AC1)."""
    spec_dir = _valid_spec_dir(tmp_path)
    orphan = _plant_orphan(tmp_path)
    assert orphan.exists()
    cp = _run_vs(str(spec_dir), "--project-root", str(tmp_path))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert not orphan.exists()


def test_validate_spec_exit1_cleanup_fires(tmp_path):
    """T-10b: a structurally-invalid spec FAILS validation (exit 1) and cleanup
    still fires — exit code unchanged, orphan swept (R4 AC3, R5 AC1).

    `_minimal_spec_dir` is Objective-only in a bound-form `F1-x` dir, so a
    structural/dir-identifier check FAILS -> `_run_validation` returns 1 (NOT a
    malformed dir, which would exit 2 at an arg guard before registration)."""
    spec_dir = _minimal_spec_dir(tmp_path)
    orphan = _plant_orphan(tmp_path)
    assert orphan.exists()
    cp = _run_vs(str(spec_dir), "--project-root", str(tmp_path))
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert not orphan.exists()


def test_validate_spec_set_language_cleanup_fires(tmp_path):
    """T-10c: the `--set-language` mode handler also triggers cleanup (R5 AC1
    mode-handler coverage)."""
    spec_dir = _minimal_spec_dir(tmp_path)
    orphan = _plant_orphan(tmp_path)
    assert orphan.exists()
    cp = _run_vs(
        str(spec_dir), "--set-language", "python", "--project-root", str(tmp_path)
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert not orphan.exists()


def test_validate_blueprint_exit0_cleanup_fires(tmp_path):
    """T-11a: the blueprint validator's default-validate path triggers cleanup
    (R5 AC2). Fixture reframe vs the task's "passing blueprint → exit 0": a
    passing blueprint needs the full approved SCOPE/ARCHITECTURE/PLAN triple
    (disproportionate brittleness for proving the hook fires), so this uses a
    minimal (SCOPE-only) blueprint and asserts `returncode in (0, 1)` — the
    binding AC (R5 AC2) holds for exit code 0 OR 1, and T-11c independently
    covers a clean exit-0 mode handler. (Test name preserved from tasks.md.)"""
    bp = tmp_path / "blueprint"
    bp.mkdir()
    (bp / "SCOPE.md").write_text("# Scope\n\nbody\n", encoding="utf-8")
    orphan = _plant_orphan(tmp_path)
    assert orphan.exists()
    cp = _run_vb(str(bp), "--project-root", str(tmp_path))
    assert cp.returncode in (0, 1), cp.stdout + cp.stderr
    assert not orphan.exists()


def test_validate_blueprint_write_arch_config_cleanup_fires(tmp_path):
    """T-11c: the `--write-arch-config` mode handler also triggers cleanup, and
    only the orphan `*.tmp` is swept — the architecture.json it writes is never
    touched (R5 AC2 mode-handler; R3)."""
    bp = tmp_path / "blueprint"
    bp.mkdir()
    (bp / "ARCHITECTURE.md").write_text(_ARCH_WITH_TOKEN, encoding="utf-8")
    orphan = _plant_orphan(tmp_path)
    assert orphan.exists()
    cp = _run_vb(str(bp), "--write-arch-config", "--project-root", str(tmp_path))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert not orphan.exists()
    assert (tmp_path / ".sdd" / "architecture.json").exists(), "arch-config must survive"


def _main_source(path: Path) -> str:
    """Return just the `def main(...)` body source (import-free, hermetic)."""
    src = path.read_text(encoding="utf-8")
    start = src.index("\ndef main(")
    end = src.index("\nif __name__", start)
    return src[start:end]


def test_registration_after_guards_uses_resolver():
    """T-14: SOURCE check pinning both AD1 decisions in each validator's `main()`:
    the `atexit.register(sweep_sdd_cruft, ...)` call (i) derives the root from
    `_resolve_marker_root_and_key` (NOT raw `arch_find_project_root` — the R2
    wrong-`.sdd/` mitigation) and (ii) appears AFTER the last arg-validation
    `sys.exit(2)`/`parser.error(...)` guard in `main()`."""
    for path in (_VS_PATH, _VB_PATH):
        main_src = _main_source(path)
        m = re.search(r"atexit\.register\(", main_src)
        assert m, f"atexit.register(...) not found in {path.name} main()"
        window = main_src[m.start() : m.start() + 250]
        assert "sweep_sdd_cruft" in window, f"{path.name}: register call lost sweep_sdd_cruft"
        # (i) correct resolver, not the raw walk-less one
        assert "_resolve_marker_root_and_key" in window, (
            f"{path.name}: registration must use _resolve_marker_root_and_key (AD1)"
        )
        assert "arch_find_project_root" not in window, (
            f"{path.name}: registration must NOT use raw arch_find_project_root (R2)"
        )
        # (ii) after the last arg-validation guard
        guard_idxs = [
            mm.start() for mm in re.finditer(r"sys\.exit\(2\)|parser\.error\(", main_src)
        ]
        assert guard_idxs, f"{path.name}: no arg-validation guard found in main()"
        assert m.start() > max(guard_idxs), (
            f"{path.name}: atexit.register must follow the last arg-validation guard"
        )


# --------------------------------------------------------------------------
# T3 (context-window-inflow-reduction): panel-findings cleanup pass —
# findings_scope-scoped, path-safety-guarded, staleness-guarded. NOT gated by
# the marker lock. See specs/context-window-inflow-reduction/{01_spec,02_design,
# 03_tasks}.md (design C6, I3, AD3, DR5, DEF-01, DEF-02; HIGH-2, MED-3).
# --------------------------------------------------------------------------


def _make_findings(sdd_dir: Path, scope: str, name: str, *, age_secs: float = 1000.0,
                   content: str = "## Machine findings\n- [HIGH] x — y\n") -> Path:
    """Create .sdd/panel-findings/<scope>/<name> aged `age_secs` in the past."""
    d = sdd_dir / "panel-findings"
    for part in scope.split("/"):
        d = d / part
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text(content, encoding="utf-8")
    old = time.time() - age_secs
    os.utime(f, (old, old))
    return f


def test_sweep_removes_only_scoped_findings(sdd_dir, tmp_path):
    """The run's own subtree *.md are removed and the leaf subdir rmdir'd."""
    f = _make_findings(sdd_dir, "sdd/feat-a", "spec-p1-critic.md")
    pending_review.sweep_sdd_cruft(tmp_path, findings_scope="sdd/feat-a")
    assert not f.exists()
    assert not (sdd_dir / "panel-findings" / "sdd" / "feat-a").exists()
    # The intermediate sdd/ parent is rmdir'd only if it too ends empty.
    assert not (sdd_dir / "panel-findings" / "sdd").exists()


def test_sweep_leaves_sibling_feature_findings_untouched(sdd_dir, tmp_path):
    """DR5: a sibling feature's subtree is never touched."""
    mine = _make_findings(sdd_dir, "sdd/feat-a", "spec-p1-critic.md")
    sib = _make_findings(sdd_dir, "sdd/feat-b", "spec-p1-critic.md")
    pending_review.sweep_sdd_cruft(tmp_path, findings_scope="sdd/feat-a")
    assert not mine.exists()
    assert sib.exists()
    # Sibling non-empty, so the shared sdd/ intermediate must survive.
    assert (sdd_dir / "panel-findings" / "sdd").is_dir()


def test_sweep_cross_tier_disjoint_sdd_blueprint_vs_blueprint(sdd_dir, tmp_path):
    """HIGH-2: an SDD feature literally slugged `blueprint` (grammar-permitted)
    lives at sdd/blueprint/ and never collides with the blueprint tier's
    panel-findings/blueprint/."""
    sdd_bp = _make_findings(sdd_dir, "sdd/blueprint", "spec-p1-critic.md")
    tier_bp = _make_findings(sdd_dir, "blueprint", "PLAN-p1-critic.md")
    pending_review.sweep_sdd_cruft(tmp_path, findings_scope="sdd/blueprint")
    assert not sdd_bp.exists()
    assert tier_bp.exists()  # the blueprint TIER subtree is untouched


def test_sweep_lexical_prefix_sibling_not_deleted(sdd_dir, tmp_path):
    """`sdd/foo` must not delete `sdd/foo-bar/` (path-JOIN, not string-prefix)."""
    mine = _make_findings(sdd_dir, "sdd/foo", "spec-p1-critic.md")
    prefix_sib = _make_findings(sdd_dir, "sdd/foo-bar", "spec-p1-critic.md")
    pending_review.sweep_sdd_cruft(tmp_path, findings_scope="sdd/foo")
    assert not mine.exists()
    assert prefix_sib.exists()


def test_sweep_skips_unsafe_findings_scope(sdd_dir, tmp_path):
    """MED-3: an absolute path, a `..` segment, or an empty component skips the
    panel-findings pass entirely (never widens/misdirects)."""
    f = _make_findings(sdd_dir, "sdd/foo", "spec-p1-critic.md")
    for unsafe in ("/sdd/foo", "sdd/../foo", "..", "sdd//foo", ""):
        pending_review.sweep_sdd_cruft(tmp_path, findings_scope=unsafe)
    assert f.exists(), "no unsafe scope may delete a real findings file"


def test_sweep_skips_recently_modified_file(sdd_dir, tmp_path):
    """Staleness guard: a file modified within the window is skipped (best-effort)."""
    recent = _make_findings(sdd_dir, "sdd/feat-a", "spec-p1-critic.md", age_secs=1.0)
    pending_review.sweep_sdd_cruft(tmp_path, findings_scope="sdd/feat-a")
    assert recent.exists()
    # Dir not rmdir'd because the recent file kept it non-empty.
    assert (sdd_dir / "panel-findings" / "sdd" / "feat-a").is_dir()


def test_sweep_early_returns_when_panel_findings_absent(sdd_dir, tmp_path):
    """DEF-02 safety: panel-findings/ absent (pre-feature repo) → clean early
    return; the *.tmp cleanup still runs."""
    (sdd_dir / "junkAAAA.tmp").write_text("j", encoding="utf-8")
    assert not (sdd_dir / "panel-findings").exists()
    pending_review.sweep_sdd_cruft(tmp_path, findings_scope="sdd/feat-a")  # no raise
    assert not (sdd_dir / "junkAAAA.tmp").exists()


def test_sweep_skips_panel_findings_when_scope_none(sdd_dir, tmp_path):
    """findings_scope=None (or absent) skips the panel-findings pass entirely."""
    f = _make_findings(sdd_dir, "sdd/feat-a", "spec-p1-critic.md")
    pending_review.sweep_sdd_cruft(tmp_path)              # default None
    assert f.exists()
    pending_review.sweep_sdd_cruft(tmp_path, findings_scope=None)
    assert f.exists()


def test_sweep_blueprint_scope_one_level_rmdir(sdd_dir, tmp_path):
    """DEF-01: the blueprint tier writes directly under panel-findings/blueprint/
    (no intermediate sdd/ parent); the one-level leaf is rmdir'd when empty."""
    f = _make_findings(sdd_dir, "blueprint", "PLAN-p1-critic.md")
    pending_review.sweep_sdd_cruft(tmp_path, findings_scope="blueprint")
    assert not f.exists()
    assert not (sdd_dir / "panel-findings" / "blueprint").exists()
    # panel-findings/ itself is NEVER removed (may host other tiers/features).
    # It is empty here, so it may or may not survive — assert only that the
    # sweep did not raise and the leaf is gone (above).


def test_sweep_tmp_and_lock_behavior_unchanged(sdd_dir, tmp_path):
    """Regression: passing findings_scope does not disturb the marker-lock-gated
    *.tmp/lock cleanup; both passes run, and neither marker file is touched."""
    (sdd_dir / "tmpZZZZ.tmp").write_text("z", encoding="utf-8")
    _lock_path(sdd_dir).write_text("", encoding="utf-8")
    arch = sdd_dir / "architecture.json"
    arch.write_text('{"language": "python"}\n', encoding="utf-8")
    pr = sdd_dir / "pending-review.json"
    pr.write_text("{}\n", encoding="utf-8")
    findings = _make_findings(sdd_dir, "sdd/feat-a", "spec-p1-critic.md")
    pending_review.sweep_sdd_cruft(tmp_path, findings_scope="sdd/feat-a")
    assert not (sdd_dir / "tmpZZZZ.tmp").exists()   # tmp swept
    assert not _lock_path(sdd_dir).exists()         # lock reclaimed
    assert not findings.exists()                    # findings swept
    assert arch.read_text() == '{"language": "python"}\n'   # untouched
    assert pr.read_text() == "{}\n"                          # untouched


def test_sweep_findings_scope_is_keyword_only():
    """I3 signature: findings_scope is keyword-only with an Optional[str]=None default."""
    sig = inspect.signature(pending_review.sweep_sdd_cruft)
    assert "findings_scope" in sig.parameters
    p = sig.parameters["findings_scope"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY
    assert p.default is None


# --------------------------------------------------------------------------
# T3 wiring: both validators pass a tier-qualified findings_scope to
# sweep_sdd_cruft at exit (design C6/I3; DEF-01 blueprint one-level).
# --------------------------------------------------------------------------


def test_validate_spec_wires_sdd_findings_scope():
    """validate_spec.py registers the sweep with findings_scope=`sdd/<dir-name>`."""
    src = _VS_PATH.read_text(encoding="utf-8")
    assert "findings_scope=f\"sdd/{Path(spec_dir).name}\"" in src, (
        "validate_spec.py must pass a tier-qualified sdd/<spec-dir-basename> scope"
    )


def test_validate_blueprint_wires_blueprint_findings_scope():
    """validate_blueprint.py registers the sweep with findings_scope='blueprint'."""
    src = _VB_PATH.read_text(encoding="utf-8")
    assert 'findings_scope="blueprint"' in src, (
        "validate_blueprint.py must pass the literal 'blueprint' tier scope (DEF-01)"
    )
