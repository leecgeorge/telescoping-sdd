"""Artifact-name resolution + the CLI fail-closed boundary — extracted from
blueprint_common (audit R3.1).

Resolves a bare artifact name (`spec.md`) to its on-disk path whether it is bare
or carries the `NN_` ordinal prefix (`01_spec.md`), failing CLOSED on a
bare+prefixed coexistence (`ArtifactAmbiguityError`); the prefix-state detector
and the mixed-state WARN; and `run_cli_failclosed`, the ONE place every script
entry point converts an uncaught ArtifactAmbiguityError into a clean exit.

A LEAF module (stdlib only), so blueprint_common imports it at the top and
re-exports — `from blueprint_common import resolve_artifact` (etc.) keeps working
and the cross-module `_resolve_marker_root_and_key` / consumers are unchanged.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional


KNOWN_ARTIFACTS: frozenset = frozenset(
    {"spec.md", "design.md", "tasks.md", "SCOPE.md", "ARCHITECTURE.md", "PLAN.md"}
)
_ARTIFACT_PREFIX_RE = re.compile(r"^\d{2}_")
# The filesystem-glob spelling of the same `NN_` ordinal grammar, used wherever
# we probe for a prefixed form. Shared (here + imported by artifact_prefix.py) so
# the regex and the glob can never drift apart.
_PREFIX_GLOB = "[0-9][0-9]_"


class ArtifactAmbiguityError(Exception):
    """Raised by `resolve_artifact` when two or more forms of the same artifact
    coexist (bare + prefixed, or multiple distinct prefixed forms). Carries
    structured fields so callers can tailor handling; the message is identical
    across callers (only their exit/disposition behaviour varies)."""

    def __init__(self, bare_name, conflicting_paths, identical_content):
        self.bare_name = bare_name
        self.conflicting_paths = list(conflicting_paths)
        self.identical_content = bool(identical_content)
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        listing = "\n".join(f"  {p}" for p in self.conflicting_paths)
        if self.identical_content:
            prefixed = next(
                (p.name for p in self.conflicting_paths
                 if _ARTIFACT_PREFIX_RE.match(p.name)),
                None,
            )
            keep = (f" (keeping the prefixed form '{prefixed}' gives sortable names)"
                    if prefixed else "")
            return (
                f"Ambiguous artifact '{self.bare_name}': multiple forms found with "
                f"identical content:\n{listing}\nBoth files are byte-identical; you "
                f"may safely remove either one{keep}."
            )
        return (
            f"Ambiguous artifact '{self.bare_name}': multiple forms found:\n{listing}\n"
            f"Remove one to continue. To fix: delete the file you do not want to keep, "
            f"then re-run."
        )


def strip_artifact_prefix(name: str) -> str:
    """Strip a leading two-digit `NN_` prefix from `name`, but ONLY when the
    stripped result is a known artifact basename. A non-artifact name (e.g. a
    user's `12_factor_notes.md`) is returned unchanged — no over-match. Pure
    function, no I/O."""
    stripped = _ARTIFACT_PREFIX_RE.sub("", name, count=1)
    if stripped != name and stripped in KNOWN_ARTIFACTS:
        return stripped
    return name


def _all_identical_content(paths) -> bool:
    """Best-effort byte-equality across paths. False on ANY read error
    (permission / missing / etc.) — a raw OSError must never escape."""
    blobs = []
    for p in paths:
        try:
            blobs.append(p.read_bytes())
        except OSError:
            return False
    return len(set(blobs)) <= 1


def resolve_artifact(directory: Path, bare_name: str) -> Path:
    """Resolve an artifact by bare name, tolerating an optional `NN_` prefix.

    Probe: bare first, then a `[0-9][0-9]_<bare_name>` glob. Returns the unique
    form found; if NEITHER exists, returns `directory / bare_name` unchanged
    (NO raise — soft-absence is preserved for callers using
    `read_file(...) -> None` / `.is_file() -> False`). Raises
    `ArtifactAmbiguityError` ONLY when both bare and a prefixed form coexist, or
    when two or more distinct prefixed forms coexist (the single chokepoint for
    ambiguity). `ArtifactAmbiguityError` is the only exception that may escape.

    Side effects: stat/glob on the happy path; on the ambiguity path only, a
    bounded best-effort content read to set `identical_content`.
    """
    bare_path = directory / bare_name
    # A name that is not a known artifact would never have its prefix honoured,
    # so never glob for it (prevents over-probe of user files like 01_foo.md).
    if bare_name not in KNOWN_ARTIFACTS:
        return bare_path

    prefixed = sorted(directory.glob(_PREFIX_GLOB + bare_name))
    bare_exists = bare_path.is_file()

    if bare_exists and prefixed:
        conflicts = [bare_path] + prefixed
        raise ArtifactAmbiguityError(bare_name, conflicts, _all_identical_content(conflicts))
    if len(prefixed) >= 2:
        raise ArtifactAmbiguityError(bare_name, prefixed, _all_identical_content(prefixed))

    if bare_exists:
        return bare_path
    if len(prefixed) == 1:
        return prefixed[0]
    return bare_path  # neither form exists — return the bare path unchanged


def _detect_prefix_state(directory: Path) -> str:
    """Classify a blueprint/ or specs/<dir>/ directory by artifact prefix state:
    `"uniform-bare"` / `"uniform-prefixed"` / `"mixed"` / `"empty"`. Counts each
    known artifact name independently (if both `spec.md` and `01_spec.md` exist,
    that single artifact contributes one bare + one prefixed, so the state is
    `"mixed"`). Pure filesystem stat — NO interactivity/CI sensing here."""
    bare_count = 0
    prefixed_count = 0
    for bare in KNOWN_ARTIFACTS:
        if (directory / bare).is_file():
            bare_count += 1
        if any(directory.glob(_PREFIX_GLOB + bare)):
            prefixed_count += 1
    if bare_count and prefixed_count:
        return "mixed"
    if bare_count:
        return "uniform-bare"
    if prefixed_count:
        return "uniform-prefixed"
    return "empty"


def _has_artifact_ambiguity(directory: Path) -> bool:
    """True if `directory` holds ANY known artifact in a state `resolve_artifact`
    would raise on (a bare form coexisting with a prefixed form, or two distinct
    prefixed forms). Reuses the resolver itself, so the ambiguity rule lives in
    exactly one place."""
    for bare in KNOWN_ARTIFACTS:
        try:
            resolve_artifact(directory, bare)
        except ArtifactAmbiguityError:
            return True
    return False


def mixed_state_warning(dir_arg: str, directory: Path) -> Optional[str]:
    """The single source of the validators' non-blocking mixed-prefix WARN.

    Returns the WARN string ONLY when the directory is mixed AND the renamer can
    actually fix it (no same-artifact collision). On a bare+prefixed collision
    the renamer would refuse and the validator is about to FAIL with the precise
    ambiguity detail, so nudging the renamer there would loop the user — return
    None and let the ambiguity error speak."""
    if _detect_prefix_state(directory) != "mixed":
        return None
    if _has_artifact_ambiguity(directory):
        return None
    # artifact_prefix.py is a sibling of this module in the shared scripts dir;
    # derive its real absolute path so the printed command is runnable from the
    # user's environment (a literal `telescoping-sdd/scripts/...` would not exist
    # under the project cwd — audit I1.3).
    renamer = Path(__file__).resolve().parent / "artifact_prefix.py"
    return (
        f"WARN: {dir_arg} has a mixed artifact-prefix state (some files prefixed, "
        f"some bare). Run `python {renamer} "
        f"{dir_arg}` to complete the rename (hash-safe)."
    )


def run_cli_failclosed(main_fn) -> None:
    """Run a script entrypoint with the fail-closed `ArtifactAmbiguityError`
    boundary in ONE place. An uncaught ambiguity from anywhere inside `main_fn`
    becomes a clean `FAIL: ambiguous artifact — ...` on stderr + exit 1 instead of
    a traceback — and no future entrypoint can forget to wrap it (the guarantee
    lives here, not copy-pasted in each `__main__`). If `main_fn` returns an int
    it is used as the exit code; `None` falls through (main_fn may sys.exit itself)."""
    try:
        rc = main_fn()
    except ArtifactAmbiguityError as exc:
        print(f"FAIL: ambiguous artifact — {exc}", file=sys.stderr)
        sys.exit(1)
    if rc is not None:
        sys.exit(rc)
