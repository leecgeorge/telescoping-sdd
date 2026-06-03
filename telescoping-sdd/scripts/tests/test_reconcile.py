"""Tests for the cross-repo reconcile layer (CPD C5 / R8).

This file is created in T12a with ONLY the two-repo fixture builder
(`_TwoRepoFixture`) and a `test_fixture_sanity` guard; T12c extends it with the
`reconcile.py` behavior tests on top of the same fixture.

**Why a builder, not raw `tmp_path` manipulation (design Risk 3).** The reconcile
tests need two synthetic repo trees that cross-point at each other — a master
repo whose `blueprint/PLAN.md` carries `### F<n>` features with
`**Implemented by:**`, and a derived repo whose `specs/<master>--F<n>-<slug>/`
directories carry `**Derived from:**` + `**Master contract hash:**` and a
`.sdd/projects.json` naming the master as a sibling. Hand-rolling those trees
inline per test makes a misbuilt fixture look like a reconcile bug. `_TwoRepoFixture`
centralises the tree construction behind two explicit builder methods so the
fragments it emits are produced ONE way, and `test_fixture_sanity` asserts those
fragments parse through the REAL parsers (`master_feature.compute_master_contract_hash`,
`project_link.parse_derived_dirname`, `project_link.parse_qualified_id`) — so a
malformed fixture fails LOUDLY at the sanity gate rather than silently corrupting
a downstream reconcile assertion.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional, Sequence

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"
_TESTS = _SCRIPTS / "tests"

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import blueprint_common  # noqa: E402
import master_feature as mf  # noqa: E402
import project_link  # noqa: E402
import project_registry  # noqa: E402
import reconcile  # noqa: E402
from _fixtures import _FROZEN_PLAN_FIXTURE  # noqa: E402


# --------------------------------------------------------------------------- #
# Grammar single-source contract (code-review #6): reconcile reads the
# derived-spec field grammar from `project_link` (the one owner), not a local
# copy — so it can't drift from the `validate_spec` authoring gate.
# --------------------------------------------------------------------------- #

def test_cpd_field_grammar_comes_from_project_link():
    assert reconcile.MASTER_CONTRACT_HASH_LINE_RE is project_link.MASTER_CONTRACT_HASH_LINE_RE
    assert reconcile.MASTER_HASH_VALUE_RE is project_link.MASTER_HASH_VALUE_RE
    assert reconcile.MASTER_HASH_UNBOUND == project_link.MASTER_HASH_UNBOUND
    # The pre-dedup local name (which hid the duplication from grep) is gone.
    assert not hasattr(reconcile, "MASTER_HASH_LINE_RE")


def test_block_boundary_comes_from_master_feature():
    """reconcile enumerates `### F<n>` blocks via master_feature.iter_feature_blocks,
    not its own heading regexes (the boundary rule has a single owner)."""
    assert hasattr(mf, "iter_feature_blocks")
    # The pre-dedup local boundary regexes are gone.
    assert not hasattr(reconcile, "_FEATURE_HEADING_RE")
    assert not hasattr(reconcile, "_SECTION_HEADING_RE")


def test_load_master_features_strips_backtick_wrap():
    """`_load_master_features` normalizes the `**Implemented by:**` value the same
    way the producer does — a backtick wrap is stripped, bare is unchanged, and an
    unbalanced value is left verbatim (never silently altered)."""
    plan = (
        "## Feature Breakdown\n\n"
        "### F7: x\n- **Implemented by:** `vps-edge`\n"
        "- **Acceptance Criteria:**\n  - a.\n"
    )
    assert reconcile._load_master_features(plan)[7]["implemented_by"] == "vps-edge"
    bare = plan.replace("`vps-edge`", "vps-edge")
    assert reconcile._load_master_features(bare)[7]["implemented_by"] == "vps-edge"
    odd = plan.replace("`vps-edge`", "`vps-edge")  # unbalanced — leave as-is
    assert reconcile._load_master_features(odd)[7]["implemented_by"] == "`vps-edge"


# --------------------------------------------------------------------------- #
# Two-repo fixture builder
# --------------------------------------------------------------------------- #


class _TwoRepoFixture:
    """Builds a cross-pointing master + derived repo pair under one `tmp_path`.

    Layout produced::

        <tmp_path>/<master_project>/          (master repo)
            blueprint/PLAN.md                 ← `### F<n>` feature blocks
        <tmp_path>/<derived_project>/         (derived repo)
            specs/<master>--F<n>-<slug>/spec.md
            .sdd/projects.json                ← names the master as a sibling

    The builder is incremental: construct it, then call `add_master_feature(...)`
    for each master `### F<n>` block and `add_derived_dir(...)` for each derived
    spec directory, then call `write()` to flush both trees to disk (the master
    `PLAN.md`, every derived `spec.md`, and the derived `.sdd/projects.json`).

    The PLAN and spec fragments mirror the on-disk shapes the real parsers accept
    (the same heading/field grammar as `_FROZEN_PLAN_FIXTURE` and DM2/DM4), so a
    fixture built here is, by construction, the input the reconcile path will see.
    """

    def __init__(
        self,
        tmp_path: Path,
        *,
        master_project: str = "residents",
        derived_project: str = "vps-edge",
    ) -> None:
        self.tmp_path = tmp_path
        self.master_project = master_project
        self.derived_project = derived_project

        self.master_root = tmp_path / master_project
        self.derived_root = tmp_path / derived_project

        # Accumulated rendered fragments (flushed by `write()`).
        self._master_feature_blocks: list[str] = []
        # name -> (dirname, rendered spec.md text)
        self._derived_specs: list[tuple[str, str]] = []

    # -- builder methods ---------------------------------------------------- #

    def add_master_feature(
        self,
        feature_number: int,
        description: str,
        ac: Sequence[str],
        *,
        implemented_by: Optional[str] = None,
        title: Optional[str] = None,
        component: str = "Service",
    ) -> str:
        """Append a master `### F<n>` feature block to the master PLAN.

        `ac` is a list of top-level acceptance-criteria bullet bodies (each is
        emitted as a `  - <text>` line under `**Acceptance Criteria:**`). The
        emitted block carries an optional `**Implemented by:**` line and a
        `**Component:**` line (both excluded from the contract hash by
        `master_feature`), matching the DM6 shape.

        Returns the rendered block text (also accumulated for `write()`).
        """
        title = title or f"Feature {feature_number}"
        lines = [f"### F{feature_number}: {title}", ""]
        lines.append(f"- **Description:** {description}")
        lines.append(f"- **Component:** {component}")
        if implemented_by is not None:
            lines.append(f"- **Implemented by:** {implemented_by}")
        lines.append("- **Acceptance Criteria:**")
        for criterion in ac:
            lines.append(f"  - {criterion}")
        block = "\n".join(lines) + "\n"
        self._master_feature_blocks.append(block)
        return block

    def add_derived_dir(
        self,
        project: str,
        feature_number: int,
        slug: str,
        derived_from: str,
        hash_value: str,
        *,
        identifier: str = "n/a",
        ucr_stanza: Optional[str] = None,
    ) -> str:
        """Register a derived spec directory `<project>--F<n>-<slug>/`.

        Emits a `spec.md` carrying `**PLAN feature identifier:** \\`n/a\\``,
        `**Derived from:** \\`<derived_from>\\`` (a qualified id like
        `residents:F7`), and `**Master contract hash:** \\`<hash_value>\\``
        (a 64-char hex digest or the literal `unbound`). An optional
        `ucr_stanza` (already-rendered `## Upstream Change Requests` text) is
        appended verbatim.

        Returns the derived directory name (also accumulated for `write()`).
        """
        dirname = f"{project}--F{feature_number}-{slug}"
        body = [
            f"# {dirname}",
            "",
            f"**PLAN feature identifier:** `{identifier}`",
            f"**Derived from:** `{derived_from}`",
            f"**Master contract hash:** `{hash_value}`",
            "",
            "## Overview",
            "",
            "Synthetic derived spec body for the two-repo reconcile fixture.",
            "",
        ]
        spec_text = "\n".join(body)
        if ucr_stanza is not None:
            spec_text = spec_text + "\n" + ucr_stanza.rstrip("\n") + "\n"
        self._derived_specs.append((dirname, spec_text))
        return dirname

    # -- flush -------------------------------------------------------------- #

    def write(self) -> "_TwoRepoFixture":
        """Materialise both repo trees to disk; return self for chaining."""
        self.write_master()
        self.write_derived()
        return self

    def write_master(self) -> Path:
        """Write the master repo's `blueprint/PLAN.md`; return its path."""
        blueprint_dir = self.master_root / "blueprint"
        blueprint_dir.mkdir(parents=True, exist_ok=True)
        plan_path = blueprint_dir / "PLAN.md"
        plan_path.write_text(self.render_plan(), encoding="utf-8")
        return plan_path

    def write_derived(self) -> Path:
        """Write the derived repo's spec dirs + `.sdd/projects.json`.

        Returns the derived repo root. The `.sdd/projects.json` is written via
        `project_registry.write_projects_config` (the single writer), so the
        registry the fixture emits is exactly the shape `read_projects_config`
        accepts.
        """
        specs_dir = self.derived_root / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        for dirname, spec_text in self._derived_specs:
            spec_dir = specs_dir / dirname
            spec_dir.mkdir(parents=True, exist_ok=True)
            (spec_dir / "spec.md").write_text(spec_text, encoding="utf-8")

        project_registry.write_projects_config(
            self.derived_root, self.projects_config()
        )
        return self.derived_root

    # -- rendered accessors (used by the sanity test before/without write) -- #

    def render_plan(self) -> str:
        """Return the full master `PLAN.md` text (preamble + feature blocks)."""
        preamble = (
            "# Implementation Plan: "
            f"{self.master_project}\n\n"
            "## Feature Breakdown\n\n"
        )
        return preamble + "\n".join(self._master_feature_blocks)

    def projects_config(self) -> dict:
        """Return the derived repo's `.sdd/projects.json` config dict.

        Names the master repo as a sibling at a path relative to the derived
        root, with `role: master` (recorded-not-enforced per DM5).
        """
        return {
            "schemaVersion": project_registry.PROJECTS_JSON_SCHEMA_VERSION,
            "thisProject": self.derived_project,
            "siblings": [
                {
                    "name": self.master_project,
                    "path": f"../{self.master_project}",
                    "role": "master",
                }
            ],
        }

    def derived_dirnames(self) -> list[str]:
        """The derived directory names registered so far."""
        return [dirname for dirname, _ in self._derived_specs]


# --------------------------------------------------------------------------- #
# Fixture sanity (Risk 3): the builder emits parser-valid fragments
# --------------------------------------------------------------------------- #


def test_fixture_sanity(tmp_path: Path) -> None:
    """A known-good `_TwoRepoFixture` emits fragments the REAL parsers accept.

    Asserts the PLAN side parses (the master feature block yields a non-None
    contract hash via `master_feature.compute_master_contract_hash`) and the
    derived side parses (the dir name decomposes via
    `project_link.parse_derived_dirname` and the `**Derived from:**` value via
    `project_link.parse_qualified_id`, both agreeing on project + feature
    number). A misbuilt fixture flips one of these and fails loudly here, before
    any reconcile test is layered on top.
    """
    fixture = _TwoRepoFixture(
        tmp_path, master_project="residents", derived_project="vps-edge"
    )

    # Master side: a feature with an excluded `Implemented by`, a nested
    # sub-bullet (the folded path), and plain top-level criteria.
    fixture.add_master_feature(
        7,
        "Synchronize resident records to the edge cache so the reader can "
        "authorize entry while the WAN link is down.",
        [
            "GIVEN a resident is created WHEN the sync runs THEN the edge "
            "cache reflects it within one interval.",
            "A withdrawn resident is purged on the next sync.",
        ],
        implemented_by="vps-edge",
        title="Resident sync",
    )

    # Derived side: a dir whose name + `Derived from` point back at residents:F7.
    derived_from = f"{fixture.master_project}:F7"
    master_hash = mf.compute_master_contract_hash(fixture.render_plan(), 7)
    assert master_hash is not None, (
        "fixture PLAN feature F7 did not parse via compute_master_contract_hash "
        "— the builder emitted a malformed master feature block"
    )

    dirname = fixture.add_derived_dir(
        project=fixture.master_project,
        feature_number=7,
        slug="resident-sync",
        derived_from=derived_from,
        hash_value=master_hash,
    )

    # Flush to disk and confirm the on-disk trees exist where reconcile expects.
    fixture.write()
    plan_path = fixture.master_root / "blueprint" / "PLAN.md"
    spec_path = fixture.derived_root / "specs" / dirname / "spec.md"
    registry_path = project_registry.config_path(fixture.derived_root)
    assert plan_path.is_file()
    assert spec_path.is_file()
    assert registry_path.is_file()

    # PLAN-side parse: the on-disk PLAN re-parses to a non-None hash equal to the
    # one we computed from the in-memory render (the write round-trips cleanly).
    on_disk_hash = mf.compute_master_contract_hash(
        plan_path.read_text(encoding="utf-8"), 7
    )
    assert on_disk_hash is not None
    assert on_disk_hash == master_hash

    # Derived-side parse: the dir name decomposes, and the `Derived from`
    # qualified id agrees with it on project + feature number (the symmetry the
    # reconcile bijection will rely on).
    parsed_dir = project_link.parse_derived_dirname(dirname)
    assert parsed_dir == (fixture.master_project, 7, "resident-sync")

    parsed_from = project_link.parse_qualified_id(derived_from)
    assert parsed_from == (fixture.master_project, 7)
    assert parsed_dir[0] == parsed_from[0]
    assert parsed_dir[1] == parsed_from[1]

    # Registry-side parse: the emitted `.sdd/projects.json` reads back via the
    # real defensive reader and names the master as a resolvable sibling.
    config = project_registry.read_projects_config(fixture.derived_root)
    assert config is not None
    sibling = project_registry.find_sibling(
        config, fixture.master_project, fixture.derived_root
    )
    assert sibling == fixture.master_root.resolve()


# --------------------------------------------------------------------------- #
# T12c: reconcile.py behavior tests (built on top of the _TwoRepoFixture above)
# --------------------------------------------------------------------------- #
#
# Conventions used below:
#   * `_build_pair(...)` constructs a canonical clean two-repo pair and returns
#     the fixture; per-test mutation happens via the fixture builder methods or
#     direct on-disk edits.
#   * `_reconcile(derived_root)` runs the default reconcile against a `.sdd` root
#     and returns the populated `ValidationResult`.
#   * `_fails(result)` / `_warns(result)` extract the FAIL / WARN detail strings.


def _reconcile(derived_root: Path) -> "reconcile.ValidationResult":
    """Run the default reconcile against a derived `.sdd` root; return the result."""
    result = reconcile.ValidationResult()
    reconcile._run_reconcile(derived_root, result)
    return result


def _checks(result, severity: str) -> list[str]:
    """Return `"<name> :: <detail>"` strings of checks at a given severity.

    The reconcile check NAME carries the machine code (e.g.
    `contract drift: shipped-but-unbound`) and the DETAIL carries the
    human-readable explanation; joining them lets a single substring assertion
    match either half regardless of where the keyword lives.
    """
    return [
        f"{name} :: {detail}"
        for name, sev, detail in result.checks
        if sev == severity
    ]


def _fails(result) -> list[str]:
    return _checks(result, blueprint_common.Severity.FAIL)


def _warns(result) -> list[str]:
    return _checks(result, blueprint_common.Severity.WARN)


def _passes(result) -> list[str]:
    return _checks(result, blueprint_common.Severity.PASS)


def _build_pair(
    tmp_path: Path,
    *,
    slug: str = "resident-sync",
    hash_value: Optional[str] = None,
    implemented_by: str = "vps-edge",
    feature_number: int = 7,
    add_derived: bool = True,
    derived_from: Optional[str] = None,
    ucr_stanza: Optional[str] = None,
) -> _TwoRepoFixture:
    """Build a canonical clean master+derived pair and flush it to disk.

    By default the master feature F<feature_number> is `Implemented by: vps-edge`
    (the derived project) and the derived dir is stamped with the CURRENT master
    contract hash, so reconcile reports a clean bijection with no drift.
    """
    fixture = _TwoRepoFixture(
        tmp_path, master_project="residents", derived_project="vps-edge"
    )
    fixture.add_master_feature(
        feature_number,
        "Synchronize resident records to the edge cache so the reader can "
        "authorize entry while the WAN link is down.",
        [
            "GIVEN a resident is created WHEN the sync runs THEN the edge cache "
            "reflects it within one interval.",
            "A withdrawn resident is purged on the next sync.",
        ],
        implemented_by=implemented_by,
        title="Resident sync",
    )
    if add_derived:
        if hash_value is None:
            hash_value = mf.compute_master_contract_hash(
                fixture.render_plan(), feature_number
            )
        if derived_from is None:
            derived_from = f"residents:F{feature_number}"
        fixture.add_derived_dir(
            project="residents",
            feature_number=feature_number,
            slug=slug,
            derived_from=derived_from,
            hash_value=hash_value,
            ucr_stanza=ucr_stanza,
        )
    fixture.write()
    return fixture


# --- shipping helper ------------------------------------------------------- #


def _approved_artifact(body: str) -> str:
    """Return `body` with an `## Approval` section whose hash is valid (shipped).

    Computes the content hash over the placeholder-neutralized body and stamps a
    matching `- [x] Approved to proceed` + `**Content Hash:**` so
    `blueprint_common.approval_hash_matches` is True for the result.
    """
    draft = (
        body.rstrip()
        + "\n\n## Approval\n\n- [x] Approved to proceed to implementation\n"
        + "**Content Hash:** `pending`\n"
    )
    digest = blueprint_common.compute_content_hash(draft)
    return draft.replace("`pending`", f"`{digest}`", 1)


def _mark_shipped(spec_dir: Path, master_hash_value: str) -> None:
    """Write approved spec.md / design.md / tasks.md (all ticked) into `spec_dir`.

    The spec.md keeps the CPD fields (with `master_hash_value` as the
    `**Master contract hash:**`) so reconcile still parses the stored hash; the
    three artifacts are all approved and every task is ticked, so
    `blueprint_common.is_shipped(spec_dir)` is True.
    """
    spec_body = (
        f"# {spec_dir.name}\n\n"
        "**PLAN feature identifier:** `n/a`\n"
        "**Derived from:** `residents:F7`\n"
        f"**Master contract hash:** `{master_hash_value}`\n\n"
        "## Overview\n\nShipped derived spec body.\n"
    )
    design_body = f"# Design: {spec_dir.name}\n\n## Interfaces\n\nDone.\n"
    tasks_body = (
        f"# Tasks: {spec_dir.name}\n\n"
        "- [x] T1: do the thing\n"
        "- [x] T2: do the other thing\n"
    )
    (spec_dir / "spec.md").write_text(_approved_artifact(spec_body), encoding="utf-8")
    (spec_dir / "design.md").write_text(
        _approved_artifact(design_body), encoding="utf-8"
    )
    (spec_dir / "tasks.md").write_text(
        _approved_artifact(tasks_body), encoding="utf-8"
    )


# --- bijection ------------------------------------------------------------- #


def test_clean_bijection_passes(tmp_path: Path) -> None:
    """Implemented by + derived dir + Derived from all agree → clean, exit 0."""
    fixture = _build_pair(tmp_path)
    result = _reconcile(fixture.derived_root)
    assert result.passed, result.summary()
    assert _fails(result) == []
    # Exit-0 assertion folded into the clean-bijection test (per T12c spec).
    rc = reconcile.main(["--project-root", str(fixture.derived_root)])
    assert rc == 0


def test_clean_bijection_with_backtick_wrapped_implemented_by(tmp_path: Path) -> None:
    """A backtick-wrapped `**Implemented by:** `vps-edge`` reconciles cleanly.

    The PLAN grammar documents the value as "optionally backtick-wrapped" and the
    producer (`validate_blueprint`) accepts it; reconcile must strip the backticks
    before the bijection compare, or a valid PLAN false-FAILs as a likely-rename
    (regression guard for the final-review bug)."""
    fixture = _build_pair(tmp_path, implemented_by="`vps-edge`")
    result = _reconcile(fixture.derived_root)
    assert result.passed, result.summary()
    assert _fails(result) == []


def test_dangling_implemented_by_fail(tmp_path: Path) -> None:
    """Implemented by with no matching derived dir → FAIL."""
    fixture = _build_pair(tmp_path, add_derived=False)
    result = _reconcile(fixture.derived_root)
    assert not result.passed
    fails = _fails(result)
    assert any("dangling" in f.lower() or "no derived directory" in f for f in fails), (
        fails
    )


def test_one_sided_derived_fail(tmp_path: Path) -> None:
    """Derived dir with no matching Implemented by → FAIL."""
    fixture = _build_pair(tmp_path, implemented_by=None)  # type: ignore[arg-type]
    result = _reconcile(fixture.derived_root)
    assert not result.passed
    fails = _fails(result)
    assert any("one-sided" in f.lower() or "no matching master feature" in f for f in fails), (
        fails
    )


def test_likely_rename_label(tmp_path: Path) -> None:
    """A feature implemented_by a DIFFERENT alias → distinct likely-rename FAIL.

    The derived dir `residents--F7-*` points at master F7, but F7 is
    `Implemented by: other-alias`, not the derived project `vps-edge`. This is a
    likely renamed alias, and the FAIL must say so and point at remediation
    (alias rename forbidden), distinct from a plain one-sided/true-deletion FAIL.
    """
    fixture = _build_pair(tmp_path, implemented_by="renamed-alias")
    result = _reconcile(fixture.derived_root)
    assert not result.passed
    fails = _fails(result)
    rename_fails = [f for f in fails if "renamed" in f.lower() or "rename" in f.lower()]
    assert rename_fails, fails
    assert any("forbidden" in f.lower() for f in rename_fails), rename_fails
    # It must NOT be reported as a plain one-sided dir.
    assert not any("one-sided" in f.lower() for f in fails), fails


def test_prefix_only_matching_ignores_slug(tmp_path: Path) -> None:
    """A slug difference between PLAN intent and derived dir is NOT a dangling link.

    The derived dir uses slug `a-totally-different-slug`, but matching is on the
    `<master>--F<n>` prefix only, so the bijection still holds (no FAIL).
    """
    fixture = _build_pair(tmp_path, slug="a-totally-different-slug")
    result = _reconcile(fixture.derived_root)
    assert result.passed, result.summary()
    assert _fails(result) == []


def test_multiple_features_same_derived_project(tmp_path: Path) -> None:
    """F7 and F9 both implemented_by vps-edge resolve independently (per-feature)."""
    fixture = _TwoRepoFixture(
        tmp_path, master_project="residents", derived_project="vps-edge"
    )
    fixture.add_master_feature(
        7, "Sync residents.", ["GIVEN a WHEN b THEN c."],
        implemented_by="vps-edge", title="Resident sync",
    )
    fixture.add_master_feature(
        9, "Audit log.", ["GIVEN d WHEN e THEN f."],
        implemented_by="vps-edge", title="Audit log",
    )
    plan = fixture.render_plan()
    h7 = mf.compute_master_contract_hash(plan, 7)
    h9 = mf.compute_master_contract_hash(plan, 9)
    fixture.add_derived_dir("residents", 7, "resident-sync", "residents:F7", h7)
    fixture.add_derived_dir("residents", 9, "audit-log", "residents:F9", h9)
    fixture.write()

    result = _reconcile(fixture.derived_root)
    assert result.passed, result.summary()
    assert _fails(result) == []
    # Both features must reconcile (two in-sync PASS lines).
    in_sync = [p for p in _passes(result) if "in sync" in p]
    assert len(in_sync) == 2, _passes(result)


def test_reused_master_feature_number(tmp_path: Path) -> None:
    """A derived dir naming a reused/closed feature number defers to the live PLAN.

    The derived dir `residents--F7-*` exists, but the CURRENT master PLAN's F7 is
    `Implemented by: some-other-project` (the number was reused for a different,
    not-this-derived feature). Bijection treats the current PLAN's F7 as
    authoritative → a likely-rename/one-sided FAIL, never a false clean.
    """
    fixture = _build_pair(tmp_path, implemented_by="some-other-project")
    result = _reconcile(fixture.derived_root)
    assert not result.passed
    # The current PLAN F7 (implemented_by some-other-project) is authoritative:
    # the derived dir does not bind back, so a FAIL is raised.
    assert _fails(result), result.summary()


# --- contract drift -------------------------------------------------------- #


def test_contract_drift_warn(tmp_path: Path) -> None:
    """Current master hash != stored derived hash (real 64-hex) → WARN, exit 0."""
    fixture = _build_pair(tmp_path, hash_value="a" * 64)
    result = _reconcile(fixture.derived_root)
    assert result.passed  # drift is a WARN, not a FAIL
    assert result.has_warnings
    warns = _warns(result)
    assert any("drift" in w.lower() for w in warns), warns


def test_unbound_needs_first_stamp(tmp_path: Path) -> None:
    """`unbound` + not shipped → 'needs first stamp' + current hash; no drift; exit 0."""
    fixture = _build_pair(tmp_path, hash_value="unbound")
    result = _reconcile(fixture.derived_root)
    assert result.passed
    # No drift WARN — needs-first-stamp is surfaced as a (PASS) advisory carrying
    # the current hash.
    assert not any("drift" in w.lower() and "mismatch" in w.lower() for w in _warns(result))
    current = mf.compute_master_contract_hash(fixture.render_plan(), 7)
    surfaced = _passes(result) + _warns(result)
    assert any("needs first stamp" in s.lower() for s in surfaced), surfaced
    assert any(current in s for s in surfaced), surfaced
    rc = reconcile.main(["--project-root", str(fixture.derived_root)])
    assert rc == 0


def test_shipped_but_unbound_escalated_warn(tmp_path: Path) -> None:
    """`unbound` + SHIPPED → distinct, louder `shipped-but-unbound` WARN; exit 0."""
    fixture = _build_pair(tmp_path, hash_value="unbound")
    spec_dir = fixture.derived_root / "specs" / fixture.derived_dirnames()[0]
    _mark_shipped(spec_dir, "unbound")
    assert blueprint_common.is_shipped(spec_dir), "fixture should be shipped"

    result = _reconcile(fixture.derived_root)
    assert result.passed  # still a WARN, not a FAIL
    warns = _warns(result)
    assert any("shipped-but-unbound" in w.lower() for w in warns), warns
    # The escalated WARN is distinct from a plain needs-first-stamp.
    assert not any("needs first stamp" in s.lower() for s in _passes(result) + warns)
    rc = reconcile.main(["--project-root", str(fixture.derived_root)])
    assert rc == 0


def test_master_hash_none_surfaced(tmp_path: Path) -> None:
    """Unparseable master feature block → surface 'could not compute master hash'.

    The feature block is corrupted on disk so `compute_master_contract_hash`
    returns None; reconcile surfaces the verify-format message, NOT a drift WARN
    and NOT a crash.
    """
    fixture = _build_pair(tmp_path)
    # Corrupt the master PLAN so feature F7 cannot be located: rename its heading.
    plan_path = fixture.master_root / "blueprint" / "PLAN.md"
    plan_text = plan_path.read_text(encoding="utf-8")
    plan_text = plan_text.replace("### F7:", "### FX-corrupt:")
    plan_path.write_text(plan_text, encoding="utf-8")

    result = _reconcile(fixture.derived_root)
    # No crash; the master-hash-unavailable surface is present, not a drift WARN.
    surfaced = _passes(result) + _warns(result)
    assert any("could not compute master hash" in s.lower() for s in surfaced), surfaced
    assert not any("drifted" in s.lower() for s in _warns(result)), _warns(result)


def test_drift_no_thrash_after_restamp(tmp_path: Path) -> None:
    """Edit master + re-stamp → exactly ONE drift WARN; rerun → still one; read-only.

    (i)   After a master edit and a fixture re-stamp to a STALE hash, reconcile
          reports exactly one drift WARN.
    (ii)  An immediate rerun with no further edit still reports exactly one
          (idempotent-on-repeat, not fire-twice).
    (iii) reconcile did NOT modify spec.md (read-only confirmed).
    """
    # Start clean, then mutate the master and leave the derived hash STALE.
    fixture = _build_pair(tmp_path, hash_value="b" * 64)  # stale on purpose
    spec_dir = fixture.derived_root / "specs" / fixture.derived_dirnames()[0]
    spec_path = spec_dir / "spec.md"
    before = spec_path.read_text(encoding="utf-8")

    result1 = _reconcile(fixture.derived_root)
    drift1 = [w for w in _warns(result1) if "drifted" in w.lower()]
    assert len(drift1) == 1, _warns(result1)

    result2 = _reconcile(fixture.derived_root)
    drift2 = [w for w in _warns(result2) if "drifted" in w.lower()]
    assert len(drift2) == 1, _warns(result2)

    after = spec_path.read_text(encoding="utf-8")
    assert after == before, "reconcile must be read-only; spec.md was modified"


# --- open UCRs ------------------------------------------------------------- #


_OPEN_UCR_STANZA = """\
## Upstream Change Requests

### UCR-1

- **Target:** `residents:F7`
- **Status:** open
- **Proposed change:** Add a tombstone flag to purged residents.
- **Rationale:** The edge reader needs to distinguish purged from never-seen.
"""

_APPLIED_UCR_STANZA = """\
## Upstream Change Requests

### UCR-1

- **Target:** `residents:F7`
- **Status:** applied
- **Proposed change:** Add a tombstone flag to purged residents.
- **Rationale:** Already merged upstream.
"""


def test_open_ucr_surfaced(tmp_path: Path) -> None:
    """A UCR with `status: open` is surfaced in reconcile output."""
    fixture = _build_pair(tmp_path, ucr_stanza=_OPEN_UCR_STANZA)
    result = _reconcile(fixture.derived_root)
    surfaced = _passes(result) + _warns(result)
    assert any("ucr-1" in s.lower() for s in surfaced), surfaced
    assert any("tombstone" in s.lower() for s in surfaced), surfaced


def test_closed_ucr_not_surfaced(tmp_path: Path) -> None:
    """A UCR with `status: applied` is NOT surfaced."""
    fixture = _build_pair(tmp_path, ucr_stanza=_APPLIED_UCR_STANZA)
    result = _reconcile(fixture.derived_root)
    surfaced = _passes(result) + _warns(result)
    assert not any("ucr-1" in s.lower() for s in surfaced), surfaced


# --- print-link mode ------------------------------------------------------- #


def test_print_link_offline(tmp_path: Path, capsys) -> None:
    """Offline --print-link generates the dir name, omits the hash, malformed→non-zero."""
    # Offline (no reachable master): correct dir name, no real hash printed.
    empty_root = tmp_path / "nowhere"
    empty_root.mkdir()
    rc = reconcile.main(
        ["--print-link", "residents:F7", "--title", "Resident Sync",
         "--project-root", str(empty_root)]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "residents--F7-resident-sync" in out
    # Offline: the master hash is NOT printed (only the `unbound` placeholder).
    assert "unbound" in out
    # The generated name round-trips through parse_derived_dirname.
    assert project_link.parse_derived_dirname("residents--F7-resident-sync") == (
        "residents", 7, "resident-sync"
    )

    # Malformed qualified id → non-zero exit, no half-formed dir name printed.
    rc_bad = reconcile.main(["--print-link", "residents:F0", "--title", "X"])
    out_bad = capsys.readouterr().out
    assert rc_bad != 0
    assert "residents--F" not in out_bad


def test_print_link_with_master(tmp_path: Path, capsys) -> None:
    """With the master reachable, --print-link prints the dir name AND the hash."""
    fixture = _build_pair(tmp_path)
    expected_hash = mf.compute_master_contract_hash(fixture.render_plan(), 7)

    rc = reconcile.main(
        ["--print-link", "residents:F7", "--title", "Resident Sync",
         "--project-root", str(fixture.derived_root)]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "residents--F7-resident-sync" in out
    assert expected_hash in out
    # Round-trips through the derived-dirname parser.
    assert project_link.parse_derived_dirname("residents--F7-resident-sync") == (
        "residents", 7, "resident-sync"
    )


def test_print_link_malformed_arg(tmp_path: Path, capsys) -> None:
    """A malformed `<project>:F<n>` arg → non-zero exit, no half-formed name."""
    rc = reconcile.main(["--print-link", "Not A Qualified Id", "--title", "X"])
    out = capsys.readouterr().out
    assert rc != 0
    # No half-formed derived directory NAME (`<project>--F<n>-<slug>`) is emitted.
    assert not re.search(r"\b[a-z0-9-]+--F\d+-", out), out


# --- WARN-skip / robustness ------------------------------------------------ #


def test_asymmetric_registry_warn_skip(tmp_path: Path) -> None:
    """Only one repo has projects.json → WARN-skip + exit 0 (no FAIL, no all-clear).

    The derived registry names a sibling whose root has no `blueprint/`/`.sdd/`
    (the master side is not set up), so `find_sibling` rejects it → WARN-skip.
    """
    fixture = _TwoRepoFixture(
        tmp_path, master_project="residents", derived_project="vps-edge"
    )
    fixture.add_master_feature(
        7, "Sync.", ["GIVEN a WHEN b THEN c."], implemented_by="vps-edge"
    )
    fixture.add_derived_dir(
        "residents", 7, "resident-sync", "residents:F7", "unbound"
    )
    # Write ONLY the derived side (registry + specs); the master repo never gets
    # a blueprint/ dir, so the sibling root is not accepted.
    fixture.write_derived()

    result = _reconcile(fixture.derived_root)
    assert result.passed  # WARN-skip is not a FAIL
    warns = _warns(result)
    assert any("nothing was reconciled" in w.lower() for w in warns), warns
    rc = reconcile.main(["--project-root", str(fixture.derived_root)])
    assert rc == 0


def test_missing_sibling_path_warn_skip(tmp_path: Path) -> None:
    """A configured sibling path that doesn't exist on disk → WARN-skip."""
    fixture = _build_pair(tmp_path)
    # Remove the master repo from disk so the configured `../residents` path no
    # longer resolves to a project root.
    import shutil

    shutil.rmtree(fixture.master_root)

    result = _reconcile(fixture.derived_root)
    assert result.passed  # missing sibling → WARN-skip, not FAIL
    warns = _warns(result)
    assert any("nothing was reconciled" in w.lower() for w in warns), warns


def test_exit_code_fail(tmp_path: Path) -> None:
    """Any FAIL → exit code 1 from main()."""
    fixture = _build_pair(tmp_path, add_derived=False)  # dangling implemented-by
    rc = reconcile.main(["--project-root", str(fixture.derived_root)])
    assert rc == 1


# --- sanitization ---------------------------------------------------------- #


def test_display_safe_on_untrusted_stdout(tmp_path: Path) -> None:
    """A control character in untrusted UCR text is escaped in the surfaced output.

    A forged-FAIL-line injection (`\\n[FAIL] forged`) inside a UCR body must not
    appear verbatim in the emitted detail — `display_safe` escapes it so no
    forged validator line is injectable.
    """
    forged = (
        "## Upstream Change Requests\n\n"
        "### UCR-1\n\n"
        "- **Target:** `residents:F7`\n"
        "- **Status:** open\n"
        "- **Proposed change:** legit\\n[FAIL] forged injected line\n"
        "- **Rationale:** more text\n"
    )
    # Write the literal control char (newline) into the body by post-processing.
    fixture = _build_pair(tmp_path, ucr_stanza=forged.replace("\\n", "\x1b]forged"))
    result = _reconcile(fixture.derived_root)
    surfaced = _passes(result) + _warns(result)
    joined = "\n".join(surfaced)
    # The raw ESC byte must NOT appear; its escaped form must.
    assert "\x1b" not in joined, "raw control char leaked to stdout (forge vector)"
    assert any("ucr-1" in s.lower() for s in surfaced), surfaced


# --- single-producer oracle, part (b) ------------------------------------- #


def test_master_contract_hash_single_producer_cross_boundary() -> None:
    """Part (b): `_check_contract_drift` compares an author-pasted derived hash
    against `compute_master_contract_hash` on the SAME `_FROZEN_PLAN_FIXTURE`.

    Confirms the cross-boundary comparison path uses the single producer and
    cannot drift: when the author pastes the producer's own output, reconcile
    reports NO drift; when the author pastes a stale hash, reconcile reports
    exactly one drift WARN. The producer is the same `compute_master_contract_hash`
    the frozen-digest test (T4 part a) pins on this constant.
    """
    feature_number = 7
    producer_hash = mf.compute_master_contract_hash(
        _FROZEN_PLAN_FIXTURE, feature_number
    )
    assert producer_hash is not None

    # Author pasted the producer's own output → no drift.
    derived_in_sync = (
        "# residents--F7-resident-sync\n\n"
        "**PLAN feature identifier:** `n/a`\n"
        "**Derived from:** `residents:F7`\n"
        f"**Master contract hash:** `{producer_hash}`\n"
    )
    result_sync = reconcile.ValidationResult()
    reconcile._check_contract_drift(
        _FROZEN_PLAN_FIXTURE, derived_in_sync, feature_number, result_sync
    )
    assert not any("drifted" in w.lower() for w in _warns(result_sync)), (
        result_sync.summary()
    )

    # Author pasted a stale 64-hex hash → exactly one drift WARN.
    stale = "c" * 64
    assert stale != producer_hash
    derived_stale = derived_in_sync.replace(producer_hash, stale)
    result_drift = reconcile.ValidationResult()
    reconcile._check_contract_drift(
        _FROZEN_PLAN_FIXTURE, derived_stale, feature_number, result_drift
    )
    drift = [w for w in _warns(result_drift) if "drifted" in w.lower()]
    assert len(drift) == 1, result_drift.summary()
    # The WARN names the producer hash, proving the comparison used the single producer.
    assert producer_hash in drift[0], drift[0]
