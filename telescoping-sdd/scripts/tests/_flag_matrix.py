"""Unit D [SEAL-14]: the archive_pass.py mode-flag matrix (design C1's table).

One generator module, so no new flag is ever silently accepted: every refused
pair is asserted in both argument orders, every ignored pair is compared with
its mode alone, and the allowed combinations must exit 0. Test modules import
it the way they import `_fixtures` (insert this directory into `sys.path`,
then `import _flag_matrix`).

Each flag is written as its argv tokens; `--skip` takes a reason.
"""

from __future__ import annotations

from itertools import combinations

FLAG_ARGV = {
    "--posture-report": ["--posture-report"],
    "--no-notice": ["--no-notice"],
    "--skip": ["--skip", "mechanical"],
    "--strict-bar": ["--strict-bar"],
    "--cross-check": ["--cross-check"],
    "--check": ["--check"],
    "--dry-run": ["--dry-run"],
    "--terminal": ["--terminal"],
    "--posture": ["--posture", "critical"],
    # The draft path is substituted by `argv(..., draft=...)`.
    "--zone-diff": ["--zone-diff", "@DRAFT"],
}

_ARCHIVE_MODES = ("--skip", "--strict-bar", "--cross-check", "--check", "--dry-run")

# Unordered pairs refused with exit 1, before the artifact-exists check.
REFUSED_PAIRS = sorted(
    {tuple(sorted((mode, other))) for mode in ("--posture-report", "--no-notice")
     for other in _ARCHIVE_MODES}
    | {tuple(sorted(("--zone-diff", other)))
       for other in ("--posture-report", "--no-notice", *_ARCHIVE_MODES)}
)

# Flag sets refused on their own: --no-notice needs --posture-report,
# including on a plain archive.
REFUSED_ALONE = [
    ("--no-notice",),
    ("--no-notice", "--posture"),
]

# (mode, flag): the flag is ignored with that mode, so the result must equal
# the mode alone.
IGNORED_PAIRS = [
    ("--posture-report", "--terminal"),
    ("--zone-diff", "--terminal"),
    ("--zone-diff", "--posture"),
]

# The read-only modes, and the extra flags a mode-alone run takes in tests so
# it has no side effect (the notice sentinel).
MODES = ("--posture-report", "--zone-diff")
QUIET = {"--posture-report": ["--no-notice"], "--zone-diff": []}

# Combinations that must run and exit 0.
ALLOWED = [
    ("--no-notice", "--posture-report", "--posture"),
]


def argv(flags, draft: str = "draft.md") -> list:
    out = []
    for f in flags:
        out.extend(draft if t == "@DRAFT" else t for t in FLAG_ARGV.get(f, [f]))
    return out


def cases() -> list:
    """(kind, ordered flag tuple) for every generated case; refused pairs in
    both orders."""
    out = []
    for a, b in REFUSED_PAIRS:
        out.append(("refused", (a, b)))
        out.append(("refused", (b, a)))
    for flags in REFUSED_ALONE:
        out.append(("refused-alone", tuple(flags)))
    for mode, flag in IGNORED_PAIRS:
        out.append(("ignored", (mode, flag)))
        out.append(("ignored", (flag, mode)))
    for flags in ALLOWED:
        out.append(("allowed", tuple(flags)))
    return out


def unordered_pairs() -> list:
    return [frozenset(p) for p in combinations(sorted(FLAG_ARGV), 2)]
