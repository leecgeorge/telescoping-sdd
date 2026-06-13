"""Panel-review `### Trajectory` table parsing — extracted from blueprint_common
(audit R3.1).

Pure, dependency-free table machinery: locating the canonical Trajectory table
(fence-aware), its bounds, trimming to the latest N rows, reading pass numbers,
and detecting orphaned (stranded) rows. A leaf module — it imports only `re`, so
blueprint_common can import it at the TOP and re-export its names (the hashing
path's `_strip_trajectory_rows` and the marker path's `stamped_at_pass_from_content`
both depend on it). Operates on RAW content — never on `content_for_hashing` output.
"""
from __future__ import annotations

import re
from typing import Optional


TRAJECTORY_HEADER = "### Trajectory"
TRAJECTORY_SEP_RE = re.compile(r"^\|[\s\-|:]+\|\s*$")
TRAJECTORY_ELIDED_NOTES_RE = re.compile(r"^(\d+) earlier passes elided$")
TRAJECTORY_KEEP_DEFAULT = 15
UPSTREAM_PANEL_TAG_RE = re.compile(r"upstream-panel ([0-9a-f]{8})")

# R4 hash-basis migration messages.
# HASH_BASIS_MIGRATION_MSG: the BLOCKING check-time FAIL detail for a v1-basis
# artifact whose stored hash no longer matches under v2. Begins with the
# distinct `HASH-BASIS-MIGRATION:` token so an operator (and `grep`) can tell it
# apart from the pre-fix `Pending-review: FAILED` text at a glance (R4.AC1).


def _panel_trajectory_header_idx(lines: list) -> "Optional[int]":
    """Line index of the canonical `### Trajectory` heading — the one INSIDE
    `## Panel Review`, fence-aware — or None.

    Single source of "which `### Trajectory` is the real one", shared by the hash
    path (`_strip_trajectory_rows`) and the bounds path (`_trajectory_bounds`), so
    the two cannot lock onto different tables on a self-documenting artifact that
    quotes an example `### Trajectory` elsewhere or inside a fenced block. Returns
    None when there is no `## Panel Review` section, or it carries no non-fenced
    `### Trajectory` heading.
    """
    panel_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^##\s+Panel Review\s*$", line):
            panel_idx = i
            break
    if panel_idx is None:
        return None
    panel_end = len(lines)
    for j in range(panel_idx + 1, len(lines)):
        if re.match(r"^##\s+", lines[j]):  # next level-2 heading ends the panel
            panel_end = j
            break
    in_fence = False
    for j in range(panel_idx + 1, panel_end):
        if lines[j].strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if lines[j].rstrip() == TRAJECTORY_HEADER:
            return j
    return None


def _trajectory_row_notes(row_line: str) -> str:
    """Return the Notes (last) cell of a trajectory row, stripped."""
    inner = row_line.strip().strip("|")
    cells = [c.strip() for c in inner.split("|")]
    return cells[-1] if cells else ""


def _trajectory_bounds(content: str) -> "Optional[tuple[int, int, int, int]]":
    """Single source of the `### Trajectory` table bounds (R10 / AD12 / H3).

    Returns (table_header_idx, first_data_idx, terminator_idx, section_end) as
    indices into `content.split("\\n")`:
      - table_header_idx: the column-header row line
      - first_data_idx:   table_header_idx + 2 (the row after header + separator)
      - terminator_idx:   the first blank/non-`|` line that ends the contiguous
                          data rows (capped at section_end) — the GFM table end
      - section_end:      the next `###`-or-shallower heading (or EOF)

    Returns None when `### Trajectory` / its table (header + separator) is absent
    — exactly the cases where `trim_trajectory_table` / `_trajectory_data_rows`
    used to early-return content/[]. Both of those now consume this helper, and
    `find_orphaned_trajectory_rows` consumes the SAME bounds, so the orphan scan
    and the anchor scan share ONE terminator definition (detector-max ==
    anchor-max by construction). Pure; never raises.

    The header is located via `_panel_trajectory_header_idx` — the SAME locator
    the hash path uses — so the rows the anchor/trim/orphan logic operates on are
    the rows the hash excludes. Falls back to the first document-wide
    `### Trajectory` only when there is no `## Panel Review` table (back-compat for
    artifacts without a Panel Review wrapper, matching the pre-refactor behavior).
    """
    lines = content.split("\n")
    header_idx = _panel_trajectory_header_idx(lines)
    if header_idx is None:
        for i, line in enumerate(lines):
            if line.rstrip() == TRAJECTORY_HEADER:
                header_idx = i
                break
    if header_idx is None:
        return None
    section_end = len(lines)
    for j in range(header_idx + 1, len(lines)):
        stripped = lines[j].lstrip()
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            if hashes <= 3:
                section_end = j
                break
    table_header_idx = None
    for j in range(header_idx + 1, section_end):
        s = lines[j].strip()
        if s.startswith("|") and s.endswith("|"):
            table_header_idx = j
            break
    if table_header_idx is None or table_header_idx + 1 >= section_end:
        return None
    if not TRAJECTORY_SEP_RE.match(lines[table_header_idx + 1]):
        return None
    first_data_idx = table_header_idx + 2
    terminator_idx = first_data_idx
    while terminator_idx < section_end:
        s = lines[terminator_idx].strip()
        if not (s.startswith("|") and s.endswith("|")):
            break
        terminator_idx += 1
    return (table_header_idx, first_data_idx, terminator_idx, section_end)


def _strip_trajectory_rows(content: str) -> str:
    """Remove data rows from the ### Trajectory table inside ## Panel Review (R1/AD1).

    Locates the canonical `### Trajectory` via `_panel_trajectory_header_idx` (the
    SAME locator `_trajectory_bounds` uses, so the rows excluded from the hash are
    exactly the rows the anchor/orphan logic operates on), bounds it at the next
    ###-or-shallower heading, and removes all data rows — keeping the heading, the
    column-header row, and the separator row intact. Every OTHER panel sub-section
    (### Latest pass detail, ### Sealed dispositions, ### Deferred dispositions)
    is left byte-identical (R7). No-op when ## Panel Review or ### Trajectory is
    absent. Idempotent.
    """
    lines = content.split("\n")
    traj_idx = _panel_trajectory_header_idx(lines)
    if traj_idx is None:
        return content
    section_end = len(lines)
    for j in range(traj_idx + 1, len(lines)):
        stripped = lines[j].lstrip()
        if stripped.startswith("#"):
            if len(stripped) - len(stripped.lstrip("#")) <= 3:
                section_end = j
                break
    table_header_idx = None
    for j in range(traj_idx + 1, section_end):
        s = lines[j].strip()
        if s.startswith("|") and s.endswith("|"):
            table_header_idx = j
            break
    if table_header_idx is None or table_header_idx + 1 >= section_end:
        return content
    if not TRAJECTORY_SEP_RE.match(lines[table_header_idx + 1]):
        return content
    data_start = table_header_idx + 2
    data_end = data_start
    while data_end < section_end:
        s = lines[data_end].strip()
        if not (s.startswith("|") and s.endswith("|")):
            break
        data_end += 1
    return "\n".join(lines[:data_start] + lines[data_end:])


def trim_trajectory_table(content: str, keep: int = TRAJECTORY_KEEP_DEFAULT) -> str:
    """Trim the `### Trajectory` table to the latest `keep` data rows.

    Rows older than the latest `keep` are replaced with a single elided
    summary row at the top of the data section:

      | … | … | — | — | — | — | — | N earlier passes elided |

    Re-approval merging: if an elided row is already present at the top
    of the data section, its count is parsed out and added to the count
    of newly-elided rows, then the merged elided row replaces the prior one.

    The function is a no-op when:
      - There is no `### Trajectory` heading.
      - The section contains no markdown table (header + separator + rows).
      - There are at most `keep` real data rows (an existing elided row
        is not counted as a data row — it's bookkeeping).

    Called from `approve_document` in both `validate_blueprint.py` and
    `validate_spec.py` so that successful approvals bound trajectory growth
    on long-lived docs without losing the audit-trail headline (the elided
    row preserves the elided pass count).
    """
    lines = content.split("\n")
    bounds = _trajectory_bounds(content)
    if bounds is None:
        return content
    _table_header_idx, data_start, data_end, _section_end = bounds

    existing_elided_count = 0
    data_first = data_start
    if data_first < data_end:
        first_notes = _trajectory_row_notes(lines[data_first])
        m = TRAJECTORY_ELIDED_NOTES_RE.match(first_notes)
        if m:
            existing_elided_count = int(m.group(1))
            data_first += 1

    real_data_count = data_end - data_first
    if real_data_count <= keep:
        return content

    to_elide = real_data_count - keep
    new_elided_count = existing_elided_count + to_elide
    elided_row = (
        f"| … | … | — | — | — | — | — | {new_elided_count} earlier passes elided |"
    )
    kept_rows = lines[data_end - keep:data_end]
    new_data_block = [elided_row, *kept_rows]
    new_lines = lines[:data_start] + new_data_block + lines[data_end:]
    return "\n".join(new_lines)


def _trajectory_data_rows(content: str) -> list[str]:
    """Data-row lines of the `### Trajectory` table (incl. any elided row), or [].

    Consumes the shared `_trajectory_bounds` so its terminator definition is
    identical to `trim_trajectory_table`'s and `find_orphaned_trajectory_rows`'s.
    """
    bounds = _trajectory_bounds(content)
    if bounds is None:
        return []
    _table_header_idx, first_data_idx, terminator_idx, _section_end = bounds
    return content.split("\n")[first_data_idx:terminator_idx]


def _row_first_cell(row_line: str) -> str:
    """First (Pass) cell of a table row, stripped — mirrors archive_pass's col 0."""
    inner = row_line.strip().strip("|")
    cells = [c.strip() for c in inner.split("|")]
    return cells[0] if cells else ""


def _is_ascii_int(cell: str) -> bool:
    """True iff `cell` is a plain ASCII integer. NOT str.isdigit(), which is True
    for non-int-convertible Unicode digits (e.g. '²') that then crash int()."""
    return cell.isascii() and cell.isdigit()


def stamped_at_pass_from_content(content: str) -> int:
    """Highest integer `Pass` value in the Trajectory table, or 0. [T2; AD5]

    Applies trim_trajectory_table first (matches approve_document's view), then
    reads the Pass column at index [0] of each data row, skipping non-digit
    cells (including the elided '…' row). Mirrors archive_pass's
    max(pass_nums, default=0).
    """
    trimmed = trim_trajectory_table(content)
    pass_nums = [
        int(cell)
        for row in _trajectory_data_rows(trimmed)
        for cell in (_row_first_cell(row),)
        if _is_ascii_int(cell)
    ]
    return max(pass_nums, default=0)


def find_orphaned_trajectory_rows(content: str) -> list[dict]:
    """Find `| … |`-shaped Trajectory data rows stranded below the contiguous-scan
    terminator (R10 / AD12). Returns one dict per orphan; [] when none.

    An ORPHANED row lies strictly between the contiguous-row terminator (the
    blank/non-`|` line that ended the table) and the `### Trajectory` sub-section's
    `section_end`, and does NOT belong to a DIFFERENT contiguous table within
    those bounds (a header immediately followed by a `TRAJECTORY_SEP_RE`
    separator begins a second table and is excluded with its rows). The scan is
    fence-aware (a `| … |` line inside a ``` block is never an orphan) and
    consumes the SAME `_trajectory_bounds` the anchor scan uses, so the orphan is
    excluded from `parsed_max` by construction (detector-max == anchor-max, H3).

    Each dict: {line_no (1-based), text, pass_int (Optional[int]),
    has_upstream_tag (bool), load_bearing (bool)} where
    load_bearing = (pass_int is not None and pass_int > parsed_max)
                   OR has_upstream_tag
    and parsed_max == stamped_at_pass_from_content(content).

    Pure read; fail-soft (never raises — a region it cannot parse yields []/
    best-effort). Operates on RAW content — NEVER content_for_hashing() output.
    """
    bounds = _trajectory_bounds(content)
    if bounds is None:
        return []
    _table_header_idx, _first_data_idx, terminator_idx, section_end = bounds
    lines = content.split("\n")
    parsed_max = stamped_at_pass_from_content(content)
    orphans: list[dict] = []
    in_fence = False
    i = terminator_idx
    while i < section_end:
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence:
            i += 1
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            # A header immediately followed by a separator begins a SECOND
            # contiguous table — skip it and its rows (not orphans).
            if i + 1 < section_end and TRAJECTORY_SEP_RE.match(lines[i + 1]):
                j = i + 2
                while j < section_end:
                    s2 = lines[j].strip()
                    if not (s2.startswith("|") and s2.endswith("|")):
                        break
                    j += 1
                i = j
                continue
            pass_cell = _row_first_cell(lines[i])
            pass_int = int(pass_cell) if _is_ascii_int(pass_cell) else None
            has_tag = bool(UPSTREAM_PANEL_TAG_RE.search(_trajectory_row_notes(lines[i])))
            load_bearing = (pass_int is not None and pass_int > parsed_max) or has_tag
            orphans.append(
                {
                    "line_no": i + 1,
                    "text": lines[i],
                    "pass_int": pass_int,
                    "has_upstream_tag": has_tag,
                    "load_bearing": load_bearing,
                }
            )
        i += 1
    return orphans
