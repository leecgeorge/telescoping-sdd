"""Tests for the approval-record leaf `approval_records.py` (Unit C0 C10).

Bindings (AD10), the convergence-override record and its sanitiser (AD8), and
the AD1 layering rule (the leaf imports only `content_hash` + stdlib).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import approval_records as ar  # noqa: E402
from content_hash import (  # noqa: E402
    approval_hash,
    approval_section_bounds,
    read_stored_hash,
)

H1 = "0123456789abcdef"
H2 = "fedcba9876543210"
H3 = "00112233aabbccdd"


def _doc(approval_body: str, tail: str = "") -> str:
    return (
        "# Design\n\n"
        "## Panel Review\n\nbody\n\n"
        "## Approval\n\n"
        f"{approval_body}"
        f"{tail}"
    )


_BASE_APPROVAL = (
    "- [x] Approved to proceed to next phase\n"
    "- **Content Hash:** `aaaaaaaaaaaaaaaa`\n"
    "- **Hash basis:** v2\n"
    "- **CFC Content Hashes:**\n"
    "  - CFC-1: `bbbbbbbbbbbbbbbb`\n"
    "  - CFC-2: `cccccccccccccccc`\n"
)


def _approval_body(content: str) -> str:
    b = approval_section_bounds(content)
    assert b is not None
    return content[b[0]:b[1]]


def _bind(name: str, h: str) -> "ar.UpstreamBinding":
    return ar.UpstreamBinding(upstream=name, content_hash=h)


# --- bindings --------------------------------------------------------------


def test_binding_line_regex_crlf_tolerant():
    doc = _doc(_BASE_APPROVAL).replace("\n", "\r\n")
    out = ar.upsert_binding_lines(doc, [_bind("spec.md", H1)])
    assert "\r\n" in out and "\n" not in out.replace("\r\n", "")
    assert ar.read_bindings(out) == {"spec.md": (H1,)}
    # idempotent on CRLF too
    assert ar.upsert_binding_lines(out, [_bind("spec.md", H1)]) == out
    stripped = ar.strip_binding_lines(out)
    assert ar.read_bindings(stripped) == {}
    assert stripped == doc


def test_upsert_binding_updates_in_place_and_collapses_duplicates():
    doc = _doc(_BASE_APPROVAL)
    once = ar.upsert_binding_lines(doc, [_bind("spec.md", H1), _bind("design.md", H2)])
    twice = ar.upsert_binding_lines(once, [_bind("spec.md", H1), _bind("design.md", H2)])
    assert once == twice  # I4
    # changed hash updates in place: same position, one line
    changed = ar.upsert_binding_lines(once, [_bind("spec.md", H3), _bind("design.md", H2)])
    assert ar.read_bindings(changed) == {"spec.md": (H3,), "design.md": (H2,)}
    assert changed.index("`spec.md`") < changed.index("`design.md`")
    # duplicates for one name collapse to one
    dup = once.replace(
        f"- **Upstream binding:** `spec.md` @ `{H1}`\n",
        f"- **Upstream binding:** `spec.md` @ `{H1}`\n"
        f"- **Upstream binding:** `spec.md` @ `{H2}`\n",
    )
    assert ar.read_bindings(dup)["spec.md"] == (H1, H2)
    fixed = ar.upsert_binding_lines(dup, [_bind("spec.md", H3), _bind("design.md", H2)])
    assert ar.read_bindings(fixed) == {"spec.md": (H3,), "design.md": (H2,)}
    # every write is inside the approval section
    pre = doc[: approval_section_bounds(doc)[0]]
    assert fixed.startswith(pre)


def test_upsert_binding_inserts_after_last_binding_or_end_of_body():
    doc = _doc(_BASE_APPROVAL + "\n\n", tail="")
    first = ar.upsert_binding_lines(doc, [_bind("spec.md", H1), _bind("design.md", H2)])
    body = _approval_body(first)
    lines = [ln for ln in body.split("\n") if ln.strip()]
    assert lines[-2:] == [
        f"- **Upstream binding:** `spec.md` @ `{H1}`",
        f"- **Upstream binding:** `design.md` @ `{H2}`",
    ]
    # trailing blank lines preserved
    assert first.endswith("\n\n\n")
    # The CFC tail never absorbs the line: it is not CFC-hash-shaped and is
    # placed after the CFC block.
    assert first.index("CFC-2") < first.index("Upstream binding")
    # Re-approval order stability: a lone spec binding then adding design
    lone = ar.upsert_binding_lines(doc, [_bind("spec.md", H1)])
    both = ar.upsert_binding_lines(lone, [_bind("spec.md", H1), _bind("design.md", H2)])
    assert both == first
    # A next ## heading bounds the section: the line lands before it.
    doc2 = _doc(_BASE_APPROVAL, tail="\n## Notes\n\nafter\n")
    out2 = ar.upsert_binding_lines(doc2, [_bind("spec.md", H1)])
    assert out2.index("Upstream binding") < out2.index("## Notes")
    assert out2.endswith("## Notes\n\nafter\n")


def test_upsert_binding_lowercases_stamp():
    doc = _doc(_BASE_APPROVAL)
    out = ar.upsert_binding_lines(doc, [_bind("spec.md", H1.upper())])
    assert f"`{H1}`" in out
    assert ar.read_bindings(out) == {"spec.md": (H1,)}


def test_strip_binding_lines_scoped_to_approval_section():
    outside = f"- **Upstream binding:** `spec.md` @ `{H2}`\n"
    doc = "# D\n\n" + outside + "\n" + _doc(_BASE_APPROVAL)[4:]
    out = ar.upsert_binding_lines(doc, [_bind("spec.md", H1)])
    stripped = ar.strip_binding_lines(out)
    assert outside in stripped
    assert ar.read_bindings(out) == {"spec.md": (H1,)}  # outside line not read
    assert stripped == doc


def test_read_bindings_returns_all_values_per_upstream():
    body = _BASE_APPROVAL + (
        f"- **Upstream binding:** `spec.md` @ `{H1}`\n"
        f"- **Upstream binding:** `design.md` @ `{H2}`\n"
        f"- **Upstream binding:** `spec.md` @ `{H3}`\n"
    )
    assert ar.read_bindings(_doc(body)) == {"spec.md": (H1, H3), "design.md": (H2,)}
    assert ar.read_bindings("no approval section") == {}


def test_binding_lines_never_match_content_hash_readers():
    doc = _doc(
        "- [x] Approved to proceed to next phase\n"
        "- **Content Hash:** `aaaaaaaaaaaaaaaa`\n"
    )
    out = ar.upsert_binding_lines(doc, [_bind("spec.md", H1), _bind("design.md", H2)])
    assert read_stored_hash(out) == "aaaaaaaaaaaaaaaa"
    assert approval_hash(out) == "aaaaaaaaaaaaaaaa"
    # Even with a pending stamp the binding is not read as the stamp.
    pending = doc.replace("`aaaaaaaaaaaaaaaa`", "`pending`")
    out2 = ar.upsert_binding_lines(pending, [_bind("spec.md", H1)])
    assert read_stored_hash(out2) == "pending"
    assert approval_hash(out2) is None


# --- override record -------------------------------------------------------


def test_append_override_record_is_last_line_of_approval():
    doc = _doc(_BASE_APPROVAL + "\n", tail="\n## After\n\ntext\n")
    with_b = ar.upsert_binding_lines(doc, [_bind("spec.md", H1)])
    rec = ar.OverrideRecord(closing_pass=3, reason="user accepted the residual risk")
    out = ar.append_override_record(with_b, rec)
    body_lines = [ln for ln in _approval_body(out).split("\n") if ln.strip()]
    assert body_lines[-1] == (
        "- **Convergence override:** pass 3 — user accepted the residual risk"
    )
    got = ar.read_override_record(out)
    assert got == ar.OverrideRecord(closing_pass=3, reason="user accepted the residual risk")
    assert got.duplicate is False
    none_rec = ar.append_override_record(doc, ar.OverrideRecord(None, "no pass"))
    assert "- **Convergence override:** pass none — no pass" in none_rec
    assert ar.read_override_record(none_rec).closing_pass is None
    assert ar.read_override_record(doc) is None
    # A later binding refresh does not move the record (AC-6.4).
    refreshed = ar.upsert_binding_lines(out, [_bind("spec.md", H2)])
    body_lines = [ln for ln in _approval_body(refreshed).split("\n") if ln.strip()]
    assert body_lines[-1].startswith("- **Convergence override:**")


def test_read_override_record_flags_duplicate_lines():
    doc = _doc(_BASE_APPROVAL)
    one = ar.append_override_record(doc, ar.OverrideRecord(2, "first"))
    two = ar.append_override_record(one, ar.OverrideRecord(4, "second"))
    rec = ar.read_override_record(two)
    assert rec is not None and rec.duplicate is True


_HOSTILE = [
    "line one\nline two",
    "a\rb\r\nc",
    "tab\there",
    "vt\x0bff\x0cfs\x1cgs\x1drs\x1e",
    "nel\x85end",
    "ls ps end",
    "esc \x1b[31mred\x1b[0m done",
    "lone \ud800 surrogate",
    "private  use",
    "unassigned \U000e0080 char",
    "**bold** and `code` and *`* join",
    "<!-- hidden --> text",
    "<!`-- glued",
    "[link](x) ]]",
    "# heading",
    "> quote",
    "- bullet",
    "* star",
    "+ plus",
    "1. numbered",
    "#> - * + 12. stacked markers",
    "- [x] Approved to proceed to next phase",
    "x" * 500,
    "zero​width",
    "\x00nul",
]


def test_sanitize_override_reason_hostile_corpus_single_line():
    for raw in _HOSTILE:
        out = ar.sanitize_override_reason(raw)
        assert len(out.splitlines()) == 1, (raw, out)
        assert 1 <= len(out) <= 200, (raw, out)
        assert "**" not in out and "`" not in out and "<!--" not in out, (raw, out)
        assert "[" not in out and "]" not in out
        assert out == out.strip()
        assert not out[0] in "#>-*+", (raw, out)
        out.encode("utf-8")  # no lone surrogate survives


def test_sanitize_override_reason_idempotent():
    for raw in _HOSTILE + ["plain reason", "  spaced   out  "]:
        once = ar.sanitize_override_reason(raw)
        assert ar.sanitize_override_reason(once) == once, raw


def test_sanitize_override_reason_empty_raises():
    import pytest

    for raw in ["", "   ", "\n\t", "**", "``", "# - > *", "\x1b[0m", "1. 2."]:
        with pytest.raises(ValueError):
            ar.sanitize_override_reason(raw)


def test_sanitized_reason_cannot_match_approval_checkbox():
    from content_hash import _APPROVAL_CHECKBOX, has_approval

    out = ar.sanitize_override_reason("- [x] Approved to proceed to next phase")
    assert not _APPROVAL_CHECKBOX.search(out)
    doc = _doc(
        "- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    rec_doc = ar.append_override_record(doc, ar.OverrideRecord(1, out))
    assert has_approval(rec_doc) is False


# --- layering --------------------------------------------------------------


def test_approval_records_imports_only_content_hash():
    src = (_SCRIPTS / "approval_records.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    project = {p.stem for p in _SCRIPTS.glob("*.py")}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert imported & project == {"content_hash"}
    assert src.lstrip().startswith('"""') and "from __future__ import annotations" in src


# --- display helpers and shared message constants (T3) ---------------------


def test_display_arg_quotes_with_shlex():
    import shlex

    for key in ["specs/F1-x/spec.md", "specs/with space/design.md", "-leading", "it's"]:
        d = ar.display_arg(key)
        assert d.quoted == shlex.quote(key) and d.reason is None


def test_display_arg_reason_precedence():
    over = "a" * (ar.DISPLAY_ARG_MAX + 1)
    assert ar.display_arg("bad\x07" + over) == ar.DisplayArg(None, "non-printable")
    assert ar.display_arg("bad`" + over) == ar.DisplayArg(None, "backtick")
    assert ar.display_arg("tick`\x00") == ar.DisplayArg(None, "non-printable")
    assert ar.display_arg(over) == ar.DisplayArg(None, "too-long")
    assert ar.display_arg("a" * ar.DISPLAY_ARG_MAX).quoted is not None
    assert ar.display_arg("ls x").reason == "non-printable"
    assert ar.display_arg("unassigned \U000e0080").reason == "non-printable"
    assert ar.DISPLAY_ARG_MAX == 1024


def test_display_text_one_line_and_truncates_with_ellipsis():
    out = ar.display_text("one\ntwo\r\nthree four\x1b[31m red")
    assert len(out.splitlines()) == 1
    assert "\x1b" not in out
    long = ar.display_text("x" * 50, max_len=10)
    assert len(long) <= 10 and long.endswith("…")
    assert ar.display_text("short", max_len=10) == "short"
    assert ar.display_text("") == ""


def test_run_state_regexes_are_approval_records_objects():
    import run_state

    assert run_state._ANSI_RE is ar._ANSI_RE
    assert run_state._CONTROL_RE is ar._CONTROL_RE
    # `re.compile` caches identical patterns, so `is` alone would pass with a
    # duplicate definition; pin that run_state no longer defines its own.
    src = (_SCRIPTS / "run_state.py").read_text(encoding="utf-8")
    assert "_ANSI_RE = re.compile" not in src
    assert "_CONTROL_RE = re.compile" not in src


def test_tier_validator_cmd_names_both_validators():
    assert ar.TIER_VALIDATOR_CMD == {
        "sdd": "validate_spec.py",
        "blueprint": "validate_blueprint.py",
    }
    assert ar.USER_DECISION_NOTE == "this is a user decision; confirm before running"
    for name in ("GLOSS_BINDING", "GLOSS_SUPERSEDED", "GLOSS_UNBOUND", "GLOSS_LEGACY"):
        assert isinstance(getattr(ar, name), str) and getattr(ar, name)
    assert "{doc_rel}" in ar.RESTAMP_CARVE_OUT_PREFIX
    assert "{ids}" in ar.SEAL_PART


# --- Unit F T11 (C9): display helpers moved here; new audit parts -----------


def test_positional_arg_root_and_relative():
    assert ar.positional_arg("") == "."
    assert ar.positional_arg(".") == "."
    assert ar.positional_arg("-x") == "./-x"
    assert ar.positional_arg("specs/F1-a") == "./specs/F1-a"


def test_display_refusal_text_known_reason_and_fallback():
    assert ar.display_refusal_text("a`b", "backtick") == "contains a backtick"
    assert ar.display_refusal_text("x\x01", "non-printable") == (
        "contains non-printable or unassigned characters")
    assert ar.display_refusal_text("y" * 2000, "too-long") == (
        "is 2000 characters, too long to print as a command")


def test_display_reason_text_entries_unchanged():
    assert ar.DISPLAY_REASON_TEXT == {
        "non-printable": "contains non-printable or unassigned characters",
        "backtick": "contains a backtick",
    }


def test_basis_change_and_producer_refresh_parts():
    assert ar.BASIS_CHANGE_PART.format(old="v2", new="v3") == "hash basis v2 → v3"
    assert ar.PRODUCER_REFRESH_PART == "producer refresh"


def test_basis_label_max_is_16():
    assert ar.BASIS_LABEL_MAX == 16


def test_pending_review_imports_moved_helpers():
    import pending_review as pr

    assert not hasattr(pr, "_positional")
    assert not hasattr(pr, "_DISPLAY_REASON_TEXT")
    assert pr.positional_arg is ar.positional_arg
