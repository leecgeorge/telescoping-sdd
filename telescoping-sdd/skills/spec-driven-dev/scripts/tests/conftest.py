"""pytest configuration for spec-driven-dev script tests.

Snapshots and restores `sys.path` around each test so the `_load_validate_*`
helpers (which prepend to `sys.path`) don't leave stale entries between
tests in this and sibling skills' test suites. Per P3-11 from the
post-implementation code review.
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
