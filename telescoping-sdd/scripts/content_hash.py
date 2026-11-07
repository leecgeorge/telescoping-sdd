"""Content-hash + approval grammar — extracted from blueprint_common (audit R3.1).

The versioned content-hash bases — v1 (frozen: includes `### Trajectory` rows),
v2 (frozen: excludes the data rows, hashes the header and separator rows
verbatim) and the current v3 (also canonicalises the header and separator rows,
so archive re-padding is hash-neutral) — their computation/verification, the
`## Approval` section grammar
(header/checkbox/Content-Hash regexes, `approval_section_bounds`, the hash-basis
line read/upsert), and the small change-detection predicates
(`changed_since_stamp`, `is_basis_migration_only`, `is_pure_basis_migration`,
`read_stored_hash`).

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
from trajectory import canonicalize_trajectory_header_rows


HASH_BASIS_CURRENT = "v3"

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
# current basis line is stamped). Shares the same line core as HASH_BASIS_LINE.
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

# Canonical milestone-feature row matcher (any checkbox state). CHARACTER-IDENTICAL
# to test_hash_and_cascade_parity.py's C4_REGEX_PATTERN; test (g) pins the parity so
# the production constant and the doctrine-check literal cannot drift.
MILESTONE_FEATURE_ROW = r"^- \[[ xX]\] F\d+\b"
# State-neutralizing sub pattern DERIVED from MILESTONE_FEATURE_ROW via string
# interpolation (so the pinned constant and the pattern actually applied cannot
# diverge): replacing `\[[ xX]\]` with `\[)[ xX](\]` and wrapping yields
# `(^- \[)[ xX](\] F\d+\b)` — group 1 = `- [`, the state char is matched-not-
# captured, group 2 = `] F<n>...`; the sub `\1 \2` normalizes ANY state to `[ ]`
# while preserving the `F<n>` suffix. A derivation-guard test (test (j)) pins
# `.groups == 2` + the sub output so a silent `.replace()` no-op fails loud here
# rather than as a generic re.error deep in compute_content_hash.
_MILESTONE_NEUTRALIZE_RE = re.compile(
    "(" + MILESTONE_FEATURE_ROW.replace(r"\[[ xX]\]", r"\[)[ xX](\]") + ")",
    re.MULTILINE,
)
# Line-anchored `## Milestones` header (EXACT — a decorated `## Milestones (Q3)`
# is intentionally skipped, mirroring _APPROVAL_HEADER's strictness).
_MILESTONES_HEADER = re.compile(r"^##\s+Milestones\s*$", re.MULTILINE)


def _neutralize_milestone_state(content: str) -> str:
    """Normalize milestone-feature checkbox STATE to `[ ]`, scoped to the first
    `## Milestones` section only — step 5 of content_for_hashing (since the v2
    basis; unchanged in v3).

    Marking a feature Done (`- [ ] F<n>` <-> `- [x] F<n>`) in `## Milestones` is a
    progress marker, not contract content, so it must not move the PLAN hash. The
    neutralization is SECTION-SCOPED (header line -> next `## ` heading or EOF,
    mirroring approval_section_bounds) so a `- [x] F<n>`-shaped line OUTSIDE
    `## Milestones` still moves the hash (R2.AC4). Touches only the checkbox state
    char, never the `F<n>` suffix, so a feature rename still moves the hash
    (R2.AC5). No-op when no `## Milestones` section exists (every non-PLAN artifact
    today) or when its heading is decorated.
    """
    m = _MILESTONES_HEADER.search(content)
    if not m:
        return content
    body_start = m.end()
    next_h2 = re.search(r"^## ", content[body_start:], re.MULTILINE)
    body_end = body_start + next_h2.start() if next_h2 else len(content)
    section = content[body_start:body_end]
    neutralized = _MILESTONE_NEUTRALIZE_RE.sub(r"\1 \2", section)
    return content[:body_start] + neutralized + content[body_end:]


def content_for_hashing(content: str) -> str:
    """Document content with dynamic approval values + Trajectory bookkeeping neutralised.

    Applies, in order (v3 basis):
      1. Substitute the Approved checkbox state with a fixed placeholder.
      2. Substitute the Content Hash value with 'pending'.
      3. Remove any `- **Hash basis:** vN` line (bullet-tolerant, document-wide,
         including its trailing newline) so the basis annotation's PRESENCE and
         value never affect the hash — an artifact with the line hashes
         identically to one without (post-migration coherence: the migration hash
         is computed before the basis line is stamped).
      4. Strip ### Trajectory data rows (panel bookkeeping is not contract
         content) so recording a panel pass does not move the hash.
      4b. Render the canonical ### Trajectory table's column-header and separator
         rows in R1's canonical form (`canonicalize_trajectory_header_rows`), so
         archive_pass.py re-padding them for a wider Notes cell does not move the
         hash either. Runs AFTER step 4 (AD10): both steps recognise the
         separator on the RAW line, so the strip stays byte-identical to v2.
      5. Normalize milestone-feature checkbox STATE to `[ ]`, scoped to the
         `## Milestones` section, so marking a feature Done (`- [ ] F<n>` <->
         `- [x] F<n>`) is hash-neutral in both directions (a progress marker, not
         contract content). Section-scoped, so a `- [x] F<n>` line elsewhere still
         moves the hash; touches only the state char, so a rename still does.

    So approving a document, recording a panel pass (however wide its Notes),
    stamping the basis line, or marking a milestone Done doesn't change its hash,
    but any substantive edit does. Idempotent: applying twice yields the same
    result. A document with no canonical Trajectory table hashes exactly as under
    the frozen v2 basis (`_content_for_hashing_v2_frozen`).
    """
    result = re.sub(
        r"- \[[ xX]\] Approved to proceed", "- [ ] Approved to proceed", content
    )
    result = re.sub(
        r"\*\*Content Hash:\*\*\s*`[^`]*`", "**Content Hash:** `pending`", result
    )
    result = _HASH_BASIS_REMOVAL_RE.sub("", result)
    result = _strip_trajectory_rows(result)
    result = canonicalize_trajectory_header_rows(result)
    result = _neutralize_milestone_state(result)
    return result.rstrip()


def _content_for_hashing_v1_frozen(content: str) -> str:
    """FROZEN copy of v1 normalization: checkbox + Content-Hash substitution only.

    This is the verbatim pre-fix `content_for_hashing` body. It does NOT strip
    ### Trajectory rows and does NOT neutralize the basis line. MUST NOT delegate
    to content_for_hashing() or any current-basis helper — it is isolated so a
    future regex change cannot silently change v1 semantics. Used by
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


# ----- FROZEN v2 basis (Unit F, AD2) -----------------------------------------
# Verbatim copies of the v2.28.0 normalisation and every helper/constant it
# touched, renamed `_v2_*` (functions) / `_V2_*` (constants and regexes). Every
# regex is a LITERAL — nothing is derived from, or imported from, a shared
# constant — so no future edit to the current basis (or to trajectory.py) can
# silently change what a v2 stamp meant. Pinned by the AC-2.1 golden
# (test_content_for_hashing_v2_frozen_golden_string) and by the AD3 closure
# check + monkeypatch sweep (test_hash_basis_v3.py). DO NOT EDIT these bodies.
# The v1 freeze above is the precedent.

_V2_CONTENT_HASH_WIDTH = 16
_V2_TRAJECTORY_HEADER = "### Trajectory"
_V2_TRAJECTORY_SEP_RE = re.compile(r"^\|[\s\-|:]+\|\s*$")
_V2_HASH_BASIS_REMOVAL_RE = re.compile(
    r"^[ \t]*(?:-\s*)?\*\*Hash basis:\*\*[ \t]*v\d+[ \t]*\r?\n?", re.MULTILINE
)
_V2_MILESTONE_NEUTRALIZE_RE = re.compile(r"(^- \[)[ xX](\] F\d+\b)", re.MULTILINE)
_V2_MILESTONES_HEADER = re.compile(r"^##\s+Milestones\s*$", re.MULTILINE)


def _v2_panel_trajectory_header_idx(lines: list) -> "Optional[int]":
    """FROZEN v2 copy of trajectory._panel_trajectory_header_idx."""
    panel_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^##\s+Panel Review\s*$", line):
            panel_idx = i
            break
    if panel_idx is None:
        return None
    panel_end = len(lines)
    for j in range(panel_idx + 1, len(lines)):
        if re.match(r"^##\s+", lines[j]):
            panel_end = j
            break
    in_fence = False
    for j in range(panel_idx + 1, panel_end):
        if lines[j].strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if lines[j].rstrip() == _V2_TRAJECTORY_HEADER:
            return j
    return None


def _v2_strip_trajectory_rows(content: str) -> str:
    """FROZEN v2 copy of trajectory._strip_trajectory_rows (pre-Unit-F body)."""
    lines = content.split("\n")
    traj_idx = _v2_panel_trajectory_header_idx(lines)
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
    if not _V2_TRAJECTORY_SEP_RE.match(lines[table_header_idx + 1]):
        return content
    data_start = table_header_idx + 2
    data_end = data_start
    while data_end < section_end:
        s = lines[data_end].strip()
        if not (s.startswith("|") and s.endswith("|")):
            break
        data_end += 1
    return "\n".join(lines[:data_start] + lines[data_end:])


def _v2_neutralize_milestone_state(content: str) -> str:
    """FROZEN v2 copy of _neutralize_milestone_state."""
    m = _V2_MILESTONES_HEADER.search(content)
    if not m:
        return content
    body_start = m.end()
    next_h2 = re.search(r"^## ", content[body_start:], re.MULTILINE)
    body_end = body_start + next_h2.start() if next_h2 else len(content)
    section = content[body_start:body_end]
    neutralized = _V2_MILESTONE_NEUTRALIZE_RE.sub(r"\1 \2", section)
    return content[:body_start] + neutralized + content[body_end:]


def _content_for_hashing_v2_frozen(content: str) -> str:
    """FROZEN copy of the v2 normalisation (v2.28.0 content_for_hashing, steps 1-5).

    Keeps the `### Trajectory` header and separator rows VERBATIM (padding
    included) — the v2 behaviour basis v3 changes. MUST NOT delegate to
    content_for_hashing() or any current-basis helper.
    """
    result = re.sub(
        r"- \[[ xX]\] Approved to proceed", "- [ ] Approved to proceed", content
    )
    result = re.sub(
        r"\*\*Content Hash:\*\*\s*`[^`]*`", "**Content Hash:** `pending`", result
    )
    result = _V2_HASH_BASIS_REMOVAL_RE.sub("", result)
    result = _v2_strip_trajectory_rows(result)
    result = _v2_neutralize_milestone_state(result)
    return result.rstrip()


def compute_content_hash_v2(content: str) -> str:
    """Compute the content hash using the FROZEN v2 normalisation."""
    return hashlib.sha256(
        _content_for_hashing_v2_frozen(content).encode("utf-8")
    ).hexdigest()[:_V2_CONTENT_HASH_WIDTH]


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

    CURRENT basis only: this returns False for an artifact stamped under an
    older basis (v1 or v2) whose stored hash does not also verify under the
    current one, which is what the validators' `check_approval` wants (it
    surfaces the HASH-BASIS-MIGRATION FAIL to nudge re-approval). Read/classify
    paths that must treat a still-coherent older-basis artifact as approved
    (is_shipped, classify_spec, render_business_brief) use
    `verify_content_hash_any_basis` instead.
    """
    return compute_content_hash(content).lower() == stored_hash.lower()


def verify_content_hash_any_basis(content: str, stored_hash: str) -> bool:
    """True iff stored_hash is coherent under the current (v3) basis, OR under the
    basis its stamp names: frozen v1 or frozen v2 (an un-migrated but
    content-coherent artifact).

    A basis change means an older-basis stamp may no longer match
    `verify_content_hash`. The VALIDATOR deliberately FAILs such an artifact
    (migration nudge), but READ/CLASSIFY paths must not: a feature shipped/
    approved under v1 or v2 is still shipped/approved — the basis change is
    tooling-internal, not a content edit. Those paths route here so an
    older-basis-coherent artifact still reads as approved until the operator
    migrates it:
      - a v1 stamp (no basis line) falls back to the frozen v1 hash computed over
        the post-trim content, exactly as the old code stamped it;
      - a `v2` stamp (Unit F AD6) falls back to `compute_content_hash_v2` over the
        RAW content, exactly as v2.28.0's strict check verified it.
    Any other label gets no fallback. Never raises. One of four basis -> hasher
    dispatch sites (DRK8): also `is_pure_basis_migration`,
    `pending_review._classifier_hasher` and `blueprint_common.check_convergence_gate`;
    each site's policy for v1 and unknown labels legitimately differs.
    """
    if verify_content_hash(content, stored_hash):
        return True
    basis = read_hash_basis(content)
    if basis == "v1":
        return compute_content_hash_v1(trim_trajectory_table(content)).lower() == stored_hash.lower()
    if basis == "v2":
        return compute_content_hash_v2(content).lower() == stored_hash.lower()
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
    """Ensure exactly ONE `- **Hash basis:** <HASH_BASIS_CURRENT>` bullet (today
    `v3`) in a ## Approval body. [AD9]

    Two-branch update-or-insert, idempotent:
      1. If a basis line already matches (HASH_BASIS_LINE), substitute it in place
         (update) — re-approving an artifact that already carries a basis line
         (any label) yields exactly one bullet, no duplication (RISK-8); with two
         or more parseable lines only the first is rewritten.
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
    hash basis changed (v1 and v2 stamps both). The validators' `check_approval`
    keeps the current-basis-only `verify_content_hash` so it still surfaces the
    HASH-BASIS-MIGRATION FAIL.
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
    """True iff a V1 re-stamp is a pure basis migration under the v1 rules (no edit). [R4/AD4]

    The frozen v1 predicate, kept unchanged (existing tests pin it). The general
    predicate every call site uses is `is_pure_basis_migration`, which applies
    these v1 rules to a v1 stamp, the frozen-v2 rule to a v2 stamp, and adds the
    "does not verify under v3" condition.

    Two conditions, both required:
      1. Structural (O(1), trim-safe): read_hash_basis(original_content) == 'v1'
         — the stored stamp predates the v2 basis annotation.
      2. Concurrent-edit (trim-safe): compute_content_hash_v1(content_trimmed)
         == stored_hash — the FROZEN v1 hash of the post-trim content matches the
         stored v1 hash, so the ONLY differences since the v1 approval are
         Trajectory rows (excluded since v2) and the basis annotation. A
         concurrent substantive edit (e.g. a reworded Defense:) OR `### Trajectory`
         growth that was never re-approved makes the v1 hash differ -> returns
         False -> the marker fires (R4.AC5 / grown-Trajectory).

    Fail-closed: returns False on a 'pending' stored_hash, a non-16-hex
    stored_hash, an unchecked approval checkbox, or any basis other than v1. All three str
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


def is_pure_basis_migration(
    *,
    original_content: str,
    stored_hash: str,
    content_trimmed: str,
) -> bool:
    """True iff this re-stamp is a PURE hash-basis migration (R3, Unit F AD4).

    R3's two conditions: the stored hash does NOT verify under the current
    basis (v3), and DOES verify under the basis its stamp names — so the only
    thing between the stamp and now is the basis change. Judged on the
    POST-TRIM content (`content_trimmed`, pre-binding-refresh), because
    `--approve` hashes post-trim content and so a pure migration's stamp was
    made over it.

    Fail-closed False on: a 'pending' stored hash; a non-16-hex stored hash; an
    unchecked approval checkbox; `content_trimmed` verifying under v3 (nothing
    to migrate — AC-3.13); or a label other than v1 / v2 (`v3`, `v4`, `v03`,
    `v10`, ...). Then by the stamp's label: `v1` -> `is_basis_migration_only`
    (the v1 rules, unchanged); `v2` -> `compute_content_hash_v2(content_trimmed)
    == stored_hash`. Case-insensitive. An out-of-grammar label (`vNext`,
    `v2.1`) is unparseable, so `read_hash_basis` reads it as v1 and the v1
    rules judge it. All three parameters are keyword-only (RISK-4). One
    predicate, three call sites (the validator FAIL, the approve-time suppress
    arm and `--run-state`), so they cannot disagree about what is a migration.
    One of four basis -> hasher dispatch sites (DRK8): also
    `verify_content_hash_any_basis`, `pending_review._classifier_hasher` and
    `blueprint_common.check_convergence_gate`.
    """
    if stored_hash == "pending":
        return False
    if not _is_valid_16_hex(stored_hash):
        return False
    if not _approval_checkbox_checked(original_content):
        return False
    if compute_content_hash(content_trimmed).lower() == stored_hash.lower():
        return False
    basis = read_hash_basis(original_content)
    if basis == "v1":
        return is_basis_migration_only(
            original_content=original_content,
            stored_hash=stored_hash,
            content_trimmed=content_trimmed,
        )
    if basis == "v2":
        return compute_content_hash_v2(content_trimmed).lower() == stored_hash.lower()
    return False
