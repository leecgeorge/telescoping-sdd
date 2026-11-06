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


# ---------------------------------------------------------------------------
# Unit C0 (T8, design Testing Strategy, `[DEF-23]`): a converged, tokened
# closing Trajectory row built on the PRODUCTION path — trajectory.render_table
# plus trajectory.stamp_provenance — so a fixture row is byte-identical to what
# archive_pass.py writes for the same cells, and its `prov=` hash equals
# compute_content_hash of the returned text.
# ---------------------------------------------------------------------------

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_SCRIPTS_DIR = str(_Path(__file__).resolve().parents[1])
if _SCRIPTS_DIR not in _sys.path:
    _sys.path.insert(0, _SCRIPTS_DIR)

_PANEL_REVIEW_SKELETON = (
    "## Panel Review\n\n"
    "### Trajectory\n\n"
    "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
    "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
    "\n"
    "### Sealed dispositions\n\n"
    "_None yet._\n\n"
    "### Latest pass detail\n\n"
    "| Severity | Source | Concern | Disposition | Notes |\n"
    "|----------|--------|---------|-------------|-------|\n"
    "\n"
)


def _ensure_panel_review(text: str) -> str:
    import re as _re

    if _re.search(r"^##\s+Panel Review\s*$", text, _re.MULTILINE):
        return text
    m = _re.search(r"^##\s+Approval\s*$", text, _re.MULTILINE)
    if m is None:
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return text + sep + _PANEL_REVIEW_SKELETON
    return text[: m.start()] + _PANEL_REVIEW_SKELETON + text[m.start():]


def _trajectory_table(text: str):
    """(lines, header_idx, terminator_idx, header_cells, rows) of the canonical table."""
    import trajectory as _tr

    bounds = _tr._trajectory_bounds(text)
    if bounds is None:
        raise ValueError("no canonical ### Trajectory table")
    lines = text.split("\n")
    h, first, term, _ = bounds
    header = _tr.split_table_row(lines[h])
    rows = [dict(zip(header, _tr.split_table_row(ln))) for ln in lines[first:term]]
    return lines, h, term, header, rows


def add_converged_closing_row(
    text: str,
    *,
    pass_no: "int | None" = None,
    notes: "str | None" = None,
    date: str = "2026-01-01",
) -> str:
    """Append a converged closing row (0 HIGH, 0 Addressed, 0 Deferred) whose
    Notes end with a provenance token, inserting a three-sub-section
    `## Panel Review` before `## Approval` when the document has none."""
    import content_hash as _ch
    import trajectory as _tr

    if notes is None:
        notes = _tr.STAMP_CONVERGED_NO_HIGH
    text = _ensure_panel_review(text)
    lines, h, term, header, rows = _trajectory_table(text)
    if pass_no is None:
        nums = [int(r.get("Pass", "")) for r in rows if _tr._is_ascii_int(r.get("Pass", ""))]
        pass_no = max(nums, default=0) + 1
    base = {
        "Pass": str(pass_no), "Date": date, "HIGHs": "0", "Regressions": "0",
        "Addressed": "0", "Deferred": "0", "Sealed": "0",
    }

    def build(prov_hex: str) -> str:
        token = _tr.provenance_token(prov_hex)
        row = dict(base, Notes=token if notes == "—" else f"{notes}; {token}")
        block = _tr.render_table(header, rows + [row])
        return "\n".join(lines[:h] + block + lines[term:])

    return _tr.stamp_provenance(build, _ch.compute_content_hash)


def restamp_provenance(text: str) -> str:
    """Recompute the newest tokened row's `prov=` hash for the current text
    (after a fixture edit made below the closing row)."""
    import content_hash as _ch
    import trajectory as _tr

    lines, h, term, header, rows = _trajectory_table(text)
    first = h + 2
    idx = None
    for i in range(term - 1, first - 1, -1):
        if _tr.read_provenance_hash(_tr.split_table_row(lines[i])[-1]) is not None:
            idx = i
            break
    if idx is None:
        raise ValueError("no tokened Trajectory row to restamp")
    old = _tr.read_provenance_hash(_tr.split_table_row(lines[idx])[-1])

    def build(prov_hex: str) -> str:
        new_lines = list(lines)
        new_lines[idx] = lines[idx].replace(f"prov={old}", f"prov={prov_hex}")
        return "\n".join(new_lines)

    return _tr.stamp_provenance(build, _ch.compute_content_hash)


def cpd_derived_spec(spec_dir: "_Path", *, master_hash: str = "unbound") -> "_Path":
    """A derived (Cross-Project Derivation) spec.md at ``spec_dir`` — directory
    form ``<project>--F<n>-<slug>`` — carrying the two provenance lines and a
    converged closing row, ready for a first approval (Unit C0 AC-3.7: approving
    it writes no binding line and leaves the CPD fields unchanged)."""
    spec_dir.mkdir(parents=True, exist_ok=True)
    project, _sep, rest = spec_dir.name.partition("--")
    feature = rest.split("-", 1)[0]
    text = (
        "# Feature: derived\n\n"
        "**PLAN feature identifier:** `n/a`\n"
        f"**Derived from:** `{project}:{feature}`\n"
        f"**Master contract hash:** `{master_hash}`\n\n"
        "## Objective\n\nx\n\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )
    p = spec_dir / "spec.md"
    p.write_text(add_converged_closing_row(text), encoding="utf-8")
    return p


_CHAIN = {
    "sdd": ("specs/feat-x", [("spec", "spec.md"), ("design", "design.md"), ("tasks", "tasks.md")]),
    "blueprint": ("blueprint", [("scope", "SCOPE.md"), ("architecture", "ARCHITECTURE.md"), ("plan", "PLAN.md")]),
}
_TERMINAL_NAMES = ("tasks.md", "PLAN.md")


def _load_validator(tier: str):
    import importlib.util

    rel = ("spec-driven-dev/scripts/validate_spec.py" if tier == "sdd"
           else "project-blueprint/scripts/validate_blueprint.py")
    name = "validate_spec" if tier == "sdd" else "validate_blueprint"
    if name in _sys.modules:
        return _sys.modules[name]
    path = _Path(__file__).resolve().parents[2] / "skills" / rel
    if str(path.parent) not in _sys.path:
        _sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def write_chain(root, tier: str, *, approve, bind: bool, prefixed: bool = False):
    """Write a tier's three artifacts, each finalised with a converged closing
    row, and stamp the phases in ``approve`` in order through the tier wrapper.
    With ``bind=True`` each stamp goes through ``plan_approval`` (the production
    path) and its writes; with ``bind=False`` no writes are passed, so
    downstreams carry no binding line (the pre-release, unbound shape)."""
    import blueprint_common as _bc

    root = _Path(root)
    (root / ".git").mkdir(parents=True, exist_ok=True)
    rel, phases = _CHAIN[tier]
    d = root / rel
    d.mkdir(parents=True, exist_ok=True)
    mod = _load_validator(tier)
    out = {}
    for i, (_flag, bare) in enumerate(phases, start=1):
        fname = f"{i:02d}_{bare}" if prefixed else bare
        text = (
            f"# {bare}\n\n**PLAN feature identifier:** `n/a`\n\n## Objective\n\nx\n\n"
            "## Approval\n\n- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
        )
        text = _ensure_panel_review(text)
        if bare not in _TERMINAL_NAMES:
            text = text.replace(
                "### Latest pass detail",
                "### Deferred dispositions\n\n<!-- none -->\n\n### Latest pass detail", 1,
            )
        p = d / fname
        p.write_text(add_converged_closing_row(text), encoding="utf-8")
        out[bare] = p
    by_flag = dict(phases)
    for flag in approve:
        bare = by_flag[flag]
        p = out[bare]
        if bind:
            plan = _bc.plan_approval(p, directory=d, bare_name=bare, task_tick=False,
                                     override_reason=None)
            if not plan.result.passed:
                raise AssertionError(plan.result.summary())
            ok = mod.approve_document(p, project_root=root, approval_writes=plan.writes)
        else:
            ok = mod.approve_document(p, project_root=root)
        if not ok:
            raise AssertionError(f"approve failed for {p}")
    return out
