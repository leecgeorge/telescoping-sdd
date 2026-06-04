"""Shared master-feature contract extractor and hasher (CPD AD7 / DM6 / I9).

Owned by this module; imported by `validate_blueprint.py` (on demand, for the
reconcile path) and `reconcile.py` via the existing
`sys.path.append(_SHARED_SCRIPTS)` pattern they already use for `cfc_parser`,
`spec_dirname`, `project_link`, and `arch_config`. Stdlib-only apart from the
`normalize_for_hash` import from the sibling `cfc_parser` module — no
third-party dependencies.

This module is the SINGLE PLACE a master-feature contract hash is computed
(the I9 single-producer invariant). Every caller that needs the hash of a
master feature's Description + Acceptance Criteria calls
`compute_master_contract_hash`; none re-derives the serialization by another
path. Reusing `cfc_parser.normalize_for_hash` keeps CFC content hashes and
master-feature contract hashes behaving identically (NFC + whitespace collapse
+ line trim + blank-line collapse).

What is extracted for a master feature `### F<n>` (DM6):

  * **Block boundary** — from the `### F<n>:` heading to the FIRST of
    {next `### F<m>` heading, next `## ` section heading, EOF}.
  * **Excluded lines** — the `### F<n>:` title line itself, the
    `**Implemented by:**` field, and the `**Component:**` field. So adding or
    removing an `**Implemented by:**` value never changes the hash.
  * **Description** — the value of the `**Description:**` field (the rest of
    the block's prose under that field is collected too if it wraps).
  * **Acceptance Criteria elements** — ONE element per TOP-LEVEL bullet under
    `**Acceptance Criteria:**`. A nested sub-bullet (a deeper-indented bullet
    line) is FOLDED into its parent element's text with a SINGLE SPACE — a
    deterministic separator, so the frozen-digest oracle is reproducible from
    the design rather than depending on a `\n`-vs-space choice. A WRAPPED
    top-level continuation line (a deeper-indented line that is NOT a bullet)
    is NOT folded: it is kept on its own line and passed to
    `normalize_for_hash` as-is, which preserves the inter-line `\n`.

The normalized element list is SORTED before serialization (DM6), so
reordering criteria does not produce false drift. Serialization is
`json.dumps({"feature": n, "description": <norm>, "acceptance_criteria":
sorted([<norm>, ...])}, sort_keys=True)`, then SHA-256 → 64 lowercase hex.

Every function is total: a feature block that cannot be located returns
`None` rather than raising.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import re
from typing import Optional

from cfc_parser import normalize_for_hash

# ---------------------------------------------------------------------------
# Compiled patterns (module-level, compiled once; no raw strings at call sites)
# ---------------------------------------------------------------------------

# A `### F<n>` feature heading. The number is captured so the boundary finder
# can both locate the target feature and detect the NEXT feature heading. We
# accept the canonical `### F<n>:` title form and also a bare `### F<n>`.
_FEATURE_HEADING = re.compile(r"^###[ \t]+F(\d+)\b.*$", re.MULTILINE)

# A `## ` section heading (any H2 that is not a deeper `###`). Used as a block
# boundary so the feature block never bleeds into the next document section.
_SECTION_HEADING = re.compile(r"^##[ \t]+\S.*$", re.MULTILINE)

# Field lines that are EXCLUDED from the contract entirely. Bullet prefix is
# optional, mirroring the `cfc_parser` `_FIELD_PREFIX` discipline.
_FIELD_PREFIX = r"^[ \t]*(?:[-*][ \t]+)?"
_IMPLEMENTED_BY_LINE = re.compile(_FIELD_PREFIX + r"\*\*Implemented by:\*\*", re.IGNORECASE)
_COMPONENT_LINE = re.compile(_FIELD_PREFIX + r"\*\*Component:\*\*", re.IGNORECASE)

# The `**Description:**` field — captures the inline value after the marker.
_DESCRIPTION_LINE = re.compile(_FIELD_PREFIX + r"\*\*Description:\*\*[ \t]*(.*)$")

# The `**Acceptance Criteria:**` field header (its bullets live on the
# following indented lines).
_ACCEPTANCE_HEADER = re.compile(_FIELD_PREFIX + r"\*\*Acceptance Criteria:\*\*[ \t]*$")

# Any top-level field line within a feature block (a `- **Field:**` line at the
# block's base indentation). Used to terminate the AC bullet collection: the AC
# block runs until the next such field or the end of the feature block.
_TOP_LEVEL_FIELD = re.compile(_FIELD_PREFIX + r"\*\*[^*]+:\*\*")

# A bullet line: optional indent, then a `-` or `*` marker, then text. The
# indent width and the body are captured so nested vs. top-level bullets can be
# distinguished and the marker stripped for folding.
_BULLET_LINE = re.compile(r"^([ \t]*)[-*][ \t]+(.*)$")


def _find_feature_block(plan_content: str, feature_number: int) -> Optional[str]:
    """Return the raw text of the `### F<n>` block, or None if not found.

    The block starts at the matching `### F<feature_number>` heading and ends
    at the FIRST of {next `### F<m>` heading, next `## ` section heading, EOF}.
    The heading line itself is INCLUDED in the returned slice (callers strip
    the title line when collecting content).
    """
    start = None
    for m in _FEATURE_HEADING.finditer(plan_content):
        if int(m.group(1)) == feature_number:
            start = m.start()
            heading_end = m.end()
            break
    if start is None:
        return None

    # Candidate boundary 1: the next feature heading after this one.
    end = len(plan_content)
    next_feature = _FEATURE_HEADING.search(plan_content, heading_end)
    if next_feature is not None:
        end = min(end, next_feature.start())
    # Candidate boundary 2: the next `## ` section heading after this one.
    next_section = _SECTION_HEADING.search(plan_content, heading_end)
    if next_section is not None:
        end = min(end, next_section.start())
    return plan_content[start:end]


def iter_feature_blocks(plan_content: str) -> "list[tuple[int, str]]":
    """Return ``[(feature_number, block_text), ...]`` for every ``### F<n>`` block.

    The same boundary rule as ``_find_feature_block`` (each block runs to the
    FIRST of {next ``### F<m>`` heading, next ``## `` section heading, EOF} and
    INCLUDES its own title line), but the feature- and section-heading scans run
    ONCE for the whole document instead of once per feature. Calling
    ``_find_feature_block`` in a loop is O(M·len(PLAN)) — M full-document regex
    scans for M features; this is O(len(PLAN)) (two finditer passes plus an
    O(log S) bisect per feature). Each returned ``block_text`` is byte-identical
    to ``_find_feature_block(plan_content, number)`` for that feature. Never
    raises; returns ``[]`` when there are no feature headings.
    """
    headings = list(_FEATURE_HEADING.finditer(plan_content))
    if not headings:
        return []
    section_starts = [m.start() for m in _SECTION_HEADING.finditer(plan_content)]
    n = len(plan_content)

    blocks: list[tuple[int, str]] = []
    for i, m in enumerate(headings):
        number = int(m.group(1))
        end = n
        if i + 1 < len(headings):
            end = min(end, headings[i + 1].start())
        # First `## ` section starting at/after the end of this heading line
        # (mirrors `_SECTION_HEADING.search(plan_content, heading_end)`).
        idx = bisect.bisect_left(section_starts, m.end())
        if idx < len(section_starts):
            end = min(end, section_starts[idx])
        blocks.append((number, plan_content[m.start():end]))
    return blocks


def extract_master_feature_contract(
    plan_content: str, feature_number: int
) -> Optional[dict]:
    """Extract one feature's Description and Acceptance Criteria from PLAN.md.

    Returns ``{"description": str, "acceptance_criteria": list[str]}`` on
    success, or ``None`` if the feature block is not found.

    Block boundary: the first of {next `### F<m>` heading, next `## ` section
    heading, EOF}. Excluded: the feature title line, `**Implemented by:**`,
    `**Component:**`. AC extraction: one element per TOP-LEVEL bullet; a nested
    sub-bullet is folded into its parent element's text with a single-space
    join; a WRAPPED top-level continuation line is NOT folded (kept with its
    `\\n`, passed to `normalize_for_hash` as-is). The element list is NOT
    sorted here — the sort happens in `compute_master_contract_hash` per DM6,
    so callers that want document order keep it.
    """
    block = _find_feature_block(plan_content, feature_number)
    if block is None:
        return None

    lines = block.split("\n")

    description = ""
    criteria: list[str] = []

    i = 0
    # Skip the title line (the `### F<n>` heading) — line 0 of the block.
    if lines and _FEATURE_HEADING.match(lines[0]):
        i = 1

    while i < len(lines):
        line = lines[i]

        # Excluded fields — skip outright.
        if _IMPLEMENTED_BY_LINE.match(line) or _COMPONENT_LINE.match(line):
            i += 1
            continue

        desc_m = _DESCRIPTION_LINE.match(line)
        if desc_m is not None:
            description = desc_m.group(1).strip()
            i += 1
            continue

        if _ACCEPTANCE_HEADER.match(line):
            i += 1
            criteria, i = _collect_acceptance_criteria(lines, i)
            continue

        i += 1

    return {"description": description, "acceptance_criteria": criteria}


def _bullet_indent(line: str) -> Optional[int]:
    """Return the indent width of a bullet line, or None if it is not a bullet."""
    m = _BULLET_LINE.match(line)
    if m is None:
        return None
    return len(m.group(1))


def _collect_acceptance_criteria(
    lines: list[str], start: int
) -> tuple[list[str], int]:
    """Collect AC elements starting at `lines[start]`; return (elements, next_index).

    One element per TOP-LEVEL bullet (the shallowest bullet indent seen in the
    block). A deeper-indented BULLET line is a nested sub-bullet → folded into
    the current element with a single space. A deeper-indented NON-bullet line
    is a WRAPPED continuation → appended on its own line (preserving `\\n`, not
    folded). Collection stops at: an excluded master-feature field line
    (`**Implemented by:**` / `**Component:**`, whether or not it is bulleted —
    these may follow the AC list in the canonical layout); any other NON-bullet
    `**Field:**` line; a non-bullet line at or below the top-level indent; or
    the end of the block.
    """
    elements: list[str] = []
    current: Optional[str] = None
    top_indent: Optional[int] = None

    i = start
    while i < len(lines):
        line = lines[i]

        # A blank line inside the AC block does not terminate it (a wrapped
        # continuation or a follow-on bullet may come after); but a blank line
        # is preserved as-is on a current wrapped element so normalize collapses
        # it deterministically. We simply skip pure-blank lines for structure.
        if line.strip() == "":
            i += 1
            continue

        # The excluded master-feature fields (`**Implemented by:**`,
        # `**Component:**`) may follow the AC block as BULLETS in the canonical
        # layout (design "Master side" data model: the `- **Implemented by:**`
        # line sits below the `- **Acceptance Criteria:**` list). Terminate the
        # AC block on them whether or not they are bulleted, so an alias /
        # component rename never folds into an AC element and shifts the
        # contract hash (CPD-D4 / DM6 hash-neutrality). The generic
        # `**Field:**` terminator below only fires for a NON-bullet field line,
        # so a bolded sub-bullet inside an AC element is still not mistaken for
        # a field.
        field_m = _TOP_LEVEL_FIELD.match(line)
        bullet_indent = _bullet_indent(line)
        if _IMPLEMENTED_BY_LINE.match(line) or _COMPONENT_LINE.match(line):
            break
        if field_m is not None and bullet_indent is None:
            break

        if bullet_indent is not None:
            if top_indent is None:
                top_indent = bullet_indent
            if bullet_indent <= top_indent:
                # New top-level bullet — start a fresh element.
                if current is not None:
                    elements.append(current)
                body = _BULLET_LINE.match(line).group(2).rstrip()
                current = body
            else:
                # Nested sub-bullet — fold into the current element with a
                # single space (deterministic separator per DM6). Drop the
                # marker; keep the body.
                body = _BULLET_LINE.match(line).group(2).strip()
                if current is None:
                    current = body
                else:
                    current = current + " " + body
            i += 1
            continue

        # Non-bullet, non-blank line.
        if current is None:
            # No bullet has started yet — not part of any element; stop. This
            # guards against trailing prose after the AC header with no bullets.
            break
        # If it is indented deeper than the top-level bullet, it is a WRAPPED
        # continuation of the current top-level bullet → keep on its own line
        # (NOT folded), preserving the inter-line `\n` for normalize_for_hash.
        leading = len(line) - len(line.lstrip())
        if top_indent is not None and leading > top_indent:
            current = current + "\n" + line.strip()
            i += 1
            continue
        # A non-bullet line at or below the top-level indent terminates the AC
        # block (it belongs to the surrounding feature body, not the AC list).
        break

    if current is not None:
        elements.append(current)
    return elements, i


def compute_master_contract_hash(
    plan_content: str, feature_number: int
) -> Optional[str]:
    """Compute the SHA-256 contract hash for a master feature (DM6 / AD7).

    Returns the 64-char lowercase hex hash, or ``None`` if the feature block is
    not found. Uses `extract_master_feature_contract` + `normalize_for_hash`
    and serializes via ``json.dumps(..., sort_keys=True)`` with the
    acceptance-criteria element list SORTED, so reordering criteria does not
    change the hash.
    """
    contract = extract_master_feature_contract(plan_content, feature_number)
    if contract is None:
        return None

    canonical = json.dumps(
        {
            "feature": feature_number,
            "description": normalize_for_hash(contract["description"]),
            "acceptance_criteria": sorted(
                normalize_for_hash(criterion)
                for criterion in contract["acceptance_criteria"]
            ),
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
