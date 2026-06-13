"""Tests for the CFC (Cross-Feature Contracts) machinery in validate_blueprint.py.

Covers per CFC.md test cases 1-30:
  * Producer-side CFC section parsing and field validation (1-3, 17-19)
  * Per-CFC content hashing (21)
  * Bound-spec classification (26)
  * Coverage walk and orphan-tag scan (15)
  * Word-boundary feature-ID matching (20)
  * Whole-number CFC tag matching, M2 prefix-collision (9, 16)
  * Owner-silent Enforcement WARN (13)
  * Trivial-edit carve-out structured hash properties (27)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _load_validate_blueprint():
    scripts_dir = Path(__file__).resolve().parents[1]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    if "validate_blueprint" in sys.modules:
        return importlib.reload(sys.modules["validate_blueprint"])
    return importlib.import_module("validate_blueprint")


vb = _load_validate_blueprint()


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------

def test_extract_cfc_section_present():
    plan = """# Plan
## Open Questions
nothing

## Cross-Feature Contracts

Body text here.

### CFC-1: Title

- **Participating features:** F1, F2

## Panel Review
"""
    section = vb.extract_cfc_section(plan)
    assert section is not None
    _start, _end, body = section
    assert "### CFC-1:" in body
    assert "## Panel Review" not in body


def test_extract_cfc_section_absent():
    plan = """# Plan
## Open Questions
nothing

## Panel Review
"""
    assert vb.extract_cfc_section(plan) is None


def test_near_miss_header_detected():
    plan = "# Plan\n\n## Cross-feature contracts\n\nbody\n"
    near = vb.detect_near_miss_cfc_header(plan)
    assert near is not None
    assert "Cross-feature contracts" in near


def test_near_miss_header_canonical_passes():
    plan = "# Plan\n\n## Cross-Feature Contracts\n\nbody\n"
    assert vb.detect_near_miss_cfc_header(plan) is None


def test_parse_cfc_entries_basic():
    body = """
### CFC-1: Lock order

- **Participating features:** F1, F3
- **Contract:** Locks must be acquired in canonical order.
- **Per-feature AC:** WHEN feature acquires locks, THEN canonical order.
- **Enforcement:** F36 owns the ArchUnit rule.

### CFC-2: Audit writer

- **Participating features:** F2, F4
- **Contract:** All writes through the writer class.
- **Per-feature AC:** WHEN writing audit logs, THEN via OperatorAuditLogWriter.
- **Enforcement:** F36 owns the ArchUnit rule NoDirectAuditLogWrite.
"""
    entries = vb.parse_cfc_entries(body)
    assert len(entries) == 2
    assert entries[0].number == 1
    assert entries[1].number == 2
    assert entries[0].title == "Lock order"
    assert entries[0].participating_features() == [1, 3]
    assert entries[1].participating_features() == [2, 4]


def test_parse_cfc_entries_detects_out_of_order_fields():
    body = """
### CFC-1: T

- **Contract:** prose
- **Participating features:** F1, F2
- **Per-feature AC:** ac
- **Enforcement:** F3 owns ArchUnit rule
"""
    entries = vb.parse_cfc_entries(body)
    assert entries[0].field_order_observed[0] == "Contract"
    assert entries[0].field_order_observed[1] == "Participating features"


# ---------------------------------------------------------------------------
# Field validation via validate_cfc_section
# ---------------------------------------------------------------------------

def _build_plan(cfc_section: str = "") -> str:
    return (
        "# Plan\n\n"
        "## Open Questions\n\n"
        "nothing\n\n"
        f"{cfc_section}"
        "## Panel Review\n\n"
        "blah\n"
    )


# Feature-id -> bound spec-directory name (1.7.0 grammar: specs/F<n>-<slug>/).
# Migrated from the pre-1.7.0 bare `specs/F<n>/` form so walk_specs no longer
# emits a `malformed-spec-dirname` WARN on these fixtures. Only the directory
# NAME changes — the in-file `**PLAN feature identifier:** F<n>` stays bare.
FEATURE_DIR_MAP = {1: "F1-alpha", 2: "F2-beta", 36: "F36-enforcement", 11: "F11-lock-order"}


def test_validate_cfc_section_missing_field_fails():
    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F2\n"
        "- **Contract:** prose\n"
        "- **Per-feature AC:** ac\n"
        # Enforcement missing
        "\n"
    )
    result = vb.ValidationResult()
    vb.validate_cfc_section(plan, result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("missing required field" in c[2].lower() for c in failures)


def test_validate_cfc_section_field_order_fails():
    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Contract:** prose\n"
        "- **Participating features:** F1, F2\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F3 owns ArchUnit rule\n"
        "\n"
    )
    result = vb.ValidationResult()
    vb.validate_cfc_section(plan, result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("canonical order" in c[0].lower() for c in failures)


def test_validate_cfc_section_participating_regex_dash_rejected():
    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F-1, F-2\n"  # dashes are wrong
        "- **Contract:** prose\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F3 owns ArchUnit rule\n"
        "\n"
    )
    result = vb.ValidationResult()
    vb.validate_cfc_section(plan, result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("regex" in c[0].lower() for c in failures)


def test_validate_cfc_section_duplicate_cfc_number_fails():
    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: First\n\n"
        "- **Participating features:** F1\n"
        "- **Contract:** prose\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F2 owns ArchUnit rule\n\n"
        "### CFC-1: Second\n\n"  # duplicate number
        "- **Participating features:** F2\n"
        "- **Contract:** prose\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F3 owns ArchUnit rule\n"
        "\n"
    )
    result = vb.ValidationResult()
    vb.validate_cfc_section(plan, result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("unique" in c[0].lower() and "CFC-1" in c[2] for c in failures)


def test_validate_cfc_section_owner_silent_warn_fires():
    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F2\n"
        "- **Contract:** prose\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** verified by an ArchUnit rule\n"  # no F<n>, no disclaimer
        "\n"
    )
    result = vb.ValidationResult()
    vb.validate_cfc_section(plan, result)
    warns = [c for c in result.checks if c[1] == "WARN"]
    assert any("Enforcement names owning feature" in c[0] for c in warns)


def test_validate_cfc_section_owner_silent_warn_suppressed_with_feature_token():
    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F2\n"
        "- **Contract:** prose\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** verified by F2's ArchUnit rule\n"
        "\n"
    )
    result = vb.ValidationResult()
    vb.validate_cfc_section(plan, result)
    warns = [c for c in result.checks if c[1] == "WARN"]
    assert not any("Enforcement names owning feature" in c[0] for c in warns)


def test_validate_cfc_section_owner_silent_warn_suppressed_with_co_owned_disclaimer():
    """P2-13 regression: the `co-owned by F<n>, F<m>` disclaimer suppresses the
    owner-silent Enforcement WARN the same as `no owning feature`."""
    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F2\n"
        "- **Contract:** prose\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** verified by an ArchUnit rule, co-owned by F1, F2\n"
        "\n"
    )
    result = vb.ValidationResult()
    vb.validate_cfc_section(plan, result)
    warns = [c for c in result.checks if c[1] == "WARN"]
    assert not any("Enforcement names owning feature" in c[0] for c in warns)


def test_multi_digit_cfc_number_does_not_substring_collide(tmp_path: Path):
    """P2-14 regression: [CFC-100] is parsed correctly and does not match against
    a feature looking for [CFC-1] or [CFC-10]."""
    body = (
        "### CFC-100: Many\n\n"
        "- **Participating features:** F1\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F2 owns ArchUnit rule\n"
    )
    entries = vb.parse_cfc_entries(body)
    assert len(entries) == 1
    assert entries[0].number == 100

    text = "THEN foo [CFC-100]"
    nums = vb.extract_cfc_tags(text)
    assert 100 in nums
    assert 1 not in nums
    assert 10 not in nums


def test_panel_review_md_contains_cfc_compliance_wording():
    """P2-2 / CFC.md test 16: regression-catcher that the rendered panel-review.md
    contains the prescribed CFC-compliance wording. Silent edit-drift would
    weaken the doctrine."""
    panel_review_path = (
        Path(__file__).resolve().parents[5]
        / "telescoping-sdd" / "skills" / "spec-driven-dev" / "references" / "panel-review.md"
    )
    content = panel_review_path.read_text(encoding="utf-8")
    assert "Cross-check this feature's artifact against every `### CFC-N`" in content
    assert "name the affected `CFC-<M>` in the concern text" in content


def test_validate_cfc_section_owner_silent_warn_suppressed_with_disclaimer():
    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F2\n"
        "- **Contract:** prose\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** verified by an ArchUnit rule (no owning feature)\n"
        "\n"
    )
    result = vb.ValidationResult()
    vb.validate_cfc_section(plan, result)
    warns = [c for c in result.checks if c[1] == "WARN"]
    assert not any("Enforcement names owning feature" in c[0] for c in warns)


def test_validate_cfc_section_near_miss_header_fails():
    plan = (
        "# Plan\n\n"
        "## Open Questions\n\nq\n\n"
        "## Cross-feature contracts\n\n"  # lowercase f
        "### CFC-1: T\n\n"
        "- **Participating features:** F1\n"
        "\n## Panel Review\n"
    )
    result = vb.ValidationResult()
    entries = vb.validate_cfc_section(plan, result)
    assert entries == []
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("header form" in c[0].lower() for c in failures)


def _plan_with_features_and_cfc(feature_headings: str, cfc_body: str) -> str:
    """A PLAN with a real Feature Breakdown plus a single CFC entry."""
    return (
        "# Plan\n\n"
        "## Feature Breakdown\n\n"
        f"{feature_headings}\n"
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        f"{cfc_body}\n"
        "## Panel Review\n\nblah\n"
    )


def test_validate_cfc_section_unknown_participating_feature_fails():
    """R1.6: a CFC naming a feature with no `### F<n>:` entry FAILs referential
    integrity (the typo / deleted-feature case that otherwise binds nothing)."""
    plan = _plan_with_features_and_cfc(
        "### F1: Alpha\n\nx\n\n### F2: Beta\n\nx\n",
        "- **Participating features:** F1, F9\n"  # F9 is undefined
        "- **Contract:** prose\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F1 owns the rule\n",
    )
    result = vb.ValidationResult()
    vb.validate_cfc_section(plan, result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("references only defined features" in c[0] for c in failures)
    assert any("F9" in c[2] for c in failures)


def test_validate_cfc_section_unknown_enforcement_feature_fails():
    """R1.6: an Enforcement clause naming a nonexistent owner also FAILs."""
    plan = _plan_with_features_and_cfc(
        "### F1: Alpha\n\nx\n\n### F2: Beta\n\nx\n",
        "- **Participating features:** F1, F2\n"
        "- **Contract:** prose\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F7 owns the ArchUnit rule\n",  # F7 undefined
    )
    result = vb.ValidationResult()
    vb.validate_cfc_section(plan, result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert any("references only defined features" in c[0] for c in failures)
    assert any("F7" in c[2] for c in failures)


def test_validate_cfc_section_all_defined_features_pass():
    """R1.6: when every named feature exists, the referential check PASSes."""
    plan = _plan_with_features_and_cfc(
        "### F1: Alpha\n\nx\n\n### F2: Beta\n\nx\n",
        "- **Participating features:** F1, F2\n"
        "- **Contract:** prose\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F1 owns the ArchUnit rule\n",
    )
    result = vb.ValidationResult()
    vb.validate_cfc_section(plan, result)
    failures = [c for c in result.checks if c[1] == "FAIL"]
    assert not any("references only defined features" in c[0] for c in failures)
    assert any(
        c[0] == "PLAN.md CFC-1 references only defined features" and c[1] == "PASS"
        for c in result.checks
    )


# ---------------------------------------------------------------------------
# Per-CFC content hashing
# ---------------------------------------------------------------------------

def test_structured_content_hash_stable_under_participating_reorder():
    body_a = (
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F3, F5\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F2 owns ArchUnit rule\n"
    )
    body_b = (
        "### CFC-1: T\n\n"
        "- **Participating features:** F5, F1, F3\n"  # reordered
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F2 owns ArchUnit rule\n"
    )
    h_a = vb.parse_cfc_entries(body_a)[0].structured_content_hash()
    h_b = vb.parse_cfc_entries(body_b)[0].structured_content_hash()
    assert h_a == h_b


def test_structured_content_hash_changes_with_substantive_edit():
    body_a = (
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F3\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** WHEN x THEN y in order A->B->C->D\n"
        "- **Enforcement:** F2 owns ArchUnit rule\n"
    )
    body_b = (
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F3\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** WHEN x THEN y in order A->B->D->C\n"  # D and C swapped
        "- **Enforcement:** F2 owns ArchUnit rule\n"
    )
    h_a = vb.parse_cfc_entries(body_a)[0].structured_content_hash()
    h_b = vb.parse_cfc_entries(body_b)[0].structured_content_hash()
    assert h_a != h_b


def test_normalize_for_hash_collapses_whitespace():
    assert vb._normalize_for_hash("a  b\tc") == "a b c"


def test_normalize_for_hash_handles_nbsp_distinctly():
    """NFC does not canonicalize NBSP (U+00A0) to space; whitespace-collapse only matches [ \\t]+."""
    assert vb._normalize_for_hash("a b") != vb._normalize_for_hash("a b")


def test_normalize_for_hash_strips_blank_line_runs():
    assert vb._normalize_for_hash("a\n\n\n\nb") == "a\n\nb"


# ---------------------------------------------------------------------------
# CFC tag extraction — whole-number, M2 prefix collision (CFC.md test 9, 16)
# ---------------------------------------------------------------------------

def test_cfc_tag_whole_number_no_prefix_collision():
    text = "THEN foo [CFC-10] and [CFC-12]"
    nums = vb.extract_cfc_tags(text)
    assert 1 not in nums
    assert 10 in nums
    assert 12 in nums


def test_then_line_only_extraction_rejects_given_tag():
    spec = (
        "**Acceptance Criteria:**\n\n"
        "- GIVEN setup [CFC-1]\n"
        "  WHEN action\n"
        "  THEN assertion\n"
    )
    # [CFC-1] is on the GIVEN line, not the THEN line — should not be picked up.
    assert vb.spec_then_line_cfc_tags(spec) == []


def test_then_line_extraction_finds_multi_tag():
    spec = (
        "**Acceptance Criteria:**\n\n"
        "- GIVEN setup\n"
        "  WHEN action\n"
        "  THEN assertion [CFC-1] [CFC-3]\n"
    )
    nums = vb.spec_then_line_cfc_tags(spec)
    assert sorted(nums) == [1, 3]


def test_word_boundary_feature_id_no_substring_match():
    """F1 inside F11 must not be matched as F1 (CFC.md test 20)."""
    text = "verified by F1 and F11 together"
    nums = [int(m.group(1)) for m in vb.FEATURE_ID_WORD_PATTERN.finditer(text)]
    assert sorted(nums) == [1, 11]


# ---------------------------------------------------------------------------
# Bound-spec classification (CFC.md test 26)
# ---------------------------------------------------------------------------

def _make_spec(
    spec_dir: Path,
    spec_md: str = None,
    design_md: str = None,
    tasks_md: str = None,
) -> None:
    spec_dir.mkdir(parents=True, exist_ok=True)
    if spec_md is not None:
        (spec_dir / "spec.md").write_text(spec_md, encoding="utf-8")
    if design_md is not None:
        (spec_dir / "design.md").write_text(design_md, encoding="utf-8")
    if tasks_md is not None:
        (spec_dir / "tasks.md").write_text(tasks_md, encoding="utf-8")


def _approved_spec(body: str) -> str:
    """Wrap `body` in an SDD-like spec.md with a valid ## Approval hash."""
    from blueprint_common import compute_content_hash

    full = (
        f"# Feature: T\n\n"
        f"**PLAN feature identifier:** `F1`\n\n"
        f"## Objective\n\nx\n\n"
        f"## Requirements\n\n{body}\n\n"
        f"## Approval\n\n"
        f"- [x] Approved to proceed to next phase\n"
        f"- **Content Hash:** `placeholder`\n"
    )
    h = compute_content_hash(full)
    return full.replace("`placeholder`", f"`{h}`")


def test_classify_spec_not_started(tmp_path: Path):
    spec_dir = tmp_path / "F1"
    spec_dir.mkdir()
    state = vb.classify_spec(spec_dir)
    assert state.state == vb.STATE_NOT_STARTED


def test_classify_spec_pre_phase_1(tmp_path: Path):
    spec_dir = tmp_path / "F1"
    _make_spec(spec_dir, spec_md="# Feature: T\n\nwip\n")  # no Approval
    state = vb.classify_spec(spec_dir)
    assert state.state == vb.STATE_PRE_PHASE_1


def test_classify_spec_in_flight_with_only_spec_approved(tmp_path: Path):
    spec_dir = tmp_path / "F1"
    _make_spec(spec_dir, spec_md=_approved_spec("R1: WHEN x THEN y [CFC-1]"))
    state = vb.classify_spec(spec_dir)
    assert state.state == vb.STATE_IN_FLIGHT


def test_classify_spec_shipped(tmp_path: Path):
    from blueprint_common import compute_content_hash

    spec_dir = tmp_path / "F1"
    spec_md = _approved_spec("R1: WHEN x THEN y [CFC-1]")
    design_md_body = "# Design\n\nstuff\n\n## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    design_md = design_md_body.replace(
        "`pending`", f"`{compute_content_hash(design_md_body)}`"
    )
    tasks_md_body = (
        "# Tasks\n\n- [x] Implement [CFC-1]\n- [x] Test\n\n"
        "## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    tasks_md = tasks_md_body.replace(
        "`pending`", f"`{compute_content_hash(tasks_md_body)}`"
    )
    _make_spec(spec_dir, spec_md=spec_md, design_md=design_md, tasks_md=tasks_md)
    state = vb.classify_spec(spec_dir)
    assert state.state == vb.STATE_SHIPPED


def test_classify_spec_narrative_only_tasks_md_is_in_flight(tmp_path: Path):
    """Narrative-only tasks.md (zero checkboxes) must NOT classify as shipped.

    Per CFC.md doctrine refinement (decision A from post-implementation review):
    `shipped` requires at least one ticked checkbox; the empty-set vacuous-truth
    case is rejected because there is no implementation work to make immutable.
    """
    from blueprint_common import compute_content_hash

    spec_dir = tmp_path / "F1"
    spec_md = _approved_spec("R1: WHEN x THEN y [CFC-1]")
    design_md_body = (
        "# Design\n\nstuff\n\n## Approval\n\n"
        "- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    design_md = design_md_body.replace(
        "`pending`", f"`{compute_content_hash(design_md_body)}`"
    )
    # Narrative-only tasks.md: no checkbox lines at all.
    tasks_md_body = (
        "# Tasks\n\nThis feature is documentation-only.\n\n"
        "## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    tasks_md = tasks_md_body.replace(
        "`pending`", f"`{compute_content_hash(tasks_md_body)}`"
    )
    _make_spec(spec_dir, spec_md=spec_md, design_md=design_md, tasks_md=tasks_md)
    state = vb.classify_spec(spec_dir)
    # Even though all artifacts are approved and the hash matches, the lack
    # of any ticked checkbox keeps the classifier on in-flight.
    assert state.state == vb.STATE_IN_FLIGHT


def test_classify_spec_in_flight_after_tick_without_stamp(tmp_path: Path):
    """All tasks ticked but tasks.md stamp is stale → still in-flight (CFC.md test 26 derived-coherence)."""
    from blueprint_common import compute_content_hash

    spec_dir = tmp_path / "F1"
    spec_md = _approved_spec("R1: WHEN x THEN y [CFC-1]")
    design_md_body = "# Design\n\nstuff\n\n## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    design_md = design_md_body.replace(
        "`pending`", f"`{compute_content_hash(design_md_body)}`"
    )
    # Stamp tasks.md with one unticked box; then tick it without re-stamping.
    tasks_md_pre = (
        "# Tasks\n\n- [ ] Implement [CFC-1]\n\n"
        "## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    tasks_md_stamped = tasks_md_pre.replace(
        "`pending`", f"`{compute_content_hash(tasks_md_pre)}`"
    )
    tasks_md_after_tick = tasks_md_stamped.replace("[ ]", "[x]", 1)
    _make_spec(
        spec_dir, spec_md=spec_md, design_md=design_md, tasks_md=tasks_md_after_tick
    )
    state = vb.classify_spec(spec_dir)
    # All boxes ticked but stored hash no longer matches → in-flight.
    assert state.state == vb.STATE_IN_FLIGHT


# ---------------------------------------------------------------------------
# Coverage walk + orphan-tag scan
# ---------------------------------------------------------------------------

def test_coverage_walk_fully_bound(tmp_path: Path):
    """All participating features have specs with the right CFC tag → fully-bound."""
    from blueprint_common import compute_content_hash

    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F2\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F3 owns ArchUnit rule\n\n"
    )
    entries = vb.parse_cfc_entries(vb.extract_cfc_section(plan)[2])

    # Build approved specs for F1 and F2 with [CFC-1] on THEN lines.
    project_root = tmp_path
    for fid in (1, 2):
        body = f"R1\n\n**Acceptance Criteria:**\n\n- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
        full = (
            f"# Feature: F{fid}\n\n"
            f"**PLAN feature identifier:** `F{fid}`\n\n"
            f"## Objective\n\nx\n\n"
            f"## Requirements\n\n{body}\n\n"
            f"## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
        )
        full = full.replace("`pending`", f"`{compute_content_hash(full)}`")
        _make_spec(project_root / "specs" / FEATURE_DIR_MAP[fid], spec_md=full)

    spec_states = vb.walk_specs(project_root)
    coverages = vb.compute_coverage(entries, spec_states)
    assert len(coverages) == 1
    assert coverages[0].status == "fully-bound"


def test_coverage_walk_partially_bound(tmp_path: Path):
    """One participant has the tag, another approved spec is missing it → partially-bound."""
    from blueprint_common import compute_content_hash

    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F2\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F3 owns ArchUnit rule\n\n"
    )
    entries = vb.parse_cfc_entries(vb.extract_cfc_section(plan)[2])

    project_root = tmp_path
    # F1 has tag
    body_f1 = "R1\n\n**Acceptance Criteria:**\n\n- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
    f1 = (
        f"# Feature: F1\n\n**PLAN feature identifier:** `F1`\n\n"
        f"## Objective\n\nx\n\n## Requirements\n\n{body_f1}\n\n"
        f"## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    f1 = f1.replace("`pending`", f"`{compute_content_hash(f1)}`")
    _make_spec(project_root / "specs" / "F1-alpha", spec_md=f1)
    # F2 lacks the tag
    body_f2 = "R1\n\n**Acceptance Criteria:**\n\n- GIVEN x\n  WHEN y\n  THEN z\n"
    f2 = (
        f"# Feature: F2\n\n**PLAN feature identifier:** `F2`\n\n"
        f"## Objective\n\nx\n\n## Requirements\n\n{body_f2}\n\n"
        f"## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    f2 = f2.replace("`pending`", f"`{compute_content_hash(f2)}`")
    _make_spec(project_root / "specs" / "F2-beta", spec_md=f2)

    spec_states = vb.walk_specs(project_root)
    coverages = vb.compute_coverage(entries, spec_states)
    assert coverages[0].status == "partially-bound"


def test_orphan_tag_tasks_md_enforcement_owner_not_departed(tmp_path: Path):
    """P1-1 regression: an enforcement-owner-only feature's tasks.md [CFC-N] tag
    is legitimate even when the feature is NOT in Participating features.

    Before this fix, F36 owning CFC-1's enforcement (named in Enforcement
    prose, not in Participating) but carrying [CFC-1] in F36/tasks.md was
    wrongly classified as `orphaned-departed`.
    """
    from blueprint_common import compute_content_hash

    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F2\n"
        "- **Contract:** rule\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F36 owns ArchUnit rule\n\n"
    )
    entries = vb.parse_cfc_entries(vb.extract_cfc_section(plan)[2])

    # Build F36's bound spec + tasks.md with [CFC-1] on a task line.
    # F36 is NOT in Participating but IS named as Enforcement owner.
    spec_body = "R1\n\n**Acceptance Criteria:**\n\n- GIVEN x\n  WHEN y\n  THEN z\n"
    spec_md = (
        f"# Feature: F36\n\n**PLAN feature identifier:** `F36`\n\n"
        f"## Objective\n\nx\n\n## Requirements\n\n{spec_body}\n\n"
        f"## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    spec_md = spec_md.replace("`pending`", f"`{compute_content_hash(spec_md)}`")

    tasks_md_body = (
        "# Tasks\n\n"
        "- [ ] Implement LockOrderCheck ArchUnit rule [CFC-1]\n\n"
        "## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    tasks_md = tasks_md_body.replace(
        "`pending`", f"`{compute_content_hash(tasks_md_body)}`"
    )
    _make_spec(tmp_path / "specs" / "F36-enforcement", spec_md=spec_md, tasks_md=tasks_md)

    spec_states = vb.walk_specs(tmp_path)
    orphans = vb.scan_orphan_tags(entries, spec_states, {})
    # F36's tasks.md tag must NOT be reported as orphaned-departed.
    assert not any(
        o.subtype == "orphaned-departed" and o.artifact == "tasks.md"
        for o in orphans
    ), f"Enforcement-owner tag wrongly flagged: {[o.message for o in orphans]}"


def test_orphan_tag_spec_md_still_requires_participating(tmp_path: Path):
    """P1-1 regression complement: a spec.md tag for a non-Participating feature
    IS legitimately `orphaned-departed`, even if the feature is an Enforcement owner.

    spec.md tags signal "this feature participates"; enforcement ownership
    alone doesn't legitimize the tag on a feature's own spec.md.
    """
    from blueprint_common import compute_content_hash

    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F1, F2\n"
        "- **Contract:** rule\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F36 owns ArchUnit rule\n\n"
    )
    entries = vb.parse_cfc_entries(vb.extract_cfc_section(plan)[2])

    # F36 is NOT in Participating. A [CFC-1] tag on its OWN spec.md THEN line
    # is wrong (the spec says "F36 participates in CFC-1" but PLAN disagrees).
    body = (
        "R1\n\n**Acceptance Criteria:**\n\n"
        "- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
    )
    spec_md = (
        f"# Feature: F36\n\n**PLAN feature identifier:** `F36`\n\n"
        f"## Objective\n\nx\n\n## Requirements\n\n{body}\n\n"
        f"## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    spec_md = spec_md.replace("`pending`", f"`{compute_content_hash(spec_md)}`")
    _make_spec(tmp_path / "specs" / "F36-enforcement", spec_md=spec_md)

    spec_states = vb.walk_specs(tmp_path)
    orphans = vb.scan_orphan_tags(entries, spec_states, {})
    assert any(
        o.subtype == "orphaned-departed" and o.artifact == "spec.md"
        for o in orphans
    )


def test_walk_specs_skips_symlinks(tmp_path: Path):
    """P1-7 regression: symlinks inside specs/ must be skipped, not followed.

    A symlinked F<n> directory could otherwise coerce the validator to read
    arbitrary files outside the project tree.
    """
    (tmp_path / "specs").mkdir()
    # Real directory: F1
    real = tmp_path / "specs" / "F1-alpha"
    real.mkdir()
    # Symlinked directory: F99 → somewhere outside.
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "specs" / "F99").symlink_to(outside, target_is_directory=True)

    states = vb.walk_specs(tmp_path)
    feature_ids = sorted(s.feature_id for s in states)
    assert 1 in feature_ids
    assert 99 not in feature_ids, "Symlinked F99 was followed; should be skipped"


def test_field_regex_empty_participating_features_does_not_swallow_next_line():
    """P1-9 regression: an empty `**Participating features:**` value must NOT
    cause the next line (`- **Contract:** ...`) to be captured as the value.

    Before this fix, `\\s*(.+)$` matched a trailing space + newline and slurped
    the Contract line; the user saw "Contract is missing" instead of the
    actual problem "Participating features value is empty."
    """
    body = (
        "### CFC-1: T\n\n"
        "- **Participating features:** \n"  # trailing space, empty value
        "- **Contract:** real contract text\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F2 owns ArchUnit rule\n"
    )
    entries = vb.parse_cfc_entries(body)
    assert len(entries) == 1
    entry = entries[0]
    # Participating features captured the (empty/whitespace) value — the
    # `[ \t]*` after the marker no longer eats the newline.
    pf_value = entry.fields["Participating features"]
    # Either None (didn't match because empty after horizontal-ws) or empty.
    # In either case, the Contract field MUST be captured separately.
    assert (
        entry.fields["Contract"] == "real contract text"
    ), f"Contract slot wrongly captured: {entry.fields['Contract']!r}"


def test_atomic_write_helper_removes_tempfile_on_failure(tmp_path: Path):
    """P1-12 regression: `_atomic_write` cleans up its tempfile if the
    rename step fails (e.g., target is a directory)."""
    assert hasattr(vb, "_atomic_write"), "_atomic_write must be reachable via vb"
    target = tmp_path / "subdir"
    target.mkdir()  # target is a directory — os.replace will fail
    try:
        vb._atomic_write(target, "content")
    except Exception:
        pass  # expected — we just care about cleanup
    tmp = target.with_suffix(target.suffix + ".tmp")
    assert not tmp.exists(), "Tempfile leaked after failed atomic write"


def test_orphan_tag_missing_cfc(tmp_path: Path):
    """Spec carries [CFC-99] but no CFC-99 exists → orphaned-missing."""
    from blueprint_common import compute_content_hash

    body = "R1\n\n**Acceptance Criteria:**\n\n- GIVEN x\n  WHEN y\n  THEN z [CFC-99]\n"
    full = (
        f"# Feature: F1\n\n**PLAN feature identifier:** `F1`\n\n"
        f"## Objective\n\nx\n\n## Requirements\n\n{body}\n\n"
        f"## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    full = full.replace("`pending`", f"`{compute_content_hash(full)}`")
    _make_spec(tmp_path / "specs" / "F1-alpha", spec_md=full)

    spec_states = vb.walk_specs(tmp_path)
    orphans = vb.scan_orphan_tags([], spec_states, {})
    assert len(orphans) == 1
    assert orphans[0].subtype == "orphaned-missing"
    assert orphans[0].cfc_number == 99


def test_orphan_tag_departed(tmp_path: Path):
    """CFC-1 exists but F1 is no longer in Participating features → orphaned-departed."""
    from blueprint_common import compute_content_hash

    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F2\n"  # F1 has departed
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F3 owns ArchUnit rule\n\n"
    )
    entries = vb.parse_cfc_entries(vb.extract_cfc_section(plan)[2])

    body = "R1\n\n**Acceptance Criteria:**\n\n- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
    full = (
        f"# Feature: F1\n\n**PLAN feature identifier:** `F1`\n\n"
        f"## Objective\n\nx\n\n## Requirements\n\n{body}\n\n"
        f"## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    full = full.replace("`pending`", f"`{compute_content_hash(full)}`")
    _make_spec(tmp_path / "specs" / "F1-alpha", spec_md=full)

    spec_states = vb.walk_specs(tmp_path)
    orphans = vb.scan_orphan_tags(entries, spec_states, {})
    assert len(orphans) == 1
    assert orphans[0].subtype == "orphaned-departed"


def test_orphan_tag_stale_content(tmp_path: Path):
    """CFC exists, F1 still participates, but CFC's content has changed since prior approval."""
    from blueprint_common import compute_content_hash

    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F1\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** WHEN x THEN y in order A->B->C->D\n"  # current text
        "- **Enforcement:** F3 owns ArchUnit rule\n\n"
    )
    entries = vb.parse_cfc_entries(vb.extract_cfc_section(plan)[2])

    body = "R1\n\n**Acceptance Criteria:**\n\n- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
    full = (
        f"# Feature: F1\n\n**PLAN feature identifier:** `F1`\n\n"
        f"## Objective\n\nx\n\n## Requirements\n\n{body}\n\n"
        f"## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    full = full.replace("`pending`", f"`{compute_content_hash(full)}`")
    _make_spec(tmp_path / "specs" / "F1-alpha", spec_md=full)

    spec_states = vb.walk_specs(tmp_path)
    # Prior hash differs from current → stale.
    prior_hashes = {1: "0" * 64}
    orphans = vb.scan_orphan_tags(entries, spec_states, prior_hashes)
    assert any(o.subtype == "orphaned-stale-content" for o in orphans)


def test_orphan_tag_scan_empty_when_no_drift(tmp_path: Path):
    """When CFC content hash matches the prior recorded hash, no stale-content orphan fires."""
    from blueprint_common import compute_content_hash

    plan = _build_plan(
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: T\n\n"
        "- **Participating features:** F1\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F3 owns ArchUnit rule\n\n"
    )
    entries = vb.parse_cfc_entries(vb.extract_cfc_section(plan)[2])
    current_hash = entries[0].structured_content_hash()

    body = "R1\n\n**Acceptance Criteria:**\n\n- GIVEN x\n  WHEN y\n  THEN z [CFC-1]\n"
    full = (
        f"# Feature: F1\n\n**PLAN feature identifier:** `F1`\n\n"
        f"## Objective\n\nx\n\n## Requirements\n\n{body}\n\n"
        f"## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    full = full.replace("`pending`", f"`{compute_content_hash(full)}`")
    _make_spec(tmp_path / "specs" / "F1-alpha", spec_md=full)

    spec_states = vb.walk_specs(tmp_path)
    orphans = vb.scan_orphan_tags(entries, spec_states, {1: current_hash})
    assert orphans == []


# ---------------------------------------------------------------------------
# CFC hash block round-trip in PLAN's ## Approval section
# ---------------------------------------------------------------------------

def test_render_and_read_cfc_hashes_round_trip():
    body = (
        "### CFC-1: T\n\n"
        "- **Participating features:** F1\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F2 owns ArchUnit rule\n\n"
        "### CFC-2: U\n\n"
        "- **Participating features:** F3\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F4 owns ArchUnit rule\n"
    )
    entries = vb.parse_cfc_entries(body)
    rendered = vb.render_cfc_hashes(entries)
    plan = (
        "# Plan\n\n## Approval\n\n"
        "- [x] Approved to proceed to feature development\n"
        "- **Content Hash:** `abcd1234`\n"
        f"{rendered}\n"
    )
    parsed = vb.read_cfc_hashes(plan)
    assert set(parsed.keys()) == {1, 2}
    assert parsed[1] == entries[0].structured_content_hash()
    assert parsed[2] == entries[1].structured_content_hash()


def test_write_cfc_hash_block_inserts_when_missing():
    plan = (
        "# Plan\n\n## Approval\n\n"
        "- [x] Approved to proceed to feature development\n"
        "- **Content Hash:** `abcd1234`\n"
    )
    body = (
        "### CFC-1: T\n\n"
        "- **Participating features:** F1\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F2 owns ArchUnit rule\n"
    )
    entries = vb.parse_cfc_entries(body)
    updated = vb._write_cfc_hash_block(plan, entries)
    assert "- **CFC Content Hashes:**" in updated
    assert f"  - CFC-1: `{entries[0].structured_content_hash()}`" in updated


def test_write_cfc_hash_block_replaces_existing():
    body = (
        "### CFC-1: T\n\n"
        "- **Participating features:** F1\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F2 owns ArchUnit rule\n"
    )
    entries = vb.parse_cfc_entries(body)
    # Use a realistic 64-char hex stale-hash; the new tightened tail regex
    # only consumes CFC-hash-shaped lines (`- CFC-N: \`<hex>\``), so the
    # fixture must use a valid hex string.
    stale_hash = "0" * 64
    plan = (
        "# Plan\n\n## Approval\n\n"
        "- [x] Approved to proceed to feature development\n"
        "- **Content Hash:** `abcd1234`\n"
        "- **CFC Content Hashes:**\n"
        f"  - CFC-1: `{stale_hash}`\n"
    )
    updated = vb._write_cfc_hash_block(plan, entries)
    assert f"`{stale_hash}`" not in updated
    assert f"`{entries[0].structured_content_hash()}`" in updated


def test_write_cfc_hash_block_preserves_unrelated_metadata_bullets(tmp_path: Path):
    r"""P1-3 regression: indented bullets that are NOT CFC-hash-shaped must survive a re-stamp.

    Earlier the tail regex `(?:\n[ \t]+-[^\n]*)*` greedily consumed any
    adjacent indented `- ...` line, deleting user-added review metadata.
    The tightened tail now matches only `- CFC-N: `<hex>`` shapes.
    """
    body = (
        "### CFC-1: T\n\n"
        "- **Participating features:** F1\n"
        "- **Contract:** c\n"
        "- **Per-feature AC:** ac\n"
        "- **Enforcement:** F2 owns ArchUnit rule\n"
    )
    entries = vb.parse_cfc_entries(body)
    plan = (
        "# Plan\n\n## Approval\n\n"
        "- [x] Approved to proceed to feature development\n"
        "- **Content Hash:** `abcd1234`\n"
        "- **CFC Content Hashes:**\n"
        f"  - CFC-1: `{'0' * 64}`\n"
        "- **Reviewer:** Alice Smith\n"
        "- **Date:** 2026-05-17\n"
    )
    updated = vb._write_cfc_hash_block(plan, entries)
    assert "Reviewer:** Alice Smith" in updated
    assert "Date:** 2026-05-17" in updated
    # And the hash was updated.
    assert f"`{entries[0].structured_content_hash()}`" in updated


def test_approve_document_does_not_rewrite_phantom_content_hash_outside_approval(
    tmp_path: Path,
):
    """P1-4 regression: a `**Content Hash:**` literal inside a Feature Breakdown entry
    (e.g., an illustrative example) must NOT be rewritten by --approve plan."""
    # Build a PLAN.md where the Feature Breakdown happens to include a literal
    # `**Content Hash:**` string (e.g., in a code example or description).
    plan_md = (
        "# Plan\n\n"
        "## Feature Breakdown\n\n"
        "### F1: Tricky example feature\n\n"
        "- **Description:** Sample doc with **Content Hash:** `phantom-not-real` inside.\n\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to feature development\n"
        "- **Content Hash:** `pending`\n"
    )
    plan_path = tmp_path / "PLAN.md"
    plan_path.write_text(plan_md, encoding="utf-8")

    vb.approve_document(plan_path)
    result = plan_path.read_text(encoding="utf-8")
    # The phantom value in Feature Breakdown stays intact.
    assert "`phantom-not-real`" in result
    # The Approval-section hash got updated (no longer `pending`).
    approval_section = result[result.index("## Approval"):]
    assert "`pending`" not in approval_section


def test_approve_document_does_not_rewrite_phantom_approval_checkbox_outside_approval(
    tmp_path: Path,
):
    """P1-4 regression: a `- [ ] Approved to proceed` literal anywhere outside `## Approval`
    (e.g., quoted in a feature description for documentation purposes) must not be ticked."""
    plan_md = (
        "# Plan\n\n"
        "## Feature Breakdown\n\n"
        "### F1: Documentation feature\n\n"
        "- **Description:** Sample showing the approval form: "
        "`- [ ] Approved to proceed to feature development` is the unchecked variant.\n\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to feature development\n"
        "- **Content Hash:** `pending`\n"
    )
    plan_path = tmp_path / "PLAN.md"
    plan_path.write_text(plan_md, encoding="utf-8")

    vb.approve_document(plan_path)
    result = plan_path.read_text(encoding="utf-8")
    # The illustrative `- [ ]` inside the description stays unchanged.
    feature_section = result[
        result.index("## Feature Breakdown") : result.index("## Approval")
    ]
    assert "[ ] Approved to proceed" in feature_section
    # And the Approval-section checkbox flipped to [x].
    approval_section = result[result.index("## Approval"):]
    assert "[x] Approved to proceed" in approval_section


def test_read_cfc_hashes_ignores_stray_block_outside_approval():
    """P1-5 regression: a stray `- **CFC Content Hashes:**` block placed AFTER `## Approval`
    (i.e., in a later section like `## Panel Review`) must not be read as the baseline."""
    plan = (
        "# Plan\n\n"
        "## Approval\n\n"
        "- [x] Approved to proceed to feature development\n"
        "- **Content Hash:** `abcd1234`\n"
        "\n"
        "## Panel Review\n\n"
        "- **CFC Content Hashes:**\n"
        f"  - CFC-99: `{'f' * 64}`\n"
    )
    hashes = vb.read_cfc_hashes(plan)
    assert hashes == {}, (
        f"Stray block outside ## Approval was read as baseline: {hashes}"
    )


def test_read_cfc_hashes_reads_in_approval_section_only():
    """Positive complement to the above: a real CFC hash block INSIDE `## Approval` is read."""
    real_hash = "a" * 64
    plan = (
        "# Plan\n\n"
        "## Approval\n\n"
        "- [x] Approved to proceed to feature development\n"
        "- **Content Hash:** `abcd1234`\n"
        "- **CFC Content Hashes:**\n"
        f"  - CFC-1: `{real_hash}`\n"
        "\n"
        "## Panel Review\n\n"
        "- **CFC Content Hashes:**\n"
        f"  - CFC-99: `{'f' * 64}`\n"
    )
    hashes = vb.read_cfc_hashes(plan)
    assert hashes == {1: real_hash}


def test_write_cfc_hash_block_removes_when_no_entries():
    plan = (
        "# Plan\n\n## Approval\n\n"
        "- [x] Approved to proceed to feature development\n"
        "- **Content Hash:** `abcd1234`\n"
        "- **CFC Content Hashes:**\n"
        "  - CFC-1: `abc`\n"
    )
    updated = vb._write_cfc_hash_block(plan, [])
    assert "CFC Content Hashes" not in updated
