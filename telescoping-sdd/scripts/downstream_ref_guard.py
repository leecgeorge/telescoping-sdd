"""Shared guard: detect downstream identifier references in upstream artifacts.

Upstream artifacts (`SCOPE`/`ARCHITECTURE` at the blueprint tier; `spec`/`design` at
the SDD tier) must not reference identifiers minted by a downstream phase — feature
IDs (`F<n>`, minted in `03_PLAN.md`) and task IDs (`T<n>`, minted in `03_tasks.md`).
Such a reference reaches into a decomposition that does not exist yet and goes stale
when features/tasks are renumbered.

Mirrors `cfc_parser.py` / `arch_config.py`: stdlib-only, named-constant patterns, and
no import from either validator (the guard owns all of its regexes). Severity is
entirely caller-injected via `PolicyConfig` (R6); this module encodes no
blocking/non-blocking decision of its own — `warn_only` is read straight off the
policy. Scanning is structure-aware and char-preserving (AD9), so a finding's
`line_no` and the two-pass dedup offsets map 1:1 to the original content.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Form-class constants
# ---------------------------------------------------------------------------

FORM_HEADING = "heading"
FORM_BARE = "bare"

# ---------------------------------------------------------------------------
# Named pattern constants (guard-owned; NOT imported from the validators)
# ---------------------------------------------------------------------------

# Blueprint tier (letter F). Bare matcher modelled on validate_blueprint.py's
# FEATURE_ID_PATTERN; heading matcher on master_feature._FEATURE_HEADING's shape.
BLUEPRINT_BARE_PATTERN = re.compile(r"\bF(\d+)\b")
BLUEPRINT_HEADING_PATTERN = re.compile(r"^###[ \t]+(?:- \[[ xX]\] )?F(\d+)\b", re.MULTILINE)

# SDD tier (letter T). No analogue existed in validate_spec.py before this feature;
# does NOT reuse the colon-requiring TASK_ENTRY_PATTERN.
SDD_BARE_PATTERN = re.compile(r"\bT(\d+)\b")
SDD_HEADING_PATTERN = re.compile(r"^###[ \t]+(?:- \[[ xX]\] )?T(\d+)\b", re.MULTILINE)

# ---------------------------------------------------------------------------
# Private structure-skip patterns
# ---------------------------------------------------------------------------

_PANEL_REVIEW_RE = re.compile(r"^## Panel Review\b", re.MULTILINE)
_NEXT_H2_RE = re.compile(r"^## ", re.MULTILINE)
# Line-anchored fence opener. Detected line-by-line (NOT a single backreference
# regex): a closing fence must use the same character and be at least as long as the
# opener (CommonMark), so an unterminated opener — including a 4-backtick run followed
# only by 3-backtick lines — fails safe (does not blank, never swallows to EOF). A
# single `(?P=fence)` backreference would instead let `{3,}` backtrack a 4-run down to
# 3 and mispair with a later 3-backtick fence (AD4 violation).
_FENCE_OPENER_RE = re.compile(r"^[ \t]*(?P<fence>`{3,}|~{3,})")
# Match-required, non-greedy DOTALL: an unterminated `<!--` does not match.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class PolicyConfig(NamedTuple):
    """Per-tier caller-injected severity and remediation policy.

    The guard encodes no severity; the two booleans below are the sole source of
    each finding's `warn_only` (R6). Each validator supplies one module-level
    instance (the booleans avoid the literal blocking/non-blocking words on purpose,
    so the Group-5 source check is not tautological).
    """
    letter: str               # "F" (blueprint) or "T" (SDD)
    heading_warn_only: bool    # heading form's warn_only. v1: False.
    bare_warn_only: bool       # bare form's warn_only. v1: True.
    troubleshooting_ref: str   # appended verbatim to every finding message
    noun: str                  # "feature" / "task" — label used in the message
    downstream_artifact: str   # e.g. "03_PLAN.md" / "03_tasks.md"


class DownstreamRefFinding(NamedTuple):
    """A single finding. The caller converts it to result.add():

        result.add(f.check_name, False, f.detail, warn_only=f.warn_only)
    """
    token: str        # verbatim matched token, e.g. "T5"
    line_no: int      # 1-based line number in the ORIGINAL content
    form: str         # FORM_HEADING or FORM_BARE — classified exactly once
    check_name: str   # for result.add(name=...)
    detail: str       # remediation + pointer for result.add(detail=...)
    warn_only: bool   # derived from policy; maps to result.add(warn_only=...)


# ---------------------------------------------------------------------------
# Private char-preserving stripping helpers (AD9)
# ---------------------------------------------------------------------------

def _blank_range(content: str, start: int, end: int) -> str:
    """Replace each non-newline char in [start, end) with a space; keep every
    newline. The prepared text stays byte-length-aligned with the original."""
    segment = content[start:end]
    blanked = "".join("\n" if ch == "\n" else " " for ch in segment)
    return content[:start] + blanked + content[end:]


def _blank_spans(content: str, spans: list[tuple[int, int]]) -> str:
    """Blank non-overlapping (start, end) spans, applied right-to-left so earlier
    offsets stay valid as the (length-preserving) edits are applied."""
    for start, end in sorted(spans, reverse=True):
        content = _blank_range(content, start, end)
    return content


def _blank_fenced_blocks(content: str) -> str:
    """AD4: blank line-anchored fenced code blocks (char-preserving). A closing fence
    must use the same character and be at least as long as the opener, so an
    unterminated opener fails safe — it does not blank, never swallowing to EOF."""
    lines = content.split("\n")
    out = list(lines)
    n = len(lines)
    i = 0
    while i < n:
        m = _FENCE_OPENER_RE.match(lines[i])
        if m:
            fence = m.group("fence")
            closer = re.compile(
                r"^[ \t]*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*$"
            )
            j = i + 1
            while j < n and not closer.match(lines[j]):
                j += 1
            if j < n:  # matching closer found — blank the whole block, char-preserving
                for k in range(i, j + 1):
                    out[k] = " " * len(lines[k])
                i = j + 1
                continue
            # unterminated opener: fail safe — do not blank
            i += 1
            continue
        i += 1
    return "\n".join(out)


def _blank_html_comments(content: str) -> str:
    """AD11: blank `<!-- ... -->` regions (match-required; unterminated fails safe)."""
    spans = [(m.start(), m.end()) for m in _HTML_COMMENT_RE.finditer(content)]
    return _blank_spans(content, spans)


def _end_of_line(content: str, pos: int) -> int:
    nl = content.find("\n", pos)
    return len(content) if nl == -1 else nl


def _blank_panel_review(content: str) -> str:
    """AD2: blank from each `## Panel Review` line to the next `## ` heading; if none
    follows, blank only the heading line (never to EOF). Handles all occurrences."""
    spans = []
    for m in _PANEL_REVIEW_RE.finditer(content):
        nxt = _NEXT_H2_RE.search(content, m.end())
        end = nxt.start() if nxt else _end_of_line(content, m.start())
        spans.append((m.start(), end))
    return _blank_spans(content, spans)


def _find_closing_run(line: str, start: int, run: int) -> int | None:
    """Index of the next backtick run of EXACTLY `run` at/after `start` on this line,
    or None. Different-length runs are content and are skipped."""
    n = len(line)
    i = start
    while i < n:
        if line[i] == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            if (j - i) == run:
                return i
            i = j
        else:
            i += 1
    return None


def _blank_inline_spans_line(line: str) -> str:
    chars = list(line)
    n = len(line)
    i = 0
    while i < n:
        if line[i] == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            run = j - i
            close = _find_closing_run(line, j, run)
            if close is not None:
                close_end = close + run
                for p in range(i, close_end):
                    chars[p] = " "
                i = close_end
                continue
            # unmatched opener: literal — advance past this run, never swallow
            i = j
            continue
        i += 1
    return "".join(chars)


def _blank_inline_spans(content: str) -> str:
    """AD3: blank inline code spans via SINGLE-LINE run-length backtick pairing.
    An opening run of N backticks closes on the next run of exactly N on the same
    line; an unmatched opener is literal. Single-line so it can never blank across a
    line-anchored heading."""
    return "\n".join(_blank_inline_spans_line(ln) for ln in content.split("\n"))


# ---------------------------------------------------------------------------
# Finding construction (form-tailored remediation; all per-tier text from policy)
# ---------------------------------------------------------------------------

def _make_finding(token: str, line_no: int, form: str, filename: str,
                  policy: PolicyConfig) -> DownstreamRefFinding:
    noun = policy.noun
    art = policy.downstream_artifact
    ident = f"{policy.letter}<n>"
    if form == FORM_HEADING:
        check_name = (
            f"{filename} must not contain a downstream {noun}-identifier heading "
            f"({token} at line {line_no})"
        )
        # A line-start heading cannot be quoted as an example — offer rename/move only.
        detail = (
            f"'### {token}: ...' is a {noun}-heading form — {noun} identifiers "
            f"({ident}) are minted in {art}, not in upstream artifacts. "
            f"Fix: rename the heading to drop the identifier (e.g. '### {token}: Setup' "
            f"-> '### Setup'), or move the section to {art}; a line-start heading must "
            f"be renamed or relocated, not quoted as an example. {policy.troubleshooting_ref}"
        )
        warn_only = policy.heading_warn_only
    else:
        check_name = (
            f"{filename} has a bare downstream {noun}-identifier reference "
            f"({token} at line {line_no})"
        )
        detail = (
            f"'{token}' in bare prose may create a phantom coupling — {noun} identifiers "
            f"({ident}) are assigned downstream in {art}. Fix: refer to the phase or file "
            f"by name (e.g. '{art}'), or if {token} is an example token, backtick it "
            f"(`{token}`). {policy.troubleshooting_ref}"
        )
        warn_only = policy.bare_warn_only
    return DownstreamRefFinding(token, line_no, form, check_name, detail, warn_only)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_for_downstream_refs(content: str, filename: str,
                             policy: PolicyConfig) -> list[DownstreamRefFinding]:
    """Scan `content` for prohibited downstream identifier references.

    Stage order (AD10), all char-preserving (AD9): fenced-blank -> HTML-comment-blank
    -> panel-blank -> heading scan (pass 1, before inline blanking) -> inline-blank ->
    bare scan (pass 2). Two-pass dedup is keyed on the identifier-letter offset
    (heading: `match.start(1) - 1`; bare: `match.start()`), so no character position
    yields two findings.
    """
    if policy.letter == "F":
        heading_pat, bare_pat = BLUEPRINT_HEADING_PATTERN, BLUEPRINT_BARE_PATTERN
    else:
        heading_pat, bare_pat = SDD_HEADING_PATTERN, SDD_BARE_PATTERN

    prepared = _blank_fenced_blocks(content)
    prepared = _blank_html_comments(prepared)
    prepared = _blank_panel_review(prepared)

    findings: list[DownstreamRefFinding] = []
    seen_offsets: set[int] = set()

    # Pass 1 — heading scan on the fenced/comment/panel-blanked text.
    for m in heading_pat.finditer(prepared):
        letter_off = m.start(1) - 1
        seen_offsets.add(letter_off)
        token = policy.letter + m.group(1)
        line_no = content[:letter_off].count("\n") + 1
        findings.append(_make_finding(token, line_no, FORM_HEADING, filename, policy))

    # Pass 2 — bare scan on the additionally inline-blanked text.
    prepared2 = _blank_inline_spans(prepared)
    for m in bare_pat.finditer(prepared2):
        letter_off = m.start()
        if letter_off in seen_offsets:
            continue
        token = m.group(0)
        line_no = content[:letter_off].count("\n") + 1
        findings.append(_make_finding(token, line_no, FORM_BARE, filename, policy))

    return findings
