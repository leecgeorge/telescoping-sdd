"""Unit C0 R3/R4 — upstream bindings: maps, collection, approval writes, race check,
binding reports and the AC-9.2 glosses for binding, superseded and unbound."""
from __future__ import annotations

import re
import sys
from functools import partial
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import blueprint_common as bc  # noqa: E402

H1 = "0123456789abcdef"
H2 = "fedcba9876543210"


def _doc(stamp: str = "pending", body: str = "body", checked: bool = None) -> str:
    if checked is None:
        checked = stamp != "pending"
    box = "x" if checked else " "
    return (
        f"# Doc\n\n## Objective\n\n{body}\n\n## Approval\n\n"
        f"- [{box}] Approved to proceed to next phase\n"
        f"- **Content Hash:** `{stamp}`\n"
    )


def _write(d: Path, name: str, text: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p


# --- T15: maps, collection, approval writes, race check ---------------------


def test_upstream_sets_follow_consistency_pairs():
    assert bc.UPSTREAM_SETS == {
        "design.md": ("spec.md",),
        "tasks.md": ("spec.md", "design.md"),
        "ARCHITECTURE.md": ("SCOPE.md",),
        "PLAN.md": ("SCOPE.md", "ARCHITECTURE.md"),
    }
    assert "spec.md" not in bc.UPSTREAM_SETS and "SCOPE.md" not in bc.UPSTREAM_SETS


def test_artifact_phase_no_map():
    assert bc.ARTIFACT_PHASE_NO == {
        "spec.md": 1, "SCOPE.md": 1, "design.md": 2, "ARCHITECTURE.md": 2,
        "tasks.md": 3, "PLAN.md": 3,
    }


def test_collect_upstream_bindings_reads_16_hex_stamps(tmp_path):
    _write(tmp_path, "01_spec.md", _doc(H1))
    _write(tmp_path, "02_design.md", _doc(H2.upper()))
    got = bc.collect_upstream_bindings(tmp_path, "tasks.md")
    assert got == (
        bc.UpstreamBinding("spec.md", H1),
        bc.UpstreamBinding("design.md", H2),
    )
    assert bc.collect_upstream_bindings(tmp_path, "spec.md") == ()


@pytest.mark.parametrize("stamp", ["pending", None, "not-hex-at-all!!"])
def test_collect_upstream_bindings_raises_on_unbindable_stamp(tmp_path, stamp):
    if stamp is not None:
        _write(tmp_path, "spec.md", _doc(stamp, checked=True))
    with pytest.raises(bc.UnbindableUpstreamError) as exc:
        bc.collect_upstream_bindings(tmp_path, "design.md")
    assert exc.value.upstream == "spec.md"
    assert "spec.md" in str(exc.value)


def test_collect_upstream_bindings_binds_drifted_upstream_to_its_stamp(tmp_path):
    _write(tmp_path, "spec.md", _doc(H1, body="edited after approval"))
    assert bc.collect_upstream_bindings(tmp_path, "design.md") == (
        bc.UpstreamBinding("spec.md", H1),
    )


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_binding_lines_written_in_upstream_sets_order(tmp_path, tier):
    if tier == "sdd":
        _write(tmp_path, "design.md", _doc(H2))
        _write(tmp_path, "spec.md", _doc(H1))
        target, first, second = "tasks.md", "spec.md", "design.md"
    else:
        _write(tmp_path, "ARCHITECTURE.md", _doc(H2))
        _write(tmp_path, "SCOPE.md", _doc(H1))
        target, first, second = "PLAN.md", "SCOPE.md", "ARCHITECTURE.md"
    b = bc.collect_upstream_bindings(tmp_path, target)
    writes = bc.ApprovalWrites(bindings=b, override=None, judged_hash="x")
    out = bc.apply_approval_writes(_doc(), tmp_path / target, writes=writes)
    assert out.index(f"`{first}`") < out.index(f"`{second}`")


def test_apply_approval_writes_idempotent(tmp_path):
    writes = bc.ApprovalWrites(
        bindings=(bc.UpstreamBinding("spec.md", H1),),
        override=bc.OverrideRecord(2, "user accepted"),
        judged_hash="x",
    )
    once = bc.apply_approval_writes(_doc(), tmp_path / "design.md", writes=writes)
    twice = bc.apply_approval_writes(once, tmp_path / "design.md", writes=writes)
    assert once == twice
    assert once.count("Convergence override") == 1


def test_apply_approval_writes_inside_approval_bounds(tmp_path):
    doc = _doc() + "\n## Notes\n\ntail\n"
    writes = bc.ApprovalWrites(
        bindings=(bc.UpstreamBinding("spec.md", H1),),
        override=bc.OverrideRecord(None, "r"), judged_hash="x",
    )
    out = bc.apply_approval_writes(doc, tmp_path / "design.md", writes=writes)
    start = bc.approval_section_bounds(doc)[0]
    assert out[:start] == doc[:start]
    assert out.endswith("## Notes\n\ntail\n")
    b = bc.approval_section_bounds(out)
    body = out[b[0]:b[1]]
    assert "Upstream binding" in body and "Convergence override" in body


def _writes_for(tmp_path, text, bindings=()):
    return bc.ApprovalWrites(
        bindings=tuple(bindings), override=None, judged_hash=bc.judged_text_hash(text)
    )


def test_verify_judged_transform_raises_on_changed_content(tmp_path):
    text = _doc(body="judged")
    p = _write(tmp_path, "spec.md", text)
    writes = _writes_for(tmp_path, text)
    trimmed = bc.trim_trajectory_table(text)
    assert bc.verify_judged_transform(trimmed, p, writes=writes) == trimmed
    with pytest.raises(bc.ApprovalRaceError):
        bc.verify_judged_transform(trimmed.replace("judged", "changed"), p, writes=writes)


def test_verify_judged_transform_raises_on_changed_upstream_stamp(tmp_path):
    up = _write(tmp_path, "spec.md", _doc(H1))
    text = _doc()
    p = _write(tmp_path, "design.md", text)
    writes = _writes_for(tmp_path, text, [bc.UpstreamBinding("spec.md", H1)])
    assert bc.verify_judged_transform(text, p, writes=writes) == text
    up.write_text(_doc(H2), encoding="utf-8")
    with pytest.raises(bc.ApprovalRaceError):
        bc.verify_judged_transform(text, p, writes=writes)


def test_verify_judged_transform_bom_file_no_race(tmp_path):
    text = _doc(body="bom body")
    p = tmp_path / "spec.md"
    p.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    as_read = p.read_text(encoding="utf-8-sig")
    writes = _writes_for(tmp_path, as_read)
    core_view = bc.trim_trajectory_table(p.read_text(encoding="utf-8-sig"))
    assert bc.verify_judged_transform(core_view, p, writes=writes) == core_view


def test_compose_content_transforms_order_and_none_skipping(tmp_path):
    calls = []

    def a(c, p):
        calls.append("a")
        return c + "A"

    def b(c, p):
        calls.append("b")
        return c + "B"

    f = bc.compose_content_transforms(a, None, b)
    assert f("x", tmp_path) == "xAB" and calls == ["a", "b"]
    assert bc.compose_content_transforms(None, None)("x", tmp_path) == "x"
    g = bc.compose_content_transforms(partial(lambda c, p, *, k: c + k, k="K"))
    assert g("x", tmp_path) == "xK"


# --- T18: validator wrappers compose the approval writes (AD12) -------------

import importlib.util  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))
import _fixtures as fx  # noqa: E402
import pending_review as pr  # noqa: E402

_SKILLS = _SCRIPTS.parent / "skills"


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    d = str((_SKILLS / rel).parent)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(name, _SKILLS / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


vs = _load("validate_spec", "spec-driven-dev/scripts/validate_spec.py")
vb = _load("validate_blueprint", "project-blueprint/scripts/validate_blueprint.py")

_CFC = (
    "## Cross-Feature Contracts\n\n"
    "### CFC-1: Shared ids\n\n"
    "- **Participating features:** F1, F2\n"
    "- **Contract:** ids are stable.\n"
    "- **Per-feature AC:** GIVEN an id WHEN read THEN it is stable [CFC-1]\n"
    "- **Enforcement:** F1 owns the check.\n\n"
)


def _art(d: Path, name: str, *, body: str = "x", extra: str = "") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    text = (
        f"# {name}\n\n**PLAN feature identifier:** `n/a`\n\n## Objective\n\n{body}\n\n{extra}"
        "## Approval\n\n- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
    )
    p = d / name
    text = fx.add_converged_closing_row(text)
    if name not in ("tasks.md", "PLAN.md"):
        # Non-terminal artifacts carry the Deferred section archive_pass expects
        # (otherwise its legacy auto-insert is a hashed edit).
        text = text.replace(
            "### Latest pass detail",
            "### Deferred dispositions\n\n<!-- none -->\n\n### Latest pass detail", 1,
        )
    p.write_text(text, encoding="utf-8")
    return p


def _mod_for(name: str):
    return vs if name in ("spec.md", "design.md", "tasks.md") else vb


def _approve_bound(p: Path, root: Path) -> bool:
    text = p.read_text(encoding="utf-8-sig")
    bare = bc.strip_artifact_prefix(p.name)
    writes = bc.ApprovalWrites(
        bindings=bc.collect_upstream_bindings(p.parent, bare),
        judged_hash=bc.judged_text_hash(text),
    )
    return _mod_for(bare).approve_document(p, project_root=root, approval_writes=writes)


def _chain(root: Path, tier: str) -> "dict[str, Path]":
    (root / ".git").mkdir(parents=True, exist_ok=True)
    if tier == "sdd":
        d = root / "specs" / "feat-x"
        names = ["spec.md", "design.md", "tasks.md"]
    else:
        d = root / "blueprint"
        names = ["SCOPE.md", "ARCHITECTURE.md", "PLAN.md"]
    out = {}
    for n in names:
        out[n] = _art(d, n, extra=_CFC if n == "PLAN.md" else "")
        assert _approve_bound(out[n], root)
    return out


def _pending_keys(root: Path) -> list:
    m = root / ".sdd" / "pending-review.json"
    return sorted(json.loads(m.read_text(encoding="utf-8"))["pending"]) if m.exists() else []


def test_sdd_wrapper_writes_bindings_for_design_and_tasks(tmp_path):
    c = _chain(tmp_path, "sdd")
    s = bc.read_stored_hash(c["spec.md"].read_text(encoding="utf-8"))
    d = bc.read_stored_hash(c["design.md"].read_text(encoding="utf-8"))
    assert bc.read_bindings(c["design.md"].read_text(encoding="utf-8")) == {"spec.md": (s,)}
    assert bc.read_bindings(c["tasks.md"].read_text(encoding="utf-8")) == {
        "spec.md": (s,), "design.md": (d,)
    }


def test_blueprint_wrapper_writes_bindings_for_architecture_and_plan(tmp_path):
    c = _chain(tmp_path, "blueprint")
    s = bc.read_stored_hash(c["SCOPE.md"].read_text(encoding="utf-8"))
    a = bc.read_stored_hash(c["ARCHITECTURE.md"].read_text(encoding="utf-8"))
    assert bc.read_bindings(c["ARCHITECTURE.md"].read_text(encoding="utf-8")) == {"SCOPE.md": (s,)}
    assert bc.read_bindings(c["PLAN.md"].read_text(encoding="utf-8")) == {
        "SCOPE.md": (s,), "ARCHITECTURE.md": (a,)
    }


def test_spec_and_scope_carry_no_binding_line(tmp_path):
    c1 = _chain(tmp_path / "a", "sdd")
    c2 = _chain(tmp_path / "b", "blueprint")
    for p in (c1["spec.md"], c2["SCOPE.md"]):
        assert "Upstream binding" not in p.read_text(encoding="utf-8")


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_bound_artifact_validates_pass_after_stamp(tmp_path, tier):
    for name, p in _chain(tmp_path, tier).items():
        r = bc.ValidationResult()
        assert bc.check_approval(p.read_text(encoding="utf-8"), name, r), r.summary()
    assert _pending_keys(tmp_path) == []


def test_binding_only_reapproval_writes_no_marker(tmp_path, capsys):
    c = _chain(tmp_path, "sdd")
    t = c["spec.md"].read_text(encoding="utf-8")
    c["spec.md"].write_text(t.replace("## Objective\n\nx\n", "## Objective\n\nedited\n"), encoding="utf-8")
    assert _approve_bound(c["spec.md"], tmp_path)
    capsys.readouterr()
    assert _approve_bound(c["design.md"], tmp_path)
    out = capsys.readouterr().out
    assert _pending_keys(tmp_path) == ["specs/feat-x/spec.md"]  # the edited spec's own
    assert "upstream binding refresh" in out
    assert bc.REAPPROVAL_REMINDER.splitlines()[0] not in out


def test_first_time_binding_reapproval_writes_no_marker(tmp_path, capsys):
    (tmp_path / ".git").mkdir()
    d = tmp_path / "specs" / "feat-x"
    sp = _art(d, "spec.md")
    assert vs.approve_document(sp, project_root=tmp_path)
    de = _art(d, "design.md")
    assert vs.approve_document(de, project_root=tmp_path)  # legacy unbound stamp
    capsys.readouterr()
    assert _approve_bound(de, tmp_path)
    out = capsys.readouterr().out
    assert _pending_keys(tmp_path) == []
    assert "upstream binding refresh" in out


def _seal_pass(p: Path, *flags: str) -> None:
    t = p.read_text(encoding="utf-8")
    sep = "|----------|--------|---------|-------------|-------|\n"
    i = t.rindex(sep) + len(sep)
    p.write_text(t[:i] + "| [MED] | critic | thing | Sealed | Defense: fine |\n" + t[i:], encoding="utf-8")
    phase = {"design.md": "2", "PLAN.md": "3"}.get(p.name, "1")
    args = [sys.executable, str(_SCRIPTS / "archive_pass.py"), str(p), "--phase", phase, *flags]
    if p.name in ("PLAN.md", "tasks.md"):
        args.append("--terminal")
    proc = subprocess.run(args, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("name", ["design.md", "PLAN.md"])
def test_seal_plus_binding_reapproval_marker_free(tmp_path, capsys, name):
    c = _chain(tmp_path, "sdd" if name == "design.md" else "blueprint")
    up = "spec.md" if name == "design.md" else "SCOPE.md"
    t = c[up].read_text(encoding="utf-8")
    c[up].write_text(t.replace("## Objective\n\nx\n", "## Objective\n\nedited\n"), encoding="utf-8")
    assert _approve_bound(c[up], tmp_path)
    before = _pending_keys(tmp_path)
    _seal_pass(c[name])
    capsys.readouterr()
    assert _approve_bound(c[name], tmp_path)
    out = capsys.readouterr().out
    assert _pending_keys(tmp_path) == before
    assert "seal promotion ([SEAL-01]) and upstream binding refresh" in out


def test_binding_reapproval_plus_edit_creates_marker(tmp_path):
    c = _chain(tmp_path, "sdd")
    t = c["design.md"].read_text(encoding="utf-8")
    c["design.md"].write_text(t.replace("## Objective\n\nx\n", "## Objective\n\nedited\n"), encoding="utf-8")
    assert _approve_bound(c["design.md"], tmp_path)
    assert _pending_keys(tmp_path) == ["specs/feat-x/design.md"]


def test_double_reapproval_single_binding_per_upstream_plan_cfc_intact(tmp_path):
    c = _chain(tmp_path, "blueprint")
    p = c["PLAN.md"]
    subprocess.run([sys.executable, str(_SCRIPTS / "archive_pass.py"), str(p), "--phase", "3",
                    "--terminal", "--strict-bar"], check=True, capture_output=True)
    assert _approve_bound(p, tmp_path)
    assert _approve_bound(p, tmp_path)
    t = p.read_text(encoding="utf-8")
    body = t[bc.approval_section_bounds(t)[0]:]
    assert body.count("`SCOPE.md`") == 1 and body.count("`ARCHITECTURE.md`") == 1
    assert body.count("**CFC Content Hashes:**") == 1
    assert set(vb.read_cfc_hashes(t)) == {1}


def test_cpd_derived_spec_fields_unchanged_no_plan_binding(tmp_path):
    (tmp_path / ".git").mkdir()
    d = tmp_path / "specs" / "residents--F7-resident-sync"
    p = fx.cpd_derived_spec(d)
    before = p.read_text(encoding="utf-8")
    assert _approve_bound(p, tmp_path)
    after = p.read_text(encoding="utf-8")
    for line in before.splitlines():
        if line.startswith("**Derived from:**") or line.startswith("**Master contract hash:**"):
            assert line in after.splitlines()
    assert "Upstream binding" not in after


def test_readers_return_own_stamp_with_binding_lines_plan_cfc(tmp_path):
    p = _chain(tmp_path, "blueprint")["PLAN.md"]
    t = p.read_text(encoding="utf-8")
    m = re.search(r"\*\*Content Hash:\*\* `([0-9a-f]{16})`", t)
    assert bc.read_stored_hash(t) == m.group(1) == bc.approval_hash(t)
    assert bc.read_bindings(t) and vb.read_cfc_hashes(t)


def test_mutated_binding_value_changes_content_hash(tmp_path):
    p = _chain(tmp_path, "sdd")["design.md"]
    t = p.read_text(encoding="utf-8")
    old = bc.read_bindings(t)["spec.md"][0]
    mutated = t.replace(f"@ `{old}`", "@ `ffffffffffffffff`")
    assert bc.compute_content_hash(mutated) != bc.compute_content_hash(t)
    r = bc.ValidationResult()
    assert not bc.check_approval(mutated, "design.md", r)


def test_crlf_file_binding_roundtrip(tmp_path):
    (tmp_path / ".git").mkdir()
    d = tmp_path / "specs" / "feat-x"
    sp = _art(d, "spec.md")
    assert vs.approve_document(sp, project_root=tmp_path)
    de = _art(d, "design.md")
    de.write_bytes(de.read_bytes().replace(b"\n", b"\r\n"))
    assert _approve_bound(de, tmp_path)
    t = de.read_text(encoding="utf-8")
    assert bc.read_bindings(t) == {"spec.md": (bc.read_stored_hash(sp.read_text(encoding="utf-8")),)}
    r = bc.ValidationResult()
    assert bc.check_approval(t, "design.md", r)


@pytest.mark.parametrize("name", ["spec.md", "PLAN.md"])
def test_wrapper_without_writes_behaves_as_before(tmp_path, name):
    (tmp_path / ".git").mkdir()
    a = _art(tmp_path / "a", name, extra=_CFC if name == "PLAN.md" else "")
    b = _art(tmp_path / "b", name, extra=_CFC if name == "PLAN.md" else "")
    mod = _mod_for(name)
    assert mod.approve_document(a, project_root=tmp_path)
    hook = vb._plan_cfc_hash_refresh if name == "PLAN.md" else None
    assert bc.approve_document(b, project_root=tmp_path, content_transform=hook)
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")


def test_verify_judged_runs_before_cfc_refresh(tmp_path, monkeypatch):
    c = _chain(tmp_path, "blueprint")
    order = []
    real_v, real_c = vb.verify_judged_transform, vb._plan_cfc_hash_refresh
    monkeypatch.setattr(vb, "verify_judged_transform", lambda c_, f, *, writes: order.append("verify") or real_v(c_, f, writes=writes))
    monkeypatch.setattr(vb, "_plan_cfc_hash_refresh", lambda c_, f: order.append("cfc") or real_c(c_, f))
    assert _approve_bound(c["PLAN.md"], tmp_path)
    assert order == ["verify", "cfc"]
    # A race refuses before any write.
    p = c["PLAN.md"]
    before = p.read_bytes()
    writes = bc.ApprovalWrites(bindings=(), judged_hash="0" * 64)
    with pytest.raises(bc.ApprovalRaceError):
        vb.approve_document(p, project_root=tmp_path, approval_writes=writes)
    assert p.read_bytes() == before


# --- T19: binding reports in validation (AD11) ------------------------------


def _checks(result, name_part):
    return [(n, sev, d) for (n, sev, d) in result.checks if name_part in n]


def _rebump(p: Path, root: Path, body: str = "edited") -> None:
    t = p.read_text(encoding="utf-8")
    p.write_text(t.replace("## Objective\n\nx\n", f"## Objective\n\n{body}\n", 1), encoding="utf-8")
    assert _approve_bound(p, root)


def _sdd_superseded(tmp_path):
    c = _chain(tmp_path, "sdd")
    a = bc.read_stored_hash(c["spec.md"].read_text(encoding="utf-8"))
    _rebump(c["spec.md"], tmp_path)
    b = bc.read_stored_hash(c["spec.md"].read_text(encoding="utf-8"))
    return c, a, b


def test_superseded_binding_fails_naming_upstream_and_both_hashes(tmp_path):
    c, a, b = _sdd_superseded(tmp_path)
    r = bc.ValidationResult()
    bc.check_upstream_bindings(c["design.md"].parent, "design.md",
                               c["design.md"].read_text(encoding="utf-8"), r)
    rows = _checks(r, "design.md upstream binding current")
    assert len(rows) == 1 and rows[0][1] == bc.Severity.FAIL
    detail = rows[0][2]
    assert "spec.md" in detail and a in detail and b in detail
    assert "newer-stamp" in detail


def test_superseded_fail_message_walk_top_down_and_seal_note(tmp_path):
    c, a, b = _sdd_superseded(tmp_path)
    r = vs.validate_design(c["design.md"].parent)
    detail = _checks(r, "design.md upstream binding current")[0][2]
    assert "Spec-Design consistency check" in detail
    assert "top-down" in detail and "further FAIL" in detail
    assert "seal-promotion re-stamp" in detail
    assert bc.GLOSS_SUPERSEDED in detail
    assert "design.md was approved against an older spec.md" in detail


def test_unbound_downstream_warns_never_fails(tmp_path):
    (tmp_path / ".git").mkdir()
    d = tmp_path / "specs" / "feat-x"
    sp = _art(d, "spec.md")
    assert vs.approve_document(sp, project_root=tmp_path)
    de = _art(d, "design.md")
    assert vs.approve_document(de, project_root=tmp_path)  # no writes: unbound
    r = vs.validate_design(d)
    rows = _checks(r, "design.md upstream binding current")
    assert len(rows) == 1 and rows[0][1] == bc.Severity.WARN
    assert "spec.md" in rows[0][2] and "--approve design" in rows[0][2]
    assert bc.GLOSS_UNBOUND in rows[0][2]


def test_partial_binding_warns_naming_missing_upstreams(tmp_path):
    c = _chain(tmp_path, "sdd")
    p = c["tasks.md"]
    t = p.read_text(encoding="utf-8")
    line = next(ln for ln in t.splitlines() if "`design.md` @" in ln)
    t = t.replace(line + "\n", "")
    stamp = bc.compute_content_hash(bc.trim_trajectory_table(t))
    t = re.sub(r"(\*\*Content Hash:\*\* `)[0-9a-f]{16}", r"\g<1>" + stamp, t)
    p.write_text(t, encoding="utf-8")
    r = bc.ValidationResult()
    bc.check_upstream_bindings(p.parent, "tasks.md", t, r)
    rows = _checks(r, "tasks.md upstream binding current")
    assert [s for _n, s, _d in rows] == [bc.Severity.WARN]
    assert "design.md" in rows[0][2] and "for spec.md" not in rows[0][2]


def test_duplicate_binding_lines_superseded(tmp_path):
    c = _chain(tmp_path, "sdd")
    t = c["design.md"].read_text(encoding="utf-8")
    line = next(ln for ln in t.splitlines() if "`spec.md` @" in ln)
    t2 = t.replace(line, line + "\n" + line)
    rep = bc.binding_report("design.md", t2, {"spec.md": c["spec.md"].read_text(encoding="utf-8")})
    assert [(s.upstream, s.reason) for s in rep.superseded] == [("spec.md", "duplicate")]


def test_unapproved_upstream_superseded(tmp_path):
    c = _chain(tmp_path, "sdd")
    t = c["design.md"].read_text(encoding="utf-8")
    pending_spec = re.sub(r"`[0-9a-f]{16}`", "`pending`", c["spec.md"].read_text(encoding="utf-8"))
    rep = bc.binding_report("design.md", t, {"spec.md": pending_spec})
    assert [s.reason for s in rep.superseded] == ["upstream-unapproved"]
    rep2 = bc.binding_report("design.md", t, {"spec.md": None})
    assert [s.reason for s in rep2.superseded] == ["upstream-unapproved"]


def test_uppercase_upstream_stamp_binds_and_compares(tmp_path):
    c = _chain(tmp_path, "sdd")
    spec = c["spec.md"].read_text(encoding="utf-8")
    h = bc.read_stored_hash(spec)
    upper = spec.replace(f"`{h}`", f"`{h.upper()}`")
    rep = bc.binding_report("design.md", c["design.md"].read_text(encoding="utf-8"), {"spec.md": upper})
    assert rep.superseded == () and rep.unbound == ()


def test_draft_downstream_gets_no_binding_row(tmp_path):
    (tmp_path / ".git").mkdir()
    d = tmp_path / "specs" / "feat-x"
    sp = _art(d, "spec.md")
    assert vs.approve_document(sp, project_root=tmp_path)
    _art(d, "design.md")  # never approved
    r = vs.validate_design(d)
    assert _checks(r, "upstream binding current") == []
    assert bc.binding_report("design.md", (d / "design.md").read_text(encoding="utf-8"), {}) == bc.BindingReport((), ())


def test_exempt_own_binding_suppresses_target_fail(tmp_path):
    c, _a, _b = _sdd_superseded(tmp_path)
    r = vs.validate_design(c["design.md"].parent, exempt_own_binding=True)
    assert [x for x in _checks(r, "design.md upstream binding current") if x[1] == bc.Severity.FAIL] == []
    for fn, d in ((vb.validate_architecture, None), (vb.validate_plan, None)):
        import inspect
        assert "exempt_own_binding" in inspect.signature(fn).parameters
    import inspect
    assert "exempt_own_binding" in inspect.signature(vs.validate_tasks).parameters


def test_validate_tasks_reports_design_superseded_via_previous_phase(tmp_path):
    c, a, b = _sdd_superseded(tmp_path)
    r = vs.validate_tasks(c["tasks.md"].parent, exempt_own_binding=True)
    rows = [x for x in r.checks if "design.md" in x[0] and "upstream binding current" in x[0]]
    assert rows and rows[0][1] == bc.Severity.FAIL
    assert a in rows[0][2] and b in rows[0][2]


def test_binding_glosses_literal():
    assert bc.GLOSS_BINDING == (
        "an upstream binding records which approved version of each upstream "
        "document this one was approved against"
    )
    assert bc.GLOSS_SUPERSEDED == (
        "superseded means this document was approved against an older version of "
        "its upstream, which has since been re-approved or changed"
    )
    assert bc.GLOSS_UNBOUND == (
        "unbound means there is no record of which upstream version this document "
        "was approved against"
    )


# --- T20: --run-state drift obligations and unbound notices (AD17) ----------

import run_state as rs  # noqa: E402

_PH = {
    "sdd": ([("Specify", "spec.md"), ("Design", "design.md"), ("Tasks", "tasks.md")], "Implement", "tasks.md"),
    "blueprint": ([("Scope", "SCOPE.md"), ("Architecture", "ARCHITECTURE.md"), ("Plan", "PLAN.md")], None, None),
}


def _derive(root: Path, d: Path, tier: str):
    phases, term, tick = _PH[tier]
    return rs.derive_run_state(tier=tier, artifact_dir=d, project_root=root, phases=phases,
                               terminal_phase_label=term, tick_hint_artifact=tick)


def _unbound_chain(root: Path, tier: str) -> "dict[str, Path]":
    """A pre-release-style chain: every artifact approved with no bindings."""
    (root / ".git").mkdir(parents=True, exist_ok=True)
    d = root / ("specs/feat-x" if tier == "sdd" else "blueprint")
    names = [n for _l, n in _PH[tier][0]]
    out = {}
    for n in names:
        out[n] = _art(d, n, extra=_CFC if n == "PLAN.md" else "")
        assert _mod_for(n).approve_document(out[n], project_root=root)
    return out


def test_run_state_upstream_drift_obligation_per_superseded_binding(tmp_path):
    c = _chain(tmp_path, "sdd")
    a = bc.read_stored_hash(c["spec.md"].read_text(encoding="utf-8"))
    _rebump(c["spec.md"], tmp_path, body="12 requirements now")
    b = bc.read_stored_hash(c["spec.md"].read_text(encoding="utf-8"))
    # clear the spec's own re-review obligation so only drift remains
    (tmp_path / ".sdd" / "pending-review.json").unlink()
    state = _derive(tmp_path, c["spec.md"].parent, "sdd")
    drift = [o for o in state.obligations if o.kind == rs.OBLIGATION_UPSTREAM_DRIFT]
    assert [o.detail.split(" ")[0] for o in drift] == ["design.md", "tasks.md"]
    for o in drift:
        assert "spec.md" in o.detail and a[:8] in o.detail and b[:8] in o.detail
        assert o.next_action.startswith("run the consistency check, then re-approve ")
        assert o.next_action.endswith(", top-down")
        assert "decline" not in o.next_action
    out = rs.format_run_state(state)
    assert "all clear" not in out


def test_run_state_unbound_qualified_all_clear(tmp_path):
    c = _unbound_chain(tmp_path, "sdd")
    state = _derive(tmp_path, c["spec.md"].parent, "sdd")
    lines = rs.format_run_state(state).splitlines()
    assert lines[1].startswith("all clear (upstream binding unverified) — ")
    unbound = [n for n in state.notices if n.kind == rs.NOTICE_UNBOUND]
    assert [n.subject for n in unbound] == ["design.md", "tasks.md"]
    assert any(bc.GLOSS_UNBOUND in ln for ln in lines)


def test_run_state_drift_wording_identical_both_tiers(tmp_path):
    out = {}
    for tier, up in (("sdd", "spec.md"), ("blueprint", "SCOPE.md")):
        root = tmp_path / tier
        c = _chain(root, tier)
        _rebump(c[up], root)
        (root / ".sdd" / "pending-review.json").unlink()
        st = _derive(root, c[up].parent, tier)
        drift = [o for o in st.obligations if o.kind == rs.OBLIGATION_UPSTREAM_DRIFT]
        out[tier] = [
            re.sub(r"[0-9a-f]{8}", "H", o.detail).replace(up, "UP").split(" ", 1)[1] for o in drift
        ], [o.next_action.split("re-approve ")[0] for o in drift]
    assert out["sdd"][1] == out["blueprint"][1]
    assert out["sdd"][0][0] == out["blueprint"][0][0]


def test_item34_unbound_chain_qualified_output(tmp_path):
    c = _unbound_chain(tmp_path, "blueprint")
    state = _derive(tmp_path, c["SCOPE.md"].parent, "blueprint")
    out = rs.format_run_state(state)
    assert out.splitlines()[1].startswith("all clear (upstream binding unverified) — ")
    assert [n.subject for n in state.notices if n.kind == rs.NOTICE_UNBOUND] == ["ARCHITECTURE.md", "PLAN.md"]


def test_item34_half_walked_chain_names_only_tasks(tmp_path):
    c = _unbound_chain(tmp_path, "sdd")
    assert _approve_bound(c["design.md"], tmp_path)
    state = _derive(tmp_path, c["spec.md"].parent, "sdd")
    assert [n.subject for n in state.notices if n.kind == rs.NOTICE_UNBOUND] == ["tasks.md"]
    assert rs.format_run_state(state).splitlines()[1].startswith("all clear (upstream binding unverified)")


def _thirty_scopes(root: Path) -> None:
    for i in range(1, 31):
        bc.upsert_pending_entry(root, f"other/F{i:02d}-s/spec.md", "a" * 16, "t", 1)
        (root / "other" / f"F{i:02d}-s").mkdir(parents=True, exist_ok=True)


def _collapse_thirty_scopes_and_unbound(tmp_path, tier):
    c = _unbound_chain(tmp_path, tier)
    d = next(iter(c.values())).parent
    first = next(iter(c))
    bc.upsert_pending_entry(tmp_path, f"{d.relative_to(tmp_path).as_posix()}/{first}", "b" * 16, "t", 1)
    bc.upsert_pending_entry(tmp_path, f"{d.relative_to(tmp_path).as_posix()}/{list(c)[1]}", "c" * 16, "t", 1)
    _thirty_scopes(tmp_path)
    lines = rs.format_run_state(_derive(tmp_path, d, tier)).splitlines()
    assert len(lines) <= 24
    pe = [ln for ln in lines if "pending elsewhere" in ln]
    ub = [ln for ln in lines if ln.lstrip().startswith("unbound:")]
    assert pe == [
        "  pending elsewhere — not resolvable from here: other/F01-s (1), other/F02-s (1), "
        "other/F03-s (1) and 27 more — resolve each from its own directory, starting with "
        "`validate_spec.py ./other/F01-s --run-state`"
    ]
    names = [n for n in c][1:]
    assert len(ub) == 1 and ub[0].startswith(f"  unbound: {', '.join(names)} — ")
    assert bc.GLOSS_UNBOUND in ub[0]


def test_collapse_fixture_thirty_scopes_and_unbound_sdd(tmp_path):
    _collapse_thirty_scopes_and_unbound(tmp_path, "sdd")


def test_collapse_fixture_thirty_scopes_and_unbound_blueprint(tmp_path):
    _collapse_thirty_scopes_and_unbound(tmp_path, "blueprint")


def test_expanded_notices_companion_case(tmp_path):
    c = _unbound_chain(tmp_path, "sdd")
    (tmp_path / "specs" / "F1-a").mkdir(parents=True)
    (tmp_path / "specs" / "F2-b").mkdir(parents=True)
    bc.upsert_pending_entry(tmp_path, "specs/F1-a/spec.md", "a" * 16, "t", 1)
    bc.upsert_pending_entry(tmp_path, "specs/F2-b/spec.md", "a" * 16, "t", 1)
    assert _approve_bound(c["design.md"], tmp_path)
    lines = rs.format_run_state(_derive(tmp_path, c["spec.md"].parent, "sdd")).splitlines()
    assert sum(1 for ln in lines if "pending elsewhere" in ln) == 2
    assert [ln for ln in lines if ln.lstrip().startswith("unbound:")][0].startswith("  unbound: tasks.md — ")
