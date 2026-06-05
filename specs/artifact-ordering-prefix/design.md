# Design: Artifact Ordering Prefix

**Spec:** `specs/artifact-ordering-prefix/spec.md`

## Goals and Non-Goals

**Goals:**
- Implement `strip_artifact_prefix(name: str) -> str` and `resolve_artifact(dir: Path, bare_name: str) -> Path` in `blueprint_common.py` as the single authoritative resolution chokepoint (R1, R2)
- Convert all ~50 construct-then-stat and equality-gate call sites across validators, `archive_pass.py`, `blueprint_common.py`, `reconcile.py`, and `render_business_brief.py` to use the two helpers (R1, R2)
- Flip default-on emission in all six phase references and both `SKILL.md` files (R3)
- Deliver a hash-safe, idempotent renamer `artifact_prefix.py` with pending-review guard (R4)
- Update all prose references in templates, agents, and phase references to use prefixed paths (R5)
- Provide a regression test suite proving bare/prefixed resolution, ambiguity detection, hash-safety, and pending-state blocking (R6)
- Add a mixed-state WARN to both validators and an interactive renamer offer to both skills (R7)

**Non-Goals:**
- No `specs/F<n>-<slug>/` directory grammar changes — `spec_dirname.py` is untouched
- No opt-out flag for default-on emission in v1
- No content modification during rename — pure filesystem rename only
- No `arch_config.py:116` directory-check modification — confirmed safe, out of scope
- No new network surfaces of any kind
- No changes to `TERMINAL_FILENAMES` structure — frozenset stays as 4 bare names, with prefix-stripping applied pre-test

## Architecture Decisions

| ID | Decision | Choice | Alternatives Rejected | Rationale | Consequences |
|----|----------|--------|-----------------------|-----------|--------------|
| AD1 | Helper location | `blueprint_common.py` | New dedicated `artifact_resolver.py` module | Already the shared home for hash helpers, `is_shipped`, and pending-review marker I/O; all call sites already import from here via `sys.path` | One canonical import path; no new module to discover or path-inject |
| AD2 | Ambiguity scan timing | Lazy — `resolve_artifact` checks on demand when the specific artifact is first accessed | Eager at directory-scan time | ~47 call sites each resolve a specific known artifact; none scan for unknown filenames. An eager scan would require a separate pre-validation pass with no existing driver; lazy is simpler and sufficient since the single-chokepoint architecture already catches every coexistence at the moment it matters | Ambiguity errors surface at first access, not at startup; multiple ambiguous files in the same dir produce one error per access; the regression tests make this observable |
| AD3 | Glob strategy for prefixed-form probe | `list(dir.glob("[0-9][0-9]_" + bare_name))` — collect ALL prefixed forms; run the glob ONLY when `bare_name in KNOWN_ARTIFACTS` | `next(dir.glob(...), None)` (finds only the first — would miss multiple-prefixed coexistence); `iterdir()` + regex filter | The ambiguity branch needs EVERY prefixed form to detect `01_spec.md` + `02_spec.md` coexistence; `next(...)` silently sees one and misses the conflict. The literal `[0-9][0-9]_` glob is anchored, no regex compile. Short-circuiting on `KNOWN_ARTIFACTS` avoids over-probing user files | If ≥2 prefixed forms coexist the list has len ≥ 2 and the ambiguity branch raises (see I2); a non-known `bare_name` skips the glob entirely |
| AD4 | `KNOWN_ARTIFACTS` placement | Module-level constant in `blueprint_common.py`, exported | In `artifact_prefix.py` only | The known-artifact set must be shared by both helpers (`strip_artifact_prefix` and `resolve_artifact`) and by the renamer's target mapping; a single definition in `blueprint_common.py` prevents drift | Importers of `blueprint_common` can also import `KNOWN_ARTIFACTS` directly |
| AD5 | CI/interactive suppression mechanism | A CLI subcommand `artifact_prefix.py --check <dir>` prints `OFFER`/`SUPPRESS` to stdout, gating on `sys.stdin.isatty()` AND `CI` env unset AND mixed state; skill prose RUNS this command and reads stdout | A `should_offer_renamer()` Python helper that skill prose "calls" (REJECTED — prose can only run a shell command and read stdout, it cannot branch on an in-process bool); a `--no-interactive` flag | Skill prose is model instructions; the only realizable contract is run-command-read-stdout. `--check` makes suppression a positive, subprocess-testable observable (run under `CI=true` / piped stdin → `SUPPRESS`). isatty/CI policy lives in the CLI, NOT in `blueprint_common` (a pure data module with zero such refs today) | The model offers iff `--check` prints `OFFER`; CI/non-interactive suppression is proven by a subprocess test, not by a helper's return value |
| AD6 | `ArtifactAmbiguityError` definition location | `blueprint_common.py` | `artifact_prefix.py` or local to each caller | Callers (`validate_spec.py`, `validate_blueprint.py`, `reconcile.py`) must catch this error; a shared definition in `blueprint_common.py` avoids each caller defining its own guard | All callers import one exception class; `test_artifact_prefix.py` imports the same class for `pytest.raises` assertions |
| AD7 | `render_business_brief._REQUIRED_ARTIFACTS` and `_read_artifact` conversion | Change `_REQUIRED_ARTIFACTS` to a tuple of bare names; replace `(p / name).is_file()` and `_read_artifact(p / name)` with `resolve_artifact(p, name)` at each site | Wrap the whole `validate_blueprint_dir` call | `validate_blueprint_dir` currently returns a resolved dir and checks bare-path membership; converting at the probe sites preserves the structure and keeps `_REQUIRED_ARTIFACTS` as the single definition | The missing-artifact error message shows the resolved path (or the bare path on absence), not a bare construction |
| AD8 | Renamer pending-review read mode | `read_pending_review(project_root, strict=True)` and REFUSE on `MarkerCorruptError` | `strict=False` (fails OPEN — a corrupt marker reads as empty-pending and the renamer proceeds, orphaning the obligation) | The renamer is enforcement-class (it gates a destructive rename on the marker); `blueprint_common.py:720-722` states every enforcement caller passes `strict=True`. A corrupt marker must fail CLOSED, mirroring `--decline-pending` (`validate_spec.py:1651-1660`) | A corrupt `.sdd/pending-review.json` makes the renamer refuse (exit non-zero), not proceed |
| AD9 | Renamer marker-key containment | Reuse `_key_is_contained` (`blueprint_common.py:822-834`) + `_prefix_in_scope` (`:837-845`) against RESOLVED paths | Roll a fresh `startswith` prefix check | The marker is keyed by per-file relpath; a naive `startswith` prefix-bleeds (`specs/foo` vs `specs/foobar`) and, with an unresolved/symlinked dir arg, can MISS the real key (fail-open). The codebase already proves these guards for the same marker | Renamer reuses the existing containment logic; symlink/`..` dir args refused; sibling dirs never cross-match |
| AD10 | Artifact-set single source | A symmetry test `set(PREFIX_MAP.keys()) == KNOWN_ARTIFACTS` (mirrors `test_arch_config.py`'s producer/consumer vocabulary-symmetry test) | Manually keeping the two in sync | `KNOWN_ARTIFACTS` (blueprint_common) and `PREFIX_MAP` (artifact_prefix.py) are two sources; without the test, adding an artifact to one but not the other silently splits (resolver tolerates it, renamer never prefixes it). The repo already uses symmetry tests (arch_config, cfc_parser) for exactly this drift class | A CI test fails if the two sets diverge |

## Component Design

### C1: Artifact Resolution Helpers (`blueprint_common.py`)

**Responsibility:** Provide the single authoritative implementation of `strip_artifact_prefix` and `resolve_artifact` so all callers share one regex and one ambiguity chokepoint.

**Location:** `telescoping-sdd/scripts/blueprint_common.py`

**Key additions:**
- `KNOWN_ARTIFACTS: frozenset[str]` — the six canonical bare names
- `ArtifactAmbiguityError(Exception)` — raised by `resolve_artifact` when both bare and prefixed forms coexist
- `strip_artifact_prefix(name: str) -> str` — strips `^\d{2}_` from `name` iff the stripped result is in `KNOWN_ARTIFACTS`; otherwise returns `name` unchanged
- `resolve_artifact(dir: Path, bare_name: str) -> Path` — probe bare then prefixed; raise `ArtifactAmbiguityError` if both exist; return bare path unchanged if neither exists

Inserted immediately after the existing `is_shipped` block (line ~334), before the `UnresolvedMarker` marker-scanning section (line ~341). The `KNOWN_ARTIFACTS` constant and `ArtifactAmbiguityError` class are defined at module level near the top of the file, grouped with existing module-level constants.

### C2: Call-Site Conversion (`validate_spec.py`, `validate_blueprint.py`, `archive_pass.py`, `blueprint_common.py`, `reconcile.py`, `render_business_brief.py`)

**Responsibility:** Convert every exact-equality gate, frozenset membership test, and construct-then-stat read site to use the two helpers from C1 — creating a prefix-tolerant read layer across the entire codebase.

**Location:** Six files enumerated in the Integration Points section; see also the call-site inventory table below.

**Conversion categories:**
1. **Equality gates** — wrap with `strip_artifact_prefix` before the `==` comparison
2. **`TERMINAL_FILENAMES` membership** — apply `strip_artifact_prefix(path.name)` before `in TERMINAL_FILENAMES`
3. **Construct-then-stat sites** — replace `dir / "bare.md"` with `resolve_artifact(dir, "bare.md")`

### C3: Renamer Script (`artifact_prefix.py`)

**Responsibility:** Accept a single directory path argument and rename all bare canonical artifacts in that directory to their `NN_` prefixed forms atomically, refusing on a corrupt/pending marker or a pre-existing ambiguity. Also provides a `--check <dir>` mode that prints `OFFER`/`SUPPRESS` — the testable interactivity gate for the R7 skill offer (C5).

**Location:** `telescoping-sdd/scripts/artifact_prefix.py` (new file)

**Key functions:**
- `main(argv)` — argparse entry point; dispatches `--check` mode vs the default rename mode; in rename mode orchestrates the guard checks then the rename loop
- `_check_mode(dir_path) -> int` — prints `OFFER` iff `_detect_prefix_state(dir_path) == "mixed"` AND `sys.stdin.isatty()` AND `CI` env unset; else prints `SUPPRESS` + reason; always exits 0 (advisory probe, never blocks)
- `_resolve_dir_and_root(dir_path) -> tuple[Path, Path, str]` — `resolve()`s the dir arg and the project root (`arch_config.find_project_root`) and returns the dir's project-root-relative posix prefix; refuses (exit 2) if the dir arg is not a directory or its resolved path escapes the root
- `_check_pending_refusal(root, dir_relprefix) -> Optional[str]` — reads `read_pending_review(root, strict=True)` (REFUSE on `MarkerCorruptError`); returns a refusal message if any pending key satisfies `_prefix_in_scope(key, dir_relprefix)` (boundary-safe — reuses the codebase helper, NOT a fresh `startswith`); None if clear
- `_check_ambiguity_preflight(dir_path) -> Optional[str]` — returns a refusal message if any bare artifact already has a coexisting prefixed form; None if clear
- `_rename_artifacts(dir_path) -> tuple[list[str], list[str]]` — returns (renamed, skipped); skips already-prefixed artifacts; refuses any artifact whose resolved path is a symlink or escapes `dir_path`; halts on first `OSError`

### C4: Mixed-State Surfacing (`validate_spec.py`, `validate_blueprint.py`)

**Responsibility:** Compute the three-state (uniformly-bare / mixed / uniformly-prefixed) for a directory and emit a non-blocking WARN only on mixed. This WARN is the machine-observable, fully-testable trigger (assert present on a mixed dir, absent on uniform).

**Location:** A new helper `_detect_prefix_state(dir_path: Path) -> str` in `blueprint_common.py` (pure filesystem stat — NO interactivity/CI sensing here); called from both validators' main dispatch to emit the WARN via `result.add(..., warn_only=True)`. The interactivity/CI gate for the *interactive offer* does NOT live here — it is the `artifact_prefix.py --check` CLI (AD5, C3, C5).

**Key functions:**
- `_detect_prefix_state(dir_path: Path) -> str` — returns `"uniform-bare"` / `"mixed"` / `"uniform-prefixed"` / `"empty"` based on artifact presence (pure stat)

### C5: Interactive Renamer Offer (both SKILL.md skill prose)

**Responsibility:** In an interactive session where the prefix state is mixed, offer to run the renamer — gated on the `--check` CLI, with faithful relay of the renamer's exit/refusals.

**Location:** Skill prose in `project-blueprint/SKILL.md` and `spec-driven-dev/SKILL.md`; this is behavior the calling Claude executes. Because prose can only run a shell command and read stdout (NOT branch on an in-process bool), the gate is the `artifact_prefix.py --check <dir>` CLI.

**Skill-prose contract (the testable half):** before presenting any offer text, the prose runs `python telescoping-sdd/scripts/artifact_prefix.py --check <dir>` and offers the renamer ONLY when stdout is `OFFER`. `--check` enforces mixed-state + interactivity + non-CI (AD5), so CI/non-interactive suppression is proven by a subprocess test of `--check`, not by model behavior.

**Prose-review checklist (the attested half — model-prose behaviors with no Python observable; verified by a numbered SKILL.md review step, NOT an automated test):**
1. The prose runs `--check` and gates the offer on an `OFFER` verdict.
2. The offer text contains the decline-reassurance sentence verbatim (declining is fine; bare names stay valid via the additive resolver).
3. The prose performs the pending-review pre-check before the offer: if a pending entry exists for the directory, do NOT present the offer as actionable — surface the pending obligation ("resolve or decline the pending review first, then re-run") instead.
4. The prose does not re-offer after a decline within the same session ("at most once per session / suppress after decline" — best-effort prose, since the model does not re-nag within a conversation; not machine-guarded).

Both `project-blueprint` and `spec-driven-dev` carry this prose.

### C6: Default-On Emission (phase references and templates)

**Responsibility:** Update all six phase reference files and both SKILL.md command examples to instruct drafting agents to write to prefixed paths.

**Location:** Six `phase-*.md` files (three per skill tier); both `SKILL.md` files; ten template files (`spec-template-*.md`, `design-template-*.md`, `tasks-template-*.md`, `scope-template.md`, `architecture-template.md`, `plan-template.md`); selectively, agent prose files in `telescoping-sdd/agents/` that reference literal artifact paths.

## Data Models

| Model | Field | Type | Constraints | Description |
|-------|-------|------|-------------|-------------|
| `KNOWN_ARTIFACTS` | — | `frozenset[str]` | Exactly 6 bare names | `{"spec.md", "design.md", "tasks.md", "SCOPE.md", "ARCHITECTURE.md", "PLAN.md"}` — the only names whose `^\d{2}_` prefix is honored |
| `PREFIX_MAP` | — | `dict[str, str]` | Keys ⊆ `KNOWN_ARTIFACTS`, values are `"NN_"` strings | `{"spec.md": "01_", "design.md": "02_", "tasks.md": "03_", "SCOPE.md": "01_", "ARCHITECTURE.md": "02_", "PLAN.md": "03_"}` — the renamer's target mapping; defined in `artifact_prefix.py` |
| `ArtifactAmbiguityError` | `bare_name` | `str` | Required | The bare artifact name (e.g. `"spec.md"`) that has conflicting forms |
| `ArtifactAmbiguityError` | `conflicting_paths` | `list[Path]` | Required, len >= 2 | All conflicting paths found (e.g. `[spec.md, 01_spec.md]` or `[01_spec.md, 02_spec.md]`); always at least 2 elements |
| `ArtifactAmbiguityError` | `identical_content` | `bool` | Required | True iff all conflicting paths have byte-identical content — message differs when True. **Best-effort:** False when content differs, a path is non-existing, OR any path is unreadable (permission / binary-decode). The content read is bounded to the ambiguity path; a raw `OSError`/`UnicodeDecodeError` must never escape `resolve_artifact` |

**Relationships:**
- `PREFIX_MAP` keys MUST equal `KNOWN_ARTIFACTS` (identical sets); a symmetry test `set(PREFIX_MAP.keys()) == KNOWN_ARTIFACTS` enforces this (AD10), mirroring `test_arch_config.py`'s vocabulary-symmetry test so the two sources cannot drift
- `ArtifactAmbiguityError` carries structured fields so callers can construct context-specific messages without string-parsing the exception message

**Persistence:** `KNOWN_ARTIFACTS` and `PREFIX_MAP` are module-level constants (no persistence). `ArtifactAmbiguityError` is ephemeral (exception only). No new persistent data models introduced.

## Interfaces

```python
# blueprint_common.py additions

KNOWN_ARTIFACTS: frozenset[str] = frozenset({
    "spec.md", "design.md", "tasks.md",
    "SCOPE.md", "ARCHITECTURE.md", "PLAN.md",
})

_PREFIX_RE = re.compile(r"^\d{2}_")


class ArtifactAmbiguityError(Exception):
    """Raised by resolve_artifact when two or more forms of the same artifact coexist.

    Covers both bare+prefixed coexistence and multiple-prefixed coexistence.
    Carries structured fields so callers can tailor the message.
    """
    def __init__(
        self,
        bare_name: str,
        conflicting_paths: list[Path],
        identical_content: bool,
    ) -> None: ...

    bare_name: str
    conflicting_paths: list[Path]   # len >= 2
    identical_content: bool         # True iff all paths have byte-identical content


def strip_artifact_prefix(name: str) -> str:
    """Strip a leading NN_ prefix from name, but only for known artifacts.

    Args:
        name: A filename basename (e.g. "01_spec.md" or "12_factor_notes.md").

    Returns:
        The basename with the NN_ prefix removed if the stripped result is in
        KNOWN_ARTIFACTS; otherwise the original name unchanged.

    Raises:
        (nothing — pure function, no I/O)

    Examples:
        strip_artifact_prefix("01_spec.md")     -> "spec.md"
        strip_artifact_prefix("03_PLAN.md")     -> "PLAN.md"
        strip_artifact_prefix("spec.md")        -> "spec.md"  (no prefix, unchanged)
        strip_artifact_prefix("12_factor.md")   -> "12_factor.md"  (not in KNOWN_ARTIFACTS)
        strip_artifact_prefix("01_design.md")   -> "design.md"  (IS in KNOWN_ARTIFACTS)
    """
    ...


def resolve_artifact(dir: Path, bare_name: str) -> Path:
    """Resolve an artifact by bare name, tolerating an optional NN_ prefix.

    Probe strategy:
      0. If bare_name NOT in KNOWN_ARTIFACTS: skip the glob entirely and return
         dir / bare_name (no prefix is ever honored for it; no ambiguity possible
         — prevents over-probe of user files like "01_something.md").
      1. prefixed = list(dir.glob("[0-9][0-9]_" + bare_name))   # ALL forms, NOT next()
      2. bare_exists = (dir / bare_name).is_file()
      3. Ambiguity check (BEFORE returning anything):
         - If bare_exists AND prefixed: raise ArtifactAmbiguityError (bare + prefixed).
         - If len(prefixed) >= 2 (no bare): raise ArtifactAmbiguityError (multiple prefixed).
      4. Return the unique form found:
         - bare_exists and not prefixed: return dir / bare_name.
         - exactly one prefixed and not bare_exists: return that prefixed path.
         - neither exists: return dir / bare_name unchanged (do NOT raise).

    Args:
        dir: The directory to probe (blueprint/ or specs/<dir>/). A non-existent
            dir is safe: Path.glob yields empty and (dir/bare).is_file() is False,
            so the bare path is returned without raising.
        bare_name: A name from KNOWN_ARTIFACTS (e.g. "spec.md"). A name not in
            KNOWN_ARTIFACTS short-circuits at step 0 (no glob attempted).

    Returns:
        A Path to the resolved artifact (may not exist if neither form present).

    Raises:
        ArtifactAmbiguityError: when both bare and any prefixed form coexist, or
            when multiple distinct prefixed forms coexist. This is the ONLY
            exception type that may escape: a raw OSError / UnicodeDecodeError
            from the best-effort identical-content read is swallowed
            (identical_content=False) and never propagates. The error MESSAGE
            text is identical across all catchers (the exception centralizes it);
            only the caller's exit/disposition behavior varies.
        (No raise when the artifact is simply absent — soft-absence must be
        preserved for callers using read_file(...) -> None / .is_file() -> False.)

    Contracts:
        - Postcondition: if the returned path exists, it is the unique form.
        - Side effects: stat/glob on the happy path; on the ambiguity path ONLY,
          a bounded best-effort content read of the conflicting files to set
          identical_content (read errors -> False, never raised). No writes.
    """
    ...
```

**ArtifactAmbiguityError message format:**

When content differs (two forms of same artifact):
```
Ambiguous artifact 'spec.md': multiple forms found:
  specs/F1-foo/spec.md
  specs/F1-foo/01_spec.md
Remove one to continue. To fix: delete the file you do not want to keep, then re-run.
```

When content is identical:
```
Ambiguous artifact 'spec.md': multiple forms found with identical content:
  specs/F1-foo/spec.md
  specs/F1-foo/01_spec.md
Both files are byte-identical; you may safely remove either one
(keeping the prefixed form '01_spec.md' gives sortable names).
```

The message format applies equally when two prefixed forms coexist (e.g. `01_spec.md` and `02_spec.md`); list both paths and state they must be resolved manually.

```python
# artifact_prefix.py public surface

PREFIX_MAP: dict[str, str] = {
    "spec.md":          "01_",
    "design.md":        "02_",
    "tasks.md":         "03_",
    "SCOPE.md":         "01_",
    "ARCHITECTURE.md":  "02_",
    "PLAN.md":          "03_",
}


def _find_project_root_for_dir(dir_path: Path) -> Path:
    """Delegate to arch_config.find_project_root to locate .sdd/pending-review.json.

    Passes dir_path directly (arch_config.find_project_root walks up looking for
    .sdd/, blueprint/, specs/, or .git markers; falls back to dir_path.parent if
    no marker found). This avoids reimplementing the walk-up logic.

    Returns:
        The resolved project root path (always returns a Path, never raises).
    """
    ...


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the renamer.

    Modes:
        default (a <dir> arg):  rename bare artifacts in <dir> to prefixed form.
        --check <dir>:          print "OFFER"/"SUPPRESS" (the R7 interactivity
                                gate skill prose runs; AD5/C5); always exits 0.

    Args:
        argv: Argument list; defaults to sys.argv[1:].

    Returns (rename mode):
        0 on success (including nothing-to-rename); any --check run also exits 0.
        1 on refusal (corrupt marker / pending-review / pre-existing ambiguity /
          rename failure / symlink-or-escape).
        2 on usage error (wrong args, non-directory path, dir escapes project root).

    Exit codes:
        0: All bare artifacts renamed (or nothing to rename); or any --check run.
        1: Refused (corrupt-marker MarkerCorruptError / pending-review /
           pre-existing ambiguity / rename OSError / unsafe path).
        2: Usage error.
    """
    ...
```

**Contracts for `main`:**
- Precondition: the supplied path is a directory
- The renamer never modifies file content — only the filesystem name
- Already-prefixed artifacts are skipped silently (idempotent)
- The first `OSError` during rename causes an immediate exit(1) with the offending path; earlier successful renames in the same run are NOT rolled back (atomic per-file, not atomic per-directory)
- Hash-safety invariant: after rename, `verify_content_hash(content, stored_hash)` returns True for every renamed file because `content_for_hashing` operates on file content and is filename-independent

```python
# blueprint_common.py additions (pure data/stat — NO interactivity/CI/session
# sensing here; the interactive-offer gate is the artifact_prefix.py --check CLI)

def _detect_prefix_state(dir_path: Path) -> str:
    """Return the prefix state of known artifacts in dir_path.

    Returns:
        "uniform-bare":     one or more bare artifacts found, zero prefixed artifacts.
        "uniform-prefixed": one or more prefixed artifacts found, zero bare artifacts.
        "mixed":            at least one bare artifact AND at least one prefixed
                            artifact found (counting independently per artifact name:
                            if both spec.md AND 01_spec.md exist, that single artifact
                            contributes one bare count and one prefixed count, making
                            the state "mixed" — the ambiguity case is correctly
                            classified as mixed and the validator WARN fires; the
                            ArtifactAmbiguityError itself is raised separately by
                            resolve_artifact when the artifact is actually read).
        "empty":            no known artifacts found in the directory.

    Side effects: filesystem stats only.
    """
    ...
```

## Error Handling

- **Strategy:** exceptions for programmer errors (`ArtifactAmbiguityError`); return-code + printed message for CLI errors (renamer exits 1 or 2); `ValidationResult.add(..., warn_only=True)` for non-blocking validator WARNs
- **Custom exceptions:**
  - `ArtifactAmbiguityError` — raised by `resolve_artifact` when coexistence detected; caught by validator callers, which convert it to a FAIL result entry naming both files and providing the recovery path; caught by renamer callers, which print and exit(1)
- **`ArtifactAmbiguityError` catch discipline (per caller class):**
  - **Validators** (`validate_spec.py`, `validate_blueprint.py`, `render_business_brief.py`) — catch and FAIL-CLOSED: convert to a FAIL result naming both files with the recovery path (validators), or `sys.exit(1)` with the message (`render_business_brief`):
    ```python
    try:
        path = resolve_artifact(spec_dir, "spec.md")
    except ArtifactAmbiguityError as exc:
        result.add("spec.md ambiguity", False, str(exc))
        return result
    ```
  - **`reconcile.py` (CPD boundary) — catch and DEGRADE:** sites 573/709 read a *sibling repo's* `blueprint/PLAN.md` and 624 the derived `spec.md`; today these degrade gracefully (content/None). An uncaught raise would abort the whole reconcile. Each `resolve_artifact` site catches `ArtifactAmbiguityError` and treats the artifact as unreadable (the existing None / skip path), preserving the soft-read semantics R1 protects; a WARN may print, but reconcile does not crash.
  - **Renamer** — catch, print, exit(1) (it gates a destructive op; ambiguity is a hard refusal).
- **Fail-closed CLI invariant:** an uncaught `ArtifactAmbiguityError` (or `MarkerCorruptError`) in ANY validator CLI branch (`--approve`, `--set-language`, `--decline-pending`, default validate) must propagate to a NON-zero exit and must NEVER reach a code path that exits 0 or stamps a content hash. (Verified safe today: `check_dir_identifier`→`resolve_artifact` runs before `approve_document`, so a raise aborts before the hash write — this invariant makes it explicit so a future broad `except` cannot flip it open.)
- **Logging:** no change to existing logging conventions; the validators print to stdout; the renamer prints to stdout on success, stderr on error (consistent with `spec_dirname.py` pattern)
- **User-facing errors:**
  - Pending-review refusal: `"Refusing to rename <dir>: pending panel-review obligation for <artifact>. Resolve or decline the pending review first (--decline-pending), then re-run."` (marker read with `strict=True`; key matched via `_prefix_in_scope`)
  - Corrupt-marker refusal: `"Refusing to rename <dir>: .sdd/pending-review.json is corrupt/unreadable. Inspect or delete it manually, then re-run."` (on `MarkerCorruptError` from `strict=True`; mirrors `--decline-pending`'s corrupt handling — fail-closed)
  - Unsafe-path refusal: `"Refusing to rename <dir>: '<artifact>' is a symlink or resolves outside <dir>."` (exit 1); `"Error: <dir> is not a directory or escapes the project root."` (exit 2)
  - Ambiguity refusal: `"Refusing to rename <dir>: both '<bare>' and '<prefixed>' already exist. Remove the conflicting file first."`
  - Ambiguity in `render_business_brief.py`: `ArtifactAmbiguityError` from `validate_blueprint_dir` → `sys.exit(1)` with the exception message (same pattern as missing-artifact); `validate_blueprint_dir` catches `ArtifactAmbiguityError` from its `resolve_artifact` calls and calls `sys.exit(1)` with the message
  - Rename failure: `"Error renaming '<src>' to '<dst>': <OSError.strerror>"`
  - Nothing to rename: `"Nothing to rename in <dir>: all known artifacts are already prefixed or absent."` (exit 0)
  - Mixed-state WARN (validator): `"WARN: <dir> has a mixed prefix state — some artifacts are prefixed, some are bare. Run 'python telescoping-sdd/scripts/artifact_prefix.py <dir>' to complete the rename."` (non-blocking, appears in `result.summary()` with WARN status)

## Testing Strategy

- **Framework:** pytest, invoked via `.venv/bin/pytest telescoping-sdd/ -q`
- **Test location:** `telescoping-sdd/scripts/tests/test_artifact_prefix.py` (new); additions to `telescoping-sdd/scripts/tests/test_archive_pass.py` and `telescoping-sdd/scripts/tests/test_blueprint_common.py`
- **Mocking approach:** `tmp_path` pytest fixture for filesystem isolation; `monkeypatch` for `sys.stdin.isatty` and CI env var suppression tests; direct module import (same `_load_archive_pass`-style pattern) for unit tests on private helpers
- **Coverage expectations:** every public function has at least one happy-path test and one error-path test; the complete R6 acceptance-criteria matrix maps 1:1 to named test functions

### `test_artifact_prefix.py` — new file

Import pattern (mirrors `test_archive_pass.py` and `test_blueprint_common.py`):

```python
_SCRIPTS = Path(__file__).resolve().parents[1]  # telescoping-sdd/scripts/
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import blueprint_common as bc
```

**Helper tests (C1 — `strip_artifact_prefix`, `resolve_artifact`):**

| Test function | What it covers |
|---|---|
| `test_strip_artifact_prefix_bare_name_unchanged` | `"spec.md"` → `"spec.md"` (no prefix, returns unchanged) |
| `test_strip_artifact_prefix_known_artifacts` | All 6 `NN_` prefixed forms → correct bare name |
| `test_strip_artifact_prefix_non_artifact_unchanged` | `"12_factor_notes.md"` → unchanged (not in KNOWN_ARTIFACTS) |
| `test_strip_artifact_prefix_zero_prefix_unchanged` | `"00_readme.md"` → unchanged (stripped `readme.md` not in KNOWN_ARTIFACTS) |
| `test_strip_artifact_prefix_user_design_file` | `"01_design.md"` → `"design.md"` (IS in KNOWN_ARTIFACTS — this tests the expected over-match is handled by `resolve_artifact`, not `strip_artifact_prefix`) |
| `test_resolve_artifact_bare_exists` | bare `spec.md` present → returns bare path |
| `test_resolve_artifact_prefixed_exists` | `01_spec.md` present, bare absent → returns prefixed path |
| `test_resolve_artifact_absent_returns_bare` | neither form exists → returns bare path (no raise) |
| `test_resolve_artifact_both_exist_raises` | both `spec.md` and `01_spec.md` present (different content) → raises `ArtifactAmbiguityError` |
| `test_resolve_artifact_both_exist_identical_content_raises` | both exist with identical content → raises `ArtifactAmbiguityError` (same-content coexistence is still ambiguous); `exc.identical_content` is True |
| `test_resolve_artifact_ambiguity_error_message_identical_content` | when `identical_content=True`, error message says "byte-identical" and advises safe removal |
| `test_resolve_artifact_user_01_design_coexists_with_02_design` | `01_design.md` AND `02_design.md` both strip to `design.md` → raises `ArtifactAmbiguityError` (multiple prefixed forms) |
| `test_resolve_artifact_non_artifact_bare_returned` | `resolve_artifact(dir, "factor_notes.md")` where neither form exists → bare path returned (name not in KNOWN_ARTIFACTS, no glob attempted) |
| `test_resolve_artifact_nonexistent_dir` | `resolve_artifact(missing_dir, "spec.md")` (dir itself absent) → returns bare path, no raise (glob on a missing dir yields empty) |
| `test_resolve_artifact_stemless_prefix_ignored` | a file `01_` / `01_.md` present → not treated as any artifact (stripped name not in KNOWN_ARTIFACTS) |
| `test_resolve_artifact_editor_backup_ignored` | `01_spec.md~` present (editor backup) → not matched by the `[0-9][0-9]_spec.md` glob; bare resolution unaffected |
| `test_resolve_artifact_single_misordinaled_prefix` | only `02_spec.md` present (no bare, wrong ordinal) → returned as canonical spec (exactly one prefixed form; the ordinal value is not validated by the resolver) |
| `test_resolve_artifact_identical_content_unreadable_is_false` | both forms coexist, one unreadable → `ArtifactAmbiguityError` raised with `identical_content=False`; no raw OSError escapes |
| `test_prefix_map_known_artifacts_symmetry` | `set(PREFIX_MAP.keys()) == KNOWN_ARTIFACTS` (AD10 — prevents the two sources drifting; mirrors `test_arch_config.py`) |

**Renamer tests (C3 — `artifact_prefix.py`):**

| Test function | What it covers |
|---|---|
| `test_renamer_renames_all_bare_artifacts` | bare dir → all 6 renamed to prefixed form |
| `test_renamer_hash_safety` | (1) write an artifact with a REAL stamped `**Content Hash:** `77cb9d8bd9d4971c`compute_content_hash`; (2) rename; (3) re-read and assert `verify_content_hash(new_content, original_stored_hash)` is True — proves the invariant end-to-end (not a placeholder hash) |
| `test_renamer_idempotent_all_prefixed` | already-prefixed dir → exit 0, "nothing to rename" |
| `test_renamer_idempotent_partial` | 2-of-3 already prefixed → renames only the remaining bare artifact |
| `test_renamer_nothing_to_rename_exit_zero` | empty dir (no known artifacts) → exit 0 |
| `test_renamer_pending_review_refusal` | pending entry for any artifact in dir → exit 1, message names the artifact |
| `test_renamer_pending_entry_different_dir_no_refusal` | pending entry for a different dir → renamer proceeds (directory-scoped check) |
| `test_renamer_ambiguity_refusal` | both `spec.md` and `01_spec.md` present → exit 1, names both |
| `test_renamer_rename_failure_halts` | first rename fails (permissions) → exit 1, no further renames attempted |
| `test_renamer_corrupt_marker_refuses` | corrupt `.sdd/pending-review.json` present → `strict=True` raises `MarkerCorruptError` → renamer exits 1, renames nothing (fail-closed) |
| `test_renamer_pending_entry_sibling_dir_no_bleed` | pending entry for `specs/foobar/spec.md`, renamer run on `specs/foo/` → proceeds (`_prefix_in_scope` is boundary-safe; `specs/foo` ≠ `specs/foobar`) |
| `test_renamer_pending_entry_per_file_key_match` | pending key is `specs/foo/02_design.md`, renamer run on `specs/foo/` → refuses (the per-file key under the dir prefix is matched) |
| `test_renamer_symlink_artifact_refused` | an artifact in the dir is a symlink → refused/skipped (resolved path escapes the dir) |
| `test_renamer_dir_relative_path_resolves` | dir passed as a relative path / with `..` → resolved before the pending-key prefix is computed; matching still correct |
| `test_renamer_finds_root_from_nested_dir` | dir arg several levels below `.sdd/` → `arch_config.find_project_root` walk-up locates the marker; the pending-key prefix is computed against the correct root (hardens RI5's unresolved-dir-arg leg) |
| `test_renamer_check_offer_mixed_interactive` | `--check` on a mixed dir with tty + no CI → prints `OFFER`, exit 0 |
| `test_renamer_check_suppress_ci` | `--check` under `CI=true` → prints `SUPPRESS`, exit 0 (subprocess; the CI-suppression observable) |
| `test_renamer_check_suppress_no_tty` | `--check` with piped stdin (no tty) → prints `SUPPRESS`, exit 0 |
| `test_renamer_check_suppress_uniform` | `--check` on a uniform-bare or uniform-prefixed dir → prints `SUPPRESS`, exit 0 |
| `test_renamer_midfailure_leaves_mixed_state` | force a mid-rename OSError, then assert `_detect_prefix_state(dir) == "mixed"` (verifies RI4's WARN-routes-back mitigation end-to-end) |

**`test_archive_pass.py` additions:**

| Test function | What it covers |
|---|---|
| `test_terminal_filenames_prefix_tolerant_plan` | `_is_terminal("", Path("03_PLAN.md"), False)` → True |
| `test_terminal_filenames_prefix_tolerant_tasks` | `_is_terminal("", Path("03_tasks.md"), False)` → True |
| `test_terminal_filenames_prefix_tolerant_tasks_python` | `_is_terminal("", Path("03_tasks-python.md"), False)` → True (defensive-registry coverage) |
| `test_terminal_filenames_prefix_tolerant_tasks_java` | `_is_terminal("", Path("03_tasks-java.md"), False)` → True (defensive-registry coverage) |
| `test_terminal_filenames_non_terminal_spec` | `_is_terminal("", Path("01_spec.md"), False)` → False |
| `test_terminal_filenames_non_terminal_design` | `_is_terminal("", Path("02_design.md"), False)` → False |
| `test_archive_pass_cli_rejects_prefixed_plan_without_terminal` | subprocess: `archive_pass.py 03_PLAN.md --phase 1` (no `--terminal`) → non-zero exit with TERMINAL_FILENAMES error |

**`test_blueprint_common.py` additions:**

| Test function | What it covers |
|---|---|
| `test_is_shipped_resolves_prefixed_artifacts` | `is_shipped` with `01_spec.md`, `02_design.md`, `03_tasks.md` in `spec_dir` → same result as bare names |
| `test_detect_prefix_state_uniform_bare` | all bare artifacts → `"uniform-bare"` |
| `test_detect_prefix_state_uniform_prefixed` | all prefixed → `"uniform-prefixed"` |
| `test_detect_prefix_state_mixed` | some bare, some prefixed → `"mixed"` |
| `test_detect_prefix_state_empty` | no artifacts → `"empty"` |

**Definition-of-done grep gate (meta-test) — necessary but NOT sufficient:**

A `test_no_bare_artifact_constructions` test in `test_artifact_prefix.py` that greps the six modified non-test source files (`validate_spec.py`, `validate_blueprint.py`, `archive_pass.py`, `blueprint_common.py`, `reconcile.py`, `render_business_brief.py`) for un-wrapped bare-artifact constructions and asserts zero matches. Patterns:
1. **Literal equality gates:** `== "spec\.md"` … `== "PLAN\.md"` (all six).
2. **Frozenset membership:** `in TERMINAL_FILENAMES` not preceded by `strip_artifact_prefix(` on the same logical line.
3. **Literal path constructions:** `/ "spec\.md"` … `/ "PLAN\.md"` outside the `resolve_artifact` body.
4. **Variable/map-indexed constructions (the highest-value sites the literal patterns MISS):** `<ident> / <ident>`, `<ident> / <map>[...]`, `<ident> / f"{...}.md"` NOT wrapped in `resolve_artifact(` — covers `spec_dir / file_map[args.approve]` (1674/2127), `spec_dir / prev_file` (613/1539), `spec_dir / f"{phase_key}.md"` (1743/2211).

**Exclusion strategy** (avoid false positives on the design's OWN error-message f-strings, which contain bare artifact names): the gate scopes to *construction syntax* (`<Path-expr> "/" <expr>`), not arbitrary string occurrences; the few legitimate literal lines (the `ArtifactAmbiguityError` message blocks) carry a `# noqa: artifact-literal` marker the gate skips; comment lines are excluded. **Negative self-test** `test_grep_gate_catches_known_bad`: a fixture containing a known-bad `dir / "spec.md"` AND a `dir / file_map[k]` that the gate MUST flag — proving the gate's own correctness rather than assuming it.

**The grep gate alone is insufficient for the variable-formed sites** (a multi-line or variable-indirected construction can still evade a line-anchored grep). The real RI1/RI2 guard is the named integration tests below.

**Integration tests (the real RI1/RI2 guard — run the REAL validators against PREFIXED dirs):**

| Test function | What it covers |
|---|---|
| `test_validate_spec_prefixed_dir_equiv` | subprocess `validate_spec.py` on a `tmp_path` with `01_spec.md`/`02_design.md`/`03_tasks.md` → identical pass/fail to the bare equivalent |
| `test_validate_blueprint_prefixed_dir_equiv` | subprocess `validate_blueprint.py` on a `blueprint/` with `01_SCOPE.md`/`02_ARCHITECTURE.md`/`03_PLAN.md` → identical to bare |
| `test_validate_spec_approve_prefixed_roundtrip` | `--approve spec` on a prefixed `01_spec.md` → stamps the hash (the `file_map`/approve-target path resolves) |
| `test_validate_blueprint_scan_prefix_prefixed_plan` | approve a prefixed `03_PLAN.md`, stamp a pending entry, assert the `scan_prefix` key (line 2244) matches the resolved relpath (RI3) |
| `test_render_business_brief_prefixed_blueprint` | `render_business_brief.py` against a prefixed blueprint → renders, no "missing artifact" (RI2) |

**R7 interactive offer — the testable half and the attested half:**

The offer is emitted by the Claude model from SKILL.md prose, so no automated test can prove the *model* stays silent. The design splits verification accordingly:

- **Testable half — the `artifact_prefix.py --check <dir>` CLI** (subprocess tests, the `test_renamer_check_*` rows above): prints `OFFER` only when mixed + tty + non-CI; `SUPPRESS` otherwise. This makes CI/non-interactive suppression a positive observable proven by a test (`test_renamer_check_suppress_ci`, `..._no_tty`), satisfying the spec's "provably absent under that signal, NOT a manual attestation" criterion — the model offers ONLY when `--check` prints `OFFER`, and `--check` prints `SUPPRESS` under CI/no-TTY.
- **Attested half — the SKILL.md prose-review checklist (C5):** "at most once per session / suppress after decline" and "decline-reassurance sentence present" are model-prose behaviors with no Python observable. Verification is a numbered review of both SKILL.md files (prose runs `--check` before any offer; reassurance sentence verbatim; pending-review pre-check before the offer; no re-offer after decline). This is honestly an attestation, not an automated test — the design does not claim otherwise (the previously-proposed `should_offer_renamer` helper was removed because a passing `helper==False` test does not prove the model emits nothing).

## File Structure

```
telescoping-sdd/
├── scripts/
│   ├── artifact_prefix.py              — NEW: hash-safe bulk renamer + --check gate (C3)
│   ├── blueprint_common.py             — MODIFIED: add KNOWN_ARTIFACTS, ArtifactAmbiguityError,
│   │                                     strip_artifact_prefix, resolve_artifact,
│   │                                     _detect_prefix_state; convert is_shipped (lines 330–332)
│   ├── archive_pass.py                 — MODIFIED: _is_terminal (line 128) and gate (line 658):
│   │                                     apply strip_artifact_prefix before TERMINAL_FILENAMES test
│   └── reconcile.py                    — MODIFIED: spec.md lookup (line 624), master PLAN.md
│                                         constructions (lines 573, 709) → resolve_artifact
├── skills/
│   ├── project-blueprint/
│   │   ├── scripts/
│   │   │   ├── validate_blueprint.py   — MODIFIED: equality gates (1381, 908, 928);
│   │   │   │                             check_previous_phase_approved (1535, 1539);
│   │   │   │                             file_map / phase_file_map values used at
│   │   │   │                             target / expected_file / scan_prefix (2127, 2211,
│   │   │   │                             2244) → resolve_artifact; path constructions
│   │   │   │                             (1561, 1659, 1745, 2090) → resolve_artifact;
│   │   │   │                             classify_spec paths (449–451) → resolve_artifact
│   │   │   └── render_business_brief.py — MODIFIED: _REQUIRED_ARTIFACTS membership check
│   │   │                                  (line 144) and _read_artifact calls (817–819)
│   │   │                                  → resolve_artifact; validate_blueprint_dir updated
│   │   ├── references/
│   │   │   ├── phase-scope.md          — MODIFIED: Write-target → 01_SCOPE.md
│   │   │   ├── phase-architecture.md   — MODIFIED: Write-target → 02_ARCHITECTURE.md
│   │   │   ├── phase-plan.md           — MODIFIED: Write-target → 03_PLAN.md
│   │   │   ├── scope-template.md       — MODIFIED: sibling artifact refs → prefixed
│   │   │   ├── architecture-template.md — MODIFIED: sibling artifact refs → prefixed
│   │   │   ├── plan-template.md        — MODIFIED: sibling artifact refs → prefixed
│   │   │   └── panel-review.md         — MODIFIED: Deferred targets + command examples
│   │   └── SKILL.md                    — MODIFIED: command examples → prefixed; add
│   │                                     interactive renamer offer prose (C5)
│   └── spec-driven-dev/
│       ├── scripts/
│       │   └── validate_spec.py        — MODIFIED: phase_order (line 608); expected_file
│       │                                 (line 1743); find_project_root PLAN gate (1313);
│       │                                 CFC consumer read (1384); approve file_map (1673);
│       │                                 path constructions (644, 864, 1049, 1110, 1149,
│       │                                 1242, 1364) → resolve_artifact
│       ├── references/
│       │   ├── phase-specify.md        — MODIFIED: Write-target → 01_spec.md
│       │   ├── phase-design.md         — MODIFIED: Write-target → 02_design.md
│       │   ├── phase-tasks.md          — MODIFIED: Write-target → 03_tasks.md
│       │   ├── panel-review.md         — MODIFIED: Deferred targets + command examples
│       │   ├── spec-template-python.md — MODIFIED: upstream path boilerplate → prefixed
│       │   ├── spec-template-java.md   — MODIFIED: upstream path boilerplate → prefixed
│       │   ├── design-template-python.md — MODIFIED: spec reference → prefixed
│       │   ├── design-template-java.md   — MODIFIED: spec reference → prefixed
│       │   ├── tasks-template-python.md  — MODIFIED: spec/design references → prefixed
│       │   └── tasks-template-java.md    — MODIFIED: spec/design references → prefixed
│       └── SKILL.md                    — MODIFIED: command examples → prefixed; add
│                                         interactive renamer offer prose (C5)
└── agents/                             — MODIFIED (selectively): agents whose prompts
                                          reference literal artifact paths updated to
                                          prefixed forms or state both forms accepted
```

**New files:**
- `telescoping-sdd/scripts/artifact_prefix.py`
- `telescoping-sdd/scripts/tests/test_artifact_prefix.py`

**NOT modified (confirmed safe):**
- `telescoping-sdd/scripts/arch_config.py` — line 116 is a directory check (`"specs"`) not a file check
- `telescoping-sdd/scripts/spec_dirname.py` — owns directory naming only
- `telescoping-sdd/scripts/cfc_parser.py` — pure content parser; no file-resolution logic

## Dependencies

| Package | Purpose |
|---------|---------|
| No new packages | `re`, `os`, `pathlib`, `json`, `sys` (all stdlib) — the feature requires no third-party dependencies. `blueprint_common.py` already imports all needed stdlib modules. `artifact_prefix.py` uses only stdlib (argparse, os, sys, pathlib, json via blueprint_common). |

## Integration Points

| Existing Module | Direction | Change Required | Details |
|-----------------|-----------|-----------------|---------|
| `blueprint_common.py` | Extended | Add 5 new symbols (pure data/stat — NO interactivity sensing) | `KNOWN_ARTIFACTS`, `ArtifactAmbiguityError`, `strip_artifact_prefix`, `resolve_artifact`, `_detect_prefix_state`; inserted after line ~334 (after the `is_shipped` block). The interactive-offer gate is NOT here — it is `artifact_prefix.py --check` |
| `archive_pass.py` | Calls into `blueprint_common` | Import `strip_artifact_prefix` | Two sites: `_is_terminal` (line 128) and the CLI gate (line 658); add import at top of file alongside existing `blueprint_common` import |
| `validate_blueprint.py` | Calls into `blueprint_common` | Import `resolve_artifact`, `ArtifactAmbiguityError`, `strip_artifact_prefix` | ~50 sites; add to existing `from blueprint_common import ...` block |
| `validate_spec.py` | Calls into `blueprint_common` | Import `resolve_artifact`, `ArtifactAmbiguityError`, `strip_artifact_prefix` | ~35 sites; add to existing import block |
| `reconcile.py` | Calls into `blueprint_common` | Import `resolve_artifact`, `ArtifactAmbiguityError` | 3 sites (573, 624, 709); each wrapped in catch-and-DEGRADE (treat ambiguity as unreadable → existing None/skip), preserving the CPD soft-read semantics — an uncaught raise must NOT abort reconcile |
| `render_business_brief.py` | Calls into `blueprint_common` | Import `resolve_artifact`, `ArtifactAmbiguityError` | 4 sites; add import; `validate_blueprint_dir` changes structure slightly — missing artifact error may show resolved path |
| `blueprint_common.is_shipped` | Internal | Replace direct path constructions (lines 330–332) | `read_file(spec_dir / "spec.md")` → `read_file(resolve_artifact(spec_dir, "spec.md"))` for all three artifact reads |
| `artifact_prefix.py` (new) | Calls into `blueprint_common` and `arch_config` | Import from both | Imports `KNOWN_ARTIFACTS`, `_detect_prefix_state`, `read_pending_review` (called `strict=True`), `verify_content_hash`, `MarkerCorruptError`, and the boundary-safe `_key_is_contained` / `_prefix_in_scope` from `blueprint_common`; `find_project_root` from `arch_config`. Defines `PREFIX_MAP` and the `--check` subcommand; same `sys.path` injection as the validators |
| `.sdd/pending-review.json` | Read by renamer (enforcement-class) | No schema change | Renamer reads via `read_pending_review(project_root, strict=True)` (REFUSE on `MarkerCorruptError` — fail-closed, AD8) and matches `data["pending"]` per-file keys against the RESOLVED dir relpath via `_prefix_in_scope` (boundary-safe, AD9); the marker structure is unchanged |

### Call-site inventory by category

**Category A: Equality gates → `strip_artifact_prefix` before `==`**

| File | Line | Current gate | Conversion note |
|------|------|-------------|-----------------|
| `validate_blueprint.py` | 1381 | `file_path.name == "PLAN.md"` | `strip_artifact_prefix(file_path.name) == "PLAN.md"` |
| `validate_blueprint.py` | 908 | `artifact_name == "tasks.md"` | `strip_artifact_prefix(artifact_name) == "tasks.md"` (vacuous — loop literal, per spec) |
| `validate_blueprint.py` | 928 | `artifact_name == "tasks.md"` | same (vacuous — second occurrence in same loop) |

**Category B: `TERMINAL_FILENAMES` membership → `strip_artifact_prefix` before `in`**

| File | Line | Current gate | Conversion note |
|------|------|-------------|-----------------|
| `archive_pass.py` | 128 | `path.name in TERMINAL_FILENAMES` | `strip_artifact_prefix(path.name) in TERMINAL_FILENAMES` |
| `archive_pass.py` | 658 | `art.name in TERMINAL_FILENAMES` | `strip_artifact_prefix(art.name) in TERMINAL_FILENAMES` |

**Category C: Construct-then-stat → `resolve_artifact`**

*`validate_spec.py`:*

| Line | Current construction | Conversion |
|------|---------------------|------------|
| 613 | `prev_path = spec_dir / prev_file` in `check_previous_phase_approved` (where `prev_file` ∈ `{"spec.md", "design.md"}` from the `phase_order` dict at line 608) | `prev_path = resolve_artifact(spec_dir, prev_file)` |
| 644 | `spec_dir / "spec.md"` in `_read_plan_identifier` | `resolve_artifact(spec_dir, "spec.md")` |
| 864 | `read_file(spec_dir / "spec.md")` in `check_dir_identifier` | `read_file(resolve_artifact(spec_dir, "spec.md"))` |
| 1049 | `spec_path = spec_dir / "spec.md"` in `validate_spec` | `spec_path = resolve_artifact(spec_dir, "spec.md")` |
| 1110 | `design_path = spec_dir / "design.md"` in `validate_design` | `design_path = resolve_artifact(spec_dir, "design.md")` |
| 1149 | `tasks_path = spec_dir / "tasks.md"` in `validate_tasks` | `tasks_path = resolve_artifact(spec_dir, "tasks.md")` |
| 1242 | `read_file(spec_dir / "spec.md")` in `validate_tasks` requirement coverage check | `read_file(resolve_artifact(spec_dir, "spec.md"))` |
| 1313 | `(candidate / "blueprint" / "PLAN.md").is_file()` in `find_project_root` | `resolve_artifact(candidate / "blueprint", "PLAN.md").is_file()` |
| 1364 | `read_file(spec_dir / "spec.md")` in `_apply_cfc_checks` | `read_file(resolve_artifact(spec_dir, "spec.md"))` |
| 1384 | `read_file(project_root / "blueprint" / "PLAN.md")` in `_apply_cfc_checks` | `read_file(resolve_artifact(project_root / "blueprint", "PLAN.md"))` |
| 1674 | `target = spec_dir / file_map[args.approve]` (the `file_map` dict is at 1673; values `"spec.md"`/`"design.md"`/`"tasks.md"`) | `target = resolve_artifact(spec_dir, file_map[args.approve])` |
| 1743 | `expected_file = spec_dir / f"{phase_key}.md" if phase_key != "spec" else spec_dir / "spec.md"` | bind `bare = "spec.md" if phase_key == "spec" else f"{phase_key}.md"`, then `expected_file = resolve_artifact(spec_dir, bare)`. (`phase_key` ∈ `{"spec","design","tasks"}`; the ternary just maps `phase_key`→bare basename — there is no f-string identity subtlety) |

*`validate_blueprint.py`:*

| Line | Current construction | Conversion |
|------|---------------------|------------|
| 449–451 | `spec_dir / "spec.md"`, `spec_dir / "design.md"`, `spec_dir / "tasks.md"` in `classify_spec` | each → `resolve_artifact(spec_dir, "spec.md")` etc. |
| 1539 | `prev_path = blueprint_dir / prev_file` where `prev_file` ∈ `{"SCOPE.md", "ARCHITECTURE.md"}` in `check_previous_phase_approved` (line 1535 gets the bare name from `phase_order` dict; 1539 builds the path) | `prev_path = resolve_artifact(blueprint_dir, prev_file)` |
| 1561 | `scope_path = blueprint_dir / "SCOPE.md"` in `validate_scope` | `scope_path = resolve_artifact(blueprint_dir, "SCOPE.md")` |
| 1659 | `arch_path = blueprint_dir / "ARCHITECTURE.md"` in `validate_architecture` | `arch_path = resolve_artifact(blueprint_dir, "ARCHITECTURE.md")` |
| 1745 | `plan_path = blueprint_dir / "PLAN.md"` in `validate_plan` | `plan_path = resolve_artifact(blueprint_dir, "PLAN.md")` |
| 2090 | `arch_path = blueprint_dir / "ARCHITECTURE.md"` in `--write-arch-config` | `arch_path = resolve_artifact(blueprint_dir, "ARCHITECTURE.md")` |
| 2127 | `target = blueprint_dir / file_map[args.approve]` | `target = resolve_artifact(blueprint_dir, file_map[args.approve])` |
| 2211 | `expected_file = blueprint_dir / phase_file_map[phase_key]` in phase loop | `expected_file = resolve_artifact(blueprint_dir, phase_file_map[phase_key])` |
| 2244 | `f"{bp_rel}/{phase_file_map[args.phase]}"` for `scan_prefix` | the pending-review key is written by `upsert_pending_entry` using the resolved file path (e.g. `blueprint/03_PLAN.md`); `scan_prefix` must use the resolved filename to match: `f"{bp_rel}/{resolve_artifact(blueprint_dir, phase_file_map[args.phase]).name}"` when `args.phase != "all"` — using the bare name here causes a key mismatch when the artifact was renamed |

*`blueprint_common.py` `is_shipped`:*

| Line | Current construction | Conversion |
|------|---------------------|------------|
| 330 | `read_file(spec_dir / "spec.md")` | `read_file(resolve_artifact(spec_dir, "spec.md"))` |
| 331 | `read_file(spec_dir / "design.md")` | `read_file(resolve_artifact(spec_dir, "design.md"))` |
| 332 | `read_file(spec_dir / "tasks.md")` | `read_file(resolve_artifact(spec_dir, "tasks.md"))` |

*`reconcile.py`:*

| Line | Current construction | Conversion |
|------|---------------------|------------|
| 573 | `master_plan_path = sibling_root / "blueprint" / "PLAN.md"` | `master_plan_path = resolve_artifact(sibling_root / "blueprint", "PLAN.md")` |
| 624 | `spec_content = blueprint_common.read_file(spec_dir / "spec.md")` | `spec_content = blueprint_common.read_file(blueprint_common.resolve_artifact(spec_dir, "spec.md"))` |
| 709 | `sibling_root / "blueprint" / "PLAN.md"` in `--print-link` mode | `blueprint_common.resolve_artifact(sibling_root / "blueprint", "PLAN.md")` |

*`render_business_brief.py`:*

| Line | Current construction | Conversion |
|------|---------------------|------------|
| 125 | `_REQUIRED_ARTIFACTS = ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md")` | unchanged (tuple of bare names); the probe at line 144 changes |
| 144 | `not (p / name).is_file()` in missing check | `not resolve_artifact(p, name).is_file()` |
| 817–819 | `_read_artifact(blueprint_path / "SCOPE.md")` etc. | `_read_artifact(resolve_artifact(blueprint_path, "SCOPE.md"))` etc. |

## Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| RI1 | A call site missed during the blast-radius sweep silently fails for prefixed artifacts; the variable/map-indexed sites (`file_map[...]`, `prev_file`, `f"{phase_key}.md"`) are the most error-prone AND evade a literal grep | High | High | The hardened grep gate adds variable-formed patterns + a negative self-test, but is NOT relied on alone for these — the named integration tests (`test_validate_*_prefixed_dir_equiv`, approve-roundtrip, render-prefixed) run the REAL validators against prefixed dirs and are the actual guard; all run as pytest before merge |
| RI2 | `render_business_brief.py` overlooked — `_REQUIRED_ARTIFACTS` probe still uses bare path construction; a fresh `blueprint/` with `01_SCOPE.md` etc. causes all three reported missing and the HTML render refuses | High | High | Explicitly in the call-site inventory (Category C); the definition-of-done grep gate covers it; a dedicated test renders a prefixed blueprint dir |
| RI3 | The `validate_blueprint.py:2244` `scan_prefix` pending-review key must be the RESOLVED relpath, not the bare string; if it stays bare and the artifact was renamed, the pending-review reconcile never fires for the prefixed file | Med | Med | Conversion in the call-site inventory explicitly states the resolved-relative-path approach; `test_renamer_pending_review_refusal` + `test_renamer_pending_entry_different_dir_no_refusal` cover the marker key logic from the renamer side; the validator-side pending key resolution is covered by an integration-style test |
| RI4 | Renamer does not roll back on first-failure; a half-renamed directory is left in a mixed state; this can confuse later operations if the WARN is also suppressed somehow | Low | Low | Mixed state triggers the WARN and the interactive offer, routing the user back to the renamer; the spec explicitly names this scenario (R7 AC) and the renamer is idempotent/re-runnable; test `test_renamer_rename_failure_halts` covers the halt behavior |
| RI5 | `.sdd/pending-review.json` is relpath-keyed; a rename without the guard orphans the obligation. Three fail-open holes: corrupt marker (`strict=False` reads empty), unresolved/symlinked dir arg, naive `startswith` prefix-bleed | Med | High | Renamer reads `strict=True` and refuses on `MarkerCorruptError` (AD8); resolves the dir + root and reuses `_key_is_contained`/`_prefix_in_scope` for boundary-safe per-file matching (AD9); refuses symlinks/escapes. Covered by `test_renamer_corrupt_marker_refuses`, `..._sibling_dir_no_bleed`, `..._per_file_key_match`, `..._symlink_artifact_refused` |
| RI6 | Over-match on `strip_artifact_prefix`: a user file `01_design.md` coexisting with the methodology artifact `02_design.md` strips to `design.md` (in KNOWN_ARTIFACTS) and triggers `ArtifactAmbiguityError` — this is the CORRECT behavior but the user may be surprised | Med | Low | `resolve_artifact` is specified to raise on multiple prefixed forms; the error message tells the user which file to remove; R6 test `test_resolve_artifact_user_01_design_coexists_with_02_design` documents and validates this |
| RI7 | Documentation drift: the ~70 prose/command-example references are only partially updated, leaving some files with bare names; inconsistency confuses practitioners reading the docs | Med | Low | R5 is a discrete tracked task in tasks.md; the R5 ACs provide concrete checks (both `panel-review.md` copies, all phase references, both SKILL.md files); a self-review checklist per touched file |
| RI8 | Dogfood rename of this repo's `specs/*/` artifacts run too early (before `tasks.md` is sealed for this feature), triggering the pending-review refusal on `specs/artifact-ordering-prefix/`; if run without a pending check, it could orphan an in-flight panel-review obligation | Low | Med | Spec explicitly mandates dogfood rename runs LAST, after all in-progress panel-review obligations are closed (Q4 decision point); R4's pending-review refusal is the safety net if ordering is violated |
| RI9 | `KNOWN_ARTIFACTS` (blueprint_common) and `PREFIX_MAP` (artifact_prefix.py) drift — an artifact added to one but not the other; the resolver tolerates it but the renamer never prefixes it (silent split) | Low | Med | `test_prefix_map_known_artifacts_symmetry` asserts `set(PREFIX_MAP.keys()) == KNOWN_ARTIFACTS` (AD10), mirroring the repo's existing arch_config/cfc_parser symmetry tests |
| RI10 | An uncaught `ArtifactAmbiguityError` at the CPD boundary (`reconcile.py`) aborts a reconcile that today degrades gracefully (a stray duplicate in a sibling repo's blueprint) | Med | Med | `reconcile.py` catches-and-degrades at each `resolve_artifact` site (Error Handling per-caller discipline); a dedicated test asserts a duplicate in a sibling repo's blueprint does not crash `--print-link` |

## Implementation Sequence

**Increment 1 — Resolution tolerance (R1, R2) + resolver-side R6 tests**

Must be fully green before Increment 2 ships. Zero observable change for existing users.

1. **C1: Add helpers to `blueprint_common.py`** — `KNOWN_ARTIFACTS`, `ArtifactAmbiguityError`, `strip_artifact_prefix`, `resolve_artifact`, `_detect_prefix_state`. All have complete tests before any call sites are converted. This is the foundational layer; everything else depends on it.

2. **C2a: Convert `archive_pass.py`** — two sites only; simplest non-validator conversion; early win verifiable by existing CLI tests.

3. **C2b: Convert `blueprint_common.is_shipped`** — three lines; pure internal change; covered by `test_is_shipped_resolves_prefixed_artifacts`.

4. **C2c: Convert `reconcile.py`** — three sites; isolated to the CPD boundary; no validator dependency.

5. **C2d: Convert `validate_spec.py`** — ~13 sites; can proceed in parallel with step 6 once C1 is done; high site count but each conversion is mechanical.

6. **C2e: Convert `validate_blueprint.py`** — ~17 sites including `classify_spec`; can proceed in parallel with step 5.

7. **C2f: Convert `render_business_brief.py`** — 4 sites; depends on C1 only; parallel with steps 5–6.

8. **Resolver-side R6 tests** — `test_artifact_prefix.py` (helper tests only), `test_archive_pass.py` additions, `test_blueprint_common.py` additions, grep gate. Full suite must pass before tagging Increment 1 complete.

**Increment 2 — Default-on emission + renamer + R7 surfacing + renamer-side R6 tests**

Depends on Increment 1 being fully green.

9. **C3: `artifact_prefix.py`** — standalone renamer; depends on `KNOWN_ARTIFACTS` and pending-review functions from C1/`blueprint_common`.

10. **C6: Default-on emission** — update all six phase references and both SKILL.md command examples to prefixed paths; update ten template files; selectively update agent prose.

11. **C4: Mixed-state WARN** — hook `_detect_prefix_state` into both validators' output; add WARN to `ValidationResult`.

12. **C5: Interactive offer prose** — update both SKILL.md files with the interactive offer behavior and suppression contract.

13. **R5: Prose sweep** — update both `panel-review.md` copies and remaining agent/template references.

14. **Renamer-side R6 tests** — `test_artifact_prefix.py` renamer tests, CI-suppression observable test.

15. **Dogfood rename** — run `artifact_prefix.py` on every `specs/*/` directory in this repo (except `artifact-ordering-prefix/` while its own `tasks.md` is still open); verify `validate_spec.py` on each renamed dir with no hash failure. Run LAST.

16. **Version bump** — increment MINOR in both `telescoping-sdd/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` in lockstep.

**Both increments ship in the same MINOR release** — the split is an internal landing order, not a release boundary.

## Open Questions

> All questions must be resolved before proceeding to the next phase.

All design questions resolved. The spec's Q1–Q5 and Q3/Q4 decision points are settled; Q1 (in-flow insertion point) is resolved above.

- [x] Q1: The exact in-flow insertion point for the interactive renamer offer within each skill's phase flow (after phase completion vs. at workflow entry) was left flexible in the spec.
  - **Resolution:** Fire the offer at workflow entry, specifically when the skill detects an existing `specs/<dir>/` or `blueprint/` directory during the initial context-assessment step (before any phase work begins). This catches practitioners who resume mid-project with a newly-upgraded plugin without requiring them to complete a phase first. Both `spec-driven-dev` and `project-blueprint` assess the working directory at entry; this is the single, consistent insertion point. If no directory is detectable at entry (fresh project with nothing on disk), the offer fires after the first artifact is emitted (since a fresh project starts uniformly prefixed, the offer will not fire then either — the mixed condition only arises from partial upgrade, which is detectable at entry).

## Panel Review

<!-- Populated by the skill across panel-review passes. archive_pass.py manages
     Trajectory and Sealed dispositions automatically; the synthesizer populates
     Latest pass detail per pass.

     Disposition vocabulary: Addressed / Deferred → tasks.md / Sealed /
     Accepted as risk / User input needed / Halt and re-scope. Sealed and
     Accepted as risk must include "Defense: <reason>" in Notes. Severity tags
     in Latest pass detail are bracketed: [HIGH] / [MED] / [LOW], optionally
     [REGRESSION].

     See SKILL.md "Panel Review section format" for the normative spec. -->

### Trajectory

| Pass | Date       | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes                           |
|------|------------|-------|-------------|-----------|----------|--------|---------------------------------|
| 1    | 2026-06-05 | 10    | 0           | 24        | 0        | 0      | tags=d0u0c10                    |
| 2    | 2026-06-05 | 0     | 0           | 4         | 0        | 0      | converged (0 HIGH); tags=d0u0c0 |

### Sealed dispositions

### Deferred dispositions

<!-- Auto-populated by archive_pass.py when a Deferred-disposed row is promoted; remains empty until first deferral. -->

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [x] Approved to proceed to next phase
- **Content Hash:** `77cb9d8bd9d4971c`
