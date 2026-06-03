"""Shared cross-project derivation grammar.

Owned by this module; imported by `validate_spec.py`, `validate_blueprint.py`,
and `reconcile.py` via the existing `sys.path.append(_SHARED_SCRIPTS)` pattern
they already use for `cfc_parser`, `spec_dirname`, and `arch_config`. Stdlib-only
— no third-party dependencies.

This module owns the typed decompositions of the two cross-project forms, so no
consumer ever re-derives either grammar (the same anti-drift discipline
`cfc_parser.py` and `spec_dirname.py` apply to their formats):

  * **qualified-id** — ``<project>:F<n>`` (DM1). Names a feature in another
    project's PLAN, e.g. ``residents:F7``. Used by the derived spec's
    ``**Derived from:**`` line and by UCR ``Target`` fields. project_link owns
    this grammar outright (a qualified id is NOT a directory name).
  * **derived directory name** — ``<project>--F<n>-<slug>`` (DM2). The on-disk
    directory name for a feature derived from a master project's feature, e.g.
    ``residents--F7-resident-sync``. Its STRUCTURAL pattern is owned by
    ``spec_dirname.DERIVED_DIRNAME_PATTERN`` (the dir-name authority) and reused
    here, so ``parse_derived_dirname`` and ``spec_dirname.is_derived_form`` share
    one compiled pattern and cannot drift; this module owns only the typed
    ``(project, feature_number, slug)`` decomposition over it.

The ``--`` sentinel between the project alias and ``F<n>`` is unambiguous
because BOTH the alias grammar and the slug grammar forbid consecutive hyphens
(``is_valid_slug`` rejects them, and the alias pattern only allows single
hyphens between alphanumeric runs). So a literal ``--`` can only be the
separator, never an internal hyphen of either side.

The import is one-way: ``project_link -> spec_dirname`` (for ``is_valid_slug``);
``spec_dirname`` never imports this module.

Every parser is total: malformed input returns ``None`` and never raises
(mirroring ``cfc_parser`` and ``spec_dirname.parse_bound``).
"""
from __future__ import annotations

import dataclasses
import re
from typing import Optional

import spec_dirname

# ---------------------------------------------------------------------------
# Compiled patterns (module-level, compiled once; no raw strings at call sites)
# ---------------------------------------------------------------------------

# Project alias: lowercase kebab — alphanumeric runs joined by single hyphens,
# at least one char, no consecutive hyphens. Same grammar as DM1's project field
# and DM2's project alias.
_PROJECT_ALIAS = r"[a-z0-9]+(?:-[a-z0-9]+)*"

# Feature number: positive integer, no leading zero (so `F0` and `F07` are both
# rejected). Mirrors `spec_dirname._BOUND_PATTERN`'s `[1-9]\d*` and the
# canonical-decimal discipline `cfc_parser` enforces on `### CFC-N`.
_FEATURE_NUMBER = r"[1-9]\d*"

# Qualified id: <project>:F<n>. Anchored with `\A`/`\Z` (NOT `^`/`$`) so a
# trailing newline does not slip through — `$` matches just before a final
# `\n`, which would let `residents:F7\n` parse and reintroduce exactly the
# control-char injection vector `display_safe` guards against. `\Z` admits no
# trailing newline, so trailing garbage and control chars are rejected.
QUALIFIED_ID_PATTERN = re.compile(
    r"\A(" + _PROJECT_ALIAS + r"):F(" + _FEATURE_NUMBER + r")\Z"
)

# Derived directory name: <project>--F<n>-<slug>. This grammar belongs to the
# spec-directory namespace, so the SINGLE compiled pattern is OWNED by
# `spec_dirname` (the module that classifies dir names) and reused here for
# decomposition — `parse_derived_dirname` and `spec_dirname.is_derived_form`
# therefore share ONE pattern object and can never drift on what a derived dir
# name is (the dual-grammar bug this reuse closes: the two used to disagree on a
# trailing-newline name, crashing validate_spec's derived branch). Contrast
# QUALIFIED_ID_PATTERN above, which project_link owns because `<project>:F<n>`
# is NOT a directory name. The shared pattern is `\A`/`\Z`-anchored (no trailing
# newline); its captures are (alias, number, slug) and the slug group is
# re-validated below via `spec_dirname.is_valid_slug` so the 1-50-char kebab cap
# lives in exactly one place (spec_dirname), never duplicated here.
DERIVED_DIRNAME_PATTERN = spec_dirname.DERIVED_DIRNAME_PATTERN

# ---------------------------------------------------------------------------
# Derived-spec provenance FIELD grammar (DM2). The two lines a derived
# `spec.md` carries, plus the master-hash value shape and the `unbound`
# bootstrap sentinel. Owned HERE so the authoring gate (`validate_spec`) and the
# integrator (`reconcile`) read byte-identical field shapes: a shared script
# must not import a skill validator, so without this single owner the two kept
# duplicate copies (one even renamed, hiding the dup from grep) that could
# silently drift — e.g. a digest-casing change missed in one copy would make
# reconcile misread valid specs as "hash field absent". The value captures are
# loose (`[^`]*`) on purpose: well-formedness is decided downstream
# (`parse_qualified_id` for the id; `MASTER_HASH_VALUE_RE` / `MASTER_HASH_UNBOUND`
# for the hash), so a malformed-but-present field still reads as present.
# ---------------------------------------------------------------------------

# `**Derived from:** \`<project>:F<n>\`` — backtick-wrapped qualified id.
DERIVED_FROM_LINE_RE = re.compile(
    r"^\*\*Derived from:\*\*\s*`([^`]*)`\s*$", re.MULTILINE
)
# `**Master contract hash:** \`<64-hex|unbound>\``.
MASTER_CONTRACT_HASH_LINE_RE = re.compile(
    r"^\*\*Master contract hash:\*\*\s*`([^`]*)`\s*$", re.MULTILINE
)
# A 64-char lowercase-hex SHA-256 digest (the `master_feature` producer output
# shape). The `unbound` sentinel is accepted separately, not via this pattern.
MASTER_HASH_VALUE_RE = re.compile(r"^[0-9a-f]{64}$")
MASTER_HASH_UNBOUND = "unbound"


def parse_qualified_id(s: str) -> Optional[tuple[str, int]]:
    """Return ``(project, feature_number)`` for a valid qualified id, else ``None``.

    Valid: ``residents:F7`` -> ``("residents", 7)``, ``vps-edge:F1`` ->
    ``("vps-edge", 1)``, ``a:F99`` -> ``("a", 99)``.

    Returns ``None`` for (non-exhaustive): an empty string, a missing project
    (``F7``), an uppercase alias (``Residents:F7``), feature number zero
    (``residents:F0``), a leading-zero number (``residents:F07``), trailing
    garbage (``residents:F7x``), consecutive hyphens in the alias
    (``bad--alias:F3``), or any embedded control character. Never raises.
    """
    if not isinstance(s, str):
        return None
    m = QUALIFIED_ID_PATTERN.match(s)
    if not m:
        return None
    return m.group(1), int(m.group(2))


def parse_derived_dirname(s: str) -> Optional[tuple[str, int, str]]:
    """Return ``(project, feature_number, slug)`` for a valid derived directory
    name, else ``None``.

    Valid: ``residents--F7-resident-sync`` ->
    ``("residents", 7, "resident-sync")``; ``vps-edge--F1-a`` ->
    ``("vps-edge", 1, "a")``.

    The slug portion must satisfy ``spec_dirname.is_valid_slug`` (lowercase
    kebab, 1-50 chars, no consecutive hyphens), so an over-50-char slug or a
    slug with consecutive hyphens makes the whole name ``None``. The ``--``
    sentinel is unambiguous because neither the alias nor the slug may contain
    consecutive hyphens.

    Returns ``None`` for (non-exhaustive): a bad alias, an uppercase-``F`` form
    that is not a valid lowercase alias (``F7--checkout``), a slug that is too
    long, consecutive hyphens in the alias (``bad--alias--F3-slug``), feature
    number zero, a leading-zero number, the empty string, or any embedded
    control character. Never raises.
    """
    if not isinstance(s, str):
        return None
    m = DERIVED_DIRNAME_PATTERN.match(s)
    if not m:
        return None
    slug = m.group(3)
    if not spec_dirname.is_valid_slug(slug):
        return None
    return m.group(1), int(m.group(2)), slug


@dataclasses.dataclass(frozen=True)
class DerivationLink:
    """A resolved (master-side, derived-side) derivation pair (DM3).

    Constructed by ``reconcile.py`` from a matched master feature and derived
    directory; the parsers return raw tuples, never this type. Frozen so a
    resolved link cannot be mutated after construction.
    """

    master_project: str  # project alias of the master repo
    master_feature_number: int  # F<n> from the master PLAN
    derived_project: str  # project alias of the derived repo
    derived_dirname: str  # full derived directory name


__all__ = [
    "QUALIFIED_ID_PATTERN",
    "DERIVED_DIRNAME_PATTERN",
    "DERIVED_FROM_LINE_RE",
    "MASTER_CONTRACT_HASH_LINE_RE",
    "MASTER_HASH_VALUE_RE",
    "MASTER_HASH_UNBOUND",
    "parse_qualified_id",
    "parse_derived_dirname",
    "DerivationLink",
]
