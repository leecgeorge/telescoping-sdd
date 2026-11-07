"""Shared, single-source resolver + store for a project's declared stack.

The stack (`python` / `java` / `generic` / …) must be resolved ONCE and
persisted, instead of being re-derived per phase by two unlinked detectors (the
SKILL.md prose layer and validate_spec.py) that can silently disagree.

Design constraints:

* SINGLE SHARED MODULE. Both the consumer (validate_spec.py) and any future
  producer (validate_blueprint.py) import the read/write/resolve helpers from
  here, exactly as cfc_parser.py centralises CFC grammar so producer and consumer
  cannot drift. There is no second, independent implementation.

* TWO WRITERS, EXPLICIT ONLY. `write_arch_config` (the language) and
  `write_posture` (the rigour posture) are the only write paths, each reached
  only by an explicit act (`validate_spec.py --set-language`,
  `validate_blueprint.py --write-arch-config`, either validator's
  `--set-posture`), never silently on a validate run. Each writer
  read-merge-writes, so it keeps the other's key, and writes atomically (temp
  file in `.sdd/`, then `os.replace`).

* OUT-OF-BAND FROM THE HASH MACHINERY, BY DESIGN. The stack value is advisory:
  it selects which of the two skippable advisory checks run (type annotations,
  test-function names) and the banner label. The posture selects the panel's
  default rigour (`critical` / `standard` / `vibe`). Neither is part of any
  content hash, and neither is written during `--approve` — avoiding the
  CFC-cascade collision and the two-files-no-atomicity hazard. A stale or
  hand-edited config can at worst mislabel the banner, toggle an advisory check
  or change a panel default; it cannot corrupt the approval chain.

* CLOSED VOCABULARY. Writes are validated against the caller-supplied set of known
  profile keys, so a typo (`pyton`) is rejected at write time and never persisted.
  Reads are defensive: an unknown key (newer schema, hand-edit) is ignored and
  resolution falls back to detection rather than trusting garbage.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

# Grammar for the controlled-vocabulary token the blueprint declares in
# ARCHITECTURE.md (`**Architecture token:** \`generic\``). Lives here, in the
# shared module, so the producer (validate_blueprint) and any consumer parse the
# token identically — the same anti-drift discipline cfc_parser.py applies to CFC
# grammar. The token is matched as a backtick-or-bare lowercase slug; membership
# in the known-language set is validated by the caller (so a typo produces a
# precise error rather than being silently dropped).
ARCH_TOKEN_PATTERN = re.compile(
    r"\*\*Architecture token:\*\*\s*`?([A-Za-z0-9][A-Za-z0-9._-]*)`?",
)


def parse_arch_token(architecture_md: str) -> Optional[str]:
    """Extract the raw `**Architecture token:**` value from ARCHITECTURE.md text.

    Returns the captured token string (NOT validated against any vocabulary —
    the caller does that, so it can distinguish "no token line present" (None)
    from "token present but unknown" (a returned string the caller rejects)).
    Returns None if the line is absent.

    HTML comments are stripped before matching so a commented-out *example*
    token (e.g. the explanatory `<!-- ... **Architecture token:** `python` -->`
    block in architecture-template.md) cannot shadow the author's real
    declaration. Without this, `.search()` would return the first match
    anywhere in the document, including inside a comment.
    """
    uncommented = re.sub(r"<!--.*?-->", "", architecture_md, flags=re.DOTALL)
    m = ARCH_TOKEN_PATTERN.search(uncommented)
    return m.group(1) if m else None

# Versioned on-disk schema. Bump only on a breaking shape change; readers ignore
# configs whose schemaVersion they do not understand (treated as "no config").
SCHEMA_VERSION = 1

# Project-local config location, relative to the project root.
CONFIG_DIRNAME = ".sdd"
CONFIG_FILENAME = "architecture.json"

# The rigour posture (Unit D, R7): a project-level preset stored beside the
# language. Closed vocabulary; an out-of-vocabulary persisted value is ignored
# at read (and reported) and refused at write.
POSTURES: tuple[str, ...] = ("critical", "standard", "vibe")
DEFAULT_POSTURE = "standard"
POSTURE_KEY = "posture"
# Name of the once-only posture-notice flag file (under the scratch root).
NOTICE_FILENAME = "posture-notice"


@dataclass(frozen=True)
class PostureResolution:
    """The resolved posture and where it came from.

    `source` is 'flag' | 'config' | 'default'. `rejected` is a persisted
    out-of-vocabulary string, raw (callers sanitise it only when printing).
    `rejected_non_text` is True when a persisted value is present but is not a
    string; that value is never echoed.
    """

    posture: str
    source: str
    rejected: Optional[str]
    rejected_non_text: bool

# How many directory levels to walk up from a spec dir when searching for the
# project root / an existing config. Mirrors detect_language()'s bound.
_MAX_WALK_UP = 10

# Markers that identify a project root when walking up from a spec directory.
# Intentionally methodology/VCS-level, NOT language-specific (language detection
# is separate): a dir containing any of these is treated as the project root.
_ROOT_MARKERS = ("specs", "blueprint", ".git", CONFIG_DIRNAME)


def find_project_root(spec_dir: Path, explicit: Optional[Path] = None) -> Path:
    """Resolve the project root for reading/writing the config.

    `explicit` (e.g. a --project-root flag) wins. Otherwise walk up from
    `spec_dir` and return the nearest ancestor that looks like a project root
    (contains specs/ , blueprint/ , .git , or .sdd). Falls back to spec_dir's
    parent (the conventional `specs/<feature>/` → project-root layout) if no
    marker is found, so the function always returns a usable directory.
    """
    if explicit is not None:
        return explicit.resolve()

    search = spec_dir.resolve()
    # If spec_dir itself is `.../specs/<feature>`, its parent's parent is root;
    # but prefer marker-based detection and only use that as the final fallback.
    for _ in range(_MAX_WALK_UP):
        for marker in _ROOT_MARKERS:
            if (search / marker).exists():
                return search
        parent = search.parent
        if parent == search:
            break
        search = parent

    # Fallback: the conventional layout is <root>/specs/<feature>/, so the
    # grandparent of spec_dir is the most likely root; guard against shallow paths.
    resolved = spec_dir.resolve()
    if resolved.parent.name == "specs":
        return resolved.parent.parent
    return resolved.parent


def config_path(project_root: Path) -> Path:
    """The absolute path the config lives at under a given project root."""
    return project_root / CONFIG_DIRNAME / CONFIG_FILENAME


def _find_config_upwards(spec_dir: Path) -> Optional[Path]:
    """Walk up from spec_dir to find an existing .sdd/architecture.json."""
    search = spec_dir.resolve()
    for _ in range(_MAX_WALK_UP):
        candidate = search / CONFIG_DIRNAME / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = search.parent
        if parent == search:
            break
        search = parent
    return None


def _atomic_write_text(target: Path, content: str) -> None:
    """Write `content` to `target` atomically: temp file beside it, then
    `os.replace`. On any failure the temp file is removed and the original is
    untouched. The technique `blueprint_common._atomic_write` uses,
    reimplemented here because this module is a leaf."""
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _read_existing(target: Path) -> Optional[dict]:
    """The existing config object at `target`, or None when there is none to
    merge with (absent, unreadable, malformed, not an object, unknown schema)."""
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schemaVersion") != SCHEMA_VERSION:
        return None
    return data


def _load_mergeable(target: Path, *, keep_language: bool) -> Optional[dict]:
    """The existing config to merge into, None when no file exists, or a
    ValueError when a file exists but cannot be merged safely (C7).

    A writer refuses rather than overwrite: silently replacing a malformed or
    unrecognised file would drop the key the other writer owns. The file is
    left byte-unchanged and the operator is told to fix or delete it.
    """
    if not target.exists():
        return None

    def refuse(reason: str) -> ValueError:
        return ValueError(f"refusing to rewrite {target}: {reason}; fix or delete it")

    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise refuse(f"unreadable ({exc.__class__.__name__})") from None
    try:
        data = json.loads(raw)
    except ValueError:
        raise refuse("malformed JSON") from None
    if not isinstance(data, dict):
        raise refuse("not a JSON object")
    if "schemaVersion" not in data:
        raise refuse("no schemaVersion")
    if data["schemaVersion"] != SCHEMA_VERSION:
        raise refuse(f"unknown schemaVersion {data['schemaVersion']!r}")
    if POSTURE_KEY in data and not isinstance(data[POSTURE_KEY], str):
        raise refuse("non-string posture")
    if keep_language and "language" in data and not isinstance(data["language"], str):
        raise refuse("non-string language")
    return data


def _dump(payload: dict) -> str:
    return json.dumps(payload, indent=2) + "\n"


def read_arch_config(
    spec_dir: Path, project_root: Optional[Path] = None
) -> Optional[dict]:
    """Read the persisted config, or None if absent/unreadable/unknown-schema.

    If `project_root` is given, reads only that root's config. Otherwise walks up
    from `spec_dir`. Returns the parsed dict (with at least a `language` key) on
    success; returns None (never raises) on any of: missing file, malformed JSON,
    unknown/absent schemaVersion, or missing `language`. None means "no usable
    persisted answer — fall back to detection".
    """
    if project_root is not None:
        path: Optional[Path] = config_path(project_root.resolve())
        if not path.is_file():
            path = None
    else:
        path = _find_config_upwards(spec_dir)

    if path is None:
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None
    if data.get("schemaVersion") != SCHEMA_VERSION:
        return None
    if not isinstance(data.get("language"), str) or not data["language"]:
        return None
    return data


def write_arch_config(
    project_root: Path,
    language: str,
    known_languages: Iterable[str],
    *,
    source: str = "user",
    detected_from: Optional[str] = None,
) -> Path:
    """Write the persisted language, keeping any persisted posture.

    `language` MUST be one of `known_languages` (the closed vocabulary) — a value
    outside it raises ValueError, so a typo is never persisted. An existing file
    that cannot be merged safely is refused with ValueError and left unchanged
    (C7). `source` records
    provenance (`user` / `blueprint` / `auto-detect`). Returns the written path.
    Creates the `.sdd/` directory if needed. Writes atomically, with a trailing
    newline and stable key order so the file diffs cleanly in version control.
    """
    known = set(known_languages)
    if language not in known:
        raise ValueError(
            f"refusing to persist unknown language {language!r}; "
            f"must be one of {sorted(known)}"
        )

    target = config_path(project_root.resolve())
    existing = _load_mergeable(target, keep_language=False)

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "language": language,
        "source": source,
    }
    if detected_from is not None:
        payload["detectedFrom"] = detected_from
    # Read-merge-write (C7): `language`, `source` and `detectedFrom` come wholly
    # from this call; the only key carried over is the posture.
    if existing is not None and isinstance(existing.get(POSTURE_KEY), str):
        payload[POSTURE_KEY] = existing[POSTURE_KEY]

    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(target, _dump(payload))
    return target


def _config_file(spec_dir: Path, project_root: Optional[Path]) -> Optional[Path]:
    if project_root is not None:
        path = config_path(project_root.resolve())
        return path if path.is_file() else None
    return _find_config_upwards(spec_dir)


def read_posture(
    spec_dir: Path, project_root: Optional[Path] = None
) -> tuple[Optional[str], Optional[str], bool]:
    """(valid value or None, rejected string or None, rejected_non_text).

    Located like `read_arch_config` (the given root, else a walk up from
    `spec_dir`), but independent of `language`: a posture-only file has a
    posture. The bool is True when a posture value is present but is not a
    string; that value is never returned. Never raises.
    """
    path = _config_file(spec_dir, project_root)
    if path is None:
        return None, None, False
    data = _read_existing(path)
    if data is None or POSTURE_KEY not in data:
        return None, None, False
    value = data[POSTURE_KEY]
    if not isinstance(value, str):
        return None, None, True
    if value in POSTURES:
        return value, None, False
    return None, value, False


def write_posture(project_root: Path, posture: str) -> Path:
    """Persist the posture by read-merge-write, keeping every other key.

    Raises ValueError for a posture outside POSTURES, or when an existing file
    cannot be merged safely (C7); the file is then left unchanged. Writes
    atomically. Returns the written path.
    """
    if posture not in POSTURES:
        raise ValueError(
            f"refusing to persist unknown posture {posture!r}; "
            f"must be one of {list(POSTURES)}"
        )
    target = config_path(project_root.resolve())
    existing = _load_mergeable(target, keep_language=True)
    payload = dict(existing) if existing is not None else {"schemaVersion": SCHEMA_VERSION}
    payload[POSTURE_KEY] = posture
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(target, _dump(payload))
    return target


def resolve_posture(
    spec_dir: Path,
    *,
    explicit: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> PostureResolution:
    """Resolve the posture: `explicit` (a --posture flag), then the persisted
    value, then DEFAULT_POSTURE. A rejected persisted value resolves as if
    absent and is reported through `rejected` / `rejected_non_text`."""
    value, rejected, non_text = read_posture(spec_dir, project_root)
    if explicit:
        return PostureResolution(explicit, "flag", rejected, non_text)
    if value is not None:
        return PostureResolution(value, "config", None, False)
    return PostureResolution(DEFAULT_POSTURE, "default", rejected, non_text)


def resolve_language(
    spec_dir: Path,
    *,
    explicit: Optional[str],
    detector: Callable[[Path, Optional[Path]], str],
    known_languages: Iterable[str],
    project_root: Optional[Path] = None,
) -> tuple[str, str]:
    """Resolve the stack via the precedence rule, returning (language, source).

    Precedence (highest first):
      1. `explicit`         — an explicit --language flag for this run.       → "flag"
      2. persisted config   — .sdd/architecture.json, if present & a known key.→ "config"
      3. `detector(...)`    — marker auto-detection (already returns the
                              neutral fallback when nothing matches).          → "auto-detect"

    A persisted value that is NOT in `known_languages` (stale schema, hand-edit,
    a profile that was removed) is ignored and resolution continues to detection,
    rather than trusting an unusable key. The detector is responsible for its own
    neutral fallback; resolve_language never invents a default itself.
    """
    known = set(known_languages)

    if explicit:
        return explicit, "flag"

    cfg = read_arch_config(spec_dir, project_root)
    if cfg is not None and cfg["language"] in known:
        return cfg["language"], "config"

    return detector(spec_dir, project_root), "auto-detect"
