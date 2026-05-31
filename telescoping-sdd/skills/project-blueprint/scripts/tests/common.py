"""Shared helpers and constants for the render_business_brief test suite.

Split into multiple test files per P3-15. This module owns:
- Helper functions (hash oracle, doc builders, CSS-color utils, body
  extractor, fixture directory makers)
- Frozen test constants (parametrize cases, frozen hash literals, scenario
  catalogues)
- Path constants (_SCRIPTS_DIR — used by tests that need to locate sibling
  scripts or read SKILL.md / phase-business-brief.md)
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
# Append (not insert) so the test bootstrap doesn't itself violate the
# `sys.path[0] unchanged after import` runtime check below.
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(_SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Approval-document builders + independent-oracle hash
# ---------------------------------------------------------------------------


def _doc_with_hash(body: str, *, ticked: bool = True, stored_hash: str) -> str:
    """Construct a minimal artifact-shaped markdown doc with the given hash."""
    box = "x" if ticked else " "
    return (
        f"{body}\n\n"
        f"## Approval\n\n"
        f"- [{box}] Approved to proceed\n"
        f"- **Content Hash:** `{stored_hash}`\n"
    )


def _independent_hash(content: str) -> str:
    """Recompute the artifact hash WITHOUT importing compute_content_hash.

    Mirrors blueprint_common.content_for_hashing (neutralise the approval
    checkbox state and the stored hash value before hashing) so the truth
    table has an independent oracle. Parity with the canonical helper is
    pinned by `test_independent_hash_oracle_parity` (P2-10).
    """
    neutralised = re.sub(
        r"- \[[ xX]\] Approved to proceed", "- [ ] Approved to proceed", content
    )
    neutralised = re.sub(
        r"\*\*Content Hash:\*\*\s*`[^`]*`", "**Content Hash:** `pending`", neutralised
    )
    neutralised = neutralised.rstrip()
    return hashlib.sha256(neutralised.encode("utf-8")).hexdigest()[:16]


def _build_doc(body: str, *, ticked: bool, hash_mode: str) -> str:
    """hash_mode: 'matching' | 'mismatching' | 'absent'"""
    if hash_mode == "absent":
        box = "x" if ticked else " "
        return f"{body}\n\n## Approval\n\n- [{box}] Approved to proceed\n"
    if hash_mode == "matching":
        scaffold = _doc_with_hash(body, ticked=ticked, stored_hash="X" * 16)
        real_hash = _independent_hash(scaffold)
        return _doc_with_hash(body, ticked=ticked, stored_hash=real_hash)
    # mismatching
    return _doc_with_hash(body, ticked=ticked, stored_hash="0" * 16)


# Frozen hashes — computed once via blueprint_common.compute_content_hash
# against the canonical bodies below.
_FROZEN_SCOPE_BODY = "# Scope\n\nBody content for SCOPE."
_FROZEN_ARCH_BODY = "# Architecture\n\nBody content for ARCHITECTURE."
_FROZEN_PLAN_BODY = "# Plan\n\nBody content for PLAN."
_FROZEN_SCOPE_HASH = "e1ebe80856f70caf"
_FROZEN_ARCH_HASH = "e25189f800d0009d"
_FROZEN_PLAN_HASH = "d94911ae63180383"


# ---------------------------------------------------------------------------
# CSS color utilities (used by WCAG-contrast test in test_render.py)
# ---------------------------------------------------------------------------


def _luminance(rgb):
    """Compute relative luminance per WCAG 2.x formula."""
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg_rgb, bg_rgb):
    fg_lum = _luminance(fg_rgb)
    bg_lum = _luminance(bg_rgb)
    lighter, darker = (max(fg_lum, bg_lum), min(fg_lum, bg_lum))
    return (lighter + 0.05) / (darker + 0.05)


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ---------------------------------------------------------------------------
# HTML body extraction (drops the <head>/<footer> noise from rendered output)
# ---------------------------------------------------------------------------


def _body_only(html_str: str) -> str:
    """Return only the <main>...</main> content of a rendered document.

    Used by XSS / mutation / link-hardening tests that should not be confused
    by stray strings inside the document head or footer.
    """
    m = re.search(r"<main>(.*?)</main>", html_str, re.DOTALL)
    return m.group(1) if m else html_str


# ---------------------------------------------------------------------------
# Path-validation fixture directory builders (used by error-path tests)
# ---------------------------------------------------------------------------


def _make_unapproved_dir(tmp_path):
    for name in ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md"):
        (tmp_path / name).write_text("# Body\n\nbody\n", encoding="utf-8")
    return tmp_path


def _make_absent_hash_dir(tmp_path):
    for name in ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md"):
        (tmp_path / name).write_text(
            "# B\n\nbody\n\n## Approval\n\n- [x] Approved to proceed\n",
            encoding="utf-8",
        )
    return tmp_path


def _make_stale_hash_dir(tmp_path):
    for name in ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md"):
        (tmp_path / name).write_text(
            "# B\n\nbody\n\n"
            "## Approval\n\n"
            "- [x] Approved to proceed\n"
            f"- **Content Hash:** `{'0' * 16}`\n",
            encoding="utf-8",
        )
    return tmp_path


# ---------------------------------------------------------------------------
# Constants used by parametrized tests
# ---------------------------------------------------------------------------

_ARTIFACT_NAMES = ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md")
_EXPECTED_OUTPUT_FILES = ("scope.html", "architecture.html", "plan.html")


# ---------------------------------------------------------------------------
# Doc-content readers (R6 grep targets — SKILL.md and phase-business-brief.md)
# ---------------------------------------------------------------------------


def _read_skill_md() -> str:
    skill_md_path = _SCRIPTS_DIR.parent / "SKILL.md"
    return skill_md_path.read_text(encoding="utf-8")


def _read_phase_doc() -> str:
    p = _SCRIPTS_DIR.parent / "references" / "phase-business-brief.md"
    return p.read_text(encoding="utf-8")
