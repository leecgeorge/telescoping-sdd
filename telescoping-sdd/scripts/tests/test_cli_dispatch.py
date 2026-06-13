"""Subprocess tests for validator main() dispatch paths (audit R2.2).

These argparse-to-function dispatch handlers had zero coverage — the library
functions underneath were unit-tested, but the main() wiring (marker-root
resolution, exit codes, gate ordering, stdout messages) was exercised by no
test, so a refactor regression would pass the suite silently. These pin the
current behavior so the R2.1 consolidation has a regression guard.
"""

import importlib
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
_VB = _SCRIPTS.parent / "skills" / "project-blueprint" / "scripts" / "validate_blueprint.py"
_VS = _SCRIPTS.parent / "skills" / "spec-driven-dev" / "scripts" / "validate_spec.py"


def _bc():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    return importlib.import_module("blueprint_common")


def _arch_config():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    return importlib.import_module("arch_config")


def _run_vb(*args):
    return subprocess.run([sys.executable, str(_VB), *args], capture_output=True, text=True)


def _run_vs(*args):
    return subprocess.run([sys.executable, str(_VS), *args], capture_output=True, text=True)


def _blueprint_dir(root: Path) -> Path:
    d = root / "blueprint"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# validate_blueprint --write-arch-config (the arch-config seam producer CLI)
# ---------------------------------------------------------------------------

def test_write_arch_config_success(tmp_path):
    bp = _blueprint_dir(tmp_path)
    (bp / "ARCHITECTURE.md").write_text(
        "# Architecture\n\n## Technology Choices\n\n**Architecture token:** `java`\n",
        encoding="utf-8",
    )
    r = _run_vb(str(bp), "--write-arch-config")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "Persisted stack 'java'" in r.stdout
    cfg = _arch_config().read_arch_config(bp, project_root=tmp_path)
    assert cfg is not None and cfg["language"] == "java"


def test_write_arch_config_missing_architecture(tmp_path):
    bp = _blueprint_dir(tmp_path)  # no ARCHITECTURE.md
    r = _run_vb(str(bp), "--write-arch-config")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "does not exist" in r.stdout


def test_write_arch_config_no_token(tmp_path):
    bp = _blueprint_dir(tmp_path)
    (bp / "ARCHITECTURE.md").write_text("# Architecture\n\nno token here\n", encoding="utf-8")
    r = _run_vb(str(bp), "--write-arch-config")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "no '**Architecture token:**" in r.stdout


def test_write_arch_config_unknown_token(tmp_path):
    bp = _blueprint_dir(tmp_path)
    (bp / "ARCHITECTURE.md").write_text(
        "# Architecture\n\n**Architecture token:** `rust`\n", encoding="utf-8"
    )
    r = _run_vb(str(bp), "--write-arch-config")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "not recognized" in r.stdout


# ---------------------------------------------------------------------------
# validate_blueprint --decline-pending / --restore-anchor
# ---------------------------------------------------------------------------

def test_decline_pending_clears_seeded_entry(tmp_path):
    bp = _blueprint_dir(tmp_path)
    bc = _bc()
    bc.upsert_pending_entry(tmp_path, "blueprint/SCOPE.md", "a" * 16, "t", 1)
    r = _run_vb(str(bp), "--decline-pending", "--project-root", str(tmp_path))
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "Declined upstream panel re-review" in r.stdout
    assert "blueprint/SCOPE.md" in r.stdout
    # The entry is gone.
    assert bc.clear_pending_entries_for_prefix(tmp_path, "blueprint") == []


def test_decline_pending_no_entries(tmp_path):
    bp = _blueprint_dir(tmp_path)
    r = _run_vb(str(bp), "--decline-pending", "--project-root", str(tmp_path))
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "No pending-review entries found" in r.stdout


def test_restore_anchor_no_restorable(tmp_path):
    bp = _blueprint_dir(tmp_path)
    r = _run_vb(str(bp), "--restore-anchor", "--project-root", str(tmp_path))
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "No restorable obligations" in r.stdout


# ---------------------------------------------------------------------------
# validate_spec --set-language (the SDD-side persisted-store write path)
# ---------------------------------------------------------------------------

def test_set_language_round_trip(tmp_path):
    d = tmp_path / "specs" / "F1-x"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# F1\n\n## Objective\n\nx\n", encoding="utf-8")
    r = _run_vs(str(d), "--set-language", "python", "--project-root", str(tmp_path))
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "Persisted stack 'python'" in r.stdout
    cfg = _arch_config().read_arch_config(d, project_root=tmp_path)
    assert cfg is not None and cfg["language"] == "python"


def test_spec_decline_pending_clears_seeded_entry(tmp_path):
    d = tmp_path / "specs" / "F1-x"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# F1\n\n## Objective\n\nx\n", encoding="utf-8")
    bc = _bc()
    bc.upsert_pending_entry(tmp_path, "specs/F1-x/spec.md", "a" * 16, "t", 1)
    r = _run_vs(str(d), "--decline-pending", "--project-root", str(tmp_path))
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "specs/F1-x/spec.md" in r.stdout
    assert bc.clear_pending_entries_for_prefix(tmp_path, "specs/F1-x") == []


def test_spec_restore_anchor_no_restorable(tmp_path):
    d = tmp_path / "specs" / "F1-x"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# F1\n\n## Objective\n\nx\n", encoding="utf-8")
    r = _run_vs(str(d), "--restore-anchor", "--project-root", str(tmp_path))
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "No restorable obligations" in r.stdout
