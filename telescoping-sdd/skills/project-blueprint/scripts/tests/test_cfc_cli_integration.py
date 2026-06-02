"""CLI integration tests for the CFC machinery.

Closes review items P1-17 (no CLI / subprocess test) and P1-18 (no realistic
multi-CFC fixture). Exercises `validate_blueprint.py` end-to-end via
subprocess against a soc_coach-shape PLAN.md with three Cross-Feature
Contracts: lock-order, single-writer, advisory-lock-registry. The fixture
mirrors the originating evidence in `documentation/CFC.md § Evidence`.

These tests are slower than unit-level CFC tests (subprocess + full validator
init) but catch regressions in argparse, `main()`, exit codes, and output
formatting that direct function calls miss.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[5]
_VALIDATOR = (
    _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts"
    / "validate_blueprint.py"
)


def _load_validate_blueprint():
    """Import validate_blueprint to call helpers like compute_content_hash from tests."""
    scripts = _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    if "validate_blueprint" in sys.modules:
        return importlib.reload(sys.modules["validate_blueprint"])
    return importlib.import_module("validate_blueprint")


vb = _load_validate_blueprint()


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_VALIDATOR), *args],
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Reusable soc_coach-shape 3-CFC fixture (P1-18)
# ---------------------------------------------------------------------------
#
# The fixture mirrors the originating evidence: F11/F13/F15/F17/F19 lock
# order, F2/F20/F29/F33/F34/F35 OperatorAuditLogWriter single-writer,
# F2/F33 + future-users advisory-lock-key registry. F36 owns enforcement
# on CFC-1 (per soc_coach Evidence table line 40).

SOC_COACH_PLAN = """# Implementation Plan: soc_coach

**Scope:** `blueprint/SCOPE.md`
**Architecture:** `blueprint/ARCHITECTURE.md`

## Feature Breakdown

### F2: Audit-log deliverer

- **Description:** First writer to the audit log
- **Component:** AuditLogService
- **Acceptance Criteria:**
  - Routes all writes through OperatorAuditLogWriter
  - Acquires advisory lock keys from the registry

### F11: Lock-order phase-1 feature

- **Description:** First feature subject to canonical lock order
- **Component:** TransactionService
- **Acceptance Criteria:**
  - Acquires locks in canonical order A->B->C->D->E->F

### F13: Lock-order phase-2 feature

- **Description:** Second lock-order participant
- **Component:** TransactionService
- **Acceptance Criteria:**
  - Acquires locks in canonical order A->B->C->D->E->F

### F33: Advisory-lock secondary user

- **Description:** Second writer using advisory locks
- **Component:** AuditLogService
- **Acceptance Criteria:**
  - Uses unique advisory-lock-key registry entry

### F36: Cross-cutting enforcement owner

- **Description:** Owns ArchUnit rules verifying cross-feature contracts
- **Component:** ArchUnitCheck
- **Acceptance Criteria:**
  - Ships LockOrderCheck ArchUnit rule
  - Ships NoDirectAuditLogWrite ArchUnit rule

## MVP Definition

**MVP includes:** F2, F11, F36

| Phase | Features | Goal |
|-------|----------|------|
| MVP | F2, F11, F36 | Foundation + first contract enforcement |
| Phase 2 | F13, F33 | Expand lock-order + advisory-lock usage |

## Feature Dependencies

```
F2 --> F33
F11 --> F13
F36 (independent enforcement owner)
```

| Feature | Depends On | Reason |
|---------|-----------|--------|
| F2 | None | Foundation writer |
| F11 | None | Foundation lock-acquirer |
| F13 | F11 | Same lock-order family |
| F33 | F2 | Same advisory-lock family |
| F36 | None | Independent enforcement owner |

## Implementation Order

| Order | Feature | Rationale |
|-------|---------|-----------|
| 1 | F36: Enforcement owner | Lands ArchUnit rules others depend on |
| 2 | F2: Audit-log deliverer | First writer |
| 3 | F11: Lock-order phase-1 | First lock-acquirer |
| 4 | F13: Lock-order phase-2 | Builds on F11 |
| 5 | F33: Advisory-lock secondary | Builds on F2 |

## Milestones

### Milestone 1: Foundation

- [ ] F36: Enforcement owner
- [ ] F2: Audit-log deliverer
- **Deliverable:** Enforcement rules in place; first writer goes through them.

### Milestone 2: Lock-order family

- [ ] F11: Lock-order phase-1
- [ ] F13: Lock-order phase-2
- **Deliverable:** Lock-order family complete.

### Milestone 3: Advisory-lock family

- [ ] F33: Advisory-lock secondary
- **Deliverable:** Advisory-lock-key usage hardened.

## Open Questions

- [x] Q1: Lock order canonical sequence? **Resolution:** A->B->C->D->E->F per F11 SDD pass 23.
- [x] Q2: Single-writer owner? **Resolution:** F36 owns the ArchUnit rule; F2 ships the writer class.

## Cross-Feature Contracts

### CFC-1: Six-table lock order

- **Participating features:** F11, F13
- **Contract:** Database locks must be acquired in canonical order A->B->C->D->E->F to prevent deadlock. F11 ships in M2 while later lock-order participants ship in M3+, so the order must be committed at PLAN level upfront — no single feature's SDD cycle can see the full set.
- **Per-feature AC:** WHEN this feature acquires database locks, THEN it acquires them in canonical order A->B->C->D->E->F.
- **Enforcement:** F36 owns the ArchUnit rule LockOrderCheck that verifies all transactional code respects the canonical order. The rule runs in CI on every PR.

### CFC-2: OperatorAuditLogWriter single-writer

- **Participating features:** F2, F33
- **Contract:** All writes to the operator audit log must route through OperatorAuditLogWriter. F2 ships the writer class; F33 (and all future audit-log writers) must use it. Direct writes bypass the single-writer guarantee.
- **Per-feature AC:** WHEN this feature writes operator audit entries, THEN it goes through OperatorAuditLogWriter (no direct table inserts).
- **Enforcement:** F36 owns the ArchUnit rule NoDirectAuditLogWrite that bans direct INSERT calls against the audit-log table outside OperatorAuditLogWriter.

### CFC-3: Advisory-lock-key registry

- **Participating features:** F2, F33
- **Contract:** Every caller of pg_advisory_xact_lock(hashtext(...)) must register its key string in the shared registry. hashtext is 32-bit, so two independent SDD-spec authors picking similar string keys cannot detect collisions without a registry. Collisions surface as random deadlocks under load.
- **Per-feature AC:** WHEN this feature uses pg_advisory_xact_lock, THEN it registers its key string in the shared registry before use.
- **Enforcement:** F2 owns the registry module and its initial entries. New entries are reviewed at PR time; no ArchUnit rule (the check is documentation-driven).

## Panel Review

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|
| 1 | 2026-05-17 | 0 | 0 | 0 | 0 | 0 | converged (0 HIGH) |

### Sealed dispositions

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [ ] Approved to proceed to feature development
- **Content Hash:** `pending`
"""


def _build_blueprint(tmp_path: Path) -> Path:
    """Lay out blueprint/ with stamped SCOPE.md + ARCHITECTURE.md + the soc_coach PLAN.md."""
    blueprint = tmp_path / "blueprint"
    blueprint.mkdir()

    # Pre-approved SCOPE + ARCHITECTURE — the validator requires their hashes
    # to validate before approving PLAN. Use minimal valid content.
    scope_body = (
        "# Project Scope\n\n"
        "## Problem Statement\n\nWe need to ship soc_coach with cross-feature contracts.\n\n"
        "## Target Users\n\nDevelopers maintaining the soc_coach codebase.\n\n"
        "## Goals\n\n- [ ] Ship CFCs cleanly\n- [ ] Validate at PLAN approval\n\n"
        "## Non-Goals\n\n- Multi-tenant support\n\n"
        "## Constraints\n\n- Postgres backend; advisory locks via hashtext.\n\n"
        "## Success Criteria\n\n- [ ] CFCs survive PR review\n\n"
        "## Panel Review\n\n### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "| 1 | 2026-05-17 | 0 | 0 | 0 | 0 | 0 | converged (0 HIGH) |\n\n"
        "### Sealed dispositions\n\n### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n\n"
        "## Approval\n\n- [x] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )
    scope_hash = vb.compute_content_hash(scope_body)
    (blueprint / "SCOPE.md").write_text(
        scope_body.replace("`pending`", f"`{scope_hash}`"), encoding="utf-8"
    )

    arch_body = (
        "# Architecture\n\n"
        "## System Overview\n\nTransaction-heavy service with audit log.\n\n"
        "## Components\n\n### TransactionService\n\nHandles transactional writes.\n\n"
        "### AuditLogService\n\nOwns the operator audit log.\n\n"
        "### ArchUnitCheck\n\nEnforces cross-feature invariants.\n\n"
        "## Component Interactions\n\nTransactionService writes via AuditLogService.\n\n"
        "## Technology Choices\n\nPostgres + advisory locks.\n\n"
        "## Data Architecture\n\nSingle audit-log table; lock-key registry table.\n\n"
        "## External Dependencies\n\nPostgres 14+.\n\n"
        "## Risks\n\nAdvisory-lock-key collisions under high concurrency.\n\n"
        "## Panel Review\n\n### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "| 1 | 2026-05-17 | 0 | 0 | 0 | 0 | 0 | converged (0 HIGH) |\n\n"
        "### Sealed dispositions\n\n### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n\n"
        "## Approval\n\n- [x] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )
    arch_hash = vb.compute_content_hash(arch_body)
    (blueprint / "ARCHITECTURE.md").write_text(
        arch_body.replace("`pending`", f"`{arch_hash}`"), encoding="utf-8"
    )

    (blueprint / "PLAN.md").write_text(SOC_COACH_PLAN, encoding="utf-8")
    return blueprint


# ---------------------------------------------------------------------------
# CLI integration tests (P1-17)
# ---------------------------------------------------------------------------

def test_cli_validate_plan_against_soc_coach_fixture(tmp_path):
    """Run `validate_blueprint.py blueprint/` against the soc_coach 3-CFC fixture.

    Exit code must be 0 (or 0-with-warnings; the fixture is structurally valid
    but the per-CFC coverage walk emits warnings since no specs/ exist yet).
    Stdout must mention the three CFCs and the per-CFC content hash slots.
    """
    blueprint = _build_blueprint(tmp_path)
    proc = _run_cli(str(blueprint), "--phase", "plan")
    # Coverage walk reports `unbound` for each CFC (no specs yet), which is
    # WARN-level. Validator exits 0 with warnings; CFC structural checks pass.
    assert proc.returncode == 0, (
        f"validate failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    # All three CFCs were parsed and validated.
    assert "CFC-1" in proc.stdout
    assert "CFC-2" in proc.stdout
    assert "CFC-3" in proc.stdout
    # Owner-silent WARN does NOT fire — Enforcement prose names F36 (CFC-1, CFC-2)
    # and F2 (CFC-3).
    assert "Enforcement names owning feature" not in proc.stdout


def test_cli_approve_plan_writes_cfc_hash_block(tmp_path):
    """`--approve plan` must write a per-CFC hash sub-block inside `## Approval`."""
    blueprint = _build_blueprint(tmp_path)
    proc = _run_cli(str(blueprint), "--approve", "plan")
    assert proc.returncode == 0, (
        f"approve failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    plan_after = (blueprint / "PLAN.md").read_text(encoding="utf-8")
    # The hash sub-block landed inside ## Approval with three entries.
    assert "- **CFC Content Hashes:**" in plan_after
    assert "CFC-1: `" in plan_after
    assert "CFC-2: `" in plan_after
    assert "CFC-3: `" in plan_after
    # The Approval section's main checkbox flipped.
    approval_section = plan_after[plan_after.index("## Approval"):]
    assert "[x] Approved to proceed" in approval_section


def test_cli_approve_plan_trims_trajectory_to_15(tmp_path):
    """`--approve plan` must trim the `### Trajectory` table to the latest 15
    data rows, replacing older rows with a single elided summary row at the top.

    Wiring test for the on-approval trim feature — the trim helper itself is
    unit-tested in `test_blueprint_common.py`; this test proves
    `approve_document` actually calls it through the CLI path.
    """
    blueprint = _build_blueprint(tmp_path)

    # Inflate the SOC_COACH_PLAN trajectory to 20 data rows. The fixture ships
    # with a single trajectory row; replace it with 20 so the trim has to act.
    plan_before = (blueprint / "PLAN.md").read_text(encoding="utf-8")
    fake_rows = "\n".join(
        f"| {i + 1} | 2026-05-{(i % 28) + 1:02d} | 0 | 0 | 1 | 0 | 0 | normal |"
        for i in range(20)
    )
    plan_before = plan_before.replace(
        "| 1 | 2026-05-17 | 0 | 0 | 0 | 0 | 0 | converged (0 HIGH) |",
        fake_rows,
    )
    (blueprint / "PLAN.md").write_text(plan_before, encoding="utf-8")

    proc = _run_cli(str(blueprint), "--approve", "plan")
    assert proc.returncode == 0, (
        f"approve failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    plan_after = (blueprint / "PLAN.md").read_text(encoding="utf-8")

    # 20 → 15 kept + 1 elided summary row. The 5 oldest rows must be absent.
    assert "5 earlier passes elided" in plan_after
    assert "| 1 | 2026-05-01 | 0 | 0 | 1 | 0 | 0 | normal |" not in plan_after
    assert "| 5 | 2026-05-05 | 0 | 0 | 1 | 0 | 0 | normal |" not in plan_after
    # The 15 latest rows (passes 6-20) must remain.
    assert "| 6 | 2026-05-06 | 0 | 0 | 1 | 0 | 0 | normal |" in plan_after
    assert "| 20 | 2026-05-20 | 0 | 0 | 1 | 0 | 0 | normal |" in plan_after
    # The elided row appears before the kept rows in the trajectory section.
    elided_pos = plan_after.find("earlier passes elided")
    kept_pos = plan_after.find("| 6 | 2026-05-06 |")
    assert 0 < elided_pos < kept_pos


def test_cli_approve_plan_gates_on_validation(tmp_path):
    """Decision E regression at the CLI level: `--approve plan` refuses to stamp
    an empty/invalid PLAN.md and exits non-zero."""
    blueprint = tmp_path / "blueprint"
    blueprint.mkdir()
    (blueprint / "SCOPE.md").write_text("# scope\n## Approval\n- [x] Approved to proceed to next phase\n", encoding="utf-8")
    (blueprint / "ARCHITECTURE.md").write_text("# arch\n## Approval\n- [x] Approved to proceed to next phase\n", encoding="utf-8")
    # Empty PLAN.md — missing every required section.
    (blueprint / "PLAN.md").write_text("", encoding="utf-8")

    proc = _run_cli(str(blueprint), "--approve", "plan")
    assert proc.returncode != 0, (
        f"empty PLAN.md was approved without --force: stdout={proc.stdout!r}"
    )
    assert "Refusing to approve" in proc.stdout or "FAIL" in proc.stdout


def test_cli_orphaned_stale_content_round_trip(tmp_path):
    """End-to-end round-trip: approve, edit a CFC, re-validate, see orphan-stale-content.

    1. Build blueprint with soc_coach PLAN + a single F11 spec.md carrying [CFC-1].
    2. Approve PLAN — writes per-CFC hashes including CFC-1.
    3. Edit CFC-1's Per-feature AC text.
    4. Re-run validate — emits `orphaned-stale-content` for F11/spec.md against CFC-1.
    """
    blueprint = _build_blueprint(tmp_path)

    # Build F11's bound spec.md carrying [CFC-1] on a THEN line.
    spec_body = (
        "R1\n\n**Acceptance Criteria:**\n\n"
        "- GIVEN F11 acquires locks\n"
        "  WHEN entering a transaction\n"
        "  THEN it acquires locks in canonical order A->B->C->D->E->F [CFC-1]\n"
    )
    spec_md = (
        "# Feature: Lock-order phase-1\n\n"
        "**PLAN feature identifier:** `F11`\n\n"
        "## Objective\n\nLock-order phase-1.\n\n"
        f"## Requirements\n\n{spec_body}\n\n"
        "## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    spec_hash = vb.compute_content_hash(spec_md)
    spec_dir = tmp_path / "specs" / "F11-lock-order"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(
        spec_md.replace("`pending`", f"`{spec_hash}`"), encoding="utf-8"
    )

    # Approve the PLAN — writes CFC-1's content hash into the Approval block.
    proc = _run_cli(str(blueprint), "--approve", "plan")
    assert proc.returncode == 0, f"approve failed: {proc.stdout!r} {proc.stderr!r}"

    # Edit CFC-1's Per-feature AC text in PLAN.md.
    plan_after_approval = (blueprint / "PLAN.md").read_text(encoding="utf-8")
    plan_drifted = plan_after_approval.replace(
        "WHEN this feature acquires database locks, THEN it acquires them in canonical order A->B->C->D->E->F.",
        "WHEN this feature acquires database locks, THEN it acquires them in canonical order A->B->D->C->E->F.",  # D and C swapped
    )
    assert plan_drifted != plan_after_approval, "Drift edit did not change PLAN.md"
    (blueprint / "PLAN.md").write_text(plan_drifted, encoding="utf-8")

    # Re-run validate. The validator's orphan-tag scan must surface the drift.
    proc = _run_cli(str(blueprint), "--phase", "plan")
    # The drifted PLAN is no longer hash-coherent with its prior approval —
    # the document-level hash check will FAIL too. We're checking that the
    # orphan-tag scan ALSO emits the stale-content row before the document
    # hash check stops the validator.
    assert "orphaned-stale-content" in proc.stdout, (
        f"orphaned-stale-content not surfaced: stdout={proc.stdout!r}"
    )
    assert "F11" in proc.stdout
    assert "CFC-1" in proc.stdout


# ---------------------------------------------------------------------------
# soc_coach fixture self-validation (P1-18)
# ---------------------------------------------------------------------------

def test_soc_coach_fixture_parses_three_cfcs():
    """Direct-function exercise of the 3-CFC fixture — confirms parser handles
    multi-CFC PLANs with overlapping Participating features."""
    section = vb.extract_cfc_section(SOC_COACH_PLAN)
    assert section is not None
    entries = vb.parse_cfc_entries(section[2])
    assert [e.number for e in entries] == [1, 2, 3]
    # CFC-1: F11, F13 in Participating; F36 named in Enforcement.
    assert sorted(entries[0].participating_features()) == [11, 13]
    assert 36 in entries[0].enforcement_owners()
    # CFC-2: F2, F33 in Participating; F36 named in Enforcement.
    assert sorted(entries[1].participating_features()) == [2, 33]
    assert 36 in entries[1].enforcement_owners()
    # CFC-3: F2, F33 in Participating; F2 named as registry owner (no ArchUnit).
    assert sorted(entries[2].participating_features()) == [2, 33]
    assert 2 in entries[2].enforcement_owners()


def test_soc_coach_fixture_per_cfc_hashes_are_distinct():
    """Each CFC has a distinct structured content hash — drift on any CFC is detectable independently."""
    section = vb.extract_cfc_section(SOC_COACH_PLAN)
    entries = vb.parse_cfc_entries(section[2])
    hashes = [e.structured_content_hash() for e in entries]
    assert len(set(hashes)) == 3, "Per-CFC hashes collided"


def test_soc_coach_fixture_overlapping_participants_classify_correctly():
    """F2 appears in both CFC-2 and CFC-3 Participating features. F36 owns
    enforcement in both CFC-1 and CFC-2. Confirm the parser does not collapse
    or de-duplicate cross-CFC."""
    section = vb.extract_cfc_section(SOC_COACH_PLAN)
    entries = vb.parse_cfc_entries(section[2])
    cfc2 = next(e for e in entries if e.number == 2)
    cfc3 = next(e for e in entries if e.number == 3)
    assert 2 in cfc2.participating_features()
    assert 2 in cfc3.participating_features()
    # F36 is named in both CFC-1 and CFC-2's Enforcement; check both retain it.
    cfc1 = next(e for e in entries if e.number == 1)
    assert 36 in cfc1.enforcement_owners()
    assert 36 in cfc2.enforcement_owners()
