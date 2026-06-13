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


def test_has_section_does_not_match_unrelated_superstring_heading():
    """R2.4: a `## Non-Goals` heading must NOT satisfy a required `Goals` section
    (the name is anchored to the start of the heading text)."""
    non_goals = "## Non-Goals\n\nout of scope\n"
    assert bc.has_section(non_goals, "Non-Goals") is True
    assert bc.has_section(non_goals, "Goals") is False
    # The bold fallback is likewise anchored: `**Non-Goals**` is not `Goals`.
    assert bc.has_section("**Non-Goals:** x\n", "Goals") is False
    # A multi-word required section still matches its exact heading.
    assert bc.has_section("## Acceptance Criteria\n\nx\n", "Acceptance Criteria") is True


def test_section_has_content_detects_empty():
    populated = "## Goals\n\nReal content.\n"
    empty = "## Goals\n\n"
    placeholder = "## Goals\n\n[describe goals]\n"
    assert bc.section_has_content(populated, "Goals") is True
    assert bc.section_has_content(empty, "Goals") is False
    assert bc.section_has_content(placeholder, "Goals") is False


def test_section_has_content_missing_section():
    assert bc.section_has_content("# Title\n", "Goals") is False


def test_section_body_returns_body_up_to_next_h2():
    content = "## Goals\n\n- one\n- two\n\n## Non-Goals\n\n- skip\n"
    assert bc.section_body(content, "Goals") == "\n- one\n- two\n"
    assert bc.section_body(content, "Non-Goals") == "\n- skip\n"


def test_section_body_absent_returns_none_empty_returns_str():
    assert bc.section_body("# Title\n", "Goals") is None  # absent -> None
    # Present but immediately followed by the next H2 -> empty body (must NOT
    # over-read into the next section).
    assert bc.section_body("## Goals\n\n## Next\n\nx\n", "Goals") == ""


def test_section_body_h3_not_read_as_h2():
    """R2.4/3.5b: an H3 `### Goals` must NOT be read as the H2 `## Goals` section
    (the prior `## Goals\\s*\\n` matched `## Goals` as a substring of `### Goals`)."""
    content = "## Real\n\nx\n\n### Goals\n\n- nested, not the section\n"
    assert bc.section_body(content, "Goals") is None
    # And it does not collide with an unrelated superstring heading either.
    assert bc.section_body("## Non-Goals\n\n- a\n", "Goals") is None


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


def test_approval_reads_are_scoped_to_the_approval_section():
    """3.5c: a body-prose `- [x] Approved` / `**Content Hash:**` example BEFORE
    the real (unchecked, pending) ## Approval section must not be read as approval
    state — reads are scoped to the section, matching the scoped write path."""
    doc = (
        "# Doc\n\n"
        "## How approval works (example)\n\n"
        "When done, you write:\n\n"
        "- [x] Approved to proceed to next phase\n"
        "- **Content Hash:** `abcabcabcabcabcd`\n\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )
    assert bc.has_approval(doc) is False
    assert bc._approval_checkbox_checked(doc) is False
    assert bc.approval_hash(doc) is None          # real section is pending
    assert bc.read_stored_hash(doc) == "pending"  # not the body-prose example


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


# ---------------------------------------------------------------------------
# _detect_prefix_state (artifact NN_-prefix feature)
# ---------------------------------------------------------------------------

def test_detect_prefix_state_uniform_bare(tmp_path):
    (tmp_path / "spec.md").write_text("x", encoding="utf-8")
    (tmp_path / "design.md").write_text("x", encoding="utf-8")
    assert bc._detect_prefix_state(tmp_path) == "uniform-bare"


def test_detect_prefix_state_uniform_prefixed(tmp_path):
    (tmp_path / "01_spec.md").write_text("x", encoding="utf-8")
    (tmp_path / "02_design.md").write_text("x", encoding="utf-8")
    assert bc._detect_prefix_state(tmp_path) == "uniform-prefixed"


def test_detect_prefix_state_mixed(tmp_path):
    (tmp_path / "spec.md").write_text("x", encoding="utf-8")
    (tmp_path / "02_design.md").write_text("x", encoding="utf-8")
    assert bc._detect_prefix_state(tmp_path) == "mixed"


def test_detect_prefix_state_empty(tmp_path):
    assert bc._detect_prefix_state(tmp_path) == "empty"


def test_is_shipped_resolves_prefixed_artifacts(tmp_path):
    """is_shipped derives the SAME verdict from NN_-prefixed artifacts (T3)."""
    spec_md, design_md, tasks_md = _shipped_triple()
    d = tmp_path / "F3-prefixed"
    d.mkdir()
    (d / "01_spec.md").write_text(spec_md, encoding="utf-8")
    (d / "02_design.md").write_text(design_md, encoding="utf-8")
    (d / "03_tasks.md").write_text(tasks_md, encoding="utf-8")
    assert bc.is_shipped(d) is True


# ===========================================================================
# Pending-review churn feature — new surface (R1/R3/R4/R7 + R9 + R10).
# ===========================================================================

_TRAJ_TBL_HEADER = (
    "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
    "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
)


def _traj_row(p, notes="—"):
    return f"| {p} | 2026-06-12 | 0 | 0 | 0 | 0 | 0 | {notes} |"


def _panel(rows=(), sealed="", latest="", deferred=""):
    out = "## Panel Review\n\n### Trajectory\n\n" + _TRAJ_TBL_HEADER
    out += "".join(r + "\n" for r in rows)
    if deferred:
        out += "\n### Deferred dispositions\n\n" + deferred + "\n"
    if sealed:
        out += "\n### Sealed dispositions\n\n" + sealed + "\n"
    if latest:
        out += "\n### Latest pass detail\n\n" + latest + "\n"
    return out


def _approval(checked=True, hash_val="abc1234567890def", basis=None):
    box = "[x]" if checked else "[ ]"
    s = (
        "## Approval\n\n"
        f"- {box} Approved to proceed to next phase\n"
        f"- **Content Hash:** `{hash_val}`\n"
    )
    if basis is not None:
        s += f"- **Hash basis:** {basis}\n"
    return s


def _full(rows=(), sealed="", latest="", deferred="", checked=True,
          hash_val="abc1234567890def", basis=None):
    return "# Doc\n\n" + _panel(rows, sealed, latest, deferred) + "\n" + _approval(
        checked, hash_val, basis
    )


# --- approval_section_bounds ----------------------------------------------


def test_approval_section_bounds_basic():
    content = "# D\n\n## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    bounds = bc.approval_section_bounds(content)
    assert bounds is not None
    body_start, body_end = bounds
    assert content[body_start:body_end].lstrip().startswith("- [x] Approved")


def test_approval_section_bounds_none_when_absent():
    assert bc.approval_section_bounds("# D\n\nno approval here\n") is None


def test_approval_section_bounds_body_prose_decoy():
    # A `## Approval` substring inside a table cell (not at line start) is skipped;
    # the line-anchored regex lands on the REAL header.
    content = (
        "# D\n\n| col | `## Approval` example | x |\n\n"
        "## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    )
    bounds = bc.approval_section_bounds(content)
    assert bounds is not None
    assert "- [x] Approved to proceed" in content[bounds[0]:bounds[1]]


def test_approval_section_bounds_real_vs_prose_decoy_line_anchored():
    # An INDENTED `## Approval`-like line (leading spaces) is NOT at a line-start
    # boundary, so the `^##` anchor skips it and finds the real section.
    content = (
        "# D\n\n    ## Approval (indented decoy)\n\nsome `## Approval` inline prose\n\n"
        "## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    )
    bounds = bc.approval_section_bounds(content)
    assert bounds is not None
    body = content[bounds[0]:bounds[1]]
    assert "- [x] Approved to proceed" in body


def test_approval_section_bounds_duplicate_header_warn(capsys):
    content = (
        "# D\n\n## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n\n"
        "## Approval\n\n- [ ] second\n"
    )
    bounds = bc.approval_section_bounds(content)
    assert bounds is not None
    err = capsys.readouterr().err
    assert "## Approval" in err and "first match" in err


# --- read_hash_basis ------------------------------------------------------


def test_read_hash_basis_uses_approval_bounds():
    content = (
        "# D\n\nbody mentions **Hash basis:** v9 in prose\n\n"
        "## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    )
    assert bc.read_hash_basis(content) == "v1"  # prose v9 outside ## Approval ignored


def test_read_hash_basis_v2_present_bulleted():
    content = _approval(basis="v2")
    assert bc.read_hash_basis(content) == "v2"


def test_read_hash_basis_absent_returns_v1():
    assert bc.read_hash_basis(_approval()) == "v1"
    assert bc.read_hash_basis("# D\n\nno approval\n") == "v1"


def test_read_hash_basis_scoped_to_approval_body_decoy():
    content = (
        "# D\n\n- **Hash basis:** v2 (a body-prose example)\n\n"
        "## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    )
    assert bc.read_hash_basis(content) == "v1"


def test_read_write_bounds_identical():
    content = _approval(basis=None)
    bounds = bc.approval_section_bounds(content)
    body_start, body_end = bounds
    new_body = bc._upsert_basis_line(content[body_start:body_end])
    written = content[:body_start] + new_body + content[body_end:]
    assert bc.read_hash_basis(written) == "v2"


# --- _strip_trajectory_rows -----------------------------------------------


def test_strip_trajectory_rows_removes_data_only():
    content = _full(rows=[_traj_row(1), _traj_row(2), _traj_row(3)])
    out = bc._strip_trajectory_rows(content)
    assert "| 1 |" not in out and "| 2 |" not in out and "| 3 |" not in out
    assert "### Trajectory" in out
    assert "| Pass | Date |" in out  # column header kept
    assert "|------|------|" in out  # separator kept


def test_strip_trajectory_rows_sealed_dispositions_untouched():
    sealed = "- `[SEAL-01]` **Thing** (pass 1, sealed) — Defense: because reasons."
    content = _full(rows=[_traj_row(1)], sealed=sealed)
    out = bc._strip_trajectory_rows(content)
    assert sealed in out


def test_strip_trajectory_rows_latest_pass_detail_untouched():
    latest = "| [HIGH] | src | concern | Addressed | note |"
    content = _full(rows=[_traj_row(1)], latest=latest)
    out = bc._strip_trajectory_rows(content)
    assert latest in out


def test_strip_trajectory_rows_deferred_dispositions_untouched():
    deferred = "- `[DEF-01]` **Thing** → tasks.md (pass 1) — Routed because: x."
    content = _full(rows=[_traj_row(1)], deferred=deferred)
    out = bc._strip_trajectory_rows(content)
    assert deferred in out


def test_strip_trajectory_rows_no_panel_section_noop():
    content = "# D\n\nbody only\n"
    assert bc._strip_trajectory_rows(content) == content


def test_strip_trajectory_rows_no_trajectory_noop():
    content = "# D\n\n## Panel Review\n\nno trajectory here\n\n## Approval\n"
    assert bc._strip_trajectory_rows(content) == content


def test_strip_trajectory_rows_empty_table_noop():
    content = _full(rows=[])
    assert bc._strip_trajectory_rows(content) == content


def test_strip_trajectory_fenced_code_block_not_matched():
    content = (
        "# D\n\n## Panel Review\n\n```\n### Trajectory\n\n" + _TRAJ_TBL_HEADER
        + _traj_row(1) + "\n```\n\n## Approval\n"
    )
    # The Trajectory heading is inside a fence -> not treated as the real table.
    assert bc._strip_trajectory_rows(content) == content


def test_strip_trajectory_outside_panel_untouched():
    content = (
        "# D\n\n## Other\n\n### Trajectory\n\n" + _TRAJ_TBL_HEADER + _traj_row(1)
        + "\n\n## Approval\n"
    )
    assert bc._strip_trajectory_rows(content) == content


def test_strip_trajectory_sealed_before_trajectory():
    body = (
        "## Panel Review\n\n### Sealed dispositions\n\n- `[SEAL-01]` keep me\n\n"
        "### Trajectory\n\n" + _TRAJ_TBL_HEADER + _traj_row(7) + "\n"
    )
    content = "# D\n\n" + body + "\n## Approval\n"
    out = bc._strip_trajectory_rows(content)
    assert "- `[SEAL-01]` keep me" in out
    assert "| 7 |" not in out


def test_strip_trajectory_duplicate_headings():
    body = (
        "## Panel Review\n\n### Trajectory\n\n" + _TRAJ_TBL_HEADER + _traj_row(1) + "\n\n"
        "### Trajectory\n\n" + _TRAJ_TBL_HEADER + _traj_row(2) + "\n"
    )
    content = "# D\n\n" + body + "\n## Approval\n"
    out = bc._strip_trajectory_rows(content)
    # First Trajectory stripped; the second heading's table is in a later sub-section
    assert "| 1 |" not in out


def test_strip_trajectory_cell_with_heading_like_string():
    row = "| 4 | 2026-06-12 | 0 | 0 | 0 | 0 | 0 | mentions ### foo inline |"
    content = _full(rows=[row])
    out = bc._strip_trajectory_rows(content)
    assert "| 4 |" not in out  # whole row removed, no misparse on the ### in the cell


def test_strip_trajectory_idempotent():
    content = _full(rows=[_traj_row(1), _traj_row(2)])
    once = bc._strip_trajectory_rows(content)
    assert bc._strip_trajectory_rows(once) == once


def test_strip_trajectory_composes_with_trim_trajectory_table():
    content = _full(rows=[_traj_row(n) for n in range(1, 20)])
    a = bc._strip_trajectory_rows(bc.trim_trajectory_table(content))
    b = bc.trim_trajectory_table(bc._strip_trajectory_rows(content))
    assert a == b


def test_strip_trajectory_trim_boundary_15_rows():
    # Stable across the 15-row trim default: strip removes all data rows either way.
    for n in (14, 15, 16, 20):
        content = _full(rows=[_traj_row(i) for i in range(1, n + 1)])
        out = bc._strip_trajectory_rows(content)
        assert "| 2026-06-12 |" not in out  # no data row survives the strip


# --- content_for_hashing v2 + v1 frozen -----------------------------------


def test_content_for_hashing_v2_strips_trajectory():
    a = bc.content_for_hashing(_full(rows=[_traj_row(1)]))
    b = bc.content_for_hashing(_full(rows=[_traj_row(1), _traj_row(2), _traj_row(3)]))
    assert a == b  # Trajectory growth does not change the hashed form


def test_content_for_hashing_v2_neutralizes_basis_line_bulleted():
    no_basis = bc.compute_content_hash(_approval(basis=None))
    bulleted = bc.compute_content_hash(_approval(basis="v2"))
    assert no_basis == bulleted


def test_content_for_hashing_v2_neutralizes_basis_line_bare():
    bare = "# D\n\n## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n**Hash basis:** v2\n"
    plain = "# D\n\n## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    assert bc.compute_content_hash(bare) == bc.compute_content_hash(plain)


def test_content_for_hashing_v2_idempotent_with_panel():
    content = _full(rows=[_traj_row(1), _traj_row(2)], basis="v2")
    once = bc.content_for_hashing(content)
    assert bc.content_for_hashing(once) == once


def test_content_for_hashing_v1_frozen_golden_string():
    inp = (
        "# Doc\n\n## Approval\n\n"
        "- [x] Approved to proceed to next phase\n"
        "- **Content Hash:** `deadbeefdeadbeef`\n"
    )
    expected = (
        "# Doc\n\n## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`"
    )
    assert bc._content_for_hashing_v1_frozen(inp) == expected


def test_content_for_hashing_v1_frozen_does_not_strip_trajectory():
    content = _full(rows=[_traj_row(1), _traj_row(2)])
    out = bc._content_for_hashing_v1_frozen(content)
    assert "| 1 |" in out and "| 2 |" in out  # v1 keeps Trajectory rows


# --- basis-line upsert + hash invariance ----------------------------------


def test_basis_line_value_is_hash_invariant():
    h_none = bc.compute_content_hash(_full(rows=[_traj_row(1)], basis=None))
    h_v1 = bc.compute_content_hash(_full(rows=[_traj_row(1)], basis="v1"))
    h_v2 = bc.compute_content_hash(_full(rows=[_traj_row(1)], basis="v2"))
    assert h_none == h_v1 == h_v2


def test_basis_line_no_duplication_on_restamp():
    body = "\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    once = bc._upsert_basis_line(body)
    twice = bc._upsert_basis_line(once)
    assert once.count("**Hash basis:**") == 1
    assert twice.count("**Hash basis:**") == 1


def test_basis_line_insert_on_first_stamp():
    body = "\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    out = bc._upsert_basis_line(body)
    assert out.count("- **Hash basis:** v2") == 1
    assert "**Content Hash:** `h`\n- **Hash basis:** v2" in out


# --- is_basis_migration_only / compute_content_hash_v1 --------------------


def test_is_basis_migration_only_true():
    content = _full(rows=[_traj_row(1)], basis=None)  # v1 artifact
    trimmed = bc.trim_trajectory_table(content)
    stored = bc.compute_content_hash_v1(trimmed)
    assert bc.is_basis_migration_only(
        original_content=content, stored_hash=stored, content_trimmed=trimmed
    ) is True


def test_is_basis_migration_only_false_v2_basis():
    content = _full(rows=[_traj_row(1)], basis="v2")
    trimmed = bc.trim_trajectory_table(content)
    stored = bc.compute_content_hash_v1(trimmed)
    assert bc.is_basis_migration_only(
        original_content=content, stored_hash=stored, content_trimmed=trimmed
    ) is False


def test_is_basis_migration_only_false_pending():
    content = _full(rows=[_traj_row(1)], basis=None, hash_val="pending")
    trimmed = bc.trim_trajectory_table(content)
    assert bc.is_basis_migration_only(
        original_content=content, stored_hash="pending", content_trimmed=trimmed
    ) is False


def test_is_basis_migration_only_false_unchecked():
    content = _full(rows=[_traj_row(1)], basis=None, checked=False)
    trimmed = bc.trim_trajectory_table(content)
    stored = bc.compute_content_hash_v1(trimmed)
    assert bc.is_basis_migration_only(
        original_content=content, stored_hash=stored, content_trimmed=trimmed
    ) is False


def test_is_basis_migration_only_false_v1_hash_mismatch():
    content = _full(rows=[_traj_row(1)], basis=None)
    trimmed = bc.trim_trajectory_table(content)
    assert bc.is_basis_migration_only(
        original_content=content, stored_hash="0" * 16, content_trimmed=trimmed
    ) is False


def test_compute_content_hash_v1_matches_frozen():
    import hashlib as _hl
    content = _full(rows=[_traj_row(1)])
    expected = _hl.sha256(
        bc._content_for_hashing_v1_frozen(content).encode("utf-8")
    ).hexdigest()[:16]
    assert bc.compute_content_hash_v1(content) == expected


# --- R9: read_open_obligation / preserve / any-qualifying-tag -------------


def test_read_open_obligation_returns_entry_when_present(tmp_path):
    bc.upsert_pending_entry(tmp_path, "specs/f/spec.md", "a" * 16, "t", 3)
    entry = bc.read_open_obligation(marker_root=tmp_path, doc_rel="specs/f/spec.md")
    assert entry is not None
    assert entry["hash"] == "a" * 16 and entry["stamped_at_pass"] == 3


def test_read_open_obligation_none_when_entry_absent(tmp_path):
    bc.upsert_pending_entry(tmp_path, "specs/f/spec.md", "a" * 16, "t", 1)
    assert bc.read_open_obligation(marker_root=tmp_path, doc_rel="specs/other/spec.md") is None


def test_read_open_obligation_none_on_missing_file(tmp_path):
    assert bc.read_open_obligation(marker_root=tmp_path, doc_rel="specs/f/spec.md") is None


def test_read_open_obligation_none_on_parse_or_unknown_version(tmp_path):
    sdd = tmp_path / ".sdd"
    sdd.mkdir()
    (sdd / "pending-review.json").write_text("{not json", encoding="utf-8")
    assert bc.read_open_obligation(marker_root=tmp_path, doc_rel="specs/f/spec.md") is None
    (sdd / "pending-review.json").write_text(
        '{"schemaVersion": 99, "pending": {"specs/f/spec.md": {"hash": "' + "a" * 16 + '"}}}',
        encoding="utf-8",
    )
    assert bc.read_open_obligation(marker_root=tmp_path, doc_rel="specs/f/spec.md") is None


def test_read_open_obligation_none_on_malformed_hash_entry(tmp_path):
    sdd = tmp_path / ".sdd"
    sdd.mkdir()
    (sdd / "pending-review.json").write_text(
        '{"schemaVersion": 1, "pending": {"specs/f/spec.md": {"hash": null, "stamped_at_pass": 1}}}',
        encoding="utf-8",
    )
    assert bc.read_open_obligation(marker_root=tmp_path, doc_rel="specs/f/spec.md") is None
    (sdd / "pending-review.json").write_text(
        '{"schemaVersion": 1, "pending": {"specs/f/spec.md": {"hash": "zzz", "stamped_at_pass": 1}}}',
        encoding="utf-8",
    )
    assert bc.read_open_obligation(marker_root=tmp_path, doc_rel="specs/f/spec.md") is None


def test_preserve_obligation_closing_condition_hash_byte_identical(tmp_path):
    bc.upsert_pending_entry(tmp_path, "specs/f/spec.md", "1234abcd5678ef90", "t0", 4)
    entry = bc.read_open_obligation(marker_root=tmp_path, doc_rel="specs/f/spec.md")
    bc._preserve_obligation_closing_condition(
        marker_root=tmp_path, doc_rel="specs/f/spec.md", open_entry=entry
    )
    after = bc.read_pending_review(tmp_path)["pending"]["specs/f/spec.md"]
    assert after["hash"] == "1234abcd5678ef90"  # byte-identical, never re-derived


def test_preserve_obligation_closing_condition_stamped_at_pass_unchanged(tmp_path):
    bc.upsert_pending_entry(tmp_path, "specs/f/spec.md", "a" * 16, "t0", 7)
    entry = bc.read_open_obligation(marker_root=tmp_path, doc_rel="specs/f/spec.md")
    bc._preserve_obligation_closing_condition(
        marker_root=tmp_path, doc_rel="specs/f/spec.md", open_entry=entry
    )
    after = bc.read_pending_review(tmp_path)["pending"]["specs/f/spec.md"]
    assert after["stamped_at_pass"] == 7


def test_preserve_obligation_closing_condition_refreshes_only_stamped_at(tmp_path):
    bc.upsert_pending_entry(tmp_path, "specs/f/spec.md", "a" * 16, "old-ts", 2)
    entry = bc.read_open_obligation(marker_root=tmp_path, doc_rel="specs/f/spec.md")
    bc._preserve_obligation_closing_condition(
        marker_root=tmp_path, doc_rel="specs/f/spec.md", open_entry=entry
    )
    after = bc.read_pending_review(tmp_path)["pending"]["specs/f/spec.md"]
    assert after["hash"] == "a" * 16 and after["stamped_at_pass"] == 2


def test_doc_has_any_qualifying_tag_finds_tag_at_any_pass():
    content = _full(rows=[_traj_row(2, notes="upstream-panel aaaaaaaa")])
    assert bc._doc_has_any_qualifying_tag(content, "aaaaaaaa") is True
    # _doc_has_qualifying_tag keeps the > anchor filter
    assert bc._doc_has_qualifying_tag(content, "aaaaaaaa", 1) is True
    assert bc._doc_has_qualifying_tag(content, "aaaaaaaa", 2) is False  # not > 2
    # raw-text invariant: feeding the hashed (Trajectory-stripped) form -> no tag
    stripped = bc.content_for_hashing(content)
    assert bc._doc_has_any_qualifying_tag(stripped, "aaaaaaaa") is False


# --- R10: orphaned-row detection + trajectory bounds ----------------------


def _doc_with_orphan(orphan_line, contiguous_passes=(1, 2, 3)):
    rows = "".join(_traj_row(p) + "\n" for p in contiguous_passes)
    return (
        "# D\n\n## Panel Review\n\n### Trajectory\n\n" + _TRAJ_TBL_HEADER + rows
        + "\n" + orphan_line + "\n\n### Sealed dispositions\n\n- `[SEAL-01]` x\n\n"
        "## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    )


def test_orphaned_row_token():
    assert bc.ORPHANED_TRAJECTORY_TOKEN == "ORPHANED-TRAJECTORY-ROW:"


def test_find_orphaned_rows_none_when_contiguous():
    content = _full(rows=[_traj_row(1), _traj_row(2), _traj_row(3)])
    assert bc.find_orphaned_trajectory_rows(content) == []


def test_find_orphaned_rows_load_bearing_pass_gt_max():
    content = _doc_with_orphan(_traj_row(29), contiguous_passes=(1, 2, 3))
    orphans = bc.find_orphaned_trajectory_rows(content)
    assert len(orphans) == 1
    assert orphans[0]["pass_int"] == 29 and orphans[0]["load_bearing"] is True


def test_find_orphaned_rows_load_bearing_upstream_tag():
    content = _doc_with_orphan(_traj_row(2, notes="upstream-panel aaaaaaaa"),
                               contiguous_passes=(1, 2, 3))
    orphans = bc.find_orphaned_trajectory_rows(content)
    assert len(orphans) == 1
    assert orphans[0]["has_upstream_tag"] is True and orphans[0]["load_bearing"] is True


def test_find_orphaned_rows_non_load_bearing_low_pass_no_tag():
    content = _doc_with_orphan(_traj_row(2), contiguous_passes=(1, 2, 3))
    orphans = bc.find_orphaned_trajectory_rows(content)
    assert len(orphans) == 1
    assert orphans[0]["load_bearing"] is False


def test_find_orphaned_rows_fence_aware_and_excludes_second_table():
    rows = "".join(_traj_row(p) + "\n" for p in (1, 2, 3))
    second_table = (
        "| A | B |\n|---|---|\n| 99 | x |\n"  # a different contiguous table
    )
    fenced = "```\n| 88 | fenced pipe |\n```\n"
    prose = "see `| 77 | prose example |` inline\n"
    content = (
        "# D\n\n## Panel Review\n\n### Trajectory\n\n" + _TRAJ_TBL_HEADER + rows
        + "\n" + fenced + "\n" + prose + "\n" + second_table
        + "\n## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    )
    orphans = bc.find_orphaned_trajectory_rows(content)
    assert orphans == []
    # fail-soft: a degenerate region never raises
    assert bc.find_orphaned_trajectory_rows("### Trajectory\n\nno table\n") == []


def test_find_orphaned_rows_parsed_max_matches_stamped_at_pass_basis():
    content = _doc_with_orphan(_traj_row(29), contiguous_passes=(1, 2, 3))
    # The orphan (pass 29) must NOT count toward the anchor max (it is excluded
    # by construction — shared _trajectory_bounds).
    assert bc.stamped_at_pass_from_content(content) == 3


def test_find_orphaned_rows_per_orphan_multiple():
    rows = "".join(_traj_row(p) + "\n" for p in (1, 2, 3))
    content = (
        "# D\n\n## Panel Review\n\n### Trajectory\n\n" + _TRAJ_TBL_HEADER + rows
        + "\n" + _traj_row(29) + "\n\n" + _traj_row(2) + "\n\n"
        "## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    )
    orphans = bc.find_orphaned_trajectory_rows(content)
    assert len(orphans) == 2
    by_lb = sorted(o["load_bearing"] for o in orphans)
    assert by_lb == [False, True]  # one load-bearing (29), one not (2)


def test_trajectory_bounds_shared_single_source():
    # _trajectory_data_rows and find_orphaned share _trajectory_bounds: the orphan
    # scan starts exactly where the contiguous data rows end.
    content = _doc_with_orphan(_traj_row(29), contiguous_passes=(1, 2, 3, 4))
    rows = bc._trajectory_data_rows(content)
    assert len(rows) == 4  # contiguous rows only (1..4), orphan excluded
    # behavior-preserving: trim on a >15-row table still elides and keeps 15
    big = _full(rows=[_traj_row(n) for n in range(1, 21)])
    trimmed = bc.trim_trajectory_table(big)
    assert "earlier passes elided" in trimmed
    assert bc.stamped_at_pass_from_content(big) == 20


# --- DEF-03 characterization: blueprint slice delegates to shared bounds ---


def test_approval_section_slice_delegates_to_bounds():
    vb_dir = _SCRIPTS.parent / "skills" / "project-blueprint" / "scripts"
    if str(vb_dir) not in sys.path:
        sys.path.insert(0, str(vb_dir))
    import importlib
    vb = importlib.import_module("validate_blueprint")
    content = (
        "# PLAN\n\nbody\n\n## Approval\n\n- [x] Approved to proceed\n"
        "- **Content Hash:** `h`\n"
    )
    assert vb._approval_section_slice(content) == bc.approval_section_bounds(content)


# --- Code-review fixes #1 / #3 (basis-aware coherence; unified locators) ---


def test_verify_content_hash_any_basis_accepts_v1_and_v2():
    # A v1-stamped artifact (no basis line): strict v2 REJECTS it (so check_approval
    # still surfaces the migration FAIL), but the basis-aware helper ACCEPTS it.
    doc = _full(rows=[_traj_row(1)], basis=None)
    v1 = bc.compute_content_hash_v1(bc.trim_trajectory_table(doc))
    doc_v1 = doc.replace("`abc1234567890def`", f"`{v1}`")
    assert bc.verify_content_hash(doc_v1, v1) is False           # strict v2
    assert bc.verify_content_hash_any_basis(doc_v1, v1) is True  # basis-aware
    # A v2 artifact is accepted by both.
    doc2 = _full(rows=[_traj_row(1)], basis="v2")
    v2 = bc.compute_content_hash(doc2)
    doc_v2 = doc2.replace("`abc1234567890def`", f"`{v2}`")
    assert bc.verify_content_hash(doc_v2, v2) is True
    assert bc.verify_content_hash_any_basis(doc_v2, v2) is True
    # A genuinely-stale v1 artifact (wrong stored hash) is rejected by both.
    assert bc.verify_content_hash_any_basis(doc_v1, "0" * 16) is False


def test_approval_hash_matches_accepts_v1_basis():
    # approval_hash_matches (backs is_shipped / classify_spec) must treat a
    # v1-coherent artifact as approved so a shipped feature isn't de-classified.
    doc = _full(rows=[_traj_row(1)], basis=None)
    v1 = bc.compute_content_hash_v1(bc.trim_trajectory_table(doc))
    doc_v1 = doc.replace("`abc1234567890def`", f"`{v1}`")
    assert bc.approval_hash_matches(doc_v1) is True


def test_trajectory_locators_agree_on_panel_table():
    # An EXAMPLE `### Trajectory` heading before `## Panel Review`: the anchor/trim/
    # orphan locator must pick the REAL in-Panel table (passes 1..3), matching the
    # hash path — NOT the earlier example (pass 99).
    doc = (
        "# D\n\n## Examples\n\n### Trajectory\n\n" + _TRAJ_TBL_HEADER + _traj_row(99) + "\n\n"
        "## Panel Review\n\n### Trajectory\n\n" + _TRAJ_TBL_HEADER
        + _traj_row(1) + "\n" + _traj_row(2) + "\n" + _traj_row(3) + "\n\n"
        "## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    )
    assert bc.stamped_at_pass_from_content(doc) == 3  # in-Panel table, not the example
    # adding a row to the in-Panel table does not move the hash (it is the table
    # the hash strips) — confirming both locators agree on the same table
    h1 = bc.compute_content_hash(doc)
    doc2 = doc.replace(
        _traj_row(3) + "\n\n## Approval",
        _traj_row(3) + "\n" + _traj_row(4) + "\n\n## Approval",
    )
    assert bc.compute_content_hash(doc2) == h1


def test_reconcile_surfaces_stranded_obligation(tmp_path):
    """3.5d: a pending entry whose target file no longer exists AND is out of the
    current prefix scope (a renamed/deleted spec dir) is surfaced as a non-blocking
    WARN, so it is never silent — even though the prefix-scoped reconcile can't
    see it."""
    # Seed an obligation for a path that does not exist on disk.
    bc.upsert_pending_entry(tmp_path, "specs/F3-old/spec.md", "a" * 16, "t", 1)
    # Reconcile on a DIFFERENT prefix (the renamed dir).
    res = bc.reconcile_to_result(
        tmp_path, "specs/F3-new",
        decline_cmd="validate_spec.py specs/F3-new --decline-pending",
    )
    blob = " | ".join(c[2] for c in res.checks)
    assert bc.STRANDED_OBLIGATION_TOKEN in blob
    assert "specs/F3-old/spec.md" in blob
    # Non-blocking: surfaced as a WARN, the result still passes.
    assert res.passed and res.has_warnings


def test_reconcile_no_stranded_warn_when_target_exists(tmp_path):
    """An out-of-scope obligation whose target file DOES exist is not stranded."""
    (tmp_path / "specs" / "F9-other").mkdir(parents=True)
    (tmp_path / "specs" / "F9-other" / "spec.md").write_text("# x\n", encoding="utf-8")
    bc.upsert_pending_entry(tmp_path, "specs/F9-other/spec.md", "a" * 16, "t", 1)
    res = bc.reconcile_to_result(
        tmp_path, "specs/F3-new", decline_cmd="x",
    )
    assert bc.STRANDED_OBLIGATION_TOKEN not in " | ".join(c[2] for c in res.checks)


def test_marker_lock_is_reentrant(tmp_path):
    """R3.4: nested _marker_lock (restamp -> upsert) must not deadlock, and the
    depth counter returns to 0. The lock + counter live in pending_review (R3.1);
    bc._marker_lock is the re-export."""
    import pending_review as pr
    assert pr._marker_lock_depth == 0
    with bc._marker_lock(tmp_path):
        assert pr._marker_lock_depth == 1
        with bc._marker_lock(tmp_path):
            assert pr._marker_lock_depth == 2
        assert pr._marker_lock_depth == 1
    assert pr._marker_lock_depth == 0


def test_marker_lock_excludes_other_process(tmp_path):
    """R3.4: while this process holds _marker_lock, another process cannot acquire
    an exclusive lock on the same .sdd/pending-review.lock — proving the lock is a
    real cross-process advisory lock, not just an in-process counter."""
    import subprocess
    import pending_review as pr
    if pr._fcntl is None:  # pragma: no cover - non-POSIX
        import pytest
        pytest.skip("fcntl unavailable")
    lock_path = (tmp_path / ".sdd" / "pending-review.lock")
    child = (
        "import fcntl, sys\n"
        f"f = open(r'{lock_path}', 'a+')\n"
        "try:\n"
        "    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
        "    print('GOT')\n"
        "except BlockingIOError:\n"
        "    print('BLOCKED')\n"
    )
    with bc._marker_lock(tmp_path):
        out = subprocess.run(
            [sys.executable, "-c", child], capture_output=True, text=True
        ).stdout.strip()
    assert out == "BLOCKED", out
    # Released after the context — the child can now acquire it.
    out2 = subprocess.run(
        [sys.executable, "-c", child], capture_output=True, text=True
    ).stdout.strip()
    assert out2 == "GOT", out2
