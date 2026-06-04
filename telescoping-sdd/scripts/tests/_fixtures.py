"""Shared test fixtures for the Cross-Project Derivation (CPD) test suite.

`_FROZEN_PLAN_FIXTURE` is a small but realistic ``PLAN.md`` text used by the
two-part single-producer frozen-digest oracle (design I9):

  * T4 ``test_master_contract_hash_frozen_digest`` (part a) hashes feature F7 of
    this fixture and asserts it equals a FROZEN literal hex digest — so any
    normalization or serialization change in ``master_feature`` is caught.
  * T12c ``test_master_contract_hash_single_producer_cross_boundary`` (part b)
    reuses THE SAME constant so the cross-boundary comparison can never silently
    diverge from the digest the frozen test pins.

It MUST stay a single shared constant (not two hand-built copies) so a change to
the fixture text moves both oracles together.

Feature F7's Acceptance Criteria deliberately exercise BOTH AC-folding paths
required by design ``[DEF-01]`` / DM6:

  * a TOP-LEVEL criterion whose text WRAPS onto a continuation line — the
    not-folded path (the continuation line keeps its own `\\n`, passed to
    ``normalize_for_hash`` as-is);
  * a TOP-LEVEL criterion with a NESTED sub-bullet — the folded path (the
    sub-bullet is joined to its parent with a single space).
"""
from __future__ import annotations

_FROZEN_PLAN_FIXTURE = """\
# Implementation Plan: Residents Portal

**Scope:** `blueprint/SCOPE.md`
**Architecture:** `blueprint/ARCHITECTURE.md`

## Feature Breakdown

### F3: Tenant directory

- **Description:** Maintain the canonical list of residents and their units.
- **Component:** Directory service
- **Acceptance Criteria:**
  - A resident can be created with a name and a unit number.
  - A resident can be soft-deleted without losing audit history.

### F7: Resident sync

- **Description:** Synchronize resident records to the edge cache so the on-prem reader can authorize entry while the WAN link is down.
- **Component:** Sync engine
- **Implemented by:** vps-edge
- **Acceptance Criteria:**
  - GIVEN a resident is created in the directory WHEN the sync runs THEN the
    edge cache reflects the new resident within one sync interval.
  - The sync is incremental and resilient to partial failures:
    - it resumes from the last acknowledged checkpoint after a crash,
    - it never drops a record already acknowledged downstream.
  - A withdrawn resident is purged from the edge cache on the next sync.

### F9: Audit log

- **Description:** Record every directory mutation for compliance review.
- **Component:** Audit service
- **Acceptance Criteria:**
  - Every create, update, and delete is recorded with an actor and a timestamp.

## Cross-Feature Contracts

(none)
"""
