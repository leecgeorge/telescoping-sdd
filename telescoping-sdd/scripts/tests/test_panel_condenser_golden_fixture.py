"""Consumption-side golden fixture: a FIXED compact table → DM2 mechanical
projection → `### Latest pass detail` → `archive_pass.py` (UNCHANGED) tag/trigger
parity (T6).

This is a **characterization / parity oracle** over unchanged `archive_pass.py`:
it must pass on first authoring (there is no production-code red phase — the
"red" is the file not yet existing). A failure signals an accidental change to
the tag-parsing / halt-vote / strict-bar contract, or a drift between the fixture
and the documented DM2 projection formula.

Projection formula this fixture encodes — quoted verbatim from
`panel-review.md § The Loop` step 2 (DR2 drift-guard binds the two hand-authored
copies via `test_golden_fixture_projection_matches_documented_formula`):

    `Severity ← SEVERITY`; `Source ← SOURCE`; `Concern ← SCOPE + " " + CONCERN`
    for Phase 2/3 HIGH rows (else `Concern ← CONCERN`)

`Disposition` and `Notes` are deliberately NOT pinned (orchestrator judgment,
MED-5); `ROW`/`ANCHOR-REFS` are reconciliation-only and never projected on disk.

See specs/context-window-inflow-reduction/{02_design.md,03_tasks.md}
(design DM2 projection, AD8, DR2; R2 AC3, R4 AC3).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ARCHIVE_PASS = _REPO_ROOT / "telescoping-sdd" / "scripts" / "archive_pass.py"
_SDD_PANEL = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/panel-review.md"


# --- The FIXED compact table (the panel-condenser's DM2 return) -------------
# ROW | ANCHOR-REFS | SEVERITY | SOURCE | SCOPE | CONCERN | DISPOSITION-PROPOSAL | FIX-INSTRUCTION
_FIXTURE_ROWS = [
    # 3 [detail] HIGH rows (drive the Phase-3 strict-bar signal).
    dict(row="1", anchors="crit-H01", severity="[HIGH]", source="critic",
         scope="[detail]", concern="single-feature FQCN naming", disp="Addressed",
         fix="rename in T4"),
    dict(row="2", anchors="crit-H02", severity="[HIGH]", source="critic",
         scope="[detail]", concern="regex tuning inside one task", disp="Addressed",
         fix="tune in T5"),
    dict(row="3", anchors="crit-H03", severity="[HIGH]", source="critic",
         scope="[detail]", concern="off-by-one fixture variant", disp="Addressed",
         fix="enumerate in T6"),
    # 1 [upstream] HIGH row (auto-routes to a halt vote).
    dict(row="4", anchors="arch-H01", severity="[HIGH]", source="architect",
         scope="[upstream]", concern="spec omits partial-failure behavior",
         disp="Addressed", fix="escalate to spec"),
    # 1 [contract] HIGH MERGED row (multi ANCHOR-REFS / multi SOURCE).
    dict(row="5", anchors="dm-H01, sec-H02", severity="[HIGH]",
         source="delivery-manager, security-reviewer", scope="[contract]",
         concern="cross-task ordering + auth invariant", disp="Addressed",
         fix="pin in T8"),
    # 1 same-id DOWNGRADE-shaped row: an anchor id on a non-HIGH row.
    dict(row="6", anchors="crit-H01", severity="[MED]", source="critic",
         scope="", concern="downgraded restatement of the FQCN nit",
         disp="Addressed", fix="noted"),
]

_LATEST_HEADER = (
    "### Latest pass detail\n\n"
    "| Severity | Source | Concern | Disposition | Notes |\n"
    "|----------|--------|---------|-------------|-------|\n"
)


def _project(rows, *, phase: int) -> str:
    """Apply the DM2 mechanical projection to produce `### Latest pass detail`
    rows. Only Severity/Source/Concern are mechanical; Disposition/Notes are
    fixed 'orchestrator judgment' values (never copied from the proposal)."""
    out = []
    for r in rows:
        is_high = "[HIGH]" in r["severity"]
        if is_high and phase in (2, 3) and r["scope"]:
            concern = f'{r["scope"]} {r["concern"]}'
        else:
            concern = r["concern"]
        # Disposition/Notes: orchestrator judgment (fixed here, NOT the proposal).
        out.append(
            f'| {r["severity"]} | {r["source"]} | {concern} | Addressed | applied |'
        )
    return "\n".join(out) + "\n"


def _traj_row(pass_n, highs, addressed, notes):
    return (
        f"| {pass_n} | 2026-07-05 | {highs} | 0 | {addressed} | 0 | 0 | {notes} |\n"
    )


def _build_artifact(tmp_path, *, phase, prior_traj=""):
    artifact = tmp_path / "spec.md"
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        f"{prior_traj}"
        "\n"
        "### Sealed dispositions\n\n_None yet._\n\n"
        "### Deferred dispositions\n\n"
        "<!-- auto -->\n\n"
        + _LATEST_HEADER
        + _project(_FIXTURE_ROWS, phase=phase)
        + "\n## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    return artifact


def _run(args):
    return subprocess.run(
        [sys.executable, str(_ARCHIVE_PASS), *args],
        capture_output=True, text=True, check=False,
    )


def test_golden_fixture_phase2_tag_counts(tmp_path):
    """Phase 2: tag counts d3u1c1 stashed in Notes (3 detail, 1 upstream, 1 contract)."""
    art = _build_artifact(tmp_path, phase=2)
    proc = _run([str(art), "--phase", "2"])
    assert proc.returncode == 0, proc.stderr
    assert "tags=d3u1c1" in art.read_text(encoding="utf-8")


def test_golden_fixture_phase3_tag_counts(tmp_path):
    """Phase 3: identical tag counts d3u1c1 — tag parsing is phase-independent."""
    art = _build_artifact(tmp_path, phase=3)
    proc = _run([str(art), "--phase", "3"])
    assert proc.returncode == 0, proc.stderr
    assert "tags=d3u1c1" in art.read_text(encoding="utf-8")


def test_golden_fixture_upstream_fires_halt_vote(tmp_path):
    """The [upstream] row auto-routes to a halt vote (Phase 2/3)."""
    for phase in ("2", "3"):
        d = tmp_path / f"p{phase}"
        d.mkdir()
        art = _build_artifact(d, phase=int(phase))
        proc = _run([str(art), "--phase", phase])
        assert proc.returncode == 0, proc.stderr
        assert "halt vote" in art.read_text(encoding="utf-8"), phase


def test_golden_fixture_strict_bar_trigger_fires(tmp_path):
    """Phase 3: with a prior [detail]-heavy NORMAL pass, the strict-bar signal
    fires on the fixture's [detail] accumulation."""
    prior = _traj_row(pass_n=1, highs=5, addressed=3, notes="tags=d3u0c0")
    art = _build_artifact(tmp_path, phase=3, prior_traj=prior)
    proc = _run([str(art), "--phase", "3"])
    assert proc.returncode == 0, proc.stderr
    assert "STRICT-BAR-SIGNAL" in proc.stdout, proc.stdout
    assert "tagged [detail]" in proc.stdout


def test_golden_fixture_merged_and_downgrade_rows_project(tmp_path):
    """The merged row (multi ANCHOR-REFS/SOURCE) and the same-id downgrade row
    (an anchor on a [MED] row) both survive projection and archive cleanly."""
    art = _build_artifact(tmp_path, phase=3)
    proc = _run([str(art), "--phase", "3"])
    assert proc.returncode == 0, proc.stderr
    text = art.read_text(encoding="utf-8")
    # HIGHs = 5 (the [MED] downgrade row is not counted); merged SOURCE preserved
    # nowhere on-disk after archive (Latest is cleared), but the pass archived OK
    # and the trajectory row records 5 HIGHs.
    m = re.search(r"\|\s*1\s*\|[^\n]*", text)
    # The just-archived pass row carries HIGHs=5.
    assert re.search(r"\|\s*1\s*\|\s*2026[^|]*\|\s*5\s*\|", text), text


def _extract_loop_step2(content: str) -> str:
    section = re.search(r"(## The Loop\n.*?)(?=\n## )", content, re.DOTALL).group(1)
    m = re.search(
        r"(2\. \*\*Synthesize in-thread\*\*.*?)(?=\n3\. For each remaining concern)",
        section, re.DOTALL,
    )
    return m.group(1)


def test_golden_fixture_projection_matches_documented_formula():
    """DR2 drift guard: the documented DM2 projection formula in panel-review.md
    encodes the SAME three mechanical mappings the fixture applies. Asserts the
    semantic mappings (whitespace/backtick-normalized), NOT a brittle exact-line
    match and NOT a vacuous 'these words appear somewhere' check — a prose edit
    that changes a MAPPING (reorders SCOPE/CONCERN, swaps a source column) while
    the fixture is not updated in lockstep will fail this test."""
    block = _extract_loop_step2(_SDD_PANEL.read_text(encoding="utf-8"))
    norm = re.sub(r"\s+", "", block).replace("`", "")
    for token in ("Severity←SEVERITY", "Source←SOURCE", 'Concern←SCOPE+""+CONCERN'):
        assert token in norm, f"projection mapping token {token!r} not in documented formula"

    # Bind the fixture to the formula: a HIGH row projects Concern = SCOPE + " " + CONCERN.
    high = next(r for r in _FIXTURE_ROWS if "[HIGH]" in r["severity"] and r["scope"])
    projected = _project([high], phase=3).strip()
    assert f'{high["scope"]} {high["concern"]}' in projected
