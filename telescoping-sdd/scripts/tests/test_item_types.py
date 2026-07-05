"""Tests for `item_types.py` — the F1 work-item type vocabulary leaf.

Staging (tasks.md T1 -> T2 -> T3):
  * T1: constants, exported fragments, no-shadowing, leaf-purity -> green after T1.
  * T2: parse_item_id (rejection / round-trip-parse / boundary / per-type) -> green after T2.
  * T3: format_item_id + bidirectional round-trip -> green after T3.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"
_ITEM_TYPES_PATH = _SCRIPTS / "item_types.py"

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import item_types as it  # noqa: E402

_PREFIXES = ("F", "D", "CR", "TD")


# ===========================================================================
# T1 — constants, exported fragments, no-shadowing, leaf-purity
# ===========================================================================

def test_exported_vocabulary_is_exact_frozenset():
    assert it.ITEM_TYPE_PREFIXES == frozenset({"F", "D", "CR", "TD"})
    assert isinstance(it.ITEM_TYPE_PREFIXES, frozenset)


def test_prefix_alternation_matches_vocabulary_and_rejects_outsiders():
    pat = re.compile(rf"\A{it.PREFIX_ALTERNATION}\Z")
    for p in _PREFIXES:
        assert pat.match(p), p
    for bad in ("X", "C", "cr", "f", "Cr", ""):
        assert not pat.match(bad), bad


def test_prefix_alternation_is_non_capturing():
    assert re.compile(it.PREFIX_ALTERNATION).groups == 0


def test_number_pattern_contract():
    assert re.compile(it.NUMBER_PATTERN).groups == 0
    pat = re.compile(rf"\A{it.NUMBER_PATTERN}\Z")
    for good in ("1", "10", "99", "1234567890123456"):
        assert pat.match(good), good
    for bad in ("01", "0", "-5", "1a", "１２"):
        assert not pat.match(bad), bad


def test_composed_fragments_reproduce_item_id_grammar():
    pat = re.compile(rf"\A{it.PREFIX_ALTERNATION}{it.NUMBER_PATTERN}\Z", re.ASCII)
    for good in ("F1", "CR12", "TD7", "D3"):
        assert pat.match(good), good
    for bad in ("CR01", "F0", "cr1", "X5", "CR１２", "C1", "F1a"):
        assert not pat.match(bad), bad


def test_no_prefix_shadows_another():
    for a in _PREFIXES:
        for b in _PREFIXES:
            if a != b:
                assert not a.startswith(b), (a, b)


def test_module_imports_only_stdlib_allowlist():
    """R5 AC1: item_types imports only stdlib (allowlist {re, __future__}) and
    no project module under telescoping-sdd/scripts/."""
    source = _ITEM_TYPES_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    allow = {"re", "__future__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                top = n.name.split(".")[0]
                assert top in allow, f"non-allowlisted import: {n.name}"
                assert not (_SCRIPTS / f"{top}.py").exists(), f"project import: {top}"
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            assert top in allow, f"non-allowlisted import-from: {node.module}"
            assert not (_SCRIPTS / f"{top}.py").exists(), f"project import: {top}"


def test_module_imports_in_isolation_without_side_effects():
    """R5 AC2: importing item_types in a FRESH interpreter re-executes the module
    (a same-process sys.modules diff would be vacuous — it is already loaded at
    collection time) and produces no side effects: clean exit, empty stdout/stderr."""
    code = "import sys; sys.path.insert(0, %r); import item_types" % str(_SCRIPTS)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "", repr(proc.stdout)
    assert proc.stderr == "", repr(proc.stderr)


# ===========================================================================
# T2 — parse_item_id
# ===========================================================================

def test_parse_canonical_id_returns_prefix_and_number():
    assert it.parse_item_id("CR12") == ("CR", 12)
    assert it.parse_item_id("F1") == ("F", 1)
    assert it.parse_item_id("D1") == ("D", 1)
    assert it.parse_item_id("CR1") == ("CR", 1)
    assert it.parse_item_id("TD1") == ("TD", 1)


@pytest.mark.parametrize("bad", ["CR01", "F001", "F0", "D00", "TD010"])
def test_parse_rejects_leading_zero_and_zero(bad):
    assert it.parse_item_id(bad) is None


@pytest.mark.parametrize("bad", ["CR１２", "F１", "D１２３"])  # full-width digits
def test_parse_rejects_non_ascii_digits(bad):
    assert it.parse_item_id(bad) is None


@pytest.mark.parametrize("bad", ["cr1", "f1", "Cr1", "td3", "Td3", "cR1"])
def test_parse_is_case_sensitive(bad):
    assert it.parse_item_id(bad) is None


@pytest.mark.parametrize("bad", ["X5", "CRX", "C1", "FF1", "CRCR5", "R1", "T1"])
def test_parse_rejects_unknown_and_near_miss_prefixes(bad):
    # "C1" must NOT parse as if `C` prefixed `CR`; "T1" must NOT parse as `TD`.
    assert it.parse_item_id(bad) is None


@pytest.mark.parametrize(
    "bad", ["", "CR", "F1a", "CR+12", "CR-12", "CR 12", " F1 ", "F1\n", "\nF1"]
)
def test_parse_rejects_wrong_shape(bad):
    assert it.parse_item_id(bad) is None


def test_parse_overlong_numeral_boundary():
    # Reject side: 4301 digits -> None, deterministically (F1's own length cap,
    # not the interpreter int<->str limit which is absent on 3.9.6). Never int()'d.
    over = "F" + "1" * (it._MAX_NUMBER_DIGITS + 1)
    assert it.parse_item_id(over) is None
    # Accept side: exactly _MAX_NUMBER_DIGITS (4300) digits parses (pins > vs >=).
    at_cap = "1" * it._MAX_NUMBER_DIGITS
    assert it.parse_item_id("F" + at_cap) == ("F", int(at_cap))


@pytest.mark.parametrize("bad", [None, 123, b"F1", 1.0, ["F1"]])
def test_parse_rejects_wrong_type_input(bad):
    # Never raises on wrong-type input — returns None.
    assert it.parse_item_id(bad) is None


def test_per_type_counters_are_independent():
    parsed = {it.parse_item_id(x) for x in ("F1", "D1", "CR1", "TD1")}
    assert len(parsed) == 4  # same number 1, four distinct pairs
    assert it.parse_item_id("F7") != it.parse_item_id("TD7")


# ===========================================================================
# T3 — format_item_id + bidirectional round-trip
# ===========================================================================

def test_format_canonical_pair_returns_id():
    assert it.format_item_id("CR", 12) == "CR12"
    assert it.format_item_id("F", 1) == "F1"


@pytest.mark.parametrize("p", _PREFIXES)
@pytest.mark.parametrize("n", [1, 2, 10, 99, 1234567890123456])
def test_round_trip_all_prefixes_and_representative_ids(p, n):
    s = it.format_item_id(p, n)
    assert s is not None, (p, n)
    assert it.parse_item_id(s) == (p, n)
    # parse-then-format on the canonical string reproduces it exactly
    assert it.format_item_id(*it.parse_item_id(s)) == s


@pytest.mark.parametrize("bad", ["X", "C", "cr", "f", "", "FF"])
def test_format_rejects_non_vocabulary_prefix(bad):
    assert it.format_item_id(bad, 1) is None


@pytest.mark.parametrize("bad", [0, -1, -100])
def test_format_rejects_non_positive_number(bad):
    assert it.format_item_id("F", bad) is None


@pytest.mark.parametrize(
    "prefix,number",
    [
        (None, 1), (1, 1), (b"F", 1),        # non-str prefix
        ("F", "1"), ("F", 1.0), ("F", None), # non-int number
        ("F", True),                          # bool is a subclass of int — rejected
    ],
)
def test_format_rejects_wrong_type_and_bool(prefix, number):
    assert it.format_item_id(prefix, number) is None


def test_format_overlong_value_boundary():
    # Reject side: >= _MAX_NUMBER_VALUE (a 4301-digit value) -> None, via a pure-int
    # compare (no str(huge_int)), deterministic on 3.9 and 3.12.
    assert it.format_item_id("F", it._MAX_NUMBER_VALUE) is None
    # Accept side: the largest in-domain value (4300 digits) formats and round-trips.
    largest = it._MAX_NUMBER_VALUE - 1
    s = it.format_item_id("F", largest)
    assert s is not None
    assert it.parse_item_id(s) == ("F", largest)
