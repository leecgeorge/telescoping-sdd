"""Tests for the shared master-feature contract extractor + hasher (CPD T4 / I9).

Covers `master_feature.extract_master_feature_contract` and
`master_feature.compute_master_contract_hash`:

  * basic extraction + stable hash;
  * the three block-boundary cases (next `### F<n>`, next `## `, EOF);
  * nested-sub-bullet folding (single-space join, exact folded text asserted);
  * exclusion of `**Implemented by:**`, the title line, and `**Component:**`;
  * whitespace stability and reorder stability (sorted element list);
  * one-word description change differs;
  * the FROZEN-literal-digest oracle over the shared `_FROZEN_PLAN_FIXTURE`
    (part a of the I9 single-producer invariant), which includes a WRAPPED
    top-level criterion (the not-folded path);
  * feature-block-not-found → None.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"
_TESTS = _SCRIPTS / "tests"

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import master_feature as mf  # noqa: E402
from _fixtures import _FROZEN_PLAN_FIXTURE  # noqa: E402

# The FROZEN literal digest for `_FROZEN_PLAN_FIXTURE` feature F7. Computed once
# from the reference implementation and hardcoded here; any normalization /
# serialization change in `master_feature` flips this and fails part (a) of the
# I9 single-producer oracle.
_FROZEN_F7_DIGEST = "a33028d56c6340ba40b8be4e9ab1d9506c17fe508bf3d980a467705eaa65dd72"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Small purpose-built fixtures
# ---------------------------------------------------------------------------

_BASIC_PLAN = """\
## Feature Breakdown

### F1: Login

- **Description:** Allow a user to authenticate with email and password.
- **Component:** Auth
- **Acceptance Criteria:**
  - A user with valid credentials receives a session token.
  - A user with invalid credentials is rejected.
"""


def test_contract_hash_extractor_basic():
    contract = mf.extract_master_feature_contract(_BASIC_PLAN, 1)
    assert contract is not None
    assert contract["description"] == (
        "Allow a user to authenticate with email and password."
    )
    assert contract["acceptance_criteria"] == [
        "A user with valid credentials receives a session token.",
        "A user with invalid credentials is rejected.",
    ]
    digest = mf.compute_master_contract_hash(_BASIC_PLAN, 1)
    assert digest is not None
    assert _HEX64.match(digest)
    # Stable across repeated calls.
    assert digest == mf.compute_master_contract_hash(_BASIC_PLAN, 1)


# ---------------------------------------------------------------------------
# Block boundary: next ### F<n>, next ## section, EOF
# ---------------------------------------------------------------------------

def test_extract_block_boundary_next_feature():
    plan = """\
## Features

### F1: First

- **Description:** The first feature.
- **Acceptance Criteria:**
  - First criterion.

### F2: Second

- **Description:** The second feature.
- **Acceptance Criteria:**
  - Second criterion.
"""
    contract = mf.extract_master_feature_contract(plan, 1)
    assert contract is not None
    assert contract["description"] == "The first feature."
    # The second feature's content must NOT bleed in.
    assert contract["acceptance_criteria"] == ["First criterion."]
    assert "second" not in contract["description"].lower()


def test_extract_block_boundary_section():
    plan = """\
## Features

### F1: First

- **Description:** The first feature.
- **Acceptance Criteria:**
  - First criterion.

## Cross-Feature Contracts

### CFC-1: something
- **Contract:** not part of F1.
"""
    contract = mf.extract_master_feature_contract(plan, 1)
    assert contract is not None
    assert contract["description"] == "The first feature."
    assert contract["acceptance_criteria"] == ["First criterion."]
    # The `## Cross-Feature Contracts` section bounds the block.
    assert "CFC" not in str(contract)


def test_extract_block_boundary_eof():
    plan = """\
## Features

### F1: Only

- **Description:** The only feature in the plan.
- **Acceptance Criteria:**
  - The single criterion.
"""
    contract = mf.extract_master_feature_contract(plan, 1)
    assert contract is not None
    assert contract["description"] == "The only feature in the plan."
    assert contract["acceptance_criteria"] == ["The single criterion."]


# ---------------------------------------------------------------------------
# Nested-bullet folding (single space) + wrapped continuation (not folded)
# ---------------------------------------------------------------------------

def test_extract_nested_bullet_folded():
    """1 parent + 2 children → exactly ONE element, single-space joined."""
    plan = """\
### F1: Sync

- **Description:** A feature with a nested AC.
- **Acceptance Criteria:**
  - The sync is resilient:
    - it resumes from the last checkpoint,
    - it never drops an acknowledged record.
"""
    contract = mf.extract_master_feature_contract(plan, 1)
    assert contract is not None
    # The parent + its two sub-bullets collapse to a SINGLE element with a
    # single-space join (deterministic separator per DM6 / [DEF-01]).
    assert contract["acceptance_criteria"] == [
        "The sync is resilient: it resumes from the last checkpoint, "
        "it never drops an acknowledged record."
    ]


# ---------------------------------------------------------------------------
# Exclusions: Implemented by, title line, Component
# ---------------------------------------------------------------------------

def test_contract_hash_excludes_implemented_by():
    without = """\
### F1: Sync

- **Description:** Sync the records.
- **Acceptance Criteria:**
  - Records arrive at the edge.
"""
    with_field = """\
### F1: Sync

- **Description:** Sync the records.
- **Implemented by:** vps-edge
- **Acceptance Criteria:**
  - Records arrive at the edge.
"""
    assert mf.compute_master_contract_hash(without, 1) == (
        mf.compute_master_contract_hash(with_field, 1)
    )


def test_contract_hash_excludes_title_and_component():
    base = """\
### F1: Original title

- **Description:** Sync the records.
- **Component:** Sync engine
- **Acceptance Criteria:**
  - Records arrive at the edge.
"""
    changed = """\
### F1: A completely different title

- **Description:** Sync the records.
- **Component:** A different component entirely
- **Acceptance Criteria:**
  - Records arrive at the edge.
"""
    assert mf.compute_master_contract_hash(base, 1) == (
        mf.compute_master_contract_hash(changed, 1)
    )


# ---------------------------------------------------------------------------
# Canonical layout: excluded fields BELOW the AC list, as bullets
#
# The "Master side" data model in cross-project-derivation.md writes
# `- **Implemented by:** <alias>` (and `- **Component:**`) as a BULLET that
# follows the `- **Acceptance Criteria:**` list. A bulleted field after the AC
# block must still be excluded — otherwise it folds into an AC element and an
# alias rename shifts the contract hash, producing false `contract-drift`
# (regression guard for the code-review #1 bug; the older exclusion tests above
# dodge it by placing the fields ABOVE the AC block).
# ---------------------------------------------------------------------------

def _canonical_after_ac(alias: str, component: str) -> str:
    return f"""\
### F7: Resident sync

- **Description:** Sync resident records to the edge cache.
- **Acceptance Criteria:**
  - GIVEN a resident is created WHEN the sync runs THEN the edge cache reflects it.
  - A withdrawn resident is purged on the next sync.
- **Implemented by:** {alias}
- **Component:** {component}
"""


def test_bulleted_excluded_fields_after_ac_not_folded():
    contract = mf.extract_master_feature_contract(
        _canonical_after_ac("vps-edge", "Sync engine"), 7
    )
    assert contract is not None
    # Exactly the two real AC bullets — neither excluded field leaked in.
    assert len(contract["acceptance_criteria"]) == 2
    for criterion in contract["acceptance_criteria"]:
        assert "Implemented by" not in criterion
        assert "Component" not in criterion


def test_alias_rename_after_ac_is_hash_neutral():
    # Renaming the derived alias (CPD-D4: hash-neutral) must not change the hash
    # even when the bulleted field sits below the AC list.
    base = mf.compute_master_contract_hash(_canonical_after_ac("vps-edge", "Sync engine"), 7)
    renamed = mf.compute_master_contract_hash(_canonical_after_ac("other-repo", "Sync engine"), 7)
    assert base is not None
    assert base == renamed


def test_excluded_field_position_is_hash_invariant():
    # The contract hash must not depend on whether the excluded fields sit above
    # or below the AC list — same Description + AC ⇒ same hash.
    below = _canonical_after_ac("vps-edge", "Sync engine")
    above = """\
### F7: Resident sync

- **Description:** Sync resident records to the edge cache.
- **Implemented by:** vps-edge
- **Component:** Sync engine
- **Acceptance Criteria:**
  - GIVEN a resident is created WHEN the sync runs THEN the edge cache reflects it.
  - A withdrawn resident is purged on the next sync.
"""
    assert mf.compute_master_contract_hash(below, 7) == (
        mf.compute_master_contract_hash(above, 7)
    )


# ---------------------------------------------------------------------------
# Whitespace stability + reorder stability
# ---------------------------------------------------------------------------

def test_contract_hash_whitespace_stable():
    tidy = """\
### F1: Sync

- **Description:** Sync the records.
- **Acceptance Criteria:**
  - Records arrive at the edge.
  - Withdrawn records are purged.
"""
    messy = """\
### F1: Sync

-   **Description:**    Sync   the    records.
- **Acceptance Criteria:**
  -    Records arrive at the edge.
  -  Withdrawn records are purged.
"""
    assert mf.compute_master_contract_hash(tidy, 1) == (
        mf.compute_master_contract_hash(messy, 1)
    )


def test_contract_hash_reorder_criteria_stable():
    forward = """\
### F1: Sync

- **Description:** Sync the records.
- **Acceptance Criteria:**
  - Alpha criterion.
  - Bravo criterion.
  - Charlie criterion.
"""
    reordered = """\
### F1: Sync

- **Description:** Sync the records.
- **Acceptance Criteria:**
  - Charlie criterion.
  - Alpha criterion.
  - Bravo criterion.
"""
    assert mf.compute_master_contract_hash(forward, 1) == (
        mf.compute_master_contract_hash(reordered, 1)
    )


# ---------------------------------------------------------------------------
# Sensitivity: one-word description change differs
# ---------------------------------------------------------------------------

def test_contract_hash_one_word_change():
    base = """\
### F1: Sync

- **Description:** Sync the records to the edge.
- **Acceptance Criteria:**
  - Records arrive at the edge.
"""
    changed = """\
### F1: Sync

- **Description:** Sync the records to the cache.
- **Acceptance Criteria:**
  - Records arrive at the edge.
"""
    assert mf.compute_master_contract_hash(base, 1) != (
        mf.compute_master_contract_hash(changed, 1)
    )


# ---------------------------------------------------------------------------
# Frozen-digest oracle (I9 part a) over the shared fixture
# ---------------------------------------------------------------------------

def test_master_contract_hash_frozen_digest():
    """Part (a) of the I9 single-producer oracle.

    `compute_master_contract_hash` over the SHARED `_FROZEN_PLAN_FIXTURE`
    (which includes a WRAPPED top-level criterion — exercising the not-folded
    path) must equal the FROZEN literal hex digest. Any normalization or
    serialization change is caught here.
    """
    digest = mf.compute_master_contract_hash(_FROZEN_PLAN_FIXTURE, 7)
    assert digest == _FROZEN_F7_DIGEST

    # Sanity: the fixture truly exercises both folding paths so the oracle is
    # not silently degenerate. F7 has exactly three AC elements: one wrapped
    # (multi-line, not folded) and one with nested sub-bullets (folded).
    contract = mf.extract_master_feature_contract(_FROZEN_PLAN_FIXTURE, 7)
    assert contract is not None
    assert len(contract["acceptance_criteria"]) == 3
    # The wrapped top-level criterion keeps an inter-line newline (not folded).
    assert any("\n" in c for c in contract["acceptance_criteria"])


# ---------------------------------------------------------------------------
# Feature block not found
# ---------------------------------------------------------------------------

def test_extract_feature_not_found_returns_none():
    assert mf.extract_master_feature_contract(_BASIC_PLAN, 42) is None
    assert mf.compute_master_contract_hash(_BASIC_PLAN, 42) is None
    # Empty input never raises.
    assert mf.extract_master_feature_contract("", 1) is None
    assert mf.compute_master_contract_hash("", 1) is None


# ---------------------------------------------------------------------------
# iter_feature_blocks — single-pass block enumeration (code-review #8)
# ---------------------------------------------------------------------------

def test_iter_feature_blocks_byte_identical_to_find_feature_block():
    """Each block from the single-pass enumerator matches `_find_feature_block`.

    This is the equivalence contract that lets `validate_blueprint._parse_implemented_by`
    swap its O(M·len) per-feature `_find_feature_block` loop for ONE pass: the
    block text for every feature must be the SAME bytes either way.
    """
    blocks = mf.iter_feature_blocks(_FROZEN_PLAN_FIXTURE)
    # The fixture has features F3, F7, F9 (a `## Cross-Feature Contracts` section
    # follows F9 and must bound it).
    assert [n for n, _ in blocks] == [3, 7, 9]
    for number, block in blocks:
        assert block == mf._find_feature_block(_FROZEN_PLAN_FIXTURE, number)
    # F9's block stops at the `## Cross-Feature Contracts` section, not EOF.
    f9_block = dict(blocks)[9]
    assert "Cross-Feature Contracts" not in f9_block


def test_iter_feature_blocks_empty_and_no_features():
    assert mf.iter_feature_blocks("") == []
    assert mf.iter_feature_blocks("# Plan\n\nNo features here.\n") == []


def test_iter_feature_blocks_reused_number_yields_both_in_order():
    """A reused `### F<n>` yields BOTH blocks in document order (first-wins is the
    consumer's concern, mirroring `_find_feature_block`'s first-match)."""
    plan = (
        "## Feature Breakdown\n\n"
        "### F1: first\n- **Description:** one\n\n"
        "### F1: second\n- **Description:** two\n"
    )
    blocks = mf.iter_feature_blocks(plan)
    assert [n for n, _ in blocks] == [1, 1]
    assert "one" in blocks[0][1] and "two" in blocks[1][1]
    # The first block matches `_find_feature_block` (which returns the first).
    assert blocks[0][1] == mf._find_feature_block(plan, 1)
