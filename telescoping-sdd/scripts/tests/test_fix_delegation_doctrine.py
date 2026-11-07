"""Unit D: fix delegation (R1-R3) — script support and doctrine pins.

This file starts with the `--fail-keys` baseline mode (AD6, I4): the
multiset of FAIL check names the orchestrator compares before and after a
promote, with approval-state keys excluded by pattern. Later Unit D tasks
add the doctrine-text pins for R1-R3 below it.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
_TESTS = _SCRIPTS / "tests"
for _p in (_SCRIPTS, _TESTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import _fixtures as fx  # noqa: E402
import blueprint_common as bc  # noqa: E402

_VS = _SCRIPTS.parent / "skills" / "spec-driven-dev" / "scripts" / "validate_spec.py"
_VB = _SCRIPTS.parent / "skills" / "project-blueprint" / "scripts" / "validate_blueprint.py"
_SCRIPT = {"sdd": _VS, "blueprint": _VB}
_FIRST_TWO = {"sdd": ["spec", "design"], "blueprint": ["scope", "architecture"]}

# The I4 exclusion table, one row per pattern (design § Interfaces, I4).
EXCLUSION_TABLE = [
    r"^.+ has Approval section$",
    r"^.+ is approved$",
    r"^.+ approval hash present$",
    r"^.+ hash basis is current$",
    r"^.+ has not been modified since approval$",
    r"^Previous phase \(.+\) approved before this phase$",
    r"^.+ upstream binding current$",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _run(tier: str, *args: str):
    return subprocess.run([sys.executable, str(_SCRIPT[tier]), *args],
                          capture_output=True, text=True)


def _validator(tier: str):
    return fx._load_validator(tier)


def _args(tier: str):
    """The fields of the argparse namespace `_phase_results` reads, at the
    defaults `--fail-keys` runs with (phase `all`, no --language)."""
    from types import SimpleNamespace

    return SimpleNamespace(phase="all", language=None)


def _raw_fail_counts(tier: str, d: Path, root: Path) -> Counter:
    mod = _validator(tier)
    c: Counter = Counter()
    for _phase, result in mod._phase_results(_args(tier), d, root):
        for name, sev, _detail in result.checks:
            if sev == bc.Severity.FAIL:
                c[name] += 1
    return c


def _fail_key_lines(tier: str, d: Path) -> list[str]:
    r = _run(tier, str(d), "--fail-keys")
    assert r.returncode == 0, (r.stdout, r.stderr)
    return [l for l in r.stdout.splitlines() if l.startswith("FAIL-KEY: ")]


def _edited_chain(tmp_path: Path, tier: str):
    """Two stamped, bound phases; then the upstream is edited in-loop."""
    out = fx.write_chain(tmp_path, tier, approve=_FIRST_TWO[tier], bind=True)
    up = next(iter(out.values()))
    return out, up, up.parent


def _edit(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("## Objective\n\nx\n", "## Objective\n\nx, edited in-loop\n", 1),
                    encoding="utf-8")


def _tree_digest(root: Path) -> dict:
    sdd = root / ".sdd"
    if not sdd.exists():
        return {}
    return {str(p.relative_to(sdd)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(sdd.rglob("*")) if p.is_file()}


def _vr(*names: str) -> "bc.ValidationResult":
    r = bc.ValidationResult()
    for n in names:
        r.add(n, False, "detail")
    return r


# ---------------------------------------------------------------------------
# --fail-keys (AD6, I4)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_fail_keys_inloop_upstream_edit_delta_empty_after_exclusion(tmp_path, tier):
    _out, up, d = _edited_chain(tmp_path, tier)
    raw_before = _raw_fail_counts(tier, d, tmp_path)
    keys_before = _fail_key_lines(tier, d)
    _edit(up)
    raw_after = _raw_fail_counts(tier, d, tmp_path)
    keys_after = _fail_key_lines(tier, d)
    assert raw_after - raw_before, "the in-loop upstream edit must flip some raw key"
    assert keys_after == keys_before


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_fail_keys_harvested_raw_keys_each_match_a_pattern(tmp_path, tier):
    _out, up, d = _edited_chain(tmp_path, tier)
    before = _raw_fail_counts(tier, d, tmp_path)
    _edit(up)
    delta = _raw_fail_counts(tier, d, tmp_path) - before
    assert delta
    for key in delta:
        assert any(p.match(key) for p in bc.APPROVAL_STATE_KEY_PATTERNS), key


def test_fail_keys_patterns_are_the_exclusion_table():
    assert [p.pattern for p in bc.APPROVAL_STATE_KEY_PATTERNS] == EXCLUSION_TABLE


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_fail_keys_unapproved_design_omits_every_exclusion_table_name(tmp_path, tier):
    # Only the first phase is stamped, so the second fails its approval-state
    # checks on every pass; none of them may surface as a FAIL key.
    out = fx.write_chain(tmp_path, tier, approve=_FIRST_TWO[tier][:1], bind=True)
    d = next(iter(out.values())).parent
    raw = _raw_fail_counts(tier, d, tmp_path)
    assert any(re.match(p, k) for p in EXCLUSION_TABLE for k in raw)
    keys = [json.loads(l.split(" ", 2)[2]) for l in _fail_key_lines(tier, d)]
    for pattern in EXCLUSION_TABLE:
        rx = re.compile(pattern)
        assert not any(rx.match(k) for k in keys), (pattern, keys)


def test_fail_keys_second_instance_raises_count():
    one = bc.fail_key_counts([_vr("spec.md has Objective section")])
    two = bc.fail_key_counts([_vr("spec.md has Objective section"),
                              _vr("spec.md has Objective section")])
    assert one["spec.md has Objective section"] == 1
    assert two["spec.md has Objective section"] == 2


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_fail_keys_zero_fail_prints_nothing_exit_0(tmp_path, tier):
    d = tmp_path / ("specs/feat-x" if tier == "sdd" else "blueprint")
    d.mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    r = _run(tier, str(d), "--fail-keys")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert r.stdout == ""


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_fail_keys_writes_no_marker_or_lock_sdd_tree_unchanged(tmp_path, tier):
    _out, up, d = _edited_chain(tmp_path, tier)
    _edit(up)
    before = _tree_digest(tmp_path)
    r = _run(tier, str(d), "--fail-keys")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert _tree_digest(tmp_path) == before
    assert not (tmp_path / ".sdd" / "pending-review.json").exists()
    assert not list(tmp_path.rglob("*.lock"))


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_fail_keys_validator_exception_exits_3_without_lines(tmp_path, tier, monkeypatch, capsys):
    out = fx.write_chain(tmp_path, tier, approve=[], bind=False)
    d = next(iter(out.values())).parent
    mod = _validator(tier)

    def boom(*_a, **_k):
        raise RuntimeError("simulated validator crash")

    monkeypatch.setattr(mod, "_phase_results", boom)
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT[tier]), str(d), "--fail-keys"])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 3
    cap = capsys.readouterr()
    assert "error: --fail-keys could not validate (RuntimeError)" in cap.out + cap.err
    assert "FAIL-KEY" not in cap.out + cap.err


def test_fail_key_counts_em_dash_name_is_one_key():
    name = "tasks.md covers all requirements from spec.md — R3"
    counts = bc.fail_key_counts([_vr(name)])
    assert list(counts) == [name]


def test_fail_key_counts_per_instance_ids_distinct():
    a = "R5: test function exists — T3/test_alpha"
    b = "R5: test function exists — T3/test_beta"
    counts = bc.fail_key_counts([_vr(a, b)])
    assert counts == Counter({a: 1, b: 1})


def test_fail_key_counts_drops_passes_and_warnings():
    r = bc.ValidationResult()
    r.add("ok", True)
    r.add("advisory", False, warn_only=True)
    r.add("bad", False)
    assert bc.fail_key_counts([r]) == Counter({"bad": 1})


def test_fail_keys_json_escapes_tab_and_newline():
    name = "weird\tname\nwith controls\x1b"
    lines = bc.fail_key_lines(bc.fail_key_counts([_vr(name, name)]))
    assert lines == [f"FAIL-KEY: 2 {json.dumps(name)}"]
    assert all("\t" not in l and "\n" not in l and "\x1b" not in l for l in lines)


def test_fail_key_lines_sorted():
    lines = bc.fail_key_lines(Counter({"b": 1, "a": 3}))
    assert lines == ['FAIL-KEY: 3 "a"', 'FAIL-KEY: 1 "b"']


# ---------------------------------------------------------------------------
# T24: `## Working files` doctrine (R3, AD2, AD6, AD7, AD13)
# ---------------------------------------------------------------------------

_SKILLS = _SCRIPTS.parent / "skills"
_AGENTS_DIR = _SCRIPTS.parent / "agents"
_PANEL_REVIEW = {
    "sdd": _SKILLS / "spec-driven-dev" / "references" / "panel-review.md",
    "blueprint": _SKILLS / "project-blueprint" / "references" / "panel-review.md",
}

# Word budgets of the new panel-review.md sections (design C1/C2/C8).
SECTION_WORD_BUDGETS = {"Working files": 700, "Applying a pass's fixes": 1500,
                        "Rigour posture": 450, "Tapered roster": 400}

_ARTIFACT_DIR_WORKING_FILE_RE = re.compile(
    r"(?<!scratch/)(specs|blueprint)/\S*(scratch|[-_.]draft|draft\.md|[-_.]snapshot|[-_.]diff)")


def panel_section(tier: str, heading: str) -> str:
    lines = _PANEL_REVIEW[tier].read_text(encoding="utf-8").split("\n")
    i = lines.index(f"## {heading}")
    j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
    return "\n".join(lines[i:j]).rstrip("\n")


def test_working_files_section_byte_identical_across_tiers():
    assert panel_section("sdd", "Working files") == panel_section("blueprint", "Working files")


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_working_files_carries_retention_resume_and_approval_message(tier):
    s = panel_section(tier, "Working files")
    assert "**The loop's first snapshot**" in s
    assert "first remove any unsuffixed `<stem>-snapshot-p<digits>.md`" in s
    assert ('"Has this loop already written a panel-pass snapshot for `<artifact>`?"') in s
    assert ('"Kept `<stem>-snapshot-p<K>.md` (this loop\'s first snapshot); the next '
            'loop\'s first snapshot write removes it."') in s
    assert "no validator or archive script removes one" in s
    assert "Restore from the snapshot only if some FAIL key's count rose" in s


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_working_files_purpose_list_closed_and_comma_separated(tier):
    s = panel_section(tier, "Working files")
    line = next(l for l in s.split("\n") if l.startswith("**Purposes (closed"))
    names = re.findall(r"`(draft|snapshot|diff|sweep|census)`", line)
    assert names == ["draft", "snapshot", "diff", "sweep", "census"]
    # spec SEAL-19: a comma between the snapshot and diff entries.
    assert re.search(r"`snapshot` \([^)]*\), `diff`", line)


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_adopter_gitignore_line_beside_panel_log(tier):
    text = _PANEL_REVIEW[tier].read_text(encoding="utf-8")
    para = next(p for p in text.split("\n\n") if p.startswith("**Panel log (`.sdd/panel-log.jsonl`).**"))
    assert "add `/.sdd/panel-log.jsonl` to the project's `.gitignore`" in para
    assert "`/.sdd/scratch/` and `/.sdd/posture-notice`" in para
    assert "§ Working files" in para


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_ignore_check_three_branch_wording_present(tier):
    s = panel_section(tier, "Working files")
    assert "git -C '<root>' check-ignore -q -- '.sdd/scratch/probe'" in s
    assert "Exit 0: ignored, proceed." in s
    assert "If the artifact is tracked (exit 1), tell the user to add `/.sdd/scratch/` and proceed." in s
    assert "If the artifact is itself ignored (exit 0), ask before writing; on decline, write no working file" in s
    assert "Exit 128: not a git repository, no check." in s
    assert "Without `git`, skip it and tell the user once." in s


def _doc_lines():
    for f in [*_SKILLS.glob("**/*.md"), *_AGENTS_DIR.glob("*.md")]:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            yield f, n, line


def test_no_working_file_location_inside_artifact_dir():
    hits = [f"{f.name}:{n}" for f, n, line in _doc_lines()
            if _ARTIFACT_DIR_WORKING_FILE_RE.search(line)]
    assert hits == []


def test_artifact_dir_location_guard_catches_known_bad():
    bad = ["specs/F1-x/02_design.draft.md", "blueprint/SCOPE_draft.md", "specs/F1-x/draft.md"]
    assert all(_ARTIFACT_DIR_WORKING_FILE_RE.search(b) for b in bad)
    assert not _ARTIFACT_DIR_WORKING_FILE_RE.search(".sdd/scratch/blueprint/01_SCOPE-draft-p2.md")


@pytest.mark.parametrize("heading", sorted(SECTION_WORD_BUDGETS))
@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_new_panel_review_section_within_word_budget(tier, heading):
    words = len(panel_section(tier, heading).split())
    assert words <= SECTION_WORD_BUDGETS[heading], (heading, words)


# ---------------------------------------------------------------------------
# T25: `## Applying a pass's fixes` doctrine (R1, R2, C1, AD3-AD6, AD8)
# ---------------------------------------------------------------------------

_APPLY = "Applying a pass's fixes"
_ROUTE_II_TRIGGER = ("body `[SELF-CHECK]` rows disposed `Addressed` when step 5 runs "
                     "after the pass's first promote")
_HASH_CMD = ("<python> -c \"import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb')"
             ".read()).hexdigest())\" '<artifact>'")


def _apply(tier: str) -> str:
    return panel_section(tier, _APPLY)


def _line(s: str, prefix: str) -> str:
    return next(l for l in s.split("\n") if l.startswith(prefix))


def test_applying_fixes_section_byte_identical_across_tiers():
    assert _apply("sdd") == _apply("blueprint")


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_applying_fixes_section_sits_between_loop_and_working_files(tier):
    heads = [l for l in _PANEL_REVIEW[tier].read_text(encoding="utf-8").split("\n")
             if l.startswith("## ")]
    i = heads.index(f"## {_APPLY}")
    assert heads[i - 1] == "## The Loop" and heads[i + 1] == "## Working files"


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_applying_fixes_carries_brief_parts_and_return_literals(tier):
    s = _apply(tier)
    labels = re.findall(r"^- \(([a-g])\) ", s, flags=re.M)
    assert labels == list("abcdefg")
    for lit in ("`row <k>: applied — <sites>`", "`row <k>: not applied — <reason>`",
                "`mirror edits:`", "`<site> — restates <fact changed by row k>`",
                '`## <H2> > ### <H3> ¶ "<first ≤40 chars of the changed line>"`',
                "`Dispatching fix draft: <analyst> [opus/<effort>]`"):
        assert lit in s, lit


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_brief_states_point_rather_than_restate_rule_inline(tier):
    d = _line(_apply(tier), "- (d) ")
    assert ("find every other place the file states the same fact and make them agree, "
            "or replace the restatement with a pointer to the place that owns the fact") in d


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_brief_do_not_touch_names_panel_review_and_approval(tier):
    c = _line(_apply(tier), "- (c) ")
    assert "every other row number" in c
    assert "`## Panel Review`" in c and "`## Approval`" in c


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_applying_fixes_carries_fail_keys_multiset_rule(tier):
    s = _apply(tier)
    para = _line(s, "**Baseline and restore.**")
    assert "--fail-keys" in para
    assert "multiset of FAIL check names" in para
    assert "approval-state keys excluded by pattern" in para
    assert "restore per § Working files" in para


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_applying_fixes_points_at_working_files(tier):
    s = _apply(tier)
    assert s.count("§ Working files") >= 5
    for prefix in ("4. ", "- (f) ", "**Hash mismatch.**"):
        assert "§ Working files" in _line(s, prefix), prefix
    # The path grammar is owned by § Working files and not restated here.
    assert ".sdd/scratch" not in s
    assert "-snapshot-p" not in s


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_hash_mismatch_stated_as_no_retry_exception(tier):
    s = _apply(tier)
    assert "the hash mismatch is the no-retry exception" in _line(s, "5. ")
    assert "no-retry exception" in _line(s, "- (iii) ")
    assert "no-retry exception" in _line(s, "| Hash mismatch |")
    assert "other than a hash mismatch" in _line(s, "| (iii) Scope-verify retry |")


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_decision_table_has_baseline_run_failure_row(tier):
    row = _line(_apply(tier), "| Baseline-run failure |")
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert len(cells) == 4
    assert "`--fail-keys` baseline exits non-zero" in cells[1]
    assert cells[2] == "none"
    assert "no promote" in cells[3] and "draft deleted" in cells[3]
    assert "rows to the user (SEAL-08 b)" in cells[3]


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_hash_mismatch_halt_shows_snapshot_diff_and_keeps_snapshot(tier):
    para = _line(_apply(tier), "**Hash mismatch.**")
    shown = para.index("show `diff -u '<snapshot>' '<artifact>'`")
    assert shown < para.index("ask whether to restore or keep")
    assert "Restore only on their confirmation." in para
    assert "After either answer the snapshot is kept" in para
    assert "the next unrestored promote's cleanup or the approval gate removes it" in para
    assert "unless it is the loop's first snapshot" in para


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_hash_command_is_portable_python_not_shasum(tier):
    assert _HASH_CMD in _apply(tier)
    assert "`<python>` is the interpreter you run the tier validator with" in _apply(tier)
    assert "shasum" not in _PANEL_REVIEW[tier].read_text(encoding="utf-8")


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_route_ii_trigger_and_suffix_rule_consistent(tier):
    s = _apply(tier)
    assert s.count(_ROUTE_II_TRIGGER) == 3
    for prefix in ("7. ", "- (ii) ", "| (ii) Self-Check dispatch |"):
        assert _ROUTE_II_TRIGGER in _line(s, prefix), prefix
    assert ("In a pass with no promote, body Self-Check findings join the "
            "SEAL-08 (b) hand-off.") in s
    assert ("`<n>` is its issue ordinal among routes issued after the first promote, "
            "counting from 2 (the first is `-2`)") in s


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_work_list_excludes_condenser_proposal_text(tier):
    assert ("no `DISPOSITION-PROPOSAL` or `FIX-INSTRUCTION` text is the work list"
            in _apply(tier))


# ---------------------------------------------------------------------------
# T26: Loop pointers, carve-out deletion, Self-Check, pass summary, Autonomy
# rows (R1, R2, C1)
# ---------------------------------------------------------------------------

_TIER_ROOT = {"sdd": _SKILLS / "spec-driven-dev", "blueprint": _SKILLS / "project-blueprint"}

# The carve-out phrase table (tasks.md T26): file -> the exact substring that
# must be absent once its owner task lands. Matching is on the exact
# substring, never a bare `orchestrator-direct`.
CARVE_OUT_PHRASES = {
    "references/panel-review.md":
        "In-loop per-concern fixes are applied by the orchestrator directly",
    "references/hash-and-cascade.md":
        "an in-loop per-concern panel fix stays orchestrator-direct",
    "references/workflow-overview.md":
        "a *substantive in-loop per-concern fix* during an active panel pass stays "
        "orchestrator-direct",
    "SKILL.md":
        "Trivial edits and in-loop per-concern panel fixes stay orchestrator-direct",
}

_CARVE_OUT_IDS = [f"{tier}:{rel}" for rel in CARVE_OUT_PHRASES for tier in ("sdd", "blueprint")]


def _carve_out_text(cid: str) -> tuple[str, str]:
    tier, rel = cid.split(":", 1)
    return (_TIER_ROOT[tier] / rel).read_text(encoding="utf-8"), CARVE_OUT_PHRASES[rel]


@pytest.mark.parametrize("cid", _CARVE_OUT_IDS)
def test_old_carve_out_sentence_absent(cid):
    text, phrase = _carve_out_text(cid)
    assert phrase not in text, cid


_APPLY_PTR = "§ Applying a pass's fixes"


def _delegate_paragraph(tier: str) -> str:
    text = (_TIER_ROOT[tier] / "references" / "workflow-overview.md").read_text(encoding="utf-8")
    return next(l for l in text.split("\n") if l.startswith("**When to delegate vs. act directly.**"))


def test_workflow_overview_points_at_applying_fixes_and_posture():
    # T30 (C1, C8): the in-loop branch points at § Applying a pass's fixes,
    # the trivial carve-out is out-of-loop only, the out-of-loop routing and
    # its § Revise the downstream pointer are kept, and § Rigour posture is
    # named; identical in both tiers.
    sdd, bp = _delegate_paragraph("sdd"), _delegate_paragraph("blueprint")
    assert sdd == bp
    p = sdd
    assert "panel-review.md` § Applying a pass's fixes" in p
    assert "panel-review.md` § Rigour posture" in p
    assert "*trivial out-of-loop* edits" in p
    assert "however small" in p
    assert "orchestrator-direct (the next pass of the same loop re-reviews it)" not in p
    assert ("a *substantial out-of-loop revision* — a cascade downstream fix, a panel-loop "
            "re-entry on a substantive gate-change, or an upstream backport — is delegated to "
            "the phase-correct analyst") in p
    assert ("See `references/hash-and-cascade.md` § \"Revise the downstream\" for the "
            "delegation brief") in p


def _section_line(tier: str, heading: str, prefix: str) -> str:
    return _line(panel_section(tier, heading).replace("\n   ", " "), prefix)


def _loop_item(tier: str, heading: str, n: int) -> str:
    s = panel_section(tier, heading)
    m = re.search(rf"^{n}\. .*?(?=^\d+\. |\Z)", s, flags=re.M | re.S)
    assert m, (heading, n)
    return m.group(0)


def _bullet(tier: str, lead: str) -> str:
    s = panel_section(tier, "The Loop")
    return next(l for l in s.split("\n") if l.lstrip().startswith(lead))


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_loop_sites_point_at_applying_fixes(tier):
    sites = {
        "step 3 Addressed": _bullet(tier, "- **Addressed**"),
        "step 3 User input needed": _bullet(tier, "- **User input needed**"),
        "step 4": _loop_item(tier, "The Loop", 4),
        "step 5": _loop_item(tier, "The Loop", 5),
        "digest 3": _loop_item(tier, "Minimum to run the NORMAL loop", 3),
        "digest 4": _loop_item(tier, "Minimum to run the NORMAL loop", 4),
    }
    for name, text in sites.items():
        assert _APPLY_PTR in text, name
    addressed = sites["step 3 Addressed"]
    assert "apply the fix to the artifact" not in addressed.lower()
    uin = sites["step 3 User input needed"]
    assert "apply the resolution" not in uin
    assert "joins the pass's dispatch" in uin


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_synthesizer_self_check_routes_body_fix_through_route_ii(tier):
    s = panel_section(tier, "Synthesizer Self-Check")
    flat = re.sub(r"\s+", " ", s)
    assert "apply the fix and re-run the checklist" not in flat
    assert "fix you applied" not in flat
    assert ("For each issue found in the artifact body: record it as a [SELF-CHECK] row "
            "disposed Addressed; route (ii) of § Applying a pass's fixes applies it, and "
            "the checklist re-runs from step 1 after that promote.") in flat
    a = _line(s, "**(a) Contract preservation**")
    assert "for each fix applied this pass" in a
    if tier == "blueprint":
        e = _line(s, "**(e) Closed-feature-row integrity")
        assert "for each fix applied this pass" in e
        assert "route (ii)" in e and _APPLY_PTR in e
        # T32's pinned exemption sentence stays verbatim.
        assert ("**Why this exists:** Phase-3 panelists routinely propose edits to feature "
                "rows when they spot a binding obligation (e.g., a CFC's per-feature AC that "
                "names F<n>), without checking F<n>'s milestone state.") in e


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_pass_summary_surface_carries_fix_bullets(tier):
    s = panel_section(tier, "Pass summary surface")
    for phrase in ("`not applied`, with its reason", "mirror edit, with its site",
                   "direct application (SEAL-08)", "**restore**", "kept paths",
                   "the next pass's summary names them as removed",
                   "`--fail-keys`", "**pre-existing FAIL keys**",
                   "\"no new failing check names\"", "approval-state keys",
                   "**re-disposed row**", "new disposition", _APPLY_PTR):
        assert phrase in s, phrase


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_autonomy_boundary_carries_r1_rows(tier):
    s = panel_section(tier, "Autonomy Boundary")
    rows = [l for l in s.split("\n") if l.startswith("| ")]
    cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
    auto = [c[0] for c in cells if len(c) == 2]
    ask = [c[1] for c in cells if len(c) == 2]
    assert any("Dispatching a pass's fixes to the drafting agent, plus its bounded further, "
               "Self-Check and retry dispatches" in a for a in auto)
    assert any("a failed baseline run" in a and "SEAL-08 user-directed fix" in a for a in ask)
    assert any("scope-verify hash mismatch" in a
               and "restore only on the user's confirmation" in a for a in ask)
    assert any("After a resume, whether this loop has already written a panel-pass snapshot"
               in a and "before the next snapshot write" in a for a in ask)


# ---------------------------------------------------------------------------
# T27: `hash-and-cascade.md` carve-out removal and Working-files pointers
# (R1, R3, C1, C2)
# ---------------------------------------------------------------------------

_BACKPORT_TRIVIALITY = (
    "A trivial backport (typo, rename, single-sentence reword — no behavior change) stays "
    "orchestrator-direct per the existing triviality carve-out; a substantial one supplies the "
    "delegation brief and runs the scope-verify + content-preservation check before "
    "*Re-Approval After Edits* runs (both are defined in § \"Revise the downstream\" — "
    "Substantial, above).")


def _hc(tier: str) -> str:
    return (_TIER_ROOT[tier] / "references" / "hash-and-cascade.md").read_text(encoding="utf-8")


def _substantial_bullet(tier: str) -> str:
    return next(l for l in _hc(tier).split("\n") if l.startswith("  - **Substantial** "))


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_hash_and_cascade_phrases_point_at_working_files(tier):
    b = _substantial_bullet(tier)
    assert "(6) a **scratch output path** (see `panel-review.md` § Working files) to `Write`" in b
    assert "(c) on pass, snapshot the live artifact (see `panel-review.md` § Working files)," in b
    # The in-loop carve-out clause now points at the in-loop home.
    assert ("The trivial-direct path above is unchanged; an in-loop panel fix follows "
            "`panel-review.md` § Applying a pass's fixes instead.") in b
    # Out-of-loop triviality carve-outs stay unchanged (spec R1).
    hc = _hc(tier)
    assert "Claude applies the fix directly; the user's \"fix it\" is the authorization." in hc
    assert _BACKPORT_TRIVIALITY in hc


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_hash_and_cascade_names_zone_diff_for_check_a(tier):
    b = _substantial_bullet(tier)
    assert "no committed script" not in b
    assert "with general-purpose tools (or `archive_pass.py --zone-diff`): (a) extract" in b


# ---------------------------------------------------------------------------
# T28: `## Rigour posture`, `## Tapered roster`, their Loop pointers, the
# digest load line (R5, R7, C8)
# ---------------------------------------------------------------------------

_STEP1_LEAD = "1. **Dispatch all three panelists in a single message.**"
_C8_STEP1 = ("On a pass after a loop's first, the roster is the one `## Tapered roster` "
             "names; 'all three' then means every seat on that roster.")
_TAPERED_SUMMARY = ("\"`<k>` of 3 panelists ran (`<names>`); say 'full panel next pass' "
                    "to run all three\"")
_VIBE_CLAUSE = "the persisted posture is `vibe` (§ Rigour posture)"


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def _step1(tier: str) -> str:
    s = panel_section(tier, "The Loop")
    return s[s.index(_STEP1_LEAD):s.index("\n2. **Synthesize in-thread**")]


def test_posture_and_taper_sections_byte_identical_across_tiers():
    for heading in ("Rigour posture", "Tapered roster"):
        assert panel_section("sdd", heading) == panel_section("blueprint", heading), heading


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_posture_and_taper_sections_follow_working_files(tier):
    heads = [l for l in _PANEL_REVIEW[tier].read_text(encoding="utf-8").split("\n")
             if l.startswith("## ")]
    i = heads.index("## Working files")
    assert heads[i + 1:i + 4] == ["## Rigour posture", "## Tapered roster",
                                  "## Pass summary surface"]


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_step_1_bold_lead_verbatim_and_taper_sentence_follows(tier):
    assert _step1(tier).startswith(_STEP1_LEAD + " " + _C8_STEP1 + " ")


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_tapered_roster_full_roster_phrases_and_guards(tier):
    s = _flat(panel_section(tier, "Tapered roster"))
    for phrase in ("**A loop's first pass**", "a STRICT-BAR pass", "a cross-check pass",
                   "any pass not preceded by an advisory", "'full panel next pass'",
                   _TAPERED_SUMMARY, "run the full roster"):
        assert phrase in s, phrase
    assert ("**A stated `critical` posture never tapers:** when the loop-start statement "
            "says `critical`, every pass runs the full roster, whatever any advisory names, "
            "including one printed by an archive call that omitted `--posture critical`.") in s
    assert "Relay the advisory line to the user right after each archive." in s
    assert "dispatch exactly the `survivors=` names the advisory gives, without asking" in s
    assert "`--panel-roster` naming the seats actually dispatched" in s


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_tapered_roster_names_constants_and_no_threshold_number(tier):
    s = panel_section(tier, "Tapered roster")
    assert "`TAPER_SIZE_CLASSES`" in s and "`TAPER_SEAT_PRIORITY`" in s
    rest = s.replace(_TAPERED_SUMMARY, "")
    assert not re.search(r"\d", rest), re.findall(r".{20}\d.{20}", rest)


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_tapered_pass_dispatch_text_unchanged_no_tapered_only_clause(tier):
    s = _flat(panel_section(tier, "Tapered roster"))
    assert ("Panelist dispatch text is unchanged on a tapered pass: no clause is added "
            "for being on a smaller panel.") in s
    step1 = _step1(tier).replace(_C8_STEP1, "").lower()
    for word in ("taper", "smaller panel", "fewer"):
        assert word not in step1, word


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_rigour_posture_statement_guard_and_override_text(tier):
    s = _flat(panel_section(tier, "Rigour posture"))
    for row in ("| `critical` | full loop, no taper (today's panel roster and exit rules) | "
                "every pass gets all three reviewers |",
                "| `standard` | full loop with the taper (§ Tapered roster) | later passes on a small change "
                "get fewer reviewers |",
                "| `vibe` | `panel-review-modes.md` § Lightweight Mode, where the taper is moot | one "
                "review pass; approval is then usually refused by the convergence gate and "
                "goes through its per-artifact override (below) |"):
        assert row in s, row
    assert "--phase <N> --posture-report" in s
    assert "state the posture, its source and how to change it" in s
    assert "`PANEL-POSTURE-NOTICE:`" in s
    assert "--set-posture <p>" in s and "`--posture <p>` on every `archive_pass.py` call" in s
    assert "load-bearing guard" in s
    assert "recommend the full loop before applying the lightweight default" in s
    assert "`--override-convergence \"<reason>\"`" in s
    assert "ask for a reason specific to this artifact" in s
    assert "Never reuse or suggest another artifact's reason" in s
    assert "never accept a reason that only cites the posture" in s


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_digest_load_line_and_situational_bullet_name_persisted_vibe(tier):
    digest = panel_section(tier, "Minimum to run the NORMAL loop")
    load = next(l for l in digest.split("\n") if l.startswith("Load on demand:"))
    assert f"**lightweight mode** (only when the user opts in or {_VIBE_CLAUSE})" in load
    sit = panel_section(tier, "Situational panel modes (loaded on demand)")
    bullet = next(l for l in sit.split("\n") if l.startswith("- **Lightweight Mode"))
    assert "when the user opts into a single-pass review" in bullet
    assert _VIBE_CLAUSE in bullet


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_digest_item_1_points_at_tapered_roster(tier):
    item1 = _loop_item(tier, "Minimum to run the NORMAL loop", 1)
    assert "§ Tapered roster" in item1
    item4 = _loop_item(tier, "Minimum to run the NORMAL loop", 4)
    assert "§ Tapered roster" in item4 and "three panelists" not in item4
    step6 = _loop_item(tier, "The Loop", 6)
    assert "§ Tapered roster" in step6 and "§ Rigour posture" in step6


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_autonomy_boundary_carries_r5_row(tier):
    s = panel_section(tier, "Autonomy Boundary")
    assert ("| Dispatching the roster the advisory names on a pass after the loop's first "
            "(§ Tapered roster) | |") in s


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_doctrine_names_advisory_and_posture_literals(tier):
    assert "`PANEL-ROSTER-ADVISORY:`" in panel_section(tier, "Tapered roster")
    assert "`PANEL-POSTURE:" in panel_section(tier, "Rigour posture")
