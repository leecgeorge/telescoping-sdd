"""Decision-E approval gate for validate_spec.py --approve (audit R1.4).

validate_spec --approve previously stamped any document that passed only the
directory<->identifier cross-check, with no content validation — so a
structurally broken spec/design/tasks could be approved, recreating the
"approved, but next validate FAILs" state the blueprint validator's Decision-E
gate exists to prevent. These tests pin the ported gate and its --force
override, plus the --task-tick carve-out that intentionally skips it.
"""

import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
_VS = _SCRIPTS.parent / "skills" / "spec-driven-dev" / "scripts" / "validate_spec.py"


def _run_vs(*args):
    return subprocess.run(
        [sys.executable, str(_VS), *args], capture_output=True, text=True
    )


def _broken_spec_dir(root: Path, name: str = "F1-demo") -> Path:
    """A spec dir that PASSES the directory<->identifier cross-check but FAILS
    content validation (missing required sections, a [TBD], no Panel Review)."""
    d = root / "specs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(
        "# F1: Demo\n\n"
        "**PLAN feature identifier:** `F1`\n\n"
        "## Objective\n\n"
        "Do a thing. [TBD — needs input]\n\n"
        "## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    return d


def _stored_hash(spec_md: Path) -> str:
    for line in spec_md.read_text(encoding="utf-8").splitlines():
        if "**Content Hash:**" in line:
            return line.split("`")[1]
    return ""


def test_approve_refuses_structurally_broken_spec(tmp_path):
    d = _broken_spec_dir(tmp_path)
    before = (d / "spec.md").read_bytes()
    r = _run_vs(str(d), "--approve", "spec", "--project-root", str(tmp_path))
    assert r.returncode == 1, r.stdout
    assert "Refusing to approve spec.md" in r.stdout
    assert "validation FAILed" in r.stdout
    # The document is NOT stamped — still the pending sentinel, byte-identical.
    assert (d / "spec.md").read_bytes() == before
    assert _stored_hash(d / "spec.md") == "pending"


def test_approve_force_overrides_the_gate(tmp_path):
    d = _broken_spec_dir(tmp_path)
    r = _run_vs(str(d), "--approve", "spec", "--force", "--project-root", str(tmp_path))
    assert r.returncode == 0, r.stdout
    assert "Approved:" in r.stdout
    # --force stamped a real hash over the broken doc (user takes responsibility).
    assert _stored_hash(d / "spec.md") not in ("", "pending")


def test_approve_no_approval_section_exits_nonzero(tmp_path):
    """A document with no `## Approval` section is refused with a non-zero exit,
    not a false 'Approved:' on exit 0 (audit R1.5)."""
    d = tmp_path / "specs" / "F1-demo"
    d.mkdir(parents=True)
    body = "# F1: Demo\n\n**PLAN feature identifier:** `F1`\n\n## Objective\n\nx\n"
    (d / "spec.md").write_text(body, encoding="utf-8")
    r = _run_vs(str(d), "--approve", "spec", "--force", "--project-root", str(tmp_path))
    assert r.returncode == 1, (r.stdout, r.stderr)
    assert "Approved:" not in r.stdout
    assert "no `## Approval` section" in r.stderr
    # The file is untouched.
    assert (d / "spec.md").read_text(encoding="utf-8") == body


def test_approve_malformed_approval_section_exits_nonzero(tmp_path):
    """A `## Approval` section missing its Content-Hash line makes the substitution
    no-op; approval must fail (nothing stamped) rather than print a false success."""
    d = tmp_path / "specs" / "F1-demo"
    d.mkdir(parents=True)
    body = (
        "# F1: Demo\n\n**PLAN feature identifier:** `F1`\n\n## Objective\n\nx\n\n"
        "## Approval\n\n- [ ] Approved to proceed to next phase\n"  # no Content Hash line
    )
    (d / "spec.md").write_text(body, encoding="utf-8")
    r = _run_vs(str(d), "--approve", "spec", "--force", "--project-root", str(tmp_path))
    assert r.returncode == 1, (r.stdout, r.stderr)
    assert "Approved:" not in r.stdout
    assert "nothing stamped" in r.stderr
    # The checkbox was NOT flipped — nothing was written.
    assert "- [ ] Approved to proceed" in (d / "spec.md").read_text(encoding="utf-8")


def test_bom_artifact_approves_and_revalidates_clean(tmp_path):
    """A UTF-8 BOM artifact must not wedge at 'stale hash' (audit R2.5). Approval
    reads BOM-tolerantly and rewrites without the BOM; re-validation matches."""
    d = tmp_path / "specs" / "F1-demo"
    d.mkdir(parents=True)
    body = (
        "# F1: Demo\n\n**PLAN feature identifier:** `F1`\n\n## Objective\n\nx\n\n"
        "## Approval\n\n- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n"
    )
    (d / "spec.md").write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))  # UTF-8 BOM
    r = _run_vs(str(d), "--approve", "spec", "--force", "--project-root", str(tmp_path))
    assert r.returncode == 0, (r.stdout, r.stderr)
    # The rewrite dropped the BOM and stamped a real hash.
    assert not (d / "spec.md").read_bytes().startswith(b"\xef\xbb\xbf")
    assert _stored_hash(d / "spec.md") not in ("", "pending")
    # Re-validating the now-approved doc shows no stale-hash FAIL.
    v = _run_vs(str(d), "--phase", "spec", "--project-root", str(tmp_path))
    assert "stale" not in v.stdout.lower()


def test_mode_flags_are_mutually_exclusive(tmp_path):
    """--approve and --set-language are mutually exclusive: argparse rejects the
    combination (exit 2) instead of silently dropping the language write (I3.2)."""
    d = _broken_spec_dir(tmp_path)
    r = _run_vs(str(d), "--approve", "spec", "--set-language", "java",
                "--project-root", str(tmp_path))
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "not allowed with argument" in r.stderr
    # Nothing was approved and no language was persisted.
    assert _stored_hash(d / "spec.md") == "pending"
    assert not (tmp_path / ".sdd" / "architecture.json").exists()


def test_approve_design_blocked_when_spec_not_approved(tmp_path):
    """The design/tasks validators run check_previous_phase_approved, so the
    gate also enforces Specify -> Design -> Tasks ordering on the approve path."""
    d = _broken_spec_dir(tmp_path)  # spec.md is unapproved (pending)
    (d / "design.md").write_text(
        "# Design\n\n## Approval\n\n"
        "- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    r = _run_vs(str(d), "--approve", "design", "--project-root", str(tmp_path))
    assert r.returncode == 1, r.stdout
    assert "Refusing to approve design.md" in r.stdout
    assert _stored_hash(d / "design.md") == "pending"


def test_approve_corrupt_marker_on_restamp_exits_nonzero(tmp_path):
    """R2.6: a re-stamp whose obligation cannot be recorded because
    .sdd/pending-review.json is corrupt must surface loudly and exit non-zero —
    not raise an uncaught traceback after the document was already stamped."""
    d = tmp_path / "specs" / "F1-demo"
    d.mkdir(parents=True)
    spec = d / "spec.md"
    spec.write_text(
        "# F1: Demo\n\n**PLAN feature identifier:** `F1`\n\n## Objective\n\nfirst\n\n"
        "## Approval\n\n- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n",
        encoding="utf-8",
    )
    # 1) Clean first approval (no marker yet).
    r1 = _run_vs(str(d), "--approve", "spec", "--force", "--project-root", str(tmp_path))
    assert r1.returncode == 0, (r1.stdout, r1.stderr)
    # 2) Edit the body so the next approve is a CHANGED re-stamp (creates an
    #    obligation -> reads the marker).
    spec.write_text(spec.read_text(encoding="utf-8").replace("first", "second edited"), encoding="utf-8")
    # 3) Corrupt the marker.
    sdd = tmp_path / ".sdd"
    sdd.mkdir(exist_ok=True)
    (sdd / "pending-review.json").write_text("{ <<<<<<< conflict not json", encoding="utf-8")
    # 4) Re-approve: stamped, but the obligation can't be recorded.
    r2 = _run_vs(str(d), "--approve", "spec", "--force", "--project-root", str(tmp_path))
    assert r2.returncode == 1, (r2.stdout, r2.stderr)
    assert "was NOT recorded" in r2.stderr
    # The document IS stamped (atomic) — the hash reflects the edited content.
    assert _stored_hash(spec) not in ("", "pending")
