"""Global regression guard: every static fixture directory under
`telescoping-sdd/scripts/tests/fixtures/` must carry a valid `FIXTURE_MANIFEST.json`
whose contents match reality.

This test fails loudly if anyone edits a fixture without regenerating the
manifest — a mistake that would silently invalidate every test depending on
that fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root is parents[3] from this file:
#   telescoping-sdd/scripts/tests/test_fixture_manifests_consistent.py
#   parents[0]=tests/  [1]=scripts/  [2]=telescoping-sdd/  [3]=<repo-root>/
_REPO_ROOT = Path(__file__).resolve().parents[3]
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.append(str(_TESTS))

from _fixture_contract import (  # noqa: E402
    assert_fixture_unchanged,
    find_static_fixture_dirs,
)

FIXTURE_ROOTS = (
    _REPO_ROOT / "telescoping-sdd" / "scripts" / "tests" / "fixtures",
    # Per-skill fixture trees (I3.6): the guard previously rooted only at the
    # shared-scripts fixtures, so a static fixture added under a skill's own
    # tests/ would silently escape the manifest check. find_static_fixture_dirs
    # skips roots that don't exist, so these are harmless until a skill grows a
    # fixtures/ dir — at which point it is guarded automatically.
    _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts" / "tests" / "fixtures",
    _REPO_ROOT / "telescoping-sdd" / "skills" / "spec-driven-dev" / "scripts" / "tests" / "fixtures",
)


def test_fixture_manifests_consistent():
    """Walk every static fixture directory; assert manifest matches reality."""
    dirs = find_static_fixture_dirs(*FIXTURE_ROOTS)
    assert dirs, (
        "Walker found no static fixture directories under: "
        f"{[str(r) for r in FIXTURE_ROOTS]}. "
        "Check the walker isn't filtering too aggressively."
    )
    for d in dirs:
        assert_fixture_unchanged(d)


def test_assert_fixture_unchanged_detects_drift(tmp_path):
    """Mutate a fixture file; helper must fail loudly."""
    import json

    from _fixture_contract import generate_fixture_manifest

    (tmp_path / "doc.md").write_text("original\n", encoding="utf-8")
    manifest = generate_fixture_manifest(tmp_path)
    (tmp_path / "FIXTURE_MANIFEST.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    # Baseline passes
    assert_fixture_unchanged(tmp_path)

    # Mutate, expect failure
    (tmp_path / "doc.md").write_text("MUTATED\n", encoding="utf-8")
    import pytest

    with pytest.raises(AssertionError, match="content drift"):
        assert_fixture_unchanged(tmp_path)


def test_assert_fixture_unchanged_detects_extra_file(tmp_path):
    import json

    from _fixture_contract import generate_fixture_manifest

    (tmp_path / "a.md").write_text("a\n", encoding="utf-8")
    manifest = generate_fixture_manifest(tmp_path)
    (tmp_path / "FIXTURE_MANIFEST.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (tmp_path / "b.md").write_text("b\n", encoding="utf-8")  # not in manifest

    import pytest

    with pytest.raises(AssertionError, match="missing from\nmanifest|missing from manifest"):
        assert_fixture_unchanged(tmp_path)


def test_generate_fixture_manifest_matches_self(tmp_path):
    """Regenerated manifest plus assert_fixture_unchanged round-trips."""
    import json

    from _fixture_contract import generate_fixture_manifest

    (tmp_path / "x.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / "y.md").write_text("world\n", encoding="utf-8")
    manifest = generate_fixture_manifest(tmp_path)
    (tmp_path / "FIXTURE_MANIFEST.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    assert_fixture_unchanged(tmp_path)


def test_dynamic_sentinel_skipped(tmp_path):
    """A directory with a .dynamic sentinel is excluded from the walker."""
    from _fixture_contract import find_static_fixture_dirs

    dyn = tmp_path / "dyn"
    dyn.mkdir()
    (dyn / "anything").write_text("x", encoding="utf-8")
    (dyn / ".dynamic").write_text("", encoding="utf-8")

    static = tmp_path / "static"
    static.mkdir()
    (static / "anything").write_text("x", encoding="utf-8")

    found = find_static_fixture_dirs(tmp_path)
    assert dyn not in found
    assert static in found
