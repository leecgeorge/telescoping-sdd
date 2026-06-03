"""Tests for the shared cross-project derivation grammar (`project_link.py`).

`project_link.py` owns the `<project>:F<n>` qualified-id grammar and the
`<project>--F<n>-<slug>` derived-directory grammar (CPD design I1 / DM1 / DM2 /
DM3). The suite guards:

* HAPPY PATH for both parsers across alias shapes (single-segment, hyphenated,
  single-char) and feature numbers.
* TOTALITY: every parser returns `None` (never raises) on malformed,
  adversarial, empty, control-char, and trailing-garbage input.
* GRAMMAR EDGES: feature-number zero rejected, leading-zero rejected,
  consecutive-hyphen alias rejected, over-cap slug rejected.
* SYMMETRY CONTRACT: any derived dirname that parses also yields a matching
  qualified-id parse — the producer/consumer-can't-drift invariant.
* STDLIB-ONLY: AST inspection asserts no third-party import.

The module is imported via the shared-scripts `sys.path` insert; `conftest.py`
in this directory snapshots/restores `sys.path` around each test.
"""
from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"
_PROJECT_LINK_PATH = _SCRIPTS / "project_link.py"

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# `project_link` imports `spec_dirname`; both resolve off `_SCRIPTS` on sys.path.
import project_link as pl  # noqa: E402
import spec_dirname as sd  # noqa: E402


# Set of standard-library top-level module names that `project_link.py` is
# permitted to import. Anything outside this set in `test_stdlib_only` is a
# third-party dependency and fails the constraint.
_STDLIB_ALLOWED = {
    "dataclasses",
    "re",
    "typing",
    "__future__",
    # First-party shared sibling module (NOT third-party) — the one-way
    # project_link -> spec_dirname import the design pins.
    "spec_dirname",
}


# ---------------------------------------------------------------------------
# parse_qualified_id
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("residents:F7", ("residents", 7)),
        ("vps-edge:F1", ("vps-edge", 1)),
        ("a:F99", ("a", 99)),
    ],
)
def test_parse_qualified_id_valid(raw, expected):
    assert pl.parse_qualified_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",                 # empty
        "F7",               # missing project
        "Residents:F7",     # uppercase alias
        "residents:F0",     # feature number zero
        "residents:F07",    # leading zero
        "residents:F7x",    # trailing garbage
        "residents:F7\n",   # control char (trailing newline)
        "residents:\x00F7",  # embedded NUL control char
        "residents:F",      # no number
        "residents:7",      # missing F
        "residents F7",     # missing colon
        ":F7",              # empty alias
    ],
)
def test_parse_qualified_id_none_cases(raw):
    assert pl.parse_qualified_id(raw) is None


# ---------------------------------------------------------------------------
# parse_derived_dirname
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("residents--F7-resident-sync", ("residents", 7, "resident-sync")),
        ("vps-edge--F1-a", ("vps-edge", 1, "a")),
    ],
)
def test_parse_derived_dirname_valid(raw, expected):
    assert pl.parse_derived_dirname(raw) == expected


def test_parse_derived_dirname_sentinel_unambiguity():
    # The headline example from the AC: `--` sentinel cleanly splits a
    # hyphenated alias from F<n>-<hyphenated-slug>.
    assert pl.parse_derived_dirname("vps-edge--F7-resident-sync") == (
        "vps-edge",
        7,
        "resident-sync",
    )


@pytest.mark.parametrize(
    "raw",
    [
        "BAD--F3-slug",            # uppercase alias (bad alias)
        "F7--checkout",            # uppercase-F form, no valid lowercase alias
        "residents--F7-" + "a" * 51,  # slug too long (> 50 chars)
        "bad--alias--F3-slug",     # consecutive hyphens in alias position
        "",                        # empty
        "residents-F7-slug",       # single hyphen, not the `--` sentinel
        "residents--F0-slug",      # feature number zero
        "residents--F07-slug",     # leading zero
        "residents--F7-Slug",      # uppercase slug (invalid slug)
        "residents--F7-bad--slug",  # consecutive hyphens in slug
        "residents--F7-",          # empty slug
        "residents--F7",           # no slug separator
        "residents--F7-slug\n",    # trailing control char
    ],
)
def test_parse_derived_dirname_none_cases(raw):
    assert pl.parse_derived_dirname(raw) is None


# ---------------------------------------------------------------------------
# Shared grammar edges
# ---------------------------------------------------------------------------

def test_feature_number_zero_rejected():
    assert pl.parse_qualified_id("residents:F0") is None
    assert pl.parse_derived_dirname("residents--F0-slug") is None


def test_leading_zero_rejected():
    assert pl.parse_qualified_id("residents:F07") is None
    assert pl.parse_derived_dirname("residents--F07-slug") is None


def test_consecutive_hyphen_alias_rejected():
    assert pl.parse_qualified_id("bad--alias:F3") is None
    # Also rejected in the derived form (the `--` would be misread as the
    # sentinel, leaving `alias--F3-slug` which is not a valid F<n>- start).
    assert pl.parse_derived_dirname("bad--alias--F3-slug") is None


# ---------------------------------------------------------------------------
# Symmetry contract (producer/consumer can't drift)
# ---------------------------------------------------------------------------

def test_symmetry_contract():
    """Every derived dirname that parses also yields a matching qualified id.

    Invariant: if parse_derived_dirname(d) == (p, n, slug), then
    parse_qualified_id(f"{p}:F{n}") == (p, n). This is the structural binding
    between the two grammars — a derivation directory always names a
    well-formed master qualified id.
    """
    candidates = [
        "residents--F7-resident-sync",
        "vps-edge--F1-a",
        "a--F99-x",
        "multi-seg-alias--F12-some-long-slug",
        "residents--F1000000-z",
        # Negative controls: these must NOT parse as derived, so they must not
        # enter the symmetry assertion below.
        "F7--checkout",
        "bad--alias--F3-slug",
        "residents--F07-slug",
        "",
    ]
    parsed_any = False
    for d in candidates:
        result = pl.parse_derived_dirname(d)
        if result is None:
            continue
        parsed_any = True
        project, number, _slug = result
        assert pl.parse_qualified_id(f"{project}:F{number}") == (project, number)
    # Guard the loop actually exercised the positive branch (otherwise a parser
    # that returns None for everything would vacuously "pass").
    assert parsed_any


# ---------------------------------------------------------------------------
# Cross-module single-grammar contract (classification vs. decomposition)
#
# `spec_dirname.is_derived_form` (the classification gate) and
# `project_link.parse_derived_dirname` (the typed decomposition) must agree on
# every input — the dual-grammar drift that crashed validate_spec's derived
# branch on a trailing-newline name. They now share ONE compiled pattern.
# ---------------------------------------------------------------------------

def test_derived_pattern_is_single_shared_object():
    """The two modules reference the SAME compiled pattern, not two copies."""
    assert pl.DERIVED_DIRNAME_PATTERN is sd.DERIVED_DIRNAME_PATTERN


@pytest.mark.parametrize("name", [
    # Valid derived names.
    "residents--F7-resident-sync",
    "vps-edge--F1-a",
    "a--F99-x",
    "multi-seg-alias--F12-some-long-slug",
    # Not derived for assorted reasons (alias/number/slug/structure).
    "F7--checkout",
    "Residents--F7-sync",
    "residents--F0-slug",
    "residents--F07-slug",
    "residents--F7-Slug",
    "residents--F7-bad--slug",
    "residents--F7-" + "a" * 51,
    "F3-checkout-flow",
    "cli-notes-app",
    "",
    # The crash trigger: `$` would admit the trailing newline, `\Z` does not.
    "residents--F7-x\n",
    "residents--F7-resident-sync\n",
])
def test_classification_and_decomposition_agree(name):
    """`is_derived_form` ⇔ `parse_derived_dirname is not None`, for every input.

    Also pins the `classify_dirname == "derived"` dispatch to the same truth,
    and confirms that whenever classification says derived the decomposition is
    non-None (so validate_spec's `dir_project, dir_number, _ = parse(...)` unpack
    can never raise `TypeError`).
    """
    parsed = pl.parse_derived_dirname(name)
    is_derived = sd.is_derived_form(name)
    assert is_derived == (parsed is not None)
    assert (sd.classify_dirname(name) == "derived") == (parsed is not None)


# ---------------------------------------------------------------------------
# Stdlib-only constraint (AST inspection)
# ---------------------------------------------------------------------------

def test_stdlib_only():
    """`project_link.py` imports only stdlib + the first-party spec_dirname."""
    tree = ast.parse(_PROJECT_LINK_PATH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # Only absolute imports carry a module; `from . import x` (level>0)
            # has module None and is not a third-party concern here.
            if node.module and node.level == 0:
                imported_roots.add(node.module.split(".")[0])
    disallowed = imported_roots - _STDLIB_ALLOWED
    assert not disallowed, f"unexpected non-stdlib imports: {sorted(disallowed)}"


# ---------------------------------------------------------------------------
# Totality / never-raises on adversarial input
# ---------------------------------------------------------------------------

def test_no_raise_on_adversarial_inputs():
    adversarial = [
        "",
        "\x00",
        "\x1b[31mresidents:F7\x1b[0m",  # ANSI escape wrapper
        "residents:F7\nrm -rf /",        # embedded newline + trailing garbage
        "residents:F7x",                 # trailing garbage
        "residents--F7-slug\x07",        # bell control char
        "a" * 10000,                     # large junk
        ":::",
        "--F1-",
        "F" * 50,
    ]
    for raw in adversarial:
        # Must return None and never raise.
        assert pl.parse_qualified_id(raw) is None
        assert pl.parse_derived_dirname(raw) is None


# ---------------------------------------------------------------------------
# Public API surface + DerivationLink
# ---------------------------------------------------------------------------

def test_public_api_surface():
    for name in (
        "parse_qualified_id",
        "parse_derived_dirname",
        "DerivationLink",
        "QUALIFIED_ID_PATTERN",
        "DERIVED_DIRNAME_PATTERN",
    ):
        assert hasattr(pl, name), f"project_link missing public export: {name}"


def test_derivation_link_is_frozen_dataclass():
    import dataclasses

    link = pl.DerivationLink(
        master_project="residents",
        master_feature_number=7,
        derived_project="vps-edge",
        derived_dirname="residents--F7-resident-sync",
    )
    assert dataclasses.is_dataclass(link)
    assert link.master_project == "residents"
    assert link.master_feature_number == 7
    assert link.derived_project == "vps-edge"
    assert link.derived_dirname == "residents--F7-resident-sync"
    with pytest.raises(dataclasses.FrozenInstanceError):
        link.master_project = "other"  # type: ignore[misc]


def test_module_importable_via_shared_scripts_path():
    # Re-import through the shared-scripts path to mirror how consumers load it.
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    mod = importlib.import_module("project_link")
    assert mod is pl or mod.__file__ == str(_PROJECT_LINK_PATH)
