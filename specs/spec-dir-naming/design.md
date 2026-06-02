# Design: Strengthen spec-directory filenames across both skills

**Spec:** `specs/spec-dir-naming/spec.md`

## Goals and Non-Goals

**Goals:**
- Introduce a single shared grammar module (`spec_dirname.py`) that owns all spec-directory name predicates, preventing `validate_spec.py` and `validate_blueprint.py` from drifting to independent interpretations (R1).
- Add a blocking directory↔identifier cross-check (`check_dir_identifier`) to `validate_spec.py`, running on both normal validation and all three `--approve` targets (R2).
- Update `walk_specs` and `classify_spec` in `validate_blueprint.py` to recognise the new bound form `F<n>-<slug>` and emit a `malformed-spec-dirname` WARN for bare `F<n>` or invalid-slug directories (R3).
- Update all documentation, templates, CLI help text, and the version to 1.7.0 to reflect the new naming contract (R4).
- Provide a comprehensive test suite that covers grammar correctness, `slugify` behavior, producer/consumer symmetry, doc-consistency scanning, and the CFC-fixture migration (R5).

**Non-Goals:**
- Changing the in-file `**PLAN feature identifier:**` grammar (`F<n>` | `n/a`). `PLAN_FEATURE_ID_LINE_RE` stays unchanged; the directory name must agree with it, not replace it.
- Coupling directory-name state to any content hash or persisted store. Renaming a directory has no effect on any approval, hash, or CFC cascade.
- Adding a `--force` escape hatch to bypass the directory gate on `--approve`.
- Validating any directory name except those under `specs/` (the `blueprint/` tree is out of scope).
- Supporting `python -m spec_dirname` invocation — the scripts directory is not on `sys.path` by default; file-path invocation is the only supported form.

---

## Architecture Decisions

| ID | Decision | Choice | Alternatives Rejected | Rationale | Consequences |
|----|----------|--------|-----------------------|-----------|--------------|
| AD1 | One shared grammar module | `spec_dirname.py` in `telescoping-sdd/scripts/`, imported by both validators via the existing `sys.path.append` pattern | Inline regex in each validator (status quo) | Mirrors `cfc_parser.py`'s anti-drift discipline (R1); prevents two validators from silently interpreting names differently; a single test suite can assert symmetry | Both validators must add one `from spec_dirname import ...` block; any future validator gets the grammar for free |
| AD2 | `walk_specs` WARN plumbing (DEF-01) + single classification source | Option (c) + unified `classify_dirname`: emit the `malformed-spec-dirname` WARN in `validate_plan` via `_emit_malformed_dirname_warns`; both the WARN helper (I3) and `walk_specs`' filter (I5) derive their classification from the new `classify_dirname(name) -> str` function in `spec_dirname.py`, which returns one of `"bound" \| "bare" \| "standalone" \| "invalid"`. Option (a) (thread a `result` param into `walk_specs`) and option (b) (return tuple) both require changing the signature of a function called at two sites. With `classify_dirname` as the single dispatch point, walk + warn use identical logic and cannot drift — this is the whole feature's anti-drift purpose applied to itself. | (a) thread `result` into `walk_specs`; (b) return `(list[SpecState], list[str])` tuple | `validate_plan` grows a small `_emit_malformed_dirname_warns` helper; `walk_specs` stays pure; the WARN is surfaced in validator output (R3 AC); both consumers switch on `classify_dirname`, closing the latent walk-vs-warn drift. |
| AD3 | `None`→`int` boundary in `classify_spec` | `fid = parse_feature_number(name); feature_id = fid if fid is not None else -1` sentinel adaptation inside `classify_spec` | Returning `None` from `classify_spec` and updating callers | `SpecState.feature_id` is typed `int` and used as a sort key and dict key; `None` would raise `TypeError` on sort. The `-1` sentinel is already used by the current code for non-matching names (`int(m.group(1)) if m else -1`), so the new code continues the same contract. Non-bound and invalid dirs with sentinel `-1` are filtered upstream in `validate_plan` before coverage/orphan analysis. | No change to `SpecState`, no change to callers; the `None`→`-1` mapping is entirely within `classify_spec` |
| AD4 | `slugify` empty-result contract | `slugify` raises `ValueError` with an actionable message including `repr(title)`; the CLI's `main()` catches it, prints to stderr, and exits 1 | Return a sentinel (e.g. `""`) and let the caller decide | A `ValueError` from within a library function is semantically correct ("contract violated: input produced no valid slug"). The CLI is the only external entry point for `slugify`; having the CLI catch and translate to a non-zero exit keeps the library clean and keeps the CLI's error message consistent. A sentinel `""` would silently propagate if a caller forgot to check it; a `ValueError` fails loudly. Using `repr(title)` in the `ValueError` message is a deliberate choice: `repr()` escapes control characters in the title (e.g., a newline becomes `\\n`), consistent with the `unicode_escape` approach used when embedding directory names in FAIL messages — the same spoofing concern applies to any user-controlled string embedded in a message, whether it is a title or a directory name. | `slugify` raises `ValueError` on empty result; CLI catches and exits 1 with a user-readable message on stderr; `repr()` is the chosen escaping for the title echo; all callers that need to handle empty results must `try/except ValueError` |
| AD5 | Accent-folding + input hardening in `slugify` | NFKD normalization is intentional and **lossy**: it expands superscripts/fullwidth/ligatures/fractions (`x²`→`x2`, `ﬁ`→`fi`, `½`→`12`), so distinct titles can collapse to the same slug. This is acceptable because the user reviews the slug before creating the directory. Input is capped at `title[:4096]` before normalization to avoid pathological Unicode normalization on arbitrarily large inputs. Control characters (NUL, `\x01`, newline, etc.) map via `[^a-z0-9]+`→`-` (treated as separators). Combining marks (category `Mn`) are dropped after NFKD decomposition. Truncation is at hyphen boundaries (see DM2). No third-party library. | `unicodedata.normalize('NFC', ...)` only; `unidecode` third-party library | NFKD decomposes `é` into `e` + combining acute, then dropping `Mn` characters yields `e` — correct accent folding with stdlib only, matching the spec's stdlib-only boundary. `unidecode` would add a third-party dependency, violating R1 and the Boundaries section. Characters without a decomposition (CJK, emoji) are not `Mn` and are also not `[a-z0-9]` after lowercasing, so they are replaced by hyphens then collapsed; if the entire title reduces to empty after this pipeline, `ValueError` is raised (AD4). | Pure stdlib; CJK/emoji titles raise `ValueError`; Latin-with-diacritics titles produce correct lowercase ASCII slugs; superscript/fullwidth collapse is intentional and documented |
| AD6 | `check_dir_identifier` return shape | Standalone function `check_dir_identifier(spec_dir: Path) -> ValidationResult` returning its own `ValidationResult` | Mutating a passed-in `result` | Makes the function independently testable and usable from the `--approve` path (which has no pre-existing `ValidationResult`) without constructing a dummy container. The pattern mirrors `validate_spec()` itself, which returns a `ValidationResult`. The caller (both `validate_spec()` and `main()`'s `--approve` path) merges or inspects the returned result. | `validate_spec()` merges `check_dir_identifier`'s result into its own; the `--approve` path calls `check_dir_identifier` first and exits if `result.passed` is False |
| AD7 | WARN vs FAIL asymmetry (DEF-02, DEF-03) | Blueprint validator emits `malformed-spec-dirname` WARN (not FAIL) for bare `F<n>` and invalid-slug dirs; spec validator emits `missing-slug` / `invalid-slug` / `dir-identifier-mismatch` FAILs | Same code name in both; making blueprint a FAIL | Blueprint's WARN keeps orphan detection backward-compatible for projects not yet migrated to 1.7.0 (R3 AC: bare `F<n>` still resolves, is not dropped). The spec validator is the authoring gate — it owns the authoritative contract and must FAIL to prevent silent skipping. Different validators, different severity, same root cause, different code names with shared purpose; the prose rule in `SKILL.md` explains why (R4 AC). | A directory named `F3` in a migrated project will see a WARN from the blueprint validator and a FAIL from the spec validator — consistent with their different roles |
| AD8 | Duplicate `feature_id` collision detection | When `walk_specs` returns multiple `SpecState` entries with the same non-`-1` `feature_id` (e.g., both `specs/F3-checkout-flow/` and `specs/F3/`, OR two bound dirs `specs/F3-alpha/` and `specs/F3-beta/`, map to id 3 via `parse_feature_number`), emit a `duplicate-feature-dir` WARN naming both directories. The helper `_emit_duplicate_feature_dir_warns(spec_states, result)` is called **exactly once**, at the point where the two mutually-exclusive `walk_specs` branches converge on a populated `spec_states` (after the `if/else`, before `compute_coverage` at ~L1607) — NOT per-branch, so it can neither double-emit nor miss the CFC branch. Each embedded directory name is escaped via `name.encode("unicode_escape").decode("ascii")` (same invariant as I2/I3). `state_by_id = {s.feature_id: s for s in spec_states}` retains the **last** entry in sort order for the given id (since `walk_specs` returns a `sorted(..., key=lambda s: s.feature_id)` list, the last entry wins). | Silently drop one (status quo with lenient `parse_feature_number`) | The lenient `parse_feature_number` that admits both `"F3-checkout-flow"` and `"F3"` as id 3 reintroduces the silent-skip class this feature exists to kill. Detecting the collision and warning loudly is the minimal fix: it preserves backward-compatibility (both dirs still resolve) while surfacing the ambiguity for the user to resolve. | `validate_plan` emits exactly one `duplicate-feature-dir` WARN when two walked dirs share the same non-`-1` feature id; `test_duplicate_feature_dirs_warn` (bound+bare AND bound+bound) asserts both dirs are named via quoted tokens; the tie-break (last-in-sorted-order wins `state_by_id`) is a consequence of `walk_specs`' current stable-sort-on-pre-sorted-input contract, deterministic and documented |
| AD9 (R6) | `archive_pass.py` reassembly corruption fix | Refactor the end-of-`main()` reassembly (currently four sequential in-place `replace_block`/insert calls at ~L954–988 using **pre-edit** offsets) so that: (1) the legacy `### Deferred dispositions` auto-insert runs FIRST and all section indices are recomputed against the post-auto-insert `lines` (as today); (2) all four edits (Latest-clear, Sealed-promote, Deferred-promote, Trajectory-append) are expressed UNIFORMLY as `(start, end, new_block)` replacement tuples against that same `lines` — an empty-section insertion is just `(anchor, anchor, block)` with `start == end`, collapsing the heading-anchor-vs-table-index split into one coordinate basis; (3) the four edit ranges are asserted pairwise non-overlapping; (4) a `_apply_edits(lines, edits)` helper applies them sorted by `start` DESCENDING in one pass. | Bare statement-swap (Sealed↔Deferred order); recompute-indices-after-each-splice | A bare swap doesn't fix the insert-branch coordinate-basis mismatch and is fragile to the auto-insert bookkeeping; recompute-after-splice works but re-runs `find_section` after every edit. The disjoint-sorted-edits form handles insert+replace uniformly, makes the no-overlap precondition explicit, and is provably correct: applying highest-`start` first means each applied edit only shifts lines BELOW an as-yet-unapplied edit's region, never within or above it. | All existing promotion semantics (SEAL-NN/DEF-NN id assignment, `Defense: rerouted` marker expansion, `--terminal`/`--skip`/empty-Latest paths) are preserved — reassembly refactor only; `test_archive_pass.py` gains the R6 regression matrix and its existing T3–T10 suite must stay green |

---

## Component Design

### C1: `spec_dirname.py` — Shared grammar module

**Responsibility:** Own the complete spec-directory name grammar, including predicate functions, `classify_dirname`, `parse_feature_number`, `slugify`, and the CLI entry point.

**Location:** `telescoping-sdd/scripts/spec_dirname.py`

**Key functions:**
- `is_valid_slug(s)` — checks the slug predicate: lowercase kebab `^[a-z0-9]+(-[a-z0-9]+)*$`, max 50 chars
- `is_bound_form(name)` — checks `^F([1-9]\d*)-(<valid-slug>)$` (uppercase `F`, positive no-leading-zero integer, then valid slug)
- `is_standalone_form(name)` — `is_valid_slug(name)` AND NOT `is_bound_form(name)` AND NOT bare-token (`re.fullmatch(r"F\d+", name)`)
- `classify_dirname(name)` — returns `"bound" | "bare" | "standalone" | "invalid"` (single dispatch point; see DM1)
- `parse_feature_number(name)` — lenient extraction of leading `F\d+` integer; returns `None` for non-matching names; intentionally returns an int even for bare `F<n>` tokens where `is_bound_form` is False (backward-compat clause)
- `slugify(title)` — accent-fold + normalize to kebab-case, cap input at 4096 chars, truncate result at 50-char hyphen boundary, raise `ValueError` on empty result
- `main()` — CLI entry point; dispatches `slugify` subcommand

**Status:** New file.

---

### C2: `check_dir_identifier` — Directory↔identifier cross-check (in `validate_spec.py`)

**Responsibility:** Classify a spec directory name against the in-file `**PLAN feature identifier:**` line and return a `ValidationResult` with a FAIL for every mismatch cell in the R2 matrix.

**Location:** `telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py` — new standalone function added after the existing `check_previous_phase_approved`.

**Key logic:**
1. Read `spec_dir.name` and classify via `classify_dirname` from `spec_dirname`.
2. Read `**PLAN feature identifier:**` from `spec_dir / "spec.md"` via `PLAN_FEATURE_ID_LINE_RE`. Read with `open(..., encoding="utf-8")` wrapped in `except (OSError, UnicodeDecodeError)` — the `except UnicodeDecodeError` arm maps to `cannot-cross-check` (see I2 and Error Handling).
3. Apply the decision matrix (see Interfaces I2) and emit the appropriate FAIL code. The check name is the exact string passed as the first argument to `result.add(name, passed, detail)` — e.g. `result.add("dir-identifier-mismatch", False, "<message>")`.
4. Return the `ValidationResult`.

**Call sites:**
- `validate_spec()`: calls `check_dir_identifier(spec_dir)` and merges its checks into its own result after the existing section/GWT/CFC checks. Note: `validate_spec()` has an early-return guard when `spec.md` is absent; `check_dir_identifier` runs AFTER that guard, so a missing `spec.md` does NOT trigger `cannot-cross-check` in the `validate_spec()` path — only the `--approve` path can reach `cannot-cross-check` on a missing file.
- `main()` `--approve` path (all three targets): calls `check_dir_identifier(spec_dir)` before calling `approve_document`; prints FAIL detail and exits non-zero if `not result.passed`. A `spec.md` that EXISTS but lacks the (template-mandatory) `**PLAN feature identifier:**` line IS a legitimate `cannot-cross-check` FAIL on both the normal validate and the approve path.

**Status:** New function in existing file.

---

### C3: `validate_blueprint.py` — Updated grammar consumers

**Responsibility:** Replace both inline directory-name regexes with `spec_dirname` calls, dispatch classification through `classify_dirname`, and surface `malformed-spec-dirname` and `duplicate-feature-dir` WARNs in `validate_plan`.

**Location:** `telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py`

**Changes:**
- Add `from spec_dirname import classify_dirname, parse_feature_number` to the existing shared-scripts import block. (`is_bound_form`, `is_standalone_form`, and `is_valid_slug` are not needed directly — all dispatch goes through `classify_dirname`; `parse_feature_number` is needed additionally for `classify_spec`'s `None`→`-1` adaptation.)
- `classify_spec`: replace `re.match(r"F(\d+)$", spec_dir.name)` with `parse_feature_number(spec_dir.name)` + `None`→`-1` sentinel.
- `walk_specs`: replace `re.match(r"F\d+$", entry.name)` filter; new logic dispatches on `classify_dirname(name)`: include if `"bound"` or `"bare"` (backward-compat), skip silently if `"standalone"`, skip silently if `"invalid"` (WARN emitted separately in `_emit_malformed_dirname_warns`). Update the `walk_specs` docstring to describe the bound/bare admit + standalone/invalid skip behavior (currently it states "entries not matching the `F<n>` pattern are skipped" — this must be updated to reflect the new four-category dispatch).
- Add `_emit_malformed_dirname_warns(project_root, result)` helper called from `validate_plan` at the two `walk_specs` call sites (~1595 and ~1603). The helper also dispatches on `classify_dirname`, so walk + warn are guaranteed to agree on classification.
- Add `_emit_duplicate_feature_dir_warns(spec_states, result)` helper called from `validate_plan` **exactly once at the post-`if/else` join** (after both `walk_specs` branches converge on `spec_states`, before `compute_coverage`), to detect and warn on `feature_id` collisions (AD8). It escapes each embedded directory name via `unicode_escape` (same invariant as I2/I3).

**Status:** Modified file.

---

### C4: `test_spec_dirname.py` — Grammar + symmetry test suite

**Responsibility:** Assert grammar correctness, `slugify` behavior, round-trips, and producer/consumer symmetry.

**Location:** `telescoping-sdd/scripts/tests/test_spec_dirname.py`

**Status:** New file.

---

### C5: CFC test fixture migration

**Responsibility:** Update `test_cfc_validation.py` and `test_cfc_cli_integration.py` to use bound-form `F<n>-<slug>` directory names wherever `walk_specs` is exercised, so the `malformed-spec-dirname` WARN does not break existing assertions.

**Location:**
- `telescoping-sdd/skills/project-blueprint/scripts/tests/test_cfc_validation.py` — modified
- `telescoping-sdd/skills/project-blueprint/scripts/tests/test_cfc_cli_integration.py` — modified

**Scope of migration — structural recipe:**

The primary migration target is a `for fid in (1, 2):` loop at around line 578 in `test_cfc_validation.py`, which constructs `project_root / "specs" / f"F{fid}"` via f-string interpolation. A literal find-replace of `specs/F1` would NOT touch this loop — the editor must locate it by its structural shape (the `f"F{fid}"` interpolation) and rewrite the loop to use a mapping instead:

```python
# Feature-id → bound directory name map (replace the f-string interpolation):
FEATURE_DIR_MAP = {1: "F1-alpha", 2: "F2-beta", 36: "F36-enforcement", 11: "F11-lock-order"}
# Usage: project_root / "specs" / FEATURE_DIR_MAP[fid]
```

In addition to the loop, migrate the following **literal** `tmp_path / "specs" / "F<n>"` construction sites (located by structure, NOT by the line numbers below — line numbers are advisory navigation hints only):

| Old literal construction | New construction | Containing test |
|--------------------------|-----------------|-----------------|
| `project_root / "specs" / "F1"` (~line 619) | `project_root / "specs" / "F1-alpha"` | `test_coverage_walk_partially_bound` |
| `project_root / "specs" / "F2"` (~line 628) | `project_root / "specs" / "F2-beta"` | `test_coverage_walk_partially_bound` |
| `tmp_path / "specs" / "F36"` (~lines 673, 715) | `tmp_path / "specs" / "F36-enforcement"` | `test_orphan_tag_tasks_md_*`, `test_orphan_tag_spec_md_*` |
| `tmp_path / "specs" / "F1"` (~lines 798, 828, 857, 888) | `tmp_path / "specs" / "F1-alpha"` | `test_orphan_tag_missing_cfc`, `test_orphan_tag_departed`, `test_orphan_tag_stale_content`, `test_orphan_tag_scan_empty_when_no_drift` |
| `tmp_path / "specs" / "F11"` in `test_cfc_cli_integration.py` (~line 399) | `tmp_path / "specs" / "F11-lock-order"` | `test_orphaned_stale_content_surfaced_after_cfc_drift` |

**Sites NOT migrated:**
- The `classify_spec` direct-call tests at ~lines 456–555 of `test_cfc_validation.py` use `tmp_path / "F1"` (NOT under `specs/`). These call `classify_spec` directly without going through `walk_specs`' entry filter, so they receive any directory name and the backward-compat `parse_feature_number` path continues to work. Do NOT migrate these.
- The `test_walk_specs_skips_symlinks` test (~line 725): migrate the real directory `tmp_path / "specs" / "F1"` → `tmp_path / "specs" / "F1-alpha"`. The symlinked `tmp_path / "specs" / "F99"` stays as-is — this test exercises the symlink-skip carve-out, not dir-name parsing; bare `F99` as a symlink target is correct for that purpose.

The stdout assertion `assert "F11" in proc.stdout` at ~line 427 of `test_cfc_cli_integration.py` continues to pass because `F11-lock-order` contains `F11` as a substring.

**Status:** Modified files.

---

## Data Models

### Grammar Predicates and Classifier (DM1)

The grammar predicates are pure functions in `spec_dirname.py`, not stored data. They form the normative definition. `classify_dirname` is the single dispatch point layered on top of the predicates.

| Predicate / function | Definition | Notes |
|-----------|-----------|-------|
| `is_valid_slug(s)` | `re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s) is not None` AND `len(s) <= 50` | 50-char cap on slug portion only; no minimum beyond one segment |
| `is_bound_form(name)` | `re.fullmatch(r"F([1-9]\d*)-([a-z0-9]+(-[a-z0-9]+)*)", name) is not None` AND the slug portion satisfies `is_valid_slug` | Uppercase `F` only; no leading zero; positive integer |
| `is_standalone_form(name)` | `is_valid_slug(name)` AND NOT `is_bound_form(name)` AND NOT bare-token (`re.fullmatch(r"F\d+", name)`) | `f3-racing` → standalone; `F3-racing` → bound; `F3` → neither |
| `parse_feature_number(name)` | Extracts int from `^F(\d+)` if present (bound or bare-token), else `None` | Lenient: returns `3` for `"F3"` and `7` for `"F007"` even though `is_bound_form` is `False`; returns `None` for `"F0-x"` (not valid bound, not bare token) |
| `classify_dirname(name)` | Returns `"bound"` if `is_bound_form(name)`; `"bare"` if `_BARE_TOKEN_PATTERN.fullmatch(name)` (i.e. `^F\d+$`); `"standalone"` if `is_standalone_form(name)`; else `"invalid"` | Single source of truth for walk + warn dispatch (AD2). `F0`, `F007` → `"bare"` (leniently, incl. zero/leading-zero). The public predicates `is_bound_form`/`is_standalone_form`/`is_valid_slug`/`parse_feature_number` remain as the composable building blocks. |

**`classify_dirname` category table:**

| Input | `classify_dirname` result | Notes |
|-------|--------------------------|-------|
| `"F3-checkout-flow"` | `"bound"` | valid bound form |
| `"F3"` | `"bare"` | bare token: backward-compat, lenient |
| `"F0"` | `"bare"` | bare token: zero is intentionally `"bare"` (lenient for backward-compat); earns WARN |
| `"F007"` | `"bare"` | bare token: leading-zero is intentionally `"bare"` (lenient); earns WARN |
| `"F0-x"` | `"invalid"` | not valid bound (zero), not bare token — invalid |
| `"F007-x"` | `"invalid"` | not valid bound (leading zero), not bare token — invalid |
| `"cli-notes-app"` | `"standalone"` | valid standalone |
| `"f3-racing"` | `"standalone"` | lowercase `f` → standalone (not bound) |
| `"My_Feature"` | `"invalid"` | invalid |

**Bare-token `"bare"` behavior:** `classify_dirname` returns `"bare"` for `^F\d+$` (including `F0`, `F007`). These resolve leniently in `walk_specs` (backward-compat, `feature_id` 0 or 7 respectively) AND earn a `malformed-spec-dirname` WARN from `_emit_malformed_dirname_warns` (blueprint) / `missing-slug` FAIL from `check_dir_identifier` (spec). This is intentional, not incidental.

**`parse_feature_number` return table:**

| Input | Returns | `classify_dirname` | Notes |
|-------|---------|-----------------|-------|
| `"F3-checkout-flow"` | `3` | `"bound"` | bound form |
| `"F3"` | `3` | `"bare"` | bare token: lenient |
| `"F0"` | `0` | `"bare"` | bare token: lenient (backward-compat) |
| `"F007"` | `7` | `"bare"` | bare token: lenient (backward-compat) |
| `"cli-notes-app"` | `None` | `"standalone"` | standalone |
| `"f3-racing"` | `None` | `"standalone"` | standalone (lowercase f) |
| `"My_Feature"` | `None` | `"invalid"` | invalid |
| `"F0-x"` | `None` | `"invalid"` | neither bare token nor valid bound form |
| `"F007-x"` | `None` | `"invalid"` | neither bare token nor valid bound form |

**Note on `parse_feature_number` leniency vs `classify_dirname`:** `parse_feature_number` matches `^F(\d+)` leniently on bound and bare-token forms. Validity gating **must** use `classify_dirname` or `is_bound_form`, never `parse_feature_number != None`. This distinction is stated in the module docstring and asserted by a dedicated test.

---

### DM2: `slugify` transformation pipeline

Input: any Unicode string (the feature title).

Steps (in order):
1. `title[:4096]` — cap input length before normalization to avoid pathological Unicode expansion on extremely long inputs.
2. `unicodedata.normalize('NFKD', title)` — decompose characters into base + combining marks. **This is intentionally lossy**: NFKD expands superscripts (`x²`→`x2`), fullwidth characters, ligatures (`ﬁ`→`fi`), and fractions (`½`→`12`), so distinct titles can produce the same slug. This is acceptable because the user reviews the generated slug before creating the directory.
3. Drop characters with Unicode category `Mn` (non-spacing combining marks) — this folds `é`→`e`, `ñ`→`n`, etc.
4. `.lower()` — normalize case.
5. `re.sub(r'[^a-z0-9]+', '-', s)` — replace any non-slug character run with a single `-`. Control characters (NUL, `\x01`, newline) fall into this bucket and are treated as separators, not errors.
6. `.strip('-')` — remove leading/trailing hyphens.
7. Truncate at a hyphen boundary so `len(result) <= 50`: split on `-`, accumulate full segments while total length (including joining hyphens) stays ≤ 50; if even the first segment alone exceeds 50 characters (extremely long single-word title), hard-truncate the first segment to exactly 50 characters. This guarantees a non-empty result for any title with at least one `[a-z0-9]` character.
8. If result is empty after step 6 (meaning the entire title had no `[a-z0-9]` characters after normalization — e.g. all emoji, all CJK, all punctuation): raise `ValueError("title produces an empty slug: {title!r} — provide a title with at least one Latin letter or digit")`.

Output: a string satisfying `is_valid_slug` — this invariant is unconditional.

**Edge case proof:** Step 7's hard-truncation fallback guarantees non-empty output for any input that survives step 6 non-empty. Step 8 raises only when step 6 produces empty. Therefore: step 7 can never produce empty. The `ValueError` path is exclusively triggered when the normalized title has zero `[a-z0-9]` characters.

**Additional test cases for edge behavior:**
- `slugify("x²³")` → `"x23"` (NFKD superscript expansion, then digit passthrough)
- `slugify("a\x00b")` → `"a-b"` (NUL treated as separator)
- `slugify("a" * 60)` → `"a" * 50` (60-char single segment → hard-truncated to 50; `len == 50`, satisfies `is_valid_slug`)

---

### DM3: `check_dir_identifier` decision matrix

The function reads two inputs — directory basename (classified via `classify_dirname`) and the in-file identifier from `spec.md` — and applies this matrix:

| Directory form | `classify_dirname` | In-file identifier | Outcome | Check name |
|----------------|--------------------|---------|------|------------|
| Bound `F<n>-<slug>` | `"bound"` | `` `F<n>` `` (n matches) | PASS | — |
| Bound `F<n>-<slug>` | `"bound"` | `` `F<m>` `` (n ≠ m) | FAIL | `dir-identifier-mismatch` |
| Bound `F<n>-<slug>` | `"bound"` | `` `n/a` `` | FAIL | `dir-identifier-mismatch` (decision-criterion message: see I2) |
| Standalone slug | `"standalone"` | `` `n/a` `` | PASS | — |
| Standalone slug | `"standalone"` | `` `F<n>` `` | FAIL | `dir-identifier-mismatch` (symmetric message: see I2) |
| Bare token `F<n>` | `"bare"` | Any | FAIL | `missing-slug` |
| Invalid name | `"invalid"` | Any | FAIL | `invalid-slug` |
| Any form | — | `spec.md` absent or identifier line missing | FAIL | `cannot-cross-check` |

**Check name contract:** The check name IS the `name` argument to `result.add(name, passed, detail)`. Matrix-cell (unit) tests assert on the exact check name. CLI/subprocess tests assert on message text via stdout substring.

**`cannot-cross-check` boundary:** In `validate_spec()`, `check_dir_identifier` runs AFTER the existing `spec.md`-exists early-return guard, so a missing `spec.md` does NOT reach `check_dir_identifier` via the `validate_spec()` path. In the `--approve` path (design, tasks), there is no such guard — a `spec.md` that exists but lacks the (template-mandatory) `**PLAN feature identifier:**` line is a legitimate `cannot-cross-check` FAIL. This is the intended behavior: the out-of-order/corrupted case is caught, while the normal `validate_spec()` early-return is preserved.

Every FAIL message:
- Names the offending directory via the `{escaped_name}` substitution point (the raw directory name escaped via `name.encode("unicode_escape").decode("ascii")`) to prevent control characters in directory names from spoofing the validator's stdout.
- States the exact rename required or the decision criterion (not just the two mechanical options).
- For `missing-slug` and `invalid-slug`: points to the slug generator CLI.
- Includes the hash-safety reassurance: "renaming a spec directory does not invalidate any existing approval or content hash".

### C6 (R6): `archive_pass.py` reassembly fix

**Responsibility:** Eliminate the multi-section reassembly corruption (R6) — when one pass promotes a new `Sealed` AND (re)writes `Deferred`, the pre-edit offsets used by the sequential in-place edits go stale and duplicate `[DEF-NN]` entries / clobber headings.

**Location:** `telescoping-sdd/scripts/archive_pass.py`, the reassembly block near the end of `main()` (~L954–988), plus a new module-level helper `_apply_edits`.

**Shape (per AD9):** after the existing auto-insert + index recomputation, collect the (up to four) section rewrites as disjoint `(start, end, new_block)` tuples against the post-auto-insert `lines`, assert pairwise non-overlap, and apply them via `_apply_edits` sorted by `start` descending. This is a **refactor**, not a new code path: the values that go into each `new_block` (cleared Latest table, promoted Sealed entries with their `[SEAL-NN]` ids, promoted Deferred entries with `[DEF-NN]` ids and `Defense: rerouted` expansion, appended Trajectory row) are computed exactly as today; only the *application* changes from sequential-with-stale-offsets to sorted-descending.

**Status:** Modified file (refactor of existing block + new helper).

---

## Interfaces

### I1: `spec_dirname.py` public API

```python
"""Shared spec-directory name grammar.

Owned by this module; imported by validate_spec.py and validate_blueprint.py
via the existing sys.path.append(_SHARED_SCRIPTS) pattern. Stdlib-only.

IMPORTANT: parse_feature_number is intentionally lenient — it returns an int
for bare F<n> tokens even though is_bound_form("F<n>") is False. Validity
gating MUST use classify_dirname or is_bound_form, never
`parse_feature_number(name) is not None`.
Bare-token leniency exists solely for backward-compatible walk_specs behaviour
in validate_blueprint.py.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# ---------------------------------------------------------------------------
# Compiled patterns (module-level, compiled once)
# ---------------------------------------------------------------------------

# Valid slug: lowercase kebab, max 50 chars.
# Used as component in bound-form regex below and as a standalone predicate.
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Bound form: F<positive-no-leading-zero>-<valid-slug>.
# Slug portion length is checked in is_bound_form (not baked into the regex,
# to keep the 50-char cap in one place: is_valid_slug).
_BOUND_PATTERN = re.compile(r"^F([1-9]\d*)-([a-z0-9]+(?:-[a-z0-9]+)*)$")

# Bare token: F followed by digits, end of string (no slug).
# Used by is_standalone_form (to exclude bare tokens from standalone),
# by classify_dirname ("bare" branch), and by parse_feature_number
# (lenient bare-token extraction for backward compat).
_BARE_TOKEN_PATTERN = re.compile(r"^F(\d+)$")

_SLUG_MAX = 50
_TITLE_MAX = 4096  # cap before NFKD to avoid pathological normalization


def is_valid_slug(s: str) -> bool:
    """Return True if s is a valid slug: lowercase kebab, 1–50 chars."""
    ...


def is_bound_form(name: str) -> bool:
    """Return True if name matches the bound form F<n>-<slug>.

    False for bare tokens ("F3"), lowercase-f forms ("f3-racing"),
    zero-prefixed ("F007-x"), or zero ("F0-x").
    """
    ...


def is_standalone_form(name: str) -> bool:
    """Return True if name is a valid standalone slug (not bound, not bare-token).

    Examples: "cli-notes-app" → True, "f3-racing" → True,
    "F3-checkout-flow" → False, "F3" → False.
    """
    ...


def classify_dirname(name: str) -> str:
    """Classify a spec directory basename into one of four categories.

    Returns:
        "bound"      if is_bound_form(name) is True
        "bare"       if name matches ^F\d+$ (bare token, incl. F0, F007)
        "standalone" if is_standalone_form(name) is True
        "invalid"    otherwise

    This is the single dispatch point for all consumers (walk_specs filter,
    _emit_malformed_dirname_warns, check_dir_identifier). Using it everywhere
    prevents walk vs. warn classification drift — the feature's own anti-drift
    principle applied to itself.

    Args:
        name: directory basename as a str (callers pass entry.name or
              spec_dir.name — both are always str). The function never raises.

    Returns:
        One of the four string literals above. Never raises.
    """
    ...


def parse_feature_number(name: str) -> Optional[int]:
    """Return the integer feature number from a bound or bare-token name.

    Lenient by design: returns an int for bare-token forms ("F3" → 3) even
    though is_bound_form("F3") is False. Does NOT extend to arbitrary
    F<digits>-prefixed strings like "F0-slug" (which is neither a valid bound
    form nor a bare token).

    Args:
        name: directory basename.

    Returns:
        The int from F<n> if name is a bound form or bare token, else None.
        Specifically: 3 for "F3-checkout-flow", 3 for "F3",
        None for "cli-notes-app", None for "f3-racing", None for "My_Feature",
        None for "F0-slug" (not a valid bound form, not a bare token).

    Raises:
        Nothing — returns None on any non-matching input.
    """
    ...


def slugify(title: str) -> str:
    """Convert a feature title to a lowercase kebab-case slug.

    Pipeline:
      1. Cap input at 4096 chars (title[:4096]) before normalization.
      2. NFKD normalization + drop Mn combining marks (accent folding).
         LOSSY: superscripts/fullwidth/ligatures/fractions are expanded
         (x²→x2, ﬁ→fi), so distinct titles can produce the same slug.
      3. Lowercase.
      4. Replace non-[a-z0-9] runs (incl. control chars) with a single hyphen.
      5. Strip leading/trailing hyphens.
      6. Truncate at a hyphen boundary so len(result) <= 50.
         If the first segment alone exceeds 50 chars, hard-truncate to 50.
      7. Raise ValueError if result is empty (no [a-z0-9] chars in title).

    Args:
        title: human-readable feature title (e.g. "Checkout Flow (v2)").

    Returns:
        A non-empty string satisfying is_valid_slug.

    Raises:
        ValueError: if the title reduces to an empty slug after normalization.
            The message includes repr(title) to escape control characters in
            the title — the same spoofing concern that applies to directory
            names applies here. repr() is the chosen escaping for title echo
            (consistent with unicode_escape for directory names in FAIL
            messages).
    """
    ...


def main() -> None:
    """CLI entry point.

    Usage:
        python telescoping-sdd/scripts/spec_dirname.py slugify "Feature Title"

    Subcommands:
        slugify <title>  — print the slug to stdout and exit 0.

    Exit codes:
        0   — success
        1   — slugify raised ValueError (empty result); message on stderr
        2   — wrong number of arguments or unknown subcommand

    Notes:
        Invoked by file path, not python -m, because telescoping-sdd/scripts/
        is not on sys.path by default.
    """
    ...
```

**Contracts:**
- `is_valid_slug` is the single authoritative length check; `slugify` guarantees its output satisfies `is_valid_slug` unconditionally.
- `classify_dirname` is the single dispatch point for all consumers; callers must not re-implement classification logic.
- `is_bound_form` implies `parse_feature_number` returns a positive int — but the converse is NOT true (lenient bare-token case).
- `slugify` never returns an empty or invalid string; it raises `ValueError` instead. `repr(title)` is the deliberate escaping used in the `ValueError` message (see AD4).
- All functions are pure (no I/O, no side effects) except `main`.

---

### I2: `check_dir_identifier` (in `validate_spec.py`)

```python
def check_dir_identifier(spec_dir: Path) -> ValidationResult:
    """Cross-check the spec directory name against the in-file PLAN feature identifier.

    Reads spec_dir.name and the **PLAN feature identifier:** line from
    spec_dir/spec.md (via PLAN_FEATURE_ID_LINE_RE). Classifies the directory
    name using classify_dirname from spec_dirname. Applies the decision matrix.

    Emits at most one FAIL check per call. The result has .passed == True iff
    no FAIL was added.

    Check names (the `name` arg to result.add):
      "dir-identifier-mismatch" — dir/identifier pair are internally inconsistent
      "missing-slug"            — bare-token dir (F<n>)
      "invalid-slug"            — dir name is neither bound, bare, nor standalone
      "cannot-cross-check"      — spec.md absent or no readable identifier line

    Note on cannot-cross-check: validate_spec() has a prior early-return guard
    for missing spec.md, so cannot-cross-check only fires there when the file
    exists but lacks the **PLAN feature identifier:** line. The --approve path
    has no such guard, so cannot-cross-check fires for both missing files and
    missing identifier lines.

    Args:
        spec_dir: absolute Path to the spec directory being validated or approved.

    Returns:
        A ValidationResult with zero or one check entries.

    Raises:
        Nothing — OSError and UnicodeDecodeError from reading spec.md both
        produce a 'cannot-cross-check' FAIL. spec.md is read with
        open(..., encoding="utf-8") wrapped in except (OSError, UnicodeDecodeError).
        A non-UTF-8 file raises UnicodeDecodeError → cannot-cross-check (the
        file is unreadable, not garbage-substituted). errors="replace" is NOT
        used: under errors="replace" the \\xff byte becomes the replacement
        character and the identifier line might still parse, producing a
        wrong result instead of cannot-cross-check. The except arm is the
        canonical path for non-UTF-8 files.

    Side effects:
        None — reads spec.md but does not modify any file.
        Note: classify_spec's pre-existing read_file I/O contract is unchanged
        and intentionally so — check_dir_identifier only reads spec.md; its
        input set under the new dirname filter is narrower-or-equal to before,
        and no new I/O surface is introduced.
    """
    ...
```

**I/O error guard:** `Path.open()` / `Path.read_text()` can raise `UnicodeDecodeError` (a `ValueError`, not an `OSError`) on a non-UTF-8 `spec.md`. The guard MUST be `except (OSError, UnicodeDecodeError)`. The `errors="replace"` alternative is NOT acceptable: under `errors="replace"`, the `\xff` byte is replaced with `U+FFFD` and the identifier line may still parse (producing garbage output), which contradicts `test_check_dir_identifier_non_utf8_spec_md` that asserts `cannot-cross-check`. Pin to the `except` arm so the test is deterministic.

**Name embedding:** When embedding the user-controlled `spec_dir.name` into any FAIL message, the raw name MUST be escaped via `name.encode("unicode_escape").decode("ascii")` before inclusion. This prevents control characters (e.g. a newline in a directory name) from spoofing the validator's stdout output. The FAIL message templates use `{escaped_name}` as the substitution point; the implementation substitutes the unicode-escaped value at runtime — it does NOT interpolate the raw `spec_dir.name` directly.

**FAIL message templates (showing `{escaped_name}` and `{n}`, `{m}`, `{slug}` substitution points):**

`dir-identifier-mismatch` — bound dir + `n/a` identifier:
```
spec directory '{escaped_name}' uses the bound form (implying PLAN feature F{n}) but
the in-file identifier is 'n/a'. Decision: if this feature is part of a
blueprint/PLAN.md, set the in-file identifier to `F{n}`; if it is standalone, rename
the directory to the bare slug '{slug}'. Renaming a spec directory does not
invalidate any existing approval or content hash.
```
*(where `{n}` is the feature number from the bound dir name and `{slug}` is the slug portion)*

`dir-identifier-mismatch` — standalone dir + `F<n>` identifier (symmetric):
```
spec directory '{escaped_name}' uses the standalone form but the in-file identifier
is 'F{n}'. Decision: if this feature is part of a blueprint/PLAN.md, rename the
directory to 'F{n}-{escaped_name}'; if it is standalone, change the in-file identifier
to `n/a`. Renaming a spec directory does not invalidate any existing approval or
content hash.
```

`dir-identifier-mismatch` — bound `F<n>` dir + `F<m>` identifier (n ≠ m):
```
spec directory '{escaped_name}' implies feature F{n} but the in-file identifier is
'F{m}'. Rename the directory to 'F{m}-{slug}' or correct the in-file identifier.
Renaming a spec directory does not invalidate any existing approval or content hash.
```

`missing-slug` — bare token `F<n>`:
```
spec directory '{escaped_name}' is missing a slug. Rename it to '{escaped_name}-<slug>' (e.g.
'{escaped_name}-checkout-flow'). To generate a slug from the feature title, run:
  python telescoping-sdd/scripts/spec_dirname.py slugify "<title>"
Renaming a spec directory does not invalidate any existing approval or content hash.
```

`invalid-slug` — invalid dir name:
```
spec directory '{escaped_name}' is not a valid name. Valid forms are 'F<n>-<slug>'
(bound, e.g. 'F3-checkout-flow') or '<slug>' (standalone, e.g. 'cli-notes-app')
where <slug> is lowercase kebab-case, max 50 characters. To generate a slug, run:
  python telescoping-sdd/scripts/spec_dirname.py slugify "<title>"
Renaming a spec directory does not invalidate any existing approval or content hash.
```

`cannot-cross-check`:
```
cannot read the PLAN feature identifier from spec.md — approve spec first (or
ensure spec.md has a '**PLAN feature identifier:**' line).
```

**Test assertion pattern:** Matrix-cell tests assert `check[0] == "dir-identifier-mismatch"` (the exact check name at index 0 of the tuple), `check[1] == Severity.FAIL` (index 1), and optionally inspect `check[2]` (the detail string) for key substrings. Tests do NOT assert on `str(c)` substring — they assert directly on the tuple fields.

---

### I3: `_emit_malformed_dirname_warns` (in `validate_blueprint.py`)

```python
def _emit_malformed_dirname_warns(project_root: Path, result: ValidationResult) -> None:
    """Walk specs/ and emit a malformed-spec-dirname WARN for each invalid entry.

    Dispatches on classify_dirname — the same function used by walk_specs' filter
    in I5 — guaranteeing that walk and warn agree on every directory's category.
    Emits a WARN for "bare" (F<n>, including F0, F007) and "invalid" (e.g.
    My_Feature) categories. Standalone and bound directories are silent-skipped.

    Called from validate_plan at both walk_specs call sites. Emits a WARN (not
    FAIL) so backward-compatible bare-token directories are preserved in the
    coverage map while still surfacing the migration prompt.

    Args:
        project_root: project root directory (specs/ lives here).
        result: the ValidationResult owned by validate_plan; WARN entries
                are added in-place.

    Returns:
        None

    Raises:
        Nothing — returns immediately if specs/ does not exist; skips
        unreadable or symlinked entries silently.

    Note:
        The helper guards the specs/ existence check internally, so it is
        safe to call unconditionally at both walk_specs call sites in
        validate_plan (~1595 and ~1603) without duplicating the is_dir check.
    """
    ...
```

**WARN message format (check name: `malformed-spec-dirname`, substitution via `{escaped_name}`):**

The raw entry name is escaped via `entry.name.encode("unicode_escape").decode("ascii")` before embedding in WARN message text (same spoofing guard as I2). The templates below use `{escaped_name}` as the substitution point.

Bare `F<n>` token (including `F0`, `F007`):
```
malformed-spec-dirname: 'specs/{escaped_name}' uses the old bare-token form. Rename to
'{escaped_name}-<slug>' (e.g. '{escaped_name}-checkout-flow'). To generate a slug, run:
  python telescoping-sdd/scripts/spec_dirname.py slugify "<title>"
Renaming does not invalidate any existing approval or content hash.
```

Invalid slug (e.g. `My_Feature`):
```
malformed-spec-dirname: 'specs/{escaped_name}' is not a valid spec directory name
and will not be included in feature resolution. Rename to 'F<n>-<slug>' (if
bound to a PLAN feature) or '<slug>' (standalone). To generate a slug, run:
  python telescoping-sdd/scripts/spec_dirname.py slugify "<title>"
```

**Test assertion pattern:** Tests assert on `check[0]` (name) and inspect `check[2]` (detail) directly — NOT on `str(c)` substring.

---

### I4: `classify_spec` adaptation (in `validate_blueprint.py`)

The only change to `classify_spec` is the first two lines of its body:

```python
# Before (to be removed):
m = re.match(r"F(\d+)$", spec_dir.name)
feature_id = int(m.group(1)) if m else -1

# After:
fid = parse_feature_number(spec_dir.name)
feature_id = fid if fid is not None else -1
```

**Contracts preserved:**
- `feature_id` is always an `int` (never `None`).
- For a bound-form name `F3-checkout-flow`, `parse_feature_number` returns `3` → `feature_id = 3`.
- For a bare-token name `F3`, `parse_feature_number` returns `3` → `feature_id = 3` (backward-compat).
- For a standalone or invalid name, `parse_feature_number` returns `None` → `feature_id = -1` (same as before).
- The `-1` sentinel is filtered in `validate_plan` before coverage/orphan analysis via the same mechanism already in place (entries with `feature_id == -1` are not in any participating-feature set).
- `classify_spec`'s pre-existing `read_file` I/O contract is unchanged and intentionally so — the function's input set under the new `walk_specs` filter is narrower-or-equal (only bound and bare dirs reach it), and no new I/O surface is introduced.

---

### I5: `walk_specs` updated filter (in `validate_blueprint.py`)

```python
# Before (to be removed):
if not re.match(r"F\d+$", entry.name):
    continue

# After:
category = classify_dirname(entry.name)
if category == "standalone":
    continue  # silent skip — correct behavior, not a warning
if category == "invalid":
    continue  # invalid form — WARN emitted separately in validate_plan
# Reaches here for: "bound" (F<n>-<slug>) and "bare" (F<n>) — backward-compat
```

This means `walk_specs` returns entries for bound-form and bare-token directories (backward-compat for the latter), excludes standalone slugs silently, and excludes invalid names silently (warned from `validate_plan` via `_emit_malformed_dirname_warns`). Symlink skip (existing `if entry.is_symlink(): continue`) is unchanged and runs before any name check.

**`walk_specs` docstring update (in scope for I5):** The current docstring states "entries not matching the `F<n>` pattern are skipped". This must be updated to describe the new four-category dispatch: bound (`F<n>-<slug>`) and bare (`F<n>`) entries are admitted (bare for backward-compat), standalone entries are skipped silently (correct behavior, not a WARN), and invalid entries are skipped silently (WARN emitted separately by `_emit_malformed_dirname_warns` in `validate_plan`). Symlinks remain skipped unconditionally before name classification.

### I6 (R6): `_apply_edits` helper in `archive_pass.py`

```python
def _apply_edits(lines: list[str], edits: list[tuple[int, int, list[str]]]) -> list[str]:
    """Apply a set of disjoint line-range replacements to `lines`.

    Each edit is (start, end, new_block): replace lines[start:end] with new_block.
    An insertion is expressed as start == end (replace an empty range).

    Edits MUST be pairwise non-overlapping (asserted). They are applied sorted by
    `start` DESCENDING, so each applied edit only shifts lines below an as-yet-
    unapplied edit's range — every edit's (start, end) stays valid against the
    original `lines` coordinate basis. Returns the new list; does not mutate input.

    Raises:
        AssertionError: if any two edit ranges overlap (a programming error — the
        four panel sections occupy disjoint spans by construction).
    """
```

The reassembly in `main()` builds **1–4** `(start, end, new_block)` tuples against the post-auto-insert `lines` and calls `_apply_edits` once, replacing the sequential in-place `replace_block`/insert calls. Pure, no I/O.

**Scope and preconditions (per architect pass-2):**
- **Conditional assembly.** Each tuple is appended ONLY under its existing guard — `latest_to_clear`, `new_seals`, `new_defs and d_start is not None`, and the always-present Trajectory append. A `--skip` or converged-empty pass therefore yields as few as one edit (Trajectory only); the refactor must NOT always construct four (that would clear a Latest table a skip pass should preserve). The empty-Latest early-exit (`sys.exit` before reassembly) path is untouched.
- **Refactor boundary.** Only the application region (~L954–988) changes, plus the new helper. All upstream computation of `new_seals`/`new_defs`/`new_traj_row` (SEAL/DEF id assignment, `Defense: rerouted` marker expansion, the DEF-not-found `EXIT_FORMAT_VIOLATION`) at ~L836–935 is unchanged and out of scope.
- **Auto-insert sequencing.** The legacy `### Deferred dispositions` auto-insert and its manual `+3` index adjustments run first, UNCHANGED; tuples are built from the already-correct post-insert indices (`t_start`, `s_start`, `d_start`/`d_end` from the re-find, `l_start`/`l_end`) — no redundant `find_section` re-scan of Trajectory/Sealed is added.
- **Half-open convention.** Every tuple is `[start, end)`; the populated Sealed/Deferred branches carry their existing `last = ...["line_idx"] + 1` exclusive end; insertions are `start == end`. The now-redundant `new_lines = lines[:]` copy is dropped (the helper returns a fresh list).
- **Non-overlap assertion** is computed over the actual tuple integers, not assumed "by construction" — a negative unit test asserts it fires on a synthetic overlapping edit list.

---

## Error Handling

**Strategy:** Exceptions for programmer errors; FAIL/WARN entries in `ValidationResult` for user-facing validation failures; `sys.exit` in CLI entry points.

| Error condition | Exception / mechanism | Metadata | Where caught |
|----------------|-----------------------|----------|--------------|
| `slugify` receives a title producing empty slug | `ValueError` with actionable message including `repr(title)` | `repr(title)` escapes control chars in title (deliberate, consistent with unicode_escape for dir names — see AD4) | `spec_dirname.main()` — printed to stderr, exit 1 |
| `slugify` called with no argument from CLI | `main()` prints usage to stderr | — | `main()` — exit 2 |
| `check_dir_identifier` cannot read `spec.md` (OSError) | `cannot-cross-check` FAIL in result | message: "approve spec first" | result returned to caller; no exception propagates |
| `check_dir_identifier` encounters non-UTF-8 `spec.md` (UnicodeDecodeError) | `cannot-cross-check` FAIL in result | same — non-UTF-8 file is unreadable, not garbage-substituted | caught by `except (OSError, UnicodeDecodeError)` in `check_dir_identifier`; `errors="replace"` is NOT used (would allow the identifier line to parse garbage, contradicting the test) |
| `check_dir_identifier` encounters unreadable identifier line (line exists but no match) | `cannot-cross-check` FAIL | same | same |
| `check_dir_identifier` called with directory name containing control characters | Embedded name is escaped via `name.encode("unicode_escape").decode("ascii")` before inclusion in FAIL message | — | within `check_dir_identifier` — never raises |
| `_emit_malformed_dirname_warns` encounters OSError on `specs/` iteration | skipped silently | — | within the helper |
| `classify_spec` receives non-bound/non-bare name | `None`→`-1` sentinel, no exception | — | within `classify_spec` |
| `approve_document` called on a dir failing cross-check | `sys.exit(1)` after printing FAIL details | — | `main()` in `validate_spec.py` |
| Two spec dirs share the same non-`-1` `feature_id` (duplicate collision) | `duplicate-feature-dir` WARN in result (AD8) | names both colliding directories in the WARN detail, each escaped via `name.encode("unicode_escape").decode("ascii")` (same invariant as I2/I3) | `_emit_duplicate_feature_dir_warns` in `validate_plan`, called once at the post-`if/else` join; no exception propagates |

**Logging:** No `logging` module usage — these are CLI tools that write to stdout/stderr directly. Error messages go to stderr for `spec_dirname.main()`; FAIL/WARN rows go to stdout via the `ValidationResult` print loop.

**Unhandled paths:** `check_dir_identifier` must never raise. The guard `except (OSError, UnicodeDecodeError)` covers all I/O error paths. `errors="replace"` is explicitly NOT an acceptable alternative (see above).

---

## Testing Strategy

**Framework:** pytest, run via `.venv/bin/pytest telescoping-sdd/ -q`.

**Test file:** `telescoping-sdd/scripts/tests/test_spec_dirname.py`

**Coverage expectation:** Every public function in `spec_dirname.py` has at least one happy-path test and at least one error-path test. Every cell in the `check_dir_identifier` decision matrix (DM3) has a dedicated test asserting on the exact check `name` via tuple field access (`check[0]`, `check[1]`, `check[2]`), NOT on `str(c)` substring. CLI/subprocess tests assert on message text via stdout substring. CLI exit codes are asserted precisely (exit 1 for empty-slug `ValueError`, exit 2 for wrong-argument-count/unknown-subcommand).

**R4 CLI-help edit verification:** R4 requires updating the `specs/my-feature/` literals in `validate_spec.py` (docstring ~L20-22, argparse epilog ~L1039, help ~L1044). These literals are NOT in `DOC_INVENTORY` (since `validate_spec.py` is a script, not a doc file) and `STALE_PLACEHOLDER_RE` matches `specs/<feature(-name)?>/` angle-bracket patterns, not the literal `specs/my-feature/`. A dedicated test `test_validate_spec_py_no_my_feature_literal` scans the `validate_spec.py` source for the literal substring `specs/my-feature/` and asserts zero matches. The new bound-form example (e.g. `specs/F1-checkout-flow/`) contains no `my-feature` token, so the test passes after the R4 edit and fails if the edit was missed.

---

### Grammar table tests

`test_is_valid_slug` — parametrize over:

| Input | Expected |
|-------|----------|
| `"checkout-flow"` | `True` |
| `"cli-notes-app"` | `True` |
| `"2fa-login"` | `True` |
| `"123"` | `True` |
| `"a"` (single char) | `True` |
| `"a" * 50` | `True` (boundary) |
| `"a" * 51` | `False` (boundary) |
| `"CheckoutFlow"` | `False` (uppercase) |
| `"checkout_flow"` | `False` (underscore) |
| `""` | `False` (empty) |
| `"checkout--flow"` | `False` (consecutive hyphens, fails `[a-z0-9]+` segment rule) |
| `"-checkout"` | `False` (leading hyphen) |
| `"checkout-"` | `False` (trailing hyphen) |

`test_is_bound_form` — parametrize over:

| Input | Expected |
|-------|----------|
| `"F3-checkout-flow"` | `True` |
| `"F1-a"` | `True` |
| `"F10-slug"` | `True` |
| `"F3"` | `False` (bare token) |
| `"f3-racing"` | `False` (lowercase f) |
| `"F0-x"` | `False` (zero) |
| `"F007-x"` | `False` (leading zero) |
| `"F3-" + "a"*50` | `True` (slug at exact cap) |
| `"F3-" + "a"*51` | `False` (slug exceeds cap) |
| `"My_Feature"` | `False` |

`test_is_standalone_form` — parametrize over:

| Input | Expected |
|-------|----------|
| `"cli-notes-app"` | `True` |
| `"f3-racing"` | `True` |
| `"2fa-login"` | `True` |
| `"F3-checkout-flow"` | `False` (bound) |
| `"F3"` | `False` (bare token) |
| `"My_Feature"` | `False` (invalid) |

`test_classify_dirname` — parametrize over the full table in DM1, including:
- `"F0"` → `"bare"` (intentional, not `"invalid"`)
- `"F007"` → `"bare"` (intentional)
- `"F0-x"` → `"invalid"` (not bare token, not valid bound)
- `"F007-x"` → `"invalid"` (not bare token, not valid bound)

`test_parse_feature_number` — parametrize over the table in DM1.

**Leniency vs validity assertion** (`test_parse_feature_number_leniency_documented`):
```python
assert spec_dirname.parse_feature_number("F3") == 3
assert not spec_dirname.is_bound_form("F3")
assert spec_dirname.classify_dirname("F3") == "bare"
# Documents: bare-token leniency must not be mistaken for validity.
```

---

### `slugify` tests

`test_slugify_basic_cases` — parametrize:

| Input | Expected output |
|-------|----------------|
| `"Checkout Flow (v2)"` | `"checkout-flow-v2"` |
| `"My Feature Title"` | `"my-feature-title"` |
| `"  leading spaces  "` | `"leading-spaces"` |
| `"a---b"` | `"a-b"` |

`test_slugify_accent_folding`:
- `"Café"` → `"cafe"`
- `"Über Feature"` → `"uber-feature"`
- `"señor"` → `"senor"`

`test_slugify_nfkd_expansion` — lossy-decomposition cases:
- `slugify("x²³")` → `"x23"` (NFKD decomposes superscripts ²→2, ³→3)
- `slugify("ﬁrst")` → `"first"` (NFKD decomposes ligature ﬁ→fi)

`test_slugify_control_character` — control chars treated as separators:
- `slugify("a\x00b")` → `"a-b"` (NUL treated as separator)

`test_slugify_empty_result_raises_value_error`:
- `"!!!"` raises `ValueError`
- `"🚀"` raises `ValueError`
- `"   "` raises `ValueError`

`test_slugify_truncation_at_hyphen_boundary`:
- Input: `"alpha-bravo-charlie-delta-echo-foxtrot-golf-hotel-india"` (a title that slugifies to 53 chars: `"alpha-bravo-charlie-delta-echo-foxtrot-golf-hotel-india"` is 55 chars → expect `"alpha-bravo-charlie-delta-echo-foxtrot-golf-hotel"` which is 49 chars and ends at a segment boundary).
- Assert `len(result) <= 50` and `result == "alpha-bravo-charlie-delta-echo-foxtrot-golf-hotel"`.
- Assert `is_valid_slug(result)` is `True`.

`test_slugify_single_segment_hard_truncation`:
- Input: `"a" * 60` (a single 60-char run of `a`).
- Expected: `"a" * 50` (hard-truncated to 50 since the single segment exceeds the cap).
- Assert `len(result) == 50` and `result == "a" * 50` and `is_valid_slug(result)` is `True`.
- This exercises the single-segment-over-50 hard-truncation path, which is distinct from the natural-hyphen-boundary truncation path.

`test_slugify_output_always_satisfies_is_valid_slug`:
- For all non-empty-result inputs above, `is_valid_slug(slugify(input))` is `True`.

`test_slugify_cli_subcommand`:
- `subprocess.run([sys.executable, str(SPEC_DIRNAME_PATH), "slugify", "My Feature"])` exits **0** and stdout contains `"my-feature"`.
- `subprocess.run([sys.executable, str(SPEC_DIRNAME_PATH), "slugify", "!!!"])` exits **1** (ValueError from empty slug) and stderr is non-empty.
- `subprocess.run([sys.executable, str(SPEC_DIRNAME_PATH), "slugify"])` exits **2** (wrong argument count), NOT 1.
- `subprocess.run([sys.executable, str(SPEC_DIRNAME_PATH), "badcmd", "x"])` exits **2** (unknown subcommand), NOT 1.

---

### `check_dir_identifier` matrix tests

`test_check_dir_identifier_matrix` — one test per DM3 cell, each asserting:
- The returned `ValidationResult.passed` value.
- The exact check `name` (first arg to `result.add`) when a FAIL is expected, by accessing `result.checks[0][0]` (the tuple's first element): `"dir-identifier-mismatch"`, `"missing-slug"`, `"invalid-slug"`, or `"cannot-cross-check"`. Tests do NOT assert on `str(c)` substring — they access tuple fields directly.

Additional matrix tests:
- `test_check_dir_identifier_hand_typed_long_slug` — a hand-typed bound dir whose slug portion exceeds 50 chars (e.g. `F3-this-slug-is-far-longer-than-the-fifty-character-hard-cap`) → assert `result.checks[0][0] == "invalid-slug"` (exercises the `is_bound_form` length-gate path, distinct from the bad-char path).
- `test_check_dir_identifier_non_utf8_spec_md` — a `spec.md` written with an invalid UTF-8 byte (e.g. `b"**PLAN feature identifier:** \xff\n"`) → assert `result.checks[0][0] == "cannot-cross-check"` and no exception raised (guards the `UnicodeDecodeError → cannot-cross-check` path; confirms `errors="replace"` is NOT used, since `errors="replace"` would allow the line to parse as garbage and return a different check name).
- `test_check_dir_identifier_missing_identifier_line` — a `spec.md` that EXISTS but has no `**PLAN feature identifier:**` line → assert `result.checks[0][0] == "cannot-cross-check"`.

**`test_check_dir_identifier_control_char_in_dirname`** — guards the stdout-spoofing fix:
- Either (a) create a spec directory whose name contains a newline or NUL byte if the OS permits (Linux allows `\n` in filenames; macOS does not allow `\0` but does allow `\n` in some contexts), or (b) unit-test the message-formatting helper directly by calling `check_dir_identifier` with a mock/patched `spec_dir` whose `.name` attribute is set to `"F3-checkout\nflow"`.
- Assert that `result.checks[0][2]` (the detail string) contains the escaped form `\\n` (the literal two-character sequence backslash-n) and does NOT contain a literal newline character.
- This is the only mechanical proof that the `unicode_escape` guard prevents a newline in a directory name from injecting a spurious newline into the validator's stdout.

---

### Producer/consumer symmetry test

`test_no_inline_dirname_regexes_in_validators` (replaces the previous substring-scan version):

```python
import ast
import importlib
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VALIDATE_SPEC_PATH = (
    _REPO_ROOT / "telescoping-sdd" / "skills" / "spec-driven-dev" / "scripts"
    / "validate_spec.py"
)
_VALIDATE_BLUEPRINT_PATH = (
    _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint" / "scripts"
    / "validate_blueprint.py"
)


def _load_spec_dirname():
    scripts = _REPO_ROOT / "telescoping-sdd" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    if "spec_dirname" in sys.modules:
        return importlib.reload(sys.modules["spec_dirname"])
    return importlib.import_module("spec_dirname")


def test_no_inline_dirname_regexes_in_validators():
    """Both validators must import classify_dirname from spec_dirname (not define
    their own). Uses ast to assert no re.match/re.compile/re.fullmatch call in
    classify_spec or walk_specs has a first string arg beginning with 'F'.

    Modelled on test_blueprint_token_vocab_matches_spec_profiles in
    test_arch_config.py (live-import comparison, not substring scan).
    """
    sd = _load_spec_dirname()

    # (a) Both validators import classify_dirname from spec_dirname.
    # Load each validator and assert classify_dirname is present AND is the
    # same function object as spec_dirname.classify_dirname (live-value check,
    # not a string scan).
    for vpath, mod_name in [
        (_VALIDATE_SPEC_PATH, "validate_spec"),
        (_VALIDATE_BLUEPRINT_PATH, "validate_blueprint"),
    ]:
        scripts_dir = vpath.parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        mod = importlib.import_module(mod_name)
        assert hasattr(mod, "classify_dirname"), \
            f"{mod_name} does not expose classify_dirname (missing import)"
        assert mod.classify_dirname is sd.classify_dirname, \
            f"{mod_name}.classify_dirname is not the same object as spec_dirname.classify_dirname"

    # (b) AST check: walk_specs and classify_spec in validate_blueprint contain
    # no re.match/re.compile/re.fullmatch call whose first string arg starts with 'F'.
    source = _VALIDATE_BLUEPRINT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    def _inline_F_regex_calls(func_name: str) -> list[str]:
        """Return a list of suspicious re-call snippets in the named function."""
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name != func_name:
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                func = child.func
                # Match re.match / re.compile / re.fullmatch
                if not (isinstance(func, ast.Attribute) and
                        func.attr in {"match", "compile", "fullmatch"} and
                        isinstance(func.value, ast.Name) and
                        func.value.id == "re"):
                    continue
                # Check if the first string arg starts with 'F'
                if child.args and isinstance(child.args[0], ast.Constant):
                    if isinstance(child.args[0].value, str) and \
                            child.args[0].value.startswith("F"):
                        found.append(ast.unparse(child))
        return found

    assert _inline_F_regex_calls("classify_spec") == [], \
        "inline F-dirname regex found in classify_spec"
    assert _inline_F_regex_calls("walk_specs") == [], \
        "inline F-dirname regex found in walk_specs"

    # (c) Positive shared-corpus check: fixed names classified identically by
    # the grammar the test imports and by classify_dirname.
    corpus = [
        ("F3-checkout-flow", "bound"),
        ("F3", "bare"),
        ("cli-notes-app", "standalone"),
        ("My_Feature", "invalid"),
        ("F0", "bare"),
        ("f3-racing", "standalone"),
    ]
    for name, expected in corpus:
        assert sd.classify_dirname(name) == expected, \
            f"classify_dirname({name!r}) expected {expected!r}"
```

---

### `test_validate_spec_py_no_my_feature_literal`

```python
def test_validate_spec_py_no_my_feature_literal():
    """R4 edit verification: validate_spec.py must contain no specs/my-feature/ literal.

    The docstring (~L20-22), epilog (~L1039), and help (~L1044) must all be
    updated to the bound-form example (e.g. specs/F1-checkout-flow/). This test
    is the mechanical proof that the R4 edit landed. It is separate from
    test_no_stale_placeholder_in_docs (which uses STALE_PLACEHOLDER_RE for
    angle-bracket patterns and does NOT match the literal 'my-feature').
    """
    source = _VALIDATE_SPEC_PATH.read_text(encoding="utf-8")
    count = source.count("specs/my-feature/")
    assert count == 0, (
        f"validate_spec.py still contains {count} occurrence(s) of "
        f"'specs/my-feature/' — update the docstring, epilog, and help string "
        f"to use the bound-form example (e.g. 'specs/F1-checkout-flow/')"
    )
```

---

### Doc-consistency test

`test_no_stale_placeholder_in_docs` — scans a DEFINED doc inventory (not a blind repo-wide rglob) for the R4 placeholder pattern. This approach is deterministic: it cannot match production docstrings in `arch_config.py`, `test_arch_config.py`, or the spec work-products themselves (`specs/spec-dir-naming/*.md`), because those files are outside the inventory.

**Exact inventory** (the R4-owned files):

```python
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SDD = _REPO_ROOT / "telescoping-sdd" / "skills" / "spec-driven-dev"
_PB  = _REPO_ROOT / "telescoping-sdd" / "skills" / "project-blueprint"

DOC_INVENTORY = [
    # SDD skill
    _SDD / "SKILL.md",
    _SDD / "references" / "phase-specify.md",
    _SDD / "references" / "phase-design.md",
    _SDD / "references" / "phase-tasks.md",
    _SDD / "references" / "examples.md",
    _SDD / "references" / "hash-and-cascade.md",
    _SDD / "references" / "panel-review.md",
    # Blueprint skill
    _PB  / "references" / "workflow-overview.md",
    # Repo root
    _REPO_ROOT / "CLAUDE.md",
    _REPO_ROOT / "README.md",
]
```

```python
STALE_PLACEHOLDER_RE = re.compile(r"specs/<feature(?:-name)?>/")

def test_no_stale_placeholder_in_docs():
    failures = []
    for path in DOC_INVENTORY:
        content = path.read_text(encoding="utf-8")
        for m in STALE_PLACEHOLDER_RE.finditer(content):
            failures.append(f"{path}: {m.group(0)!r}")
    assert not failures, "Stale placeholder(s) found:\n" + "\n".join(failures)
```

**Why inventory over rglob:** The rglob approach would match legitimate occurrences in `arch_config.py` (~lines 95, 102, 113 — production docstrings using `specs/<feature>/`), `test_arch_config.py` (~line 60 — `_spec_dir` docstring), and all files under `specs/spec-dir-naming/` (the SDD work products for this very feature). Scanning only the R4-owned inventory avoids these false positives and makes the test deterministic without requiring a growing allowlist.

**`test_hash_and_cascade_parity.py` `VOCABULARY_SWAP_MAP` key:** That file's `"specs/<feature-name>/": "blueprint/"` key is NOT in the inventory, so the doc-consistency test never fires on it. No allowlist is needed and no change to that file's key is required.

---

### `classify_spec` never-None test

`test_classify_spec_feature_id_never_none`:
- For each of `"F1-alpha"`, `"F1"`, `"cli-notes-app"`, `"My_Feature"`: create a `tmp_path / name` directory and call `vb.classify_spec(tmp_path / name)`. Assert `state.feature_id is not None` and `isinstance(state.feature_id, int)`.

---

### `validate_plan`-level integration test

`test_validate_plan_malformed_dirname_warns_and_zero_specstates` — locate in `test_spec_dirname.py` (alongside the grammar tests) or a new `test_spec_dirname_integration.py`. A `MINIMAL_PLAN` constant must be defined in the test module.

The `MINIMAL_PLAN` is a structurally valid `PLAN.md` string that:
- passes the `content is None` guard (non-empty)
- passes the required-section guards in `validate_plan` (must include the required headings — adapt from the existing CFC test helpers in `test_cfc_validation.py`)
- contains NO `[CFC-N]` tags (exercises the **non-CFC fast path** in `validate_plan`: the `else` branch at ~line 1599-1603, which calls `walk_specs(project_root)` only if `specs/` exists — this is the branch under test)

The minimal PLAN exercises the non-CFC branch: `cfc_entries` is empty, `plan_has_cfc_tags` is False, so `validate_plan` takes the fast-path `else` branch and calls `walk_specs(project_root)` conditionally. This is important because it means `_emit_malformed_dirname_warns` is called exactly once from that branch — confirming RD2's "mutually-exclusive branches" property and locking the no-double-emit claim.

```python
def test_validate_plan_malformed_dirname_warns_and_zero_specstates(tmp_path: Path):
    """AD2 plumbing end-to-end: My_Feature/ emits malformed-spec-dirname WARN
    AND contributes zero SpecState entries; checkout-flow/ (standalone) emits
    no WARN. Exercises the non-CFC fast path in validate_plan."""
    # Arrange: blueprint/PLAN.md at tmp_path/blueprint/PLAN.md so that
    # validate_plan(tmp_path / "blueprint") resolves project_root = tmp_path
    # and walk_specs hits tmp_path/specs/.
    blueprint_dir = tmp_path / "blueprint"
    blueprint_dir.mkdir()
    (blueprint_dir / "PLAN.md").write_text(MINIMAL_PLAN, encoding="utf-8")
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "My_Feature").mkdir()    # invalid → WARN + excluded from walk
    (specs / "checkout-flow").mkdir() # standalone → silent skip, no WARN

    result = vb.validate_plan(blueprint_dir)

    # (a) Invalid dir produces exactly one malformed-spec-dirname WARN.
    # Assert on tuple field check[0] (name), not str(c) substring.
    malformed_warns = [
        c for c in result.checks
        if c[0] == "malformed-spec-dirname"
    ]
    assert len(malformed_warns) == 1, (
        f"Expected exactly 1 malformed-spec-dirname WARN (locks RD2 no-double-emit), "
        f"got {len(malformed_warns)}: {malformed_warns}"
    )

    # (b) The single WARN's detail mentions My_Feature (escaped).
    assert "My_Feature" in malformed_warns[0][2], (
        f"WARN detail should mention My_Feature, got: {malformed_warns[0][2]!r}"
    )

    # (c) Standalone dir produces no WARN mentioning checkout-flow.
    assert not any(
        "checkout-flow" in c[2] for c in result.checks
    ), "checkout-flow/ must not generate any WARN"

    # (d) walk_specs returns zero entries for both dirs (My_Feature excluded as
    # invalid; checkout-flow excluded as standalone).
    spec_states = vb.walk_specs(tmp_path)
    assert spec_states == [], (
        f"My_Feature and checkout-flow should both be excluded from walk_specs, "
        f"got: {spec_states}"
    )
```

---

### Duplicate feature-id collision test

`test_duplicate_feature_dirs_warn` — new test asserting AD8's `duplicate-feature-dir` WARN:

```python
import pytest

@pytest.mark.parametrize("dir_a, dir_b", [
    ("F3-alpha", "F3"),        # bound + bare (migration artifact)
    ("F3-alpha", "F3-beta"),   # bound + bound (two slugs, same number — the more common real case)
])
def test_duplicate_feature_dirs_warn(tmp_path: Path, dir_a, dir_b):
    """AD8: two spec dirs with the same feature_id emit exactly one duplicate-feature-dir WARN
    that names BOTH directories."""
    blueprint_dir = tmp_path / "blueprint"
    blueprint_dir.mkdir()
    (blueprint_dir / "PLAN.md").write_text(MINIMAL_PLAN, encoding="utf-8")
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / dir_a).mkdir()    # feature_id 3
    (specs / dir_b).mkdir()    # feature_id 3 (collision)

    result = vb.validate_plan(blueprint_dir)

    dup_warns = [c for c in result.checks if c[0] == "duplicate-feature-dir"]
    # Exactly one WARN — guards against a per-branch double-emit (cf. RD2 discipline).
    assert len(dup_warns) == 1, (
        f"Expected exactly one duplicate-feature-dir WARN for {dir_a}+{dir_b}, got {len(dup_warns)}"
    )
    detail = dup_warns[0][2]
    # BOTH names must appear — use quoted/delimited tokens so a substring (e.g. 'F3'
    # inside 'F3-alpha') cannot satisfy the assertion for the OTHER directory.
    assert f"'{dir_a}'" in detail, f"Expected '{dir_a}' named in WARN detail: {detail!r}"
    assert f"'{dir_b}'" in detail, f"Expected '{dir_b}' named in WARN detail: {detail!r}"


def test_duplicate_feature_dir_warn_escapes_control_chars(tmp_path: Path):
    """AD8 + escaping invariant: a colliding dir name with a control char is escaped in the WARN
    detail (no literal newline), mirroring test_check_dir_identifier_control_char_in_dirname.
    If the test FS rejects the name, unit-test the WARN-formatting helper directly instead."""
    # ... create specs/"F3"/ and specs/"F3-a\nb"/ (both id 3); assert "\\n" in detail
    #     and "\n" not in detail.
```

**Tie-break documented:** When `state_by_id = {s.feature_id: s for s in spec_states}` encounters duplicate ids, the **last** entry in the sorted list wins (since `walk_specs` returns `sorted(..., key=lambda s: s.feature_id)` and Python dict construction retains the last value for a duplicate key). For equal `feature_id`, directory name sort order (lexicographic, from `sorted(specs_root.iterdir())`) determines position. The `duplicate-feature-dir` WARN names both directories so the user can resolve the ambiguity.

---

### CLI exit-code precision test

`test_slugify_cli_exit_codes_precise`:
- `slugify "valid title"` → exit 0.
- `slugify "!!!"` (empty result) → exit **1**, NOT 2.
- `slugify` (missing argument) → exit **2**, NOT 1.
- `badcmd x` (unknown subcommand) → exit **2**, NOT 1.

These assert the exact exit-code semantics from I1's exit table, preventing the common failure mode of asserting only "non-zero".

---

### CFC fixture migration

The `specs/F<n>` paths in `test_cfc_validation.py` and `test_cfc_cli_integration.py` that pass through `walk_specs` are migrated to `specs/F<n>-<slug>` using the structural recipe in C5.

**Feature-id → bound name map:**
```python
FEATURE_DIR_MAP = {1: "F1-alpha", 2: "F2-beta", 36: "F36-enforcement", 11: "F11-lock-order"}
```

The `for fid in (1, 2):` loop is rewritten to use this map (replacing `f"F{fid}"` with `FEATURE_DIR_MAP[fid]`). All literal `tmp_path / "specs" / "F<n>"` constructions at the sites listed in C5 are updated to use the corresponding mapped name.

Sites NOT migrated:
- `classify_spec` direct-call tests (lines ~456–555 of `test_cfc_validation.py`): use `tmp_path / "F1"` outside `specs/`, directly call `classify_spec`, do not go through `walk_specs`. Backward-compat `parse_feature_number` path unchanged.
- `test_walk_specs_skips_symlinks` symlink target `specs/F99`: symlink-skip carve-out test; stays bare.
- `test_walk_specs_skips_symlinks` real directory `specs/F1`: MIGRATE to `specs/F1-alpha` (the real dir's name is irrelevant to the symlink test, but it goes through `walk_specs` and would earn a WARN if left bare).

The stdout assertion `assert "F11" in proc.stdout` in `test_cfc_cli_integration.py` continues to pass because `F11-lock-order` contains `F11` as a substring.

---

### `test_hash_and_cascade_parity.py` update

No change to the `VOCABULARY_SWAP_MAP` key (`"specs/<feature-name>/"` → `"blueprint/"`). Because the doc-consistency test uses an explicit inventory (not rglob), this file is outside the scanned set and requires no allowlist addition. If a comment referencing the inventory approach is useful for future maintainers, add it; but no code change is required.

---

### R6: `test_archive_pass.py` corruption-regression matrix

New tests reproducing the simultaneous-promotion corruption (AD9). Each builds a panel-review document, runs `archive_pass.py <doc> --phase 2` in-process (or via the module's `main`/helper), and asserts STRUCTURAL invariants — not just heading counts:

- `test_reassembly_empty_sealed_populated_deferred` — `### Sealed dispositions` empty (insert branch), `### Deferred dispositions` has `[DEF-01]`/`[DEF-02]` (replace branch), Latest has one new Sealed + one new Deferred. This is the case that lost the heading in the wild.
- `test_reassembly_populated_sealed_populated_deferred` — both sections pre-populated (both replace branches).
- `test_reassembly_legacy_auto_insert_deferred` — document with NO `### Deferred dispositions` heading (triggers the ~L663–671 auto-insert), plus a new Sealed + new Deferred.

Shared structural assertions (a helper `_assert_panel_intact(text)`), specified precisely to avoid false-greens:
- each of `### Sealed dispositions`, `### Deferred dispositions`, `### Latest pass detail`, `## Approval` appears **exactly once** — assert `text.count(h) == 1` for each, INDEPENDENTLY and BEFORE any window scan (a duplicated `### Deferred dispositions` heading is itself a corruption symptom; deriving the window from a `.find()` that silently picks the first of two headings would mask it);
- locate the unique `### Deferred dispositions` heading and the next line matching `^#{2,3}\s` (computed by scan, NOT hard-coded to `### Latest pass detail` — a DEF orphaned past Latest, just above `## Approval`, must not escape);
- assert every `[DEF-NN]` **token** (the bracketed id, e.g. `[DEF-01]` — NOT the human concern title, which legitimately recurs) occurrence index lies strictly within `(deferred_heading_idx, next_heading_idx)`, AND that no `[DEF-NN]` token appears anywhere outside that window (this cross-check is what catches a *duplicate* DEF: one correct in-window + one orphaned into Sealed);
- the promoted `[SEAL-NN]` lands under `### Sealed dispositions`; the new `[DEF-NN]` id is sequential; `### Latest pass detail` is an empty table; a `### Trajectory` row was appended; the `- **Content Hash:** `b454da4cde94a551`archive_pass` as a subprocess via `_run_archive_pass([str(artifact), "--phase", "2"])` then `_assert_panel_intact(artifact.read_text())` (the T4–T8 pattern). Do NOT call `main()` in-process (it `sys.exit`s). The legacy-auto-insert case builds on `_legacy_artifact_without_deferred_section` (no Deferred heading) with a Latest carrying one Sealed + one Deferred row, so the auto-insert fires AND a simultaneous Sealed promotion shifts indices.

**Pure-unit tests for `_apply_edits`** (via `_load_archive_pass()`, the helper-test pattern) — the AD9 invariant is otherwise unverified: `test_apply_edits_rejects_overlapping_ranges` (asserts `AssertionError` on a synthetic overlapping edit list) and `test_apply_edits_applies_descending` (two disjoint edits with different line-count deltas land correctly regardless of list order).

**Red-before/green-after (explicit per-cell gate):** each matrix test must be verified to FAIL against the pre-refactor code and PASS after AD9 — run against HEAD before the fix, don't assume. For `test_reassembly_populated_sealed_populated_deferred`, the fixture must produce a non-zero net line-count delta in the Sealed edit (it does — one new SEAL row added above a populated Deferred) so the stale-offset bug actually fires.

**No regression:** the existing T3–T10 archive_pass suite must stay green — explicitly name as regression anchors `test_combined_legacy_artifact_with_deferred_rows` (reconcile with the new legacy-auto-insert case so they are complementary, not redundant — the new one adds a simultaneous Sealed), `test_deferred_terminal_forbids_deferred_row` (`--terminal` still exits 1), `test_deferred_promotion_two_rows_sequential_ids`, the `Defense: rerouted` marker-expansion tests, and the strict-bar trigger tests (they read the appended Trajectory row).

---

## File Structure

```
telescoping-sdd/
├── scripts/
│   ├── spec_dirname.py                     NEW — grammar module + slugify + CLI
│   ├── arch_config.py                      unchanged
│   ├── cfc_parser.py                       unchanged
│   ├── blueprint_common.py                 unchanged
│   ├── archive_pass.py                      MODIFIED (R6) — reassembly refactor + _apply_edits helper
│   └── tests/
│       ├── test_spec_dirname.py            NEW — full grammar + symmetry + doc suite
│       ├── test_archive_pass.py            MODIFIED (R6) — add Sealed+Deferred corruption matrix
│       ├── test_hash_and_cascade_parity.py unchanged (no allowlist change needed)
│       ├── test_arch_config.py             unchanged
│       └── test_cfc_parser_contract.py     unchanged
├── skills/
│   ├── spec-driven-dev/
│   │   ├── SKILL.md                        MODIFIED — placeholders + prose rule + migration note
│   │   ├── scripts/
│   │   │   └── validate_spec.py            MODIFIED — import spec_dirname; add check_dir_identifier;
│   │   │                                              call from validate_spec() and --approve path;
│   │   │                                              update CLI help strings and docstring
│   │   └── references/
│   │       ├── phase-specify.md            MODIFIED — directory naming + prose rule
│   │       ├── phase-design.md             MODIFIED — directory naming
│   │       ├── phase-tasks.md              MODIFIED — directory naming
│   │       ├── examples.md                 MODIFIED — directory naming
│   │       ├── hash-and-cascade.md         MODIFIED — directory naming
│   │       └── panel-review.md             MODIFIED — specs/<feature>/ refs
│   └── project-blueprint/
│       ├── scripts/
│       │   ├── validate_blueprint.py       MODIFIED — import spec_dirname (classify_dirname +
│       │   │                                          parse_feature_number only; is_bound_form,
│       │   │                                          is_standalone_form, is_valid_slug not imported
│       │   │                                          directly — all dispatch via classify_dirname);
│       │   │                                          replace BOTH inline regexes in classify_spec
│       │   │                                          + walk_specs; update walk_specs docstring;
│       │   │                                          add _emit_malformed_dirname_warns helper;
│       │   │                                          add _emit_duplicate_feature_dir_warns helper;
│       │   │                                          call both helpers from validate_plan
│       │   └── tests/
│       │       ├── test_cfc_validation.py  MODIFIED — migrate bare-token walk_specs fixtures to
│       │       │                                      F<n>-<slug>; keep classify_spec direct-call
│       │       │                                      tests and bare symlink target unchanged
│       │       └── test_cfc_cli_integration.py MODIFIED — migrate specs/F11 → specs/F11-lock-order
│       └── references/
│           └── workflow-overview.md        MODIFIED — update feature→spec-dir examples (lines 8,43,81-84)
├── .claude-plugin/
│   └── plugin.json                         MODIFIED — version 1.6.0 → 1.7.0

.claude-plugin/
└── marketplace.json                        MODIFIED — version 1.6.0 → 1.7.0

CLAUDE.md                                   MODIFIED — line ~96 validate_spec.py example
README.md                                   MODIFIED — line ~101 Output-dir cell
```

**File path verification:** All paths above are confirmed against the current repo layout. The `_SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"` path in both validators resolves to `telescoping-sdd/scripts/` — the directory where `spec_dirname.py` will live.

---

## Dependencies

| Package | Purpose | Notes |
|---------|---------|-------|
| `re` (stdlib) | Regex predicates in `spec_dirname.py` | Already used by both validators |
| `unicodedata` (stdlib) | NFKD normalization + Mn-category drop in `slugify` | Already imported by `validate_blueprint.py`; already used by `cfc_parser.py` for `normalize_for_hash` |
| `ast` (stdlib) | AST-based inline-regex check in `test_no_inline_dirname_regexes_in_validators` | Used in test only; already part of stdlib |

No new third-party dependencies. `spec_dirname.py` is stdlib-only, matching `cfc_parser.py` and `arch_config.py`.

---

## Integration Points

| Existing module | Direction | Change required | Details |
|-----------------|-----------|-----------------|---------|
| `validate_spec.py` | Calls into `spec_dirname` | Add `from spec_dirname import classify_dirname` after existing `from arch_config import ...` block | `is_bound_form`, `is_standalone_form`, `is_valid_slug`, and `parse_feature_number` are not needed directly — `check_dir_identifier` dispatches solely through `classify_dirname`. Mirrors existing `from cfc_parser import ...` pattern |
| `validate_spec.py` | `validate_spec()` | Add `check_dir_identifier(spec_dir)` call and merge result | After existing `validate_cfc_consumer` call (~line 576); merge via `result.checks.extend(check_dir_identifier(spec_dir).checks)` |
| `validate_spec.py` | `main()` `--approve` path (~line 1096) | Call `check_dir_identifier(spec_dir)` before `approve_document(target)`; exit non-zero if not passed | Between the `if not target.is_file()` guard and `approve_document(target)` |
| `validate_spec.py` | Docstring + argparse help | Update `specs/my-feature/` → `specs/F1-checkout-flow/` at all three sites (~L20-22, ~L1039, ~L1044) | Verified by `test_validate_spec_py_no_my_feature_literal` |
| `validate_blueprint.py` | Calls into `spec_dirname` | Add `from spec_dirname import classify_dirname, parse_feature_number` after existing `from cfc_parser import ...` block | `is_bound_form`, `is_standalone_form`, `is_valid_slug` are NOT imported — all dispatch goes through `classify_dirname`. Same `sys.path.append` pattern already handles the import |
| `validate_blueprint.py` | `classify_spec` (~line 354) | Replace `re.match(r"F(\d+)$", ...)` with `parse_feature_number` + `None`→`-1` | Two-line change; `import re` remains (used elsewhere) |
| `validate_blueprint.py` | `walk_specs` (~line 456) | Replace `re.match(r"F\d+$", entry.name)` filter with `classify_dirname`-dispatch logic; update `walk_specs` docstring | Entry filter logic (see I5); symlink skip unchanged |
| `validate_blueprint.py` | `validate_plan` (~lines 1595, 1603) | Call `_emit_malformed_dirname_warns(project_root, result)` before each `walk_specs(project_root)` call (both mutually-exclusive branches); call `_emit_duplicate_feature_dir_warns(spec_states, result)` exactly once at the post-`if/else` join (~L1607, after `spec_states` is assigned by whichever branch ran, before `compute_coverage`) | malformed warns: both branch sites; duplicate-id warn: single post-join site (no double-emit, no missed CFC branch) |
| `test_cfc_validation.py` | Fixture dirs via `walk_specs` | Migrate using structural recipe in C5 (rewrite `f"F{fid}"` loop + literal sites) | Direct `classify_spec` calls and `F99` symlink target unchanged |
| `test_cfc_cli_integration.py` | `specs/F11` fixture | Migrate to `specs/F11-lock-order` | `"F11" in proc.stdout` assertion survives |
| `test_hash_and_cascade_parity.py` | Doc-consistency | No change — inventory approach removes need for an allowlist | `VOCABULARY_SWAP_MAP` key unchanged |
| `SKILL.md` (spec-driven-dev) | Prose rule | Replace `specs/<feature-name>/` + `specs/<feature>/`; add bound/standalone rule + migration note | Normative home; referenced by `phase-specify.md` |
| `workflow-overview.md` (project-blueprint) | Spec-dir examples | Replace `specs/user-auth/` etc. with `specs/F1-user-auth/` etc. | Lines 8, 43, 81–84 per R4 AC |
| `CLAUDE.md` (repo root) | Example on line ~96 | Update `specs/<feature>/` → `specs/F1-<slug>/` | — |
| `README.md` (repo root) | Output-dir cell on line ~101 | Update `specs/<feature-name>/` → `specs/F<n>-<slug>/` | — |
| `plugin.json` + `marketplace.json` | Version field | `1.6.0` → `1.7.0` | plugin.json is authoritative per CLAUDE.md convention |
| `archive_pass.py` (R6) | `main()` reassembly block (~L954–988) | Refactor four sequential `replace_block`/insert calls into disjoint `(start,end,block)` tuples applied via new `_apply_edits` helper, sorted descending by `start` | Self-contained; NO file overlap with R1–R5; independently revertable. Preserves all promotion semantics |
| `test_archive_pass.py` (R6) | New regression matrix | Add the simultaneous Sealed+Deferred promotion tests (empty-Sealed+populated-Deferred, populated+populated, legacy auto-insert) | Red-before/green-after; existing T3–T10 suite must stay green |

---

## Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| RD1 | `check_dir_identifier` raises on an unexpected path shape (very short path, `spec.md` read race) instead of returning `cannot-cross-check` FAIL | Low | Med | All I/O in `check_dir_identifier` is wrapped in `except (OSError, UnicodeDecodeError)` (NOT `errors="replace"` — see I2 and Error Handling); the function contract explicitly states "Raises: Nothing". Test must exercise both the missing-file path and the non-UTF-8 path. |
| RD2 | `_emit_malformed_dirname_warns` runs twice per `validate_plan` call, doubling WARNs | Low | Low | The two `walk_specs` call sites are in mutually-exclusive `if`/`else` branches (~1594–1603). Only one branch executes per `validate_plan` invocation. The helper is called once per invocation. `test_validate_plan_malformed_dirname_warns_and_zero_specstates` asserts exactly one `malformed-spec-dirname` WARN, locking this guarantee mechanically. |
| RD3 | Doc-consistency test catches false positives from `arch_config.py` docstrings, `test_arch_config.py`, or `specs/spec-dir-naming/*.md` | Low | Low | Addressed by switching to a defined inventory approach (not rglob). The inventory contains only the R4-owned files, so no false positive is possible. No allowlist needed. |
| RD4 | CFC test fixture migration fails if an assertion checks the bare-token directory name string directly (e.g. `assert "specs/F1" in output`) | Low | Med | The one `proc.stdout` check is `"F11" in proc.stdout` which is a substring match surviving the rename. All other assertions key on parsed feature_id ints. Confirmed by reading both test files. The structural migration recipe (C5) accounts for the `f"F{fid}"` loop, not just literal strings. |
| RD5 | `slugify` truncation produces a result that does not satisfy `is_valid_slug` (e.g., truncates mid-segment leaving a trailing hyphen) | Low | Med | Truncation algorithm accumulates full segments only (split on `-`, join back with `-` while under the cap); a trailing hyphen cannot result. The `test_slugify_output_always_satisfies_is_valid_slug` and `test_slugify_single_segment_hard_truncation` tests assert this invariant. |
| RD6 | Doc sweep misses a stale placeholder in a newly-added file between spec write and implementation | Med | Low | The `test_no_stale_placeholder_in_docs` inventory is maintained alongside R4 doc changes; any new R4 file added after the fact must also be added to `DOC_INVENTORY`. This is a deliberate coupling — inventory additions are the correct maintenance action. |
| RD7 | `walk_specs` and `_emit_malformed_dirname_warns` classify the same directory differently (latent walk-vs-warn drift) | Low | Med | Both dispatch through `classify_dirname` — the single source of truth (AD2, C1). A misclassification in one automatically misclassifies the other, making drift impossible. The `test_classify_dirname` parametrized test asserts the function's behavior for all categories including `"bare"` (F0, F007). |
| RD8 | A project with both `specs/F3-checkout-flow/` and `specs/F3/` silently drops one entry from `state_by_id` (dict key collision), reintroducing the silent-skip class this feature exists to kill | Low | High | `_emit_duplicate_feature_dir_warns` detects and WARNs on any non-`-1` `feature_id` appearing more than once in the walked `spec_states`; the tie-break (last-in-sorted-order wins) is documented and deterministic. `test_duplicate_feature_dirs_warn` asserts both dirs are named in the WARN. |
| RD9 (R6) | The reassembly refactor regresses the existing `archive_pass.py` Deferred-dispositions test suite (T3–T10) — promotion id assignment, `Defense: rerouted` expansion, `--terminal`/`--skip` paths flow through the rewritten block | Med | Med | The refactor changes only edit *application order*, not the computed `new_block` values; the full `test_archive_pass.py` suite plus the new R6 matrix must pass (red-before/green-after on the matrix, green-throughout on T3–T10). The `_apply_edits` helper asserts non-overlap so a future fifth section edit can't silently reintroduce the bug. |

---

## Implementation Sequence

The sequence front-loads the shared module and tests so integration errors surface before touching consumers.

1. **`spec_dirname.py` + `test_spec_dirname.py`** (C1, C4) — foundational; all consumer changes depend on this module existing and its contracts being verified. Grammar tests (including `classify_dirname`, bare-token F0/F007, and NFKD expansion cases), `slugify` tests (including control-char, single-segment truncation, and CLI exit-code precision), symmetry test (AST-based), doc-consistency test (inventory approach), and matrix tests all live here. Build and test in isolation first.

2. **CFC fixture migration** (C5) — before touching `validate_blueprint.py`, migrate the test fixtures to bound form using the structural recipe (rewrite the `f"F{fid}"` loop + all literal construction sites). This step has no code changes in production modules. Running the existing test suite at this point will still pass, confirming the fixture content is correct before the validator changes land.

3. **`validate_blueprint.py`** (C3) — replace the two inline regexes (using `classify_dirname` as the dispatch point), update `walk_specs` docstring, add `_emit_malformed_dirname_warns` and `_emit_duplicate_feature_dir_warns`. After this step, `test_cfc_validation.py` and `test_cfc_cli_integration.py` must still pass with the migrated fixtures from step 2. The symmetry test from step 1 now also passes.

4. **`validate_spec.py`** (C2) — add `check_dir_identifier` (with `UnicodeDecodeError`-safe I/O via `except (OSError, UnicodeDecodeError)` — NOT `errors="replace"` — and control-char-escaped message embedding), integrate into `validate_spec()`, and gate `--approve`. Update CLI help and docstring. These changes are isolated to `validate_spec.py` and do not depend on step 3 (but step 1 must be complete). Can run in parallel with step 3 if needed.

5. **Documentation + CLI help** (R4) — update all `.md` files and `validate_spec.py`'s argparse help and docstring. Mechanical sweep; depends on all steps above being complete so the prose is written against the final behaviour.

6. **Version bump** (R4) — `plugin.json` and `marketplace.json` to `1.7.0`. Last step to avoid bumping before the feature is complete.

**R6 (`archive_pass.py` fix) is an independent track.** It touches only `archive_pass.py` + `test_archive_pass.py` — zero file overlap with steps 1–5 and no logical dependency in either direction — so it can be implemented and landed in parallel (or as its own commit) at any point. Internal order: write the R6 regression matrix first (red against current code), then refactor the reassembly via `_apply_edits` until the matrix is green AND the existing T3–T10 archive_pass suite stays green. The 1.7.0 release notes must name R6 as a distinct fix (per spec R6).

Steps 3 and 4 can be developed in parallel if two developers are working the feature; otherwise the sequential order 1→2→3→4→5→6 is preferred.

---

## Open Questions

> All questions below are resolved. No open questions block Phase 3 (Tasks).

- [x] Q1: **Resolved** — `walk_specs` WARN plumbing is option (c): emit in `validate_plan` via a new `_emit_malformed_dirname_warns` helper. Rationale: no signature change to `walk_specs` or its callers; the helper is isolated to `validate_plan` which already owns a `ValidationResult`. See AD2.

- [x] Q2: **Resolved** — `None`→`-1` adaptation is `fid = parse_feature_number(name); feature_id = fid if fid is not None else -1` inside `classify_spec`. See AD3 and I4.

- [x] Q3: **Resolved** — `slugify` raises `ValueError` on empty result; the CLI catches it and exits 1 with a message on stderr. See AD4 and I1.

- [x] Q4: **Resolved** — accent folding via `unicodedata.normalize('NFKD', ...)` + drop `Mn` combining marks, stdlib only. NFKD is intentionally lossy (superscripts/fullwidth/ligatures). Input capped at 4096 chars. CJK/emoji produce empty slug → `ValueError`. See AD5 and DM2.

- [x] Q5: **Resolved** — `check_dir_identifier` returns a `ValidationResult` (not mutates a passed-in one). Called from `validate_spec()` and from `main()`'s `--approve` path. See AD6 and I2.

- [x] Q6: **Resolved** — `classify_dirname` is the single dispatch point for both `walk_specs` filter and `_emit_malformed_dirname_warns`, eliminating latent walk-vs-warn drift. Bare tokens `F0`, `F007` resolve to `"bare"` (intentional, backward-compat). See AD2, DM1.

- [x] Q7: **Resolved** — `check_dir_identifier` never raises: reads `spec.md` with `except (OSError, UnicodeDecodeError)` guard; `errors="replace"` is explicitly NOT used (would allow garbage-parse of non-UTF-8 files, contradicting `test_check_dir_identifier_non_utf8_spec_md`). Directory names embedded in FAIL messages are escaped via `encode("unicode_escape").decode("ascii")`. See I2, Error Handling.

- [x] Q8: **Resolved** — doc-consistency test uses a defined inventory (not rglob), eliminating false positives from `arch_config.py` docstrings, `test_arch_config.py`, and `specs/spec-dir-naming/*.md`. No allowlist required. See Testing Strategy (Doc-consistency test).

---

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
| 1    | 2026-06-01 | 4     | 0           | 17        | 0        | 0      | tags=d0u0c4                     |
| 2    | 2026-06-02 | 2     | 0           | 13        | 0        | 0      | tags=d0u0c2                     |
| 3    | 2026-06-02 | 0     | 0           | 6         | 0        | 3      | converged (0 HIGH); tags=d0u0c0 |
| 4    | 2026-06-02 | 0     | 0           | 11        | 0        | 0      | converged (0 HIGH); tags=d0u0c0 |

### Sealed dispositions

- `[SEAL-01]` **slugify step-7 hard-truncation has no explicit re-strip;…** (pass 3, accepted-as-risk) — Defense: whole-segment join + single-run slice cannot produce a trailing hyphen; test_slugify_output_always_satisfies_is_valid_slug covers the truncation cases, so the invariant is mechanically guarded.
- `[SEAL-02]` **MINIMAL_PLAN over-specified — only non-empty is needed to…** (pass 3, accepted-as-risk) — Defense: a fully-valid PLAN is a harmless superset and avoids coupling the test to validate_plan's internal early-return structure.
- `[SEAL-03]` **truncation-test prose says "53 chars" then "55 chars"…** (pass 3, accepted-as-risk) — Defense: asserted value (55) and expected slug are both correct; R4 test is correctly scoped to the `specs/my-feature/` literal.

### Deferred dispositions

<!-- Auto-populated by archive_pass.py when a Deferred-disposed row is promoted; remains empty until first deferral. -->

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [x] Approved to proceed to next phase
- **Content Hash:** `b454da4cde94a551`
