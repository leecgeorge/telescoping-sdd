"""Fixture-management contract.

Every static fixture directory must contain a `FIXTURE_MANIFEST.json` listing
the SHA-256 of every file in the directory (excluding the manifest itself).
Tests that consume a fixture call `assert_fixture_unchanged()` as their first
assertion to fail loudly if the live fixture has drifted from the manifest.

The manifest may carry additional fixture-specific keys (e.g.,
`expected_hashes`, `expected_stdout`); the contract only enforces `files`.

Dynamic fixtures — those built per-test under `tmp_path` — are out of scope
for this contract. Their generator modules live under a sibling
`tests/fixture_builders/` directory, NOT under `tests/fixtures/`. A directory
containing a `.dynamic` sentinel file is skipped by the global walker.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "FIXTURE_MANIFEST.json"
DYNAMIC_SENTINEL = ".dynamic"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_fixture_files(fixture_dir: Path) -> list[Path]:
    """Files in fixture_dir, sorted, excluding the manifest itself."""
    return sorted(
        p for p in fixture_dir.iterdir()
        if p.is_file() and p.name != MANIFEST_FILENAME
    )


def generate_fixture_manifest(fixture_dir: Path) -> dict[str, Any]:
    """Build a fresh manifest dict for `fixture_dir` from current contents.

    Used by fixture authors to regenerate the manifest after deliberate edits.
    Callers may merge additional fixture-specific keys (e.g.,
    `expected_hashes`) before writing.
    """
    return {
        "files": {
            p.name: _sha256_file(p) for p in _iter_fixture_files(fixture_dir)
        }
    }


def assert_fixture_unchanged(fixture_dir: Path) -> None:
    """Fail loudly if any file in `fixture_dir` has drifted from the manifest.

    Raises AssertionError with a precise diagnostic on:
      * missing manifest
      * malformed manifest (no `files` key)
      * file in manifest missing on disk
      * file on disk not in manifest (only files at the top level count)
      * SHA-256 mismatch
    """
    manifest_path = fixture_dir / MANIFEST_FILENAME
    assert manifest_path.is_file(), (
        f"Fixture manifest missing: {manifest_path}. "
        f"Run generate_fixture_manifest({fixture_dir}) and commit the result."
    )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"Fixture manifest is not valid JSON: {manifest_path}: {exc}"
        ) from exc

    files = manifest.get("files")
    assert isinstance(files, dict), (
        f"Fixture manifest at {manifest_path} has no 'files' key (or it is "
        f"not a dict). Got: {type(files).__name__}"
    )

    actual_names = {p.name for p in _iter_fixture_files(fixture_dir)}
    expected_names = set(files.keys())

    missing_on_disk = expected_names - actual_names
    extra_on_disk = actual_names - expected_names
    assert not missing_on_disk, (
        f"Fixture files in {fixture_dir} listed in manifest but missing on "
        f"disk: {sorted(missing_on_disk)}"
    )
    assert not extra_on_disk, (
        f"Fixture files in {fixture_dir} present on disk but missing from "
        f"manifest: {sorted(extra_on_disk)}. Regenerate the manifest."
    )

    drifted = []
    for name, expected_hash in sorted(files.items()):
        actual_hash = _sha256_file(fixture_dir / name)
        if actual_hash != expected_hash:
            drifted.append((name, expected_hash, actual_hash))
    assert not drifted, (
        f"Fixture content drift in {fixture_dir}:\n"
        + "\n".join(
            f"  {name}: expected {exp[:12]}…, got {act[:12]}…"
            for name, exp, act in drifted
        )
        + "\nIf the drift is intentional, regenerate FIXTURE_MANIFEST.json."
    )


def is_dynamic_fixture_dir(fixture_dir: Path) -> bool:
    """True if `fixture_dir` carries the `.dynamic` sentinel and is skipped."""
    return (fixture_dir / DYNAMIC_SENTINEL).exists()


def find_static_fixture_dirs(*roots: Path) -> list[Path]:
    """Sub-directories of any root that contain at least one regular file
    AND do not carry a `.dynamic` sentinel. The roots themselves are
    silently skipped if they don't exist.
    """
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_dir():
                continue
            if is_dynamic_fixture_dir(p):
                continue
            if any(child.is_file() for child in p.iterdir()):
                out.append(p)
    return out
