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
