"""Self-tests for the byte-level read-only test harness `run_state_snapshot`.

The `snapshot_tree` harness ([DEF-02]) is the mechanism the R5 read-only proofs
(T6/T7) depend on: a before/after byte-level snapshot of every workflow-state
file. These tests pin the two properties the proofs rely on:

* CHANGE DETECTION — a single-byte edit to any snapshotted file changes the
  returned hash map (so a real mutation cannot slip past the proof).
* NO-STRAY-CRUFT PRECONDITION — a planted `*.tmp` / `pending-review.lock` trips
  the precondition assertion, so the R5 proof cannot silently pass with cruft
  present (those are the `atexit sweep_sdd_cruft` targets excluded per the R5
  carve-out).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_snapshot():
    scripts_tests = _REPO_ROOT / "telescoping-sdd" / "scripts" / "tests"
    if str(scripts_tests) not in sys.path:
        sys.path.insert(0, str(scripts_tests))
    if "run_state_snapshot" in sys.modules:
        return importlib.reload(sys.modules["run_state_snapshot"])
    return importlib.import_module("run_state_snapshot")


snap = _load_snapshot()


def _rich_tree(root: Path) -> None:
    """Build a tree resembling a real feature dir: artifacts with ## Approval
    blocks + hashes, plus .sdd/architecture.json and .sdd/pending-review.json."""
    specs = root / "specs" / "feature"
    specs.mkdir(parents=True)
    (specs / "01_spec.md").write_text(
        "# Spec\n\n## Approval\n\n- [x] Approved to proceed\n"
        "- **Content Hash:** `0123456789abcdef`\n- **Hash basis:** v2\n",
        encoding="utf-8",
    )
    (specs / "02_design.md").write_text(
        "# Design\n\n## Approval\n\n- [ ] Approved to proceed\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    sdd = root / ".sdd"
    sdd.mkdir()
    (sdd / "architecture.json").write_text(
        '{"schemaVersion": 1, "language": "python", "source": "user"}\n',
        encoding="utf-8",
    )
    (sdd / "pending-review.json").write_text(
        '{"schemaVersion": 1, "pending": {}}\n', encoding="utf-8"
    )


def test_snapshot_tree_detects_content_change(tmp_path):
    _rich_tree(tmp_path)

    before = snap.snapshot_tree(tmp_path)
    # A no-op leaves the snapshot byte-identical.
    assert snap.snapshot_tree(tmp_path) == before

    # A single-byte edit to any snapshotted file makes the snapshots differ.
    target = tmp_path / "specs" / "feature" / "01_spec.md"
    target.write_text(target.read_text(encoding="utf-8") + "x", encoding="utf-8")
    after = snap.snapshot_tree(tmp_path)
    assert after != before
    # And it is precisely the edited file whose hash moved.
    rel = str(target.relative_to(tmp_path))
    assert after[rel] != before[rel]


def test_snapshot_tree_precondition_rejects_stray_cruft(tmp_path):
    _rich_tree(tmp_path)
    # A clean tree passes the precondition.
    snap.assert_no_stray_cruft(tmp_path)

    # A planted *.tmp trips it.
    (tmp_path / ".sdd" / "abc123.tmp").write_text("x", encoding="utf-8")
    with pytest.raises(AssertionError):
        snap.assert_no_stray_cruft(tmp_path)

    # ...and so does a planted pending-review.lock.
    (tmp_path / ".sdd" / "abc123.tmp").unlink()
    (tmp_path / ".sdd" / "pending-review.lock").write_text("", encoding="utf-8")
    with pytest.raises(AssertionError):
        snap.assert_no_stray_cruft(tmp_path)


def test_snapshot_tree_excludes_cruft_from_hash_map(tmp_path):
    """The sweep targets are excluded from the snapshot (R5 carve-out) so a
    legitimate atexit-sweep create/remove of a `.lock`/`.tmp` never shows up as a
    false diff in the read-only proof."""
    _rich_tree(tmp_path)
    base = snap.snapshot_tree(tmp_path)
    # Adding a cruft file does not change the snapshot (it is excluded).
    (tmp_path / ".sdd" / "pending-review.lock").write_text("", encoding="utf-8")
    (tmp_path / ".sdd" / "zzz.tmp").write_text("stale", encoding="utf-8")
    assert snap.snapshot_tree(tmp_path) == base


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
