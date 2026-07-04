"""Behavior tests for `archive_pass.py`.

Locks in current behavior to catch regressions in any future edit to
archive_pass.py.
"""

from __future__ import annotations

import re
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


def test_find_section_ignores_fenced_example_heading(tmp_path):
    """3.5e: a fenced `### Trajectory` example BEFORE the real table must not be
    mistaken for the real section — archive_pass must append the new pass to the
    REAL table (and leave the fenced example untouched), matching the hash/anchor
    reader's fence-aware locator."""
    artifact = tmp_path / "spec.md"
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "How the trajectory looks (example, do not edit):\n\n"
        "```\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "| 99   | 2000-01-01 | 0 | 0 | 0 | 0 | 0 | fenced example |\n"
        "```\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "\n"
        "### Sealed dispositions\n\n_None yet._\n\n"
        "### Deferred dispositions\n\n<!-- empty -->\n\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        "| [MED] | pragmatist | minor | Addressed | fixed |\n"
        "\n## Approval\n\n- [ ] Approved to proceed to next phase\n- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # The fenced example row is untouched...
    assert "| 99   | 2000-01-01 | 0 | 0 | 0 | 0 | 0 | fenced example |" in text
    # ...and the new pass (1) was appended to the REAL (empty) table, not derived
    # from the fenced example's pass 99.
    assert "| 1 " in text
    assert "| 100 " not in text  # would be 99+1 if the fenced table had been read
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | pragmatist | minor thing | Deferred → PLAN.md | Routed because: downstream work |\n",
    )
    proc = _run_archive_pass([str(artifact), "--strict-bar"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "strict-bar pass; converged (0 HIGH)" in text


def test_archive_writes_utf8_atomically(tmp_path):
    """The artifact is written as UTF-8 (not the platform-default locale) and
    atomically (no leftover temp file). A Deferred disposition emits the non-ASCII
    arrow into the Trajectory/Deferred sections; that byte must round-trip as the
    UTF-8 sequence, not be mojibaked or fail to encode (audit R1.3)."""
    artifact = _artifact_with_latest(
        tmp_path,
        "| [MED] | pragmatist | minor thing | Deferred → PLAN.md | Routed because: downstream work |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    raw = artifact.read_bytes()
    # Decodes cleanly as UTF-8 (would raise if written via a lossy/locale codec)...
    text = raw.decode("utf-8")
    # ...and the arrow is present as the genuine UTF-8 encoding of U+2192.
    assert "→" in text
    assert b"\xe2\x86\x92" in raw
    # Atomic write leaves no temp sibling behind.
    assert not (tmp_path / "spec.md.tmp").exists()


def test_archive_handles_unicode_digit_pass_without_crash(tmp_path):
    """R2.7: a Trajectory row whose Pass cell is a non-ASCII digit ('²') must not
    crash next-pass computation (str.isdigit() is True for it but int() raises).
    The writer now uses _is_ascii_int — matching the hash/anchor reader — so the
    Unicode-digit row is skipped and next pass = max(ASCII passes) + 1."""
    unicode_row = {
        "Pass": "²", "Date": "2026-05-15", "HIGHs": "0", "Regressions": "0",
        "Addressed": "0", "Deferred": "0", "Sealed": "0", "Notes": "weird",
    }
    ascii_row = _traj_row(3, highs=0)
    artifact = _artifact_with_trajectory(
        tmp_path, [unicode_row, ascii_row],
        latest_rows="| [MED] | pragmatist | minor | Addressed | fixed |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    text = artifact.read_text(encoding="utf-8")
    # The appended row is pass 4 (max ASCII 3 + 1), not a crash or pass derived
    # from the Unicode-digit row.
    assert "| 4 " in text


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


def test_parse_table_warns_on_unescaped_pipe_row(capsys):
    """A panel-table row whose cell count != header (an unescaped `|` in a
    Concern/Notes cell) must NOT be dropped silently — it would vanish from the
    HIGH/Deferred/Sealed counts and the audit trail. parse_table warns instead
    (review finding Scripts D5-2)."""
    ap = _load_archive_pass()
    lines = [
        "| Severity | Source | Concern | Disposition | Notes |",
        "|----------|--------|---------|-------------|-------|",
        "| [HIGH] | critic | clean row | Addressed | ok |",
        "| [MED] | critic | a | b unescaped | Deferred | leftover |",
    ]
    rows, table = ap.parse_table(lines, 0, len(lines))
    assert table is not None
    assert len(rows) == 1 and rows[0]["Severity"] == "[HIGH]"
    err = capsys.readouterr().err
    assert "expected 5" in err and "unescaped '|'" in err


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


# --- artifact NN_-prefix tolerance for TERMINAL_FILENAMES (T2) ---

def test_terminal_filenames_prefix_tolerant_plan():
    ap = _load_archive_pass()
    assert ap._is_terminal("", Path("03_PLAN.md"), False) is True


def test_terminal_filenames_prefix_tolerant_tasks():
    ap = _load_archive_pass()
    assert ap._is_terminal("", Path("03_tasks.md"), False) is True


def test_terminal_filenames_prefix_tolerant_tasks_python():
    ap = _load_archive_pass()  # defensive-registry coverage (never emitted as a user artifact)
    assert ap._is_terminal("", Path("03_tasks-python.md"), False) is True


def test_terminal_filenames_prefix_tolerant_tasks_java():
    ap = _load_archive_pass()  # defensive-registry coverage
    assert ap._is_terminal("", Path("03_tasks-java.md"), False) is True


def test_terminal_filenames_non_terminal_spec():
    ap = _load_archive_pass()
    assert ap._is_terminal("", Path("01_spec.md"), False) is False


def test_terminal_filenames_non_terminal_design():
    ap = _load_archive_pass()
    assert ap._is_terminal("", Path("02_design.md"), False) is False


def test_archive_pass_cli_rejects_prefixed_plan_without_terminal(tmp_path):
    """The CLI TERMINAL gate (the second membership site) rejects 03_PLAN.md
    without --terminal, exactly as it does for bare PLAN.md."""
    plan = tmp_path / "03_PLAN.md"
    plan.write_text("# Plan\n", encoding="utf-8")
    proc = _run_archive_pass([str(plan)])
    assert proc.returncode != 0
    assert "TERMINAL_FILENAMES" in proc.stderr


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
        # R7 numeric worked example — relocated to the convergence sub-ref by the
        # progressive-disclosure split (v2.21.0); it lives with `## Strict-Bar
        # Convergence Mode`, so assert it there rather than in the slim CORE.
        conv = p.parent / "panel-review-convergence.md"
        assert conv.is_file(), f"{skill}: panel-review-convergence.md missing"
        conv_text = conv.read_text(encoding="utf-8")
        assert "Worked example (R7)" in conv_text, f"{skill}: I6 R7 example missing"
        # Concrete percentages
        assert "40%" in conv_text or "80%" in conv_text, f"{skill}: I6 numeric values missing"


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


# ============================================================================
# T8 (R6, AD9/I6) — multi-section reassembly corruption regression matrix.
# When ONE pass promotes a new Sealed AND (re)writes Deferred, the pre-fix
# code applied the four section edits sequentially using PRE-EDIT offsets:
# the Sealed promotion (above Deferred in file order) shifted the Deferred
# section down, so the subsequent Deferred edit wrote at stale offsets —
# duplicating [DEF-NN] entries and clobbering the Deferred / Approval headings.
# These tests are RED against the pre-refactor code and GREEN after AD9.
# ============================================================================


def _artifact_with_seals_and_defs(
    tmp_path, sealed_body, deferred_body, latest_rows, name="spec.md"
):
    """Panel doc with configurable Sealed + Deferred section bodies + Latest rows.

    `sealed_body` / `deferred_body` are the text BETWEEN the section heading
    (followed by its blank line) and the next heading — "" for an empty section,
    or pre-populated `[SEAL-NN]` / `[DEF-NN]` entry lines (each newline-terminated,
    ending with a trailing blank line).
    """
    artifact = tmp_path / name
    artifact.write_text(
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        "\n"
        "### Sealed dispositions\n\n"
        f"{sealed_body}"
        "### Deferred dispositions\n\n"
        f"{deferred_body}"
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


def _assert_panel_intact(text):
    """Structural invariants that the simultaneous Sealed+Deferred promotion
    must preserve. Each heading appears exactly once; every `[DEF-NN]` token
    lives strictly inside the unique Deferred window and is never duplicated.
    """
    import re

    for h in (
        "### Sealed dispositions",
        "### Deferred dispositions",
        "### Latest pass detail",
        "## Approval",
    ):
        # Count headings independently and BEFORE any window scan — a duplicated
        # heading is itself a corruption symptom that a .find()-based window
        # would silently mask.
        n = text.count(h)
        assert n == 1, f"{h!r} appears {n} time(s), expected exactly 1"

    lines = text.splitlines()
    d_idx = next(
        i for i, ln in enumerate(lines) if ln.strip() == "### Deferred dispositions"
    )
    # The Deferred window ends at the NEXT ##/### heading (computed by scan, NOT
    # hard-coded to ### Latest — a DEF orphaned past Latest must not escape).
    next_h = next(
        (i for i in range(d_idx + 1, len(lines)) if re.match(r"^#{2,3}\s", lines[i])),
        len(lines),
    )
    def_token = re.compile(r"\[DEF-\d+\]")
    for i, ln in enumerate(lines):
        if def_token.search(ln):
            assert d_idx < i < next_h, (
                f"[DEF-NN] token outside the Deferred window "
                f"({d_idx} < {i} < {next_h} failed): {ln!r}"
            )
    tokens = def_token.findall(text)
    assert len(tokens) == len(set(tokens)), f"duplicate [DEF-NN] tokens: {tokens}"


_NEW_SEAL_PLUS_DEFERRED_LATEST = (
    "| [HIGH] | critic | new sealed concern | Sealed | Defense: user-directed keep |\n"
    "| [MED] | pragmatist | new deferred concern | Deferred → tasks.md | "
    "Routed because: belongs later |\n"
)

_TWO_EXISTING_DEFS = (
    "- `[DEF-01]` **First deferred** → tasks.md (pass 1) — Routed because: a.\n"
    "- `[DEF-02]` **Second deferred** → tasks.md (pass 1) — Routed because: b.\n\n"
)


def test_reassembly_empty_sealed_populated_deferred(tmp_path):
    """Empty Sealed (insert branch) + populated Deferred (replace branch) +
    simultaneous new Sealed + new Deferred. This is the case that lost the
    heading in the wild. RED pre-fix, GREEN post-fix.
    """
    artifact = _artifact_with_seals_and_defs(
        tmp_path,
        sealed_body="",  # empty -> Sealed insert branch
        deferred_body=_TWO_EXISTING_DEFS,  # [DEF-01]/[DEF-02] -> Deferred replace branch
        latest_rows=_NEW_SEAL_PLUS_DEFERRED_LATEST,
    )
    proc = _run_archive_pass([str(artifact), "--phase", "2"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    _assert_panel_intact(text)
    # The new SEAL landed under Sealed; the new DEF is sequential (DEF-03).
    assert "[SEAL-01]" in text
    assert "[DEF-01]" in text and "[DEF-02]" in text and "[DEF-03]" in text
    # Latest cleared (the promoted rows no longer appear as Latest table rows).
    assert "Deferred → tasks.md | Routed because: belongs later" not in text
    assert "| [HIGH] | critic | new sealed concern |" not in text
    # The new SEAL is under ### Sealed dispositions, not orphaned into Deferred.
    lines = text.splitlines()
    s_idx = lines.index("### Sealed dispositions")
    d_idx = lines.index("### Deferred dispositions")
    seal_line = next(i for i, ln in enumerate(lines) if "[SEAL-01]" in ln)
    assert s_idx < seal_line < d_idx, "[SEAL-01] not in the Sealed section"


def test_reassembly_populated_sealed_populated_deferred(tmp_path):
    """Both sections pre-populated (both replace branches). The new Sealed row
    grows the Sealed block by one line (net +1 delta), shifting Deferred — the
    stale-offset trigger. RED pre-fix, GREEN post-fix.
    """
    artifact = _artifact_with_seals_and_defs(
        tmp_path,
        sealed_body=(
            "- `[SEAL-01]` **Existing seal** (pass 1, user-directed) — Defense: x.\n\n"
        ),
        deferred_body=_TWO_EXISTING_DEFS,
        latest_rows=_NEW_SEAL_PLUS_DEFERRED_LATEST,
    )
    proc = _run_archive_pass([str(artifact), "--phase", "2"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    _assert_panel_intact(text)
    # Existing + new seal both present and sequential.
    assert "[SEAL-01]" in text and "[SEAL-02]" in text
    assert "[DEF-03]" in text
    # Deferred section ends with all three DEF entries in order.
    lines = text.splitlines()
    d_idx = lines.index("### Deferred dispositions")
    next_h = next(
        i for i in range(d_idx + 1, len(lines)) if lines[i].startswith("#")
    )
    window = "\n".join(lines[d_idx:next_h])
    assert window.index("[DEF-01]") < window.index("[DEF-02]") < window.index("[DEF-03]")


def test_reassembly_legacy_auto_insert_deferred(tmp_path):
    """Legacy artifact with NO ### Deferred dispositions heading (triggers the
    auto-insert) PLUS a simultaneous new Sealed + new Deferred. The auto-insert
    adds the section, then both promotions must land correctly in one pass.
    RED pre-fix, GREEN post-fix.
    """
    artifact = _legacy_artifact_without_deferred_section(
        tmp_path, _NEW_SEAL_PLUS_DEFERRED_LATEST
    )
    proc = _run_archive_pass([str(artifact), "--phase", "2"])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    _assert_panel_intact(text)
    assert "### Deferred dispositions" in text  # auto-inserted
    assert "[SEAL-01]" in text
    assert "[DEF-01]" in text  # first DEF in a freshly-inserted section
    # Section order preserved.
    assert (
        text.find("### Sealed dispositions")
        < text.find("### Deferred dispositions")
        < text.find("### Latest pass detail")
        < text.find("## Approval")
    )


def test_apply_edits_rejects_overlapping_ranges():
    """_apply_edits asserts pairwise non-overlap (AD9/I6 precondition)."""
    import pytest

    ap = _load_archive_pass()
    with pytest.raises(AssertionError):
        ap._apply_edits(["a", "b", "c", "d"], [(0, 2, ["X"]), (1, 3, ["Y"])])


def test_apply_edits_applies_descending():
    """Two disjoint edits with different line-count deltas land correctly
    regardless of input order (descending-by-start application)."""
    ap = _load_archive_pass()
    lines = ["0", "1", "2", "3", "4", "5"]
    edits = [(4, 5, ["X"]), (1, 2, ["A1", "A2", "A3"])]
    expected = ["0", "A1", "A2", "A3", "2", "3", "X", "5"]
    assert ap._apply_edits(lines, edits) == expected
    # Order-independent: reversed input yields the identical result.
    assert ap._apply_edits(lines, list(reversed(edits))) == expected
    # Input list is not mutated.
    assert lines == ["0", "1", "2", "3", "4", "5"]


# ---------------------------------------------------------------------------
# R10: orphaned-Trajectory-row guard on the write path (T15 / DEF-15/16).
# ---------------------------------------------------------------------------

_GUARD_TRAJ_HEADER = (
    "## Panel Review\n\n### Trajectory\n\n"
    "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
    "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
)


def _guard_row(p, notes="—"):
    return f"| {p} | 2026-06-12 | 0 | 0 | 0 | 0 | 0 | {notes} |"


def _doc_no_orphan():
    return (
        "# D\n\n" + _GUARD_TRAJ_HEADER
        + _guard_row(1) + "\n" + _guard_row(2) + "\n\n"
        "### Sealed dispositions\n\n_None yet._\n\n"
        "## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    )


def _doc_with_orphan():
    # A `| 29 | ... |` row stranded below the table's blank-line terminator.
    return (
        "# D\n\n" + _GUARD_TRAJ_HEADER
        + _guard_row(1) + "\n" + _guard_row(2) + "\n\n"
        + _guard_row(29) + "\n\n"
        "### Sealed dispositions\n\n_None yet._\n\n"
        "## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `h`\n"
    )


def test_archive_guard_refuses_self_strand(tmp_path):
    # An append whose own write would strand a row (present in new, absent in old)
    # -> the guard refuses (SystemExit), no write performed.
    import pytest
    ap = _load_archive_pass()
    with pytest.raises(SystemExit):
        ap._orphan_guard(tmp_path / "spec.md", _doc_no_orphan(), _doc_with_orphan())


def test_archive_guard_preexisting_orphan_still_appends(tmp_path, capsys):
    # A PRE-EXISTING orphan (present in BOTH old and new) -> the guard SURFACES a
    # non-blocking notice and STILL proceeds (no SystemExit) — the operator is not
    # dead-ended. This pins the prospective-vs-pre-append SET DIFF, not a naive
    # "any orphan present?" check (which would wrongly refuse).
    ap = _load_archive_pass()
    old = _doc_with_orphan()
    new = old.replace(_guard_row(2) + "\n\n", _guard_row(2) + "\n" + _guard_row(3) + "\n\n")
    ap._orphan_guard(tmp_path / "spec.md", old, new)  # must NOT raise
    err = capsys.readouterr().err
    assert ap.ORPHANED_TRAJECTORY_TOKEN in err
    assert "already has an orphaned" in err


def test_archive_guard_dry_run_does_not_exit_on_self_strand(tmp_path, capsys):
    # Code-review fix #7: under dry_run a would-strand write is surfaced as a notice
    # but does NOT raise SystemExit (a preview must be side-effect-free, non-fatal).
    ap = _load_archive_pass()
    ap._orphan_guard(tmp_path / "spec.md", _doc_no_orphan(), _doc_with_orphan(), dry_run=True)
    err = capsys.readouterr().err
    assert ap.ORPHANED_TRAJECTORY_TOKEN in err
    assert "dry-run" in err


def test_archive_normal_trajectory_unaffected(tmp_path):
    # A well-formed Trajectory -> archive behaviour is unchanged (no orphan notice,
    # the Latest pass detail row is promoted to a new contiguous Trajectory row).
    artifact = _artifact_with_trajectory(
        tmp_path,
        [_traj_row(pass_n=1, highs=2, addressed=2)],
        latest_rows="| [HIGH] | critic | concern A | Addressed | fixed in §2 |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    assert "ORPHANED-TRAJECTORY-ROW:" not in proc.stderr
    text = artifact.read_text()
    # behaviour preserved: a new Pass 2 row is appended contiguously
    assert "| 2 " in text or "| 2 |" in text


def test_sealed_rewrite_preserves_interleaved_lines(tmp_path):
    """3.5f: promoting a new seal into a Sealed section that has a non-matching
    line interleaved BETWEEN two existing entries must not delete that line. The
    old whole-span replace (rebuilt from matched lines only) silently dropped it."""
    interleaved = "<!-- operator note: SEAL-02 reviewed 2026-06-13, keep -->"
    sealed_body = (
        "- `[SEAL-01]` **First seal** (pass 1, user-directed) — Defense: a.\n"
        f"{interleaved}\n"
        "- `[SEAL-02]` **Second seal** (pass 1, user-directed) — Defense: b.\n"
        "\n"
    )
    artifact = _artifact_with_seals_and_defs(
        tmp_path,
        sealed_body=sealed_body,
        deferred_body="_None yet._\n\n",
        latest_rows="| [HIGH] | critic | new concern | Sealed | Defense: user-directed keep |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # Existing entries + the interleaved comment all survive...
    assert "[SEAL-01]" in text and "[SEAL-02]" in text
    assert interleaved in text  # would be DELETED by the old span-replace
    # ...and the new seal (SEAL-03) was appended.
    assert "[SEAL-03]" in text


def test_deferred_rewrite_preserves_interleaved_lines(tmp_path):
    """3.5f: same protection for the Deferred section."""
    interleaved = "<!-- DEF-02 superseded by F12; keep for audit -->"
    deferred_body = (
        "- `[DEF-01]` **First** → tasks.md (pass 1) — Routed because: a.\n"
        f"{interleaved}\n"
        "- `[DEF-02]` **Second** → tasks.md (pass 1) — Routed because: b.\n"
        "\n"
    )
    artifact = _artifact_with_seals_and_defs(
        tmp_path,
        sealed_body="_None yet._\n\n",
        deferred_body=deferred_body,
        latest_rows="| [MED] | pragmatist | later | Deferred → tasks.md | Routed because: belongs later |\n",
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    assert "[DEF-01]" in text and "[DEF-02]" in text
    assert interleaved in text  # would be DELETED by the old span-replace
    assert "[DEF-03]" in text


# ============================================================================
# Workflow Context Reduction — R2 mid-loop trajectory trim
# T1: all-modes / both-write-sites / anti-mis-gate / idempotence / orphan /
#     detector-window.  RED until _maybe_trim_trajectory is implemented (T3).
# ============================================================================

_WCR_ELIDED = "earlier passes elided"
# A converged (0-HIGH) Latest row so a NORMAL pass proceeds past the
# "nothing to archive" early-exit and reaches the main write site (:1173).
_WCR_NORMAL_LATEST = "| [LOW] | critic | minor nit | Addressed | fixed |\n"


def _wcr_rows(n, start=1, notes="—"):
    """n NORMAL trajectory-row dicts, passes `start`..`start+n-1`."""
    return [_traj_row(pass_n=i, highs=0, notes=notes) for i in range(start, start + n)]


def _wcr_traj_data_rows(text):
    """Data-row lines of the `### Trajectory` table (real + elided), order-preserving."""
    lines = text.split("\n")
    start = None
    for i, l in enumerate(lines):
        if l.strip() == "### Trajectory":
            start = i
            break
    if start is None:
        return []
    out = []
    started = False
    for l in lines[start + 1:]:
        s = l.strip()
        if s.startswith("### ") or s.startswith("## "):
            break
        if not s.startswith("|"):
            if started:
                break
            continue
        if s.startswith("| Pass ") or set(s) <= set("|-: "):
            started = True
            continue
        started = True
        out.append(l)
    return out


def _wcr_split_traj(text):
    """(real_rows, elided_rows) — elided rows carry the 'N earlier passes elided' note."""
    data = _wcr_traj_data_rows(text)
    real = [r for r in data if _WCR_ELIDED not in r]
    elided = [r for r in data if _WCR_ELIDED in r]
    return real, elided


def _wcr_elided_count(text):
    _, elided = _wcr_split_traj(text)
    if not elided:
        return 0
    m = re.search(r"(\d+) earlier passes elided", elided[0])
    return int(m.group(1)) if m else 0


def _wcr_pass_num(row_line):
    cells = [c.strip() for c in row_line.strip().strip("|").split("|")]
    try:
        return int(cells[0])
    except (ValueError, IndexError):
        return None


def _wcr_legacy_artifact(tmp_path, traj_rows, latest_rows=""):
    """Artifact MISSING `### Deferred dispositions` — reaches the early
    auto-inserted empty-Latest write site (archive_pass.py:943)."""
    body = "".join(
        f"| {r['Pass']} | {r['Date']} | {r['HIGHs']} | {r['Regressions']} | "
        f"{r['Addressed']} | {r['Deferred']} | {r['Sealed']} | {r['Notes']} |\n"
        for r in traj_rows
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
        # deliberately NO ### Deferred dispositions section
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


def test_mid_loop_trim_fires_on_normal(tmp_path):
    """R2: a NORMAL archive of a >15-row `pending` artifact trims to <=15 real
    rows + one elided row (main write site)."""
    artifact = _artifact_with_trajectory(
        tmp_path, _wcr_rows(20), latest_rows=_WCR_NORMAL_LATEST
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    real, elided = _wcr_split_traj(artifact.read_text(encoding="utf-8"))
    assert len(real) <= 15, f"expected trim to <=15 real rows, got {len(real)}"
    assert len(elided) == 1, f"expected exactly one elided row, got {len(elided)}"


def test_mid_loop_trim_fires_on_strict_bar(tmp_path):
    """R2 all-modes: `--strict-bar` archive trims."""
    artifact = _artifact_with_trajectory(tmp_path, _wcr_rows(20))
    proc = _run_archive_pass([str(artifact), "--strict-bar"])
    assert proc.returncode == 0, proc.stderr
    real, elided = _wcr_split_traj(artifact.read_text(encoding="utf-8"))
    assert len(real) <= 15 and len(elided) == 1


def test_mid_loop_trim_fires_on_cross_check(tmp_path):
    """R2 all-modes: `--cross-check` archive trims."""
    artifact = _artifact_with_trajectory(tmp_path, _wcr_rows(20))
    proc = _run_archive_pass([str(artifact), "--cross-check"])
    assert proc.returncode == 0, proc.stderr
    real, elided = _wcr_split_traj(artifact.read_text(encoding="utf-8"))
    assert len(real) <= 15 and len(elided) == 1


def test_mid_loop_trim_fires_on_skip(tmp_path):
    """R2 all-modes: `--skip` archive trims."""
    artifact = _artifact_with_trajectory(tmp_path, _wcr_rows(20))
    proc = _run_archive_pass([str(artifact), "--skip", "mechanical rename"])
    assert proc.returncode == 0, proc.stderr
    real, elided = _wcr_split_traj(artifact.read_text(encoding="utf-8"))
    assert len(real) <= 15 and len(elided) == 1


def test_mid_loop_trim_at_main_write_site(tmp_path):
    """R2 both-sites: the main write (archive_pass.py:1173) trims. A standard
    latest-processing archive reaches write_or_diff at the end of main()."""
    artifact = _artifact_with_trajectory(
        tmp_path, _wcr_rows(20), latest_rows=_WCR_NORMAL_LATEST
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    real, elided = _wcr_split_traj(artifact.read_text(encoding="utf-8"))
    assert len(real) <= 15 and len(elided) == 1


def test_mid_loop_trim_at_early_empty_latest_site(tmp_path):
    """R2 both-sites: the early auto-inserted empty-Latest write
    (archive_pass.py:943) trims too. Reached by a legacy artifact missing
    `### Deferred dispositions`, with an empty Latest and no mode flag."""
    artifact = _wcr_legacy_artifact(tmp_path, _wcr_rows(20), latest_rows="")
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    text = artifact.read_text(encoding="utf-8")
    # confirm the auto-insert path was taken (this is Site-1, not the main write)
    assert "### Deferred dispositions" in text, "expected the :943 auto-insert path"
    real, elided = _wcr_split_traj(text)
    assert len(real) <= 15, f"Site-1 trim did not fire: {len(real)} real rows"
    assert len(elided) == 1


def test_never_approved_pending_artifact_is_trimmed(tmp_path):
    """R2 anti-mis-gate: a never-approved `pending` artifact (no `**Hash basis:**`
    line, so read_hash_basis == 'v1') is TRIMMED — the explicit regression against
    a bare-`v2` gate that would wrongly hold the trim back for this population."""
    artifact = _artifact_with_trajectory(
        tmp_path, _wcr_rows(20), latest_rows=_WCR_NORMAL_LATEST
    )
    seed = artifact.read_text(encoding="utf-8")
    assert "- [ ] Approved" in seed and "**Hash basis:**" not in seed
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    real, elided = _wcr_split_traj(artifact.read_text(encoding="utf-8"))
    assert len(real) <= 15 and len(elided) == 1


def test_repeated_archive_merges_elided_count_cumulatively(tmp_path):
    """R2 idempotence: repeated trimming archives merge into ONE elided row with a
    cumulative (not double-counted) count, and the orphan-guard is not tripped."""
    artifact = _artifact_with_trajectory(tmp_path, _wcr_rows(20))
    proc1 = _run_archive_pass([str(artifact), "--skip", "mechanical one"])
    assert proc1.returncode == 0, proc1.stderr
    count1 = _wcr_elided_count(artifact.read_text(encoding="utf-8"))
    proc2 = _run_archive_pass([str(artifact), "--skip", "mechanical two"])
    assert proc2.returncode == 0, proc2.stderr
    text2 = artifact.read_text(encoding="utf-8")
    _, elided2 = _wcr_split_traj(text2)
    assert len(elided2) == 1, "elided rows must merge into ONE, not accumulate"
    assert _wcr_elided_count(text2) > count1, "elided count must grow cumulatively"
    assert "refusing to write" not in proc2.stderr


def test_orphan_guard_not_tripped_by_trim(tmp_path):
    """R2: the trim inserts a contiguous elided row, so `_orphan_guard` stays
    clean (exit 0, no refusal)."""
    artifact = _artifact_with_trajectory(
        tmp_path, _wcr_rows(20), latest_rows=_WCR_NORMAL_LATEST
    )
    proc = _run_archive_pass([str(artifact)])
    assert proc.returncode == 0, proc.stderr
    assert "refusing to write" not in proc.stderr and "would strand" not in proc.stderr
    real, elided = _wcr_split_traj(artifact.read_text(encoding="utf-8"))
    assert len(real) <= 15 and len(elided) == 1


def test_detector_window_preserves_last_two_normal_rows(tmp_path):
    """R2 detector-window margin: with keep=15 (>> the strict-bar/halt detector
    reach), the trim BOTH fires (<=15 real rows — the RED teeth before T3) AND
    leaves the last 2 rows and last 2 NORMAL rows intact. 19 NORMAL seed rows +
    a `--strict-bar` archive appends pass 20 (non-NORMAL): last 2 rows = 19,20;
    last 2 NORMAL = 18,19."""
    artifact = _artifact_with_trajectory(tmp_path, _wcr_rows(19))
    proc = _run_archive_pass([str(artifact), "--strict-bar"])
    assert proc.returncode == 0, proc.stderr
    real, _ = _wcr_split_traj(artifact.read_text(encoding="utf-8"))
    assert len(real) <= 15, f"trim did not fire: {len(real)} real rows"
    passes = [_wcr_pass_num(r) for r in real]
    for p in (18, 19, 20):
        assert p in passes, f"pass {p} must survive the trim (detector window); got {passes}"


# ============================================================================
# Workflow Context Reduction — R2 committed-v1 gate semantics
# T2: v2 hash-neutrality / v1-committed skip / approval byte-identity.
#     RED until _maybe_trim_trajectory is implemented (T3).
# ============================================================================

_WCR_APPROVAL_V2 = (
    "## Approval\n\n"
    "- [x] Approved to proceed to implementation\n"
    "- **Content Hash:** `0123456789abcdef`\n"
    "- **Hash basis:** v2\n"
)
_WCR_APPROVAL_V1_COMMITTED = (
    "## Approval\n\n"
    "- [x] Approved to proceed to implementation\n"
    "- **Content Hash:** `0123456789abcdef`\n"
)
_WCR_APPROVAL_PENDING = (
    "## Approval\n\n"
    "- [ ] Approved to proceed to implementation\n"
    "- **Content Hash:** `pending`\n"
)
_WCR_APPROVAL_V1_MALFORMED_HASH = (
    "## Approval\n\n"
    "- [x] Approved to proceed to implementation\n"
    "- **Content Hash:** `not-a-real-hash`\n"
)


def _wcr_traj_body(n):
    """`n` NORMAL trajectory data-row lines (passes 1..n)."""
    return "".join(
        f"| {i} | 2026-05-15 | 0 | 0 | 0 | 0 | 0 | — |\n" for i in range(1, n + 1)
    )


def _wcr_doc(traj_body, approval):
    return (
        "# Doc\n\n"
        "## Panel Review\n\n"
        "### Trajectory\n\n"
        "| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |\n"
        "|------|------|-------|-------------|-----------|----------|--------|-------|\n"
        f"{traj_body}"
        "\n"
        "### Sealed dispositions\n\n"
        "_None yet._\n\n"
        "### Latest pass detail\n\n"
        "| Severity | Source | Concern | Disposition | Notes |\n"
        "|----------|--------|---------|-------------|-------|\n"
        "\n"
        f"{approval}"
    )


def _wcr_import_content_hash():
    # _load_archive_pass() puts telescoping-sdd/scripts on sys.path.
    _load_archive_pass()
    import importlib

    return importlib.import_module("content_hash")


def test_mid_loop_trim_hash_neutral_for_v2_approved():
    """R2: trimming a v2-approved artifact mid-loop leaves its content hash
    unchanged (content_for_hashing strips `### Trajectory` rows before hashing)."""
    ap = _load_archive_pass()
    ch = _wcr_import_content_hash()
    content = _wcr_doc(_wcr_traj_body(25), _WCR_APPROVAL_V2)
    before = ch.compute_content_hash(content)
    trimmed = ap._maybe_trim_trajectory(content, content)
    # the v2 artifact is NOT gated — the trim must actually fire
    real, elided = _wcr_split_traj(trimmed)
    assert len(real) <= 15 and len(elided) == 1, "v2 artifact should be trimmed"
    assert ch.compute_content_hash(trimmed) == before, "v2 trim must be hash-neutral"


def test_v1_committed_artifact_not_trimmed_mid_loop():
    """R2: a genuine v1-committed artifact (approved, basis 'v1', non-'pending'
    stored hash) is left UNTRIMMED mid-loop — its committed hash cannot drift."""
    ap = _load_archive_pass()
    ch = _wcr_import_content_hash()
    content = _wcr_doc(_wcr_traj_body(25), _WCR_APPROVAL_V1_COMMITTED)
    # the three-predicate skip case holds
    assert ch.has_approval(content)
    assert ch.read_hash_basis(content) == "v1"
    assert ch.read_stored_hash(content) != "pending"
    result = ap._maybe_trim_trajectory(content, content)
    assert result == content, "v1-committed artifact must NOT be trimmed mid-loop"
    assert len(_wcr_split_traj(result)[0]) == 25, "all 25 rows must be untouched"


def test_v1_malformed_hash_is_trimmed_not_treated_as_committed():
    """R2 fix: a checked-approval, v1-basis artifact whose stored hash is present
    but NOT well-formed 16-hex (a corrupted/hand-edited stamp) must NOT be read
    as "a genuine committed v1 hash" — it must be trimmed like any other
    non-committed artifact, mirroring changed_since_stamp/is_basis_migration_only's
    fail-closed handling of a malformed stored hash."""
    ap = _load_archive_pass()
    ch = _wcr_import_content_hash()
    content = _wcr_doc(_wcr_traj_body(25), _WCR_APPROVAL_V1_MALFORMED_HASH)
    assert ch.has_approval(content)
    assert ch.read_hash_basis(content) == "v1"
    assert ch.read_stored_hash(content) == "not-a-real-hash"
    assert not ch._is_valid_16_hex(ch.read_stored_hash(content))
    result = ap._maybe_trim_trajectory(content, content)
    assert result != content, "malformed v1 hash must NOT be treated as committed"
    assert len(_wcr_split_traj(result)[0]) < 25, "trajectory must be trimmed"


def test_approval_time_trajectory_byte_identical_to_pre_change():
    """R2: a run that mid-loop-trims and then reaches the approval trim yields a
    `### Trajectory` byte-identical to the pre-change approval-only trim.

    Both paths are driven from ONE shared row-set via `trim_trajectory_table`'s
    idempotent cumulative-elided merge — no external 'before' artifact needed.
    """
    ap = _load_archive_pass()
    from blueprint_common import trim_trajectory_table

    content = _wcr_doc(_wcr_traj_body(25), _WCR_APPROVAL_PENDING)
    assert len(_wcr_split_traj(content)[0]) > 15, "setup must exercise the trim"
    # (b) pre-change approval-only behavior: no mid-loop trim, a single approval trim
    approve_only = trim_trajectory_table(content)
    # (a) new behavior: several mid-loop trims (the gated helper), then the approval trim
    mid = content
    for _ in range(3):
        mid = ap._maybe_trim_trajectory(mid, mid)
    mid_then_approve = trim_trajectory_table(mid)
    assert mid_then_approve == approve_only, (
        "mid-loop-then-approve must equal approve-only (trim idempotence)"
    )
