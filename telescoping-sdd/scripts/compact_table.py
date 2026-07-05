"""Interchange-shape validators for the off-thread panel-review payloads.

Two pure functions validate the *shape* (AD8 bucket-A syntactic grammar) of the
two in-context interchange payloads that the panel loop passes between the
orchestrator and its thin subagents:

  * ``validate_compact_table(text, *, phase)`` — the DM2 8-column compact table
    that ``panel-condenser`` returns.
  * ``validate_discrepancy_list(items)`` — the DM4 discrepancy list that
    ``consistency-reader`` returns.

Both return a list of violation strings (empty = valid) and never raise. Shape
checks ONLY — no synthesis/fidelity judgment (design AD15); the bucket-B
structural checks (empty-when-HIGH-expected, non-return) are the orchestrator's.

The disposition vocabulary and the ``→ <target>`` base-extraction split rule are
single-sourced from ``archive_pass`` via a one-way read-only import of
``is_known_disposition`` and ``disposition_base`` (design C7, LOW-8, HIGH-1).
``archive_pass`` never imports this module, so its contract (Q3) is untouched.

See specs/context-window-inflow-reduction/02_design.md (C7, AD5, AD8, AD15, I4,
I5, DM2, DM4).
"""

from __future__ import annotations

import re
from typing import List

from archive_pass import disposition_base, is_known_disposition  # one-way single-source (C7/HIGH-1)

# DM2 headers — exactly and in this order (AD5).
COMPACT_TABLE_HEADERS = [
    "ROW",
    "ANCHOR-REFS",
    "SEVERITY",
    "SOURCE",
    "SCOPE",
    "CONCERN",
    "DISPOSITION-PROPOSAL",
    "FIX-INSTRUCTION",
]
_N_COLS = len(COMPACT_TABLE_HEADERS)

# Column indices (0-based).
_I_ANCHORS = 1
_I_SEVERITY = 2
_I_SOURCE = 3
_I_SCOPE = 4
_I_CONCERN = 5
_I_DISPOSITION = 6
_I_FIX = 7

# Phase-conditional SCOPE vocabulary ([detail] is Phase 3 only — DM2/MED-2).
_SCOPE_BY_PHASE = {
    1: set(),  # Phase 1: SCOPE must be ABSENT on every row.
    2: {"[contract]", "[upstream]"},
    3: {"[contract]", "[detail]", "[upstream]"},
}

# Newline-like characters forbidden inside the free-text cells (LOW-7).
_EMBEDDED_NEWLINES = ("\n", "\r", " ", " ")

# DM4 required fields.
_DISCREPANCY_FIELDS = ("checklist_item", "file", "quoted_span_or_line", "description")

# Split a markdown row on unescaped pipes (a literal `\|` is an escaped cell char).
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_SEVERITY_TAG = re.compile(r"\[(HIGH|MED|LOW|REGRESSION)\]")
_SEPARATOR_ROW = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def _split_cells(line: str) -> List[str]:
    """Split a `| a | b |`-style row into its inner cells (raw, un-stripped)."""
    parts = _UNESCAPED_PIPE.split(line)
    # A well-formed row is bounded by pipes → leading/trailing empty fragments.
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return parts


def validate_compact_table(text: str, *, phase: int) -> List[str]:
    """Return AD8 bucket-A (syntactic) violations for a DM2 compact table.

    ``phase`` (1/2/3) is REQUIRED — the SCOPE rule is phase-conditional. Pure,
    no I/O. Checks SHAPE only (see module docstring). Never raises.
    """
    violations: List[str] = []
    allowed_scope = _SCOPE_BY_PHASE.get(phase)
    if allowed_scope is None:
        return [f"phase must be 1, 2, or 3 (got {phase!r})"]

    # Split on '\n' only (NOT splitlines(), which would also split on the very
    # U+2028/U+2029 we need to detect INSIDE a cell); strip a trailing '\r'
    # line-ending so only a mid-cell '\r' is flagged as embedded.
    raw_lines = text.split("\n")
    table_lines = []
    for ln in raw_lines:
        body = ln[:-1] if ln.endswith("\r") else ln
        if body.strip().startswith("|"):
            table_lines.append(body)

    if len(table_lines) < 2:
        return ["no markdown table found (need a header row and a separator row)"]

    header_cells = [c.strip() for c in _split_cells(table_lines[0])]
    if header_cells != COMPACT_TABLE_HEADERS:
        return [
            "headers must be exactly, in order: "
            f"{COMPACT_TABLE_HEADERS} (got {header_cells})"
        ]

    if not _SEPARATOR_ROW.match(table_lines[1]):
        violations.append("row 2 must be a markdown separator row (|---|---|...)")
        data_lines = table_lines[1:]
    else:
        data_lines = table_lines[2:]

    for n, line in enumerate(data_lines, start=1):
        # A well-formed data row is bounded by pipes. A missing trailing pipe
        # signals a row broken by an embedded newline in the final cell (the
        # `\n`-in-FIX-INSTRUCTION case that a cell-count check alone misses).
        if not line.strip().endswith("|"):
            violations.append(
                f"data row {n}: missing trailing '|' "
                "(malformed row — possible embedded newline in the final cell)"
            )
            continue
        raw_cells = _split_cells(line)
        if len(raw_cells) != _N_COLS:
            violations.append(
                f"data row {n}: expected {_N_COLS} cells, got {len(raw_cells)}"
            )
            continue
        cells = [c.strip() for c in raw_cells]
        severity = cells[_I_SEVERITY]
        anchors = cells[_I_ANCHORS]
        source = cells[_I_SOURCE]
        scope = cells[_I_SCOPE]
        disposition = cells[_I_DISPOSITION]
        fix = cells[_I_FIX]

        # SEVERITY: exactly one core tag, optional trailing [REGRESSION], nothing else.
        found = _SEVERITY_TAG.findall(severity)
        core = [t for t in found if t in ("HIGH", "MED", "LOW")]
        leftover = _SEVERITY_TAG.sub("", severity).strip()
        if len(core) != 1 or leftover:
            violations.append(
                f"data row {n}: SEVERITY {severity!r} must be exactly one of "
                "[HIGH]/[MED]/[LOW] with an optional trailing [REGRESSION]"
            )
            is_high = False
        else:
            is_high = core[0] == "HIGH"

        # DISPOSITION-PROPOSAL: base-extract then vocab membership (single-sourced).
        if not is_known_disposition(disposition):
            violations.append(
                f"data row {n}: DISPOSITION-PROPOSAL {disposition!r} base is "
                "out-of-vocabulary"
            )

        # HIGH-row non-empty requirements.
        if is_high:
            if not anchors:
                violations.append(f"data row {n}: ANCHOR-REFS empty on a HIGH row")
            if not source:
                violations.append(f"data row {n}: SOURCE empty on a HIGH row")
            if not disposition:
                violations.append(
                    f"data row {n}: DISPOSITION-PROPOSAL empty on a HIGH row"
                )

        # FIX-INSTRUCTION non-empty when the proposal base is Addressed (LOW-4).
        if is_high and disposition_base(disposition) == "Addressed" and not fix:
            violations.append(
                f"data row {n}: FIX-INSTRUCTION empty on an Addressed-base HIGH row"
            )

        # SCOPE phase rule (MED-2).
        if phase == 1:
            if scope:
                violations.append(
                    f"data row {n}: SCOPE {scope!r} must be ABSENT in Phase 1"
                )
        else:  # phase 2 or 3
            if is_high:
                if not scope:
                    violations.append(
                        f"data row {n}: SCOPE required on a Phase {phase} HIGH row"
                    )
                elif scope not in allowed_scope:
                    violations.append(
                        f"data row {n}: SCOPE {scope!r} not in "
                        f"{sorted(allowed_scope)} for Phase {phase}"
                    )
            elif scope and scope not in allowed_scope:
                violations.append(
                    f"data row {n}: SCOPE {scope!r} not in "
                    f"{sorted(allowed_scope)} for Phase {phase}"
                )

        # No embedded newline in the free-text cells (LOW-7). The line-level
        # split above already strips a row-terminating '\r' before cells are
        # split, so any '\r' surviving in a cell here is a genuinely embedded
        # one and must not be stripped before this check.
        for label, value in (("CONCERN", raw_cells[_I_CONCERN]), ("FIX-INSTRUCTION", raw_cells[_I_FIX])):
            if any(ch in value for ch in _EMBEDDED_NEWLINES):
                violations.append(
                    f"data row {n}: {label} contains an embedded newline "
                    "(\\n/\\r/U+2028/U+2029)"
                )

    return violations


def _is_nonempty_single_line_str(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.strip() != ""
        and not any(ch in value for ch in _EMBEDDED_NEWLINES)
    )


def validate_discrepancy_list(items: List[dict]) -> List[str]:
    """Return DM4 schema violations for a discrepancy list (empty = valid).

    Pure, stdlib-only, no I/O. Each item must carry all four fields, each a
    non-empty single-line string. An empty list ``[]`` is valid (a
    no-discrepancies return, distinct from the dispatch-layer ``"clean"``
    sentinel, which this validator never sees). Never raises.
    """
    violations: List[str] = []
    if not isinstance(items, list):
        return [f"discrepancy list must be a list (got {type(items).__name__})"]
    for n, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            violations.append(f"item {n}: must be an object")
            continue
        for field in _DISCREPANCY_FIELDS:
            if field not in item:
                violations.append(f"item {n}: missing required field {field!r}")
            elif not _is_nonempty_single_line_str(item[field]):
                violations.append(
                    f"item {n}: field {field!r} must be a non-empty single-line string"
                )
    return violations
