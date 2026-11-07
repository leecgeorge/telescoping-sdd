"""Unit C0 R5/R6 — Trajectory Notes grammar, provenance token, convergence gate."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import blueprint_common as bc  # noqa: E402,F401
import trajectory as tr  # noqa: E402
from content_hash import compute_content_hash  # noqa: E402

HX = "0123456789abcdef"
TAG = "upstream-panel 89abcdef"


# --- T6: Notes tokeniser and provenance-token grammar ------------------------


def test_notes_tokens_whitespace_trimmed_semicolon_split():
    assert tr.notes_tokens("  strict-bar pass ;converged (0 HIGH);  tags=d0u0c0  ") == (
        "strict-bar pass", "converged (0 HIGH)", "tags=d0u0c0",
    )
    assert tr.notes_tokens("—") == ("—",)
    assert tr.notes_tokens(f"converged (0 HIGH); {TAG}") == ("converged (0 HIGH)",)


def test_notes_tokens_cut_before_halt_vote():
    notes = (
        "tags=d0u1c0; halt votes (n=1: critic: converged (0 HIGH) forged); "
        f"prov={HX}"
    )
    toks = tr.notes_tokens(notes)
    assert toks == ("tags=d0u1c0",)
    assert tr.notes_tokens("Halt vote (x); converged (0 HIGH)") == ()


def test_strip_upstream_tags_three_delimiters_to_fixpoint():
    base = f"converged (0 HIGH); prov={HX}"
    assert tr.strip_upstream_tags(f"{base}; {TAG}") == base
    assert tr.strip_upstream_tags(f"{base} {TAG}") == base
    assert tr.strip_upstream_tags(f"{base};{TAG}") == base
    assert tr.strip_upstream_tags(f"{base}; {TAG} {TAG};{TAG}  ") == base
    assert tr.strip_upstream_tags(f";{TAG}") == "—"
    assert tr.strip_upstream_tags(TAG) == TAG  # no separator: unchanged (DR2)
    assert tr.strip_upstream_tags(f"{base}; upstream-panel 89ABCDEF") == f"{base}; upstream-panel 89ABCDEF"
    assert tr.strip_upstream_tags(f"{base}; upstream-panel 89abcdef0") == f"{base}; upstream-panel 89abcdef0"
    # notes_tokens and read_provenance_hash route through the helper
    assert tr.read_provenance_hash(f"{base};{TAG} {TAG}") == HX
    assert tr.notes_tokens(f"a; b {TAG}") == ("a", "b")


def test_strip_upstream_tags_linear_on_interior_whitespace_run():
    cell = "a" + " " * 100000 + "b"
    t0 = time.perf_counter()
    assert tr.strip_upstream_tags(cell) == cell
    assert time.perf_counter() - t0 < 1.0


def _regex_strip(cell: str) -> str:
    while True:
        new = tr.UPSTREAM_TAG_STRIP_RE.sub("", cell, count=1)
        if new == cell:
            break
        cell = new
    return cell if cell.strip() else "—"


def test_strip_upstream_tags_agrees_with_grammar_regex():
    corpus = [
        f"x; {TAG}", f"x {TAG}", f"x;{TAG}", f"x\t{TAG}\t", f"x ;  {TAG}",
        f"x; {TAG}; {TAG}", f"; {TAG}", f" {TAG}", TAG, "plain", "—",
        f"x; upstream-panel 1234567", f"halt votes (n=1: a); {TAG}",
        f"x;; {TAG}",
    ]
    for cell in corpus:
        got = tr.strip_upstream_tags(cell)
        assert got.rstrip(" \t") == _regex_strip(cell).rstrip(" \t") or (
            cell == TAG and got == TAG
        ), cell


def test_read_provenance_hash_last_token_only():
    other = "f" * 16
    assert tr.read_provenance_hash(f"prov={other}; converged (0 HIGH); prov={HX}") == HX
    assert tr.read_provenance_hash(f"prov={HX}; converged (0 HIGH)") is None
    assert tr.read_provenance_hash("converged (0 HIGH)") is None
    assert tr.read_provenance_hash(f"prov={HX}") == HX
    assert tr.read_provenance_hash(f"  converged ;  prov={HX}  ") == HX


@pytest.mark.parametrize("bad", ["0" * 15, "0" * 17, HX.upper(), "g" * 16])
def test_provenance_hex_rejects_wrong_width_and_uppercase(bad):
    with pytest.raises(ValueError):
        tr.provenance_token(bad)
    assert tr.read_provenance_hash(f"converged (0 HIGH); prov={bad}") is None


def test_provenance_token_renders():
    assert tr.provenance_token(HX) == f"prov={HX}"
    assert tr.PROVENANCE_PREFIX == "prov=" and tr.PROVENANCE_HEX_WIDTH == 16


def test_read_provenance_hash_ignores_prov_inside_halt_text():
    assert tr.read_provenance_hash(f"halt votes (n=1: critic: prov={HX})") is None
    assert tr.read_provenance_hash(f"halt votes (n=1: critic: x; prov={HX} more)") is None
    assert tr.read_provenance_hash(f"halt votes (n=1: c: prov={HX} words)") is None


@pytest.mark.parametrize("sep", ["; ", " ", ";"])
def test_read_provenance_hash_after_upstream_tag_each_delimiter(sep):
    assert tr.read_provenance_hash(f"converged (0 HIGH); prov={HX}{sep}{TAG}") == HX


def test_escaped_pipe_notes_tokenised_after_unescape():
    row = f"| 3 | 2026-01-01 | 0 | 0 | 0 | 0 | 0 | a \\| b; converged (0 HIGH); prov={HX} |"
    cells = tr.split_table_row(row)
    notes = cells[-1]
    assert notes.startswith("a | b")
    assert tr.notes_tokens(notes)[:2] == ("a | b", "converged (0 HIGH)")
    assert tr.read_provenance_hash(notes) == HX


def test_stamp_provenance_returns_second_render():
    renders = []

    def build(h):
        renders.append(h)
        return f"head\n| row | prov={h} |\n"

    def hasher(text):
        return compute_content_hash(text.replace(text.split("prov=")[1][:16], "X" * 16))

    out = tr.stamp_provenance(build, hasher)
    assert renders[0] == "0" * 16
    assert renders[1] == hasher(build("0" * 16))
    assert out == build(renders[1])


def test_stamp_provenance_raises_on_divergent_render():
    with pytest.raises(RuntimeError):
        tr.stamp_provenance(lambda h: f"body {h}", compute_content_hash)


# --- T22: the pure convergence verdict (AD5) ----------------------------------

import subprocess  # noqa: E402

CNH = tr.STAMP_CONVERGED_NO_HIGH
SB = tr.STAMP_STRICT_BAR
CC = tr.STAMP_CROSS_CHECK
P = f"prov={HX}"


def _row(p, notes, addressed="0", deferred="0", highs="0", sealed="0"):
    return f"| {p} | 2026-01-01 | {highs} | 0 | {addressed} | {deferred} | {sealed} | {notes} |"


def _tdoc(*rows, header=None, sections=True):
    header = header or "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |"
    ncols = header.count("|") - 1
    sep = "|" + "|".join(["---"] * ncols) + "|"
    body = "\n".join(rows)
    extra = (
        "### Sealed dispositions\n\n_None yet._\n\n"
        "### Latest pass detail\n\n| Severity | Source | Concern | Disposition | Notes |\n"
        "|---|---|---|---|---|\n\n"
    ) if sections else ""
    return (
        "# D\n\n## Objective\n\nx\n\n## Panel Review\n\n### Trajectory\n\n"
        f"{header}\n{sep}\n{body}\n\n{extra}"
        "## Approval\n\n- [ ] Approved to proceed\n- **Content Hash:** `pending`\n"
    )


def _verdict(*rows, **kw):
    return tr.evaluate_convergence(_tdoc(*rows, **kw))


def test_closing_row_skips_skip_rows_and_elided_row():
    rows = tr.parse_trajectory_rows(_tdoc(
        "| … | … | — | — | — | — | — | 3 earlier passes elided |",
        _row(4, f"{CNH}; {P}"),
        _row(5, f"skipped (mechanical: typo); {P}", "—", "—"),
        "| … | … | — | — | — | — | — | 9 earlier passes elided |",
    ))
    assert rows[tr.select_closing_row(rows)].pass_no == 4
    assert tr.select_closing_row([]) is None


def test_converged_closing_row_passes():
    v = _verdict(_row(1, "x; " + P, addressed="2"), _row(2, f"{CNH}; {P}"))
    assert v.failed == () and v.closing_pass == 2 and v.legacy is False
    assert v.freshness_hash == HX
    assert _verdict(_row(1, f"{tr.STAMP_CONVERGED_SEALED}; sealed=2; {P}")).failed == ()


def test_missing_converged_stamp_fails_a():
    assert _verdict(_row(1, P)).failed == ("no-converged-stamp",)


def test_addressed_nonzero_fails_b():
    assert _verdict(_row(1, f"{CNH}; {P}", addressed="3")).failed == ("addressed=3",)


def test_deferred_nonzero_fails_c():
    assert _verdict(_row(1, f"{CNH}; {P}", deferred="1")).failed == ("deferred=1",)


def test_cross_check_after_strict_bar_passes():
    v = _verdict(_row(1, f"{SB}; {CNH}; {P}"), _row(2, f"skipped (mechanical: x); {P}", "—", "—"),
                 _row(3, f"{CC}; {CNH}; {P}"))
    assert v.failed == ()


def test_cross_check_without_strict_bar_fails_d():
    assert _verdict(_row(1, f"{CNH}; {P}"), _row(2, f"{CC}; {CNH}; {P}")).failed == (
        "cross-check-without-strict-bar",
    )
    assert _verdict(_row(1, f"{CC}; {CNH}; {P}")).failed == ("cross-check-without-strict-bar",)


def test_normal_after_strict_bar_fails_d():
    assert _verdict(_row(1, f"{SB}; {CNH}; {P}"), _row(2, f"{CNH}; {P}")).failed == (
        "normal-after-strict-bar",
    )


def test_strict_bar_closing_fails_regardless_of_convergence():
    assert _verdict(_row(1, f"{SB}; {CNH}; {P}")).failed == ("strict-bar-closing",)
    assert _verdict(_row(1, f"{SB}; {P}")).failed == ("no-converged-stamp", "strict-bar-closing")


def test_halt_disposition_stamp_fails_e():
    v = _verdict(_row(1, f"{CNH}; {tr.STAMP_HALT_DISPOSITION}; halt vote (critic: x); {P}"))
    assert v.failed == ("halt-and-rescope",)


def test_upstream_halt_vote_without_halt_stamp_passes_e():
    v = _verdict(_row(1, f"{tr.STAMP_CONVERGED_SEALED}; sealed=1; tags=d0u1c0; halt vote (architect: gap); {P}"))
    assert v.failed == ()


def test_no_rows_gives_no_converged_pass_code():
    v = _verdict()
    assert v.failed == ("no-converged-pass",) and v.closing_pass is None
    v2 = _verdict(_row(1, f"skipped (mechanical: x); {P}", "—", "—"))
    assert v2.failed == ("no-converged-pass",)


def test_sealed_value_ignored():
    for n in ("0", "1", "99", "—"):
        assert _verdict(_row(1, f"{tr.STAMP_CONVERGED_SEALED}; sealed={n}; {P}", sealed=n)).failed == ()


def test_marker_in_concern_title_not_read():
    # A concern title quoted in halt text, or a substring inside another token,
    # never reads as a stamp.
    assert _verdict(_row(1, f"title mentions converged (0 HIGH) inline; {P}")).failed == ("no-converged-stamp",)
    assert _verdict(_row(1, f"halt vote (c: converged (0 HIGH)); {P}")).failed == ("no-converged-stamp",)
    assert _verdict(_row(1, f"{CNH}; a strict-bar pass mention; {P}")).failed == ()


def test_extra_tokens_do_not_break_reading():
    assert _verdict(_row(1, f"future=1;  {CNH} ; tags=d0u0c0; other thing; {P}")).failed == ()


def test_missing_addressed_column_code():
    v = _verdict("| 1 | x | 0 | 0 | 0 | 0 | " + f"{CNH}; {P} |",
                 header="| Pass | Date | HIGHs | Regressions | Deferred | Sealed | Notes |")
    assert v.failed == ("missing-column:Addressed",) and v.legacy is False


def test_malformed_row_code_reports_file_line_no_row_text():
    doc = _tdoc(_row(1, f"{CNH}; {P}"), f"| 2 | 2026 | 0 | 0 | 0 | {CNH}; {P} |", _row(3, f"{CNH}; {P}"))
    line_no = doc.split("\n").index(f"| 2 | 2026 | 0 | 0 | 0 | {CNH}; {P} |") + 1
    v = tr.evaluate_convergence(doc)
    assert v.failed == (f"malformed-row:{line_no}",)
    assert all("2026" not in c for c in v.failed)
    # non-integer count cell on a non-skip integer row
    v2 = _verdict(_row(1, f"{CNH}; {P}", addressed="x"))
    assert v2.failed[0].startswith("malformed-row:")
    # inside the region trim would elide (17 rows, row 1 malformed)
    rows = [f"| 1 | d | 0 | 0 | {CNH}; {P} |"] + [_row(i, f"{CNH}; {P}") for i in range(2, 18)]
    v3 = _verdict(*rows)
    assert v3.failed and v3.failed[0].startswith("malformed-row:")


def test_tokenless_table_structural_fault_is_legacy_not_fail():
    v = _verdict(f"| 1 | d | 0 | {CNH} |", _row(2, CNH))
    assert v.failed[0].startswith("malformed-row:") and v.legacy is True
    v2 = _verdict("| 1 | x | 0 | 0 | 0 | 0 | " + f"{CNH} |",
                  header="| Pass | Date | HIGHs | Regressions | Deferred | Sealed | Notes |")
    assert v2.failed == ("missing-column:Addressed",) and v2.legacy is True


def test_no_data_rows_is_not_legacy_and_fails_no_converged_pass():
    v = _verdict()
    assert v.legacy is False and v.failed == ("no-converged-pass",)


def test_freshness_hash_from_newest_tokened_skip_row():
    other = "f" * 16
    v = _verdict(_row(1, f"{CNH}; {P}"), _row(2, f"skipped (mechanical: x); prov={other}", "—", "—"))
    assert v.closing_pass == 1 and v.freshness_hash == other


def test_legacy_closing_row_ignores_later_tokened_skip():
    v = _verdict(_row(1, CNH), _row(2, f"skipped (mechanical: x); {P}", "—", "—"))
    assert v.legacy is True and v.freshness_hash is None and v.failed == ()


@pytest.mark.parametrize("sep", ["; ", " ", ";"])
def test_upstream_tag_after_prov_three_ways_closing_row_selected(sep):
    v = _verdict(_row(1, f"{CNH}; {P}{sep}{TAG}"))
    assert v.closing_pass == 1 and v.legacy is False and v.freshness_hash == HX and v.failed == ()


def test_legacy_format_flag_when_subsection_missing():
    assert _verdict(_row(1, f"{CNH}; {P}"), sections=False).legacy_format is True
    assert _verdict(_row(1, f"{CNH}; {P}")).legacy_format is False


def test_empty_notes_cell_and_duplicate_pass_values():
    v = _verdict(_row(1, f"{CNH}; {P}"), "| 2 | d | 0 | 0 | 0 | 0 | 0 |  |")
    assert v.failed == ("no-converged-stamp",) and v.closing_pass == 2
    v2 = _verdict(_row(3, P), _row(3, f"{CNH}; {P}"))
    assert v2.failed == () and v2.closing_pass == 3


def test_defended_dispositions_pin_and_column_mapping():
    import archive_pass

    assert archive_pass.DEFENDED_DISPOSITIONS == ("Sealed", "Accepted as risk")
    skills = _SCRIPTS.parent / "skills"
    for tier in ("spec-driven-dev", "project-blueprint"):
        text = (skills / tier / "references" / "panel-review.md").read_text(encoding="utf-8")
        step8 = text[text.index("8. **Exit when the pass leaves no unresolved HIGH concern**"):]
        step8 = step8[: step8.index("\n9. ")] if "\n9. " in step8 else step8
        assert "**Non-blocking:** `Sealed`, `Accepted as risk`." in step8
    # (a)-(c) read Notes, Addressed and Deferred respectively
    row = tr.parse_trajectory_rows(_tdoc(_row(1, f"{CNH}; {P}", addressed="4", deferred="5")))[0]
    assert (row.cells["Addressed"], row.cells["Deferred"]) == ("4", "5")


_LATEST_SEP = "|---|---|---|---|---|\n"


@pytest.mark.parametrize("disp,converged", [
    ("Sealed | Defense: fine", True),
    ("Accepted as risk | Defense: ok", True),
    ("Addressed | fixed", False),
    ("Deferred → design.md | Routed because: design work", False),
    ("Halt and re-scope | stop", False),
])
def test_one_real_archive_per_disposition(tmp_path, disp, converged):
    doc = _tdoc().replace(
        "### Latest pass detail", "### Deferred dispositions\n\n<!-- x -->\n\n### Latest pass detail"
    )
    i = doc.rindex(_LATEST_SEP) + len(_LATEST_SEP)
    doc = doc[:i] + f"| [HIGH] | critic | thing | {disp} |\n" + doc[i:]
    p = tmp_path / "spec.md"
    p.write_text(doc, encoding="utf-8")
    proc = subprocess.run([sys.executable, str(_SCRIPTS / "archive_pass.py"), str(p), "--phase", "1"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    v = tr.evaluate_convergence(p.read_text(encoding="utf-8"))
    assert (v.failed == ()) is converged, v.failed


# --- T23: the convergence gate wrapper (AD6) ---------------------------------

KINDS = ["spec.md", "design.md", "tasks.md", "SCOPE.md", "ARCHITECTURE.md", "PLAN.md"]


def _fresh(*rows, edit_after=False, **kw):
    """_tdoc whose `PROV` placeholders all become the document's real hash
    (header/separator widths don't depend on row text, so this is exact)."""
    doc = _tdoc(*rows, **kw)
    h = compute_content_hash(doc)
    doc = doc.replace("PROV", f"prov={h}")
    if edit_after:
        doc = doc.replace("## Objective\n\nx\n", "## Objective\n\nedited after the pass\n")
    return doc


def _gate(doc, name="design.md", path=None):
    r = bc.ValidationResult()
    v = bc.check_convergence_gate(doc, name, path or Path(f"specs/feat-x/{name}"), r)
    rows = [c for c in r.checks if c[0] == f"{name} convergence gate"]
    return v, rows


def _sev(rows):
    sevs = {c[1] for c in rows}
    if bc.Severity.FAIL in sevs:
        return "FAIL"
    if bc.Severity.WARN in sevs:
        return "WARN"
    return "PASS"


_SCENARIOS = {
    "converged": (lambda: _fresh(_row(1, f"{CNH}; PROV")), "PASS"),
    "unconverged": (lambda: _fresh(_row(1, "PROV", highs="2")), "FAIL"),
    "addressed": (lambda: _fresh(_row(1, f"{CNH}; PROV", addressed="1")), "FAIL"),
    "deferred": (lambda: _fresh(_row(1, f"{CNH}; PROV", deferred="1")), "FAIL"),
    "strict-bar-closing": (lambda: _fresh(_row(1, f"{SB}; {CNH}; PROV")), "FAIL"),
    "cross-after-strict": (lambda: _fresh(_row(1, f"{SB}; {CNH}; PROV"), _row(2, f"{CC}; {CNH}; PROV")), "PASS"),
    "cross-without-strict": (lambda: _fresh(_row(1, f"{CC}; {CNH}; PROV")), "FAIL"),
    "normal-after-strict": (lambda: _fresh(_row(1, f"{SB}; {CNH}; PROV"), _row(2, f"{CNH}; PROV")), "FAIL"),
    "halt": (lambda: _fresh(_row(1, f"{CNH}; {tr.STAMP_HALT_DISPOSITION}; PROV")), "FAIL"),
    "legacy-warn": (lambda: _tdoc(_row(1, "—", highs="1")), "WARN"),
    "freshness-fail": (lambda: _fresh(_row(1, f"{CNH}; PROV"), edit_after=True), "FAIL"),
    "freshness-via-skip": (lambda: _fresh(_row(1, f"{CNH}; prov={'e' * 16}"),
                                          _row(2, "skipped (mechanical: typo); PROV", "—", "—")), "PASS"),
}


@pytest.mark.parametrize("scenario", list(_SCENARIOS))
@pytest.mark.parametrize("name", KINDS)
def test_gate_core_matrix_six_kinds_twelve_scenarios(name, scenario):
    build, expected = _SCENARIOS[scenario]
    _v, rows = _gate(build(), name)
    assert rows, "the gate always reports a row"
    assert _sev(rows) == expected, rows


def test_no_evidence_route_panel_pass_only():
    doc = "# D\n\n## Objective\n\nx\n\n## Approval\n\n- [ ] Approved to proceed\n- **Content Hash:** `pending`\n"
    _v, rows = _gate(doc)
    d = rows[0][2]
    assert _sev(rows) == "FAIL" and "no converged panel pass recorded" in d
    assert "archive_pass.py" in d and "--override-convergence" not in d


def test_latest_detail_only_counts_as_no_evidence():
    doc = _tdoc()
    i = doc.rindex(_LATEST_SEP) + len(_LATEST_SEP)
    doc = doc[:i] + "| [HIGH] | c | x | Addressed | y |\n" + doc[i:]
    _v, rows = _gate(doc)
    assert "no converged panel pass recorded" in rows[0][2]
    assert "--override-convergence" not in rows[0][2]


def test_skip_only_evidence_offers_override():
    _v, rows = _gate(_tdoc(_row(1, f"skipped (mechanical: x); {P}", "—", "—")))
    d = rows[0][2]
    assert "no converged panel pass recorded" in d
    assert '--override-convergence "<reason>"' in d and bc.USER_DECISION_NOTE in d


def test_seal_only_evidence_offers_override():
    doc = _tdoc().replace("_None yet._", "- `[SEAL-01]` **x** (pass 1, user-directed) — Defense: d.")
    _v, rows = _gate(doc)
    assert "--override-convergence" in rows[0][2] and bc.USER_DECISION_NOTE in rows[0][2]


def test_legacy_single_table_names_migration_route():
    doc = ("# D\n\n## Panel Review\n\n| Pass | Date | HIGHs | Notes |\n|---|---|---|---|\n"
           "| 1 | 2026-01-01 | 0 | done |\n\n## Approval\n\n- [ ] Approved to proceed\n- **Content Hash:** `pending`\n")
    _v, rows = _gate(doc)
    d = rows[0][2]
    assert "no converged panel pass recorded" in d
    i = d.index("three-sub-section")
    assert i < d.index("archive_pass.py")


def test_freshness_fail_routes_in_order():
    _v, rows = _gate(_fresh(_row(1, f"{CNH}; PROV"), edit_after=True), "design.md",
                     Path("specs/feat-x/design.md"))
    d = rows[0][2]
    assert "edited-after-pass" in d
    a = d.index('archive_pass.py specs/feat-x/design.md --phase 2 --skip "<what changed>"')
    b = d.index("another panel pass")
    c = d.index("--override-convergence")
    assert a < b < c and bc.USER_DECISION_NOTE in d[c:]


@pytest.mark.parametrize("name,terminal", [("design.md", False), ("tasks.md", True), ("PLAN.md", True), ("SCOPE.md", False)])
def test_terminal_flag_printed_iff_is_terminal_artifact(name, terminal):
    _v, rows = _gate(_fresh(_row(1, f"{CNH}; PROV"), edit_after=True), name)
    assert ("--terminal" in rows[0][2]) is terminal
    doc = _fresh(_row(1, f"{CNH}; PROV"), edit_after=True).replace("# D\n", "# D\n<!-- terminal-phase: scope -->\n")
    _v, rows = _gate(doc, "SCOPE.md")
    assert "--terminal" in rows[0][2]


def test_legacy_closing_row_warns_naming_audit_command():
    _v, rows = _gate(_tdoc(_row(1, "—", highs="1")))
    assert _sev(rows) == "WARN" and "--audit-convergence" in rows[0][2]
    assert bc.GLOSS_LEGACY in rows[0][2]
    _v, rows = _gate(_tdoc(_row(1, CNH)))
    assert _sev(rows) == "PASS"


def test_legacy_gloss_literal():
    assert bc.GLOSS_LEGACY == (
        "legacy means the closing panel row was archived before provenance tokens "
        "existed, so whether the document changed after that pass cannot be checked"
    )


def test_normal_after_strict_bar_message_names_cross_check():
    _v, rows = _gate(_fresh(_row(1, f"{SB}; {CNH}; PROV"), _row(2, f"{CNH}; PROV")))
    assert bc.MSG_MISSING_CROSS_CHECK in rows[0][2] and "--cross-check" in bc.MSG_MISSING_CROSS_CHECK


def test_strict_bar_closing_message_cites_exit_cross_check():
    _v, rows = _gate(_fresh(_row(1, f"{SB}; {CNH}; PROV")))
    assert bc.MSG_STRICT_BAR_EXIT in rows[0][2]
    assert "panel-review-convergence.md` § Exit cross-check" in bc.MSG_STRICT_BAR_EXIT


def test_lightweight_single_pass_unconverged_offers_override():
    _v, rows = _gate(_fresh(_row(1, "PROV", highs="1", addressed="2")))
    d = rows[0][2]
    assert _sev(rows) == "FAIL" and '--override-convergence "<reason>"' in d and bc.USER_DECISION_NOTE in d


def _archived(tmp_path, name, *flags, terminal_marker=False):
    doc = _tdoc()
    if name not in ("tasks.md", "PLAN.md"):
        doc = doc.replace("### Latest pass detail", "### Deferred dispositions\n\n<!-- x -->\n\n### Latest pass detail")
    if terminal_marker:
        doc = doc.replace("# D\n", "# D\n<!-- terminal-phase: scope -->\n")
    i = doc.rindex(_LATEST_SEP) + len(_LATEST_SEP)
    doc = doc[:i] + "| [MED] | critic | thing | Sealed | Defense: ok |\n" + doc[i:]
    p = tmp_path / name
    p.write_text(doc, encoding="utf-8")
    proc = subprocess.run([sys.executable, str(_SCRIPTS / "archive_pass.py"), str(p), "--phase", "3", *flags],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return p


@pytest.mark.parametrize("name,marker", [("PLAN.md", False), ("tasks.md", False), ("SCOPE.md", True)])
def test_terminal_archives_gated_like_normal(tmp_path, name, marker):
    p = _archived(tmp_path, name, "--terminal", terminal_marker=marker)
    v, rows = _gate(p.read_text(encoding="utf-8"), name, p)
    assert _sev(rows) == "PASS" and v.failed == ()


def test_widen_then_first_approval_freshness_passes(tmp_path):
    p = _archived(tmp_path, "design.md", "--strict-bar")
    _v, rows = _gate(p.read_text(encoding="utf-8"), "design.md", p)
    assert "edited-after-pass" not in rows[0][2]  # fails strict-bar-closing only
    (tmp_path / "n").mkdir()
    q = _archived(tmp_path / "n", "design.md")
    _v, rows = _gate(q.read_text(encoding="utf-8"), "design.md", q)
    assert _sev(rows) == "PASS"


@pytest.mark.parametrize("sep", ["; ", " ", ";"])
def test_upstream_tag_after_prov_three_ways_freshness_outcome(sep):
    fresh = _fresh(_row(1, f"{CNH}; PROV" + sep + TAG))
    assert _sev(_gate(fresh)[1]) == "PASS"
    stale = fresh.replace("## Objective\n\nx\n", "## Objective\n\nedited\n")
    assert "edited-after-pass" in _gate(stale)[1][0][2]


def test_blueprint_common_reexports_trajectory_gate_names():
    for n in ("PROVENANCE_PREFIX", "PROVENANCE_HEX_WIDTH", "PROVENANCE_TOKEN_RE", "UPSTREAM_TAG_STRIP_RE",
              "notes_tokens", "read_provenance_hash", "stamp_provenance", "provenance_token",
              "evaluate_convergence", "ConvergenceVerdict", "TrajectoryRow", "parse_trajectory_rows",
              "select_closing_row", "strip_upstream_tags"):
        assert getattr(bc, n) is getattr(tr, n), n


# --- T24: the read-only convergence audit (AD9) ------------------------------


def _approved_doc(doc: str) -> str:
    h = compute_content_hash(doc)
    return doc.replace("- [ ] Approved to proceed", "- [x] Approved to proceed").replace("`pending`", f"`{h}`")


def _with_override(doc: str, n=1, reason="accepted lighter bar") -> str:
    for _ in range(n):
        doc = bc.append_override_record(doc, bc.OverrideRecord(1, reason))
    return doc


def _audit(tmp_path, docs: "dict[str, str]"):
    items = []
    for name, text in docs.items():
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        items.append((name, p))
    return bc.audit_convergence(items)


def _state(entries, path):
    return next(e for e in entries if e.path == path)


def test_audit_reports_each_state(tmp_path):
    good = _approved_doc(_fresh(_row(1, f"{CNH}; PROV")))
    bad = _approved_doc(_fresh(_row(1, "PROV", highs="2")))
    none = _approved_doc(_tdoc())
    draft = _fresh(_row(1, "PROV", highs="2"))  # unapproved: not audited
    es = _audit(tmp_path, {"a.md": good, "b.md": bad, "c.md": none, "d.md": draft})
    assert [e.path for e in es] == ["a.md", "b.md", "c.md"]
    assert _state(es, "a.md").state == "converged"
    assert _state(es, "b.md").state == "unconverged (no-converged-stamp)"
    assert _state(es, "c.md").state == "no converged panel pass recorded"


def test_audit_converged_previously_overridden(tmp_path):
    es = _audit(tmp_path, {"a.md": _with_override(_approved_doc(_fresh(_row(1, f"{CNH}; PROV"))))})
    assert es[0].state == "converged (previously overridden)"


def test_audit_overridden_with_stored_reason(tmp_path):
    es = _audit(tmp_path, {"a.md": _with_override(_approved_doc(_fresh(_row(1, "PROV", highs="1"))))})
    assert es[0].state == "overridden" and es[0].reason == "accepted lighter bar"
    text, _code = bc.format_audit_report(es)
    assert "a.md: overridden — reason: accepted lighter bar" in text


def test_audit_duplicate_override_never_overridden(tmp_path):
    es = _audit(tmp_path, {"a.md": _with_override(_approved_doc(_fresh(_row(1, "PROV", highs="1"))), n=2)})
    assert es[0].state == "unconverged (no-converged-stamp)"
    text, code = bc.format_audit_report(es)
    assert "(duplicate override records)" in text and code != 0


def test_audit_legacy_label_and_no_closing_row_case(tmp_path):
    doc = _approved_doc(_tdoc())
    assert tr.evaluate_convergence(doc).legacy is False
    es = _audit(tmp_path, {"a.md": doc, "b.md": _approved_doc(_tdoc(_row(1, CNH)))})
    assert es[0].legacy is True and es[0].state == "no converged panel pass recorded"
    assert es[1].legacy is True and es[1].state == "converged"
    text, code = bc.format_audit_report(es)
    assert "a.md: no converged panel pass recorded — legacy" in text and code == 0


def test_audit_skips_freshness_for_ticked_tasks(tmp_path):
    doc = _approved_doc(_fresh(_row(1, f"{CNH}; PROV"))).replace("## Objective\n\nx\n", "## Objective\n\n- [x] T1 ticked\n")
    es = _audit(tmp_path, {"tasks.md": doc})
    assert es[0].state == "converged"


def test_audit_summary_line_format(tmp_path):
    es = _audit(tmp_path, {
        "a.md": _approved_doc(_fresh(_row(1, f"{CNH}; PROV"))),
        "b.md": _approved_doc(_fresh(_row(1, "PROV", highs="1"))),
        "c.md": _approved_doc(_tdoc(_row(1, "—", highs="1"))),
    })
    es.append(bc.AuditEntry("specs/x", "unauditable (ambiguous NN_ prefix)", False, None))
    text, _ = bc.format_audit_report(es)
    assert text.splitlines()[-1] == (
        "convergence audit: converged 1, converged (previously overridden) 0, overridden 0, "
        "unconverged 1, no converged panel pass recorded 0, unauditable 1; legacy 1"
    )


def test_audit_exit_code_counts_non_legacy_only(tmp_path):
    es = _audit(tmp_path, {"a.md": _approved_doc(_fresh(_row(1, f"{CNH}; PROV"))),
                           "c.md": _approved_doc(_tdoc(_row(1, "—", highs="1")))})
    assert bc.format_audit_report(es)[1] == 0
    es = _audit(tmp_path, {"b.md": _approved_doc(_fresh(_row(1, "PROV", highs="1")))})
    assert bc.format_audit_report(es)[1] == 1


def test_audit_f4_shape_unconverged_legacy_exit_0(tmp_path):
    doc = _approved_doc(_tdoc(_row(1, "—", highs="6", addressed="6"), _row(2, "—", highs="1", addressed="1"),
                              _row(3, "—", highs="1", addressed="1"), _row(4, "—", highs="3", addressed="3")))
    es = _audit(tmp_path, {"02_design.md": doc})
    assert es[0].state.startswith("unconverged (") and es[0].legacy is True
    assert bc.format_audit_report(es)[1] == 0


def test_audit_unauditable_ambiguous_prefix_nonzero(tmp_path):
    d = tmp_path / "specs" / "F1-x"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# a\n", encoding="utf-8")
    (d / "01_spec.md").write_text("# b\n", encoding="utf-8")
    es = bc.audit_directory(d, ("spec.md", "design.md", "tasks.md"), label=str(d))
    assert [e.state for e in es] == ["unauditable (ambiguous NN_ prefix)"]
    assert bc.format_audit_report(es)[1] != 0


@pytest.mark.parametrize("sep", ["; ", " ", ";"])
def test_upstream_tag_after_prov_three_ways_audit_label_not_legacy(tmp_path, sep):
    es = _audit(tmp_path, {"a.md": _approved_doc(_fresh(_row(1, f"{CNH}; PROV{sep}{TAG}")))})
    assert es[0].legacy is False and es[0].state == "converged"


# --- T25: plan_approval and write_chain (AD7) ---------------------------------

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
import _fixtures as fx  # noqa: E402


def _put(d: Path, name: str, text: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p


def _stamped_up(d: Path, name: str, h: str = "00112233aabbccdd") -> None:
    _put(d, name, f"# up\n\n## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `{h}`\n")


def _plan(p: Path, bare: str, *, task_tick=False, reason=None):
    return bc.plan_approval(p, directory=p.parent, bare_name=bare, task_tick=task_tick,
                            override_reason=reason)


def _fails(plan):
    return [c for c in plan.result.checks if c[1] == bc.Severity.FAIL]


def test_plan_approval_refuses_unbindable_upstream(tmp_path):
    p = _put(tmp_path, "design.md", _fresh(_row(1, f"{CNH}; PROV")))
    _put(tmp_path, "spec.md", "# s\n\n## Approval\n\n- [ ] Approved to proceed\n- **Content Hash:** `pending`\n")
    plan = _plan(p, "design.md")
    f = _fails(plan)
    assert len(f) == 1 and "spec.md" in f[0][2] and "Approve the named upstream first" in f[0][2]
    assert plan.result.passed is False


def test_plan_approval_task_tick_unstamped_refused(tmp_path):
    _stamped_up(tmp_path, "spec.md")
    _stamped_up(tmp_path, "design.md")
    p = _put(tmp_path, "tasks.md", _fresh(_row(1, f"{CNH}; PROV")))
    plan = _plan(p, "tasks.md", task_tick=True)
    f = _fails(plan)
    assert len(f) == 1 and "plain `--approve tasks`" in f[0][2] and plan.writes is None


def test_plan_approval_task_tick_stamped_runs_no_gate(tmp_path):
    p = _put(tmp_path, "tasks.md", _approved_doc(_fresh(_row(1, "PROV", highs="3"))))
    plan = _plan(p, "tasks.md", task_tick=True)
    assert plan.result.passed and plan.writes is None
    assert not any("convergence gate" in c[0] for c in plan.result.checks)


def test_plan_approval_reapproval_skips_gate(tmp_path):
    _stamped_up(tmp_path, "spec.md")
    p = _put(tmp_path, "design.md", _approved_doc(_fresh(_row(1, "PROV", highs="3"))))
    plan = _plan(p, "design.md")
    assert plan.result.passed and not any("convergence gate" in c[0] for c in plan.result.checks)
    assert plan.writes.bindings == (bc.UpstreamBinding("spec.md", "00112233aabbccdd"),)


def test_override_record_pass_n_and_pass_none(tmp_path):
    p = _put(tmp_path / "a", "spec.md", _fresh(_row(4, "PROV", highs="2")))
    plan = _plan(p, "spec.md", reason="  ship it **now**  ")
    assert plan.result.passed
    assert plan.writes.override == bc.OverrideRecord(4, "ship it now")
    q = _put(tmp_path / "b", "spec.md", _tdoc(_row(1, f"skipped (mechanical: x); {P}", "—", "—")))
    plan = _plan(q, "spec.md", reason="no pass")
    assert plan.writes.override == bc.OverrideRecord(None, "no pass")


def test_override_not_needed_note_three_cases(tmp_path):
    cases = {
        "passing": _fresh(_row(1, f"{CNH}; PROV")),
        "legacy": _tdoc(_row(1, "—", highs="1")),
        "reapproval": _approved_doc(_fresh(_row(1, "PROV", highs="1"))),
    }
    for k, text in cases.items():
        p = _put(tmp_path / k, "spec.md", text)
        plan = _plan(p, "spec.md", reason="r")
        assert plan.result.passed, k
        assert plan.writes.override is None, k
        assert any("override not needed" in ln for ln in plan.post_lines), k


def test_override_audit_line_echoes_stored_reason(tmp_path):
    p = _put(tmp_path, "spec.md", _fresh(_row(2, "PROV", highs="1", addressed="1")))
    plan = _plan(p, "spec.md", reason="`user` accepted\nthe risk")
    line = [ln for ln in plan.post_lines if ln.startswith("convergence override:")][0]
    assert "spec.md" in line and "pass 2" in line
    assert "no-converged-stamp" in line and "addressed=1" in line
    assert line.endswith("reason: user accepted the risk")


def test_plan_approval_is_pure_read(tmp_path):
    _stamped_up(tmp_path, "spec.md")
    p = _put(tmp_path, "design.md", _fresh(_row(1, "PROV", highs="1")))
    before = {f: f.read_bytes() for f in tmp_path.rglob("*") if f.is_file()}
    _plan(p, "design.md", reason="x")
    assert before == {f: f.read_bytes() for f in tmp_path.rglob("*") if f.is_file()}


def test_judged_hash_matches_verify_judged_transform(tmp_path):
    p = tmp_path / "spec.md"
    p.write_bytes(b"\xef\xbb\xbf" + _fresh(_row(1, f"{CNH}; PROV")).encode("utf-8"))
    plan = _plan(p, "spec.md")
    core_view = bc.trim_trajectory_table(p.read_text(encoding="utf-8-sig"))
    assert bc.verify_judged_transform(core_view, p, writes=plan.writes) == core_view


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_write_chain_bind_true_uses_plan_approval_both_tiers(tmp_path, tier, monkeypatch):
    calls = []
    real = bc.plan_approval
    monkeypatch.setattr(bc, "plan_approval", lambda *a, **k: calls.append(k["bare_name"]) or real(*a, **k))
    phases = ["spec", "design", "tasks"] if tier == "sdd" else ["scope", "architecture", "plan"]
    chain = fx.write_chain(tmp_path, tier, approve=phases, bind=True)
    assert len(calls) == 3
    names = list(chain)
    for name, p in chain.items():
        t = p.read_text(encoding="utf-8")
        r = bc.ValidationResult()
        assert bc.check_approval(t, name, r), r.summary()
        bc.check_upstream_bindings(p.parent, name, t, r)
        assert r.passed and not r.has_warnings, r.summary()
    assert bc.read_bindings(chain[names[2]].read_text(encoding="utf-8")).keys() == {names[0], names[1]}


def test_write_chain_bind_false_writes_no_binding_lines(tmp_path):
    chain = fx.write_chain(tmp_path, "sdd", approve=["spec", "design", "tasks"], bind=False, prefixed=True)
    assert [p.name for p in chain.values()] == ["01_spec.md", "02_design.md", "03_tasks.md"]
    for p in chain.values():
        t = p.read_text(encoding="utf-8")
        assert "Upstream binding" not in t and bc._is_valid_16_hex(bc.read_stored_hash(t))


# --- T29: the SDD approve path with the gate live ----------------------------

import argparse  # noqa: E402
import json  # noqa: E402

_VS_CLI = _SCRIPTS.parent / "skills" / "spec-driven-dev" / "scripts" / "validate_spec.py"


def _vs_run(root, d, *args):
    return subprocess.run([sys.executable, str(_VS_CLI), str(d), *args, "--project-root", str(root)],
                          capture_output=True, text=True)


def _sdd(root, approve=("spec",)):
    return fx.write_chain(root, "sdd", approve=list(approve), bind=True)


_NO_EVIDENCE = (
    "# Design\n\n**PLAN feature identifier:** `n/a`\n\n## Objective\n\nx\n\n"
    "## Approval\n\n- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
)


def _unconverged(title="Design"):
    return _fresh(_row(1, "PROV", highs="2")).replace("# D\n", f"# {title}\n\n**PLAN feature identifier:** `n/a`\n")


def test_sdd_no_evidence_without_force_prints_panel_and_gate_fail(tmp_path):
    c = _sdd(tmp_path)
    c["design.md"].write_text(_NO_EVIDENCE, encoding="utf-8")
    r = _vs_run(tmp_path, c["design.md"].parent, "--approve", "design")
    assert r.returncode == 1
    assert "Panel Review" in r.stdout and "no converged panel pass recorded" in r.stdout
    assert "--override-convergence" not in r.stdout.split("no converged panel pass recorded")[1].split("\n")[0]


def test_sdd_no_evidence_with_force_still_refused(tmp_path):
    c = _sdd(tmp_path)
    c["design.md"].write_text(_NO_EVIDENCE, encoding="utf-8")
    before = c["design.md"].read_bytes()
    r = _vs_run(tmp_path, c["design.md"].parent, "--approve", "design", "--force")
    assert r.returncode == 1 and "no converged panel pass recorded" in r.stdout
    assert "has Panel Review" not in r.stdout
    assert c["design.md"].read_bytes() == before


def test_sdd_force_does_not_bypass_gate(tmp_path):
    c = _sdd(tmp_path)
    c["design.md"].write_text(_unconverged(), encoding="utf-8")
    r = _vs_run(tmp_path, c["design.md"].parent, "--approve", "design", "--force")
    assert r.returncode == 1 and "design.md convergence gate" in r.stdout


def test_sdd_force_plus_override_no_evidence_stamps_pass_none(tmp_path):
    c = _sdd(tmp_path)
    c["design.md"].write_text(_NO_EVIDENCE, encoding="utf-8")
    r = _vs_run(tmp_path, c["design.md"].parent, "--approve", "design", "--force",
                "--override-convergence", "user accepts no panel")
    assert r.returncode == 0, r.stdout
    t = c["design.md"].read_text(encoding="utf-8")
    assert "- **Convergence override:** pass none — user accepts no panel" in t
    assert "convergence override: design.md approved at pass none" in r.stdout


@pytest.mark.parametrize("reason", ["", "   "])
def test_sdd_override_blank_whitespace_or_missing_reason_exit_2(tmp_path, reason):
    c = _sdd(tmp_path)
    r = _vs_run(tmp_path, c["design.md"].parent, "--approve", "design", "--override-convergence", reason)
    assert r.returncode == 2 and '--override-convergence "<reason>"' in r.stdout
    r2 = _vs_run(tmp_path, c["design.md"].parent, "--approve", "design", "--override-convergence")
    assert r2.returncode == 2


@pytest.mark.parametrize("reason", ["***", "###", "\x1b[0m"])
def test_sdd_override_reason_sanitising_empty_exit_2_before_read(tmp_path, reason):
    c = _sdd(tmp_path)
    c["design.md"].chmod(0o000)
    try:
        r = _vs_run(tmp_path, c["design.md"].parent, "--approve", "design", "--override-convergence", reason)
    finally:
        c["design.md"].chmod(0o644)
    assert r.returncode == 2 and '--override-convergence "<reason>"' in r.stdout


def test_sdd_override_without_approve_exit_2(tmp_path):
    c = _sdd(tmp_path)
    r = _vs_run(tmp_path, c["design.md"].parent, "--override-convergence", "x")
    assert r.returncode == 2 and "only valid with --approve" in r.stdout


def test_sdd_override_preserved_across_reapproval(tmp_path):
    c = _sdd(tmp_path)
    c["design.md"].write_text(_unconverged(), encoding="utf-8")
    d = c["design.md"].parent
    assert _vs_run(tmp_path, d, "--approve", "design", "--force", "--override-convergence", "keep me").returncode == 0
    line = next(ln for ln in c["design.md"].read_text(encoding="utf-8").splitlines() if "Convergence override" in ln)
    t = c["design.md"].read_text(encoding="utf-8")
    c["design.md"].write_text(t.replace("## Objective\n\nx\n", "## Objective\n\nedited\n"), encoding="utf-8")
    r = _vs_run(tmp_path, d, "--approve", "design", "--force")
    assert r.returncode == 0, r.stdout
    t2 = c["design.md"].read_text(encoding="utf-8")
    assert t2.count("Convergence override") == 1 and line in t2.splitlines()


def test_sdd_reapproval_never_meets_gate(tmp_path):
    c = _sdd(tmp_path)
    c["design.md"].write_text(_unconverged(), encoding="utf-8")
    d = c["design.md"].parent
    assert _vs_run(tmp_path, d, "--approve", "design", "--force", "--override-convergence", "x").returncode == 0
    r = _vs_run(tmp_path, d, "--approve", "design", "--force")
    assert r.returncode == 0 and "convergence gate" not in r.stdout


def test_sdd_approve_spec_first_approval_runs_gate(tmp_path):
    (tmp_path / ".git").mkdir()
    d = tmp_path / "specs" / "feat-x"
    d.mkdir(parents=True)
    (d / "spec.md").write_text(_unconverged("Spec"), encoding="utf-8")
    r = _vs_run(tmp_path, d, "--approve", "spec", "--force")
    assert r.returncode == 1 and "spec.md convergence gate" in r.stdout
    (d / "spec.md").write_text(_fresh(_row(1, f"{CNH}; PROV")).replace("# D\n", "# S\n\n**PLAN feature identifier:** `n/a`\n"), encoding="utf-8")
    # the replace above changed hashed text after stamping the token; restamp it
    (d / "spec.md").write_text(fx.restamp_provenance((d / "spec.md").read_text(encoding="utf-8")), encoding="utf-8")
    assert _vs_run(tmp_path, d, "--approve", "spec", "--force").returncode == 0


def test_sdd_elided_trajectory_closing_row_selected(tmp_path):
    (tmp_path / ".git").mkdir()
    d = tmp_path / "specs" / "feat-x"
    d.mkdir(parents=True)
    text = _NO_EVIDENCE.replace("# Design", "# Spec")
    for _ in range(17):
        text = fx.add_converged_closing_row(text)
    (d / "spec.md").write_text(text, encoding="utf-8")
    r = _vs_run(tmp_path, d, "--approve", "spec", "--force")
    assert r.returncode == 0, r.stdout
    assert "earlier passes elided" in (d / "spec.md").read_text(encoding="utf-8")


def test_sdd_widen_then_first_approval_passes_freshness(tmp_path):
    (tmp_path / ".git").mkdir()
    d = tmp_path / "specs" / "feat-x"
    d.mkdir(parents=True)
    doc = _tdoc().replace("# D\n", "# S\n\n**PLAN feature identifier:** `n/a`\n").replace(
        "### Latest pass detail", "### Deferred dispositions\n\n<!-- x -->\n\n### Latest pass detail")
    p = d / "spec.md"
    p.write_text(doc, encoding="utf-8")
    for flag in ("--strict-bar", "--cross-check"):
        subprocess.run([sys.executable, str(_SCRIPTS / "archive_pass.py"), str(p), "--phase", "1", flag],
                       check=True, capture_output=True)
    r = _vs_run(tmp_path, d, "--approve", "spec", "--force")
    assert r.returncode == 0, r.stdout


def test_sdd_bom_artifact_no_race(tmp_path):
    (tmp_path / ".git").mkdir()
    d = tmp_path / "specs" / "feat-x"
    d.mkdir(parents=True)
    body = fx.add_converged_closing_row(_NO_EVIDENCE.replace("# Design", "# Spec"))
    (d / "spec.md").write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    r = _vs_run(tmp_path, d, "--approve", "spec", "--force")
    assert r.returncode == 0, r.stdout


def test_sdd_task_tick_unstamped_refused_byte_identical(tmp_path):
    c = _sdd(tmp_path, approve=("spec", "design"))
    before = c["tasks.md"].read_bytes()
    r = _vs_run(tmp_path, c["tasks.md"].parent, "--approve", "tasks", "--task-tick")
    assert r.returncode == 1 and "plain `--approve tasks`" in r.stdout
    assert c["tasks.md"].read_bytes() == before


def test_sdd_task_tick_preserves_bindings_and_override(tmp_path):
    c = _sdd(tmp_path, approve=("spec", "design"))
    c["tasks.md"].write_text(_unconverged("Tasks"), encoding="utf-8")
    d = c["tasks.md"].parent
    assert _vs_run(tmp_path, d, "--approve", "tasks", "--force", "--override-convergence", "ok").returncode == 0
    t = c["tasks.md"].read_text(encoding="utf-8")
    keep = [ln for ln in t.splitlines() if "Upstream binding" in ln or "Convergence override" in ln]
    assert len(keep) == 3
    c["tasks.md"].write_text(t.replace("## Objective\n\nx\n", "## Objective\n\n- [x] T1\n"), encoding="utf-8")
    r = _vs_run(tmp_path, d, "--approve", "tasks", "--task-tick")
    assert r.returncode == 0, r.stdout
    t2 = c["tasks.md"].read_text(encoding="utf-8")
    assert [ln for ln in t2.splitlines() if "Upstream binding" in ln or "Convergence override" in ln] == keep


def _supersede_design(c, root):
    t = c["design.md"].read_text(encoding="utf-8")
    c["design.md"].write_text(t.replace("## Objective\n\nx\n", "## Objective\n\nchanged\n"), encoding="utf-8")
    assert _vs_run(root, c["design.md"].parent, "--approve", "design", "--force").returncode == 0


def test_sdd_task_tick_keeps_superseded_binding_reported(tmp_path):
    c = _sdd(tmp_path, approve=("spec", "design", "tasks"))
    _supersede_design(c, tmp_path)
    d = c["tasks.md"].parent
    before = [ln for ln in c["tasks.md"].read_text(encoding="utf-8").splitlines() if "Upstream binding" in ln]
    assert _vs_run(tmp_path, d, "--approve", "tasks", "--task-tick").returncode == 0
    after = [ln for ln in c["tasks.md"].read_text(encoding="utf-8").splitlines() if "Upstream binding" in ln]
    assert before == after
    v = _vs_run(tmp_path, d)
    assert "tasks.md upstream binding current" in v.stdout and "newer-stamp" in v.stdout
    rs_out = _vs_run(tmp_path, d, "--run-state").stdout
    assert "upstream-drift" in rs_out


def test_sdd_approve_design_exempts_own_superseded_binding(tmp_path):
    c = _sdd(tmp_path, approve=("spec", "design"))
    t = c["spec.md"].read_text(encoding="utf-8")
    c["spec.md"].write_text(t.replace("## Objective\n\nx\n", "## Objective\n\nedited\n"), encoding="utf-8")
    d = c["spec.md"].parent
    assert _vs_run(tmp_path, d, "--approve", "spec", "--force").returncode == 0
    new_b = bc.read_stored_hash(c["spec.md"].read_text(encoding="utf-8"))
    r = _vs_run(tmp_path, d, "--approve", "design")  # refused for structure, not its own binding
    assert "design.md upstream binding current" not in r.stdout
    assert _vs_run(tmp_path, d, "--approve", "design", "--force").returncode == 0
    assert bc.read_bindings(c["design.md"].read_text(encoding="utf-8")) == {"spec.md": (new_b,)}


def test_sdd_approve_tasks_fails_on_design_superseded_binding(tmp_path):
    c = _sdd(tmp_path, approve=("spec", "design"))
    t = c["spec.md"].read_text(encoding="utf-8")
    c["spec.md"].write_text(t.replace("## Objective\n\nx\n", "## Objective\n\nedited\n"), encoding="utf-8")
    d = c["spec.md"].parent
    assert _vs_run(tmp_path, d, "--approve", "spec", "--force").returncode == 0
    r = _vs_run(tmp_path, d, "--approve", "tasks")
    assert r.returncode == 1 and "previous phase (design.md) upstream binding current" in r.stdout


@pytest.mark.parametrize("force", [False, True])
def test_sdd_unbindable_upstream_refused_with_and_without_force(tmp_path, force):
    c = fx.write_chain(tmp_path, "sdd", approve=[], bind=True)
    args = ["--approve", "design"] + (["--force"] if force else [])
    r = _vs_run(tmp_path, c["design.md"].parent, *args)
    assert r.returncode == 1
    assert "Approve the named upstream first" in r.stdout and "spec.md" in r.stdout
    assert bc.read_stored_hash(c["design.md"].read_text(encoding="utf-8")) == "pending"


def test_sdd_approval_race_error_exit_1_file_unchanged(tmp_path, monkeypatch, capsys):
    vs = fx._load_validator("sdd")
    c = _sdd(tmp_path)
    p = c["design.md"]
    real = vs.plan_approval

    def racing(target, **kw):
        plan = real(target, **kw)
        Path(target).write_text(fx.add_converged_closing_row(Path(target).read_text(encoding="utf-8")),
                                encoding="utf-8")
        return plan

    monkeypatch.setattr(vs, "plan_approval", racing)
    args = argparse.Namespace(approve="design", force=True, task_tick=False, language=None)
    rc = vs._handle_approve(args, p.parent, tmp_path)
    after_rewrite = p.read_bytes()
    assert rc == 1 and "changed during approval; re-run" in capsys.readouterr().out
    assert p.read_bytes() == after_rewrite and bc.read_stored_hash(p.read_text(encoding="utf-8")) == "pending"


# --- T30: the blueprint approve path with the gate live -----------------------

_VB_CLI = _SCRIPTS.parent / "skills" / "project-blueprint" / "scripts" / "validate_blueprint.py"


def _vb_run(root, d, *args):
    return subprocess.run([sys.executable, str(_VB_CLI), str(d), *args, "--project-root", str(root)],
                          capture_output=True, text=True)


def _bp(root, approve=("scope",)):
    return fx.write_chain(root, "blueprint", approve=list(approve), bind=True)


_BP_NO_EVIDENCE = (
    "# Architecture\n\n## Objective\n\nx\n\n"
    "## Approval\n\n- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
)
_PLAN_CFC = (
    "# Plan\n\n## Cross-Feature Contracts\n\n### CFC-1: ids\n\n"
    "- **Participating features:** F1, F2\n- **Contract:** stable ids.\n"
    "- **Per-feature AC:** GIVEN an id WHEN read THEN stable [CFC-1]\n"
    "- **Enforcement:** F1 owns the check.\n\n"
    "## Approval\n\n- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
)


def test_blueprint_no_evidence_without_force_prints_panel_and_gate_fail(tmp_path):
    c = _bp(tmp_path)
    c["ARCHITECTURE.md"].write_text(_BP_NO_EVIDENCE, encoding="utf-8")
    r = _vb_run(tmp_path, c["ARCHITECTURE.md"].parent, "--approve", "architecture")
    assert r.returncode == 1
    assert "Panel Review" in r.stdout and "no converged panel pass recorded" in r.stdout


def test_blueprint_force_does_not_bypass_gate(tmp_path):
    c = _bp(tmp_path)
    c["ARCHITECTURE.md"].write_text(_unconverged("Architecture"), encoding="utf-8")
    r = _vb_run(tmp_path, c["ARCHITECTURE.md"].parent, "--approve", "architecture", "--force")
    assert r.returncode == 1 and "ARCHITECTURE.md convergence gate" in r.stdout


def test_blueprint_force_still_surfaces_cfc_drift_warns(tmp_path):
    c = _bp(tmp_path, approve=("scope", "architecture"))
    owner_silent = _PLAN_CFC.replace("- **Enforcement:** F1 owns the check.", "- **Enforcement:** verified by an ArchUnit rule.")
    c["PLAN.md"].write_text(fx.add_converged_closing_row(owner_silent), encoding="utf-8")
    r = _vb_run(tmp_path, c["PLAN.md"].parent, "--approve", "plan", "--force")
    assert r.returncode == 0, r.stdout
    assert "CFC coverage / drift warnings" in r.stdout
    assert r.stdout.index("CFC coverage / drift warnings") < r.stdout.index("Approved:")
    c2 = _bp(tmp_path / "b", approve=("scope", "architecture"))
    c2["PLAN.md"].write_text(_PLAN_CFC, encoding="utf-8")  # no closing row: gate refuses
    r2 = _vb_run(tmp_path / "b", c2["PLAN.md"].parent, "--approve", "plan", "--force")
    assert r2.returncode == 1 and "PLAN.md convergence gate" in r2.stdout


def test_blueprint_force_plus_override_no_evidence_stamps_pass_none(tmp_path):
    c = _bp(tmp_path)
    c["ARCHITECTURE.md"].write_text(_BP_NO_EVIDENCE, encoding="utf-8")
    r = _vb_run(tmp_path, c["ARCHITECTURE.md"].parent, "--approve", "architecture", "--force",
                "--override-convergence", "accepted")
    assert r.returncode == 0, r.stdout
    assert "- **Convergence override:** pass none — accepted" in c["ARCHITECTURE.md"].read_text(encoding="utf-8")


@pytest.mark.parametrize("reason", ["", "  "])
def test_blueprint_override_blank_reason_exit_2(tmp_path, reason):
    c = _bp(tmp_path)
    r = _vb_run(tmp_path, c["SCOPE.md"].parent, "--approve", "architecture", "--override-convergence", reason)
    assert r.returncode == 2 and '--override-convergence "<reason>"' in r.stdout


@pytest.mark.parametrize("reason", ["***", "###", "\x1b[0m"])
def test_blueprint_override_reason_sanitising_empty_exit_2_before_read(tmp_path, reason):
    c = _bp(tmp_path)
    p = c["ARCHITECTURE.md"]
    p.chmod(0o000)
    try:
        r = _vb_run(tmp_path, p.parent, "--approve", "architecture", "--override-convergence", reason)
    finally:
        p.chmod(0o644)
    assert r.returncode == 2


def test_blueprint_scope_reapproval_then_architecture_approval_rebinds(tmp_path):
    c = _bp(tmp_path, approve=("scope", "architecture"))
    d = c["SCOPE.md"].parent
    t = c["SCOPE.md"].read_text(encoding="utf-8")
    c["SCOPE.md"].write_text(t.replace("## Objective\n\nx\n", "## Objective\n\nedited\n"), encoding="utf-8")
    assert _vb_run(tmp_path, d, "--approve", "scope", "--force").returncode == 0
    new = bc.read_stored_hash(c["SCOPE.md"].read_text(encoding="utf-8"))
    r = _vb_run(tmp_path, d, "--approve", "architecture", "--force")
    assert r.returncode == 0, r.stdout
    assert bc.read_bindings(c["ARCHITECTURE.md"].read_text(encoding="utf-8")) == {"SCOPE.md": (new,)}


def test_blueprint_override_without_approve_exit_2(tmp_path):
    c = _bp(tmp_path)
    r = _vb_run(tmp_path, c["SCOPE.md"].parent, "--override-convergence", "x")
    assert r.returncode == 2 and "only valid with --approve" in r.stdout


def test_blueprint_reapproval_never_meets_gate(tmp_path):
    c = _bp(tmp_path)
    c["ARCHITECTURE.md"].write_text(_unconverged("Architecture"), encoding="utf-8")
    d = c["SCOPE.md"].parent
    assert _vb_run(tmp_path, d, "--approve", "architecture", "--force", "--override-convergence", "x").returncode == 0
    r = _vb_run(tmp_path, d, "--approve", "architecture", "--force")
    assert r.returncode == 0 and "convergence gate" not in r.stdout


def test_blueprint_widen_then_first_approval_passes_freshness(tmp_path):
    (tmp_path / ".git").mkdir()
    d = tmp_path / "blueprint"
    d.mkdir()
    doc = _tdoc().replace("### Latest pass detail", "### Deferred dispositions\n\n<!-- x -->\n\n### Latest pass detail")
    p = d / "SCOPE.md"
    p.write_text(doc, encoding="utf-8")
    for flag in ("--strict-bar", "--cross-check"):
        subprocess.run([sys.executable, str(_SCRIPTS / "archive_pass.py"), str(p), "--phase", "1", flag],
                       check=True, capture_output=True)
    assert _vb_run(tmp_path, d, "--approve", "scope", "--force").returncode == 0


def test_blueprint_approve_architecture_exempts_own_superseded_binding(tmp_path):
    c = _bp(tmp_path, approve=("scope", "architecture"))
    d = c["SCOPE.md"].parent
    t = c["SCOPE.md"].read_text(encoding="utf-8")
    c["SCOPE.md"].write_text(t.replace("## Objective\n\nx\n", "## Objective\n\nedited\n"), encoding="utf-8")
    assert _vb_run(tmp_path, d, "--approve", "scope", "--force").returncode == 0
    r = _vb_run(tmp_path, d, "--approve", "architecture")
    assert "ARCHITECTURE.md upstream binding current" not in r.stdout


def test_blueprint_approve_plan_fails_on_architecture_superseded_binding(tmp_path):
    c = _bp(tmp_path, approve=("scope", "architecture"))
    d = c["SCOPE.md"].parent
    t = c["SCOPE.md"].read_text(encoding="utf-8")
    c["SCOPE.md"].write_text(t.replace("## Objective\n\nx\n", "## Objective\n\nedited\n"), encoding="utf-8")
    assert _vb_run(tmp_path, d, "--approve", "scope", "--force").returncode == 0
    r = _vb_run(tmp_path, d, "--approve", "plan")
    assert r.returncode == 1 and "previous phase (ARCHITECTURE.md) upstream binding current" in r.stdout


@pytest.mark.parametrize("force", [False, True])
def test_blueprint_unbindable_upstream_refused_with_and_without_force(tmp_path, force):
    c = fx.write_chain(tmp_path, "blueprint", approve=[], bind=True)
    r = _vb_run(tmp_path, c["SCOPE.md"].parent, "--approve", "architecture", *(["--force"] if force else []))
    assert r.returncode == 1 and "Approve the named upstream first" in r.stdout and "SCOPE.md" in r.stdout


def test_blueprint_race_seam_plan_with_cfc_refused_before_refresh(tmp_path, monkeypatch, capsys):
    vb = fx._load_validator("blueprint")
    c = _bp(tmp_path, approve=("scope", "architecture"))
    p = c["PLAN.md"]
    p.write_text(fx.add_converged_closing_row(_PLAN_CFC), encoding="utf-8")
    real = vb.plan_approval
    refreshed = []
    real_refresh = vb._plan_cfc_hash_refresh
    monkeypatch.setattr(vb, "_plan_cfc_hash_refresh", lambda c_, f: refreshed.append(1) or real_refresh(c_, f))

    def racing(target, **kw):
        plan = real(target, **kw)
        Path(target).write_text(fx.add_converged_closing_row(Path(target).read_text(encoding="utf-8")),
                                encoding="utf-8")
        return plan

    monkeypatch.setattr(vb, "plan_approval", racing)
    rc = vb._handle_approve(argparse.Namespace(approve="plan", force=True), p.parent, tmp_path)
    after = p.read_bytes()
    assert rc == 1 and "changed during approval; re-run" in capsys.readouterr().out
    assert p.read_bytes() == after and "CFC Content Hashes" not in p.read_text(encoding="utf-8")


def test_gate_outcomes_identical_both_tiers(tmp_path):
    texts = {}
    for tier, name, flag, run in (("sdd", "design.md", "design", _vs_run),
                                  ("blueprint", "ARCHITECTURE.md", "architecture", _vb_run)):
        root = tmp_path / tier
        c = fx.write_chain(root, tier, approve=[{"sdd": "spec", "blueprint": "scope"}[tier]], bind=True)
        c[name].write_text(_unconverged(), encoding="utf-8")
        r = run(root, c[name].parent, "--approve", flag, "--force")
        assert r.returncode == 1
        line = next(ln for ln in r.stdout.splitlines() if f"{name} convergence gate" in ln)
        texts[tier] = re.sub(r"\S*" + re.escape(name), "ART", line)
    assert texts["sdd"] == texts["blueprint"]


# --- T31: --audit-convergence on both validators -------------------------------

import os  # noqa: E402

import run_state_snapshot as _snap  # noqa: E402


def test_sdd_audit_feature_dir_and_parent_dir(tmp_path):
    a = fx.write_chain(tmp_path, "sdd", approve=["spec", "design"], bind=True)
    feat = a["spec.md"].parent
    (tmp_path / "specs" / "notes").mkdir()  # non-feature child: ignored
    other = tmp_path / "specs" / "aaa-first"
    other.mkdir()
    (other / "spec.md").write_text(_approved_doc(_fresh(_row(1, "PROV", highs="1"))), encoding="utf-8")
    r = _vs_run(tmp_path, feat, "--audit-convergence")
    lines = r.stdout.splitlines()
    assert [ln.split(":")[0] for ln in lines[:-1]] == ["feat-x/spec.md", "feat-x/design.md"]
    assert all(ln.endswith(": converged") for ln in lines[:-1])
    assert lines[-1].startswith("convergence audit: converged 2,") and r.returncode == 0
    r = _vs_run(tmp_path, tmp_path / "specs", "--audit-convergence")
    lines = r.stdout.splitlines()
    assert lines[0].startswith("aaa-first/spec.md: unconverged (")
    assert [ln.split(":")[0] for ln in lines[1:-1]] == ["feat-x/spec.md", "feat-x/design.md"]
    assert r.returncode == 1


def test_blueprint_audit_three_artifacts(tmp_path):
    c = fx.write_chain(tmp_path, "blueprint", approve=["scope", "architecture", "plan"], bind=True)
    r = _vb_run(tmp_path, c["SCOPE.md"].parent, "--audit-convergence")
    lines = r.stdout.splitlines()
    assert [ln.split(":")[0] for ln in lines[:-1]] == [
        "blueprint/SCOPE.md", "blueprint/ARCHITECTURE.md", "blueprint/PLAN.md"]
    assert lines[-1].startswith("convergence audit: converged 3,") and r.returncode == 0


def _cruft(root: Path, scope: str):
    sdd = root / ".sdd"
    (sdd / "panel-findings" / scope).mkdir(parents=True, exist_ok=True)
    files = [sdd / "x.tmp", sdd / "pending-review.lock", sdd / "panel-findings" / scope / "x.md"]
    old = 1_000_000_000
    for f in files:
        f.write_text("old\n", encoding="utf-8")
        os.utime(f, (old, old))
    return files


def _audit_writes_nothing(tmp_path, tier):
    c = fx.write_chain(tmp_path, tier, approve=[{"sdd": "spec", "blueprint": "scope"}[tier]], bind=True)
    d = next(iter(c.values())).parent
    run = _vs_run if tier == "sdd" else _vb_run
    scope = "sdd/feat-x" if tier == "sdd" else "blueprint"
    files = _cruft(tmp_path, scope)
    before = {f: f.read_bytes() for f in files}
    snap = _snap.snapshot_tree(tmp_path)
    r = run(tmp_path, d, "--audit-convergence")
    assert r.returncode == 0, r.stdout
    assert {f: f.read_bytes() for f in files} == before
    assert _snap.snapshot_tree(tmp_path) == snap
    run(tmp_path, d)  # control: plain validation runs the atexit sweep
    assert not files[0].exists()


def test_audit_writes_nothing_subprocess_sdd(tmp_path):
    _audit_writes_nothing(tmp_path, "sdd")


def test_audit_writes_nothing_subprocess_blueprint(tmp_path):
    _audit_writes_nothing(tmp_path, "blueprint")


@pytest.mark.parametrize("tier,extra", [("sdd", ["--approve", "spec"]), ("blueprint", ["--run-state"])])
def test_audit_flag_mutually_exclusive_with_modes(tmp_path, tier, extra):
    c = fx.write_chain(tmp_path, tier, approve=[], bind=False)
    d = next(iter(c.values())).parent
    run = _vs_run if tier == "sdd" else _vb_run
    assert run(tmp_path, d, "--audit-convergence", *extra).returncode == 2


def test_sdd_audit_parent_with_ambiguous_child_is_unauditable(tmp_path):
    fx.write_chain(tmp_path, "sdd", approve=["spec"], bind=True)
    amb = tmp_path / "specs" / "bbb"
    amb.mkdir()
    (amb / "spec.md").write_text("# a\n", encoding="utf-8")
    (amb / "01_spec.md").write_text("# b\n", encoding="utf-8")
    r = _vs_run(tmp_path, tmp_path / "specs", "--audit-convergence")
    assert "bbb: unauditable (ambiguous NN_ prefix)" in r.stdout, r.stdout + r.stderr
    assert "feat-x/spec.md: converged" in r.stdout and r.returncode == 1


# --- T34: the AC-5.5 lightweight-exit paragraph -------------------------------

AC_5_5_PARAGRAPH = (
    "**Approval after a lightweight exit.** If the single pass did not converge, the "
    "artifact's first `--approve` is refused by the convergence gate; the route out is "
    "the convergence override (`--override-convergence \"<reason>\"`), a user decision "
    "the validator records in the artifact's `## Approval` section."
)
_PRICED = "**The priced-edit rule does not apply here**"


def test_lightweight_override_paragraph_byte_identical_both_copies():
    found = []
    for tier in ("spec-driven-dev", "project-blueprint"):
        text = (_SCRIPTS.parent / "skills" / tier / "references" / "panel-review-modes.md").read_text(encoding="utf-8")
        sec = text[text.index("## Lightweight Mode (single-pass panel)"):]
        sec = sec[: sec.index("\n## ", 5)]
        priced_end = sec.index("\n", sec.index(_PRICED))
        assert sec[priced_end:].startswith("\n\n" + AC_5_5_PARAGRAPH + "\n"), tier
        found.append(AC_5_5_PARAGRAPH in sec)
    assert found == [True, True]


# --- T36: the user-decision wording on the two opt-in flags (AC-9.1) ----------

import pending_review as _pr  # noqa: E402


def _decline_key_messages(root: Path) -> "dict[str, str]":
    (root / "specs" / "F1-x").mkdir(parents=True)
    for k in ("specs/F1-x/spec.md", "specs/F3-old/spec.md"):
        bc.upsert_pending_entry(root, k, "a" * 16, "t", 1)
    keys = ["specs/F1-x/spec.md", "specs/F3-old/spec.md"]
    route = _pr.owning_dir_route(root, keys[1], keys, target_rel="specs", running_tier="sdd", use="run-state")
    res = _pr.decline_pending_scoped(root, ".", running_tier="sdd")
    refusal = _pr.format_decline_refusal(res.refusal, project_root=root, target_rel=".", running_tier="sdd")
    stranded = " | ".join(c[2] for c in _pr.reconcile_to_result(
        root, "specs/F1-x", decline_cmd="x", running_tier="sdd").checks)
    return {"vanished-route": route, "multi-scope-refusal": refusal, "stranded-warn": stranded}


def _override_messages() -> "dict[str, str]":
    cases = {
        "AC-5.2": _fresh(_row(1, "PROV", highs="2")),
        "AC-5.3": _fresh(_row(1, f"{SB}; {CNH}; PROV")),
        "AC-5.5": _fresh(_row(1, "PROV", highs="1", addressed="2")),
        "AC-5.11": _fresh(_row(1, f"{CNH}; PROV"), edit_after=True),
        "AC-5.6-skip-only": _tdoc(_row(1, f"skipped (mechanical: x); {P}", "—", "—")),
        "AC-5.6-seal-only": _tdoc().replace("_None yet._", "- `[SEAL-01]` **x** (pass 1, user-directed) — Defense: d."),
    }
    return {k: _gate(doc)[1][0][2] for k, doc in cases.items()}


@pytest.mark.parametrize("which", [
    "vanished-route", "multi-scope-refusal", "stranded-warn",
    "AC-5.2", "AC-5.3", "AC-5.5", "AC-5.11", "AC-5.6-skip-only", "AC-5.6-seal-only",
])
def test_user_decision_flag_messages_carry_note(tmp_path, which):
    msgs = _decline_key_messages(tmp_path) if which in ("vanished-route", "multi-scope-refusal", "stranded-warn") else _override_messages()
    msg = msgs[which]
    assert ("--decline-key" in msg) or ("--override-convergence" in msg), msg
    assert bc.USER_DECISION_NOTE == "this is a user decision; confirm before running"
    assert bc.USER_DECISION_NOTE in msg, msg


def test_no_evidence_message_names_no_override():
    doc = "# D\n\n## Objective\n\nx\n\n## Approval\n\n- [ ] Approved to proceed\n- **Content Hash:** `pending`\n"
    d = _gate(doc)[1][0][2]
    assert "no converged panel pass recorded" in d
    assert "--override-convergence" not in d and bc.USER_DECISION_NOTE not in d


# --- Unit F T13 (R4): the gate accepts a frozen-v2 prov= ----------------------


def _v2_prov_doc(edit_after: bool = False) -> str:
    """A never-approved artifact whose converged closing row carries a prov=
    computed under FROZEN v2 (as an archive_pass.py from before Unit F wrote it)."""
    from content_hash import compute_content_hash_v2

    doc = _tdoc(_row(1, f"{CNH}; PROV"))
    h2 = compute_content_hash_v2(doc)
    assert h2 != compute_content_hash(doc)  # the padded table: v2 and v3 really differ
    doc = doc.replace("PROV", f"prov={h2}")
    if edit_after:
        doc = doc.replace("## Objective\n\nx\n", "## Objective\n\nedited after the pass\n")
    return doc


def test_gate_accepts_v2_prov_on_unedited_padded_artifact():
    """AC-4.1: an in-flight v2 prov= on content unedited since that archive does
    not report edited-after-pass at the first --approve after the upgrade."""
    _v, rows = _gate(_v2_prov_doc())
    assert all("edited-after-pass" not in r[2] for r in rows)
    assert _sev(rows) == "PASS" and "closing pass 1 converged" in rows[0][2]


def test_gate_rejects_v2_prov_after_substantive_edit():
    """AC-4.2: the same artifact plus a substantive edit still reports
    edited-after-pass, as in v2.28.0."""
    _v, rows = _gate(_v2_prov_doc(edit_after=True))
    assert "edited-after-pass" in rows[0][2]


def test_gate_rejects_prov_matching_neither_basis():
    doc = _v2_prov_doc()
    m = re.search(r"prov=([0-9a-f]{16})", doc)
    flipped = ("0" if m.group(1)[0] != "0" else "1") + m.group(1)[1:]
    _v, rows = _gate(doc.replace(m.group(0), f"prov={flipped}"))
    assert "edited-after-pass" in rows[0][2]
