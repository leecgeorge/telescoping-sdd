"""Shared, single-source store + resolver for a project's sibling registry.

Cross-Project Derivation (CPD) lets a derived repo reference master features in a
SIBLING repo. The location of those siblings is recorded once in
`.sdd/projects.json` (DM5) and read defensively by every consumer
(`validate_blueprint.py`, `reconcile.py`) through this one module — exactly as
`arch_config.py` centralises the stack store so the prose layer and the
validators cannot drift on its shape.

Design constraints (mirrors `arch_config.py`):

* SINGLE SHARED MODULE. Every consumer imports `read_projects_config` /
  `find_sibling` from here; there is no second, independent reader of
  `projects.json`.

* SINGLE WRITER, EXPLICIT ONLY. `write_projects_config` is the one write path and
  raises on a wrong `schemaVersion`, so a malformed registry is never persisted.

* DEFENSIVE READ. A registry that is absent, malformed-JSON, unknown-schema, or
  structurally-present-but-wrong-typed (e.g. `siblings` as a string, `name` as an
  int) resolves to `None` — never a downstream `Path([...])` / index crash. The
  read never raises.

* CONTAINMENT (security guardrail). A sibling legitimately points OUTSIDE the
  current root, so blanket containment-to-root is wrong. `resolve_sibling_path`
  resolves relative paths from the PROJECT ROOT (not the calling-process cwd),
  `.resolve()`s the result (like `blueprint_common._key_is_contained`), and
  ACCEPTS it only when the resolved directory looks like a project root (contains
  `blueprint/` or `.sdd/`). `find_sibling` honours that accept-bool and never
  returns a rejected path. The per-file `O_NOFOLLOW` / `fstat` / bounded-read
  symlink boundary is a separate read-time helper (`safe_read_sibling`, added by
  T12b) layered alongside these resolvers; this module deliberately leaves room
  for it.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional, Tuple

# Versioned on-disk schema. Bump only on a breaking shape change; readers ignore
# configs whose schemaVersion they do not understand (treated as "no registry").
PROJECTS_JSON_SCHEMA_VERSION = 1

# Upper bound (in bytes) on a single sibling file read. The sibling repo is
# UNTRUSTED input, so reconcile must never load a hostile multi-GB (or
# `st_size`-under-reporting FUSE/network) sibling file into memory before the
# parser runs. `safe_read_sibling` reads at most `MAX_SIBLING_READ_BYTES + 1`
# bytes FROM THE FD and WARN-skips (returns None) when the cap is exceeded —
# bounding the ACTUAL read, not trusting the advisory `os.fstat(fd).st_size`.
MAX_SIBLING_READ_BYTES = 5 * 1024 * 1024

# Project-local registry location, relative to the project root. Mirrors the
# arch_config.py `.sdd/` convention so a project's CPD config and stack config
# co-locate.
CONFIG_DIRNAME = ".sdd"
CONFIG_FILENAME = "projects.json"

# Markers that identify a directory as a project root. A resolved sibling path is
# accepted only when it contains one of these — a usability guardrail to catch a
# mis-pointed `path`, NOT the security boundary (the read-time O_NOFOLLOW +
# commonpath guard in safe_read_sibling, added by T12b, is the boundary).
_ROOT_MARKERS = ("blueprint", CONFIG_DIRNAME)


def config_path(project_root: Path) -> Path:
    """The absolute path the registry lives at under a given project root."""
    return project_root / CONFIG_DIRNAME / CONFIG_FILENAME


def read_projects_config(project_root: Path) -> Optional[dict]:
    """Read `.sdd/projects.json` under `project_root`, or None if unusable.

    Returns the parsed dict on success; returns None (never raises) on any of:
    missing file, malformed JSON, unknown/absent `schemaVersion`, or a missing OR
    WRONG-TYPED required field. Per-field `isinstance` discipline (mirrors
    `arch_config.read_arch_config`): the top level must be a dict; `thisProject` a
    non-empty str; `siblings` a list; each sibling a dict with str `name` + str
    `path`. `role` is recorded-not-enforced — its absence or an unrecognized value
    does NOT make the registry unusable. A structurally-present but wrong-typed
    registry (siblings as a string, name as an int, path as a list) resolves to
    None — never a downstream `Path([...])` / index crash. None means "no usable
    registry".
    """
    path = config_path(project_root.resolve())
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None
    if data.get("schemaVersion") != PROJECTS_JSON_SCHEMA_VERSION:
        return None
    if not isinstance(data.get("thisProject"), str) or not data["thisProject"]:
        return None

    siblings = data.get("siblings")
    if not isinstance(siblings, list):
        return None
    for sibling in siblings:
        if not isinstance(sibling, dict):
            return None
        if not isinstance(sibling.get("name"), str) or not sibling["name"]:
            return None
        if not isinstance(sibling.get("path"), str) or not sibling["path"]:
            return None
        # `role` is recorded-not-enforced: absent or any type is tolerated here.

    return data


def write_projects_config(project_root: Path, config: dict) -> Path:
    """Write (or overwrite) `.sdd/projects.json`. The ONE write path.

    `config` must carry `schemaVersion` == PROJECTS_JSON_SCHEMA_VERSION, plus
    `thisProject` and `siblings`. Raises ValueError if `schemaVersion` is wrong, so
    a malformed registry is never persisted (mirrors
    `arch_config.write_arch_config`). Creates the `.sdd/` directory if needed.
    Writes a trailing newline and stable key order so the file diffs cleanly in
    version control. Returns the written path.
    """
    if config.get("schemaVersion") != PROJECTS_JSON_SCHEMA_VERSION:
        raise ValueError(
            f"refusing to persist projects.json with schemaVersion "
            f"{config.get('schemaVersion')!r}; "
            f"must be {PROJECTS_JSON_SCHEMA_VERSION}"
        )

    target = config_path(project_root.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def _looks_like_project_root(directory: Path) -> bool:
    """True iff `directory` contains a `blueprint/` or `.sdd/` marker.

    The accept gate for a resolved sibling path — a usability guardrail catching a
    mis-pointed `path`, NOT the security boundary.
    """
    for marker in _ROOT_MARKERS:
        try:
            if (directory / marker).is_dir():
                return True
        except OSError:
            return False
    return False


def resolve_sibling_path(
    sibling_path_str: str, project_root: Path
) -> Tuple[Path, bool]:
    """Resolve a sibling `path` entry to an absolute Path + accept-bool.

    Returns `(resolved_absolute_path, accepted_as_sibling)`. A RELATIVE path is
    resolved from `project_root` (the directory containing `.sdd/`), NOT the
    calling-process cwd, so the same registry resolves to the same absolute path
    regardless of where the tool was invoked. The path is then `.resolve()`-ed
    (like `blueprint_common._key_is_contained` resolves its candidate — not a
    lexical join), which also collapses `..` traversal and dereferences symlinks.

    `accepted_as_sibling` is True ONLY when the resolved directory looks like a
    project root (contains `blueprint/` or `.sdd/`). A path that resolves outside a
    repo (e.g. `../../etc`), or a symlink pointing at a non-repo directory, is
    rejected (`accepted_as_sibling=False`); no read is attempted on a rejected
    path. This accept gate is a usability guardrail, not the security boundary —
    the read-time O_NOFOLLOW + commonpath guard (safe_read_sibling, T12b) is the
    boundary. Never raises.
    """
    root = Path(project_root).resolve()
    candidate = Path(sibling_path_str)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        # An un-resolvable path (e.g. a permission error walking the chain) is
        # treated as not-a-sibling rather than raising.
        return candidate, False

    return resolved, _looks_like_project_root(resolved)


def find_sibling(
    config: Optional[dict], sibling_name: str, project_root: Path
) -> Optional[Path]:
    """Return the resolved+ACCEPTED absolute path for a named sibling, or None.

    Looks up `siblings[].name == sibling_name` and calls `resolve_sibling_path`;
    returns the path ONLY when `accepted_as_sibling` is True. Returns None if the
    config is None, the sibling name is absent, or the resolved path was rejected
    by the accept gate. This is the call site `_emit_derived_dir_warns` / reconcile
    actually use, so it MUST honour the accept-bool — it must NEVER return a path
    that `resolve_sibling_path` rejected (otherwise the containment is bypassed
    here). Never raises.
    """
    if config is None:
        return None

    siblings = config.get("siblings")
    if not isinstance(siblings, list):
        return None

    for sibling in siblings:
        if not isinstance(sibling, dict):
            continue
        if sibling.get("name") != sibling_name:
            continue
        path_str = sibling.get("path")
        if not isinstance(path_str, str) or not path_str:
            return None
        resolved, accepted = resolve_sibling_path(path_str, project_root)
        return resolved if accepted else None

    return None


def safe_read_sibling(
    target_path: Path, sibling_root: Path
) -> Optional[str]:
    """Read a file inside an UNTRUSTED sibling repo, or None on any guard failure.

    This is the I3 READ-TIME security contract (CPD design): the single read-time
    boundary every consumer (`reconcile.py`) uses to pull text out of a sibling
    repo. It is deliberately fail-closed — ANY guard failure returns None (a
    WARN-skip signal for the caller) rather than raising or returning partial
    content. It NEVER raises.

    The guard, in order:

    (1) O_NOFOLLOW open on the FINAL component. `os.open(..., O_RDONLY |
        O_NOFOLLOW | O_NONBLOCK)` refuses to follow a final-component symlink
        (`<root>/blueprint/PLAN.md -> /etc/passwd`), so a symlinked target is
        rejected at the open syscall (`OSError` -> None). `O_NONBLOCK` ensures the
        open itself never blocks on a FIFO with no writer (it is a harmless no-op
        on a regular file), so a non-regular target cannot hang the OPEN before
        the `S_ISREG` reject below.

    (2) fstat the OPEN FD + regular-file check. `os.fstat(fd)` then
        `stat.S_ISREG(st_mode)` rejects a FIFO / device / socket so a non-regular
        target cannot hang the read.

    (3) Bounded read FROM THE FD. Reads at most `MAX_SIBLING_READ_BYTES + 1`
        bytes from the fd via a LOOP (a single os.read() may short-read on a
        FUSE / network mount, so it is not trusted as the whole file) and
        refuses (None) if the cap is exceeded — bounding the ACTUAL read, not
        trusting the advisory `st_size` (which a FUSE / network mount or a racing
        grow can under-report).

    (4) commonpath confinement. Confirms `os.path.commonpath` of the RESOLVED
        sibling root and the RESOLVED target equals the resolved root — both
        operands `.resolve()`d (mirrors `blueprint_common._key_is_contained`), so
        the prefix-bleed `/root/residents` vs `/root/residents-evil` rejects
        component-wise. A `commonpath` ValueError (mixed abs/rel, no common
        prefix, different drives) is caught and treated as reject.

    RESIDUAL (Risk 8): O_NOFOLLOW guards only the FINAL component, and `.resolve()`
    walks the chain in a separate syscall from the open, so an INTERMEDIATE-component
    symlink swap in a hostile, writable sibling tree is NOT closed in v1. This is
    an accepted v1 residual; the TOCTOU-free fix (a per-component `openat(dirfd,
    comp, O_DIRECTORY | O_NOFOLLOW)` walk) is deferred hardening.

    Returns the decoded text on success; None on any guard failure.
    """
    target = Path(target_path)
    root = Path(sibling_root)

    # (4) commonpath confinement, computed up-front on the resolved operands. A
    # path that does not resolve, or shares no common prefix with the resolved
    # root (mixed abs/rel, different drive -> ValueError), is rejected. Resolving
    # the target here may dereference a symlink chain, but the actual READ below
    # is still done under O_NOFOLLOW on the final component, so a final-component
    # symlink is refused at open regardless of what this resolution sees.
    try:
        resolved_root = root.resolve()
        resolved_target = target.resolve()
    except OSError:
        return None
    try:
        common = os.path.commonpath(
            [str(resolved_root), str(resolved_target)]
        )
    except ValueError:
        return None
    if common != str(resolved_root):
        return None

    fd = None
    try:
        # (1) O_NOFOLLOW on the final component — a final-component symlink raises.
        # O_NONBLOCK keeps the open from blocking on a writer-less FIFO (no-op on
        # a regular file) so a non-regular target is rejected by S_ISREG below
        # instead of hanging the open.
        open_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        try:
            fd = os.open(str(target), open_flags)
        except OSError:
            return None

        # (2) fstat the open fd; reject anything that is not a regular file so a
        # FIFO / device / socket cannot block the read.
        try:
            st = os.fstat(fd)
        except OSError:
            return None
        if not stat.S_ISREG(st.st_mode):
            return None

        # (3) Bounded read FROM THE FD via a LOOP up to cap+1 bytes total. A
        # single os.read() may short-read (a FUSE / network mount can return
        # fewer bytes than requested even for a regular file), so one syscall is
        # not the whole file: relying on it would let an over-cap file slip past
        # `len > cap` (DoS / cap bypass) or truncate an in-cap file (a master
        # hash computed over partial content -> false drift). Loop until EOF
        # (empty read) or until we have read more than the cap.
        chunks: list[bytes] = []
        remaining = MAX_SIBLING_READ_BYTES + 1
        try:
            while remaining > 0:
                chunk = os.read(fd, remaining)
                if not chunk:  # EOF — the whole file is in `chunks`.
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
        except OSError:
            return None
        raw = b"".join(chunks)
        if len(raw) > MAX_SIBLING_READ_BYTES:
            return None

        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
