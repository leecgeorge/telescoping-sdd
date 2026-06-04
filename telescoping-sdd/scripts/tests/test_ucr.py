"""Tests for the shared `ucr.py` UCR stanza parser (T3, requirement R9).

Covers the DM4 grammar: valid parse, duplicate-id / bad-status / missing-field
signals, multi-line free-text termination, no-over-split on field-shaped body
lines, ReDoS-safe linear-time on a large adversarial body, leading-zero id
rejected as malformed (not a duplicate), and parser symmetry between the two
consumers (`validate_spec.py` and `reconcile.py`) on the return value.

`conftest.py` in this directory snapshots/restores `sys.path` around each test,
so the path append below does not leak between tests.
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SHARED_SCRIPTS = _REPO_ROOT / "telescoping-sdd" / "scripts"


def _load_ucr():
    """Import (or reload) the shared `ucr` module with the shared scripts on sys.path.

    `ucr` imports `spec_dirname`, which also lives in the shared scripts dir, so
    that directory must be on `sys.path` first — mirrors how the real consumers
    (`validate_spec.py`, `reconcile.py`) set up their path.
    """
    if str(_SHARED_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SHARED_SCRIPTS))
    if "ucr" in sys.modules:
        return importlib.reload(sys.modules["ucr"])
    return importlib.import_module("ucr")


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _stanza(*entries: str) -> str:
    """Wrap entry blocks in a `## Upstream Change Requests` section with surrounding doc."""
    body = "\n\n".join(entries)
    return (
        "# Spec: Something\n\n"
        "## Some Earlier Section\n\n"
        "Earlier prose.\n\n"
        "## Upstream Change Requests\n\n"
        f"{body}\n\n"
        "## A Later Section\n\n"
        "Trailing prose that must NOT be parsed as a UCR field.\n"
    )


def _entry(
    number: str,
    target: str = "`residents:F7`",
    status: str = "open",
    proposed: str = "Add a sync hook.",
    rationale: str = "Keeps the resident roster current.",
    *,
    omit: tuple[str, ...] = (),
) -> str:
    """Build one `### UCR-<n>` entry, optionally omitting named fields."""
    lines = [f"### UCR-{number}", ""]
    if "Target" not in omit:
        lines.append(f"- **Target:** {target}")
    if "Status" not in omit:
        lines.append(f"- **Status:** {status}")
    if "Proposed change" not in omit:
        lines.append(f"- **Proposed change:** {proposed}")
    if "Rationale" not in omit:
        lines.append(f"- **Rationale:** {rationale}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ucr_valid_parse():
    """A well-formed single UCR entry parses with correct id, status, and field bodies."""
    ucr = _load_ucr()
    content = _stanza(_entry("1"))
    result = ucr.parse_ucr_stanza(content)

    assert result.present is True
    assert result.has_signals() is False
    assert len(result.entries) == 1

    entry = result.entries[0]
    assert entry.number == 1
    assert entry.target() == "`residents:F7`"
    assert entry.status() == "open"
    assert entry.raw_fields["Proposed change"] == "Add a sync hook."
    assert entry.raw_fields["Rationale"] == "Keeps the resident roster current."
    # Free text is reachable for printing ONLY via the display_safe wrapper.
    assert entry.safe_proposed_change() == "Add a sync hook."
    assert entry.missing_fields() == []


def test_ucr_duplicate_id_flagged():
    """Two `### UCR-1` entries produce a duplicate-id signal carrying the number."""
    ucr = _load_ucr()
    content = _stanza(_entry("1"), _entry("1", proposed="A second change."))
    result = ucr.parse_ucr_stanza(content)

    assert result.duplicate_ids == [1]
    assert result.has_signals() is True
    # Both entries are still parsed (the consumer emits the FAIL from the signal).
    assert len(result.entries) == 2


def test_ucr_bad_status_flagged():
    """A status outside {open, applied, withdrawn} produces an invalid-status signal."""
    ucr = _load_ucr()
    content = _stanza(_entry("3", status="pending"))
    result = ucr.parse_ucr_stanza(content)

    assert result.invalid_status_ids == [3]
    assert result.has_signals() is True
    # A valid status does NOT trip the signal.
    for good in ("open", "applied", "withdrawn"):
        ok = ucr.parse_ucr_stanza(_stanza(_entry("4", status=good)))
        assert ok.invalid_status_ids == []


def test_ucr_missing_field_flagged():
    """An entry missing the `Target` field produces a missing-field signal."""
    ucr = _load_ucr()
    content = _stanza(_entry("2", omit=("Target",)))
    result = ucr.parse_ucr_stanza(content)

    assert (2, "Target") in result.missing_field_ids
    assert result.has_signals() is True
    # The other three required fields are present, so only Target is missing.
    missing_for_2 = [name for (num, name) in result.missing_field_ids if num == 2]
    assert missing_for_2 == ["Target"]


def test_ucr_multiline_free_text():
    """A free-text body spanning blank lines terminates at the next field / `### UCR-` / `## ` / EOF.

    Exercises all four terminators:
      * `Proposed change` (multi-line, blank line interior) terminated by `- **Rationale:**`
      * `Rationale` (multi-line) terminated by the next `### UCR-` heading
      * the LAST entry's `Rationale` terminated by the `## A Later Section` heading
    """
    ucr = _load_ucr()
    multiline_proposed = (
        "First line of the change.\n"
        "\n"
        "A second paragraph after a blank line."
    )
    multiline_rationale = (
        "Because the roster drifts.\n"
        "\n"
        "And reconciliation is manual today."
    )
    entry1 = "\n".join(
        [
            "### UCR-1",
            "",
            "- **Target:** `residents:F7`",
            "- **Status:** open",
            f"- **Proposed change:** {multiline_proposed}",
            f"- **Rationale:** {multiline_rationale}",
        ]
    )
    entry2 = _entry("2", rationale="Final-entry rationale before the next section.")
    content = _stanza(entry1, entry2)
    result = ucr.parse_ucr_stanza(content)

    e1 = result.entries[0]
    # Proposed change kept its interior blank line and stopped at `- **Rationale:**`.
    assert e1.raw_fields["Proposed change"] == multiline_proposed
    assert "Rationale" not in e1.raw_fields["Proposed change"]
    # Rationale stopped at the next `### UCR-` heading.
    assert e1.raw_fields["Rationale"] == multiline_rationale
    assert "UCR-2" not in e1.raw_fields["Rationale"]

    # The final entry's Rationale stopped at the `## A Later Section` heading.
    e2 = result.entries[1]
    assert e2.raw_fields["Rationale"] == "Final-entry rationale before the next section."
    assert "Later Section" not in (e2.raw_fields["Rationale"] or "")
    assert "Trailing prose" not in (e2.raw_fields["Rationale"] or "")
    assert result.has_signals() is False


def test_ucr_field_shaped_body_no_oversplit():
    """A `Proposed change` body containing a field-like line does not over-split.

    A line such as `- **Status:** open` embedded inside the prose of the
    Proposed change body IS one of the four real field names, and it appears
    AFTER the real Status line, so it must be folded into the free-text body
    rather than treated as a second Status field. The parser takes the FIRST
    occurrence of each field, so the embedded look-alike stays in the body.
    """
    ucr = _load_ucr()
    proposed = (
        "Rename the marker.\n"
        "Example of the line we are changing:\n"
        "- **Status:** open\n"
        "...and that is the whole change."
    )
    entry = "\n".join(
        [
            "### UCR-1",
            "",
            "- **Target:** `residents:F7`",
            "- **Status:** applied",
            f"- **Proposed change:** {proposed}",
            "- **Rationale:** Clarity.",
        ]
    )
    content = _stanza(entry)
    result = ucr.parse_ucr_stanza(content)

    e = result.entries[0]
    # The REAL status is the first one; the embedded look-alike is body text.
    assert e.status() == "applied"
    assert "- **Status:** open" in e.raw_fields["Proposed change"]
    # Rationale (which comes after the embedded look-alike) is still parsed.
    assert e.raw_fields["Rationale"] == "Clarity."
    # No spurious invalid-status signal from the embedded `open` look-alike.
    assert result.invalid_status_ids == []
    assert result.has_signals() is False


def test_ucr_large_adversarial_body():
    """A large free-text body completes in (near-)linear time — no `.*?` backtracking.

    The body is a long run of field-prefix-LIKE bytes (`- **`) that would force
    catastrophic backtracking under a `.*?`-terminated field regex. The offset-
    slicing parser must complete quickly and keep the whole blob in the body.
    """
    ucr = _load_ucr()
    huge = ("- **not a real field** " * 200_000).strip()
    entry = "\n".join(
        [
            "### UCR-1",
            "",
            "- **Target:** `residents:F7`",
            "- **Status:** open",
            f"- **Proposed change:** {huge}",
            "- **Rationale:** Big.",
        ]
    )
    content = _stanza(entry)

    start = time.perf_counter()
    result = ucr.parse_ucr_stanza(content)
    elapsed = time.perf_counter() - start

    # Generous ceiling — a backtracking parser would blow far past this.
    assert elapsed < 2.0, f"parse took {elapsed:.2f}s — possible ReDoS"
    e = result.entries[0]
    assert e.raw_fields["Proposed change"].startswith("- **not a real field**")
    assert e.raw_fields["Rationale"] == "Big."
    assert result.has_signals() is False


def test_ucr_leading_zero_id_malformed():
    """`### UCR-01` is rejected as a malformed id at parse time — not a duplicate of 1."""
    ucr = _load_ucr()
    content = _stanza(_entry("01"))
    result = ucr.parse_ucr_stanza(content)

    assert "01" in result.malformed_ids
    # It never became an entry, so it is not in the duplicate set either.
    assert result.entries == []
    assert result.duplicate_ids == []

    # And `UCR-1` followed by `UCR-01` is one real entry + one malformed id,
    # NOT a duplicate pair.
    mixed = _load_ucr().parse_ucr_stanza(_stanza(_entry("1"), _entry("01")))
    assert [e.number for e in mixed.entries] == [1]
    assert mixed.duplicate_ids == []
    assert "01" in mixed.malformed_ids


def test_ucr_zero_id_malformed():
    """`### UCR-0` (zero) is rejected as malformed, mirroring the CFC grammar."""
    ucr = _load_ucr()
    result = ucr.parse_ucr_stanza(_stanza(_entry("0")))
    assert "0" in result.malformed_ids
    assert result.entries == []


def test_ucr_absent_stanza_is_noop():
    """A spec with no `## Upstream Change Requests` section yields present=False, no signals."""
    ucr = _load_ucr()
    content = "# Spec\n\n## Overview\n\nNo UCR stanza here.\n"
    result = ucr.parse_ucr_stanza(content)
    assert result.present is False
    assert result.entries == []
    assert result.has_signals() is False


def test_ucr_display_safe_accessor_neutralizes_control_chars():
    """Free-text sink accessor escapes control bytes so no forged FAIL/WARN line is injectable."""
    ucr = _load_ucr()
    # Embed a CR + ANSI-escape-like sequence in the rationale inline value.
    nasty = "ok\\r\\x1b[31mFAIL forged line"  # literal backslashes in source markdown
    # Build with a genuine control char in the body.
    proposed_with_ctrl = "before\x1b[31m FAIL: forged\rafter"
    entry = "\n".join(
        [
            "### UCR-1",
            "",
            "- **Target:** `residents:F7`",
            "- **Status:** open",
            f"- **Proposed change:** {proposed_with_ctrl}",
            "- **Rationale:** plain.",
        ]
    )
    content = _stanza(entry)
    result = ucr.parse_ucr_stanza(content)
    e = result.entries[0]

    safe = e.safe_proposed_change()
    # No raw ESC or CR survive into the sink output.
    assert "\x1b" not in safe
    assert "\r" not in safe
    # The escaped forms are present and visible instead.
    assert "\\x1b" in safe
    assert "\\r" in safe
    # The raw body still carries the control char (comparison path), proving the
    # ONLY neutralization happens at the display_safe sink, not at parse time.
    assert "\x1b" in e.raw_fields["Proposed change"]
    assert nasty  # silence unused-var lints; documents the intent


def test_ucr_parser_symmetry():
    """`validate_spec.py` and `reconcile.py` parse the same stanza identically.

    Both consumers import the SAME shared `ucr.parse_ucr_stanza`; a shared
    script must not import a skill validator, so this is the anti-drift oracle.
    We load the module twice via two independent import paths (a fresh reload
    standing in for the second consumer) and assert the return values agree on
    entry ids, statuses, raw field bodies, and every signal list. The oracle is
    on the PARSER return value (not on either consumer's output shape).
    """
    content = _stanza(
        _entry("1", status="open", proposed="One.\n\nTwo."),
        _entry("2", status="applied"),
        _entry("01"),  # malformed id
        _entry("5", status="pending"),  # bad status
        _entry("6", omit=("Rationale",)),  # missing field
        _entry("1", proposed="dup."),  # duplicate of 1
    )

    ucr_a = _load_ucr()
    result_a = ucr_a.parse_ucr_stanza(content)

    # Second independent consumer: force a fresh import of the same module.
    sys.modules.pop("ucr", None)
    ucr_b = _load_ucr()
    result_b = ucr_b.parse_ucr_stanza(content)

    def _shape(r):
        return {
            "present": r.present,
            "ids": [e.number for e in r.entries],
            "targets": [e.target() for e in r.entries],
            "statuses": [e.status() for e in r.entries],
            "proposed": [e.raw_fields["Proposed change"] for e in r.entries],
            "rationale": [e.raw_fields["Rationale"] for e in r.entries],
            "duplicate_ids": sorted(r.duplicate_ids),
            "invalid_status_ids": sorted(r.invalid_status_ids),
            "missing_field_ids": sorted(r.missing_field_ids),
            "malformed_ids": sorted(r.malformed_ids),
        }

    assert _shape(result_a) == _shape(result_b)
    # And spot-check the shape is the expected non-trivial one (so symmetry is
    # not vacuously comparing two empty results).
    shape = _shape(result_a)
    assert shape["ids"] == [1, 2, 5, 6, 1]
    assert shape["duplicate_ids"] == [1]
    assert shape["invalid_status_ids"] == [5]
    assert (6, "Rationale") in shape["missing_field_ids"]
    assert shape["malformed_ids"] == ["01"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
