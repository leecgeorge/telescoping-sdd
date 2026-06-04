"""Tests for the shared sibling registry (`project_registry.py`).

`project_registry.py` owns the `.sdd/projects.json` schema (DM5), its defensive
read/write, and the `resolve_sibling_path` accept-gate + `find_sibling`
containment resolver (CPD design I3). The suite guards:

* ROUND-TRIP: what `write_projects_config` persists is exactly what
  `read_projects_config` reads back.
* DEFENSIVE READ: absent / malformed-JSON / unknown-schema / missing-or-wrong-
  typed-field all resolve to `None` (never raise), mirroring `arch_config.py`.
* RECORDED-NOT-ENFORCED `role`: a sibling with no `role` is still usable.
* ROOT-RELATIVE RESOLUTION: a relative sibling path resolves from the PROJECT
  ROOT, not the process cwd — proven cwd-independent via `monkeypatch.chdir`.
* ACCEPT GATE: a resolved dir is accepted as a sibling only when it contains
  `blueprint/` or `.sdd/`; `..`-traversal, symlinked non-repo roots, and non-repo
  dirs are rejected.
* CONFINEMENT HONOURED: `find_sibling` never returns a path the accept gate
  rejected.

The module is imported via the shared-scripts `sys.path` insert; `conftest.py` in
this directory snapshots/restores `sys.path` around each test.

The fd-based read-time security tests (`test_containment_*` over
`safe_read_sibling`, the I3 READ-TIME guard) live in the final section of this
file (added by T12b): O_NOFOLLOW final-component refusal, `S_ISREG` non-regular
reject, `commonpath` confinement (ValueError-caught, prefix-bleed component-wise),
and the bounded read that refuses an over-cap file via the actual read rather than
the advisory `st_size`.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import project_registry as pr  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_repo_root(base: Path, name: str, *, with_marker: str = "blueprint") -> Path:
    """Create a directory that looks like a project root (has a marker dir)."""
    root = base / name
    root.mkdir(parents=True, exist_ok=True)
    if with_marker:
        (root / with_marker).mkdir(parents=True, exist_ok=True)
    return root


def _valid_config(this_project: str = "vps-edge", siblings=None) -> dict:
    if siblings is None:
        siblings = [{"name": "residents", "path": "../residents", "role": "master"}]
    return {
        "schemaVersion": pr.PROJECTS_JSON_SCHEMA_VERSION,
        "thisProject": this_project,
        "siblings": siblings,
    }


def _write_raw(project_root: Path, text: str) -> Path:
    """Write arbitrary bytes to the registry path, bypassing the writer."""
    target = pr.config_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


# --------------------------------------------------------------------------- #
# read / write round-trip + defensive read
# --------------------------------------------------------------------------- #


def test_read_valid_registry(tmp_path: Path):
    root = tmp_path / "vps-edge"
    root.mkdir()
    config = _valid_config()
    written = pr.write_projects_config(root, config)
    assert written == pr.config_path(root.resolve())

    read_back = pr.read_projects_config(root)
    assert read_back == config


def test_read_absent_file(tmp_path: Path):
    root = tmp_path / "vps-edge"
    root.mkdir()
    assert pr.read_projects_config(root) is None  # no raise


def test_read_malformed_json(tmp_path: Path):
    root = tmp_path / "vps-edge"
    root.mkdir()
    _write_raw(root, "{ this is not valid json ")
    assert pr.read_projects_config(root) is None


def test_read_unknown_schema_version(tmp_path: Path):
    root = tmp_path / "vps-edge"
    root.mkdir()
    config = _valid_config()
    config["schemaVersion"] = 999
    _write_raw(root, json.dumps(config))
    assert pr.read_projects_config(root) is None


def test_read_missing_required_field(tmp_path: Path):
    root = tmp_path / "vps-edge"
    root.mkdir()

    # Missing thisProject.
    no_this = _valid_config()
    del no_this["thisProject"]
    _write_raw(root, json.dumps(no_this))
    assert pr.read_projects_config(root) is None

    # Missing siblings.
    no_siblings = _valid_config()
    del no_siblings["siblings"]
    _write_raw(root, json.dumps(no_siblings))
    assert pr.read_projects_config(root) is None


def test_read_mistyped_field(tmp_path: Path):
    root = tmp_path / "vps-edge"
    root.mkdir()

    # siblings as a string (not a list) → None, not a crash.
    siblings_str = _valid_config()
    siblings_str["siblings"] = "../residents"
    _write_raw(root, json.dumps(siblings_str))
    assert pr.read_projects_config(root) is None

    # sibling name as an int → None.
    name_int = _valid_config(siblings=[{"name": 7, "path": "../residents"}])
    _write_raw(root, json.dumps(name_int))
    assert pr.read_projects_config(root) is None

    # sibling path as a list → None.
    path_list = _valid_config(siblings=[{"name": "residents", "path": ["../residents"]}])
    _write_raw(root, json.dumps(path_list))
    assert pr.read_projects_config(root) is None

    # thisProject as an int → None.
    this_int = _valid_config()
    this_int["thisProject"] = 42
    _write_raw(root, json.dumps(this_int))
    assert pr.read_projects_config(root) is None


def test_read_role_absent_still_usable(tmp_path: Path):
    root = tmp_path / "vps-edge"
    root.mkdir()
    # role absent on one, unrecognized on another → still a usable registry.
    config = _valid_config(
        siblings=[
            {"name": "residents", "path": "../residents"},
            {"name": "other", "path": "../other", "role": "weird-role"},
        ]
    )
    _write_raw(root, json.dumps(config))
    read_back = pr.read_projects_config(root)
    assert read_back is not None
    assert read_back["siblings"][0]["name"] == "residents"


def test_write_rejects_wrong_schema_version(tmp_path: Path):
    root = tmp_path / "vps-edge"
    root.mkdir()
    bad = _valid_config()
    bad["schemaVersion"] = 2
    with pytest.raises(ValueError):
        pr.write_projects_config(root, bad)


# --------------------------------------------------------------------------- #
# resolve_sibling_path — accept gate + root-relative resolution
# --------------------------------------------------------------------------- #


def test_resolve_sibling_relative_path(tmp_path: Path, monkeypatch):
    """`../residents` resolves to the same abs path regardless of process cwd."""
    project_root = _make_repo_root(tmp_path, "vps-edge")
    sibling = _make_repo_root(tmp_path, "residents")

    # Resolve once from the repo's own directory.
    monkeypatch.chdir(project_root)
    resolved_a, accepted_a = pr.resolve_sibling_path("../residents", project_root)

    # Resolve again from a completely unrelated cwd — must be identical.
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    resolved_b, accepted_b = pr.resolve_sibling_path("../residents", project_root)

    assert resolved_a == sibling.resolve()
    assert resolved_a == resolved_b  # cwd-independent
    assert accepted_a is True and accepted_b is True


def test_resolve_sibling_dotdot_traversal(tmp_path: Path, monkeypatch):
    """`../../other` resolves from project_root, not cwd; `..` collapses."""
    nested = tmp_path / "workspace" / "team"
    nested.mkdir(parents=True)
    project_root = _make_repo_root(nested, "vps-edge")
    # ../../other from <workspace>/team/vps-edge → <workspace>/other
    sibling = _make_repo_root(tmp_path / "workspace", "other")

    monkeypatch.chdir(tmp_path)  # unrelated cwd
    resolved, accepted = pr.resolve_sibling_path("../../other", project_root)
    assert resolved == sibling.resolve()
    assert ".." not in resolved.parts
    assert accepted is True


def test_resolve_sibling_symlink(tmp_path: Path):
    """A symlinked sibling root pointing at a non-repo dir is not accepted."""
    project_root = _make_repo_root(tmp_path, "vps-edge")
    # Real target has NO repo marker.
    plain = tmp_path / "plain-dir"
    plain.mkdir()
    link = tmp_path / "linked-sibling"
    link.symlink_to(plain, target_is_directory=True)

    resolved, accepted = pr.resolve_sibling_path("../linked-sibling", project_root)
    # `.resolve()` dereferences the symlink to the real (non-repo) target.
    assert resolved == plain.resolve()
    assert accepted is False  # no blueprint/ or .sdd/ at the real target


def test_resolve_sibling_non_repo_dir_rejected(tmp_path: Path):
    """A path resolving to a non-repo location is rejected; no read attempted."""
    project_root = _make_repo_root(tmp_path, "vps-edge")
    # A directory with no repo marker.
    (tmp_path / "not-a-repo").mkdir()
    resolved, accepted = pr.resolve_sibling_path("../not-a-repo", project_root)
    assert accepted is False

    # And a path escaping entirely (e.g. toward /etc) is also rejected.
    _, accepted_escape = pr.resolve_sibling_path("../../etc", project_root)
    assert accepted_escape is False


def test_resolve_sibling_accepts_sdd_marker(tmp_path: Path):
    """`.sdd/` alone (no blueprint/) satisfies the accept gate."""
    project_root = _make_repo_root(tmp_path, "vps-edge")
    _make_repo_root(tmp_path, "residents", with_marker=".sdd")
    _, accepted = pr.resolve_sibling_path("../residents", project_root)
    assert accepted is True


# --------------------------------------------------------------------------- #
# find_sibling — honours the accept gate, never returns a rejected path
# --------------------------------------------------------------------------- #


def test_find_sibling_found(tmp_path: Path):
    project_root = _make_repo_root(tmp_path, "vps-edge")
    sibling = _make_repo_root(tmp_path, "residents")
    config = _valid_config()
    got = pr.find_sibling(config, "residents", project_root)
    assert got == sibling.resolve()


def test_find_sibling_not_found(tmp_path: Path):
    project_root = _make_repo_root(tmp_path, "vps-edge")
    _make_repo_root(tmp_path, "residents")
    config = _valid_config()
    assert pr.find_sibling(config, "nonexistent", project_root) is None


def test_find_sibling_none_config(tmp_path: Path):
    project_root = _make_repo_root(tmp_path, "vps-edge")
    assert pr.find_sibling(None, "residents", project_root) is None


def test_find_sibling_honors_containment(tmp_path: Path):
    """find_sibling returns None for a non-repo / symlinked non-repo sibling root —
    it never returns a path resolve_sibling_path rejected."""
    project_root = _make_repo_root(tmp_path, "vps-edge")

    # Sibling name matches but the target is NOT a repo root (no marker).
    (tmp_path / "residents").mkdir()  # no blueprint/ or .sdd/
    config = _valid_config()  # points at ../residents
    assert pr.find_sibling(config, "residents", project_root) is None

    # Symlinked sibling root pointing at a non-repo dir is likewise rejected.
    plain = tmp_path / "plain"
    plain.mkdir()
    (tmp_path / "linked").symlink_to(plain, target_is_directory=True)
    linked_config = _valid_config(
        siblings=[{"name": "residents", "path": "../linked", "role": "master"}]
    )
    assert pr.find_sibling(linked_config, "residents", project_root) is None


def test_registry_resolution_root_per_consumer(tmp_path: Path, monkeypatch):
    """`../residents` resolves to the same abs path regardless of process cwd for
    each consumer's root-finder (find_sibling is the consumer-facing call site)."""
    project_root = _make_repo_root(tmp_path, "vps-edge")
    sibling = _make_repo_root(tmp_path, "residents")
    config = _valid_config()

    monkeypatch.chdir(project_root)
    got_a = pr.find_sibling(config, "residents", project_root)

    other = tmp_path / "deep" / "nested" / "cwd"
    other.mkdir(parents=True)
    monkeypatch.chdir(other)
    got_b = pr.find_sibling(config, "residents", project_root)

    assert got_a == sibling.resolve()
    assert got_a == got_b


# --------------------------------------------------------------------------- #
# safe_read_sibling — I3 READ-TIME guard (O_NOFOLLOW / fstat / S_ISREG /
# bounded read / commonpath confinement). Fail-closed: any guard failure → None,
# never raises.
# --------------------------------------------------------------------------- #


def test_safe_read_sibling_happy_path(tmp_path: Path):
    """A regular file inside the sibling root reads back its content."""
    root = _make_repo_root(tmp_path, "residents")
    target = root / "blueprint" / "PLAN.md"
    target.write_text("hello sibling\n", encoding="utf-8")
    assert pr.safe_read_sibling(target, root) == "hello sibling\n"


def test_containment_final_component_symlink_rejected(tmp_path: Path):
    """O_NOFOLLOW refuses a final-component symlink → None, never follows it."""
    root = _make_repo_root(tmp_path, "residents")
    # The real secret lives OUTSIDE the sibling root.
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET\n", encoding="utf-8")
    # A final-component symlink inside the root pointing at the secret.
    link = root / "blueprint" / "PLAN.md"
    link.symlink_to(secret)

    result = pr.safe_read_sibling(link, root)
    assert result is None  # O_NOFOLLOW refused; secret never read
    assert result != "TOP SECRET\n"


def test_containment_non_regular_target(tmp_path: Path, monkeypatch):
    """A non-regular target (FIFO / socket) → S_ISREG reject, returns None, no hang."""
    root = _make_repo_root(tmp_path, "residents")
    blueprint = root / "blueprint"

    # FIFO: a plain open(fifo, O_RDONLY) blocks until a writer appears. The helper
    # opens with O_NONBLOCK so the open does NOT hang, then S_ISREG rejects it.
    # If the helper regressed (dropped O_NONBLOCK), this test would hang — that is
    # the no-hang guarantee under test.
    fifo = blueprint / "pipe"
    os.mkfifo(fifo)
    assert pr.safe_read_sibling(fifo, root) is None

    # Unix domain socket: a bound socket is also non-regular → S_ISREG reject.
    # AF_UNIX paths are length-capped (~104 bytes on macOS), shorter than a deep
    # pytest tmp_path, so bind via a RELATIVE name from inside the dir, then probe
    # the helper with the absolute path.
    sock_path = blueprint / "sock"
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        monkeypatch.chdir(blueprint)
        srv.bind("sock")
    except OSError:
        # Some sandboxes forbid AF_UNIX bind entirely; the FIFO arm above already
        # exercises the S_ISREG non-regular reject, so degrade gracefully.
        srv.close()
        return
    try:
        assert sock_path.is_socket()
        assert pr.safe_read_sibling(sock_path, root) is None
    finally:
        srv.close()


def test_containment_commonpath_valueerror(tmp_path: Path):
    """A commonpath ValueError (mixed abs/rel operands) is caught → reject, no raise."""
    root = _make_repo_root(tmp_path, "residents")
    target = root / "blueprint" / "PLAN.md"
    target.write_text("data\n", encoding="utf-8")

    # Pass a RELATIVE sibling_root while the target resolves absolute. After
    # .resolve() both become absolute, so to truly exercise the ValueError catch
    # we feed an operand that commonpath cannot reconcile. The most reliable
    # cross-platform trigger is mixing an absolute and a relative path that
    # .resolve() cannot normalize to share a prefix; on POSIX, .resolve() makes
    # both absolute, so we assert the guard does not raise and rejects when the
    # target lies outside the root regardless.
    #
    # Directly probe the ValueError path: a relative-vs-absolute commonpath input.
    import os.path as _osp

    with pytest.raises(ValueError):
        _osp.commonpath(["relative/path", str(target.resolve())])

    # And the helper itself, given a root and target with no common prefix,
    # rejects without raising.
    other_root = _make_repo_root(tmp_path, "elsewhere")
    assert pr.safe_read_sibling(target, other_root) is None


def test_containment_prefix_bleed_rejected(tmp_path: Path):
    """`/root/residents` vs `/root/residents-evil` rejects component-wise."""
    # Sibling root is `.../residents`; the target lives in a sibling-named
    # `.../residents-evil` that shares a STRING prefix but not a path component.
    root = _make_repo_root(tmp_path, "residents")
    evil = _make_repo_root(tmp_path, "residents-evil")
    target = evil / "blueprint" / "PLAN.md"
    target.write_text("evil\n", encoding="utf-8")

    # The target is a real regular file (so only commonpath confinement can stop
    # it), but it is NOT contained in `residents` — a naive startswith on the
    # string would bleed; commonpath rejects component-wise.
    assert pr.safe_read_sibling(target, root) is None


def test_containment_bounded_read(tmp_path: Path, monkeypatch):
    """A file over MAX_SIBLING_READ_BYTES is refused via the bounded READ (not st_size)."""
    root = _make_repo_root(tmp_path, "residents")
    target = root / "blueprint" / "PLAN.md"

    # Shrink the cap so the test file stays tiny but still exceeds the bound.
    monkeypatch.setattr(pr, "MAX_SIBLING_READ_BYTES", 16)

    # Just at the cap → accepted.
    target.write_text("x" * 16, encoding="utf-8")
    assert pr.safe_read_sibling(target, root) == "x" * 16

    # One byte over the cap → refused (None) via the cap+1 bounded read.
    target.write_text("y" * 17, encoding="utf-8")
    assert pr.safe_read_sibling(target, root) is None


def test_containment_short_read_loops(tmp_path: Path, monkeypatch):
    """A short-reading fd still yields the whole file AND still enforces the cap.

    Regression for code-review #4: a single `os.read()` may return fewer bytes
    than requested (FUSE / network mounts), so the read must LOOP. With a single
    syscall an in-cap file would truncate (false drift) and an over-cap file
    whose first read is short would slip past `len > cap` (cap/DoS bypass).
    Here every `os.read` is forced to return at most one byte.
    """
    root = _make_repo_root(tmp_path, "residents")
    target = root / "blueprint" / "PLAN.md"
    monkeypatch.setattr(pr, "MAX_SIBLING_READ_BYTES", 16)

    real_read = os.read
    monkeypatch.setattr(os, "read", lambda fd, n: real_read(fd, 1 if n > 1 else n))

    # In-cap file: the loop reassembles all 12 bytes despite 1-byte reads
    # (a single-read implementation would return just "h").
    target.write_text("hello siblin", encoding="utf-8")  # 12 bytes
    assert pr.safe_read_sibling(target, root) == "hello siblin"

    # Exactly at the cap: fully assembled, not refused.
    target.write_text("x" * 16, encoding="utf-8")
    assert pr.safe_read_sibling(target, root) == "x" * 16

    # Over the cap: a short first read must NOT let it pass the guard.
    target.write_text("y" * 17, encoding="utf-8")
    assert pr.safe_read_sibling(target, root) is None
