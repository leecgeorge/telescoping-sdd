"""Regression guard for the security-exposure-seam feature (R5).

Asserts the exposure-triage (1a), doctrine + response-rule (2b), sequencing-check
(2a-lite), and security-reviewer cross-check (C9) controls are PRESENT — within their
named `##` sections, or file-wide for the inline back-links — mirrored across both
tiers, that the back-links resolve to a real target heading, that the three-panelist
invariant is intact (no 4th seat), and that the v2.1.0 release metadata is in lockstep.

See specs/security-exposure-seam/{spec,design,tasks}.md (R1-R6; anchors A1-A7; DM1-DM4).

`SectionMissingError` / `extract_section` are copied BY CONTENT from
test_write_inversion.py (content-first signature `extract_section(text, heading, path)`;
full-line heading match; heading line excluded from the body; raises on absence). This
is deliberately NOT the `_panel_doc_helpers.py` variant (regex/DOTALL, heading-inclusive,
`pytest.fail`), which is semantically incompatible with these SectionMissingError-based
assertions.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

# --- Target files ---
PHASE_SPECIFY = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/phase-specify.md"
PHASE_SCOPE = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/phase-scope.md"
PHASE_PLAN = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/phase-plan.md"
PHASE_TASKS = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/phase-tasks.md"
DEVILS_ADVOCATE = _REPO_ROOT / "telescoping-sdd/agents/devils-advocate.md"
DELIVERY_MANAGER = _REPO_ROOT / "telescoping-sdd/agents/delivery-manager.md"
SECURITY_REVIEWER = _REPO_ROOT / "telescoping-sdd/agents/security-reviewer.md"
PANEL_REVIEW_SDD = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references/panel-review.md"
PANEL_REVIEW_BLUEPRINT = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references/panel-review.md"
PLUGIN_JSON = _REPO_ROOT / "telescoping-sdd/.claude-plugin/plugin.json"
MARKETPLACE_JSON = _REPO_ROOT / ".claude-plugin/marketplace.json"
CHANGELOG = _REPO_ROOT / "CHANGELOG.md"

# --- Structural anchors (verbatim from the canonical blocks; the new ones A4/A5/A6/A7
# had zero pre-patch occurrences across the tree, so a file-wide search is non-vacuous). ---
A1_TRIAGE = "An un-installed or un-hardened intermediate state served publicly is a FINDING"
A2_DOCTRINE = "(i) ship its own hardening in the same feature, or (ii)"
A3_SEQUENCING = "name the interim mitigation or reorder"
A4_BACKLINK = "consult the Exposure Doctrine before approving the ordering"
A5_RESPONSE = "raise it as an `[upstream]`-tagged concern"
A6_UNCONDITIONAL = (
    "blesses an un-installed or un-hardened public endpoint as an expected PASS state is itself the FINDING"
)
A7_CROSSCHECK = "reachable before its hardening is a FINDING"

# Set-equality targets for the three-panelist invariant (DM4).
EXPECTED_AUTHORING_PANEL = frozenset(
    {"telescoping-sdd:user-advocate", "telescoping-sdd:devils-advocate", "telescoping-sdd:pragmatist"}
)
EXPECTED_DELIVERY_PANEL = frozenset(
    {"telescoping-sdd:delivery-manager", "telescoping-sdd:critic", "telescoping-sdd:simplifier"}
)

EXPECTED_VERSION = "2.4.0"
CHANGELOG_FIRST_ENTRY = "## 2.4.0 — Pending-review churn fix (hash-basis v2)"  # em-dash U+2014, NOT a hyphen-minus


class SectionMissingError(AssertionError):
    """Raised when an expected section/block is absent — surfaces as a named test failure."""

    def __init__(self, path: Path, target: str) -> None:
        super().__init__(f"{path}: expected section/block not found: {target!r}")


def extract_section(text: str, heading: str, path: Path = Path("<unknown>")) -> str:
    """Return a '##'-level section body (heading line excluded), bounded by the next '##'.

    Heading match is full-line, so '## Exposure Doctrine' does not collide with a longer
    heading. Raises SectionMissingError (not pytest.fail; not '') if the heading is absent.
    """
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.rstrip("\n\r ") == heading.rstrip():
            start = i + 1
            break
    if start is None:
        raise SectionMissingError(path, heading)
    section_lines = []
    for line in lines[start:]:
        if line.startswith("##"):
            break
        section_lines.append(line)
    return "".join(section_lines)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _panel_tokens(content: str, phase_label: str, path: Path) -> frozenset:
    """Collect the `telescoping-sdd:<name>` tokens on the single `**<Phase>:**` bullet line
    inside `## Panelists per phase`. Tokens are read from that ONE physical line only (not the
    whole section), so the Design/Architecture bullet's tokens do not leak in. Set-equality
    against this catches a missing panelist, a 4th seat, and a name-swap in one assertion (DM4).
    """
    section = extract_section(content, "## Panelists per phase", path)
    for line in section.splitlines():
        if phase_label in line:
            return frozenset(re.findall(r"telescoping-sdd:[\w-]+", line))
    raise SectionMissingError(path, f"panelist bullet {phase_label!r}")


# --- R1: triage anchor (A1) — per tier + mirror conjunction ---
def test_triage_sdd_anchor():
    body = extract_section(_read(PHASE_SPECIFY), "## Network Exposure Triage", PHASE_SPECIFY)
    assert A1_TRIAGE in body


def test_triage_blueprint_anchor():
    body = extract_section(_read(PHASE_SCOPE), "## Network Exposure Triage", PHASE_SCOPE)
    assert A1_TRIAGE in body


def test_triage_mirror_invariant():
    sdd = extract_section(_read(PHASE_SPECIFY), "## Network Exposure Triage", PHASE_SPECIFY)
    blueprint = extract_section(_read(PHASE_SCOPE), "## Network Exposure Triage", PHASE_SCOPE)
    assert A1_TRIAGE in sdd
    assert A1_TRIAGE in blueprint


# --- R2: doctrine anchor (A2) — per tier + mirror conjunction ---
def test_doctrine_sdd_anchor():
    body = extract_section(_read(PHASE_SPECIFY), "## Exposure Doctrine", PHASE_SPECIFY)
    assert A2_DOCTRINE in body


def test_doctrine_blueprint_anchor():
    body = extract_section(_read(PHASE_SCOPE), "## Exposure Doctrine", PHASE_SCOPE)
    assert A2_DOCTRINE in body


def test_doctrine_mirror_invariant():
    sdd = extract_section(_read(PHASE_SPECIFY), "## Exposure Doctrine", PHASE_SPECIFY)
    blueprint = extract_section(_read(PHASE_SCOPE), "## Exposure Doctrine", PHASE_SCOPE)
    assert A2_DOCTRINE in sdd
    assert A2_DOCTRINE in blueprint


# --- R3: sequencing check anchor (A3) ---
def test_sequencing_anchor():
    body = extract_section(_read(DELIVERY_MANAGER), "## Exposure Sequencing Check", DELIVERY_MANAGER)
    assert A3_SEQUENCING in body


# --- R2: back-link presence (A4) + response rule (A5), file-wide (inline prose, not a heading) ---
def test_backlink_plan_presence():
    assert A4_BACKLINK in _read(PHASE_PLAN)


def test_backlink_tasks_presence():
    assert A4_BACKLINK in _read(PHASE_TASKS)


def test_backlink_plan_response_rule():
    assert A5_RESPONSE in _read(PHASE_PLAN)


def test_backlink_tasks_response_rule():
    assert A5_RESPONSE in _read(PHASE_TASKS)


# --- R2: back-link resolution — the same-tier target heading must exist (no dangling reference).
# Bare call: an unhandled SectionMissingError fails the test directly. ---
def test_backlink_plan_resolution():
    # phase-plan.md (blueprint tier) back-link resolves against phase-scope.md
    extract_section(_read(PHASE_SCOPE), "## Exposure Doctrine", PHASE_SCOPE)


def test_backlink_tasks_resolution():
    # phase-tasks.md (SDD tier) back-link resolves against phase-specify.md
    extract_section(_read(PHASE_SPECIFY), "## Exposure Doctrine", PHASE_SPECIFY)


# --- R1: devils-advocate independent audit (A1 + the A6 unconditional obligation) ---
def test_devils_advocate_triage_section():
    body = extract_section(_read(DEVILS_ADVOCATE), "## Exposure Triage", DEVILS_ADVOCATE)
    assert A1_TRIAGE in body


def test_devils_advocate_unconditional_obligation():
    body = extract_section(_read(DEVILS_ADVOCATE), "## Exposure Triage", DEVILS_ADVOCATE)
    assert A6_UNCONDITIONAL in body


# --- Three-panelist invariant (no 4th seat) — both copies, set-equality per phase bullet ---
def test_panelist_invariant_sdd():
    content = _read(PANEL_REVIEW_SDD)
    assert _panel_tokens(content, "**Specify:**", PANEL_REVIEW_SDD) == EXPECTED_AUTHORING_PANEL
    assert _panel_tokens(content, "**Tasks:**", PANEL_REVIEW_SDD) == EXPECTED_DELIVERY_PANEL


def test_panelist_invariant_blueprint():
    content = _read(PANEL_REVIEW_BLUEPRINT)
    assert _panel_tokens(content, "**Scope:**", PANEL_REVIEW_BLUEPRINT) == EXPECTED_AUTHORING_PANEL
    assert _panel_tokens(content, "**Plan:**", PANEL_REVIEW_BLUEPRINT) == EXPECTED_DELIVERY_PANEL


# --- R6: version lockstep + changelog em-dash heading ---
def test_version_plugin_json():
    data = json.loads(_read(PLUGIN_JSON))
    assert data["version"] == EXPECTED_VERSION


def test_version_marketplace_json():
    data = json.loads(_read(MARKETPLACE_JSON))
    entry = next(p for p in data["plugins"] if p["name"] == "telescoping-sdd")
    assert entry["version"] == EXPECTED_VERSION


def test_changelog_em_dash_entry():
    # The FIRST '## '-prefixed line must be the 2.1.0 entry with a U+2014 em-dash (ordering matters).
    first_heading = next(
        line.rstrip("\n\r ") for line in _read(CHANGELOG).splitlines() if line.startswith("## ")
    )
    assert first_heading == CHANGELOG_FIRST_ENTRY


# --- C9 (user-approved): security-reviewer Design-phase backstop (A7 operative obligation) ---
def test_security_reviewer_crosscheck():
    body = extract_section(_read(SECURITY_REVIEWER), "## Exposure Doctrine Cross-Check", SECURITY_REVIEWER)
    assert A7_CROSSCHECK in body
