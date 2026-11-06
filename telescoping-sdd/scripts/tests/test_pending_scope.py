"""Unit C0 R1 — pending-review obligation scopes, tiers, routes and the scoped decline.

Every R1 case runs with bare and `NN_`-prefixed keys where the name matters.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import blueprint_common as bc  # noqa: E402,F401  (load order: bc before pending_review)
import pending_review as pr  # noqa: E402


# --- T9: scope, tier and containment helpers --------------------------------


def test_scope_of_key_is_raw_split():
    assert pr.scope_of_key("specs/F1-x/01_spec.md") == "specs/F1-x"
    assert pr.scope_of_key("./specs/F1-x/01_spec.md") == "./specs/F1-x"
    assert pr.scope_of_key("specs//F1-x/01_spec.md") == "specs//F1-x"
    assert pr.scope_of_key("PLAN.md") == "."
    assert pr.scope_of_key("blueprint/SCOPE.md") == "blueprint"


@pytest.mark.parametrize("prefixed", [False, True])
def test_tier_of_scope_bare_and_prefixed_names(prefixed):
    p = "01_" if prefixed else ""
    q = "03_" if prefixed else ""
    assert pr.tier_of_scope([f"specs/F1-x/{p}spec.md", f"specs/F1-x/{q}tasks.md"]) == "sdd"
    assert pr.tier_of_scope([f"blueprint/{p}SCOPE.md", f"blueprint/{q}PLAN.md"]) == "blueprint"


def test_tier_of_scope_ignores_unrecognised_names():
    assert pr.tier_of_scope(["specs/F1-x/01_spec.md", "specs/F1-x/tasks-python.md"]) == "sdd"
    assert pr.tier_of_scope(["specs/F1-x/03_tasks-python.md", "specs/F1-x/02_design.md"]) == "sdd"


def test_tier_of_scope_none_for_both_tiers_or_no_names():
    assert pr.tier_of_scope(["x/notes.md", "x/tasks-python.md"]) is None
    assert pr.tier_of_scope(["x/spec.md", "x/PLAN.md"]) is None
    assert pr.tier_of_scope([]) is None


def test_partition_keys_uses_raw_prefix_in_scope():
    keys = [
        "specs/F1-x/01_spec.md",
        "./specs/F1-x/01_spec.md",
        "specs//F1-x/01_spec.md",
        "specs/F1-x-extra/spec.md",
        "blueprint/SCOPE.md",
    ]
    in_scope, elsewhere = pr.partition_keys(keys, "specs/F1-x")
    assert in_scope == ["specs/F1-x/01_spec.md"]
    assert elsewhere == keys[1:]
    for k in keys:
        assert (k in in_scope) == pr._prefix_in_scope(k, "specs/F1-x")
    # root target is match-all (R1 known limit), as the gate applies it
    assert pr.partition_keys(keys, ".") == (keys, [])


def test_is_containment_escaping_absolute_and_outside_root(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    assert pr.is_containment_escaping(root, "/etc/passwd") is True
    assert pr.is_containment_escaping(root, "../outside/spec.md") is True
    assert pr.is_containment_escaping(root, "specs/F1-x/spec.md") is False


def test_dotdot_key_resolving_inside_project_not_escaping(tmp_path):
    (tmp_path / "specs" / "F1-x").mkdir(parents=True)
    key = "specs/F1-x/../F1-x/spec.md"
    assert pr.is_containment_escaping(tmp_path, key) is False
    # _key_is_contained is stricter (any `..` part) and is NOT the label (AD14)
    assert pr._key_is_contained(tmp_path, key) is False


def test_dotdot_foo_directory_not_escaping(tmp_path):
    (tmp_path / "..foo").mkdir()
    assert pr.is_containment_escaping(tmp_path, "..foo/spec.md") is False


def test_nul_key_neither_helper_raises(tmp_path):
    key = "specs/F1-x\x00/spec.md"
    assert pr.is_containment_escaping(tmp_path, key) is True
    assert pr._key_is_contained(tmp_path, key) is False


def test_symlink_loop_key_labelled_escaping(tmp_path):
    os.symlink(tmp_path / "b", tmp_path / "a")
    os.symlink(tmp_path / "a", tmp_path / "b")
    key = "a/spec.md"
    got_escaping = pr.is_containment_escaping(tmp_path, key)
    got_contained = pr._key_is_contained(tmp_path, key)
    if sys.version_info < (3, 13):
        assert got_escaping is True
        assert got_contained is False


# --- T10: owning-directory route builder (AD16) ------------------------------

from approval_records import USER_DECISION_NOTE  # noqa: E402

SPEC_CMD = "validate_spec.py"
BP_CMD = "validate_blueprint.py"


def _mk(root: Path, *dirs: str) -> None:
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)


def _route(root, key, keys=None, *, target=".", tier="sdd", use="run-state"):
    return pr.owning_dir_route(
        root, key, keys if keys is not None else [key],
        target_rel=target, running_tier=tier, use=use,
    )


def test_owning_dir_route_run_state_template(tmp_path):
    _mk(tmp_path, "specs/F1-x")
    out = _route(tmp_path, "specs/F1-x/01_spec.md", target=".")
    assert out == (
        "owned by specs/F1-x — resolve it from that directory: run its panel, "
        f"or run the decline there: `{SPEC_CMD} ./specs/F1-x --decline-pending`"
    )


def test_owning_dir_route_refusal_template(tmp_path):
    _mk(tmp_path, "specs/F1-x")
    out = _route(tmp_path, "specs/F1-x/spec.md", use="refusal")
    assert out == f"`{SPEC_CMD} ./specs/F1-x --decline-pending`"


def test_owning_dir_route_stranded_template_carries_user_decision_note(tmp_path):
    _mk(tmp_path, "specs/F1-x")
    out = _route(tmp_path, "specs/F1-x/spec.md", use="stranded")
    assert out.startswith("for the session or user that owns specs/F1-x: ")
    assert f"`{SPEC_CMD} ./specs/F1-x --decline-pending`" in out
    assert out.endswith(USER_DECISION_NOTE)


def test_owning_dir_route_gate_fail_template(tmp_path):
    _mk(tmp_path, "specs/F1-x")
    out = _route(tmp_path, "specs/F1-x/spec.md", use="gate-fail")
    assert out == (
        f"owned by specs/F1-x: decline it from there: "
        f"`{SPEC_CMD} ./specs/F1-x --decline-pending`"
    )


def test_route_uses_running_tier_command(tmp_path):
    _mk(tmp_path, "blueprint", "specs/F1-x")
    assert BP_CMD in _route(tmp_path, "blueprint/01_SCOPE.md", tier="blueprint", use="refusal")
    # key's own tier wins when it differs from the running tier
    out = _route(tmp_path, "blueprint/PLAN.md", tier="sdd", use="refusal")
    assert BP_CMD in out and SPEC_CMD not in out


def test_route_prints_both_validators_for_untiered_key(tmp_path):
    _mk(tmp_path, "notes")
    out = _route(tmp_path, "notes/readme.md", use="refusal")
    assert f"`{SPEC_CMD} ./notes --decline-pending`" in out
    assert f"`{BP_CMD} ./notes --decline-pending`" in out


def test_vanished_dir_route_names_missing_directory(tmp_path):
    _mk(tmp_path, "specs")
    out = _route(tmp_path, "specs/F3-old/spec.md")
    assert out.startswith("the owning directory specs/F3-old no longer exists on disk")


def test_vanished_dir_route_single_scope_ancestor_decline(tmp_path):
    _mk(tmp_path, "specs")
    keys = ["specs/F3-old/spec.md", "specs/F3-old/design.md"]
    out = _route(tmp_path, keys[0], keys)
    assert f"`{SPEC_CMD} ./specs --decline-pending`" in out
    assert "--decline-key" not in out
    assert USER_DECISION_NOTE not in out


def test_vanished_dir_route_multi_scope_ancestor_uses_decline_key(tmp_path):
    _mk(tmp_path, "specs/F1-x")
    keys = ["specs/F3-old/spec.md", "specs/F1-x/spec.md"]
    out = _route(tmp_path, keys[0], keys)
    assert (
        f"`{SPEC_CMD} ./specs --decline-pending --decline-key=specs/F3-old/spec.md`" in out
    )
    assert USER_DECISION_NOTE in out


def test_vanished_ancestor_route_carries_escaping_side_effect_clause(tmp_path):
    _mk(tmp_path, "specs")
    keys = ["specs/F3-old/spec.md", "specs/../../evil/spec.md"]
    out = _route(tmp_path, keys[0], keys)
    assert f"`{SPEC_CMD} ./specs --decline-pending`" in out
    assert "also clears every other obligation that decline reaches" in out


@pytest.mark.parametrize("key", [
    "specs/./F1-x/spec.md",
    "specs//F1-x/spec.md",
    "specs/F1-x/../F1-x/spec.md",
])
def test_anomalous_segment_key_gets_inspect_by_hand_form(tmp_path, key):
    _mk(tmp_path, "specs/F1-x")
    out = _route(tmp_path, key)
    assert "has `.`, `..` or empty path segments" in out
    assert "--decline-pending" not in out
    assert ".sdd/pending-review.json" in out


def test_root_scope_dot_exempt_from_anomaly_rule(tmp_path):
    out = _route(tmp_path, "PLAN.md", tier="blueprint", use="refusal")
    assert out == f"`{BP_CMD} . --decline-pending`"


def test_escaping_key_route_wins_over_anomaly_rule(tmp_path):
    out = _route(tmp_path, "specs/../../evil/spec.md", target="specs/F1-x")
    assert "segments" not in out
    assert f"`{SPEC_CMD} . --decline-pending`" in out


def test_escaping_key_in_lane_gets_target_decline(tmp_path):
    _mk(tmp_path, "specs/F1-x")
    key = "specs/F1-x/../../../evil/spec.md"
    out = _route(tmp_path, key, target="specs/F1-x")
    assert f"`{SPEC_CMD} ./specs/F1-x --decline-pending`" in out
    assert "containment-escaping" in out


def test_out_of_lane_escaping_key_gets_project_root_route(tmp_path):
    out = _route(tmp_path, "/abs/evil/spec.md", target="specs/F1-x")
    assert f"`{SPEC_CMD} . --decline-pending`" in out
    assert "also clears every other obligation that decline reaches" in out
    assert "once the other scopes' obligations are resolved" in out
    assert USER_DECISION_NOTE in out


@pytest.mark.parametrize("key", ["specs/F1-x/spec\n.md", "specs/F1-x/\x1b[2Jspec.md"])
def test_route_key_with_newline_or_esc_gets_no_command(tmp_path, key):
    _mk(tmp_path, "specs/F1-x")
    out = _route(tmp_path, key)
    assert "--decline-pending" not in out
    assert "\n" not in out and "\x1b" not in out
    assert "contains non-printable or unassigned characters" in out
    assert ascii(key)[:40] in out


def test_route_key_with_backtick_reason_backtick(tmp_path):
    _mk(tmp_path, "specs/F1-x")
    out = _route(tmp_path, "specs/F1-x/sp`ec.md")
    assert "contains a backtick" in out and "--decline-pending" not in out


def test_route_key_over_max_truncated_ascii_echo(tmp_path):
    key = "specs/" + "a" * 1100 + "/spec.md"
    out = _route(tmp_path, key)
    assert f"is {len(key)} characters, too long to print as a command" in out
    assert f"… ({len(key)} chars)" in out
    assert len(out) < 400


def test_decline_key_starting_with_dash_prints_equals_form(tmp_path):
    _mk(tmp_path, "-specs/F1-x")
    keys = ["-specs/F3-old/spec.md", "-specs/F1-x/spec.md"]
    out = _route(tmp_path, keys[0], keys)
    assert "--decline-key=-specs/F3-old/spec.md" in out
    assert "./-specs --decline-pending" in out


def test_positional_target_dash_prints_dot_slash_and_root_prints_dot(tmp_path):
    _mk(tmp_path, "-x")
    assert _route(tmp_path, "-x/spec.md", use="refusal") == (
        f"`{SPEC_CMD} ./-x --decline-pending`"
    )
    keys = ["F3-old/spec.md", "F1-x/spec.md"]
    _mk(tmp_path, "F1-x")
    out = _route(tmp_path, keys[0], keys)
    assert f"`{SPEC_CMD} . --decline-pending --decline-key=F3-old/spec.md`" in out


def test_trailing_clause_order_user_decision_then_project_root(tmp_path):
    out = _route(tmp_path, "/abs/evil/spec.md", target="specs/F1-x")
    assert out.endswith(f"{USER_DECISION_NOTE} (run from the project root)")


# --- T11: scoped decline, refusal and per-key opt-in (AD15) ------------------

import json  # noqa: E402
import shlex  # noqa: E402

import test_reapproval_gate as _trg  # noqa: E402  (shared doc/seed helpers)

H = "a" * 16


def _seed(root: Path, *keys: str, hash16: str = H, make_dirs: bool = True) -> None:
    for k in keys:
        if make_dirs and not pr.is_containment_escaping(root, k):
            (root / pr.scope_of_key(k)).mkdir(parents=True, exist_ok=True)
        bc.upsert_pending_entry(root, k, hash16, "t", 1)


def _marker_bytes(root: Path) -> bytes:
    return (root / ".sdd" / "pending-review.json").read_bytes()


def _pending(root: Path) -> list:
    p = root / ".sdd" / "pending-review.json"
    if not p.exists():
        return []
    return sorted(json.loads(p.read_text(encoding="utf-8"))["pending"])


def _set_hash(root: Path, key: str, value) -> None:
    p = root / ".sdd" / "pending-review.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["pending"][key]["hash"] = value
    p.write_text(json.dumps(d), encoding="utf-8")


def _decline(root, target, tier="sdd", key=None):
    return pr.decline_pending_scoped(root, target, running_tier=tier, decline_key=key)


def _refusal_text(root, res, target, tier="sdd"):
    return pr.format_decline_refusal(
        res.refusal, project_root=root, target_rel=target, running_tier=tier
    )


def test_partition_decline_clear_set_form_reads_and_persists_once(tmp_path, monkeypatch):
    _seed(tmp_path, "specs/F1-x/spec.md", "specs/F1-x/design.md", "specs/F2-y/spec.md")
    reads, persists = [], []
    real_read, real_persist = pr.read_pending_review, pr._persist_or_unlink_marker
    monkeypatch.setattr(pr, "read_pending_review", lambda *a, **k: reads.append(1) or real_read(*a, **k))
    monkeypatch.setattr(pr, "_persist_or_unlink_marker", lambda *a, **k: persists.append(1) or real_persist(*a, **k))
    cleared, held, flagged = pr.partition_decline_clear(
        tmp_path, "ignored", keys={"specs/F1-x/spec.md", "specs/F2-y/spec.md"}
    )
    assert sorted(cleared) == ["specs/F1-x/spec.md", "specs/F2-y/spec.md"]
    assert held == [] and flagged == []
    assert len(reads) == 1 and len(persists) == 1
    assert _pending(tmp_path) == ["specs/F1-x/design.md"]


def test_decline_refused_root_over_two_scopes(tmp_path):
    _seed(tmp_path, "blueprint/01_SCOPE.md", "specs/F1-x/01_spec.md")
    res = _decline(tmp_path, ".")
    assert res.refusal is not None and res.refusal.reason == "multi-scope"
    assert res.cleared == res.held_back == res.flagged == ()
    assert set(res.refusal.keys_by_scope) == {"blueprint", "specs/F1-x"}
    text = _refusal_text(tmp_path, res, ".")
    assert "`validate_blueprint.py ./blueprint --decline-pending`" in text
    assert "`validate_spec.py ./specs/F1-x --decline-pending`" in text
    assert "(1)" in text and "(2)" in text and "(3)" not in text
    assert "--decline-key" in text and USER_DECISION_NOTE in text


def test_decline_refused_specs_parent_over_two_features(tmp_path):
    _seed(tmp_path, "specs/F1-x/spec.md", "specs/F2-y/02_design.md")
    res = _decline(tmp_path, "specs")
    assert res.refusal.reason == "multi-scope"
    text = _refusal_text(tmp_path, res, "specs")
    assert "specs/F1-x/spec.md" in text and "specs/F2-y/02_design.md" in text


def test_decline_refused_other_tier_only(tmp_path):
    _seed(tmp_path, "blueprint/PLAN.md")
    before = _marker_bytes(tmp_path)
    res = _decline(tmp_path, "blueprint", tier="sdd")
    assert res.refusal.reason == "other-tier"
    assert _marker_bytes(tmp_path) == before
    assert "`validate_blueprint.py ./blueprint --decline-pending`" in _refusal_text(
        tmp_path, res, "blueprint"
    )


def test_decline_refused_undeterminable_multi_scope_prints_both_commands(tmp_path):
    _seed(tmp_path, "notes/a.md", "specs/F1-x/spec.md")
    res = _decline(tmp_path, ".")
    assert res.refusal.reason == "multi-scope"
    text = _refusal_text(tmp_path, res, ".")
    assert "`validate_spec.py ./notes --decline-pending`" in text
    assert "`validate_blueprint.py ./notes --decline-pending`" in text


def test_decline_refusal_leaves_marker_byte_unchanged(tmp_path):
    _seed(tmp_path, "blueprint/SCOPE.md", "specs/F1-x/spec.md")
    before = _marker_bytes(tmp_path)
    _decline(tmp_path, ".")
    assert _marker_bytes(tmp_path) == before


def test_decline_refusal_lists_escaping_keys(tmp_path):
    _seed(tmp_path, "blueprint/SCOPE.md", "specs/F1-x/spec.md", "../evil/spec.md")
    res = _decline(tmp_path, ".")
    assert res.refusal.escaping_keys == ("../evil/spec.md",)
    text = _refusal_text(tmp_path, res, ".")
    assert text.index("../evil/spec.md") > text.index("specs/F1-x/spec.md")


def test_decline_escaping_key_plus_one_scope_clears_both(tmp_path):
    _seed(tmp_path, "specs/F1-x/spec.md", "../evil/spec.md")
    res = _decline(tmp_path, ".")
    assert res.refusal is None
    assert res.cleared == ("specs/F1-x/spec.md",) and res.flagged == ("../evil/spec.md",)
    msg, code = pr.format_decline_output(
        list(res.cleared), list(res.held_back), list(res.flagged),
        restore_cmd="x", project_root=tmp_path,
    )
    assert bc.DECLINE_FLAGGED_ESCAPING_MSG.format(doc_rel="../evil/spec.md") in msg
    assert code == bc.EXIT_DECLINE_HELD_BACK
    assert _pending(tmp_path) == []


def test_decline_foreign_malformed_hash_key_refuses(tmp_path):
    _seed(tmp_path, "specs/F1-x/spec.md", "../evil/spec.md", "specs/F2-y/spec.md")
    _set_hash(tmp_path, "specs/F2-y/spec.md", "not-hex")
    before = _marker_bytes(tmp_path)
    res = _decline(tmp_path, ".")
    assert res.refusal is not None and res.refusal.reason == "multi-scope"
    assert _marker_bytes(tmp_path) == before


@pytest.mark.parametrize("prefixed", [False, True])
def test_decline_root_prefix_single_scope_unchanged(tmp_path, prefixed):
    k = "specs/F1-x/01_spec.md" if prefixed else "specs/F1-x/spec.md"
    _seed(tmp_path, k)
    res = _decline(tmp_path, ".")
    assert res.refusal is None and res.cleared == (k,)
    # The v2.27.0 path gives the same partition on an identical marker.
    _seed(tmp_path, k)
    assert bc.partition_decline_clear(tmp_path, ".") == ([k], [], [])


def test_decline_undeterminable_scope_own_directory_unchanged(tmp_path):
    _seed(tmp_path, "notes/a.md", "notes/b.md")
    res = _decline(tmp_path, "notes", tier="blueprint")
    assert res.refusal is None and sorted(res.cleared) == ["notes/a.md", "notes/b.md"]


def test_decline_key_clears_only_named_key(tmp_path):
    _seed(tmp_path, "specs/F1-x/spec.md", "specs/F1-x/design.md")
    _seed(tmp_path, "specs/F3-old/spec.md", "specs/F3-old/design.md", make_dirs=False)
    res = _decline(tmp_path, "specs", key="specs/F3-old/spec.md")
    assert res.refusal is None and res.cleared == ("specs/F3-old/spec.md",)
    assert _pending(tmp_path) == [
        "specs/F1-x/design.md", "specs/F1-x/spec.md", "specs/F3-old/design.md",
    ]
    msg, _ = pr.format_decline_output(
        list(res.cleared), [], [], restore_cmd="x", project_root=tmp_path,
        scope="specs/F3-old",
    )
    assert "specs/F3-old/spec.md" in msg and "specs/F3-old" in msg


@pytest.mark.parametrize("case,reason", [
    ("missing", "key-not-in-marker"),
    ("escaping", "key-escaping"),
    ("out-of-scope", "key-not-in-scope"),
    ("dir-exists", "key-dir-exists"),
    ("other-tier", "key-other-tier"),
])
def test_decline_key_refusal_reasons(tmp_path, case, reason):
    _seed(tmp_path, "specs/F1-x/spec.md", "../evil/spec.md", "elsewhere/F9/spec.md")
    _seed(tmp_path, "specs/F3-old/spec.md", "specs/F4-gone/PLAN.md", make_dirs=False)
    key = {
        "missing": "specs/F3-old/design.md",
        "escaping": "../evil/spec.md",
        "out-of-scope": "elsewhere/F9/spec.md",
        "dir-exists": "specs/F1-x/spec.md",
        "other-tier": "specs/F4-gone/PLAN.md",
    }[case]
    target = "specs" if case != "escaping" else "."
    before = _marker_bytes(tmp_path)
    res = _decline(tmp_path, target, key=key)
    assert res.refusal is not None and res.refusal.reason == reason
    assert _marker_bytes(tmp_path) == before
    assert _refusal_text(tmp_path, res, target)


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_decline_key_untiered_vanished_accepted_by_both_tiers(tmp_path, tier):
    _seed(tmp_path, "specs/F1-x/spec.md")
    _seed(tmp_path, "specs/F3-old/notes.md", make_dirs=False)
    res = _decline(tmp_path, "specs", tier=tier, key="specs/F3-old/notes.md")
    assert res.refusal is None and res.cleared == ("specs/F3-old/notes.md",)


def test_decline_key_unrecognised_name_takes_scope_tier(tmp_path):
    _seed(tmp_path, "specs/F1-x/spec.md")
    _seed(tmp_path, "specs/F3-old/tasks-python.md", "specs/F3-old/spec.md", make_dirs=False)
    res = _decline(tmp_path, "specs", tier="blueprint", key="specs/F3-old/tasks-python.md")
    assert res.refusal is not None and res.refusal.reason == "key-other-tier"
    res = _decline(tmp_path, "specs", tier="sdd", key="specs/F3-old/tasks-python.md")
    assert res.refusal is None


def test_set_form_clear_with_held_back_key_exits_3_and_writes_once(tmp_path, monkeypatch):
    _trg._seed_unsat_key(tmp_path, "specs/F1-x/spec.md")
    _seed(tmp_path, "specs/F1-x/design.md")
    persists = []
    real = pr._persist_or_unlink_marker
    monkeypatch.setattr(pr, "_persist_or_unlink_marker", lambda *a, **k: persists.append(1) or real(*a, **k))
    res = _decline(tmp_path, "specs/F1-x")
    assert res.held_back == ("specs/F1-x/spec.md",) and res.cleared == ("specs/F1-x/design.md",)
    assert len(persists) == 1
    _, code = pr.format_decline_output(
        list(res.cleared), list(res.held_back), [], restore_cmd="r", project_root=tmp_path
    )
    assert code == 3


def test_dotdot_key_alone_cleared_as_flagged_malformed(tmp_path):
    (tmp_path / "specs" / "F1-x").mkdir(parents=True)
    k = "specs/F1-x/../F1-x/spec.md"
    _seed(tmp_path, k)
    res = _decline(tmp_path, ".")
    assert res.refusal is None and res.flagged == (k,)
    msg, _ = pr.format_decline_output([], [], [k], restore_cmd="x", project_root=tmp_path)
    assert bc.DECLINE_FLAGGED_MALFORMED_MSG.format(doc_rel=k) in msg


def test_dotdot_key_with_f1_keys_refused_as_multi_scope(tmp_path):
    (tmp_path / "specs" / "F1-x").mkdir(parents=True)
    _seed(tmp_path, "specs/F1-x/spec.md", "specs/F1-x/../F1-x/design.md")
    res = _decline(tmp_path, "specs/F1-x")
    assert res.refusal is not None and res.refusal.reason == "multi-scope"


def test_flagged_malformed_message_not_escaping():
    assert "containment-escaping" not in bc.DECLINE_FLAGGED_MALFORMED_MSG
    assert "containment-escaping" in bc.DECLINE_FLAGGED_ESCAPING_MSG


def test_format_decline_output_without_project_root_unchanged():
    msg, code = pr.format_decline_output(["a/spec.md"], [], ["b/spec.md"], restore_cmd="r")
    assert msg == (
        "Declined upstream panel re-review; cleared 1 pending entry: a/spec.md\n"
        + bc.DECLINE_FLAGGED_ANOMALOUS_MSG.format(doc_rel="b/spec.md")
    )
    assert code == 3


def test_refusal_states_clean_scope_command_waits_for_anomaly(tmp_path):
    _seed(tmp_path, "specs/F1-x/spec.md", "specs/F2-y/spec.md")
    _seed(tmp_path, "specs/F1-x/./design.md")
    res = _decline(tmp_path, "specs")
    text = _refusal_text(tmp_path, res, "specs")
    assert "stays refused until" in text and "resolved by hand" in text


def test_decline_echo_routes_hostile_key_through_display_text(tmp_path):
    k = "specs/F1-x/sp\x1b[2Jec .md"
    msg, _ = pr.format_decline_output([k], [k], [k], restore_cmd="r", project_root=tmp_path)
    assert "\x1b" not in msg and " " not in msg
    assert len(msg.splitlines()) == 3


def test_nul_key_only_entry_root_decline_cleared_with_escaping_msg(tmp_path):
    k = "specs/F1-x\x00/spec.md"
    _seed(tmp_path, k, make_dirs=False)
    res = _decline(tmp_path, ".")
    assert res.refusal is None and res.flagged == (k,)
    msg, _ = pr.format_decline_output([], [], list(res.flagged), restore_cmd="r", project_root=tmp_path)
    assert "containment-escaping" in msg


def test_worst_case_230_char_key_refusal_command_intact(tmp_path):
    long_dir = "specs/" + "F3-" + "x" * 200
    key = f"{long_dir}/spec.md"
    assert len(key) >= 210
    _seed(tmp_path, "specs/F1-x/spec.md")
    _seed(tmp_path, key, make_dirs=False)
    res = _decline(tmp_path, "specs")
    text = _refusal_text(tmp_path, res, "specs")
    cmd_lines = [ln for ln in text.splitlines() if "--decline-key=" in ln]
    assert cmd_lines
    cmd = cmd_lines[0].split("`")[1]
    assert len(cmd) > 200
    assert shlex.split(cmd) == [
        "validate_spec.py", "./specs", "--decline-pending", f"--decline-key={key}",
    ]


def test_blueprint_common_reexports_scoped_decline_names():
    for name in (
        "decline_pending_scoped", "format_decline_refusal", "DeclineRefusal",
        "DeclineResult", "scope_of_key", "tier_of_scope", "partition_keys",
        "is_containment_escaping", "owning_dir_route",
        "BLUEPRINT_ARTIFACT_NAMES", "SDD_ARTIFACT_NAMES",
    ):
        assert getattr(bc, name) is getattr(pr, name), name


# --- T12: reconcile_to_result routes (AD16) ----------------------------------


def _checks(res):
    return [c[2] for c in res.checks]


def test_stranded_warn_existing_dir_routes_to_owning_decline(tmp_path):
    (tmp_path / "specs" / "F3-old").mkdir(parents=True)
    bc.upsert_pending_entry(tmp_path, "specs/F3-old/spec.md", H, "t", 1)
    (tmp_path / "specs" / "F1-x").mkdir(parents=True)
    res = pr.reconcile_to_result(
        tmp_path, "specs/F1-x", decline_cmd="x", running_tier="sdd"
    )
    blob = " | ".join(_checks(res))
    assert bc.STRANDED_OBLIGATION_TOKEN in blob
    assert "for the session or user that owns specs/F3-old" in blob
    assert "`validate_spec.py ./specs/F3-old --decline-pending`" in blob
    assert USER_DECISION_NOTE in blob
    assert "against its original location" not in blob
    assert res.passed and res.has_warnings


def test_stranded_warn_vanished_dir_gives_ancestor_route(tmp_path):
    (tmp_path / "specs" / "F1-x").mkdir(parents=True)
    bc.upsert_pending_entry(tmp_path, "specs/F3-old/spec.md", H, "t", 1)
    res = pr.reconcile_to_result(
        tmp_path, "specs/F1-x", decline_cmd="x", running_tier="sdd"
    )
    blob = " | ".join(_checks(res))
    assert "the owning directory specs/F3-old no longer exists on disk" in blob
    assert "`validate_spec.py ./specs --decline-pending`" in blob


def test_gate_fail_other_scope_key_uses_gate_fail_template(tmp_path):
    (tmp_path / "specs" / "F1-x").mkdir(parents=True)
    (tmp_path / "specs" / "F1-x" / "spec.md").write_text("# s\n", encoding="utf-8")
    bc.upsert_pending_entry(tmp_path, "specs/F1-x/spec.md", H, "t", 1)
    res = pr.reconcile_to_result(tmp_path, ".", decline_cmd="ROOTCMD", running_tier="blueprint")
    blob = " | ".join(_checks(res))
    assert not res.passed
    assert "owned by specs/F1-x: decline it from there: `validate_spec.py ./specs/F1-x --decline-pending`" in blob
    assert "ROOTCMD" not in blob


def test_gate_fail_own_scope_key_keeps_decline_cmd(tmp_path):
    (tmp_path / "specs" / "F1-x").mkdir(parents=True)
    (tmp_path / "specs" / "F1-x" / "spec.md").write_text("# s\n", encoding="utf-8")
    bc.upsert_pending_entry(tmp_path, "specs/F1-x/spec.md", H, "t", 1)
    res = pr.reconcile_to_result(tmp_path, "specs/F1-x", decline_cmd="OWNCMD", running_tier="sdd")
    blob = " | ".join(_checks(res))
    assert "OR decline: `OWNCMD`" in blob
    assert "owned by" not in blob


def test_reconcile_running_tier_default_keeps_existing_callers(tmp_path):
    bc.upsert_pending_entry(tmp_path, "specs/F3-old/spec.md", H, "t", 1)
    res = bc.reconcile_to_result(tmp_path, "specs/F3-new", decline_cmd="x")
    blob = " | ".join(_checks(res))
    assert bc.STRANDED_OBLIGATION_TOKEN in blob and "specs/F3-old/spec.md" in blob
    assert res.passed and res.has_warnings


def test_reconcile_nul_key_root_target_does_not_raise(tmp_path):
    bc.upsert_pending_entry(tmp_path, "specs/F1-x/spec.md", H, "t", 1)
    _add_raw_key(tmp_path, "specs/F1-x\x00/spec.md")
    res = pr.reconcile_to_result(tmp_path, ".", decline_cmd="x", running_tier="sdd")
    assert not res.passed
    assert all("\x00" not in c for c in _checks(res))


def test_nested_target_nul_key_stranded_loop_does_not_raise(tmp_path):
    bc.upsert_pending_entry(tmp_path, "specs/F1-x/spec.md", H, "t", 1)
    _add_raw_key(tmp_path, "specs/F2\x00/spec.md")
    res = pr.reconcile_to_result(tmp_path, "specs/F1-x", decline_cmd="x", running_tier="sdd")
    assert all("\x00" not in c for c in _checks(res))


def test_reconcile_expected_tag_echo_through_display_text(tmp_path):
    (tmp_path / "specs" / "F1-x").mkdir(parents=True)
    (tmp_path / "specs" / "F1-x" / "spec.md").write_text("# s\n", encoding="utf-8")
    bc.upsert_pending_entry(tmp_path, "specs/F1-x/spec.md", H, "t", 1)
    _set_hash(tmp_path, "specs/F1-x/spec.md", "\x1b[2J" + "a" * 12)
    res = pr.reconcile_to_result(tmp_path, "specs/F1-x", decline_cmd="x", running_tier="sdd")
    for c in _checks(res):
        assert "\x1b" not in c


def _add_raw_key(root: Path, key: str, hash16: str = H) -> None:
    p = root / ".sdd" / "pending-review.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["pending"][key] = dict(next(iter(d["pending"].values())), hash=hash16)
    p.write_text(json.dumps(d), encoding="utf-8")


# --- T13: --run-state partition and notices (AD17) ---------------------------

import run_state as rs  # noqa: E402

_SDD_PHASES = [("Specify", "spec.md"), ("Design", "design.md"), ("Tasks", "tasks.md")]
_BP_PHASES = [("Scope", "SCOPE.md"), ("Architecture", "ARCHITECTURE.md"), ("Plan", "PLAN.md")]


def _rs(root: Path, target: str, tier: str = "blueprint"):
    d = root / target if target != "." else root
    d.mkdir(parents=True, exist_ok=True)
    state = rs.derive_run_state(
        tier=tier, artifact_dir=d, project_root=root,
        phases=_BP_PHASES if tier == "blueprint" else _SDD_PHASES,
        terminal_phase_label=None if tier == "blueprint" else "Implement",
        tick_hint_artifact=None if tier == "blueprint" else "tasks.md",
    )
    return state, rs.format_run_state(state)


def test_run_state_two_tier_marker_lists_elsewhere_as_informational(tmp_path):
    _seed(tmp_path, "blueprint/01_SCOPE.md", "specs/F1-x/01_spec.md")
    state, out = _rs(tmp_path, "blueprint")
    assert [o.detail for o in state.obligations] == [
        "upstream panel re-review pending for blueprint/01_SCOPE.md"
    ]
    assert [(n.kind, n.subject) for n in state.notices] == [
        (rs.NOTICE_PENDING_ELSEWHERE, "specs/F1-x")
    ]
    line = [ln for ln in out.splitlines() if "pending elsewhere" in ln][0]
    assert "pending elsewhere — not resolvable from here" in line
    assert "specs/F1-x" in line
    assert "./blueprint --decline-pending" not in line
    assert "`validate_spec.py ./specs/F1-x --decline-pending`" in line


def test_run_state_vanished_owner_states_missing_directory(tmp_path):
    _seed(tmp_path, "blueprint/SCOPE.md")
    _seed(tmp_path, "specs/F3-old/spec.md", make_dirs=False)
    (tmp_path / "specs").mkdir()
    _, out = _rs(tmp_path, "blueprint")
    line = [ln for ln in out.splitlines() if "pending elsewhere" in ln][0]
    assert "the owning directory specs/F3-old no longer exists on disk" in line
    assert "`validate_spec.py ./specs --decline-pending`" in line


def test_run_state_all_clear_with_elsewhere_entry(tmp_path):
    _seed(tmp_path, "specs/F1-x/spec.md")
    _, out = _rs(tmp_path, "blueprint")
    lines = out.splitlines()
    assert lines[1].startswith("all clear — ")
    assert any("pending elsewhere — not resolvable from here: specs/F1-x" in ln for ln in lines)


def test_run_state_three_scopes_only_own_actionable(tmp_path):
    _seed(tmp_path, "blueprint/SCOPE.md", "specs/F1-x/spec.md", "specs/F2-y/spec.md")
    state, _ = _rs(tmp_path, "specs/F1-x", tier="sdd")
    assert [o.detail for o in state.obligations] == [
        "upstream panel re-review pending for specs/F1-x/spec.md"
    ]
    assert sorted(n.subject for n in state.notices) == ["blueprint", "specs/F2-y"]


def test_root_target_obligations_get_owned_by_next_action(tmp_path):
    _seed(tmp_path, "PLAN.md", "specs/F1-x/spec.md")
    state, _ = _rs(tmp_path, ".")
    by = {o.detail.rsplit(" ", 1)[1]: o.next_action for o in state.obligations}
    assert by["PLAN.md"].startswith("run the panel")
    assert by["specs/F1-x/spec.md"].startswith("owned by specs/F1-x — ")
    assert state.notices == []


def test_out_of_lane_escaping_keys_form_no_scope_group(tmp_path):
    _seed(tmp_path, "specs/F1-x/spec.md", "../evil/spec.md", "/abs/x/spec.md", "zeta/PLAN.md")
    state, _ = _rs(tmp_path, "specs/F1-x", tier="sdd")
    subjects = [n.subject for n in state.notices]
    assert subjects == ["zeta", rs.NO_SCOPE_SUBJECT]
    no_scope = state.notices[-1]
    assert no_scope.detail.startswith("2 obligations")
    assert "`validate_spec.py . --decline-pending`" in no_scope.route


def test_escaping_key_in_lane_run_state_route_is_target_decline(tmp_path):
    _seed(tmp_path, "specs/F1-x/../../../evil/spec.md")
    state, _ = _rs(tmp_path, "specs/F1-x", tier="sdd")
    assert len(state.obligations) == 1
    assert "`validate_spec.py ./specs/F1-x --decline-pending`" in state.obligations[0].next_action


def _many_scopes(root: Path, n: int) -> None:
    _seed(root, *[f"specs/F{i:02d}-s/spec.md" for i in range(1, n + 1)])


def test_collapsed_pending_elsewhere_line_three_scopes_and_n_more(tmp_path):
    _many_scopes(tmp_path, 30)
    _seed(tmp_path, "blueprint/SCOPE.md")
    _, out = _rs(tmp_path, "blueprint")
    lines = out.splitlines()
    assert len(lines) <= 24
    pe = [ln for ln in lines if "pending elsewhere" in ln]
    assert pe == [
        "  pending elsewhere — not resolvable from here: specs/F01-s (1), "
        "specs/F02-s (1), specs/F03-s (1) and 27 more — resolve each from its "
        "own directory, starting with `validate_spec.py ./specs/F01-s --run-state`"
    ]


def test_collapsed_form_one_to_three_groups_has_no_and_more():
    notices = [
        rs.Notice(rs.NOTICE_PENDING_ELSEWHERE, f"s{i}", "1 obligation",
                  f"owned by s{i} — resolve it from that directory: run its panel, or run the decline there: `validate_spec.py ./s{i} --decline-pending`")
        for i in range(3)
    ]
    line = rs._collapsed_notice_line(rs.NOTICE_PENDING_ELSEWHERE, notices)
    listed = line.split("not resolvable from here: ", 1)[1].split(" — ", 1)[0]
    assert listed == "s0 (1), s1 (1), s2 (1)"


def test_collapsed_route_uses_first_existing_scope():
    notices = [
        rs.Notice(rs.NOTICE_PENDING_ELSEWHERE, "a-gone", "1 obligation",
                  "the owning directory a-gone no longer exists on disk — decline it ..."),
        rs.Notice(rs.NOTICE_PENDING_ELSEWHERE, "b", "2 obligations",
                  "owned by b — resolve it from that directory: run its panel, or run the decline there: `validate_blueprint.py ./b --decline-pending`"),
    ]
    line = rs._collapsed_notice_line(rs.NOTICE_PENDING_ELSEWHERE, notices)
    assert line.endswith("starting with `validate_blueprint.py ./b --run-state`")
    assert "a-gone (1), b (2) —" in line


def test_obligations_never_dropped_past_ceiling(tmp_path):
    _seed(tmp_path, *[f"blueprint/x{i}/SCOPE.md" for i in range(30)])
    _many_scopes(tmp_path, 10)
    state, out = _rs(tmp_path, "blueprint")
    assert len(state.obligations) == 30
    assert sum(1 for ln in out.splitlines() if ln.startswith("  - pending-review")) == 30
    assert sum(1 for ln in out.splitlines() if "pending elsewhere" in ln) == 1


def test_notices_collapse_before_artifact_lines_fold():
    arts = [rs.ArtifactState(f"a{i}.md", True, False, rs.HashStatus.NA) for i in range(20)]
    notices = [
        rs.Notice(rs.NOTICE_PENDING_ELSEWHERE, f"s{i}", "1 obligation", f"owned by s{i} — x `c ./s{i} --decline-pending`")
        for i in range(10)
    ]
    state = rs.RunState("sdd", "Design", arts, [], "n", notices)
    lines = rs.format_run_state(state).splitlines()
    assert len(lines) <= 24
    assert sum(1 for ln in lines if "pending elsewhere" in ln) == 1
    assert not any("more — run the full validator" in ln for ln in lines)


def test_command_lines_exempt_from_line_cap(tmp_path):
    long_dir = "specs/" + "F3-" + "x" * 200
    _seed(tmp_path, "blueprint/SCOPE.md")
    _seed(tmp_path, f"{long_dir}/spec.md")
    _, out = _rs(tmp_path, "blueprint")
    line = [ln for ln in out.splitlines() if "pending elsewhere" in ln][0]
    assert len(line) > 200
    cmd = line.split("`")[1]
    assert shlex.split(cmd) == ["validate_spec.py", f"./{long_dir}", "--decline-pending"]


def test_notice_fields_literal_tuple_pinned():
    import dataclasses

    assert rs.NOTICE_FIELDS == ("kind", "subject", "detail", "route")
    assert tuple(f.name for f in dataclasses.fields(rs.Notice)) == rs.NOTICE_FIELDS


def test_core_run_state_fields_include_notices():
    assert rs.CORE_RUN_STATE_FIELDS[-1] == "notices"


def test_run_state_with_notices_exits_0_and_writes_nothing(tmp_path):
    import subprocess

    _seed(tmp_path, "blueprint/SCOPE.md", "specs/F1-x/spec.md")
    (tmp_path / ".git").mkdir()
    # The pre-existing atexit cruft sweep removes the marker's .lock file; that
    # is not a content write, so lock files are excluded from the comparison.
    def _snap():
        return {p: p.read_bytes() for p in tmp_path.rglob("*")
                if p.is_file() and p.suffix != ".lock"}

    before = _snap()
    vb = _SCRIPTS.parent / "skills" / "project-blueprint" / "scripts" / "validate_blueprint.py"
    proc = subprocess.run(
        [sys.executable, str(vb), str(tmp_path / "blueprint"), "--run-state",
         "--project-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "pending elsewhere — not resolvable from here" in proc.stdout
    assert before == _snap()


def test_nul_key_run_state_route_is_root_own_decline(tmp_path):
    bc.upsert_pending_entry(tmp_path, "PLAN.md", H, "t", 1)
    _add_raw_key(tmp_path, "specs/F1-x\x00/spec.md")
    p = tmp_path / ".sdd" / "pending-review.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    del d["pending"]["PLAN.md"]
    p.write_text(json.dumps(d), encoding="utf-8")
    state, out = _rs(tmp_path, ".")
    assert len(state.obligations) == 1
    assert "`validate_blueprint.py . --decline-pending`" in state.obligations[0].next_action
    assert "\x00" not in out


# --- T14: CLI wiring of the scoped decline and --decline-key ----------------

import subprocess  # noqa: E402

_VS = _SCRIPTS.parent / "skills" / "spec-driven-dev" / "scripts" / "validate_spec.py"
_VB = _SCRIPTS.parent / "skills" / "project-blueprint" / "scripts" / "validate_blueprint.py"


def _cli(tier: str, root: Path, target: str, *args: str) -> "subprocess.CompletedProcess[str]":
    d = root / target if target != "." else root
    d.mkdir(parents=True, exist_ok=True)
    script = _VS if tier == "sdd" else _VB
    return subprocess.run(
        [sys.executable, str(script), str(d), *args, "--project-root", str(root)],
        capture_output=True, text=True,
    )


def test_cli_two_tier_decline_each_clears_own(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    for r in (a, b):
        r.mkdir()
        _seed(r, "blueprint/SCOPE.md", "specs/F1-x/spec.md")
    pa = _cli("blueprint", a, "blueprint", "--decline-pending")
    assert pa.returncode == 0, pa.stdout + pa.stderr
    assert _pending(a) == ["specs/F1-x/spec.md"]
    pb = _cli("sdd", b, "specs/F1-x", "--decline-pending")
    assert pb.returncode == 0, pb.stdout + pb.stderr
    assert _pending(b) == ["blueprint/SCOPE.md"]


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_cli_multi_scope_decline_refused_exit_4_both_tiers(tmp_path, tier):
    _seed(tmp_path, "blueprint/SCOPE.md", "specs/F1-x/spec.md")
    before = _marker_bytes(tmp_path)
    proc = _cli(tier, tmp_path, ".", "--decline-pending")
    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert "Refusing --decline-pending" in proc.stdout
    assert _marker_bytes(tmp_path) == before


def test_cli_decline_key_success_names_key_and_scope(tmp_path):
    _seed(tmp_path, "specs/F1-x/spec.md")
    _seed(tmp_path, "specs/F3-old/spec.md", make_dirs=False)
    proc = _cli("sdd", tmp_path, "specs", "--decline-pending",
                "--decline-key=specs/F3-old/spec.md")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "specs/F3-old/spec.md" in proc.stdout and "(scope specs/F3-old)" in proc.stdout
    assert _pending(tmp_path) == ["specs/F1-x/spec.md"]


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_cli_decline_key_without_decline_pending_exit_2(tmp_path, tier):
    _seed(tmp_path, "specs/F1-x/spec.md")
    proc = _cli(tier, tmp_path, "specs/F1-x", "--decline-key=specs/F1-x/spec.md")
    assert proc.returncode == 2
    assert "--decline-key" in (proc.stdout + proc.stderr)


def test_cli_run_state_partition_both_tiers(tmp_path):
    _seed(tmp_path, "blueprint/SCOPE.md", "specs/F1-x/spec.md")
    pb = _cli("blueprint", tmp_path, "blueprint", "--run-state")
    ps = _cli("sdd", tmp_path, "specs/F1-x", "--run-state")
    assert pb.returncode == ps.returncode == 0
    assert "pending elsewhere — not resolvable from here: specs/F1-x" in pb.stdout
    assert "pending elsewhere — not resolvable from here: blueprint" in ps.stdout
    assert "for blueprint/SCOPE.md →" in pb.stdout
    assert "for specs/F1-x/spec.md →" in ps.stdout


_ANOMALOUS = ["./specs/F1-x/spec.md", "specs//F1-x/spec.md", "specs/F1-x/../F1-x/spec.md"]


@pytest.mark.parametrize("key", _ANOMALOUS)
def test_cli_run_state_anomalous_key_prints_inspect_by_hand(tmp_path, key):
    (tmp_path / "specs" / "F1-x").mkdir(parents=True)
    _seed(tmp_path, key)
    proc = _cli("sdd", tmp_path, ".", "--run-state")
    assert proc.returncode == 0
    line = [ln for ln in proc.stdout.splitlines() if "pending-review" in ln][0]
    assert "has `.`, `..` or empty path segments" in line
    assert "--decline-pending`" not in line


@pytest.mark.parametrize("key", _ANOMALOUS)
def test_cli_multi_scope_refusal_with_anomalous_key_prints_inspect_by_hand(tmp_path, key):
    (tmp_path / "specs" / "F1-x").mkdir(parents=True)
    _seed(tmp_path, "specs/F2-y/spec.md", key)
    proc = _cli("sdd", tmp_path, ".", "--decline-pending")
    assert proc.returncode == 4, proc.stdout
    lines = proc.stdout.splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.strip() == key)
    route = lines[i + 1]
    assert "has `.`, `..` or empty path segments" in route
    assert "--decline-pending`" not in route
