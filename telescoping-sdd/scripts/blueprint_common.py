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

# arch_config is a leaf module (no blueprint_common dependency), so this import
# is one-directional. Used by the shared _resolve_marker_root_and_key (R2.1).
from arch_config import find_project_root as arch_find_project_root

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
    """True if content contains the section name as a heading or bold label.

    The heading match anchors the name to the START of the heading text (after
    the `#`s), with a trailing word boundary. The prior `^#+\\s+.*<name>` allowed
    the name anywhere in the heading, so a required `Goals` section was satisfied
    by an unrelated `## Non-Goals` heading (audit R2.4). The bold fallback already
    anchors the `**` immediately before the name, so `**Non-Goals**` does not
    satisfy `Goals`.
    """
    heading = re.compile(
        rf"^#+\s+{re.escape(section_name)}\b", re.MULTILINE | re.IGNORECASE
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


# --- Hash-basis version annotation (R4 / AD2) ------------------------------
#
# The hash-computation basis changed from v1 (### Trajectory rows INCLUDED in
# the hash) to v2 (### Trajectory rows EXCLUDED). The basis is recorded as a
# `- **Hash basis:** v2` bullet inside each newly-approved artifact's
# `## Approval` section; an ABSENT line is the v1 sentinel (existing artifacts).
HASH_BASIS_CURRENT = "v2"

# Bullet-tolerant basis-line regex. Matches `- **Hash basis:** vN` (written
# form) and bare `**Hash basis:** vN`. DUAL-USE: (1) document-wide in
# content_for_hashing() to neutralize any basis-line occurrence so it never
# affects the hash, AND (2) scoped within the ## Approval slice in
# read_hash_basis() / the basis-line upsert. A future maintainer must NOT anchor
# or tighten this pattern for the read path without preserving the document-wide
# neutralize semantics — else stray body-prose basis-line text becomes
# hash-non-invariant and reintroduces churn.
HASH_BASIS_LINE = re.compile(
    r"^[ \t]*(?:-\s*)?\*\*Hash basis:\*\*\s*(v\d+)\s*$", re.MULTILINE
)
# Removal variant used ONLY by content_for_hashing(): consumes the whole basis
# line INCLUDING its trailing newline so that an artifact WITH a basis line
# hashes identically to one WITHOUT (presence-invariance, not just value-
# invariance). A bare value-substitution would leave "present" != "absent" and
# break post-migration hash coherence (the migration hash is computed before the
# v2 line is stamped). Shares the same line core as HASH_BASIS_LINE.
_HASH_BASIS_REMOVAL_RE = re.compile(
    r"^[ \t]*(?:-\s*)?\*\*Hash basis:\*\*[ \t]*v\d+[ \t]*\r?\n?", re.MULTILINE
)


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


def content_for_hashing(content: str) -> str:
    """Document content with dynamic approval values + Trajectory rows neutralised.

    Applies, in order (v2 basis):
      1. Substitute the Approved checkbox state with a fixed placeholder.
      2. Substitute the Content Hash value with 'pending'.
      3. Remove any `- **Hash basis:** vN` line (bullet-tolerant, document-wide,
         including its trailing newline) so the basis annotation's PRESENCE and
         value never affect the hash — an artifact with the line hashes
         identically to one without (post-migration coherence: the migration hash
         is computed before the v2 line is stamped).
      4. Strip ### Trajectory data rows (panel bookkeeping is not contract
         content) so recording a panel pass does not move the hash.

    So approving a document, recording a converged panel pass, or stamping the
    basis line doesn't change its hash, but any substantive edit does.
    Idempotent: applying twice yields the same result.
    """
    result = re.sub(
        r"- \[[ xX]\] Approved to proceed", "- [ ] Approved to proceed", content
    )
    result = re.sub(
        r"\*\*Content Hash:\*\*\s*`[^`]*`", "**Content Hash:** `pending`", result
    )
    result = _HASH_BASIS_REMOVAL_RE.sub("", result)
    result = _strip_trajectory_rows(result)
    return result.rstrip()


def _content_for_hashing_v1_frozen(content: str) -> str:
    """FROZEN copy of v1 normalization: checkbox + Content-Hash substitution only.

    This is the verbatim pre-fix `content_for_hashing` body. It does NOT strip
    ### Trajectory rows and does NOT neutralize the basis line. MUST NOT delegate
    to content_for_hashing() or any shared v2 helper — it is isolated so a future
    v2 regex change cannot silently change v1 semantics. Used by
    compute_content_hash_v1() (production, via is_basis_migration_only) and the
    golden-string regression test (RISK-2).
    """
    result = re.sub(
        r"- \[[ xX]\] Approved to proceed", "- [ ] Approved to proceed", content
    )
    result = re.sub(
        r"\*\*Content Hash:\*\*\s*`[^`]*`", "**Content Hash:** `pending`", result
    )
    return result.rstrip()


def compute_content_hash_v1(content: str) -> str:
    """Compute the content hash using the FROZEN v1 normalization.

    Used by is_basis_migration_only() to confirm no concurrent substantive edit:
    if compute_content_hash_v1(content_trimmed) == stored_hash, the only changes
    since the v1 approval are Trajectory rows (trimmed/now-excluded) and the basis
    annotation — i.e., a pure basis migration.
    """
    return hashlib.sha256(
        _content_for_hashing_v1_frozen(content).encode("utf-8")
    ).hexdigest()[:16]


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

    STRICT v2: this returns False for a v1-stamped artifact, which is what the
    validators' `check_approval` wants (it surfaces the HASH-BASIS-MIGRATION FAIL
    to nudge re-approval). Read/classify paths that must treat a still-coherent
    v1 artifact as approved (is_shipped, classify_spec, render_business_brief)
    use `verify_content_hash_any_basis` instead.
    """
    return compute_content_hash(content).lower() == stored_hash.lower()


def verify_content_hash_any_basis(content: str, stored_hash: str) -> bool:
    """True iff stored_hash is coherent under the current (v2) basis OR the legacy
    v1 basis (an un-migrated but content-coherent artifact).

    The v2 hash-basis change (### Trajectory + the Hash-basis line excluded) means
    a v1-stamped artifact's stored hash no longer matches `verify_content_hash`.
    The VALIDATOR deliberately FAILs such an artifact (migration nudge), but
    READ/CLASSIFY paths must not: a feature shipped/approved under v1 is still
    shipped/approved — the basis change is tooling-internal, not a content edit.
    Those paths route here so a v1-coherent artifact still reads as approved until
    the operator migrates it. Falls back to the frozen v1 hash (computed over the
    post-trim content, exactly as the old code stamped it) only when the stored
    stamp is on the v1 basis (no `- **Hash basis:** v2` line).
    """
    if verify_content_hash(content, stored_hash):
        return True
    if read_hash_basis(content) == "v1":
        return compute_content_hash_v1(trim_trajectory_table(content)).lower() == stored_hash.lower()
    return False


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


def approval_section_bounds(content: str) -> "Optional[tuple[int, int]]":
    """Return (body_start, body_end) for the first `## Approval` section, or None.

    The SINGLE authoritative bounds helper for ALL approval-section operations
    (basis-line read/write, checkbox + Content-Hash rewrites). Uses the
    line-anchored `_APPROVAL_HEADER` regex, so a body-prose `## Approval`
    substring not at a line boundary is never matched. `body_start` is the
    character offset immediately after the header line; `body_end` is the start
    of the next `## ` heading (or EOF). First match only; a stderr WARN is
    printed when more than one `## Approval` header exists (same policy as
    blueprint's `_approval_section_slice`, which now delegates here). Returns
    None when no `## Approval` header is present.
    """
    matches = list(_APPROVAL_HEADER.finditer(content))
    if not matches:
        return None
    if len(matches) > 1:
        print(
            f"WARN: document contains {len(matches)} `## Approval` headers; "
            "approval state operations target the first match only — "
            "the others will silently orphan state.",
            file=sys.stderr,
        )
    m = matches[0]
    body_start = m.end()
    next_h2 = re.search(r"^## ", content[body_start:], re.MULTILINE)
    body_end = body_start + next_h2.start() if next_h2 else len(content)
    return (body_start, body_end)


def read_hash_basis(content: str) -> str:
    """Return the hash-basis version from the `## Approval` section, or 'v1'.

    Scoped via `approval_section_bounds` — searches ONLY within the `## Approval`
    body using `HASH_BASIS_LINE`, so a body-prose basis-line example elsewhere in
    the document is not matched. Returns 'v1' (the migration sentinel for
    existing artifacts) when the section is absent or the line is missing. Never
    raises. First match wins within the section.
    """
    bounds = approval_section_bounds(content)
    if bounds is None:
        return "v1"
    body_start, body_end = bounds
    m = HASH_BASIS_LINE.search(content[body_start:body_end])
    return m.group(1) if m else "v1"


def _upsert_basis_line(approval_body: str) -> str:
    """Ensure exactly ONE `- **Hash basis:** v2` bullet in a ## Approval body. [AD9]

    Two-branch update-or-insert, idempotent:
      1. If a basis line already matches (HASH_BASIS_LINE), substitute it in place
         (update) — re-approving a v2 artifact yields exactly one bullet, no
         duplication (RISK-8).
      2. Else insert a new bullet immediately after the Content Hash line.

    Leaves the body unchanged when there is no Content Hash line to anchor an
    insert on. Operates on the ## Approval SLICE only (callers pass the slice from
    `approval_section_bounds`), so no document-wide write.
    """
    new_line = f"- **Hash basis:** {HASH_BASIS_CURRENT}"
    if HASH_BASIS_LINE.search(approval_body):
        return HASH_BASIS_LINE.sub(new_line, approval_body, count=1)
    m = APPROVAL_HASH_LINE.search(approval_body)
    if m is None:
        return approval_body
    end = m.end()
    return approval_body[:end] + "\n" + new_line + approval_body[end:]


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

    Routes through `verify_content_hash_any_basis` so an artifact approved under
    the legacy v1 basis (still content-coherent, not yet migrated) reads as
    coherent here — this backs `is_shipped` and `classify_spec`, which must not
    silently de-classify a genuinely shipped/approved feature merely because the
    hash basis changed. The validators' `check_approval` keeps the STRICT v2
    `verify_content_hash` so it still surfaces the HASH-BASIS-MIGRATION FAIL.
    """
    if not has_approval(content):
        return False
    stored = approval_hash(content)
    if stored is None:
        return False
    return verify_content_hash_any_basis(content, stored)


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
    """Read file contents (UTF-8, BOM-tolerant) or return None if not a file.

    Uses utf-8-sig so a leading byte-order mark (common from Windows editors) is
    stripped rather than surviving as U+FEFF. The hash producer and consumer must
    read identical text — render_business_brief already strips the BOM, so a plain
    'utf-8' read here would wedge a BOM'd artifact permanently at 'stale hash'
    (audit R2.5). Safe for non-BOM files (utf-8-sig only strips a BOM if present).
    """
    if path.is_file():
        return path.read_text(encoding="utf-8-sig")
    return None


# ---------------------------------------------------------------------------
# Shared validator helpers (audit R2.1)
#
# check_approval, _resolve_marker_root_and_key, and check_previous_phase_approved
# were near-byte-identical copies in both validate_blueprint.py and
# validate_spec.py — the "duplicate logic" drift channel the audit flagged. They
# live here now, imported by both; check_previous_phase_approved takes the
# per-skill phase ordering as a parameter (the sole real difference).
# ---------------------------------------------------------------------------


def check_approval(content: str, filename: str, result: "ValidationResult") -> bool:
    """Check if a document is approved and the approval is still valid.

    Returns True if the document is approved and its stored hash matches.
    """
    if not _APPROVAL_HEADER.search(content):
        result.add(f"{filename} has Approval section", False, "Missing ## Approval section")
        return False

    result.add(f"{filename} has Approval section", True)

    is_approved = bool(_APPROVAL_CHECKBOX.search(content))
    result.add(f"{filename} is approved", is_approved)

    if not is_approved:
        return False

    hash_match = APPROVAL_HASH_LINE_STRICT.search(content)
    if not hash_match:
        result.add(f"{filename} approval hash present", False, "No content hash found")
        return False

    stored_hash = hash_match.group(1)
    hashes_match = stored_hash != "pending" and verify_content_hash(content, stored_hash)
    if (
        not hashes_match
        and stored_hash != "pending"
        and read_hash_basis(content) == "v1"
        and is_basis_migration_only(
            original_content=content,
            stored_hash=stored_hash,
            content_trimmed=trim_trajectory_table(content),
        )
    ):
        # R4: a v1-basis artifact whose ONLY change is the basis (no substantive
        # edit) is a MIGRATION — emit the distinguishable HASH-BASIS-MIGRATION FAIL.
        # A genuine edit to a v1 artifact falls through to the normal stale FAIL
        # below (its --approve WILL create a marker, so the migration message —
        # which promises none — must not fire for it).
        result.add(f"{filename} hash basis is current", False, HASH_BASIS_MIGRATION_MSG)
        return False
    result.add(
        f"{filename} has not been modified since approval",
        hashes_match,
        f"Stored: {stored_hash}, Current: {compute_content_hash(content)}"
        if not hashes_match
        else "",
    )
    return hashes_match


def _resolve_marker_root_and_key(
    path: Path, project_root: Optional[Path]
) -> "tuple[Path, str]":
    """Resolve the `.sdd/` marker root and `path`'s project-root-relative key.

    Uses `project_root` when given, else walks up from `path` via
    `arch_find_project_root`. Write-side containment guard: if `path` is NOT
    under the resolved root (a misconfigured `--project-root` that isn't an
    ancestor would otherwise yield a `../…` key that reconcile permanently
    rejects -> stuck-pending deadlock), fall back to walking up from `path`
    (guaranteed an ancestor) and WARN.
    """
    start = path if path.is_dir() else path.parent
    root = (
        project_root if project_root is not None else arch_find_project_root(start)
    )
    rel = Path(os.path.relpath(path.resolve(), Path(root).resolve())).as_posix()
    if rel.startswith("..") or os.path.isabs(rel):
        print(
            f"WARNING: project root {root} is not an ancestor of {path}; "
            f"resolving the .sdd/ marker root by walking up from the document "
            f"instead (ignoring the supplied root for the marker).",
            file=sys.stderr,
        )
        root = arch_find_project_root(start)
        rel = Path(os.path.relpath(path.resolve(), Path(root).resolve())).as_posix()
    return Path(root), rel


def check_previous_phase_approved(
    target_dir: Path,
    current_phase: str,
    result: "ValidationResult",
    phase_order: dict,
) -> None:
    """Verify the previous phase's document is approved before this phase.

    `phase_order` maps each phase to its predecessor's artifact filename (e.g.
    `{"design": "spec.md", "tasks": "design.md"}` for SDD, or
    `{"architecture": "SCOPE.md", "plan": "ARCHITECTURE.md"}` for blueprint) —
    the sole per-skill difference, so it is a parameter rather than a fork.
    """
    prev_file = phase_order.get(current_phase)
    if prev_file is None:
        return  # first phase has no predecessor

    prev_path = resolve_artifact(target_dir, prev_file)
    prev_content = read_file(prev_path)
    if prev_content is None:
        result.add(f"Previous phase ({prev_file}) exists", False)
        return

    approved = check_approval(prev_content, f"previous phase ({prev_file})", result)
    if not approved:
        result.add(
            f"Previous phase ({prev_file}) approved before this phase",
            False,
            f"{prev_file} must be approved before proceeding",
        )


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
        read_file(resolve_artifact(spec_dir, "spec.md")),
        read_file(resolve_artifact(spec_dir, "design.md")),
        read_file(resolve_artifact(spec_dir, "tasks.md")),
    )


# ---------------------------------------------------------------------------
# Artifact-name resolution (NN_ ordinal prefix tolerance)
# ---------------------------------------------------------------------------
#
# The methodology may emit artifacts with a two-digit ordinal prefix
# (01_spec.md, 02_design.md, 03_tasks.md, 01_SCOPE.md, ...) so a directory
# listing sorts in phase order. Resolution is additive: both the bare and the
# prefixed form resolve to the same artifact. These helpers are the single
# authoritative chokepoint so every caller shares one regex and one ambiguity
# rule (see specs/artifact-ordering-prefix/design.md).

KNOWN_ARTIFACTS: frozenset = frozenset(
    {"spec.md", "design.md", "tasks.md", "SCOPE.md", "ARCHITECTURE.md", "PLAN.md"}
)

_ARTIFACT_PREFIX_RE = re.compile(r"^\d{2}_")
# The filesystem-glob spelling of the same `NN_` ordinal grammar, used wherever
# we probe for a prefixed form. Shared (here + imported by artifact_prefix.py) so
# the regex and the glob can never drift apart.
_PREFIX_GLOB = "[0-9][0-9]_"


class ArtifactAmbiguityError(Exception):
    """Raised by `resolve_artifact` when two or more forms of the same artifact
    coexist (bare + prefixed, or multiple distinct prefixed forms). Carries
    structured fields so callers can tailor handling; the message is identical
    across callers (only their exit/disposition behaviour varies)."""

    def __init__(self, bare_name, conflicting_paths, identical_content):
        self.bare_name = bare_name
        self.conflicting_paths = list(conflicting_paths)
        self.identical_content = bool(identical_content)
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        listing = "\n".join(f"  {p}" for p in self.conflicting_paths)
        if self.identical_content:
            prefixed = next(
                (p.name for p in self.conflicting_paths
                 if _ARTIFACT_PREFIX_RE.match(p.name)),
                None,
            )
            keep = (f" (keeping the prefixed form '{prefixed}' gives sortable names)"
                    if prefixed else "")
            return (
                f"Ambiguous artifact '{self.bare_name}': multiple forms found with "
                f"identical content:\n{listing}\nBoth files are byte-identical; you "
                f"may safely remove either one{keep}."
            )
        return (
            f"Ambiguous artifact '{self.bare_name}': multiple forms found:\n{listing}\n"
            f"Remove one to continue. To fix: delete the file you do not want to keep, "
            f"then re-run."
        )


def strip_artifact_prefix(name: str) -> str:
    """Strip a leading two-digit `NN_` prefix from `name`, but ONLY when the
    stripped result is a known artifact basename. A non-artifact name (e.g. a
    user's `12_factor_notes.md`) is returned unchanged — no over-match. Pure
    function, no I/O."""
    stripped = _ARTIFACT_PREFIX_RE.sub("", name, count=1)
    if stripped != name and stripped in KNOWN_ARTIFACTS:
        return stripped
    return name


def _all_identical_content(paths) -> bool:
    """Best-effort byte-equality across paths. False on ANY read error
    (permission / missing / etc.) — a raw OSError must never escape."""
    blobs = []
    for p in paths:
        try:
            blobs.append(p.read_bytes())
        except OSError:
            return False
    return len(set(blobs)) <= 1


def resolve_artifact(directory: Path, bare_name: str) -> Path:
    """Resolve an artifact by bare name, tolerating an optional `NN_` prefix.

    Probe: bare first, then a `[0-9][0-9]_<bare_name>` glob. Returns the unique
    form found; if NEITHER exists, returns `directory / bare_name` unchanged
    (NO raise — soft-absence is preserved for callers using
    `read_file(...) -> None` / `.is_file() -> False`). Raises
    `ArtifactAmbiguityError` ONLY when both bare and a prefixed form coexist, or
    when two or more distinct prefixed forms coexist (the single chokepoint for
    ambiguity). `ArtifactAmbiguityError` is the only exception that may escape.

    Side effects: stat/glob on the happy path; on the ambiguity path only, a
    bounded best-effort content read to set `identical_content`.
    """
    bare_path = directory / bare_name
    # A name that is not a known artifact would never have its prefix honoured,
    # so never glob for it (prevents over-probe of user files like 01_foo.md).
    if bare_name not in KNOWN_ARTIFACTS:
        return bare_path

    prefixed = sorted(directory.glob(_PREFIX_GLOB + bare_name))
    bare_exists = bare_path.is_file()

    if bare_exists and prefixed:
        conflicts = [bare_path] + prefixed
        raise ArtifactAmbiguityError(bare_name, conflicts, _all_identical_content(conflicts))
    if len(prefixed) >= 2:
        raise ArtifactAmbiguityError(bare_name, prefixed, _all_identical_content(prefixed))

    if bare_exists:
        return bare_path
    if len(prefixed) == 1:
        return prefixed[0]
    return bare_path  # neither form exists — return the bare path unchanged


def _detect_prefix_state(directory: Path) -> str:
    """Classify a blueprint/ or specs/<dir>/ directory by artifact prefix state:
    `"uniform-bare"` / `"uniform-prefixed"` / `"mixed"` / `"empty"`. Counts each
    known artifact name independently (if both `spec.md` and `01_spec.md` exist,
    that single artifact contributes one bare + one prefixed, so the state is
    `"mixed"`). Pure filesystem stat — NO interactivity/CI sensing here."""
    bare_count = 0
    prefixed_count = 0
    for bare in KNOWN_ARTIFACTS:
        if (directory / bare).is_file():
            bare_count += 1
        if any(directory.glob(_PREFIX_GLOB + bare)):
            prefixed_count += 1
    if bare_count and prefixed_count:
        return "mixed"
    if bare_count:
        return "uniform-bare"
    if prefixed_count:
        return "uniform-prefixed"
    return "empty"


def _has_artifact_ambiguity(directory: Path) -> bool:
    """True if `directory` holds ANY known artifact in a state `resolve_artifact`
    would raise on (a bare form coexisting with a prefixed form, or two distinct
    prefixed forms). Reuses the resolver itself, so the ambiguity rule lives in
    exactly one place."""
    for bare in KNOWN_ARTIFACTS:
        try:
            resolve_artifact(directory, bare)
        except ArtifactAmbiguityError:
            return True
    return False


def mixed_state_warning(dir_arg: str, directory: Path) -> Optional[str]:
    """The single source of the validators' non-blocking mixed-prefix WARN.

    Returns the WARN string ONLY when the directory is mixed AND the renamer can
    actually fix it (no same-artifact collision). On a bare+prefixed collision
    the renamer would refuse and the validator is about to FAIL with the precise
    ambiguity detail, so nudging the renamer there would loop the user — return
    None and let the ambiguity error speak."""
    if _detect_prefix_state(directory) != "mixed":
        return None
    if _has_artifact_ambiguity(directory):
        return None
    # artifact_prefix.py is a sibling of this module in the shared scripts dir;
    # derive its real absolute path so the printed command is runnable from the
    # user's environment (a literal `telescoping-sdd/scripts/...` would not exist
    # under the project cwd — audit I1.3).
    renamer = Path(__file__).resolve().parent / "artifact_prefix.py"
    return (
        f"WARN: {dir_arg} has a mixed artifact-prefix state (some files prefixed, "
        f"some bare). Run `python {renamer} "
        f"{dir_arg}` to complete the rename (hash-safe)."
    )


def run_cli_failclosed(main_fn) -> None:
    """Run a script entrypoint with the fail-closed `ArtifactAmbiguityError`
    boundary in ONE place. An uncaught ambiguity from anywhere inside `main_fn`
    becomes a clean `FAIL: ambiguous artifact — ...` on stderr + exit 1 instead of
    a traceback — and no future entrypoint can forget to wrap it (the guarantee
    lives here, not copy-pasted in each `__main__`). If `main_fn` returns an int
    it is used as the exit code; `None` falls through (main_fn may sys.exit itself)."""
    try:
        rc = main_fn()
    except ArtifactAmbiguityError as exc:
        print(f"FAIL: ambiguous artifact — {exc}", file=sys.stderr)
        sys.exit(1)
    if rc is not None:
        sys.exit(rc)


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

    # R10: surface orphaned `### Trajectory` rows on the CURRENT artifact (this
    # runs every phase, unlike check_approval which only checks the prior phase).
    add_orphaned_trajectory_results(content, filename, result)


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

# R4 hash-basis migration messages.
# HASH_BASIS_MIGRATION_MSG: the BLOCKING check-time FAIL detail for a v1-basis
# artifact whose stored hash no longer matches under v2. Begins with the
# distinct `HASH-BASIS-MIGRATION:` token so an operator (and `grep`) can tell it
# apart from the pre-fix `Pending-review: FAILED` text at a glance (R4.AC1).
HASH_BASIS_MIGRATION_MSG = (
    "HASH-BASIS-MIGRATION: this artifact was stamped under hash basis v1 "
    "(### Trajectory rows included in hash). Run `--approve <phase>` to migrate "
    "to basis v2 (### Trajectory rows excluded). No pending-review obligation is "
    "created by a basis-only migration re-stamp."
)
# HASH_BASIS_MIGRATION_SUPPRESS_MSG: the NON-blocking approve-time audit line
# printed by restamp_or_suppress's R4 migrate-suppress branch (a v1 artifact's
# basis-only migration re-stamp wrote no marker). DISTINCT from the blocking FAIL
# above; carries a {doc_rel} format field; begins with `hash-basis-migrated:`.
HASH_BASIS_MIGRATION_SUPPRESS_MSG = (
    "hash-basis-migrated: {doc_rel} re-stamped to basis v2; no pending-review "
    "obligation written (basis-only migration, content otherwise unchanged)."
)

# R10 orphaned-Trajectory-row diagnostic token (FAIL when load-bearing, WARN
# otherwise); both validators import it and the archive_pass.py pre-existing
# notice reuses it so the operator connects the two.
ORPHANED_TRAJECTORY_TOKEN = "ORPHANED-TRAJECTORY-ROW:"

# R9 unsatisfiable-obligation diagnostic token: a legacy re-anchored marker whose
# genuine upstream-panel tag sits on a pass <= the recorded anchor, so the
# strictly-`> anchor` reconcile can never clear it.
UNSATISFIABLE_OBLIGATION_TOKEN = "UNSATISFIABLE-OBLIGATION:"

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


def is_basis_migration_only(
    *,
    original_content: str,
    stored_hash: str,
    content_trimmed: str,
) -> bool:
    """True iff this re-stamp is a PURE hash-basis migration (v1->v2, no edit). [R4/AD4]

    Two conditions, both required:
      1. Structural (O(1), trim-safe): read_hash_basis(original_content) == 'v1'
         — the stored stamp predates the v2 basis annotation.
      2. Concurrent-edit (trim-safe): compute_content_hash_v1(content_trimmed)
         == stored_hash — the FROZEN v1 hash of the post-trim content matches the
         stored v1 hash, so the ONLY differences since the v1 approval are
         Trajectory rows (now excluded in v2) and the basis annotation. A
         concurrent substantive edit (e.g. a reworded Defense:) OR `### Trajectory`
         growth that was never re-approved makes the v1 hash differ -> returns
         False -> the marker fires (R4.AC5 / grown-Trajectory).

    Fail-closed: returns False on a 'pending' stored_hash, a non-16-hex
    stored_hash, an unchecked approval checkbox, or a v2 basis. All three str
    parameters are keyword-only — a positional swap is a TypeError, not a silent
    miss (RISK-4).
    """
    if stored_hash == "pending":
        return False
    if not _is_valid_16_hex(stored_hash):
        return False
    if not _approval_checkbox_checked(original_content):
        return False
    if read_hash_basis(original_content) != "v1":
        return False
    return compute_content_hash_v1(content_trimmed).lower() == stored_hash.lower()


# ----- Trajectory Pass parsing (R2 stamped_at_pass) -----------------------


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


# ----- R9 obligation lifecycle: unconditional preserve (AD11) --------------


def read_open_obligation(*, marker_root: Path, doc_rel: str) -> Optional[dict]:
    """Return the OPEN pending-review entry for `doc_rel`, or None. [R9/AD11]

    The SINGLE dispatch read for restamp_or_suppress's "is an obligation open?"
    question. Reads strict=False, so a corrupt/unknown-schemaVersion/absent
    marker reads as no-open-obligation (None) — restamp_or_suppress then routes
    to the fresh-obligation / migration path rather than aborting here.

    H2 malformed-entry filter: an entry present but whose `hash` is absent/None/
    non-16-hex is treated as NOT open (returns None). Such an entry has no
    satisfiable closing condition (reconcile matches the tag against hash[:8]);
    preserving it would manufacture the unsatisfiable dead-end R9 exists to
    eliminate. A returned entry ALWAYS carries a valid 16-hex `hash`. A
    pre-existing malformed entry on disk is surfaced loudly by the STRICT
    reconcile readout, never silently carried.

    SCOPE OF strict=False (spec R9.AC4): fail-open is scoped ONLY to this
    dispatch question. The reconcile readout keeps its strict read and still
    surfaces MarkerCorruptError. The fail-open governs only WHICH branch is
    taken — on a corrupt marker the create/migrate branch's upsert_pending_entry
    (strict=True) WILL raise (the intended fail-closed abort; clobber-protection
    that must not be relaxed).

    Pure read.
    """
    data = read_pending_review(marker_root, strict=False)
    entry = data.get("pending", {}).get(doc_rel)
    if not isinstance(entry, dict):
        return None
    h = entry.get("hash")
    if not isinstance(h, str) or not _is_valid_16_hex(h):
        return None
    return entry


def _preserve_obligation_closing_condition(
    *, marker_root: Path, doc_rel: str, open_entry: dict
) -> None:
    """Re-write the obligation holding its closing condition VERBATIM. [R9/H6]

    Unconditional-preserve (AD11): re-upsert with the SAME `hash` and
    `stamped_at_pass` taken verbatim from `open_entry`; only `stamped_at` is
    refreshed (a liveness touch — DEF-11). The obligation `hash` IS the reconcile
    tag-match key, so it is written back byte-identical and NEVER recomputed.
    Precondition (guaranteed by read_open_obligation's H2 filter):
    open_entry['hash'] is a valid 16-hex string.
    """
    upsert_pending_entry(
        marker_root,
        doc_rel,
        open_entry["hash"],
        now_iso_utc(),
        open_entry.get("stamped_at_pass", 0),
    )


def restamp_or_suppress(
    content_hash: str,
    *,
    stored_hash: str,
    original_content: str,
    content_trimmed: str,
    marker_root: Path,
    doc_rel: str,
) -> None:
    """Post-stamp decision: preserve, create, or suppress a pending-review marker.

    Called from both validators' approve_document() bodies, replacing the bare
    `if changed_since_stamp(...): upsert + REAPPROVAL_REMINDER` block. The
    dispatch is a TOTAL ordering on a SINGLE fact — *is an obligation already
    open for this document?* — with NO content classification (spec R9):

      changed_since_stamp? ── no ─→ (return; nothing owed)
            │ yes
            ├─ obligation open ─→ R9 UNCONDITIONAL PRESERVE: hold the closing
            │                     condition verbatim (H6); no REAPPROVAL_REMINDER.
            │                     R1/R4 suppression and R2 creation do NOT apply
            │                     — they only ever decide whether to CREATE a
            │                     marker, never override an open one (R4 "never
            │                     two markers" upheld; DEF-12 basis-agnostic).
            ├─ none open, not a basis migration ─→ R2 fresh obligation: create +
            │                     REAPPROVAL_REMINDER.
            └─ none open, pure basis migration ─→ R4 suppress: audit line only,
                                  no marker.

    Guarded-if (not early return), so suppression/preservation is scoped to the
    marker block. content_hash is positional; the rest are keyword-only (a
    same-typed-str positional swap is a TypeError — RISK-4).
    """
    if not changed_since_stamp(content_hash, stored_hash, original_content):
        return
    open_entry = read_open_obligation(marker_root=marker_root, doc_rel=doc_rel)
    if open_entry is not None:
        _preserve_obligation_closing_condition(
            marker_root=marker_root, doc_rel=doc_rel, open_entry=open_entry
        )
        print(
            f"r9-preserve: obligation closing condition preserved for {doc_rel} "
            f"(preserved pre-panel hash {open_entry['hash'][:8]}, pass "
            f"{open_entry.get('stamped_at_pass', 0)}; differs by design from the "
            f"just-stamped Content-Hash — see hash-and-cascade.md)"
        )
    elif not is_basis_migration_only(
        original_content=original_content,
        stored_hash=stored_hash,
        content_trimmed=content_trimmed,
    ):
        upsert_pending_entry(
            marker_root,
            doc_rel,
            content_hash,
            now_iso_utc(),
            stamped_at_pass_from_content(original_content),
        )
        print(REAPPROVAL_REMINDER)
    else:
        print(HASH_BASIS_MIGRATION_SUPPRESS_MSG.format(doc_rel=doc_rel))


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


def _row_has_tag(row: str, hash_short: str) -> bool:
    """True iff `row`'s Notes cell carries an `upstream-panel <hash_short>` tag.

    The single per-row tag-scan shared by `_doc_has_qualifying_tag` (which adds
    the `> anchor` filter) and `_doc_has_any_qualifying_tag` (which does not), so
    the two cannot drift in how they match the tag. RAW row text only — never
    content_for_hashing() output (the v2 strip removes every tag — H4-security).
    """
    notes = _trajectory_row_notes(row)
    return any(m.group(1) == hash_short for m in UPSTREAM_PANEL_TAG_RE.finditer(notes))


def _doc_has_any_qualifying_tag(content: str, hash_short: str) -> bool:
    """True iff Trajectory carries `upstream-panel <hash_short>` on ANY pass. [R9/C3]

    No `> anchor` filter — used by the unsatisfiable-state detector to ask
    "does a genuine tag exist at all?". Scans RAW document text (NEVER
    content_for_hashing() output, which strips every Trajectory tag — H4-security).
    """
    return any(_row_has_tag(row, hash_short) for row in _trajectory_data_rows(content))


def _doc_has_qualifying_tag(content: str, hash_short: str, stamped_at_pass: int) -> bool:
    """True iff Trajectory has `upstream-panel <hash_short>` on a Pass > stamped_at_pass.

    Delegates the tag-scan to the shared `_row_has_tag` and re-adds the
    strictly-`> anchor` filter (H4-security: RAW text only).
    """
    for row in _trajectory_data_rows(content):
        first = _row_first_cell(row)
        if not _is_ascii_int(first) or int(first) <= stamped_at_pass:
            continue
        if _row_has_tag(row, hash_short):
            return True
    return False


def _persist_or_unlink_marker(project_root: Path, data: dict) -> None:
    """Write the marker, or delete the file when no obligations remain.

    The shared tail of every read-modify-clear marker op (reconcile / restore),
    so the "unlink when the last obligation clears" invariant lives in ONE place.
    Callers invoke it only after they actually changed `data`.
    """
    root = Path(project_root)
    if not data["pending"]:
        mpath = _marker_path(root)
        if mpath.exists():
            mpath.unlink()
    else:
        write_pending_review(root, data)


def _entry_anchor(entry: dict) -> int:
    """The entry's `stamped_at_pass` coerced to int (non-int/absent -> 0) — the
    shared tolerance for hand-edited markers used by reconcile and the
    unsatisfiable detector."""
    anchor = entry.get("stamped_at_pass", 0)
    return anchor if isinstance(anchor, int) else 0


def _read_contained_doc(project_root: Path, key: str) -> "Optional[str]":
    """Doc text for a pending-marker `key`, or None when the key escapes the
    project root (AD12 containment) or the file can't be read. Silent — the
    reconcile readout keeps its OWN containment guard because it additionally
    WARNs and keeps the entry pending on an escaping key."""
    root = Path(project_root)
    if not _key_is_contained(root, key):
        return None
    try:
        return (root / key).read_text(encoding="utf-8-sig")  # BOM-tolerant (R2.5)
    except OSError:
        return None


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
        anchor = _entry_anchor(entry)
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
            doc_content = (root / key).read_text(encoding="utf-8-sig")  # BOM-tolerant (R2.5)
        except OSError:
            still_pending.append((key, expected_tag))
            continue
        if _doc_has_qualifying_tag(doc_content, hash_short, anchor):
            del pending[key]
            changed = True
        else:
            still_pending.append((key, expected_tag))
    if changed:
        _persist_or_unlink_marker(root, data)
    return still_pending


def _obligation_is_unsatisfiable(project_root: Path, key: str, entry: dict) -> bool:
    """True iff `entry` is a legacy re-anchored obligation that reconcile can never
    clear: a genuine `upstream-panel <hash[:8]>` tag EXISTS in the doc's
    Trajectory, but only on a pass `<= stamped_at_pass` (incl. the exact
    `== stamped_at_pass` F47 boundary, since the clear test is strictly `>`). [R9/C3]

    A fresh obligation with NO tag yet (the healthy post-archive-pre-stamp or
    just-created window) is NOT unsatisfiable. A malformed/short hash, a
    containment-failing key, or an unreadable doc reads as not-unsatisfiable
    (falls back to the generic pending message). Pure read.
    """
    hash_short = str(entry.get("hash", ""))[:8]
    if len(hash_short) < 8:
        return False
    content = _read_contained_doc(project_root, key)
    if content is None:
        return False
    anchor = _entry_anchor(entry)
    return _doc_has_any_qualifying_tag(content, hash_short) and not _doc_has_qualifying_tag(
        content, hash_short, anchor
    )


def restore_anchor_for_prefix(project_root: Path, path_prefix: str) -> list[str]:
    """Content-attested remedy for unsatisfiable (legacy re-anchored) obligations. [R9/C3]

    For each pending entry under `path_prefix` whose doc carries a GENUINE
    `upstream-panel <hash[:8]>` tag on ANY archived Trajectory row, clear the
    obligation — the tag is the proof the panel ran, so restoring the anchor so
    it reconciles is equivalent to clearing it. It clears ONLY when the genuine
    tag is present (content-attested — never a free "mark satisfied", H5); an
    obligation with no qualifying tag is left pending. Reads strict=True (a
    corrupt SHARED marker is never clobbered). A tag stranded on an ORPHANED row
    is invisible here (R10 surfaces it first); the operator makes it contiguous,
    then this clears it. Returns the cleared keys.
    """
    data = read_pending_review(project_root, strict=True)
    pending = data["pending"]
    restored: list[str] = []
    for key in list(pending):
        if not _prefix_in_scope(key, path_prefix):
            continue
        hash_short = str(pending[key].get("hash", ""))[:8]
        if len(hash_short) < 8:
            continue
        content = _read_contained_doc(project_root, key)
        if content is None:
            continue
        if _doc_has_any_qualifying_tag(content, hash_short):
            del pending[key]
            restored.append(key)
    if restored:
        _persist_or_unlink_marker(project_root, data)
    return restored


def add_orphaned_trajectory_results(
    content: str, filename: str, result: ValidationResult
) -> None:
    """Fold orphaned-Trajectory-row diagnostics into `result` (R10/C7).

    One result per orphan: a blocking FAIL when load-bearing (Pass > parsed max,
    OR carries an `upstream-panel` tag), a non-blocking WARN otherwise. Each names
    the specific row (line + text) and the two co-equal remedies. DETECT-and-
    SURFACE only — never mutates content. Shared so both validators behave
    identically (R5).
    """
    for orphan in find_orphaned_trajectory_rows(content):
        detail = (
            f"{ORPHANED_TRAJECTORY_TOKEN} {filename} line {orphan['line_no']}: a "
            f"Trajectory data row is stranded below the table's blank-line "
            f"terminator: {orphan['text'].strip()!r}. It is invisible to the "
            f"contiguous-row scan that backs anchoring/reconcile. Fix it EITHER by "
            f"making the row contiguous with the table (remove the intervening "
            f"blank line) if it is a genuine entry, OR by DELETING it if it is not "
            f"(e.g. a stray pipe line); joining junk into the table is the wrong "
            f"fix. Let `archive_pass.py` own Trajectory row appends."
        )
        result.add(
            f"{filename} Trajectory rows are contiguous",
            False,
            detail,
            warn_only=not orphan["load_bearing"],
        )


def reconcile_to_result(
    project_root: Path,
    path_prefix: str,
    *,
    decline_cmd: str,
    restore_cmd: str = "",
) -> ValidationResult:
    """Reconcile pending obligations under `path_prefix` and fold the outcome
    into a `ValidationResult` (one `pending-review` FAIL per still-pending doc).

    Shared by both validators so the FAIL prose cannot drift. `decline_cmd` is
    the validator-specific decline command shown in the generic FAIL detail;
    `restore_cmd` is the validator-specific anchor-restoration command shown in
    the R9 UNSATISFIABLE-OBLIGATION diagnostic. A corrupt marker yields a single
    fail-closed FAIL (AD11) — the reconcile readout stays STRICT, so a corrupt /
    unknown-schemaVersion marker surfaces loudly here (spec R9.AC4), never the
    dispatch read's fail-open.

    Per still-pending doc: a legacy re-anchored obligation whose genuine tag sits
    on a pass `<= anchor` (unsatisfiable) gets a distinct UNSATISFIABLE-OBLIGATION
    diagnostic naming the content-attested anchor-restoration remedy; every other
    still-pending doc gets the generic pending-review FAIL.
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
    if not still_pending:
        return result
    # The marker parsed (reconcile_pending_review succeeded above); a non-strict
    # re-read just fetches the remaining entry fields for classification.
    pending = read_pending_review(project_root, strict=False)["pending"]
    for doc_rel, expected_tag in still_pending:
        entry = pending.get(doc_rel, {})
        if _obligation_is_unsatisfiable(project_root, doc_rel, entry):
            restore_hint = (
                f" Restore the anchor so the existing genuine tag reconciles: "
                f"`{restore_cmd}`."
                if restore_cmd
                else ""
            )
            result.add(
                "pending-review",
                False,
                f"{UNSATISFIABLE_OBLIGATION_TOKEN} {doc_rel} carries a genuine "
                f"`{expected_tag}` tag, but only on a Trajectory pass <= the "
                f"recorded anchor, so the standard reconcile (which clears strictly "
                f"above the anchor) can never satisfy it — a legacy re-anchored "
                f"marker.{restore_hint} Content-attested: it clears only because the "
                f"genuine tag is present — no marker-cache editing, no "
                f"`{decline_cmd}` needed.",
            )
        else:
            result.add(
                "pending-review",
                False,
                f"upstream panel re-review pending for {doc_rel}. Expected Trajectory "
                f"Notes tag: `{expected_tag}`. Resolve by running the panel and "
                f"stamping that tag per hash-and-cascade.md step 3e (after "
                f"`archive_pass.py {doc_rel} --phase <N>`), OR decline: `{decline_cmd}`.",
            )
    return result
