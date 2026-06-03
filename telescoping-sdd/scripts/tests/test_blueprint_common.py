"""Tests for `blueprint_common.py`.

Covers the public surface plus the frozen-fixture hash regression matrix.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Locate telescoping-sdd/scripts/ and the tests dir relative to this file so the
# test runs both from the repo root and from any sub-directory.
_SCRIPTS = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for p in (_SCRIPTS, _TESTS):
    if str(p) not in sys.path:
        sys.path.append(str(p))

import json

import pytest

import blueprint_common as bc
from _fixture_contract import assert_fixture_unchanged

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "line_ending_variants"


# ---------------------------------------------------------------------------
# content_for_hashing
# ---------------------------------------------------------------------------


def test_content_for_hashing_idempotent():
    sample = (
        "# Title\n\n## Approval\n\n"
        "- [x] Approved to proceed to next phase\n"
        "- **Content Hash:** `abc1234567890def`\n"
    )
    once = bc.content_for_hashing(sample)
    twice = bc.content_for_hashing(once)
    assert once == twice


def test_content_for_hashing_neutralises_checkbox_and_hash():
    approved = "- [x] Approved to proceed to next phase\n- **Content Hash:** `deadbeef00000000`\n"
    pending = "- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`"
    assert bc.content_for_hashing(approved) == pending


# ---------------------------------------------------------------------------
# compute_content_hash / verify_content_hash
# ---------------------------------------------------------------------------


def test_compute_content_hash_stable():
    sample = "# Doc\n\nbody.\n"
    h1 = bc.compute_content_hash(sample)
    h2 = bc.compute_content_hash(sample)
    assert h1 == h2
    assert len(h1) == 16
    assert all(c in "0123456789abcdef" for c in h1)


def test_compute_content_hash_invariant_under_approval_toggle():
    """Approving a document must not change its hash."""
    pending = (
        "# Doc\n\nbody.\n\n## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )
    approved = (
        "# Doc\n\nbody.\n\n## Approval\n\n"
        "- [x] Approved to proceed to next phase\n"
        "- **Content Hash:** `0123456789abcdef`\n"
    )
    assert bc.compute_content_hash(pending) == bc.compute_content_hash(approved)


def test_compute_content_hash_changes_on_body_edit():
    a = (
        "# Doc\n\nbody A.\n\n## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )
    b = a.replace("body A", "body B")
    assert bc.compute_content_hash(a) != bc.compute_content_hash(b)


def test_verify_content_hash_match():
    sample = "# Doc\n\nbody.\n"
    h = bc.compute_content_hash(sample)
    assert bc.verify_content_hash(sample, h) is True
    assert bc.verify_content_hash(sample, "0000000000000000") is False


# ---------------------------------------------------------------------------
# Frozen-fixture hash matrix — byte-for-byte regression guard
# ---------------------------------------------------------------------------


def test_hash_frozen_fixture_matrix():
    """Each variant in the {LF,CRLF} × {BOM,no-BOM} × {EOL,no-EOL} matrix
    hashes to the value recorded in FIXTURE_MANIFEST.json.
    """
    assert_fixture_unchanged(FIXTURE_DIR)
    manifest = json.loads(
        (FIXTURE_DIR / "FIXTURE_MANIFEST.json").read_text(encoding="utf-8")
    )
    expected = manifest["expected_hashes_read_text_utf8"]
    assert len(expected) == 8, "Expected 8 fixtures in the matrix"

    drifted = []
    for name, baseline in expected.items():
        # `read_text(encoding="utf-8")` mirrors validate_blueprint.read_file —
        # BOM is preserved in the content the hasher sees.
        content = (FIXTURE_DIR / name).read_text(encoding="utf-8")
        actual = bc.compute_content_hash(content)
        if actual != baseline:
            drifted.append((name, baseline, actual))
    assert not drifted, (
        "Hash drift from manifest baselines:\n"
        + "\n".join(f"  {n}: expected {e}, got {a}" for n, e, a in drifted)
    )


# ---------------------------------------------------------------------------
# has_section / section_has_content
# ---------------------------------------------------------------------------


def test_has_section_heading_and_bold():
    heading = "## Goals\n\nstuff\n"
    bold = "**Goals:** stuff\n"
    plain = "Goals are good.\n"
    assert bc.has_section(heading, "Goals") is True
    assert bc.has_section(bold, "Goals") is True
    assert bc.has_section(plain, "Goals") is False


def test_section_has_content_detects_empty():
    populated = "## Goals\n\nReal content.\n"
    empty = "## Goals\n\n"
    placeholder = "## Goals\n\n[describe goals]\n"
    assert bc.section_has_content(populated, "Goals") is True
    assert bc.section_has_content(empty, "Goals") is False
    assert bc.section_has_content(placeholder, "Goals") is False


def test_section_has_content_missing_section():
    assert bc.section_has_content("# Title\n", "Goals") is False


# ---------------------------------------------------------------------------
# extract_panel_section
# ---------------------------------------------------------------------------


def test_extract_panel_section_strips_html_comments():
    content = (
        "## Panel Review\n\n"
        "<!-- example: | row | User input needed | -->\n"
        "Real body.\n\n## Next\n"
    )
    body = bc.extract_panel_section(content)
    assert "Real body" in body
    assert "User input needed" not in body  # comment was stripped


def test_extract_panel_section_missing_returns_empty():
    assert bc.extract_panel_section("# Title\n\nNo panel here.\n") == ""


# ---------------------------------------------------------------------------
# scan_unresolved_markers
# ---------------------------------------------------------------------------


def test_scan_unresolved_markers_all_types():
    content = (
        "# Doc\n\n"
        "[TBD — needs input]\n"
        "TODO: do this\n"
        "FIXME bug here\n"
        "XXX hack\n"
        "HACK temporary\n"
        "What ??? indeed\n"
        "- [ ] Q1: first question\n"
        "- [ ] Q2: second\n"
        "## Panel Review\n\n"
        "| HIGH | thing | User input needed | |\n"
    )
    hits = bc.scan_unresolved_markers(content)
    kinds = {h.kind for h in hits}
    assert "tbd" in kinds
    assert "unresolved_general" in kinds
    assert "unchecked_question" in kinds
    assert "user_input_needed" in kinds
    # Sanity on counts — each should fire at least once
    by_kind = {}
    for h in hits:
        by_kind.setdefault(h.kind, []).append(h.text)
    assert len(by_kind["tbd"]) == 1
    assert len(by_kind["unchecked_question"]) == 2
    assert any("TODO" in t for t in by_kind["unresolved_general"])
    assert any("???" in t for t in by_kind["unresolved_general"])


def test_scan_unresolved_markers_clean_doc():
    content = (
        "# Doc\n\nClean body, no markers anywhere.\n\n"
        "## Panel Review\n\n| LOW | minor | Addressed | resolved |\n"
    )
    assert bc.scan_unresolved_markers(content) == []


# ---------------------------------------------------------------------------
# validate_panel_review (smoke)
# ---------------------------------------------------------------------------


def test_validate_panel_review_new_format_with_trajectory():
    content = (
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| 1 | 2026-04-30 | Pass note |\n"
        "### Sealed dispositions\n\n"
        "### Latest pass detail\n\n"
        "## Next\n"
    )
    result = bc.ValidationResult()
    bc.validate_panel_review(content, "DOC.md", result)
    names = {n for n, _, _ in result.checks}
    assert "DOC.md 'Panel Review' shows the panel has run" in names
    # Look up severity for that check
    for n, sev, _ in result.checks:
        if "shows the panel has run" in n:
            assert sev == bc.Severity.PASS


def test_validate_panel_review_unresolved_user_input():
    content = (
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| 1 | 2026-04-30 | note |\n"
        "### Latest pass detail\n\n"
        "| [HIGH] | concern | User input needed | tbd |\n"
        "## Next\n"
    )
    result = bc.ValidationResult()
    bc.validate_panel_review(content, "DOC.md", result)
    failures = [n for n, sev, _ in result.checks if sev == bc.Severity.FAIL]
    assert any("unresolved panel concerns" in n for n in failures)


def test_validate_panel_review_missing_section():
    result = bc.ValidationResult()
    bc.validate_panel_review("# Title\n\nNo panel.\n", "DOC.md", result)
    # Missing body → only the empty-content check runs
    assert any(
        "section has content" in n and sev == bc.Severity.FAIL
        for n, sev, _ in result.checks
    )


# ---------------------------------------------------------------------------
# trim_trajectory_table — on-approval trajectory bookkeeping
# ---------------------------------------------------------------------------


def _build_doc_with_trajectory(n_rows: int, *, elided_prefix: str = "") -> str:
    """Build a minimal doc with a `### Trajectory` table containing n_rows data rows.

    `elided_prefix` is an optional pre-existing elided row to prepend (re-approval
    scenarios). Pass like `"| … | … | — | — | — | — | — | 7 earlier passes elided |"`.
    """
    header = "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |"
    sep = "|------|------|-------|-------------|-----------|----------|--------|-------|"
    rows = [
        f"| {i+1} | 2026-05-{(i % 28) + 1:02d} | 0 | 0 | 3 | 1 | 0 | normal |"
        for i in range(n_rows)
    ]
    table_body = [header, sep]
    if elided_prefix:
        table_body.append(elided_prefix)
    table_body.extend(rows)
    return (
        "# Plan\n\n## Panel Review\n\n### Trajectory\n\n"
        + "\n".join(table_body)
        + "\n\n### Sealed dispositions\n\n(none)\n\n### Latest pass detail\n\n"
    )


def test_trim_trajectory_no_op_when_under_threshold():
    """≤ 15 data rows → content unchanged."""
    doc = _build_doc_with_trajectory(10)
    assert bc.trim_trajectory_table(doc) == doc


def test_trim_trajectory_no_op_at_exact_threshold():
    """Exactly 15 data rows → content unchanged."""
    doc = _build_doc_with_trajectory(15)
    assert bc.trim_trajectory_table(doc) == doc


def test_trim_trajectory_elides_oldest_when_over_threshold():
    """16 data rows → 1 elided, 15 kept, plus elided summary row at top."""
    doc = _build_doc_with_trajectory(16)
    trimmed = bc.trim_trajectory_table(doc)
    assert trimmed != doc
    # Elided row is present with count 1.
    assert "1 earlier passes elided" in trimmed
    # The oldest row (Pass 1) is gone; the latest 15 (passes 2-16) are kept.
    assert "| 1 | 2026-05-01 |" not in trimmed
    assert "| 2 | 2026-05-02 |" in trimmed
    assert "| 16 | 2026-05-16 |" in trimmed
    # Elided row appears before the kept rows.
    elided_pos = trimmed.find("earlier passes elided")
    pass2_pos = trimmed.find("| 2 | 2026-05-02 |")
    assert elided_pos < pass2_pos


def test_trim_trajectory_merges_existing_elided_count_on_reapproval():
    """If an elided row is already present, its count merges with new elisions."""
    existing = "| … | … | — | — | — | — | — | 7 earlier passes elided |"
    # 18 real rows + the existing elided row at the top.
    # On trim: keep 15, elide 3 new ones, merged count = 7 + 3 = 10.
    doc = _build_doc_with_trajectory(18, elided_prefix=existing)
    trimmed = bc.trim_trajectory_table(doc)
    assert "10 earlier passes elided" in trimmed
    assert "7 earlier passes elided" not in trimmed
    # Three oldest real rows (passes 1, 2, 3) are gone; 4-18 kept.
    assert "| 3 | 2026-05-03 |" not in trimmed
    assert "| 4 | 2026-05-04 |" in trimmed
    assert "| 18 | 2026-05-18 |" in trimmed


def test_trim_trajectory_no_op_when_under_threshold_with_existing_elided():
    """≤ 15 real rows + existing elided row → no-op (elided row preserved)."""
    existing = "| … | … | — | — | — | — | — | 4 earlier passes elided |"
    doc = _build_doc_with_trajectory(15, elided_prefix=existing)
    assert bc.trim_trajectory_table(doc) == doc


def test_trim_trajectory_no_op_when_no_trajectory_section():
    """Document with no `### Trajectory` heading → content unchanged."""
    doc = "# Plan\n\n## Stuff\n\nContent.\n"
    assert bc.trim_trajectory_table(doc) == doc


def test_trim_trajectory_no_op_when_section_has_no_table():
    """`### Trajectory` heading present but no markdown table → content unchanged."""
    doc = (
        "# Plan\n\n## Panel Review\n\n### Trajectory\n\n"
        "_(no passes archived yet)_\n\n### Latest pass detail\n\n"
    )
    assert bc.trim_trajectory_table(doc) == doc


def test_trim_trajectory_does_not_touch_following_sections():
    """Trim must not leak into ### Sealed dispositions / ### Latest pass detail."""
    doc = _build_doc_with_trajectory(20)
    doc = doc.replace(
        "### Sealed dispositions\n\n(none)",
        "### Sealed dispositions\n\n- `[SEAL-1]` **Topic** (pass 3, 2026-05-03) — defended.",
    )
    trimmed = bc.trim_trajectory_table(doc)
    # Sealed-dispositions content untouched.
    assert "[SEAL-1]" in trimmed
    assert "Topic" in trimmed
    # Trajectory trimmed correctly.
    assert "5 earlier passes elided" in trimmed


def test_trim_trajectory_custom_keep_value():
    """`keep` parameter overrides the default threshold."""
    doc = _build_doc_with_trajectory(8)
    trimmed = bc.trim_trajectory_table(doc, keep=5)
    assert "3 earlier passes elided" in trimmed
    assert "| 3 | 2026-05-03 |" not in trimmed
    assert "| 4 | 2026-05-04 |" in trimmed
    assert "| 8 | 2026-05-08 |" in trimmed


# ---------------------------------------------------------------------------
# Relocated approval predicates + is_shipped (T9a)
# ---------------------------------------------------------------------------
#
# `has_approval`, `approval_hash`, `approval_hash_matches`, `all_tasks_ticked`,
# `read_file`, `is_shipped_from_contents`, and `is_shipped` were relocated here
# from validate_blueprint.py so reconcile.py can share them without importing a
# skill validator. The validator's own classify_spec test suite is the
# behavioral regression guard; these tests pin the predicates at their new home.


def _stamp(body: str) -> str:
    """Return `body` with its `pending` Content Hash replaced by the real hash."""
    return body.replace("`pending`", f"`{bc.compute_content_hash(body)}`")


def _approved_doc(inner: str = "stuff") -> str:
    """A minimal approved document (checkbox + matching Content Hash)."""
    body = (
        f"# Doc\n\n{inner}\n\n## Approval\n\n"
        "- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    return _stamp(body)


def test_has_approval_true_false():
    assert bc.has_approval(_approved_doc()) is True
    assert bc.has_approval("# Doc\n\nwip\n") is False
    # Header present but checkbox unticked → not approved.
    unticked = "# Doc\n\n## Approval\n\n- [ ] Approved to proceed to next phase\n"
    assert bc.has_approval(unticked) is False


def test_approval_hash_value_and_pending():
    doc = _approved_doc()
    assert bc.approval_hash(doc) == bc.compute_content_hash(doc)
    # Absent line → None.
    assert bc.approval_hash("# Doc\n\nwip\n") is None
    # Literal 'pending' → None.
    pending = (
        "# Doc\n\n## Approval\n\n- [x] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )
    assert bc.approval_hash(pending) is None


def test_approval_hash_matches_true_and_stale():
    doc = _approved_doc()
    assert bc.approval_hash_matches(doc) is True
    # Mutate the body after stamping → stale hash → no match.
    stale = doc.replace("stuff", "stuff edited")
    assert bc.approval_hash_matches(stale) is False
    # Unapproved doc → False.
    assert bc.approval_hash_matches("# Doc\n\nwip\n") is False


def test_narrow_hash_regex_distinct_from_broad():
    """The relocated narrow APPROVAL_HASH_LINE_STRICT only matches hex-or-pending;
    the module's broad APPROVAL_HASH_LINE captures any backtick body. They are
    deliberately NOT unified (broad surfaces corruption verbatim for
    read_stored_hash; narrow is a clean approval gate)."""
    corrupt = (
        "# Doc\n\n## Approval\n\n- [x] Approved to proceed to next phase\n"
        "- **Content Hash:** `not-hex!!`\n"
    )
    # Narrow strict regex does NOT match a non-hex value → approval_hash None.
    assert bc.approval_hash(corrupt) is None
    # Broad regex (used by read_stored_hash) DOES surface the corrupt value.
    assert bc.read_stored_hash(corrupt) == "not-hex!!"
    assert bc.APPROVAL_HASH_LINE_STRICT is not bc.APPROVAL_HASH_LINE


def test_all_tasks_ticked_matrix():
    # All ticked (before Approval) → True.
    ticked = "# Tasks\n\n- [x] A\n- [x] B\n\n## Approval\n\n- [x] Approved to proceed\n"
    assert bc.all_tasks_ticked(ticked) is True
    # One unticked → False.
    one_open = "# Tasks\n\n- [x] A\n- [ ] B\n\n## Approval\n\n- [x] Approved to proceed\n"
    assert bc.all_tasks_ticked(one_open) is False
    # Narrative-only (zero task checkboxes) → False (vacuous-truth rejected).
    narrative = "# Tasks\n\nDocs only.\n\n## Approval\n\n- [x] Approved to proceed\n"
    assert bc.all_tasks_ticked(narrative) is False
    # The Approval checkbox must NOT count as a task: a tasks.md whose only
    # checkbox is the Approval marker is narrative-only → False.
    only_approval = "# Tasks\n\nDocs only.\n\n## Approval\n\n- [x] Approved to proceed to next phase\n"
    assert bc.all_tasks_ticked(only_approval) is False


def test_read_file_present_and_absent(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("hi\n", encoding="utf-8")
    assert bc.read_file(p) == "hi\n"
    assert bc.read_file(tmp_path / "missing.md") is None


def _shipped_triple():
    """Return (spec_md, design_md, tasks_md) for a fully-shipped feature."""
    spec_md = _approved_doc("spec body")
    design_md = _approved_doc("design body")
    tasks_body = (
        "# Tasks\n\n- [x] Implement\n- [x] Test\n\n## Approval\n\n"
        "- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    tasks_md = _stamp(tasks_body)
    return spec_md, design_md, tasks_md


def test_is_shipped_from_contents_true():
    spec_md, design_md, tasks_md = _shipped_triple()
    assert bc.is_shipped_from_contents(spec_md, design_md, tasks_md) is True


def test_is_shipped_from_contents_false_cases():
    spec_md, design_md, tasks_md = _shipped_triple()
    # Missing any artifact → False.
    assert bc.is_shipped_from_contents(None, design_md, tasks_md) is False
    assert bc.is_shipped_from_contents(spec_md, None, tasks_md) is False
    assert bc.is_shipped_from_contents(spec_md, design_md, None) is False
    # design not approved → False.
    assert bc.is_shipped_from_contents(spec_md, "# Design\n\nwip\n", tasks_md) is False
    # tasks approved but a box unticked → False.
    tasks_open = _stamp(
        "# Tasks\n\n- [x] A\n- [ ] B\n\n## Approval\n\n"
        "- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    assert bc.is_shipped_from_contents(spec_md, design_md, tasks_open) is False


def test_is_shipped_path_wrapper(tmp_path):
    spec_md, design_md, tasks_md = _shipped_triple()
    d = tmp_path / "F1-feature"
    d.mkdir()
    (d / "spec.md").write_text(spec_md, encoding="utf-8")
    (d / "design.md").write_text(design_md, encoding="utf-8")
    (d / "tasks.md").write_text(tasks_md, encoding="utf-8")
    assert bc.is_shipped(d) is True
    # Remove tasks.md → not shipped.
    (d / "tasks.md").unlink()
    assert bc.is_shipped(d) is False
    # Empty dir → not shipped, no raise.
    empty = tmp_path / "F2-empty"
    empty.mkdir()
    assert bc.is_shipped(empty) is False
