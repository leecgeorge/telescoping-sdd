"""Shared, single-source resolver + store for a project's declared stack.

The stack (`python` / `java` / `generic` / …) must be resolved ONCE and
persisted, instead of being re-derived per phase by two unlinked detectors (the
SKILL.md prose layer and validate_spec.py) that can silently disagree.

Design constraints:

* SINGLE SHARED MODULE. Both the consumer (validate_spec.py) and any future
  producer (validate_blueprint.py) import the read/write/resolve helpers from
  here, exactly as cfc_parser.py centralises CFC grammar so producer and consumer
  cannot drift. There is no second, independent implementation.

* SINGLE WRITER, EXPLICIT ONLY. `write_arch_config` is the one write path. It is
  invoked only on an explicit act (`validate_spec.py --set-language`), never
  silently on every validate run — so a later run READS the persisted value (no
  re-derivation) rather than two callers racing to re-write it.

* OUT-OF-BAND FROM THE HASH MACHINERY, BY DESIGN. The stack value is advisory
  only: it selects which of the two skippable advisory checks run (type
  annotations, test-function names) and the banner label. Nothing structural
  (required sections, GIVEN/WHEN/THEN, [CFC-N] tags, the content hash) depends on
  it. So the config is NOT folded into any content hash and NOT written during
  `--approve` — avoiding the CFC-cascade collision and the two-files-no-atomicity
  hazard. A stale/hand-edited config can at worst mislabel the banner or toggle an
  advisory check; it cannot corrupt the approval chain.

* CLOSED VOCABULARY. Writes are validated against the caller-supplied set of known
  profile keys, so a typo (`pyton`) is rejected at write time and never persisted.
  Reads are defensive: an unknown key (newer schema, hand-edit) is ignored and
  resolution falls back to detection rather than trusting garbage.
"""

from __future__ import annotations

import json
import re
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
    """Write (or overwrite) the persisted config. The ONE write path.

    `language` MUST be one of `known_languages` (the closed vocabulary) — a value
    outside it raises ValueError, so a typo is never persisted. `source` records
    provenance (`user` / `blueprint` / `auto-detect`). Returns the written path.
    Creates the `.sdd/` directory if needed. Writes a trailing newline and stable
    key order so the file diffs cleanly in version control.
    """
    known = set(known_languages)
    if language not in known:
        raise ValueError(
            f"refusing to persist unknown language {language!r}; "
            f"must be one of {sorted(known)}"
        )

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "language": language,
        "source": source,
    }
    if detected_from is not None:
        payload["detectedFrom"] = detected_from

    target = config_path(project_root.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


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
