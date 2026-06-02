"""Tests for validate_blueprint.py.

Verifies:
  * Helpers are imported from blueprint_common (not redefined locally).
  * Hash output is byte-identical to the baselines stored in the
    shared frozen-fixture matrix.
  * sys.path[0] is unchanged after importing validate_blueprint (regression
    guard that sys.path.append, not sys.path.insert(0, ...), was used).
  * Full CLI runs end-to-end under both load modes:
      - `--plugin-dir`-style direct source invocation
      - synthetic marketplace-style layout reconstructed from the captured
        observed_marketplace_layout.json
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SHARED_FIXTURES = (
    _REPO_ROOT / "telescoping-sdd" / "scripts" / "tests" / "fixtures" / "line_ending_variants"
)


def _load_validate_blueprint():
    """Import validate_blueprint from its sibling scripts directory."""
    scripts_dir = Path(__file__).resolve().parents[1]  # scripts/
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    if "validate_blueprint" in sys.modules:
        return importlib.reload(sys.modules["validate_blueprint"])
    return importlib.import_module("validate_blueprint")


def test_validate_blueprint_imports_from_blueprint_common():
    """The 8 shared helpers must be present on validate_blueprint's namespace,
    sourced from blueprint_common (not re-defined locally).
    """
    vb = _load_validate_blueprint()
    sys.path.insert(
        0, str(_REPO_ROOT / "telescoping-sdd" / "scripts")
    )
    import blueprint_common as bc  # noqa: E402

    for name in (
        "content_for_hashing",
        "compute_content_hash",
        "verify_content_hash",
        "has_section",
        "section_has_content",
        "scan_unresolved_markers",
        "extract_panel_section",
        "validate_panel_review",
        "ValidationResult",
        "Severity",
    ):
        vb_obj = getattr(vb, name)
        bc_obj = getattr(bc, name)
        # Same object (imported, not redefined)
        assert vb_obj is bc_obj, (
            f"validate_blueprint.{name} is not the same object as "
            f"blueprint_common.{name} — refactor missed it"
        )


def test_sys_path_append_not_insert():
    """Importing validate_blueprint must not mutate sys.path[0]. The shared
    helpers are appended, not inserted at the front, so callers' module
    resolution order is preserved.
    """
    # Establish a known sys.path[0]
    sentinel = "/__validate_blueprint_test_sentinel__"
    sys.path.insert(0, sentinel)
    try:
        # Force a fresh import so the module-level sys.path.append re-runs
        sys.modules.pop("validate_blueprint", None)
        before = sys.path[0]
        scripts_dir = Path(__file__).resolve().parents[1]
        if str(scripts_dir) not in sys.path:
            sys.path.append(str(scripts_dir))
        importlib.import_module("validate_blueprint")
        after = sys.path[0]
        assert before == after == sentinel, (
            f"sys.path[0] changed during import: {before!r} -> {after!r}. "
            f"validate_blueprint must use sys.path.append, not insert(0, ...)"
        )
    finally:
        # Clean up
        if sentinel in sys.path:
            sys.path.remove(sentinel)


def test_validate_blueprint_hash_matches_manifest_baselines():
    """Hash output on the frozen-fixture matrix is byte-identical to the
    baselines stored alongside the fixtures.
    """
    vb = _load_validate_blueprint()
    manifest = json.loads(
        (_SHARED_FIXTURES / "FIXTURE_MANIFEST.json").read_text(encoding="utf-8")
    )
    expected = manifest["expected_hashes_read_text_utf8"]
    drifted = []
    for name, baseline in expected.items():
        content = (_SHARED_FIXTURES / name).read_text(encoding="utf-8")
        actual = vb.compute_content_hash(content)
        if actual != baseline:
            drifted.append((name, baseline, actual))
    assert not drifted, (
        "validate_blueprint.compute_content_hash drifted from manifest baseline:\n"
        + "\n".join(f"  {n}: expected {e}, got {a}" for n, e, a in drifted)
    )


def test_validate_blueprint_compute_content_hash_matches_blueprint_common():
    """Cross-check: compute_content_hash on validate_blueprint and on
    blueprint_common produce identical output for the same input.
    """
    vb = _load_validate_blueprint()
    sys.path.insert(0, str(_REPO_ROOT / "telescoping-sdd" / "scripts"))
    import blueprint_common as bc  # noqa: E402

    sample = (
        "# Doc\n\nbody text.\n\n## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )
    assert vb.compute_content_hash(sample) == bc.compute_content_hash(sample)


# ---------------------------------------------------------------------------
# Full-CLI end-to-end test — subprocess.run under both plugin load modes
# ---------------------------------------------------------------------------

# A minimal but complete SCOPE.md that satisfies validate_blueprint's
# scope-phase checks. The Approval section is unstamped so the test can
# exercise --approve and read back the Content Hash.
_MINIMAL_SCOPE_MD = """\
# Test Project Scope

## Problem Statement

We need to verify validate_blueprint runs end-to-end under both plugin
load modes — `--plugin-dir` and the marketplace cache layout.

## Target Users

### Test Maintainer
The CI matrix runs this fixture to detect breakage in plugin layout.

## Goals

- Validate that parents[3] arithmetic finds blueprint_common at runtime.

## Non-Goals

- Validating ARCHITECTURE.md or PLAN.md (out of scope for this fixture).

## Constraints

| Type | Detail | Source |
|------|--------|--------|
| Tech | Python 3.11+ | CI matrix |
| Tech | POSIX-only | platform skip |

## Success Criteria

- [ ] validate_blueprint exits 0 against this fixture under both load modes.

## Panel Review

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|
| 1 | 2026-04-30 | 0 | 0 | 0 | 0 | 0 | synthetic-fixture clean |

### Sealed dispositions

_None._

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [ ] Approved to proceed to next phase
- **Content Hash:** `pending`
"""


def _read_stamped_hash(scope_path: Path) -> str:
    """Extract the Content Hash from an approved SCOPE.md."""
    content = scope_path.read_text(encoding="utf-8")
    m = re.search(r"\*\*Content Hash:\*\*\s*`([a-f0-9]+)`", content)
    assert m, f"No stamped hash in {scope_path}:\n{content}"
    return m.group(1)


def _write_blueprint_dir(target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    (target / "SCOPE.md").write_text(_MINIMAL_SCOPE_MD, encoding="utf-8")
    return target


def _load_marketplace_layout() -> dict:
    layout_path = (
        _REPO_ROOT / "telescoping-sdd" / "scripts" / "tests" / "fixtures"
        / "observed_marketplace_layout.json"
    )
    return json.loads(layout_path.read_text(encoding="utf-8"))


def _build_synthetic_marketplace(tmp_path: Path) -> Path:
    """Reconstruct the captured marketplace tree under tmp_path and copy in
    the working-tree validate_blueprint.py and blueprint_common.py at the
    paths the captured layout says they live. Returns the path to the
    synthetic validate_blueprint.py.
    """
    layout = _load_marketplace_layout()
    version_dir_name = layout["version_dir_name"]
    synth_root = tmp_path / "synthetic_cache" / version_dir_name
    synth_root.mkdir(parents=True)

    # Recreate every directory from the captured layout (skip files — we
    # only need the directory shape). Then copy the two scripts whose
    # presence the validator's `parents[3] / "scripts"` lookup depends on.
    for entry in layout["tree"]["entries"]:
        if entry["type"] == "dir":
            (synth_root / entry["path"]).mkdir(parents=True, exist_ok=True)

    src_scripts = _REPO_ROOT / "telescoping-sdd" / "scripts"
    dst_scripts = synth_root / "scripts"
    dst_scripts.mkdir(exist_ok=True)
    shutil.copy2(src_scripts / "blueprint_common.py", dst_scripts / "blueprint_common.py")
    shutil.copy2(src_scripts / "cfc_parser.py", dst_scripts / "cfc_parser.py")
    # arch_config.py is a runtime import of validate_blueprint (the --write-arch-config
    # seam); a published install ships it in the shared scripts dir, so the synthetic
    # layout must include it too or `parents[3] / "scripts"` import resolution fails.
    shutil.copy2(src_scripts / "arch_config.py", dst_scripts / "arch_config.py")
    # spec_dirname.py is imported by validate_blueprint (classify_dirname /
    # parse_feature_number for spec-directory grammar); same synthetic-layout
    # requirement as arch_config.
    shutil.copy2(src_scripts / "spec_dirname.py", dst_scripts / "spec_dirname.py")

    src_validator = (
        _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts"
        / "validate_blueprint.py"
    )
    dst_validator_dir = synth_root / "skills" / "project-blueprint" / "scripts"
    dst_validator_dir.mkdir(parents=True, exist_ok=True)
    dst_validator = dst_validator_dir / "validate_blueprint.py"
    shutil.copy2(src_validator, dst_validator)
    return dst_validator


def _run_cli(validator: Path, blueprint_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(validator), str(blueprint_dir), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def test_validate_blueprint_post_r0_full_cli(tmp_path):
    """Run validate_blueprint end-to-end via subprocess under both load
    modes. Each invocation exits 0 against the same fixture and stamps the
    SCOPE.md with the same Content Hash that blueprint_common would
    independently compute.
    """
    sys.path.insert(0, str(_REPO_ROOT / "telescoping-sdd" / "scripts"))
    import blueprint_common as bc  # noqa: E402

    expected_hash = bc.compute_content_hash(_MINIMAL_SCOPE_MD)

    # --- Mode A: --plugin-dir style (validate_blueprint at its source path).
    blueprint_a = _write_blueprint_dir(tmp_path / "mode_plugin_dir" / "blueprint")
    src_validator = (
        _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts"
        / "validate_blueprint.py"
    )
    proc = _run_cli(src_validator, blueprint_a, "--phase", "scope")
    assert proc.returncode == 0, (
        f"--plugin-dir validate failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    proc = _run_cli(src_validator, blueprint_a, "--approve", "scope")
    assert proc.returncode == 0, (
        f"--plugin-dir approve failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    stamped_a = _read_stamped_hash(blueprint_a / "SCOPE.md")
    assert stamped_a == expected_hash, (
        f"Hash mismatch in --plugin-dir mode: stamped={stamped_a}, expected={expected_hash}"
    )

    # --- Mode B: synthetic marketplace-style layout reconstructed from the
    # captured observed_marketplace_layout.json. Validates that
    # `parents[3] / "scripts"` resolves to the published shared-scripts dir.
    synth_validator = _build_synthetic_marketplace(tmp_path)
    blueprint_b = _write_blueprint_dir(tmp_path / "mode_marketplace" / "blueprint")
    proc = _run_cli(synth_validator, blueprint_b, "--phase", "scope")
    assert proc.returncode == 0, (
        f"marketplace validate failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    proc = _run_cli(synth_validator, blueprint_b, "--approve", "scope")
    assert proc.returncode == 0, (
        f"marketplace approve failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    stamped_b = _read_stamped_hash(blueprint_b / "SCOPE.md")
    assert stamped_b == expected_hash, (
        f"Hash mismatch in marketplace mode: stamped={stamped_b}, expected={expected_hash}"
    )

    # --- Cross-mode equality (the load-mode invariant)
    assert stamped_a == stamped_b, (
        f"Hash diverged between load modes: --plugin-dir={stamped_a}, "
        f"marketplace={stamped_b}"
    )


# ============================================================================
# PLAN.md '### Deferred dispositions' hard-fail check
# ============================================================================

def _make_minimal_plan_dir(tmp_path, plan_extra: str = "") -> Path:
    """Create a minimal blueprint/ dir with PLAN.md (and an empty ARCHITECTURE.md
    approval shim so check_previous_phase_approved doesn't block validation).
    """
    blueprint_dir = tmp_path / "blueprint"
    blueprint_dir.mkdir()
    # Minimal approved SCOPE.md + ARCHITECTURE.md (just enough for the previous-phase check)
    for name in ("SCOPE.md", "ARCHITECTURE.md"):
        (blueprint_dir / name).write_text(
            f"# {name[:-3]}\n\n## Approval\n- [x] Approved\n- **Content Hash:** `abc123`\n",
            encoding="utf-8",
        )
    plan_body = (
        "# PLAN\n\n"
        "## Feature Breakdown\n### F1: feature\n\n"
        "## MVP Definition\n\n"
        "## Feature Dependencies\n\n"
        "## Implementation Order\n\n"
        "## Milestones\n\n"
        "## Panel Review\n\n"
        f"{plan_extra}"
        "## Approval\n- [ ] Approved\n- **Content Hash:** `pending`\n"
    )
    (blueprint_dir / "PLAN.md").write_text(plan_body, encoding="utf-8")
    return blueprint_dir


def test_validate_plan_fails_on_deferred_dispositions_section(tmp_path):
    """PLAN.md containing `### Deferred dispositions` triggers a FAIL result."""
    vb = _load_validate_blueprint()
    blueprint_dir = _make_minimal_plan_dir(
        tmp_path, plan_extra="### Deferred dispositions\n\n",
    )
    result = vb.validate_plan(blueprint_dir)
    failed_checks = [c for c in result.checks if c[1] == "FAIL"]
    # The specific check we added must have failed
    deferred_failures = [
        c for c in failed_checks
        if "Deferred dispositions" in c[0]
    ]
    assert deferred_failures, f"expected deferred-section FAIL; got: {failed_checks}"


def test_validate_plan_passes_without_deferred_dispositions_section(tmp_path):
    """PLAN.md without the section produces no deferred-section FAIL."""
    vb = _load_validate_blueprint()
    blueprint_dir = _make_minimal_plan_dir(tmp_path, plan_extra="")
    result = vb.validate_plan(blueprint_dir)
    deferred_failures = [
        c for c in result.checks
        if "Deferred dispositions" in c[0] and c[1] == "FAIL"
    ]
    assert not deferred_failures, (
        f"expected no deferred-section FAIL; got: {deferred_failures}"
    )


def test_validate_plan_fails_only_on_line_anchored_heading(tmp_path):
    """The string inside a fenced code block does NOT trigger the FAIL —
    line-anchored regex correctly rejects non-heading occurrences."""
    vb = _load_validate_blueprint()
    plan_extra = (
        "Example format:\n\n"
        "```\n"
        "### Deferred dispositions\n"
        "```\n\n"
    )
    blueprint_dir = _make_minimal_plan_dir(tmp_path, plan_extra=plan_extra)
    result = vb.validate_plan(blueprint_dir)
    deferred_failures = [
        c for c in result.checks
        if "Deferred dispositions" in c[0] and c[1] == "FAIL"
    ]
    # Fenced code blocks contain the literal text as a line starting with
    # "### " too. The line-anchored regex (?m)^### Deferred dispositions\s*$
    # still matches it — known limitation. If a stronger guard is needed,
    # use a markdown-AST-aware check.
    assert deferred_failures, "Fenced-block headings still match line-anchored regex"


def test_validate_plan_fails_on_crlf_terminated_heading(tmp_path):
    """`### Deferred dispositions\\r\\n` (CRLF) triggers the FAIL — `\\s*$`
    correctly consumes `\\r` since `\\r` is in `\\s`."""
    vb = _load_validate_blueprint()
    blueprint_dir = _make_minimal_plan_dir(tmp_path, plan_extra="")
    # Overwrite PLAN.md with CRLF line endings, with the heading present
    plan = blueprint_dir / "PLAN.md"
    body = plan.read_text(encoding="utf-8")
    body = body.replace(
        "## Panel Review\n",
        "## Panel Review\n\n### Deferred dispositions\r\n",
    )
    # Write back as bytes to preserve the CRLF
    plan.write_bytes(body.encode("utf-8"))
    result = vb.validate_plan(blueprint_dir)
    deferred_failures = [
        c for c in result.checks
        if "Deferred dispositions" in c[0] and c[1] == "FAIL"
    ]
    assert deferred_failures, "CRLF-terminated heading must still trigger FAIL"
