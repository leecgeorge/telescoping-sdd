#!/usr/bin/env python3
"""archive_pass.py — Archive a panel-review pass.

Reads an artifact (spec.md / design.md / etc.) and processes its `## Panel Review`
section:
  - Promotes newly-sealed items from `### Latest pass detail` into
    `### Sealed dispositions` (assigning sequential `[SEAL-NN]` IDs)
  - Appends a row to `### Trajectory` with HIGHs / regressions / disposition counts
  - Clears `### Latest pass detail` so the next pass starts with an empty table

The Panel Review format the script enforces is normative; the
authoritative shape lives in this module's parsing logic and the matching
templates under `telescoping-sdd/skills/*/references/`.

`--strict-bar` and `--cross-check` are panel-mode modifiers (see each skill's
`references/strict-bar-prompts.md`). They process Latest pass detail exactly
like a normal archive but additionally stamp the `### Trajectory` Notes column
so the trajectory records which mode the pass ran in:
  - `--strict-bar`  → Notes `strict-bar pass`. A strict-bar pass counts toward
    the 5-pass cap.
  - `--cross-check` → Notes `cross-check pass (excluded from cap)`. A
    cross-check pass is exit ceremony and does NOT count toward the cap; the
    synthesizer excludes cross-check-noted rows when counting passes.
Independent of mode, a pass that leaves no *unresolved* HIGH is marked
converged in Notes, in one of two forms:
  - `converged (0 HIGH)`                          — no HIGH was raised at all.
  - `converged (0 unresolved HIGH); sealed=<N>`   — N HIGHs were raised and all
    of them were disposed `Sealed` / `Accepted as risk`.
The exit test, on one line so it stays greppable:
  no HIGH concerns other than those dismissed with a recorded `Defense:`
i.e. the non-blocking set is exactly DEFENDED_DISPOSITIONS, the
same set `validate_row` already requires a `Defense:` for. `Addressed`,
`Deferred`, `Halt and re-scope` and `User input needed` all still block: an
`Addressed` HIGH means an edit was made that nobody has reviewed.

That `Defense:` check is deliberately **presence**-only — `validate_row`
requires the literal token in the row's Notes and grades nothing after it.

`sealed=<N>` is a stable machine token: the grammar `sealed=(\\d+)` is a
published contract for later readers. Emitting it
licenses observation, not enforcement — gating approval on its value would
re-open the seal-justification question this design deliberately leaves to the
`Defense:` requirement.

Two things the stamp does NOT track. The `### Trajectory` **HIGHs** column
keeps recording HIGHs *raised*, so a converged row may show a non-zero count;
and the **Sealed column** counts `Sealed` / `Accepted as risk` rows of every
severity, while `sealed=<N>` counts the HIGH-severity ones only — on a pass
that sealed a MED the two legitimately differ. A converged row may also carry
halt-vote text; read the whole Notes cell.

The marker is appended to any mode tag (e.g. `strict-bar pass; converged
(0 HIGH)`) and is documentation-of-fact for the trajectory.
With either flag, an empty Latest pass detail still produces a trajectory row
(all counts zero) so the mode pass is recorded. The flags are mutually
exclusive with each other and with `--skip`.

Usage:
    archive_pass.py <artifact-path> --phase {1,2,3} [--skip <reason>]
                    [--strict-bar] [--cross-check] [--dry-run] [--check]
                    [--panel-roster NAMES]

`--phase` is required. It drives phase-dependent trigger logic:
  - Phase 1: unchanged (no [upstream] route; existing Deferred-driven
    strict-bar signal).
  - Phase 2: [upstream]-tagged rows in Latest count as halt votes alongside
    "Halt and re-scope" dispositions; strict-bar signal unchanged from
    Deferred → DOWNSTREAM accumulation.
  - Phase 3: [upstream] auto-routes to halt votes (as Phase 2); strict-bar
    signal switches to [detail]-tag accumulation (Phase 3's analogue of
    Deferred-downstream, since Phase 3 has no further blueprint phase).

For Phases 2 and 3, a `tags=dXuYcZ` substring is added to the trajectory
Notes column at archive time, recording the count of [detail]/[upstream]/
[contract]-tagged rows in the just-archived Latest. Tag counting is
restricted to HIGH-severity rows from panelist sources (not [SELF-CHECK]
rows); MED/LOW rows and [SELF-CHECK] entries are not counted regardless
of any tag prefix they may carry, since tags are a panel-routing mechanism
for HIGH-severity findings only. The strict-bar signal detector parses
this substring across consecutive rows (since Latest is cleared after
each archive).

`--panel-roster NAMES` (this pass's dispatched panelists, in dispatch order,
comma-separated; repeatable) additionally stamps a `panel=H.M.L,…` unique-yield
token in the new row's Notes, before `tags=`: one `H.M.L` group per roster seat,
counting the just-archived Latest rows whose Source names exactly that one
panelist (merged and [SELF-CHECK] rows count for nobody; Disposition is not
read). A roster that does not match the canonical `## Panelists per phase`
order, or a Source naming a panelist outside the roster, suppresses the token
with a stderr warning and changes nothing else. Omitting the flag stamps no
token; `--skip` never stamps one. Every archive that clears Latest also appends
the cleared rows to the `.sdd/panel-log.jsonl` sidecar (never read by the loop).

Exit codes:
    0  success (empty Latest is a no-op unless --strict-bar/--cross-check)
    1  format violation in Latest pass detail, or conflicting mode flags
    2  unresolved 'User input needed' concerns in Latest pass detail
    3  panel-review section missing or in old format
"""

import argparse
import difflib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from approval_records import display_arg, display_text  # noqa: E402
from arch_config import (  # noqa: E402
    NOTICE_FILENAME,
    POSTURES,
    config_path,
    resolve_posture,
)

# archive_pass.py is a sibling of blueprint_common.py in telescoping-sdd/scripts/,
# so a bare import resolves when run as a CLI (script dir on sys.path) and under
# the test loader (which appends the scripts dir).
from blueprint_common import (  # noqa: E402
    ORPHANED_TRAJECTORY_TOKEN,
    find_orphaned_trajectory_rows,
    has_approval,
    read_hash_basis,
    read_stored_hash,
    trim_trajectory_table,
    _is_ascii_int,
    _resolve_marker_root_and_key,
    _is_valid_16_hex,
)
# Table helpers, terminal rules and stamp constants live in the trajectory leaf
# (Unit C0 AD1/AD2); the old names below are aliases of the same objects.
from trajectory import (  # noqa: E402
    CONVERGED_STAMPS,
    SEAL_ENTRY_RE,
    STAMP_CONVERGED_NO_HIGH,
    STAMP_CONVERGED_SEALED,
    STAMP_CROSS_CHECK,
    STAMP_HALT_DISPOSITION,
    STAMP_STRICT_BAR,
    TERMINAL_FILENAMES,
    TERMINAL_HTML_MARKER,
    TRAJECTORY_COLS,
    _NUMERIC_PREFIX_RE,
    _UNESCAPED_PIPE,
    _strip_numeric_prefix,
    is_terminal_artifact,
    notes_tokens,
    render_table,
    render_table_row,
    render_trajectory_table,
    seats_token_present,
    SEATS_ROSTER_LENGTH,
    format_seats_record,
    split_table_row,
    provenance_token,
    stamp_provenance,
)
from content_hash import compute_content_hash  # noqa: E402

SEAL_PAT = SEAL_ENTRY_RE
_split_row = split_table_row


DISPOSITION_LABELS = {
    "Addressed",
    "Deferred",
    "Sealed",
    "Accepted as risk",
    "User input needed",
    "Halt and re-scope",
}

# The dispositions this script REQUIRES a `Defense:` for (see validate_row).
# The exit predicate is defined as exactly this set, deliberately: it can then
# be re-derived from the code rather than memorised, and it cannot drift from
# what the archive actually enforces.
DEFENDED_DISPOSITIONS = ("Sealed", "Accepted as risk")


def disposition_base(disp: str) -> str:
    """Return a disposition's base label, stripping any `→ <target>` suffix.

    Reproduces the historic ``disp.split("→")[0].strip()`` exactly — including
    the no-arrow passthrough and the surrounding-whitespace trim. This is the
    SINGLE source of the `→`-split-base rule in this module (design DR9); every
    base-extraction call site routes through it, and ``compact_table.py`` (T2)
    imports the public ``is_known_disposition`` one-way so the rule is never
    re-implemented downstream.
    """
    return disp.split("→")[0].strip() if "→" in disp else disp.strip()


def is_known_disposition(disp: str) -> bool:
    """True iff a disposition's base label is in the frozen vocabulary.

    Base-extracts first (so `Deferred → design.md` is known on its `Deferred`
    base) then tests membership — the same order as ``validate_row``.
    """
    return disposition_base(disp) in DISPOSITION_LABELS

H_PANEL_REVIEW = "## Panel Review"
H_TRAJECTORY = "### Trajectory"
H_SEALED = "### Sealed dispositions"
H_LATEST = "### Latest pass detail"

LATEST_COLS = ["Severity", "Source", "Concern", "Disposition", "Notes"]

EXIT_OK = 0
EXIT_FORMAT_VIOLATION = 1
EXIT_USER_INPUT_NEEDED = 2
EXIT_OLD_FORMAT_OR_MISSING = 3
# Unit D (C1): --zone-diff found a difference in the hard-fail zone.
EXIT_ZONE_DIFFERS = 4

SEPARATOR_PAT = re.compile(r"^\|[\s\-|:]+\|\s*$")

# Deferred-dispositions feature (R1, R2, R5, R7) — see specs/deferred-dispositions/
H_DEFERRED = "### Deferred dispositions"
DEFERRED_REDISPOSITION_PREFIX = "Defense: already routed to "
PANEL_SECTION_ORDER = [H_TRAJECTORY, H_SEALED, H_DEFERRED, H_LATEST]

# Unit C (AD10, DM2): artifact stem -> (tier, phase), and the canonical
# dispatch roster per (tier, phase). CANONICAL_ROSTERS must equal each tier's
# `## Panelists per phase` with the prefix removed (roster-parity test).
ARTIFACT_STEMS = {
    "SCOPE": ("blueprint", 1),
    "ARCHITECTURE": ("blueprint", 2),
    "PLAN": ("blueprint", 3),
    "spec": ("sdd", 1),
    "design": ("sdd", 2),
    "tasks": ("sdd", 3),
    "tasks-python": ("sdd", 3),
    "tasks-java": ("sdd", 3),
}
_ROSTER_P1 = ("user-advocate", "devils-advocate", "pragmatist")
_ROSTER_P3 = ("delivery-manager", "critic", "simplifier")
CANONICAL_ROSTERS = {
    ("sdd", 1): _ROSTER_P1,
    ("blueprint", 1): _ROSTER_P1,
    ("sdd", 2): ("architect", "testability-reviewer", "security-reviewer"),
    ("blueprint", 2): ("architect", "ops-reviewer", "security-reviewer"),
    ("sdd", 3): _ROSTER_P3,
    ("blueprint", 3): _ROSTER_P3,
}
PANELIST_PREFIX = "telescoping-sdd:"


def _normalize_panelist_name(name: str) -> str:
    """Strip whitespace and one leading 'telescoping-sdd:' prefix. Case is kept."""
    name = name.strip()
    if name.startswith(PANELIST_PREFIX):
        name = name[len(PANELIST_PREFIX):].strip()
    return name


def parse_panel_roster(values: Optional[list]) -> Optional[list]:
    """Flatten `--panel-roster` values (append action) into an ordered name list.

    Each value is split on ',', each element normalised, empties dropped.
    Returns None when the flag was absent OR the result is empty (AD8).
    Never raises.
    """
    if not values:
        return None
    roster = []
    for value in values:
        for element in str(value).split(","):
            name = _normalize_panelist_name(element)
            if name:
                roster.append(name)
    return roster or None


def artifact_tier(path: Path) -> Optional[str]:
    """'sdd' | 'blueprint' from ARTIFACT_STEMS, or None for an unknown stem."""
    name = _strip_numeric_prefix(Path(path).name)
    stem = name[:-3] if name.endswith(".md") else name
    entry = ARTIFACT_STEMS.get(stem)
    return entry[0] if entry else None


# Unit D (C5): on phase 2 with an unknown tier, each Phase 2 name has one
# canonical position across both tiers (position 2 differs by tier only), so a
# union lookup resolves positions without the tier.
_PHASE2_UNION_POSITIONS = {
    name: i
    for t in ("sdd", "blueprint")
    for i, name in enumerate(CANONICAL_ROSTERS[(t, 2)], start=1)
}


def _canonical_positions(roster: list, tier: Optional[str], phase: int) -> Optional[tuple]:
    """1-based canonical positions of `roster` when it is a canonical-order
    subsequence (full or proper) of the roster in force, else None. Pure.

    Known tier: CANONICAL_ROSTERS[(tier, phase)]. Unknown tier on phases 1 and
    3: the shared roster. Unknown tier on phase 2: the union lookup, so a
    roster mixing `testability-reviewer` and `ops-reviewer` (both position 2)
    does not resolve.
    """
    if not roster:
        return None
    if tier is None and phase == 2:
        if any(n not in _PHASE2_UNION_POSITIONS for n in roster):
            return None
        positions = tuple(_PHASE2_UNION_POSITIONS[n] for n in roster)
    else:
        canonical = list(CANONICAL_ROSTERS[("sdd" if tier is None else tier, phase)])
        if any(n not in canonical for n in roster):
            return None
        positions = tuple(canonical.index(n) + 1 for n in roster)
    if any(a >= b for a, b in zip(positions, positions[1:])):
        return None
    return positions


def roster_seat_positions(roster: list, tier: Optional[str], phase: int) -> Optional[tuple]:
    """1-based canonical positions when `roster` is a PROPER canonical-order
    subsequence of the roster in force (C5's union lookup on phase 2 with an
    unknown tier); else None. A full roster returns None: it carries no
    `seats=` token (AD11). Pure."""
    positions = _canonical_positions(roster, tier, phase)
    if positions is None or len(positions) >= SEATS_ROSTER_LENGTH:
        return None
    return positions


def check_roster_order(roster: list, tier: Optional[str], phase: int) -> Optional[str]:
    """Return the DM5 order warning, or None.

    None for the canonical roster or a proper subsequence of it in canonical
    relative order (Unit D, C5: a tapered pass). Canonical =
    CANONICAL_ROSTERS[(tier, phase)]; when tier is None and phase is 1 or 3,
    the shared roster for that phase (rendered as tier 'shared'); when tier is
    None and phase is 2, the cross-tier union lookup. A transposed, duplicated
    or unrecognised name warns, as Unit C AD9 specifies. Pure.
    """
    if _canonical_positions(roster, tier, phase) is not None:
        return None
    if tier is None and phase == 2:
        return (
            f"warning: panel= not stamped — --panel-roster {','.join(roster)} does "
            f"not resolve to canonical Phase 2 positions in order (architect; "
            f"testability-reviewer or ops-reviewer; security-reviewer) "
            f"(## Panelists per phase)."
        )
    if tier is None:
        canonical = CANONICAL_ROSTERS[("sdd", phase)]
        tier_label = "shared"
    else:
        canonical = CANONICAL_ROSTERS[(tier, phase)]
        tier_label = tier
    return (
        f"warning: panel= not stamped — --panel-roster {','.join(roster)} does "
        f"not match the canonical {tier_label} Phase {phase} order "
        f"{','.join(canonical)} (## Panelists per phase)."
    )

DEF_PAT = re.compile(
    r"^-\s+`\[DEF-(\d+)\]`\s+\*\*(.+?)\*\*\s+→\s+(\S+)\s+\(pass\s+(\d+)\)\s+—\s+Routed because:\s+(.+)$"
)
MARKER_STRICT_PAT = re.compile(r"^Defense: rerouted \[DEF-(\d{2})\]\.?\s*$")
MARKER_WIDE_PAT = re.compile(r"^\s*[Dd]efense:\s*[Rr]e-?routed\b")
TARGET_PAT = re.compile(
    r"^(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\.md$"
)


def _is_terminal(content: str, path: Path, explicit_flag: bool) -> bool:
    """Return True if the artifact is a terminal-phase artifact.

    Priority order (per design AD1, I2):
      1. explicit_flag (--terminal was passed on CLI)
      2. path.name in TERMINAL_FILENAMES (case-sensitive registry)
      3. TERMINAL_HTML_MARKER in content (terminal SCOPE.md backstop)
    """
    if explicit_flag:
        return True
    return is_terminal_artifact(content, path.name)


class FormatViolation(Exception):
    def __init__(self, message, line_num=None):
        super().__init__(message)
        self.line_num = line_num


def find_section(lines, heading, start=0, end=None):
    """Locate `heading` between `start` and `end`. Section ends at the next
    heading of the same or higher level, or at `end`.

    Fence-aware (audit 3.5e): a heading-shaped line inside a fenced code block
    (``` ... ```) is a quoted example, not a real section, so it is never matched
    as the section header AND never treated as the section terminator. Without
    this, a self-documenting artifact that quotes `### Trajectory` (or `### Sealed
    dispositions`, etc.) inside a fence would make this writer disagree with
    blueprint_common's fence-aware hash/anchor reader about which table is real.
    """
    if end is None:
        end = len(lines)
    level = len(heading) - len(heading.lstrip("#"))
    s = None
    in_fence = False
    for i in range(start, end):
        if lines[i].lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if lines[i].rstrip() == heading:
            s = i
            break
    if s is None:
        return None
    e = end
    in_fence = False
    for i in range(s + 1, end):
        if lines[i].lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if lines[i].startswith("#"):
            line_level = len(lines[i]) - len(lines[i].lstrip("#"))
            if line_level <= level:
                e = i
                break
    return s, e


def find_table(lines, start, end):
    """First markdown table in [start, end). Returns (header_idx, sep_idx,
    first_data_idx, end_data_idx) or None."""
    h = None
    for i in range(start, end):
        s = lines[i].strip()
        if s.startswith("|") and s.endswith("|"):
            h = i
            break
    if h is None or h + 1 >= end:
        return None
    if not SEPARATOR_PAT.match(lines[h + 1]):
        return None
    sep = h + 1
    first = sep + 1
    last = first
    while last < end:
        s = lines[last].strip()
        if not (s.startswith("|") and s.endswith("|")):
            break
        last += 1
    return h, sep, first, last




def parse_table(lines, start, end, *, malformed=None, table_name=""):
    """Parse a pipe table into a list of header-keyed row dicts.

    `malformed`, when supplied, collects one dict per row whose cell count does
    not match the header (DM8's MalformedRow fields); the stderr warning is
    emitted either way. `table_name` labels those records so the caller's
    diagnostic can name the table and state the consequence that applies to it.

    Both new parameters are keyword-only, so the arity and the 3-positional
    call pinned by test_parse_table_warns_on_unescaped_pipe_row are untouched.
    Returns the unchanged `(rows, table)` 2-tuple. Never raises; the hard
    failure is the caller's (AD14).
    """
    table = find_table(lines, start, end)
    if table is None:
        return [], None
    h, _, first, last = table
    header = _split_row(lines[h])
    rows = []
    for i in range(first, last):
        cells = _split_row(lines[i])
        if len(cells) == len(header):
            rows.append(dict(zip(header, cells)))
        elif lines[i].strip():
            # A non-blank row whose cell count != header. Since _split_row
            # honours the documented `\|` escape, this is no longer the
            # ordinary escaped-pipe case — it is a genuinely malformed row. Do
            # NOT drop it silently: a dropped row vanishes from the
            # HIGH/Deferred/Sealed counts and the audit trail. Warn, naming the
            # 1-based line and the offender, and record it for the caller's
            # gate.
            excerpt = lines[i].strip()[:100]
            print(
                f"warning: panel table row at line {i + 1} has {len(cells)} "
                f"cells, expected {len(header)} — unescaped '|'? escape it as "
                f"'\\|'. Row not counted: {excerpt}",
                file=sys.stderr,
            )
            if malformed is not None:
                malformed.append({
                    "line_num": i + 1,
                    "actual": len(cells),
                    "expected": len(header),
                    "excerpt": excerpt,
                    "table": table_name,
                })
    return rows, table


def parse_seals(lines, start, end):
    entries = []
    for i in range(start, end):
        m = SEAL_PAT.match(lines[i].rstrip())
        if m:
            entries.append({
                "id": int(m.group(1)),
                "title": m.group(2),
                "pass": int(m.group(3)),
                "disposition": m.group(4).strip(),
                "tail": m.group(5).strip(),
                "line_idx": i,
            })
    return entries


def parse_defs(lines, start, end):
    """Parse [DEF-NN] entries from `### Deferred dispositions`.

    Mirrors parse_seals(). Emits stderr WARN on non-matching non-blank/non-comment
    lines within section bounds (per design I1 contract + security LOW-6).
    """
    entries = []
    for i in range(start, end):
        line = lines[i]
        stripped = line.rstrip()
        m = DEF_PAT.match(stripped)
        if m:
            entries.append({
                "id": int(m.group(1)),
                "title": m.group(2),
                "target": m.group(3),
                "pass_n": int(m.group(4)),
                "rationale": m.group(5).strip(),
                "line_idx": i,
            })
        elif stripped and not stripped.startswith("<!--") and stripped.startswith("- "):
            # Looks like an entry-shaped line but doesn't match — warn (don't exit).
            print(
                f"warning: line {i + 1} in '### Deferred dispositions' does not "
                f"match expected [DEF-NN] format and was skipped: "
                f"{repr(stripped[:80])}. Check the entry shape; this entry will "
                f"not be referenceable by marker expansion.",
                file=sys.stderr,
            )
    return entries


def next_def_id(def_entries):
    """Return the next sequential [DEF-NN] ID (max + 1, or 1 if empty)."""
    return max((e["id"] for e in def_entries), default=0) + 1


def lookup_def(def_entries, def_id):
    """Return the def_entry with the given id, or None if not found."""
    for e in def_entries:
        if e["id"] == def_id:
            return e
    return None


def validate_row(row, line_num):
    sev = row.get("Severity", "").strip()
    sev_tags = re.findall(r"\[(HIGH|MED|LOW)\]", sev)
    if len(sev_tags) != 1:
        raise FormatViolation(
            f"Severity '{sev}' must include exactly one of [HIGH]/[MED]/[LOW]",
            line_num,
        )
    extra = re.sub(r"\[(HIGH|MED|LOW|REGRESSION)\]", "", sev).strip()
    if extra:
        raise FormatViolation(
            f"Severity '{sev}' has unknown tag(s): '{extra}'",
            line_num,
        )
    disp = row.get("Disposition", "").strip()
    disp_base = disposition_base(disp)
    if disp_base not in DISPOSITION_LABELS:
        raise FormatViolation(
            f"Disposition '{disp}' not in vocabulary {sorted(DISPOSITION_LABELS)}",
            line_num,
        )
    if disp_base in DEFENDED_DISPOSITIONS:
        if "Defense:" not in row.get("Notes", ""):
            raise FormatViolation(
                "Sealed/Accepted-as-risk row must include 'Defense:' in Notes",
                line_num,
            )


def derive_title(concern, max_len=60):
    t = re.sub(r"^\[\w+\]\s*", "", concern.strip())
    if len(t) <= max_len:
        return t
    return t[:max_len].rsplit(" ", 1)[0] + "…"


def extract_defense(notes):
    m = re.search(r"Defense:\s*(.+)$", notes)
    if m:
        return m.group(1).strip().rstrip(".")
    return notes.strip()


# --- Tag handling for Phases 2 and 3 (per blueprint-strict.md) -----------
# Panelists prefix each HIGH finding's Concern with [contract] / [detail] /
# [upstream]. Phase 1 doesn't use these tags; Phases 2 and 3 do.

def high_disposition_counts(rows):
    """Classify HIGH-severity Latest-pass-detail rows for the exit predicate.

    A HIGH is *unresolved* when it carries no `Defense:`-backed disposition --
    i.e. its disposition base is not in DEFENDED_DISPOSITIONS. `validate_row`
    has already guaranteed that any such row carries `Defense:` in its Notes,
    so "sealed" here implies "defended".

    Args:
        rows: parsed `### Latest pass detail` rows, each with "Severity" and
            "Disposition".

    Returns:
        (raised, sealed_high, unresolved):
          raised      -- HIGH rows of any disposition; what the HIGHs column records.
          sealed_high -- HIGH rows disposed Sealed / Accepted as risk; the `sealed=<N>` token.
          unresolved  -- raised - sealed_high; zero is the exit condition.

    Pure over its argument. Malformed rows are rejected earlier by validate_row.
    """
    raised = 0
    sealed_high = 0
    for r in rows:
        if "[HIGH]" not in r["Severity"]:
            continue
        raised += 1
        if disposition_base(r["Disposition"]) in DEFENDED_DISPOSITIONS:
            sealed_high += 1
    return raised, sealed_high, raised - sealed_high


TAG_NAMES = ("detail", "upstream", "contract")


def _starts_with_tag(concern, tag):
    """True if Concern text starts with the given tag like '[upstream]'."""
    return concern.lstrip().startswith(tag)


def _is_self_check(row: dict) -> bool:
    """True iff the row's Source contains '[SELF-CHECK]' (AD12)."""
    return "[SELF-CHECK]" in row.get("Source", "")


def _is_panel_tagged_high(row):
    """True if the row is a HIGH-severity panel-raised row eligible for
    tag-based trigger routing. Tags are a panel mechanism for routing
    halt-and-rescope and strict-bar triggers — they apply to HIGH rows
    raised by panelists. [SELF-CHECK] rows describe synthesizer regressions
    (a/b/c/d categories) and are exempt from the tag mechanism. MED/LOW
    rows are also exempt — they don't block convergence so they don't
    need routing.
    """
    if "[HIGH]" not in row.get("Severity", ""):
        return False
    return not _is_self_check(row)


def count_tags(rows):
    """Return {"detail": N, "upstream": N, "contract": N} for the given rows.
    Counts only HIGH-severity, panelist-sourced rows whose Concern starts
    with the tag (per _is_panel_tagged_high).
    """
    return {
        tag: sum(
            1 for r in rows
            if _is_panel_tagged_high(r)
            and _starts_with_tag(r.get("Concern", ""), f"[{tag}]")
        )
        for tag in TAG_NAMES
    }


def format_tag_summary(counts):
    """Render counts as compact 'd5u0c2' string for the Notes prefix."""
    return f"d{counts['detail']}u{counts['upstream']}c{counts['contract']}"


def parse_tag_summary(notes):
    """Parse 'tags=d5u0c2' substring from Notes. Returns dict or None."""
    m = re.search(r"tags=d(\d+)u(\d+)c(\d+)", notes)
    if not m:
        return None
    return {
        "detail": int(m.group(1)),
        "upstream": int(m.group(2)),
        "contract": int(m.group(3)),
    }


# Unit C (AD11, DM1, I4, I6): the `panel=H.M.L,…` per-seat unique-yield token.
_SEVERITY_BUCKETS = {"HIGH": 0, "MED": 1, "LOW": 2}
_SEVERITY_CORE_RE = re.compile(r"\[(HIGH|MED|LOW)\]")


def _severity_bucket(severity_cell: str) -> Optional[int]:
    """0/1/2 for the cell's single [HIGH]/[MED]/[LOW] tag; None if absent."""
    m = _SEVERITY_CORE_RE.search(severity_cell or "")
    return _SEVERITY_BUCKETS[m.group(1)] if m else None


def count_panel_yield(rows: list, roster: list) -> tuple:
    """Return (counts, unrecognised).

    counts:       list of (h, m, l) tuples, one per roster seat, in roster order.
    unrecognised: list of distinct (source_cell, name) pairs, in first-seen order.
    For each row: skip if _is_self_check. Split Source on ',' and normalise each
    name; drop empty names. If the list is empty, or any name is not in the
    roster, record (cell, name) as unrecognised (cell, '' for an empty Source).
    If exactly one name and it is in the roster, increment the bucket of the
    FIRST seat holding that name; a later seat repeating the name stays
    (0, 0, 0). Two or more names increment nobody. Disposition is never read.
    Pure.
    """
    acc = [[0, 0, 0] for _ in roster]
    unrecognised = []
    seen = set()

    def _note(pair):
        if pair not in seen:
            seen.add(pair)
            unrecognised.append(pair)

    for row in rows:
        if _is_self_check(row):
            continue
        cell = row.get("Source", "")
        names = [n for n in (_normalize_panelist_name(x) for x in cell.split(",")) if n]
        if not names:
            _note((cell, ""))
            continue
        unknown = [n for n in names if n not in roster]
        for name in unknown:
            _note((cell, name))
        if unknown or len(names) != 1:
            continue
        bucket = _severity_bucket(row.get("Severity", ""))
        if bucket is not None:
            acc[roster.index(names[0])][bucket] += 1
    return [tuple(c) for c in acc], unrecognised


_N = r"[0-9]{1,9}"  # ASCII digits, bounded (never-raises)
PANEL_TOKEN_RE = re.compile(rf"panel=({_N}\.{_N}\.{_N}(?:,{_N}\.{_N}\.{_N})*)")


def format_panel_summary(counts: list) -> str:
    """[(2, 1, 0), (0, 0, 1)] -> '2.1.0,0.0.1' (caller prepends 'panel=')."""
    return ",".join(f"{h}.{m}.{l}" for h, m, l in counts)


def parse_panel_summary(notes: str) -> Optional[list]:
    """Return a list of (h, m, l) int tuples for the first token of
    trajectory.notes_tokens(notes) that fullmatches PANEL_TOKEN_RE, or None.

    notes_tokens cuts before the first 'halt vote' token, so text quoted inside
    the halt vote is never read and neighbouring tokens are never consumed.
    Never raises: the bounded ASCII grammar makes every group a safe int().
    """
    for tok in notes_tokens(notes or ""):
        m = PANEL_TOKEN_RE.fullmatch(tok)
        if m:
            return [
                tuple(int(n) for n in group.split("."))
                for group in m.group(1).split(",")
            ]
    return None


# Unit C (CP5, AD13-AD16, DM3, DM5, I7): the panel-log sidecar. One JSON line per
# cleared Latest row, appended after a successful archive write. Nothing in the
# loop reads it; it lives outside every artifact, so it touches no hash.
PANEL_LOG_RELPATH = Path(".sdd") / "panel-log.jsonl"
PANEL_LOG_SCHEMA = 1
_SELF_CHECK_LETTER_RE = re.compile(r"\[SELF-CHECK\]\s*\(([a-f])\)")


def derive_defect_shape(row: dict) -> list:
    """Markers per AD16, in the fixed order scope, self-check, regression."""
    shape = []
    concern = row.get("Concern", "").lstrip()
    for tag in ("contract", "detail", "upstream"):
        if concern.startswith(f"[{tag}]"):
            shape.append(f"scope:{tag}")
            break
    m = _SELF_CHECK_LETTER_RE.search(row.get("Source", ""))
    if m:
        shape.append(f"self-check:{m.group(1)}")
    if "[REGRESSION]" in row.get("Severity", ""):
        shape.append("regression")
    return shape


def build_panel_log_records(rows: list, *, artifact_key: str, pass_n: int,
                            phase: int, date_iso: str, mode: str) -> list:
    """One DM3 dict per row, in table order. Pure."""
    records = []
    for row in rows:
        m = _SEVERITY_CORE_RE.search(row.get("Severity", ""))
        records.append({
            "schema": PANEL_LOG_SCHEMA,
            "artifact": artifact_key,
            "pass": pass_n,
            "phase": phase,
            "date": date_iso,
            "mode": mode,
            "severity": m.group(1) if m else "",
            "regression": "[REGRESSION]" in row.get("Severity", ""),
            "source": row.get("Source", ""),
            "concern": row.get("Concern", ""),
            "disposition": row.get("Disposition", ""),
            "notes": row.get("Notes", ""),
            "shape": derive_defect_shape(row),
        })
    return records


def _panel_log_warning(path, exc) -> str:
    return (
        f"warning: panel-log append to {path} failed "
        f"({exc.__class__.__name__}: {exc}); the artifact archive itself succeeded."
    )


def append_panel_log(root: Path, records: list) -> None:
    """Append records as pure-ASCII JSON lines to root/PANEL_LOG_RELPATH.

    mkdir(root/'.sdd'); open with mode 'a', encoding 'utf-8'; write all lines in
    one write() call. If the file is non-empty and its last byte is not a
    newline (a torn earlier append), the write starts with one newline. Catches
    Exception and prints the DM5 warning. Never raises; no-op on no records.
    """
    if not records:
        return
    path = Path(root) / PANEL_LOG_RELPATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lead = ""
        if path.exists() and path.stat().st_size > 0:
            with open(path, "rb") as fh:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":
                    lead = "\n"
        payload = lead + "".join(
            json.dumps(rec, ensure_ascii=True) + "\n" for rec in records
        )
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(payload)
    except Exception as exc:  # noqa: BLE001 - bookkeeping must never block (R7)
        print(_panel_log_warning(path, exc), file=sys.stderr)


def _is_normal_pass_row(row):
    """A trajectory row is NORMAL if its Notes don't indicate a mode pass or skip.

    Strict-bar and cross-check passes carry distinctive Notes substrings; skipped
    passes start with 'skipped'. Halt votes are NORMAL passes that happen to have
    voted halt and are kept in the population. Elided-summary rows written by
    `blueprint_common.trim_trajectory_table` on approval are bookkeeping, not a
    real pass; their Notes contain `earlier passes elided`.
    """
    notes = row.get("Notes", "").lower()
    if "strict-bar pass" in notes:
        return False
    if "cross-check pass" in notes:
        return False
    if notes.startswith("skipped"):
        return False
    if "earlier passes elided" in notes:
        return False
    return True


def detect_strict_bar_signal(prior_traj_rows, current_pass_row, args, rerouted_def_count=0):
    """Return an advisory string if the strict-bar trigger condition is met.

    Trigger fires when, looking at the last two NORMAL-mode trajectory rows
    (the just-archived row plus the most recent prior NORMAL row):

      1. HIGH delta (current - previous) >= -1 — i.e. HIGH-count is NOT
         meaningfully dropping. A drop of 2 or more is real convergence and
         strict-bar shouldn't fire there.
      2. Phase-dependent ratio condition:
         - Phase 1 and 2: pooled Deferred ratio > 0.5 (the panel is mostly
           producing downstream-deferred work, not this-phase fixes).
         - Phase 3: pooled [detail]-tag ratio > 0.5 (the panel is mostly
           producing single-feature SDD-cycle concerns — the Phase-3 analogue
           of Deferred-downstream, since Phase 3 has no further blueprint
           phase to defer to). Per blueprint-strict.md.

    T7 (R7 refinement): rerouted_def_count counts re-routed-deferral rows in
    the current pass (rows expanded from `Defense: rerouted [DEF-NN]` markers
    by archive_pass.py at archive time). These rows are disposed `Sealed` but
    represent re-raised deferrals — the trigger counts them additively toward
    pooled_deferred so R5's marker-based discipline doesn't silently blind
    the strict-bar signal. rerouted_def_count defaults to 0 to preserve
    backward-compat with existing callers.

    Terminal archives (--terminal) suppress the trigger entirely.

    Detection runs only when the current pass is NORMAL mode (not --strict-bar,
    --cross-check, or --skip); strict-bar can only be entered from NORMAL.
    """
    if args.strict_bar or args.cross_check or args.skip:
        return None
    if getattr(args, "terminal", False):
        return None
    if not _is_normal_pass_row(current_pass_row):
        return None
    prior_normal = [r for r in prior_traj_rows if _is_normal_pass_row(r)]
    if not prior_normal:
        return None
    prev = prior_normal[-1]
    try:
        prev_high = int(prev["HIGHs"])
        curr_high = int(current_pass_row["HIGHs"])
    except (KeyError, ValueError):
        return None
    delta = curr_high - prev_high
    if delta < -1:
        return None

    if args.phase == 3:
        # Phase 3: drive on [detail] tag accumulation. Numerator: count of
        # [detail] tags across two passes (parsed from the tags=dXuYcZ Notes
        # substring stashed at archive time). Denominator: total disposed
        # concerns across two passes (Addressed + Deferred + Sealed columns —
        # symmetric with Phase 1/2's pooled_total formulation). Per
        # blueprint-strict.md pseudo-code: detail_pct = detail_count / len(disposed).
        prev_tags = parse_tag_summary(prev.get("Notes", ""))
        curr_tags = parse_tag_summary(current_pass_row.get("Notes", ""))
        if prev_tags is None or curr_tags is None:
            return None
        pooled_detail = prev_tags["detail"] + curr_tags["detail"]
        try:
            prev_total = (
                int(prev["Addressed"]) + int(prev["Deferred"]) + int(prev["Sealed"])
            )
            curr_total = (
                int(current_pass_row["Addressed"])
                + int(current_pass_row["Deferred"])
                + int(current_pass_row["Sealed"])
            )
        except (KeyError, ValueError):
            return None
        pooled_total = prev_total + curr_total
        if pooled_total == 0:
            return None
        ratio = pooled_detail / pooled_total
        if ratio <= 0.5:
            return None
        return (
            f"STRICT-BAR-SIGNAL: trigger conditions met "
            f"(HIGH delta {delta:+d} across last two NORMAL passes; "
            f"{int(round(ratio * 100))}% of disposed concerns tagged [detail]). "
            f"Ask the user whether to run the next pass with --strict-bar."
        )

    # Phase 1 and 2: existing behavior — driven by Deferred → DOWNSTREAM
    # accumulation in the trajectory's count columns.
    try:
        prev_addressed = int(prev["Addressed"])
        curr_addressed = int(current_pass_row["Addressed"])
        prev_deferred = int(prev["Deferred"])
        curr_deferred = int(current_pass_row["Deferred"])
        prev_sealed = int(prev["Sealed"])
        curr_sealed = int(current_pass_row["Sealed"])
    except (KeyError, ValueError):
        return None
    # T7 (R7): rerouted_def_count is ADDITIVE to curr_deferred. A single row
    # has a single disposition (Deferred OR Sealed, never both), so the two
    # counts are disjoint per pass. See design I7 mixed-pass worked example.
    pooled_deferred = prev_deferred + curr_deferred + rerouted_def_count
    pooled_total = (
        prev_addressed + curr_addressed
        + prev_deferred + curr_deferred
        + prev_sealed + curr_sealed
    )
    if pooled_total == 0:
        return None
    ratio = pooled_deferred / pooled_total
    if ratio <= 0.5:
        return None
    return (
        f"STRICT-BAR-SIGNAL: trigger conditions met "
        f"(HIGH delta {delta:+d} across last two NORMAL passes; "
        f"{int(round(ratio * 100))}% of concerns deferred downstream). "
        f"Ask the user whether to run the next pass with --strict-bar."
    )


def format_halt_notes(halt_rows):
    if not halt_rows:
        return "—"
    if len(halt_rows) == 1:
        r = halt_rows[0]
        return f"halt vote ({r['Source']}: {derive_title(r['Concern'], max_len=40)})"
    summaries = "; ".join(
        f"{r['Source']}: {derive_title(r['Concern'], max_len=30)}"
        for r in halt_rows[:3]
    )
    if len(halt_rows) > 3:
        summaries += "; ..."
    return f"halt votes (n={len(halt_rows)}: {summaries})"




def replace_block(lines, start, end, new_block):
    return lines[:start] + new_block + lines[end:]


def _apply_edits(lines, edits):
    """Apply a set of disjoint line-range replacements to ``lines``.

    Each edit is ``(start, end, new_block)``: replace ``lines[start:end]`` with
    ``new_block``. An insertion is expressed as ``start == end`` (replacing an
    empty range). Edits MUST be pairwise non-overlapping (asserted).

    They are applied sorted by ``start`` DESCENDING, so each applied edit only
    shifts lines BELOW an as-yet-unapplied edit's range — every edit's
    ``(start, end)`` therefore stays valid against the original ``lines``
    coordinate basis. This is the fix for the multi-section reassembly
    corruption (R6/AD9): the previous code applied four section edits
    sequentially using pre-edit offsets, so promoting a Sealed entry (above the
    Deferred section in file order) shifted Deferred and the subsequent Deferred
    edit wrote at a stale offset.

    Returns a new list; does not mutate the input.

    Raises:
        AssertionError: if any two edit ranges overlap (a programming error —
        the four panel sections occupy disjoint spans by construction).
    """
    ordered = sorted(edits, key=lambda e: e[0])
    for (a_start, a_end, _), (b_start, b_end, _) in zip(ordered, ordered[1:]):
        assert a_end <= b_start, (
            f"overlapping edits: ({a_start}, {a_end}) and ({b_start}, {b_end})"
        )
    # Apply in DESCENDING start order — reversed(ordered), reusing the single sort
    # above — so each applied edit only shifts lines below an as-yet-unapplied
    # edit's range, keeping every (start, end) valid against the original basis.
    result = lines[:]
    for start, end, new_block in reversed(ordered):
        result = result[:start] + list(new_block) + result[end:]
    return result


def _orphan_guard(path, old_content, new_content, dry_run=False):
    """R10 guard on the row-append path (DEF-15/DEF-16).

    Scans `old_content` ONCE and diffs the PROSPECTIVE post-append orphan set
    against it (reusing the shared `find_orphaned_trajectory_rows`):
      - If this write would CREATE/STRAND an orphan (one present in new_content
        but not accounted for in old_content) -> REFUSE (no write). Under
        `dry_run` the refusal is surfaced as a notice but does NOT exit — a
        preview must be side-effect-free and non-fatal.
      - If a PRE-EXISTING orphan is present (in both) -> SURFACE a non-blocking
        notice with the shared token (so the operator connects it to the later
        validator FAIL) and proceed with the contiguous append. The orphan is
        never mutated — the operator clears it per the validator's remediation.
    DETECT-and-SURFACE only; never auto-heals.
    """
    pre_existing = find_orphaned_trajectory_rows(old_content)
    pre_counts = Counter(o["text"] for o in pre_existing)
    newly = []
    for o in find_orphaned_trajectory_rows(new_content):
        if pre_counts.get(o["text"], 0) > 0:
            pre_counts[o["text"]] -= 1
        else:
            newly.append(o)
    if newly:
        detail = "; ".join(
            f"line {o['line_no']}: {o['text'].strip()!r}" for o in newly
        )
        if dry_run:
            print(
                f"{ORPHANED_TRAJECTORY_TOKEN} note (dry-run): this archive WOULD "
                f"strand a Trajectory row below the table terminator ({detail}); "
                f"the write would be refused.",
                file=sys.stderr,
            )
        else:
            print(
                f"{ORPHANED_TRAJECTORY_TOKEN} refusing to write {path}: this archive "
                f"would strand a Trajectory row below the table terminator ({detail}). "
                f"No write performed.",
                file=sys.stderr,
            )
            raise SystemExit(1)
    if pre_existing:
        detail = "; ".join(
            f"line {o['line_no']}: {o['text'].strip()!r}" for o in pre_existing
        )
        print(
            f"{ORPHANED_TRAJECTORY_TOKEN} note: {path} already has an orphaned "
            f"Trajectory row ({detail}); the archive appends contiguously and does "
            f"NOT mutate it, but a validator will surface it until you make it "
            f"contiguous or delete it.",
            file=sys.stderr,
        )


def _atomic_write(path, content):
    """Write `content` to `path` atomically (temp-file in the same dir + os.replace).

    archive_pass rewrites approval-bearing artifacts (spec.md / design.md /
    PLAN.md) in place on every panel pass; a plain write_text truncates the file
    first, so a crash / disk-full / SIGKILL mid-write would leave the panel audit
    trail and approved content truncated. The temp file lives beside the target so
    os.replace is atomic; on failure it is removed and the original is untouched.
    encoding='utf-8' matches every other writer in the repo — the format archive
    emits contains non-ASCII (the Deferred arrow, em dash, ellipsis), which the
    platform-default encoding would mojibake or fail to encode (audit R1.3).
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _maybe_trim_trajectory(original_content, new_content):
    """Trim the ### Trajectory table in `new_content`, unless the artifact carries
    a genuine committed v1 hash (a trim would invalidate it).

    Gate (skip the trim) iff ALL hold on the artifact's committed state:
        has_approval(original_content)                       # approval box is [x]
        and read_hash_basis(original_content) == "v1"        # no `**Hash basis:**` line
        and _is_valid_16_hex(read_stored_hash(original_content))  # a real, well-formed
                                                                   # committed hash

    Otherwise apply trim_trajectory_table(new_content). This trims:
      - a never-yet-approved artifact (basis reports "v1" but stored hash is
        'pending' → not skipped) — R2's dominant population and the explicit
        anti-mis-gate case (a bare `== "v2"` gate would wrongly hold it back),
      - a v2- or v3-approved artifact (basis "v2"/"v3" → not skipped;
        trajectory data rows are stripped before hashing under both the frozen v2
        and the current v3 basis → provably hash-neutral), and
      - an approved v1-basis artifact whose stored hash is present but malformed
        (not 16 lowercase hex chars) — mirrors the fail-closed handling in
        `changed_since_stamp`/`is_basis_migration_only`, which both treat a
        malformed stored hash as untrustworthy rather than genuine, so a
        corrupted stamp is never read as "a real committed hash" here either.

    The predicates and trim_trajectory_table are all fail-soft (never raise);
    every fail-soft direction is safe — a missing/unchecked approval, an absent
    Content-Hash line, or a malformed stored hash leans to trim-by-default, only
    a genuine well-formed committed v1 hash leans to skip. `original_content` is
    the pre-pass artifact (approval fields are untouched by archive, so gating on
    it == gating on new_content).
    """
    if (
        has_approval(original_content)
        and read_hash_basis(original_content) == "v1"
        and _is_valid_16_hex(read_stored_hash(original_content))
    ):
        return new_content
    return trim_trajectory_table(new_content)


def write_or_diff(path, old_content, new_content, dry_run):
    _orphan_guard(path, old_content, new_content, dry_run=dry_run)
    if dry_run:
        diff = difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
            n=3,
        )
        sys.stdout.writelines(diff)
    else:
        _atomic_write(path, new_content)


# ---------------------------------------------------------------------------
# Unit D (R7, I5, DM2, DM6, DM7): rigour posture and the working-file root
# ---------------------------------------------------------------------------

_VALIDATOR_PATHS = {
    "sdd": Path(__file__).resolve().parent.parent / "skills" / "spec-driven-dev"
    / "scripts" / "validate_spec.py",
    "blueprint": Path(__file__).resolve().parent.parent / "skills" / "project-blueprint"
    / "scripts" / "validate_blueprint.py",
}
_POSTURE_NOTICE_LEAD = (
    "PANEL-POSTURE-NOTICE: standard is now the default — passes after a loop's "
    "first may run fewer panelists. Persist critical to keep every pass at three: "
)


def _shown_arg(text: str) -> str:
    q = display_arg(text)
    return q.quoted if q.quoted is not None else display_text(text, max_len=80)


def _set_posture_command(tier: str, art_dir: Path) -> str:
    return (f"python {_shown_arg(str(_VALIDATOR_PATHS[tier]))} "
            f"{_shown_arg(str(art_dir))} --set-posture critical")


def posture_notice(tier: Optional[str], art_dir: Path) -> str:
    """DM2's one-time notice; an unknown tier prints both validators' commands."""
    if tier is None:
        cmds = (f"{_set_posture_command('sdd', art_dir)}, or "
                f"{_set_posture_command('blueprint', art_dir)}")
    else:
        cmds = _set_posture_command(tier, art_dir)
    return _POSTURE_NOTICE_LEAD + cmds


def scratch_scope(art: Path) -> Optional[str]:
    """DM7's `<scope>`: `sdd/<spec-dir-basename>` or `blueprint`; None for an
    unknown stem."""
    tier = artifact_tier(art)
    if tier is None:
        return None
    return f"sdd/{Path(art).resolve().parent.name}" if tier == "sdd" else "blueprint"


def scratch_line(root: Path, art: Path) -> str:
    """`PANEL-SCRATCH: root=<root> dir=<root>/.sdd/scratch/<scope>/`, or
    `dir=unresolved` for an unknown stem or a character display_text replaces."""
    root_s = str(root)
    shown_root = display_text(root_s)
    scope = scratch_scope(art)
    if scope is None or shown_root != root_s or display_text(scope) != scope:
        return f"PANEL-SCRATCH: root={shown_root} dir=unresolved"
    return f"PANEL-SCRATCH: root={root_s} dir={root_s}/.sdd/scratch/{scope}/"


def marker_root(art: Path) -> Path:
    """The one root for posture, scratch and the notice (Unit C AD15)."""
    root, _key = _resolve_marker_root_and_key(art, None)
    return Path(root).resolve()


def resolve_run_posture(art: Path, explicit: Optional[str], root: Path):
    """Resolve the posture against `root` and print DM2's stderr warning for a
    rejected persisted value (one bounded line; a non-string value is never
    echoed). Returns the PostureResolution."""
    res = resolve_posture(Path(art).parent, explicit=explicit, project_root=root)
    where = config_path(root)
    tail = (f"using '{res.posture}' ({res.source}). Persist a valid one with "
            f"--set-posture.")
    if res.rejected_non_text:
        print(f"warning: ignoring non-text posture value in {where}; {tail}",
              file=sys.stderr)
    elif res.rejected is not None:
        shown = display_text(res.rejected, max_len=40)
        print(f"warning: ignoring posture '{shown}' in {where} (not one of "
              f"{', '.join(POSTURES)}); {tail}", file=sys.stderr)
    return res


def posture_report(art: Path, explicit: Optional[str], no_notice: bool) -> int:
    """`--posture-report`: read-only apart from the DM6 sentinel. Prints
    PANEL-POSTURE, then the one-time notice, then PANEL-SCRATCH. Exit 0."""
    root = marker_root(art)
    res = resolve_run_posture(art, explicit, root)
    print(f"PANEL-POSTURE: {res.posture} (source: {res.source})")
    sentinel = root / ".sdd" / NOTICE_FILENAME
    if res.source == "default" and not no_notice and not sentinel.is_file():
        print(posture_notice(artifact_tier(art), Path(art).parent))
        try:
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.touch(exist_ok=False)
        except OSError as exc:
            print(f"warning: could not record the posture notice at {sentinel} "
                  f"({exc.__class__.__name__}); it may print again.", file=sys.stderr)
    print(scratch_line(root, art))
    return EXIT_OK


def _hard_fail_zone(text: str) -> list:
    """The hard-fail zone's lines: from the `### Sealed dispositions` heading
    that `find_section` locates inside `## Panel Review` (fence-aware) to end
    of file; the whole file when there is none. Trailing whitespace removed."""
    lines = text.splitlines()
    start = 0
    panel = find_section(lines, H_PANEL_REVIEW)
    if panel is not None:
        sealed = find_section(lines, H_SEALED, panel[0], panel[1])
        if sealed is not None:
            start = sealed[0]
    return [ln.rstrip() for ln in lines[start:]]


def zone_diff(live: str, draft: str) -> list:
    """Unified-diff lines between the two texts' hard-fail zones; empty when
    they match after trailing-whitespace normalisation (C1). Pure."""
    a, b = _hard_fail_zone(live), _hard_fail_zone(draft)
    if a == b:
        return []
    return list(difflib.unified_diff(a, b, "live", "draft", lineterm=""))


def zone_diff_mode(art: Path, draft_arg: str) -> int:
    """`--zone-diff <draft>`: print `ZONE-DIFF: clean` (exit 0) or the diff
    (exit EXIT_ZONE_DIFFERS). An unreadable draft exits 3 and is never clean."""
    draft = Path(draft_arg)
    try:
        draft_text = draft.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        reason = "not found"
    except IsADirectoryError:
        reason = "a directory"
    except UnicodeDecodeError:
        reason = "not valid UTF-8"
    except OSError as exc:
        reason = exc.__class__.__name__
    else:
        reason = None
    if reason is not None:
        print(f"error: cannot read draft {draft} ({reason})", file=sys.stderr)
        return EXIT_OLD_FORMAT_OR_MISSING
    live_text = art.read_text(encoding="utf-8-sig")
    out = zone_diff(live_text, draft_text)
    if not out:
        print("ZONE-DIFF: clean")
        return EXIT_OK
    print("\n".join(out))
    return EXIT_ZONE_DIFFERS


# ---------------------------------------------------------------------------
# Unit D taper engine (R5: AD9, AD10, DM2-DM4, I2). Grouped under one banner so
# a later leaf-module extraction is mechanical [SEAL-03].
# ---------------------------------------------------------------------------

SMALL_MAX_BODY_LINES = 12
SMALL_MAX_ADDRESSED = 3

TAPER_SIZE_CLASSES = (
    ("zero", 1),
    ("small", 2),
    ("large", 3),
)
TAPER_SIZE_CLASSES_DOC = """R5's threshold table: the one home of the size classes.

Evaluated in order; the first match wins.
  zero  — no Latest row is disposed Addressed. The next roster is 1.
  small — no Addressed HIGH, the pass's snapshot is present, at most 12 changed
          body lines and at most 3 Addressed rows. The next roster is 2.
  large — anything else, including an unknown size. The next roster is 3.
"""


@dataclass(frozen=True)
class ChangeSize:
    """AD9's inputs. `body_lines` None means unknown; `reason` is 'measured',
    'no-edit', 'snapshot-absent', 'snapshot-empty', 'no-promote' or
    'unknown-tier'."""

    addressed: int
    addressed_high: int
    body_lines: Optional[int]
    reason: str


def _snapshot_path(root: Path, art: Path, pass_n: int) -> Optional[Path]:
    """DM7's unsuffixed pre-dispatch snapshot for pass `pass_n`:
    `<root>/.sdd/scratch/<scope>/<stem>-snapshot-p<N>.md`; None for an unknown
    stem (no scope can be formed)."""
    scope = scratch_scope(art)
    if scope is None:
        return None
    return Path(root) / ".sdd" / "scratch" / scope / f"{Path(art).stem}-snapshot-p{pass_n}.md"


def _cut_body(text: str) -> list:
    """Lines before the real (fence-aware) `## Panel Review`; the whole file
    when there is none."""
    lines = text.splitlines()
    sec = find_section(lines, H_PANEL_REVIEW)
    return lines if sec is None else lines[:sec[0]]


def _changed_body_lines(before: str, after: str) -> int:
    """Lines starting `+` or `-` in `unified_diff(n=0)`, the two file-header
    lines dropped by position (so a body `---` rule still counts); `@@` hunk
    lines are not counted."""
    diff = list(difflib.unified_diff(_cut_body(before), _cut_body(after), n=0,
                                     lineterm=""))[2:]
    return sum(1 for ln in diff if ln[:1] in ("+", "-"))


def _is_addressed(row: dict) -> bool:
    return disposition_base(row.get("Disposition", "")) == "Addressed"


def measure_change(art: Path, root: Path, latest_rows: list, pass_n: int) -> ChangeSize:
    """AD9. Never raises on I/O: an unreadable snapshot reads as absent."""
    addressed = [r for r in latest_rows if _is_addressed(r)]
    a = len(addressed)
    h = sum(1 for r in addressed if _severity_bucket(r.get("Severity", "")) == 0)
    if a == 0:
        return ChangeSize(0, 0, 0, "no-edit")
    snap = _snapshot_path(root, art, pass_n)
    if snap is None:
        return ChangeSize(a, h, None, "unknown-tier")
    try:
        raw = snap.read_bytes()
        snap_text = raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ChangeSize(a, h, None, "snapshot-absent")
    if not raw:
        return ChangeSize(a, h, None, "snapshot-empty")
    if not (snap.parent / f"{Path(art).stem}-draft-p{pass_n}.md").is_file():
        return ChangeSize(a, h, None, "no-promote")
    try:
        live = Path(art).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ChangeSize(a, h, None, "snapshot-absent")
    return ChangeSize(a, h, _changed_body_lines(snap_text, live), "measured")


def classify_change(size: ChangeSize) -> str:
    """DM3's classes (TAPER_SIZE_CLASSES_DOC), first match wins. Pure."""
    if size.addressed == 0:
        return "zero"
    if (size.addressed_high == 0 and size.body_lines is not None
            and size.body_lines <= SMALL_MAX_BODY_LINES
            and size.addressed <= SMALL_MAX_ADDRESSED):
        return "small"
    return "large"


# DM4: per-phase seat priority over canonical positions (initial values; the
# one home). A roster of k takes the first k positions, sorted into canonical
# order. The anchor (first) seat is the one whose remit covers consistency
# across the whole artifact (AD10).
TAPER_SEAT_PRIORITY = {1: (2, 1, 3), 2: (1, 3, 2), 3: (2, 1, 3)}

# DM2's reason vocabulary, in precedence order (the first that applies prints).
ADVISORY_REASONS = (
    "error", "high-on-tapered-pass", "high-unknown-roster", "addressed-high",
    "unknown-tier", "snapshot-absent", "snapshot-empty", "no-promote", "size",
)
_CLASS_ROSTER = dict(TAPER_SIZE_CLASSES)


@dataclass(frozen=True)
class RosterAdvisory:
    next_pass: int
    roster: int
    survivors: Optional[tuple]   # None means all (full roster)
    size_class: str
    reason: str
    size: Optional[ChangeSize]


def name_survivors(roster: int, tier: Optional[str], phase: int) -> Optional[tuple]:
    """DM4 survivors for a roster of `roster` (< 3), in canonical order, named
    through CANONICAL_ROSTERS; None for a full roster or when a position cannot
    be named (phase 2 position 2 with an unknown tier)."""
    if roster >= SEATS_ROSTER_LENGTH:
        return None
    positions = sorted(TAPER_SEAT_PRIORITY[phase][:roster])
    if tier is None and phase == 2:
        by_pos = {i: n for n, i in _PHASE2_UNION_POSITIONS.items()}
        names = []
        for pos in positions:
            holders = [n for n, i in _PHASE2_UNION_POSITIONS.items() if i == pos]
            if len(holders) != 1:
                return None
            names.append(by_pos[pos])
        return tuple(names)
    canonical = CANONICAL_ROSTERS[("sdd" if tier is None else tier, phase)]
    return tuple(canonical[p - 1] for p in positions)


def _row_roster_kind(notes: str) -> str:
    """'tapered' (a seats= token, or a panel= with fewer than 3 groups),
    'unknown' (no panel= token), or 'full'. Read from the written row's Notes."""
    groups = parse_panel_summary(notes)
    if groups is None:
        return "unknown"
    if seats_token_present(notes) or len(groups) < SEATS_ROSTER_LENGTH:
        return "tapered"
    return "full"


def compute_roster_advisory(*, art: Path, root: Path, tier: Optional[str], phase: int,
                            pass_n: int, latest_rows: list, new_row: dict) -> RosterAdvisory:
    """DM3 overrides, then classes, then DM4 survivors. The HIGH count and the
    tapered/unknown reading come from `new_row`, the Trajectory row just
    written, never from the --panel-roster argument (R5: on-disk inputs)."""
    size = measure_change(art, root, latest_rows, pass_n)
    size_class = classify_change(size)
    try:
        highs = int(new_row.get("HIGHs", "0"))
    except ValueError:
        highs = 0
    kind = _row_roster_kind(new_row.get("Notes", ""))
    if highs > 0 and kind == "tapered":
        reason, roster = "high-on-tapered-pass", 3
    elif highs > 0 and kind == "unknown":
        reason, roster = "high-unknown-roster", 3
    else:
        roster = _CLASS_ROSTER[size_class]
        if size.addressed_high > 0:
            reason = "addressed-high"
        elif size.reason in ("unknown-tier", "snapshot-absent", "snapshot-empty", "no-promote"):
            reason = size.reason
        else:
            reason = "size"
    return RosterAdvisory(pass_n + 1, roster, name_survivors(roster, tier, phase),
                          size_class, reason, size)


def format_roster_advisory(adv: RosterAdvisory) -> str:
    """DM2's advisory line."""
    size = adv.size

    def v(x):
        return "?" if x is None else str(x)

    names = "all" if adv.survivors is None else ",".join(adv.survivors)
    return (
        f"PANEL-ROSTER-ADVISORY: pass {adv.next_pass} roster={adv.roster}/3 "
        f"survivors={names} (class={adv.size_class}; reason={adv.reason}; "
        f"body-lines={v(size.body_lines if size else None)}; "
        f"addressed={v(size.addressed if size else None)}; "
        f"addressed-high={v(size.addressed_high if size else None)})"
    )


def _guard_posture_flags(args) -> None:
    """C1's guard rows for the read-only modes --zone-diff and --posture-report
    and for --no-notice: each is refused with the other mode and with --skip,
    --strict-bar, --cross-check, --check and --dry-run, and --no-notice is
    refused without --posture-report. Exit 1, before the artifact-exists
    check. (tests/_flag_matrix.py generates the cases.)"""
    others = [("--zone-diff", args.zone_diff is not None),
              ("--posture-report", args.posture_report), ("--no-notice", args.no_notice),
              ("--skip", args.skip), ("--strict-bar", args.strict_bar),
              ("--cross-check", args.cross_check), ("--check", args.check),
              ("--dry-run", args.dry_run)]
    zone = args.zone_diff is not None
    for flag, on in (("--zone-diff", zone), ("--posture-report", args.posture_report),
                     ("--no-notice", args.no_notice)):
        if not on:
            continue
        for other, other_on in others:
            if other_on and other != flag and not (
                {flag, other} == {"--posture-report", "--no-notice"}
            ):
                print(f"error: {flag} cannot be combined with {other}", file=sys.stderr)
                sys.exit(EXIT_FORMAT_VIOLATION)
    if args.no_notice and not args.posture_report:
        print("error: --no-notice is valid only with --posture-report", file=sys.stderr)
        sys.exit(EXIT_FORMAT_VIOLATION)


def main():
    parser = argparse.ArgumentParser(description="Archive a panel-review pass.")
    parser.add_argument("artifact", help="Path to artifact (spec.md / design.md / etc.)")
    parser.add_argument(
        "--skip", metavar="REASON",
        help="Record a skipped (mechanical-only) pass without processing Latest",
    )
    parser.add_argument(
        "--strict-bar", action="store_true",
        help="Stamp the trajectory row as a strict-bar pass (counts toward cap)",
    )
    parser.add_argument(
        "--cross-check", action="store_true",
        help="Stamp the trajectory row as a cross-check pass (excluded from cap)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the diff that would be applied; do not modify the file",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Validate format contract only; do not archive",
    )
    parser.add_argument(
        "--phase", type=int, choices=[1, 2, 3], required=True,
        help="Phase number (1=first artifact, 2=middle, 3=terminal). "
             "Drives phase-dependent trigger logic — Phase 2/3 count "
             "[upstream]-tagged rows as halt votes, and Phase 3 uses "
             "[detail]-tag accumulation for the strict-bar signal.",
    )
    parser.add_argument(
        "--terminal", action="store_true",
        help="Mark this archive as a terminal-phase artifact (PLAN.md, tasks.md, "
             "or a SCOPE.md that the user has explicitly marked terminal). "
             "Suppresses ### Deferred dispositions auto-insert and promotion; "
             "rejects Deferred-disposed rows in Latest.",
    )
    parser.add_argument(
        "--panel-roster", action="append", metavar="NAMES", default=None,
        help="This pass's dispatched panelists in dispatch order, comma-separated "
             "(bare names; a 'telescoping-sdd:' prefix is stripped). Stamps a "
             "panel=H.M.L,... unique-yield token in Trajectory Notes. Omit to stamp "
             "nothing. Ignored with --skip.",
    )
    parser.add_argument(
        "--posture", choices=list(POSTURES), default=None,
        help="This run's rigour posture (critical, standard or vibe); overrides "
             "the persisted posture for this run only.",
    )
    parser.add_argument(
        "--posture-report", action="store_true",
        help="Read-only: print PANEL-POSTURE, the one-time default notice and "
             "PANEL-SCRATCH (the working-file root and directory), then exit 0.",
    )
    parser.add_argument(
        "--zone-diff", metavar="DRAFT", default=None,
        help="Read-only scope-verify check (a): compare the hard-fail zone (from "
             "### Sealed dispositions to end of file) of the artifact and DRAFT. "
             "Prints 'ZONE-DIFF: clean' and exits 0, or prints the diff and exits 4.",
    )
    parser.add_argument(
        "--no-notice", action="store_true",
        help="With --posture-report only: suppress the one-time notice and do not "
             "record it as shown (for a root lookup).",
    )
    args = parser.parse_args()

    if sum(bool(x) for x in (args.skip, args.strict_bar, args.cross_check)) > 1:
        print(
            "error: --skip, --strict-bar, and --cross-check are mutually exclusive",
            file=sys.stderr,
        )
        sys.exit(EXIT_FORMAT_VIOLATION)
    _guard_posture_flags(args)

    art = Path(args.artifact)
    if not art.is_file():
        print(f"error: artifact not found: {art}", file=sys.stderr)
        sys.exit(EXIT_OLD_FORMAT_OR_MISSING)

    # Unit D (I5): read-only, before the TERMINAL_FILENAMES guard, so a
    # terminal artifact needs no --terminal for it.
    if args.posture_report:
        sys.exit(posture_report(art, args.posture, args.no_notice))
    if args.zone_diff is not None:
        sys.exit(zone_diff_mode(art, args.zone_diff))

    if _strip_numeric_prefix(art.name) in TERMINAL_FILENAMES and not args.terminal:
        print(
            f"error: '{art.name}' is in the TERMINAL_FILENAMES registry "
            f"(case-sensitive: PLAN.md, tasks.md, tasks-python.md, tasks-java.md). "
            f"Archive with --terminal. Note: the registry is case-sensitive — "
            f"'plan.md' does NOT match; rename to canonical case if needed.",
            file=sys.stderr,
        )
        sys.exit(EXIT_FORMAT_VIOLATION)

    content = art.read_text(encoding="utf-8-sig")  # BOM-tolerant; rewrite drops it (R2.5)
    lines = content.splitlines()

    panel = find_section(lines, H_PANEL_REVIEW)
    if panel is None:
        print(f"error: '## Panel Review' section not found in {art}", file=sys.stderr)
        sys.exit(EXIT_OLD_FORMAT_OR_MISSING)
    p_start, p_end = panel

    traj = find_section(lines, H_TRAJECTORY, p_start + 1, p_end)
    sealed = find_section(lines, H_SEALED, p_start + 1, p_end)
    latest = find_section(lines, H_LATEST, p_start + 1, p_end)
    if traj is None or sealed is None or latest is None:
        print(
            f"error: panel-review section missing required sub-sections.\n"
            f"  expected: {H_TRAJECTORY}, {H_SEALED}, {H_LATEST}\n"
            f"  manual migration required.",
            file=sys.stderr,
        )
        sys.exit(EXIT_OLD_FORMAT_OR_MISSING)
    t_start, _ = traj
    s_start, s_end = sealed
    l_start, l_end = latest

    # T4 (R1, R2): auto-insert ### Deferred dispositions on legacy non-terminal
    # artifacts. Idempotent — no-op if section already present. Skipped under
    # --terminal (terminal artifacts must not carry the section per R1) and
    # under --check (validation-only mode, no writes). Per design C3, the
    # inserted block is `[blank, header, blank]` placed at l_start (before the
    # ### Latest pass detail heading); l_start/l_end shift by +3, other indices
    # unaffected because the insert lands below them in file order.
    is_terminal = _is_terminal(content, art, args.terminal)
    deferred = find_section(lines, H_DEFERRED, p_start + 1, p_end)
    auto_inserted = False
    if deferred is None and not is_terminal and not args.check:
        lines = lines[:l_start] + ["", H_DEFERRED, ""] + lines[l_start:]
        l_start += 3
        l_end += 3
        p_end += 3
        auto_inserted = True

    # T5 (R2): re-find ### Deferred dispositions section post-auto-insert and
    # parse existing [DEF-NN] entries for promotion ID continuity. Skipped for
    # terminal artifacts (they don't have the section).
    def_entries = []
    d_start = None
    d_end = None
    if not is_terminal:
        deferred_post = find_section(lines, H_DEFERRED, p_start + 1, p_end)
        if deferred_post is not None:
            d_start, d_end = deferred_post
            def_entries = parse_defs(lines, d_start, d_end)

    # Two separate collectors, so each row's diagnostic can name the table it
    # came from and the consequence that actually applies to it. A single
    # shared list would force one generic message across both tables (AD14).
    latest_malformed = []
    traj_malformed = []
    latest_rows, latest_table = parse_table(
        lines, l_start, l_end,
        malformed=latest_malformed, table_name="Latest pass detail",
    )
    traj_rows, traj_table = parse_table(
        lines, t_start, traj[1],
        malformed=traj_malformed, table_name="Trajectory",
    )
    # Refuse to archive a pass containing a row that could not be parsed. Sited
    # here rather than inside parse_table because the pinned warn test
    # constrains that function to warn-and-return. Placed before the
    # validate_row loop and before the --check early return, so --check gives
    # the same verdict as a real archive and nothing is written first.
    if latest_malformed or traj_malformed:
        for m in latest_malformed + traj_malformed:
            print(
                f"error: {m['table']} row at line {m['line_num']} has "
                f"{m['actual']} cells, expected {m['expected']} — escape a "
                f"literal pipe as '\\|'. Row: {m['excerpt']}",
                file=sys.stderr,
            )
        if latest_malformed:
            print(
                "error: refusing to archive — an unparsed Latest pass detail row "
                "is invisible to the 'User input needed' gate and to "
                "seal/deferral promotion.",
                file=sys.stderr,
            )
        if traj_malformed:
            print(
                "error: refusing to archive — an unparsed Trajectory row is not "
                "counted, so pass numbering and the strict-bar signal are "
                "computed from an incomplete table.",
                file=sys.stderr,
            )
        sys.exit(EXIT_FORMAT_VIOLATION)
    seal_entries = parse_seals(lines, s_start, s_end)

    violations = []
    if latest_table is not None:
        _, _, first, _ = latest_table
        for idx, row in enumerate(latest_rows):
            try:
                validate_row(row, line_num=first + idx + 1)
            except FormatViolation as v:
                violations.append(v)
    if violations:
        for v in violations:
            print(f"format violation (line {v.line_num}): {v}", file=sys.stderr)
        sys.exit(EXIT_FORMAT_VIOLATION)

    if args.check:
        print(f"OK: format valid; {len(latest_rows)} row(s) in Latest pass detail.")
        sys.exit(EXIT_OK)

    # T5 (R2): terminal-Deferred-forbidden check. Terminal artifacts must not
    # carry Deferred-disposed rows in Latest (per R1 + spec § terminal phase).
    if is_terminal:
        forbidden = [
            r for r in latest_rows
            if disposition_base(r.get("Disposition", "")) == "Deferred"
        ]
        if forbidden:
            r = forbidden[0]
            concern = r.get("Concern", "")[:80]
            print(
                f"error: Terminal-phase archive: Deferred disposition is forbidden. "
                f"Row: Severity={r.get('Severity', '')} Source={r.get('Source', '')} "
                f"Concern={concern}. Remove or re-dispose before archiving with --terminal.",
                file=sys.stderr,
            )
            sys.exit(EXIT_FORMAT_VIOLATION)

    unresolved = [
        r for r in latest_rows
        if disposition_base(r.get("Disposition", "")) == "User input needed"
    ]
    if unresolved:
        print(
            f"error: {len(unresolved)} 'User input needed' concern(s) in Latest pass detail.\n"
            f"  resolve them (re-disposition as Addressed / Deferred / Sealed / "
            f"Accepted as risk) before archiving.",
            file=sys.stderr,
        )
        sys.exit(EXIT_USER_INPUT_NEEDED)

    # Use blueprint_common._is_ascii_int (NOT str.isdigit(), which is True for
    # non-int-convertible Unicode digits like '²' that then crash int()), and
    # r.get("Pass", "") (NOT r["Pass"], which KeyErrors on a renamed header) so
    # the writer's next-pass computation matches the hash/anchor reader exactly
    # (audit R2.7).
    pass_nums = [
        int(cell)
        for cell in (r.get("Pass", "").strip() for r in traj_rows)
        if _is_ascii_int(cell)
    ]
    next_pass = max(pass_nums, default=0) + 1
    seal_ids = [e["id"] for e in seal_entries]
    next_seal = max(seal_ids, default=0) + 1

    new_seals = []
    new_defs = []  # T5: Deferred-row promotions (parallel to new_seals)
    run_posture = None  # resolved only on NORMAL / --strict-bar / --cross-check (DM2)
    if args.skip:
        if latest_rows:
            print(
                f"warning: --skip used but Latest pass detail has {len(latest_rows)} row(s); "
                f"skip mode appends a trajectory row WITHOUT processing those rows.",
                file=sys.stderr,
            )
        new_traj_row = {
            "Pass": str(next_pass),
            "Date": date.today().isoformat(),
            "HIGHs": "—",
            "Regressions": "—",
            "Addressed": "—",
            "Deferred": "—",
            "Sealed": "—",
            "Notes": f"skipped (mechanical: {args.skip})",
        }
        latest_to_clear = False
    else:
        # Unit D (DM2): NORMAL, --strict-bar and --cross-check resolve the
        # posture (--check and --skip never do).
        run_posture = resolve_run_posture(art, args.posture, marker_root(art))
        mode_pass = args.strict_bar or args.cross_check
        if not latest_rows and not mode_pass:
            print(
                "warning: Latest pass detail is empty; nothing to archive.",
                file=sys.stderr,
            )
            if auto_inserted:
                # T4: write the auto-inserted section even when there's no archive work
                new_content = "\n".join(lines) + ("\n" if content.endswith("\n") else "")
                # R2: trim the trajectory before writing (gated for committed-v1)
                new_content = _maybe_trim_trajectory(content, new_content)
                write_or_diff(art, content, new_content, args.dry_run)
            sys.exit(EXIT_OK)
        highs, sealed_high, unresolved_highs = high_disposition_counts(latest_rows)
        regressions = sum(1 for r in latest_rows if "[REGRESSION]" in r["Severity"])
        addressed = sum(
            1 for r in latest_rows
            if disposition_base(r["Disposition"]) == "Addressed"
        )
        deferred = sum(
            1 for r in latest_rows
            if disposition_base(r["Disposition"]) == "Deferred"
        )
        sealed_count = sum(
            1 for r in latest_rows
            if disposition_base(r["Disposition"]) in DEFENDED_DISPOSITIONS
        )
        halt_rows = [
            r for r in latest_rows
            if disposition_base(r["Disposition"]) == "Halt and re-scope"
        ]
        # Phases 2 and 3: [upstream]-tagged HIGH panel rows auto-route to
        # halt votes alongside explicit "Halt and re-scope" dispositions.
        # Phase 1 has no upstream artifact to halt back to, so [upstream]
        # doesn't apply. MED/LOW rows and [SELF-CHECK] rows are excluded
        # from auto-routing (see _is_panel_tagged_high).
        if args.phase in (2, 3):
            upstream_rows = [
                r for r in latest_rows
                if _is_panel_tagged_high(r)
                and _starts_with_tag(r.get("Concern", ""), "[upstream]")
            ]
            for r in upstream_rows:
                if r not in halt_rows:
                    halt_rows.append(r)
        notes = format_halt_notes(halt_rows)
        tag_parts = []
        if args.strict_bar:
            tag_parts.append(STAMP_STRICT_BAR)
        elif args.cross_check:
            tag_parts.append(STAMP_CROSS_CHECK)
        if unresolved_highs == 0:
            if sealed_high == 0:
                tag_parts.append(STAMP_CONVERGED_NO_HIGH)
            else:
                tag_parts.append(STAMP_CONVERGED_SEALED)
                tag_parts.append(f"sealed={sealed_high}")
        # Unit C (CP4, AD9, AD11): the panel= unique-yield token, before tags=
        # and outside its phase gate. A roster/Source mismatch warns on stderr
        # and suppresses the token; nothing else changes.
        roster = parse_panel_roster(args.panel_roster)
        if roster is not None:
            counts, unrecognised = count_panel_yield(latest_rows, roster)
            order_warning = check_roster_order(roster, artifact_tier(art), args.phase)
            roster_csv = ",".join(roster)
            for cell, name in unrecognised:
                if name == "":
                    print(
                        f"warning: panel= not stamped — Source {cell!r} is empty, "
                        f"so the row cannot be attributed to --panel-roster {roster_csv}.",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"warning: panel= not stamped — Source {cell!r} names "
                        f"{name!r}, which is not in --panel-roster {roster_csv}.",
                        file=sys.stderr,
                    )
            if order_warning:
                print(order_warning, file=sys.stderr)
            if not unrecognised and not order_warning:
                tag_parts.append(f"panel={format_panel_summary(counts)}")
                # Unit D (AD11, DM1): a tapered pass records its dispatched
                # canonical seat positions directly after panel=.
                positions = roster_seat_positions(roster, artifact_tier(art), args.phase)
                if positions is not None:
                    tag_parts.append(format_seats_record(positions))
        # Stash tag counts for Phase 2/3 so detect_strict_bar_signal can read
        # them across passes (Latest is cleared after each archive).
        if args.phase in (2, 3):
            tag_counts = count_tags(latest_rows)
            tag_parts.append(f"tags={format_tag_summary(tag_counts)}")
        # AD4: a fixed whole token whenever any Latest row is disposed Halt and
        # re-scope (any phase, any severity), written before the halt-vote text
        # so the gate's tokeniser (cut at the first `halt vote`) still sees it.
        if any(
            disposition_base(r.get("Disposition", "")) == "Halt and re-scope"
            for r in latest_rows
        ):
            tag_parts.append(STAMP_HALT_DISPOSITION)
        if tag_parts:
            tag = "; ".join(tag_parts)
            notes = tag if notes == "—" else f"{tag}; {notes}"
        new_traj_row = {
            "Pass": str(next_pass),
            "Date": date.today().isoformat(),
            "HIGHs": str(highs),
            "Regressions": str(regressions),
            "Addressed": str(addressed),
            "Deferred": str(deferred),
            "Sealed": str(sealed_count),
            "Notes": notes,
        }
        # Phase-1 row classification (T5 + T6): single iteration over latest_rows
        # building both new_seals (for Sealed/Accepted-as-risk rows) and new_defs
        # (for Deferred rows). T6 marker-expansion logic lives in the Sealed branch.
        next_def = next_def_id(def_entries)
        for r in latest_rows:
            d = disposition_base(r["Disposition"])
            if d in DEFENDED_DISPOSITIONS:
                title = derive_title(r["Concern"])
                notes_field = r.get("Notes", "")
                rerouted_def = False
                # T6 (C5, R5, R7): marker classification — strict first, then
                # wide near-miss. Strict match expands to canonical Defense via
                # DEFERRED_REDISPOSITION_PREFIX (R7 single source of truth).
                m_strict = MARKER_STRICT_PAT.match(notes_field)
                if m_strict:
                    def_id_int = int(m_strict.group(1))
                    def_lookup = lookup_def(def_entries, def_id_int)
                    if def_lookup is None:
                        print(
                            f"error: Row in Latest pass detail references "
                            f"[DEF-{def_id_int:02d}] in marker "
                            f"'Defense: rerouted [DEF-{def_id_int:02d}]' but no "
                            f"matching [DEF-{def_id_int:02d}] entry exists in "
                            f"### Deferred dispositions. Check the DEF ID or "
                            f"add the entry manually.",
                            file=sys.stderr,
                        )
                        sys.exit(EXIT_FORMAT_VIOLATION)
                    target = def_lookup["target"]
                    # Canonical text uses DEFERRED_REDISPOSITION_PREFIX as the
                    # write-side anchor that R7's trigger reads back.
                    defense = (
                        f"already routed to {target} as [DEF-{def_id_int:02d}]; "
                        f"no new evidence presented this pass"
                    )
                    rerouted_def = True
                elif MARKER_WIDE_PAT.search(notes_field):
                    notes_excerpt = notes_field[:80]
                    print(
                        f"error: Row in Latest pass detail has Notes resembling "
                        f"the re-routed-deferral marker but does not match the "
                        f"strict format '^Defense: rerouted \\[DEF-NN\\]$' "
                        f"(where NN is the zero-padded 2-digit ID, case-sensitive "
                        f"'Defense: rerouted', no hyphen in 'rerouted'). "
                        f"Found: {repr(notes_excerpt)}. Did you mean "
                        f"'Defense: rerouted [DEF-NN]'? See panel-review.md "
                        f"step 3 for the marker contract.",
                        file=sys.stderr,
                    )
                    sys.exit(EXIT_FORMAT_VIOLATION)
                else:
                    defense = extract_defense(notes_field)
                disp_label = "user-directed" if d == "Sealed" else "accepted-as-risk"
                new_seals.append({
                    "id": next_seal,
                    "title": title,
                    "pass": next_pass,
                    "disposition": disp_label,
                    "defense": defense,
                    "rerouted_def": rerouted_def,
                })
                next_seal += 1
            elif d == "Deferred":
                # T5 (R2): validate Routed because: presence
                notes_field = r.get("Notes", "")
                if "Routed because:" not in notes_field:
                    concern = r.get("Concern", "")[:80]
                    print(
                        f"error: Row in Latest pass detail has Disposition "
                        f"'{r['Disposition']}' but Notes lacks required "
                        f"'Routed because: <reason>' prefix. Offending row: "
                        f"Severity={r.get('Severity', '')} Source={r.get('Source', '')} "
                        f"Concern={concern}. Add 'Routed because:' to Notes and retry.",
                        file=sys.stderr,
                    )
                    sys.exit(EXIT_FORMAT_VIOLATION)
                # T5 (R2): extract and validate target shape
                disposition_str = r["Disposition"]
                target = disposition_str.split("→", 1)[1].strip() if "→" in disposition_str else ""
                if not TARGET_PAT.match(target):
                    print(
                        f"error: Row in Latest pass detail has Disposition "
                        f"'{disposition_str}' with target '{target}' that does not "
                        f"match the required filename shape '^[A-Za-z0-9._/-]+\\.md$' "
                        f"(no traversal segments). Targets must be plain markdown "
                        f"filenames (e.g., 'tasks.md', 'PLAN.md', 'subdir/tasks.md'). "
                        f"Fix the disposition and retry.",
                        file=sys.stderr,
                    )
                    sys.exit(EXIT_FORMAT_VIOLATION)
                # T5: queue for promotion
                title = derive_title(r["Concern"])
                rationale = notes_field.split("Routed because:", 1)[1].strip().rstrip(".")
                new_defs.append({
                    "id": next_def,
                    "title": title,
                    "target": target,
                    "pass_n": next_pass,
                    "rationale": rationale,
                })
                next_def += 1
        latest_to_clear = True

    # Format ONLY the NEW entries. When a section already has entries we INSERT
    # these after the last existing one rather than replacing the whole entry
    # span — a span replace rebuilt from matched lines silently deleted any
    # interleaved non-matching line (a hand-wrapped entry's continuation, an HTML
    # comment, operator prose) the strict single-line patterns don't match (audit
    # 3.5f). For an empty section the existing-entries list is [] so the two forms
    # coincide.
    new_seal_entry_lines = [
        f"- `[SEAL-{s['id']:02d}]` **{s['title']}** "
        f"(pass {s['pass']}, {s['disposition']}) — Defense: {s['defense']}."
        for s in new_seals
    ]
    # T5 (R2): build Deferred-section entry lines
    new_def_entry_lines = [
        f"- `[DEF-{dd['id']:02d}]` **{dd['title']}** "
        f"→ {dd['target']} (pass {dd['pass_n']}) — Routed because: {dd['rationale']}."
        for dd in new_defs
    ]

    new_latest_block = render_table(LATEST_COLS, [])

    # R6 (AD9/I6): express each section rewrite UNIFORMLY as a disjoint
    # (start, end, new_block) replacement tuple against the post-auto-insert
    # `lines`, then apply them all via _apply_edits sorted descending-by-start.
    # An empty-section insertion is just (anchor, anchor, block) with
    # start == end — collapsing the heading-anchor-vs-table-index split into one
    # coordinate basis. Each tuple is appended ONLY under its existing guard, so
    # a --skip / converged-empty pass still yields as few as one edit (Trajectory
    # only). This replaces the previous sequential replace_block/insert calls
    # that used stale pre-edit offsets (corrupting Deferred when Sealed shifted).
    base_edits = []

    if latest_to_clear:
        if latest_table is not None:
            h, _, _, last = latest_table
            base_edits.append((h, last, new_latest_block))
        else:
            base_edits.append((l_start + 1, l_start + 1, [""] + new_latest_block))

    if new_seals:
        if seal_entries:
            # Insert AFTER the last existing entry (start == end), preserving the
            # existing entry span verbatim — no whole-span rewrite (3.5f).
            last_seal = seal_entries[-1]["line_idx"] + 1
            base_edits.append((last_seal, last_seal, new_seal_entry_lines))
        else:
            base_edits.append((s_start + 1, s_start + 1, [""] + new_seal_entry_lines))

    # T5 (R2): write Deferred-section promotions
    if new_defs and d_start is not None:
        if def_entries:
            last_def = def_entries[-1]["line_idx"] + 1
            base_edits.append((last_def, last_def, new_def_entry_lines))
        else:
            base_edits.append((d_start + 1, d_start + 1, [""] + new_def_entry_lines))

    # AC-5.11 / AD3: every archived row (normal, mode-stamped and --skip) ends
    # with a provenance token `prov=<hash>` whose hash is compute_content_hash
    # of the written file. `build` renders the whole new file for a given token
    # hex; stamp_provenance renders it with a same-width placeholder, hashes it,
    # re-renders with that hash and verifies the hash did not move (Trajectory
    # data rows are hash-excluded, so only the column widths matter).
    def _with_token(notes: str, prov_hex: str) -> str:
        token = provenance_token(prov_hex)
        return token if notes == "—" else f"{notes}; {token}"

    def build(prov_hex: str) -> str:
        row = dict(new_traj_row, Notes=_with_token(new_traj_row["Notes"], prov_hex))
        traj_block = render_trajectory_table(traj_rows + [row])
        edits = list(base_edits)
        if traj_table is not None:
            h, _, _, last = traj_table
            edits.append((h, last, traj_block))
        else:
            edits.append((t_start + 1, t_start + 1, [""] + traj_block))
        new_lines = _apply_edits(lines, edits)
        out = "\n".join(new_lines) + ("\n" if content.endswith("\n") else "")
        # R2: trim the trajectory before writing (gated for committed-v1 artifacts)
        return _maybe_trim_trajectory(content, out)

    try:
        new_content = stamp_provenance(build, compute_content_hash)
    except RuntimeError as exc:
        print(f"error: {exc}; nothing was written.", file=sys.stderr)
        sys.exit(EXIT_FORMAT_VIOLATION)
    new_traj_row = dict(
        new_traj_row,
        Notes=_with_token(new_traj_row["Notes"], compute_content_hash(new_content)),
    )
    write_or_diff(art, content, new_content, args.dry_run)

    # Unit C (CP5, AD13): append the cleared rows to the panel-log sidecar, only
    # after a successful write. Nothing here can change the exit code or stdout.
    if latest_to_clear and latest_rows and not args.dry_run:
        log_path = PANEL_LOG_RELPATH  # reported as-is if root resolution fails
        try:
            root, key = _resolve_marker_root_and_key(art, None)
            log_path = root / PANEL_LOG_RELPATH
            mode = (
                "strict-bar" if args.strict_bar
                else "cross-check" if args.cross_check
                else "normal"
            )
            append_panel_log(root, build_panel_log_records(
                latest_rows, artifact_key=key, pass_n=next_pass, phase=args.phase,
                date_iso=new_traj_row["Date"], mode=mode))
        except Exception as exc:  # noqa: BLE001 - never fail after the write (R7)
            print(_panel_log_warning(log_path, exc), file=sys.stderr)

    # T7 (R7): count rerouted-deferral rows from this pass for trigger refinement
    rerouted_def_count = sum(1 for s in new_seals if s.get("rerouted_def", False))
    advisory = detect_strict_bar_signal(
        traj_rows, new_traj_row, args, rerouted_def_count=rerouted_def_count
    )
    if advisory:
        print(advisory)

    # Unit D (R5, R7): the next pass's roster, on a NORMAL archive under the
    # standard posture only. Never changes the exit code.
    if (run_posture is not None and not (args.strict_bar or args.cross_check)
            and run_posture.posture == "standard"):
        try:
            line = format_roster_advisory(compute_roster_advisory(
                art=art, root=marker_root(art), tier=artifact_tier(art), phase=args.phase,
                pass_n=next_pass, latest_rows=latest_rows, new_row=new_traj_row))
        except Exception:  # noqa: BLE001 — fail to the full roster
            line = format_roster_advisory(RosterAdvisory(
                next_pass + 1, 3, None, "large", "error", None))
        print(line)

    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
