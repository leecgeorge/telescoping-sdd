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
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple


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


# ---------------------------------------------------------------------------
# Table helpers, terminal rules and stamp constants (Unit C0 AD1/AD2).
# Moved here from archive_pass.py so the validators can read them without
# importing a CLI script; archive_pass.py keeps aliases under the old names.
# ---------------------------------------------------------------------------

TRAJECTORY_COLS = [
    "Pass", "Date", "HIGHs", "Regressions",
    "Addressed", "Deferred", "Sealed", "Notes",
]

SEAL_ENTRY_RE = re.compile(
    r"^-\s+`\[SEAL-(\d+)\]`\s+\*\*(.+?)\*\*\s+\(pass\s+(\d+),\s+([^)]+)\)\s+—\s+(.+)$"
)

TERMINAL_FILENAMES = frozenset({"PLAN.md", "tasks.md", "tasks-python.md", "tasks-java.md"})
TERMINAL_HTML_MARKER = "<!-- terminal-phase: scope -->"

# Kept equal to artifact_resolution._ARTIFACT_PREFIX_RE (pinned by a test).
_NUMERIC_PREFIX_RE = re.compile(r"^\d{2}_")


def _strip_numeric_prefix(name: str) -> str:
    """Strip a leading two-digit ``NN_`` ordinal prefix (raw, UNIFORM strip).

    Used before the ``TERMINAL_FILENAMES`` membership tests so a prefixed
    ``03_PLAN.md`` / ``03_tasks.md`` (and the defensive ``03_tasks-python.md`` /
    ``03_tasks-java.md``) resolve to the bare registry name. We strip raw rather
    than via ``blueprint_common.strip_artifact_prefix`` because the terminal
    registry includes ``tasks-python.md`` / ``tasks-java.md``, which are NOT in
    ``KNOWN_ARTIFACTS`` — the 4-name frozenset is its own over-match guard.
    """
    return _NUMERIC_PREFIX_RE.sub("", name, count=1)


def is_terminal_artifact(content: str, name: str) -> bool:
    """True when the artifact is terminal-phase by filename or HTML marker.

    archive_pass._is_terminal's rules minus the CLI flag: the (prefix-stripped)
    name is in ``TERMINAL_FILENAMES``, or the content carries
    ``TERMINAL_HTML_MARKER`` (the terminal SCOPE.md backstop).
    """
    if _strip_numeric_prefix(name) in TERMINAL_FILENAMES:
        return True
    return TERMINAL_HTML_MARKER in content


# Split a markdown row on unescaped pipes; a literal `\|` is an escaped cell
# character. Borrowed from compact_table.py's _UNESCAPED_PIPE; deliberately not
# imported from it (that would couple this leaf to a validator module).
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def split_table_row(line):
    """Split one markdown table line into stripped, unescaped cell values.

    Splits on unescaped `|` only, drops one leading and one trailing empty
    boundary fragment, then strips each cell and unescapes `\\|` to `|`.
    Applied identically to the header line and to every data row, so header
    and rows can never disagree on cell count.

    A malformed line yields a wrong-length list; the caller decides what that
    means. Nothing is raised here.
    """
    parts = _UNESCAPED_PIPE.split(line.strip())
    # Drop exactly ONE empty boundary fragment at each end — not every one, as
    # str.strip("|") did. Repeated adjacent boundary pipes therefore survive as
    # empty cells rather than collapsing.
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [c.strip().replace("\\|", "|") for c in parts]


def render_table_row(values, widths):
    cells = [f" {v.ljust(w)} " for v, w in zip(values, widths)]
    return "|" + "|".join(cells) + "|"


def render_table(headers, rows):
    if not rows:
        widths = [len(h) for h in headers]
    else:
        widths = [
            max(len(h), max(len(r.get(h, "")) for r in rows))
            for h in headers
        ]
    out = [
        render_table_row(headers, widths),
        "|" + "|".join("-" * (w + 2) for w in widths) + "|",
    ]
    for r in rows:
        out.append(render_table_row([r.get(h, "") for h in headers], widths))
    return out


# Converged / mode stamps written into Trajectory Notes by archive_pass.py and
# read by the validators (AD2). One definition, so writer and readers can't drift.
STAMP_STRICT_BAR = "strict-bar pass"
STAMP_CROSS_CHECK = "cross-check pass (excluded from cap)"
STAMP_CONVERGED_NO_HIGH = "converged (0 HIGH)"
STAMP_CONVERGED_SEALED = "converged (0 unresolved HIGH)"
CONVERGED_STAMPS = (STAMP_CONVERGED_NO_HIGH, STAMP_CONVERGED_SEALED)
# Fixed whole token appended whenever any Latest row is disposed Halt and re-scope (AD4).
STAMP_HALT_DISPOSITION = "halt-and-rescope disposed"


# ---------------------------------------------------------------------------
# Notes tokeniser and provenance token (Unit C0 AD3/AD4)
# ---------------------------------------------------------------------------

PROVENANCE_PREFIX = "prov="
PROVENANCE_HEX_WIDTH = 16
# fullmatch against the whole last `;`-token, whitespace-trimmed (AD3).
PROVENANCE_TOKEN_RE = re.compile(r"prov=([0-9a-f]{16})")
# Grammar constant only (AD3/AD13): a trailing hand-appended upstream-panel tag
# with its one preceding separator. Never applied with re.search over a whole
# cell — that tries every start position and is quadratic on an interior
# whitespace run. `strip_upstream_tags` implements the same grammar linearly.
UPSTREAM_TAG_STRIP_RE = re.compile(r"(?:;[ \t]*|[ \t]+)upstream-panel [0-9a-f]{8}[ \t]*$")
_UPSTREAM_TAG_TAIL_RE = re.compile(r"upstream-panel [0-9a-f]{8}")
_HALT_VOTE_PREFIX = "halt vote"


def strip_upstream_tags(cell: str) -> str:
    """Strip trailing `upstream-panel <8-hex>` tags, to a fixpoint (AD3, DEF-06).

    Each round removes one tag together with exactly one preceding separator
    (`;` with optional spaces/tabs, or a run of spaces/tabs) — the
    ``UPSTREAM_TAG_STRIP_RE`` grammar, applied from the end of the cell so the
    work is linear. A tag with no separator before it (a bare tag cell) stops
    the loop and is kept. A cell left empty becomes ``—``.
    """
    while True:
        c = cell.rstrip(" \t")
        i = c.rfind("upstream-panel ")
        if i < 0 or not _UPSTREAM_TAG_TAIL_RE.fullmatch(c, i):
            return cell
        head = c[:i]
        trimmed = head.rstrip(" \t")
        if trimmed.endswith(";"):
            new = trimmed[:-1]
        elif len(trimmed) < len(head):
            new = trimmed
        else:
            return cell
        if not new.strip():
            return "—"
        cell = new


def notes_tokens(notes: str) -> "Tuple[str, ...]":
    """Whole-token view of a Notes cell (DM5).

    Trailing upstream-panel tags stripped, then whitespace-trimmed `;`-split
    tokens, cut before the first token starting with 'halt vote' (any case):
    archive_pass writes every stamp before the halt text, so a concern title
    quoted there can never forge a stamp (AD4).
    """
    out = []
    for tok in strip_upstream_tags(notes).split(";"):
        t = tok.strip()
        if t.lower().startswith(_HALT_VOTE_PREFIX):
            break
        if t:
            out.append(t)
    return tuple(out)


def provenance_token(content_hash: str) -> str:
    """Return ``prov=<hash>``. Raises ValueError unless 16 lowercase hex."""
    if not PROVENANCE_TOKEN_RE.fullmatch(PROVENANCE_PREFIX + content_hash):
        raise ValueError(
            f"provenance hash must be {PROVENANCE_HEX_WIDTH} lowercase hex, got {content_hash!r}"
        )
    return PROVENANCE_PREFIX + content_hash


def read_provenance_hash(notes: str) -> Optional[str]:
    """The 16-hex hash of a row's provenance token, or None (AD3).

    After stripping trailing upstream-panel tags to a fixpoint, the whole last
    `;`-token, trimmed, must fullmatch ``PROVENANCE_TOKEN_RE``. A ``prov=``
    anywhere else is never read.
    """
    last = strip_upstream_tags(notes).split(";")[-1].strip()
    m = PROVENANCE_TOKEN_RE.fullmatch(last)
    return m.group(1) if m else None


def stamp_provenance(build: "Callable[[str], str]", hasher: "Callable[[str], str]") -> str:
    """Double render (AD3): render with a same-width placeholder, hash it, then
    re-render with that hash and confirm the second render hashes the same.

    Returns the second render. Raises RuntimeError if the hashes differ (the
    caller exits 1 with no write).
    """
    placeholder = "0" * PROVENANCE_HEX_WIDTH
    first = build(placeholder)
    h = hasher(first)
    second = build(h)
    h2 = hasher(second)
    if h2 != h:
        raise RuntimeError(
            f"provenance stamp is not hash-neutral: placeholder render hashed {h}, "
            f"stamped render hashed {h2}"
        )
    return second


# ---------------------------------------------------------------------------
# Convergence verdict (Unit C0 AD5) — pure; never raises
# ---------------------------------------------------------------------------

_REQUIRED_GATE_COLUMNS = ("Pass", "Addressed", "Deferred", "Notes")
_PANEL_SUBSECTIONS = ("### Trajectory", "### Sealed dispositions", "### Latest pass detail")


@dataclass(frozen=True)
class TrajectoryRow:
    """DM5: one Trajectory data row as the gate reads it."""

    pass_no: Optional[int]
    cells: "Dict[str, str]"
    is_skip: bool
    tokens: "Tuple[str, ...]"
    provenance: Optional[str]
    arity_ok: bool


@dataclass(frozen=True)
class ConvergenceVerdict:
    """DM6. ``failed`` holds AD5 codes (empty = pass); freshness is the
    wrapper's. ``legacy``: the closing row exists but carries no provenance
    token, or a token-less table has a structural fault."""

    closing_pass: Optional[int]
    failed: "Tuple[str, ...]"
    legacy: bool
    legacy_format: bool
    freshness_hash: Optional[str]


def _row_from_cells(header: "List[str]", cells: "List[str]") -> TrajectoryRow:
    arity_ok = len(cells) == len(header)
    d = dict(zip(header, cells))
    pass_cell = d.get("Pass", "")
    pass_no = int(pass_cell) if _is_ascii_int(pass_cell) else None
    notes = d.get("Notes", "")
    is_skip = notes.startswith("skipped")
    if arity_ok and pass_no is not None and not is_skip:
        for col in ("Addressed", "Deferred"):
            if col in d and not _is_ascii_int(d[col]):
                arity_ok = False
    return TrajectoryRow(
        pass_no=pass_no,
        cells=d,
        is_skip=is_skip,
        tokens=notes_tokens(notes),
        provenance=read_provenance_hash(notes),
        arity_ok=arity_ok,
    )


def parse_trajectory_rows(content: str) -> "List[TrajectoryRow]":
    """Rows of the canonical table via ``_trajectory_bounds``; [] when absent.
    Never raises."""
    try:
        bounds = _trajectory_bounds(content)
        if bounds is None:
            return []
        lines = content.split("\n")
        h, first, term, _end = bounds
        header = split_table_row(lines[h])
        return [_row_from_cells(header, split_table_row(ln)) for ln in lines[first:term]]
    except Exception:  # noqa: BLE001 — a reader on hand-edited text never raises
        return []


def select_closing_row(rows: "Sequence[TrajectoryRow]") -> Optional[int]:
    """Index of the last integer-Pass, non-skip row (AC-5.1), or None."""
    for i in range(len(rows) - 1, -1, -1):
        if rows[i].pass_no is not None and not rows[i].is_skip:
            return i
    return None


def _panel_legacy_format(content: str) -> bool:
    lines = content.split("\n")
    try:
        start = next(i for i, ln in enumerate(lines) if re.match(r"^##\s+Panel Review\s*$", ln))
    except StopIteration:
        return False
    end = next((j for j in range(start + 1, len(lines)) if re.match(r"^##\s+", lines[j])), len(lines))
    present = {ln.rstrip() for ln in lines[start + 1:end]}
    return any(h not in present for h in _PANEL_SUBSECTIONS)


def _structural_codes(content: str) -> "Tuple[List[str], bool]":
    """(codes, any_token) from the UNTRIMMED table: missing gate columns and
    malformed rows by 1-based file line (no row text)."""
    bounds = _trajectory_bounds(content)
    if bounds is None:
        return [], False
    lines = content.split("\n")
    h, first, term, _end = bounds
    header = split_table_row(lines[h])
    codes = [f"missing-column:{c}" for c in _REQUIRED_GATE_COLUMNS if c not in header]
    any_token = False
    for idx in range(first, term):
        row = _row_from_cells(header, split_table_row(lines[idx]))
        if row.provenance is not None:
            any_token = True
        if not codes and not row.arity_ok:
            codes.append(f"malformed-row:{idx + 1}")
    if codes and not any_token:
        any_token = any(PROVENANCE_PREFIX in ln for ln in lines[first:term]) and any(
            read_provenance_hash(split_table_row(ln)[-1] if split_table_row(ln) else "")
            for ln in lines[first:term]
        )
    return codes, any_token


def evaluate_convergence(content: str) -> ConvergenceVerdict:
    """AC-5.1–5.7 verdict (AD5). Arity/cell checks on the untrimmed content,
    row selection on ``trim_trajectory_table(content)``. Pure; never raises."""
    legacy_format = _panel_legacy_format(content)
    try:
        codes, any_token = _structural_codes(content)
    except Exception:  # noqa: BLE001
        codes, any_token = ["malformed-row:0"], False
    if codes:
        return ConvergenceVerdict(None, tuple(codes), not any_token, legacy_format, None)

    rows = parse_trajectory_rows(trim_trajectory_table(content))
    idx = select_closing_row(rows)
    if idx is None:
        return ConvergenceVerdict(None, ("no-converged-pass",), False, legacy_format, None)
    r = rows[idx]
    failed: "List[str]" = []
    if not any(t in CONVERGED_STAMPS for t in r.tokens):
        failed.append("no-converged-stamp")
    for col, code in (("Addressed", "addressed"), ("Deferred", "deferred")):
        n = int(r.cells[col])
        if n > 0:
            failed.append(f"{code}={n}")
    prev = next(
        (rows[j] for j in range(idx - 1, -1, -1)
         if rows[j].pass_no is not None and not rows[j].is_skip),
        None,
    )
    prev_strict = prev is not None and STAMP_STRICT_BAR in prev.tokens
    if STAMP_STRICT_BAR in r.tokens:
        failed.append("strict-bar-closing")
    elif STAMP_CROSS_CHECK in r.tokens:
        if not prev_strict:
            failed.append("cross-check-without-strict-bar")
    elif prev_strict:
        failed.append("normal-after-strict-bar")
    if STAMP_HALT_DISPOSITION in r.tokens:
        failed.append("halt-and-rescope")
    legacy = r.provenance is None
    freshness = None
    if not legacy:
        freshness = next(
            (rows[j].provenance for j in range(len(rows) - 1, idx - 1, -1)
             if rows[j].provenance is not None),
            None,
        )
    # Ordering per AD5: (a), (b), (c), (d) codes, strict-bar-closing, (e).
    order = {"no-converged-stamp": 0, "addressed": 1, "deferred": 2,
             "cross-check-without-strict-bar": 3, "normal-after-strict-bar": 3,
             "strict-bar-closing": 4, "halt-and-rescope": 5}
    failed.sort(key=lambda c: order.get(c.split("=")[0], 9))
    return ConvergenceVerdict(r.pass_no, tuple(failed), legacy, legacy_format, freshness)
