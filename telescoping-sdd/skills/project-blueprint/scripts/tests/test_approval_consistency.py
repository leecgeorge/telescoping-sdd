"""Approval-detection consistency (review finding Scripts D5-4).

`has_approval()` / `approval_hash_matches()` (Family A, also used by
render_business_brief) and `check_approval()` must return the SAME verdict for
the same document — including a capital `- [X]` checkbox, an upper-case content
hash, and a `## Approval` header with extra whitespace. Before the regex-family
unification these two paths could disagree (case / whitespace drift).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(_SCRIPTS_DIR))

import validate_blueprint as vb  # noqa: E402


def _doc(*, header: str = "## Approval", box: str = "x", stored: str = "pending") -> str:
    return (
        "# Doc\n\nSome body content.\n\n"
        f"{header}\n\n"
        f"- [{box}] Approved to proceed\n"
        f"- **Content Hash:** `{stored}`\n"
    )


def _stamped(*, header: str = "## Approval", box: str = "x", upper: bool = False) -> str:
    """A correctly-approved doc: the stored hash is the real hash of this exact
    header/box form (content_for_hashing neutralises box + hash, so it is stable)."""
    h = vb.compute_content_hash(_doc(header=header, box=box, stored="pending"))
    return _doc(header=header, box=box, stored=h.upper() if upper else h)


def _check_approval(content: str) -> bool:
    res = vb.ValidationResult()
    return vb.check_approval(content, "PLAN.md", res)


def test_capital_x_and_uppercase_hash_agree_across_both_paths():
    doc = _stamped(box="X", upper=True)
    assert vb.has_approval(doc) is True
    assert vb.approval_hash_matches(doc) is True
    assert _check_approval(doc) is True


def test_flexible_header_whitespace_agrees_across_both_paths():
    for header in ("##  Approval", "##\tApproval", "##   Approval"):
        doc = _stamped(header=header)
        assert vb.has_approval(doc) is True, header
        assert vb.approval_hash_matches(doc) is True, header
        assert _check_approval(doc) is True, header


def test_lowercase_canonical_baseline_matches():
    doc = _stamped()
    assert vb.approval_hash_matches(doc) is True
    assert _check_approval(doc) is True


def test_tampered_body_fails_both_paths_consistently():
    tampered = _stamped().replace("Some body content.", "TAMPERED body content.")
    # Still detected as an approved section (header + checked box present) ...
    assert vb.has_approval(tampered) is True
    # ... but the hash no longer matches, on BOTH paths.
    assert vb.approval_hash_matches(tampered) is False
    assert _check_approval(tampered) is False
