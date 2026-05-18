"""Tests for the consumer-side CFC machinery in validate_spec.py.

Covers per CFC.md consumer-side test cases:
  * Identifier-line skip rule (5 cases per M5/P7/Q11)
  * Spec.md [CFC-N] tag presence on THEN lines (test 5, 6, 8, 9)
  * Tasks.md [CFC-N] enforcement-task tag (test 15)
  * Mid-stream drift WARN (test 11)
  * n/a + PLAN-with-CFCs opt-out warn (test 14, Q11)
  * Whole-number tag parsing — M2 prefix-collision (test 9)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _load_validate_spec():
    scripts_dir = Path(__file__).resolve().parents[1]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    if "validate_spec" in sys.modules:
        return importlib.reload(sys.modules["validate_spec"])
    return importlib.import_module("validate_spec")


vs = _load_validate_spec()


def _approved_spec(
    feature_id: str,
    requirements_body: str = "R1\n\n**Acceptance Criteria:**\n\n- GIVEN x\n  WHEN y\n  THEN z\n",
) -> str:
    full = (
        f"# Feature: T\n\n"
        f"**PLAN feature identifier:** `{feature_id}`\n\n"
        f"## Objective\n\nx\n\n"
        f"## Requirements\n\n{requirements_body}\n\n"
        f"## Approval\n\n- [x] Approved\n- **Content Hash:** `pending`\n"
    )
    h = vs.compute_content_hash(full)
    return full.replace("`pending`", f"`{h}`")


def _make_project(
    tmp_path: Path,
    feature_id: str = "F1",
    spec_content: str = None,
    tasks_content: str = None,
    plan_content: str = None,
) -> Path:
    if plan_content is not None:
        blueprint = tmp_path / "blueprint"
        blueprint.mkdir(parents=True, exist_ok=True)
        (blueprint / "PLAN.md").write_text(plan_content, encoding="utf-8")
    spec_dir = tmp_path / "specs" / feature_id
    spec_dir.mkdir(parents=True, exist_ok=True)
    if spec_content is not None:
        (spec_dir / "spec.md").write_text(spec_content, encoding="utf-8")
    if tasks_content is not None:
        (spec_dir / "tasks.md").write_text(tasks_content, encoding="utf-8")
    return spec_dir


def _plan_with_cfc(participating: str = "F1", enforcement: str = "no owning feature") -> str:
    feature_ids = [t.strip() for t in participating.split(",")]
    feature_block = "\n\n".join(
        f"### {fid}: T\n\n- **Description:** d\n- **Component:** c"
        for fid in feature_ids
    )
    return (
        "# Plan\n\n"
        "## Feature Breakdown\n\n"
        f"{feature_block}\n\n"
        "## MVP Definition\n\n"
        "MVP: " + ", ".join(feature_ids) + "\n\n"
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: Test contract\n\n"
        f"- **Participating features:** {participating}\n"
        "- **Contract:** test rule\n"
        "- **Per-feature AC:** WHEN x THEN y\n"
        f"- **Enforcement:** {enforcement}\n\n"
        "## Panel Review\n"
    )


def _plan_without_cfc() -> str:
    return (
        "# Plan\n\n"
        "## Feature Breakdown\n\n"
        "### F1: T\n\n- **Description:** d\n- **Component:** c\n\n"
        "## MVP Definition\n\nMVP: F1\n\n"
        "## Panel Review\n"
    )


def test_identifier_line_absent_fails(tmp_path: Path):
    spec_md = (
        "# Feature: T\n\n## Objective\n\nx\n\n## Requirements\n\nR1\n"
        "## Approval\n\n- [x] Approved\n- **Content Hash:** `pending`\n"
    )
    h = vs.compute_content_hash(spec_md)
    spec_md = spec_md.replace("`pending`", f"`{h}`")
    spec_dir = _make_project(tmp_path, spec_content=spec_md)
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("missing required `**PLAN feature identifier:**`" in c[2] for c in failures)


def test_identifier_na_no_plan_skips(tmp_path: Path):
    spec_md = _approved_spec("n/a")
    spec_dir = _make_project(tmp_path, spec_content=spec_md)
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    binding_checks = [c for c in result.checks if "CFC" in c[0]]
    assert binding_checks == []


def test_identifier_na_with_stale_cfc_tags_warns(tmp_path: Path):
    """Decision B — `n/a` identifier with [CFC-N] tags in spec.md must emit a per-tag WARN.

    A user downgrading from F<n> to `n/a` (intentional or accidental) may leave
    stale `[CFC-N]` tags in place. Without this WARN, the binding silently dies.
    """
    spec_md = _approved_spec(
        "n/a",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z [CFC-1] [CFC-3]\n"
        ),
    )
    spec_dir = _make_project(tmp_path, spec_content=spec_md)  # no PLAN.md
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    warns = [c for c in result.checks if c[1] == "WARN"]
    assert any(
        "[CFC-1]" in c[2] and "[CFC-3]" in c[2] and "stale" in c[2].lower()
        for c in warns
    )


def test_identifier_na_no_stale_tags_no_warn(tmp_path: Path):
    """Decision B regression guard — `n/a` without any tags must not emit the stale-tag WARN."""
    spec_md = _approved_spec("n/a")  # standard fixture has no [CFC-N] tags
    spec_dir = _make_project(tmp_path, spec_content=spec_md)  # no PLAN.md
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    warns = [c for c in result.checks if c[1] == "WARN"]
    assert not any("stale" in c[2].lower() for c in warns)


def test_identifier_na_plan_with_cfc_warns(tmp_path: Path):
    spec_md = _approved_spec("n/a")
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, plan_content=_plan_with_cfc()
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    warns = [c for c in result.checks if c[1] == "WARN"]
    assert any("declares `n/a`" in c[2] for c in warns)


def test_identifier_fn_no_plan_fails(tmp_path: Path):
    spec_md = _approved_spec("F1")
    spec_dir = _make_project(tmp_path, spec_content=spec_md)
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("no blueprint/PLAN.md exists" in c[2] for c in failures)


def test_identifier_unknown_fn_fails(tmp_path: Path):
    spec_md = _approved_spec("F99")
    spec_dir = _make_project(
        tmp_path, feature_id="F99", spec_content=spec_md,
        plan_content=_plan_without_cfc(),
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("not found in" in c[2] and "Feature Breakdown" in c[2] for c in failures)


def test_identifier_resolves_happy_path(tmp_path: Path):
    spec_md = _approved_spec("F1")
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, plan_content=_plan_without_cfc()
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    warns = [c for c in result.checks if c[1] == "WARN"]
    assert failures == []
    assert warns == []


def test_spec_missing_cfc_tag_fails(tmp_path: Path):
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z\n"
        ),
    )
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, plan_content=_plan_with_cfc("F1")
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("[CFC-1]" in c[0] for c in failures)


def test_spec_with_cfc_tag_on_then_passes(tmp_path: Path):
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
        ),
    )
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, plan_content=_plan_with_cfc("F1")
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert failures == []


def test_spec_with_cfc_tag_on_given_doesnt_satisfy(tmp_path: Path):
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x [CFC-1]\n  WHEN y\n  THEN z\n"
        ),
    )
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, plan_content=_plan_with_cfc("F1")
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("[CFC-1]" in c[0] for c in failures)


def test_spec_cfc_tag_whole_number_no_prefix_collision(tmp_path: Path):
    plan = _plan_with_cfc("F1")
    plan = plan.replace(
        "## Panel Review",
        "### CFC-10: Other\n\n"
        "- **Participating features:** F1\n"
        "- **Contract:** another rule\n"
        "- **Per-feature AC:** WHEN p THEN q\n"
        "- **Enforcement:** no owning feature\n\n"
        "## Panel Review",
    )
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z [CFC-10]\n"
        ),
    )
    spec_dir = _make_project(tmp_path, spec_content=spec_md, plan_content=plan)
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("[CFC-1]" in c[0] for c in failures)


def test_spec_orphan_tag_warns(tmp_path: Path):
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z [CFC-99]\n"
        ),
    )
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, plan_content=_plan_with_cfc("F1")
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    warns = [c for c in result.checks if c[1] == "WARN"]
    assert any("[CFC-99]" in c[0] for c in warns)


def test_tasks_missing_enforcement_tag_fails(tmp_path: Path):
    plan = _plan_with_cfc(
        participating="F1",
        enforcement="F1 owns the ArchUnit rule NoDirectAuditLogWrite",
    )
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
        ),
    )
    tasks_md = "# Tasks\n\n- [ ] Do thing\n- [ ] Another thing\n"
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, tasks_content=tasks_md, plan_content=plan
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, tasks_md, "tasks", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("enforcement task" in c[0].lower() for c in failures)


def test_tasks_enforcement_tag_present_passes(tmp_path: Path):
    plan = _plan_with_cfc(
        participating="F1",
        enforcement="F1 owns the ArchUnit rule NoDirectAuditLogWrite",
    )
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
        ),
    )
    tasks_md = (
        "# Tasks\n\n"
        "- [ ] Implement OperatorAuditLogWriter [CFC-1]\n"
        "- [ ] Other task\n"
    )
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, tasks_content=tasks_md, plan_content=plan
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, tasks_md, "tasks", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert failures == []


def test_tasks_no_enforcement_owner_no_obligation(tmp_path: Path):
    plan = _plan_with_cfc(
        participating="F1",
        # Authoring rule: name F<n> ONLY when owning. F36 owns; F1 is not named.
        enforcement="F36 owns the ArchUnit rule",
    )
    plan = plan.replace(
        "## MVP Definition",
        "### F36: O\n\n- **Description:** d\n- **Component:** c\n\n## MVP Definition",
    )
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
        ),
    )
    tasks_md = "# Tasks\n\n- [ ] Do thing\n- [ ] Another thing\n"
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, tasks_content=tasks_md, plan_content=plan
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, tasks_md, "tasks", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert failures == []


def test_feature_id_resolves_from_feature_breakdown_only(tmp_path: Path):
    """P1-2 regression: `### F<n>:` headings outside `## Feature Breakdown` must
    NOT satisfy the identifier resolver.

    A `### F99:` heading inside `## Open Questions` or any other section
    should not silently make `**PLAN feature identifier:** F99` resolve.
    """
    spec_md = _approved_spec("F99")
    # PLAN has a real F1 in Feature Breakdown; an `### F99:` heading appears
    # ONLY inside `## Open Questions` (e.g., as an illustrative quote).
    plan = (
        "# Plan\n\n"
        "## Feature Breakdown\n\n"
        "### F1: T\n\n- **Description:** d\n- **Component:** c\n\n"
        "## MVP Definition\n\nMVP: F1\n\n"
        "## Open Questions\n\n"
        "Should we consider an illustrative example like:\n\n"
        "### F99: Hypothetical late-binding feature\n\n"
        "(Not a real feature; just for discussion.)\n\n"
        "## Panel Review\n"
    )
    spec_dir = _make_project(
        tmp_path, feature_id="F99", spec_content=spec_md, plan_content=plan
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any(
        "not found in" in c[2] and "Feature Breakdown" in c[2] for c in failures
    ), "F99 outside Feature Breakdown should not satisfy identifier resolution"


def test_approve_document_writes_atomically_on_failure(tmp_path: Path):
    """P1-12 regression: a failed approve_document leaves the original file intact.

    Simulates the failure path by passing a path that doesn't allow renaming
    (target is a directory). Verifies the temp file is cleaned up.
    """
    target = tmp_path / "is_a_dir"
    target.mkdir()
    try:
        vs.approve_document(target)
    except Exception:
        pass  # expected
    tmp = target.with_suffix(target.suffix + ".tmp")
    assert not tmp.exists(), "Tempfile leaked after failed atomic write"


def test_tag_in_wrong_location_distinct_diagnostic(tmp_path: Path):
    """P2-3 regression: a [CFC-N] tag on a GIVEN line emits a 'tag location' FAIL
    in addition to (or instead of) the 'missing tag' FAIL, pointing the author
    at the correct location."""
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x [CFC-1]\n  WHEN y\n  THEN z\n"
        ),
    )
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, plan_content=_plan_with_cfc("F1")
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("tag location" in c[0].lower() for c in failures), (
        f"Distinct 'tag location' diagnostic missing: {[c[0] for c in failures]}"
    )


def test_fenced_code_block_then_line_does_not_count_as_binding(tmp_path: Path):
    """P2-4 regression: a THEN ... [CFC-1] line inside a triple-backtick fenced
    code block (illustrative example) must NOT count as a real binding."""
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z\n\n"
            "Example shape (illustrative, not a binding):\n\n"
            "```\n"
            "  THEN illustrative-text [CFC-1]\n"
            "```\n"
        ),
    )
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, plan_content=_plan_with_cfc("F1")
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("[CFC-1]" in c[0] and "binding tag" in c[0] for c in failures), (
        "Tag inside fenced code block should not satisfy the binding check"
    )


def test_bullet_style_then_line_matches_binding(tmp_path: Path):
    """P2-5 regression: a `- THEN <assertion> [CFC-N]` bullet-style AC must satisfy
    the binding check the same as a narrative `THEN ...` line."""
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n"
            "- WHEN y\n"
            "- THEN z [CFC-1]\n"  # bullet-style THEN
        ),
    )
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, plan_content=_plan_with_cfc("F1")
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec_md, "spec", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    # The binding check passes (bullet-style THEN was matched).
    assert not any(
        "missing required CFC binding" in c[2].lower() for c in failures
    ), f"Bullet-style THEN was not recognised: {failures}"


def test_indented_sub_task_checkbox_satisfies_enforcement_obligation(tmp_path: Path):
    """P2-6 regression: an indented sub-task (`  - [ ] ...`) carrying a [CFC-N]
    tag satisfies the Phase-3 enforcement-task obligation."""
    plan = _plan_with_cfc(
        participating="F1",
        enforcement="F1 owns the ArchUnit rule NoDirectAuditLogWrite",
    )
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
        ),
    )
    # Top-level task with an indented sub-task carrying the binding tag.
    tasks_md = (
        "# Tasks\n\n"
        "- [ ] Implement NoDirectAuditLogWrite enforcement\n"
        "  - [ ] Write the ArchUnit rule [CFC-1]\n"
    )
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, tasks_content=tasks_md, plan_content=plan
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, tasks_md, "tasks", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert failures == [], (
        f"Indented sub-task tag should count: {failures}"
    )


def test_enforcement_owner_word_boundary_no_substring_match(tmp_path: Path):
    plan = _plan_with_cfc(
        participating="F1, F11",
        enforcement="F11 owns the ArchUnit rule",
    )
    plan = plan.replace(
        "## MVP Definition",
        "### F11: O\n\n- **Description:** d\n- **Component:** c\n\n## MVP Definition",
    )
    spec_md = _approved_spec(
        "F1",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
        ),
    )
    tasks_md = "# Tasks\n\n- [ ] Do thing\n"
    spec_dir = _make_project(
        tmp_path, spec_content=spec_md, tasks_content=tasks_md, plan_content=plan
    )
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, tasks_md, "tasks", result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert failures == []
