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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Mapping, NamedTuple, Optional, Sequence, Tuple

# arch_config is a leaf module (no blueprint_common dependency), so this import
# is one-directional. Used by the shared _resolve_marker_root_and_key (R2.1).
from arch_config import find_project_root as arch_find_project_root

# trajectory.py is a leaf (imports only `re`), extracted from this module (audit
# R3.1). Imported at the TOP and re-exported so the hashing path's
# `_strip_trajectory_rows` and the marker path's `stamped_at_pass_from_content`
# resolve, and every existing `from blueprint_common import trim_trajectory_table`
# (etc.) keeps working. Layering: trajectory <- blueprint_common <- pending_review.
from trajectory import (  # noqa: E402,F401
    TRAJECTORY_ELIDED_NOTES_RE,
    TRAJECTORY_HEADER,
    TRAJECTORY_KEEP_DEFAULT,
    TRAJECTORY_SEP_RE,
    UPSTREAM_PANEL_TAG_RE,
    find_orphaned_trajectory_rows,
    stamped_at_pass_from_content,
    trim_trajectory_table,
    _is_ascii_int,
    _panel_trajectory_header_idx,
    _row_first_cell,
    _strip_trajectory_rows,
    _trajectory_bounds,
    _trajectory_data_rows,
    _trajectory_row_notes,
    # Unit C0 (AD1/AD2): table helpers, terminal rules and stamp constants.
    CONVERGED_STAMPS,
    SEAL_ENTRY_RE,
    STAMP_CONVERGED_NO_HIGH,
    STAMP_CONVERGED_SEALED,
    STAMP_CROSS_CHECK,
    STAMP_HALT_DISPOSITION,
    STAMP_STRICT_BAR,
    TERMINAL_FILENAMES,
    TERMINAL_HTML_MARKER,
    TRAJECTORY_COLS,
    is_terminal_artifact,
    render_table,
    render_table_row,
    split_table_row,
    # Unit C0 (T6/T22): provenance token and the convergence verdict.
    PROVENANCE_HEX_WIDTH,
    PROVENANCE_PREFIX,
    PROVENANCE_TOKEN_RE,
    UPSTREAM_TAG_STRIP_RE,
    ConvergenceVerdict,
    TrajectoryRow,
    evaluate_convergence,
    notes_tokens,
    parse_trajectory_rows,
    provenance_token,
    read_provenance_hash,
    select_closing_row,
    stamp_provenance,
    strip_upstream_tags,
)

# content_hash.py is a layer over trajectory (audit R3.1): the versioned
# content-hash basis, the `## Approval` grammar, and the change-detection
# predicates. Imported here and re-exported so check_approval (kept in this
# module — it builds a ValidationResult) and every consumer's
# `from blueprint_common import compute_content_hash` (etc.) still resolve.
from content_hash import (  # noqa: E402,F401
    APPROVAL_HASH_LINE,
    APPROVAL_HASH_LINE_STRICT,
    CONTENT_HASH_HEX,
    CONTENT_HASH_WIDTH,
    HASH_BASIS_CURRENT,
    HASH_BASIS_LINE,
    approval_hash,
    approval_hash_matches,
    approval_section_bounds,
    changed_since_stamp,
    compute_content_hash,
    compute_content_hash_v1,
    content_for_hashing,
    has_approval,
    is_basis_migration_only,
    read_hash_basis,
    read_stored_hash,
    verify_content_hash,
    verify_content_hash_any_basis,
    _APPROVAL_CHECKBOX,
    _APPROVAL_HEADER,
    _HASH_BASIS_REMOVAL_RE,
    _approval_checkbox_checked,
    _content_for_hashing_v1_frozen,
    _is_valid_16_hex,
    _upsert_basis_line,
)

# artifact_resolution.py is a leaf (stdlib only), extracted from this module
# (audit R3.1): NN_-prefix-aware artifact resolution, the ArtifactAmbiguityError
# fail-closed rule, and the run_cli_failclosed CLI boundary. Imported at the top
# and re-exported so `from blueprint_common import resolve_artifact` (etc.) keeps
# working and the bc-internal check_previous_phase_approved / marker code resolve
# it unchanged.
from artifact_resolution import (  # noqa: E402,F401
    KNOWN_ARTIFACTS,
    ArtifactAmbiguityError,
    mixed_state_warning,
    resolve_artifact,
    run_cli_failclosed,
    strip_artifact_prefix,
    _ARTIFACT_PREFIX_RE,
    _PREFIX_GLOB,
    _all_identical_content,
    _detect_prefix_state,
    _has_artifact_ambiguity,
)

# approval_records.py is a leaf over content_hash (Unit C0 AD1): the `## Approval`
# record grammar (upstream bindings, convergence override), display safety, and
# the operator text both lower layers print. Imported at the top and re-exported.
# Layering: {trajectory, artifact_resolution} <- content_hash <- approval_records
# <- blueprint_common <- pending_review.
from approval_records import (  # noqa: E402,F401
    BINDING_LINE_RE,
    BINDING_PART,
    DISPLAY_ARG_MAX,
    GLOSS_BINDING,
    GLOSS_LEGACY,
    GLOSS_SUPERSEDED,
    GLOSS_UNBOUND,
    OVERRIDE_LINE_RE,
    REPAD_PART,
    RESTAMP_CARVE_OUT_PREFIX,
    SEAL_PART,
    TIER_VALIDATOR_CMD,
    USER_DECISION_NOTE,
    DisplayArg,
    OverrideRecord,
    UpstreamBinding,
    append_override_record,
    display_arg,
    display_text,
    read_bindings,
    read_override_record,
    sanitize_override_reason,
    strip_binding_lines,
    upsert_binding_lines,
)

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

# Canonical set of workflow-internal inline tag families — the `[FAMILY-N]`
# tokens stamped into artifact prose: SEAL/DEF panel dispositions (spec/design/
# tasks phases, owned by archive_pass.py), SCOPE/ARCH panel dispositions (scope/
# architecture phases), and CFC cross-feature-contract tags (owned by
# cfc_parser.py). SINGLE SOURCE so the Business Brief filter that strips these
# from stakeholder HTML (render_business_brief, I3.5) builds its allowlist from
# this tuple rather than re-hardcoding a list that can silently drift from the
# grammar. test_inline_tag_families_parity asserts every family a validator
# actually recognizes is a member here.
INLINE_TAG_FAMILIES = ("SEAL", "DEF", "SCOPE", "ARCH", "CFC")
# Regex fragment alternating the families, e.g. rf" ?\[(?:{INLINE_TAG_FAMILIES_RE})-\d+\]".
INLINE_TAG_FAMILIES_RE = "|".join(INLINE_TAG_FAMILIES)

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


def section_body(content: str, section_name: str) -> Optional[str]:
    """Return the body of an H2 `## <name>` section (text after the heading line
    up to the next `## ` heading or EOF), or None if the H2 heading is absent.

    The heading is anchored to the start of a line, so an H3 `### <name>` is NOT
    read as the H2 section — the prior unanchored `## <name>\\s*\\n(.*?)` extractors
    matched `## <name>` as a substring of `### <name>` (audit R2.4/3.5b). A present
    but empty section returns "" (distinct from an absent section's None) so
    callers can tell "section missing" from "section empty".
    """
    # [ \t] (not \s) around the name so trailing blank lines are NOT consumed —
    # otherwise an empty section immediately followed by another `## ` heading
    # would over-read into the next section. Terminator `\n##\s` stops at the next
    # H2 but not an H3 (`### `, whose 3rd char is `#`, fails the `\s`).
    m = re.search(
        rf"^##[ \t]+{re.escape(section_name)}[ \t]*$\n(.*?)(?=\n##\s|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    return m.group(1) if m else None


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
_TASK_CHECKBOX_LINE = re.compile(r"^-\s+\[([ xX])\]\s+", re.MULTILINE)














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
    # The checkbox and Content-Hash lines are read ONLY inside the ## Approval
    # section (audit 3.5c) — matching the scoped write path — so a body-prose
    # `- [x] Approved` / `**Content Hash:**` example before the section is never
    # read as real approval state. The hash itself still verifies over the WHOLE
    # document (verify_content_hash(content, ...) below).
    bounds = approval_section_bounds(content)
    if bounds is None:
        result.add(f"{filename} has Approval section", False, "Missing ## Approval section")
        return False
    approval_body = content[bounds[0]:bounds[1]]

    result.add(f"{filename} has Approval section", True)

    is_approved = bool(_APPROVAL_CHECKBOX.search(approval_body))
    result.add(f"{filename} is approved", is_approved)

    if not is_approved:
        return False

    hash_match = APPROVAL_HASH_LINE_STRICT.search(approval_body)
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
        return
    # Unit C0 (AC-4.2): the previous artifact's own superseded bindings block
    # this phase too (its signature and predecessor contract are unchanged).
    prev_bare = strip_artifact_prefix(prev_path.name)
    rep = binding_report(prev_bare, prev_content, _read_upstream_texts(target_dir, prev_bare))
    for s in rep.superseded:
        result.add(
            f"previous phase ({prev_file}) upstream binding current",
            False,
            superseded_binding_detail(prev_bare, s),
        )


def _atomic_write(target: Path, content: str) -> None:
    """Write `content` to `target` atomically via temp-file + os.replace.

    Guards against partial-state corruption on Ctrl-C / disk-full / process kill
    mid-write. The temp file lives beside the target (so os.replace is atomic on
    POSIX); on failure it is removed and the original is untouched. The temp path
    is appended to the re-raised exception so cross-mount (EXDEV) / permission
    errors point at a real artifact.
    """
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp_removed = False
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)
    except Exception as exc:
        try:
            tmp.unlink(missing_ok=True)
            tmp_removed = True
        except Exception:
            pass
        tmp_status = "removed" if tmp_removed else f"left at {tmp}"
        exc.args = (*exc.args, f"atomic write to {target} failed; temp file {tmp_status}")
        raise


# ----- Unit C0 R3: upstream maps, approval writes and the race check ---------

# Each downstream's upstreams, keyed by bare name, in binding-line order (AD11).
UPSTREAM_SETS = {
    "design.md": ("spec.md",),
    "tasks.md": ("spec.md", "design.md"),
    "ARCHITECTURE.md": ("SCOPE.md",),
    "PLAN.md": ("SCOPE.md", "ARCHITECTURE.md"),
}

# Bare artifact name -> panel phase number (`archive_pass.py --phase <N>`).
ARTIFACT_PHASE_NO = {
    "spec.md": 1, "SCOPE.md": 1,
    "design.md": 2, "ARCHITECTURE.md": 2,
    "tasks.md": 3, "PLAN.md": 3,
}


class UnbindableUpstreamError(Exception):
    """An upstream's stamp is pending, missing or not 16-hex, so a downstream
    approval cannot bind to it (AC-3.8)."""

    def __init__(self, upstream: str, value: "Optional[str]") -> None:
        self.upstream = upstream
        self.value = value
        shown = "missing" if value is None else f"`{display_text(value, max_len=40)}`"
        super().__init__(
            f"{upstream} has no 16-hex approval stamp (Content Hash: {shown})"
        )


class ApprovalRaceError(Exception):
    """Judged content or an upstream stamp changed between plan_approval and
    the stamp (AD7); raised before any write."""


@dataclass(frozen=True)
class ApprovalWrites:
    """DM3: what an approval writes into `## Approval` beyond the stamp."""

    bindings: "Tuple[UpstreamBinding, ...]" = ()
    override: "Optional[OverrideRecord]" = None
    judged_hash: str = ""


def judged_text_hash(text: str) -> str:
    """Full-text SHA-256 of the trimmed text — NOT compute_content_hash: every
    byte counts, Trajectory rows and stamp lines included (AD7)."""
    return hashlib.sha256(trim_trajectory_table(text).encode("utf-8")).hexdigest()


def _read_upstream_stamp(directory: Path, upstream: str) -> "Optional[str]":
    """The upstream's stored stamp text, or None when absent/unreadable.
    ArtifactAmbiguityError propagates."""
    p = resolve_artifact(directory, upstream)
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    return read_stored_hash(text)


def collect_upstream_bindings(directory: Path, bare_name: str) -> "Tuple[UpstreamBinding, ...]":
    """The bindings a `bare_name` approval would write, in UPSTREAM_SETS order.

    Each upstream binds to its stored 16-hex stamp, lowercased, even when its
    content has drifted (that drift is the previous-phase check's to report).
    Raises UnbindableUpstreamError for a pending, missing or non-16-hex stamp
    (AC-3.8).
    """
    out = []
    for up in UPSTREAM_SETS.get(bare_name, ()):
        value = _read_upstream_stamp(Path(directory), up)
        if value is None or not _is_valid_16_hex(value):
            raise UnbindableUpstreamError(up, value)
        out.append(UpstreamBinding(upstream=up, content_hash=value.lower()))
    return tuple(out)


def verify_judged_transform(content: str, file_path: Path, *, writes: ApprovalWrites) -> str:
    """First transform in approve_document's chain (AD7, AD12): refuse with
    ApprovalRaceError if the core's trimmed content no longer hashes to what
    plan_approval judged, or an upstream stamp it bound has moved. Returns the
    content unchanged."""
    if judged_text_hash(content) != writes.judged_hash:
        raise ApprovalRaceError(
            f"{file_path} changed between the approval check and the stamp"
        )
    for b in writes.bindings:
        now = _read_upstream_stamp(Path(file_path).parent, b.upstream)
        if now is None or now.lower() != b.content_hash:
            raise ApprovalRaceError(
                f"{b.upstream}'s approval stamp changed between the approval "
                f"check and the stamp"
            )
    return content


def apply_approval_writes(content: str, file_path: Path, *, writes: ApprovalWrites) -> str:
    """Upsert the binding lines (AD10) and append the override record once
    (AD8), inside approval_section_bounds only. Idempotent (I4)."""
    if writes.bindings:
        content = upsert_binding_lines(content, writes.bindings)
    if writes.override is not None and read_override_record(content) is None:
        content = append_override_record(content, writes.override)
    return content


def compose_content_transforms(*transforms):
    """One `content_transform(content, file_path)` applying each non-None
    transform in order (AD12: race check, producer hook, approval writes)."""
    chain = [t for t in transforms if t is not None]

    def _composed(content: str, file_path: Path) -> str:
        for t in chain:
            content = t(content, file_path)
        return content

    return _composed


# ----- Unit C0 R3/R4: binding reports ----------------------------------------

# The consistency check each downstream's bindings are re-verified with, and
# its `--approve` phase flag.
_BINDING_PAIR_CHECK = {
    "design.md": "Spec-Design",
    "tasks.md": "Spec-Design-Tasks",
    "ARCHITECTURE.md": "Scope-Architecture",
    "PLAN.md": "Scope-Architecture-Plan",
}
_APPROVE_PHASE_FLAG = {
    "spec.md": "spec", "design.md": "design", "tasks.md": "tasks",
    "SCOPE.md": "scope", "ARCHITECTURE.md": "architecture", "PLAN.md": "plan",
}


@dataclass(frozen=True)
class SupersededBinding:
    """DM4: one superseded binding. ``reason`` is 'newer-stamp',
    'upstream-unapproved' or 'duplicate'."""

    upstream: str
    recorded: "Tuple[str, ...]"
    current: str
    reason: str


@dataclass(frozen=True)
class BindingReport:
    """DM4: unbound upstreams and superseded bindings of one downstream."""

    unbound: "Tuple[str, ...]" = ()
    superseded: "Tuple[SupersededBinding, ...]" = ()


def binding_report(
    downstream_bare: str,
    downstream_text: str,
    upstream_texts: "Mapping[str, Optional[str]]",
) -> BindingReport:
    """The one binding comparator (AD11), shared by validation, `--run-state` and
    the previous-phase check. A no-op on an unapproved downstream (a draft never
    reads as unbound, AC-3.6). Over an approved downstream it is total: an
    upstream with no line is unbound; one whose text is None or whose stamp is
    not 16-hex is superseded ('upstream-unapproved'); two or more lines for one
    upstream are superseded ('duplicate'); a single line whose value differs
    from the upstream's current stamp is superseded ('newer-stamp'). Stamps are
    compared lowercased."""
    if not has_approval(downstream_text):
        return BindingReport()
    recorded = read_bindings(downstream_text)
    unbound = []
    superseded = []
    for up in UPSTREAM_SETS.get(downstream_bare, ()):
        vals = recorded.get(up, ())
        if not vals:
            unbound.append(up)
            continue
        text = upstream_texts.get(up)
        cur = read_stored_hash(text) if text is not None else "missing"
        if text is None or not _is_valid_16_hex(cur):
            superseded.append(SupersededBinding(up, vals, cur, "upstream-unapproved"))
        elif len(vals) >= 2:
            superseded.append(SupersededBinding(up, vals, cur.lower(), "duplicate"))
        elif vals[0] != cur.lower():
            superseded.append(SupersededBinding(up, vals, cur.lower(), "newer-stamp"))
    return BindingReport(tuple(unbound), tuple(superseded))


def _read_upstream_texts(directory: Path, bare_name: str) -> "dict":
    return {
        up: read_file(resolve_artifact(Path(directory), up))
        for up in UPSTREAM_SETS.get(bare_name, ())
    }


def superseded_binding_detail(downstream: str, s: SupersededBinding) -> str:
    """AC-4.1 / AC-4.2 FAIL text for one superseded binding (shared wording)."""
    dt = lambda x: display_text(x, max_len=DISPLAY_ARG_MAX)  # noqa: E731
    rec = ", ".join(dt(v) for v in s.recorded)
    if s.reason == "duplicate":
        what = f"{downstream} has {len(s.recorded)} binding lines for {s.upstream} ({rec})"
    elif s.reason == "upstream-unapproved":
        what = (
            f"{downstream} is bound to {s.upstream} @ {rec}, but {s.upstream} is not "
            f"approved now (Content Hash: {dt(s.current)})"
        )
    else:
        what = (
            f"{downstream} is bound to {s.upstream} @ {rec}, but {s.upstream} is now "
            f"stamped {dt(s.current)}"
        )
    pair = _BINDING_PAIR_CHECK.get(downstream, "consistency")
    flag = _APPROVE_PHASE_FLAG.get(downstream, "<phase>")
    return (
        f"{what} ({s.reason}) — {downstream} was approved against an older "
        f"{s.upstream}; {GLOSS_SUPERSEDED}. Run the {pair} consistency check "
        f"against the current {s.upstream}, then re-approve top-down "
        f"(`--approve {flag}`), expecting further FAILs below it until each "
        f"downstream is re-approved. An upstream re-approval with no "
        f"reviewed-content change (e.g. a seal-promotion re-stamp) produces this "
        f"same FAIL; the re-approval clears it."
    )


def check_upstream_bindings(
    directory: Path,
    bare_name: str,
    content: str,
    result: "ValidationResult",
    *,
    exempt_own_binding: bool = False,
) -> None:
    """`<name> upstream binding current`: superseded -> FAIL (AC-4.1), unbound
    -> WARN (AC-3.6). No-op when the artifact is unapproved, has no upstreams,
    or ``exempt_own_binding`` (the approve about to rebind it)."""
    if exempt_own_binding or bare_name not in UPSTREAM_SETS or not has_approval(content):
        return
    rep = binding_report(bare_name, content, _read_upstream_texts(directory, bare_name))
    check = f"{bare_name} upstream binding current"
    for s in rep.superseded:
        result.add(check, False, superseded_binding_detail(bare_name, s))
    if rep.unbound:
        pair = _BINDING_PAIR_CHECK[bare_name]
        flag = _APPROVE_PHASE_FLAG[bare_name]
        result.add(
            check,
            False,
            f"{bare_name} has no upstream binding for {', '.join(rep.unbound)} — "
            f"{GLOSS_UNBOUND}. To bind it: run the {pair} consistency check against "
            f"the current upstream, then re-approve (`--approve {flag}`), top-down.",
            warn_only=True,
        )
    if not rep.superseded and not rep.unbound:
        result.add(check, True)


# ----- Unit C0 R5: the convergence gate wrapper (AD6) -------------------------

MSG_MISSING_CROSS_CHECK = (
    "a NORMAL pass followed a strict-bar pass — the likely cause is a missing "
    "`--cross-check` stamp: a STRICT-BAR run exits only through a cross-check "
    "pass archived with `archive_pass.py --cross-check`"
)
MSG_STRICT_BAR_EXIT = (
    "the closing pass is a STRICT-BAR pass, which exits only through a cross-check "
    "(`panel-review-convergence.md` § Exit cross-check)"
)
_MSG_LEGACY_FORMAT = (
    "`## Panel Review` is in the legacy single-table format, which the archive "
    "script refuses: first migrate it by hand to the three-sub-section format "
    "(`### Trajectory`, `### Sealed dispositions`, `### Latest pass detail`)"
)


def _gate_code_text(code: str) -> str:
    if code == "no-converged-stamp":
        return "the closing pass carries no converged stamp (it left an unresolved HIGH concern)"
    if code.startswith("addressed="):
        return (f"the closing pass disposed {code.split('=', 1)[1]} concern(s) Addressed "
                f"— an edit no pass has reviewed yet")
    if code.startswith("deferred="):
        return f"the closing pass disposed {code.split('=', 1)[1]} concern(s) Deferred"
    if code == "cross-check-without-strict-bar":
        return "the closing cross-check pass has no strict-bar pass before it"
    if code == "normal-after-strict-bar":
        return MSG_MISSING_CROSS_CHECK
    if code == "strict-bar-closing":
        return MSG_STRICT_BAR_EXIT
    if code == "halt-and-rescope":
        return "the closing pass recorded a Halt and re-scope disposition"
    if code == "edited-after-pass":
        return "the content changed after the closing pass was archived, so no pass reviewed it"
    return code


def _panel_body(content: str) -> str:
    m = re.search(r"^##\s+Panel Review\s*$", content, re.MULTILINE)
    if m is None:
        return ""
    nxt = re.search(r"^##\s+", content[m.end():], re.MULTILINE)
    return content[m.end(): m.end() + nxt.start()] if nxt else content[m.end():]


def check_convergence_gate(
    content: str, bare_name: str, artifact_path: Path, result: "ValidationResult"
) -> ConvergenceVerdict:
    """`<name> convergence gate` (R5). The caller runs it at FIRST approval only
    (I5). Adds one FAIL, WARN or PASS row with the AD6 evidence-based routes, and
    returns the verdict with ``edited-after-pass`` appended when the freshness
    check (AC-5.11) fails."""
    check = f"{bare_name} convergence gate"
    v = evaluate_convergence(content)
    terminal = " --terminal" if is_terminal_artifact(content, Path(artifact_path).name) else ""
    phase = ARTIFACT_PHASE_NO.get(bare_name, "<N>")
    art = display_text(str(artifact_path), max_len=DISPLAY_ARG_MAX)
    panel_route = (
        f"run another panel pass and archive it (`archive_pass.py {art} --phase {phase}{terminal}`)"
    )
    override_route = (
        f"approve with `--override-convergence \"<reason>\"` — {USER_DECISION_NOTE}"
    )
    failed = list(v.failed)

    if v.legacy and failed:
        codes = "; ".join(_gate_code_text(c) for c in failed)
        result.add(
            check, False,
            f"{bare_name}'s closing Trajectory row is legacy ({GLOSS_LEGACY}); it would "
            f"fail the convergence rules ({', '.join(failed)}: {codes}). Not blocking: "
            f"size the backlog with `--audit-convergence`.",
            warn_only=True,
        )
        return v
    if v.legacy:
        result.add(check, True, "legacy closing row passes the convergence rules")
        return v

    if "no-converged-pass" in failed:
        body = _panel_body(content)
        evidence = bool(PANEL_TRAJECTORY_ROW.search(body) or PANEL_SEAL_ENTRY.search(body))
        routes = []
        if v.legacy_format:
            routes.append(_MSG_LEGACY_FORMAT)
        routes.append(panel_route)
        if evidence:
            routes.append(override_route)
        result.add(
            check, False,
            f"no converged panel pass recorded for {bare_name} (no Trajectory row "
            f"other than skip rows). Route out: " + "; or ".join(routes) + ".",
        )
        return v

    if v.freshness_hash is not None and v.freshness_hash != compute_content_hash(content):
        failed.append("edited-after-pass")

    if not failed:
        result.add(check, True, f"closing pass {v.closing_pass} converged")
        return v

    reasons = "; ".join(_gate_code_text(c) for c in failed)
    if "edited-after-pass" in failed:
        routes = (
            f"(1) for a mechanical edit only, record it: `archive_pass.py {art} --phase "
            f"{phase}{terminal} --skip \"<what changed>\"` (valid only per "
            f"panel-review-modes.md § When to Skip the Panel); (2) for a substantive "
            f"edit, {panel_route.replace('run another panel pass', 'another panel pass')}; "
            f"(3) {override_route}"
        )
    else:
        routes = f"{panel_route}; or {override_route}"
    result.add(
        check, False,
        f"{bare_name}'s closing pass {v.closing_pass} did not converge "
        f"({', '.join(failed)}): {reasons}. Route out: {routes}.",
    )
    return ConvergenceVerdict(v.closing_pass, tuple(failed), v.legacy, v.legacy_format, v.freshness_hash)


# ----- Unit C0 R6: the read-only convergence audit (AD9) ---------------------

AUDIT_STATES = (
    "converged",
    "converged (previously overridden)",
    "overridden",
    "unconverged",
    "no converged panel pass recorded",
)
AUDIT_UNAUDITABLE = "unauditable (ambiguous NN_ prefix)"
_AUDIT_OK = {"converged", "converged (previously overridden)", "overridden"}


@dataclass(frozen=True)
class AuditEntry:
    """DM12: one audit report line. ``reason`` carries the stored override
    reason for 'overridden', or 'duplicate override records'."""

    path: str
    state: str
    legacy: bool
    reason: "Optional[str]" = None


def _audit_one(label: str, text: str) -> AuditEntry:
    v = evaluate_convergence(text)
    rec = read_override_record(text)
    duplicate = rec is not None and rec.duplicate
    if duplicate:
        rec = None
    note = "duplicate override records" if duplicate else None
    if "no-converged-pass" in v.failed:
        if rec is not None:
            return AuditEntry(label, "overridden", v.legacy, rec.reason)
        # AC-6.5: an approved artifact with no closing row and no override
        # record is labelled legacy here, independently of verdict.legacy.
        return AuditEntry(label, "no converged panel pass recorded", True, note)
    if not v.failed:
        state = "converged (previously overridden)" if rec is not None else "converged"
        return AuditEntry(label, state, v.legacy, note)
    if rec is not None:
        return AuditEntry(label, "overridden", v.legacy, rec.reason)
    return AuditEntry(label, f"unconverged ({', '.join(v.failed)})", v.legacy, note)


def audit_convergence(artifacts: "Sequence[Tuple[str, Path]]") -> "List[AuditEntry]":
    """Judge each APPROVED artifact (valid 16-hex stored stamp) by its current
    closing row, AC-5.2–5.6, without the freshness check (AC-6.5). Pure read."""
    out = []
    for label, path in artifacts:
        p = Path(path)
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        if not _is_valid_16_hex(read_stored_hash(text)):
            continue
        out.append(_audit_one(label, text))
    return out


def audit_directory(
    directory: Path, names: "Sequence[str]", *, label: "Optional[str]" = None
) -> "List[AuditEntry]":
    """Audit one artifact directory. An ambiguous NN_ prefix makes the whole
    directory one `unauditable` entry (AD9) instead of aborting the run."""
    shown = label if label is not None else str(directory)
    try:
        paths = [resolve_artifact(Path(directory), n) for n in names]
        items = [(f"{shown}/{p.name}", p) for p in paths]
    except ArtifactAmbiguityError:
        return [AuditEntry(display_text(shown, max_len=DISPLAY_ARG_MAX), AUDIT_UNAUDITABLE, False)]
    return audit_convergence(items)


def format_audit_report(entries: "Sequence[AuditEntry]") -> "Tuple[str, int]":
    """(text, exit_code): one line per entry, then the DM12 summary line. Exit
    0 iff nothing is unauditable and every non-legacy artifact is converged,
    previously overridden or overridden."""
    lines = []
    counts = {s: 0 for s in AUDIT_STATES}
    unauditable = legacy = 0
    ok = True
    for e in entries:
        line = f"{display_text(e.path, max_len=DISPLAY_ARG_MAX)}: {e.state}"
        if e.state == "overridden" and e.reason:
            line += f" — reason: {display_text(e.reason, max_len=DISPLAY_ARG_MAX)}"
        elif e.reason:
            line += f" ({e.reason})"
        if e.legacy:
            line += " — legacy"
        lines.append(line)
        if e.state == AUDIT_UNAUDITABLE:
            unauditable += 1
            ok = False
            continue
        if e.legacy:
            legacy += 1
            continue
        base = "unconverged" if e.state.startswith("unconverged") else e.state
        counts[base] = counts.get(base, 0) + 1
        if base not in _AUDIT_OK:
            ok = False
    lines.append(
        "convergence audit: "
        + ", ".join(f"{s} {counts[s]}" for s in AUDIT_STATES)
        + f", unauditable {unauditable}; legacy {legacy}"
    )
    return "\n".join(lines), 0 if ok else 1


# ----- Unit C0 R5/R6/R3: approve-flow orchestration (AD7) ---------------------


@dataclass
class ApprovalPlan:
    """DM11. Any FAIL row in ``result`` means exit 1 and no write, under any
    flags. ``writes`` is None under --task-tick (AC-3.9) or on a refusal."""

    writes: "Optional[ApprovalWrites]"
    result: "ValidationResult"
    post_lines: "List[str]"


_OVERRIDE_NOT_NEEDED = "convergence override not needed for {name}: {why}; no override record written"


def plan_approval(
    target: Path,
    *,
    directory: Path,
    bare_name: str,
    task_tick: bool,
    override_reason: "Optional[str]",
) -> ApprovalPlan:
    """Judge one approve before anything is written (AD7). Pure read.

    Rows: AC-5.8's unstamped --task-tick refusal (SDD only); AC-3.8's
    unbindable-upstream refusal; at first approval (no valid 16-hex stored
    stamp, R5 scope) the convergence gate, or the override that resolves its
    FAIL. Records the full-text ``judged_hash`` the race check re-verifies.
    """
    result = ValidationResult()
    post: "List[str]" = []
    text = Path(target).read_text(encoding="utf-8-sig")
    first = not _is_valid_16_hex(read_stored_hash(text))
    name = display_text(Path(target).name, max_len=DISPLAY_ARG_MAX)

    if task_tick:
        if first:
            result.add(
                f"{bare_name} task-tick on a stamped artifact",
                False,
                f"{name} carries no approval stamp, so `--task-tick` would be a first "
                f"approval that bypasses the convergence gate and the upstream binding "
                f"write. Route out: run a plain `--approve tasks`.",
            )
        elif override_reason is not None:
            post.append(_OVERRIDE_NOT_NEEDED.format(
                name=name, why="a re-approval never meets the convergence gate"))
        return ApprovalPlan(None, result, post)

    try:
        bindings = collect_upstream_bindings(directory, bare_name)
    except UnbindableUpstreamError as exc:
        flag = _APPROVE_PHASE_FLAG.get(exc.upstream, "<phase>")
        result.add(
            f"{bare_name} upstream approval stamp",
            False,
            f"{exc}, so {name} cannot record which version it was approved against. "
            f"Approve the named upstream first: `--approve {flag}`.",
        )
        return ApprovalPlan(None, result, post)

    override = None
    if first:
        gate = ValidationResult()
        verdict = check_convergence_gate(text, bare_name, Path(target), gate)
        gate_failed = any(c[1] == Severity.FAIL for c in gate.checks)
        if gate_failed and override_reason is not None:
            reason = sanitize_override_reason(override_reason)
            override = OverrideRecord(verdict.closing_pass, reason)
            shown_pass = "none" if verdict.closing_pass is None else str(verdict.closing_pass)
            result.add(
                f"{bare_name} convergence gate", False,
                f"overridden as a user decision (closing pass {shown_pass}; "
                f"{', '.join(verdict.failed)}) — recorded in ## Approval",
                warn_only=True,
            )
            post.append(
                f"convergence override: {name} approved at pass {shown_pass} although "
                f"it failed ({', '.join(verdict.failed)}) — reason: {reason}"
            )
        else:
            result.checks.extend(gate.checks)
            if override_reason is not None:
                why = (
                    "its closing row is legacy, so the gate only warns"
                    if verdict.legacy else "it passes the convergence gate"
                )
                if not gate_failed:
                    post.append(_OVERRIDE_NOT_NEEDED.format(name=name, why=why))
    elif override_reason is not None:
        post.append(_OVERRIDE_NOT_NEEDED.format(
            name=name, why="a re-approval never meets the convergence gate"))

    writes = ApprovalWrites(
        bindings=bindings, override=override, judged_hash=judged_text_hash(text)
    )
    return ApprovalPlan(writes, result, post)


def approve_document(
    file_path: Path,
    *,
    task_tick: bool = False,
    project_root: "Optional[Path]" = None,
    content_transform=None,
) -> bool:
    """Shared approve_document core (audit 3.5a) — both validators wrap this.

    Marks a document approved: trims the Trajectory table, optionally applies a
    PRODUCER hook to the trimmed content (`content_transform(content, file_path)`
    — the blueprint side refreshes PLAN.md's per-CFC hash sub-block here; the SDD
    side passes None), computes the content hash, scopes the checkbox / Content-
    Hash / Hash-basis rewrites to the `## Approval` slice, verifies they landed
    (R1.5), writes atomically, prints `Approved:`, and on a CHANGED re-stamp calls
    restamp_or_suppress — UNLESS the CONSUMER flag `task_tick` is set (the SDD
    Phase-4 carve-out, which suppresses the marker and prints an audit line).

    Returns True when stamped, False when approval could not be applied (no
    `## Approval` section, or its checkbox / Content-Hash line is missing so the
    substitutions would silently no-op). Callers MUST propagate a False return as
    a non-zero exit — stamping nothing while exiting 0 is the silent-corruption
    failure this guards against (R1.5). restamp_or_suppress may raise
    MarkerCorruptError AFTER the stamp; this lets it propagate so in-process
    callers see it (the CLI --approve branches catch it for a clean exit, R2.6).
    """
    original_content = file_path.read_text(encoding="utf-8-sig")  # BOM-tolerant (R2.5)
    # Read the prior stored hash BEFORE the trim/transform mutates content (DEF-06).
    stored_hash = read_stored_hash(original_content)

    # Trim the `### Trajectory` table to the latest rows BEFORE hashing — the
    # trimmed table is part of the approved content.
    content = trim_trajectory_table(original_content)
    content_trimmed = content  # post-trim, pre-transform: the migration baseline

    # Producer hook (e.g. PLAN.md per-CFC hash refresh) applied post-trim, pre-hash
    # so the refreshed sub-block is part of the document-level hash.
    if content_transform is not None:
        content = content_transform(content, file_path)
    # Post-transform, pre-rewrite snapshot (Unit C0 AD12): what the restamp
    # classifier compares with content_trimmed (only binding lines may differ).
    transformed = content

    content_hash = compute_content_hash(content)

    # Checkbox + Content-Hash + `- **Hash basis:** v2`, scoped to the `## Approval`
    # slice via the shared approval_section_bounds (R8/AD10) — a document-wide
    # re.sub would rewrite a body-prose example of those lines.
    approval = approval_section_bounds(content)
    if approval is None:
        print(
            f"Error: {file_path} has no `## Approval` section; cannot approve.",
            file=sys.stderr,
        )
        return False
    body_start, body_end = approval
    approval_body = content[body_start:body_end]
    approval_body = re.sub(
        r"- \[ \] Approved to proceed", "- [x] Approved to proceed", approval_body
    )
    approval_body = re.sub(
        r"\*\*Content Hash:\*\*\s*`[^`]*`",
        f"**Content Hash:** `{content_hash}`",
        approval_body,
    )
    approval_body = _upsert_basis_line(approval_body)

    # Verify the substitutions landed before writing — a missing/mangled checkbox
    # or Content-Hash line makes the re.subs no-op, which would stamp nothing yet
    # print a false success (R1.5). Accepts an already-checked box (re-stamp).
    checkbox_ok = "[x] Approved to proceed" in approval_body
    hash_ok = f"**Content Hash:** `{content_hash}`" in approval_body
    if not (checkbox_ok and hash_ok):
        missing = []
        if not checkbox_ok:
            missing.append("a `- [ ] Approved to proceed` checkbox")
        if not hash_ok:
            missing.append("a `- **Content Hash:** `...`` line")
        print(
            f"Error: {file_path}'s `## Approval` section is missing "
            f"{' and '.join(missing)}; cannot approve (nothing stamped).",
            file=sys.stderr,
        )
        return False
    content = content[:body_start] + approval_body + content[body_end:]

    _atomic_write(file_path, content)
    print(f"Approved: {file_path} (hash: {content_hash})")

    if task_tick:
        # SDD Phase-4 task-tick carve-out (DEF-01/RI-11): suppress reminder + marker.
        print(
            f"task-tick: pending-review suppressed for {file_path} "
            f"(Phase-4 carve-out)"
        )
        return True
    root, doc_rel = _resolve_marker_root_and_key(file_path, project_root)
    restamp_or_suppress(
        content_hash,
        stored_hash=stored_hash,
        original_content=original_content,
        content_trimmed=content_trimmed,
        marker_root=root,
        doc_rel=doc_rel,
        final_content=transformed,
    )
    return True


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

MARKER_RELPATH = Path(".sdd") / "pending-review.json"
MARKER_SCHEMA_VERSION = 1

# Tag the agent stamps into a Trajectory Notes cell after the upstream panel
# (hash-and-cascade.md step 3e); the R2 clear matches it.
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

# 3.5d stranded-obligation token: a pending-review entry whose target file no
# longer exists (typically a renamed/deleted spec directory), which moves the
# obligation out of the prefix-scoped reconcile's view so it would otherwise be
# both invisible and unclearable.
STRANDED_OBLIGATION_TOKEN = "STRANDED-OBLIGATION:"

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

# ----- AD5: --decline-pending partition + reversed-order WARN constants ------
# Operator-facing strings for the order-independent-anchor feature (M-guard).
# Single source of truth so both validators + tests reference one object; none
# describe a *fresh* reversed-order obligation as "legacy" (R3). Imported into
# pending_review.py (the three decline-side ones in T1; REVERSED_ORDER_CREATE_WARN
# in T5 where the WARN print lands) and both validators.

# --decline-pending exit code when one or more keys are held back or flagged
# (a non-clean partition). Distinct from 1 (corrupt marker) and 2 (arg error).
EXIT_DECLINE_HELD_BACK = 3
# --decline-pending exit code when the decline is refused outright (multi-scope,
# other-tier, or a refused --decline-key); nothing is written (Unit C0 AD15).
EXIT_DECLINE_REFUSED = 4

DECLINE_UNSATISFIABLE_HELD_BACK_MSG = (
    "Held back {doc_rel}: NOT declined. A genuine upstream-panel re-review tag is "
    "present (the panel WAS performed), so declining it would falsely record that "
    "panel as skipped. Clear it with `{restore_cmd}` (content-attested), not "
    "--decline-pending."
)

DECLINE_FLAGGED_ANOMALOUS_MSG = (
    "Flagged {doc_rel}: cleared, but its pending-review entry was unclassifiable "
    "(corrupt/non-16-hex hash, or an out-of-tree key) — surfaced so a corrupt entry "
    "is never mistaken for a normal decline. Inspect .sdd/pending-review.json if "
    "this is unexpected."
)

# Unit C0 (AD16): the two kinds a FLAGGED key splits into when the caller knows
# the project root. DECLINE_FLAGGED_ANOMALOUS_MSG stays for callers that don't.
DECLINE_FLAGGED_ESCAPING_MSG = (
    "Flagged {doc_rel}: cleared, but its key is containment-escaping (its path "
    "resolves outside the project, so no session can own or satisfy it) — "
    "surfaced so it is never mistaken for a normal decline. Inspect "
    ".sdd/pending-review.json if this is unexpected."
)

DECLINE_FLAGGED_MALFORMED_MSG = (
    "Flagged {doc_rel}: cleared, but its pending-review entry was malformed "
    "(corrupt/non-16-hex hash, or a hand-edited path) — surfaced so a corrupt "
    "entry is never mistaken for a normal decline. Inspect "
    ".sdd/pending-review.json if this is unexpected."
)

REVERSED_ORDER_CREATE_WARN = (
    "reversed-order-create: the `### Trajectory` row at this obligation's anchor "
    "already carries an upstream-panel tag — the 'review-then-approve' shape (a "
    "panel pass was archived before this --approve). The obligation for {doc_rel} "
    "was still created, but it may be unsatisfiable by the normal reconcile; if so, "
    "clear it with `--restore-anchor` (content-attested), NOT --decline-pending."
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


# ---------------------------------------------------------------------------
# Pending-review marker lifecycle (extracted to pending_review.py, audit R3.1)
#
# The marker read/write, the advisory lock, the obligation lifecycle, and
# reconcile_to_result now live in pending_review.py. They are re-exported here
# (at the BOTTOM, after every primitive they depend on is defined) so the public
# surface is unchanged — `from blueprint_common import upsert_pending_entry`
# (etc.) keeps working, and pending_review can import its primitives from this
# partially-loaded module without a cycle.
# ---------------------------------------------------------------------------
from pending_review import (  # noqa: E402
    BLUEPRINT_ARTIFACT_NAMES,
    RestampDelta,
    classify_restamp_delta,
    format_restamp_carve_out,
    SDD_ARTIFACT_NAMES,
    DeclineRefusal,
    DeclineResult,
    decline_pending_scoped,
    format_decline_refusal,
    is_containment_escaping,
    owning_dir_route,
    partition_keys,
    scope_of_key,
    tier_of_scope,
    clear_pending_entries_for_prefix,
    format_decline_output,
    partition_decline_clear,
    read_open_obligation,
    read_pending_review,
    reconcile_pending_review,
    reconcile_to_result,
    restamp_or_suppress,
    restore_anchor_for_prefix,
    sweep_sdd_cruft,
    upsert_pending_entry,
    write_pending_review,
    # Private helpers some consumers/tests reach for by name (e.g.
    # artifact_prefix.py's boundary-safe prefix check) — re-exported so the move
    # stays transparent. (_marker_lock_depth is deliberately NOT re-exported: a
    # re-exported int would be a stale snapshot — use pending_review's.)
    _anchor_row_carries_tag,
    _doc_has_any_qualifying_tag,
    _doc_has_matching_orphaned_tag,
    _doc_has_qualifying_tag,
    _empty_marker,
    _entry_anchor,
    _key_is_contained,
    _marker_lock,
    _marker_path,
    _obligation_is_unsatisfiable,
    _persist_or_unlink_marker,
    _prefix_in_scope,
    _preserve_obligation_closing_condition,
    _read_contained_doc,
    _restamp_or_suppress_locked,
    _row_has_tag,
)
