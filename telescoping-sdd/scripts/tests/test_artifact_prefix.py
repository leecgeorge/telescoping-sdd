"""Tests for the artifact NN_-prefix feature.

Phase A (Increment 1): the resolution helpers in ``blueprint_common.py``
(``strip_artifact_prefix`` / ``resolve_artifact``). The renamer
(``artifact_prefix.py``), the grep gate, and the cross-validator integration
tests are added in Phase B / T8.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Locate telescoping-sdd/scripts/ relative to this file so the test runs from
# the repo root or any sub-directory (mirrors test_blueprint_common.py).
_SCRIPTS = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for p in (_SCRIPTS, _TESTS):
    if str(p) not in sys.path:
        sys.path.append(str(p))

import pytest

import blueprint_common as bc


def _write(p: Path, content: str = "x") -> Path:
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# strip_artifact_prefix
# ---------------------------------------------------------------------------

def test_strip_artifact_prefix_bare_name_unchanged():
    assert bc.strip_artifact_prefix("spec.md") == "spec.md"


def test_strip_artifact_prefix_known_artifacts():
    assert bc.strip_artifact_prefix("01_spec.md") == "spec.md"
    assert bc.strip_artifact_prefix("02_design.md") == "design.md"
    assert bc.strip_artifact_prefix("03_tasks.md") == "tasks.md"
    assert bc.strip_artifact_prefix("01_SCOPE.md") == "SCOPE.md"
    assert bc.strip_artifact_prefix("02_ARCHITECTURE.md") == "ARCHITECTURE.md"
    assert bc.strip_artifact_prefix("03_PLAN.md") == "PLAN.md"


def test_strip_artifact_prefix_non_artifact_unchanged():
    assert bc.strip_artifact_prefix("12_factor_notes.md") == "12_factor_notes.md"


def test_strip_artifact_prefix_zero_prefix_unchanged():
    # stripped "readme.md" is not a known artifact -> unchanged
    assert bc.strip_artifact_prefix("00_readme.md") == "00_readme.md"


def test_strip_artifact_prefix_user_design_file():
    # stripped result IS a known artifact, so the prefix strips. (A genuine
    # 01_design.md + 02_design.md coexistence is caught by resolve_artifact.)
    assert bc.strip_artifact_prefix("01_design.md") == "design.md"


# ---------------------------------------------------------------------------
# resolve_artifact
# ---------------------------------------------------------------------------

def test_resolve_artifact_bare_exists(tmp_path):
    _write(tmp_path / "spec.md")
    assert bc.resolve_artifact(tmp_path, "spec.md") == tmp_path / "spec.md"


def test_resolve_artifact_prefixed_exists(tmp_path):
    _write(tmp_path / "01_spec.md")
    assert bc.resolve_artifact(tmp_path, "spec.md") == tmp_path / "01_spec.md"


def test_resolve_artifact_absent_returns_bare(tmp_path):
    assert bc.resolve_artifact(tmp_path, "spec.md") == tmp_path / "spec.md"


def test_resolve_artifact_both_exist_raises(tmp_path):
    _write(tmp_path / "spec.md", "a")
    _write(tmp_path / "01_spec.md", "b")
    with pytest.raises(bc.ArtifactAmbiguityError) as exc:
        bc.resolve_artifact(tmp_path, "spec.md")
    assert {p.name for p in exc.value.conflicting_paths} == {"spec.md", "01_spec.md"}
    assert exc.value.identical_content is False


def test_resolve_artifact_both_exist_identical_content_raises(tmp_path):
    _write(tmp_path / "spec.md", "same")
    _write(tmp_path / "01_spec.md", "same")
    with pytest.raises(bc.ArtifactAmbiguityError) as exc:
        bc.resolve_artifact(tmp_path, "spec.md")
    assert exc.value.identical_content is True


def test_resolve_artifact_ambiguity_error_message_identical_content(tmp_path):
    _write(tmp_path / "spec.md", "same")
    _write(tmp_path / "01_spec.md", "same")
    with pytest.raises(bc.ArtifactAmbiguityError) as exc:
        bc.resolve_artifact(tmp_path, "spec.md")
    assert "byte-identical" in str(exc.value)


def test_resolve_artifact_user_01_design_coexists_with_02_design(tmp_path):
    # both strip to design.md (a known artifact) -> multiple-prefixed ambiguity
    _write(tmp_path / "01_design.md", "a")
    _write(tmp_path / "02_design.md", "b")
    with pytest.raises(bc.ArtifactAmbiguityError):
        bc.resolve_artifact(tmp_path, "design.md")


def test_resolve_artifact_non_artifact_bare_returned(tmp_path):
    # not a known artifact -> no glob, bare path returned
    assert bc.resolve_artifact(tmp_path, "factor_notes.md") == tmp_path / "factor_notes.md"


def test_resolve_artifact_nonexistent_dir(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert bc.resolve_artifact(missing, "spec.md") == missing / "spec.md"


def test_resolve_artifact_stemless_prefix_ignored(tmp_path):
    _write(tmp_path / "01_.md")  # not 01_spec.md
    assert bc.resolve_artifact(tmp_path, "spec.md") == tmp_path / "spec.md"


def test_resolve_artifact_editor_backup_ignored(tmp_path):
    _write(tmp_path / "01_spec.md~")  # editor backup, not matched by the glob
    assert bc.resolve_artifact(tmp_path, "spec.md") == tmp_path / "spec.md"


def test_resolve_artifact_single_misordinaled_prefix(tmp_path):
    _write(tmp_path / "02_spec.md")  # wrong ordinal, but the only prefixed form
    assert bc.resolve_artifact(tmp_path, "spec.md") == tmp_path / "02_spec.md"


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="chmod-based unreadable test is unreliable as root / on Windows",
)
def test_resolve_artifact_identical_content_unreadable_is_false(tmp_path):
    _write(tmp_path / "spec.md", "a")
    unreadable = _write(tmp_path / "01_spec.md", "a")
    os.chmod(unreadable, 0)
    try:
        with pytest.raises(bc.ArtifactAmbiguityError) as exc:
            bc.resolve_artifact(tmp_path, "spec.md")
        # an unreadable conflicting file -> best-effort comparison is False,
        # and no raw OSError escaped (only ArtifactAmbiguityError did)
        assert exc.value.identical_content is False
    finally:
        os.chmod(unreadable, 0o644)


# ---------------------------------------------------------------------------
# T8: definition-of-done grep gate + negative self-test
# ---------------------------------------------------------------------------

import re  # noqa: E402
import subprocess  # noqa: E402

_REPO = Path(__file__).resolve().parents[3]
_CONVERTED_SOURCES = [
    _REPO / "telescoping-sdd/scripts/blueprint_common.py",
    _REPO / "telescoping-sdd/scripts/archive_pass.py",
    _REPO / "telescoping-sdd/scripts/reconcile.py",
    _REPO / "telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py",
    _REPO / "telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py",
    _REPO / "telescoping-sdd/skills/project-blueprint/scripts/render_business_brief.py",
]

_NAMES = r"(?:spec|design|tasks|SCOPE|ARCHITECTURE|PLAN)"
_PATH_RE = re.compile(r'/ "' + _NAMES + r'\.md"')
_EQ_RE = re.compile(r'== "' + _NAMES + r'\.md"')
_TERM_RE = re.compile(r"\bin TERMINAL_FILENAMES\b")


def _strip_inline_comment(line: str) -> str:
    """Drop a trailing ``# ...`` comment, respecting simple ' and " string
    literals. Without this, a `resolve_artifact(` mentioned only in a comment
    would falsely exempt a real bare construction on the same line."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote and line[i - 1] != "\\":
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#":
            return line[:i]
    return line


def _code_lines(text: str):
    """Yield code lines (with any trailing comment stripped), skipping comment
    lines and triple-quoted docstrings so the gate neither false-positives on
    prose nor false-negatives on an exemption token hidden in a comment."""
    in_doc = False
    for raw in text.splitlines():
        s = raw.strip()
        tq = s.count('"""') + s.count("'''")
        if in_doc:
            if tq % 2 == 1:
                in_doc = False
            continue
        if tq % 2 == 1:
            in_doc = True
            continue
        if tq >= 2 or s.startswith("#"):
            continue
        yield _strip_inline_comment(raw)


def _flag_bare_constructions(text: str) -> list[str]:
    """Return the un-resolver-wrapped bare-artifact constructions in `text`.

    A construction is OK only when it routes through the resolution layer:
      - ``dir / "X.md"`` must sit inside a ``resolve_artifact(`` call,
      - ``== "X.md"`` must be guarded by ``strip_artifact_prefix(``,
      - ``in TERMINAL_FILENAMES`` must be preceded by a numeric-prefix strip.
    """
    flagged = []
    for line in _code_lines(text):
        if _PATH_RE.search(line) and "resolve_artifact(" not in line:
            flagged.append(line.strip())
        if _EQ_RE.search(line) and "strip_artifact_prefix(" not in line:
            flagged.append(line.strip())
        if _TERM_RE.search(line) and "strip" not in line:
            flagged.append(line.strip())
    return flagged


def test_no_bare_artifact_constructions():
    """Every converted source file routes artifact resolution through the
    helpers — zero un-wrapped bare constructions remain (RI1 definition-of-done)."""
    offenders = {}
    for src in _CONVERTED_SOURCES:
        bad = _flag_bare_constructions(src.read_text(encoding="utf-8"))
        if bad:
            offenders[src.name] = bad
    assert offenders == {}, f"un-wrapped bare artifact constructions: {offenders}"


def test_grep_gate_catches_known_bad():
    """Negative self-test: the gate's matcher MUST flag known-bad constructions
    (so a silently-matching-nothing gate can't pass as green)."""
    known_bad = (
        'target = spec_dir / "spec.md"\n'
        'if file_path.name == "PLAN.md":\n'
        "if art.name in TERMINAL_FILENAMES:\n"
    )
    flagged = _flag_bare_constructions(known_bad)
    assert len(flagged) == 3
    # ...and the legitimate wrapped forms are NOT flagged:
    good = (
        'target = resolve_artifact(spec_dir, "spec.md")\n'
        'if strip_artifact_prefix(file_path.name) == "PLAN.md":\n'
        "if _strip_numeric_prefix(art.name) in TERMINAL_FILENAMES:\n"
    )
    assert _flag_bare_constructions(good) == []
    # ...and an exemption token hidden in a COMMENT must NOT exempt a real bare
    # construction (the comment hole the reviewer flagged):
    commented = 'target = spec_dir / "spec.md"  # TODO: route via resolve_artifact()\n'
    assert _flag_bare_constructions(commented) == ['target = spec_dir / "spec.md"']


# ---------------------------------------------------------------------------
# T8: integration — the REAL validators against prefixed dirs (RI1/RI2 guard)
# ---------------------------------------------------------------------------

_VALIDATE_SPEC = _REPO / "telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py"

_MIN_SPEC = (
    "# Feature: Equiv\n\n"
    "**PLAN feature identifier:** `n/a`\n\n"
    "## Objective\n\nDo a thing.\n"
)


def _run_validate_spec(spec_dir: Path, *extra):
    return subprocess.run(
        [sys.executable, str(_VALIDATE_SPEC), str(spec_dir), *extra],
        capture_output=True, text=True,
    )


def test_validate_spec_prefixed_dir_equiv(tmp_path):
    """validate_spec produces the SAME verdict for a prefixed 01_spec.md as for
    bare spec.md, and explicitly resolves the prefixed file (no 'does not exist')."""
    bare = tmp_path / "equiv-bare"
    bare.mkdir()
    (bare / "spec.md").write_text(_MIN_SPEC, encoding="utf-8")
    pref = tmp_path / "equiv-pref"
    pref.mkdir()
    (pref / "01_spec.md").write_text(_MIN_SPEC, encoding="utf-8")

    rb = _run_validate_spec(bare)
    rp = _run_validate_spec(pref)
    # identical pass/fail verdict
    assert rb.returncode == rp.returncode
    # the prefixed run found and validated the file (resolution worked)
    assert "spec.md exists" in rp.stdout
    assert "does not exist" not in rp.stdout
    # the bare 'spec.md exists' PASS is mirrored in the prefixed run
    assert ("[PASS] spec.md exists" in rb.stdout) == ("[PASS] spec.md exists" in rp.stdout)


def test_validate_spec_ambiguity_exits_nonzero_no_hash(tmp_path):
    """Fail-closed (design.md:349): a dir with BOTH spec.md and 01_spec.md makes
    validate (and --approve) exit non-zero and stamp no hash."""
    d = tmp_path / "ambig"
    d.mkdir()
    (d / "spec.md").write_text(_MIN_SPEC, encoding="utf-8")
    (d / "01_spec.md").write_text(_MIN_SPEC + "\ndifferent\n", encoding="utf-8")

    rv = _run_validate_spec(d)
    assert rv.returncode != 0
    assert "mbigu" in (rv.stdout + rv.stderr)  # "Ambiguous"/"ambiguity"

    ra = _run_validate_spec(d, "--approve", "spec")
    assert ra.returncode != 0
    # neither artifact had its pending hash replaced with a real one
    assert "Content Hash: `pending`" in (d / "spec.md").read_text() or \
        "**Content Hash:**" not in (d / "spec.md").read_text()


# ---------------------------------------------------------------------------
# T9 / T10: the renamer (artifact_prefix.py)
# ---------------------------------------------------------------------------

import artifact_prefix as ap  # noqa: E402


def _project(tmp_path):
    """A project root carrying a `.sdd/` marker (so find_project_root resolves
    to it) plus an empty `specs/foo/` feature dir. Returns (root, feature_dir)."""
    root = tmp_path / "proj"
    (root / ".sdd").mkdir(parents=True)
    feat = root / "specs" / "foo"
    feat.mkdir(parents=True)
    return root, feat


def _run_renamer(argv):
    """Call ap.main, normalising SystemExit to its int code."""
    try:
        return ap.main(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1


def _pending(root, doc_rel):
    bc.upsert_pending_entry(root, doc_rel, "deadbeefdeadbeef", "2026-01-01T00:00:00+00:00", 1)


def test_prefix_map_known_artifacts_symmetry():
    """AD10: the renamer's PREFIX_MAP and the resolver's KNOWN_ARTIFACTS cannot drift."""
    assert set(ap.PREFIX_MAP.keys()) == bc.KNOWN_ARTIFACTS


def test_renamer_renames_all_bare_artifacts(tmp_path):
    _, feat = _project(tmp_path)
    for n in ("spec.md", "design.md", "tasks.md"):
        (feat / n).write_text("x", encoding="utf-8")
    assert _run_renamer([str(feat)]) == 0
    assert (feat / "01_spec.md").is_file()
    assert (feat / "02_design.md").is_file()
    assert (feat / "03_tasks.md").is_file()
    assert not (feat / "spec.md").exists()


def test_renamer_hash_safety(tmp_path):
    """3-step: stamp a REAL content hash, rename, re-verify the hash holds."""
    _, feat = _project(tmp_path)
    raw = ("# Feature\n\nbody text\n\n## Approval\n\n"
           "- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n")
    h = bc.compute_content_hash(bc.content_for_hashing(raw))
    stamped = raw.replace("`pending`", f"`{h}`")
    assert bc.verify_content_hash(stamped, h)  # sanity
    (feat / "spec.md").write_text(stamped, encoding="utf-8")
    assert _run_renamer([str(feat)]) == 0
    after = (feat / "01_spec.md").read_text(encoding="utf-8")
    assert bc.verify_content_hash(after, h)  # hash still valid after the rename


def test_renamer_idempotent_all_prefixed(tmp_path):
    _, feat = _project(tmp_path)
    (feat / "01_spec.md").write_text("x", encoding="utf-8")
    (feat / "02_design.md").write_text("x", encoding="utf-8")
    assert _run_renamer([str(feat)]) == 0  # nothing to rename


def test_renamer_idempotent_partial(tmp_path):
    _, feat = _project(tmp_path)
    (feat / "01_spec.md").write_text("x", encoding="utf-8")
    (feat / "design.md").write_text("x", encoding="utf-8")
    assert _run_renamer([str(feat)]) == 0
    assert (feat / "02_design.md").is_file()
    assert (feat / "01_spec.md").is_file()  # untouched


def test_renamer_nothing_to_rename_exit_zero(tmp_path):
    _, feat = _project(tmp_path)
    assert _run_renamer([str(feat)]) == 0


def test_renamer_pending_review_refusal(tmp_path, capsys):
    root, feat = _project(tmp_path)
    (feat / "spec.md").write_text("x", encoding="utf-8")
    _pending(root, "specs/foo/spec.md")
    assert _run_renamer([str(feat)]) == 1
    assert "pending" in capsys.readouterr().err
    assert (feat / "spec.md").exists()  # not renamed


def test_renamer_pending_entry_different_dir_no_refusal(tmp_path):
    root, feat = _project(tmp_path)
    (feat / "spec.md").write_text("x", encoding="utf-8")
    _pending(root, "specs/bar/spec.md")  # different feature dir
    assert _run_renamer([str(feat)]) == 0
    assert (feat / "01_spec.md").is_file()


def test_renamer_pending_entry_sibling_dir_no_bleed(tmp_path):
    root, feat = _project(tmp_path)
    (feat / "spec.md").write_text("x", encoding="utf-8")
    _pending(root, "specs/foobar/spec.md")  # 'foo' must NOT prefix-bleed onto 'foobar'
    assert _run_renamer([str(feat)]) == 0
    assert (feat / "01_spec.md").is_file()


def test_renamer_pending_entry_per_file_key_match(tmp_path, capsys):
    root, feat = _project(tmp_path)
    (feat / "design.md").write_text("x", encoding="utf-8")
    _pending(root, "specs/foo/02_design.md")  # per-file key under the dir prefix
    assert _run_renamer([str(feat)]) == 1
    assert "pending" in capsys.readouterr().err


def test_renamer_corrupt_marker_refuses(tmp_path, capsys):
    root, feat = _project(tmp_path)
    (feat / "spec.md").write_text("x", encoding="utf-8")
    (root / ".sdd" / "pending-review.json").write_text("{not json", encoding="utf-8")
    assert _run_renamer([str(feat)]) == 1
    assert "corrupt" in capsys.readouterr().err
    assert (feat / "spec.md").exists()  # fail-closed: nothing renamed


def test_renamer_ambiguity_refusal(tmp_path, capsys):
    _, feat = _project(tmp_path)
    (feat / "spec.md").write_text("a", encoding="utf-8")
    (feat / "01_spec.md").write_text("b", encoding="utf-8")
    assert _run_renamer([str(feat)]) == 1
    # message now comes from resolve_artifact (the shared chokepoint)
    assert "Ambiguous artifact" in capsys.readouterr().err
    # fail-closed: neither conflicting file was renamed or removed
    assert (feat / "spec.md").exists() and (feat / "01_spec.md").exists()


def test_renamer_symlink_artifact_refused(tmp_path, capsys):
    _, feat = _project(tmp_path)
    target = tmp_path / "outside.md"
    target.write_text("x", encoding="utf-8")
    try:
        (feat / "spec.md").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert _run_renamer([str(feat)]) == 1
    assert "symlink" in capsys.readouterr().err
    # fail-closed: the symlink was NOT renamed
    assert (feat / "spec.md").is_symlink()
    assert not (feat / "01_spec.md").exists()


def test_renamer_rename_failure_halts(tmp_path, monkeypatch):
    _, feat = _project(tmp_path)
    for n in ("spec.md", "design.md", "tasks.md"):
        (feat / n).write_text("x", encoding="utf-8")
    real = ap.os.rename
    state = {"n": 0}

    def flaky(src, dst):
        state["n"] += 1
        if state["n"] == 2:
            raise OSError(13, "permission denied")
        return real(src, dst)

    monkeypatch.setattr(ap.os, "rename", flaky)
    assert _run_renamer([str(feat)]) == 1
    # halted AT the failure: the 1st rename committed, the failing artifact and
    # all SUBSEQUENT ones are untouched (no roll-forward past the error).
    assert (feat / "01_spec.md").is_file()   # 1st succeeded
    assert (feat / "design.md").is_file()    # 2nd failed -> still bare
    assert (feat / "tasks.md").is_file()     # 3rd never attempted
    assert not (feat / "03_tasks.md").exists()


def test_renamer_midfailure_leaves_mixed_state(tmp_path, monkeypatch):
    _, feat = _project(tmp_path)
    for n in ("spec.md", "design.md", "tasks.md"):
        (feat / n).write_text("x", encoding="utf-8")
    real = ap.os.rename
    state = {"n": 0}

    def flaky(src, dst):
        state["n"] += 1
        if state["n"] == 2:
            raise OSError(13, "permission denied")
        return real(src, dst)

    monkeypatch.setattr(ap.os, "rename", flaky)
    _run_renamer([str(feat)])
    # one renamed, the rest bare -> mixed; the WARN routes the user back (RI4)
    assert bc._detect_prefix_state(feat) == "mixed"


def test_renamer_dir_relative_path_resolves(tmp_path):
    root, feat = _project(tmp_path)
    (feat / "spec.md").write_text("x", encoding="utf-8")
    _pending(root, "specs/foo/spec.md")
    # a non-canonical path to feat must resolve before the pending key is matched
    noncanonical = str(feat / ".." / "foo")
    assert _run_renamer([noncanonical]) == 1  # still refused (resolution worked)


def test_renamer_finds_root_from_nested_dir(tmp_path):
    root, feat = _project(tmp_path)
    nested = feat / "sub" / "deeper"
    nested.mkdir(parents=True)
    (nested / "spec.md").write_text("x", encoding="utf-8")
    _pending(root, "specs/foo/sub/deeper/spec.md")
    # find_project_root must walk up several levels to the .sdd marker
    assert _run_renamer([str(nested)]) == 1  # pending in scope -> refused


def test_renamer_check_offer_mixed_interactive(tmp_path, capsys, monkeypatch):
    _, feat = _project(tmp_path)
    (feat / "spec.md").write_text("x", encoding="utf-8")
    (feat / "02_design.md").write_text("x", encoding="utf-8")  # mixed
    monkeypatch.setattr(ap, "_is_interactive", lambda: True)
    assert _run_renamer(["--check", str(feat)]) == 0
    assert capsys.readouterr().out.strip() == "OFFER"


def test_renamer_check_suppress_ci(tmp_path, capsys, monkeypatch):
    _, feat = _project(tmp_path)
    (feat / "spec.md").write_text("x", encoding="utf-8")
    (feat / "02_design.md").write_text("x", encoding="utf-8")  # mixed
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setenv("CI", "true")
    assert _run_renamer(["--check", str(feat)]) == 0
    assert "SUPPRESS" in capsys.readouterr().out


def test_renamer_check_suppress_no_tty(tmp_path, capsys, monkeypatch):
    _, feat = _project(tmp_path)
    (feat / "spec.md").write_text("x", encoding="utf-8")
    (feat / "02_design.md").write_text("x", encoding="utf-8")  # mixed
    monkeypatch.setattr(ap, "_is_interactive", lambda: False)
    assert _run_renamer(["--check", str(feat)]) == 0
    assert "SUPPRESS" in capsys.readouterr().out


def test_renamer_check_suppress_uniform(tmp_path, capsys, monkeypatch):
    _, feat = _project(tmp_path)
    (feat / "spec.md").write_text("x", encoding="utf-8")  # uniform-bare
    monkeypatch.setattr(ap, "_is_interactive", lambda: True)
    assert _run_renamer(["--check", str(feat)]) == 0
    assert "SUPPRESS" in capsys.readouterr().out  # never offers on a uniform dir


# ---------------------------------------------------------------------------
# T12: mixed-state validator WARN
# ---------------------------------------------------------------------------

def test_validator_warn_present_on_mixed(tmp_path):
    d = tmp_path / "mixed"
    d.mkdir()
    (d / "spec.md").write_text(_MIN_SPEC, encoding="utf-8")
    (d / "02_design.md").write_text("# design\n", encoding="utf-8")  # mixed, no per-artifact conflict
    r = _run_validate_spec(d)
    assert "mixed artifact-prefix state" in r.stdout


def test_validator_warn_absent_on_uniform_bare(tmp_path):
    d = tmp_path / "ub"
    d.mkdir()
    (d / "spec.md").write_text(_MIN_SPEC, encoding="utf-8")
    r = _run_validate_spec(d)
    assert "mixed artifact-prefix state" not in r.stdout


# ---------------------------------------------------------------------------
# T8 (remainder): blueprint-side + render integration on prefixed dirs
# ---------------------------------------------------------------------------

_VALIDATE_BLUEPRINT = _REPO / "telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py"
_RENDER = _REPO / "telescoping-sdd/skills/project-blueprint/scripts/render_business_brief.py"
_BP_ARTIFACTS = [("SCOPE.md", "01_"), ("ARCHITECTURE.md", "02_"), ("PLAN.md", "03_")]


def _run_script(script, *args):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)


def test_validate_blueprint_prefixed_dir_equiv(tmp_path):
    """validate_blueprint derives the SAME verdict for a prefixed blueprint as a
    bare one (RI2) — and the prefixed artifacts are resolved, not reported absent."""
    bare = tmp_path / "bp-bare"
    bare.mkdir()
    for n, _ in _BP_ARTIFACTS:
        (bare / n).write_text(f"# {n}\n", encoding="utf-8")
    pref = tmp_path / "bp-pref"
    pref.mkdir()
    for n, p in _BP_ARTIFACTS:
        (pref / (p + n)).write_text(f"# {n}\n", encoding="utf-8")

    rb = _run_script(_VALIDATE_BLUEPRINT, str(bare))
    rp = _run_script(_VALIDATE_BLUEPRINT, str(pref))
    assert rb.returncode == rp.returncode
    # the prefixed dir resolved its three artifacts (not flagged mixed)
    assert "mixed artifact-prefix state" not in rp.stdout


def test_render_business_brief_resolves_prefixed_blueprint(tmp_path):
    """render_business_brief's validate_blueprint_dir gate (the RI2 fix, T7)
    resolves NN_-prefixed artifacts — it does NOT abort with 'missing required
    artifacts'."""
    pref = tmp_path / "bp"
    pref.mkdir()
    for n, p in _BP_ARTIFACTS:
        (pref / (p + n)).write_text(f"# {n}\n", encoding="utf-8")
    r = _run_script(_RENDER, str(pref))
    assert "missing required artifacts" not in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Code-review fixes: #4 (WARN suppressed on ambiguity) + #6 (root over-refusal)
# ---------------------------------------------------------------------------

def test_mixed_state_warning_suppressed_on_ambiguity(tmp_path):
    """#4: a same-artifact bare+prefixed collision is 'mixed', but the renamer
    can't fix it — mixed_state_warning returns None (no misleading nudge)."""
    d = tmp_path / "collide"
    d.mkdir()
    (d / "spec.md").write_text("a", encoding="utf-8")
    (d / "01_spec.md").write_text("b", encoding="utf-8")    # collision
    (d / "02_design.md").write_text("c", encoding="utf-8")  # makes the state 'mixed'
    assert bc._detect_prefix_state(d) == "mixed"
    assert bc.mixed_state_warning(str(d), d) is None


def test_mixed_state_warning_present_when_fixable(tmp_path):
    """#4: a mixed dir with NO collision IS renamer-fixable -> a WARN is returned."""
    d = tmp_path / "fixable"
    d.mkdir()
    (d / "spec.md").write_text("a", encoding="utf-8")       # bare
    (d / "02_design.md").write_text("c", encoding="utf-8")  # prefixed, different artifact
    warn = bc.mixed_state_warning(str(d), d)
    assert warn is not None and "artifact_prefix.py" in warn


def test_validator_no_renamer_nudge_on_ambiguity(tmp_path):
    """#4 end-to-end: on a same-artifact collision the validator FAILs with the
    ambiguity detail and does NOT print a 'run the renamer' nudge it can't act on."""
    d = tmp_path / "ambig-warn"
    d.mkdir()
    (d / "spec.md").write_text(_MIN_SPEC, encoding="utf-8")
    (d / "01_spec.md").write_text(_MIN_SPEC + "\nx\n", encoding="utf-8")
    r = _run_validate_spec(d)
    assert r.returncode != 0                       # ambiguity is fail-closed
    assert "artifact_prefix.py" not in r.stdout    # no misleading renamer nudge


def test_renamer_root_dir_not_over_refused_by_nested_pending(tmp_path):
    """#6: when the renamer targets the project ROOT (rel=''), an unrelated NESTED
    pending obligation must NOT block it (_prefix_in_scope('', key) matches every
    key, so the root case is guarded to direct-children only)."""
    root = tmp_path / "proj"
    (root / ".sdd").mkdir(parents=True)
    (root / "SCOPE.md").write_text("x", encoding="utf-8")   # a root-level artifact
    bc.upsert_pending_entry(
        root, "specs/foo/spec.md", "deadbeefdeadbeef", "2026-01-01T00:00:00+00:00", 1
    )
    assert _run_renamer([str(root)]) == 0          # nested obligation does NOT refuse
    assert (root / "01_SCOPE.md").is_file()


def test_renamer_root_dir_still_refused_by_root_level_pending(tmp_path):
    """#6 (complement): a pending obligation for a ROOT-LEVEL artifact DOES still
    refuse a root-level rename — the guard only ignores nested keys."""
    root = tmp_path / "proj"
    (root / ".sdd").mkdir(parents=True)
    (root / "SCOPE.md").write_text("x", encoding="utf-8")
    bc.upsert_pending_entry(
        root, "SCOPE.md", "deadbeefdeadbeef", "2026-01-01T00:00:00+00:00", 1
    )
    assert _run_renamer([str(root)]) == 1
