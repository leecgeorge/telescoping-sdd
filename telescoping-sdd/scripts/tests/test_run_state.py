"""Shared-helper tests for run_state.py (the C1 module).

Covers the dataclass/constant contract (T2), the current-phase derivation (T3),
the read-only derivation body (T4), and the compact sanitized renderer (T5),
plus the cross-tier parity/contract + import-guard tests. The module is loaded
via the importlib + sys.path pattern used across the shared-script suite
(mirrors test_arch_config.py).
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import json
import pathlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"


def _load_run_state():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    if "run_state" in sys.modules:
        return importlib.reload(sys.modules["run_state"])
    return importlib.import_module("run_state")


def _load_content_hash():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    return importlib.import_module("content_hash")


rs = _load_run_state()
ch = _load_content_hash()


# --- shared test builders ---------------------------------------------------

SDD_PHASES = [("Specify", "spec.md"), ("Design", "design.md"), ("Tasks", "tasks.md")]
BP_PHASES = [("Scope", "SCOPE.md"), ("Architecture", "ARCHITECTURE.md"), ("Plan", "PLAN.md")]


def _st(name, *, exists=False, approved=False, hash_status=None, tick_hint=False):
    """Build one ArtifactState; hash_status defaults to NA."""
    return rs.ArtifactState(
        name=name,
        exists=exists,
        approved=approved,
        hash_status=hash_status if hash_status is not None else rs.HashStatus.NA,
        tick_hint=tick_hint,
    )


def _pair(phase_defs, states):
    """Zip ordered (label, bare_name) defs with a matching list of states into
    the (label, ArtifactState) pairs `_derive_current_phase` consumes."""
    return [(lbl, st) for (lbl, _name), st in zip(phase_defs, states)]


def _approved(name):
    return _st(name, exists=True, approved=True, hash_status=rs.HashStatus.MATCHES)


# --- real-artifact fixture builders (genuine stamps via content_hash) --------

_TRAJ = (
    "## Panel Review\n\n### Trajectory\n\n"
    "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
    "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
    "| 1 | 2026-07-04 | 0 | 0 | 0 | 0 | 0 | — |\n"
)


def _doc(*, body="Do a thing.", checked, hash_val, basis, with_traj=False):
    s = f"# Doc\n\n## Objective\n\n{body}\n\n"
    if with_traj:
        s += _TRAJ + "\n"
    s += "## Approval\n\n"
    box = "[x]" if checked else "[ ]"
    s += f"- {box} Approved to proceed\n- **Content Hash:** `{hash_val}`\n"
    if basis is not None:
        s += f"- **Hash basis:** {basis}\n"
    return s


def _write_matches_v2(path: Path, body="Do a thing."):
    """Write an approved v2 artifact whose stored hash MATCHES current content."""
    content = _doc(body=body, checked=True, hash_val="pending", basis="v2")
    h = ch.compute_content_hash(content)
    path.write_text(content.replace("`pending`", f"`{h}`"), encoding="utf-8")
    return h


def _write_stale_v2(path: Path, body="Do a thing."):
    """Approved v2, then a substantive edit → genuine content drift (STALE)."""
    _write_matches_v2(path, body=body)
    content = path.read_text(encoding="utf-8")
    path.write_text(content + "\n\nExtra substantive prose that drifts the hash.\n", encoding="utf-8")


def _write_stale_migration_v1(path: Path, body="Do a thing."):
    """A v1-basis approved artifact (Trajectory-bearing, no basis line) whose
    stored v1 hash is coherent → a pure v1→v2 basis migration (STALE_MIGRATION)."""
    content = _doc(body=body, checked=True, hash_val="pending", basis=None, with_traj=True)
    v1 = ch.compute_content_hash_v1(ch.trim_trajectory_table(content))
    path.write_text(content.replace("`pending`", f"`{v1}`"), encoding="utf-8")
    return v1


def _write_unapproved(path: Path, body="Do a thing."):
    path.write_text(_doc(body=body, checked=False, hash_val="pending", basis=None), encoding="utf-8")


def _sdd_dir(tmp_path: Path) -> Path:
    d = tmp_path / "specs" / "feature"
    d.mkdir(parents=True)
    return d


def _bp_dir(tmp_path: Path) -> Path:
    d = tmp_path / "blueprint"
    d.mkdir(parents=True)
    return d


def _write_marker(tmp_path: Path, payload):
    """Write .sdd/pending-review.json with `payload` (str written verbatim, else
    JSON-encoded)."""
    sdd = tmp_path / ".sdd"
    sdd.mkdir(exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (sdd / "pending-review.json").write_text(text, encoding="utf-8")


def _open_marker(doc_rel="specs/feature/spec.md"):
    return {
        "schemaVersion": 1,
        "pending": {
            doc_rel: {
                "hash": "0123456789abcdef",
                "stamped_at": "2026-07-04T00:00:00Z",
                "stamped_at_pass": 1,
            }
        },
    }


def _derive_sdd(spec_dir, project_root):
    return rs.derive_run_state(
        tier="sdd",
        artifact_dir=spec_dir,
        project_root=project_root,
        phases=SDD_PHASES,
        terminal_phase_label="Implement",
        tick_hint_artifact="tasks.md",
    )


def _derive_bp(bp_dir, project_root):
    return rs.derive_run_state(
        tier="blueprint",
        artifact_dir=bp_dir,
        project_root=project_root,
        phases=BP_PHASES,
        terminal_phase_label=None,
        tick_hint_artifact=None,
    )


# ---------------------------------------------------------------------------
# T2 — dataclasses + shared field-name constants (the parity contract, R6 AC4)
# ---------------------------------------------------------------------------


def test_core_run_state_fields_match_runstate_dataclass():
    names = tuple(f.name for f in dataclasses.fields(rs.RunState))
    assert rs.CORE_RUN_STATE_FIELDS == names


def test_artifact_fields_match_artifactstate_dataclass():
    names = tuple(f.name for f in dataclasses.fields(rs.ArtifactState))
    assert rs.ARTIFACT_FIELDS == names


def test_obligation_fields_match_obligation_dataclass():
    names = tuple(f.name for f in dataclasses.fields(rs.Obligation))
    assert rs.OBLIGATION_FIELDS == names


def test_hash_status_enum_members():
    members = {m.name for m in rs.HashStatus}
    assert members == {"NA", "MATCHES", "STALE", "STALE_MIGRATION", "DEGRADED"}
    # str Enum: value equals name (usable directly in rendered text).
    assert isinstance(rs.HashStatus.STALE, str)


def test_obligation_kind_constants():
    assert rs.OBLIGATION_PENDING_REVIEW == "pending-review"
    assert rs.OBLIGATION_MARKER_UNREADABLE == "marker-unreadable"
    assert rs.OBLIGATION_DEGRADED_READ == "degraded-read"


# ---------------------------------------------------------------------------
# T3 — _derive_current_phase (AD3 suffixes)
# ---------------------------------------------------------------------------


def test_current_phase_zero_artifacts_not_started():
    sdd = _pair(SDD_PHASES, [_st(n) for _l, n in SDD_PHASES])
    cur, nxt = rs._derive_current_phase(sdd, "Implement")
    assert cur == "Specify (not started)"
    assert nxt  # an all-clear/next pointer is still present at the zero edge

    bp = _pair(BP_PHASES, [_st(n) for _l, n in BP_PHASES])
    cur, nxt = rs._derive_current_phase(bp, None)
    assert cur == "Scope (not started)"
    assert nxt


def test_current_phase_all_approved_terminal_label():
    sdd = _pair(SDD_PHASES, [_approved(n) for _l, n in SDD_PHASES])
    cur, nxt = rs._derive_current_phase(sdd, "Implement")
    assert cur == "Implement"
    assert nxt

    bp = _pair(BP_PHASES, [_approved(n) for _l, n in BP_PHASES])
    cur, nxt = rs._derive_current_phase(bp, None)
    assert cur == "Plan (complete)"  # blueprint terminal=None → defined label
    assert nxt


def test_current_phase_mixed_first_unapproved():
    # spec approved, design present-but-unapproved, tasks absent → Design.
    states = [
        _approved("spec.md"),
        _st("design.md", exists=True, approved=False, hash_status=rs.HashStatus.NA),
        _st("tasks.md"),
    ]
    cur, _nxt = rs._derive_current_phase(_pair(SDD_PHASES, states), "Implement")
    assert cur.startswith("Design")


def test_current_phase_out_of_order_reports_earliest():
    # design approved while spec missing/unapproved → still reports Specify (H).
    states = [
        _st("spec.md", exists=False, approved=False, hash_status=rs.HashStatus.NA),
        _approved("design.md"),
        _st("tasks.md"),
    ]
    cur, _nxt = rs._derive_current_phase(_pair(SDD_PHASES, states), "Implement")
    assert cur.startswith("Specify")


def test_current_phase_ambiguous_suffix_not_not_started():
    # ArtifactAmbiguityError signature: exists=False, hash_status=DEGRADED.
    states = [
        _st("spec.md", exists=False, approved=False, hash_status=rs.HashStatus.DEGRADED),
        _st("design.md"),
        _st("tasks.md"),
    ]
    cur, _nxt = rs._derive_current_phase(_pair(SDD_PHASES, states), "Implement")
    assert cur == "Specify (ambiguous)"
    assert "(not started)" not in cur


def test_current_phase_degraded_suffix():
    # present-but-unreadable signature: exists=True, hash_status=DEGRADED.
    states = [
        _st("spec.md", exists=True, approved=False, hash_status=rs.HashStatus.DEGRADED),
        _st("design.md"),
        _st("tasks.md"),
    ]
    cur, _nxt = rs._derive_current_phase(_pair(SDD_PHASES, states), "Implement")
    assert cur == "Specify (degraded)"
    assert "(not started)" not in cur


# ---------------------------------------------------------------------------
# T4 — derive_run_state + _read_artifact_text (read-only derivation)
# ---------------------------------------------------------------------------


def _artifact(state, name):
    return next(a for a in state.artifacts if a.name == name)


def test_derive_mixed_state_per_artifact_status(tmp_path):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    _write_unapproved(spec_dir / "design.md")
    # tasks.md absent
    state = _derive_sdd(spec_dir, tmp_path)
    assert _artifact(state, "spec.md").approved is True
    assert _artifact(state, "spec.md").hash_status == rs.HashStatus.MATCHES
    assert _artifact(state, "design.md").exists is True
    assert _artifact(state, "design.md").approved is False
    assert _artifact(state, "design.md").hash_status == rs.HashStatus.NA
    assert _artifact(state, "tasks.md").exists is False
    assert state.current_phase.startswith("Design")


def test_derive_genuine_drift_reports_stale(tmp_path):
    spec_dir = _sdd_dir(tmp_path)
    _write_stale_v2(spec_dir / "spec.md")
    state = _derive_sdd(spec_dir, tmp_path)
    assert _artifact(state, "spec.md").hash_status == rs.HashStatus.STALE


def test_derive_basis_migration_reports_stale_migration(tmp_path):
    spec_dir = _sdd_dir(tmp_path)
    _write_stale_migration_v1(spec_dir / "spec.md")
    state = _derive_sdd(spec_dir, tmp_path)
    assert _artifact(state, "spec.md").hash_status == rs.HashStatus.STALE_MIGRATION


def test_derive_phase4_tasks_stale_sets_tick_hint(tmp_path):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    _write_matches_v2(spec_dir / "design.md")
    _write_stale_v2(spec_dir / "tasks.md")
    state = _derive_sdd(spec_dir, tmp_path)
    assert state.current_phase == "Implement"
    tasks = _artifact(state, "tasks.md")
    assert tasks.hash_status == rs.HashStatus.STALE
    assert tasks.tick_hint is True


def test_derive_migration_tasks_no_tick_hint(tmp_path):
    # tasks.md approved + STALE_MIGRATION (v1) in Implement → tick_hint stays
    # False: the AD6 gate is STALE ONLY, never STALE_MIGRATION.
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    _write_matches_v2(spec_dir / "design.md")
    _write_stale_migration_v1(spec_dir / "tasks.md")
    state = _derive_sdd(spec_dir, tmp_path)
    assert state.current_phase == "Implement"
    tasks = _artifact(state, "tasks.md")
    assert tasks.hash_status == rs.HashStatus.STALE_MIGRATION
    assert tasks.tick_hint is False


def test_derive_blueprint_never_sets_tick_hint(tmp_path):
    bp_dir = _bp_dir(tmp_path)
    _write_matches_v2(bp_dir / "SCOPE.md")
    _write_matches_v2(bp_dir / "ARCHITECTURE.md")
    _write_stale_v2(bp_dir / "PLAN.md")
    state = _derive_bp(bp_dir, tmp_path)
    assert all(a.tick_hint is False for a in state.artifacts)


def test_derive_malformed_approval_reads_stale_no_raise(tmp_path):
    spec_dir = _sdd_dir(tmp_path)
    (spec_dir / "spec.md").write_text(
        "# Doc\n\n## Approval\n\n- [x] Approved to proceed\n"
        "- **Content Hash:** `not-a-valid-hash`\n",
        encoding="utf-8",
    )
    # Must not raise (AD8 in-helper no-raise) and reads STALE via the fail-closed
    # non-16-hex branch.
    state = _derive_sdd(spec_dir, tmp_path)
    assert _artifact(state, "spec.md").hash_status == rs.HashStatus.STALE


def test_derive_corrupt_marker_maps_marker_unreadable(tmp_path):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    _write_marker(tmp_path, "{ this is not valid json")  # fuzzed garbage bytes
    state = _derive_sdd(spec_dir, tmp_path)
    kinds = {o.kind for o in state.obligations}
    assert rs.OBLIGATION_MARKER_UNREADABLE in kinds
    # Never laundered into a pending-review "all clear" / silent no-obligation.
    assert rs.OBLIGATION_PENDING_REVIEW not in kinds


def test_derive_corrupt_marker_next_action_present(tmp_path):
    spec_dir = _sdd_dir(tmp_path)
    _write_marker(tmp_path, "{ not json")
    state = _derive_sdd(spec_dir, tmp_path)
    ob = next(o for o in state.obligations if o.kind == rs.OBLIGATION_MARKER_UNREADABLE)
    assert "pending-review.json" in ob.next_action


@pytest.mark.parametrize(
    "exc",
    [PermissionError("nope"), UnicodeDecodeError("utf-8", b"", 0, 1, "bad")],
)
def test_derive_present_but_unreadable_degraded(tmp_path, monkeypatch, exc):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    orig = pathlib.Path.read_text

    def boom(self, *a, **k):
        if self.name == "spec.md":
            raise exc
        return orig(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", boom)
    state = _derive_sdd(spec_dir, tmp_path)
    spec = _artifact(state, "spec.md")
    assert spec.exists is True
    assert spec.hash_status == rs.HashStatus.DEGRADED
    assert spec.approved is False
    degraded = [o for o in state.obligations if o.kind == rs.OBLIGATION_DEGRADED_READ]
    assert degraded


def test_derive_absent_artifact_distinct_from_degraded(tmp_path):
    spec_dir = _sdd_dir(tmp_path)  # no artifacts at all
    state = _derive_sdd(spec_dir, tmp_path)
    spec = _artifact(state, "spec.md")
    assert spec.exists is False
    assert spec.hash_status == rs.HashStatus.NA
    # An absent artifact raises NO obligation (distinct from degraded).
    assert not [o for o in state.obligations if o.kind == rs.OBLIGATION_DEGRADED_READ]


def test_derive_degraded_obligation_next_action_present(tmp_path, monkeypatch):
    spec_dir = _sdd_dir(tmp_path)
    _write_matches_v2(spec_dir / "spec.md")
    orig = pathlib.Path.read_text

    def boom(self, *a, **k):
        if self.name == "spec.md":
            raise PermissionError("nope")
        return orig(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", boom)
    state = _derive_sdd(spec_dir, tmp_path)
    ob = next(o for o in state.obligations if o.kind == rs.OBLIGATION_DEGRADED_READ)
    assert ob.next_action.strip()  # non-trivial


def test_derive_zero_artifacts_with_open_marker_both_render(tmp_path):
    spec_dir = _sdd_dir(tmp_path)  # no artifacts
    _write_marker(tmp_path, _open_marker())
    state = _derive_sdd(spec_dir, tmp_path)
    # phase line still present (not started) AND the open obligation surfaces.
    assert state.current_phase.startswith("Specify")
    assert any(o.kind == rs.OBLIGATION_PENDING_REVIEW for o in state.obligations)


def test_cross_tier_parity_semantic_exclusivity(tmp_path):
    # SDD tier: a stale tasks.md in Implement (tick_hint True) + open marker.
    sdd_root = tmp_path / "sdd"
    sdd_root.mkdir()
    spec_dir = sdd_root / "specs" / "feature"
    spec_dir.mkdir(parents=True)
    _write_matches_v2(spec_dir / "spec.md")
    _write_matches_v2(spec_dir / "design.md")
    _write_stale_v2(spec_dir / "tasks.md")
    _write_marker(sdd_root, _open_marker("specs/feature/design.md"))
    sdd_state = _derive_sdd(spec_dir, sdd_root)

    # Blueprint tier: an approved+stale PLAN.md.
    bp_root = tmp_path / "bp"
    bp_root.mkdir()
    bp = bp_root / "blueprint"
    bp.mkdir(parents=True)
    _write_matches_v2(bp / "SCOPE.md")
    _write_matches_v2(bp / "ARCHITECTURE.md")
    _write_stale_v2(bp / "PLAN.md")
    bp_state = _derive_bp(bp, bp_root)

    shared_kinds = {
        rs.OBLIGATION_PENDING_REVIEW,
        rs.OBLIGATION_MARKER_UNREADABLE,
        rs.OBLIGATION_DEGRADED_READ,
    }
    for state in (sdd_state, bp_state):
        assert tuple(f.name for f in dataclasses.fields(state)) == rs.CORE_RUN_STATE_FIELDS
        for a in state.artifacts:
            assert tuple(f.name for f in dataclasses.fields(a)) == rs.ARTIFACT_FIELDS
        for o in state.obligations:
            assert tuple(f.name for f in dataclasses.fields(o)) == rs.OBLIGATION_FIELDS
            assert o.kind in shared_kinds
    # tick_hint is never True on the blueprint tier.
    assert all(a.tick_hint is False for a in bp_state.artifacts)
    # ...but the SDD tier CAN set it (sanity that the exclusivity is real).
    assert any(a.tick_hint for a in sdd_state.artifacts)


def test_run_state_does_not_import_validators():
    src = (_SCRIPTS / "run_state.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(n.name.split(".")[0] for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "validate_spec" not in imported
    assert "validate_blueprint" not in imported


# ---------------------------------------------------------------------------
# T5 — format_run_state + _sanitize (compact render, AD13/AD14)
# ---------------------------------------------------------------------------


def _ob(kind, detail="detail-text", next_action="do the thing"):
    return rs.Obligation(kind=kind, detail=detail, next_action=next_action)


def _stale(name):
    return _st(name, exists=True, approved=True, hash_status=rs.HashStatus.STALE)


def test_format_fully_clean_two_lines_with_next_step():
    state = rs.RunState(
        tier="sdd",
        current_phase="Implement",
        artifacts=[_approved("spec.md"), _approved("design.md"), _approved("tasks.md")],
        obligations=[],
        next_step="proceed to Implement",
    )
    out = rs.format_run_state(state)
    assert len(out.splitlines()) <= 2
    assert "proceed to Implement" in out


def test_format_stale_vs_stale_migration_distinct_next_action():
    state = rs.RunState(
        tier="sdd",
        current_phase="Implement",
        artifacts=[
            _stale("spec.md"),
            _st("design.md", exists=True, approved=True, hash_status=rs.HashStatus.STALE_MIGRATION),
        ],
        obligations=[],
        next_step="x",
    )
    out = rs.format_run_state(state)
    assert "re-approval + panel re-review" in out
    assert "re-stamp only" in out
    spec_line = next(l for l in out.splitlines() if "spec.md" in l)
    design_line = next(l for l in out.splitlines() if "design.md" in l)
    assert "re-stamp only" not in spec_line
    assert "re-approval" not in design_line


def test_format_tick_hint_suffix_wording():
    tasks = _st("tasks.md", exists=True, approved=True, hash_status=rs.HashStatus.STALE, tick_hint=True)
    state = rs.RunState(tier="sdd", current_phase="Implement", artifacts=[tasks], obligations=[], next_step="x")
    out = rs.format_run_state(state)
    assert "may be expected task-tick ticks; run the full validator to confirm" in out


def test_format_stale_migration_tasks_no_tick_suffix():
    tasks = _st("tasks.md", exists=True, approved=True, hash_status=rs.HashStatus.STALE_MIGRATION, tick_hint=False)
    state = rs.RunState(tier="sdd", current_phase="Implement", artifacts=[tasks], obligations=[], next_step="x")
    out = rs.format_run_state(state)
    assert "task-tick ticks" not in out


def test_format_clean_artifacts_collapse():
    state = rs.RunState(
        tier="sdd",
        current_phase="Implement",
        artifacts=[_stale("spec.md"), _approved("design.md"), _approved("tasks.md")],
        obligations=[],
        next_step="x",
    )
    out = rs.format_run_state(state)
    assert "spec.md" in out
    assert "design.md" not in out  # clean → collapsed
    assert "tasks.md" not in out


def test_format_overflow_preserves_all_obligations():
    arts = [_stale(f"a{i}.md") for i in range(30)]
    obs = [
        _ob(rs.OBLIGATION_MARKER_UNREADABLE, "marker-bad-detail"),
        _ob(rs.OBLIGATION_DEGRADED_READ, "degraded-detail"),
        _ob(rs.OBLIGATION_PENDING_REVIEW, "pending-doc-detail"),
    ]
    state = rs.RunState(tier="sdd", current_phase="Implement", artifacts=arts, obligations=obs, next_step="x")
    out = rs.format_run_state(state)
    assert any("more" in l for l in out.splitlines())  # overflow line present
    # NO obligation (integrity or plain pending-review) is ever dropped (AD13 + J).
    assert "marker-bad-detail" in out
    assert "degraded-detail" in out
    assert "pending-doc-detail" in out


def test_format_stacking_order_phase_artifacts_obligations():
    state = rs.RunState(
        tier="sdd",
        current_phase="Design",
        artifacts=[_stale("spec.md")],
        obligations=[_ob(rs.OBLIGATION_PENDING_REVIEW, "pending-doc-detail")],
        next_step="x",
    )
    out = rs.format_run_state(state)
    assert out.index("Design") < out.index("spec.md") < out.index("pending-doc-detail")


def test_format_no_color_only_encoding():
    state = rs.RunState(tier="sdd", current_phase="Implement", artifacts=[_stale("spec.md")], obligations=[], next_step="x")
    out = rs.format_run_state(state)
    assert "\x1b" not in out  # no ANSI escapes anywhere
    assert "STALE" in out  # status carried as a plain-text label


def test_sanitize_strips_control_ansi_and_caps_length():
    dirty = "\x1b[31mRED\x1b[0m\x07bell" + "A" * 500
    clean = rs._sanitize(dirty)
    assert "\x1b" not in clean
    assert "\x07" not in clean
    assert "RED" in clean and "bell" in clean
    assert len(clean) <= 200


def test_sanitize_collapses_embedded_newline_no_extra_line():
    assert rs._sanitize("a\nb\rc") == "a b c"
    assert "\n" not in rs._sanitize("x\ny")
    # Format-level: an obligation detail carrying an embedded newline cannot
    # inject a standalone fake "all clear" physical line (status spoof, AD14-C).
    state = rs.RunState(
        tier="sdd",
        current_phase="Design",
        artifacts=[_stale("spec.md")],
        obligations=[_ob(rs.OBLIGATION_PENDING_REVIEW, "evil\nall clear — proceed to nowhere")],
        next_step="x",
    )
    out = rs.format_run_state(state)
    assert "all clear — proceed to nowhere" not in out.splitlines()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
