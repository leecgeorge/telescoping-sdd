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
    # trajectory.py (leaf), content_hash.py (layer over trajectory), and
    # pending_review.py hold concerns blueprint_common re-exports (audit R3.1);
    # blueprint_common imports all three at load time, so a published install
    # ships them in the shared scripts dir and the synthetic layout must too.
    shutil.copy2(src_scripts / "trajectory.py", dst_scripts / "trajectory.py")
    shutil.copy2(src_scripts / "content_hash.py", dst_scripts / "content_hash.py")
    shutil.copy2(src_scripts / "artifact_resolution.py", dst_scripts / "artifact_resolution.py")
    shutil.copy2(src_scripts / "pending_review.py", dst_scripts / "pending_review.py")
    shutil.copy2(src_scripts / "cfc_parser.py", dst_scripts / "cfc_parser.py")
    # downstream_ref_guard.py is imported by validate_blueprint (the downstream-identifier
    # guard wired into validate_scope/validate_architecture); a published install ships it
    # in the shared scripts dir, so the synthetic layout must include it too.
    shutil.copy2(
        src_scripts / "downstream_ref_guard.py", dst_scripts / "downstream_ref_guard.py"
    )
    # arch_config.py is a runtime import of validate_blueprint (the --write-arch-config
    # seam); a published install ships it in the shared scripts dir, so the synthetic
    # layout must include it too or `parents[3] / "scripts"` import resolution fails.
    shutil.copy2(src_scripts / "arch_config.py", dst_scripts / "arch_config.py")
    # spec_dirname.py is imported by validate_blueprint (classify_dirname /
    # parse_feature_number for spec-directory grammar); same synthetic-layout
    # requirement as arch_config.
    shutil.copy2(src_scripts / "spec_dirname.py", dst_scripts / "spec_dirname.py")
    # master_feature.py is imported by validate_blueprint (CPD T9b: the
    # `**Implemented by:**` positional parser reuses its feature-block boundary
    # detection); same synthetic-layout requirement as the others.
    shutil.copy2(src_scripts / "master_feature.py", dst_scripts / "master_feature.py")
    # project_link.py + project_registry.py are imported by validate_blueprint
    # (CPD T11: the derived-dir coverage exclusion parses `<project>--F<n>-<slug>`
    # prefixes via project_link.parse_derived_dirname and gates exclusion on
    # project_registry.find_sibling); same synthetic-layout requirement as above.
    shutil.copy2(src_scripts / "project_link.py", dst_scripts / "project_link.py")
    shutil.copy2(
        src_scripts / "project_registry.py", dst_scripts / "project_registry.py"
    )
    # run_state.py is a runtime import of validate_blueprint (the --run-state
    # rehydration seam); a published install ships it in the shared scripts dir,
    # so the synthetic layout must include it too or `parents[3] / "scripts"`
    # import resolution fails.
    shutil.copy2(src_scripts / "run_state.py", dst_scripts / "run_state.py")
    # reset_checkpoint.py is a runtime import of both validators (the reset-at-
    # gate advisory seam); likewise shipped in the shared scripts dir.
    shutil.copy2(src_scripts / "reset_checkpoint.py", dst_scripts / "reset_checkpoint.py")

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


def test_validate_plan_fails_on_duplicate_feature_number(tmp_path):
    """R1.7: two `### F1:` blocks inside Feature Breakdown FAIL the uniqueness
    check — duplicates resolve oppositely across CPD consumers and collapse in
    set()-based feature lookups. Feature resolution is scoped to ## Feature
    Breakdown (R2.3), so the duplicate must live there."""
    vb = _load_validate_blueprint()
    blueprint_dir = _make_minimal_plan_dir(tmp_path)
    # Overwrite PLAN.md so ## Feature Breakdown carries two ### F1: blocks.
    plan = blueprint_dir / "PLAN.md"
    text = plan.read_text(encoding="utf-8").replace(
        "## Feature Breakdown\n### F1: feature\n",
        "## Feature Breakdown\n### F1: feature\n\n### F1: duplicate of feature 1\n\nbody\n",
    )
    plan.write_text(text, encoding="utf-8")
    result = vb.validate_plan(blueprint_dir)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    dup = [c for c in failures if c[0] == "PLAN.md feature numbers are unique"]
    assert dup, f"expected duplicate-feature FAIL; got: {failures}"
    assert "F1" in dup[0][2]


def test_validate_plan_specs_walk_honors_project_root_non_sibling(tmp_path):
    """R3.3: on a non-sibling layout (docs/blueprint/ + repo-root specs/), the
    specs/ walk must honor --project-root instead of hard-coding
    blueprint_dir.parent (which would look in docs/specs/ and find nothing)."""
    vb = _load_validate_blueprint()
    (tmp_path / ".git").mkdir()
    bp = tmp_path / "docs" / "blueprint"
    bp.mkdir(parents=True)
    # A malformed (`invalid`) spec dirname under the REPO-ROOT specs/.
    bad = tmp_path / "specs" / "F1_bad"
    bad.mkdir(parents=True)
    (bad / "spec.md").write_text("# x\n", encoding="utf-8")
    # Minimal PLAN.md so validate_plan reaches the specs walk.
    (bp / "PLAN.md").write_text(
        "# PLAN\n\n## Feature Breakdown\n### F1: f\n\n## MVP Definition\n\n"
        "## Feature Dependencies\n\n## Implementation Order\n\n## Milestones\n\n"
        "## Panel Review\n\n## Approval\n- [ ] Approved\n- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    for name in ("SCOPE.md", "ARCHITECTURE.md"):
        (bp / name).write_text(
            f"# {name}\n\n## Approval\n- [x] Approved\n- **Content Hash:** `abc123`\n",
            encoding="utf-8",
        )

    def _has_malformed(result):
        return any("malformed" in c[0].lower() or "F1_bad" in c[2] for c in result.checks)

    # With --project-root the walk finds repo-root specs/ and surfaces the warn;
    # without it, blueprint_dir.parent == docs/ has an empty specs walk.
    assert _has_malformed(vb.validate_plan(bp, project_root=tmp_path))
    assert not _has_malformed(vb.validate_plan(bp))


def test_validate_plan_unique_feature_numbers_pass(tmp_path):
    """A PLAN with distinct feature numbers PASSes the uniqueness check."""
    vb = _load_validate_blueprint()
    blueprint_dir = _make_minimal_plan_dir(tmp_path)  # single ### F1:
    result = vb.validate_plan(blueprint_dir)
    assert not any(
        c[0] == "PLAN.md feature numbers are unique" and c[1] == "FAIL"
        for c in result.checks
    )
    assert any(
        c[0] == "PLAN.md feature numbers are unique" and c[1] == "PASS"
        for c in result.checks
    )


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


# ============================================================================
# T9a: is_shipped symmetry with classify_spec STATE_SHIPPED (full state matrix)
# ============================================================================


def _bc():
    """Import blueprint_common from the shared scripts dir."""
    shared = str(_REPO_ROOT / "telescoping-sdd" / "scripts")
    if shared not in sys.path:
        sys.path.append(shared)
    import blueprint_common as bc  # noqa: E402

    return bc


def _stamp_doc(body: str) -> str:
    """Replace a `pending` Content Hash with the real hash (matches classify_spec fixtures)."""
    bc = _bc()
    return body.replace("`pending`", f"`{bc.compute_content_hash(body)}`")


def _approved_spec_md() -> str:
    body = (
        "# Feature: T\n\n**PLAN feature identifier:** `F1`\n\n"
        "## Objective\n\nx\n\n## Approval\n\n"
        "- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    return _stamp_doc(body)


def _approved_design_md() -> str:
    body = (
        "# Design\n\nstuff\n\n## Approval\n\n"
        "- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    return _stamp_doc(body)


def _approved_tasks_md(ticked: bool = True, narrative: bool = False) -> str:
    if narrative:
        tasks = "# Tasks\n\nThis feature is documentation-only.\n\n"
    else:
        box = "x" if ticked else " "
        tasks = f"# Tasks\n\n- [{box}] Implement\n- [{box}] Test\n\n"
    body = (
        tasks + "## Approval\n\n"
        "- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    return _stamp_doc(body)


def _build_state(tmp_path: Path, key: str) -> Path:
    """Build a spec dir for one of the six classify_spec states. Returns the dir."""
    d = tmp_path / f"F1-{key}"
    d.mkdir()
    if key == "not-started":
        return d  # no files
    if key == "pre-phase-1":
        (d / "spec.md").write_text("# Feature: T\n\nwip\n", encoding="utf-8")
        return d
    if key == "spec-only":
        (d / "spec.md").write_text(_approved_spec_md(), encoding="utf-8")
        return d
    if key == "tasks-ticked-without-stamp":
        # spec + design approved; tasks ticked AFTER stamping → stale hash.
        (d / "spec.md").write_text(_approved_spec_md(), encoding="utf-8")
        (d / "design.md").write_text(_approved_design_md(), encoding="utf-8")
        stamped = _approved_tasks_md(ticked=False)
        after_tick = stamped.replace("[ ]", "[x]", 1)
        (d / "tasks.md").write_text(after_tick, encoding="utf-8")
        return d
    if key == "narrative-only-tasks":
        (d / "spec.md").write_text(_approved_spec_md(), encoding="utf-8")
        (d / "design.md").write_text(_approved_design_md(), encoding="utf-8")
        (d / "tasks.md").write_text(_approved_tasks_md(narrative=True), encoding="utf-8")
        return d
    if key == "fully-shipped":
        (d / "spec.md").write_text(_approved_spec_md(), encoding="utf-8")
        (d / "design.md").write_text(_approved_design_md(), encoding="utf-8")
        (d / "tasks.md").write_text(_approved_tasks_md(ticked=True), encoding="utf-8")
        return d
    raise AssertionError(f"unknown state key {key!r}")


def test_is_shipped_symmetry(tmp_path: Path):
    """blueprint_common.is_shipped(spec_dir) is True IFF classify_spec reaches
    STATE_SHIPPED on the SAME fixture — over the full classify_spec state matrix.

    The six states exercise the full three-artifact domain (not just the
    spec+design-approved sub-domain): only `fully-shipped` should be shipped;
    every other state — including the tricky tasks-ticked-without-stamp and
    narrative-only-tasks cases — must be NOT shipped on BOTH sides. If this
    test fails, the T9a relocation diverged from classify_spec's verdict.
    """
    vb = _load_validate_blueprint()
    bc = _bc()

    matrix = [
        ("not-started", False),
        ("pre-phase-1", False),
        ("spec-only", False),
        ("tasks-ticked-without-stamp", False),
        ("narrative-only-tasks", False),
        ("fully-shipped", True),
    ]
    for key, expect_shipped in matrix:
        d = _build_state(tmp_path, key)
        classified_shipped = vb.classify_spec(d).state == vb.STATE_SHIPPED
        shared_shipped = bc.is_shipped(d)
        assert classified_shipped == expect_shipped, (
            f"classify_spec for state {key!r}: expected shipped={expect_shipped}, "
            f"got {classified_shipped}"
        )
        # The core invariant: the shared predicate agrees with the validator IFF.
        assert shared_shipped == classified_shipped, (
            f"is_shipped/{key}={shared_shipped} disagrees with "
            f"classify_spec STATE_SHIPPED={classified_shipped}"
        )


# ============================================================================
# T9b: `**Implemented by:**` positional per-feature parsing (I8)
# ============================================================================

import ast as _ast


def _impl_by_failures(result):
    return [c for c in result.checks if c[1] == "FAIL" and "Implemented by" in c[0]]


def _run_impl_by(plan_content: str):
    vb = _load_validate_blueprint()
    from blueprint_common import ValidationResult  # noqa: E402

    result = ValidationResult()
    parsed = vb._parse_implemented_by(plan_content, result)
    return parsed, result


def test_implemented_by_valid():
    """A valid `**Implemented by:** vps-edge` binds to its feature with no FAIL."""
    plan = (
        "## Feature Breakdown\n\n"
        "### F1: alpha\n**Implemented by:** vps-edge\n**Component:** X\n"
    )
    parsed, result = _run_impl_by(plan)
    assert parsed == {1: "vps-edge"}
    assert _impl_by_failures(result) == []
    # Backtick-wrapped value is also accepted.
    plan_bt = "## Feature Breakdown\n\n### F1: a\n**Implemented by:** `vps-edge`\n"
    parsed_bt, result_bt = _run_impl_by(plan_bt)
    assert parsed_bt == {1: "vps-edge"}
    assert _impl_by_failures(result_bt) == []


def test_implemented_by_canonical_bulleted_form():
    """The canonical PLAN layout writes the field as a BULLET below the AC list.

    Regression guard for code-review #2: the producer-side patterns must match
    `- **Implemented by:** <alias>` (the form the consumers `reconcile` and
    `master_feature` already match) or the malformed/duplicate gates never fire
    on a correctly-authored PLAN. The earlier tests dodge this by using the
    non-bulleted form.
    """
    # Valid bulleted field, sitting BELOW the AC list as in the data model.
    plan = (
        "## Feature Breakdown\n\n"
        "### F1: alpha\n"
        "- **Description:** Sync the records.\n"
        "- **Acceptance Criteria:**\n"
        "  - Records arrive at the edge.\n"
        "- **Implemented by:** vps-edge\n"
        "- **Component:** Sync engine\n"
    )
    parsed, result = _run_impl_by(plan)
    assert parsed == {1: "vps-edge"}
    assert _impl_by_failures(result) == []

    # A malformed bulleted value still FAILs (gate is not blind to the bullet).
    bad = (
        "## Feature Breakdown\n\n"
        "### F1: a\n- **Implemented by:** Bad_Alias\n"
    )
    parsed_bad, result_bad = _run_impl_by(bad)
    assert parsed_bad == {}
    fails = _impl_by_failures(result_bad)
    assert len(fails) == 1
    assert "implemented-by-malformed" in fails[0][2]

    # Two bulleted fields in one block still trip the duplicate gate.
    dup = (
        "## Feature Breakdown\n\n"
        "### F1: a\n- **Implemented by:** one\n- **Implemented by:** two\n"
    )
    parsed_dup, result_dup = _run_impl_by(dup)
    assert parsed_dup == {}
    dup_fails = _impl_by_failures(result_dup)
    assert len(dup_fails) == 1
    assert "implemented-by-duplicate" in dup_fails[0][2]


def test_implemented_by_absent_no_warn():
    """No FAIL or WARN when the field is absent on every feature."""
    plan = "## Feature Breakdown\n\n### F1: a\n**Component:** X\n\n### F2: b\n**Component:** Y\n"
    parsed, result = _run_impl_by(plan)
    assert parsed == {}
    # Absence is fully silent — no checks of any severity emitted by the parser.
    assert result.checks == []


def test_implemented_by_malformed():
    """Empty / wrong-case / bad-char values → implemented-by-malformed FAIL."""
    for bad in ("Bad_Case", "UPPER", "has space", "trailing-", "", "bad_char"):
        plan = f"## Feature Breakdown\n\n### F1: a\n**Implemented by:** {bad}\n"
        parsed, result = _run_impl_by(plan)
        assert parsed == {}, f"malformed value {bad!r} must not bind"
        fails = _impl_by_failures(result)
        assert len(fails) == 1, f"expected one FAIL for {bad!r}, got {fails}"
        assert "well-formed" in fails[0][0]
        assert "implemented-by-malformed" in fails[0][2]


def test_implemented_by_duplicate():
    """Two `**Implemented by:**` lines in one feature block → implemented-by-duplicate FAIL."""
    plan = (
        "## Feature Breakdown\n\n"
        "### F1: a\n**Implemented by:** one\n**Implemented by:** two\n"
    )
    parsed, result = _run_impl_by(plan)
    assert parsed == {}, "a duplicate-bearing feature must not bind a value"
    fails = _impl_by_failures(result)
    assert len(fails) == 1
    assert "single" in fails[0][0]
    assert "implemented-by-duplicate" in fails[0][2]


def test_implemented_by_preamble_ignored():
    """`**Implemented by:**` before the first `### F<n>` attaches to no feature
    and is silently ignored (not even a malformed check)."""
    plan = (
        "# PLAN\n\n**Implemented by:** Bad_Case_In_Preamble\n\n"
        "## Feature Breakdown\n\n### F1: a\n**Implemented by:** real-proj\n"
    )
    parsed, result = _run_impl_by(plan)
    # Only F1's value binds; the preamble occurrence is invisible (no FAIL even
    # though its value is malformed, because it is out of any feature's scope).
    assert parsed == {1: "real-proj"}
    assert _impl_by_failures(result) == []


def test_implemented_by_positional_scope():
    """Two features each with their own `**Implemented by:**` — each binds to its
    own block (positional scoping), not cross-contaminated."""
    plan = (
        "## Feature Breakdown\n\n"
        "### F1: alpha\n**Implemented by:** alpha-proj\n**Component:** X\n\n"
        "### F2: beta\n**Implemented by:** beta-proj\n**Component:** Y\n\n"
        "## MVP Definition\n\nF1, F2\n"
    )
    parsed, result = _run_impl_by(plan)
    assert parsed == {1: "alpha-proj", 2: "beta-proj"}
    assert _impl_by_failures(result) == []


def test_implemented_by_reuses_master_feature_boundary():
    """Structural assertion (mirrors test_no_inline_dirname_regexes_in_validators):
    `_parse_implemented_by` reuses master_feature's `### F<n>` block-boundary
    detection and introduces NO second inline feature-heading boundary regex.
    """
    vb = _load_validate_blueprint()
    # master_feature is imported as a module and its boundary primitives are the
    # ones the parser uses (live-object reuse, not a re-derived copy).
    import master_feature  # noqa: E402

    assert vb.master_feature is master_feature
    # `_parse_implemented_by` enumerates blocks via `iter_feature_blocks`; the
    # underlying boundary primitives remain available on the module.
    assert hasattr(master_feature, "iter_feature_blocks")
    assert hasattr(master_feature, "_find_feature_block")
    assert hasattr(master_feature, "_FEATURE_HEADING")

    # AST scan: inside _parse_implemented_by, there must be no inline re.compile/
    # re.match/re.search/re.finditer with a string literal that looks like a
    # `### F<n>` feature-heading boundary regex (the boundary must come from
    # master_feature, not a second copy here).
    source = (
        Path(__file__).resolve().parents[1] / "validate_blueprint.py"
    ).read_text(encoding="utf-8")
    tree = _ast.parse(source)

    def _inline_feature_heading_regexes(func_name):
        found = []
        for node in _ast.walk(tree):
            if not (isinstance(node, _ast.FunctionDef) and node.name == func_name):
                continue
            for child in _ast.walk(node):
                if not isinstance(child, _ast.Call):
                    continue
                func = child.func
                is_re_call = (
                    isinstance(func, _ast.Attribute)
                    and func.attr in {"compile", "match", "search", "finditer", "fullmatch"}
                    and isinstance(func.value, _ast.Name)
                    and func.value.id == "re"
                )
                if not is_re_call:
                    continue
                if child.args and isinstance(child.args[0], _ast.Constant):
                    val = child.args[0].value
                    if isinstance(val, str) and ("### F" in val or "###" in val and "F(" in val):
                        found.append(_ast.unparse(child))
        return found

    assert _inline_feature_heading_regexes("_parse_implemented_by") == [], (
        "_parse_implemented_by must not inline a `### F<n>` boundary regex; "
        "reuse master_feature.iter_feature_blocks instead"
    )


def test_approval_hash_grammar_comes_from_blueprint_common():
    """code-review #7: the narrow approval-hash regex is the shared
    blueprint_common.APPROVAL_HASH_LINE_STRICT, not a local copy — so it can't
    drift from validate_spec's gate."""
    vb = _load_validate_blueprint()
    import blueprint_common as bc  # noqa: E402

    assert vb.APPROVAL_HASH_LINE is bc.APPROVAL_HASH_LINE_STRICT


def test_implemented_by_integrated_in_validate_plan(tmp_path):
    """A malformed `**Implemented by:**` surfaces as a FAIL through the full
    validate_plan path (not just the unit helper)."""
    vb = _load_validate_blueprint()
    blueprint_dir = _make_minimal_plan_dir(
        tmp_path,
        plan_extra="",
    )
    # Inject a malformed Implemented by into the F1 feature block.
    plan = blueprint_dir / "PLAN.md"
    body = plan.read_text(encoding="utf-8")
    body = body.replace(
        "### F1: feature\n",
        "### F1: feature\n**Implemented by:** Bad_Case\n",
    )
    plan.write_text(body, encoding="utf-8")
    result = vb.validate_plan(blueprint_dir)
    fails = [c for c in result.checks if c[1] == "FAIL" and "Implemented by" in c[0]]
    assert fails, f"expected an Implemented by FAIL through validate_plan; got {result.checks}"
    assert "implemented-by-malformed" in fails[0][2]


# ---------------------------------------------------------------------------
# T11 — CPD derived-dir exclusion + registry-read-once (I10)
# ---------------------------------------------------------------------------


def _make_spec_dirs(project_root: Path, names) -> None:
    """Create empty spec/<name> directories under project_root/specs/."""
    specs_root = project_root / "specs"
    specs_root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (specs_root / name).mkdir()


def _make_sibling_repo(parent: Path, name: str) -> Path:
    """Create a directory that passes find_sibling's accept-gate (contains a
    `.sdd/` marker so it `_looks_like_project_root`). Returns the sibling root."""
    sib = parent / name
    (sib / ".sdd").mkdir(parents=True)
    return sib


def test_derived_dir_excluded_with_sibling(tmp_path: Path):
    """A derived-form dir whose master IS configured as a sibling is excluded from
    coverage (not a SpecState) AND emits NO derived-dir-no-sibling WARN."""
    vb = _load_validate_blueprint()
    import project_registry  # noqa: E402

    # Two sibling repos live side-by-side under tmp_path: the derived project and
    # its master ("residents"). The derived project's registry names the master.
    project_root = tmp_path / "vps-edge"
    project_root.mkdir()
    _make_sibling_repo(tmp_path, "residents")
    project_registry.write_projects_config(
        project_root,
        {
            "schemaVersion": 1,
            "thisProject": "vps-edge",
            "siblings": [
                {"name": "residents", "path": "../residents", "role": "master"}
            ],
        },
    )
    _make_spec_dirs(project_root, ["residents--F7-resident-sync"])

    entries = vb._classified_spec_entries(project_root)
    # Sanity: the directory classified as "derived".
    assert [c for _, c in entries] == ["derived"]

    # Excluded from coverage (no SpecState).
    states = vb._states_from_entries(entries)
    assert states == []

    # Sibling configured → no informational WARN.
    from blueprint_common import ValidationResult  # noqa: E402

    registry = project_registry.read_projects_config(project_root)
    assert registry is not None
    result = ValidationResult()
    vb._emit_derived_dir_warns(entries, registry, project_root, result)
    assert [c for c in result.checks if c[0] == "derived-dir-no-sibling"] == []


def test_derived_dir_informational_warn_no_sibling(tmp_path: Path):
    """A derived-form dir with NO matching sibling configured emits a
    derived-dir-no-sibling WARN naming the master project and asking intent."""
    vb = _load_validate_blueprint()
    import project_registry  # noqa: E402
    from blueprint_common import Severity, ValidationResult  # noqa: E402

    project_root = tmp_path / "vps-edge"
    project_root.mkdir()
    # No projects.json at all → registry is None → no matching sibling.
    _make_spec_dirs(project_root, ["residents--F7-resident-sync"])

    entries = vb._classified_spec_entries(project_root)
    assert [c for _, c in entries] == ["derived"]
    # Still excluded from coverage regardless of sibling state.
    assert vb._states_from_entries(entries) == []

    registry = project_registry.read_projects_config(project_root)
    assert registry is None
    result = ValidationResult()
    vb._emit_derived_dir_warns(entries, registry, project_root, result)

    warns = [c for c in result.checks if c[0] == "derived-dir-no-sibling"]
    assert len(warns) == 1
    name, sev, detail = warns[0]
    assert sev == Severity.WARN
    assert "residents" in detail  # names the master project
    assert "intentional" in detail.lower()  # asks if intentional


def test_bound_standalone_unaffected_by_derived_exclusion(tmp_path: Path):
    """Bound and standalone dirs (no `--`) are untouched by the derived branch:
    bound still becomes a SpecState; standalone is still silently skipped; neither
    earns a derived-dir-no-sibling WARN."""
    vb = _load_validate_blueprint()
    import project_registry  # noqa: E402
    from blueprint_common import ValidationResult  # noqa: E402

    project_root = tmp_path / "proj"
    project_root.mkdir()
    _make_spec_dirs(
        project_root,
        ["F3-local-feature", "some-standalone-thing"],
    )

    entries = vb._classified_spec_entries(project_root)
    cats = {name.name: cat for (name, cat) in entries}
    assert cats == {
        "F3-local-feature": "bound",
        "some-standalone-thing": "standalone",
    }

    # Bound → exactly one SpecState (feature id 3); standalone skipped.
    states = vb._states_from_entries(entries)
    assert [s.feature_id for s in states] == [3]

    # No derived dirs → no derived WARN regardless of registry.
    result = ValidationResult()
    vb._emit_derived_dir_warns(entries, None, project_root, result)
    assert [c for c in result.checks if c[0] == "derived-dir-no-sibling"] == []


def test_single_walk_derived_excluded_from_both(tmp_path: Path):
    """ONE _classified_spec_entries walk over {derived, bound, truly-invalid}: the
    derived dir is in NEITHER the states list NOR the malformed-WARN set; the
    invalid dir still warns; the bound dir still becomes a SpecState."""
    vb = _load_validate_blueprint()
    from blueprint_common import ValidationResult  # noqa: E402

    project_root = tmp_path / "vps-edge"
    project_root.mkdir()
    _make_spec_dirs(
        project_root,
        [
            "residents--F7-resident-sync",  # derived
            "F3-local-feature",             # bound
            "My_Invalid_Dir",               # invalid
        ],
    )

    # SINGLE walk feeds both consumers.
    entries = vb._classified_spec_entries(project_root)
    cats = {name.name: cat for (name, cat) in entries}
    assert cats["residents--F7-resident-sync"] == "derived"
    assert cats["F3-local-feature"] == "bound"
    assert cats["My_Invalid_Dir"] == "invalid"

    # (1) States list: derived excluded, bound included, invalid excluded.
    states = vb._states_from_entries(entries)
    state_names = {s.spec_dir.name for s in states}
    assert "residents--F7-resident-sync" not in state_names
    assert "F3-local-feature" in state_names

    # (2) Malformed-WARN set: derived NOT warned; invalid IS warned.
    warn_result = ValidationResult()
    vb._emit_malformed_dirname_warns(entries, warn_result)
    malformed = [
        c for c in warn_result.checks if c[0] == "malformed-spec-dirname"
    ]
    malformed_text = " ".join(detail for _, _, detail in malformed)
    assert "residents--F7-resident-sync" not in malformed_text
    assert "My_Invalid_Dir" in malformed_text
