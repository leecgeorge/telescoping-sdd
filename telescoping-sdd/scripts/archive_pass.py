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
Independent of mode, a pass with zero HIGH-severity concerns is marked
`converged (0 HIGH)` in Notes. The marker is appended to any mode tag (e.g.
`strict-bar pass; converged (0 HIGH)`) and is documentation-of-fact for the
trajectory — the loop's exit decision still reads the HIGHs column directly.
With either flag, an empty Latest pass detail still produces a trajectory row
(all counts zero) so the mode pass is recorded. The flags are mutually
exclusive with each other and with `--skip`.

Usage:
    archive_pass.py <artifact-path> --phase {1,2,3} [--skip <reason>]
                    [--strict-bar] [--cross-check] [--dry-run] [--check]

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

Exit codes:
    0  success (empty Latest is a no-op unless --strict-bar/--cross-check)
    1  format violation in Latest pass detail, or conflicting mode flags
    2  unresolved 'User input needed' concerns in Latest pass detail
    3  panel-review section missing or in old format
"""

import argparse
import difflib
import re
import sys
from datetime import date
from pathlib import Path


DISPOSITION_LABELS = {
    "Addressed",
    "Deferred",
    "Sealed",
    "Accepted as risk",
    "User input needed",
    "Halt and re-scope",
}

H_PANEL_REVIEW = "## Panel Review"
H_TRAJECTORY = "### Trajectory"
H_SEALED = "### Sealed dispositions"
H_LATEST = "### Latest pass detail"

TRAJECTORY_COLS = [
    "Pass", "Date", "HIGHs", "Regressions",
    "Addressed", "Deferred", "Sealed", "Notes",
]
LATEST_COLS = ["Severity", "Source", "Concern", "Disposition", "Notes"]

EXIT_OK = 0
EXIT_FORMAT_VIOLATION = 1
EXIT_USER_INPUT_NEEDED = 2
EXIT_OLD_FORMAT_OR_MISSING = 3

SEAL_PAT = re.compile(
    r"^-\s+`\[SEAL-(\d+)\]`\s+\*\*(.+?)\*\*\s+\(pass\s+(\d+),\s+([^)]+)\)\s+—\s+(.+)$"
)
SEPARATOR_PAT = re.compile(r"^\|[\s\-|:]+\|\s*$")


class FormatViolation(Exception):
    def __init__(self, message, line_num=None):
        super().__init__(message)
        self.line_num = line_num


def find_section(lines, heading, start=0, end=None):
    """Locate `heading` between `start` and `end`. Section ends at the next
    heading of the same or higher level, or at `end`."""
    if end is None:
        end = len(lines)
    level = len(heading) - len(heading.lstrip("#"))
    s = None
    for i in range(start, end):
        if lines[i].rstrip() == heading:
            s = i
            break
    if s is None:
        return None
    e = end
    for i in range(s + 1, end):
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


def parse_table(lines, start, end):
    table = find_table(lines, start, end)
    if table is None:
        return [], None
    h, _, first, last = table
    header = [c.strip() for c in lines[h].strip().strip("|").split("|")]
    rows = []
    for i in range(first, last):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if len(cells) == len(header):
            rows.append(dict(zip(header, cells)))
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
    disp_base = disp.split("→")[0].strip() if "→" in disp else disp
    if disp_base not in DISPOSITION_LABELS:
        raise FormatViolation(
            f"Disposition '{disp}' not in vocabulary {sorted(DISPOSITION_LABELS)}",
            line_num,
        )
    if disp_base in ("Sealed", "Accepted as risk"):
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

TAG_NAMES = ("detail", "upstream", "contract")


def _starts_with_tag(concern, tag):
    """True if Concern text starts with the given tag like '[upstream]'."""
    return concern.lstrip().startswith(tag)


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
    if "[SELF-CHECK]" in row.get("Source", ""):
        return False
    return True


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


def detect_strict_bar_signal(prior_traj_rows, current_pass_row, args):
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

    Detection runs only when the current pass is NORMAL mode (not --strict-bar,
    --cross-check, or --skip); strict-bar can only be entered from NORMAL.
    """
    if args.strict_bar or args.cross_check or args.skip:
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
    pooled_deferred = prev_deferred + curr_deferred
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


def render_table_row(values, widths):
    cells = [f" {v.ljust(w)} " for v, w in zip(values, widths)]
    return "|" + "|".join(cells) + "|"


def render_table(headers, rows):
    if not rows:
        widths = [len(h) for h in headers]
    else:
        widths = [
            max(len(h), max(len(r.get(h, "")) for r in rows))
            for h in headers
        ]
    out = [
        render_table_row(headers, widths),
        "|" + "|".join("-" * (w + 2) for w in widths) + "|",
    ]
    for r in rows:
        out.append(render_table_row([r.get(h, "") for h in headers], widths))
    return out


def replace_block(lines, start, end, new_block):
    return lines[:start] + new_block + lines[end:]


def write_or_diff(path, old_content, new_content, dry_run):
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
        path.write_text(new_content)


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
    args = parser.parse_args()

    if sum(bool(x) for x in (args.skip, args.strict_bar, args.cross_check)) > 1:
        print(
            "error: --skip, --strict-bar, and --cross-check are mutually exclusive",
            file=sys.stderr,
        )
        sys.exit(EXIT_FORMAT_VIOLATION)

    art = Path(args.artifact)
    if not art.is_file():
        print(f"error: artifact not found: {art}", file=sys.stderr)
        sys.exit(EXIT_OLD_FORMAT_OR_MISSING)

    content = art.read_text()
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

    latest_rows, latest_table = parse_table(lines, l_start, l_end)
    traj_rows, traj_table = parse_table(lines, t_start, traj[1])
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

    unresolved = [
        r for r in latest_rows
        if r.get("Disposition", "").split("→")[0].strip() == "User input needed"
    ]
    if unresolved:
        print(
            f"error: {len(unresolved)} 'User input needed' concern(s) in Latest pass detail.\n"
            f"  resolve them (re-disposition as Addressed / Deferred / Sealed / "
            f"Accepted as risk) before archiving.",
            file=sys.stderr,
        )
        sys.exit(EXIT_USER_INPUT_NEEDED)

    pass_nums = [int(r["Pass"]) for r in traj_rows if r["Pass"].strip().isdigit()]
    next_pass = max(pass_nums, default=0) + 1
    seal_ids = [e["id"] for e in seal_entries]
    next_seal = max(seal_ids, default=0) + 1

    new_seals = []
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
        mode_pass = args.strict_bar or args.cross_check
        if not latest_rows and not mode_pass:
            print(
                "warning: Latest pass detail is empty; nothing to archive.",
                file=sys.stderr,
            )
            sys.exit(EXIT_OK)
        highs = sum(1 for r in latest_rows if "[HIGH]" in r["Severity"])
        regressions = sum(1 for r in latest_rows if "[REGRESSION]" in r["Severity"])
        addressed = sum(
            1 for r in latest_rows
            if r["Disposition"].split("→")[0].strip() == "Addressed"
        )
        deferred = sum(
            1 for r in latest_rows
            if r["Disposition"].split("→")[0].strip() == "Deferred"
        )
        sealed_count = sum(
            1 for r in latest_rows
            if r["Disposition"].split("→")[0].strip() in ("Sealed", "Accepted as risk")
        )
        halt_rows = [
            r for r in latest_rows
            if r["Disposition"].split("→")[0].strip() == "Halt and re-scope"
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
            tag_parts.append("strict-bar pass")
        elif args.cross_check:
            tag_parts.append("cross-check pass (excluded from cap)")
        if highs == 0:
            tag_parts.append("converged (0 HIGH)")
        # Stash tag counts for Phase 2/3 so detect_strict_bar_signal can read
        # them across passes (Latest is cleared after each archive).
        if args.phase in (2, 3):
            tag_counts = count_tags(latest_rows)
            tag_parts.append(f"tags={format_tag_summary(tag_counts)}")
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
        for r in latest_rows:
            d = r["Disposition"].split("→")[0].strip()
            if d in ("Sealed", "Accepted as risk"):
                title = derive_title(r["Concern"])
                defense = extract_defense(r["Notes"])
                disp_label = "user-directed" if d == "Sealed" else "accepted-as-risk"
                new_seals.append({
                    "id": next_seal,
                    "title": title,
                    "pass": next_pass,
                    "disposition": disp_label,
                    "defense": defense,
                })
                next_seal += 1
        latest_to_clear = True

    new_traj_block = render_table(TRAJECTORY_COLS, traj_rows + [new_traj_row])

    new_sealed_lines = [lines[e["line_idx"]] for e in seal_entries]
    for s in new_seals:
        new_sealed_lines.append(
            f"- `[SEAL-{s['id']:02d}]` **{s['title']}** "
            f"(pass {s['pass']}, {s['disposition']}) — Defense: {s['defense']}."
        )

    new_latest_block = render_table(LATEST_COLS, [])

    new_lines = lines[:]

    if latest_to_clear:
        if latest_table is not None:
            h, _, _, last = latest_table
            new_lines = replace_block(new_lines, h, last, new_latest_block)
        else:
            block = [""] + new_latest_block
            new_lines = new_lines[:l_start + 1] + block + new_lines[l_start + 1:]

    if new_seals:
        if seal_entries:
            first_seal = seal_entries[0]["line_idx"]
            last_seal = seal_entries[-1]["line_idx"] + 1
            new_lines = replace_block(new_lines, first_seal, last_seal, new_sealed_lines)
        else:
            block = [""] + new_sealed_lines
            new_lines = new_lines[:s_start + 1] + block + new_lines[s_start + 1:]

    if traj_table is not None:
        h, _, _, last = traj_table
        new_lines = replace_block(new_lines, h, last, new_traj_block)
    else:
        block = [""] + new_traj_block
        new_lines = new_lines[:t_start + 1] + block + new_lines[t_start + 1:]

    new_content = "\n".join(new_lines) + ("\n" if content.endswith("\n") else "")
    write_or_diff(art, content, new_content, args.dry_run)

    advisory = detect_strict_bar_signal(traj_rows, new_traj_row, args)
    if advisory:
        print(advisory)

    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
