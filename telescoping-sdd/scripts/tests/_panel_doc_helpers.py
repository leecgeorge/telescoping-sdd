"""Shared helpers for the panel-doctrine parity tests.

Extracted (T12) from `test_hash_and_cascade_parity.py` so that BOTH it and
`test_panel_review_autonomy.py` import ONE definition of these symbols — no
cross-test-module import, no duplicated tuple that could drift. Mirrors the
existing `_fixture_contract.py` / `_subagent_extractors.py` shared-helper
pattern in this directory.
"""

from __future__ import annotations

import re

import pytest

# SDD-only vocabulary that must never appear in a project-blueprint section
# (the PB copies vocabulary-swap these to SCOPE.md / ARCHITECTURE.md / PLAN.md /
# Scope / Architecture phase / Plan phase).
PB_FORBIDDEN_SDD_VOCABULARY = (
    "spec.md",
    "design.md",
    "tasks.md",
    "Specify",
    "Design phase",
    "Tasks phase",
)


def extract_section(content: str, heading: str) -> str:
    """Return the section starting at `heading` until the next `## ` heading."""
    pattern = re.compile(rf"({re.escape(heading)}\n.*?)(?=\n## |\Z)", re.DOTALL)
    m = pattern.search(content)
    if not m:
        pytest.fail(f"Section heading not found: {heading!r}")
    return m.group(1)


def extract_step_3_block(section: str) -> str:
    """Return the step-3 (Upstream panel re-review) block content."""
    pattern = re.compile(
        r"(3\. \*\*Upstream panel re-review\.?\*\*.*?)(?=\n4\. \*\*)", re.DOTALL
    )
    m = pattern.search(section)
    if not m:
        pytest.fail("Step 3 (Upstream panel re-review) block not found")
    return m.group(1)


def extract_subsection(content: str, heading: str) -> str | None:
    """Return a markdown subsection's body — from `heading` to the next `## `/`### `
    heading, or EOF. Returns None if the heading is absent. Unlike `extract_section`
    (which stops only at `## `), this stops at the next same-or-higher-level heading,
    so it correctly bounds a `### ` subsection."""
    idx = content.find(heading)
    if idx == -1:
        return None
    after = content[idx + len(heading):]
    m = re.search(r"\n(?:##|###) ", after)
    return after[: m.start()] if m else after
