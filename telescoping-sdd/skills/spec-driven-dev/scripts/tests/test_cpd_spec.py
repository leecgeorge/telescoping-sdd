"""Tests for the Cross-Project Derivation (CPD) checks in validate_spec.py.

Covers tasks T5–T8:
  * T5 — the `"derived"` branch in `check_dir_identifier` (I4): the derived-gate
    PASS plus each `derived-provenance-mismatch` reason, and the malformed
    short-circuit.
  * T6 — `_check_cpd_fields` precedence ladder (I5): `derived-fields-on-non-derived-dir`,
    `unbound` accepted, `master-hash-malformed`, `derived-fields-incomplete`,
    both-fields-absent no-FAIL, and the integrated exactly-one-FAIL count
    (`test_derived_both_malformed_and_mismatched_one_fail`).
  * T7 — `_validate_ucr_stanza` (I6): valid / duplicate / bad-status /
    missing-field, and coexistence with `## Accepted Divergences`.
  * T8 — the derived-spec exemption in `validate_cfc_consumer` (I7): a derived
    spec in a repo WITH a local PLAN + active CFC section + stale `[CFC-N]` tags
    has BOTH WARNs suppressed; a non-derived `n/a` spec in the same repo still
    warns.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _load_validate_spec():
    scripts_dir = Path(__file__).resolve().parents[1]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    if "validate_spec" in sys.modules:
        return importlib.reload(sys.modules["validate_spec"])
    return importlib.import_module("validate_spec")


vs = _load_validate_spec()


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _spec_md(
    *,
    identifier: str = "n/a",
    derived_from: str | None = "residents:F7",
    master_hash: str | None = "unbound",
    extra_sections: str = "",
    requirements_body: str = "R1\n\n**Acceptance Criteria:**\n\n- GIVEN x\n  WHEN y\n  THEN z\n",
) -> str:
    """Build a structurally complete spec.md with the required sections plus the
    optional CPD provenance fields and any extra sections (e.g. a UCR stanza).

    `derived_from` / `master_hash` of None omit that line entirely.
    """
    cpd_lines = ""
    if derived_from is not None:
        cpd_lines += f"**Derived from:** `{derived_from}`\n"
    if master_hash is not None:
        cpd_lines += f"**Master contract hash:** `{master_hash}`\n"
    full = (
        f"# Feature: T\n\n"
        f"**PLAN feature identifier:** `{identifier}`\n"
        f"{cpd_lines}\n"
        f"## Objective\n\nx\n\n"
        f"## Requirements\n\n{requirements_body}\n\n"
        f"## Project Structure\n\nx\n\n"
        f"## Boundaries\n\nx\n\n"
        f"## Success Criteria\n\n- [ ] done\n\n"
        f"## Panel Review\n\n"
        f"### Trajectory\n\n"
        f"| Pass | Date | Notes |\n|---|---|---|\n"
        f"| 1 | 2026-06-03 | clean |\n\n"
        f"{extra_sections}"
        f"## Approval\n\n- [x] Approved\n- **Content Hash:** `pending`\n"
    )
    h = vs.compute_content_hash(full)
    return full.replace("`pending`", f"`{h}`")


def _make_spec_dir(tmp_path: Path, dirname: str, spec_content: str) -> Path:
    spec_dir = tmp_path / "specs" / dirname
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(spec_content, encoding="utf-8")
    return spec_dir


def _fails(result) -> list[tuple[str, str, str]]:
    return [c for c in result.checks if c[1] == "FAIL"]


def _warns(result) -> list[tuple[str, str, str]]:
    return [c for c in result.checks if c[1] == "WARN"]


def _has_code(checks, code: str) -> bool:
    return any(c[0] == code for c in checks)


# ===========================================================================
# T5 — derived branch in check_dir_identifier (I4)
# ===========================================================================

def test_check_dir_identifier_derived_pass(tmp_path: Path):
    """A consistent derived spec passes the dir<->identifier cross-check."""
    spec = _spec_md(identifier="n/a", derived_from="residents:F7")
    spec_dir = _make_spec_dir(tmp_path, "residents--F7-resident-sync", spec)
    result = vs.check_dir_identifier(spec_dir, spec_content=spec)
    assert result.passed
    assert _fails(result) == []


def test_check_dir_identifier_derived_project_mismatch(tmp_path: Path):
    spec = _spec_md(identifier="n/a", derived_from="other-project:F7")
    spec_dir = _make_spec_dir(tmp_path, "residents--F7-resident-sync", spec)
    result = vs.check_dir_identifier(spec_dir, spec_content=spec)
    fails = _fails(result)
    assert _has_code(fails, "derived-provenance-mismatch")
    msg = fails[0][2]
    assert "residents" in msg and "other-project" in msg


def test_check_dir_identifier_derived_number_mismatch(tmp_path: Path):
    spec = _spec_md(identifier="n/a", derived_from="residents:F8")
    spec_dir = _make_spec_dir(tmp_path, "residents--F7-resident-sync", spec)
    result = vs.check_dir_identifier(spec_dir, spec_content=spec)
    fails = _fails(result)
    assert _has_code(fails, "derived-provenance-mismatch")
    msg = fails[0][2]
    assert "F7" in msg and "F8" in msg


def test_check_dir_identifier_derived_missing_derived_from(tmp_path: Path):
    spec = _spec_md(identifier="n/a", derived_from=None, master_hash=None)
    spec_dir = _make_spec_dir(tmp_path, "residents--F7-resident-sync", spec)
    result = vs.check_dir_identifier(spec_dir, spec_content=spec)
    fails = _fails(result)
    assert _has_code(fails, "derived-provenance-mismatch")
    assert "missing" in fails[0][2].lower()


def test_check_dir_identifier_derived_non_na_identifier(tmp_path: Path):
    spec = _spec_md(identifier="F7", derived_from="residents:F7")
    spec_dir = _make_spec_dir(tmp_path, "residents--F7-resident-sync", spec)
    result = vs.check_dir_identifier(spec_dir, spec_content=spec)
    fails = _fails(result)
    assert _has_code(fails, "derived-provenance-mismatch")
    assert "n/a" in fails[0][2]


def test_check_dir_identifier_derived_malformed_short_circuits(tmp_path: Path):
    """A malformed `Derived from` value produces the well-formedness FAIL (owned
    by `_check_cpd_fields`), NOT a mismatch FAIL — `check_dir_identifier`'s
    derived branch short-circuits without a second FAIL."""
    spec = _spec_md(identifier="n/a", derived_from="not a qualified id")
    spec_dir = _make_spec_dir(tmp_path, "residents--F7-resident-sync", spec)
    # check_dir_identifier alone: derived branch short-circuits, NO mismatch FAIL.
    result = vs.check_dir_identifier(spec_dir, spec_content=spec)
    assert not _has_code(_fails(result), "derived-provenance-mismatch")
    # Full validate_spec path: the well-formedness FAIL is emitted (by _check_cpd_fields).
    full = vs.validate_spec(spec_dir)
    assert _has_code(_fails(full), "derived-from-malformed")


# ===========================================================================
# T6 — _check_cpd_fields precedence ladder (I5)
# ===========================================================================

def test_derived_fields_on_non_derived_dir(tmp_path: Path):
    """A CPD field on a bound (non-derived) directory FAILs with
    `derived-fields-on-non-derived-dir`."""
    spec = _spec_md(identifier="F3", derived_from="residents:F3", master_hash="unbound")
    spec_dir = _make_spec_dir(tmp_path, "F3-foo", spec)
    result = vs.ValidationResult()
    vs._check_cpd_fields(spec_dir, spec, result)
    assert _has_code(_fails(result), "derived-fields-on-non-derived-dir")
    # ... and on a standalone directory.
    spec2 = _spec_md(identifier="n/a", derived_from="residents:F3", master_hash="unbound")
    spec_dir2 = _make_spec_dir(tmp_path, "cli-notes-app", spec2)
    result2 = vs.ValidationResult()
    vs._check_cpd_fields(spec_dir2, spec2, result2)
    assert _has_code(_fails(result2), "derived-fields-on-non-derived-dir")


def test_master_hash_unbound_accepted(tmp_path: Path):
    """The `unbound` bootstrap sentinel passes structural validation."""
    spec = _spec_md(identifier="n/a", derived_from="residents:F7", master_hash="unbound")
    spec_dir = _make_spec_dir(tmp_path, "residents--F7-resident-sync", spec)
    result = vs.ValidationResult()
    vs._check_cpd_fields(spec_dir, spec, result)
    assert _fails(result) == []


def test_master_hash_malformed_rejected(tmp_path: Path):
    """63 hex chars, uppercase, or non-hex each FAIL `master-hash-malformed`."""
    sixty_three = "a" * 63
    uppercase = "A" * 64
    non_hex = "g" * 64
    for bad in (sixty_three, uppercase, non_hex):
        spec = _spec_md(identifier="n/a", derived_from="residents:F7", master_hash=bad)
        spec_dir = _make_spec_dir(tmp_path, "residents--F7-resident-sync", spec)
        result = vs.ValidationResult()
        vs._check_cpd_fields(spec_dir, spec, result)
        assert _has_code(_fails(result), "master-hash-malformed"), bad


def test_co_occurrence_fail_one_missing(tmp_path: Path):
    """Exactly one CPD field present FAILs `derived-fields-incomplete`."""
    # Derived from present, master hash absent.
    spec = _spec_md(identifier="n/a", derived_from="residents:F7", master_hash=None)
    spec_dir = _make_spec_dir(tmp_path, "residents--F7-resident-sync", spec)
    result = vs.ValidationResult()
    vs._check_cpd_fields(spec_dir, spec, result)
    assert _has_code(_fails(result), "derived-fields-incomplete")
    # Master hash present, derived from absent.
    spec2 = _spec_md(identifier="n/a", derived_from=None, master_hash="unbound")
    spec_dir2 = _make_spec_dir(tmp_path, "residents--F7-resident-sync", spec2)
    result2 = vs.ValidationResult()
    vs._check_cpd_fields(spec_dir2, spec2, result2)
    assert _has_code(_fails(result2), "derived-fields-incomplete")


def test_derived_both_malformed_and_mismatched_one_fail(tmp_path: Path):
    """A `Derived from` value that is both malformed AND mismatched vs the
    directory yields EXACTLY ONE FAIL through the full validate_spec() path."""
    # Malformed value that is also "wrong" relative to the directory.
    spec = _spec_md(identifier="n/a", derived_from="BAD::F8", master_hash="unbound")
    spec_dir = _make_spec_dir(tmp_path, "residents--F7-resident-sync", spec)
    result = vs.validate_spec(spec_dir)
    fails = _fails(result)
    cpd_fails = [
        c for c in fails
        if c[0] in ("derived-from-malformed", "derived-provenance-mismatch")
    ]
    assert len(cpd_fails) == 1, cpd_fails
    assert cpd_fails[0][0] == "derived-from-malformed"


def test_cpd_fields_absent_on_non_derived_no_fail(tmp_path: Path):
    """A non-derived spec with NEITHER CPD field emits no CPD FAIL."""
    spec = _spec_md(identifier="n/a", derived_from=None, master_hash=None)
    spec_dir = _make_spec_dir(tmp_path, "cli-notes-app", spec)
    result = vs.ValidationResult()
    vs._check_cpd_fields(spec_dir, spec, result)
    assert _fails(result) == []


# ===========================================================================
# T7 — _validate_ucr_stanza (I6)
# ===========================================================================

_VALID_UCR = (
    "## Upstream Change Requests\n\n"
    "### UCR-1\n\n"
    "- **Target:** `residents:F7`\n"
    "- **Status:** open\n"
    "- **Proposed change:** Tighten the sync window.\n"
    "- **Rationale:** Edge nodes drift.\n\n"
)


def test_ucr_stanza_valid_accepted(tmp_path: Path):
    """A well-formed UCR stanza emits no FAIL."""
    result = vs.ValidationResult()
    vs._validate_ucr_stanza(_VALID_UCR, result)
    assert _fails(result) == []


def test_ucr_stanza_duplicate_id_fail(tmp_path: Path):
    dup = _VALID_UCR + (
        "### UCR-1\n\n"
        "- **Target:** `residents:F7`\n"
        "- **Status:** applied\n"
        "- **Proposed change:** Again.\n"
        "- **Rationale:** Repeat.\n\n"
    )
    result = vs.ValidationResult()
    vs._validate_ucr_stanza(dup, result)
    assert _has_code(_fails(result), "duplicate-ucr-id")


def test_ucr_stanza_bad_status_fail(tmp_path: Path):
    bad = _VALID_UCR.replace("- **Status:** open", "- **Status:** pending")
    result = vs.ValidationResult()
    vs._validate_ucr_stanza(bad, result)
    assert _has_code(_fails(result), "ucr-invalid-status")


def test_ucr_stanza_missing_field_fail(tmp_path: Path):
    missing = (
        "## Upstream Change Requests\n\n"
        "### UCR-1\n\n"
        "- **Status:** open\n"
        "- **Proposed change:** No target.\n"
        "- **Rationale:** Missing the Target field.\n\n"
    )
    result = vs.ValidationResult()
    vs._validate_ucr_stanza(missing, result)
    assert _has_code(_fails(result), "ucr-missing-field")


def test_ucr_coexists_with_accepted_divergences(tmp_path: Path):
    """A UCR stanza AND an `## Accepted Divergences` section may coexist; no FAIL
    for the coexistence."""
    coexist = (
        _VALID_UCR
        + "## Accepted Divergences\n\n"
        + "- We intentionally skip the optional resync ping.\n\n"
    )
    result = vs.ValidationResult()
    vs._validate_ucr_stanza(coexist, result)
    assert _fails(result) == []


def test_ucr_stanza_absent_no_op(tmp_path: Path):
    """No `## Upstream Change Requests` stanza -> no-op, no FAIL."""
    result = vs.ValidationResult()
    vs._validate_ucr_stanza("# Spec\n\nno stanza here\n", result)
    assert result.checks == []


# ===========================================================================
# T8 — derived-spec exemption in validate_cfc_consumer (I7)
# ===========================================================================

def _plan_with_active_cfc() -> str:
    return (
        "# Plan\n\n"
        "## Feature Breakdown\n\n"
        "### F1: T\n\n- **Description:** d\n- **Component:** c\n\n"
        "## MVP Definition\n\nMVP: F1\n\n"
        "## Cross-Feature Contracts\n\n"
        "### CFC-1: Test contract\n\n"
        "- **Participating features:** F1\n"
        "- **Contract:** test rule\n"
        "- **Per-feature AC:** WHEN x THEN y\n"
        "- **Enforcement:** no owning feature\n\n"
        "## Panel Review\n"
    )


def _make_repo_with_plan(
    tmp_path: Path, dirname: str, spec_content: str
) -> Path:
    """Build a repo tree with blueprint/PLAN.md (active CFC) + a spec dir, where
    find_project_root can locate the local PLAN relative to the spec dir."""
    blueprint = tmp_path / "blueprint"
    blueprint.mkdir(parents=True, exist_ok=True)
    (blueprint / "PLAN.md").write_text(_plan_with_active_cfc(), encoding="utf-8")
    spec_dir = tmp_path / "specs" / dirname
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(spec_content, encoding="utf-8")
    return spec_dir


def test_derived_spec_exempt_from_na_cfc_warn(tmp_path: Path):
    """A derived spec in a repo that HAS a local PLAN with an active CFC section
    AND stale `[CFC-N]` THEN-line tags has BOTH the `n/a`+active-CFC WARN and the
    `n/a`+stale-tag WARN suppressed."""
    spec = _spec_md(
        identifier="n/a",
        derived_from="residents:F7",
        master_hash="unbound",
        requirements_body=(
            "R1\n\n**Acceptance Criteria:**\n\n"
            "- GIVEN x\n  WHEN y\n  THEN z [CFC-1] [CFC-3]\n"
        ),
    )
    spec_dir = _make_repo_with_plan(tmp_path, "residents--F7-resident-sync", spec)
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec, "spec", result)
    warns = _warns(result)
    # Neither the active-CFC WARN nor the stale-tag WARN may appear.
    assert not any("declares `n/a`" in c[2] for c in warns), warns
    assert not any("stale" in c[2].lower() for c in warns), warns
    # No CFC binding checks at all (full exemption).
    assert not any("CFC" in c[0] for c in result.checks), result.checks


def test_non_derived_na_spec_still_warns(tmp_path: Path):
    """A NON-derived `n/a` spec in the same active-CFC repo still gets the
    `n/a`+active-CFC WARN — the exemption is not over-broad."""
    spec = _spec_md(identifier="n/a", derived_from=None, master_hash=None)
    spec_dir = _make_repo_with_plan(tmp_path, "cli-notes-app", spec)
    result = vs.ValidationResult()
    vs.validate_cfc_consumer(spec_dir, spec, "spec", result)
    warns = _warns(result)
    assert any("declares `n/a`" in c[2] for c in warns), warns


# ---------------------------------------------------------------------------
# Grammar single-source contract (code-review #6 / #7): validate_spec must not
# keep its own copy of the CPD field grammar or the narrow approval-hash grammar
# — both come from the shared owners, so they can't drift from reconcile / the
# blueprint validator.
# ---------------------------------------------------------------------------

def test_cpd_field_grammar_comes_from_project_link():
    import project_link
    assert vs.DERIVED_FROM_LINE_RE is project_link.DERIVED_FROM_LINE_RE
    assert vs.MASTER_CONTRACT_HASH_LINE_RE is project_link.MASTER_CONTRACT_HASH_LINE_RE
    assert vs.MASTER_HASH_VALUE_RE is project_link.MASTER_HASH_VALUE_RE
    assert vs.MASTER_HASH_UNBOUND == project_link.MASTER_HASH_UNBOUND


def test_approval_hash_grammar_comes_from_blueprint_common():
    import blueprint_common
    assert vs.APPROVAL_HASH_LINE is blueprint_common.APPROVAL_HASH_LINE_STRICT
