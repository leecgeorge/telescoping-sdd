"""Shared spec-directory name grammar.

Owned by this module; imported by `validate_spec.py` (the authoring gate /
consumer) and `validate_blueprint.py` (the coverage walker) via the existing
`sys.path.append(_SHARED_SCRIPTS)` pattern they already use for `cfc_parser`
and `arch_config`. Stdlib-only — no third-party dependencies.

This module is the single source of truth for what a `specs/<dir>/` name may
look like, so the two validators cannot drift to independent interpretations
(the same anti-drift discipline `cfc_parser.py` applies to the CFC format).

Two valid directory forms:
  * **bound** — ``F<n>-<slug>`` (uppercase ``F``, positive no-leading-zero
    integer, then a valid slug). Used for a feature that appears in
    ``blueprint/PLAN.md`` (in-file identifier ``F<n>``).
  * **standalone** — a bare ``<slug>`` (lowercase kebab-case). Used for a
    feature with no PLAN (in-file identifier ``n/a``).

IMPORTANT: ``parse_feature_number`` is intentionally LENIENT — it returns an
int for a bare ``F<n>`` token (e.g. ``"F3"`` -> 3) even though
``is_bound_form("F3")`` is ``False``. Validity gating MUST therefore use
``classify_dirname`` or ``is_bound_form``, never
``parse_feature_number(name) is not None``. The bare-token leniency exists
solely for backward-compatible ``walk_specs`` behaviour in
``validate_blueprint.py`` (so pre-1.7.0 ``specs/F<n>/`` directories still
resolve to the right feature id while earning a migration WARN).

The directory-name contract is deliberately out-of-band from every content
hash and the ``--approve``/CFC cascade: renaming a spec directory never
invalidates any approval or hash.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Compiled patterns (module-level, compiled once)
# ---------------------------------------------------------------------------

# Valid slug: lowercase kebab, max length checked separately in is_valid_slug.
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Bound form: F<positive-no-leading-zero>-<slug>. The slug-length cap is NOT
# baked into this regex — is_bound_form re-checks the slug portion via
# is_valid_slug so the 50-char cap lives in exactly one place.
_BOUND_PATTERN = re.compile(r"^F([1-9]\d*)-([a-z0-9]+(?:-[a-z0-9]+)*)$")

# Bare token: F followed by digits, end of string (no slug). Used by
# is_standalone_form (to exclude bare tokens from standalone), classify_dirname
# (the "bare" branch), and parse_feature_number (lenient extraction).
_BARE_TOKEN_PATTERN = re.compile(r"^F(\d+)$")

# Derived form: <project-alias>--F<n>-<slug>. The `--` sentinel separates a
# lowercase-kebab project alias from a bound-style F<n>-<slug> tail. The
# slug-length cap is NOT baked into this regex — is_derived_form re-checks the
# slug portion via is_valid_slug so the 50-char cap lives in exactly one place.
#
# Anchored with `\A`/`\Z` (NOT `^`/`$`): `$` matches just before a trailing
# `\n`, so `^...$` would classify `proj--F7-slug\n` as derived while
# project_link's decomposition rejects it — the two grammars would then disagree
# on a newline-suffixed name and the unpack in validate_spec's derived branch
# would crash on the `None`. `\Z` admits no trailing newline (matching the same
# control-char-injection guard `display_safe` exists for).
#
# This compiled object is the SINGLE structural grammar for the derived
# directory name: `project_link.DERIVED_DIRNAME_PATTERN` re-exports THIS pattern
# (one-way import: project_link -> spec_dirname) and `parse_derived_dirname`
# decomposes via it, so "is it derived?" (this module's classification gate) and
# "decompose it" (project_link's typed parse) share one grammar and can never
# drift — the cross-module analogue of how is_bound_form / parse_bound share
# `_BOUND_PATTERN` here. spec_dirname owns the dir-name STRUCTURE; project_link
# owns the typed decomposition and the qualified-id (`<project>:F<n>`) grammar.
DERIVED_DIRNAME_PATTERN = re.compile(
    r"\A([a-z0-9]+(?:-[a-z0-9]+)*)--F([1-9]\d*)-([a-z0-9]+(?:-[a-z0-9]+)*)\Z"
)

_SLUG_MAX = 50
_TITLE_MAX = 4096  # cap before NFKD to avoid pathological normalization

# Canonical user-facing CLI hint for generating a slug. Single source so every
# FAIL/WARN message in both validators points at the same invocation (avoids the
# string drifting across copies). Derived from this module's own location at
# runtime so the printed command is actually runnable from the user's
# environment (the script lives in the plugin install root, NOT under the
# project's cwd — a literal `telescoping-sdd/scripts/...` would not exist there).
SLUGIFY_CLI_HINT = f'python {Path(__file__).resolve()} slugify "<title>"'


def is_valid_slug(s: str) -> bool:
    """Return True if ``s`` is a valid slug: lowercase kebab, 1-50 chars.

    No minimum beyond a single non-empty kebab segment; 50 is an inclusive
    hard cap. This is the single authoritative length check for the grammar.
    """
    return bool(_SLUG_PATTERN.match(s)) and len(s) <= _SLUG_MAX


def is_bound_form(name: str) -> bool:
    """Return True if ``name`` matches the bound form ``F<n>-<slug>``.

    False for bare tokens (``"F3"``), lowercase-f forms (``"f3-racing"``),
    leading-zero (``"F007-x"``), or zero (``"F0-x"``). The slug portion must
    additionally satisfy ``is_valid_slug`` (so an over-50-char slug is False).
    """
    m = _BOUND_PATTERN.match(name)
    return bool(m) and is_valid_slug(m.group(2))


def is_standalone_form(name: str) -> bool:
    """Return True if ``name`` is a valid standalone slug.

    A standalone name is a valid slug that is neither a bound form nor a bare
    ``F<n>`` token. Examples: ``"cli-notes-app"`` -> True, ``"f3-racing"`` ->
    True (lowercase ``f``), ``"F3-checkout-flow"`` -> False (bound), ``"F3"``
    -> False (bare token).
    """
    return (
        is_valid_slug(name)
        and not is_bound_form(name)
        and not _BARE_TOKEN_PATTERN.match(name)
    )


def is_derived_form(name: str) -> bool:
    """Return True iff ``name`` matches ``<project>--F<n>-<slug>`` (valid slug).

    The project alias must be lowercase kebab, ``F<n>`` a positive
    no-leading-zero integer, and the slug portion must additionally satisfy
    ``is_valid_slug`` (so an over-50-char slug is False). Consistent with
    ``is_bound_form`` / ``is_standalone_form``: a Boolean gate only — no tuple
    decomposition (that lives in ``project_link.parse_derived_dirname``).

    False for ``"F7--checkout"`` (uppercase ``F`` is not a valid lowercase
    project alias) and any name without the ``--`` sentinel. Never raises.

    Uses the same compiled ``DERIVED_DIRNAME_PATTERN`` that
    ``project_link.parse_derived_dirname`` decomposes with, so this gate and that
    decomposition agree on every input (including a trailing-newline name, which
    both reject — no crash in validate_spec's derived branch).
    """
    m = DERIVED_DIRNAME_PATTERN.match(name)
    return bool(m) and is_valid_slug(m.group(3))


def is_derived_spec(spec_dir) -> bool:
    """Return True iff ``spec_dir.name`` classifies as ``"derived"``.

    The SINGLE shared predicate keyed off ``classify_dirname`` so the
    ``validate_spec`` derived-branch gate (I4) and the ``validate_cfc_consumer``
    derived-spec exemption (I7) cannot drift on what "derived" means. Takes a
    path-like with a ``.name`` attribute. Never raises.
    """
    return classify_dirname(spec_dir.name) == "derived"


def classify_dirname(name: str) -> str:
    """Classify a spec directory basename into one of five categories.

    Returns:
        ``"bound"``      if ``is_bound_form(name)`` is True
        ``"derived"``    if ``is_derived_form(name)`` is True
                         (``<project>--F<n>-<slug>``)
        ``"bare"``       if ``name`` matches ``^F\\d+$`` (bare token, incl.
                         ``F0``, ``F007`` — leniently, for backward compat)
        ``"standalone"`` if ``is_standalone_form(name)`` is True
        ``"invalid"``    otherwise (e.g. ``F0-x``, ``F007-x``, ``My_Feature``,
                         ``F7--checkout``)

    The ``derived`` branch runs after ``is_bound_form`` and before the
    bare-token branch: an uppercase-``F`` form like ``F7--checkout`` is not a
    valid lowercase project alias, so it falls through to the bare-token branch
    and then on to ``"invalid"`` (it has a ``--`` suffix).

    This is the single dispatch point for all consumers (the ``walk_specs``
    filter, ``_emit_malformed_dirname_warns``, ``check_dir_identifier``, and the
    ``is_derived_spec`` predicate). Using it everywhere prevents walk-vs-warn
    classification drift — the feature's own anti-drift principle applied to
    itself. Never raises.
    """
    if is_bound_form(name):
        return "bound"
    if is_derived_form(name):
        return "derived"
    if _BARE_TOKEN_PATTERN.match(name):
        return "bare"
    if is_standalone_form(name):
        return "standalone"
    return "invalid"


def parse_feature_number(name: str) -> Optional[int]:
    """Return the integer feature number from a bound or bare-token name.

    Lenient by design: returns an int for a bare-token form (``"F3"`` -> 3)
    even though ``is_bound_form("F3")`` is False. Does NOT extend to arbitrary
    ``F<digits>-`` prefixed strings like ``"F0-slug"`` (neither a valid bound
    form nor a bare token -> None).

    Returns:
        3 for ``"F3-checkout-flow"`` and ``"F3"``; 0 for ``"F0"``; 7 for
        ``"F007"``; None for ``"cli-notes-app"``, ``"f3-racing"``,
        ``"My_Feature"``, ``"F0-x"``, ``"F007-x"``.

    Validity gating MUST use ``classify_dirname``/``is_bound_form``, never
    ``parse_feature_number(name) is not None``. Never raises.
    """
    m = _BOUND_PATTERN.match(name)
    if m:
        return int(m.group(1))
    m = _BARE_TOKEN_PATTERN.match(name)
    if m:
        return int(m.group(1))
    return None


def parse_bound(name: str) -> Optional[tuple[int, str]]:
    """Return ``(feature_number, slug)`` for a valid bound name, else ``None``.

    The single grammar-owned decomposition of the bound form. Consumers that
    need both the number and the slug (e.g. validate_spec's rename suggestions)
    call this instead of re-splitting the name themselves — re-splitting would
    be a second interpretation of the grammar this module exists to centralize.
    Returns ``None`` for bare, standalone, or invalid names.

        parse_bound("F3-checkout-flow") -> (3, "checkout-flow")
        parse_bound("F3")               -> None   # bare, no slug
        parse_bound("checkout-flow")    -> None   # standalone
    """
    m = _BOUND_PATTERN.match(name)
    if m and is_valid_slug(m.group(2)):
        return int(m.group(1)), m.group(2)
    return None


def display_safe(name: str) -> str:
    """Escape a directory name for safe embedding in validator stdout.

    Control characters (newline, CR, NUL, ANSI escapes) in a directory name
    could otherwise inject forged FAIL/WARN lines into the validators' output.
    This is the single shared spoofing guard used by both ``validate_spec.py``
    and ``validate_blueprint.py`` — do NOT re-inline the encode/decode at call
    sites (three copies were drifting before this was centralized).
    """
    return name.encode("unicode_escape").decode("ascii")


def slugify(title: str) -> str:
    """Convert a feature title to a lowercase kebab-case slug.

    Pipeline (per design DM2):
      1. Cap input at 4096 chars before normalization.
      2. NFKD normalization, then drop ``Mn`` combining marks (accent folding).
         LOSSY: superscripts / fullwidth / ligatures / fractions are expanded
         (``x²`` -> ``x2``, ``ﬁ`` -> ``fi``), so distinct titles can collapse
         to the same slug — acceptable because the user reviews the slug before
         creating the directory.
      3. Lowercase.
      4. Replace each run of non-``[a-z0-9]`` characters (incl. control chars)
         with a single hyphen.
      5. Strip leading/trailing hyphens.
      6. Truncate at a hyphen boundary so ``len(result) <= 50``; if the first
         segment alone exceeds 50 chars, hard-truncate it to 50.
      7. Raise ``ValueError`` if the result is empty (no ``[a-z0-9]`` chars).

    The output unconditionally satisfies ``is_valid_slug``.

    Raises:
        ValueError: if the title reduces to an empty slug. The message includes
            ``repr(title)`` to escape control characters in the title (the same
            spoofing concern that applies to directory names in FAIL messages).
    """
    capped = title[:_TITLE_MAX]
    decomposed = unicodedata.normalize("NFKD", capped)
    no_marks = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    lowered = no_marks.lower()
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered)
    stripped = hyphenated.strip("-")

    if len(stripped) > _SLUG_MAX:
        segments = stripped.split("-")
        out: list[str] = []
        total = 0
        for seg in segments:
            add = len(seg) + (1 if out else 0)
            if total + add <= _SLUG_MAX:
                out.append(seg)
                total += add
            else:
                break
        # If even the first segment alone exceeds the cap, hard-truncate it.
        result = "-".join(out) if out else segments[0][:_SLUG_MAX]
    else:
        result = stripped

    if not result:
        raise ValueError(
            f"title produces an empty slug: {title!r} — provide a title with "
            f"at least one Latin letter or digit"
        )
    return result


def main() -> None:
    """CLI entry point.

    Usage:
        python <this-script>/spec_dirname.py slugify "Feature Title"

    Invoked by file path, NOT ``python -m spec_dirname`` — the shared scripts
    directory is not on ``sys.path`` by default. The user-facing hint
    (``SLUGIFY_CLI_HINT``) resolves ``<this-script>`` to this file's real
    absolute location at runtime.

    Exit codes:
        0  success
        1  slugify raised ValueError (empty result); message on stderr
        2  wrong number of arguments or unknown subcommand
    """
    argv = sys.argv[1:]
    usage = f"usage: {SLUGIFY_CLI_HINT}"
    if len(argv) < 1 or argv[0] != "slugify":
        print(usage, file=sys.stderr)
        sys.exit(2)
    if len(argv) != 2:
        print(usage, file=sys.stderr)
        sys.exit(2)
    try:
        print(slugify(argv[1]))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
