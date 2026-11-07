"""Tests for the shared arch_config.py declare-once stack store + resolver.

The suite guards the design constraints of the declare-once stack store:

* PRECEDENCE: explicit flag > persisted config > auto-detect.
* SINGLE WRITER + CLOSED VOCABULARY: write rejects unknown keys (no persisted
  typos); only the explicit write path mutates the file.
* DEFENSIVE READ: malformed / unknown-schema / unknown-key configs are ignored
  (treated as "no config"), so resolution falls back to detection rather than
  trusting garbage.
* ROUND-TRIP SYMMETRY: what the writer persists is exactly what the resolver
  reads back and what the real validate_spec consumer resolves — the test that
  prevents the prose/script dual-detector drift from re-appearing.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_arch_config():
    scripts = _REPO_ROOT / "telescoping-sdd" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    if "arch_config" in sys.modules:
        return importlib.reload(sys.modules["arch_config"])
    return importlib.import_module("arch_config")


def _load_validate_spec():
    scripts = _REPO_ROOT / "telescoping-sdd" / "skills" / "spec-driven-dev" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    if "validate_spec" in sys.modules:
        return importlib.reload(sys.modules["validate_spec"])
    return importlib.import_module("validate_spec")


def _load_validate_blueprint():
    scripts = _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    if "validate_blueprint" in sys.modules:
        return importlib.reload(sys.modules["validate_blueprint"])
    return importlib.import_module("validate_blueprint")


ac = _load_arch_config()

KNOWN = ["python", "java", "generic"]


def _spec_dir(tmp_path: Path) -> Path:
    """A conventional <root>/specs/<feature>/ layout, returning the feature dir."""
    d = tmp_path / "specs" / "feature"
    d.mkdir(parents=True)
    return d


# --- write: closed vocabulary --------------------------------------------------

def test_write_persists_known_language(tmp_path):
    path = ac.write_arch_config(tmp_path, "generic", KNOWN, source="user")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["language"] == "generic"
    assert data["schemaVersion"] == ac.SCHEMA_VERSION
    assert data["source"] == "user"
    assert path == tmp_path / ".sdd" / "architecture.json"


def test_write_rejects_unknown_language(tmp_path):
    try:
        ac.write_arch_config(tmp_path, "pyton", KNOWN)
    except ValueError as e:
        assert "pyton" in str(e)
    else:
        raise AssertionError("expected ValueError for unknown language")
    # nothing should have been written
    assert not (tmp_path / ".sdd" / "architecture.json").exists()


def test_write_creates_sdd_dir_and_trailing_newline(tmp_path):
    path = ac.write_arch_config(tmp_path, "python", KNOWN)
    assert path.read_text(encoding="utf-8").endswith("\n")


# --- read: defensive -----------------------------------------------------------

def test_read_absent_returns_none(tmp_path):
    assert ac.read_arch_config(_spec_dir(tmp_path), project_root=tmp_path) is None


def test_read_malformed_json_returns_none(tmp_path):
    cfgdir = tmp_path / ".sdd"
    cfgdir.mkdir()
    (cfgdir / "architecture.json").write_text("{not json", encoding="utf-8")
    assert ac.read_arch_config(tmp_path, project_root=tmp_path) is None


def test_read_unknown_schema_returns_none(tmp_path):
    ac.write_arch_config(tmp_path, "python", KNOWN)
    p = tmp_path / ".sdd" / "architecture.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["schemaVersion"] = 999
    p.write_text(json.dumps(data), encoding="utf-8")
    assert ac.read_arch_config(tmp_path, project_root=tmp_path) is None


def test_read_walks_up_from_spec_dir(tmp_path):
    ac.write_arch_config(tmp_path, "java", KNOWN)
    spec_dir = _spec_dir(tmp_path)
    cfg = ac.read_arch_config(spec_dir)  # no explicit root → must walk up
    assert cfg is not None and cfg["language"] == "java"


# --- resolve: precedence -------------------------------------------------------

def _detector_returning(value):
    """A stand-in detector that records it was called and returns `value`."""
    calls = {"n": 0}

    def _detect(spec_dir, project_root=None):
        calls["n"] += 1
        return value

    _detect.calls = calls
    return _detect


def test_resolve_flag_wins_over_everything(tmp_path):
    ac.write_arch_config(tmp_path, "java", KNOWN)  # config says java
    det = _detector_returning("python")
    lang, src = ac.resolve_language(
        _spec_dir(tmp_path), explicit="python", detector=det,
        known_languages=KNOWN, project_root=tmp_path,
    )
    assert (lang, src) == ("python", "flag")
    assert det.calls["n"] == 0  # detector not even consulted


def test_resolve_config_wins_over_detect(tmp_path):
    ac.write_arch_config(tmp_path, "generic", KNOWN)
    det = _detector_returning("python")
    lang, src = ac.resolve_language(
        _spec_dir(tmp_path), explicit=None, detector=det,
        known_languages=KNOWN, project_root=tmp_path,
    )
    assert (lang, src) == ("generic", "config")
    assert det.calls["n"] == 0  # config short-circuits detection


def test_resolve_falls_through_to_detect_when_no_config(tmp_path):
    det = _detector_returning("generic")
    lang, src = ac.resolve_language(
        _spec_dir(tmp_path), explicit=None, detector=det,
        known_languages=KNOWN, project_root=tmp_path,
    )
    assert (lang, src) == ("generic", "auto-detect")
    assert det.calls["n"] == 1


def test_resolve_ignores_config_with_unknown_key(tmp_path):
    # A config naming a language no longer in the known set must NOT be trusted;
    # resolution falls through to detection instead.
    cfgdir = tmp_path / ".sdd"
    cfgdir.mkdir()
    (cfgdir / "architecture.json").write_text(
        json.dumps({"schemaVersion": ac.SCHEMA_VERSION, "language": "cobol"}),
        encoding="utf-8",
    )
    det = _detector_returning("generic")
    lang, src = ac.resolve_language(
        tmp_path, explicit=None, detector=det,
        known_languages=KNOWN, project_root=tmp_path,
    )
    assert (lang, src) == ("generic", "auto-detect")


# --- round-trip symmetry: writer ↔ real consumer ------------------------------

def test_roundtrip_writer_matches_validate_spec_consumer(tmp_path):
    """The single most important test: what arch_config WRITES is exactly what the
    real validate_spec consumer RESOLVES — proving the prose/script layers cannot
    drift to different answers once a value is persisted."""
    vs = _load_validate_spec()
    spec_dir = _spec_dir(tmp_path)

    for lang in KNOWN:
        ac.write_arch_config(tmp_path, lang, list(vs.LANGUAGE_PROFILES.keys()))
        resolved, source = ac.resolve_language(
            spec_dir,
            explicit=None,
            detector=vs.detect_language,          # the REAL detector
            known_languages=list(vs.LANGUAGE_PROFILES.keys()),
            project_root=tmp_path,
        )
        assert resolved == lang, f"persisted {lang!r} but consumer resolved {resolved!r}"
        assert source == "config"
        # and the resolved key maps to a real profile (no python silent-fallback)
        assert vs.get_profile(resolved)["label"]


def test_write_vocabulary_matches_validate_spec_profiles(tmp_path):
    """The writer's accepted vocabulary must be exactly the consumer's profile
    keys — otherwise a key the writer accepts could be unresolvable downstream."""
    vs = _load_validate_spec()
    keys = list(vs.LANGUAGE_PROFILES.keys())
    # every known key is writable...
    for k in keys:
        ac.write_arch_config(tmp_path, k, keys)
    # ...and a key outside that set is refused.
    try:
        ac.write_arch_config(tmp_path, "definitely-not-a-profile", keys)
    except ValueError:
        pass
    else:
        raise AssertionError("writer accepted a key not in validate_spec profiles")


# --- arch-token grammar --------------------------------------------------------

def test_parse_arch_token_backtick_and_bare():
    assert ac.parse_arch_token("**Architecture token:** `generic`") == "generic"
    assert ac.parse_arch_token("**Architecture token:** python") == "python"
    assert ac.parse_arch_token("# Architecture\n\nno token here\n") is None


def test_parse_arch_token_ignores_commented_example_shadowing_real_token():
    """A commented-out example token must NOT shadow the author's real
    declaration (review finding: .search() would otherwise grab the first match,
    including one inside an HTML comment)."""
    md = (
        "## Technology Choices\n\n"
        "<!-- Example: **Architecture token:** `python` -->\n\n"
        "**Architecture token:** `java`\n"
    )
    assert ac.parse_arch_token(md) == "java"


def test_parse_arch_token_real_template_shape_resolves_generic():
    """The shipped template shape (real token line, then an explanatory comment
    that itself contains bare backtick examples) resolves to the real token."""
    md = (
        "**Architecture token:** `generic`\n\n"
        "<!-- ... use `python`, `java`, or `generic` ... -->\n"
    )
    assert ac.parse_arch_token(md) == "generic"


# --- producer vocabulary symmetry (blueprint ↔ spec) --------------------------

def test_blueprint_token_vocab_matches_spec_profiles():
    """The blueprint's KNOWN_ARCH_TOKENS must equal validate_spec's profile keys.
    project-blueprint keeps the list as a literal (it does not import the
    consumer); this test is the mechanical guard against the two drifting."""
    vs = _load_validate_spec()
    vb = _load_validate_blueprint()
    assert sorted(vb.KNOWN_ARCH_TOKENS) == sorted(vs.LANGUAGE_PROFILES.keys())


# --- full blueprint→SDD seam ---------------------------------------------------

def test_seam_blueprint_token_resolves_on_spec_side(tmp_path):
    """End-to-end: a token declared in ARCHITECTURE.md, persisted by the producer
    helper, is exactly what the SDD-side resolver reads back as 'config'."""
    vs = _load_validate_spec()
    # Simulate the producer's write step (same shared writer, source="blueprint").
    arch_md = "## Technology Choices\n\n**Architecture token:** `generic`\n"
    token = ac.parse_arch_token(arch_md)
    ac.write_arch_config(
        tmp_path, token, list(vs.LANGUAGE_PROFILES.keys()),
        source="blueprint", detected_from="ARCHITECTURE.md",
    )
    # Consumer (a feature dir under the same project root) resolves it.
    spec_dir = _spec_dir(tmp_path)
    lang, src = ac.resolve_language(
        spec_dir, explicit=None, detector=vs.detect_language,
        known_languages=list(vs.LANGUAGE_PROFILES.keys()), project_root=tmp_path,
    )
    assert (lang, src) == ("generic", "config")


# ---------------------------------------------------------------------------
# Unit D (R7): the rigour posture key, stored beside the language (I3, C7).
# ---------------------------------------------------------------------------

import pytest


def _root(tmp_path: Path) -> Path:
    _spec_dir(tmp_path)
    return tmp_path


def _cfg(tmp_path: Path) -> dict:
    return json.loads(ac.config_path(tmp_path).read_text(encoding="utf-8"))


def _write_raw(tmp_path: Path, payload) -> Path:
    p = ac.config_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        payload if isinstance(payload, str) else json.dumps(payload),
        encoding="utf-8",
    )
    return p


@pytest.mark.parametrize("posture", ["critical", "standard", "vibe"])
def test_each_posture_round_trips(tmp_path, posture):
    spec = _spec_dir(tmp_path)
    ac.write_posture(tmp_path, posture)
    assert ac.read_posture(spec) == (posture, None, False)
    res = ac.resolve_posture(spec)
    assert (res.posture, res.source) == (posture, "config")
    assert ac.POSTURES == ("critical", "standard", "vibe")
    assert ac.DEFAULT_POSTURE == "standard"
    assert ac.POSTURE_KEY == "posture"
    assert ac.NOTICE_FILENAME == "posture-notice"


def test_language_then_posture_keeps_both(tmp_path):
    _root(tmp_path)
    ac.write_arch_config(tmp_path, "python", KNOWN)
    ac.write_posture(tmp_path, "critical")
    data = _cfg(tmp_path)
    assert data["language"] == "python" and data["posture"] == "critical"


def test_posture_then_language_keeps_both(tmp_path):
    _root(tmp_path)
    ac.write_posture(tmp_path, "vibe")
    ac.write_arch_config(tmp_path, "java", KNOWN)
    data = _cfg(tmp_path)
    assert data["language"] == "java" and data["posture"] == "vibe"


def test_posture_only_file_language_falls_back_to_detection(tmp_path):
    spec = _spec_dir(tmp_path)
    ac.write_posture(tmp_path, "critical")
    assert ac.read_arch_config(spec) is None
    lang, source = ac.resolve_language(
        spec, explicit=None, detector=_detector_returning("generic"),
        known_languages=KNOWN,
    )
    assert (lang, source) == ("generic", "auto-detect")


def test_language_only_file_posture_resolves_default(tmp_path):
    spec = _spec_dir(tmp_path)
    ac.write_arch_config(tmp_path, "python", KNOWN)
    assert ac.read_posture(spec) == (None, None, False)
    res = ac.resolve_posture(spec)
    assert (res.posture, res.source, res.rejected, res.rejected_non_text) == (
        "standard", "default", None, False,
    )


def test_rejected_posture_ignored_at_read_raises_at_write(tmp_path):
    spec = _spec_dir(tmp_path)
    _write_raw(tmp_path, {"schemaVersion": 1, "language": "python", "posture": "yolo"})
    assert ac.read_posture(spec) == (None, "yolo", False)
    res = ac.resolve_posture(spec)
    assert (res.posture, res.source, res.rejected) == ("standard", "default", "yolo")
    before = ac.config_path(tmp_path).read_bytes()
    with pytest.raises(ValueError):
        ac.write_posture(tmp_path, "yolo")
    assert ac.config_path(tmp_path).read_bytes() == before


@pytest.mark.parametrize("value", [3, None, ["vibe"], {"p": "vibe"}, True])
def test_read_posture_non_string_flagged_never_returned(tmp_path, value):
    spec = _spec_dir(tmp_path)
    _write_raw(tmp_path, {"schemaVersion": 1, "language": "python", "posture": value})
    assert ac.read_posture(spec) == (None, None, True)
    res = ac.resolve_posture(spec)
    assert res.posture == "standard" and res.rejected_non_text is True
    assert res.rejected is None


def test_resolve_posture_precedence_flag_config_default(tmp_path):
    spec = _spec_dir(tmp_path)
    assert ac.resolve_posture(spec).source == "default"
    ac.write_posture(tmp_path, "vibe")
    res = ac.resolve_posture(spec)
    assert (res.posture, res.source) == ("vibe", "config")
    res = ac.resolve_posture(spec, explicit="critical")
    assert (res.posture, res.source) == ("critical", "flag")
    res = ac.resolve_posture(spec, project_root=tmp_path)
    assert (res.posture, res.source) == ("vibe", "config")


def test_write_posture_keeps_language_source_detected_from(tmp_path):
    _root(tmp_path)
    ac.write_arch_config(tmp_path, "python", KNOWN, source="blueprint",
                         detected_from="ARCHITECTURE.md")
    ac.write_posture(tmp_path, "critical")
    data = _cfg(tmp_path)
    assert data == {
        "schemaVersion": 1, "language": "python", "source": "blueprint",
        "detectedFrom": "ARCHITECTURE.md", "posture": "critical",
    }
    raw = ac.config_path(tmp_path).read_text(encoding="utf-8")
    assert raw.endswith("\n") and list(json.loads(raw))[-1] == "posture"


def test_write_arch_config_keeps_posture(tmp_path):
    _root(tmp_path)
    ac.write_arch_config(tmp_path, "python", KNOWN, detected_from="pyproject.toml")
    ac.write_posture(tmp_path, "vibe")
    # A later language write keeps posture; a detectedFrom it does not pass is
    # dropped, as it is today (C7: only `posture` is carried over).
    ac.write_arch_config(tmp_path, "java", KNOWN)
    data = _cfg(tmp_path)
    assert data == {"schemaVersion": 1, "language": "java", "source": "user",
                    "posture": "vibe"}


@pytest.mark.parametrize("writer", ["posture", "language"])
def test_torn_write_leaves_original_and_no_temp(tmp_path, monkeypatch, writer):
    _root(tmp_path)
    ac.write_arch_config(tmp_path, "python", KNOWN)
    target = ac.config_path(tmp_path)
    before = target.read_bytes()

    def boom(*_a, **_k):
        raise OSError("simulated torn write")

    monkeypatch.setattr(ac.os, "replace", boom)
    with pytest.raises(OSError):
        if writer == "posture":
            ac.write_posture(tmp_path, "critical")
        else:
            ac.write_arch_config(tmp_path, "java", KNOWN)
    assert target.read_bytes() == before
    assert sorted(p.name for p in target.parent.iterdir()) == [ac.CONFIG_FILENAME]


def test_posture_write_leaves_approved_hash_unchanged(tmp_path):
    """The posture is out-of-band from every content hash (C7): persisting it
    leaves an approved artifact's bytes, its stored hash and the marker alone."""
    scripts = _REPO_ROOT / "telescoping-sdd" / "scripts"
    tests = scripts / "tests"
    for p in (scripts, tests):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import _fixtures as fx
    import content_hash

    out = fx.write_chain(tmp_path, "sdd", approve=["spec"], bind=False)
    spec = out["spec.md"]
    before = spec.read_bytes()
    stored = content_hash.compute_content_hash(spec.read_text(encoding="utf-8"))
    ac.write_posture(tmp_path, "critical")
    assert spec.read_bytes() == before
    assert content_hash.compute_content_hash(spec.read_text(encoding="utf-8")) == stored
    assert not (tmp_path / ".sdd" / "pending-review.json").exists()


# ---------------------------------------------------------------------------
# Unit D T4 (C7, I4): refuse an unmergeable file; --set-posture on both tiers.
# ---------------------------------------------------------------------------

import subprocess

_VS = _REPO_ROOT / "telescoping-sdd" / "skills" / "spec-driven-dev" / "scripts" / "validate_spec.py"
_VB = _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts" / "validate_blueprint.py"

_UNMERGEABLE = {
    "malformed-json": "{not json",
    "not-an-object": "[1, 2]",
    "absent-schema": json.dumps({"language": "python"}),
    "unknown-schema": json.dumps({"schemaVersion": 99, "language": "python"}),
    "non-string-posture": json.dumps({"schemaVersion": 1, "language": "python", "posture": 7}),
}


def _run(script: Path, *args):
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True)


_REFUSAL_CASES = [(w, r) for w in ("posture", "language") for r in _UNMERGEABLE] + [
    # Only write_posture keeps the language, so only it must refuse a
    # non-string one; write_arch_config replaces the language wholesale.
    ("posture", "non-string-language"),
]


@pytest.mark.parametrize("writer,reason", _REFUSAL_CASES)
def test_unmergeable_file_refused_by_both_writers_byte_unchanged(tmp_path, writer, reason):
    raw = (json.dumps({"schemaVersion": 1, "language": 5})
           if reason == "non-string-language" else _UNMERGEABLE[reason])
    target = _write_raw(tmp_path, raw)
    before = target.read_bytes()
    with pytest.raises(ValueError) as exc:
        if writer == "posture":
            ac.write_posture(tmp_path, "critical")
        else:
            ac.write_arch_config(tmp_path, "python", KNOWN)
    msg = str(exc.value)
    assert msg.startswith(f"refusing to rewrite {target}: ")
    assert msg.endswith("; fix or delete it")
    assert target.read_bytes() == before
    assert sorted(p.name for p in target.parent.iterdir()) == [ac.CONFIG_FILENAME]


def _cli_case(tmp_path: Path, case: str):
    if case in ("sdd-set-posture", "sdd-set-language"):
        spec = _spec_dir(tmp_path)
        arg = ["--set-posture", "critical"] if case == "sdd-set-posture" else ["--set-language", "python"]
        return _VS, [str(spec), *arg]
    bp = tmp_path / "blueprint"
    bp.mkdir()
    (bp / "ARCHITECTURE.md").write_text(
        "# Architecture\n\n## Technology Choices\n\n**Architecture token:** `python`\n",
        encoding="utf-8",
    )
    arg = ["--set-posture", "critical"] if case == "bp-set-posture" else ["--write-arch-config"]
    return _VB, [str(bp), *arg]


@pytest.mark.parametrize(
    "case", ["sdd-set-posture", "bp-set-posture", "sdd-set-language", "bp-write-arch-config"]
)
def test_unmergeable_file_cli_exits_2_file_unchanged(tmp_path, case):
    (tmp_path / ".git").mkdir()
    script, argv = _cli_case(tmp_path, case)
    target = _write_raw(tmp_path, _UNMERGEABLE["malformed-json"])
    before = target.read_bytes()
    r = _run(script, *argv)
    assert r.returncode == 2, (r.stdout, r.stderr)
    out = r.stdout + r.stderr
    assert "error: refusing to rewrite" in out
    assert "Traceback" not in r.stderr
    assert target.read_bytes() == before


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_set_posture_cli_writes_only_architecture_json(tmp_path, tier):
    (tmp_path / ".git").mkdir()
    script, argv = _cli_case(tmp_path, "sdd-set-posture" if tier == "sdd" else "bp-set-posture")
    before = {p.relative_to(tmp_path): p.read_bytes()
              for p in tmp_path.rglob("*") if p.is_file()}
    r = _run(script, *argv)
    assert r.returncode == 0, (r.stdout, r.stderr)
    target = ac.config_path(tmp_path)
    assert f"Persisted posture 'critical' to {target}" in r.stdout
    after = {p.relative_to(tmp_path): p.read_bytes()
             for p in tmp_path.rglob("*") if p.is_file()}
    changed = {k for k in after if before.get(k) != after[k]}
    assert changed == {Path(".sdd") / "architecture.json"}
    assert _cfg(tmp_path)["posture"] == "critical"


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_set_posture_cli_leaves_hash_and_no_pending_review(tmp_path, tier):
    scripts = _REPO_ROOT / "telescoping-sdd" / "scripts"
    tests = scripts / "tests"
    for p in (scripts, tests):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import _fixtures as fx

    first = "spec" if tier == "sdd" else "scope"
    out = fx.write_chain(tmp_path, tier, approve=[first], bind=False)
    art = next(iter(out.values()))
    before = art.read_bytes()
    script = _VS if tier == "sdd" else _VB
    r = _run(script, str(art.parent), "--set-posture", "critical")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "Persisted posture 'critical' to" in r.stdout
    assert art.read_bytes() == before
    assert not (tmp_path / ".sdd" / "pending-review.json").exists()
    v = _run(script, str(art.parent))
    assert "has not been modified since approval" not in "\n".join(
        l for l in v.stdout.splitlines() if "[FAIL]" in l
    )


@pytest.mark.parametrize("script", [_VS, _VB], ids=["sdd", "blueprint"])
def test_set_posture_rejects_out_of_vocabulary_value(tmp_path, script):
    d = tmp_path / "x"
    d.mkdir()
    r = _run(script, str(d), "--set-posture", "yolo")
    assert r.returncode == 2
    assert "invalid choice" in r.stderr
    assert not ac.config_path(tmp_path).exists()
