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
