"""`## Approval` record grammar and safe display of marker-derived text (Unit C0 C10).

A leaf module: pure, `ValidationResult`-free helpers shared by the approval,
decline and run-state paths. It imports only `content_hash` and the standard
library (design AD1) — never `blueprint_common` or `pending_review` — so both
lower layers can import it without touching the bottom-import invariant.

Holds:
  * Upstream bindings (AD10): one ``- **Upstream binding:** `<name>` @ `<16-hex>` ``
    line per upstream, read and written inside ``approval_section_bounds`` only.
  * The convergence-override record (AD8) and its reason sanitiser.
"""
from __future__ import annotations

import re
import shlex
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from content_hash import approval_section_bounds

# ANSI CSI escape sequences (color/cursor control) — stripped before render.
# Same patterns run_state.py has always used; run_state imports these objects.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# Control chars EXCEPT tab/newline/CR; includes DEL (0x7f) and lone ESC (0x1b).
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Upstream bindings (AD10)
# ---------------------------------------------------------------------------

BINDING_LINE_RE = re.compile(
    r"^- \*\*Upstream binding:\*\* `(?P<name>[A-Za-z]+\.md)` @ `(?P<hash>[0-9a-f]{16})`[ \t]*\r?$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class UpstreamBinding:
    """DM1: an upstream's bare name and its stamp at approve time."""

    upstream: str
    content_hash: str


def _render_binding(b: UpstreamBinding) -> str:
    return f"- **Upstream binding:** `{b.upstream}` @ `{b.content_hash.lower()}`"


def _approval_lines(content: str):
    """(body_start, body_end, lines) for the `## Approval` body, or None.

    ``lines`` keep their line endings, so ``"".join(lines)`` is the body.
    """
    bounds = approval_section_bounds(content)
    if bounds is None:
        return None
    start, end = bounds
    return start, end, content[start:end].splitlines(keepends=True)


def _eol_of(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def _body_eol(lines: List[str]) -> str:
    # The header regex's trailing `\s*` can leave the body starting with a bare
    # "\n" even in a CRLF file, so any CRLF line decides.
    return "\r\n" if any(ln.endswith("\r\n") for ln in lines) else "\n"


def _binding_match(line: str):
    return BINDING_LINE_RE.match(line.rstrip("\n"))


def _insert_after(lines: List[str], idx: int, text: str, eol: str) -> None:
    """Insert ``text`` as a new line after ``lines[idx]`` (or at 0 when idx < 0)."""
    if idx >= 0 and not _eol_of(lines[idx]):
        lines[idx] = lines[idx] + eol
    lines.insert(idx + 1, text + eol)


def _last_nonblank(lines: List[str]) -> int:
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip():
            return i
    return -1


def read_bindings(content: str) -> Dict[str, Tuple[str, ...]]:
    """Every recorded binding value per upstream, in file order (AD11)."""
    got = _approval_lines(content)
    if got is None:
        return {}
    out: Dict[str, List[str]] = {}
    for ln in got[2]:
        m = _binding_match(ln)
        if m:
            out.setdefault(m.group("name"), []).append(m.group("hash"))
    return {k: tuple(v) for k, v in out.items()}


def strip_binding_lines(content: str) -> str:
    """Remove ``BINDING_LINE_RE`` lines inside ``approval_section_bounds`` only."""
    got = _approval_lines(content)
    if got is None:
        return content
    start, end, lines = got
    kept = [ln for ln in lines if not _binding_match(ln)]
    if len(kept) == len(lines):
        return content
    return content[:start] + "".join(kept) + content[end:]


def upsert_binding_lines(content: str, bindings: Sequence[UpstreamBinding]) -> str:
    """Write one binding line per upstream (AD10). Idempotent (I4).

    For each binding, in argument order: an existing line for that name is
    substituted in place and any further lines for the name are removed;
    otherwise the line is inserted after the last binding line present, or
    after the last non-blank line of the `## Approval` body (trailing blank
    lines preserved). Stamps are lowercased. No-op without an Approval section.
    """
    got = _approval_lines(content)
    if got is None or not bindings:
        return content
    start, end, lines = got
    eol = _body_eol(lines)
    for b in bindings:
        new_text = _render_binding(b)
        idxs = [
            i for i, ln in enumerate(lines)
            if (m := _binding_match(ln)) and m.group("name") == b.upstream
        ]
        if idxs:
            first = idxs[0]
            lines[first] = new_text + (_eol_of(lines[first]) or "")
            for i in reversed(idxs[1:]):
                del lines[i]
            continue
        bind_idxs = [i for i, ln in enumerate(lines) if _binding_match(ln)]
        anchor = bind_idxs[-1] if bind_idxs else _last_nonblank(lines)
        _insert_after(lines, anchor, new_text, eol)
    return content[:start] + "".join(lines) + content[end:]


# ---------------------------------------------------------------------------
# Convergence-override record (AD8)
# ---------------------------------------------------------------------------

OVERRIDE_LINE_RE = re.compile(
    r"^- \*\*Convergence override:\*\* pass (?P<pass>\d+|none) — (?P<reason>.+?)[ \t]*\r?$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class OverrideRecord:
    """DM2. ``duplicate`` is True when two or more override lines exist; every
    caller then treats the record as absent."""

    closing_pass: Optional[int]
    reason: str
    duplicate: bool = False


def _render_override(rec: OverrideRecord) -> str:
    p = "none" if rec.closing_pass is None else str(rec.closing_pass)
    return f"- **Convergence override:** pass {p} — {rec.reason}"


def read_override_record(content: str) -> Optional[OverrideRecord]:
    """None if absent; a record with ``duplicate=True`` if two or more lines exist."""
    got = _approval_lines(content)
    if got is None:
        return None
    matches = [m for m in (OVERRIDE_LINE_RE.match(ln.rstrip("\n")) for ln in got[2]) if m]
    if not matches:
        return None
    m = matches[0]
    p = None if m.group("pass") == "none" else int(m.group("pass"))
    return OverrideRecord(closing_pass=p, reason=m.group("reason"), duplicate=len(matches) > 1)


def append_override_record(content: str, record: OverrideRecord) -> str:
    """Append the record as the last non-blank line of `## Approval`."""
    got = _approval_lines(content)
    if got is None:
        return content
    start, end, lines = got
    _insert_after(lines, _last_nonblank(lines), _render_override(record), _body_eol(lines))
    return content[:start] + "".join(lines) + content[end:]


# Unicode categories replaced by a space: controls, format chars, line and
# paragraph separators, surrogates, private use, unassigned (AD8 step 2). This
# covers every separator `str.splitlines()` honours.
_REPLACED_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn"})
_LEADING_MARKER_RE = re.compile(r"^(?:[#>\-*+]|\d+\.)\s*")
OVERRIDE_REASON_MAX = 200


def _replace_unsafe_chars(text: str) -> str:
    return "".join(
        " " if unicodedata.category(ch) in _REPLACED_CATEGORIES else ch for ch in text
    )


def sanitize_override_reason(raw: str) -> str:
    """AD8 sanitiser. Idempotent; output is one line under ``str.splitlines()``.

    Raises ValueError when nothing printable remains.
    """
    text = _ANSI_RE.sub("", raw)
    text = _replace_unsafe_chars(text)
    while True:
        prev = text
        text = text.replace("`", "").replace("**", "").replace("<!--", "<! --")
        if text == prev:
            break
    text = text.replace("[", "(").replace("]", ")")
    text = re.sub(r"\s+", " ", text).strip()
    while True:
        new = _LEADING_MARKER_RE.sub("", text, count=1).lstrip()
        if new == text:
            break
        text = new
    text = text[:OVERRIDE_REASON_MAX].rstrip()
    if not text:
        raise ValueError("override reason is empty after sanitising")
    return text


# ---------------------------------------------------------------------------
# Display safety (AD16)
# ---------------------------------------------------------------------------

DISPLAY_ARG_MAX = 1024


class DisplayArg(NamedTuple):
    """``quoted`` is ``shlex.quote(text)``, or None with a ``reason``:
    'non-printable' | 'backtick' | 'too-long', in that precedence."""

    quoted: Optional[str]
    reason: Optional[str]


def _has_unsafe_char(text: str) -> bool:
    return any(unicodedata.category(ch) in _REPLACED_CATEGORIES for ch in text)


def display_arg(text: str) -> DisplayArg:
    """Shell-quote ``text`` for a printed command, or refuse with a reason."""
    if _has_unsafe_char(text):
        return DisplayArg(None, "non-printable")
    if "`" in text:
        return DisplayArg(None, "backtick")
    if len(text) > DISPLAY_ARG_MAX:
        return DisplayArg(None, "too-long")
    return DisplayArg(shlex.quote(text), None)


def display_text(text: str, *, max_len: Optional[int] = None) -> str:
    """AD8's character rule without quoting: ANSI removed, every replaced-category
    character becomes a space, so the result is one physical line. Truncated to
    ``max_len`` characters (ending in an ellipsis) when longer."""
    out = _replace_unsafe_chars(_ANSI_RE.sub("", text))
    if max_len is not None and len(out) > max_len:
        out = out[: max(max_len - 1, 0)] + "…"
    return out


# ---------------------------------------------------------------------------
# Operator message constants shared by pending_review.py and run_state.py
# ---------------------------------------------------------------------------

# AC-9.2 plain-word glosses.
GLOSS_BINDING = (
    "an upstream binding records which approved version of each upstream "
    "document this one was approved against"
)
GLOSS_SUPERSEDED = (
    "superseded means this document was approved against an older version of "
    "its upstream, which has since been re-approved or changed"
)
GLOSS_UNBOUND = (
    "unbound means there is no record of which upstream version this document "
    "was approved against"
)
GLOSS_LEGACY = (
    "legacy means the closing panel row was archived before provenance tokens "
    "existed, so whether the document changed after that pass cannot be checked"
)

# AC-9.1: the one home for the user-decision wording.
USER_DECISION_NOTE = "this is a user decision; confirm before running"

# I9 restamp audit line: prefix + parts (seal, binding, re-pad) joined by " and ".
RESTAMP_CARVE_OUT_PREFIX = (
    "restamp-carve-out: {doc_rel} re-stamped with no pending-review marker — "
)
SEAL_PART = "seal promotion ({ids})"
BINDING_PART = "upstream binding refresh"
REPAD_PART = "Trajectory table re-pad"

# The validator each tier's routes print.
TIER_VALIDATOR_CMD = {
    "sdd": "validate_spec.py",
    "blueprint": "validate_blueprint.py",
}
