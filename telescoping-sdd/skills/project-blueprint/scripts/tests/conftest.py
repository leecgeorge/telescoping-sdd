"""pytest configuration for project-blueprint script tests.

Snapshots and restores `sys.path` around each test so the `_load_validate_*`
helpers (which prepend to `sys.path`) don't leave stale entries between
tests in this and sibling skills' test suites. Per P3-11 from the
post-implementation code review.

Provides:
- `fixture_tiny_png_path` — session-scoped 67-byte 1x1 PNG path.
- `fixture_scope_with_panel_review_and_frontmatter` — function-scoped SCOPE
  body containing every R2 strippable construct.
- `fixture_approved_triple_frozen` — function-scoped frozen-hash trio.
- `fixture_approved_triple` — function-scoped on-disk approved triple
  (computes hashes lazily via blueprint_common.compute_content_hash).

These fixtures are shared across the split test modules (P3-15).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from common import (  # type: ignore[import-not-found]
    _doc_with_hash,
    _FROZEN_ARCH_BODY,
    _FROZEN_ARCH_HASH,
    _FROZEN_PLAN_BODY,
    _FROZEN_PLAN_HASH,
    _FROZEN_SCOPE_BODY,
    _FROZEN_SCOPE_HASH,
    _SCRIPTS_DIR,
)

# 67-byte minimal valid PNG (1x1, fully transparent). Used as the
# brand-logo stand-in for tests that need a real on-disk PNG but don't
# care about content. Same literal as committed in the design's fixture
# manifest.
_TINY_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xfa\xcf\x00\x00\x00\x02\x00\x01\xe5\x27\xde\xfc"
    b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
)


@pytest.fixture(autouse=True)
def _restore_sys_path():
    """Restore `sys.path` after each test."""
    snapshot = list(sys.path)
    yield
    sys.path[:] = snapshot


@pytest.fixture(scope="session")
def fixture_tiny_png_path(tmp_path_factory) -> Path:
    """Write the 67-byte minimal PNG to a session-scoped tmp path; return it.

    Used by render-pipeline tests that need a real on-disk PNG (e.g. when
    monkeypatching `_LOGO_ASSET_PATH` to a small known-good payload) without
    forcing each test to write the bytes itself.
    """
    p = tmp_path_factory.mktemp("logo-fixture") / "test-logo-tiny.png"
    p.write_bytes(_TINY_PNG_BYTES)
    return p


@pytest.fixture
def fixture_scope_with_panel_review_and_frontmatter() -> str:
    """A SCOPE.md body containing every R2 strippable construct: YAML
    frontmatter, `## Panel Review` section with sub-headings, inline `[SEAL]`
    token, `## Approval` block with checkbox + content hash. Used by R2 / C5
    filter tests."""
    return (
        "---\n"
        "title: Scope\n"
        "---\n"
        "\n"
        "# Project Scope\n"
        "\n"
        "Decision-context per [SEAL-01] applies.\n"
        "\n"
        "## Panel Review\n"
        "\n"
        "### Trajectory\n"
        "\n"
        "| Pass | HIGHs |\n"
        "|------|-------|\n"
        "| 1    | 3     |\n"
        "\n"
        "### Sealed dispositions\n"
        "\n"
        "- `[SEAL-02]` something\n"
        "\n"
        "## Approval\n"
        "\n"
        "- [x] Approved to proceed\n"
        "- **Content Hash:** `4417a0d55fa4c2ec`\n"
    )


@pytest.fixture
def fixture_approved_triple_frozen() -> tuple[str, str, str]:
    """Three artifact contents with HARDCODED hash literals.

    Regeneration runbook — when `blueprint_common.compute_content_hash` changes
    intentionally:

        python -c "import sys; sys.path.insert(0, 'telescoping-sdd/scripts'); \\
                   from blueprint_common import compute_content_hash; \\
                   print(compute_content_hash(open('<artifact>').read()))"

    Run for each of SCOPE, ARCHITECTURE, PLAN; update the three literals in
    common.py. Always verify the change is intentional — the test failure
    that prompted regeneration is the safety signal, not a chore to
    mechanically silence.
    """
    return (
        _doc_with_hash(_FROZEN_SCOPE_BODY, stored_hash=_FROZEN_SCOPE_HASH),
        _doc_with_hash(_FROZEN_ARCH_BODY, stored_hash=_FROZEN_ARCH_HASH),
        _doc_with_hash(_FROZEN_PLAN_BODY, stored_hash=_FROZEN_PLAN_HASH),
    )


@pytest.fixture
def fixture_approved_triple(tmp_path):
    """Three artifact files with ticked approval checkboxes AND correct
    content hashes (computed via blueprint_common.compute_content_hash).
    Returns the blueprint directory path."""
    shared = str(_SCRIPTS_DIR.resolve().parents[2] / "scripts")
    if shared not in sys.path:
        sys.path.append(shared)
    from blueprint_common import compute_content_hash  # type: ignore[import-not-found]

    bodies = {
        "SCOPE.md": "# My Project\n\nScope body content.\n",
        "ARCHITECTURE.md": "# Arch\n\nArchitecture body content.\n",
        "PLAN.md": "# Plan\n\nPlan body content.\n",
    }
    for fname, body in bodies.items():
        scaffold = (
            f"{body}\n\n"
            f"## Approval\n\n"
            f"- [x] Approved to proceed\n"
            f"- **Content Hash:** `{'0' * 16}`\n"
        )
        real_hash = compute_content_hash(scaffold)
        final = (
            f"{body}\n\n"
            f"## Approval\n\n"
            f"- [x] Approved to proceed\n"
            f"- **Content Hash:** `{real_hash}`\n"
        )
        (tmp_path / fname).write_text(final, encoding="utf-8")
    return tmp_path
