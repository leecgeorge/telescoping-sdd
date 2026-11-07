"""Unit D (R2, C1): `archive_pass.py --zone-diff <draft>`, scope-verify check (a).

The hard-fail zone runs from the `### Sealed dispositions` heading that
`find_section` locates inside `## Panel Review` to end of file (the whole file
when there is none), compared after trailing-whitespace normalisation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import archive_pass as ap  # noqa: E402

_ARCHIVE = _SCRIPTS / "archive_pass.py"

LIVE = """# Spec

## Objective

x

## Panel Review

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|
| 1 | 2026-11-07 | 0 | 0 | 0 | 0 | 0 | converged (0 HIGH) |

### Sealed dispositions

- `[SEAL-01]` **A thing** (pass 1, critic) — Defense: it is fine.

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [ ] Approved to proceed to next phase
- **Content Hash:** `pending`
"""


def _run(art, draft, *flags, phase="1"):
    return subprocess.run([sys.executable, str(_ARCHIVE), str(art), "--phase", phase,
                           "--zone-diff", str(draft), *flags],
                          capture_output=True, text=True)


def test_zone_diff_identical_zones_empty():
    body_edit = LIVE.replace("## Objective\n\nx\n", "## Objective\n\ny, edited\n")
    assert ap.zone_diff(LIVE, LIVE) == []
    assert ap.zone_diff(LIVE, body_edit) == []


def test_zone_diff_one_char_defense_change_reported():
    draft = LIVE.replace("it is fine.", "it is fine!")
    out = ap.zone_diff(LIVE, draft)
    assert out and any("it is fine!" in l for l in out)


def test_zone_diff_trailing_whitespace_only_clean():
    draft = LIVE.replace("it is fine.\n", "it is fine.   \n").replace(
        "- **Content Hash:** `pending`\n", "- **Content Hash:** `pending`\t\n")
    assert ap.zone_diff(LIVE, draft) == []


def test_zone_diff_no_sealed_heading_whole_file_is_zone():
    live = "# Doc\n\nbody\n"
    assert ap.zone_diff(live, live) == []
    assert ap.zone_diff(live, "# Doc\n\nbody changed\n") != []


def test_zone_diff_fenced_sealed_quote_after_real_section_ignored():
    fenced = ("\n```\n### Sealed dispositions\n- quoted example\n```\n")
    live = LIVE.replace("## Approval\n", fenced + "\n## Approval\n")
    draft = live.replace("it is fine.", "changed defense")
    # The real section (not the fenced quote) starts the zone, so the change
    # above the fence is still inside it.
    assert ap.zone_diff(live, draft) != []
    assert ap.zone_diff(live, live) == []


def test_zone_diff_bom_prefixed_draft_reads_clean(tmp_path):
    art = tmp_path / "01_spec.md"
    art.write_text(LIVE, encoding="utf-8")
    draft = tmp_path / "01_spec-draft-p1.md"
    draft.write_bytes(b"\xef\xbb\xbf" + LIVE.encode("utf-8"))
    r = _run(art, draft)
    assert (r.returncode, r.stdout) == (0, "ZONE-DIFF: clean\n"), r.stderr


@pytest.mark.parametrize("kind", ["missing", "directory", "invalid-utf8"])
def test_zone_diff_unreadable_draft_exits_3_never_clean(tmp_path, kind):
    art = tmp_path / "01_spec.md"
    art.write_text(LIVE, encoding="utf-8")
    draft = tmp_path / "draft.md"
    if kind == "directory":
        draft.mkdir()
    elif kind == "invalid-utf8":
        draft.write_bytes(b"\xff\xfe\x00bad")
    r = _run(art, draft)
    assert r.returncode == 3
    assert r.stderr.startswith(f"error: cannot read draft {draft} (")
    assert "clean" not in r.stdout


def test_zone_diff_cli_exit_0_clean_and_4_differs(tmp_path):
    art = tmp_path / "01_spec.md"
    art.write_text(LIVE, encoding="utf-8")
    same = tmp_path / "same.md"
    same.write_text(LIVE.replace("x\n", "x, body edit\n", 1), encoding="utf-8")
    assert _run(art, same).stdout == "ZONE-DIFF: clean\n"
    other = tmp_path / "other.md"
    other.write_text(LIVE.replace("it is fine.", "edited"), encoding="utf-8")
    r = _run(art, other)
    assert r.returncode == ap.EXIT_ZONE_DIFFERS == 4
    assert "edited" in r.stdout and "clean" not in r.stdout
    assert art.read_text(encoding="utf-8") == LIVE  # read-only


def test_zone_diff_works_on_terminal_artifact_without_terminal_flag(tmp_path):
    art = tmp_path / "03_tasks.md"
    art.write_text(LIVE, encoding="utf-8")
    r = _run(art, art, phase="3")
    assert (r.returncode, r.stdout) == (0, "ZONE-DIFF: clean\n"), r.stderr
