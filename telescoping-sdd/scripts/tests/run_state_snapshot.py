"""Byte-level read-only test harness for the `--run-state` R5 proofs ([DEF-02]).

A shared, NON-test helper module (matching the `_fixture_contract.py` /
`_fixtures.py` shared-helper precedent in this directory). It is imported by:
  * the same-dir `test_run_state.py`, and
  * the two skill CLI test files via
    `sys.path.insert(0, <telescoping-sdd/scripts/tests>)` + `import
    run_state_snapshot` (Q1 resolution).

`snapshot_tree(root)` returns a `{relpath: sha256hex}` map of every file under
`root`, and `assert_no_stray_cruft(root)` is the precondition the R5 proofs run
before/after `--run-state` so the proof can never silently pass with cruft
present. Both DELIBERATELY exclude the `atexit sweep_sdd_cruft` targets
(`*.tmp`, `pending-review.lock`) from the hash map: the sweep may legitimately
create/remove those at interpreter exit, and they are not workflow-state, so
counting them would produce a false "mutation" in a genuinely read-only run
(the R5 carve-out). Distinct from the cruft-sweep tests, which only assert a
planted `.tmp` is gone and never hash the whole tree.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List

# The `atexit sweep_sdd_cruft` targets — excluded from the byte-level snapshot
# and asserted-absent by the precondition (R5 carve-out). Kept in one place so
# the snapshot exclusion and the precondition can never disagree on what "cruft"
# is.
_CRUFT_LOCK_NAME = "pending-review.lock"
_CRUFT_TMP_SUFFIX = ".tmp"


def _is_cruft(path: Path) -> bool:
    """True iff `path` is a sweep target (an abandoned `*.tmp` atomic-write temp
    or the advisory `pending-review.lock`)."""
    return path.name == _CRUFT_LOCK_NAME or path.suffix == _CRUFT_TMP_SUFFIX


def snapshot_tree(root: Path) -> "Dict[str, str]":
    """Return `{posix-relpath: sha256-hex}` for every non-cruft file under `root`.

    Deterministic (keys are project-root-relative POSIX paths). The sweep targets
    (`*.tmp`, `pending-review.lock`) are excluded so their legitimate
    creation/removal by the shared `atexit` sweep never registers as a workflow-
    state mutation in an otherwise read-only `--run-state` run (R5 carve-out).
    """
    root = Path(root)
    out: "Dict[str, str]" = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not _is_cruft(p):
            rel = p.relative_to(root).as_posix()
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def assert_no_stray_cruft(root: Path) -> None:
    """Assert no `*.tmp` / `pending-review.lock` exists anywhere under `root`.

    The precondition the R5 byte-level proof runs so it can never pass silently
    with cruft present (which the snapshot itself excludes) — planted cruft would
    otherwise mask a real write into one of those excluded paths.
    """
    root = Path(root)
    stray: "List[str]" = [
        p.relative_to(root).as_posix()
        for p in sorted(root.rglob("*"))
        if p.is_file() and _is_cruft(p)
    ]
    assert not stray, (
        f"stray .sdd/ cruft present under {root}; cannot prove read-only "
        f"cleanly: {stray}"
    )
