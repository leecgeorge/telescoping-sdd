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
        "### Deferred dispositions\n\n"
        "<!-- Auto-populated by archive_pass.py when a Deferred-disposed row is promoted; remains empty until first deferral. -->\n\n"
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
        "| [MED] | pragmatist | minor thing | Deferred → PLAN.md | Routed because: downstream work |\n",
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
        "### Deferred dispositions\n\n"
        "<!-- Auto-populated by archive_pass.py when a Deferred-disposed row is promoted; remains empty until first deferral. -->\n\n"
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
        "| [HIGH] | critic | concern A | Deferred → PLAN.md | Routed because: downstream work |\n"
        "| [HIGH] | pragmatist | concern B | Deferred → PLAN.md | Routed because: downstream work |\n"
        "| [HIGH] | devils-advocate | concern C | Deferred → PLAN.md | Routed because: downstream work |\n"
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
            "| [HIGH] | critic | concern A | Deferred → PLAN.md | Routed because: downstream work |\n"
            "| [HIGH] | pragmatist | concern B | Deferred → PLAN.md | Routed because: downstream work |\n"
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
            "| [HIGH] | architect | concern A | Deferred → tasks.md | Routed because: downstream work |\n"
            "| [HIGH] | architect | concern B | Deferred → tasks.md | Routed because: downstream work |\n"
            "| [HIGH] | architect | concern C | Deferred → tasks.md | Routed because: downstream work |\n"
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


# ============================================================================
# Deferred-dispositions feature — T1 tests (constants, _is_terminal, --terminal)
# See specs/deferred-dispositions/{spec.md, design.md, tasks.md}
# ============================================================================

_MINIMAL_PANEL_ARTIFACT = (
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
    "- **Content Hash:** `pending`\n"
)


def test_terminal_guard_fires_for_PLAN_md(tmp_path):
    """PLAN.md without --terminal trips the registry guard."""
    artifact = tmp_path / "PLAN.md"
    artifact.write_text(_MINIMAL_PANEL_ARTIFACT, encoding="utf-8")
    proc = _run_archive_pass([str(artifact), "--check"])
    assert proc.returncode != 0
    assert "TERMINAL_FILENAMES" in proc.stderr
    assert "--terminal" in proc.stderr


def test_terminal_guard_fires_for_tasks_md(tmp_path):
    """tasks.md without --terminal trips the registry guard."""
    artifact = tmp_path / "tasks.md"
    artifact.write_text(_MINIMAL_PANEL_ARTIFACT, encoding="utf-8")
    proc = _run_archive_pass([str(artifact), "--check"])
    assert proc.returncode != 0
    assert "TERMINAL_FILENAMES" in proc.stderr


def test_terminal_guard_case_sensitive(tmp_path):
    """plan.md (lowercase) is NOT in the case-sensitive registry."""
    artifact = tmp_path / "plan.md"
    artifact.write_text(_MINIMAL_PANEL_ARTIFACT, encoding="utf-8")
    proc = _run_archive_pass([str(artifact), "--check"])
    # Whether the script exits 0 or non-zero for other reasons doesn't matter;
    # the specific registry error MUST NOT be in stderr.
    assert "TERMINAL_FILENAMES" not in proc.stderr


def test_terminal_flag_suppresses_registry_guard(tmp_path):
    """PLAN.md --terminal does not trip the registry guard."""
    artifact = tmp_path / "PLAN.md"
    artifact.write_text(_MINIMAL_PANEL_ARTIFACT, encoding="utf-8")
    proc = _run_archive_pass([str(artifact), "--check", "--terminal"])
    assert "TERMINAL_FILENAMES" not in proc.stderr


def test_is_terminal_explicit_flag_priority():
    """_is_terminal returns True when explicit_flag=True regardless of other inputs."""
    ap = _load_archive_pass()
    assert ap._is_terminal("any content", Path("spec.md"), True) is True


def test_is_terminal_registry_match():
    """_is_terminal returns True for filenames in TERMINAL_FILENAMES."""
    ap = _load_archive_pass()
    assert ap._is_terminal("any content", Path("/x/PLAN.md"), False) is True
    assert ap._is_terminal("any content", Path("/x/tasks.md"), False) is True
    assert ap._is_terminal("any content", Path("/x/spec.md"), False) is False


def test_is_terminal_html_marker_detection():
    """_is_terminal returns True for content containing TERMINAL_HTML_MARKER."""
    ap = _load_archive_pass()
    content = "## Panel Review\n\n<!-- terminal-phase: scope -->\n"
    assert ap._is_terminal(content, Path("/x/SCOPE.md"), False) is True
    assert ap._is_terminal("no marker here", Path("/x/SCOPE.md"), False) is False


def test_terminal_filenames_registry_membership():
    """The registry is a frozenset containing the four canonical terminal filenames."""
    ap = _load_archive_pass()
    assert ap.TERMINAL_FILENAMES == frozenset(
        {"PLAN.md", "tasks.md", "tasks-python.md", "tasks-java.md"}
    )


def test_target_pat_rejects_traversal_and_accepts_subdir():
    """TARGET_PAT: rejects .. segments, requires .md, allows subdir paths."""
    ap = _load_archive_pass()
    assert ap.TARGET_PAT.match("tasks.md")
    assert ap.TARGET_PAT.match("subdir/tasks.md")
    assert ap.TARGET_PAT.match("a/b/c/PLAN.md")
    assert not ap.TARGET_PAT.match("../tasks.md")
    assert not ap.TARGET_PAT.match("../../etc/passwd.md")
    assert not ap.TARGET_PAT.match("foo/../bar.md")
    assert not ap.TARGET_PAT.match("tasks.md | extra")
    assert not ap.TARGET_PAT.match("tasks")


# ============================================================================
# T3 — parse_defs, next_def_id, lookup_def (C2, I1, I1b)
# ============================================================================

def test_parse_defs_empty_section():
    """Empty section header → empty list."""
    ap = _load_archive_pass()
    lines = ["### Deferred dispositions", "", ""]
    assert ap.parse_defs(lines, 0, len(lines)) == []


def test_parse_defs_single_entry():
    """One well-formed entry → list of one dict with all six fields."""
    ap = _load_archive_pass()
    lines = [
        "### Deferred dispositions",
        "",
        "- `[DEF-01]` **Some concern title** → tasks.md (pass 2) — Routed because: belongs in tasks phase.",
        "",
    ]
    entries = ap.parse_defs(lines, 0, len(lines))
    assert len(entries) == 1
    e = entries[0]
    assert e["id"] == 1
    assert e["title"] == "Some concern title"
    assert e["target"] == "tasks.md"
    assert e["pass_n"] == 2
    assert e["rationale"].rstrip(".") == "belongs in tasks phase"
    assert isinstance(e["line_idx"], int)


def test_parse_defs_three_entries_sequential_ids():
    """Multiple entries returned in file order with correct IDs."""
    ap = _load_archive_pass()
    lines = [
        "### Deferred dispositions",
        "",
        "- `[DEF-01]` **First** → tasks.md (pass 1) — Routed because: reason 1.",
        "- `[DEF-02]` **Second** → tasks.md (pass 2) — Routed because: reason 2.",
        "- `[DEF-03]` **Third** → PLAN.md (pass 3) — Routed because: reason 3.",
    ]
    entries = ap.parse_defs(lines, 0, len(lines))
    assert [e["id"] for e in entries] == [1, 2, 3]
    assert [e["target"] for e in entries] == ["tasks.md", "tasks.md", "PLAN.md"]


def test_parse_defs_ignores_html_comments():
    """HTML comments within section bounds are not parsed as entries."""
    ap = _load_archive_pass()
    lines = [
        "### Deferred dispositions",
        "",
        "<!-- Auto-populated by archive_pass.py -->",
        "",
        "- `[DEF-01]` **Real entry** → tasks.md (pass 1) — Routed because: real reason.",
    ]
    entries = ap.parse_defs(lines, 0, len(lines))
    assert len(entries) == 1
    assert entries[0]["id"] == 1


def test_next_def_id_empty():
    ap = _load_archive_pass()
    assert ap.next_def_id([]) == 1


def test_next_def_id_continues_from_max():
    ap = _load_archive_pass()
    entries = [{"id": 1}, {"id": 2}, {"id": 3}]
    assert ap.next_def_id(entries) == 4


def test_lookup_def_finds_existing():
    ap = _load_archive_pass()
    entries = [{"id": 1, "target": "a.md"}, {"id": 2, "target": "b.md"}]
    found = ap.lookup_def(entries, 2)
    assert found is not None and found["target"] == "b.md"


def test_lookup_def_returns_none_when_missing():
    ap = _load_archive_pass()
    entries = [{"id": 1, "target": "a.md"}]
    assert ap.lookup_def(entries, 99) is None


# ============================================================================
# T4 — Auto-insert of ### Deferred dispositions on legacy artifacts (C3)
# ============================================================================

def _legacy_artifact_without_deferred_section(tmp_path, latest_rows="", name="spec.md"):
    """Pre-feature artifact lacking ### Deferred dispositions. Used by T4 tests."""
    artifact = tmp_path / name
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


def test_auto_insert_on_legacy_artifact(tmp_path):
    """Archive of legacy artifact (no section) inserts the header in the right position."""
    artifact = _legacy_artifact_without_deferred_section(
        tmp_path, "| [MED] | pragmatist | minor | Addressed | fixed |\n"
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "### Deferred dispositions" in text
    # Section appears between Sealed and Latest
    i_sealed = text.find("### Sealed dispositions")
    i_def = text.find("### Deferred dispositions")
    i_latest = text.find("### Latest pass detail")
    assert i_sealed < i_def < i_latest


def test_auto_insert_idempotent(tmp_path):
    """Archiving twice does not duplicate the header."""
    artifact = _legacy_artifact_without_deferred_section(
        tmp_path, "| [MED] | pragmatist | minor | Addressed | fixed |\n"
    )
    proc1 = _run_archive_pass([str(artifact)])
    assert proc1.returncode == 0, proc1.stderr
    # Second pass — add a fresh Latest row and re-archive
    text = artifact.read_text(encoding="utf-8")
    text = text.replace(
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|",
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        "| [MED] | pragmatist | minor2 | Addressed | fixed |"
    )
    artifact.write_text(text, encoding="utf-8")
    proc2 = _run_archive_pass([str(artifact)])
    assert proc2.returncode == 0, proc2.stderr
    final = artifact.read_text(encoding="utf-8")
    assert final.count("### Deferred dispositions") == 1


def test_auto_insert_dry_run_no_write(tmp_path):
    """--dry-run on legacy artifact does NOT modify the file."""
    artifact = _legacy_artifact_without_deferred_section(
        tmp_path, "| [MED] | pragmatist | minor | Addressed | fixed |\n"
    )
    original = artifact.read_text(encoding="utf-8")
    proc = _run_archive_pass([str(artifact), "--dry-run"])
    assert proc.returncode == 0, proc.stderr
    after = artifact.read_text(encoding="utf-8")
    assert original == after, "dry-run must not write the file"
    # The diff should mention the section
    assert "### Deferred dispositions" in proc.stdout


def test_auto_insert_terminal_no_insert(tmp_path):
    """--terminal flag suppresses auto-insert."""
    artifact = _legacy_artifact_without_deferred_section(
        tmp_path, "| [MED] | pragmatist | minor | Addressed | fixed |\n",
        name="some_terminal.md",
    )
    proc = _run_archive_pass([str(artifact), "--terminal"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "### Deferred dispositions" not in text


def test_auto_insert_skipped_pass_still_inserts(tmp_path):
    """--skip on a legacy artifact still self-heals the format (auto-insert runs)."""
    artifact = _legacy_artifact_without_deferred_section(tmp_path, "")
    proc = _run_archive_pass([str(artifact), "--skip", "mechanical: rename"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "### Deferred dispositions" in text


def test_auto_insert_section_order(tmp_path):
    """After auto-insert, section order matches PANEL_SECTION_ORDER."""
    ap = _load_archive_pass()
    artifact = _legacy_artifact_without_deferred_section(
        tmp_path, "| [MED] | pragmatist | minor | Addressed | fixed |\n"
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    positions = [text.find(heading) for heading in ap.PANEL_SECTION_ORDER]
    assert all(p >= 0 for p in positions), f"missing section(s): {positions}"
    assert positions == sorted(positions), (
        f"section order mismatch: {list(zip(ap.PANEL_SECTION_ORDER, positions))}"
    )


def test_auto_insert_no_repair_of_wrong_position(tmp_path):
    """If H_DEFERRED is already present (even mis-positioned), don't relocate it."""
    artifact = tmp_path / "spec.md"
    # Place ### Deferred dispositions BETWEEN Trajectory and Sealed (wrong position).
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "\n"
        "### Deferred dispositions\n\n"  # mis-positioned (should be after Sealed)
        "\n"
        "### Sealed dispositions\n\n"
        "_None yet._\n\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        "| [MED] | pragmatist | minor | Addressed | fixed |\n"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # The section is still present exactly once (no duplicate inserted)
    assert text.count("### Deferred dispositions") == 1


# ============================================================================
# T5 — Deferred-row promotion + Routed because: + target shape guard (C4)
# ============================================================================

def test_deferred_row_promoted_with_def_id(tmp_path):
    """Single Deferred row with Routed because: → [DEF-01] in output; Latest cleared."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | pragmatist | concern A | Deferred → tasks.md | Routed because: belongs in tasks |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "[DEF-01]" in text
    assert "→ tasks.md" in text
    assert "Routed because: belongs in tasks." in text
    # concern A should no longer be in Latest (cleared)
    assert "concern A" not in text or text.count("concern A") == 1  # remains only in [DEF-NN]


def test_deferred_promotion_two_rows_sequential_ids(tmp_path):
    """Two Deferred rows in one pass get [DEF-01] and [DEF-02]."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | pragmatist | first | Deferred → tasks.md | Routed because: reason 1 |\n"
        "| [MED] | critic | second | Deferred → tasks.md | Routed because: reason 2 |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "[DEF-01]" in text
    assert "[DEF-02]" in text


def test_deferred_promotion_fails_without_routed_because(tmp_path):
    """Deferred row missing Routed because: → exit 1 with error naming the row."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | pragmatist | concern X | Deferred → tasks.md | just a note |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode != 0
    assert "Routed because:" in proc.stderr
    assert "concern X" in proc.stderr or "pragmatist" in proc.stderr


def test_deferred_promotion_target_shape_rejects_traversal_with_md(tmp_path):
    """Path-traversal target ../../etc/passwd.md (with .md) is rejected."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | critic | x | Deferred → ../../etc/passwd.md | Routed because: r |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode != 0
    assert "target" in proc.stderr.lower()


def test_deferred_promotion_target_shape_rejects_double_dot_segment_mid_path(tmp_path):
    """Mid-path .. segment foo/../bar.md is rejected."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | critic | x | Deferred → foo/../bar.md | Routed because: r |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode != 0


def test_deferred_promotion_target_shape_accepts_subdir(tmp_path):
    """Target subdir/tasks.md is accepted (no traversal segments)."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | critic | x | Deferred → subdir/tasks.md | Routed because: r |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "→ subdir/tasks.md" in text


def test_deferred_skip_does_not_promote(tmp_path):
    """--skip with Deferred row present → no promotion, exit 0."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | critic | x | Deferred → tasks.md | Routed because: r |\n",
    )
    proc = _run_archive_pass([str(artifact), "--skip", "mechanical: rename"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # Skipped: no [DEF-01] promoted
    assert "[DEF-01]" not in text


def test_deferred_terminal_forbids_deferred_row(tmp_path):
    """--terminal archive with Deferred row in Latest → exit 1."""
    # Use a non-registry filename so the registry guard doesn't fire first
    artifact = tmp_path / "PLAN.md"
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
        "| [MED] | critic | x | Deferred → tasks.md | Routed because: r |\n"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    proc = _run_archive_pass([str(artifact), "--phase", "3", "--terminal"])
    assert proc.returncode != 0
    assert "Terminal" in proc.stderr and "Deferred" in proc.stderr


def test_combined_legacy_artifact_with_deferred_rows(tmp_path):
    """Legacy artifact (no Deferred section header) + Deferred row → single archive
    auto-inserts the header AND promotes the row in one transaction."""
    artifact = _legacy_artifact_without_deferred_section(
        tmp_path,
        "| [MED] | pragmatist | concern A | Deferred → tasks.md | Routed because: belongs in tasks |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # Header was inserted
    assert "### Deferred dispositions" in text
    # Promotion happened
    assert "[DEF-01]" in text
    assert "→ tasks.md" in text
    # Latest pass detail is cleared (only the header table remains, no concern A row)
    # The string "concern A" may still appear in [DEF-NN]'s title, so check for the table row
    assert "Deferred → tasks.md | Routed because:" not in text


def test_terminal_with_dry_run_combination(tmp_path):
    """--terminal --dry-run with Deferred row → exit 1, file unchanged."""
    artifact = tmp_path / "PLAN.md"
    body = (
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
        "| [MED] | critic | x | Deferred → tasks.md | Routed because: r |\n"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )
    artifact.write_text(body, encoding="utf-8")
    proc = _run_archive_pass(
        [str(artifact), "--phase", "3", "--terminal", "--dry-run"]
    )
    assert proc.returncode != 0
    # File unchanged on disk
    assert artifact.read_text(encoding="utf-8") == body
    assert "Terminal" in proc.stderr and "Deferred" in proc.stderr


# ============================================================================
# T6 — Marker expansion: strict / wide near-miss / plain (C5, R5)
# ============================================================================

def _artifact_with_def_and_marker(tmp_path, marker_notes: str, def_id: str = "01", target: str = "tasks.md"):
    """Artifact with one pre-existing [DEF-<id>] entry and a Sealed row with the given marker Notes."""
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
        "### Deferred dispositions\n\n"
        f"- `[DEF-{def_id}]` **Some concern** → {target} (pass 1) — Routed because: belongs in tasks.\n"
        "\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        f"| [MED] | pragmatist | similar concern | Sealed | {marker_notes} |\n"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    return artifact


def test_marker_strict_match_expands_to_canonical(tmp_path):
    """Defense: rerouted [DEF-01] → expands to canonical text with DEFERRED_REDISPOSITION_PREFIX."""
    ap = _load_archive_pass()
    artifact = _artifact_with_def_and_marker(tmp_path, "Defense: rerouted [DEF-01]")
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # Canonical text appears in the Sealed entry
    assert ap.DEFERRED_REDISPOSITION_PREFIX in text
    assert "as [DEF-01]" in text
    assert "no new evidence presented this pass" in text


def test_marker_trailing_period_tolerated(tmp_path):
    """Defense: rerouted [DEF-01]. (trailing period) is accepted by strict match."""
    artifact = _artifact_with_def_and_marker(tmp_path, "Defense: rerouted [DEF-01].")
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr


def test_marker_trailing_whitespace_tolerated(tmp_path):
    """Defense: rerouted [DEF-01]   (trailing whitespace) is accepted."""
    artifact = _artifact_with_def_and_marker(tmp_path, "Defense: rerouted [DEF-01]   ")
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr


def test_marker_unresolved_def_id_exits_nonzero(tmp_path):
    """Defense: rerouted [DEF-99] with no [DEF-99] entry → exit 1."""
    artifact = _artifact_with_def_and_marker(tmp_path, "Defense: rerouted [DEF-99]")
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode != 0
    assert "[DEF-99]" in proc.stderr or "DEF-99" in proc.stderr


def test_near_miss_hyphenated_rerouted(tmp_path):
    """Defense: re-routed [DEF-01] (hyphenated) → near-miss hard-fail."""
    artifact = _artifact_with_def_and_marker(tmp_path, "Defense: re-routed [DEF-01]")
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode != 0
    assert "marker" in proc.stderr.lower()


def test_near_miss_wrong_casing(tmp_path):
    """defense: rerouted [DEF-01] (lowercase Defense) → wide pattern catches (case-tolerant on leading keyword)."""
    artifact = _artifact_with_def_and_marker(tmp_path, "defense: rerouted [DEF-01]")
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode != 0


def test_near_miss_single_digit_id(tmp_path):
    """Defense: rerouted [DEF-1] (single-digit) → near-miss hard-fail."""
    artifact = _artifact_with_def_and_marker(tmp_path, "Defense: rerouted [DEF-1]")
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode != 0


def test_near_miss_three_digit_id(tmp_path):
    """Defense: rerouted [DEF-007] (three-digit) → near-miss hard-fail."""
    artifact = _artifact_with_def_and_marker(tmp_path, "Defense: rerouted [DEF-007]")
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode != 0


def test_near_miss_smart_quotes(tmp_path):
    """Defense: rerouted 'DEF-01' (smart-quoted brackets) → near-miss hard-fail."""
    # U+2018/U+2019 single quotation marks around DEF-01
    artifact = _artifact_with_def_and_marker(
        tmp_path, "Defense: rerouted ‘DEF-01’"
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode != 0


def test_plain_sealed_no_rerouted_substring(tmp_path):
    """Defense: previously reviewed in §3 → plain Sealed promotion, no error."""
    artifact = _artifact_with_def_and_marker(
        tmp_path, "Defense: previously reviewed in §3"
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # The Sealed entry contains the original defense text, not the canonical
    assert "previously reviewed" in text


def test_plain_sealed_prose_contains_rerouted_word_does_not_hard_fail(tmp_path):
    """Legitimate prose containing 'rerouted' mid-sentence does NOT trigger near-miss."""
    artifact = _artifact_with_def_and_marker(
        tmp_path,
        "Defense: the concern was already rerouted upstream to architecture review",
    )
    proc = _run_archive_pass([str(artifact)])
    # Wide pattern is anchored: ^\s*Defense:\s*[Rr]e-?routed\b — this prose
    # starts with "Defense: the" so the rerouted-token isn't at start; should
    # NOT match wide-near-miss and should NOT hard-fail.
    assert proc.returncode == 0, proc.stderr


def test_marker_strict_pat_matches_spec_example():
    """MARKER_STRICT_PAT matches valid forms; rejects known near-misses."""
    ap = _load_archive_pass()
    # Matches: zero-padded 2-digit, optional trailing period/whitespace
    assert ap.MARKER_STRICT_PAT.match("Defense: rerouted [DEF-12]")
    assert ap.MARKER_STRICT_PAT.match("Defense: rerouted [DEF-01].")
    assert ap.MARKER_STRICT_PAT.match("Defense: rerouted [DEF-01]   ")
    # Rejects near-misses
    assert not ap.MARKER_STRICT_PAT.match("Defense: re-routed [DEF-01]")
    assert not ap.MARKER_STRICT_PAT.match("Defense: rerouted [DEF-1]")
    assert not ap.MARKER_STRICT_PAT.match("defense: rerouted [DEF-01]")
    assert not ap.MARKER_STRICT_PAT.match("Defense: rerouted [DEF-007]")


# ============================================================================
# T7 — R7 Strict-Bar Trigger Refinement (C6)
# ============================================================================

def test_strict_bar_counts_rerouted_deferrals(tmp_path):
    """Pass 1: 3 literal Deferred; Pass 2: 2 marker-expanded rerouted → STRICT-BAR-SIGNAL fires."""
    # Build pre-archived Pass 1 with 3 Deferred, then add Pass 2 with markers
    traj_rows = [
        _traj_row(
            pass_n=1, highs=3, addressed=0, deferred=3, sealed=0, notes="—",
        ),
    ]
    artifact = tmp_path / "spec.md"
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        f"| 1 | 2026-05-18 | 3 | 0 | 0 | 3 | 0 | — |\n"
        "\n"
        "### Sealed dispositions\n\n"
        "_None yet._\n\n"
        "### Deferred dispositions\n\n"
        "- `[DEF-01]` **First** → tasks.md (pass 1) — Routed because: r1.\n"
        "- `[DEF-02]` **Second** → tasks.md (pass 1) — Routed because: r2.\n"
        "\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        "| [HIGH] | critic | concern A | Sealed | Defense: rerouted [DEF-01] |\n"
        "| [HIGH] | critic | concern B | Sealed | Defense: rerouted [DEF-02] |\n"
        "| [HIGH] | critic | concern C | Addressed | fixed |\n"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    # Trigger should fire — Pass 2 has 0 literal Deferred + 2 rerouted (additive)
    # plus Pass 1's 3 literal Deferred. pooled_deferred = 5, pooled_total = 5+1 = 6.
    # ratio = 5/6 ≈ 83% > 50%, HIGH delta = 0 (3→3), so trigger fires.
    assert "STRICT-BAR-SIGNAL" in proc.stdout


def test_strict_bar_suppressed_terminal(tmp_path):
    """--terminal suppresses the strict-bar trigger entirely."""
    artifact = tmp_path / "PLAN.md"
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "| 1 | 2026-05-18 | 3 | 0 | 0 | 3 | 0 | — |\n"
        "\n"
        "### Sealed dispositions\n\n"
        "_None yet._\n\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        "| [HIGH] | critic | concern A | Addressed | fixed |\n"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    proc = _run_archive_pass([str(artifact), "--phase", "3", "--terminal"])
    assert proc.returncode == 0, proc.stderr
    # Even with high prior Deferred, terminal archives don't run strict-bar
    assert "STRICT-BAR-SIGNAL" not in proc.stdout


def test_detect_strict_bar_signal_back_compat_default(tmp_path):
    """Calling detect_strict_bar_signal without rerouted_def_count works (default 0)."""
    ap = _load_archive_pass()
    import argparse as _argparse
    args = _argparse.Namespace(
        strict_bar=False, cross_check=False, skip=None,
        terminal=False, phase=1,
    )
    prior = [{
        "Pass": "1", "Date": "2026-05-18", "HIGHs": "2", "Regressions": "0",
        "Addressed": "0", "Deferred": "2", "Sealed": "0", "Notes": "—",
    }]
    current = {
        "Pass": "2", "Date": "2026-05-18", "HIGHs": "2", "Regressions": "0",
        "Addressed": "0", "Deferred": "2", "Sealed": "0", "Notes": "—",
    }
    # Call without kwarg
    result_no_kwarg = ap.detect_strict_bar_signal(prior, current, args)
    # Call with explicit 0
    result_with_zero = ap.detect_strict_bar_signal(
        prior, current, args, rerouted_def_count=0
    )
    assert result_no_kwarg == result_with_zero


def test_strict_bar_fires_when_only_rerouted_deferrals_signal(tmp_path):
    """Pass 1: 3 literal Deferred; Pass 2: 0 literal Deferred BUT 3 rerouted → SIGNAL fires."""
    artifact = tmp_path / "spec.md"
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "| 1 | 2026-05-18 | 3 | 0 | 0 | 3 | 0 | — |\n"
        "\n"
        "### Sealed dispositions\n\n"
        "_None yet._\n\n"
        "### Deferred dispositions\n\n"
        "- `[DEF-01]` **A** → tasks.md (pass 1) — Routed because: r1.\n"
        "- `[DEF-02]` **B** → tasks.md (pass 1) — Routed because: r2.\n"
        "- `[DEF-03]` **C** → tasks.md (pass 1) — Routed because: r3.\n"
        "\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        "| [HIGH] | critic | concern A | Sealed | Defense: rerouted [DEF-01] |\n"
        "| [HIGH] | critic | concern B | Sealed | Defense: rerouted [DEF-02] |\n"
        "| [HIGH] | critic | concern C | Sealed | Defense: rerouted [DEF-03] |\n"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    # Pass 2: 0 literal Deferred + 3 rerouted. With Pass 1's 3 literal:
    # pooled_deferred = 3 + 0 + 3 = 6, pooled_total = 3 + 3 = 6, ratio = 100%
    # HIGH delta = 0 (3→3) → trigger fires
    assert "STRICT-BAR-SIGNAL" in proc.stdout


def test_rerouted_def_flag_set_during_marker_expansion(tmp_path):
    """Direct unit test: marker expansion sets rerouted_def=True on new_seals entry.

    This guards against silent T6 regressions where the flag fails to set,
    which would let T7 trigger tests pass with rerouted_def_count=0 defaulted-in.
    """
    # End-to-end check via the trajectory side-effect: a marker-expanded Sealed
    # row contributes to rerouted_def_count, which under matching conditions
    # makes the trigger fire. If the flag fails to set, the trigger wouldn't
    # fire, even with the marker-expanded row present.
    artifact = tmp_path / "spec.md"
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "| 1 | 2026-05-18 | 1 | 0 | 0 | 1 | 0 | — |\n"
        "\n"
        "### Sealed dispositions\n\n"
        "_None yet._\n\n"
        "### Deferred dispositions\n\n"
        "- `[DEF-01]` **Concern** → tasks.md (pass 1) — Routed because: r.\n"
        "\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        "| [HIGH] | critic | Concern | Sealed | Defense: rerouted [DEF-01] |\n"
        "\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    # Trigger should fire: Pass 1 deferred=1, Pass 2 deferred=0 + rerouted=1.
    # pooled_deferred=2, pooled_total = (0+1+0)+(0+0+1) = 2, ratio=100%.
    # HIGH delta = 0 (1→1).
    assert "STRICT-BAR-SIGNAL" in proc.stdout


# ============================================================================
# T9 — panel-review.md amendment-presence test (C8, R3, R5, AD9, I6)
# ============================================================================

def test_panel_review_md_amendments_present():
    """For each of the three target panel-review.md files, assert all the T9
    additions are present. Skip on missing files (partial-install safety).
    """
    ap = _load_archive_pass()
    # Path resolution: archive_pass.py lives at telescoping-sdd/scripts/; panel-review.md
    # at telescoping-sdd/skills/<skill>/references/.
    base = Path(ap.__file__).parent.parent / "skills"
    skills = ["project-blueprint", "spec-driven-dev"]
    import pytest as _pytest
    for skill in skills:
        p = base / skill / "references" / "panel-review.md"
        if not p.is_file():
            _pytest.skip(f"panel-review.md not present for {skill}")
        text = p.read_text(encoding="utf-8")
        # Step 1 deferred-suppression instruction
        assert "For items in Deferred dispositions" in text, f"{skill}: I3 missing"
        # Step 3 marker discipline + worked examples
        assert "Defense: rerouted [DEF-NN]" in text, f"{skill}: I4 marker missing"
        assert "positive example" in text.lower(), f"{skill}: I4 positive example missing"
        assert "negative example" in text.lower(), f"{skill}: I4 negative example missing"
        # Step 6 terminal-archive doctrine: --terminal substring present
        assert "--terminal" in text, f"{skill}: I5 terminal flag missing"
        # Format block: ### Deferred dispositions and [DEF-NN] vocabulary
        assert "### Deferred dispositions" in text, f"{skill}: AD9 section heading missing"
        assert "[DEF-NN]" in text, f"{skill}: AD9 vocabulary missing"
        # R7 numeric worked example
        assert "Worked example (R7)" in text, f"{skill}: I6 R7 example missing"
        # Concrete percentages
        assert "40%" in text or "80%" in text, f"{skill}: I6 numeric values missing"


def test_panel_review_md_disposition_vocabulary_preserved():
    """R5 AC4: existing disposition-vocabulary bullets are preserved verbatim
    across the T9 atomic update. Defends against accidental rewrites.
    """
    ap = _load_archive_pass()
    base = Path(ap.__file__).parent.parent / "skills"
    import pytest as _pytest
    for skill in ["project-blueprint", "spec-driven-dev"]:
        p = base / skill / "references" / "panel-review.md"
        if not p.is_file():
            _pytest.skip(f"panel-review.md not present for {skill}")
        text = p.read_text(encoding="utf-8")
        # The canonical disposition vocabulary must still be documented
        for token in ("Addressed", "Sealed", "Accepted as risk", "User input needed", "Halt and re-scope"):
            assert token in text, f"{skill}: disposition vocabulary token missing: {token}"


def test_deferred_redisposition_prefix_drift():
    """The DEFERRED_REDISPOSITION_PREFIX constant value appears verbatim in
    each panel-review.md (the canonical-prefix expansion landing place).
    """
    ap = _load_archive_pass()
    base = Path(ap.__file__).parent.parent / "skills"
    import pytest as _pytest
    prefix = ap.DEFERRED_REDISPOSITION_PREFIX  # "Defense: already routed to "
    for skill in ["project-blueprint", "spec-driven-dev"]:
        p = base / skill / "references" / "panel-review.md"
        if not p.is_file():
            _pytest.skip(f"panel-review.md not present for {skill}")
        text = p.read_text(encoding="utf-8")
        # The R7 worked example or surrounding text should contain the prefix
        # (either as the literal canonical text in the example, or as a reference)
        assert prefix in text, (
            f"{skill}: DEFERRED_REDISPOSITION_PREFIX value {prefix!r} not present "
            f"verbatim in panel-review.md — drift detected"
        )


# ============================================================================
# T10 — Template coverage test (C9)
# ============================================================================

_NON_TERMINAL_TEMPLATE_PATHS = [
    "skills/project-blueprint/references/scope-template.md",
    "skills/project-blueprint/references/architecture-template.md",
    "skills/spec-driven-dev/references/spec-template-python.md",
    "skills/spec-driven-dev/references/spec-template-java.md",
    "skills/spec-driven-dev/references/design-template-python.md",
    "skills/spec-driven-dev/references/design-template-java.md",
]
_TERMINAL_TEMPLATE_PATHS = [
    "skills/project-blueprint/references/plan-template.md",
    "skills/spec-driven-dev/references/tasks-template-python.md",
    "skills/spec-driven-dev/references/tasks-template-java.md",
]


def test_template_deferred_dispositions_present():
    """Registry-driven coverage of template files.

    Non-terminal templates: must contain `### Deferred dispositions` AND
    the auto-populate HTML comment.
    Terminal templates: must NOT contain `### Deferred dispositions` as a
    section heading; MUST contain the prohibition HTML comment.
    """
    ap = _load_archive_pass()
    base = Path(ap.__file__).parent.parent  # telescoping-sdd/

    for rel in _NON_TERMINAL_TEMPLATE_PATHS:
        p = base / rel
        assert p.is_file(), f"missing non-terminal template: {p}"
        text = p.read_text(encoding="utf-8")
        assert "### Deferred dispositions" in text, f"{rel}: missing section heading"
        assert "Auto-populated by archive_pass.py" in text, (
            f"{rel}: missing auto-populate HTML comment"
        )

    for rel in _TERMINAL_TEMPLATE_PATHS:
        p = base / rel
        assert p.is_file(), f"missing terminal template: {p}"
        text = p.read_text(encoding="utf-8")
        # Terminal: must NOT contain ### Deferred dispositions as a section heading
        import re as _re
        assert not _re.search(r"(?m)^### Deferred dispositions\s*$", text), (
            f"{rel}: terminal template must not contain '### Deferred dispositions' heading"
        )
        # Must contain prohibition HTML comment
        assert "Terminal Phase: must NOT contain" in text, (
            f"{rel}: missing prohibition HTML comment"
        )
