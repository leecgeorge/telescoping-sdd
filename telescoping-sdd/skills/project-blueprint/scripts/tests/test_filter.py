"""T4 — Content filter (C5) tests for render_business_brief.py.

Split from the original test_render_business_brief.py per P3-15. Shared
helpers and constants live in `common.py`; shared fixtures (tiny PNG path,
approved-triple fixtures, panel-review fixture) live in `conftest.py`.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(_SCRIPTS_DIR))

import render_business_brief  # noqa: E402


@pytest.fixture
def fixture_scope_with_panel_review_and_frontmatter() -> str:
    return (
        "---\n"
        "title: Scope\n"
        "---\n"
        "\n"
        "# Project Scope\n"
        "\n"
        "Decision-context per [SEAL-01] applies.\n"
        "\n"
        "## Panel Review\n"
        "\n"
        "### Trajectory\n"
        "\n"
        "| Pass | HIGHs |\n"
        "|------|-------|\n"
        "| 1    | 3     |\n"
        "\n"
        "### Sealed dispositions\n"
        "\n"
        "- `[SEAL-02]` something\n"
        "\n"
        "## Approval\n"
        "\n"
        "- [x] Approved to proceed\n"
        "- **Content Hash:** `4417a0d55fa4c2ec`\n"
    )


_R2_CASES = [
    (
        "frontmatter",
        "---\nkey: val\n---\nBody\n",
        ["---", "key: val"],
        ["Body"],
    ),
    (
        "panel_review",
        "# Doc\n\nBody\n\n## Panel Review\n\nDetail\n\n### Trajectory\n\nRow\n",
        ["## Panel Review", "Trajectory", "Row"],
        ["# Doc", "Body"],
    ),
    (
        "approval",
        "# Doc\n\n## Approval\n\n- [x] Approved\n- **Content Hash:** `4417a0d55fa4c2ec`\n",
        ["## Approval", "Approved", "4417a0d55fa4c2ec"],
        ["# Doc"],
    ),
    (
        "inline_tokens",
        "Decision per [SEAL-01] and [DEF-2] and [SCOPE-3] and [ARCH-7] and [CFC-2].\n",
        ["[SEAL-01]", "[DEF-2]", "[SCOPE-3]", "[ARCH-7]", "[CFC-2]"],
        ["Decision per", "and"],
    ),
    (
        "content_hash",
        "Decision **Content Hash:** `4417a0d55fa4c2ec` stays\n",
        ["**Content Hash:**", "4417a0d55fa4c2ec"],
        ["Decision", "stays"],
    ),
    (
        "cfc_section_retained",
        "## Cross-Feature Contracts\n\n### CFC-1: Lock order\n\nBody [CFC-1] body.\n",
        ["[CFC-1]"],
        ["## Cross-Feature Contracts", "Lock order", "Body body."],
    ),
]


@pytest.mark.parametrize(
    "label,doc,absent_fragments,present_fragments", _R2_CASES,
    ids=[c[0] for c in _R2_CASES],
)
def test_filter_per_rule_parametrized(label, doc, absent_fragments, present_fragments):
    out = render_business_brief.filter_content(doc)
    for frag in absent_fragments:
        assert frag not in out, f"{label}: expected absent fragment {frag!r}, got: {out!r}"
    for frag in present_fragments:
        assert frag in out, f"{label}: expected present fragment {frag!r}, got: {out!r}"


@pytest.mark.parametrize(
    "label,doc",
    [
        ("no_frontmatter", "# Doc\n\nBody\n"),
        ("body_hr_line", "# Doc\n\n---\n\nMore body\n"),
        ("unclosed_frontmatter", "---\nkey: val\nbody but no close\n"),
        ("trailing_ws_close_delim", "---\nkey: val\n---  \nBody\n"),
        ("bom_prefixed", "﻿---\nkey: val\n---\nBody\n"),
    ],
)
def test_filter_frontmatter_evasion_cases_parametrized(label, doc):
    out = render_business_brief.filter_content(doc)
    if label == "no_frontmatter":
        assert out == doc
    elif label == "body_hr_line":
        assert "---" in out  # the body hr line survives
        assert "More body" in out
    elif label == "unclosed_frontmatter":
        # No closing delim → no match → input passes through
        assert out == doc
    elif label == "trailing_ws_close_delim":
        assert "key: val" not in out
        assert "Body" in out
    elif label == "bom_prefixed":
        # BOM prefix breaks `\A---` anchor; documented behaviour is that
        # callers strip BOM via utf-8-sig before filtering (see T3 note).
        assert out.startswith("﻿")


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("a [SEAL-01] b", "a b"),
        ("a [DEF-12] b", "a b"),
        ("a [SCOPE-3] b", "a b"),
        ("a [ARCH-7] b", "a b"),
        ("a [CFC-2] b", "a b"),
        ("a [SEAL-001] b", "a b"),
        ("[SEAL-01] start", " start"),  # start-of-string: no leading space to absorb
        ("end [SEAL-01]", "end"),
        ("a [SEAL-1]. end", "a. end"),
        ("a [SEAL-1] [SEAL-2] b", "a b"),
    ],
)
def test_filter_inline_tokens_parametrized(input_text, expected):
    assert render_business_brief.filter_content(input_text) == expected


def test_filter_inline_token_word_fusion_documented():
    """When no preceding space, the token is removed but no merge happens —
    the prior character stays intact (documents the no-leading-space case)."""
    assert render_business_brief.filter_content("word[SEAL-01]more") == "wordmore"


def test_filter_inline_tokens_in_table_cell():
    """Token in a table cell: token removed, cell delimiters intact."""
    doc = "| Col | Other |\n|-----|-------|\n| a [SEAL-01] | b |\n"
    out = render_business_brief.filter_content(doc)
    assert "[SEAL-01]" not in out
    assert "| a | b |" in out


def test_filter_does_not_collapse_intentional_double_spaces():
    """Two-space markdown line break and 4-space code indent are preserved."""
    doc = "line one  \nline two\n\n    indented code\n"
    out = render_business_brief.filter_content(doc)
    assert "line one  \nline two" in out
    assert "    indented code" in out


def test_filter_ordering_contract_textual():
    """Rules 1-3 are order-required; rules 4-5 may swap. Document via textual
    inspection so a future re-ordering must update the contract first."""
    src = inspect.getsource(render_business_brief.filter_content)
    idx_frontmatter = src.index("_FILTER_FRONTMATTER")
    idx_panel = src.index("_FILTER_PANEL_REVIEW_SECTION")
    idx_approval = src.index("_FILTER_APPROVAL_SECTION")
    idx_tokens = src.index("_FILTER_INLINE_TOKENS")
    idx_hash = src.index("_FILTER_CONTENT_HASH")
    assert idx_frontmatter < idx_panel < idx_approval
    assert idx_panel < idx_tokens and idx_panel < idx_hash
    assert idx_approval < idx_tokens and idx_approval < idx_hash


def test_filter_constants_sourced_from_shared_grammar():
    """I3.5: the Business Brief filters must be BUILT FROM the shared grammar
    constants, not re-hardcode their own tag-family list or hash width — a
    re-hardcode is exactly the drift channel that leaks a stray token/hash into
    stakeholder HTML."""
    import blueprint_common as bc

    # Inline-token filter alternates exactly the canonical families, in order.
    for fam in bc.INLINE_TAG_FAMILIES:
        assert fam in render_business_brief._FILTER_INLINE_TOKENS.pattern
    assert (
        render_business_brief._FILTER_INLINE_TOKENS.pattern
        == r" ?\[(%s)-\d+\]" % bc.INLINE_TAG_FAMILIES_RE
    )
    # Content-hash filter uses the shared width fragment (no independent {N}).
    assert bc.CONTENT_HASH_HEX in render_business_brief._FILTER_CONTENT_HASH.pattern
    assert bc.CONTENT_HASH_HEX == r"[0-9a-f]{%d}" % bc.CONTENT_HASH_WIDTH


def test_inline_tag_families_cover_validator_recognized_tags():
    """I3.5: every `[FAMILY-N]` tag a validator actually RECOGNIZES must be a
    member of INLINE_TAG_FAMILIES — otherwise the Business Brief filter, which
    builds its strip-list from that tuple, would let the unlisted family leak
    through into stakeholder HTML. Guards against adding a recognizer without
    extending the canonical set."""
    import archive_pass
    import blueprint_common as bc
    import cfc_parser

    families = set(bc.INLINE_TAG_FAMILIES)
    # Families with a structured recognizer in the validators.
    assert "SEAL" in families  # archive_pass.SEAL_PAT
    assert "DEF" in families  # archive_pass.DEF_PAT
    assert "CFC" in families  # cfc_parser.CFC_TAG_PATTERN
    # The recognizer regexes embed the family literal — assert they agree.
    assert "[SEAL-" in archive_pass.SEAL_PAT.pattern
    assert "[DEF-" in archive_pass.DEF_PAT.pattern
    assert "CFC-" in cfc_parser.CFC_TAG_PATTERN.pattern


def test_filter_content_hash_construct():
    """The `**Content Hash:** \\`<16-hex>\\`` exact emit shape is stripped;
    bare 16-char hex elsewhere is NOT touched. Backtick is ASCII U+0060."""
    doc = (
        "Hash stamp: **Content Hash:** `4417a0d55fa4c2ec` here.\n"
        "Bare token 0123456789abcdef appears in prose.\n"
    )
    out = render_business_brief.filter_content(doc)
    assert "**Content Hash:**" not in out
    assert "4417a0d55fa4c2ec" not in out
    assert "0123456789abcdef" in out  # bare hex is preserved
    # ASCII backtick guard
    assert "`" in render_business_brief._FILTER_CONTENT_HASH.pattern
    assert "‘" not in render_business_brief._FILTER_CONTENT_HASH.pattern
    assert "’" not in render_business_brief._FILTER_CONTENT_HASH.pattern


@pytest.mark.parametrize(
    "label,doc",
    [
        (
            "cfc_before_panel_review",
            "# Doc\n\n## Cross-Feature Contracts\n\n### CFC-1: Lock\n\nBody [CFC-1] body.\n\n## Panel Review\n\nDetail\n",
        ),
        (
            "cfc_after_panel_review",
            "# Doc\n\n## Panel Review\n\nDetail\n\n## Cross-Feature Contracts\n\n### CFC-1: Lock\n\nBody [CFC-1] body.\n",
        ),
    ],
)
def test_filter_cfc_section_retained_both_layout_orderings(label, doc):
    out = render_business_brief.filter_content(doc)
    assert "## Cross-Feature Contracts" in out
    assert "### CFC-1: Lock" in out
    assert "[CFC-1]" not in out
    assert "## Panel Review" not in out


@pytest.mark.parametrize(
    "label,doc",
    [
        (
            "section_followed_by_h2",
            "# Doc\n\n## Panel Review\n\nDetail\n\n## Other\n\nKeep this\n",
        ),
        ("section_at_eof", "# Doc\n\nBody\n\n## Panel Review\n\nDetail\n"),
        (
            "section_with_h3",
            "# Doc\n\n## Panel Review\n\nIntro\n\n### Trajectory\n\nRow\n",
        ),
        (
            "panel_then_approval_adjacent",
            "# Doc\n\n## Panel Review\n\nDetail\n## Approval\n\n- [x] Approved\n",
        ),
        (
            "approval_before_panel_review",
            "# Doc\n\n## Approval\n\n- [x] Approved\n\n## Panel Review\n\nDetail\n",
        ),
    ],
)
def test_filter_panel_review_approval_boundary_cases_parametrized(label, doc):
    out = render_business_brief.filter_content(doc)
    assert "## Panel Review" not in out
    assert "## Approval" not in out
    if label == "section_followed_by_h2":
        assert "## Other" in out and "Keep this" in out


@pytest.mark.xfail(
    reason="Out-of-contract: fenced code block containing literal `## ` "
    "at line start causes early section-strip truncation. The fake heading "
    "leaks into the post-filter output because the filter does not parse "
    "fenced-code-block boundaries (design.md §Filter; SEAL-10)."
)
def test_filter_out_of_contract_fenced_code_xfail():
    doc = (
        "# Doc\n\n"
        "## Panel Review\n\n"
        "```\n"
        "## fake heading\n"
        "```\n\n"
        "## Real After\n\nReal body\n"
    )
    out = render_business_brief.filter_content(doc)
    # If filter parsed fenced-code boundaries, the fake heading inside the
    # code fence would be absorbed as Panel-Review body. Without that
    # parser, the strip truncates early at the fake heading line.
    assert "## fake heading" not in out


@pytest.mark.parametrize(
    "label,heading",
    [
        ("approval_process_survives", "## Approval Process"),
        ("approval_workflow_survives", "## Approval Workflow"),
        ("panel_review_extended_survives", "## Panel Review and Approval"),
        ("panel_review_cycle_label_survives", "## Panel Review (Cycle 2)"),
    ],
)
def test_filter_section_heading_boundary_specificity(label, heading):
    """P2-2: section-strip regexes must anchor on end-of-line, not on a word
    boundary. A SCOPE/ARCH/PLAN body heading like `## Approval Process` (an
    author writing about their project's own internal approval workflow as
    a deliverable) used to be silently swallowed by the `^## Approval\\b`
    regex; this test pins the tightened `\\s*$` anchor."""
    doc = (
        "# Doc\n\n"
        "Intro body.\n\n"
        f"{heading}\n\n"
        "Body of the surviving section.\n"
    )
    out = render_business_brief.filter_content(doc)
    assert heading in out, f"{label}: heading {heading!r} silently stripped"
    assert "Body of the surviving section." in out, (
        f"{label}: body of surviving section also stripped"
    )


@pytest.mark.xfail(
    reason="Out-of-contract: markdown reference-style links like "
    "`[the doc][SCOPE-1]` plus `[SCOPE-1]: https://example.com` get corrupted "
    "by _FILTER_INLINE_TOKENS, which strips the `[SCOPE-1]` reference key and "
    "leaves a dangling `: https://example.com` line (P2-7). Authors are "
    "expected to use inline `[the doc](https://...)` links instead — see "
    "phase-business-brief.md §Authoring rules. Documented as accepted risk "
    "because reference-style links are rare in business-brief author copy."
)
def test_filter_out_of_contract_reference_link_xfail():
    doc = (
        "Read [the doc][SCOPE-1] for details.\n\n"
        "[SCOPE-1]: https://example.com/scope\n"
    )
    out = render_business_brief.filter_content(doc)
    # If the filter understood markdown reference-link syntax, both the inline
    # `[SCOPE-1]` AND the `[SCOPE-1]: url` definition would be preserved (or
    # both removed). Currently the inline tag is stripped but the definition
    # row is mutilated into `: https://example.com/scope` — broken output.
    assert ": https://example.com" not in out


def test_filter_content_idempotency(fixture_scope_with_panel_review_and_frontmatter):
    doc = fixture_scope_with_panel_review_and_frontmatter
    once = render_business_brief.filter_content(doc)
    twice = render_business_brief.filter_content(once)
    assert once == twice
