"""Tests for the shared spec-directory name grammar (`spec_dirname.py`) and the
two validators that consume it.

Staging (see tasks.md T2 EXPECTED-RED roster):
  * grammar + slugify tests        -> green after T1 (the module).
  * symmetry / classify_spec /     -> green after T4 (validate_blueprint).
    validate_plan integration
  * check_dir_identifier matrix /  -> green after T5 (validate_spec).
    my-feature literal
  * doc-consistency                -> green after T6 (doc sweep).
"""
from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"
_SPEC_SCRIPTS = (
    _REPO_ROOT / "telescoping-sdd" / "skills" / "spec-driven-dev" / "scripts"
)
_BP_SCRIPTS = (
    _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts"
)
_SPEC_DIRNAME_PATH = _SCRIPTS / "spec_dirname.py"
_VALIDATE_SPEC_PATH = _SPEC_SCRIPTS / "validate_spec.py"
_VALIDATE_BLUEPRINT_PATH = _BP_SCRIPTS / "validate_blueprint.py"

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import spec_dirname as sd  # noqa: E402


def _load_module(mod_name: str, scripts_dir: Path):
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    if mod_name in sys.modules:
        return importlib.reload(sys.modules[mod_name])
    return importlib.import_module(mod_name)


def _load_validate_spec():
    return _load_module("validate_spec", _SPEC_SCRIPTS)


def _load_validate_blueprint():
    return _load_module("validate_blueprint", _BP_SCRIPTS)


# ===========================================================================
# Grammar predicates (green after T1)
# ===========================================================================

@pytest.mark.parametrize("value,expected", [
    ("checkout-flow", True),
    ("cli-notes-app", True),
    ("2fa-login", True),
    ("123", True),
    ("a", True),
    ("a" * 50, True),
    ("a" * 51, False),
    ("CheckoutFlow", False),
    ("checkout_flow", False),
    ("", False),
    ("checkout--flow", False),
    ("-checkout", False),
    ("checkout-", False),
])
def test_is_valid_slug(value, expected):
    assert sd.is_valid_slug(value) is expected


@pytest.mark.parametrize("value,expected", [
    ("F3-checkout-flow", True),
    ("F1-a", True),
    ("F10-slug", True),
    ("F3", False),
    ("f3-racing", False),
    ("F0-x", False),
    ("F007-x", False),
    ("F3-" + "a" * 50, True),
    ("F3-" + "a" * 51, False),
    ("My_Feature", False),
])
def test_is_bound_form(value, expected):
    assert sd.is_bound_form(value) is expected


@pytest.mark.parametrize("value,expected", [
    ("cli-notes-app", True),
    ("f3-racing", True),
    ("2fa-login", True),
    ("F3-checkout-flow", False),
    ("F3", False),
    ("My_Feature", False),
])
def test_is_standalone_form(value, expected):
    assert sd.is_standalone_form(value) is expected


@pytest.mark.parametrize("value,expected", [
    ("F3-checkout-flow", "bound"),
    ("F3", "bare"),
    ("F0", "bare"),
    ("F007", "bare"),
    ("F0-x", "invalid"),
    ("F007-x", "invalid"),
    ("cli-notes-app", "standalone"),
    ("f3-racing", "standalone"),
    ("My_Feature", "invalid"),
])
def test_classify_dirname(value, expected):
    assert sd.classify_dirname(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("F3-checkout-flow", 3),
    ("F3", 3),
    ("F0", 0),
    ("F007", 7),
    ("cli-notes-app", None),
    ("f3-racing", None),
    ("My_Feature", None),
    ("F0-x", None),
    ("F007-x", None),
])
def test_parse_feature_number(value, expected):
    assert sd.parse_feature_number(value) == expected


def test_parse_feature_number_leniency_documented():
    """parse_feature_number is lenient on bare tokens; validity gating must NOT
    rely on `parse_feature_number is not None`."""
    assert sd.parse_feature_number("F3") == 3
    assert not sd.is_bound_form("F3")
    assert sd.classify_dirname("F3") == "bare"


# ===========================================================================
# Derived form: DERIVED_DIRNAME_PATTERN / is_derived_form / classify_dirname (T2)
# ===========================================================================

@pytest.mark.parametrize("name", [
    "residents--F7-resident-sync",
    "vps-edge--F1-a",
])
def test_classify_dirname_derived_form(name):
    assert sd.classify_dirname(name) == "derived"


def test_classify_dirname_derived_hyphenated_alias():
    """A hyphenated (multi-segment kebab) project alias is valid."""
    assert sd.classify_dirname("vps-edge--F7-sync") == "derived"


def test_classify_dirname_derived_slug_too_long():
    """Slug > 50 chars → invalid (slug cap enforced via is_valid_slug)."""
    name = "residents--F7-" + "a" * 51
    assert sd.classify_dirname(name) == "invalid"


def test_classify_dirname_f7_double_dash_checkout():
    """`F7--checkout` is NOT derived: uppercase F is not a valid lowercase
    project alias, so it falls through to invalid (it has a `--` suffix)."""
    assert sd.classify_dirname("F7--checkout") == "invalid"


@pytest.mark.parametrize("name,expected", [
    # The four pre-existing categories are unchanged after the derived branch.
    ("F3-checkout-flow", "bound"),
    ("F1-a", "bound"),
    ("cli-notes-app", "standalone"),
    ("f3-racing", "standalone"),
    ("F3", "bare"),
    ("F0", "bare"),
    ("F007", "bare"),
    ("F0-x", "invalid"),
    ("F007-x", "invalid"),
    ("My_Feature", "invalid"),
])
def test_classify_dirname_derived_no_regression(name, expected):
    """Adding the derived branch leaves bound/standalone/bare/invalid intact."""
    assert sd.classify_dirname(name) == expected


@pytest.mark.parametrize("name", [
    "residents--F7-resident-sync",
    "vps-edge--F1-a",
    "vps-edge--F7-sync",
    "a--F99-x",
])
def test_is_derived_form_true_cases(name):
    assert sd.is_derived_form(name) is True


@pytest.mark.parametrize("name", [
    "F3-checkout-flow",                 # bound
    "cli-notes-app",                    # standalone
    "F3",                               # bare
    "My_Feature",                       # invalid
    "F7--checkout",                     # uppercase-F alias → not derived
    "Residents--F7-sync",               # uppercase alias char → not derived
    "residents--F0-sync",               # leading/zero feature number
    "residents--F07-sync",              # leading-zero feature number
    "residents--F7-" + "a" * 51,        # slug > 50 chars
    "residents--F7-sync\n",              # trailing newline (\Z, not $) → not derived
])
def test_is_derived_form_false_cases(name):
    assert sd.is_derived_form(name) is False


def test_classify_dirname_trailing_newline_not_derived():
    """A newline-suffixed derived-looking name is NOT derived (regression).

    `DERIVED_DIRNAME_PATTERN` is `\\A...\\Z`-anchored, not `^...$`, so `$`
    matching just before a trailing `\\n` cannot classify `proj--F7-x\\n` as
    derived while `project_link.parse_derived_dirname` (the same compiled
    pattern) rejects it. The two used to disagree, crashing validate_spec's
    derived branch on the `None` unpack.
    """
    assert sd.is_derived_form("residents--F7-x\n") is False
    assert sd.classify_dirname("residents--F7-x\n") == "invalid"


def test_is_derived_spec_wrapper(tmp_path):
    """is_derived_spec is the single shared predicate over classify_dirname."""
    derived = tmp_path / "residents--F7-resident-sync"
    derived.mkdir()
    bound = tmp_path / "F3-checkout-flow"
    bound.mkdir()
    standalone = tmp_path / "cli-notes-app"
    standalone.mkdir()
    assert sd.is_derived_spec(derived) is True
    assert sd.is_derived_spec(bound) is False
    assert sd.is_derived_spec(standalone) is False


# ===========================================================================
# slugify (green after T1)
# ===========================================================================

@pytest.mark.parametrize("title,expected", [
    ("Checkout Flow (v2)", "checkout-flow-v2"),
    ("My Feature Title", "my-feature-title"),
    ("  leading spaces  ", "leading-spaces"),
    ("a---b", "a-b"),
])
def test_slugify_basic_cases(title, expected):
    assert sd.slugify(title) == expected


@pytest.mark.parametrize("title,expected", [
    ("Café", "cafe"),
    ("Über Feature", "uber-feature"),
    ("señor", "senor"),
])
def test_slugify_accent_folding(title, expected):
    assert sd.slugify(title) == expected


@pytest.mark.parametrize("title,expected", [
    ("x²³", "x23"),
    ("ﬁrst", "first"),
])
def test_slugify_nfkd_expansion(title, expected):
    assert sd.slugify(title) == expected


def test_slugify_control_character():
    assert sd.slugify("a\x00b") == "a-b"


@pytest.mark.parametrize("title", ["!!!", "🚀", "   "])
def test_slugify_empty_result_raises_value_error(title):
    with pytest.raises(ValueError):
        sd.slugify(title)


def test_slugify_truncation_at_hyphen_boundary():
    title = "alpha-bravo-charlie-delta-echo-foxtrot-golf-hotel-india"  # 55 chars
    result = sd.slugify(title)
    assert result == "alpha-bravo-charlie-delta-echo-foxtrot-golf-hotel"
    assert len(result) <= 50
    assert sd.is_valid_slug(result)


def test_slugify_single_segment_hard_truncation():
    result = sd.slugify("a" * 60)
    assert result == "a" * 50
    assert len(result) == 50
    assert sd.is_valid_slug(result)


def test_slugify_output_always_satisfies_is_valid_slug():
    titles = [
        "Checkout Flow (v2)", "My Feature Title", "  leading spaces  ", "a---b",
        "Café", "Über Feature", "señor", "x²³", "ﬁrst", "a\x00b",
        "alpha-bravo-charlie-delta-echo-foxtrot-golf-hotel-india", "a" * 60,
    ]
    for title in titles:
        assert sd.is_valid_slug(sd.slugify(title)), title


def _run_cli(*args):
    import subprocess
    return subprocess.run(
        [sys.executable, str(_SPEC_DIRNAME_PATH), *args],
        capture_output=True, text=True, check=False,
    )


def test_slugify_cli_subcommand():
    proc = _run_cli("slugify", "My Feature")
    assert proc.returncode == 0, proc.stderr
    assert "my-feature" in proc.stdout
    proc_empty = _run_cli("slugify", "!!!")
    assert proc_empty.returncode == 1
    assert proc_empty.stderr.strip()
    proc_noarg = _run_cli("slugify")
    assert proc_noarg.returncode == 2
    proc_bad = _run_cli("badcmd", "x")
    assert proc_bad.returncode == 2


def test_slugify_cli_exit_codes_precise():
    assert _run_cli("slugify", "valid title").returncode == 0
    assert _run_cli("slugify", "!!!").returncode == 1  # empty result, NOT 2
    assert _run_cli("slugify").returncode == 2          # missing arg, NOT 1
    assert _run_cli("badcmd", "x").returncode == 2      # unknown subcmd, NOT 1


def test_spec_dirname_is_stdlib_only():
    """R4 mitigation: spec_dirname imports no third-party packages."""
    source = _SPEC_DIRNAME_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    stdlib_ok = {"re", "sys", "unicodedata", "typing", "pathlib", "__future__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                assert n.name.split(".")[0] in stdlib_ok, f"non-stdlib import: {n.name}"
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] in stdlib_ok, (
                f"non-stdlib import-from: {node.module}"
            )


# ===========================================================================
# check_dir_identifier matrix (green after T5)
# ===========================================================================

def _make_spec_dir(tmp_path, dirname, identifier="n/a", with_spec=True):
    d = tmp_path / dirname
    d.mkdir(parents=True, exist_ok=True)
    if with_spec:
        (d / "spec.md").write_text(
            f"# Feature: X\n\n**PLAN feature identifier:** `{identifier}`\n\n"
            f"## Objective\n\nstuff\n",
            encoding="utf-8",
        )
    return d


@pytest.mark.parametrize("dirname,identifier,expected", [
    ("F3-checkout-flow", "F3", None),                         # bound n==m  -> PASS
    ("F3-checkout-flow", "F5", "dir-identifier-mismatch"),    # bound n!=m
    ("F3-checkout-flow", "n/a", "dir-identifier-mismatch"),   # bound + n/a
    ("checkout-flow", "n/a", None),                           # standalone + n/a -> PASS
    ("checkout-flow", "F3", "dir-identifier-mismatch"),       # standalone + F3
    ("F3", "F3", "missing-slug"),                             # bare token
    ("My_Feature", "n/a", "invalid-slug"),                    # invalid name
])
def test_check_dir_identifier_matrix(tmp_path, dirname, identifier, expected):
    vs = _load_validate_spec()
    d = _make_spec_dir(tmp_path, dirname, identifier)
    result = vs.check_dir_identifier(d)
    if expected is None:
        assert result.passed, f"expected PASS for {dirname!r}/{identifier!r}: {result.checks}"
    else:
        assert not result.passed, f"expected FAIL for {dirname!r}/{identifier!r}"
        assert result.checks[0][0] == expected
        assert result.checks[0][1] == "FAIL"


def test_check_dir_identifier_hand_typed_long_slug(tmp_path):
    vs = _load_validate_spec()
    d = _make_spec_dir(tmp_path, "F3-" + "a" * 51, "F3")
    result = vs.check_dir_identifier(d)
    assert result.checks[0][0] == "invalid-slug"


def test_check_dir_identifier_non_utf8_spec_md(tmp_path):
    vs = _load_validate_spec()
    d = tmp_path / "F3-checkout-flow"
    d.mkdir()
    (d / "spec.md").write_bytes(b"**PLAN feature identifier:** \xff\n")
    result = vs.check_dir_identifier(d)
    assert result.checks[0][0] == "cannot-cross-check"


def test_check_dir_identifier_missing_identifier_line(tmp_path):
    vs = _load_validate_spec()
    d = tmp_path / "F3-checkout-flow"
    d.mkdir()
    (d / "spec.md").write_text("# Feature: X\n\nno identifier line here\n", encoding="utf-8")
    result = vs.check_dir_identifier(d)
    assert result.checks[0][0] == "cannot-cross-check"


def test_check_dir_identifier_control_char_in_dirname(tmp_path):
    """A newline in the directory name must be escaped in the FAIL detail so it
    cannot inject a spurious newline into the validator's stdout."""
    vs = _load_validate_spec()
    raw_name = "F3-checkout\nflow"
    try:
        d = tmp_path / raw_name
        d.mkdir()
        (d / "spec.md").write_text(
            "**PLAN feature identifier:** `F3`\n", encoding="utf-8"
        )
    except OSError:
        pytest.skip("filesystem rejects newline in directory name")
    result = vs.check_dir_identifier(d)
    detail = result.checks[0][2]
    assert "F3-checkout\\nflow" in detail        # escaped form present
    assert "F3-checkout\nflow" not in detail      # raw newline NOT injected


# ===========================================================================
# Producer/consumer symmetry (green after T4 + T5)
# ===========================================================================

def test_no_inline_dirname_regexes_in_validators():
    """Both validators import classify_dirname from spec_dirname (same object),
    and validate_blueprint has no inline F-dirname regex in classify_spec or
    walk_specs. Modelled on test_arch_config's live-import comparison."""
    for vpath, mod_name, scripts_dir in [
        (_VALIDATE_SPEC_PATH, "validate_spec", _SPEC_SCRIPTS),
        (_VALIDATE_BLUEPRINT_PATH, "validate_blueprint", _BP_SCRIPTS),
    ]:
        mod = _load_module(mod_name, scripts_dir)
        assert hasattr(mod, "classify_dirname"), (
            f"{mod_name} does not expose classify_dirname (missing import)"
        )
        assert mod.classify_dirname is sd.classify_dirname, (
            f"{mod_name}.classify_dirname is not spec_dirname.classify_dirname"
        )

    source = _VALIDATE_BLUEPRINT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    def _inline_F_regex_calls(func_name):
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name != func_name:
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                func = child.func
                if not (
                    isinstance(func, ast.Attribute)
                    and func.attr in {"match", "compile", "fullmatch"}
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "re"
                ):
                    continue
                if child.args and isinstance(child.args[0], ast.Constant):
                    if isinstance(child.args[0].value, str) and child.args[0].value.startswith("F"):
                        found.append(ast.unparse(child))
        return found

    assert _inline_F_regex_calls("classify_spec") == [], "inline F-regex in classify_spec"
    assert _inline_F_regex_calls("walk_specs") == [], "inline F-regex in walk_specs"

    corpus = [
        ("F3-checkout-flow", "bound"), ("F3", "bare"), ("cli-notes-app", "standalone"),
        ("My_Feature", "invalid"), ("F0", "bare"), ("f3-racing", "standalone"),
        ("residents--F7-x", "derived"),  # CPD: exercise the new category through both validators
    ]
    for name, expected in corpus:
        assert sd.classify_dirname(name) == expected


def test_validate_spec_py_no_my_feature_literal():
    """R4: validate_spec.py must contain no `specs/my-feature/` literal."""
    source = _VALIDATE_SPEC_PATH.read_text(encoding="utf-8")
    count = source.count("specs/my-feature/")
    assert count == 0, (
        f"validate_spec.py still has {count} occurrence(s) of 'specs/my-feature/' "
        f"— update the docstring, epilog, and help string to a bound-form example"
    )


# ===========================================================================
# classify_spec / validate_plan integration (green after T4)
# ===========================================================================

def test_classify_spec_feature_id_never_none(tmp_path):
    vb = _load_validate_blueprint()
    for name in ("F1-alpha", "F1", "cli-notes-app", "My_Feature"):
        d = tmp_path / name
        d.mkdir()
        state = vb.classify_spec(d)
        assert state.feature_id is not None
        assert isinstance(state.feature_id, int)


def test_classify_spec_resolves_bound_and_bare_feature_id(tmp_path):
    """Value check (not just never-None): the bound F<n>-<slug> form resolves to
    its number — the silent-skip bug R3 kills. A never-None test is insufficient
    because the OLD regex also returned a non-None int (-1) for 'F1-alpha'."""
    vb = _load_validate_blueprint()
    for name in ("F1-alpha", "F1"):
        d = tmp_path / name
        d.mkdir()
        assert vb.classify_spec(d).feature_id == 1, name


MINIMAL_PLAN = (
    "# Plan\n\n"
    "## Open Questions\n\n"
    "nothing\n\n"
    "## Feature Breakdown\n\n"
    "### F1: Example feature\n\n"
    "- **Component:** Some component\n"
    "- **Acceptance Criteria:** the feature works\n\n"
    "## MVP Definition\n\n"
    "F1 is the MVP.\n\n"
    "## Feature Dependencies\n\n"
    "F1 has no dependencies.\n\n"
    "## Implementation Order\n\n"
    "1. F1\n\n"
    "## Milestones\n\n"
    "- M1: F1\n\n"
    "## Panel Review\n\n"
    "blah\n"
)


def test_validate_plan_malformed_dirname_warns_and_zero_specstates(tmp_path):
    """AD2 plumbing end-to-end: My_Feature/ emits exactly one malformed-spec-dirname
    WARN AND contributes zero SpecState entries; checkout-flow/ (standalone) emits
    no WARN. Exercises the non-CFC fast path in validate_plan."""
    vb = _load_validate_blueprint()
    blueprint_dir = tmp_path / "blueprint"
    blueprint_dir.mkdir()
    (blueprint_dir / "PLAN.md").write_text(MINIMAL_PLAN, encoding="utf-8")
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "My_Feature").mkdir()     # invalid -> WARN + excluded
    (specs / "checkout-flow").mkdir()  # standalone -> silent skip

    result = vb.validate_plan(blueprint_dir)

    malformed = [c for c in result.checks if c[0] == "malformed-spec-dirname"]
    assert len(malformed) == 1, f"expected 1 malformed WARN, got {len(malformed)}: {malformed}"
    assert "My_Feature" in malformed[0][2]
    assert not any("checkout-flow" in c[2] for c in result.checks)

    assert vb.walk_specs(tmp_path) == []


@pytest.mark.parametrize("dir_a,dir_b", [
    ("F3-alpha", "F3"),       # bound + bare (migration artifact)
    ("F3-alpha", "F3-beta"),  # bound + bound (two slugs, same number)
])
def test_duplicate_feature_dirs_warn(tmp_path, dir_a, dir_b):
    """AD8: two spec dirs with the same feature_id emit exactly one
    duplicate-feature-dir WARN naming BOTH directories."""
    vb = _load_validate_blueprint()
    blueprint_dir = tmp_path / "blueprint"
    blueprint_dir.mkdir()
    (blueprint_dir / "PLAN.md").write_text(MINIMAL_PLAN, encoding="utf-8")
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / dir_a).mkdir()
    (specs / dir_b).mkdir()

    result = vb.validate_plan(blueprint_dir)
    dup = [c for c in result.checks if c[0] == "duplicate-feature-dir"]
    assert len(dup) == 1, f"expected 1 duplicate WARN for {dir_a}+{dir_b}, got {len(dup)}"
    detail = dup[0][2]
    assert f"'{dir_a}'" in detail, f"{dir_a!r} not named in {detail!r}"
    assert f"'{dir_b}'" in detail, f"{dir_b!r} not named in {detail!r}"


def test_duplicate_feature_dir_warn_escapes_control_chars():
    """The duplicate-feature-dir WARN escapes control chars in directory names
    (defense-in-depth, mirroring the validate_spec / malformed-warn invariant).
    Tested via a DIRECT helper call with synthetic SpecStates: a control char
    makes a name 'invalid', so such a directory never resolves to a feature_id
    through walk_specs — the escaping is reachable only defensively."""
    vb = _load_validate_blueprint()
    s1 = vb.SpecState(
        feature_id=3, spec_dir=Path("specs/F3"), state=vb.STATE_NOT_STARTED,
        cfc_tags_in_spec=[], cfc_tags_in_tasks=[], spec_content=None, tasks_content=None,
    )
    s2 = vb.SpecState(
        feature_id=3, spec_dir=Path("specs/F3-a\nb"), state=vb.STATE_NOT_STARTED,
        cfc_tags_in_spec=[], cfc_tags_in_tasks=[], spec_content=None, tasks_content=None,
    )
    result = vb.ValidationResult()
    vb._emit_duplicate_feature_dir_warns([s1, s2], result)
    dup = [c for c in result.checks if c[0] == "duplicate-feature-dir"]
    assert len(dup) == 1
    detail = dup[0][2]
    assert "\\n" in detail        # escaped form present
    assert "a\nb" not in detail    # raw newline NOT injected


# ===========================================================================
# Doc-consistency (green after T6)
# ===========================================================================

import re as _re  # noqa: E402

_SDD = _REPO_ROOT / "telescoping-sdd" / "skills" / "spec-driven-dev"
_PB = _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint"

DOC_INVENTORY = [
    _SDD / "SKILL.md",
    _SDD / "references" / "phase-specify.md",
    _SDD / "references" / "phase-design.md",
    _SDD / "references" / "phase-tasks.md",
    _SDD / "references" / "examples.md",
    _SDD / "references" / "hash-and-cascade.md",
    _SDD / "references" / "panel-review.md",
    _PB / "references" / "workflow-overview.md",
    _REPO_ROOT / "CLAUDE.md",
    _REPO_ROOT / "README.md",
]

STALE_PLACEHOLDER_RE = _re.compile(r"specs/<feature(?:-name)?>/")


def test_no_stale_placeholder_in_docs():
    failures = []
    for path in DOC_INVENTORY:
        content = path.read_text(encoding="utf-8")
        for m in STALE_PLACEHOLDER_RE.finditer(content):
            failures.append(f"{path}: {m.group(0)!r}")
    assert not failures, "Stale placeholder(s) found:\n" + "\n".join(failures)


# ===========================================================================
# Review-driven regression tests (post-1.7.0 code-review fixes)
# ===========================================================================

@pytest.mark.parametrize("name,expected", [
    ("F3-checkout-flow", (3, "checkout-flow")),
    ("F10-a-b-c", (10, "a-b-c")),
    ("F3", None),            # bare, no slug
    ("cli-notes-app", None),  # standalone
    ("F0-x", None),          # zero is not a valid bound number
    ("My_Feature", None),    # invalid
])
def test_parse_bound(name, expected):
    """parse_bound is the single grammar-owned (number, slug) decomposition."""
    assert sd.parse_bound(name) == expected


def test_display_safe_escapes_control_chars():
    assert sd.display_safe("F3-a\nb") == "F3-a\\nb"
    assert sd.display_safe("checkout-flow") == "checkout-flow"


def test_check_dir_identifier_bare_zero_no_circular_suggestion(tmp_path):
    """F0/F00 (feature number 0) has NO valid bound form; the missing-slug
    message must not suggest the impossible 'F0-<slug>'."""
    vs = _load_validate_spec()
    for dirname in ("F0", "F00"):
        d = _make_spec_dir(tmp_path / dirname.lower(), dirname, "n/a")
        r = vs.check_dir_identifier(d)
        assert r.checks[0][0] == "missing-slug"
        detail = r.checks[0][2]
        assert "F0-<slug>" not in detail and "F0-checkout-flow" not in detail
        assert "n >= 1" in detail


def test_check_dir_identifier_bare_leading_zero_suggests_canonical(tmp_path):
    """F03 (bare, leading zero) → suggest canonical 'F3-<slug>', not 'F03-<slug>'."""
    vs = _load_validate_spec()
    d = _make_spec_dir(tmp_path, "F03", "n/a")
    r = vs.check_dir_identifier(d)
    assert r.checks[0][0] == "missing-slug"
    detail = r.checks[0][2]
    assert "F3-<slug>" in detail
    assert "F03-<slug>" not in detail


def test_check_dir_identifier_numeric_compare_ignores_leading_zero(tmp_path):
    """A bound dir F3-x with a non-canonical in-file identifier 'F03' is the SAME
    feature number → PASS, not a false dir-identifier-mismatch."""
    vs = _load_validate_spec()
    d = _make_spec_dir(tmp_path, "F3-x", "F03")
    r = vs.check_dir_identifier(d)
    assert r.passed, r.checks


def test_check_dir_identifier_cannot_cross_check_names_placeholder_fix(tmp_path):
    """When spec.md still has the unfilled `F<n>` template placeholder, the
    cannot-cross-check message points at the real fix (fill it in), not just
    'approve spec first'."""
    vs = _load_validate_spec()
    d = tmp_path / "F3-checkout-flow"
    d.mkdir()
    (d / "spec.md").write_text("**PLAN feature identifier:** `F<n>`\n", encoding="utf-8")
    r = vs.check_dir_identifier(d)
    assert r.checks[0][0] == "cannot-cross-check"
    assert "placeholder" in r.checks[0][2].lower()


def test_validate_plan_bare_zero_warn_no_circular_suggestion(tmp_path):
    """specs/F0/ malformed WARN must not suggest the impossible 'F0-<slug>'."""
    vb = _load_validate_blueprint()
    blueprint_dir = tmp_path / "blueprint"
    blueprint_dir.mkdir()
    (blueprint_dir / "PLAN.md").write_text(MINIMAL_PLAN, encoding="utf-8")
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "F0").mkdir()
    result = vb.validate_plan(blueprint_dir)
    warns = [c for c in result.checks if c[0] == "malformed-spec-dirname"]
    assert len(warns) == 1
    assert "F0-<slug>" not in warns[0][2]
    assert "n >= 1" in warns[0][2]
