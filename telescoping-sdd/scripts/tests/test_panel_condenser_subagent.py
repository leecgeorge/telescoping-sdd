"""Reference-prose + parity guard for the panel-condenser loop rewrite (T5).

Pins, in BOTH `panel-review.md` copies, the context-window-inflow-reduction
Milestone-A loop rewrite: the findings-to-disk panelist contract, the
`panel-condenser` dispatch + compact-table return, the per-anchor AD7
reconciliation + fallback, the DM2→`### Latest pass detail` projection formula,
the `## Concern tagging` proposal/confirm edit, the new `## Pass summary surface`
section (incl. the LOW-5 `[upstream]` scope-mismatch surfacing), and the
0-new-HIGH-but-non-empty-manifest reconciliation boundary. Also pins the R4
invariants (disposition vocabulary / Self-Check / Autonomy Boundary /
`### Latest pass detail` layout) present-unchanged, and byte-identity of the new
shared blocks across the two copies (asymmetries allow-listed).

Mirrors `test_panel_input_disk_read.py` / `test_write_inversion.py` (self-
contained; no shared-helper import). See specs/context-window-inflow-reduction/
{01_spec.md,02_design.md,03_tasks.md} (design C3, C4, AD6, AD7, AD10, AD11,
AD12, DM2, Q6; R1, R2, R4, R5).
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
SDD = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/panel-review.md"
PB = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/panel-review.md"
BOTH = [pytest.param(SDD, id="sdd"), pytest.param(PB, id="pb")]


# --- Frozen phrases (couple this guard to the T5 prose) --------------------
FINDINGS_TO_DISK_PHRASE = "return only a manifest"
FINDINGS_PATH_PHRASE = ".sdd/panel-findings/<findings_scope>/"
NO_INLINE_BODIES_PHRASE = "no prose bodies and no MED/LOW detail inline"
CLEAR_REENTRY_PHRASE = "clear the prior pass's findings within *this run's*"
CONDENSER_DISPATCH_PHRASE = "telescoping-sdd:panel-condenser"
COMPACT_TABLE_COLUMNS = (
    "ROW | ANCHOR-REFS | SEVERITY | SOURCE | SCOPE | CONCERN "
    "| DISPOSITION-PROPOSAL | FIX-INSTRUCTION"
)
RECONCILE_PHRASE = "Reconcile the returned table by identity, per anchor"
FALLBACK_PHRASE = "Fall back on failure"
GRAMMAR_HELPER_PHRASE = "compact_table.validate_compact_table"
PROJECTION_FORMULA = (
    '`Severity ← SEVERITY`; `Source ← SOURCE`; '
    '`Concern ← SCOPE + " " + CONCERN` for Phase 2/3 HIGH rows '
    '(else `Concern ← CONCERN`)'
)
CONCERN_PROPOSE_CONFIRM_PHRASE = "Condenser proposes, you confirm"
UPSTREAM_CONFIRM_PHRASE = "confirm any `[upstream]` tag semantically"
PASS_SUMMARY_HEADING = "## Pass summary surface"
SCOPE_MISMATCH_PHRASE = "scope mismatch"
ZERO_HIGH_BOUNDARY_PHRASE = "do not short-circuit on the trajectory HIGH count"

# R4 invariants (must remain present and unchanged).
DISPOSITION_VOCAB = ["Addressed", "Deferred", "Sealed", "Accepted as risk",
                     "User input needed", "Halt and re-scope"]
SELF_CHECK_HEADING = "## Synthesizer Self-Check"
AUTONOMY_HEADING = "## Autonomy Boundary"
LATEST_DETAIL_HEADER = "| Severity | Source | Concern | Disposition | Notes |"


# --- Section-scoped extraction ---------------------------------------------
class SectionMissingError(AssertionError):
    def __init__(self, path: Path, target: str) -> None:
        super().__init__(f"{path}: expected section or block not found: {target!r}")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_section(content: str, heading: str, path: Path) -> str:
    pattern = re.compile(rf"({re.escape(heading)}\n.*?)(?=\n## |\Z)", re.DOTALL)
    m = pattern.search(content)
    if not m:
        raise SectionMissingError(path, heading)
    return m.group(1)


def _extract_loop_step2(content: str, path: Path) -> str:
    """Step 2 of '## The Loop' — condenser dispatch + reconcile + projection."""
    section = _extract_section(content, "## The Loop", path)
    pattern = re.compile(
        r"(2\. \*\*Synthesize in-thread\*\*.*?)"
        r"(?=\n3\. For each remaining concern)",
        re.DOTALL,
    )
    m = pattern.search(section)
    if not m:
        raise SectionMissingError(path, "step 2 of ## The Loop")
    return m.group(1)


# --- Presence: findings-to-disk contract -----------------------------------
@pytest.mark.parametrize("path", BOTH)
def test_findings_to_disk_contract_present_both_copies(path: Path) -> None:
    section = _extract_section(_read(path), "## The Loop", path)
    assert FINDINGS_TO_DISK_PHRASE in section, path
    assert FINDINGS_PATH_PHRASE in section, path
    assert NO_INLINE_BODIES_PHRASE in section, path


@pytest.mark.parametrize("path", BOTH)
def test_prior_pass_findings_cleared_at_reentry(path: Path) -> None:
    section = _extract_section(_read(path), "## The Loop", path)
    assert CLEAR_REENTRY_PHRASE in section, path


@pytest.mark.parametrize("path", BOTH)
def test_condenser_dispatch_and_compact_table_return_present(path: Path) -> None:
    block = _extract_loop_step2(_read(path), path)
    assert CONDENSER_DISPATCH_PHRASE in block, path
    assert COMPACT_TABLE_COLUMNS in block, path


@pytest.mark.parametrize("path", BOTH)
def test_per_anchor_reconciliation_and_fallback_present(path: Path) -> None:
    block = _extract_loop_step2(_read(path), path)
    assert RECONCILE_PHRASE in block, path
    assert FALLBACK_PHRASE in block, path
    assert GRAMMAR_HELPER_PHRASE in block, path


@pytest.mark.parametrize("path", BOTH)
def test_dm2_projection_formula_present_verbatim(path: Path) -> None:
    block = _extract_loop_step2(_read(path), path)
    assert PROJECTION_FORMULA in block, (
        f"{path}: DM2 projection formula not present verbatim in Loop step 2"
    )


@pytest.mark.parametrize("path", BOTH)
def test_concern_tagging_proposal_confirm_edit_present(path: Path) -> None:
    section = _extract_section(_read(path), "## Concern tagging (Phase 2 and 3)", path)
    assert CONCERN_PROPOSE_CONFIRM_PHRASE in section, path
    assert UPSTREAM_CONFIRM_PHRASE in section, path


@pytest.mark.parametrize("path", BOTH)
def test_pass_summary_surface_present(path: Path) -> None:
    section = _extract_section(_read(path), PASS_SUMMARY_HEADING, path)
    assert section.strip(), f"{path}: '{PASS_SUMMARY_HEADING}' empty/absent"


@pytest.mark.parametrize("path", BOTH)
def test_upstream_hint_vs_proposed_mismatch_surfaced(path: Path) -> None:
    """LOW-5: a distinct assertion that the pass-summary block surfaces a
    scope_hint-vs-proposed-SCOPE mismatch (not folded into the general
    pass-summary presence check)."""
    section = _extract_section(_read(path), PASS_SUMMARY_HEADING, path)
    assert SCOPE_MISMATCH_PHRASE in section, path
    assert "scope_hint" in section, path


@pytest.mark.parametrize("path", BOTH)
def test_zero_new_high_nonempty_manifest_reconcile_covered(path: Path) -> None:
    block = _extract_loop_step2(_read(path), path)
    assert ZERO_HIGH_BOUNDARY_PHRASE in block, path


@pytest.mark.parametrize("path", BOTH)
def test_panel_review_r4_invariants_unchanged(path: Path) -> None:
    content = _read(path)
    for label in DISPOSITION_VOCAB:
        assert label in content, f"{path}: disposition vocabulary '{label}' missing"
    assert SELF_CHECK_HEADING in content, path
    assert AUTONOMY_HEADING in content, path
    assert LATEST_DETAIL_HEADER in content, path


# --- Parity: new shared blocks byte-identical across copies -----------------
def _assert_byte_identical(block_pb: str, block_sdd: str, label: str) -> None:
    if block_pb != block_sdd:
        diff = "".join(
            difflib.unified_diff(
                block_pb.splitlines(keepends=True),
                block_sdd.splitlines(keepends=True),
                fromfile=str(PB),
                tofile=str(SDD),
            )
        )
        pytest.fail(f"{label} not byte-identical across copies:\n{diff}")


def test_shared_loop_blocks_byte_identical_across_copies() -> None:
    """R5: the new shared blocks (Loop step 2, Pass summary surface) are
    byte-identical across both copies; documented asymmetries live elsewhere."""
    _assert_byte_identical(
        _extract_loop_step2(_read(PB), PB),
        _extract_loop_step2(_read(SDD), SDD),
        "Loop step 2 (condenser dispatch + reconcile + projection)",
    )
    _assert_byte_identical(
        _extract_section(_read(PB), PASS_SUMMARY_HEADING, PB),
        _extract_section(_read(SDD), PASS_SUMMARY_HEADING, SDD),
        "## Pass summary surface",
    )


# --- Unit C (T2): condenser fail-closed contract + body grammar ------------
# Design CP1, AD1, AD2, [SEAL-11]; spec R1, R3. Guards the agent body itself.
CONDENSER = _REPO_ROOT / "telescoping-sdd/agents/panel-condenser.md"
FAIL_CLOSED_HEADING = "## Fail closed on an unusable input"
OUTPUT_HEADING = "## Output: the compact table (exact headers, in order)"
REFUSAL_PREFIX = "CONDENSER REFUSED"
REFUSAL_REASONS = ("no such file", "unreadable", "no ## Machine findings section")
# AD2's exact wire form, as a regex.
_REASON_ALT = "|".join(re.escape(r) for r in REFUSAL_REASONS)
AD2_GRAMMAR = re.compile(
    r"^CONDENSER REFUSED — cannot read findings file\(s\): "
    rf"\S.*? \((?:{_REASON_ALT})\)"
    rf"(?:; \S.*? \((?:{_REASON_ALT})\))*"
    r"\. No table returned; \d+ paths given, \d+ readable\.$"
)


def _condenser() -> str:
    return _read(CONDENSER)


def _fail_closed_section() -> str:
    return _extract_section(_condenser(), FAIL_CLOSED_HEADING, CONDENSER)


def _what_to_do_step(n: int) -> str:
    section = _extract_section(_condenser(), "## What to do", CONDENSER)
    m = re.search(rf"^{n}\. .*$", section, re.MULTILINE)
    if not m:
        raise SectionMissingError(CONDENSER, f"## What to do step {n}")
    return m.group(0)


def _grammar_bullet(label: str) -> str:
    m = re.search(rf"^- \*\*{re.escape(label)}\*\* .*$", _condenser(), re.MULTILINE)
    if not m:
        raise SectionMissingError(CONDENSER, f"grammar bullet {label}")
    return m.group(0)


def test_condenser_has_fail_closed_section() -> None:
    content = _condenser()
    assert FAIL_CLOSED_HEADING in content
    assert content.index("## What to do") < content.index(FAIL_CLOSED_HEADING)
    assert content.index(FAIL_CLOSED_HEADING) < content.index(OUTPUT_HEADING)


def test_condenser_step1_points_to_fail_closed_section() -> None:
    step1 = _what_to_do_step(1)
    assert "`" + FAIL_CLOSED_HEADING + "`" in step1
    assert "Before merging" in step1


def test_condenser_refusal_form_and_reasons_present() -> None:
    section = _fail_closed_section()
    assert REFUSAL_PREFIX in section
    for reason in REFUSAL_REASONS:
        assert reason in section, reason


def test_condenser_refusal_fires_on_any_one_path() -> None:
    section = _fail_closed_section()
    assert "any one" in section
    assert "hard error" in section
    assert "readable subset" in section  # "do not proceed on the readable subset"


def test_condenser_quiet_panelist_file_is_valid() -> None:
    section = _fail_closed_section()
    assert "quiet panelist" in section
    assert "no rows" in section
    assert "valid" in section


def test_condenser_step5_carves_out_refusal() -> None:
    step5 = _what_to_do_step(5)
    assert "except" in step5
    assert "`" + FAIL_CLOSED_HEADING + "`" in step5


def test_condenser_boundaries_permit_refusal_line() -> None:
    section = _extract_section(
        _condenser(), "## Boundaries (what you must NOT do)", CONDENSER
    )
    bullets = [ln for ln in section.splitlines() if ln.startswith("- ")]
    assert any(
        "refusal line" in b and FAIL_CLOSED_HEADING in b for b in bullets
    ), bullets


def test_condenser_source_bullet_requires_every_row() -> None:
    bullet = _grammar_bullet("SOURCE")
    assert "non-empty on every row" in bullet
    assert "non-empty on every HIGH row" not in bullet


def test_condenser_source_bullet_keeps_merged_row_clause() -> None:
    assert "a merged row names every contributing panelist" in _grammar_bullet(
        "SOURCE"
    )


def test_condenser_anchor_refs_bullet_stays_high_only() -> None:
    assert "non-empty on every HIGH row" in _grammar_bullet("ANCHOR-REFS")


def test_condenser_refusal_example_matches_ad2_grammar() -> None:
    """[SEAL-11]: the worked example conforms to AD2's grammar."""
    spans = re.findall(r"`(CONDENSER REFUSED[^`]*)`", _fail_closed_section())
    examples = [s for s in spans if "<reason>" not in s]  # skip the template
    assert examples, "no concrete worked refusal example in the section"
    for ex in examples:
        assert AD2_GRAMMAR.match(ex), ex
    # The grammar itself rejects a non-conforming line (guards the regex).
    assert not AD2_GRAMMAR.match("CONDENSER REFUSED — something went wrong.")


# --- Unit C (T3): step-2 census sub-step + refusal routing (R1, R11) -------
import shutil  # noqa: E402
import subprocess  # noqa: E402
import textwrap  # noqa: E402

CENSUS_PHRASES = (
    "Census sub-step",
    "NO-SECTION",
    "shortfall",
    "excess",
    "CONDENSER REFUSED",
    "set -- '",
    'for f in "$@"',
)


@pytest.mark.parametrize("path", BOTH)
def test_step2_census_substep_present(path: Path) -> None:
    block = _extract_loop_step2(_read(path), path)
    for phrase in CENSUS_PHRASES:
        assert phrase in block, (path, phrase)
    # [SEAL-06]: a census failure has its own routing clause, not a slot in
    # the returned-table *structurally* off parenthetical.
    m = re.search(r"\*structurally\* off \(([^)]*)\)", block)
    assert m, path
    assert "census failure" not in m.group(1), (path, m.group(1))
    assert "census discrepancy" in m.group(1), (path, m.group(1))
    assert "records a census failure" in block, path
    assert "CONDENSER REFUSED" in m.group(1), (path, m.group(1))
    assert "without dispatching the condenser" in block, path
    # [SEAL-18]: the census is moot once the manifest check already fell back.
    assert "moot" in block, path


@pytest.mark.parametrize("path", BOTH)
def test_pass_summary_names_refusal_and_census(path: Path) -> None:
    section = _extract_section(_read(path), PASS_SUMMARY_HEADING, path)
    bullet = next(
        ln for ln in section.splitlines() if "degraded-mode disclosure" in ln
    )
    assert "CONDENSER REFUSED" in bullet, path
    assert "census" in bullet, path


def _census_fence(path: Path) -> str:
    block = _extract_loop_step2(_read(path), path)
    start = block.index("Census sub-step")
    m = re.search(r"\n( +)```bash\n(.*?)\n\1```", block[start:], re.DOTALL)
    assert m, f"{path}: census fence not found"
    for line in m.group(2).splitlines():
        assert line.startswith("   "), (path, line)  # every fence line indented ≥3
    return textwrap.dedent(m.group(2))


def _sq(p: str) -> str:
    """The doctrine's own quoting rule: single quotes, ' written as '\\'' ."""
    return "'" + p.replace("'", "'\\''") + "'"


def _run_census(path: Path, files: list) -> dict:
    if shutil.which("bash") is None or shutil.which("awk") is None:
        pytest.skip("bash/awk not available")
    script = _census_fence(path)
    for k, f in enumerate(files, start=1):
        placeholder = f"'<findings-path-{k}>'"
        assert placeholder in script, (path, placeholder)
        script = script.replace(placeholder, _sq(str(f)))
    out = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=False
    ).stdout
    # Parse: locate each known "<path> " prefix in order.
    prefixes = [str(f) + " " for f in files]
    positions = []
    cursor = 0
    for p in prefixes:
        i = out.index(p, cursor)
        positions.append(i)
        cursor = i + len(p)
    assert positions[0] == 0, f"text precedes the first prefix: {out!r}"
    result = {}
    for k, (p, i) in enumerate(zip(prefixes, positions)):
        end = positions[k + 1] if k + 1 < len(positions) else len(out)
        result[p[:-1]] = out[i + len(p):end].strip()
    return result


_MF_TWO_WITH_REGRESSION = (
    "# findings\n\n## Machine findings\n\n"
    "- [HIGH] one — why\n"
    "- [HIGH] [REGRESSION] two — why\n\n"
    "## Assessment (human)\n\n- [HIGH] prose bullet\n- [HIGH] another\n"
)
_MF_QUIET = "# findings\n\n## Machine findings\n\n## Assessment (human)\n\nquiet\n"
_MF_THREE = (
    "## Machine findings\n- [HIGH] a — r\n- [MED] b — r\n- [LOW] c — r\n"
)
_NO_SECTION = "# findings\n\n## Assessment (human)\n\n- [HIGH] prose only\n"


def _awkward_dir(tmp_path: Path) -> Path:
    d = tmp_path / "dir with $HOME and 'quote'"
    d.mkdir()
    return d


@pytest.mark.parametrize("path", BOTH)
def test_census_command_run_a_present_files_exact_mapping(
    path: Path, tmp_path: Path
) -> None:
    d = _awkward_dir(tmp_path)
    f1, f2, f3 = d / "a-p1-x.md", d / "a-p1-y.md", d / "a-p1-z.md"
    f1.write_text(_MF_TWO_WITH_REGRESSION)
    f2.write_text(_MF_QUIET)
    f3.write_text(_MF_THREE)
    got = _run_census(path, [f1, f2, f3])
    assert got == {str(f1): "2", str(f2): "0", str(f3): "3"}, got


@pytest.mark.parametrize("path", BOTH)
def test_census_command_run_b_failures_exact_mapping(
    path: Path, tmp_path: Path
) -> None:
    d = _awkward_dir(tmp_path)
    f1, f2, f3 = d / "b-p1-x.md", d / "b-p1-missing.md", d / "b-p1-z.md"
    f1.write_text(_MF_THREE)
    f3.write_text(_NO_SECTION)
    got = _run_census(path, [f1, f2, f3])
    assert got[str(f1)] == "3", got
    # [SEAL-27]: the one two-valued entry — never a digit string.
    assert got[str(f2)] in ("", "NO-SECTION"), got
    assert got[str(f3)] == "NO-SECTION", got
    assert set(got) == {str(f1), str(f2), str(f3)}, got


# --- Unit C (T10): --panel-roster, panel= token and panel-log doctrine -----
SECTION_FORMAT_HEADING = "## Panel Review section format"
PHASE3_ROSTER_FLAG = "--panel-roster delivery-manager,critic,simplifier"


def _digest_item4(content: str, path: Path) -> str:
    section = _extract_section(content, "## Minimum to run the NORMAL loop", path)
    m = re.search(r"^4\. .*$", section, re.MULTILINE)
    if not m:
        raise SectionMissingError(path, "digest item 4")
    return m.group(0)


def _loop_step6(content: str, path: Path) -> str:
    section = _extract_section(content, "## The Loop", path)
    m = re.search(r"(6\. Run `python.*?)(?=\n7\. )", section, re.DOTALL)
    if not m:
        raise SectionMissingError(path, "step 6 of ## The Loop")
    return m.group(1)


def _section_format(content: str, path: Path) -> str:
    """`## Panel Review section format` up to `## Concern tagging`: the section
    holds a fenced `## Panel Review` example, so `_extract_section`'s next-`## `
    bound would stop inside it."""
    start = content.find("\n" + SECTION_FORMAT_HEADING + "\n")
    end = content.find("\n## Concern tagging (Phase 2 and 3)", start + 1)
    if start < 0 or end < 0:
        raise SectionMissingError(path, SECTION_FORMAT_HEADING)
    return content[start + 1:end]


def _panel_token_paragraph(content: str, path: Path) -> str:
    section = _section_format(content, path)
    m = re.search(r"^\*\*`panel=` token\.\*\*.*?(?=\n\n)", section, re.MULTILINE | re.DOTALL)
    if not m:
        raise SectionMissingError(path, "panel= token paragraph")
    return m.group(0)


@pytest.mark.parametrize("path", BOTH)
def test_digest_item4_names_panel_roster(path: Path) -> None:
    item = _digest_item4(_read(path), path)
    assert "--panel-roster <names>" in item, path
    assert "## Panelists per phase" in item, path
    assert "telescoping-sdd:" in item, path  # the prefix-stripping gloss


@pytest.mark.parametrize("path", BOTH)
def test_step6_names_panel_roster_and_points_to_token(path: Path) -> None:
    step = _loop_step6(_read(path), path)
    assert "--panel-roster <names>" in step, path
    assert "**Trajectory**" in step and "panel=" in step, path
    assert "Omitting the flag stamps no token" in step, path
    assert "digest item 4" in step, path


@pytest.mark.parametrize("path", BOTH)
def test_terminal_invocation_carries_phase3_roster(path: Path) -> None:
    step = _loop_step6(_read(path), path)
    term = next(ln for ln in step.splitlines() if "**Terminal-archive invocation.**" in ln)
    assert PHASE3_ROSTER_FLAG in term, path


@pytest.mark.parametrize("path", BOTH)
def test_section_format_documents_panel_token(path: Path) -> None:
    para = _panel_token_paragraph(_read(path), path)
    assert "panel=H.M.L" in para, path
    assert "data-row content" in para, path
    assert "re-pad" in para, path
    assert "## Panelists per phase" in para, path  # positional decode


@pytest.mark.parametrize("path", BOTH)
def test_section_format_panel_log_gitignore_instruction(path: Path) -> None:
    section = _section_format(_read(path), path)
    assert "**Panel log (`.sdd/panel-log.jsonl`).**" in section, path
    assert "`/.sdd/panel-log.jsonl`" in section, path
    assert "One-time repository setup" in section, path


def test_t10_doctrine_blocks_byte_identical_across_copies() -> None:
    _assert_byte_identical(
        _panel_token_paragraph(_read(PB), PB),
        _panel_token_paragraph(_read(SDD), SDD),
        "panel= token paragraph",
    )
