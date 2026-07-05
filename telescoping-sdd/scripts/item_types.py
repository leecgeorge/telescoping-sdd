"""Work-item type vocabulary — the single, closed owner of the four work-item
type prefixes (`F`, `D`, `CR`, `TD`) and the parse/format primitives over them.

A stdlib-only leaf module (imports only `re`, plus the `from __future__` header):
every other grammar owner imports this module's `PREFIX_ALTERNATION` /
`ITEM_TYPE_PREFIXES` instead of re-deriving `(?:F|D|CR|TD)`, so the vocabulary
has exactly one source of truth and cannot drift. Keeping it a dependency-free
leaf (no project imports) keeps the shared-grammar dependency graph acyclic,
mirroring the `trajectory` / `content_hash` / `artifact_resolution` split.

Doctrine:
  * Sentinel-`None`, never-raises. `parse_item_id` / `format_item_id` return
    `None` on any rejection (unknown / malformed / out-of-domain / wrong-type
    input) rather than raising, matching the `spec_dirname.parse_bound` /
    `parse_feature_number` family. Callers null-check the result.
  * Case-sensitive, ASCII-only, positive, no-leading-zero canonical id space —
    matching `spec_dirname`'s "uppercase prefix, positive no-leading-zero"
    grammar — so no two distinct strings ever parse to the same `(prefix, number)`.
  * None of the four prefixes is a textual prefix of another, so the alternation
    needs no longest-match-first ordering (asserted by the test suite, not assumed).
  * `PREFIX_ALTERNATION` is prefix-only and embed-safe; consumers splice it with
    `NUMBER_PATTERN` and supply their own anchoring.
"""
from __future__ import annotations

import re

# The closed vocabulary. Immutable so an importing consumer cannot mutate the
# shared set; membership tests are O(1). (frozenset, mirroring
# artifact_resolution.KNOWN_ARTIFACTS.)
ITEM_TYPE_PREFIXES: frozenset = frozenset({"F", "D", "CR", "TD"})

# Prefix-only, non-capturing, embed-safe alternation fragment. NOT anchored and
# NOT a whole-identifier matcher — consumers splice it into a larger regex that
# supplies its own number sub-pattern and anchoring. No prefix textually shadows
# another, so the spec ordering is safe.
PREFIX_ALTERNATION: str = r"(?:F|D|CR|TD)"

# ASCII, positive, no-leading-zero number sub-pattern (non-capturing). Exported
# so a consumer composing a whole-identifier regex reuses the SAME number grammar
# this module enforces rather than re-deriving `[1-9][0-9]*` and drifting.
NUMBER_PATTERN: str = r"(?:[1-9][0-9]*)"

# Private, compiled once. `\A...\Z` (not `^...$`) refuses a trailing newline;
# `re.ASCII` restricts `[0-9]` to ASCII digits (never Unicode `Nd`).
_ITEM_ID_RE = re.compile(r"\A(?P<prefix>F|D|CR|TD)(?P<number>[1-9][0-9]*)\Z", re.ASCII)

# Deterministic overlong-numeral cap = CPython's documented default int<->str
# digit-conversion limit. Enforced by this module on EVERY Python version (the
# interpreter's own limit is absent pre-3.9.14), so overlong rejection is uniform
# and DoS-safe across the CI 3.9 + 3.12 matrix. `_MAX_NUMBER_VALUE` is the
# exclusive upper bound `format_item_id` compares against (pure-int, no
# `str(huge_int)`). 4300 digits is astronomically beyond any real work-item id.
_MAX_NUMBER_DIGITS: int = 4300
_MAX_NUMBER_VALUE: int = 10 ** _MAX_NUMBER_DIGITS


def parse_item_id(item_id: str) -> tuple[str, int] | None:
    """Parse a canonical work-item identifier into its ``(prefix, number)`` pair.

    The single shared decomposition of a work-item id, so no consumer
    re-implements identifier splitting and every consumer agrees on what a valid
    identifier is.

    Args:
        item_id: The identifier string to parse, e.g. ``"CR12"``. Any input that
            is not a canonical identifier — unknown prefix (``"X5"``, ``"C1"``),
            wrong case (``"cr1"``), leading zeros (``"CR01"``, ``"F001"``), zero
            (``"F0"``), non-ASCII digits (``"CR１２"``), wrong shape (empty,
            ``"CR"``, ``"F1a"``, ``"CR+12"``, ``"CR 12"``, ``" F1 "``), or a
            non-``str`` type (``None``, ``int``, ``bytes``) — is rejected.

    Returns:
        A 2-tuple ``(prefix, number)`` where ``prefix`` is one of
        ``"F"``/``"D"``/``"CR"``/``"TD"`` and ``number`` is a positive int
        (``>= 1``), OR ``None`` if ``item_id`` is not a canonical identifier.

    Never raises, and never does unbounded work. A numeral whose digit count
    exceeds ``_MAX_NUMBER_DIGITS`` (4300, CPython's default int-to-str limit) is
    rejected as ``None`` by an explicit length check BEFORE ``int()`` —
    deterministically on every Python version, including pre-3.9.14 builds that
    have no interpreter limit; a lowered interpreter limit is also caught via a
    ``ValueError`` backstop.
    """
    # Reject non-str FIRST: _ITEM_ID_RE.match() raises TypeError (not ValueError)
    # on a non-str, which the int() backstop below would not catch.
    if not isinstance(item_id, str):
        return None
    match = _ITEM_ID_RE.match(item_id)
    if match is None:
        return None
    digits = match.group("number")
    # Deterministic overlong guard, before int(), on every version.
    if len(digits) > _MAX_NUMBER_DIGITS:
        return None
    try:
        number = int(digits)
    except ValueError:  # backstop: an embedding app lowered the interpreter limit
        return None
    return (match.group("prefix"), number)


def format_item_id(prefix: str, number: int) -> str | None:
    """Render a ``(prefix, number)`` pair into its canonical identifier string.

    The single shared rendering primitive, so identifier formatting is defined in
    exactly one place and round-trips with ``parse_item_id``.

    Args:
        prefix: A type prefix; must be a member of ``ITEM_TYPE_PREFIXES``
            (case-sensitive). A non-vocabulary or non-``str`` prefix is rejected.
        number: A positive integer (``>= 1``). Zero, negatives, ``bool``, and
            non-``int`` types are rejected. No meaningful upper bound, but a number
            with more than 4300 digits (``>= _MAX_NUMBER_VALUE``) is rejected so
            format's domain matches ``parse_item_id``'s cap and rendering never
            trips CPython's int-to-str limit.

    Returns:
        The canonical no-leading-zero identifier, e.g. ``"CR12"``, OR ``None`` if
        ``prefix`` or ``number`` is out of the canonical domain.

    Never raises.
    """
    if prefix not in ITEM_TYPE_PREFIXES:
        # Membership handles both non-vocabulary and non-str prefixes (a non-str
        # is simply not in the frozenset) without raising.
        return None
    # bool is a subclass of int — reject it explicitly so True does not format
    # as "F1". Reject non-int types and non-positive / overlong values.
    if isinstance(number, bool) or not isinstance(number, int):
        return None
    if number < 1 or number >= _MAX_NUMBER_VALUE:
        return None
    return f"{prefix}{number}"
