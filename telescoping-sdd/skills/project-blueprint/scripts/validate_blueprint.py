#!/usr/bin/env python3
"""Validate and approve project blueprint artifacts.

Checks that SCOPE.md, ARCHITECTURE.md, and PLAN.md have required sections,
no unresolved questions or decisions, and follow the expected structure.
Can also approve documents for phase transitions using content hashes
to detect post-approval edits.

Usage:
    python validate_blueprint.py <blueprint-directory>
    python validate_blueprint.py blueprint/ --phase scope
    python validate_blueprint.py blueprint/ --approve scope
    python validate_blueprint.py blueprint/ --output json
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

# sys.path bootstrap — skill entry point (audit R3.5: one idiom across entry
# points). Put telescoping-sdd/scripts/ (the shared helpers, sibling of
# telescoping-sdd/skills/) on sys.path via an idempotent guarded APPEND. Append,
# never insert(0): a skill validator runs under the plugin/marketplace runtime,
# where displacing the caller's sys.path[0] would break its module resolution
# (regression guard for T3 AC). The `not in` guard stops repeated imports from
# stacking duplicate entries. Shared-script entry points (reconcile.py,
# artifact_prefix.py) use a guarded insert(0) instead — nothing else bootstraps
# them, so they must take precedence.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.append(str(_SHARED_SCRIPTS))

from blueprint_common import (  # noqa: E402
    APPROVAL_HASH_LINE_STRICT,
    PANEL_UNRESOLVED_DISPOSITION,
    REAPPROVAL_REMINDER,
    MarkerCorruptError,
    Severity,
    UnresolvedMarker,
    ValidationResult,
    approval_hash,
    approve_document as _approve_document_core,
    _atomic_write,
    mixed_state_warning,
    resolve_artifact,
    run_cli_failclosed,
    strip_artifact_prefix,
    approval_hash_matches,
    approval_section_bounds,
    changed_since_stamp,
    check_approval,
    check_previous_phase_approved,
    clear_pending_entries_for_prefix,
    compute_content_hash,
    content_for_hashing,
    format_decline_output,
    partition_decline_clear,
    extract_panel_section,
    has_approval,
    has_section,
    section_body,
    _resolve_marker_root_and_key,
    is_basis_migration_only,
    is_shipped_from_contents,
    now_iso_utc,
    read_file,
    read_hash_basis,
    read_stored_hash,
    reconcile_to_result,
    restamp_or_suppress,
    restore_anchor_for_prefix,
    sweep_sdd_cruft,
    scan_unresolved_markers,
    section_has_content,
    stamped_at_pass_from_content,
    trim_trajectory_table,
    upsert_pending_entry,
    validate_panel_review,
    verify_content_hash,
    HASH_BASIS_MIGRATION_MSG,
    _APPROVAL_HEADER as APPROVAL_HEADER,
    _upsert_basis_line,
)

from cfc_parser import (  # noqa: E402
    CFC_ENTRY_PATTERN,
    CFC_FIELD_ORDER,
    CFC_FIELD_PATTERNS,
    CFC_HEADER_PATTERN,
    CFC_PARTICIPATING_VALUE_PATTERN,
    FEATURE_ID_WORD_PATTERN,
    PLAN_FEATURE_ID_PATTERN as PLAN_FEATURE_ID_LINE,
    TASKS_CHECKBOX_CFC_PATTERN as TASKS_CHECKBOX_WITH_CFC,
    CFCEntry as _SharedCFCEntry,
    detect_near_miss_cfc_header,
    extract_cfc_section,
    extract_cfc_tags,
    feature_breakdown_numbers,
    normalize_for_hash as _normalize_for_hash,
    parse_cfc_entries as _shared_parse_cfc_entries,
)
from arch_config import (  # noqa: E402
    find_project_root as arch_find_project_root,
    parse_arch_token,
    write_arch_config,
)
from downstream_ref_guard import PolicyConfig, scan_for_downstream_refs  # noqa: E402
from spec_dirname import (  # noqa: E402
    SLUGIFY_CLI_HINT,
    classify_dirname,
    display_safe,
    parse_feature_number,
)

# Imported as a MODULE (not `from … import`) so the `**Implemented by:**`
# positional parser reuses master_feature's feature-block boundary detection
# (`iter_feature_blocks` enumerates every `### F<n>` block in one pass) rather
# than re-deriving a second inline `### F<n>` boundary regex here. The structural
# test `test_implemented_by_reuses_master_feature_boundary` asserts this (mirrors
# test_no_inline_dirname_regexes_in_validators).
import master_feature  # noqa: E402

# Shared cross-project-derivation grammar + sibling registry (CPD). Imported for
# the derived-dir exclusion in the coverage walk: `parse_derived_dirname` pulls
# the master-project prefix from a `<project>--F<n>-<slug>` directory and
# `find_sibling` decides whether a matching master sibling is configured.
import project_link  # noqa: E402
import project_registry  # noqa: E402
from run_state import derive_run_state, format_run_state, safe_print  # noqa: E402

# Stack vocabulary the blueprint may declare. Mirrors validate_spec.py's
# LANGUAGE_PROFILES keys; kept as a literal here (project-blueprint does not
# import the consumer) and asserted equal by the arch-config contract test, so a
# divergence is caught mechanically rather than drifting silently.
KNOWN_ARCH_TOKENS = ["python", "java", "generic"]


# ---------------------------------------------------------------------------
# Required sections per phase
# ---------------------------------------------------------------------------

SCOPE_REQUIRED_SECTIONS = [
    "Problem Statement",
    "Target Users",
    "Goals",
    "Non-Goals",
    "Constraints",
    "Success Criteria",
    "Panel Review",
]

ARCHITECTURE_REQUIRED_SECTIONS = [
    "System Overview",
    "Components",
    "Component Interactions",
    "Technology Choices",
    "Data Architecture",
    "External Dependencies",
    "Risks",
    "Panel Review",
]

PLAN_REQUIRED_SECTIONS = [
    "Feature Breakdown",
    "MVP Definition",
    "Feature Dependencies",
    "Implementation Order",
    "Milestones",
    "Panel Review",
]

# Feature `### F<n>:` headings are now resolved through cfc_parser's shared
# feature_breakdown_numbers() (scoped to ## Feature Breakdown) so the producer
# and consumer agree on which features exist (audit R2.3).

# Regex to match component entries like "### Component Name"
COMPONENT_ENTRY_PATTERN = re.compile(r"^###\s+\S+", re.MULTILINE)

# Regex to match feature IDs referenced in dependency/order tables
FEATURE_ID_PATTERN = re.compile(r"\bF(\d+)\b")

# Blueprint-tier policy for the shared downstream-identifier guard (F<n>; minted in
# 03_PLAN.md). v1: heading form blocks --approve, bare token is a non-blocking WARN.
BLUEPRINT_DOWNSTREAM_POLICY = PolicyConfig(
    letter="F",
    heading_warn_only=False,
    bare_warn_only=True,
    troubleshooting_ref=(
        "See project-blueprint/references/troubleshooting.md "
        "'Downstream identifier in upstream artifact'."
    ),
    noun="feature",
    downstream_artifact="03_PLAN.md",
)

# Regex to match component references in feature breakdown
FEATURE_COMPONENT_REF = re.compile(r"\*\*Component:\*\*\s*(.+)")

# Regex to match acceptance criteria in features
FEATURE_ACCEPTANCE_CRITERIA = re.compile(r"\*\*Acceptance Criteria:\*\*", re.IGNORECASE)

# Regex to match risk entries in tables
RISK_ENTRY_PATTERN = re.compile(r"\|\s*R\d+\s*\|")

# ---------------------------------------------------------------------------
# `**Implemented by:**` — optional per-feature cross-project delegation field (I8)
# ---------------------------------------------------------------------------
#
# A master PLAN feature MAY carry `**Implemented by:** <project-alias>` to mark
# that the feature is implemented in a sibling (derived) repo. The value grammar
# is a lowercase-kebab project alias (same as a `<project>` alias elsewhere in
# CPD). Parsing is POSITIONAL — each occurrence binds to the `### F<n>` block it
# sits inside; an occurrence in the PLAN preamble (before the first `### F<n>`)
# attaches to no feature and is silently ignored. Absence is silent (the normal
# "implemented locally" case). The field is single-valued per feature.
#
# Two patterns: a PRESENCE detector that matches any `**Implemented by:**` line
# regardless of value (so a malformed value is still caught, not silently
# dropped), and the STRICT matcher (I8) that accepts only a well-formed
# lowercase-kebab alias (optionally backtick-wrapped).
#
# Both accept an OPTIONAL `- `/`* ` bullet prefix — the canonical PLAN layout
# (design "Master side" data model) writes the field as a bullet, and the
# consumers (`reconcile.IMPLEMENTED_BY_LINE_RE`, `master_feature._IMPLEMENTED_BY_LINE`)
# match the bulleted form, so the producer-side validator must agree or the
# malformed/duplicate gates would never fire on a correctly-authored PLAN.
IMPLEMENTED_BY_LINE = re.compile(
    r"^[ \t]*(?:[-*][ \t]+)?\*\*Implemented by:\*\*[ \t]*(.*?)[ \t]*$", re.MULTILINE
)
IMPLEMENTED_BY_PATTERN = re.compile(
    r"^[ \t]*(?:[-*][ \t]+)?\*\*Implemented by:\*\*\s*(`?)([a-z0-9]+(?:-[a-z0-9]+)*)\1\s*$",
    re.MULTILINE,
)


def _parse_implemented_by(content: str, result: ValidationResult) -> dict[int, str]:
    """Validate every `**Implemented by:**` field in PLAN.md, positionally.

    Returns ``{feature_number: project_alias}`` for each WELL-FORMED, singular
    occurrence bound to a feature block. Emits:
      * FAIL ``implemented-by-malformed`` — value empty / wrong-case / bad char
        (does not match the lowercase-kebab alias grammar).
      * FAIL ``implemented-by-duplicate`` — two `**Implemented by:**` lines in
        ONE `### F<n>` block (the field is single-valued per feature, I8).

    Preamble occurrences (before the first `### F<n>`) attach to no feature and
    are silently ignored. Absence is silent.

    Block scoping REUSES master_feature's boundary detection: every `### F<n>`
    block is produced in a SINGLE pass by ``master_feature.iter_feature_blocks``
    — no second inline `### F<n>` boundary regex lives here (asserted
    structurally), and no per-feature re-scan of the whole PLAN (the prior
    `_find_feature_block`-per-heading loop was O(M·len(PLAN))).

    Any `**Implemented by:**` line before the first feature heading attaches to
    no feature → silently ignored (it is not in any feature's scope, because it
    is not inside a returned block).
    """
    implemented_by: dict[int, str] = {}

    seen_numbers: set[int] = set()
    for number, block in master_feature.iter_feature_blocks(content):
        if number in seen_numbers:
            # The same feature number heading appearing twice is a separate
            # concern handled elsewhere; process each block once for this field.
            continue
        seen_numbers.add(number)

        occurrences = list(IMPLEMENTED_BY_LINE.finditer(block))
        if not occurrences:
            continue  # absence is silent

        if len(occurrences) > 1:
            result.add(
                f"PLAN.md F{number} has a single `**Implemented by:**` value",
                False,
                f"F{number} has {len(occurrences)} `**Implemented by:**` lines; "
                f"the field is single-valued per feature. Code: "
                f"implemented-by-duplicate. Remove the extra line(s).",
            )
            continue

        raw_value = occurrences[0].group(1)
        strict = IMPLEMENTED_BY_PATTERN.match(occurrences[0].group(0))
        if strict is None:
            result.add(
                f"PLAN.md F{number} `**Implemented by:**` value is well-formed",
                False,
                f"F{number} `**Implemented by:**` value "
                f"'{display_safe(raw_value)}' is not a valid lowercase-kebab "
                f"project alias (e.g. `vps-edge`). Code: implemented-by-malformed.",
            )
            continue

        implemented_by[number] = strict.group(2)

    return implemented_by


# ---------------------------------------------------------------------------
# Cross-Feature Contracts (CFC) — producer-side validation
# ---------------------------------------------------------------------------
#
# The ## Cross-Feature Contracts section in PLAN.md is OPTIONAL. When present,
# each ### CFC-N: <title> subsection has four required fields in order:
#   - **Participating features:** F1, F3, F5
#   - **Contract:** <free prose>
#   - **Per-feature AC:** <verbatim AC line>
#   - **Enforcement:** <free prose, naming owning feature as F<n> verbatim>
#
# Parser primitives — CFCEntry, the regex constants, extract_cfc_section,
# parse_cfc_entries, detect_near_miss_cfc_header, extract_cfc_tags,
# normalize_for_hash — live in `telescoping-sdd/scripts/cfc_parser.py` and are
# imported above. Producer-specific extensions (structured_content_hash,
# soft-WARN keyword regex) live below.
#
# See documentation/CFC.md for the full spec and references/plan-template.md
# for the producer-side authoring contract.

# Enforcement-keyword set for the owner-silent WARN. Anchored to noun-context
# to avoid false positives on bare "check" / "hook" in plain English.
CFC_ENFORCEMENT_KEYWORDS = re.compile(
    r"\b(ArchUnit rule|CI (?:check|workflow|grep)|integration test|"
    r"runbook gate|pre-commit hook|ArchUnit)\b",
    re.IGNORECASE,
)


class CFCEntry(_SharedCFCEntry):
    """Producer-side CFCEntry — adds structured_content_hash on top of the shared parser."""

    def structured_content_hash(self) -> str:
        """Return a stable hash over the CFC's structured content.

        Hash inputs (per CFC.md): sorted-and-deduped Participating-features
        list, whitespace-normalized Per-feature AC, and whitespace-normalized
        Enforcement text. Contract prose is excluded — it's free-form
        rationale, not a binding clause. Reordering participating features
        in the source yields the same hash (sorted before hashing).
        Deduping is per P2-9: an authoring cosmetic fix that removes an
        accidental duplicate (`F1, F1` → `F1`) must not produce a spurious
        `orphaned-stale-content` WARN.

        Returns the SHA-256 hexdigest of the canonical-form serialization.
        """
        participating = sorted(set(self.participating_features()))
        per_feature_ac = _normalize_for_hash(self.fields.get("Per-feature AC") or "")
        enforcement = _normalize_for_hash(self.fields.get("Enforcement") or "")
        canonical = json.dumps(
            {
                "n": self.number,
                "participating": participating,
                "per_feature_ac": per_feature_ac,
                "enforcement": enforcement,
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_cfc_entries(section_body: str) -> list[CFCEntry]:
    """Parse all ### CFC-N entries from a section body — returns producer-side CFCEntry subclass."""
    shared_entries = _shared_parse_cfc_entries(section_body)
    return [
        CFCEntry(number=e.number, title=e.title, body=e.body)
        for e in shared_entries
    ]


# ---------------------------------------------------------------------------
# Spec.md / design.md / tasks.md helpers for bound-spec classification
# ---------------------------------------------------------------------------
#
# The PLAN-side validator walks specs/F<n>/ to determine each feature's
# bound state (not-started / pre-Phase-1 / in-flight / shipped) and to
# collect [CFC-N] tag bindings. See CFC.md § Bound-spec detection.

# PLAN_FEATURE_ID_LINE and TASKS_CHECKBOX_WITH_CFC are imported from cfc_parser
# (the shared format owner) under their historical local names — the producer and
# consumer no longer compile separate copies of these cross-skill seam grammars
# (audit R2.3).
# `APPROVAL_HEADER` / `APPROVAL_CHECKBOX` are retained here because
# `_approval_section_slice` and `check_approval` (below) still use them. The
# approval-detection HELPERS (`has_approval`, `approval_hash`,
# `approval_hash_matches`, `all_tasks_ticked`, `is_shipped`) and the file
# `read_file` were RELOCATED into `blueprint_common.py` (CPD T9a / I9) so
# `reconcile.py` can derive the same shipped verdict without importing this skill
# validator. This validator imports back the ones it CALLS (`approval_hash_matches`,
# `is_shipped_from_contents`, `read_file`) plus `approval_hash` / `has_approval`,
# which it RE-EXPORTS for `render_business_brief` (pinned by test_cli_integration).
# The narrow
# content-hash line is the SHARED `blueprint_common.APPROVAL_HASH_LINE_STRICT`
# (imported as `APPROVAL_HASH_LINE`) so both validators key on ONE object;
# blueprint_common keeps a DISTINCT broad copy (capturing any backtick body) for
# read_stored_hash — deliberately not unified with the narrow gate.
# `APPROVAL_HEADER` is the SHARED `blueprint_common._APPROVAL_HEADER` (imported
# above) — the blueprint-local duplicate was DELETED so the `## Approval` header
# regex has ONE source (AD8); `_approval_section_slice` now delegates to the
# shared `approval_section_bounds`.
# Strict form: `- [x] Approved to proceed`. Per P3-8 from the
# post-implementation review, the prior loose `-\s*\[(x|X)\]` matched any
# checked box anywhere, which would have false-positived if a spec ever
# added an unrelated `- [x] <something>` sub-checkbox under `## Approval`.
APPROVAL_CHECKBOX = re.compile(r"- \[[xX]\] Approved to proceed")
APPROVAL_HASH_LINE = APPROVAL_HASH_LINE_STRICT


def spec_then_line_cfc_tags(spec_content: str) -> list[int]:
    """Return CFC numbers tagged on THEN lines inside spec.md acceptance criteria."""
    return extract_cfc_tags(spec_content)


def tasks_checkbox_cfc_tags(tasks_content: str) -> list[int]:
    """Return CFC numbers tagged on tasks.md checkbox lines."""
    return [int(m.group(1)) for m in TASKS_CHECKBOX_WITH_CFC.finditer(tasks_content)]


def parse_plan_feature_identifier(spec_content: str) -> Optional[str]:
    """Return the `**PLAN feature identifier:**` value as `F<n>` or `n/a`, or None if absent/malformed."""
    m = PLAN_FEATURE_ID_LINE.search(spec_content)
    if m is None:
        return None
    return m.group(1)


# ---------------------------------------------------------------------------
# Bound-spec classification + coverage walk + orphan-tag scan
# ---------------------------------------------------------------------------
#
# These run at PLAN validation (and at --approve plan) to give the PLAN
# author visibility into:
#   (a) which features are bound to which CFCs (coverage walk)
#   (b) which specs carry orphaned [CFC-N] tags (orphan-tag scan)
#
# See CFC.md § Bound-spec detection for the four-state classification and
# the orphan subtypes (orphaned-missing / orphaned-departed / orphaned-stale-content).

# Class names match the strings in CFC.md so the report output and the
# documented behavior stay in sync.
STATE_NOT_STARTED = "not-started"
STATE_PRE_PHASE_1 = "pre-Phase-1"
STATE_IN_FLIGHT = "in-flight"
STATE_SHIPPED = "shipped"


class SpecState:
    """Classification of a feature's spec directory and the artifacts in it."""

    def __init__(
        self,
        feature_id: int,
        spec_dir: Path,
        state: str,
        cfc_tags_in_spec: list[int],
        cfc_tags_in_tasks: list[int],
        spec_content: Optional[str],
        tasks_content: Optional[str],
    ):
        self.feature_id = feature_id
        self.spec_dir = spec_dir
        self.state = state  # one of STATE_*
        self.cfc_tags_in_spec = cfc_tags_in_spec
        self.cfc_tags_in_tasks = cfc_tags_in_tasks
        self.spec_content = spec_content
        self.tasks_content = tasks_content

    @property
    def is_bound(self) -> bool:
        """A spec is bound if it has shipped — Phase 4 complete."""
        return self.state == STATE_SHIPPED


def classify_spec(spec_dir: Path) -> SpecState:
    """Classify the feature's spec into one of the four bound-detection states.

    Per CFC.md § Bound-spec detection:
      - not-started: spec.md missing
      - pre-Phase-1: spec.md exists, no ## Approval (or hash stale)
      - in-flight: spec.md approved, Phase 4 not yet complete
      - shipped: all phases approved + all tasks ticked + tasks.md hash matches content
    """
    # Feature number via the shared grammar: bound (F<n>-<slug>) and bare
    # (F<n>) forms both resolve to their int; standalone/invalid names -> None,
    # adapted to the existing -1 sentinel. SpecState.feature_id is typed int and
    # used as a sort key and dict key, so it must NEVER be None (a None would
    # raise TypeError on the sort and misbehave as a membership/dict key).
    fid = parse_feature_number(spec_dir.name)
    feature_id = fid if fid is not None else -1

    spec_path = resolve_artifact(spec_dir, "spec.md")
    design_path = resolve_artifact(spec_dir, "design.md")
    tasks_path = resolve_artifact(spec_dir, "tasks.md")

    spec_content = read_file(spec_path)
    if spec_content is None:
        return SpecState(
            feature_id=feature_id,
            spec_dir=spec_dir,
            state=STATE_NOT_STARTED,
            cfc_tags_in_spec=[],
            cfc_tags_in_tasks=[],
            spec_content=None,
            tasks_content=None,
        )

    cfc_in_spec = spec_then_line_cfc_tags(spec_content)
    tasks_content = read_file(tasks_path)
    cfc_in_tasks = (
        tasks_checkbox_cfc_tags(tasks_content) if tasks_content else []
    )

    # Phase 1 approved?
    if not approval_hash_matches(spec_content):
        return SpecState(
            feature_id=feature_id,
            spec_dir=spec_dir,
            state=STATE_PRE_PHASE_1,
            cfc_tags_in_spec=cfc_in_spec,
            cfc_tags_in_tasks=cfc_in_tasks,
            spec_content=spec_content,
            tasks_content=tasks_content,
        )

    # Spec.md approved. Check design.md and tasks.md.
    design_content = read_file(design_path)
    design_approved = bool(
        design_content and approval_hash_matches(design_content)
    )
    tasks_approved = bool(
        tasks_content and approval_hash_matches(tasks_content)
    )

    if not (design_approved and tasks_approved):
        # In-flight: spec is approved but at least one downstream artifact
        # is not yet at a coherent approved state.
        return SpecState(
            feature_id=feature_id,
            spec_dir=spec_dir,
            state=STATE_IN_FLIGHT,
            cfc_tags_in_spec=cfc_in_spec,
            cfc_tags_in_tasks=cfc_in_tasks,
            spec_content=spec_content,
            tasks_content=tasks_content,
        )

    # All three artifacts approved. Shipped iff every task box is ticked AND
    # tasks.md's approval hash matches current content (derived-coherence
    # per CFC.md Q4). The matching hash IS the ship signal — no separate
    # ceremony marker needed. Derive the verdict from the SHARED
    # `blueprint_common.is_shipped_from_contents` (the relocated full
    # STATE_SHIPPED condition) so this validator and `reconcile.py` cannot
    # drift on what "shipped" means. The contents were already read above; pass
    # them in to avoid a second disk read. (is_shipped_from_contents re-checks
    # the spec/design/tasks approval clauses — all True at this point — so the
    # result is identical to the prior inline `all_tasks_ticked AND
    # approval_hash_matches(tasks)` check, including the tasks_content-None →
    # in-flight guard.)
    state = (
        STATE_SHIPPED
        if is_shipped_from_contents(spec_content, design_content, tasks_content)
        else STATE_IN_FLIGHT
    )

    return SpecState(
        feature_id=feature_id,
        spec_dir=spec_dir,
        state=state,
        cfc_tags_in_spec=cfc_in_spec,
        cfc_tags_in_tasks=cfc_in_tasks,
        spec_content=spec_content,
        tasks_content=tasks_content,
    )


def _classified_spec_entries(project_root: Path) -> list[tuple[Path, str]]:
    """Walk specs/ ONCE and return ``(entry, classify_dirname(entry.name))`` for
    each non-symlink subdirectory, sorted by name.

    Single source of the specs/ listing + per-entry classification, so both
    spec_states derivation (`_states_from_entries`) and the malformed-dirname
    WARNs (`_emit_malformed_dirname_warns`) run off ONE walk instead of each
    iterating and re-classifying every entry (they were two separate walks
    before). Symlinks are skipped before classification — they can point outside
    the project tree, and following them would let a stray symlink coerce the
    validator into reading arbitrary files.
    """
    specs_root = project_root / "specs"
    if not specs_root.is_dir():
        return []
    try:
        entries = sorted(specs_root.iterdir())
    except OSError:
        return []
    classified: list[tuple[Path, str]] = []
    for entry in entries:
        if entry.is_symlink() or not entry.is_dir():
            continue
        classified.append((entry, classify_dirname(entry.name)))
    return classified


def _states_from_entries(entries: list[tuple[Path, str]]) -> list[SpecState]:
    """Build the SpecState list from pre-classified specs/ entries, sorted by
    feature_id ascending. Admits "bound" (F<n>-<slug>) and "bare" (F<n>,
    backward-compat); skips "standalone" (correctly not a PLAN-bound feature),
    "derived" (a CPD cross-project link — handled by `_emit_derived_dir_warns`,
    never a LOCAL PLAN-bound feature), and "invalid" (surfaced as a
    malformed-spec-dirname WARN instead).

    The "derived" skip is an EXPLICIT branch (not an accidental membership
    fall-through) so a future change to the admitted-category set cannot silently
    pull a `<project>--F<n>-<slug>` directory into local PLAN coverage.
    """
    states: list[SpecState] = []
    for entry, category in entries:
        if category in ("bound", "bare"):
            states.append(classify_spec(entry))
        elif category == "derived":
            # A CPD derived-form directory is a cross-project link, NOT a local
            # PLAN feature; it is excluded from coverage here and routed to
            # `_emit_derived_dir_warns` for the sibling-gated informational WARN.
            continue
        # "standalone" and "invalid" are skipped / warned separately.
    return sorted(states, key=lambda s: s.feature_id)


def walk_specs(project_root: Path) -> list[SpecState]:
    """Walk every PLAN-bound spec directory under project_root and classify each.

    Dispatches on `classify_dirname` (the single shared grammar dispatch point):
      * "bound" (F<n>-<slug>) — admitted.
      * "bare" (F<n>) — admitted for backward-compatibility (pre-1.7.0 form);
        `_emit_malformed_dirname_warns` surfaces a migration WARN separately.
      * "standalone" (<slug>) — skipped silently (a valid standalone feature is
        correctly NOT a PLAN-bound feature).
      * "invalid" — skipped silently (WARN emitted separately in validate_plan).

    Returns a list ordered by feature ID ascending. Implemented over the shared
    single-walk `_classified_spec_entries`, so `validate_plan` can derive both
    the SpecStates and the malformed-dirname WARNs from one walk. Symlinks are
    skipped before classification (see `_classified_spec_entries`). Kept as a
    standalone helper because tests classify a specs/ tree directly via it.
    """
    return _states_from_entries(_classified_spec_entries(project_root))


def _emit_malformed_dirname_warns(
    entries: list[tuple[Path, str]], result: ValidationResult
) -> None:
    """Emit a `malformed-spec-dirname` WARN for each bare-token or invalid spec
    directory, from the pre-classified `_classified_spec_entries` list (shares
    the single specs/ walk with spec_states derivation, so walk and warn read
    the SAME classification — they can never disagree on a directory's category).

    "bare" (F<n>, incl. F0/F007) and "invalid" (e.g. My_Feature) earn a WARN;
    "bound" and "standalone" are silent. WARN (not FAIL) keeps backward-
    compatible bare-token directories in the coverage map while surfacing the
    migration prompt. Embedded directory names are escaped via
    `spec_dirname.display_safe` (the shared spoofing guard).
    """
    for entry, category in entries:
        if category not in ("bare", "invalid"):
            continue
        escaped = display_safe(entry.name)
        if category == "bare":
            # Suggest the CANONICAL bound rename: parse_feature_number strips a
            # leading zero (F03 -> 3). Feature 0 (F0/F00) has no valid bound form
            # (bound names start at F1), so steer those to n>=1 or a standalone.
            num = parse_feature_number(entry.name)
            if num and num >= 1:
                rename_to = f"'F{num}-<slug>' (e.g. 'F{num}-checkout-flow')"
            else:
                rename_to = (
                    "'F<n>-<slug>' with n >= 1 (feature numbers start at F1), or to "
                    "a bare '<slug>' for a standalone feature"
                )
            detail = (
                f"'specs/{escaped}' uses the old bare-token form. Rename to "
                f"{rename_to}. To generate a slug, run:\n  {SLUGIFY_CLI_HINT}\n"
                f"Renaming does not invalidate any existing approval or content hash."
            )
        else:  # "invalid"
            detail = (
                f"'specs/{escaped}' is not a valid spec directory name and will "
                f"not be included in feature resolution. Rename to 'F<n>-<slug>' "
                f"(if bound to a PLAN feature) or '<slug>' (standalone). To "
                f"generate a slug, run:\n  {SLUGIFY_CLI_HINT}"
            )
        result.add("malformed-spec-dirname", False, detail, warn_only=True)


def _emit_derived_dir_warns(
    entries: list[tuple[Path, str]],
    registry: Optional[dict],
    project_root: Path,
    result: ValidationResult,
) -> None:
    """Emit an informational WARN for each CPD derived-form directory whose master
    project has NO matching sibling configured in `.sdd/projects.json` (AD6).

    A `<project>--F<n>-<slug>` directory is excluded from local PLAN coverage by
    `_states_from_entries` (it is a cross-project link, not a local feature). That
    exclusion is sibling-GATED: silent exclusion is correct only when a matching
    master sibling is configured, so a fat-fingered `--` in a NATIVE feature name
    is not silently swallowed. When no matching sibling is found, this surfaces an
    informational WARN (`derived-dir-no-sibling`, warn_only) naming the master
    project and asking if the derivation was intentional.

    "Matching" is role-INDEPENDENT (R6): a `siblings[].name` equal to the derived
    dir's `<project>` prefix, regardless of the sibling's recorded `role`.
    `find_sibling` already returns the resolved sibling path only when the name
    matches AND the accept-gate passes, so a `None` here means "no matching,
    resolvable sibling root" — exactly the case the WARN exists for.

    `registry` is read ONCE by the caller (`validate_plan`) and passed in; this
    helper never re-reads `.sdd/projects.json` per directory. Embedded directory
    and project names are escaped via `display_safe` (the shared spoofing guard).
    """
    for entry, category in entries:
        if category != "derived":
            continue
        parsed = project_link.parse_derived_dirname(entry.name)
        if parsed is None:
            # Defensive: a "derived" classification implies the name parses, but
            # if the two grammars ever drift, fall back to the malformed-dirname
            # walk rather than emitting a half-formed derived WARN.
            continue
        master_project, _, _ = parsed
        sibling_path = project_registry.find_sibling(
            registry, master_project, project_root
        )
        if sibling_path is None:
            result.add(
                "derived-dir-no-sibling",
                False,
                f"'specs/{display_safe(entry.name)}' looks like a derived spec "
                f"(master project '{display_safe(master_project)}') but no "
                f"matching sibling is configured in .sdd/projects.json — is this "
                f"intentional? If it is a native feature with a stray '--' in its "
                f"name, rename it; otherwise add the master project to "
                f".sdd/projects.json.",
                warn_only=True,
            )
        # else: a matching sibling is configured → silently excluded from coverage.


def _emit_duplicate_feature_dir_warns(
    spec_states: list[SpecState], result: ValidationResult
) -> None:
    """Emit a `duplicate-feature-dir` WARN for each feature_id shared by two or
    more walked spec directories (e.g. specs/F3-alpha/ + specs/F3/, or two bound
    dirs specs/F3-alpha/ + specs/F3-beta/).

    The lenient `parse_feature_number` admits both forms as the same id, which
    would silently drop one entry from any id-keyed dict — exactly the
    silent-skip class this feature exists to kill. Builds its OWN id->dirs map
    (it must NOT rely on `compute_coverage`'s `state_by_id`, which is built
    inside a conditional that may not run). Both names are escaped via
    unicode_escape. Call exactly once at the post-`if/else` join, OUTSIDE the
    subsequent `if cfc_entries or has_any_cfc_tags:` coverage block.
    """
    by_id: dict[int, list[str]] = {}
    for s in spec_states:
        if s.feature_id == -1:
            continue
        by_id.setdefault(s.feature_id, []).append(s.spec_dir.name)
    for fid, names in by_id.items():
        if len(names) < 2:
            continue
        escaped = ", ".join(f"'{display_safe(n)}'" for n in sorted(names))
        detail = (
            f"feature id {fid} is claimed by multiple spec directories: {escaped}. "
            f"Each PLAN feature must map to exactly one spec directory — rename or "
            f"remove the duplicates so the feature resolves unambiguously."
        )
        result.add("duplicate-feature-dir", False, detail, warn_only=True)


class CFCCoverage:
    """Coverage state per CFC.

    `feature_states` maps a participating feature's ID to one of:
      * "tagged-in-flight" — spec.md approved, carries the [CFC-N] tag, but
        feature has not shipped (Phase 4 incomplete).
      * "tagged-shipped" — spec.md approved, carries the [CFC-N] tag, AND
        the feature has shipped (Phase 4 complete; immutable).
      * "approved-no-tag" — spec.md approved, feature is in flight or
        shipped, but the [CFC-N] tag is missing. This is a binding gap.
      * "pre-Phase-1" — spec.md exists but is not yet approved.
      * "not-started" — no spec.md.

    Per P3-9 (renamed legacy "bound" to "tagged-*" to disambiguate from
    `STATE_SHIPPED`) and P3-10 (in-flight vs shipped distinction now
    surfaced) from the post-implementation code review.
    """

    def __init__(self, cfc_number: int):
        self.cfc_number = cfc_number
        self.participating: list[int] = []
        self.feature_states: dict[int, str] = {}

    @property
    def status(self) -> str:
        """One of 'fully-bound' / 'partially-bound' / 'unbound'.

        A feature is "covered" for this CFC if its spec is approved AND carries
        the [CFC-N] tag on a THEN line (either tagged-in-flight or
        tagged-shipped — both count). In-flight-untagged / pre-Phase-1 /
        not-started are all "not covered."
        """
        if not self.participating:
            return "unbound"
        covered = sum(
            1 for fid in self.participating
            if self.feature_states.get(fid) in ("tagged-in-flight", "tagged-shipped")
        )
        if covered == 0:
            return "unbound"
        if covered == len(self.participating):
            return "fully-bound"
        return "partially-bound"


def compute_coverage(
    cfc_entries: list[CFCEntry], spec_states: list[SpecState]
) -> list[CFCCoverage]:
    """Compute per-CFC coverage from CFC entries + walked spec states."""
    state_by_id = {s.feature_id: s for s in spec_states}
    coverages: list[CFCCoverage] = []
    for entry in cfc_entries:
        cov = CFCCoverage(entry.number)
        cov.participating = entry.participating_features()
        for fid in cov.participating:
            spec = state_by_id.get(fid)
            if spec is None:
                cov.feature_states[fid] = "not-started"
                continue
            if spec.state == STATE_NOT_STARTED:
                cov.feature_states[fid] = "not-started"
            elif spec.state == STATE_PRE_PHASE_1:
                cov.feature_states[fid] = "pre-Phase-1"
            else:
                # Approved at the spec.md level (in-flight or shipped). Check
                # for the [CFC-N] tag binding on a THEN line, and surface
                # the in-flight-vs-shipped distinction so the PLAN author
                # can judge urgency (per P3-10).
                if entry.number in spec.cfc_tags_in_spec:
                    if spec.state == STATE_SHIPPED:
                        cov.feature_states[fid] = "tagged-shipped"
                    else:
                        cov.feature_states[fid] = "tagged-in-flight"
                else:
                    cov.feature_states[fid] = "approved-no-tag"
        coverages.append(cov)
    return coverages


class OrphanTag:
    """One orphaned [CFC-N] tag found by the orphan-tag scan."""

    def __init__(
        self,
        spec_dir: Path,
        artifact: str,  # 'spec.md' or 'tasks.md'
        cfc_number: int,
        subtype: str,  # 'orphaned-missing' / 'orphaned-departed' / 'orphaned-stale-content'
        message: str,
    ):
        self.spec_dir = spec_dir
        self.artifact = artifact
        self.cfc_number = cfc_number
        self.subtype = subtype
        self.message = message


def scan_orphan_tags(
    cfc_entries: list[CFCEntry],
    spec_states: list[SpecState],
    prior_cfc_hashes: dict[int, str],
) -> list[OrphanTag]:
    """Find all [CFC-N] tags in walked specs that no longer resolve cleanly.

    Three subtypes (per CFC.md):
      - orphaned-missing: tag references a CFC number not present in current PLAN
      - orphaned-departed: CFC exists but the spec's feature is no longer Participating
      - orphaned-stale-content: CFC exists, feature still Participating, but the
        CFC's structured content hash differs from prior_cfc_hashes[N]

    prior_cfc_hashes: per-CFC content hashes from the prior PLAN approval (empty
    on the first PLAN approval; orphaned-stale-content never fires until the
    second PLAN approval).
    """
    orphans: list[OrphanTag] = []
    entry_by_number = {e.number: e for e in cfc_entries}

    for spec in spec_states:
        # Bound-state filter: skip not-started and pre-Phase-1 — they have
        # nothing approved to orphan.
        if spec.state in (STATE_NOT_STARTED, STATE_PRE_PHASE_1):
            continue

        # Collect all tag occurrences from spec.md and tasks.md.
        for artifact_name, tags in (
            ("spec.md", spec.cfc_tags_in_spec),
            ("tasks.md", spec.cfc_tags_in_tasks),
        ):
            seen_in_artifact: set[int] = set()
            for n in tags:
                if n in seen_in_artifact:
                    continue
                seen_in_artifact.add(n)
                entry = entry_by_number.get(n)
                if entry is None:
                    # orphaned-missing — try to suggest near matches.
                    suggestions = _nearest_cfc_numbers(n, entry_by_number.keys())
                    sugg_text = (
                        f" — did you mean {', '.join(f'CFC-{s}' for s in suggestions)}?"
                        if suggestions
                        else ""
                    )
                    orphans.append(
                        OrphanTag(
                            spec_dir=spec.spec_dir,
                            artifact=artifact_name,
                            cfc_number=n,
                            subtype="orphaned-missing",
                            message=(
                                f"{spec.spec_dir.name}/{artifact_name} carries "
                                f"[CFC-{n}] which has no matching CFC in current PLAN"
                                f"{sugg_text}"
                            ),
                        )
                    )
                    continue
                # CFC exists; check membership. The rule differs per artifact:
                #   - spec.md tags signal "this feature participates in the
                #     contract", so Participating membership is required.
                #   - tasks.md tags signal "this feature works on the
                #     contract" — which is legitimate for either a Participating
                #     feature OR an Enforcement-owner feature (the feature
                #     named in the Enforcement prose may not itself be a
                #     Participating member; e.g., F36 owning the ArchUnit
                #     rule that verifies F2/F11's writes — F36 isn't in
                #     Participating but does carry the [CFC-N] tag on the
                #     task implementing the rule).
                # Per P1-1 from the post-implementation code review.
                participating = entry.participating_features()
                enforcement_owners = entry.enforcement_owners()
                if strip_artifact_prefix(artifact_name) == "tasks.md":
                    is_legitimate_holder = (
                        spec.feature_id in participating
                        or spec.feature_id in enforcement_owners
                    )
                else:
                    is_legitimate_holder = spec.feature_id in participating
                if not is_legitimate_holder:
                    orphans.append(
                        OrphanTag(
                            spec_dir=spec.spec_dir,
                            artifact=artifact_name,
                            cfc_number=n,
                            subtype="orphaned-departed",
                            message=(
                                f"{spec.spec_dir.name}/{artifact_name} carries "
                                f"[CFC-{n}] but F{spec.feature_id} is no longer "
                                f"in CFC-{n}'s Participating features"
                                + (
                                    " (and is not named as an Enforcement owner)"
                                    if strip_artifact_prefix(artifact_name) == "tasks.md"
                                    else ""
                                )
                                + " — remove the tag (allowed metadata edit), or "
                                f"restore F{spec.feature_id} to CFC-{n} if the "
                                "removal was unintended"
                            ),
                        )
                    )
                    continue
                # CFC exists; feature is still Participating; check content drift.
                current_hash = entry.structured_content_hash()
                prior_hash = prior_cfc_hashes.get(n)
                if prior_hash is not None and prior_hash != current_hash:
                    orphans.append(
                        OrphanTag(
                            spec_dir=spec.spec_dir,
                            artifact=artifact_name,
                            cfc_number=n,
                            subtype="orphaned-stale-content",
                            message=(
                                f"{spec.spec_dir.name}/{artifact_name} carries "
                                f"[CFC-{n}] bound at content hash {prior_hash[:12]}; "
                                f"CFC-{n}'s content hash has since changed to "
                                f"{current_hash[:12]}. "
                                f"{'Bound spec is shipped — immutable; remediation via new feature or unbound-spec absorption.' if spec.state == STATE_SHIPPED else 'Spec is in flight — amend in place via hash-and-cascade.'}"
                            ),
                        )
                    )

    return orphans


def _nearest_cfc_numbers(target: int, existing: list[int], k: int = 2) -> list[int]:
    """Return the up-to-k existing CFC numbers closest to target by absolute distance."""
    existing_list = sorted(existing, key=lambda n: (abs(n - target), n))
    return existing_list[:k]


# Per-CFC content hashes stored alongside PLAN.md's main approval hash.
# Stored as an indented sub-block under the `## Approval` section:
#
#   ## Approval
#
#   - [x] Approved to proceed to feature development
#   - **Content Hash:** `abc123...`
#   - **CFC Content Hashes:**
#     - CFC-1: `def456...`
#     - CFC-2: `ghi789...`
#
# The validator parses these at PLAN re-validation and uses them as the
# prior-state baseline for orphaned-stale-content detection. The
# `approve_document` flow re-computes them at every --approve plan.

CFC_HASH_BLOCK_HEADER = re.compile(
    r"^\s*-\s*\*\*CFC Content Hashes:\*\*\s*$", re.MULTILINE
)
CFC_HASH_LINE = re.compile(
    r"^\s*-\s*CFC-(\d+):\s*`([0-9a-fA-F]+)`\s*$", re.MULTILINE
)


def _approval_section_slice(content: str) -> Optional[tuple[int, int]]:
    """Return (body_start, body_end) bounding PLAN.md's `## Approval` section body, or None.

    body_start is the offset immediately after the `## Approval` header line;
    body_end is the offset of the next `## ` heading (or end-of-file if no
    later heading). Used by `read_cfc_hashes`, `_write_cfc_hash_block`, and
    `approve_document` to scope their regex operations to the Approval
    section body — without this scope, phantom `**Content Hash:**` lines or
    stray `- **CFC Content Hashes:**` sub-blocks anywhere else in PLAN.md
    can confuse the validator (silent data corruption + invalid baselines).

    Emits a stderr warning if the document contains more than one `## Approval`
    header — only the first is honoured for scope. A duplicate header would
    otherwise silently orphan hash state in the second section (per the
    light-touch verification pass, critic finding #1).

    Delegates to the shared `approval_section_bounds` (AD8) so the write-bounds
    here and the basis-line read-bounds in `read_hash_basis` are identical by
    construction — the single source of "where the `## Approval` section is".
    """
    return approval_section_bounds(content)


def read_cfc_hashes(plan_content: str) -> dict[int, str]:
    """Read per-CFC content hashes from PLAN.md's `## Approval` section.

    Returns an empty dict if the block is absent (which is the case on a
    first PLAN approval or for PLANs predating the CFC amendment). The scan
    is bounded to the `## Approval` section body — stray `- CFC-N:` lines
    elsewhere in PLAN.md are not considered baselines.
    """
    slice_range = _approval_section_slice(plan_content)
    if slice_range is None:
        return {}
    body_start, body_end = slice_range
    approval_body = plan_content[body_start:body_end]
    if not CFC_HASH_BLOCK_HEADER.search(approval_body):
        return {}
    return {
        int(m.group(1)): m.group(2)
        for m in CFC_HASH_LINE.finditer(approval_body)
    }


def render_cfc_hashes(cfc_entries: list[CFCEntry]) -> str:
    """Render per-CFC content hashes as a markdown sub-block under `- **CFC Content Hashes:**`.

    Returns the markdown lines (no leading newline). Empty string if there
    are no CFC entries.
    """
    if not cfc_entries:
        return ""
    lines = ["- **CFC Content Hashes:**"]
    for entry in sorted(cfc_entries, key=lambda e: e.number):
        lines.append(f"  - CFC-{entry.number}: `{entry.structured_content_hash()}`")
    return "\n".join(lines)


def validate_cfc_section(content: str, result: ValidationResult) -> list[CFCEntry]:
    """Run all soft validations on the ## Cross-Feature Contracts section.

    The section is optional — absence is not a failure. When present:
      - Each ### CFC-N entry must have the four required fields in order.
      - Participating features must match the strict regex.
      - CFC numbers must be unique within the document.
      - Owner-silent Enforcement prose emits a WARN.

    Returns the list of parsed CFC entries (possibly empty if the section is
    absent or contains no entries). Downstream coverage walk + orphan-tag
    scan consume this list.
    """
    # Near-miss header check fires even if no canonical header is found —
    # catches the silent-extractor-failure case from CFC.md P6.
    near_miss = detect_near_miss_cfc_header(content)
    if near_miss:
        result.add(
            "PLAN.md ## Cross-Feature Contracts header form",
            False,
            f"Header '{near_miss}' does not match canonical "
            f"'## Cross-Feature Contracts' form (case-sensitive, no trailing "
            f"colon, no extra whitespace). If you intended to declare a CFC "
            f"section, fix the header. If not, rename the section to avoid "
            f"the near-miss.",
        )
        return []

    section = extract_cfc_section(content)
    if section is None:
        # Section absent — optional, no failure.
        return []

    _start, _end, body = section
    from cfc_parser import parse_cfc_entries_with_malformed
    shared_entries, malformed = parse_cfc_entries_with_malformed(body)
    # Wrap into producer-side CFCEntry subclass (has structured_content_hash).
    entries = [
        CFCEntry(number=e.number, title=e.title, body=e.body)
        for e in shared_entries
    ]

    # Per P3-12: surface malformed CFC numbers (leading zero, `CFC-0`)
    # explicitly rather than silently dropping them. They would collide with
    # their canonical forms (`CFC-007` vs `CFC-7`) under int() parsing.
    for malformed_heading in malformed:
        result.add(
            f"PLAN.md CFC heading format: {malformed_heading.split(':')[0]}",
            False,
            f"CFC heading '{malformed_heading}' uses a non-canonical number "
            f"format (leading zero or zero). CFC numbers must be a canonical "
            f"decimal integer with no leading zeros and not zero (i.e., 1, 2, "
            f"3, ...). Renumber to the canonical form.",
        )

    # Empty section (header present, no CFC entries) — informational only.
    if not entries:
        result.add(
            "PLAN.md ## Cross-Feature Contracts section has entries",
            True,
            "Section present with no CFC entries (informational; no CFCs declared)",
            warn_only=True,
        )
        return entries

    # CFC number uniqueness — within current PLAN.md (no cross-history check).
    numbers_seen: dict[int, int] = {}
    for entry in entries:
        numbers_seen[entry.number] = numbers_seen.get(entry.number, 0) + 1
    duplicates = sorted(n for n, count in numbers_seen.items() if count > 1)
    if duplicates:
        labels = ", ".join(f"CFC-{n}" for n in duplicates)
        result.add(
            "PLAN.md CFC numbers are unique",
            False,
            f"Duplicate CFC number(s): {labels}",
        )
    else:
        result.add("PLAN.md CFC numbers are unique", True)

    # Referential integrity (R1.6): the set of features actually defined in PLAN
    # (its `### F<n>:` Feature Breakdown headings). Every feature a CFC names —
    # in Participating features or Enforcement prose — must be in this set. A
    # typo (F19 for F9) or a feature later deleted from PLAN otherwise yields a
    # contract that silently never binds anything: compute_coverage maps the
    # unknown id to 'not-started', a fully-unbound CFC is suppressed from output,
    # and the consumer can never catch it (the spec for a nonexistent feature
    # never exists). The "mechanically bound" guarantee must not fail open on a
    # one-character mistake.
    defined_features = set(feature_breakdown_numbers(content))

    # Per-entry field validation.
    for entry in entries:
        cfc_label = f"CFC-{entry.number}"

        # 1. Required fields present.
        missing = [
            name for name in CFC_FIELD_ORDER if entry.fields[name] is None
        ]
        if missing:
            result.add(
                f"PLAN.md {cfc_label} has all required fields",
                False,
                f"Missing required field(s): {', '.join(missing)}",
            )
        else:
            result.add(
                f"PLAN.md {cfc_label} has all required fields",
                True,
            )

        # 2. Field order.
        if not missing and entry.field_order_observed != list(CFC_FIELD_ORDER):
            result.add(
                f"PLAN.md {cfc_label} fields appear in canonical order",
                False,
                f"Expected order {list(CFC_FIELD_ORDER)}, "
                f"observed {entry.field_order_observed}",
            )
        elif not missing:
            result.add(
                f"PLAN.md {cfc_label} fields appear in canonical order",
                True,
            )

        # 3. Duplicate fields.
        for name, count in entry.field_duplicates.items():
            result.add(
                f"PLAN.md {cfc_label} field '{name}' appears more than once",
                False,
                f"Field '{name}' appears {count} times; "
                f"each field must appear exactly once",
            )

        # 4. Participating-features regex.
        if entry.fields["Participating features"] is not None:
            pf_value = entry.fields["Participating features"]
            if not CFC_PARTICIPATING_VALUE_PATTERN.match(pf_value):
                result.add(
                    f"PLAN.md {cfc_label} Participating features regex",
                    False,
                    f"Value '{pf_value}' does not match "
                    f"^F\\d+(, F\\d+)*$ (comma-separated F<n> tokens, "
                    f"no backticks, no other prose)",
                )
            else:
                # Check for duplicates within the list.
                ids = entry.participating_features()
                if len(ids) != len(set(ids)):
                    result.add(
                        f"PLAN.md {cfc_label} Participating features has no duplicates",
                        False,
                        f"Duplicate feature ID(s) in Participating features",
                    )
                else:
                    result.add(
                        f"PLAN.md {cfc_label} Participating features regex",
                        True,
                    )

        # 5. Owner-silent Enforcement WARN.
        enf_value = entry.fields["Enforcement"]
        if enf_value is not None:
            has_keyword = bool(CFC_ENFORCEMENT_KEYWORDS.search(enf_value))
            has_feature_token = bool(FEATURE_ID_WORD_PATTERN.search(enf_value))
            _enf_lower = enf_value.lower()
            has_explicit_disclaimer = any(
                phrase in _enf_lower
                for phrase in ("no owning feature", "co-owned", "no single owner", "no owner")
            )
            if has_keyword and not has_feature_token and not has_explicit_disclaimer:
                result.add(
                    f"PLAN.md {cfc_label} Enforcement names owning feature",
                    False,
                    "Enforcement prose mentions a verifying mechanism "
                    "but names no owning feature. Add F<n> verbatim, or "
                    "write a disclaimer ('no owning feature' / 'co-owned by "
                    "F<n>, F<m>' / 'no single owner' / 'no owner') explicitly "
                    "so the consumer-side task-analyst knows whose tasks.md "
                    "to bind.",
                    warn_only=True,
                )

        # 6. Referential integrity (R1.6): every named feature must be defined
        # in PLAN's Feature Breakdown. participating_features() returns [] on a
        # malformed Participating value (already FAILed at step 4), so this does
        # not double-report; enforcement_owners() returns every F<n> in the
        # Enforcement prose.
        named = set(entry.participating_features()) | set(entry.enforcement_owners())
        unknown = sorted(n for n in named if n not in defined_features)
        if unknown:
            labels = ", ".join(f"F{n}" for n in unknown)
            result.add(
                f"PLAN.md {cfc_label} references only defined features",
                False,
                f"{cfc_label} names feature(s) with no `### F<n>:` entry in "
                f"PLAN's Feature Breakdown: {labels}. Fix the number, or "
                f"add/restore the feature — an unknown feature id silently "
                f"never binds (the contract cannot be enforced against a "
                f"feature that does not exist).",
            )
        elif named:
            result.add(
                f"PLAN.md {cfc_label} references only defined features",
                True,
            )

    return entries


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
#
# `read_file` is imported from blueprint_common (relocated in T9a).


def validate_resolved(content: str, filename: str, result: ValidationResult) -> None:
    """Check that all questions, decisions, and markers are resolved."""
    by_kind: dict[str, list[str]] = {}
    for hit in scan_unresolved_markers(content):
        by_kind.setdefault(hit.kind, []).append(hit.text)

    unchecked = by_kind.get("unchecked_question", [])
    result.add(
        f"{filename} has no unresolved open questions",
        len(unchecked) == 0,
        f"{len(unchecked)} unchecked question(s) found" if unchecked else "",
    )

    tbds = by_kind.get("tbd", [])
    result.add(
        f"{filename} has no [TBD] decisions",
        len(tbds) == 0,
        f"{len(tbds)} [TBD] marker(s) found" if tbds else "",
    )

    markers = by_kind.get("unresolved_general", [])
    result.add(
        f"{filename} has no unresolved markers (TODO/FIXME/???)",
        len(markers) == 0,
        f"Found: {', '.join(markers)}" if markers else "",
        warn_only=True,
    )


# ---------------------------------------------------------------------------
# Approval helpers
# ---------------------------------------------------------------------------

# check_approval shares the canonical approval-detection constants defined above
# (APPROVAL_HEADER / APPROVAL_CHECKBOX / APPROVAL_HASH_LINE) and the shared
# verify_content_hash comparison, so this validator, has_approval() /
# approval_hash_matches() (used by render_business_brief), and validate_spec.py's
# check_approval all interpret the approval format identically — accepting
# `- [x]` / `- [X]`, an upper- or lower-case hex hash, and a `## Approval` header
# with flexible surrounding whitespace. (A second, stricter regex family used to
# live here and could disagree with the canonical set on the same document.)


# check_approval and _resolve_marker_root_and_key are imported from
# blueprint_common (audit R2.1) — both validators shared byte-identical copies.


def _plan_cfc_hash_refresh(content: str, file_path: Path) -> str:
    """PRODUCER hook (audit 3.5a): refresh PLAN.md's per-CFC content-hash sub-block.

    Applied by the shared approve_document core to the post-trim content, BEFORE
    the document-level hash is computed, so the refreshed sub-block is part of the
    approved content. For non-PLAN.md documents this is a no-op. Lives on the
    blueprint side because the CFC machinery (extract/parse/render) is
    blueprint-only; the SDD validator passes no transform.
    """
    if strip_artifact_prefix(file_path.name) != "PLAN.md":
        return content
    section = extract_cfc_section(content)
    cfc_entries = parse_cfc_entries(section[2]) if section else []
    return _write_cfc_hash_block(content, cfc_entries)


def approve_document(file_path: Path, *, project_root: Optional[Path] = None) -> bool:
    """Mark a document as approved (thin wrapper over the shared core, audit 3.5a).

    Delegates to ``blueprint_common.approve_document``, passing the blueprint-only
    PLAN.md per-CFC hash refresh as the producer ``content_transform`` so the
    sub-block is part of the document-level hash (H2). There is no task-tick
    carve-out here — blueprint has no Phase 4. Signature is preserved so all
    in-process callers and tests keep working; see the core for the full contract
    (R1.5 / R2.6 / re-stamp handling).
    """
    return _approve_document_core(
        file_path,
        project_root=project_root,
        content_transform=_plan_cfc_hash_refresh,
    )


def _write_cfc_hash_block(plan_content: str, cfc_entries: list[CFCEntry]) -> str:
    """Insert/replace the `- **CFC Content Hashes:**` sub-block in PLAN.md's `## Approval` section.

    If `cfc_entries` is empty (no CFC section, or empty section), removes any
    existing block. If a block already exists, replaces it. If no block exists
    and we have entries, appends the new block after the Content Hash line.

    All operations are scoped to the `## Approval` section body. The tail of
    an existing block matches only CFC-hash-shaped lines (``  - CFC-N: `<hex>` ``)
    — adjacent user-added metadata bullets (e.g., a reviewer list) are
    preserved.
    """
    rendered = render_cfc_hashes(cfc_entries)

    approval = _approval_section_slice(plan_content)
    if approval is None:
        # No ## Approval section at all — nothing we can write into.
        return plan_content
    body_start, body_end = approval
    approval_body = plan_content[body_start:body_end]

    # Locate any existing block within the approval body. A block starts at
    # `- **CFC Content Hashes:**` and continues through CFC-hash-shaped
    # indented entries — *not* arbitrary indented bullets — so adjacent
    # user-added metadata (`- **Reviewer:** Alice`) is preserved.
    existing = re.search(
        r"(?ms)^\s*-\s*\*\*CFC Content Hashes:\*\*\s*$"
        r"(?:\n[ \t]+-[ \t]+CFC-\d+:[ \t]+`[0-9a-fA-F]+`[ \t]*)*",
        approval_body,
    )

    if existing:
        if rendered:
            new_body = (
                approval_body[: existing.start()]
                + rendered
                + approval_body[existing.end():]
            )
        else:
            # Remove the existing block + a trailing newline if present.
            end = existing.end()
            if end < len(approval_body) and approval_body[end] == "\n":
                end += 1
            new_body = approval_body[: existing.start()] + approval_body[end:]
        return plan_content[:body_start] + new_body + plan_content[body_end:]

    if not rendered:
        return plan_content  # no entries, no existing block, nothing to do

    # Append the block after the Content Hash line inside the approval body.
    hash_line = re.search(
        r"(?m)^(\s*-\s*\*\*Content Hash:\*\*\s*`[^`]*`\s*)$",
        approval_body,
    )
    if hash_line is None:
        # Approval section may not have a Content Hash line yet; do nothing.
        return plan_content
    insertion = "\n" + rendered
    new_body = (
        approval_body[: hash_line.end()]
        + insertion
        + approval_body[hash_line.end():]
    )
    return plan_content[:body_start] + new_body + plan_content[body_end:]


# check_previous_phase_approved is imported from blueprint_common (audit R2.1);
# the blueprint phase ordering is passed in via BLUEPRINT_PHASE_ORDER.
BLUEPRINT_PHASE_ORDER = {
    "architecture": "SCOPE.md",
    "plan": "ARCHITECTURE.md",
}

# --run-state phase map (C3): ordered (phase_label, bare_artifact_name) pairs.
# The blueprint tier has NO Phase-4/Implement altitude, so its terminal label and
# tick-hint artifact are both None (tick_hint never fires here). A straight mirror
# of SDD_RUN_STATE_PHASES, passed into the shared derive_run_state (run_state.py).
BLUEPRINT_RUN_STATE_PHASES = [
    ("Scope", "SCOPE.md"),
    ("Architecture", "ARCHITECTURE.md"),
    ("Plan", "PLAN.md"),
]
BLUEPRINT_RUN_STATE_TERMINAL = None
BLUEPRINT_RUN_STATE_TICK_HINT_ARTIFACT = None
# Documented CFC-descope boundary (AD5): the blueprint CFC `orphaned-stale-content`
# obligation needs a whole-repo specs/ walk + CFC parse — disproportionate for a
# compact rehydration aid, so it is surfaced by the FULL validator instead. The
# --run-state output names that boundary so a rehydrating reader is never misled.
CFC_DESCOPE_NOTE = (
    "note: Cross-Feature Contract drift is not checked here — "
    "run the full validator to verify CFCs."
)


# ---------------------------------------------------------------------------
# Phase validators
# ---------------------------------------------------------------------------

def validate_scope(blueprint_dir: Path) -> ValidationResult:
    """Validate SCOPE.md for required sections and resolved questions."""
    result = ValidationResult()
    scope_path = resolve_artifact(blueprint_dir, "SCOPE.md")
    content = read_file(scope_path)

    result.add("SCOPE.md exists", content is not None, str(scope_path))
    if content is None:
        return result

    # Check all required sections exist
    for section in SCOPE_REQUIRED_SECTIONS:
        result.add(
            f"SCOPE.md has '{section}' section",
            has_section(content, section),
        )

    # Check for success criteria checkboxes ([ xX] — accept uppercase, audit R2.4)
    has_checkboxes = bool(re.search(r"- \[[ xX]\]", content))
    result.add(
        "SCOPE.md has success criteria checkboxes",
        has_checkboxes,
    )

    # Check for at least one target user defined
    user_sections = re.findall(r"^###\s+.+", content, re.MULTILINE)
    # Filter to only user sections (within Target Users)
    user_block = section_body(content, "Target Users")
    if user_block is not None:
        user_entries = re.findall(r"^###\s+.+", user_block, re.MULTILINE)
        result.add(
            "SCOPE.md defines at least one target user",
            len(user_entries) > 0,
            f"Found {len(user_entries)} user type(s)" if user_entries else "No user types defined",
        )
    else:
        result.add(
            "SCOPE.md defines at least one target user",
            False,
            "Target Users section not found or empty",
        )

    # Check for at least one goal
    goals_block = section_body(content, "Goals")
    if goals_block is not None:
        goal_items = re.findall(r"^-\s+.+", goals_block, re.MULTILINE)
        result.add(
            "SCOPE.md has at least one goal",
            len(goal_items) > 0,
        )
    else:
        result.add("SCOPE.md has at least one goal", False)

    # Check for at least one non-goal
    nongoals_block = section_body(content, "Non-Goals")
    if nongoals_block is not None:
        nongoal_items = re.findall(r"^-\s+.+", nongoals_block, re.MULTILINE)
        result.add(
            "SCOPE.md has at least one non-goal",
            len(nongoal_items) > 0,
        )
    else:
        result.add("SCOPE.md has at least one non-goal", False)

    # Check for at least one constraint
    constraints_block = section_body(content, "Constraints")
    if constraints_block is not None:
        # Look for table rows (pipe-delimited) beyond the header
        table_rows = re.findall(
            r"^\|[^|]+\|[^|]+\|", constraints_block, re.MULTILINE
        )
        # Subtract header and separator rows
        has_constraint_data = len(table_rows) > 2
        result.add(
            "SCOPE.md has at least one constraint defined",
            has_constraint_data,
            warn_only=True,
        )

    validate_resolved(content, "SCOPE.md", result)
    validate_panel_review(content, "SCOPE.md", result)

    for finding in scan_for_downstream_refs(content, "SCOPE.md", BLUEPRINT_DOWNSTREAM_POLICY):
        result.add(finding.check_name, False, finding.detail, warn_only=finding.warn_only)

    return result


def validate_architecture(blueprint_dir: Path) -> ValidationResult:
    """Validate ARCHITECTURE.md for required sections and resolved questions."""
    result = ValidationResult()

    check_previous_phase_approved(blueprint_dir, "architecture", result, BLUEPRINT_PHASE_ORDER)

    arch_path = resolve_artifact(blueprint_dir, "ARCHITECTURE.md")
    content = read_file(arch_path)

    result.add("ARCHITECTURE.md exists", content is not None, str(arch_path))
    if content is None:
        return result

    # Check all required sections exist
    for section in ARCHITECTURE_REQUIRED_SECTIONS:
        result.add(
            f"ARCHITECTURE.md has '{section}' section",
            has_section(content, section),
        )

    # Check for at least one component defined (### heading within Components section)
    component_block = section_body(content, "Components")
    if component_block is not None:
        component_entries = re.findall(r"^###\s+.+", component_block, re.MULTILINE)
        result.add(
            "ARCHITECTURE.md defines at least one component",
            len(component_entries) > 0,
            f"Found {len(component_entries)} component(s)"
            if component_entries
            else "No components defined",
        )
    else:
        result.add(
            "ARCHITECTURE.md defines at least one component",
            False,
            "Components section not found",
        )

    # Check for at least one technology choice in table
    tech_block = section_body(content, "Technology Choices")
    if tech_block is not None:
        table_rows = re.findall(r"^\|[^|]+\|", tech_block, re.MULTILINE)
        has_tech_data = len(table_rows) > 2  # header + separator + at least one row
        result.add(
            "ARCHITECTURE.md has at least one technology choice",
            has_tech_data,
        )
    else:
        result.add(
            "ARCHITECTURE.md has at least one technology choice",
            False,
        )

    # Check for at least one risk identified
    has_risks = bool(RISK_ENTRY_PATTERN.search(content))
    result.add(
        "ARCHITECTURE.md identifies at least one risk",
        has_risks,
    )

    # Check for component interaction details (table or diagram)
    interaction_block = section_body(content, "Component Interactions")
    if interaction_block is not None:
        has_diagram = bool(re.search(r"```", interaction_block))
        has_table = bool(re.search(r"\|.*\|.*\|", interaction_block))
        result.add(
            "ARCHITECTURE.md has component interaction details (diagram or table)",
            has_diagram or has_table,
            warn_only=True,
        )

    validate_resolved(content, "ARCHITECTURE.md", result)
    validate_panel_review(content, "ARCHITECTURE.md", result)

    for finding in scan_for_downstream_refs(content, "ARCHITECTURE.md", BLUEPRINT_DOWNSTREAM_POLICY):
        result.add(finding.check_name, False, finding.detail, warn_only=finding.warn_only)

    return result


def _validate_plan_cfc_coverage(
    content: str,
    result: ValidationResult,
    blueprint_dir: Path,
    project_root: Optional[Path],
) -> None:
    """Cross-artifact CFC validation for PLAN.md (audit R3.2 — split out of
    validate_plan).

    Three concerns, in order: (1) validate the optional `## Cross-Feature
    Contracts` section's field structure + the `**Implemented by:**` delegation
    field; (2) walk `specs/` ONCE (classification + malformed-dirname /
    derived-dir / duplicate-dir WARNs); (3) when any CFC entry or `[CFC-N]` tag
    exists, emit per-CFC coverage WARNs and the orphan-tag scan. The specs/ walk
    is unconditional — even a CFC-less PLAN must be scanned for orphan tags left
    behind by a removed CFC. Mutates `result`; returns nothing.
    """
    # ## Cross-Feature Contracts is optional — absence is not a failure.
    # When present, validate field structure, regex, uniqueness, and emit
    # the owner-silent Enforcement WARN.
    cfc_entries = validate_cfc_section(content, result)

    # `**Implemented by:**` — optional per-feature cross-project delegation field
    # (CPD I8). Validate every occurrence positionally (malformed value /
    # duplicate-in-block FAILs); absence and preamble occurrences are silent.
    _parse_implemented_by(content, result)

    # Cross-artifact CFC checks (coverage walk + orphan-tag scan). specs/ is
    # walked unconditionally — even a PLAN with no CFCs must be scanned for
    # orphan [CFC-N] tags (it may have removed its CFCs and left orphans behind).
    # ONE walk of specs/ (`_classified_spec_entries`) feeds BOTH the SpecState
    # classification AND the malformed-dirname WARNs, so each entry is listed and
    # classified once (it was iterated/classified twice before).
    # Resolve the specs/ walk root through the shared marker-walk (honoring an
    # explicit --project-root) rather than hard-coding blueprint_dir.parent, which
    # assumed specs/ is a sibling of blueprint/ and silently produced an empty
    # walk on a non-sibling layout (e.g. docs/blueprint/ + repo-root specs/) —
    # audit R3.3. Falls back to blueprint_dir.parent if no marker root is found.
    walk_root = arch_find_project_root(blueprint_dir, project_root) or blueprint_dir.parent
    spec_entries = _classified_spec_entries(walk_root)
    _emit_malformed_dirname_warns(spec_entries, result)
    # CPD derived-dir exclusion (I10): read the sibling registry ONCE here and
    # pass it in — never re-read per directory. `_states_from_entries` excludes
    # derived dirs from coverage; this surfaces the sibling-gated informational
    # WARN for any derived dir lacking a matching master sibling.
    derived_registry = project_registry.read_projects_config(walk_root)
    _emit_derived_dir_warns(spec_entries, derived_registry, walk_root, result)
    spec_states = _states_from_entries(spec_entries)
    has_any_cfc_tags = any(
        s.cfc_tags_in_spec or s.cfc_tags_in_tasks for s in spec_states
    )

    # Duplicate-feature-dir detection runs ONCE here — OUTSIDE the coverage block
    # below (which only runs when there is CFC work) — so a non-CFC PLAN with
    # colliding spec directories still gets the WARN.
    _emit_duplicate_feature_dir_warns(spec_states, result)

    if cfc_entries or has_any_cfc_tags:
        prior_hashes = read_cfc_hashes(content)
        coverages = compute_coverage(cfc_entries, spec_states)
        orphans = scan_orphan_tags(cfc_entries, spec_states, prior_hashes)

        # Coverage walk: emit a WARN only for `partially-bound`. `fully-bound`
        # and `unbound` produce no validator-level row — the PLAN author
        # gets a clean output unless there's actually work to do. (Per P2-16
        # from the post-implementation review: the previous all-three-states
        # emission was output noise that obscured real findings.)
        for cov in coverages:
            if cov.status == "partially-bound":
                result.add(
                    f"PLAN.md CFC-{cov.cfc_number} coverage",
                    False,
                    f"partially-bound: "
                    + ", ".join(
                        f"F{fid}=[{cov.feature_states.get(fid, '?')}]"
                        for fid in cov.participating
                    ),
                    warn_only=True,
                )
            elif cov.status == "fully-bound":
                # Surface in-flight vs shipped distinction in the detail
                # string (P3-10) so the PLAN author can judge urgency at a
                # glance. Emitted as PASS — the binding is complete.
                state_summary = ", ".join(
                    f"F{fid}=[{cov.feature_states.get(fid, '?')}]"
                    for fid in cov.participating
                )
                result.add(
                    f"PLAN.md CFC-{cov.cfc_number} coverage",
                    True,
                    f"fully-bound: {state_summary}",
                )
            # `unbound` produces no validator row — work hasn't started on
            # any participant; informational noise the PLAN author doesn't
            # need to see while drafting other sections.

        # Orphan-tag scan: each orphan emits a WARN. The validator surfaces
        # them as actionable; the user fixes via the remediation paths in
        # workflow-overview.md § Bound-Spec Immutability.
        for orphan in orphans:
            result.add(
                f"PLAN.md orphan-tag scan: {orphan.subtype}",
                False,
                orphan.message,
                warn_only=True,
            )


def validate_plan(
    blueprint_dir: Path, project_root: Optional[Path] = None
) -> ValidationResult:
    """Validate PLAN.md for required sections and resolved questions."""
    result = ValidationResult()

    check_previous_phase_approved(blueprint_dir, "plan", result, BLUEPRINT_PHASE_ORDER)

    plan_path = resolve_artifact(blueprint_dir, "PLAN.md")
    content = read_file(plan_path)

    result.add("PLAN.md exists", content is not None, str(plan_path))
    if content is None:
        return result

    # Deferred-dispositions prohibition. PLAN.md is the terminal Phase-3 artifact
    # and must not carry a ### Deferred dispositions sub-section. Use line-anchored
    # regex to reject only heading-position matches; this avoids false positives on
    # fenced code blocks or HTML comments that mention the heading string. This
    # check is placed before any CFC code is invoked.
    if re.search(r"(?m)^### Deferred dispositions\s*$", content):
        result.add(
            "PLAN.md does not contain '### Deferred dispositions'",
            False,
            "PLAN.md must not contain a '### Deferred dispositions' sub-section — "
            "terminal Phase-3 artifacts route via '[contract]'/'[detail]'/'[upstream]' "
            "tags instead. Remove the section to proceed.",
        )

    # Check all required sections exist
    for section in PLAN_REQUIRED_SECTIONS:
        result.add(
            f"PLAN.md has '{section}' section",
            has_section(content, section),
        )

    # Check for feature entries (### F1:, F2:, etc.) — scoped to ## Feature
    # Breakdown via the shared helper so the producer counts the SAME features
    # the consumer resolves against (audit R2.3).
    features = feature_breakdown_numbers(content)
    result.add(
        "PLAN.md has feature entries (### F1:, F2:, ...)",
        len(features) > 0,
        f"Found {len(features)} feature(s)" if features else "No features found",
    )

    # R1.7: feature numbers must be unique. Two `### F3:` blocks collapse
    # silently in every set()-based feature-id consumer, and the two CPD
    # consumers resolve a duplicate OPPOSITELY — master_feature's contract hash
    # takes the FIRST block while reconcile's `Implemented by` takes the LAST —
    # so a derived repo can be told it is in sync with a contract the master
    # author believes they replaced. Detect and block at the source.
    feature_numbers = feature_breakdown_numbers(content)
    dup_counts: dict[int, int] = {}
    for n in feature_numbers:
        dup_counts[n] = dup_counts.get(n, 0) + 1
    dup_features = sorted(n for n, c in dup_counts.items() if c > 1)
    if dup_features:
        labels = ", ".join(f"F{n}" for n in dup_features)
        result.add(
            "PLAN.md feature numbers are unique",
            False,
            f"Duplicate '### F<n>:' heading(s): {labels}. Each feature number "
            f"must appear exactly once — duplicate blocks collapse silently in "
            f"feature-id consumers and the two CPD consumers resolve them "
            f"oppositely (first-block-wins for the master contract hash, "
            f"last-block-wins for 'Implemented by'). Renumber the duplicate.",
        )
    elif features:
        result.add("PLAN.md feature numbers are unique", True)

    # Check that features have acceptance criteria
    has_ac = bool(FEATURE_ACCEPTANCE_CRITERIA.search(content))
    result.add(
        "PLAN.md features have acceptance criteria",
        has_ac,
    )

    # Check that features reference architecture components
    has_component_refs = bool(FEATURE_COMPONENT_REF.search(content))
    result.add(
        "PLAN.md features reference architecture components",
        has_component_refs,
        warn_only=True,
    )

    # Check MVP definition contains feature references
    mvp_block = section_body(content, "MVP Definition")
    if mvp_block is not None:
        mvp_features = FEATURE_ID_PATTERN.findall(mvp_block)
        result.add(
            "PLAN.md MVP definition references specific features",
            len(mvp_features) > 0,
            f"MVP references {len(mvp_features)} feature(s)"
            if mvp_features
            else "No feature references in MVP definition",
        )
    else:
        result.add(
            "PLAN.md MVP definition references specific features",
            False,
        )

    # Check implementation order has entries
    order_block = section_body(content, "Implementation Order")
    if order_block is not None:
        order_features = FEATURE_ID_PATTERN.findall(order_block)
        result.add(
            "PLAN.md implementation order references features",
            len(order_features) > 0,
        )

        # Check that all defined features appear in implementation order
        defined_features = {str(n) for n in feature_breakdown_numbers(content)}
        ordered_features = set(order_features)
        unordered = defined_features - ordered_features
        if unordered:
            missing_labels = ", ".join(
                f"F{f}" for f in sorted(unordered, key=int)
            )
            result.add(
                "PLAN.md all features appear in implementation order",
                False,
                f"Missing from order: {missing_labels}",
                warn_only=True,
            )
        else:
            result.add(
                "PLAN.md all features appear in implementation order",
                True,
            )
    else:
        result.add(
            "PLAN.md implementation order references features",
            False,
        )

    # Check feature dependency coverage
    deps_block = section_body(content, "Feature Dependencies")
    if deps_block is not None:
        dep_features = set(FEATURE_ID_PATTERN.findall(deps_block))
        defined_features = {str(n) for n in feature_breakdown_numbers(content)}
        missing_deps = defined_features - dep_features
        if missing_deps:
            missing_labels = ", ".join(
                f"F{f}" for f in sorted(missing_deps, key=int)
            )
            result.add(
                "PLAN.md all features appear in dependency graph",
                False,
                f"Missing from dependencies: {missing_labels}",
                warn_only=True,
            )
        else:
            result.add(
                "PLAN.md all features appear in dependency graph",
                True,
            )

    # Check milestones have feature references
    milestones_block = section_body(content, "Milestones")
    if milestones_block is not None:
        milestone_entries = re.findall(
            r"^###\s+Milestone\s+\d+:", milestones_block, re.MULTILINE
        )
        milestone_features = FEATURE_ID_PATTERN.findall(milestones_block)
        result.add(
            "PLAN.md has milestones with feature assignments",
            len(milestone_entries) > 0 and len(milestone_features) > 0,
        )
    else:
        result.add(
            "PLAN.md has milestones with feature assignments",
            False,
        )

    # Cross-artifact CFC validation: section field-structure, `**Implemented
    # by:**`, the specs/ coverage walk, and the orphan-tag scan (audit R3.2 —
    # extracted to keep validate_plan's own complexity down).
    _validate_plan_cfc_coverage(content, result, blueprint_dir, project_root)

    validate_resolved(content, "PLAN.md", result)
    validate_panel_review(content, "PLAN.md", result)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _handle_decline_pending(blueprint_dir: Path, project_root: Optional[Path]) -> int:
    """`--decline-pending` mode (audit R3.2 — extracted from main).

    Clear this blueprint's pending-review obligations — an auditable user decision
    (logged to stdout), validator-owned marker lifecycle. Returns an exit code.
    """
    root, bp_rel = _resolve_marker_root_and_key(blueprint_dir, project_root)
    restore_cmd = f"validate_blueprint.py {blueprint_dir} --restore-anchor"
    try:
        cleared, held_back, flagged = partition_decline_clear(root, bp_rel)
    except MarkerCorruptError as exc:
        print(
            f"Cannot decline: {exc}. The marker is corrupt; inspect or delete "
            f".sdd/pending-review.json manually."
        )
        return 1
    if not cleared and not held_back and not flagged:
        print(f"No pending-review entries found for {blueprint_dir}.")
        return 0
    msg, code = format_decline_output(cleared, held_back, flagged, restore_cmd=restore_cmd)
    print(msg)
    return code


def _handle_restore_anchor(blueprint_dir: Path, project_root: Optional[Path]) -> int:
    """`--restore-anchor` mode (audit R3.2 — extracted from main).

    Clear a legacy re-anchored (UNSATISFIABLE) obligation whose genuine
    `upstream-panel` tag is already archived. Content-attested — clears ONLY where
    the real tag is present. Returns an exit code.
    """
    root, bp_rel = _resolve_marker_root_and_key(blueprint_dir, project_root)
    try:
        restored = restore_anchor_for_prefix(root, bp_rel)
    except MarkerCorruptError as exc:
        print(
            f"Cannot restore: {exc}. The marker is corrupt; inspect or delete "
            f".sdd/pending-review.json manually."
        )
        return 1
    if restored:
        noun = "obligation" if len(restored) == 1 else "obligations"
        print(
            f"Restored anchor; cleared {len(restored)} satisfied {noun} "
            f"(genuine upstream-panel tag present): {', '.join(restored)}"
        )
    else:
        print(
            f"No restorable obligations for {blueprint_dir} (none carry a "
            f"genuine upstream-panel tag yet)."
        )
    return 0


def _handle_write_arch_config(blueprint_dir: Path) -> int:
    """`--write-arch-config` mode (audit R3.2 — extracted from main).

    Carry the blueprint's declared stack across the blueprint→SDD seam. Standalone
    and explicit — NOT folded into --approve, so it never interacts with the PLAN
    content hash or the CFC cascade. Writes via the SAME shared writer the SDD side
    uses (source="blueprint"), to the project root (parent of blueprint/). Returns
    an exit code.
    """
    arch_path = resolve_artifact(blueprint_dir, "ARCHITECTURE.md")
    content = read_file(arch_path)
    if content is None:
        print(f"Error: {arch_path} does not exist")
        return 2
    token = parse_arch_token(content)
    if token is None:
        print(
            "Error: ARCHITECTURE.md has no '**Architecture token:** `<value>`' "
            "line. Add one under ## Technology Choices (e.g. "
            "`**Architecture token:** \\`generic\\``)."
        )
        return 2
    if token not in KNOWN_ARCH_TOKENS:
        print(
            f"Error: architecture token '{token}' is not recognized; "
            f"must be one of {sorted(KNOWN_ARCH_TOKENS)}."
        )
        return 2
    project_root = blueprint_dir.parent
    written = write_arch_config(
        project_root,
        token,
        KNOWN_ARCH_TOKENS,
        source="blueprint",
        detected_from="ARCHITECTURE.md",
    )
    print(f"Persisted stack '{token}' (from ARCHITECTURE.md) to {written}")
    return 0


def _handle_run_state(args, blueprint_dir: Path, project_root: Optional[Path]) -> int:
    """`--run-state` mode. Read-only, out-of-band, always returns 0. [C3/I6; AD11-L2]

    A straight mirror of the SDD tier's handler (C2) with NO CFC-orphan
    computation (descoped, AD5): no `scan_orphan_tags` call and no
    `extra_obligations`. Resolves the marker root, builds the blueprint phase
    list (terminal label + tick-hint artifact both None — no Phase-4 altitude),
    calls the shared `derive_run_state` + `format_run_state`, prints, and appends
    the CFC-descope note so the documented boundary is legible. When `--output
    json` was passed, first prints the AD9/Q1 one-line text-only notice.

    Layer 2 of the never-crash contract (AD11): a broad `except Exception`
    backstop wraps the ENTIRE body — marker-root resolution, phase-list build,
    derive, format, AND every print — so NOTHING runs outside the guard and no
    missed exception can break the always-exit-0 contract. It never delegates to
    `run_cli_failclosed` (which exits non-zero). The backstop line is a HARDCODED,
    exception-text-free static string (it never interpolates caught-exception
    text — that would reopen the AD14 spoof channel). Both prints are
    `BrokenPipeError`-guarded via the shared `safe_print` (AD11-E).
    """
    try:
        marker_root = _resolve_marker_root_and_key(blueprint_dir, project_root)[0]
        if getattr(args, "output", "text") == "json":
            safe_print("note: --run-state emits text only this cycle")
        state = derive_run_state(
            tier="blueprint",
            artifact_dir=blueprint_dir,
            project_root=marker_root,
            phases=BLUEPRINT_RUN_STATE_PHASES,
            terminal_phase_label=BLUEPRINT_RUN_STATE_TERMINAL,
            tick_hint_artifact=BLUEPRINT_RUN_STATE_TICK_HINT_ARTIFACT,
        )
        safe_print(format_run_state(state))
        safe_print(CFC_DESCOPE_NOTE)
        return 0
    except Exception:
        safe_print(
            "run-state: unable to derive a summary; run the full validator "
            "(validate_blueprint.py <dir>) for details"
        )
        return 0


def _handle_approve(args, blueprint_dir: Path, project_root: Optional[Path]) -> int:
    """`--approve {scope,architecture,plan}` mode (audit R3.2 — extracted from main).

    Gates on the matching phase validator (Decision E), surfaces CFC drift/coverage
    WARNs before approve_document refreshes the per-CFC baseline, then stamps.
    Returns an exit code.
    """
    file_map = {
        "scope": "SCOPE.md",
        "architecture": "ARCHITECTURE.md",
        "plan": "PLAN.md",
    }
    target = resolve_artifact(blueprint_dir, file_map[args.approve])
    if not target.is_file():
        print(f"Error: {target} does not exist")
        return 2

    validators = {
        "scope": validate_scope,
        "architecture": validate_architecture,
        "plan": lambda d: validate_plan(d, project_root),
    }
    # Compute the pre-approval result once: it drives both the Decision-E
    # gate and the CFC-drift surfacing below.
    pre_result = validators[args.approve](blueprint_dir)

    # Decision E — gate on validation. Approving a structurally-broken
    # document silently corrupts state and produces a confusing
    # "approved, but next validate FAILs" 3am scenario. Refuse to stamp
    # unless validation passes. --force overrides after the user has
    # read the FAIL items.
    if not args.force and not pre_result.passed:
        print(f"Refusing to approve {target.name}: validation FAILed.")
        print(pre_result.summary())
        print(
            f"\nFix the FAIL items above, OR re-run with --force to "
            f"approve anyway (you take responsibility for the "
            f"approved-but-invalid state)."
        )
        return 1

    # Surface CFC drift / coverage WARNs BEFORE approve_document refreshes
    # the per-CFC content-hash baseline (which overwrites the prior state
    # the orphaned-stale-content scan compares against). These are
    # warn_only rows, so they did not block the Decision-E gate above —
    # without this, a clean `--approve plan` would silently drop them and
    # then erase the drift baseline (CFC D1-2).
    cfc_warns = [
        (n, s, d)
        for (n, s, d) in pre_result.checks
        if s == "WARN" and ("orphan-tag scan" in n or "CFC" in n)
    ]
    if cfc_warns:
        print(
            "CFC coverage / drift warnings — review before approving "
            "(approval (re)stamps the per-CFC content-hash baseline):"
        )
        for n, s, d in cfc_warns:
            print(f"  [{s}] {n}" + (f" — {d}" if d else ""))
        print()

    try:
        stamped = approve_document(target, project_root=project_root)
    except MarkerCorruptError as exc:
        # The document was stamped (atomic) before restamp_or_suppress hit the
        # corrupt marker — surface it cleanly instead of a traceback, and exit
        # non-zero so the operator re-records the obligation (audit R2.6).
        print(
            f"WARNING: {target} was stamped, but its re-approval obligation "
            f"was NOT recorded: {exc}. The .sdd/pending-review.json marker is "
            f"corrupt (e.g. unresolved git conflict markers). Fix it and "
            f"re-run --approve so the obligation for this edit is recorded.",
            file=sys.stderr,
        )
        return 1
    return 0 if stamped else 1


def _run_validation(args, blueprint_dir: Path, project_root: Optional[Path]) -> int:
    """Default mode: validate the requested phase(s), reconcile pending-review,
    print the summary (audit R3.2 — extracted from main). Returns an exit code
    (1 if anything FAILed, else 0)."""
    use_json = args.output == "json"

    if not use_json:
        print(f"Validating: {blueprint_dir}\n")

    all_passed = True
    has_any_warnings = False
    json_output: dict = {
        "blueprint_dir": str(blueprint_dir),
        "phases": {},
    }

    phase_file_map = {
        "scope": "SCOPE.md",
        "architecture": "ARCHITECTURE.md",
        "plan": "PLAN.md",
    }

    validators = {
        "scope": ("Scope (SCOPE.md)", lambda d: validate_scope(d)),
        "architecture": (
            "Architecture (ARCHITECTURE.md)",
            lambda d: validate_architecture(d),
        ),
        "plan": ("Plan (PLAN.md)", lambda d: validate_plan(d, project_root)),
    }

    for phase_key, (label, validator) in validators.items():
        if args.phase not in ("all", phase_key):
            continue

        # In "all" mode, skip phases whose files don't exist yet
        expected_file = resolve_artifact(blueprint_dir, phase_file_map[phase_key])
        if args.phase == "all" and not expected_file.exists():
            continue

        result = validator(blueprint_dir)

        if not result.passed:
            status = "FAILED"
        elif result.has_warnings:
            status = "PASSED (with warnings)"
        else:
            status = "PASSED"

        if use_json:
            json_output["phases"][phase_key] = {
                "status": status,
                "checks": result.to_dict(),
            }
        else:
            print(f"{label}: {status}")
            print(result.summary())
            print()

        if not result.passed:
            all_passed = False
        if result.has_warnings:
            has_any_warnings = True

    # R2 (dispatch-level): reconcile pending-review ONCE and surface still-pending
    # obligations as a dedicated result — NOT inside each validate_* (which would
    # auto-clear up to 3x and let an absent/skipped phase's FAIL vanish). AD7/I10/H1.
    root, bp_rel = _resolve_marker_root_and_key(blueprint_dir, project_root)
    scan_prefix = (
        bp_rel if args.phase == "all" else f"{bp_rel}/{resolve_artifact(blueprint_dir, phase_file_map[args.phase]).name}"
    )
    pending_result = reconcile_to_result(
        root,
        scan_prefix,
        decline_cmd=f"validate_blueprint.py {blueprint_dir} --decline-pending",
        restore_cmd=f"validate_blueprint.py {blueprint_dir} --restore-anchor",
    )
    if pending_result.checks:
        if use_json:
            json_output["pending_review"] = pending_result.to_dict()
        else:
            print(
                f"Pending-review: "
                f"{'FAILED' if not pending_result.passed else 'PASSED'}"
            )
            print(pending_result.summary())
            print()
        if not pending_result.passed:
            all_passed = False

    if use_json:
        if all_passed and not has_any_warnings:
            json_output["result"] = "passed"
        elif all_passed:
            json_output["result"] = "passed_with_warnings"
        else:
            json_output["result"] = "failed"
        print(json.dumps(json_output, indent=2))
    else:
        if all_passed and not has_any_warnings:
            print("All validations passed.")
        elif all_passed and has_any_warnings:
            print("All validations passed with warnings. Review WARN items above.")
        else:
            print("Some validations failed. See FAIL items above.")

    return 1 if not all_passed else 0


def main():
    parser = argparse.ArgumentParser(
        description="Validate project blueprint artifacts.",
        epilog="Example: python validate_blueprint.py blueprint/",
    )
    parser.add_argument(
        "blueprint_dir",
        type=Path,
        help="Path to the blueprint directory (e.g., blueprint/)",
    )
    parser.add_argument(
        "--phase",
        choices=["scope", "architecture", "plan", "all"],
        default="all",
        help="Which phase to validate (default: all existing files)",
    )
    # Mode flags are mutually exclusive: each selects a distinct operation, and
    # argparse rejects any combination (exit 2) rather than silently resolving by
    # if-ordering (audit I3.2). --force is a modifier of --approve and stays on
    # the main parser.
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--approve",
        choices=["scope", "architecture", "plan"],
        help="Approve a phase document (marks it approved with content hash)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip the pre-approval validation gate (use after manually reviewing FAIL items)",
    )
    mode_group.add_argument(
        "--write-arch-config",
        action="store_true",
        help="Read the '**Architecture token:**' from ARCHITECTURE.md and persist "
        "it to <project-root>/.sdd/architecture.json so the declared stack crosses "
        "the blueprint→SDD seam. Standalone op (does NOT run during --approve and "
        "touches no content hash).",
    )
    mode_group.add_argument(
        "--run-state",
        action="store_true",
        help="Print a compact, read-only one-screen rehydration summary (current "
        "phase, per-artifact approved/hash status, open obligations, next step) "
        "and exit 0. Side-effect-free; the safe way to re-orient after a context "
        "reset. Emits text only; CFC drift is checked only by the full validator.",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root for the .sdd/ pending-review marker (default: walk up "
        "from blueprint_dir)",
    )
    mode_group.add_argument(
        "--decline-pending",
        action="store_true",
        help="Clear this blueprint's genuinely-owed pending-review obligations — an "
        "explicit, auditable decision to skip the upstream panel re-review. An "
        "UNSATISFIABLE obligation whose genuine panel tag is present (the panel WAS "
        "performed) is refused and routed to --restore-anchor, never mis-recorded "
        "as skipped; exit 3 if any obligation is held back or flagged.",
    )
    mode_group.add_argument(
        "--restore-anchor",
        action="store_true",
        help="Clear an UNSATISFIABLE pending-review obligation — a fresh "
        "reversed-order re-approval, or a legacy re-anchored marker — whose "
        "genuine `upstream-panel` tag is already present on an archived Trajectory "
        "row. Content-attested: clears ONLY when the real tag "
        "exists (never asserts a panel ran); no marker-cache editing.",
    )
    args = parser.parse_args()

    blueprint_dir = args.blueprint_dir.resolve()
    if not blueprint_dir.is_dir():
        print(f"Error: {blueprint_dir} is not a directory")
        sys.exit(2)

    # R7 mixed-state surfacing: non-blocking nudge ONLY when a mixed dir is
    # renamer-fixable (the helper suppresses the nudge on a same-artifact
    # collision, where the validator is about to FAIL with the ambiguity detail).
    _warn = mixed_state_warning(str(args.blueprint_dir), blueprint_dir)
    if _warn:
        print(_warn)

    project_root = args.project_root.resolve() if args.project_root else None
    if project_root is not None and not project_root.is_dir():
        print(f"Error: --project-root {project_root} is not a directory")
        sys.exit(2)

    # Best-effort .sdd/ cruft cleanup at process exit (WORKING-NOTES Item 2).
    # Registered AFTER the arg-validation sys.exit(2) guards above and before the
    # mode dispatch. Uses _resolve_marker_root_and_key(...)[0] — the SAME
    # write-side root the run's marker ops use — NOT raw arch_find_project_root,
    # which would sweep an unrelated .sdd/ under a non-ancestor --project-root
    # (AD1). This also keeps cleanup aligned with _handle_write_arch_config's
    # blueprint_dir.parent write root.
    atexit.register(
        sweep_sdd_cruft, _resolve_marker_root_and_key(blueprint_dir, project_root)[0]
    )

    # Mode dispatch (audit R3.2). The mode flags are argparse-mutually-exclusive,
    # so at most one of these is set; each handler returns a process exit code.
    # The default (no mode flag) runs validation.
    if args.decline_pending:
        sys.exit(_handle_decline_pending(blueprint_dir, project_root))
    if args.restore_anchor:
        sys.exit(_handle_restore_anchor(blueprint_dir, project_root))
    if args.write_arch_config:
        sys.exit(_handle_write_arch_config(blueprint_dir))
    if args.run_state:
        sys.exit(_handle_run_state(args, blueprint_dir, project_root))
    if args.approve:
        sys.exit(_handle_approve(args, blueprint_dir, project_root))

    sys.exit(_run_validation(args, blueprint_dir, project_root))


if __name__ == "__main__":
    # Fail-closed (design.md:349): an uncaught ArtifactAmbiguityError from any
    # resolve_artifact site — including the no-`result` soft gate classify_spec
    # and the --approve target — exits non-zero before any content hash is
    # stamped. The boundary is shared so a new entrypoint can't forget it.
    run_cli_failclosed(main)
