"""Unit C0 R2 — the restamp-delta classifier (AD13) and its create-arm wiring.

Scenarios are built on the real tools: a document is approved through the
`approve_document` core, then `archive_pass.py` runs, then the classifier is fed
exactly the inputs the next re-stamp would compute.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _p in (str(_SCRIPTS), str(_TESTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import blueprint_common as bc  # noqa: E402
import pending_review as pr  # noqa: E402
import trajectory as tr  # noqa: E402
import _fixtures as fx  # noqa: E402

_ARCHIVE = _SCRIPTS / "archive_pass.py"
_TERMINAL = {"tasks.md", "PLAN.md"}
_PHASE = {"spec.md": 1, "SCOPE.md": 1, "design.md": 2, "ARCHITECTURE.md": 2, "tasks.md": 3, "PLAN.md": 3}
TAG = "upstream-panel 1234abcd"


def _skeleton(name: str, *, deferred: bool = True, body: str = "x") -> str:
    deferred_block = ""
    if deferred and name not in _TERMINAL:
        deferred_block = (
            "### Deferred dispositions\n\n"
            "<!-- Auto-populated by archive_pass.py. -->\n\n"
        )
    return (
        f"# Doc\n\n## Objective\n\n{body}\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "\n"
        "### Sealed dispositions\n\n"
        "_None yet._\n\n"
        f"{deferred_block}"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )


def _approved(root: Path, name: str = "spec.md", *, passes: int = 1, deferred: bool = True,
              row_notes=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    text = _skeleton(name, deferred=deferred)
    for i in range(passes):
        notes = (row_notes or {}).get(i + 1)
        text = fx.add_converged_closing_row(text, **({"notes": notes} if notes else {}))
    p = root / name
    p.write_text(text, encoding="utf-8")
    assert bc.approve_document(p, project_root=root)
    return p


def _add_latest(p: Path, *rows: str) -> None:
    t = p.read_text(encoding="utf-8")
    sep = "|----------|--------|---------|-------------|-------|\n"
    i = t.rindex(sep) + len(sep)
    p.write_text(t[:i] + "".join(r + "\n" for r in rows) + t[i:], encoding="utf-8")


def _archive(p: Path, *flags: str) -> None:
    args = [sys.executable, str(_ARCHIVE), str(p), "--phase", str(_PHASE[p.name]), *flags]
    if p.name in _TERMINAL:
        args.append("--terminal")
    proc = subprocess.run(args, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def _seal(concern: str = "a thing", sev: str = "MED") -> str:
    return f"| [{sev}] | critic | {concern} | Sealed | Defense: fine |"


def _classify(p: Path, transform=None):
    orig = p.read_text(encoding="utf-8-sig")
    trimmed = bc.trim_trajectory_table(orig)
    final = transform(trimmed) if transform else trimmed
    return pr.classify_restamp_delta(
        stored_hash=bc.read_stored_hash(orig), original_content=orig,
        content_trimmed=trimmed, final_content=final,
    )


def _edit(p: Path, old: str, new: str, count: int = 1) -> None:
    t = p.read_text(encoding="utf-8")
    assert old in t, old
    p.write_text(t.replace(old, new, count), encoding="utf-8")


def _row_line(p: Path, pass_no: int) -> str:
    return next(ln for ln in p.read_text(encoding="utf-8").splitlines()
                if re.match(rf"^\| {pass_no}\s+\|", ln))


def _hand_tag(p: Path, pass_no: int, sep: str = "; ") -> None:
    line = _row_line(p, pass_no)
    body = line.rstrip().rstrip("|").rstrip()
    _edit(p, line, f"{body}{sep}{TAG} |")


# --- T16: the pure classifier -----------------------------------------------


def test_classifier_recognises_seal_promotion_only(tmp_path):
    p = _approved(tmp_path)
    _add_latest(p, _seal())
    _archive(p)
    d = _classify(p)
    assert d == pr.RestampDelta(promoted_seals=("SEAL-01",), binding_refresh=False, repad=False)


def test_classifier_recognises_binding_refresh_only(tmp_path):
    p = _approved(tmp_path, "design.md")
    b = (bc.UpstreamBinding("spec.md", "0123456789abcdef"),)
    d = _classify(p, lambda t: bc.upsert_binding_lines(t, b))
    assert d == pr.RestampDelta(promoted_seals=(), binding_refresh=True, repad=False)


def test_classifier_recognises_pure_archive_repad(tmp_path):
    p = _approved(tmp_path)
    _archive(p, "--strict-bar")  # empty Latest; the wider strict-bar Notes re-pads
    d = _classify(p)
    assert d == pr.RestampDelta(promoted_seals=(), binding_refresh=False, repad=True)


def test_classifier_repad_plus_newest_row_hand_tag(tmp_path):
    p = _approved(tmp_path)
    _archive(p, "--strict-bar")
    _hand_tag(p, 2)
    d = _classify(p)
    assert d is not None and d.repad is True and d.promoted_seals == ()


def test_classifier_hand_tag_semicolon_delimiter_spec(tmp_path):
    p = _approved(tmp_path, "spec.md")
    _hand_tag(p, 1, "; ")
    _add_latest(p, _seal())
    _archive(p)
    d = _classify(p)
    assert d is not None and d.promoted_seals == ("SEAL-01",)


def test_classifier_hand_tag_space_delimiter_plan(tmp_path):
    p = _approved(tmp_path, "PLAN.md")
    _hand_tag(p, 1, " ")
    _add_latest(p, _seal())
    _archive(p)
    d = _classify(p)
    assert d is not None and d.promoted_seals == ("SEAL-01",)


def test_classifier_candidate_iv_matches_older_row_tag_only(tmp_path):
    root = tmp_path
    p = _approved(root, passes=2)
    # Tag the OLDER row after the last archive, then re-approve (stamp keeps
    # the untagged widths), then archive a sealing pass that re-renders.
    _hand_tag(p, 1)
    assert bc.approve_document(p, project_root=root)
    _add_latest(p, _seal())
    _archive(p)
    d = _classify(p)
    assert d is not None and d.promoted_seals == ("SEAL-01",)


def test_classifier_candidate_iii_matches_newest_row_tag(tmp_path):
    root = tmp_path
    p = _approved(root, passes=2)
    _hand_tag(p, 2)
    assert bc.approve_document(p, project_root=root)
    _add_latest(p, _seal())
    _archive(p)
    d = _classify(p)
    assert d is not None and d.promoted_seals == ("SEAL-01",)


def test_classifier_tries_both_blank_line_forms(tmp_path):
    # First seal into an empty section: archive inserts a blank line too.
    p = _approved(tmp_path / "a")
    _add_latest(p, _seal())
    _archive(p)
    assert _classify(p).promoted_seals == ("SEAL-01",)
    # A later seal appended after an existing entry: no blank line.
    q = _approved(tmp_path / "b")
    _add_latest(q, _seal("first"))
    _archive(q)
    assert bc.approve_document(q, project_root=tmp_path / "b")
    _add_latest(q, _seal("second"))
    _archive(q)
    assert _classify(q).promoted_seals == ("SEAL-02",)


def test_classifier_reworded_defense_unrecognised(tmp_path):
    p = _approved(tmp_path)
    _add_latest(p, _seal("first"))
    _archive(p)
    assert bc.approve_document(p, project_root=tmp_path)
    _add_latest(p, _seal("second"))
    _archive(p)
    _edit(p, "**first** (pass 2, user-directed) — Defense: fine.",
          "**first** (pass 2, user-directed) — Defense: reworded.")
    assert _classify(p) is None


def test_classifier_def_promotion_unrecognised(tmp_path):
    p = _approved(tmp_path)
    _add_latest(p, "| [MED] | critic | later | Deferred → design.md | Routed because: it is design work |")
    _archive(p)
    assert _classify(p) is None


def test_classifier_reworded_header_plus_seal_unrecognised(tmp_path):
    p = _approved(tmp_path)
    _add_latest(p, _seal())
    _archive(p)
    t = p.read_text(encoding="utf-8")
    hdr = next(ln for ln in t.splitlines() if ln.startswith("| Pass "))
    _edit(p, hdr, hdr.replace("| Notes ", "| Notez "))
    assert _classify(p) is None


@pytest.mark.parametrize("with_seal", [False, True])
def test_classifier_hand_padded_header_unrecognised(tmp_path, with_seal):
    p = _approved(tmp_path)
    if with_seal:
        _add_latest(p, _seal())
        _archive(p)
    t = p.read_text(encoding="utf-8")
    hdr = next(ln for ln in t.splitlines() if ln.startswith("| Pass "))
    sep = t.splitlines()[t.splitlines().index(hdr) + 1]
    _edit(p, hdr + "\n" + sep, hdr.replace("| Pass ", "| Pass   ") + "\n" + sep.replace("|------|", "|--------|", 1))
    assert _classify(p) is None


@pytest.mark.parametrize("case", ["pass-absent", "count-over-sealed", "non-sequential"])
def test_classifier_seal_without_table_evidence_unrecognised(tmp_path, case):
    p = _approved(tmp_path)
    _add_latest(p, _seal())
    _archive(p)
    entry = "- `[SEAL-01]` **a thing** (pass 2, user-directed) — Defense: fine."
    if case == "pass-absent":
        _edit(p, entry, entry.replace("(pass 2,", "(pass 9,"))
    elif case == "count-over-sealed":
        _edit(p, entry, entry + "\n" + entry.replace("SEAL-01", "SEAL-02").replace("a thing", "extra"))
    else:
        _edit(p, entry, entry.replace("SEAL-01", "SEAL-03"))
    assert _classify(p) is None


def test_classifier_producer_delta_unrecognised(tmp_path):
    p = _approved(tmp_path, "PLAN.md")
    _add_latest(p, _seal())
    _archive(p)

    def cfc(t):
        return t.replace("- **Content Hash:**", "- **CFC Content Hashes:**\n  - CFC-1: `abcdef0123456789`\n- **Content Hash:**")

    assert _classify(p) is not None
    assert _classify(p, cfc) is None


def test_classifier_deferred_auto_insert_unrecognised(tmp_path):
    p = _approved(tmp_path, deferred=False)
    _add_latest(p, _seal())
    _archive(p)
    assert "### Deferred dispositions" in p.read_text(encoding="utf-8")
    assert _classify(p) is None


def test_classifier_trim_elision_fails_safe(tmp_path):
    long = "converged (0 HIGH); " + "a very long hand note " * 4
    p = _approved(tmp_path, passes=16, row_notes={1: long.strip()})
    assert "earlier passes elided" in p.read_text(encoding="utf-8")
    _add_latest(p, _seal())
    _archive(p)
    assert _classify(p) is None


def test_classifier_escaped_pipe_repad_fails_safe(tmp_path):
    p = _approved(tmp_path, row_notes={1: "a \\| b converged (0 HIGH) widest note here"})
    _archive(p, "--strict-bar")
    assert _classify(p) is None


@pytest.mark.parametrize("seal_pass,expected", [(2, None), (19, ("SEAL-01",))])
def test_classifier_cut_points_capped_at_16(tmp_path, seal_pass, expected):
    """With passes 1..20 in the table, a pass-2 seal needs cut point K=1, the
    20th-newest pass — beyond the 15-pass cap, so it is not tried (create arm).
    A pass-19 seal needs K=18, within the cap."""
    p = _approved(tmp_path, passes=20)
    t = p.read_text(encoding="utf-8")
    elided = next(ln for ln in t.splitlines() if "earlier passes elided" in ln)
    row6 = _row_line(p, 6)
    restored = "\n".join(row6.replace("| 6 ", f"| {k} ", 1) for k in range(1, 6))
    _edit(p, elided, restored)  # data rows are hash-excluded
    target = _row_line(p, seal_pass)
    cells = target.split("|")
    cells[7] = cells[7].replace("0", "1", 1)
    _edit(p, target, "|".join(cells))
    _edit(p, "### Sealed dispositions\n\n_None yet._",
          f"### Sealed dispositions\n\n- `[SEAL-01]` **x** (pass {seal_pass}, user-directed) — Defense: d.\n\n_None yet._")
    d = _classify(p)
    if expected is None:
        assert d is None
    else:
        assert d is not None and d.promoted_seals == expected


# --- T17: the classifier in the re-stamp create arm -------------------------

import json  # noqa: E402

from approval_records import (  # noqa: E402
    REPAD_PART,
    RESTAMP_CARVE_OUT_PREFIX,
    SEAL_PART,
)

_VS = _SCRIPTS.parent / "skills" / "spec-driven-dev" / "scripts" / "validate_spec.py"
_VB = _SCRIPTS.parent / "skills" / "project-blueprint" / "scripts" / "validate_blueprint.py"
_KIND = {  # name -> (tier, phase flag, directory)
    "spec.md": ("sdd", "spec", "specs/feat-x"),
    "design.md": ("sdd", "design", "specs/feat-x"),
    "tasks.md": ("sdd", "tasks", "specs/feat-x"),
    "SCOPE.md": ("blueprint", "scope", "blueprint"),
    "ARCHITECTURE.md": ("blueprint", "architecture", "blueprint"),
    "PLAN.md": ("blueprint", "plan", "blueprint"),
}
_UPSTREAMS = {
    "design.md": ("spec.md",), "tasks.md": ("spec.md", "design.md"),
    "ARCHITECTURE.md": ("SCOPE.md",), "PLAN.md": ("SCOPE.md", "ARCHITECTURE.md"),
}
_CFC = (
    "## Cross-Feature Contracts\n\n"
    "### CFC-1: Shared ids\n\n"
    "- **Participating features:** F1, F2\n"
    "- **Contract:** ids are stable.\n"
    "- **Per-feature AC:** GIVEN an id WHEN read THEN it is stable [CFC-1]\n"
    "- **Enforcement:** F1 owns the check.\n\n"
)
_REMINDER = bc.REAPPROVAL_REMINDER.splitlines()[0]


def _stamped_upstream(d: Path, name: str) -> None:
    (d / name).write_text(
        "# Up\n\n**PLAN feature identifier:** `n/a`\n\n## Objective\n\nx\n\n"
        "## Approval\n\n- [x] Approved to proceed to next phase\n"
        "- **Content Hash:** `00112233aabbccdd`\n",
        encoding="utf-8",
    )


def _cli_approve(root: Path, name: str) -> "subprocess.CompletedProcess[str]":
    tier, flag, rel = _KIND[name]
    script = _VS if tier == "sdd" else _VB
    return subprocess.run(
        [sys.executable, str(script), str(root / rel), "--approve", flag, "--force",
         "--project-root", str(root)],
        capture_output=True, text=True,
    )


def _matrix_fixture(root: Path, name: str, widen: bool) -> Path:
    """Approved artifact whose stamp-time Sealed section holds [SEAL-01]; then
    a pass promoting [SEAL-02] (widening Notes when `widen`)."""
    tier, _flag, rel = _KIND[name]
    d = root / rel
    d.mkdir(parents=True)
    (root / ".git").mkdir(exist_ok=True)
    for up in _UPSTREAMS.get(name, ()):
        _stamped_upstream(d, up)
    text = _skeleton(name).replace(
        "## Objective\n\nx\n",
        "**PLAN feature identifier:** `n/a`\n\n## Objective\n\nx\n"
        + ("\n" + _CFC if name == "PLAN.md" else ""),
    )
    p = d / name
    p.write_text(text, encoding="utf-8")
    _add_latest(p, _seal("existing"))
    _archive(p)
    proc = _cli_approve(root, name)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    _add_latest(p, _seal("promoted"))
    _archive(p, *(["--strict-bar"] if widen else []))
    return p


def _pending_keys(root: Path) -> list:
    m = root / ".sdd" / "pending-review.json"
    return sorted(json.loads(m.read_text(encoding="utf-8"))["pending"]) if m.exists() else []


@pytest.mark.parametrize("widen", [False, True], ids=["narrow", "widen"])
@pytest.mark.parametrize("scenario", ["AC-2.1", "AC-2.2"])
@pytest.mark.parametrize("name", list(_KIND))
def test_seal_promotion_matrix_through_tier_approve(tmp_path, name, scenario, widen):
    p = _matrix_fixture(tmp_path, name, widen)
    if scenario == "AC-2.2":
        _edit(p, "**existing** (pass 1, user-directed) — Defense: fine.",
              "**existing** (pass 1, user-directed) — Defense: reworded.")
    proc = _cli_approve(tmp_path, name)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = proc.stdout
    carve = [ln for ln in out.splitlines() if ln.startswith("restamp-carve-out:")]
    key = f"{_KIND[name][2]}/{name}"
    if scenario == "AC-2.1":
        assert _pending_keys(tmp_path) == []
        assert _REMINDER not in out
        assert len(carve) == 1 and "[SEAL-02]" in carve[0] and key in carve[0]
    else:
        assert _pending_keys(tmp_path) == [key]
        assert _REMINDER in out
        assert carve == []


def test_other_hashed_edit_creates_marker(tmp_path):
    p = _approved(tmp_path)
    _add_latest(p, _seal())
    _archive(p)
    _edit(p, "## Objective\n\nx\n", "## Objective\n\nchanged\n")
    assert bc.approve_document(p, project_root=tmp_path)
    assert _pending_keys(tmp_path) == ["spec.md"]


def test_preserve_arm_unchanged_with_open_obligation(tmp_path, capsys):
    p = _approved(tmp_path)
    _edit(p, "## Objective\n\nx\n", "## Objective\n\nchanged\n")
    assert bc.approve_document(p, project_root=tmp_path)
    before = (tmp_path / ".sdd" / "pending-review.json").read_text(encoding="utf-8")
    capsys.readouterr()
    _add_latest(p, _seal())
    _archive(p)
    assert bc.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    assert "r9-preserve:" in out and "restamp-carve-out:" not in out
    after = json.loads((tmp_path / ".sdd" / "pending-review.json").read_text(encoding="utf-8"))
    assert after["pending"]["spec.md"]["hash"] == json.loads(before)["pending"]["spec.md"]["hash"]


def test_classifier_exception_creates_marker_and_no_carve_out_line(tmp_path, capsys, monkeypatch):
    p = _approved(tmp_path)
    _add_latest(p, _seal())
    _archive(p)

    def boom(**kw):
        raise ValueError("classifier bug")

    monkeypatch.setattr(pr, "classify_restamp_delta", boom)
    capsys.readouterr()
    assert bc.approve_document(p, project_root=tmp_path)
    out = capsys.readouterr().out
    assert _pending_keys(tmp_path) == ["spec.md"]
    assert "restamp-carve-out:" not in out and _REMINDER in out


def _approve_out(p: Path, root: Path, capsys) -> str:
    capsys.readouterr()
    assert bc.approve_document(p, project_root=root)
    return capsys.readouterr().out


def test_i9_line_exact_seal_only_repad_only_and_seal_plus_repad(tmp_path, capsys):
    prefix = RESTAMP_CARVE_OUT_PREFIX.format(doc_rel="spec.md")
    a = _approved(tmp_path / "a")
    _add_latest(a, _seal())
    _archive(a)
    out = _approve_out(a, tmp_path / "a", capsys)
    assert prefix + SEAL_PART.format(ids="[SEAL-01]") in out.splitlines()
    assert prefix == "restamp-carve-out: spec.md re-stamped with no pending-review marker — "
    assert SEAL_PART.format(ids="[SEAL-01]") == "seal promotion ([SEAL-01])"
    b = _approved(tmp_path / "b")
    _archive(b, "--strict-bar")
    out = _approve_out(b, tmp_path / "b", capsys)
    assert prefix + REPAD_PART in out.splitlines()
    assert REPAD_PART == "Trajectory table re-pad"
    c = _approved(tmp_path / "c")
    _add_latest(c, _seal("one"), _seal("two"))
    _archive(c, "--strict-bar")
    out = _approve_out(c, tmp_path / "c", capsys)
    assert (prefix + "seal promotion ([SEAL-01], [SEAL-02]) and Trajectory table re-pad") in out.splitlines()


def test_exactly_one_i9_line_per_approve(tmp_path, capsys):
    p = _approved(tmp_path)
    _add_latest(p, _seal())
    _archive(p, "--strict-bar")
    out = _approve_out(p, tmp_path, capsys)
    assert sum(1 for ln in out.splitlines() if ln.startswith("restamp-carve-out:")) == 1
    assert _REMINDER not in out


def test_final_content_is_pre_rewrite_snapshot(tmp_path, capsys, monkeypatch):
    p = _approved(tmp_path, "design.md")
    _add_latest(p, _seal())
    _archive(p)
    seen = {}
    real = pr.classify_restamp_delta

    def spy(**kw):
        seen.update(kw)
        return real(**kw)

    monkeypatch.setattr(pr, "classify_restamp_delta", spy)
    writes = bc.ApprovalWrites(bindings=(bc.UpstreamBinding("spec.md", "0123456789abcdef"),))
    stored = bc.read_stored_hash(p.read_text(encoding="utf-8"))
    out = capsys.readouterr()
    assert bc.approve_document(
        p, project_root=tmp_path,
        content_transform=bc.compose_content_transforms(
            lambda c, f: bc.apply_approval_writes(c, f, writes=writes)
        ),
    )
    out = capsys.readouterr().out
    assert "Upstream binding" in seen["final_content"]
    assert f"`{stored}`" in seen["final_content"]  # stamp not yet rewritten
    assert "seal promotion ([SEAL-01]) and upstream binding refresh" in out


# --- T18: both carve-out paths share the classifier --------------------------


def test_classifier_called_on_both_carve_out_paths(tmp_path, monkeypatch, capsys):
    calls = []
    real = pr.classify_restamp_delta
    monkeypatch.setattr(pr, "classify_restamp_delta", lambda **kw: calls.append(1) or real(**kw))
    a = _approved(tmp_path / "a")
    _add_latest(a, _seal())
    _archive(a)
    assert bc.approve_document(a, project_root=tmp_path / "a")  # AC-2.1 path
    b = _approved(tmp_path / "b", "design.md")
    (tmp_path / "b" / "spec.md").write_text(
        "# s\n\n## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `0123456789abcdef`\n",
        encoding="utf-8",
    )
    w = bc.ApprovalWrites(bindings=(bc.UpstreamBinding("spec.md", "0123456789abcdef"),),
                          judged_hash=bc.judged_text_hash(b.read_text(encoding="utf-8")))
    assert bc.approve_document(b, project_root=tmp_path / "b", content_transform=bc.compose_content_transforms(
        lambda c, f: bc.verify_judged_transform(c, f, writes=w),
        lambda c, f: bc.apply_approval_writes(c, f, writes=w)))  # AC-3.3 path
    assert len(calls) == 2
    out = capsys.readouterr().out
    assert out.count("restamp-carve-out:") == 2


def test_i9_line_exact_binding_only_and_all_three_parts(tmp_path, capsys):
    from approval_records import BINDING_PART

    assert BINDING_PART == "upstream binding refresh"
    b = _approved(tmp_path / "b", "design.md")
    (tmp_path / "b" / "spec.md").write_text(
        "# s\n\n## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `0123456789abcdef`\n",
        encoding="utf-8",
    )

    def bind(p):
        w = bc.ApprovalWrites(bindings=bc.collect_upstream_bindings(p.parent, "design.md"),
                              judged_hash=bc.judged_text_hash(p.read_text(encoding="utf-8")))
        return bc.compose_content_transforms(
            lambda c, f: bc.verify_judged_transform(c, f, writes=w),
            lambda c, f: bc.apply_approval_writes(c, f, writes=w))

    capsys.readouterr()
    assert bc.approve_document(b, project_root=tmp_path / "b", content_transform=bind(b))
    prefix = RESTAMP_CARVE_OUT_PREFIX.format(doc_rel="design.md")
    assert prefix + BINDING_PART in capsys.readouterr().out.splitlines()
    (tmp_path / "b" / "spec.md").write_text(
        "# s\n\n## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `fedcba9876543210`\n",
        encoding="utf-8",
    )
    _add_latest(b, _seal())
    _archive(b, "--strict-bar")
    capsys.readouterr()
    assert bc.approve_document(b, project_root=tmp_path / "b", content_transform=bind(b))
    assert (prefix + "seal promotion ([SEAL-01]) and upstream binding refresh and Trajectory table re-pad") in capsys.readouterr().out.splitlines()
