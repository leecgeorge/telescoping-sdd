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
