"""Unit C0 R7 — every cited AC label resolves to a definition in spec.md (AD18)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
for _p in (str(_SCRIPTS), str(_SCRIPTS.parents[2] / "scripts"), str(_SCRIPTS.parents[2] / "scripts" / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import validate_spec as vs  # noqa: E402
import blueprint_common as bc  # noqa: E402

CHECK = "AC labels resolve"


def _rows(result, name):
    return [c for c in result.checks if c[0] == f"{name} {CHECK}"]


def _check(tmp_path, spec_text, name="spec.md", content=None):
    d = tmp_path / "specs" / "feat-x"
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(spec_text, encoding="utf-8")
    text = spec_text if name == "spec.md" else content
    if name != "spec.md":
        (d / name).write_text(text, encoding="utf-8")
    r = bc.ValidationResult()
    vs.check_ac_labels(d, name, text, r)
    return _rows(r, name)


SPEC = (
    "# Spec\n\n## Requirements\n\n"
    "- **AC-1.1**\n  GIVEN x WHEN y THEN z\n"
    "- **AC-1.2** trailing text cites AC-1.1\n"
)


def test_definition_is_line_start_bold_label():
    assert vs.collect_ac_definitions(SPEC) == {"AC-1.1": 5, "AC-1.2": 7}
    assert vs.collect_ac_definitions("* **AC-3.4**\n+ **AC-3.5** x\n") == {"AC-3.4": 1, "AC-3.5": 2}
    assert vs.collect_ac_definitions("- **AC-1.1x**\n- AC-1.2\n") == {}


def test_indented_definition_not_recognised():
    assert vs.collect_ac_definitions("  - **AC-1.1**\n") == {}


def test_only_spec_defines_labels(tmp_path):
    rows = _check(tmp_path, SPEC, "design.md", "# D\n\n- **AC-9.9** defined here?\nsee AC-9.9\n")
    assert rows and rows[0][1] == bc.Severity.FAIL and "AC-9.9:3" in rows[0][2]


def test_definition_trailing_text_is_scanned():
    cites = vs.collect_ac_citations(SPEC, is_spec=True)
    assert cites == [("AC-1.1", 7)]


def test_citation_exclusions_fence_span_and_panel_review():
    text = (
        "cites AC-1.1\n"
        "```\nAC-7.7 in fence\n```\n"
        "inline `AC-8.8` span\n"
        "## Panel Review\n\nAC-6.6 history\n\n"
        "## Approval\n\nAC-1.2 after\n"
    )
    assert vs.collect_ac_citations(text, is_spec=False) == [("AC-1.1", 1), ("AC-1.2", 12)]


def test_tilde_fence_and_double_backtick_span_excluded():
    text = "~~~\nAC-7.7\n~~~\n`` AC-8.8 `x` `` and AC-1.1.2 and xAC-1.1 and AC-1.10\n"
    assert vs.collect_ac_citations(text, is_spec=False) == [("AC-1.10", 4)]


def test_dangling_label_fails_with_line_numbers(tmp_path):
    rows = _check(tmp_path, SPEC, "tasks.md", "# T\n\nsee AC-1.1\nand AC-4.2\nand AC-5.1\n")
    assert len(rows) == 1 and rows[0][1] == bc.Severity.FAIL
    d = rows[0][2]
    assert "AC-4.2:4" in d and "AC-5.1:5" in d and "AC-1.1" not in d
    assert "define the label" in d and "code span" in d and "When to Skip the Panel" in d


def test_dangling_label_blocks_approve(tmp_path):
    d = tmp_path / "specs" / "feat-x"
    d.mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    (d / "spec.md").write_text(SPEC + "\nBroken pointer to AC-9.1.\n", encoding="utf-8")
    r = vs.validate_spec(d)
    assert any(c[0] == f"spec.md {CHECK}" and c[1] == bc.Severity.FAIL for c in r.checks)
    assert not r.passed


def test_no_labels_no_citations_no_row(tmp_path):
    assert _check(tmp_path, "# Spec\n\nnothing\n") == []
    assert _check(tmp_path, "# Spec\n", "design.md", "# D\n") == []


def test_illustrative_citation_without_definitions_warns(tmp_path):
    rows = _check(tmp_path, "# Spec\n\nlike AC-2.6 in another feature\n")
    assert len(rows) == 1 and rows[0][1] == bc.Severity.WARN and "AC-2.6" in rows[0][2]


def test_wrong_but_existing_label_passes_known_limit(tmp_path):
    rows = _check(tmp_path, SPEC, "design.md", "# D\n\nthe hash rule is AC-1.2 (actually AC-1.1's claim)\n")
    assert [r[1] for r in rows] == [bc.Severity.PASS]


def test_unreviewed_edit_doctrine_shape_passes(tmp_path):
    defs = "".join(f"- **AC-{r}.{n}**\n  GIVEN a WHEN b THEN c\n" for r in range(1, 5) for n in range(1, 4))
    spec = (
        "# Spec\n\n## Requirements\n\n" + defs
        + "\nSee AC-2.3 and AC-4.1.\n\n## Panel Review\n\nconcern on AC-9.9 renumbered\n\n## Approval\n\nx\n"
    )
    design = "# D\n\nimplements AC-1.1, AC-1.2, AC-3.3\n\n## Panel Review\n\nold AC-7.7\n"
    tasks = "# T\n\n- AC: AC-4.3\n\n```\nAC-8.8\n```\n"
    for name, text in (("spec.md", spec), ("design.md", design), ("tasks.md", tasks)):
        rows = _check(tmp_path, spec, name, text)
        assert [r[1] for r in rows] == [bc.Severity.PASS], (name, rows)
