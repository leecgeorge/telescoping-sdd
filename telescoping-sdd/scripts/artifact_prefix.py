#!/usr/bin/env python3
"""Hash-safe bulk renamer for methodology artifacts.

Renames a project's BARE artifacts to their ``NN_`` ordinal form
(``spec.md`` -> ``01_spec.md`` ...) so a directory listing sorts in phase
order. Pure filesystem renames — the file CONTENT is never touched, so the
content hash (which is filename-independent) stays valid and no approval is
invalidated.

Also provides ``--check <dir>``, which prints ``OFFER`` / ``SUPPRESS`` to
stdout and always exits 0 — the realizable, testable gate the skill prose runs
before presenting the R7 interactive offer (see specs/artifact-ordering-prefix
design AD5 / C5).

Fail-closed refusals (exit 1): a corrupt or in-flight ``.sdd/pending-review.json``
obligation for the directory, a pre-existing bare+prefixed ambiguity, a symlinked
or escaping artifact, or any rename ``OSError``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# sys.path bootstrap — shared-script ENTRY POINT (audit R3.5: one idiom across
# entry points). This script lives in telescoping-sdd/scripts/ alongside the
# shared helpers it imports; nothing else bootstraps it, so it puts its own dir
# on sys.path via a guarded insert(0) — taking precedence so the imports resolve.
# (Skill validators under skills/*/scripts/ use a guarded APPEND instead, to avoid
# displacing the plugin runtime's sys.path[0].)
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import arch_config  # noqa: E402
import blueprint_common as bc  # noqa: E402

# Target ordinal per canonical artifact, by phase order. Its keys MUST equal
# blueprint_common.KNOWN_ARTIFACTS (enforced by a symmetry test).
PREFIX_MAP = {
    "spec.md": "01_",
    "design.md": "02_",
    "tasks.md": "03_",
    "SCOPE.md": "01_",
    "ARCHITECTURE.md": "02_",
    "PLAN.md": "03_",
}

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2


def _is_interactive() -> bool:
    """True iff this is an interactive session (a real TTY and not a CI run).
    The R7 offer is suppressed otherwise. Kept tiny so tests can monkeypatch
    ``sys.stdin.isatty`` / the ``CI`` env var."""
    try:
        tty = sys.stdin.isatty()
    except (ValueError, OSError):
        tty = False
    ci = os.environ.get("CI", "").strip().lower() in ("true", "1")
    return tty and not ci


def _check_mode(directory: Path) -> int:
    """Print OFFER iff the dir is mixed AND interactive; else SUPPRESS. Advisory:
    always exits 0, never blocks (a missing/odd dir resolves to a SUPPRESS)."""
    state = bc._detect_prefix_state(directory)
    if state == "mixed" and _is_interactive():
        print("OFFER")
    elif state != "mixed":
        print(f"SUPPRESS (state={state})")
    else:
        print("SUPPRESS (non-interactive)")
    return EXIT_OK


def _resolve_dir_and_root(dir_arg: str) -> "tuple[Path, Path, str]":
    """Resolve the dir argument and its project root; return
    ``(resolved_dir, root, dir_relprefix)``. Exits 2 if the path is not a
    directory or its resolved form escapes the project root."""
    directory = Path(dir_arg).resolve()
    if not directory.is_dir():
        print(f"Error: {dir_arg} is not a directory", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    root = arch_config.find_project_root(directory).resolve()
    try:
        rel = directory.relative_to(root).as_posix()
    except ValueError:
        print(f"Error: {dir_arg} resolves outside the project root {root}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    return directory, root, ("" if rel == "." else rel)


def _check_pending_refusal(root: Path, dir_relprefix: str) -> "str | None":
    """Return a refusal message if any in-scope pending-review entry exists (or
    the marker is corrupt — read strict=True, fail-closed), else None. Reuses the
    codebase's boundary-safe ``_prefix_in_scope`` so siblings never cross-match."""
    try:
        data = bc.read_pending_review(root, strict=True)
    except bc.MarkerCorruptError as exc:
        return (f".sdd/pending-review.json is corrupt/unreadable ({exc}). "
                f"Inspect or delete it manually, then re-run.")
    for key in data.get("pending", {}):
        if not bc._prefix_in_scope(key, dir_relprefix):
            continue
        # Project-root guard: an empty scope prefix means `directory` IS the
        # project root, and `_prefix_in_scope("...", "")` matches EVERY key. The
        # renamer only touches artifacts directly in `directory`, so at the root
        # restrict the refusal to root-level (no-separator) obligations rather
        # than every unrelated nested one.
        if dir_relprefix == "" and "/" in key:
            continue
        return (f"pending panel-review obligation for {key}. Resolve or decline "
                f"the pending review first (--decline-pending), then re-run.")
    return None


def _check_ambiguity_preflight(directory: Path) -> "str | None":
    """Return a refusal if any known artifact is already in a state the resolver
    would choke on (a bare form coexisting with a prefixed form, or >=2 prefixed
    forms). Reuses `resolve_artifact` itself, so the repair tool and the
    resolution chokepoint enforce ONE ambiguity rule and can never diverge."""
    for bare in PREFIX_MAP:
        try:
            bc.resolve_artifact(directory, bare)
        except bc.ArtifactAmbiguityError as exc:
            return str(exc)
    return None


def _rename_artifacts(directory: Path) -> "tuple[list[str], list[str]]":
    """Rename bare artifacts in `directory` to their prefixed form. Returns
    ``(renamed, skipped)``. Skips already-prefixed/absent artifacts (idempotent),
    refuses a symlinked or escaping artifact, and halts (exit 1) on the first
    ``OSError`` — atomic per-file, not per-directory."""
    renamed: list[str] = []
    skipped: list[str] = []
    for bare, prefix in PREFIX_MAP.items():
        src = directory / bare
        if not src.exists():
            if list(directory.glob(bc._PREFIX_GLOB + bare)):
                skipped.append(bare)  # already prefixed
            continue
        if src.is_symlink() or src.resolve().parent != directory:
            print(f"Refusing to rename '{bare}': it is a symlink or resolves "
                  f"outside {directory}.", file=sys.stderr)
            sys.exit(EXIT_REFUSED)
        dst = directory / (prefix + bare)
        try:
            os.rename(src, dst)
        except OSError as exc:
            print(f"Error renaming '{src}' to '{dst}': {exc.strerror or exc}",
                  file=sys.stderr)
            sys.exit(EXIT_REFUSED)
        renamed.append(bare)
    return renamed, skipped


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Hash-safe NN_ ordinal renamer for methodology artifacts."
    )
    parser.add_argument("directory", help="blueprint/ or specs/<dir>/ to operate on")
    parser.add_argument(
        "--check", action="store_true",
        help="print OFFER/SUPPRESS (the R7 interactive-offer gate) and exit 0",
    )
    args = parser.parse_args(argv)

    if args.check:
        return _check_mode(Path(args.directory))

    directory, root, rel = _resolve_dir_and_root(args.directory)

    refusal = _check_pending_refusal(root, rel)
    if refusal:
        print(f"Refusing to rename {args.directory}: {refusal}", file=sys.stderr)
        return EXIT_REFUSED
    refusal = _check_ambiguity_preflight(directory)
    if refusal:
        print(f"Refusing to rename {args.directory}: {refusal}", file=sys.stderr)
        return EXIT_REFUSED

    renamed, _skipped = _rename_artifacts(directory)
    if not renamed:
        print(f"Nothing to rename in {args.directory}: all known artifacts are "
              f"already prefixed or absent.")
        return EXIT_OK
    print(f"Renamed {len(renamed)} artifact(s) in {args.directory}: "
          + ", ".join(renamed))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
