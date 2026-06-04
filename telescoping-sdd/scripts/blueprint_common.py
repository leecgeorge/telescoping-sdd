"""Shared validator helpers used by `validate_blueprint.py` and `validate_spec.py`.

The module exposes pure functions plus the `Severity` and `ValidationResult`
classes (`validate_panel_review` mutates a `ValidationResult`, so its
container belongs here too). Callers add presentation-layer concerns
(argparse, JSON serialisation, CLI exit codes) on top.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional

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
        r"- \[[ xX]\] Approved to proceed", "- [ ] Approved to proceed", content
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
    """True iff stored_hash equals the hash recomputed over content.

    Compared case-insensitively: compute_content_hash() emits lower-case hex,
    but a hand-edited stamp may be upper-case, and hash identity must not depend
    on case. This is the single comparison both validators' approval checks
    route through, so they cannot drift on hash interpretation.
    """
    return compute_content_hash(content).lower() == stored_hash.lower()


# ---------------------------------------------------------------------------
# Approval-detection + shipped classification (relocated from validate_blueprint)
# ---------------------------------------------------------------------------
#
# `has_approval`, `approval_hash`, `approval_hash_matches`, `all_tasks_ticked`,
# `read_file`, and the new `is_shipped` predicate were RELOCATED here from
# `validate_blueprint.py` (CPD I9 "shared, not re-implemented") so that
# `reconcile.py` — a shared script that must NOT import a skill validator — can
# derive the SAME `STATE_SHIPPED` verdict the blueprint validator uses.
# `validate_blueprint.classify_spec` imports these back and derives its shipped
# branch from `is_shipped`; the existing `classify_spec` test suite runs
# UNMODIFIED as the regression guard.
#
# These functions need a narrow approval regex — kept DISTINCT from
# this module's broad `APPROVAL_HASH_LINE` (defined far below, capturing
# `([^`]*)` for read_stored_hash's fail-open detection). The narrow form here
# captures `([0-9a-fA-F]+|pending)` exactly as the pre-relocation
# validate_blueprint copy did, so the relocated behavior is byte-identical.
# They are deliberately NOT unified with the broad form (the broad one surfaces
# corruption verbatim; the narrow one is a clean match-or-miss approval gate).
#
# `APPROVAL_HASH_LINE_STRICT` is PUBLIC and is the SINGLE narrow approval-hash
# grammar: both skill validators' `check_approval` import THIS object rather than
# each compiling their own copy, so the three byte-identical narrow patterns can
# no longer drift (tighten one, the others follow). `test_blueprint_common`
# asserts narrow != broad; the validator suites assert they share this object.

# `## Approval` section header.
_APPROVAL_HEADER = re.compile(r"^##\s+Approval\s*$", re.MULTILINE)
# Strict approval-checkbox form: `- [x] Approved to proceed`.
_APPROVAL_CHECKBOX = re.compile(r"- \[[xX]\] Approved to proceed")
# Narrow `**Content Hash:**` line — DISTINCT from the broad `APPROVAL_HASH_LINE`
# below (this one matches only hex-or-'pending'; the broad one captures any
# backtick body so read_stored_hash can fail-open on corruption).
APPROVAL_HASH_LINE_STRICT = re.compile(
    r"^\s*(?:-\s*)?\*\*Content Hash:\*\*\s*`([0-9a-fA-F]+|pending)`", re.MULTILINE
)
# A task-list checkbox line (ticked or unticked) at the start of a line.
_TASK_CHECKBOX_LINE = re.compile(r"^-\s+\[([ xX])\]\s+", re.MULTILINE)


def has_approval(content: str) -> bool:
    """Return True if the content has a `## Approval` section with a checked box."""
    if not _APPROVAL_HEADER.search(content):
        return False
    return bool(_APPROVAL_CHECKBOX.search(content))


def approval_hash(content: str) -> Optional[str]:
    """Return the stamped `**Content Hash:**` value, or None if absent or 'pending'."""
    m = APPROVAL_HASH_LINE_STRICT.search(content)
    if m is None:
        return None
    value = m.group(1)
    return None if value == "pending" else value


def approval_hash_matches(content: str) -> bool:
    """Return True if the stored Content Hash matches the current file content.

    Routes through `verify_content_hash` — the single hash-coherence comparison
    both validators use — so an approved document whose stored hash matches the
    recomputed content hash reads as still-coherent.
    """
    if not has_approval(content):
        return False
    stored = approval_hash(content)
    if stored is None:
        return False
    return verify_content_hash(content, stored)


def all_tasks_ticked(tasks_content: str) -> bool:
    """Return True if tasks.md has at least one task checkbox and every task
    checkbox is ticked.

    A narrative-only tasks.md (zero task checkboxes) returns False — it cannot
    classify as `shipped` because there is no implementation work to make
    immutable (the empty-set vacuous-truth case is rejected).

    Scoping: counts only checkboxes BEFORE the `## Approval` heading. The
    `## Approval` section's own `- [x] Approved ...` checkbox is the approval
    marker, not a task, and must not contribute.
    """
    approval_match = _APPROVAL_HEADER.search(tasks_content)
    scan_region = (
        tasks_content[: approval_match.start()] if approval_match else tasks_content
    )
    boxes = list(_TASK_CHECKBOX_LINE.finditer(scan_region))
    if not boxes:
        return False
    return all(b.group(1).lower() == "x" for b in boxes)


def read_file(path: Path) -> Optional[str]:
    """Read file contents (UTF-8) or return None if the path is not a file."""
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return None


def is_shipped_from_contents(
    spec_content: Optional[str],
    design_content: Optional[str],
    tasks_content: Optional[str],
) -> bool:
    """Content-core of `is_shipped`: the full STATE_SHIPPED condition.

    True IFF spec.md is approved (checkbox + matching hash) AND design.md is
    approved AND tasks.md is approved AND every task checkbox in tasks.md is
    ticked. A missing artifact (None) fails the corresponding clause. This is
    the exact three-artifact gate `validate_blueprint.classify_spec` reaches
    `STATE_SHIPPED` through — kept as a pure-string core so callers that
    already hold the file contents (e.g. reconcile, or the validator's own
    classify_spec which reads them once) do not re-read from disk.
    """
    if spec_content is None or not approval_hash_matches(spec_content):
        return False
    if design_content is None or not approval_hash_matches(design_content):
        return False
    if tasks_content is None or not approval_hash_matches(tasks_content):
        return False
    return all_tasks_ticked(tasks_content)


def is_shipped(spec_dir: Path) -> bool:
    """Return True IFF the feature at `spec_dir` has SHIPPED.

    Path wrapper over `is_shipped_from_contents`: reads spec.md / design.md /
    tasks.md from `spec_dir` and applies the full STATE_SHIPPED condition.
    Shared so `reconcile.py` and `validate_blueprint.classify_spec` derive the
    SAME shipped verdict from ONE definition (no drift).
    """
    return is_shipped_from_contents(
        read_file(spec_dir / "spec.md"),
        read_file(spec_dir / "design.md"),
        read_file(spec_dir / "tasks.md"),
    )


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


# ---------------------------------------------------------------------------
# Pending-review marker (R1 reminder + R2 marker) — shared by both validators.
#
# NOTE: this section adds filesystem I/O (json read/write, os.replace) to a
# module that was otherwise pure. The helpers are grouped here so both
# validators import ONE canonical implementation (AD1); a future extraction to
# a dedicated pending_review.py is a clean mechanical refactor.
# ---------------------------------------------------------------------------

# Promoted from the validators (was per-file, hex-only). The capture is
# BROADENED to `([^`]*)` so read_stored_hash surfaces a present-but-malformed
# value verbatim instead of collapsing it to 'pending' (a hex-only capture
# would hide corruption -> fail-open). [T1; design C1/read_stored_hash]
APPROVAL_HASH_LINE = re.compile(
    r"^\s*(?:-\s*)?\*\*Content Hash:\*\*\s*`([^`]*)`", re.MULTILINE
)

MARKER_RELPATH = Path(".sdd") / "pending-review.json"
MARKER_SCHEMA_VERSION = 1

# Tag the agent stamps into a Trajectory Notes cell after the upstream panel
# (hash-and-cascade.md step 3e); the R2 clear matches it.
UPSTREAM_PANEL_TAG_RE = re.compile(r"upstream-panel ([0-9a-f]{8})")

# The loud reminder printed AFTER the `Approved:` line on a changed-document
# re-stamp (R1). Contains the four spec-mandated verbatim strings.
REAPPROVAL_REMINDER = (
    "!" * 70 + "\n"
    "RE-APPROVAL REMINDER\n"
    "Step 3 (upstream panel re-review) is REQUIRED before cascade unless the diff is visibly trivial.\n"
    "Conservative default: lean=yes unless the diff is visibly trivial.\n"
    "Classify the edit source per hash-and-cascade.md AD1 (claude-edit + non-trivial -> lean-yes).\n"
    + "!" * 70
)


class MarkerCorruptError(Exception):
    """Raised when .sdd/pending-review.json exists but is unparseable.

    Distinguishes a corrupt enforcement marker (a fail-closed error) from an
    absent one (a legitimately-empty state). [AD11]
    """


def now_iso_utc() -> str:
    """Current UTC time as an ISO-8601 string (shared so both validators agree)."""
    return datetime.now(timezone.utc).isoformat()


# ----- changed-since-stamp detection (R1) ---------------------------------


def read_stored_hash(content: str) -> str:
    """Value in the document's `**Content Hash:**` line, or 'pending'. [T1]

    Captures the backtick content broadly so a present-but-malformed value is
    returned VERBATIM (not collapsed to 'pending') — that lets
    changed_since_stamp fail closed on corruption. Returns 'pending' only when
    the line is absent or literally holds 'pending'.
    """
    m = APPROVAL_HASH_LINE.search(content)
    if not m:
        return "pending"
    return m.group(1).strip()


def _is_valid_16_hex(value: str) -> bool:
    return len(value) == 16 and all(c in "0123456789abcdef" for c in value.lower())


def _approval_checkbox_checked(content: str) -> bool:
    return bool(re.search(r"-\s*\[[xX]\]\s*Approved to proceed", content))


def changed_since_stamp(new_content_hash: str, stored_hash: str, content: str) -> bool:
    """True when a previously-approved document's content has changed. [T1; I1]

    Compares the ALREADY-COMPUTED new_content_hash (the value approve_document
    is about to write — post-CFC-refresh for PLAN.md) against stored_hash; does
    NOT re-derive the hash (avoids the PLAN.md CFC divergence). Previously-
    approved = stored_hash present and not 'pending' AND checkbox [x].
    Fail-closed: a present stored_hash that is not a valid 16-hex value (non-hex
    garbage, wrong length, OR empty backticks) is treated as approved-but-
    unverifiable -> True. The 16-hex check is case-insensitive. Only a literal
    'pending' (read_stored_hash's value for an absent/`pending` line) is a
    genuine first-approval and short-circuits to False.
    """
    if stored_hash == "pending":
        return False
    if not _approval_checkbox_checked(content):
        return False
    if not _is_valid_16_hex(stored_hash):
        # Present on an approved doc but not a valid 16-hex value (incl. empty
        # backticks `` -> "") -> fail closed: fire the marker.
        return True
    return new_content_hash.lower() != stored_hash.lower()


# ----- Trajectory Pass parsing (R2 stamped_at_pass) -----------------------


def _trajectory_data_rows(content: str) -> list[str]:
    """Data-row lines of the `### Trajectory` table (incl. any elided row), or []."""
    lines = content.split("\n")
    header_idx = None
    for i, line in enumerate(lines):
        if line.rstrip() == TRAJECTORY_HEADER:
            header_idx = i
            break
    if header_idx is None:
        return []
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
        return []
    if not TRAJECTORY_SEP_RE.match(lines[table_header_idx + 1]):
        return []
    rows = []
    for j in range(table_header_idx + 2, section_end):
        s = lines[j].strip()
        if not (s.startswith("|") and s.endswith("|")):
            break
        rows.append(lines[j])
    return rows


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


# ----- marker file I/O (R2) -----------------------------------------------


def _marker_path(project_root: Path) -> Path:
    return Path(project_root) / MARKER_RELPATH


def _empty_marker() -> dict:
    return {"schemaVersion": MARKER_SCHEMA_VERSION, "pending": {}}


def read_pending_review(project_root: Path, *, strict: bool = False) -> dict:
    """Read .sdd/pending-review.json. [T1; I3; AD11]

    ABSENT -> empty-pending dict (both modes). PRESENT-but-unparseable (bad
    JSON / missing 'pending' / wrong type): strict=False -> empty-pending;
    strict=True -> raise MarkerCorruptError (fail-closed; every ENFORCEMENT
    caller — the validate FAIL check, upsert, clear, reconcile — passes
    strict=True).
    """
    path = _marker_path(project_root)
    if not path.exists():
        return _empty_marker()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        if strict:
            raise MarkerCorruptError(f"{path} is present but unreadable/unparseable")
        return _empty_marker()
    if not isinstance(data, dict) or not isinstance(data.get("pending"), dict):
        if strict:
            raise MarkerCorruptError(f"{path} has an invalid schema")
        return _empty_marker()
    # An UNKNOWN schemaVersion (a future v2 marker with a different entry shape)
    # must not be read as v1 with .get() defaults — fail closed under strict so
    # an old validator never silently mis-handles a newer marker. (Absent
    # version is back-compat: treat as v1.)
    ver = data.get("schemaVersion", MARKER_SCHEMA_VERSION)
    if ver != MARKER_SCHEMA_VERSION:
        if strict:
            raise MarkerCorruptError(
                f"{path} has unknown schemaVersion {ver!r} (this tool writes "
                f"v{MARKER_SCHEMA_VERSION})"
            )
        return _empty_marker()
    data["schemaVersion"] = MARKER_SCHEMA_VERSION
    return data


def write_pending_review(project_root: Path, data: dict) -> None:
    """Atomically write .sdd/pending-review.json via mkstemp + os.replace. [T1; I4]

    Uses a UNIQUE temp name (suffix '.tmp'), NOT a fixed `<file>.tmp`, because
    the marker is shared and may be written concurrently. Creates .sdd/ if
    absent.
    """
    path = _marker_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def upsert_pending_entry(
    project_root: Path,
    doc_path_rel: str,
    hash_val: str,
    stamped_at: str,
    stamped_at_pass: int,
) -> None:
    """Add/replace one pending entry without disturbing others. [T1; I5]

    Reads strict=True so a corrupt SHARED marker is never clobbered (refusing to
    reset other features' obligations to {}).
    """
    data = read_pending_review(project_root, strict=True)
    data["pending"][doc_path_rel] = {
        "hash": hash_val,
        "stamped_at": stamped_at,
        "stamped_at_pass": stamped_at_pass,
    }
    write_pending_review(project_root, data)


def clear_pending_entries_for_prefix(project_root: Path, prefix: str) -> list[str]:
    """Remove pending entries whose key == prefix or starts with prefix + '/'. [T1; I6]

    Pure string prefix-matching (no path resolution — needs no AD12 guard).
    `startswith(prefix + '/')` avoids prefix-bleed (feat-a vs feat-a-extra).
    Returns removed keys; deletes the marker file when `pending` becomes empty.
    Reads strict=True (refuse to clobber a corrupt marker).
    """
    data = read_pending_review(project_root, strict=True)
    pending = data["pending"]
    removed = [k for k in list(pending) if _prefix_in_scope(k, prefix)]
    for k in removed:
        del pending[k]
    if not pending:
        path = _marker_path(project_root)
        if path.exists():
            path.unlink()
    elif removed:
        write_pending_review(project_root, data)
    return removed


# ----- reconcile: clear satisfied entries, return still-pending (R2 clear) --


def _key_is_contained(project_root: Path, key: str) -> bool:
    """True iff `key` resolves to a path inside project_root (AD12 guard)."""
    if os.path.isabs(key) or ".." in Path(key).parts:
        return False
    root = Path(project_root).resolve()
    try:
        candidate = (root / key).resolve()
    except OSError:
        return False
    try:
        return os.path.commonpath([str(root), str(candidate)]) == str(root)
    except ValueError:
        return False


def _prefix_in_scope(key: str, prefix: str) -> bool:
    """True iff `key` falls under `prefix`. An empty or '.' prefix — the scoped
    dir IS the project root, so its relpath is '.' — matches ALL keys (otherwise
    a marker written with a bare key like 'PLAN.md' would never match '.' and the
    gate would silently pass). Otherwise exact match or `prefix + '/'` startswith
    (the latter avoids prefix-bleed: feat-a vs feat-a-extra)."""
    if prefix in ("", "."):
        return True
    return key == prefix or key.startswith(prefix + "/")


def _doc_has_qualifying_tag(content: str, hash_short: str, stamped_at_pass: int) -> bool:
    """True iff Trajectory has `upstream-panel <hash_short>` on a Pass > stamped_at_pass."""
    for row in _trajectory_data_rows(content):
        first = _row_first_cell(row)
        if not _is_ascii_int(first) or int(first) <= stamped_at_pass:
            continue
        notes = _trajectory_row_notes(row)
        if any(m.group(1) == hash_short for m in UPSTREAM_PANEL_TAG_RE.finditer(notes)):
            return True
    return False


def reconcile_pending_review(
    project_root: Path, path_prefix: str
) -> list[tuple[str, str]]:
    """Clear satisfied pending entries; return still-pending (doc, expected_tag). [T3; I7]

    For each entry whose key == path_prefix or starts with path_prefix + '/',
    applies the AD12 containment guard, reads the doc's Trajectory, and clears
    the entry when a qualifying `upstream-panel <hash-short>` tag appears on a
    Pass > stamped_at_pass. Reads strict=True (corrupt marker ->
    MarkerCorruptError; the caller converts it to a FAIL). A hostile key
    (absolute / '..' / escapes root) is skipped with a WARN and kept pending; a
    missing/unreadable target doc is also kept pending (both fail-closed).
    The read-modify-write is not globally atomic; last-writer-wins is fine
    because a cleared entry is idempotently re-derivable from the Trajectory.
    """
    data = read_pending_review(project_root, strict=True)
    pending = data["pending"]
    root = Path(project_root)
    still_pending: list[tuple[str, str]] = []
    changed = False
    for key in list(pending):
        if not _prefix_in_scope(key, path_prefix):
            continue
        entry = pending[key]
        hash_short = str(entry.get("hash", ""))[:8]
        anchor = entry.get("stamped_at_pass", 0)
        if not isinstance(anchor, int):
            anchor = 0
        expected_tag = f"upstream-panel {hash_short}"
        if not _key_is_contained(root, key):
            print(
                f"WARNING: pending-review marker key {key!r} escapes the project "
                f"root; skipping (not read).",
                file=sys.stderr,
            )
            still_pending.append((key, expected_tag))
            continue
        try:
            doc_content = (root / key).read_text(encoding="utf-8")
        except OSError:
            still_pending.append((key, expected_tag))
            continue
        if _doc_has_qualifying_tag(doc_content, hash_short, anchor):
            del pending[key]
            changed = True
        else:
            still_pending.append((key, expected_tag))
    if changed:
        if not pending:
            mpath = _marker_path(root)
            if mpath.exists():
                mpath.unlink()
        else:
            write_pending_review(root, data)
    return still_pending


def reconcile_to_result(
    project_root: Path, path_prefix: str, *, decline_cmd: str
) -> ValidationResult:
    """Reconcile pending obligations under `path_prefix` and fold the outcome
    into a `ValidationResult` (one `pending-review` FAIL per still-pending doc).

    Shared by both validators so the FAIL prose cannot drift. `decline_cmd` is
    the validator-specific command shown in the FAIL detail. A corrupt marker
    yields a single fail-closed FAIL (AD11) rather than an unhandled crash.
    """
    result = ValidationResult()
    try:
        still_pending = reconcile_pending_review(project_root, path_prefix)
    except MarkerCorruptError as exc:
        result.add(
            "pending-review",
            False,
            f"`.sdd/pending-review.json` is unreadable/corrupt ({exc}). Cannot "
            f"verify upstream-panel obligations — inspect it, or clear with "
            f"`{decline_cmd}`.",
        )
        return result
    for doc_rel, expected_tag in still_pending:
        result.add(
            "pending-review",
            False,
            f"upstream panel re-review pending for {doc_rel}. Expected Trajectory "
            f"Notes tag: `{expected_tag}`. Resolve by running the panel and "
            f"stamping that tag per hash-and-cascade.md step 3e (after "
            f"`archive_pass.py {doc_rel} --phase <N>`), OR decline: `{decline_cmd}`.",
        )
    return result
