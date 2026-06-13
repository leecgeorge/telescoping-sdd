"""Content-hash + approval grammar — extracted from blueprint_common (audit R3.1).

The versioned content-hash basis (v1 includes `### Trajectory` rows, v2 excludes
them), its computation/verification, the `## Approval` section grammar
(header/checkbox/Content-Hash regexes, `approval_section_bounds`, the hash-basis
line read/upsert), and the small change-detection predicates
(`changed_since_stamp`, `is_basis_migration_only`, `read_stored_hash`).

A layer OVER trajectory.py (content_for_hashing strips Trajectory rows from the
hash) and UNDER blueprint_common (which keeps `check_approval` — it builds a
ValidationResult — and re-exports everything here). Layering:
trajectory <- content_hash <- blueprint_common <- pending_review. No
ValidationResult dependency lives here, so there is no cycle.
"""
from __future__ import annotations

import hashlib
import re
import sys
from typing import Optional

from trajectory import _strip_trajectory_rows, trim_trajectory_table


HASH_BASIS_CURRENT = "v2"

# Width (in lowercase hex chars) of the content hash — the SHA-256 prefix kept by
# compute_content_hash(). SINGLE SOURCE: the two producers below slice to this
# width, and CONTENT_HASH_HEX builds the matching consumer regex fragment so a
# downstream matcher (e.g. the Business Brief `**Content Hash:**` strip, I3.5)
# can never hardcode a width that drifts from what is actually emitted.
CONTENT_HASH_WIDTH = 16
# Regex fragment matching exactly one emitted content hash (lowercase hex, since
# hexdigest() emits lowercase). Use inside a larger pattern, e.g.
# rf"`{CONTENT_HASH_HEX}`". NOT anchored — callers add their own context.
CONTENT_HASH_HEX = r"[0-9a-f]{%d}" % CONTENT_HASH_WIDTH

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
APPROVAL_HASH_LINE = re.compile(
    r"^\s*(?:-\s*)?\*\*Content Hash:\*\*\s*`([^`]*)`", re.MULTILINE
)


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
    ).hexdigest()[:CONTENT_HASH_WIDTH]


def compute_content_hash(content: str) -> str:
    """SHA-256 (16-hex-char prefix) of content_for_hashing(content)."""
    body = content_for_hashing(content)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:CONTENT_HASH_WIDTH]


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
    """Return True if the content has a `## Approval` section with a checked box.

    The checkbox is read ONLY inside the `## Approval` section (audit 3.5c) — the
    write path was already scoped (R8), so a body-prose `- [x] Approved` example
    before the real section must not be read as approval state.
    """
    bounds = approval_section_bounds(content)
    if bounds is None:
        return False
    body = content[bounds[0]:bounds[1]]
    return bool(_APPROVAL_CHECKBOX.search(body))


def approval_hash(content: str) -> Optional[str]:
    """Return the stamped `**Content Hash:**` value, or None if absent or 'pending'.

    Read ONLY inside the `## Approval` section (audit 3.5c).
    """
    bounds = approval_section_bounds(content)
    if bounds is None:
        return None
    m = APPROVAL_HASH_LINE_STRICT.search(content[bounds[0]:bounds[1]])
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


def read_stored_hash(content: str) -> str:
    """Value in the `## Approval` section's `**Content Hash:**` line, or 'pending'. [T1]

    Captures the backtick content broadly so a present-but-malformed value is
    returned VERBATIM (not collapsed to 'pending') — that lets
    changed_since_stamp fail closed on corruption. Returns 'pending' when the
    `## Approval` section or the line is absent, or the line literally holds
    'pending'. Read is scoped to the Approval section (audit 3.5c) so a body-prose
    Content-Hash example is never read as the stored hash.
    """
    bounds = approval_section_bounds(content)
    if bounds is None:
        return "pending"
    m = APPROVAL_HASH_LINE.search(content[bounds[0]:bounds[1]])
    if not m:
        return "pending"
    return m.group(1).strip()


def _is_valid_16_hex(value: str) -> bool:
    return len(value) == 16 and all(c in "0123456789abcdef" for c in value.lower())


def _approval_checkbox_checked(content: str) -> bool:
    # Scoped to the ## Approval section (audit 3.5c) — a body-prose checkbox
    # example must not register as approval state.
    bounds = approval_section_bounds(content)
    if bounds is None:
        return False
    body = content[bounds[0]:bounds[1]]
    return bool(re.search(r"-\s*\[[xX]\]\s*Approved to proceed", body))


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
