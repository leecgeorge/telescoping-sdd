"""Shared, read-only run-state summary for `--run-state` (both validators). [C1]

Derives a tier-agnostic `RunState` from disk and renders it as a compact,
sanitized one-screen rehydration summary. A single shared leaf so the SDD and
blueprint tiers cannot drift (R6). Consumed by `validate_spec.py` (C2) and
`validate_blueprint.py` (C3) via a thin `_handle_run_state` wrapper each.

Dependency direction (AD2 — leaf discipline, acyclic): this module imports only
shared leaves/layers — `content_hash`, `pending_review` (incl.
`MarkerCorruptError`), `artifact_resolution`, and `blueprint_common.read_file` /
`trim_trajectory_table` — and NEVER a validator. The parity/import-guard test
asserts the no-validator-import rule. Layering:
`trajectory <- content_hash <- blueprint_common <- pending_review`, so importing
`pending_review` transitively loads `blueprint_common` (a wider surface than the
bare leaves) but acyclicity holds because `blueprint_common` never imports a
validator.

Never-crash contract (AD11) lives across two layers: `derive_run_state` (Layer
1) performs the real per-primitive catches for per-artifact DEGRADED granularity
and specific obligations; each validator's `_handle_run_state` (Layer 2) adds a
broad backstop. `--run-state` writes nothing (R5).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from dataclasses import fields as _dc_fields
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

# AD2 — import ONLY shared leaves/layers, NEVER a validator. blueprint_common is
# imported before pending_review (pending_review layers over it). The
# import-guard test asserts no validator name appears here.
from artifact_resolution import ArtifactAmbiguityError, resolve_artifact
from approval_records import (
    DISPLAY_ARG_MAX,
    GLOSS_UNBOUND,
    TIER_VALIDATOR_CMD,
    _ANSI_RE,
    _CONTROL_RE,
    display_arg,
    display_text,
)
from blueprint_common import UPSTREAM_SETS, binding_report, read_file, trim_trajectory_table
from content_hash import (
    changed_since_stamp,
    compute_content_hash,
    has_approval,
    is_pure_basis_migration,
    read_stored_hash,
)
from pending_review import (
    MarkerCorruptError,
    is_containment_escaping,
    owning_dir_route,
    partition_keys,
    read_pending_review,
    scope_of_key,
    tier_of_scope,
)


class HashStatus(str, Enum):
    """Per-artifact hash state.

    `NA` = not approved (no stamped hash to compare); `MATCHES` = stamped hash
    coherent; `STALE` = the hash moved (re-approve; a panel re-review is owed
    unless `--approve` recognises the delta as a carve-out); `STALE_MIGRATION` =
    a pure hash-basis migration (a v1 or v2 stamp, unedited since) — a costless
    re-stamp only (no re-review, AD4);
    `DEGRADED` = the read failed / was ambiguous (cannot verify). A `str` Enum so
    a member renders as its lowercase-free name directly in text.
    """

    NA = "NA"
    MATCHES = "MATCHES"
    STALE = "STALE"
    STALE_MIGRATION = "STALE_MIGRATION"
    DEGRADED = "DEGRADED"


# --- Obligation kind constants (the shared vocabulary, R6 AC4) --------------
OBLIGATION_PENDING_REVIEW = "pending-review"
OBLIGATION_MARKER_UNREADABLE = "marker-unreadable"
OBLIGATION_DEGRADED_READ = "degraded-read"
# Unit C0 (AD17): a superseded upstream binding — a blocking obligation, so it
# is never dropped and it prevents "all clear" (AC-4.3).
OBLIGATION_UPSTREAM_DRIFT = "upstream-drift"

# --- Notice kinds (Unit C0 AD17): informational, never obligations ----------
NOTICE_PENDING_ELSEWHERE = "pending-elsewhere"
NOTICE_UNBOUND = "unbound"
# The out-of-lane containment-escaping keys' group subject; sorts last.
NO_SCOPE_SUBJECT = "(no scope)"
PENDING_ELSEWHERE_LABEL = "pending elsewhere — not resolvable from here"


@dataclass
class ArtifactState:
    """One artifact's derived state (I3-produced).

    `exists` is whether the artifact *dirent* resolves — `True` even for a
    present-but-unreadable file (whose `hash_status` is then `DEGRADED`). A
    per-artifact `next_action` is intentionally NOT a field: it is derived from
    `hash_status` at render time (AD4), so the two stale labels cannot drift.
    """

    name: str
    exists: bool
    approved: bool
    hash_status: HashStatus
    tick_hint: bool = False


@dataclass
class Obligation:
    """One open obligation with its plain-language next-action.

    `kind` is one of the OBLIGATION_* constants. `detail` is sanitized before it
    reaches stdout (AD14); `next_action` is a plain-language imperative.
    """

    kind: str
    detail: str
    next_action: str


@dataclass
class Notice:
    """One informational line (Unit C0 AD17) — never blocks "all clear".

    `kind` is NOTICE_PENDING_ELSEWHERE (subject = the owning scope) or
    NOTICE_UNBOUND (subject = the artifact). For pending-elsewhere, `detail`
    begins with the obligation count (``"<n> obligation(s)"``), which the
    collapsed form reads back. `route` is the plain-language way out.
    """

    kind: str
    subject: str
    detail: str
    route: str


@dataclass
class RunState:
    """The whole rehydration summary (AD1) — in-memory only, never persisted."""

    tier: str
    current_phase: str
    artifacts: "List[ArtifactState]" = field(default_factory=list)
    obligations: "List[Obligation]" = field(default_factory=list)
    next_step: str = ""
    notices: "List[Notice]" = field(default_factory=list)


# --- Shared field-name constants (the parity contract, R6 AC4) --------------
# Hardcoded LITERAL tuples — the independent, pinned contract the dataclasses are
# checked against (NOT derived from the dataclasses, which would make the parity
# test tautological and give no protection). A field added/reordered without
# updating the matching constant fails the parity test loudly, so the two tiers'
# summaries cannot silently drift.
CORE_RUN_STATE_FIELDS = (
    "tier", "current_phase", "artifacts", "obligations", "next_step", "notices",
)
ARTIFACT_FIELDS = ("name", "exists", "approved", "hash_status", "tick_hint")
OBLIGATION_FIELDS = ("kind", "detail", "next_action")
NOTICE_FIELDS = ("kind", "subject", "detail", "route")

# Fail LOUDLY at import time (not only in the test suite) if a dataclass field
# is added/renamed/reordered without updating the matching tuple above.
assert tuple(f.name for f in _dc_fields(RunState)) == CORE_RUN_STATE_FIELDS
assert tuple(f.name for f in _dc_fields(ArtifactState)) == ARTIFACT_FIELDS
assert tuple(f.name for f in _dc_fields(Obligation)) == OBLIGATION_FIELDS
assert tuple(f.name for f in _dc_fields(Notice)) == NOTICE_FIELDS

# Blueprint's all-approved current-phase label (its terminal_phase_label is None,
# since the blueprint tier has no Phase-4/Implement altitude — AD3).
BLUEPRINT_ALL_APPROVED_LABEL = "Plan (complete)"


def _phase_suffix(state: "ArtifactState") -> str:
    """The AD3 suffix qualifying WHY `state`'s phase is the current (first
    non-`exists AND approved`) phase.

    Four states, three named suffixes (the AD3 contract) plus the bare
    actively-in-phase case:
      * `exists=True,  DEGRADED` (present-but-unreadable) -> `" (degraded)"`
      * `exists=False, DEGRADED` (ArtifactAmbiguityError) -> `" (ambiguous)"`
      * `exists=False, not DEGRADED` (genuinely absent)   -> `" (not started)"`
      * `exists=True,  not DEGRADED` (present, not yet approved) -> `""` (bare;
        the reader is actively in this phase, mid-draft).
    Never returns `" (not started)"` for a present-but-unverifiable artifact, so
    the phase header agrees with the degraded-read / ambiguity obligation instead
    of falsely claiming the phase never started.
    """
    if state.hash_status == HashStatus.DEGRADED:
        return " (degraded)" if state.exists else " (ambiguous)"
    if not state.exists:
        return " (not started)"
    return ""


def _phase_next_step(label: str, state: "ArtifactState") -> str:
    """The next-step pointer for a blocking phase, matching `_phase_suffix`'s
    same three-way split so the header's "next:" hint never tells the reader to
    "complete and approve" a phase whose real blocker is an unreadable or
    ambiguous artifact (those are resolved differently, not by finishing a
    draft)."""
    if state.hash_status == HashStatus.DEGRADED:
        if state.exists:
            return f"resolve why {label} is unreadable — see the degraded-read obligation below"
        return f"resolve the ambiguous {label} artifact — see the obligation below"
    return f"complete and approve {label}"


def _derive_current_phase(
    phases: "List[Tuple[str, ArtifactState]]",
    terminal_phase_label: "Optional[str]",
) -> "Tuple[str, str]":
    """Return `(current_phase, next_step)` from ordered `(label, state)` pairs. [AD3]

    `current_phase` = the label (+ AD3 suffix) of the FIRST phase whose artifact
    is not (`exists` AND `approved`) — robust to a later phase being "ahead" (an
    out-of-order approval still reports the earliest incomplete phase). When ALL
    phase artifacts are approved: `terminal_phase_label` if given (SDD
    `"Implement"`), else the defined blueprint all-approved label
    (`"Plan (complete)"`). `next_step` is a plain-language pointer, always
    present (even in the all-clear / zero-artifact edge).
    """
    for label, state in phases:
        if state.exists and state.approved:
            continue
        current = label + _phase_suffix(state)
        return current, _phase_next_step(label, state)
    # All phases approved.
    if terminal_phase_label is not None:
        return terminal_phase_label, f"proceed to {terminal_phase_label}"
    return (
        BLUEPRINT_ALL_APPROVED_LABEL,
        "all blueprint phases approved — drive each PLAN feature through "
        "spec-driven-dev",
    )


# --- I3: guarded raw read ---------------------------------------------------

# `_read_artifact_text` outcomes.
_READ_OK = "ok"
_READ_ABSENT = "absent"
_READ_DEGRADED = "degraded"


def _read_artifact_text(path: Path) -> "Tuple[str, Optional[str]]":
    """Guarded raw read of one artifact. Returns `(outcome, text)`. [I3; AD11-L1]

    Never raises for a normal read failure (the Layer-1 catch):
      * absent (`read_file` -> None because it is not a file) -> `("absent", None)`
      * present-but-unreadable (`PermissionError` / `UnicodeDecodeError` / other
        `OSError`) -> `("degraded", None)`
      * success -> `("ok", text)`
    Reads via `blueprint_common.read_file` (utf-8-sig, BOM-tolerant) so the text
    hashed here is byte-identical to what the validators' hash producer/consumer
    read — a plain utf-8 read would wedge a BOM'd artifact at a false stale hash.
    """
    try:
        text = read_file(path)
    except (OSError, UnicodeDecodeError):
        return (_READ_DEGRADED, None)
    if text is None:
        return (_READ_ABSENT, None)
    return (_READ_OK, text)


def _classify_hash(text: str) -> HashStatus:
    """MATCHES / STALE / STALE_MIGRATION for an already-approved artifact. [AD4]

    Splits a stale result via `is_pure_basis_migration` (Unit F: the same
    predicate the validator FAIL and the approve-time arm use, so the three
    cannot disagree): a pure basis migration of a v1 or v2 stamp reads
    STALE_MIGRATION (costless, no re-review); any other drift reads STALE.
    Malformed `## Approval` hashes read STALE via `changed_since_stamp`'s
    fail-closed non-16-hex branch and never raise (AD8).
    """
    stored = read_stored_hash(text)
    new_hash = compute_content_hash(text)
    if not changed_since_stamp(new_hash, stored, text):
        return HashStatus.MATCHES
    if is_pure_basis_migration(
        original_content=text,
        stored_hash=stored,
        content_trimmed=trim_trajectory_table(text),
    ):
        return HashStatus.STALE_MIGRATION
    return HashStatus.STALE


def _derive_artifact_state(
    artifact_dir: Path, bare_name: str, obligations: "List[Obligation]"
) -> "Tuple[ArtifactState, Optional[str]]":
    """Resolve + read one artifact into an `ArtifactState`, appending any
    degraded / ambiguity `Obligation` to `obligations`. Layer-1 per-primitive
    catches (AD11) — the three distinct states (absent / degraded / ambiguous)
    are kept separate so the AD3 phase suffix stays truthful.

    Returns ``(state, text)``; ``text`` is the content read (None when absent,
    degraded or ambiguous) so the binding report can reuse it (Unit C0 C5)."""
    try:
        path = resolve_artifact(artifact_dir, bare_name)
    except ArtifactAmbiguityError:
        # exists=False + DEGRADED is the ambiguity signature that drives AD3's
        # " (ambiguous)" suffix (distinct from absent's exists=False + NA).
        obligations.append(
            Obligation(
                kind=OBLIGATION_DEGRADED_READ,
                detail=f"ambiguous NN_ prefix for {bare_name} (bare and prefixed forms coexist)",
                next_action=f"remove the duplicate form of {bare_name} (keep one), then re-run",
            )
        )
        return ArtifactState(
            name=bare_name, exists=False, approved=False, hash_status=HashStatus.DEGRADED
        ), None

    outcome, text = _read_artifact_text(path)
    if outcome == _READ_ABSENT:
        return ArtifactState(
            name=bare_name, exists=False, approved=False, hash_status=HashStatus.NA
        ), None
    if outcome == _READ_DEGRADED:
        obligations.append(
            Obligation(
                kind=OBLIGATION_DEGRADED_READ,
                detail=f"{bare_name} is present but could not be read (permission or encoding)",
                next_action=f"inspect {bare_name}'s permissions/encoding, or re-create it; then re-run",
            )
        )
        return ArtifactState(
            name=bare_name, exists=True, approved=False, hash_status=HashStatus.DEGRADED
        ), None

    # Readable content.
    if not has_approval(text):
        return ArtifactState(
            name=bare_name, exists=True, approved=False, hash_status=HashStatus.NA
        ), text
    return ArtifactState(
        name=bare_name, exists=True, approved=True, hash_status=_classify_hash(text)
    ), text


_UNBOUND_ROUTE = (
    "run each one's consistency check against its current upstream, then "
    "re-approve it top-down (`--approve <phase>`) to record its binding — "
    + GLOSS_UNBOUND
)


def _append_binding_state(
    states: "List[Tuple[ArtifactState, Optional[str]]]",
    obligations: "List[Obligation]",
    notices: "List[Notice]",
) -> None:
    """Per approved downstream, the shared ``binding_report`` (AD11): each
    superseded binding is an upstream-drift obligation; each unbound downstream
    an informational ``unbound`` notice (AD17). Same wording in both tiers."""
    texts = {st.name: text for st, text in states}
    for st, text in states:
        if st.name not in UPSTREAM_SETS or not st.approved or text is None:
            continue
        rep = binding_report(
            st.name, text, {up: texts.get(up) for up in UPSTREAM_SETS[st.name]}
        )
        for b in rep.superseded:
            rec = ", ".join(v[:8] for v in b.recorded)
            obligations.append(
                Obligation(
                    kind=OBLIGATION_UPSTREAM_DRIFT,
                    detail=(
                        f"{st.name} was approved against {b.upstream} @ {rec}, but "
                        f"{b.upstream} is now {display_text(b.current[:16])[:8]} ({b.reason})"
                    ),
                    next_action=f"run the consistency check, then re-approve {st.name}, top-down",
                )
            )
        if rep.unbound:
            notices.append(
                Notice(
                    kind=NOTICE_UNBOUND,
                    subject=st.name,
                    detail=f"no upstream binding for {', '.join(rep.unbound)}",
                    route=_UNBOUND_ROUTE,
                )
            )


def _append_marker_obligations(
    project_root: Path,
    target_rel: str,
    obligations: "List[Obligation]",
    notices: "List[Notice]",
    *,
    running_tier: str,
) -> None:
    """Read the pending-review marker via the STRICT path; partition it (R1).

    The first catch-and-continue caller of the strict path (every existing strict
    caller aborts): a `MarkerCorruptError` becomes a `marker-unreadable`
    obligation and is NEVER laundered into "no obligations" by falling back to the
    non-strict reader. An absent marker reads as empty-pending (no obligation).

    Unit C0 (AD14/AD17): keys are partitioned by the raw ``_prefix_in_scope``
    test the target's approval gate applies. In-scope keys are obligations; an
    in-scope key owned by another scope (a root or parent target, R1's known
    limit) gets the AD16 "owned by ..." next action. Every other key becomes a
    ``pending-elsewhere`` notice grouped by scope (out-of-lane
    containment-escaping keys form one ``(no scope)`` group), never an
    obligation and never a decline from the current target.
    """
    try:
        data = read_pending_review(project_root, strict=True)
    except MarkerCorruptError as exc:
        obligations.append(
            Obligation(
                kind=OBLIGATION_MARKER_UNREADABLE,
                detail=f".sdd/pending-review.json is present but unreadable/corrupt ({exc})",
                next_action="inspect/repair .sdd/pending-review.json (or clear it with --decline-pending)",
            )
        )
        return
    keys = list(data.get("pending", {}))
    in_scope, elsewhere = partition_keys(keys, target_rel)
    own_scope = target_rel if target_rel not in ("", ".") else "."
    for doc_rel in in_scope:
        if scope_of_key(doc_rel) == own_scope:
            next_action = "run the panel + stamp the tag, or decline with --decline-pending"
        else:
            next_action = owning_dir_route(
                project_root, doc_rel, keys, target_rel=target_rel,
                running_tier=running_tier, use="run-state",
            )
        obligations.append(
            Obligation(
                kind=OBLIGATION_PENDING_REVIEW,
                detail=f"upstream panel re-review pending for {display_text(doc_rel, max_len=DISPLAY_ARG_MAX)}",
                next_action=next_action,
            )
        )
    groups: "dict[str, List[str]]" = {}
    for k in elsewhere:
        subject = NO_SCOPE_SUBJECT if is_containment_escaping(project_root, k) else scope_of_key(k)
        groups.setdefault(subject, []).append(k)
    for subject in sorted(groups, key=lambda s_: (s_ == NO_SCOPE_SUBJECT, s_)):
        ks = groups[subject]
        n = len(ks)
        notices.append(
            Notice(
                kind=NOTICE_PENDING_ELSEWHERE,
                subject=subject,
                detail=f"{n} obligation{'s' if n != 1 else ''}",
                route=owning_dir_route(
                    project_root, ks[0], keys, target_rel=target_rel,
                    running_tier=running_tier, use="run-state",
                ),
            )
        )


def derive_run_state(
    *,
    tier: str,
    artifact_dir: Path,
    project_root: Path,
    phases: "List[Tuple[str, str]]",
    terminal_phase_label: "Optional[str]",
    tick_hint_artifact: "Optional[str]",
) -> RunState:
    """Derive the run-state summary read-only from disk. [I1; AD11-L1]

    Reads each artifact via `resolve_artifact` + a degraded-read-guarded raw
    read, computes approved/hash status (splitting a pure hash-basis migration
    from genuine drift, AD4), derives the current phase (AD3), sets the Phase-4
    tick_hint (AD6), and reads the pending-review marker via the STRICT path.
    Performs the REAL per-primitive catches (Layer 1) so no reachable read
    exception propagates; never mutates any file; imports only shared leaves
    (AD2 — no validator import). A broad Layer-2 backstop in each validator's
    `_handle_run_state` guards anything this layer misses.
    """
    obligations: "List[Obligation]" = []
    states = [
        _derive_artifact_state(artifact_dir, bare_name, obligations)
        for _label, bare_name in phases
    ]
    artifacts = [st for st, _text in states]

    pairs = [(label, state) for (label, _bare), state in zip(phases, artifacts)]
    current_phase, next_step = _derive_current_phase(pairs, terminal_phase_label)

    # AD6 Phase-4 tick hint: only when the tier HAS a Phase 4 (terminal label),
    # we are at that terminal phase (all artifacts approved), and the tick-hint
    # artifact is STALE (genuine drift) — never STALE_MIGRATION (a hash-basis
    # migration is not task-ticks).
    if (
        tick_hint_artifact is not None
        and terminal_phase_label is not None
        and current_phase == terminal_phase_label
    ):
        for a in artifacts:
            if a.name == tick_hint_artifact and a.hash_status == HashStatus.STALE:
                a.tick_hint = True

    notices: "List[Notice]" = []
    try:
        target_rel = Path(
            os.path.relpath(Path(artifact_dir).resolve(), Path(project_root).resolve())
        ).as_posix()
    except (OSError, ValueError):
        target_rel = "."
    _append_marker_obligations(
        project_root, target_rel, obligations, notices, running_tier=tier
    )
    _append_binding_state(states, obligations, notices)

    return RunState(
        tier=tier,
        current_phase=current_phase,
        artifacts=artifacts,
        obligations=obligations,
        next_step=next_step,
        notices=notices,
    )


# --- I2: compact sanitized renderer (AD13/AD14) -----------------------------

# Soft body-line ceiling (AD13). Met by collapsing CLEAN artifacts and, only if
# still exceeded, an overflow line — never by dropping an obligation.
_MAX_LINES = 24
# Per-line length cap (AD14). Bounds one oversized field to one screen width.
_LINE_CAP = 200
# _ANSI_RE (CSI escapes) and _CONTROL_RE (control chars except tab/newline/CR,
# which the newline collapse below handles) are the approval_records objects,
# imported at the top (Unit C0 AD1).

# Integrity obligation kinds — never dropped at the ceiling, ordered first so
# they are never the first thing truncated (AD13).
_INTEGRITY_KINDS = (OBLIGATION_MARKER_UNREADABLE, OBLIGATION_DEGRADED_READ)


def _sanitize(text: str, cap: bool = True) -> str:
    """Neutralize a rendered field before it reaches stdout. [AD14]

    Collapses `\\n` / `\\r` / `\\t` to a single space FIRST (so no field can
    expand into multiple physical lines or spoof a fake status line), then strips
    ANSI escape sequences and other control characters, then truncates to a
    per-line length cap. Because newlines are collapsed first, one field is
    guaranteed one physical line, so the AD13 line count taken over sanitized
    fields is valid. Idempotent.

    Deliberately NOT `spec_dirname.display_safe` (unicode_escape): that helper
    renders escapes as visible literal text for a single inline identifier and
    has no length cap; this renderer needs multi-field lines collapsed to
    exactly one physical line each AND length-capped, which unicode_escape
    alone doesn't give.

    ``cap=False`` (Unit C0 AD16) exempts a line that carries a route command or
    a gloss from the per-line cap, so a command is never cut mid-argument.
    """
    text = str(text)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = _ANSI_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    if cap and len(text) > _LINE_CAP:
        text = text[: _LINE_CAP - 1] + "…"
    return text


def _artifact_is_clean(a: ArtifactState) -> bool:
    """A CLEAN artifact collapses (no line): an approved+coherent artifact, or a
    genuinely-absent not-started phase. Everything else (STALE / STALE_MIGRATION
    / DEGRADED / present-but-unapproved) is non-clean and gets a line."""
    if a.approved and a.hash_status == HashStatus.MATCHES:
        return True
    if not a.exists and a.hash_status == HashStatus.NA:
        return True
    return False


def _artifact_next_action(a: ArtifactState) -> str:
    """The per-artifact next-action, derived HERE from `hash_status` (AD4) — the
    two stale labels MUST render DISTINCT next-actions, never one generic line."""
    if a.hash_status == HashStatus.STALE:
        return "run --approve; a panel re-review is owed unless --approve reports otherwise"
    if a.hash_status == HashStatus.STALE_MIGRATION:
        return "re-stamp only — no panel re-review"
    if a.hash_status == HashStatus.DEGRADED:
        return "unverifiable — see the degraded-read obligation below"
    if a.exists and not a.approved:  # present but not yet approved
        return "finish and approve this phase"
    return ""


def _artifact_line(a: ArtifactState) -> str:
    parts = f"  {_sanitize(a.name)}: {_sanitize(a.hash_status.value)}"
    action = _artifact_next_action(a)
    if action:
        parts += f" — {_sanitize(action)}"
    if a.tick_hint:
        parts += " — may be expected task-tick ticks; run the full validator to confirm"
    return _sanitize(parts)


def _obligation_line(o: Obligation) -> str:
    # The next action may carry a route command: exempt it (and the outer line)
    # from the per-line cap; the detail keeps it (AD16).
    return _sanitize(
        f"  - {_sanitize(o.kind)}: {_sanitize(o.detail)} → {_sanitize(o.next_action, cap=False)}",
        cap=False,
    )



_RUN_STATE_ROUTE_EXISTS_PREFIX = "owned by "
_BACKTICKED_RE = re.compile(r"`([^`]*)`")


def _notice_count(n: Notice) -> int:
    head = n.detail.split(" ", 1)[0]
    return int(head) if head.isdigit() else 1


def _expanded_notice_line(n: Notice) -> str:
    if n.kind == NOTICE_PENDING_ELSEWHERE:
        text = (
            f"  {PENDING_ELSEWHERE_LABEL}: {_sanitize(n.subject)} — "
            f"{_sanitize(n.detail)} — {_sanitize(n.route, cap=False)}"
        )
    else:
        text = f"  {_sanitize(n.kind)}: {_sanitize(n.subject)} — {_sanitize(n.detail)} — {_sanitize(n.route, cap=False)}"
    return _sanitize(text, cap=False)


def _collapsed_pending_elsewhere_route(group: "List[Notice]") -> str:
    """Route for the collapsed line: start from the first listed scope whose
    directory exists (its run-state route is the 'owned by' template), printed
    as that scope's ``--run-state`` command; AD16's project-root template when
    ``(no scope)`` is the only group."""
    for n in group:
        if n.subject != NO_SCOPE_SUBJECT and n.route.startswith(_RUN_STATE_ROUTE_EXISTS_PREFIX):
            cmds = [
                c.replace("--decline-pending", "--run-state")
                for c in _BACKTICKED_RE.findall(n.route)
            ]
            if cmds:
                shown = " or ".join(f"`{c}`" for c in cmds)
                return f"resolve each from its own directory, starting with {shown}"
    return group[0].route


def _collapsed_notice_line(kind: str, group: "List[Notice]") -> str:
    if kind == NOTICE_PENDING_ELSEWHERE:
        listed = ", ".join(
            f"{_sanitize(n.subject)} ({_notice_count(n)})" for n in group[:3]
        )
        more = f" and {len(group) - 3} more" if len(group) > 3 else ""
        route = _collapsed_pending_elsewhere_route(group)
        return _sanitize(
            f"  {PENDING_ELSEWHERE_LABEL}: {listed}{more} — {_sanitize(route, cap=False)}",
            cap=False,
        )
    subjects = ", ".join(_sanitize(n.subject) for n in group)
    return _sanitize(
        f"  {_sanitize(kind)}: {subjects} — {_sanitize(group[0].route, cap=False)}",
        cap=False,
    )


def _notice_groups(state: RunState) -> "List[Tuple[str, List[Notice]]]":
    order = [NOTICE_PENDING_ELSEWHERE, NOTICE_UNBOUND]
    out = []
    for kind in order + sorted({n.kind for n in state.notices} - set(order)):
        group = [n for n in state.notices if n.kind == kind]
        if group:
            out.append((kind, group))
    return out


def _render_notices(state: RunState, remaining: int) -> "List[str]":
    """Notice lines within ``remaining`` slots (AD17 budget step 4, AC-1.2):
    every notice prints expanded only if all of them fit; otherwise each kind
    collapses to one summary line."""
    groups = _notice_groups(state)
    expanded = []
    for kind, group in groups:
        if kind == NOTICE_UNBOUND:
            # AC-4.4 / AD17: always ONE unbound line naming every unbound artifact.
            expanded.append(_collapsed_notice_line(kind, group))
        else:
            expanded.extend(_expanded_notice_line(n) for n in group)
    if len(expanded) <= remaining:
        return expanded
    return [_collapsed_notice_line(kind, group) for kind, group in groups]


def format_run_state(state: RunState) -> str:
    """Render the compact, sanitized one-screen summary. [I2; AD13/AD14]

    Fully-clean directory -> a <=2-line all-clear pointing at the next step
    (plus any informational notices). Otherwise, in fixed order: (1)
    header/phase line, (2) non-clean artifact lines (clean artifacts collapse),
    (3) obligations block, (4) notices. Integrity obligations (marker-unreadable
    / degraded-read) and open pending-review obligations are NEVER dropped, even
    past the soft <=24-line ceiling.

    Budget (Unit C0 AD17), in priority order: (1) header and obligations, never
    dropped; (2) one collapsed line per notice kind present, reserved; (3)
    non-clean artifact lines in what remains, with "+N more" only if even they
    do not fit; (4) notices expanded instead of collapsed only if the expanded
    form fits in what is left. Every field is routed through `_sanitize`. Pure
    function (no I/O).
    """
    n_kinds = len(_notice_groups(state))
    fully_clean = not state.obligations and all(
        _artifact_is_clean(a) for a in state.artifacts
    )
    if fully_clean:
        header = _sanitize(f"run-state [{state.tier}] — current phase: {state.current_phase}")
        # AC-4.4: an unbound approved downstream qualifies the all-clear.
        clear = (
            "all clear (upstream binding unverified)"
            if any(n.kind == NOTICE_UNBOUND for n in state.notices)
            else "all clear"
        )
        lines = [header, _sanitize(f"{clear} — {state.next_step}")]
        lines += _render_notices(state, max(_MAX_LINES - len(lines), n_kinds))
        return "\n".join(lines)

    header = [_sanitize(f"run-state [{state.tier}] — current phase: {state.current_phase} · next: {state.next_step}")]

    artifact_lines = [_artifact_line(a) for a in state.artifacts if not _artifact_is_clean(a)]

    # Obligations are NEVER dropped; integrity kinds first so they are never the
    # first thing truncated (AD13).
    ordered_obs = [o for o in state.obligations if o.kind in _INTEGRITY_KINDS] + [
        o for o in state.obligations if o.kind not in _INTEGRITY_KINDS
    ]
    obligation_lines = ["obligations:"] + [_obligation_line(o) for o in ordered_obs] if ordered_obs else []

    # Header, obligations and one collapsed line per notice kind consume the
    # budget first; residual non-clean artifact lines beyond the remaining
    # budget collapse into a single "+N more" overflow line rather than being
    # silently dropped.
    reserved = len(header) + len(obligation_lines) + n_kinds
    budget = _MAX_LINES - reserved
    if budget < 0:
        budget = 0
    if len(artifact_lines) > budget:
        # The overflow line itself occupies one slot of the budget — keep
        # budget - 1 real lines so the total never exceeds _MAX_LINES.
        keep = budget - 1 if budget > 0 else 0
        dropped = len(artifact_lines) - keep
        artifact_lines = artifact_lines[:keep] + [
            _sanitize(f"  +{dropped} more — run the full validator")
        ]

    used = len(header) + len(artifact_lines) + len(obligation_lines)
    notice_lines = _render_notices(state, max(_MAX_LINES - used, n_kinds))
    return "\n".join(header + artifact_lines + obligation_lines + notice_lines)


def safe_print(text: str) -> None:
    """BrokenPipe-safe print (AD11-E) — shared so both validators' `--run-state`
    handler cannot drift on this zero-variance helper (unlike `_handle_run_state`
    itself, which genuinely varies per tier and stays validator-side)."""
    try:
        print(text)
    except BaseException:
        pass
