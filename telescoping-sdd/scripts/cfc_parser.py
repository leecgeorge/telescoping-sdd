"""Shared CFC (Cross-Feature Contracts) parser.

Imported by both `validate_blueprint.py` (producer) and `validate_spec.py`
(consumer). Owns:
  * The CFC section header / entry / field regexes.
  * The four-field `CFCEntry` parsed representation.
  * `extract_cfc_section`, `parse_cfc_entries`, `detect_near_miss_cfc_header`.
  * Whole-number `[CFC-N]` tag regex and a `extract_cfc_tags` helper.
  * Word-boundary `\\bF\\d+\\b` feature-ID matcher.
  * Normalization primitive used by structured content hashing.

Per CFC.md `## Deferred to v2`, the *cascade machinery* (`cfc_consistency.py`)
is intentionally deferred. The *parser layer* is shared here to prevent
producer/consumer drift on the file format itself.

The module is dependency-free (stdlib only) so both validators can import
it without sys.path acrobatics beyond the existing
telescoping-sdd/scripts/ path-append they already do for `blueprint_common`.

See `documentation/CFC.md` (the spec) and CFC.md decision C from the
post-implementation review for context.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional


# ---------------------------------------------------------------------------
# CFC section + entry parsing
# ---------------------------------------------------------------------------

# Strict header regex — case-sensitive, no trailing colon, no extra spaces.
CFC_HEADER_PATTERN = re.compile(r"^##\s+Cross-Feature Contracts\s*$", re.MULTILINE)

# `### CFC-N: <title>` entry header. The number must be a non-zero, no-
# leading-zero decimal integer — `CFC-007` and `CFC-7` would int() to the
# same number and silently collide with each other in the uniqueness check
# (per P3-12 from the post-implementation review).
CFC_ENTRY_PATTERN = re.compile(r"^###\s+CFC-(\d+):\s*(.+?)\s*$", re.MULTILINE)
CFC_ENTRY_NUMBER_FORMAT = re.compile(r"^(0|[1-9]\d*)$")

# Field-detection patterns. Each accepts an optional markdown bullet prefix
# (`- ` or `* `) so the plan-template's bulleted form works. The post-marker
# whitespace uses `[ \t]*` (horizontal whitespace only) rather than `\s*`
# (which would match newlines via backtracking on empty values and slurp the
# next line into the captured group — see decision P1-9 from the post-
# implementation code review for the bug this guards against).
_FIELD_PREFIX = r"^[ \t]*(?:[-*][ \t]+)?"
CFC_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "Participating features": re.compile(
        _FIELD_PREFIX + r"\*\*Participating features:\*\*[ \t]*(.+)$", re.MULTILINE
    ),
    "Contract": re.compile(
        _FIELD_PREFIX + r"\*\*Contract:\*\*[ \t]*(.+)$", re.MULTILINE
    ),
    "Per-feature AC": re.compile(
        _FIELD_PREFIX + r"\*\*Per-feature AC:\*\*[ \t]*(.+)$", re.MULTILINE
    ),
    "Enforcement": re.compile(
        _FIELD_PREFIX + r"\*\*Enforcement:\*\*[ \t]*(.+)$", re.MULTILINE
    ),
}
CFC_FIELD_ORDER: tuple[str, ...] = (
    "Participating features",
    "Contract",
    "Per-feature AC",
    "Enforcement",
)

# Strict value regex for the Participating features field: F<n>, F<n>, ... only.
CFC_PARTICIPATING_VALUE_PATTERN = re.compile(r"^F\d+(?:,\s*F\d+)*$")

# Word-boundary feature-ID matcher for free-prose detection (per CFC.md M2).
FEATURE_ID_WORD_PATTERN = re.compile(r"\bF(\d+)\b")

# Whole-number CFC tag matcher (per CFC.md M2 — `[CFC-1]` must not match
# inside `[CFC-10]`). Code paths that ask "does this artifact contain
# `[CFC-<M>]`" must parse the captured integer and compare to <M>.
CFC_TAG_PATTERN = re.compile(r"\[CFC-(\d+)\]")


class CFCEntry:
    """Parsed representation of one ### CFC-N entry.

    Construction parses the four required fields out of the entry body via
    CFC_FIELD_PATTERNS. Producer-side adds extension behaviour
    (`structured_content_hash`) by mixing in or subclassing this type; the
    consumer side uses the parsed fields directly via the `fields` dict.
    """

    def __init__(
        self,
        number: int,
        title: str,
        body: str,
    ):
        self.number = number
        self.title = title
        self.body = body
        self.fields: dict[str, Optional[str]] = {
            name: None for name in CFC_FIELD_ORDER
        }
        self.field_order_observed: list[str] = []
        self.field_duplicates: dict[str, int] = {}
        self._parse_fields()

    def _parse_fields(self) -> None:
        observed: list[tuple[int, str, str]] = []
        for name, pattern in CFC_FIELD_PATTERNS.items():
            for m in pattern.finditer(self.body):
                observed.append((m.start(), name, m.group(1).strip()))
        observed.sort(key=lambda t: t[0])
        seen: dict[str, int] = {}
        for _pos, name, value in observed:
            seen[name] = seen.get(name, 0) + 1
            if self.fields[name] is None:
                self.fields[name] = value
                self.field_order_observed.append(name)
        self.field_duplicates = {
            name: count for name, count in seen.items() if count > 1
        }

    def participating_features(self) -> list[int]:
        """Return the integer F<n> identifiers from Participating features, or [] if unparseable.

        Duplicates are preserved in the return order (matches the source) so
        a duplicate-detection check elsewhere can flag them. The
        `structured_content_hash` consumer sorts AND dedupes — a benign
        cosmetic-fix-causes-orphan WARN is prevented by deduping before
        hashing (per P2-9 from the post-implementation review).
        """
        value = self.fields.get("Participating features")
        if value is None:
            return []
        if not CFC_PARTICIPATING_VALUE_PATTERN.match(value):
            return []
        return [int(m.group(1)) for m in FEATURE_ID_WORD_PATTERN.finditer(value)]

    def enforcement_owners(self) -> list[int]:
        """Return F<n> identifiers named in the Enforcement field (word-boundary), or [] if absent."""
        value = self.fields.get("Enforcement")
        if value is None:
            return []
        return [int(m.group(1)) for m in FEATURE_ID_WORD_PATTERN.finditer(value)]


def extract_cfc_section(content: str) -> Optional[tuple[int, int, str]]:
    """Locate the `## Cross-Feature Contracts` section.

    Returns `(start_offset, end_offset, body_text)` where start/end bound
    the section body (not including the header line itself), or None if
    the section is absent.

    The header must match `^## Cross-Feature Contracts\\s*$` exactly. Near-miss
    variants (lowercase 'f', trailing colon, extra whitespace) are rejected;
    use `detect_near_miss_cfc_header` to surface them.
    """
    m = CFC_HEADER_PATTERN.search(content)
    if m is None:
        return None
    body_start = m.end()
    next_h2 = re.search(r"^## ", content[body_start:], re.MULTILINE)
    body_end = body_start + next_h2.start() if next_h2 else len(content)
    return (body_start, body_end, content[body_start:body_end])


def parse_cfc_entries(section_body: str) -> list[CFCEntry]:
    """Parse all `### CFC-N` entries from a section body.

    Returns a list in document order. Each entry has its fields populated.
    Leading-zero or zero CFC numbers (`CFC-0`, `CFC-007`) are silently
    dropped — they collide with their canonical forms (`CFC-7`) under
    `int()` parsing and the soft-validation layer above flags the malformed
    heading. Use `parse_cfc_entries_with_malformed` if you need to surface
    the malformed entries for diagnostics.
    """
    entries, _malformed = parse_cfc_entries_with_malformed(section_body)
    return entries


def parse_cfc_entries_with_malformed(
    section_body: str,
) -> tuple[list[CFCEntry], list[str]]:
    """Same as `parse_cfc_entries` but also returns malformed heading strings.

    Headings whose number portion is not in the canonical decimal form
    (`^(0|[1-9]\\d*)$`) — e.g. `CFC-007` or `CFC-0` — are dropped from the
    returned `entries` list and surfaced in `malformed` so the validator
    can emit a clear "leading-zero / zero number rejected" diagnostic
    instead of silently accepting and colliding (per P3-12).
    """
    entries: list[CFCEntry] = []
    malformed: list[str] = []
    matches = list(CFC_ENTRY_PATTERN.finditer(section_body))
    if not matches:
        return entries, malformed
    for i, m in enumerate(matches):
        raw_number = m.group(1)
        title = m.group(2).strip()
        if not CFC_ENTRY_NUMBER_FORMAT.match(raw_number) or raw_number == "0":
            malformed.append(f"CFC-{raw_number}: {title}")
            continue
        number = int(raw_number)
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(section_body)
        entries.append(
            CFCEntry(
                number=number,
                title=title,
                body=section_body[body_start:body_end],
            )
        )
    return entries, malformed


def detect_near_miss_cfc_header(content: str) -> Optional[str]:
    """Return the offending line if a near-miss CFC header is present.

    Catches case-drift, trailing punctuation, indentation, and stray
    whitespace that would cause silent extractor failure. Returns None if
    no near-miss is found (which includes the canonical-header case — that
    is handled by `extract_cfc_section` directly).

    Per P3-6 from the post-implementation review: indented headers
    (`   ## Cross-Feature Contracts`) are also detected — Markdown renderers
    sometimes treat indented `##` as a heading, but `CFC_HEADER_PATTERN`
    requires column-zero. The indented form is rejected with the same
    near-miss diagnostic so the user notices.
    """
    if CFC_HEADER_PATTERN.search(content):
        return None
    near_miss = re.compile(
        r"^[ \t]*##\s*[Cc]ross[-\s][Ff]eature\s+[Cc]ontracts?[\s:]*$",
        re.MULTILINE,
    )
    m = near_miss.search(content)
    if m:
        return m.group(0).rstrip()
    return None


# ---------------------------------------------------------------------------
# CFC tag extraction
# ---------------------------------------------------------------------------

# Fenced code-block matcher (triple-backtick or triple-tilde). Used to strip
# code examples before scanning for THEN lines / tag matches, so an
# illustrative AC inside a code example doesn't count as a real binding.
_FENCED_CODE_BLOCK = re.compile(
    r"(?ms)^([ \t]*)(?P<fence>`{3,}|~{3,})[^\n]*\n.*?\n[ \t]*(?P=fence)[ \t]*$"
)


def _strip_fenced_code_blocks(text: str) -> str:
    """Return `text` with fenced code blocks replaced by blank lines (preserves line numbers)."""
    def _blank_replacement(m: re.Match[str]) -> str:
        return "\n" * m.group(0).count("\n")
    return _FENCED_CODE_BLOCK.sub(_blank_replacement, text)


# THEN-line matcher: accepts optional leading whitespace and an optional
# markdown bullet prefix (`- ` or `* `) so list-style ACs are detected
# alongside narrative-style ones. Per P2-5 from the post-implementation
# code review.
_THEN_LINE = re.compile(r"^[ \t]*(?:[-*][ \t]+)?THEN\b[^\n]*$", re.MULTILINE)


def extract_cfc_tags(text: str) -> list[int]:
    """Return CFC numbers from `[CFC-N]` tags on THEN-prefixed lines (whole-number, per M2).

    Fenced code blocks are stripped before the scan — an illustrative `THEN ...
    [CFC-1]` line inside a triple-backtick code example does not count as a
    real binding (per P2-4 from the post-implementation code review).

    The THEN-line matcher accepts optional bullet prefixes (`- THEN`, `* THEN`)
    per P2-5. Tags anywhere else in the text are ignored here — use
    `find_misplaced_cfc_tags` to surface tags outside THEN-binding contexts.
    """
    text = _strip_fenced_code_blocks(text)
    numbers: list[int] = []
    for m in _THEN_LINE.finditer(text):
        line = m.group(0)
        numbers.extend(int(g) for g in CFC_TAG_PATTERN.findall(line))
    return numbers


def find_misplaced_cfc_tags(text: str) -> list[tuple[int, str]]:
    """Return `[CFC-N]` tags that appear outside an acceptable location.

    Acceptable locations per the spec: a THEN line inside an
    `**Acceptance Criteria:**` block (spec.md) or a checkbox line (tasks.md
    — checked by the caller, not here). Fenced code blocks are excluded
    entirely. This helper exists so consumer-side validation can emit
    "tag in wrong location" rather than the misleading "missing tag"
    when an author put `[CFC-N]` on a GIVEN/WHEN line, in a requirement
    header, in body prose, or in a single-line GIVEN/WHEN/THEN compression.

    Returns a list of `(cfc_number, offending_line)` tuples. Per P2-3.
    """
    stripped = _strip_fenced_code_blocks(text)
    misplaced: list[tuple[int, str]] = []
    for m in CFC_TAG_PATTERN.finditer(stripped):
        # Find the full line containing this match.
        line_start = stripped.rfind("\n", 0, m.start()) + 1
        line_end = stripped.find("\n", m.end())
        if line_end == -1:
            line_end = len(stripped)
        line = stripped[line_start:line_end]
        # Acceptable on a THEN line (multi-line GIVEN/WHEN/THEN form).
        if _THEN_LINE.match(line):
            continue
        misplaced.append((int(m.group(1)), line.strip()))
    return misplaced


# ---------------------------------------------------------------------------
# Hashing normalization primitive
# ---------------------------------------------------------------------------

def normalize_for_hash(text: str) -> str:
    """Apply the CFC.md normalization rules: NFC + whitespace collapse + line trim + blank-line collapse.

    Used by per-CFC structured content hashing (producer side). The four
    steps run in order:

      1. Unicode NFC normalization (visually-identical strings with different
         code-point sequences hash identically).
      2. Whitespace collapse: every run of `[ \\t]+` collapses to a single
         space. NBSP (U+00A0) is intentionally NOT included — it must
         survive as a distinct character to defeat whitespace-trick edits.
      3. Line trim: leading and trailing whitespace per line is stripped.
      4. Blank-line collapse: runs of consecutive blank lines reduce to one.
    """
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
