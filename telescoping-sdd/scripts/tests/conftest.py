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
