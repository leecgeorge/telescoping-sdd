"""Contract test for the shared `cfc_parser.py` module.

Verifies that producer (`validate_blueprint.py`) and consumer (`validate_spec.py`)
parse the same `## Cross-Feature Contracts` section identically — both extract
the same CFC numbers, the same Participating-features lists, and the same
Enforcement owners. This test exists to catch drift between the two callers
if either ever reaches into the shared module's internals or builds parallel
parsers despite the shared layer.

Per architect A1 / code-quality P1 finding from the post-implementation code
review (decision C).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_producer():
    scripts = _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    if "validate_blueprint" in sys.modules:
        return importlib.reload(sys.modules["validate_blueprint"])
    return importlib.import_module("validate_blueprint")


def _load_consumer():
    scripts = _REPO_ROOT / "telescoping-sdd" / "skills" / "spec-driven-dev" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    if "validate_spec" in sys.modules:
        return importlib.reload(sys.modules["validate_spec"])
    return importlib.import_module("validate_spec")


CANONICAL_FIXTURE = """# Plan

## Feature Breakdown

### F1: First
### F2: Second
### F11: Eleven
### F36: Owner

## Cross-Feature Contracts

### CFC-1: Lock order across features

- **Participating features:** F1, F2, F11
- **Contract:** Locks must be acquired in canonical order A->B->C->D. F1 ships in M5 while F11 ships in M8, so this can't be a single-feature concern.
- **Per-feature AC:** WHEN this feature acquires database locks, THEN they acquire in canonical order A->B->C->D.
- **Enforcement:** F36 owns the ArchUnit rule LockOrderCheck.

### CFC-2: Single-writer for audit log

- **Participating features:** F1, F2
- **Contract:** All writes to the audit log must route through OperatorAuditLogWriter.
- **Per-feature AC:** WHEN this feature writes audit entries, THEN it goes through OperatorAuditLogWriter.
- **Enforcement:** F36 owns the ArchUnit rule NoDirectAuditLogWrite.

## Panel Review
"""


def test_producer_and_consumer_parse_identical_cfc_numbers():
    """Both sides see the same set of CFC numbers."""
    vb = _load_producer()
    vs = _load_consumer()

    producer_section = vb.extract_cfc_section(CANONICAL_FIXTURE)
    assert producer_section is not None
    producer_entries = vb.parse_cfc_entries(producer_section[2])
    producer_numbers = sorted(e.number for e in producer_entries)

    consumer_entries = vs._parse_cfc_section(CANONICAL_FIXTURE)
    consumer_numbers = sorted(e["number"] for e in consumer_entries)

    assert producer_numbers == consumer_numbers == [1, 2]


def test_producer_and_consumer_parse_identical_participating_features():
    """Both sides extract the same Participating-features list per CFC."""
    vb = _load_producer()
    vs = _load_consumer()

    producer_section = vb.extract_cfc_section(CANONICAL_FIXTURE)
    producer_by_n = {
        e.number: sorted(e.participating_features())
        for e in vb.parse_cfc_entries(producer_section[2])
    }
    consumer_by_n = {
        e["number"]: sorted(e["participating"])
        for e in vs._parse_cfc_section(CANONICAL_FIXTURE)
    }
    assert producer_by_n == consumer_by_n
    assert producer_by_n[1] == [1, 2, 11]
    assert producer_by_n[2] == [1, 2]


def test_producer_and_consumer_parse_identical_enforcement_owners():
    """Both sides extract the same Enforcement-owner feature IDs per CFC."""
    vb = _load_producer()
    vs = _load_consumer()

    producer_section = vb.extract_cfc_section(CANONICAL_FIXTURE)
    producer_by_n = {
        e.number: sorted(e.enforcement_owners())
        for e in vb.parse_cfc_entries(producer_section[2])
    }
    consumer_by_n = {
        e["number"]: sorted(e["enforcement_owners"])
        for e in vs._parse_cfc_section(CANONICAL_FIXTURE)
    }
    assert producer_by_n == consumer_by_n
    assert producer_by_n[1] == [36]
    assert producer_by_n[2] == [36]


def test_producer_and_consumer_agree_on_absent_section():
    """A PLAN with no Cross-Feature Contracts section yields empty results from both sides."""
    vb = _load_producer()
    vs = _load_consumer()

    plan_no_cfc = "# Plan\n\n## Feature Breakdown\n\n### F1: T\n\n## Panel Review\n"
    assert vb.extract_cfc_section(plan_no_cfc) is None
    assert vs._parse_cfc_section(plan_no_cfc) == []


def test_producer_and_consumer_share_cfc_tag_extraction():
    """Both sides agree on which [CFC-N] tags appear on a THEN line, including multi-tag."""
    vb = _load_producer()
    vs = _load_consumer()

    spec_block = (
        "**Acceptance Criteria:**\n\n"
        "- GIVEN setup\n"
        "  WHEN action\n"
        "  THEN result [CFC-1] [CFC-3]\n"
    )
    producer_tags = sorted(vb.spec_then_line_cfc_tags(spec_block))
    consumer_tags = sorted(vs._spec_then_line_cfc_tags(spec_block))
    assert producer_tags == consumer_tags == [1, 3]


# ---------------------------------------------------------------------------
# Edge-case parity — added per the light-touch verification pass.
# Each fixture asserts producer and consumer agree on parse output for a
# specific edge case the canonical happy-path fixtures don't exercise. If
# either side drifts, one of these fails before silent divergence ships.
# ---------------------------------------------------------------------------


def _producer_numbers(vb, plan: str) -> list[int]:
    section = vb.extract_cfc_section(plan)
    if section is None:
        return []
    return sorted(e.number for e in vb.parse_cfc_entries(section[2]))


def _consumer_numbers(vs, plan: str) -> list[int]:
    return sorted(e["number"] for e in vs._parse_cfc_section(plan))


def test_edge_case_leading_zero_cfc_number_rejected_by_both_sides():
    """`### CFC-007` is not a valid CFC header (per CFC_ENTRY_NUMBER_FORMAT, P3-12)."""
    vb = _load_producer()
    vs = _load_consumer()

    plan = (
        "# Plan\n\n## Cross-Feature Contracts\n\n"
        "### CFC-007: Bad number\n\n"
        "- **Participating features:** F1, F2\n"
        "- **Contract:** x\n"
        "- **Per-feature AC:** y\n"
        "- **Enforcement:** F3 owns z\n"
    )
    assert _producer_numbers(vb, plan) == _consumer_numbers(vs, plan) == []


def test_edge_case_near_miss_header_skipped_by_both_sides():
    """A lowercase / mistyped `## cross-feature contracts` is not the CFC section."""
    vb = _load_producer()
    vs = _load_consumer()

    plan = (
        "# Plan\n\n## cross-feature contracts\n\n"
        "### CFC-1: Should be invisible\n\n"
        "- **Participating features:** F1\n"
        "- **Contract:** x\n"
        "- **Per-feature AC:** y\n"
        "- **Enforcement:** F2 owns z\n"
    )
    assert _producer_numbers(vb, plan) == _consumer_numbers(vs, plan) == []


def test_edge_case_fenced_code_block_then_line_does_not_bind():
    """A `THEN ... [CFC-N]` line inside a triple-backtick fence is illustrative, not a binding."""
    vb = _load_producer()
    vs = _load_consumer()

    spec_block = (
        "**Example (do not enforce):**\n\n"
        "```\n"
        "GIVEN x\n"
        "WHEN y\n"
        "THEN result [CFC-99]\n"
        "```\n"
    )
    producer_tags = sorted(vb.spec_then_line_cfc_tags(spec_block))
    consumer_tags = sorted(vs._spec_then_line_cfc_tags(spec_block))
    assert producer_tags == consumer_tags == []


def test_edge_case_nbsp_in_participating_features_parses_identically_on_both_sides():
    """NBSP in the Participating-features value parses to the same feature list on both sides.

    Python's `\\s` matches NBSP, so the strict value pattern accepts
    `F1,<NBSP>F2` and both sides parse it identically. The hash normalization
    layer separately preserves NBSP as distinct so cosmetic-edit drift still
    surfaces in content hashing. The *contract* this test pins is that both
    sides agree on whatever parsing outcome the implementation chooses.
    """
    vb = _load_producer()
    vs = _load_consumer()

    nbsp = " "
    plan = (
        "# Plan\n\n## Cross-Feature Contracts\n\n"
        "### CFC-1: NBSP edge\n\n"
        f"- **Participating features:** F1,{nbsp}F2\n"
        "- **Contract:** x\n"
        "- **Per-feature AC:** y\n"
        "- **Enforcement:** F3 owns z\n"
    )
    section = vb.extract_cfc_section(plan)
    assert section is not None
    producer_entry = vb.parse_cfc_entries(section[2])[0]
    consumer_entry = vs._parse_cfc_section(plan)[0]
    assert (
        producer_entry.participating_features() == consumer_entry["participating"]
    )


def test_edge_case_multi_digit_cfc_no_substring_collision():
    """`[CFC-100]` on a THEN line does not match against CFC-1 or CFC-10 (M2 prefix collision)."""
    vb = _load_producer()
    vs = _load_consumer()

    spec_block = (
        "**Acceptance Criteria:**\n\n"
        "- GIVEN setup\n"
        "  WHEN action\n"
        "  THEN result [CFC-100]\n"
    )
    producer_tags = sorted(vb.spec_then_line_cfc_tags(spec_block))
    consumer_tags = sorted(vs._spec_then_line_cfc_tags(spec_block))
    assert producer_tags == consumer_tags == [100]
    assert 1 not in producer_tags and 10 not in producer_tags


def test_edge_case_missing_per_feature_ac_field_still_parses_cfc():
    """A CFC entry missing the `**Per-feature AC:**` field is still parsed as CFC-N — field absence is a separate diagnostic, not a parse failure."""
    vb = _load_producer()
    vs = _load_consumer()

    plan = (
        "# Plan\n\n## Cross-Feature Contracts\n\n"
        "### CFC-5: Missing AC field\n\n"
        "- **Participating features:** F1, F2\n"
        "- **Contract:** x\n"
        "- **Enforcement:** F3 owns z\n"
    )
    assert _producer_numbers(vb, plan) == _consumer_numbers(vs, plan) == [5]


# ---------------------------------------------------------------------------
# Seam-grammar single-ownership (audit R2.3). The PLAN-feature-identifier line
# and the tasks-checkbox [CFC-N] grammar used to be compiled separately in each
# validator with no symmetry test. They now live in cfc_parser; these assert
# both validators reference the SAME object, so they cannot drift.
# ---------------------------------------------------------------------------


def _cfc_parser():
    scripts = _REPO_ROOT / "telescoping-sdd" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return importlib.import_module("cfc_parser")


def test_seam_grammars_are_the_shared_objects():
    vb = _load_producer()
    vs = _load_consumer()
    cp = _cfc_parser()
    # Identity (is), not just equality — both validators alias the one source.
    assert vb.PLAN_FEATURE_ID_LINE is cp.PLAN_FEATURE_ID_PATTERN
    assert vs.PLAN_FEATURE_ID_LINE_RE is cp.PLAN_FEATURE_ID_PATTERN
    assert vb.TASKS_CHECKBOX_WITH_CFC is cp.TASKS_CHECKBOX_CFC_PATTERN
    assert vs.TASKS_CHECKBOX_WITH_CFC_RE is cp.TASKS_CHECKBOX_CFC_PATTERN


def test_feature_breakdown_resolution_is_scoped_and_shared():
    cp = _cfc_parser()
    plan = (
        "# Plan\n\n## Feature Breakdown\n\n"
        "### F1: alpha\n\nx\n\n### F2: beta\n\nx\n\n"
        "## Open Questions\n\n### F9: NOT a feature (outside Feature Breakdown)\n"
    )
    # Only the two headings inside ## Feature Breakdown count; F9 is excluded.
    assert cp.feature_breakdown_numbers(plan) == [1, 2]


def test_producer_and_consumer_resolve_features_through_same_helper(monkeypatch):
    # Both validators import feature_breakdown_numbers from cfc_parser; patching
    # the source is observed by both, proving neither kept a private copy.
    vb = _load_producer()
    vs = _load_consumer()
    cp = _cfc_parser()
    assert vb.feature_breakdown_numbers is cp.feature_breakdown_numbers
    assert vs.feature_breakdown_numbers is cp.feature_breakdown_numbers


def test_validator_helpers_are_hoisted_to_blueprint_common():
    """check_approval, _resolve_marker_root_and_key, and
    check_previous_phase_approved were byte-identical copies in both validators;
    post-R2.1 both reference the single blueprint_common implementation."""
    vb = _load_producer()
    vs = _load_consumer()
    scripts = _REPO_ROOT / "telescoping-sdd" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    bc = importlib.import_module("blueprint_common")
    for name in (
        "check_approval",
        "_resolve_marker_root_and_key",
        "check_previous_phase_approved",
    ):
        assert getattr(vb, name) is getattr(bc, name), name
        assert getattr(vs, name) is getattr(bc, name), name
