"""Pending-review marker lifecycle — extracted from blueprint_common (audit R3.1).

The `.sdd/pending-review.json` marker: atomic read/write, the reentrant
cross-process advisory lock, the obligation lifecycle (upsert / preserve /
restamp / clear / reconcile / restore-anchor), and the reconcile_to_result
ValidationResult builder. Pulled into its own module so blueprint_common is no
longer a God module mixing pure parsing/hashing with filesystem I/O (a split the
module's own long-standing note had planned).

Import discipline: this module imports the hashing/trajectory/result PRIMITIVES
from blueprint_common, and blueprint_common re-exports the marker public names
from here at the BOTTOM of that file — so the load order is always
blueprint_common first, and every existing `from blueprint_common import
upsert_pending_entry` (etc.) keeps working unchanged. Do not import
pending_review before blueprint_common.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

# Best-effort staleness window (seconds) for the panel-findings sweep: a matched
# findings file modified within this window is left in place as defense-in-depth
# against a same-feature concurrent double-validate writer (design C6/DR5). Not a
# correctness guarantee — a mistaken delete degrades only to a DISCLOSED
# missing-file → AD7 fallback, never a silent drop.
STALE_WINDOW_SECS = 300

try:  # POSIX advisory file locking (audit R3.4)
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - non-POSIX
    _fcntl = None
try:  # Windows advisory file locking
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover - non-Windows
    _msvcrt = None

from blueprint_common import (  # noqa: E402
    DECLINE_FLAGGED_ANOMALOUS_MSG,
    DECLINE_UNSATISFIABLE_HELD_BACK_MSG,
    EXIT_DECLINE_HELD_BACK,
    HASH_BASIS_MIGRATION_SUPPRESS_MSG,
    MARKER_RELPATH,
    MARKER_SCHEMA_VERSION,
    MarkerCorruptError,
    REAPPROVAL_REMINDER,
    REVERSED_ORDER_CREATE_WARN,
    STRANDED_OBLIGATION_TOKEN,
    UNSATISFIABLE_OBLIGATION_TOKEN,
    UPSTREAM_PANEL_TAG_RE,
    ValidationResult,
    _is_ascii_int,
    _is_valid_16_hex,
    _row_first_cell,
    _trajectory_data_rows,
    _trajectory_row_notes,
    changed_since_stamp,
    content_for_hashing,
    find_orphaned_trajectory_rows,
    is_basis_migration_only,
    now_iso_utc,
    stamped_at_pass_from_content,
)


def _marker_path(project_root: Path) -> Path:
    return Path(project_root) / MARKER_RELPATH


# --- Cross-process marker lock (audit R3.4) --------------------------------
#
# Every .sdd/pending-review.json operation is a read-modify-write: write is
# atomic (mkstemp + os.replace), but two concurrent processes (e.g. parallel
# --approve runs in a multi-subagent workflow) can both read the same baseline
# and have the second os.replace erase the first's just-added entry — silently
# dropping a re-approval obligation (fail-open). An exclusive advisory lock on a
# sibling `.sdd/pending-review.lock` serializes the read→write so the loser
# re-reads the winner's state. Reentrant within a process (the operations nest:
# restamp_or_suppress -> upsert/preserve) via a depth counter; best-effort —
# where neither fcntl nor msvcrt exists the lock degrades to a no-op (single-
# process correctness is unaffected; only the cross-process race is left open).
_marker_lock_depth = 0


@contextlib.contextmanager
def _marker_lock(project_root: Path):
    global _marker_lock_depth
    if _marker_lock_depth > 0:  # already held by this process — reenter
        _marker_lock_depth += 1
        try:
            yield
        finally:
            _marker_lock_depth -= 1
        return
    lock_path = _marker_path(project_root).with_name("pending-review.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+")
    try:
        if _fcntl is not None:
            _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
        elif _msvcrt is not None:  # pragma: no cover - Windows
            fh.seek(0)
            _msvcrt.locking(fh.fileno(), _msvcrt.LK_LOCK, 1)
        _marker_lock_depth = 1
        try:
            yield
        finally:
            _marker_lock_depth = 0
            if _fcntl is not None:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
            elif _msvcrt is not None:  # pragma: no cover - Windows
                fh.seek(0)
                _msvcrt.locking(fh.fileno(), _msvcrt.LK_UNLCK, 1)
    finally:
        fh.close()


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

    INVARIANT (load-bearing for `sweep_sdd_cruft`'s NB-gate correctness): every
    caller of this function MUST hold `_marker_lock`. The unique `.tmp` staged
    here lives, under that lock, for the whole write — so `sweep_sdd_cruft` can
    treat a successful non-blocking lock acquire as proof that no
    write_pending_review() is in flight and every `*.tmp` is genuinely abandoned.
    Currently held by all four callers (upsert_pending_entry,
    clear_pending_entries_for_prefix, reconcile_pending_review,
    restore_anchor_for_prefix). A future direct caller that omits the lock would
    silently reopen the concurrent-writer `*.tmp` race. (Enforced by docstring,
    not a runtime assert: test_write_pending_review_atomic calls this directly,
    without the lock, to exercise atomicity.)
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
    reset other features' obligations to {}). The read→write is held under the
    cross-process marker lock so a concurrent op can't lose this entry (R3.4).
    """
    with _marker_lock(project_root):
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
    # Hold the lock across read_open_obligation -> preserve/upsert so the whole
    # decision is atomic vs a concurrent marker op (R3.4). The nested upsert /
    # preserve reenter the lock (no-op).
    with _marker_lock(marker_root):
        _restamp_or_suppress_locked(
            content_hash,
            stored_hash=stored_hash,
            original_content=original_content,
            content_trimmed=content_trimmed,
            marker_root=marker_root,
            doc_rel=doc_rel,
        )


def _restamp_or_suppress_locked(
    content_hash: str,
    *,
    stored_hash: str,
    original_content: str,
    content_trimmed: str,
    marker_root: Path,
    doc_rel: str,
) -> None:
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
        anchor = stamped_at_pass_from_content(original_content)
        upsert_pending_entry(
            marker_root,
            doc_rel,
            content_hash,
            now_iso_utc(),
            anchor,
        )
        print(REAPPROVAL_REMINDER)
        # R4/AD7: reversed-order ("review-then-approve") WARN — additive-only, this
        # create arm ONLY; a pure print gated on the content-derived signal, no
        # marker-state change (the R9-preserve and basis-migration arms are
        # untouched). Fires on Variant A (tag on the anchor row at approve time);
        # Variant B is an accepted no-fire caught downstream by the reconcile
        # UNSATISFIABLE-OBLIGATION diagnostic (RK-D2).
        if _anchor_row_carries_tag(original_content, anchor):
            print(REVERSED_ORDER_CREATE_WARN.format(doc_rel=doc_rel))
    else:
        print(HASH_BASIS_MIGRATION_SUPPRESS_MSG.format(doc_rel=doc_rel))


def clear_pending_entries_for_prefix(project_root: Path, prefix: str) -> list[str]:
    """Remove pending entries whose key == prefix or starts with prefix + '/'. [T1; I6]

    WARNING (order-independent-anchor / ARCH-M2): this is NO LONGER the CLI
    `--decline-pending` entry point — both validators now route through
    `partition_decline_clear`, which honors the hard floor (never clears an
    UNSATISFIABLE-with-tag obligation). This all-or-nothing primitive is retained
    for its other callers/tests; a NEW caller wiring `--decline-pending` back to it
    would silently reintroduce the mis-record bug `partition_decline_clear` closes.

    Pure string prefix-matching (no path resolution — needs no AD12 guard).
    `startswith(prefix + '/')` avoids prefix-bleed (feat-a vs feat-a-extra).
    Returns removed keys; deletes the marker file when `pending` becomes empty.
    Reads strict=True (refuse to clobber a corrupt marker). Read→write held under
    the cross-process marker lock (R3.4).
    """
    with _marker_lock(project_root):
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


# ----- R2: partitioned --decline-pending (order-independent-anchor, C1) -----


def _doc_has_matching_orphaned_tag(content: str, hash_short: str) -> bool:
    """True iff a load-bearing ORPHANED Trajectory row carries THIS entry's own
    `upstream-panel <hash_short>` tag (SEC-H1 / SEC2-M1).

    `_obligation_is_unsatisfiable` only scans CONTIGUOUS rows, so a genuine tag
    stranded on an orphaned row (a stray blank line, or a hand-run archive_pass —
    the reversed-order operator's profile) is invisible to it and the key would
    mis-clear a performed panel. Hash-scoping to the entry's own hash[:8] stops a
    STALE prior-cycle orphaned tag from blocking a later, unrelated conscious-waive
    (SEC2-M1). RAW content only (never content_for_hashing output — H4-security).
    Pure read.
    """
    for orphan in find_orphaned_trajectory_rows(content):
        if orphan.get("has_upstream_tag") and _row_has_tag(orphan.get("text", ""), hash_short):
            return True
    return False


def _anchor_row_carries_tag(content: str, anchor_pass: int) -> bool:
    """True iff SOME `### Trajectory` row whose Pass == anchor_pass carries a
    genuine `upstream-panel` tag — the 'tag-before-approve' reversed-order
    fingerprint (R4/AD2).

    OR across every row matching anchor_pass (a hand-edited table may duplicate a
    pass), mirroring `_doc_has_qualifying_tag`'s per-row scan. anchor_pass <= 0 ->
    False (a first-approval anchor has no archived row to tag). RAW content only
    (never content_for_hashing output — the v2 strip removes every tag;
    H4-security). Pure read.

    COVERAGE (AD2): fires on Variant A (tag stamped on the anchor row BEFORE the
    create-approve). It CANNOT fire on Variant B (archive an untagged row ->
    approve -> tag afterward), which is content-identical at create time to the
    ordinary converged-untagged row (R4 AC2 no-fire) — Variant B is caught
    downstream by reconcile's UNSATISFIABLE-OBLIGATION diagnostic + the R2
    decline-guard (accepted no-fire, RK-D2).
    """
    if anchor_pass <= 0:
        return False
    for row in _trajectory_data_rows(content):
        first = _row_first_cell(row)
        if (
            _is_ascii_int(first)
            and int(first) == anchor_pass
            and UPSTREAM_PANEL_TAG_RE.search(_trajectory_row_notes(row))
        ):
            return True
    return False


def partition_decline_clear(
    project_root: Path, path_prefix: str
) -> "tuple[list[str], list[str], list[str]]":
    """Selectively clear declinable pending entries under `path_prefix`. [R2/AD3]

    Partitions each in-scope key into three buckets, then clears only the
    declinable ones under ONE `_marker_lock` hold:
      - HELD BACK (the hard floor — never cleared; wins over FLAGGED): a valid
        16-hex, contained key that is either UNSATISFIABLE by
        `_obligation_is_unsatisfiable` (genuine contiguous tag on a pass <= anchor)
        OR carries a load-bearing ORPHANED tag matching its own hash[:8]
        (`_doc_has_matching_orphaned_tag`, SEC-H1). Declining either would
        mis-record a genuinely-performed panel as skipped.
      - FLAGGED (cleared, but surfaced with a distinct WARN): the entry could not
        be classified — malformed/non-16-hex hash, or a containment-escaping key.
        Cleared (a valid waive, matching clear_pending_entries_for_prefix's
        behavior) but never folded silently into the "cleared normally" narrative
        (SEC-M1).
      - CLEARED: everything else, incl. a genuinely-owed UNTAGGED obligation (the
        conscious-waive path — unaffected).
    Strict read (MarkerCorruptError propagates — never clobbers a corrupt shared
    marker). ONE `_read_contained_doc` per key threads both the unsatisfiable and
    orphaned-tag checks (single read — avoids a TOCTOU + redundant I/O). Persists
    via `_persist_or_unlink_marker` only when something was cleared or flagged.
    Iterates a `list(pending)` snapshot (delete-inside-loop safe). Returns
    `(cleared, held_back, flagged)`.
    """
    with _marker_lock(project_root):
        data = read_pending_review(project_root, strict=True)
        pending = data["pending"]
        cleared: "list[str]" = []
        held_back: "list[str]" = []
        flagged: "list[str]" = []
        for key in list(pending):
            if not _prefix_in_scope(key, path_prefix):
                continue
            entry = pending[key]
            h = entry.get("hash")
            valid = (
                isinstance(h, str)
                and _is_valid_16_hex(h)
                and _key_is_contained(project_root, key)
            )
            held = False
            if valid:
                content = _read_contained_doc(project_root, key)
                hash_short = h[:8]
                if _obligation_is_unsatisfiable(project_root, key, entry) or (
                    content is not None
                    and _doc_has_matching_orphaned_tag(content, hash_short)
                ):
                    held = True
            if held:
                held_back.append(key)              # hard floor: NOT cleared
            elif not valid:
                flagged.append(key)                # cleared, but surfaced
                del pending[key]
            else:
                cleared.append(key)                # conscious-waive / declinable
                del pending[key]
        if cleared or flagged:
            _persist_or_unlink_marker(project_root, data)
        return cleared, held_back, flagged


def format_decline_output(
    cleared: "list[str]", held_back: "list[str]", flagged: "list[str]", *, restore_cmd: str
) -> "tuple[str, int]":
    """Build the --decline-pending operator message + exit code. Pure. [R2/AD4/AD5]

    Names every NON-EMPTY set in one output (so a partial result is never misread
    as total failure by a scripted/CI caller); each held-back line states WHY
    decline is wrong here + names `restore_cmd` and never the word "legacy"; each
    flagged line is surfaced with the anomalous-key WARN. Exit code is 0 only when
    both `held_back` and `flagged` are empty, else EXIT_DECLINE_HELD_BACK (3). The
    all-three-empty no-op case is handled by the caller before this is invoked.
    """
    lines: "list[str]" = []
    if cleared:
        noun = "entry" if len(cleared) == 1 else "entries"
        lines.append(
            f"Declined upstream panel re-review; cleared {len(cleared)} pending "
            f"{noun}: {', '.join(cleared)}"
        )
    for key in held_back:
        lines.append(
            DECLINE_UNSATISFIABLE_HELD_BACK_MSG.format(doc_rel=key, restore_cmd=restore_cmd)
        )
    for key in flagged:
        lines.append(DECLINE_FLAGGED_ANOMALOUS_MSG.format(doc_rel=key))
    code = 0 if (not held_back and not flagged) else EXIT_DECLINE_HELD_BACK
    return "\n".join(lines), code


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
    The read→write is held under the cross-process marker lock (R3.4) so a
    concurrent upsert can't be lost — a clear is idempotently re-derivable from
    the Trajectory, but a reconcile interleaving an upsert could otherwise
    resurrect a just-cleared entry or drop a just-created one.
    """
    with _marker_lock(project_root):
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
    """Content-attested remedy for unsatisfiable obligations — a fresh reversed-order re-approval OR a legacy re-anchored marker. [R9/C3]

    For each pending entry under `path_prefix` whose doc carries a GENUINE
    `upstream-panel <hash[:8]>` tag on ANY archived Trajectory row, clear the
    obligation — the tag is the proof the panel ran, so restoring the anchor so
    it reconciles is equivalent to clearing it. It clears ONLY when the genuine
    tag is present (content-attested — never a free "mark satisfied", H5); an
    obligation with no qualifying tag is left pending. Reads strict=True (a
    corrupt SHARED marker is never clobbered). A tag stranded on an ORPHANED row
    is invisible here (R10 surfaces it first); the operator makes it contiguous,
    then this clears it. Returns the cleared keys. Read→write held under the
    cross-process marker lock (R3.4).
    """
    with _marker_lock(project_root):
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

    # The marker parsed (reconcile_pending_review succeeded above); a non-strict
    # re-read fetches the remaining entry fields for classification and the
    # stranded-obligation scan.
    pending = read_pending_review(project_root, strict=False)["pending"]

    # Stranded-obligation surfacing (audit 3.5d). A pending entry whose target
    # file no longer exists AND is outside this run's prefix scope is typically a
    # renamed/deleted spec directory: the file moved out of scope, so the
    # prefix-scoped reconcile never sees it and it can't be declined from the new
    # directory. Surface it as a WARN (out-of-scope only — an in-scope missing
    # file already surfaces as the FAIL below) so the obligation is never silent.
    root = Path(project_root)
    for key in pending:
        if _prefix_in_scope(key, path_prefix):
            continue
        if not _key_is_contained(root, key):
            continue  # hostile keys own a separate WARN inside reconcile
        if not (root / key).exists():
            result.add(
                "pending-review",
                False,
                f"{STRANDED_OBLIGATION_TOKEN} pending-review entry for {key} points "
                f"at a file that no longer exists (likely a renamed or deleted spec "
                f"directory). The obligation is outside this run's scope, so it can "
                f"neither reconcile nor be declined from here. Restore the original "
                f"path, or decline it against its original location.",
                warn_only=True,
            )

    if not still_pending:
        return result
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
                f"above the anchor) can never satisfy it. It arose either as a fresh "
                f"reversed-order re-approval (a panel pass archived before the "
                f"re-approve) or a legacy re-anchored marker.{restore_hint} "
                f"Content-attested: it clears only because the "
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


# ----- Best-effort .sdd/ cruft cleanup ------------------------------------


def _sweep_panel_findings(sdd_dir: Path, findings_scope: Optional[str]) -> None:
    """Remove this run's own `.sdd/panel-findings/<findings_scope>/*.md` (C6).

    Guarded DIFFERENTLY from the *.tmp/lock pass (NOT by the marker lock — a
    panelist Write to a findings file never touches _marker_lock or
    write_pending_review(), so the NB marker-lock acquire proves nothing about a
    findings writer):
      (a)  TWO-LEVEL TIER/SLUG SCOPING — `findings_scope` is a tier-qualified
           RELATIVE subpath (`sdd/<spec-dir-basename>` for the SDD tier, or the
           literal `blueprint` for the blueprint tier). Built with path-JOIN,
           never string-prefix, so `sdd/foo` can never reach `sdd/foo-bar/`, a
           sibling feature, or the other tier.
      (a2) PATH-COMPONENT SAFETY (MED-3) — skip entirely if the scope is absolute,
           carries any `..`/`.` segment, or has an empty component.
      (b)  STALENESS GUARD — skip any matched file modified within
           STALE_WINDOW_SECS (best-effort defense against a concurrent writer).
    `findings_scope` None/empty skips the pass. After removing the matched
    `*.md`, rmdir the leaf subdir if empty, then each ancestor UP TO (but never
    including) `panel-findings/` if it too ends empty (so the intermediate `sdd/`
    parent is reclaimed only when the last feature under it is gone; the
    one-level `blueprint` scope has no such intermediate — DEF-01).

    DEF-02 self-heal note: a panelist's `Write` auto-creates the parent dirs of
    its findings file, so an absent `panel-findings/` (or scope subtree) is the
    normal pre-feature state — this pass early-returns cleanly and the next
    panel pass recreates whatever it needs. Never raises; swallows OSError; never
    touches pending-review.json or architecture.json.
    """
    try:
        if not findings_scope:
            return
        scope = str(findings_scope)
        # Path-component safety (MED-3): reject absolute / .. / . / empty component.
        if os.path.isabs(scope):
            return
        parts = scope.replace("\\", "/").split("/")
        if any(p in ("", "..", ".") for p in parts):
            return
        pf_root = sdd_dir / "panel-findings"
        target = pf_root
        for p in parts:
            target = target / p                             # path-JOIN, not prefix
        if not target.is_dir():
            return
        now = time.time()
        for md in target.glob("*.md"):
            try:
                if now - md.stat().st_mtime < STALE_WINDOW_SECS:
                    continue                                # staleness guard (b)
                md.unlink()
            except OSError:
                pass
        # rmdir the leaf, then ancestors up to (exclusive) panel-findings/.
        d = target
        while d != pf_root and d.is_dir():
            try:
                d.rmdir()                                   # succeeds only if empty
            except OSError:
                break
            d = d.parent
    except Exception:
        pass                                                # best-effort (R4)


def sweep_sdd_cruft(marker_root: Path, *, findings_scope: Optional[str] = None) -> None:
    """Best-effort cleanup of orphaned .sdd/ cruft.

    Removes *.tmp files (abandoned atomic-write temps from write_pending_review())
    and unlinks pending-review.lock when provably uncontested. A single non-blocking
    LOCK_EX | LOCK_NB acquire on pending-review.lock is the unified gate for BOTH
    operations: a successful acquire proves no write_pending_review() is in flight
    (so every *.tmp is genuinely abandoned and both files are safe to remove);
    BlockingIOError / OSError means a concurrent writer holds the lock, so cleanup
    skips both and leaves them for a later run.

    On platforms without fcntl or msvcrt, runs both cleanup operations
    unconditionally (the lock is already a no-op there; nothing to protect).

    INVARIANT (load-bearing for gate correctness): every caller of
    write_pending_review() MUST hold _marker_lock. Currently verified for all four
    callers: upsert_pending_entry, clear_pending_entries_for_prefix,
    reconcile_pending_review, restore_anchor_for_prefix. A future direct caller
    that violates this invariant reopens the concurrent-writer *.tmp race.

    Never raises. Never changes the caller's process exit code. Never touches
    architecture.json or pending-review.json. Never calls mkdir; if .sdd/ is absent,
    returns immediately.

    Args:
        marker_root: The project root that *contains* .sdd/ — pass the first
            element of _resolve_marker_root_and_key(spec_dir, project_root), the
            SAME write-side root the run's marker operations use. NOT the .sdd/
            directory itself; NOT raw args.project_root (which may be None and,
            when a non-ancestor --project-root is supplied, differs from the
            write-side root — using it would sweep the wrong .sdd/).
        findings_scope: Tier-qualified RELATIVE subpath of the panel-findings
            subtree this run covered — `sdd/<spec-dir-basename>` for the SDD tier
            or the literal `blueprint` for the blueprint tier. Drives the C6
            panel-findings cleanup pass (see _sweep_panel_findings). None/empty
            (the default) skips that pass entirely; the *.tmp/lock cleanup is
            unaffected either way.
    """
    try:
        sdd_dir = _marker_path(marker_root).parent          # marker_root/.sdd
        if not sdd_dir.is_dir():
            return
        # Panel-findings pass (C6) — NOT gated by the marker lock; runs on every
        # platform regardless of the *.tmp/lock gate outcome below.
        _sweep_panel_findings(sdd_dir, findings_scope)
        lock_path = _marker_path(marker_root).with_name("pending-review.lock")

        if _fcntl is None and _msvcrt is None:              # no-lock platform (AD3)
            # Sweep *.tmp BEFORE unlinking lock — reversing this order reopens
            # Risk-1b obligation-drop.
            for tmp in sdd_dir.glob("*.tmp"):
                try:
                    tmp.unlink()
                except OSError:
                    pass
            try:
                lock_path.unlink()
            except OSError:
                pass
            return

        # Locking platform: gate both operations on a single NB exclusive acquire.
        try:
            fh = open(lock_path, "a+")                      # creates file if absent
        except OSError:
            return
        try:
            try:
                if _fcntl is not None:
                    _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                else:                                        # _msvcrt is not None
                    fh.seek(0)
                    _msvcrt.locking(fh.fileno(), _msvcrt.LK_NBLCK, 1)
            except (BlockingIOError, OSError):
                return                                       # peer holds lock; skip both
            # Acquire succeeded: no write_pending_review() is in flight, so every
            # *.tmp is genuinely abandoned. Sweep *.tmp BEFORE unlinking lock —
            # reversing this order reopens Risk-1b obligation-drop (a peer could
            # re-rendezvous on the freed path and stage a live temp our sweep
            # would then delete).
            for tmp in sdd_dir.glob("*.tmp"):
                try:
                    tmp.unlink()
                except OSError:
                    pass
            try:
                lock_path.unlink()                          # accepted race window (AD2)
            except OSError:
                pass                                        # Windows: unlink-while-open
            try:
                if _fcntl is not None:
                    _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
                else:
                    fh.seek(0)
                    _msvcrt.locking(fh.fileno(), _msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        finally:
            fh.close()                                      # fd always released
    except Exception:
        pass                                                # best-effort (R4)
