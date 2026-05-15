# Test fixtures

Static fixtures consumed by the test suite. Two contracts apply:

- **Sub-directories** (e.g. `line_ending_variants/`) must carry a `FIXTURE_MANIFEST.json` listing the SHA-256 of every file in the directory. `test_fixture_manifests_consistent.py` walks them on every test run and fails if content drifts from the manifest. Regenerate the manifest deliberately after intentional edits — see `_fixture_contract.py:generate_fixture_manifest`.
- **Top-level JSON files** (e.g. `observed_marketplace_layout.json`) are not under the manifest contract; they're consumed directly by their owning test.

## `observed_marketplace_layout.json`

Describes the directory structure that the `telescoping-sdd` plugin presents inside `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` after a marketplace install. Used by `skills/project-blueprint/scripts/tests/test_validate_blueprint.py` to reconstruct a synthetic marketplace cache and verify that the validator's `parents[3] / "scripts"` arithmetic resolves to the right shared-scripts location under that layout.

Fields:

- `version_dir_name` — the leaf directory name in the cache path (e.g. `1.0.0`). The test uses it to construct `tmp_path / "synthetic_cache" / <version_dir_name>`; the literal value doesn't matter as long as it's a valid directory name.
- `tree.entries` — every file and directory the plugin contributes to the cache, with relative paths. The test materialises these as empty stubs to build the synthetic layout. The validator scripts (`validate_blueprint.py`, `blueprint_common.py`) are copied in on top at the paths the layout expects.

When the plugin layout changes (new directories under `agents/`, `scripts/`, or `skills/`), regenerate this file to match.
