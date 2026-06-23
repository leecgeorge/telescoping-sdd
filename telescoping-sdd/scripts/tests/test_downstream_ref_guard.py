"""Tests for the shared downstream_ref_guard.py module + the R5 prevention-doc guard.

Two independent layers:
  (A) Group 7 doc-presence tests — filesystem-only; green once T1-T5 land; no guard
      import, so they pass before downstream_ref_guard.py exists.
  (B) Groups 1-3 guard-unit tests — import scan_for_downstream_refs from
      downstream_ref_guard via a LAZY module-level loader, so a missing module
      surfaces as a per-test failure (red until T7) rather than a collection error.

Repo root is parents[3] from this file:
  telescoping-sdd/scripts/tests/test_downstream_ref_guard.py
  parents[0]=tests/ [1]=scripts/ [2]=telescoping-sdd/ [3]=<repo-root>/
"""

from __future__ import annotations

import ast
import importlib
import sys
import tokenize
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "telescoping-sdd" / "scripts"


def _load_guard():
    """Lazy import of the guard module (mirrors test_validate_tasks.py:15-23). No
    reload — a stable module object keeps `scan_for_downstream_refs` identical to the
    object both validators import (asserted by the Group-6 import-identity test)."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    return importlib.import_module("downstream_ref_guard")


def _policies():
    """Return (guard_module, blueprint_policy, sdd_policy). Built from the guard's
    own PolicyConfig so Groups 1-3 exercise the guard in isolation (the validators'
    own *_DOWNSTREAM_POLICY constants are exercised behaviorally in Group 9, T11)."""
    g = _load_guard()
    bp = g.PolicyConfig(
        letter="F",
        heading_warn_only=False,
        bare_warn_only=True,
        troubleshooting_ref=(
            "See project-blueprint/references/troubleshooting.md "
            "'Downstream identifier in upstream artifact'."
        ),
        noun="feature",
        downstream_artifact="03_PLAN.md",
    )
    sdd = g.PolicyConfig(
        letter="T",
        heading_warn_only=False,
        bare_warn_only=True,
        troubleshooting_ref=(
            "See spec-driven-dev/references/troubleshooting.md "
            "'Downstream identifier in upstream artifact'."
        ),
        noun="task",
        downstream_artifact="03_tasks.md",
    )
    return g, bp, sdd


def _scan(content, policy, filename="fixture.md"):
    g = _load_guard()
    return g.scan_for_downstream_refs(content, filename, policy)


def _tokens(findings):
    return {f.token for f in findings}


def _by_token(findings, token):
    return [f for f in findings if f.token == token]


# ===========================================================================
# Group 7 — Prevention-doc / rollout-doc presence (R5, R7 AC#3)
# Filesystem-only; no guard import; green once T1-T5 land.
# ===========================================================================

MARKER = "DO NOT use downstream identifier references in this artifact"

# name -> (repo-relative path, tier letter that must appear alongside the marker)
_PREVENTION_FILES = {
    "project-spec-analyst": ("telescoping-sdd/agents/project-spec-analyst.md", "F"),
    "project-architecture-analyst": ("telescoping-sdd/agents/project-architecture-analyst.md", "F"),
    "feature-spec-analyst": ("telescoping-sdd/agents/feature-spec-analyst.md", "T"),
    "feature-architecture-analyst": ("telescoping-sdd/agents/feature-architecture-analyst.md", "T"),
    "phase-scope": ("telescoping-sdd/skills/project-blueprint/references/phase-scope.md", "F"),
    "phase-architecture": ("telescoping-sdd/skills/project-blueprint/references/phase-architecture.md", "F"),
    "phase-specify": ("telescoping-sdd/skills/spec-driven-dev/references/phase-specify.md", "T"),
    "phase-design": ("telescoping-sdd/skills/spec-driven-dev/references/phase-design.md", "T"),
}

_TROUBLESHOOTING = {
    "blueprint": "telescoping-sdd/skills/project-blueprint/references/troubleshooting.md",
    "sdd": "telescoping-sdd/skills/spec-driven-dev/references/troubleshooting.md",
}
TROUBLESHOOTING_SECTION = "## Downstream identifier in upstream artifact"
CHANGELOG_ANCHOR = "heading-form FAIL"


@pytest.mark.parametrize("name", list(_PREVENTION_FILES))
def test_prevention_text_present(name):
    rel, letter = _PREVENTION_FILES[name]
    text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
    assert MARKER in text, f"{name}: shared prohibition marker missing"
    assert f"{letter}<n>" in text, f"{name}: tier letter {letter}<n> missing near the prohibition"


@pytest.mark.parametrize("tier", list(_TROUBLESHOOTING))
def test_troubleshooting_section_present(tier):
    text = (_REPO_ROOT / _TROUBLESHOOTING[tier]).read_text(encoding="utf-8")
    assert TROUBLESHOOTING_SECTION in text, f"{tier}: troubleshooting section heading missing"


def test_changelog_breaking_change_note():
    text = (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert CHANGELOG_ANCHOR in text, "CHANGELOG breaking-change anchor 'heading-form FAIL' missing"


# ===========================================================================
# Group 1 — Frozen STRIPPER_FIXTURE (primary structure-aware regression anchor)
# Cases (a)-(k) in pinned order, each annotated with its expected outcome.
# Construction safeguards (panel Pass-2): case (c)'s unmatched run is INLINE (not a
# line-start fence); case (i)'s unterminated comment has no later `-->`; case (j) uses
# a 4-backtick fence and case (k) uses a 3-backtick fence, so neither mispairs.
# Tokens are unique per case so an assertion can target one token unambiguously.
# ===========================================================================

STRIPPER_FIXTURE = """\
Intro paragraph with no downstream tokens.

(a) Fenced block below — the bare token inside it must be EXEMPT.
```
config value T3 lives inside a fence
```

(b) Nested inline span on one line — the token inside it is EXEMPT: here is `` `T5` `` quoted.

(c) An unmatched inline triple-backtick run ``` appears mid-prose with no same-line closer;
the real bare token on the next line is DETECTED:
the token T9 is in scannable prose.

(d) A heading inside a fenced block is EXEMPT:
```
### T11: Setup inside a fence
```

(e) Panel Review section — its inner tokens are EXEMPT; the following section is scanned.
## Panel Review
discussion mentions bare T7 in panel prose
### T10: Sealed item line inside the panel
## Footer
the real bare token T14 after the panel is DETECTED.

(f) Far-apart single backticks on different lines straddle a real heading; single-line
pairing cannot blank it, so the heading is DETECTED:
opening backtick `
### T12: Real heading straddled by backticks
closing backtick `

(g) A heading inside an HTML comment is EXEMPT:
<!--
### T13: Commented-out heading
-->

(h) A real, non-exempt heading is DETECTED:
### T15: Real standalone heading

(i) An unterminated HTML comment (no closer) does not swallow the heading after it,
which is DETECTED (fails safe):
<!-- this comment is never closed
### T16: After an unterminated comment

(j) An unterminated 4-backtick fence (no equal-length closer) does not swallow the
heading after it, which is DETECTED (fails safe):
````
### T17: After an unterminated fence

(k) A fenced section-marker inside a Panel Review must not end the panel skip early
(fenced/comment blanking runs before panel blanking), so the inner token stays EXEMPT
and the token in the true following section is DETECTED:
## Panel Review
```
## NotASection
```
inner bare token T18 stays inside the panel
## Footer
the real bare token T19 after the panel is DETECTED.
"""


def test_stripper_fixture_bare_token_detected():
    _g, _bp, sdd = _policies()
    findings = _scan(STRIPPER_FIXTURE, sdd)
    t9 = _by_token(findings, "T9")
    assert len(t9) == 1 and t9[0].form == "bare"


def test_stripper_fixture_fenced_block_exempt():
    _g, _bp, sdd = _policies()
    assert not _by_token(_scan(STRIPPER_FIXTURE, sdd), "T3")


def test_stripper_fixture_nested_backtick_exempt():
    _g, _bp, sdd = _policies()
    assert not _by_token(_scan(STRIPPER_FIXTURE, sdd), "T5")


def test_stripper_fixture_unmatched_backtick_literal():
    # The unmatched inline ``` run must NOT swallow the later bare T9.
    _g, _bp, sdd = _policies()
    assert _by_token(_scan(STRIPPER_FIXTURE, sdd), "T9")


def test_stripper_fixture_panel_review_exempt():
    _g, _bp, sdd = _policies()
    toks = _tokens(_scan(STRIPPER_FIXTURE, sdd))
    assert "T7" not in toks and "T10" not in toks


def test_stripper_fixture_panel_skip_stops_at_next_section():
    # Panel skip is bounded to the next `## ` heading, not to EOF — T14 in `## Footer`
    # is DETECTED.
    _g, _bp, sdd = _policies()
    assert _by_token(_scan(STRIPPER_FIXTURE, sdd), "T14")


def test_stripper_fixture_heading_in_fenced_block_exempt():
    _g, _bp, sdd = _policies()
    assert not _by_token(_scan(STRIPPER_FIXTURE, sdd), "T11")


def test_stripper_fixture_multiline_span_does_not_hide_heading():
    _g, _bp, sdd = _policies()
    t12 = _by_token(_scan(STRIPPER_FIXTURE, sdd), "T12")
    assert len(t12) == 1 and t12[0].form == "heading"


def test_stripper_fixture_html_comment_exempt():
    _g, _bp, sdd = _policies()
    assert not _by_token(_scan(STRIPPER_FIXTURE, sdd), "T13")


def test_stripper_fixture_line_no_is_exact():
    # AD9 char-preservation: the finding's line_no equals the heading's true 1-based line.
    _g, _bp, sdd = _policies()
    t15 = _by_token(_scan(STRIPPER_FIXTURE, sdd), "T15")
    assert len(t15) == 1
    expected = next(
        i for i, ln in enumerate(STRIPPER_FIXTURE.split("\n"), start=1)
        if ln.startswith("### T15:")
    )
    assert t15[0].line_no == expected


def test_stripper_fixture_unterminated_comment_no_swallow():
    _g, _bp, sdd = _policies()
    t16 = _by_token(_scan(STRIPPER_FIXTURE, sdd), "T16")
    assert len(t16) == 1 and t16[0].form == "heading"


def test_stripper_fixture_unterminated_fence_no_swallow():
    _g, _bp, sdd = _policies()
    t17 = _by_token(_scan(STRIPPER_FIXTURE, sdd), "T17")
    assert len(t17) == 1 and t17[0].form == "heading"


def test_stripper_fixture_commented_section_marker_does_not_end_panel_skip():
    _g, _bp, sdd = _policies()
    toks = _tokens(_scan(STRIPPER_FIXTURE, sdd))
    assert "T18" not in toks  # stays inside the panel (fenced `## NotASection` doesn't end it)
    assert "T19" in toks       # the true following section is scanned


# ===========================================================================
# Group 2 — Form classification + precedence + DEF-01 boundary fixtures
# ===========================================================================

def test_heading_form_is_fail():
    g, _bp, sdd = _policies()
    findings = _scan("### T5: Setup\n", sdd)
    assert len(findings) == 1
    assert findings[0].form == g.FORM_HEADING and findings[0].warn_only is False


def test_bare_form_is_warn():
    g, _bp, sdd = _policies()
    findings = _scan("we revisit T3 in prose here\n", sdd)
    assert len(findings) == 1
    assert findings[0].form == g.FORM_BARE and findings[0].warn_only is True


def test_heading_token_not_also_bare_warn():
    _g, _bp, sdd = _policies()
    findings = _scan("### T5: Setup\n", sdd)
    assert len(findings) == 1  # the heading token is classified once, not also bare


def test_second_token_on_heading_line_is_bare_warn():
    g, _bp, sdd = _policies()
    findings = _scan("### T5: see T3 here\n", sdd)
    forms = {f.token: f.form for f in findings}
    assert forms == {"T5": g.FORM_HEADING, "T3": g.FORM_BARE}


def test_checkbox_heading_caught_ticked():
    g, _bp, sdd = _policies()
    findings = _scan("### - [x] T5: Done\n", sdd)
    assert len(findings) == 1 and findings[0].form == g.FORM_HEADING


def test_checkbox_heading_caught_unticked():
    g, _bp, sdd = _policies()
    findings = _scan("### - [ ] T5: Pending\n", sdd)
    assert len(findings) == 1 and findings[0].form == g.FORM_HEADING


def test_checkbox_heading_capital_X():
    g, _bp, sdd = _policies()
    findings = _scan("### - [X] T5: Done\n", sdd)
    assert len(findings) == 1 and findings[0].form == g.FORM_HEADING


def test_checkbox_heading_token_not_also_bare_warn():
    # The checkbox prefix shifts the offset math (match.start(1)-1); still exactly one finding.
    _g, _bp, sdd = _policies()
    assert len(_scan("### - [x] T5: Done\n", sdd)) == 1


@pytest.mark.parametrize("line", ["#### T5: Desc\n", "   ### T5: Desc\n"])
def test_deeper_heading_degrades_to_bare_warn(line):
    # DEF-01: a depth-4 heading and a 3-space-indented (non-line-anchored) heading both
    # degrade to bare-WARN, not heading-FAIL.
    g, _bp, sdd = _policies()
    findings = _scan(line, sdd)
    assert len(findings) == 1 and findings[0].form == g.FORM_BARE


def test_depth_2_heading_degrades_to_bare_warn():
    g, _bp, sdd = _policies()
    findings = _scan("## T5: Desc\n", sdd)
    assert len(findings) == 1 and findings[0].form == g.FORM_BARE


def test_heading_message_echoes_token_and_line():
    _g, _bp, sdd = _policies()
    f = _scan("\n\n### T5: Setup\n", sdd)[0]
    assert "T5" in f.check_name and "T5" in f.detail
    assert str(f.line_no) in f.check_name


def test_heading_message_does_not_suggest_backtick():
    # A line-start heading cannot be backticked away — the heading remediation must not
    # mention backtick; it must offer rename/move and point at the troubleshooting entry.
    _g, _bp, sdd = _policies()
    f = _scan("### T5: Setup\n", sdd)[0]
    assert "backtick" not in f.detail.lower()
    assert "rename" in f.detail.lower()
    assert "Downstream identifier in upstream artifact" in f.detail


def test_bare_message_suggests_refer_or_backtick():
    _g, _bp, sdd = _policies()
    f = _scan("we revisit T3 here\n", sdd)[0]
    low = f.detail.lower()
    assert "backtick" in low or "refer" in low
    assert "Downstream identifier in upstream artifact" in f.detail


# ===========================================================================
# Group 3 — Tier asymmetry (one shared template, per-tier instantiation)
# ===========================================================================

def test_blueprint_policy_finds_F_not_T():
    _g, bp, _sdd = _policies()
    toks = _tokens(_scan("bare F3 and bare T3 in prose\n", bp))
    assert "F3" in toks and "T3" not in toks


def test_sdd_policy_finds_T_not_F():
    _g, _bp, sdd = _policies()
    toks = _tokens(_scan("bare F3 and bare T3 in prose\n", sdd))
    assert "T3" in toks and "F3" not in toks


def test_blueprint_heading_F_is_fail():
    g, bp, _sdd = _policies()
    findings = _scan("### F3: Auth\n", bp)
    assert len(findings) == 1 and findings[0].form == g.FORM_HEADING and findings[0].warn_only is False


def test_sdd_heading_T_not_flagged_at_blueprint():
    _g, bp, _sdd = _policies()
    assert _scan("### T5: Setup\n", bp) == []


def test_blueprint_heading_F_not_flagged_at_sdd():
    _g, _bp, sdd = _policies()
    assert _scan("### F5: Feature\n", sdd) == []


# ===========================================================================
# Source-introspection helpers (Groups 4 & 6 structural tests)
# ===========================================================================

_VALIDATE_BLUEPRINT_SRC = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py"
_VALIDATE_SPEC_SRC = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py"
_GUARD_SRC = _SCRIPTS_DIR / "downstream_ref_guard.py"


def _find_function(path: Path, name: str) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name}() not found in {path.name}")


def _function_references_name(path: Path, func: str, target: str) -> bool:
    """True if `target` appears as a Name/Attribute inside func's body. AST-based, so
    comments and docstrings are excluded automatically."""
    node = _find_function(path, func)
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == target:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr == target:
            return True
    return False


def _string_constants_excluding_docstring(node: ast.AST) -> list[str]:
    body = list(node.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(getattr(body[0], "value", None), ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]  # drop the docstring
    out = []
    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                out.append(sub.value)
    return out


# ===========================================================================
# Group 4 — Allow-by-construction (R4)
# ===========================================================================

def test_tasks_md_filename_no_finding():
    _g, _bp, sdd = _policies()
    assert _scan("See tasks.md for details.\n", sdd) == []


def test_plan_filename_no_finding():
    _g, bp, _sdd = _policies()
    assert _scan("See PLAN for the feature breakdown.\n", bp) == []


def test_deferred_phase_name_no_finding():
    _g, _bp, sdd = _policies()
    assert _scan("Deferred -> tasks.md\n", sdd) == []


def test_bare_token_adjacent_to_filename_still_flagged():
    # The discriminating test (R4 AC#2): adjacency to the permitted filename must NOT
    # suppress a real bare token. The token is NOT backticked.
    _g, _bp, sdd = _policies()
    toks = _tokens(_scan("see T3 in tasks.md\n", sdd))
    assert "T3" in toks


def test_requirement_id_R_no_finding():
    _g, bp, sdd = _policies()
    assert _scan("R1 and ### R3: are requirement/risk IDs\n", sdd) == []
    assert _scan("R1 and ### R3: are requirement/risk IDs\n", bp) == []


def test_validate_tasks_not_wired():
    # Source-absence proxy (R2 AC#4 / R3 AC#4). Authoritative guarantee is the
    # behavioral test_validate_tasks_no_guard_finding (Group 9, T11).
    assert not _function_references_name(_VALIDATE_SPEC_SRC, "validate_tasks", "scan_for_downstream_refs")


def test_validate_plan_not_wired():
    assert not _function_references_name(_VALIDATE_BLUEPRINT_SRC, "validate_plan", "scan_for_downstream_refs")


# ===========================================================================
# Group 5 — Policy independence (R6)
# ===========================================================================

def test_custom_policy_heading_warn_only_true():
    g, _bp, _sdd = _policies()
    policy = g.PolicyConfig(letter="T", heading_warn_only=True, bare_warn_only=True,
                            troubleshooting_ref="ref", noun="task", downstream_artifact="03_tasks.md")
    findings = _scan("### T5: Setup\n", policy)
    assert len(findings) == 1 and findings[0].warn_only is True


def test_custom_policy_bare_warn_only_false():
    g, _bp, _sdd = _policies()
    policy = g.PolicyConfig(letter="T", heading_warn_only=False, bare_warn_only=False,
                            troubleshooting_ref="ref", noun="task", downstream_artifact="03_tasks.md")
    findings = _scan("bare T3 in prose\n", policy)
    assert len(findings) == 1 and findings[0].warn_only is False


def test_policy_independence_both_tiers():
    g, _bp, _sdd = _policies()
    for letter, heading_tok, bare in (("F", "### F3: Auth\n", "bare F2 here\n"),
                                      ("T", "### T3: Auth\n", "bare T2 here\n")):
        warn_head = g.PolicyConfig(letter=letter, heading_warn_only=True, bare_warn_only=True,
                                   troubleshooting_ref="r", noun="x", downstream_artifact="d")
        fail_bare = g.PolicyConfig(letter=letter, heading_warn_only=False, bare_warn_only=False,
                                   troubleshooting_ref="r", noun="x", downstream_artifact="d")
        assert _scan(heading_tok, warn_head)[0].warn_only is True
        assert _scan(bare, fail_bare)[0].warn_only is False


def test_no_hardcoded_severity_in_guard_source():
    # Supplementary structural check: no "FAIL"/"WARN" string literal among code STRING
    # tokens (tokenize excludes COMMENT tokens; the guard source also keeps the words out
    # of docstrings, so this stays clean without docstring-position logic).
    bad = []
    with open(_GUARD_SRC, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type == tokenize.STRING and ("FAIL" in tok.string or "WARN" in tok.string):
                bad.append(tok.string)
    assert bad == [], f"hard-coded severity literal(s) in guard source: {bad}"


# ===========================================================================
# Group 6 — Tier-symmetry / guard-ownership (R1)
# (the cross-validator import-identity test lives in T11, post-wiring)
# ===========================================================================

def test_pattern_constants_are_guard_owned():
    g = _load_guard()
    for const in ("BLUEPRINT_BARE_PATTERN", "BLUEPRINT_HEADING_PATTERN",
                  "SDD_BARE_PATTERN", "SDD_HEADING_PATTERN"):
        assert hasattr(g, const), f"{const} not owned by downstream_ref_guard"


def test_both_tiers_share_allow_construction_behaviour():
    # The same names-based allow (no F/T+digit in "See PLAN ...") yields zero findings
    # under both policies — one shared function, not two parallel implementations.
    _g, bp, sdd = _policies()
    assert _scan("See PLAN for the feature breakdown.\n", bp) == []
    assert _scan("See PLAN for the feature breakdown.\n", sdd) == []


def test_guard_imports_stdlib_only():
    tree = ast.parse(_GUARD_SRC.read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert mods <= {"re", "typing", "__future__"}, f"non-stdlib import(s): {mods}"


_WIRED_FUNCTIONS = [
    (_VALIDATE_BLUEPRINT_SRC, "validate_scope"),
    (_VALIDATE_BLUEPRINT_SRC, "validate_architecture"),
    (_VALIDATE_SPEC_SRC, "validate_spec"),
    (_VALIDATE_SPEC_SRC, "validate_design"),
]
_INLINE_MATCHER_SHAPES = ("F(\\d", "T(\\d", "\\bF(", "\\bT(")


def test_no_inline_downstream_matcher_in_wired_validators():
    # R1 AC#2: every F/T-token match in the wired upstream-validation paths routes
    # through the guard — no inline matcher reproduced in the four wired function bodies.
    # The module-level FEATURE_ID_PATTERN legitimately remains (used by validate_plan).
    for path, func in _WIRED_FUNCTIONS:
        node = _find_function(path, func)
        for s in _string_constants_excluding_docstring(node):
            for shape in _INLINE_MATCHER_SHAPES:
                assert shape not in s, f"{func}: inline downstream matcher {shape!r} in {s!r}"


# ===========================================================================
# Group 8 — Self-clean (R7 / smoke): this feature's own artifacts scan clean
# Triage note: a red here is a guard/stripper bug first — do NOT backtick a token in
# the already-approved 01_spec.md/02_design.md (that forces a re-approval cascade).
# ===========================================================================

_OWN_SPEC = _REPO_ROOT / "specs/no-downstream-identifier-references/01_spec.md"
_OWN_DESIGN = _REPO_ROOT / "specs/no-downstream-identifier-references/02_design.md"

# The Group-8/10 tests dogfood-scan this feature's OWN author-side artifacts under
# specs/, which is gitignored (`/specs/` in .gitignore) and therefore ABSENT in a
# clean CI checkout. Skip (don't fail) when the artifacts aren't present locally.
_SPECS_ABSENT_REASON = "author-side specs/ artifacts are gitignored, absent in a clean checkout (CI)"


def test_own_spec_scans_clean_at_blueprint_tier():
    if not _OWN_SPEC.exists():
        pytest.skip(_SPECS_ABSENT_REASON)
    _g, bp, _sdd = _policies()
    assert _scan(_OWN_SPEC.read_text(encoding="utf-8"), bp) == []


def test_own_spec_scans_clean_at_sdd_tier():
    if not _OWN_SPEC.exists():
        pytest.skip(_SPECS_ABSENT_REASON)
    _g, _bp, sdd = _policies()
    assert _scan(_OWN_SPEC.read_text(encoding="utf-8"), sdd) == []


def test_own_design_scans_clean_at_sdd_tier():
    if not _OWN_DESIGN.exists():
        pytest.skip(_SPECS_ABSENT_REASON)
    _g, _bp, sdd = _policies()
    assert _scan(_OWN_DESIGN.read_text(encoding="utf-8"), sdd) == []


# ===========================================================================
# Group 10 — Rollout regression (R7 AC#1): no existing in-repo upstream artifact
# gains a heading-FAIL. Bare-WARN findings are allowed (AD8).
# ===========================================================================

def test_existing_specs_no_new_heading_fail():
    g, _bp, sdd = _policies()
    scanned = sorted(_REPO_ROOT.glob("specs/*/01_spec.md")) + sorted(_REPO_ROOT.glob("specs/*/02_design.md"))
    if not scanned:
        pytest.skip(_SPECS_ABSENT_REASON)
    heading_hits = []
    for path in scanned:
        for f in g.scan_for_downstream_refs(path.read_text(encoding="utf-8"), path.name, sdd):
            if f.form == g.FORM_HEADING:
                heading_hits.append((str(path.relative_to(_REPO_ROOT)), f.token, f.line_no))
    assert heading_hits == [], f"existing artifact(s) would gain a heading-FAIL: {heading_hits}"


# ===========================================================================
# DEF-02 (optional) — fence-stripper semantic parity with cfc_parser
# The guard uses line-based fence detection (fails safe on an unterminated fence)
# while cfc_parser uses a single backreference regex; they intentionally differ in
# mechanism, so this asserts SEMANTIC parity (both exempt fenced content, neither
# exempts surrounding prose) rather than byte-identical offsets.
# ===========================================================================

def test_fenced_block_stripper_parity_with_cfc_parser():
    g = _load_guard()
    cfc = importlib.import_module("cfc_parser")
    snippet = "before T9 token\n```\nfenced T3 token\n```\nafter T8 token\n"
    guard_out = g._blank_fenced_blocks(snippet)
    cfc_out = cfc._strip_fenced_code_blocks(snippet)
    # Both strip the fenced token, both keep the surrounding prose tokens.
    assert "T3" not in guard_out and "T3" not in cfc_out
    assert "T9" in guard_out and "T9" in cfc_out
    assert "T8" in guard_out and "T8" in cfc_out


# ===========================================================================
# Group 9 — Validator-wiring behavioral (R2/R3 enforcement path), + the two
# post-wiring cross-cutting tests. Run the actual wired validators on synthetic
# fixtures. The BINDING assertion is on the specific guard-produced check (located by
# its check_name substring); global result.passed is secondary. Every wired function's
# only early-return before the guard call is `if content is None`, so a fixture with
# just the artifact file reaches the guard.
# ===========================================================================

_SDD_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "skills" / "spec-driven-dev" / "scripts"
_BP_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts"

# Guard check_name signatures (tier-specific); both forms contain the "<noun>-identifier" stem.
_SDD_HEADING_SIG = "downstream task-identifier heading"
_SDD_BARE_SIG = "bare downstream task-identifier"
_SDD_ANY_SIG = "downstream task-identifier"
_BP_HEADING_SIG = "downstream feature-identifier heading"
_BP_BARE_SIG = "bare downstream feature-identifier"
_BP_ANY_SIG = "downstream feature-identifier"


def _load_validate_spec():
    if str(_SDD_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SDD_SCRIPTS))
    if "validate_spec" in sys.modules:
        return importlib.reload(sys.modules["validate_spec"])
    return importlib.import_module("validate_spec")


def _load_validate_blueprint():
    if str(_BP_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_BP_SCRIPTS))
    if "validate_blueprint" in sys.modules:
        return importlib.reload(sys.modules["validate_blueprint"])
    return importlib.import_module("validate_blueprint")


def _guard_checks(result, substr):
    return [(n, s, d) for (n, s, d) in result.checks if substr in n]


def _write(d: Path, name: str, text: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")
    return d


_SPEC_BASE = "# Spec\n\n**PLAN feature identifier:** `n/a`\n\n## Objective\n\nbody text\n"
_DESIGN_BASE = "# Design\n\n## Goals and Non-Goals\n\nbody text\n"
_SCOPE_BASE = "# Scope\n\n## Problem Statement\n\nbody text\n"
_ARCH_BASE = "# Architecture\n\n## System Overview\n\nbody text\n"


def test_validate_spec_heading_blocks(tmp_path):
    vs = _load_validate_spec()
    d = _write(tmp_path / "feat-spec-h", "spec.md", _SPEC_BASE + "\n### T5: Setup\n")
    res = vs.validate_spec(d)
    hits = _guard_checks(res, _SDD_HEADING_SIG)
    assert len(hits) == 1 and hits[0][1] == "FAIL"
    assert res.passed is False
    # Non-vacuity: the same base WITHOUT the heading produces no guard heading check.
    d2 = _write(tmp_path / "feat-spec-clean", "spec.md", _SPEC_BASE)
    assert _guard_checks(vs.validate_spec(d2), _SDD_HEADING_SIG) == []


def test_validate_design_heading_blocks(tmp_path):
    vs = _load_validate_spec()
    d = _write(tmp_path / "feat-design-h", "design.md", _DESIGN_BASE + "\n### T5: Setup\n")
    res = vs.validate_design(d)
    hits = _guard_checks(res, _SDD_HEADING_SIG)
    assert len(hits) == 1 and hits[0][1] == "FAIL"
    assert res.passed is False


def test_validate_spec_bare_token_warns_not_blocks(tmp_path):
    vs = _load_validate_spec()
    d = _write(tmp_path / "feat-spec-b", "spec.md", _SPEC_BASE + "\nwe revisit T3 later\n")
    res = vs.validate_spec(d)
    warn = _guard_checks(res, _SDD_BARE_SIG)
    assert len(warn) == 1 and warn[0][1] == "WARN"          # binding: WARN present
    assert _guard_checks(res, _SDD_HEADING_SIG) == []        # binding: no guard FAIL


def test_validate_design_bare_token_warns_not_blocks(tmp_path):
    vs = _load_validate_spec()
    d = _write(tmp_path / "feat-design-b", "design.md", _DESIGN_BASE + "\nwe revisit T3 later\n")
    res = vs.validate_design(d)
    warn = _guard_checks(res, _SDD_BARE_SIG)
    assert len(warn) == 1 and warn[0][1] == "WARN"
    assert _guard_checks(res, _SDD_HEADING_SIG) == []


def test_validate_scope_heading_blocks(tmp_path):
    vb = _load_validate_blueprint()
    d = _write(tmp_path / "bp_scope_h" / "blueprint", "SCOPE.md", _SCOPE_BASE + "\n### F3: Auth\n")
    res = vb.validate_scope(d)
    hits = _guard_checks(res, _BP_HEADING_SIG)
    assert len(hits) == 1 and hits[0][1] == "FAIL"
    assert res.passed is False
    d2 = _write(tmp_path / "bp_scope_clean" / "blueprint", "SCOPE.md", _SCOPE_BASE)
    assert _guard_checks(vb.validate_scope(d2), _BP_HEADING_SIG) == []


def test_validate_scope_bare_token_warns_not_blocks(tmp_path):
    vb = _load_validate_blueprint()
    d = _write(tmp_path / "bp_scope_b" / "blueprint", "SCOPE.md", _SCOPE_BASE + "\nsee F2 elsewhere\n")
    res = vb.validate_scope(d)
    warn = _guard_checks(res, _BP_BARE_SIG)
    assert len(warn) == 1 and warn[0][1] == "WARN"
    assert _guard_checks(res, _BP_HEADING_SIG) == []


def test_validate_architecture_heading_blocks(tmp_path):
    vb = _load_validate_blueprint()
    d = _write(tmp_path / "bp_arch_h" / "blueprint", "ARCHITECTURE.md", _ARCH_BASE + "\n### F3: Auth\n")
    res = vb.validate_architecture(d)
    hits = _guard_checks(res, _BP_HEADING_SIG)
    assert len(hits) == 1 and hits[0][1] == "FAIL"
    assert res.passed is False


def test_validate_architecture_bare_token_warns_not_blocks(tmp_path):
    vb = _load_validate_blueprint()
    d = _write(tmp_path / "bp_arch_b" / "blueprint", "ARCHITECTURE.md", _ARCH_BASE + "\nsee F2 elsewhere\n")
    res = vb.validate_architecture(d)
    warn = _guard_checks(res, _BP_BARE_SIG)
    assert len(warn) == 1 and warn[0][1] == "WARN"
    assert _guard_checks(res, _BP_HEADING_SIG) == []


def test_validate_tasks_no_guard_finding(tmp_path):
    # tasks.md legitimately mints `### T<n>:` headings; the guard is NOT wired here.
    vs = _load_validate_spec()
    d = _write(tmp_path / "feat-tasks", "tasks.md",
               "# Tasks\n\n### - [x] T1: Done\n\nbody\n\n### T9: Later\n")
    res = vs.validate_tasks(d)
    assert _guard_checks(res, _SDD_ANY_SIG) == []


def test_validate_plan_no_guard_finding(tmp_path):
    # PLAN.md legitimately mints `### F<n>:` headings; the guard is NOT wired here.
    vb = _load_validate_blueprint()
    plan = ("# Plan\n\n## Feature Breakdown\n\n### F1: Alpha\n\nx\n\n### F2: Beta\n\nx\n\n"
            "### F3: Gamma\n\nx\n\n### F4: Delta\n\nx\n")
    d = _write(tmp_path / "bp_plan" / "blueprint", "PLAN.md", plan)
    res = vb.validate_plan(d)
    assert _guard_checks(res, _BP_ANY_SIG) == []


def test_both_validators_import_scan_function_from_guard():
    vs = _load_validate_spec()
    vb = _load_validate_blueprint()
    # Both validators reference the SAME scan function object, owned by the guard module.
    assert vs.scan_for_downstream_refs is vb.scan_for_downstream_refs
    assert vs.scan_for_downstream_refs.__module__ == "downstream_ref_guard"


def test_policy_troubleshooting_ref_resolves():
    vs = _load_validate_spec()
    vb = _load_validate_blueprint()
    phrase = "Downstream identifier in upstream artifact"
    assert phrase in vs.SDD_DOWNSTREAM_POLICY.troubleshooting_ref
    assert phrase in vb.BLUEPRINT_DOWNSTREAM_POLICY.troubleshooting_ref
    sdd_ts = (_REPO_ROOT / _TROUBLESHOOTING["sdd"]).read_text(encoding="utf-8")
    bp_ts = (_REPO_ROOT / _TROUBLESHOOTING["blueprint"]).read_text(encoding="utf-8")
    assert f"## {phrase}" in sdd_ts and f"## {phrase}" in bp_ts
