"""Shared validator helpers used by `validate_blueprint.py` and `validate_spec.py`.

The module exposes pure functions plus the `Severity` and `ValidationResult`
classes (`validate_panel_review` mutates a `ValidationResult`, so its
container belongs here too). Callers add presentation-layer concerns
(argparse, JSON serialisation, CLI exit codes) on top.
"""

from __future__ import annotations

import hashlib
import re
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------

UNCHECKED_QUESTION_PATTERN = re.compile(r"^-\s*\[ \]\s*Q\d+:", re.MULTILINE)

TBD_PATTERN = re.compile(r"\[TBD[^\]]*\]", re.IGNORECASE)

UNRESOLVED_MARKERS = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b|\?\?\?", re.IGNORECASE)

PANEL_UNRESOLVED_DISPOSITION = re.compile(
    r"\|\s*User input needed\s*\|", re.IGNORECASE
)

PANEL_RESOLVED_DISPOSITION = re.compile(
    r"\|\s*(Addressed|Deferred(?:\s*→[^|]*)?|Sealed|Accepted as risk|Halt and re-scope|—)\s*\|",
    re.IGNORECASE,
)

PANEL_TRAJECTORY_ROW = re.compile(
    r"^\|\s*\d+\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|", re.MULTILINE
)

PANEL_SEAL_ENTRY = re.compile(r"^-\s+`\[SEAL-\d+\]`", re.MULTILINE)

PANEL_LATEST_DETAIL_ROW = re.compile(
    r"^\|\s*\[(?:HIGH|MED|LOW)\]", re.MULTILINE
)


# ---------------------------------------------------------------------------
# ValidationResult / Severity
# ---------------------------------------------------------------------------


class Severity:
    FAIL = "FAIL"
    WARN = "WARN"
    PASS = "PASS"


class ValidationResult:
    def __init__(self) -> None:
        self.checks: list[tuple[str, str, str]] = []

    def add(
        self,
        name: str,
        passed: bool,
        detail: str = "",
        warn_only: bool = False,
    ) -> None:
        if passed:
            self.checks.append((name, Severity.PASS, detail))
        elif warn_only:
            self.checks.append((name, Severity.WARN, detail))
        else:
            self.checks.append((name, Severity.FAIL, detail))

    @property
    def passed(self) -> bool:
        return all(sev != Severity.FAIL for _, sev, _ in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(sev == Severity.WARN for _, sev, _ in self.checks)

    def summary(self) -> str:
        lines = []
        for name, severity, detail in self.checks:
            line = f"  [{severity}] {name}"
            if detail:
                line += f" — {detail}"
            lines.append(line)
        return "\n".join(lines)

    def to_dict(self) -> list[dict]:
        return [
            {"name": name, "status": severity, "detail": detail}
            for name, severity, detail in self.checks
        ]


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------


def has_section(content: str, section_name: str) -> bool:
    """True if content contains the section name as a heading or bold label."""
    heading = re.compile(
        rf"^#+\s+.*{re.escape(section_name)}", re.MULTILINE | re.IGNORECASE
    )
    bold = re.compile(rf"\*\*{re.escape(section_name)}", re.IGNORECASE)
    return bool(heading.search(content) or bold.search(content))


def section_has_content(content: str, section_name: str) -> bool:
    """True if a section exists and has substantive content after the heading."""
    heading = re.compile(
        rf"^(#+)\s+.*{re.escape(section_name)}.*$", re.MULTILINE | re.IGNORECASE
    )
    match = heading.search(content)
    if not match:
        return False

    heading_level = len(match.group(1))
    start = match.end()

    next_heading = re.compile(rf"^#{{{1},{heading_level}}}\s+", re.MULTILINE)
    next_match = next_heading.search(content, start)
    end = next_match.start() if next_match else len(content)

    section_body = content[start:end].strip()
    if not section_body:
        return False

    cleaned = re.sub(r"\[.*?\]", "", section_body).strip()
    if not cleaned:
        return False

    return True


def extract_panel_section(content: str) -> str:
    """Body of '## Panel Review' with HTML comments stripped, or '' if missing."""
    match = re.search(
        r"^##\s+Panel Review\s*\n(.*?)(?=\n^##\s+|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return ""
    body = match.group(1)
    return re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------


def content_for_hashing(content: str) -> str:
    """Document content with dynamic approval values neutralised.

    Substitutes the Approved checkbox state and Content Hash value with fixed
    placeholders so approving a document doesn't change its hash, but any
    other edit does. Idempotent: applying twice yields the same result.
    """
    result = re.sub(
        r"- \[[ x]\] Approved to proceed", "- [ ] Approved to proceed", content
    )
    result = re.sub(
        r"\*\*Content Hash:\*\*\s*`[^`]*`", "**Content Hash:** `pending`", result
    )
    return result.rstrip()


def compute_content_hash(content: str) -> str:
    """SHA-256 (16-hex-char prefix) of content_for_hashing(content)."""
    body = content_for_hashing(content)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def verify_content_hash(content: str, stored_hash: str) -> bool:
    """True iff stored_hash equals the hash recomputed over content."""
    return compute_content_hash(content) == stored_hash


# ---------------------------------------------------------------------------
# Marker scanning
# ---------------------------------------------------------------------------


class UnresolvedMarker(NamedTuple):
    kind: str  # 'tbd' | 'unresolved_general' | 'unchecked_question' | 'user_input_needed'
    text: str


def scan_unresolved_markers(content: str) -> list[UnresolvedMarker]:
    """All unresolved-marker hits in content. Empty list = fully resolved.

    Detects: [TBD]-style brackets, TODO/FIXME/XXX/HACK keywords, ???,
    unchecked open questions (`- [ ] Q<N>:`), and panel rows still in the
    'User input needed' disposition column.
    """
    hits: list[UnresolvedMarker] = []
    for m in TBD_PATTERN.findall(content):
        hits.append(UnresolvedMarker("tbd", m))
    for match in UNRESOLVED_MARKERS.finditer(content):
        hits.append(UnresolvedMarker("unresolved_general", match.group(0)))
    for m in UNCHECKED_QUESTION_PATTERN.findall(content):
        hits.append(UnresolvedMarker("unchecked_question", m))
    for m in PANEL_UNRESOLVED_DISPOSITION.findall(content):
        hits.append(UnresolvedMarker("user_input_needed", m))
    return hits


# ---------------------------------------------------------------------------
# Panel-review check
# ---------------------------------------------------------------------------


def validate_panel_review(
    content: str, filename: str, result: ValidationResult
) -> None:
    """Check that the Panel Review section is present, populated, and clean.

    Two formats accepted:
      * **New format:** three sub-sections —
        `### Trajectory`, `### Sealed dispositions`, `### Latest pass detail`.
      * **Legacy format:** a single `## Panel Review` table.

    Evidence the panel has run is any of: a resolved-disposition row, a
    Trajectory row, or a `[SEAL-NN]` entry. An artifact lacking all three
    fails validation.
    """
    panel_body = extract_panel_section(content)

    has_body = bool(panel_body.strip())
    result.add(
        f"{filename} 'Panel Review' section has content",
        has_body,
        "Panel Review section is empty or contains only placeholder text"
        if not has_body
        else "",
    )
    if not has_body:
        return

    unresolved = PANEL_UNRESOLVED_DISPOSITION.findall(panel_body)
    result.add(
        f"{filename} has no unresolved panel concerns",
        len(unresolved) == 0,
        f"{len(unresolved)} concern(s) still in 'User input needed' disposition"
        if unresolved
        else "",
    )

    is_new_format = "### Trajectory" in panel_body
    if is_new_format:
        has_trajectory = bool(PANEL_TRAJECTORY_ROW.search(panel_body))
        has_seal = bool(PANEL_SEAL_ENTRY.search(panel_body))
        has_latest = bool(PANEL_LATEST_DETAIL_ROW.search(panel_body))
        panel_ran = has_trajectory or has_seal or has_latest
        missing_msg = (
            "No evidence found — panel has not run or its results were not "
            "written. Expected at least one of: a Trajectory row "
            "(numeric Pass + ISO date), a `[SEAL-NN]` entry, or a row in "
            "Latest pass detail with a bracketed severity tag."
        )
    else:
        panel_ran = bool(PANEL_RESOLVED_DISPOSITION.search(panel_body))
        missing_msg = (
            "No resolved dispositions found — panel has not run or results "
            "were not written"
        )
    result.add(
        f"{filename} 'Panel Review' shows the panel has run",
        panel_ran,
        missing_msg if not panel_ran else "",
    )


# ---------------------------------------------------------------------------
# Trajectory-table trim (called from approve_document on both producer and
# consumer validators)
# ---------------------------------------------------------------------------

TRAJECTORY_HEADER = "### Trajectory"
TRAJECTORY_SEP_RE = re.compile(r"^\|[\s\-|:]+\|\s*$")
TRAJECTORY_ELIDED_NOTES_RE = re.compile(r"^(\d+) earlier passes elided$")
TRAJECTORY_KEEP_DEFAULT = 15


def _trajectory_row_notes(row_line: str) -> str:
    """Return the Notes (last) cell of a trajectory row, stripped."""
    inner = row_line.strip().strip("|")
    cells = [c.strip() for c in inner.split("|")]
    return cells[-1] if cells else ""


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

    header_idx = None
    for i, line in enumerate(lines):
        if line.rstrip() == TRAJECTORY_HEADER:
            header_idx = i
            break
    if header_idx is None:
        return content

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
        return content
    if not TRAJECTORY_SEP_RE.match(lines[table_header_idx + 1]):
        return content

    sep_idx = table_header_idx + 1
    data_start = sep_idx + 1
    data_end = data_start
    while data_end < section_end:
        s = lines[data_end].strip()
        if not (s.startswith("|") and s.endswith("|")):
            break
        data_end += 1

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
