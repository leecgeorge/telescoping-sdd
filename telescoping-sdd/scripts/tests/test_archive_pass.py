"""Behavior tests for `archive_pass.py`.

Locks in current behavior to catch regressions in any future edit to
archive_pass.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ARCHIVE_PASS = _REPO_ROOT / "telescoping-sdd" / "scripts" / "archive_pass.py"


def _run_archive_pass(args: list[str]) -> subprocess.CompletedProcess[str]:
    # Default to --phase 1 for tests that don't care about phase-dependent
    # behavior. Tests targeting Phase 2/3 paths pass --phase explicitly.
    if "--phase" not in args and "--help" not in args:
        args = [*args, "--phase", "1"]
    return subprocess.run(
        [sys.executable, str(_ARCHIVE_PASS), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_archive_pass_lives_at_private_scripts():
    assert _ARCHIVE_PASS.is_file(), (
        f"archive_pass.py missing at expected new home {_ARCHIVE_PASS}"
    )
    # And the old locations are gone.
    assert not (
        _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts"
        / "archive_pass.py"
    ).exists(), "Old project-blueprint copy should have been deleted"
    assert not (
        _REPO_ROOT / "telescoping-sdd" / "skills" / "spec-driven-dev" / "scripts"
        / "archive_pass.py"
    ).exists(), "Old spec-driven-dev copy should have been deleted"


def test_archive_pass_help_smoke():
    """Smoke test: --help is the safest invocation that exercises argparse."""
    proc = _run_archive_pass(["--help"])
    assert proc.returncode == 0, proc.stderr
    assert "archive_pass.py" in proc.stdout
    assert "panel-review" in proc.stdout.lower()


def test_archive_pass_check_on_clean_artifact(tmp_path):
    """Behavior preservation: --check on an artifact with an empty Latest
    section is a no-op (exit 0, no edit). If this regresses, archive_pass.py
    has drifted from its pre-move behavior.
    """
    artifact = tmp_path / "spec.md"
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "\n"
        "### Sealed dispositions\n\n"
        "_None yet._\n\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    proc = _run_archive_pass([str(artifact), "--check"])
    # An empty Latest is a no-op — exit 0. If --check ever exits non-zero on
    # an empty Latest, archive_pass.py has changed semantics.
    assert proc.returncode == 0, (
        f"--check on empty Latest exited {proc.returncode}: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


def _artifact_with_latest(tmp_path, latest_rows: str) -> Path:
    artifact = tmp_path / "spec.md"
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "\n"
        "### Sealed dispositions\n\n"
        "_None yet._\n\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        f"{latest_rows}"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    return artifact


def test_strict_bar_stamps_trajectory_notes(tmp_path):
    """--strict-bar stamps the Notes column; a zero-HIGH pass is marked converged."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | pragmatist | minor thing | Deferred → PLAN.md | later |\n",
    )
    proc = _run_archive_pass([str(artifact), "--strict-bar"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "strict-bar pass; converged (0 HIGH)" in text


def test_normal_pass_marks_convergence(tmp_path):
    """A NORMAL pass with zero HIGH concerns gets 'converged (0 HIGH)' in Notes."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | pragmatist | minor thing | Addressed | fixed |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "converged (0 HIGH)" in text


def test_normal_pass_with_highs_not_marked_converged(tmp_path):
    """A NORMAL pass with HIGH concerns is NOT marked as converged."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [HIGH] | devils-advocate | real concern | Addressed | fixed in §2 |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "converged" not in text


def test_cross_check_with_zero_highs_also_marks_convergence(tmp_path):
    """A --cross-check pass with zero HIGH concerns is marked converged too."""
    artifact = _artifact_with_latest(tmp_path, "")
    proc = _run_archive_pass([str(artifact), "--cross-check"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "cross-check pass (excluded from cap); converged (0 HIGH)" in text


def test_cross_check_stamped_and_records_empty_latest(tmp_path):
    """--cross-check stamps the Notes column and still records a row when
    Latest pass detail is empty (a clean cross-check produces no concerns)."""
    artifact = _artifact_with_latest(tmp_path, "")
    proc = _run_archive_pass([str(artifact), "--cross-check"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "cross-check pass (excluded from cap)" in text
    # An empty Latest with a mode flag still appends a trajectory row.
    assert "| 1 " in text or "| 1  " in text


def test_cross_check_processes_non_empty_latest(tmp_path):
    """--cross-check on a non-empty Latest processes the rows like a normal
    archive (HIGH count parsed, Latest cleared) and additionally stamps the
    Notes column with the cross-check tag."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [HIGH] | devils-advocate | real concern | Addressed | fixed in §2 |\n",
    )
    proc = _run_archive_pass([str(artifact), "--cross-check"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # Notes column stamped.
    assert "cross-check pass (excluded from cap)" in text
    # Row processed like a normal archive: the HIGH was counted.
    assert "| 1 " in text or "| 1  " in text  # Pass number
    # Latest pass detail was cleared (the concern row is gone).
    assert "real concern" not in text


def test_mode_flags_are_mutually_exclusive(tmp_path):
    """--skip, --strict-bar, and --cross-check cannot be combined."""
    artifact = _artifact_with_latest(tmp_path, "")
    proc = _run_archive_pass([str(artifact), "--skip", "x", "--strict-bar"])
    assert proc.returncode == 1, (
        f"expected exit 1 for conflicting mode flags, got {proc.returncode}: "
        f"stderr={proc.stderr!r}"
    )
    assert "mutually exclusive" in proc.stderr


# --- Strict-bar trigger detection -----------------------------------------


def _traj_row(pass_n, highs, addressed=0, deferred=0, sealed=0, notes="—"):
    return {
        "Pass": str(pass_n), "Date": "2026-05-15",
        "HIGHs": str(highs), "Regressions": "0",
        "Addressed": str(addressed), "Deferred": str(deferred),
        "Sealed": str(sealed), "Notes": notes,
    }


def _artifact_with_trajectory(tmp_path, traj_rows, latest_rows=""):
    """Artifact with pre-baked trajectory rows plus an optional Latest pass detail."""
    body = ""
    for r in traj_rows:
        body += (
            f"| {r['Pass']} | {r['Date']} | {r['HIGHs']} | {r['Regressions']} | "
            f"{r['Addressed']} | {r['Deferred']} | {r['Sealed']} | {r['Notes']} |\n"
        )
    artifact = tmp_path / "spec.md"
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        f"{body}"
        "\n"
        "### Sealed dispositions\n\n"
        "_None yet._\n\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        f"{latest_rows}"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    return artifact


def _three_deferred_highs():
    return (
        "| [HIGH] | critic | concern A | Deferred → PLAN.md | later |\n"
        "| [HIGH] | pragmatist | concern B | Deferred → PLAN.md | later |\n"
        "| [HIGH] | devils-advocate | concern C | Deferred → PLAN.md | later |\n"
    )


def test_strict_bar_signal_fires_on_flat_high_with_deferred(tmp_path):
    """Flat HIGH-count + >50% deferred should fire the advisory."""
    artifact = _artifact_with_trajectory(
        tmp_path,
        [_traj_row(pass_n=1, highs=3, deferred=3)],
        latest_rows=_three_deferred_highs(),
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    assert "STRICT-BAR-SIGNAL" in proc.stdout, (
        f"expected advisory on stdout, got stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


def test_strict_bar_signal_does_not_fire_on_dropping_high(tmp_path):
    """HIGH dropping by 2+ across passes is genuine convergence — must not fire."""
    artifact = _artifact_with_trajectory(
        tmp_path,
        [_traj_row(pass_n=1, highs=5, deferred=5)],
        latest_rows=(
            "| [HIGH] | critic | concern A | Deferred → PLAN.md | later |\n"
            "| [HIGH] | pragmatist | concern B | Deferred → PLAN.md | later |\n"
        ),
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    assert "STRICT-BAR-SIGNAL" not in proc.stdout, (
        f"advisory should NOT fire on -3 HIGH delta; got stdout={proc.stdout!r}"
    )


def test_strict_bar_signal_does_not_fire_when_mostly_addressed(tmp_path):
    """Flat HIGH-count but mostly Addressed (not Deferred) — panel is doing real
    work, not spinning. Must not fire."""
    artifact = _artifact_with_trajectory(
        tmp_path,
        [_traj_row(pass_n=1, highs=3, addressed=3)],
        latest_rows=(
            "| [HIGH] | critic | concern A | Addressed | fixed in §2 |\n"
            "| [HIGH] | pragmatist | concern B | Addressed | fixed in §3 |\n"
            "| [HIGH] | devils-advocate | concern C | Addressed | fixed in §4 |\n"
        ),
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    assert "STRICT-BAR-SIGNAL" not in proc.stdout


def test_strict_bar_signal_does_not_fire_with_only_one_prior_pass(tmp_path):
    """First pass alone is insufficient signal — need two NORMAL passes."""
    artifact = _artifact_with_trajectory(
        tmp_path, [], latest_rows=_three_deferred_highs(),
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    assert "STRICT-BAR-SIGNAL" not in proc.stdout


def test_strict_bar_signal_suppressed_when_current_pass_is_strict_bar(tmp_path):
    """A --strict-bar pass must not emit the advisory even if conditions match —
    we only switch into strict-bar from NORMAL."""
    artifact = _artifact_with_trajectory(
        tmp_path,
        [_traj_row(pass_n=1, highs=3, deferred=3)],
        latest_rows=_three_deferred_highs(),
    )
    proc = _run_archive_pass([str(artifact), "--strict-bar"])
    assert proc.returncode == 0, proc.stderr
    assert "STRICT-BAR-SIGNAL" not in proc.stdout


def test_strict_bar_signal_steps_over_intervening_strict_bar_rows(tmp_path):
    """A strict-bar pass in history shouldn't be the 'previous' reference point;
    the detector steps back to the last NORMAL row."""
    artifact = _artifact_with_trajectory(
        tmp_path,
        [
            _traj_row(pass_n=1, highs=3, deferred=3),
            _traj_row(pass_n=2, highs=2, deferred=2, notes="strict-bar pass"),
        ],
        latest_rows=_three_deferred_highs(),
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    # Pass 1 (HIGHs=3, deferred) vs new pass (HIGHs=3, deferred): flat + deferred → fire.
    assert "STRICT-BAR-SIGNAL" in proc.stdout, (
        f"detector should step over the strict-bar row; "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


# --- Phase argument required ----------------------------------------------


def test_phase_argument_is_required(tmp_path):
    """--phase is a required argument; invoking without it must error."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | pragmatist | minor | Addressed | fixed |\n",
    )
    # Bypass the helper's default --phase injection by calling subprocess directly.
    proc = subprocess.run(
        [sys.executable, str(_ARCHIVE_PASS), str(artifact)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode != 0
    assert "--phase" in proc.stderr


# --- Phase-dependent halt-vote routing for [upstream] tag -----------------


def test_phase_2_upstream_tag_auto_routes_to_halt_vote(tmp_path):
    """In Phase 2, a row tagged [upstream] counts as a halt vote alongside
    explicit 'Halt and re-scope' dispositions — per blueprint-strict.md."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [HIGH] | architect | [upstream] SCOPE doesn't commit goal X | "
        "Addressed | fixed in §2 |\n",
    )
    proc = _run_archive_pass([str(artifact), "--phase", "2"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # The [upstream] row got auto-routed to halt votes; Notes reflects it.
    assert "halt vote" in text


def test_phase_3_upstream_tag_auto_routes_to_halt_vote(tmp_path):
    """Same as Phase 2 — Phase 3 also routes [upstream] tags to halt votes."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [HIGH] | critic | [upstream] ARCH doesn't include component Y | "
        "Addressed | fixed in §3 |\n",
    )
    proc = _run_archive_pass([str(artifact), "--phase", "3"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "halt vote" in text


def test_phase_1_upstream_tag_does_not_auto_route(tmp_path):
    """Phase 1 has no upstream artifact, so [upstream] tags do NOT auto-route
    to halt votes (they're just normal rows with an unusual prefix)."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [HIGH] | pragmatist | [upstream] unusual but no upstream exists | "
        "Addressed | fixed |\n",
    )
    proc = _run_archive_pass([str(artifact), "--phase", "1"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # No halt-vote routing in Phase 1.
    assert "halt vote" not in text


# --- Tag-summary stashing in Notes (Phase 2 and 3 only) -------------------


def test_phase_2_stashes_tag_summary_in_notes(tmp_path):
    """Phase 2 archive stashes a `tags=dXuYcZ` substring in the Notes column
    so the strict-bar detector can read tag counts across passes."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [HIGH] | architect | [contract] cross-feature port | Addressed | x |\n"
        "| [HIGH] | testability | [contract] test scaffold contract | Addressed | y |\n",
    )
    proc = _run_archive_pass([str(artifact), "--phase", "2"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # Two [contract] tags, zero [detail], zero [upstream].
    assert "tags=d0u0c2" in text


def test_phase_3_stashes_tag_summary_in_notes(tmp_path):
    """Phase 3 archive also stashes `tags=dXuYcZ`."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [HIGH] | critic | [detail] FQCN naming nitpick | Addressed | x |\n"
        "| [HIGH] | critic | [detail] regex tuning | Addressed | y |\n"
        "| [HIGH] | critic | [contract] cross-feature ordering | Addressed | z |\n",
    )
    proc = _run_archive_pass([str(artifact), "--phase", "3"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "tags=d2u0c1" in text


def test_phase_1_does_not_stash_tag_summary(tmp_path):
    """Phase 1 has no tag mechanism; the Notes column should NOT include the
    `tags=` substring."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [HIGH] | pragmatist | concern | Addressed | fixed |\n",
    )
    proc = _run_archive_pass([str(artifact), "--phase", "1"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "tags=" not in text


# --- Phase-3 strict-bar signal driven by [detail] accumulation ------------


def _three_detail_highs():
    return (
        "| [HIGH] | critic | [detail] single-feature FQCN | Addressed | x |\n"
        "| [HIGH] | critic | [detail] regex tuning | Addressed | y |\n"
        "| [HIGH] | critic | [detail] runbook authoring | Addressed | z |\n"
    )


def test_phase_3_strict_bar_signal_fires_on_detail_accumulation(tmp_path):
    """Phase 3 strict-bar signal fires on flat HIGH + >50% [detail] tags
    across last two NORMAL passes."""
    artifact = _artifact_with_trajectory(
        tmp_path,
        # Prior pass: HIGHs=3, all [detail] (tags=d3u0c0).
        [_traj_row(pass_n=1, highs=3, addressed=3, notes="tags=d3u0c0")],
        latest_rows=_three_detail_highs(),
    )
    proc = _run_archive_pass([str(artifact), "--phase", "3"])
    assert proc.returncode == 0, proc.stderr
    assert "STRICT-BAR-SIGNAL" in proc.stdout, (
        f"expected Phase-3 signal on [detail] accumulation; "
        f"stdout={proc.stdout!r}"
    )
    assert "tagged [detail]" in proc.stdout


def test_phase_3_strict_bar_signal_does_not_fire_on_contract_tags(tmp_path):
    """Phase 3 with mostly [contract] tags (not [detail]) does NOT fire —
    those are legitimate at-this-phase work."""
    artifact = _artifact_with_trajectory(
        tmp_path,
        [_traj_row(pass_n=1, highs=3, addressed=3, notes="tags=d0u0c3")],
        latest_rows=(
            "| [HIGH] | critic | [contract] cross-feature port | Addressed | x |\n"
            "| [HIGH] | critic | [contract] env-var convention | Addressed | y |\n"
            "| [HIGH] | critic | [contract] migration ordering | Addressed | z |\n"
        ),
    )
    proc = _run_archive_pass([str(artifact), "--phase", "3"])
    assert proc.returncode == 0, proc.stderr
    assert "STRICT-BAR-SIGNAL" not in proc.stdout


def test_phase_3_strict_bar_signal_does_not_fire_without_prior_tag_summary(tmp_path):
    """If the prior trajectory row has no `tags=` substring (e.g., legacy row
    from before the patch), the Phase-3 detector skips — it can't compare."""
    artifact = _artifact_with_trajectory(
        tmp_path,
        # Prior row predates the tag mechanism; Notes is '—'.
        [_traj_row(pass_n=1, highs=3, addressed=3, notes="—")],
        latest_rows=_three_detail_highs(),
    )
    proc = _run_archive_pass([str(artifact), "--phase", "3"])
    assert proc.returncode == 0, proc.stderr
    assert "STRICT-BAR-SIGNAL" not in proc.stdout


def test_phase_2_strict_bar_signal_still_uses_deferred(tmp_path):
    """Phase 2 strict-bar signal continues to use Deferred → DOWNSTREAM
    accumulation (unchanged from before the patch)."""
    artifact = _artifact_with_trajectory(
        tmp_path,
        # Note: Phase 2 row from prior pass; tags=d0u0c0 since the panel
        # produced only [contract] in NORMAL, but here we're testing the
        # Deferred path so we use a deferred-heavy prior row.
        [_traj_row(pass_n=1, highs=3, deferred=3, notes="tags=d0u0c0")],
        latest_rows=(
            "| [HIGH] | architect | concern A | Deferred → tasks.md | later |\n"
            "| [HIGH] | architect | concern B | Deferred → tasks.md | later |\n"
            "| [HIGH] | architect | concern C | Deferred → tasks.md | later |\n"
        ),
    )
    proc = _run_archive_pass([str(artifact), "--phase", "2"])
    assert proc.returncode == 0, proc.stderr
    assert "STRICT-BAR-SIGNAL" in proc.stdout
    assert "deferred downstream" in proc.stdout


# --- Halt-trigger integration: two-consecutive [upstream] passes ----------


def test_phase_3_two_consecutive_upstream_passes_create_halt_pattern(tmp_path):
    """When two consecutive Phase-3 NORMAL passes each contain an [upstream]
    finding, both trajectory rows get 'halt vote' in Notes — the precondition
    for the auto halt-trigger to fire (which the synthesizer detects from
    reading the trajectory's last two rows)."""
    # Prior pass already recorded a halt vote from an [upstream] finding.
    prior_row = _traj_row(
        pass_n=1, highs=1, addressed=1,
        notes="halt vote (critic: [upstream] SCOPE doesn't commit G4); tags=d0u1c0",
    )
    artifact = _artifact_with_trajectory(
        tmp_path,
        [prior_row],
        latest_rows=(
            "| [HIGH] | critic | [upstream] ARCH doesn't include component Y | "
            "Addressed | escalate |\n"
        ),
    )
    proc = _run_archive_pass([str(artifact), "--phase", "3"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # The newly-archived row should also carry 'halt vote'.
    # Both prior and new row have 'halt vote' — synthesizer's check fires.
    assert text.count("halt vote") >= 2


def test_phase_2_two_consecutive_upstream_passes_create_halt_pattern(tmp_path):
    """Same pattern for Phase 2."""
    prior_row = _traj_row(
        pass_n=1, highs=1, addressed=1,
        notes="halt vote (architect: [upstream] SCOPE doesn't commit X); tags=d0u1c0",
    )
    artifact = _artifact_with_trajectory(
        tmp_path,
        [prior_row],
        latest_rows=(
            "| [HIGH] | architect | [upstream] SCOPE doesn't commit Y | "
            "Addressed | escalate |\n"
        ),
    )
    proc = _run_archive_pass([str(artifact), "--phase", "2"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert text.count("halt vote") >= 2


# --- Soc_coach pattern: Phase-3 [detail] accumulation across two passes ---


# --- Severity and source filters on tag detection ------------------------


def test_med_upstream_row_does_not_auto_route_to_halt(tmp_path):
    """A MED row with an [upstream] tag (panelist mistake — tags should be
    on HIGH only) must NOT auto-route to a halt vote. The mechanism is
    HIGH-only per blueprint-strict.md."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | architect | [upstream] mislabeled severity | Addressed | x |\n",
    )
    proc = _run_archive_pass([str(artifact), "--phase", "2"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "halt vote" not in text


def test_self_check_upstream_row_does_not_auto_route_to_halt(tmp_path):
    """A [SELF-CHECK] HIGH row whose Concern happens to start with [upstream]
    (extremely unusual — self-check categories are a/b/c, not panel tags)
    must NOT auto-route to halt. Self-check rows describe synthesizer
    regressions, not at-this-phase routing decisions."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [HIGH] | [SELF-CHECK] (a) | [upstream] coincidental prefix | Addressed | x |\n",
    )
    proc = _run_archive_pass([str(artifact), "--phase", "2"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "halt vote" not in text


def test_med_detail_row_does_not_count_in_tag_summary(tmp_path):
    """A MED row tagged [detail] must NOT contribute to the tags=dXuYcZ
    summary — only HIGH panel rows count."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [HIGH] | critic | [detail] real detail concern | Addressed | x |\n"
        "| [MED]  | critic | [detail] should not count | Addressed | y |\n",
    )
    proc = _run_archive_pass([str(artifact), "--phase", "3"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # Only the HIGH [detail] row counts.
    assert "tags=d1u0c0" in text


def test_soc_coach_pattern_fires_phase_3_strict_bar(tmp_path):
    """Synthetic replay of soc_coach passes 21-22 (per blueprint-strict.md
    test case 1): panel keeps finding [detail]-tagged Phase-3 concerns; HIGH
    count stays flat. Confirm BOTH:
      - archive_pass.py emits STRICT-BAR-SIGNAL (>50% [detail])
      - halt-trigger does NOT fire (no [upstream] tags)
    """
    # Pass 21: 3 HIGHs all [detail].
    prior_row = _traj_row(
        pass_n=21, highs=3, addressed=3,
        notes="tags=d3u0c0",
    )
    # Pass 22: 3 more HIGHs all [detail]; HIGH count flat at 3.
    artifact = _artifact_with_trajectory(
        tmp_path,
        [prior_row],
        latest_rows=(
            "| [HIGH] | critic | [detail] ArchUnit existence-check ≥2 vs ==2 | Addressed | x |\n"
            "| [HIGH] | critic | [detail] sha256(URL) leaks via shell history | Addressed | y |\n"
            "| [HIGH] | critic | [detail] CI grep regex character class | Addressed | z |\n"
        ),
    )
    proc = _run_archive_pass([str(artifact), "--phase", "3"])
    assert proc.returncode == 0, proc.stderr
    assert "STRICT-BAR-SIGNAL" in proc.stdout
    assert "100% of disposed concerns tagged [detail]" in proc.stdout
    text = artifact.read_text(encoding="utf-8")
    # No [upstream] tags → no halt vote in either trajectory row.
    assert "halt vote" not in text


# ---------------------------------------------------------------------------
# Unit tests for module-private helpers (import-based, not subprocess)
# ---------------------------------------------------------------------------


def _load_archive_pass():
    """Import archive_pass for direct testing of private helpers."""
    import importlib

    scripts = _REPO_ROOT / "telescoping-sdd" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    if "archive_pass" in sys.modules:
        return importlib.reload(sys.modules["archive_pass"])
    return importlib.import_module("archive_pass")


def test_is_normal_pass_row_recognizes_elided_row_as_non_normal():
    """Elided summary rows written by trim_trajectory_table are bookkeeping,
    not real passes — the strict-bar / halt-trigger code must skip them.
    """
    ap = _load_archive_pass()
    elided_row = {
        "Pass": "…",
        "Date": "…",
        "HIGHs": "—",
        "Regressions": "—",
        "Addressed": "—",
        "Deferred": "—",
        "Sealed": "—",
        "Notes": "7 earlier passes elided",
    }
    assert ap._is_normal_pass_row(elided_row) is False


def test_is_normal_pass_row_still_recognizes_existing_non_normal_kinds():
    """Existing non-normal-row contracts must still hold."""
    ap = _load_archive_pass()
    assert ap._is_normal_pass_row({"Notes": "strict-bar pass"}) is False
    assert ap._is_normal_pass_row({"Notes": "cross-check pass"}) is False
    assert ap._is_normal_pass_row({"Notes": "skipped (mechanical: rename)"}) is False


def test_is_normal_pass_row_recognizes_normal_row():
    """A pass row without any of the exclusion substrings is NORMAL."""
    ap = _load_archive_pass()
    assert ap._is_normal_pass_row({"Notes": "converged (0 HIGH)"}) is True
    assert ap._is_normal_pass_row({"Notes": "halt vote tags=d2u0c1"}) is True
