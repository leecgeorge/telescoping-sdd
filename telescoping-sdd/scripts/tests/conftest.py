"""pytest configuration for shared telescoping-sdd/scripts/ tests.

Snapshots and restores `sys.path` around each test so the cross-skill
loader helpers in `test_cfc_parser_contract.py` (which prepend to
`sys.path`) don't leak between tests. Per P3-11 from the post-
implementation code review.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _restore_sys_path():
    """Restore `sys.path` after each test."""
    snapshot = list(sys.path)
    yield
    sys.path[:] = snapshot


# --- Unit C (AD17): keep archive_pass.py's panel-log sidecar out of basetemp ---
# A test artifact written straight into `tmp_path` has no root marker, so
# `find_project_root` falls back to tmp_path's parent — pytest's basetemp — and
# the first archive would create `basetemp/.sdd/`. That directory is itself a
# root marker, so it would silently move root resolution for every later test.
import contextlib  # noqa: E402
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402


@contextlib.contextmanager
def panel_log_basetemp_guard(basetemp: Path):
    """Remove `basetemp/.sdd/` on exit iff it did not exist on entry."""
    sdd = Path(basetemp) / ".sdd"
    existed = sdd.exists()
    try:
        yield
    finally:
        if not existed and sdd.exists():
            shutil.rmtree(sdd, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_panel_log_basetemp(tmp_path_factory):
    with panel_log_basetemp_guard(tmp_path_factory.getbasetemp()):
        yield
