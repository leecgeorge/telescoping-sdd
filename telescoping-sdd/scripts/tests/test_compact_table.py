"""Unit tests for `compact_table.py` — the interchange-shape validators.

Covers `validate_compact_table(text, *, phase)` (AD8 bucket-A syntactic grammar
over the DM2 8-column table) and `validate_discrepancy_list(items)` (DM4 schema).
Deterministic shape checks only — no synthesis/fidelity judgment (design AD15).

See specs/context-window-inflow-reduction/{01_spec.md,02_design.md,03_tasks.md}
(design C7, AD5, AD8, AD15, I4, I5, DM2, DM4; HIGH-1, LOW-8, MED-2, MED-4, LOW-4,
LOW-7).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"


def _load():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    if "compact_table" in sys.modules:
        return importlib.reload(sys.modules["compact_table"])
    return importlib.import_module("compact_table")


# --- Table builders --------------------------------------------------------

_HEADER = (
    "| ROW | ANCHOR-REFS | SEVERITY | SOURCE | SCOPE | CONCERN "
    "| DISPOSITION-PROPOSAL | FIX-INSTRUCTION |"
)
_SEP = "|-----|-------------|----------|--------|-------|---------|----------------------|-----------------|"


def _table(*rows: str) -> str:
    return "\n".join([_HEADER, _SEP, *rows]) + "\n"


def _row(
    row="1",
    anchors="arch-H01",
    severity="[HIGH]",
    source="architect",
    scope="[contract]",
    concern="a concern",
    disposition="Addressed",
    fix="edit the thing",
):
    return (
        f"| {row} | {anchors} | {severity} | {source} | {scope} "
        f"| {concern} | {disposition} | {fix} |"
    )


# --- validate_compact_table ------------------------------------------------


def test_validate_compact_table_accepts_clean_phase2_table():
    ct = _load()
    # Phase 2: SCOPE required on HIGH rows, [detail] NOT allowed.
    assert ct.validate_compact_table(_table(_row(scope="[contract]")), phase=2) == []


def test_validate_compact_table_rejects_reordered_headers():
    ct = _load()
    bad_header = (
        "| ANCHOR-REFS | ROW | SEVERITY | SOURCE | SCOPE | CONCERN "
        "| DISPOSITION-PROPOSAL | FIX-INSTRUCTION |"
    )
    text = "\n".join([bad_header, _SEP, _row()]) + "\n"
    assert ct.validate_compact_table(text, phase=2) != []


def test_validate_compact_table_rejects_wrong_cell_count():
    ct = _load()
    # Only 7 cells (dropped FIX-INSTRUCTION).
    short = "| 1 | arch-H01 | [HIGH] | architect | [contract] | a concern | Addressed |"
    assert ct.validate_compact_table(_table(short), phase=2) != []


def test_validate_compact_table_rejects_bad_severity():
    ct = _load()
    assert ct.validate_compact_table(
        _table(_row(severity="[CRITICAL]")), phase=2
    ) != []
    # Two core severities is also invalid.
    assert ct.validate_compact_table(
        _table(_row(severity="[HIGH][MED]")), phase=2
    ) != []


def test_validate_compact_table_accepts_deferred_target_base():
    """HIGH-1: a `Deferred → design.md` proposal is accepted on its Deferred base."""
    ct = _load()
    assert ct.validate_compact_table(
        _table(_row(disposition="Deferred → design.md", fix="")), phase=2
    ) == []


def test_validate_compact_table_rejects_out_of_vocab_base():
    ct = _load()
    assert ct.validate_compact_table(
        _table(_row(disposition="Postponed → design.md", fix="")), phase=2
    ) != []


def test_validate_compact_table_rejects_empty_source_on_high_row():
    """MED-4: empty SOURCE on a HIGH row is a syntactic violation."""
    ct = _load()
    assert ct.validate_compact_table(_table(_row(source="  ")), phase=2) != []


def test_validate_compact_table_rejects_missing_anchor_refs_on_high_row():
    ct = _load()
    assert ct.validate_compact_table(_table(_row(anchors="  ")), phase=2) != []


def test_validate_compact_table_rejects_empty_fix_on_addressed_high():
    """LOW-4: an Addressed-base HIGH row must name the fix."""
    ct = _load()
    assert ct.validate_compact_table(
        _table(_row(disposition="Addressed", fix="   ")), phase=2
    ) != []


def test_validate_compact_table_rejects_embedded_newline_in_free_text():
    """LOW-7: an embedded newline (\\n / \\r / U+2028 / U+2029) in CONCERN or
    FIX-INSTRUCTION is rejected."""
    ct = _load()
    for ch in ("\r", "\u2028", "\u2029", "\n"):
        text = _table(_row(concern=f"line one{ch}line two"))
        assert ct.validate_compact_table(text, phase=2) != [], repr(ch)
        text_fix = _table(_row(fix=f"do a{ch}then b"))
        assert ct.validate_compact_table(text_fix, phase=2) != [], repr(ch)


def test_validate_compact_table_phase2_requires_scope():
    """MED-2: Phase 2 HIGH row missing SCOPE is rejected; a valid one accepted."""
    ct = _load()
    assert ct.validate_compact_table(_table(_row(scope="  ")), phase=2) != []
    assert ct.validate_compact_table(_table(_row(scope="[upstream]")), phase=2) == []


def test_validate_compact_table_phase1_forbids_scope():
    """MED-2: Phase 1 row carrying a SCOPE tag is rejected; no-SCOPE accepted."""
    ct = _load()
    assert ct.validate_compact_table(_table(_row(scope="[contract]")), phase=1) != []
    assert ct.validate_compact_table(_table(_row(scope="")), phase=1) == []


def test_validate_compact_table_phase2_forbids_detail_scope():
    """[detail] is Phase 3 only — a Phase 2 HIGH row with [detail] is rejected."""
    ct = _load()
    assert ct.validate_compact_table(_table(_row(scope="[detail]")), phase=2) != []
    assert ct.validate_compact_table(_table(_row(scope="[detail]")), phase=3) == []


def test_validate_compact_table_accepts_merged_and_downgrade_shaped_rows():
    """AD7/DR1: a merged row (multi ANCHOR-REFS/SOURCE) and a same-id downgrade-
    shaped row (an anchor id on a non-HIGH row) are valid SHAPES the orchestrator
    must be able to see."""
    ct = _load()
    merged = _row(
        row="1",
        anchors="arch-H01, sec-H02",
        source="architect, security-reviewer",
        scope="[contract]",
    )
    downgrade = _row(
        row="2",
        anchors="arch-H01",
        severity="[MED]",
        source="architect",
        scope="",  # non-HIGH row: SCOPE not required in P3
        disposition="Accepted as risk",
        fix="",
    )
    assert ct.validate_compact_table(_table(merged, downgrade), phase=3) == []


def test_compact_table_vocab_matches_archive_pass_labels():
    """LOW-8/HIGH-1: the accepted disposition-base label set is exactly
    archive_pass.DISPOSITION_LABELS AND a `Deferred → target` is accepted — pins
    the SHARED split rule imported via archive_pass.is_known_disposition."""
    ct = _load()
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    import archive_pass

    for label in archive_pass.DISPOSITION_LABELS:
        # Addressed needs a fix; others don't. Deferred/User-input need extras
        # only at the on-disk archive layer, not in the shape validator.
        fix = "edit" if label == "Addressed" else ""
        assert ct.validate_compact_table(
            _table(_row(disposition=label, fix=fix)), phase=2
        ) == [], label
    # And a base-extracted targeted Deferred is accepted (shared split rule).
    assert ct.validate_compact_table(
        _table(_row(disposition="Deferred → tasks.md", fix="")), phase=2
    ) == []


# --- validate_discrepancy_list ---------------------------------------------


def _disc(**over):
    item = {
        "checklist_item": "criterion 1",
        "file": "spec.md",
        "quoted_span_or_line": "line 12: foo",
        "description": "mismatch between X and Y",
    }
    item.update(over)
    return item


def test_validate_discrepancy_list_rejects_missing_field():
    ct = _load()
    bad = _disc()
    del bad["description"]
    assert ct.validate_discrepancy_list([bad]) != []


def test_validate_discrepancy_list_rejects_empty_span():
    ct = _load()
    assert ct.validate_discrepancy_list([_disc(quoted_span_or_line="")]) != []


def test_validate_discrepancy_list_accepts_wellformed():
    ct = _load()
    assert ct.validate_discrepancy_list([_disc(), _disc(file="design.md")]) == []


def test_validate_discrepancy_list_empty_list_distinct_from_clean_sentinel():
    """Tasks-phase note: an empty list [] is a valid no-discrepancies return,
    distinct from the dispatch-layer `"clean"` sentinel (which this validator
    never sees)."""
    ct = _load()
    assert ct.validate_discrepancy_list([]) == []
