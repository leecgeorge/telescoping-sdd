#!/usr/bin/env python3
"""panel_yield.py — read-only, maintainer-facing per-panelist yield report.

Reads the `### Trajectory` table of each artifact given (files, or directories
walked recursively for `*.md`) and reports the `panel=H.M.L,…` unique-yield
tokens that `archive_pass.py --panel-roster` stamps, per artifact and per pass.

Results are strictly per artifact: seat k means a different panelist in each
tier and phase, so a cross-artifact sum would mix rosters. The groups are
positional and decode against the roster in force when the row was written
(`## Panelists per phase` in each tier's `panel-review.md`). This report never
resolves a seat to a panelist name. Maintainer obligation: any change to either
tier's `## Panelists per phase`, or to `archive_pass.CANONICAL_ROSTERS`, must be
recorded in `CHANGELOG.md` as a roster change with its version, so historical
stamps stay decodable.

It opens files read-only and writes only to stdout and stderr: no artifact,
marker, hash or approval state is touched.

Usage:
    panel_yield.py PATH [PATH ...] [--json]

Exit codes:
    0  success
    1  one or more PATHs do not exist (named on stderr; the others are reported)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from archive_pass import ARTIFACT_STEMS, parse_panel_summary  # noqa: E402
from trajectory import (  # noqa: E402
    STAMP_CROSS_CHECK,
    STAMP_STRICT_BAR,
    TRAJECTORY_ELIDED_NOTES_RE,
    _strip_numeric_prefix,
    parse_seats_record,
    parse_trajectory_rows,
    seats_token_present,
)

MED_LOW_CAVEAT = (
    "MED/LOW confidence caveat. HIGH counts are anchor-keyed: every HIGH a "
    "panelist raised carries an id the orchestrator reconciles. MED and LOW "
    "carry no such key, so the three numbers in a group are not "
    "equal-confidence. Two error sources act on MED/LOW. Upward: merging "
    "MED/LOW concerns across panelists is a prose judgment with no id key, and "
    "under-merging inflates a seat's count; nothing addresses this. Downward: a "
    "condenser omission deflates the count; the orchestrator's census detects "
    "it and routes the pass to the degraded fallback. Net direction: the MED/LOW "
    "figures are slightly high, and that holds only because the census closes "
    "the downward path. Residual: a pass whose census was skipped or miscounted "
    "leaves the error bidirectional, with no knowable net direction for that "
    "pass. Even a performed census has limits: it cannot see a MED-to-LOW (or "
    "LOW-to-MED) re-grade of a row that is present; opposite errors at two "
    "severities can cancel in the total; and on a degraded-path pass the Source "
    "cells were projected by the orchestrator, not validated. Sample gaps: a "
    "seat whose findings file was never written is stamped 0.0.0 on the "
    "degraded path, indistinguishable from a quiet panelist; a Phase-2 stamp on "
    "an artifact of unknown tier was never order-checked; a pass whose token was "
    "suppressed by a roster or Source mismatch carries no token and reads as no "
    "data, like a pass archived with the roster omitted; on that same "
    "unknown-tier Phase-2 path a roster that repeats a name credits the first "
    "seat holding it and leaves the later duplicate seat at 0.0.0, which looks "
    "like a quiet seat; and a fully quiet NORMAL pass writes no Trajectory row, "
    "so the quietest passes are under-represented."
)

YIELD_NOT_COST = (
    "Yield-not-cost statement. These figures measure yield only, not cost. The "
    "orchestrator cannot see a subagent's tool-call count, so every cost figure "
    "in this repository has been counted by hand from transcripts. Cost is "
    "reproducible on demand in a one-off A/B comparison, whereas yield "
    "attribution is time-dependent and destroyed at archive, which is why only "
    "yield is instrumented."
)

_ELIDED_LABEL = "…"

# Unit D (R6, C6): notes for rows that are not comparable with full-roster rows.
_CANONICAL_SEATS = 3
_NOT_RUN = "— not run —"
_UNRESOLVED_NOTE = "seats unresolved — not comparable"


def _tapered_note(positions) -> str:
    return (f"tapered (seats {','.join(str(p) for p in positions)}): "
            "not comparable with full-roster rows for unique yield")


@dataclass(frozen=True)
class PassYield:
    """DM4: one reported Trajectory row."""

    pass_label: str
    seats: Optional[List[Tuple[int, int, int]]]
    note: str
    # Unit D DM10: canonical 1-based positions of a tapered row's dispatched
    # seats (None for a full roster or a pre-feature row), and whether the
    # row's unique yield is comparable with full-roster rows.
    dispatched_positions: Optional[Tuple[int, ...]] = None
    comparable: bool = False


@dataclass(frozen=True)
class ArtifactYield:
    """DM4: one artifact's report."""

    path: str
    tier: Optional[str]
    phase: Optional[int]
    elided: int
    passes: List[PassYield]
    status: str


def collect_artifacts(paths: list) -> list:
    """Expand directories to their `*.md` files (recursive, sorted); keep files."""
    out = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            out.extend(sorted(q for q in p.rglob("*.md") if q.is_file()))
        else:
            out.append(p)
    return out


def _stem_entry(path: Path) -> Optional[Tuple[str, int]]:
    name = _strip_numeric_prefix(path.name)
    stem = name[:-3] if name.endswith(".md") else name
    return ARTIFACT_STEMS.get(stem)


def _note_for(row, seats) -> str:
    if row.is_skip:
        return "archived --skip"
    if STAMP_STRICT_BAR in row.tokens:
        return "strict-bar"
    if STAMP_CROSS_CHECK in row.tokens:
        return "cross-check"
    if seats is None:
        return "no panel= token"
    return ""


def read_artifact_yield(path: Path) -> ArtifactYield:
    """Always returns an ArtifactYield. status='no_panel_review' when
    parse_trajectory_rows returns []; 'unreadable' when the open or UTF-8
    decode fails; else 'ok'. Rows with arity_ok False are skipped."""
    path = Path(path)
    entry = _stem_entry(path)
    tier, phase = (entry if entry else (None, None))
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ArtifactYield(str(path), tier, phase, 0, [], "unreadable")
    rows = parse_trajectory_rows(content)
    if not rows:
        return ArtifactYield(str(path), tier, phase, 0, [], "no_panel_review")
    elided = 0
    passes = []
    for row in rows:
        if not row.arity_ok:
            continue
        notes = row.cells.get("Notes", "")
        m = TRAJECTORY_ELIDED_NOTES_RE.match(notes.strip())
        if m:
            elided = int(m.group(1))
            passes.append(PassYield(_ELIDED_LABEL, None, ""))
            continue
        seats = parse_panel_summary(notes)
        note = _note_for(row, seats)
        positions = None
        comparable = False
        if seats is not None:
            if seats_token_present(notes):
                positions = parse_seats_record(notes)
                extra = _tapered_note(positions) if positions else _UNRESOLVED_NOTE
            elif len(seats) < _CANONICAL_SEATS:
                extra = _UNRESOLVED_NOTE
            else:
                extra = ""
                comparable = True
            if extra:
                note = f"{note}; {extra}" if note else extra
        passes.append(PassYield(row.cells.get("Pass", ""), seats, note, positions, comparable))
    return ArtifactYield(str(path), tier, phase, elided, passes, "ok")


_PASS_W = 6
_SEAT_W = 14


def _header(a: ArtifactYield) -> str:
    where = f"{a.tier} phase {a.phase}" if a.tier else "phase unknown"
    recorded = sum(1 for p in a.passes if p.pass_label != _ELIDED_LABEL)
    if a.elided:
        return (f"{a.path} ({where}, {a.elided + recorded} passes recorded, "
                f"{a.elided} earlier passes elided)")
    return f"{a.path} ({where}, {recorded} passes, nothing elided)"


def _render_block(a: ArtifactYield) -> str:
    lines = [_header(a)]
    if not a.passes:
        return lines[0]
    width = max(
        [len(p.seats) for p in a.passes if p.seats]
        + [max(p.dispatched_positions) for p in a.passes if p.dispatched_positions],
        default=1,
    )
    lines.append("  " + "pass".ljust(_PASS_W)
                 + "".join(f"seat {k}".ljust(_SEAT_W) for k in range(1, width + 1)).rstrip())
    for p in a.passes:
        if p.pass_label == _ELIDED_LABEL:
            cells = ["— elided —"] * width
            note = f"{a.elided} earlier passes elided"
        elif p.seats is None:
            cells = ["— no data —"] * width
            note = p.note
        elif p.dispatched_positions:
            by_pos = dict(zip(p.dispatched_positions, p.seats))
            cells = [(f"{by_pos[k][0]}.{by_pos[k][1]}.{by_pos[k][2]}" if k in by_pos else _NOT_RUN)
                     for k in range(1, width + 1)]
            note = p.note
        else:
            cells = [f"{h}.{m}.{lo}" for h, m, lo in p.seats]
            cells += [""] * (width - len(cells))
            note = p.note
        line = "  " + p.pass_label.ljust(_PASS_W) + "".join(c.ljust(_SEAT_W) for c in cells)
        lines.append((line + (f"   ({note})" if note else "")).rstrip())
    return "\n".join(lines)


def render_text(results: list) -> str:
    """Per-artifact blocks for status='ok'; one '<path> (unreadable)' line per
    unreadable file; one final omitted-count line when any file had no
    trajectory; then the two statements."""
    blocks = []
    omitted = 0
    for a in results:
        if a.status == "ok":
            blocks.append(_render_block(a))
        elif a.status == "unreadable":
            blocks.append(f"{a.path} (unreadable)")
        else:
            omitted += 1
    if omitted:
        blocks.append(f"{omitted} file(s) with no ## Panel Review trajectory omitted.")
    blocks.extend([MED_LOW_CAVEAT, YIELD_NOT_COST])
    return "\n\n".join(blocks) + "\n"


def render_json(results: list) -> str:
    """{"artifacts": [...DM4 as dicts...], "caveats": {...}}"""
    return json.dumps(
        {
            "artifacts": [asdict(a) for a in results],
            "caveats": {
                "med_low_confidence": MED_LOW_CAVEAT,
                "yield_not_cost": YIELD_NOT_COST,
            },
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="panel_yield.py",
        description="Read-only per-artifact report of panel= unique-yield tokens.",
    )
    parser.add_argument("paths", nargs="+", metavar="PATH",
                        help="Artifact files, or directories to walk for *.md")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args(argv)
    missing = [p for p in args.paths if not Path(p).exists()]
    for p in missing:
        print(f"error: no such path: {p}", file=sys.stderr)
    present = [p for p in args.paths if Path(p).exists()]
    results = [read_artifact_yield(p) for p in collect_artifacts(present)]
    sys.stdout.write(render_json(results) if args.json else render_text(results))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
