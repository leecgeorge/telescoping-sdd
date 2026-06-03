"""Shared UCR (Upstream Change Request) stanza parser.

Imported by BOTH `validate_spec.py` (the consumer that structurally validates
the stanza, I6) and `reconcile.py` (the shared-script entry point that surfaces
open UCRs, I11). A shared script must NOT import a skill validator, so the
grammar + parser live here in their own stdlib-only module — the same
producer/consumer-can't-drift discipline `cfc_parser.py` applies to the CFC
format (design AD4 / DM4).

On-disk format of one entry inside the `## Upstream Change Requests` section
(design DM4):

    ### UCR-<n>

    - **Target:** `<project>:F<n>`
    - **Status:** open | applied | withdrawn
    - **Proposed change:** <free text, terminated by the next `- **` field,
      the next `### UCR-` heading, the next `## ` section, or EOF>
    - **Rationale:** <free text, same termination rule>

Parser strategy (ReDoS-safe, mirrors `cfc_parser`): field extraction uses
`finditer` over line-anchored `^...$` field patterns, then slices the free-text
bodies by the OFFSETS between matches. There is NO `.*?` look-ahead terminator
(which backtracks catastrophically on a large adversarial `spec.md`); the body
of a field is everything from the end of its own `**Field:**` match up to the
start of the next field match (or the entry boundary). This is the exact
`_FIELD_PREFIX` + offset-slicing discipline `cfc_parser` adopted to avoid the
slurp-next-line bug.

Free-text fields (`Proposed change`, `Rationale`) carry untrusted spec text and
must NEVER be raw-printed to a terminal. They are exposed ONLY through the
`display_safe`-wrapped accessors `UCREntry.safe_proposed_change()` /
`UCREntry.safe_rationale()` (and the generic `UCREntry.safe_field(name)`) so a
consumer cannot reach the raw body to print it. The raw text is still available
on `UCREntry.raw_fields` for structural comparison (e.g. the parser-symmetry
test), but every stdout sink path goes through the `display_safe` wrapper.
"""

from __future__ import annotations

import re
from typing import Optional

import spec_dirname  # display_safe — see module docstring on sys.path setup.


# ---------------------------------------------------------------------------
# Section + entry grammar
# ---------------------------------------------------------------------------

# Strict header for the UCR section. Case-sensitive, no trailing colon.
UCR_HEADER_PATTERN = re.compile(
    r"^##\s+Upstream Change Requests\s*$", re.MULTILINE
)

# `### UCR-<n>` entry header. The number is captured raw; canonical-decimal
# validation (no leading zero, non-zero unless literally `0`) happens against
# UCR_ENTRY_NUMBER_FORMAT below, exactly like `### CFC-N`.
UCR_ENTRY_PATTERN = re.compile(r"^###\s+UCR-(\d+)\s*$", re.MULTILINE)
UCR_ENTRY_NUMBER_FORMAT = re.compile(r"^(0|[1-9]\d*)$")

# Field-detection prefix — identical discipline to cfc_parser._FIELD_PREFIX:
# an optional markdown bullet (`- ` or `* `) before `**Field:**`, with
# horizontal-whitespace-only after the marker so an empty value cannot backtrack
# across a newline and slurp the following line into the captured group.
_FIELD_PREFIX = r"^[ \t]*(?:[-*][ \t]+)?"

UCR_FIELD_NAMES: tuple[str, ...] = (
    "Target",
    "Status",
    "Proposed change",
    "Rationale",
)

# Required fields whose absence is a missing-field signal.
UCR_REQUIRED_FIELDS: tuple[str, ...] = UCR_FIELD_NAMES

# Free-text fields whose body may span multiple lines and must go through the
# display_safe accessor before reaching any stdout sink.
UCR_FREE_TEXT_FIELDS: frozenset[str] = frozenset({"Proposed change", "Rationale"})

# Closed status vocabulary (design DM4).
UCR_STATUS_VOCABULARY: frozenset[str] = frozenset({"open", "applied", "withdrawn"})

# One compiled pattern per field. Each captures the inline remainder of the
# field's own line in group(1); the multi-line body (for free-text fields) is
# reconstructed by offset-slicing, NOT by this regex, so there is no `.*?`.
UCR_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    name: re.compile(
        _FIELD_PREFIX + r"\*\*" + re.escape(name) + r":\*\*[ \t]*(.*)$",
        re.MULTILINE,
    )
    for name in UCR_FIELD_NAMES
}

# Any-field detector — used to find the NEXT field boundary when slicing a
# free-text body, regardless of which field it is. Matches the same prefix
# shape as the individual field patterns so an embedded field-LIKE line inside
# a body still counts as a boundary ONLY when it is one of the four real
# fields; a generic `**Whatever:**` line is intentionally NOT a boundary.
_ANY_FIELD_PATTERN = re.compile(
    _FIELD_PREFIX
    + r"\*\*(?:"
    + r"|".join(re.escape(name) for name in UCR_FIELD_NAMES)
    + r"):\*\*",
    re.MULTILINE,
)


class UCREntry:
    """Parsed representation of one `### UCR-<n>` entry.

    `raw_fields` holds the verbatim body text per field (free-text fields keep
    their full multi-line body, trailing whitespace stripped). Sink paths must
    use `safe_field` / `safe_proposed_change` / `safe_rationale`, which wrap the
    raw text with `spec_dirname.display_safe` so untrusted control/ANSI/RTL
    bytes cannot forge a FAIL/WARN line or visually reorder terminal output.
    """

    def __init__(self, number: int, raw_fields: dict[str, Optional[str]]):
        self.number = number
        self.raw_fields: dict[str, Optional[str]] = raw_fields

    # -- structural accessors (raw; safe for comparison, not for printing) --

    def target(self) -> Optional[str]:
        """Return the raw `Target` value (a backtick-wrapped qualified id) or None.

        Control-char-free by grammar in practice; the qualified-id structural
        check in `validate_spec.py` runs on this raw value.
        """
        return self.raw_fields.get("Target")

    def status(self) -> Optional[str]:
        """Return the raw `Status` value or None."""
        return self.raw_fields.get("Status")

    def has_field(self, name: str) -> bool:
        """Return True iff the field is present (non-None) in this entry."""
        return self.raw_fields.get(name) is not None

    def missing_fields(self) -> list[str]:
        """Return the required fields absent from this entry, in canonical order."""
        return [
            name
            for name in UCR_REQUIRED_FIELDS
            if self.raw_fields.get(name) is None
        ]

    # -- display sinks (the ONLY way a free-text body reaches stdout) --

    def safe_field(self, name: str) -> Optional[str]:
        """Return the `display_safe`-escaped value of `name`, or None if absent.

        This is the sanctioned stdout sink for any field — free-text fields are
        ONLY reachable for printing through this wrapper, so a consumer cannot
        accidentally raw-print untrusted UCR body text (reconcile robustness
        contract). Every codepoint > 0x7F (and all C0/C1 control + ANSI + RTL /
        zero-width) renders as a visible `\\uXXXX` escape.
        """
        raw = self.raw_fields.get(name)
        if raw is None:
            return None
        return spec_dirname.display_safe(raw)

    def safe_proposed_change(self) -> Optional[str]:
        """Return the `display_safe`-escaped `Proposed change` body, or None."""
        return self.safe_field("Proposed change")

    def safe_rationale(self) -> Optional[str]:
        """Return the `display_safe`-escaped `Rationale` body, or None."""
        return self.safe_field("Rationale")


class UCRParseResult:
    """Structured result of parsing a `## Upstream Change Requests` stanza.

    Carries the parsed entries PLUS the three signals a consumer
    (`validate_spec.py`) needs to emit FAILs without re-deriving them:

      * `duplicate_ids`         — canonical UCR numbers that appeared > once.
      * `invalid_status_ids`    — UCR numbers whose status is outside the
                                  closed vocabulary {open, applied, withdrawn}.
      * `missing_field_ids`     — list of (ucr_number, field_name) for each
                                  required field absent from an entry.
      * `malformed_ids`         — raw id strings rejected at parse time
                                  (leading zero like `01`); these never become
                                  `entries` and never reach the duplicate check.

    `present` records whether the `## Upstream Change Requests` section existed
    at all, so a consumer can no-op cleanly when it is absent.
    """

    def __init__(
        self,
        present: bool,
        entries: list[UCREntry],
        duplicate_ids: list[int],
        invalid_status_ids: list[int],
        missing_field_ids: list[tuple[int, str]],
        malformed_ids: list[str],
    ):
        self.present = present
        self.entries = entries
        self.duplicate_ids = duplicate_ids
        self.invalid_status_ids = invalid_status_ids
        self.missing_field_ids = missing_field_ids
        self.malformed_ids = malformed_ids

    def has_signals(self) -> bool:
        """Return True iff any error signal is set (duplicate/status/missing/malformed)."""
        return bool(
            self.duplicate_ids
            or self.invalid_status_ids
            or self.missing_field_ids
            or self.malformed_ids
        )


def extract_ucr_section(content: str) -> Optional[str]:
    """Return the body of the `## Upstream Change Requests` section, or None.

    The body excludes the header line itself and runs to the next `## ` section
    heading or EOF. Mirrors `cfc_parser.extract_cfc_section`'s boundary logic.
    Never raises.
    """
    m = UCR_HEADER_PATTERN.search(content)
    if m is None:
        return None
    body_start = m.end()
    next_h2 = re.search(r"^## ", content[body_start:], re.MULTILINE)
    body_end = body_start + next_h2.start() if next_h2 else len(content)
    return content[body_start:body_end]


def _parse_entry_fields(entry_body: str) -> dict[str, Optional[str]]:
    """Extract the four fields from one entry body via offset-slicing (no `.*?`).

    For each field, the inline remainder on the field's own line is captured by
    that field's pattern. For free-text fields the body extends from the end of
    the field's match line to the start of the NEXT real field (per
    `_ANY_FIELD_PATTERN`) or the end of the entry body — sliced by offset, never
    by a backtracking terminator.
    """
    fields: dict[str, Optional[str]] = {name: None for name in UCR_FIELD_NAMES}

    # Collect the first occurrence offset of each field (start of its line and
    # end of its `**Field:** ` marker, where the inline value begins).
    matches: list[tuple[int, int, str]] = []
    for name, pattern in UCR_FIELD_PATTERNS.items():
        m = pattern.search(entry_body)
        if m is None:
            continue
        # m.start() is the line start (prefix); the inline value begins at the
        # start of group(1).
        value_start = m.start(1)
        matches.append((m.start(), value_start, name))

    # Order by where each field appears so we can slice bodies between them.
    matches.sort(key=lambda t: t[0])

    for idx, (_line_start, value_start, name) in enumerate(matches):
        # The body for this field runs to the start of the next field's LINE,
        # or to the end of the entry body for the final field. This is a pure
        # offset slice — no regex spans the gap, so it is linear in body size.
        if idx + 1 < len(matches):
            next_line_start = matches[idx + 1][0]
        else:
            next_line_start = len(entry_body)
        body = entry_body[value_start:next_line_start]
        if name in UCR_FREE_TEXT_FIELDS:
            # Preserve interior blank lines; only strip outer whitespace.
            fields[name] = body.strip()
        else:
            # Single-line fields: take only the inline remainder of the line.
            fields[name] = body.splitlines()[0].strip() if body else ""

    return fields


def parse_ucr_stanza(content: str) -> UCRParseResult:
    """Parse the `## Upstream Change Requests` stanza from full `spec.md` text.

    Returns a `UCRParseResult` carrying the structured entries plus the
    duplicate-id / invalid-status / missing-field / malformed-id signals the
    consumer needs. NEVER raises.

    Entry numbers use the same canonical-decimal grammar as `### CFC-N`
    (`^(0|[1-9]\\d*)$`, with both leading-zero forms like `01` AND `0` itself
    REJECTED as malformed). A malformed id is recorded in `malformed_ids` and
    its entry is dropped — it never reaches the duplicate check (so a leading-
    zero id is "malformed", never "a duplicate of N").

    Free-text bodies are sliced by offsets between line-anchored field matches;
    there is no `.*?` terminator, so a large adversarial body parses in linear
    time.
    """
    section = extract_ucr_section(content)
    if section is None:
        return UCRParseResult(
            present=False,
            entries=[],
            duplicate_ids=[],
            invalid_status_ids=[],
            missing_field_ids=[],
            malformed_ids=[],
        )

    entries: list[UCREntry] = []
    malformed_ids: list[str] = []
    seen_counts: dict[int, int] = {}
    invalid_status_ids: list[int] = []
    missing_field_ids: list[tuple[int, str]] = []

    headers = list(UCR_ENTRY_PATTERN.finditer(section))
    for i, m in enumerate(headers):
        raw_number = m.group(1)
        # Body of this entry runs from the end of its header line to the start
        # of the next `### UCR-` header (offset slice; no backtracking).
        body_start = m.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(section)
        entry_body = section[body_start:body_end]

        # Canonical-decimal id gate — leading-zero / zero rejected, exactly like
        # CFC. A malformed id never becomes an entry, so it cannot be a duplicate.
        if not UCR_ENTRY_NUMBER_FORMAT.match(raw_number) or raw_number == "0":
            malformed_ids.append(raw_number)
            continue

        number = int(raw_number)
        seen_counts[number] = seen_counts.get(number, 0) + 1

        raw_fields = _parse_entry_fields(entry_body)
        entry = UCREntry(number=number, raw_fields=raw_fields)
        entries.append(entry)

        # Missing-required-field signal.
        for field_name in entry.missing_fields():
            missing_field_ids.append((number, field_name))

        # Invalid-status signal — only when a status value is actually present
        # (a missing Status is already covered by the missing-field signal).
        status_value = entry.status()
        if status_value is not None and status_value not in UCR_STATUS_VOCABULARY:
            invalid_status_ids.append(number)

    duplicate_ids = [num for num, count in seen_counts.items() if count > 1]
    duplicate_ids.sort()

    return UCRParseResult(
        present=True,
        entries=entries,
        duplicate_ids=duplicate_ids,
        invalid_status_ids=invalid_status_ids,
        missing_field_ids=missing_field_ids,
        malformed_ids=malformed_ids,
    )
