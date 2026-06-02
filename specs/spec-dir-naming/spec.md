# Feature: Strengthen spec-directory filenames across both skills

**PLAN feature identifier:** `n/a`

## Objective

The two skills that compose telescoping-sdd disagree on what a spec directory is named. `spec-driven-dev` treats `specs/<feature-name>/` as a free-form, user-typed placeholder with no validation; `project-blueprint`'s `walk_specs` function matches `specs/F<n>/` via the strict inline regex `^F\d+$`. A user who names a spec directory `specs/checkout-flow/` with in-file identifier `F3` is silently skipped by `walk_specs`, dropping the feature out of CFC orphan detection with no warning. This is the core bug.

This feature introduces a shared directory-name grammar owned by the new module `telescoping-sdd/scripts/spec_dirname.py`, enforces a directory↔identifier cross-check as a blocking error in `validate_spec.py` (including on the `--approve` path, which currently approves without running any validation), loosens `walk_specs` and `classify_spec` in `validate_blueprint.py` to resolve the new `F<n>-<slug>` bound form while warning on bare `F<n>` tokens, updates all documentation and templates to reflect the new naming contract, and bumps the plugin to version 1.7.0.

It also fixes a pre-existing corruption bug in the shared `telescoping-sdd/scripts/archive_pass.py` (R6), discovered while dogfooding this very workflow: when a panel pass promotes BOTH a new `Sealed` entry AND rewrites existing `Deferred` entries, the multi-section reassembly applies block edits using indices computed against the pre-edit document, so the `Sealed`-section insert shifts the `Deferred` section below it and the subsequent `Deferred` edit writes at stale offsets — duplicating `[DEF-NN]` entries and clobbering the `### Deferred dispositions` and `## Approval` headings. It is folded in here because it lives in the same shared-scripts directory and the same panel-artifact tooling this feature already touches.

## Requirements

### R1: Shared directory-name grammar module

As a developer integrating both skills, I want a single shared Python module that owns the spec-directory name grammar, so that `validate_spec.py` and `validate_blueprint.py` cannot drift to different interpretations of what a valid spec-directory name looks like.

**Acceptance Criteria:**

- GIVEN a call to `spec_dirname.is_bound_form("F3-checkout-flow")`
  WHEN the function executes
  THEN it returns `True` and `spec_dirname.parse_feature_number("F3-checkout-flow")` returns `3`

- GIVEN a call to `spec_dirname.is_standalone_form("cli-notes-app")`
  WHEN the function executes
  THEN it returns `True` and `spec_dirname.parse_feature_number("cli-notes-app")` returns `None`

- GIVEN a call to `spec_dirname.is_bound_form("F3")` (bare token, no slug)
  WHEN the function executes
  THEN it returns `False` (bare `F<n>` is not a valid bound form)

- GIVEN a call to `spec_dirname.parse_feature_number("F3")` (bare token, no slug)
  WHEN the function executes
  THEN it returns `3` — bare tokens remain parseable for backward compatibility in `classify_spec`, even though `is_bound_form("F3")` returns `False`

- GIVEN a call to `spec_dirname.is_standalone_form("F3-checkout-flow")`
  WHEN the function executes
  THEN it returns `False` (the `F<n>-` prefix is reserved for the bound form, not a standalone slug)

- GIVEN the bound-form prefix is **case-sensitive uppercase-`F` only**, and a call to `spec_dirname.is_bound_form("f3-racing")` or `spec_dirname.parse_feature_number("f3-racing")` (lowercase `f`)
  WHEN each executes
  THEN `is_bound_form` returns `False` and `parse_feature_number` returns `None` — a lowercase `f<digits>-...` name is a valid standalone slug, never silently read as bound (so `is_standalone_form("f3-racing")` returns `True`)

- GIVEN a feature number of zero or with leading zeros (`"F0-x"`, `"F007-x"`)
  WHEN `spec_dirname.is_bound_form(...)` is called
  THEN it returns `False` — feature numbers are positive with no leading zeros, matching the CFC layer's reject-zero / reject-leading-zero rule in `validate_blueprint.py` (so the bound grammar cannot silently swallow `F007` → 7)

- GIVEN slug strings with uppercase letters (`"CheckoutFlow"`), underscores (`"checkout_flow"`), or mixed-case characters
  WHEN `spec_dirname.is_valid_slug(slug)` is called on each
  THEN each returns `False`

- GIVEN a valid lowercase kebab-case token such as `"checkout-flow"` or `"cli-notes-app"`
  WHEN `spec_dirname.is_valid_slug(slug)` is called
  THEN it returns `True`

- GIVEN slugs of exactly 50 and exactly 51 characters
  WHEN `spec_dirname.is_valid_slug(slug)` is called on each
  THEN the 50-char slug returns `True` and the 51-char slug returns `False` (50 is an inclusive hard cap applied to the **slug portion only**, not the `F<n>-` prefix; there is no minimum beyond a single non-empty kebab segment)

- GIVEN a leading-digit slug such as `"2fa-login"` and a numeric-only slug such as `"123"`
  WHEN `spec_dirname.is_valid_slug(slug)` is called on each
  THEN each returns `True` (the grammar permits digits anywhere, including the first character)

- GIVEN a title string such as `"Checkout Flow (v2)"`
  WHEN `spec_dirname.slugify("Checkout Flow (v2)")` is called
  THEN it returns a lowercase kebab-case string matching `^[a-z0-9]+(-[a-z0-9]+)*$`, with no leading or trailing hyphens and no consecutive hyphens

- GIVEN any title for which `slugify` produces a non-empty result
  WHEN `spec_dirname.slugify(title)` is called
  THEN its output ALWAYS satisfies `is_valid_slug` — in particular `slugify` truncates at a word (hyphen-segment) boundary so the result never exceeds the 50-char cap. `slugify` and `is_valid_slug` can never disagree on the same string.

- GIVEN a title that reduces to empty after slugification (all punctuation/emoji such as `"!!!"` or `"🚀"`, or a non-Latin script that transliterates to nothing)
  WHEN `spec_dirname.slugify(title)` is called
  THEN it raises a clear error (or returns a sentinel the CLI converts to a non-zero exit with an actionable message) — it never returns an empty or invalid slug. [Accent-folding policy for Latin-with-diacritics titles (e.g. `"Café"` → `"cafe"`) is specified in design.md.]

- GIVEN `spec_dirname` is imported in both `validate_spec.py` and `validate_blueprint.py`
  WHEN both validators classify the same directory name
  THEN they call the same grammar functions from `spec_dirname` — no duplicated inline directory-name regexes remain in either validator. Specifically, BOTH inline regexes currently in `validate_blueprint.py` (`classify_spec`'s `re.match(r"F(\d+)$", ...)` and `walk_specs`'s `re.match(r"F\d+$", ...)`) are removed in favor of `spec_dirname` calls.

- GIVEN `parse_feature_number` is lenient by design (returns `3` for bare `"F3"` even though `is_bound_form("F3")` is `False`)
  WHEN the test suite asserts the pairing
  THEN it documents (in the module docstring) and asserts that validity gating MUST use `is_bound_form`, never `parse_feature_number != None`, so no caller mistakes leniency for validity

- GIVEN `spec_dirname.py` is placed in `telescoping-sdd/scripts/` alongside `cfc_parser.py` and `arch_config.py`
  WHEN either validator imports it via the existing `_SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"` path and `sys.path.append` pattern
  THEN the import succeeds with no additional `sys.path` configuration

### R2: Directory↔identifier cross-check in `validate_spec.py`

As a spec author, I want `validate_spec.py` to block validation and approval when a spec directory's name disagrees with its in-file PLAN feature identifier, so that a misnamed directory never silently drops the feature from CFC orphan detection.

The cross-check is implemented as a **standalone function** `check_dir_identifier(spec_dir) -> ValidationResult` (it keys off the directory name plus the `**PLAN feature identifier:**` line read from `spec.md`), so it can run independently of `validate_spec()` — which early-returns when `spec.md` is absent and only covers the spec phase. `validate_spec()` calls it; the `--approve` path (for spec, design, AND tasks) calls it directly before stamping.

**Acceptance Criteria:**

- GIVEN a spec directory named `F3-checkout-flow` with in-file identifier `` `F3` `` (n==m, valid bound form)
  WHEN `validate_spec.py <spec-dir>` is run
  THEN the cross-check passes and validation continues normally

- GIVEN a spec directory named `F3-checkout-flow` with in-file identifier `` `F5` `` (n≠m mismatch)
  WHEN `validate_spec.py <spec-dir>` is run
  THEN the validator emits a `dir-identifier-mismatch` FAIL naming the offending directory and both the directory-implied number (3) and the in-file identifier (F5), and exits with non-zero status

- GIVEN a spec directory named `F3-checkout-flow` with in-file identifier `` `n/a` `` (bound-form path, standalone identifier)
  WHEN `validate_spec.py <spec-dir>` is run
  THEN the validator emits a FAIL that states the **decision criterion**, not just two mechanical options: "if this feature is part of a `blueprint/PLAN.md`, set the identifier to `` `F3` ``; if it is standalone, rename the directory to the bare slug `checkout-flow`", and exits with non-zero status

- GIVEN a spec directory named `checkout-flow` (standalone slug) with in-file identifier `` `F3` ``
  WHEN `validate_spec.py <spec-dir>` is run
  THEN the validator emits a FAIL stating the decision criterion **symmetrically** (mirroring the bound-dir + `n/a` case): "if this feature is part of a `blueprint/PLAN.md`, rename the directory to `F3-checkout-flow`; if it is standalone, change the in-file identifier to `` `n/a` ``", and exits with non-zero status — the message must not steer the user toward binding a spec they may have meant to keep standalone

- GIVEN a spec directory named `checkout-flow` (standalone slug) with in-file identifier `` `n/a` ``
  WHEN `validate_spec.py <spec-dir>` is run
  THEN the cross-check passes

- GIVEN a spec directory named `F3` (bare token, no slug)
  WHEN `validate_spec.py <spec-dir>` is run
  THEN the validator emits a `missing-slug` FAIL regardless of the in-file identifier, naming the directory and instructing the user to rename it to `F3-<slug>`, and exits with non-zero status

- GIVEN a spec directory with characters not in lowercase kebab form (e.g. `My_Feature`)
  WHEN `validate_spec.py <spec-dir>` is run
  THEN the validator emits an `invalid-slug` FAIL naming the offending directory name, and exits with non-zero status

- GIVEN any `missing-slug` or `invalid-slug` FAIL
  WHEN the message is rendered
  THEN it names the offending directory, states the exact rename target, AND points to the slug generator so the user can self-serve the `<slug>` value — e.g. "to generate a slug from the feature title, run `python telescoping-sdd/scripts/spec_dirname.py slugify \"<title>\"`"

- GIVEN a spec directory named `F3-checkout-flow` with in-file identifier `` `F3` `` and a valid `spec.md`
  WHEN `validate_spec.py <spec-dir> --approve spec` is run
  THEN `check_dir_identifier` executes before `approve_document` is called, and a directory mismatch causes the process to exit with non-zero status before any file is written

- GIVEN a spec directory named `F3-checkout-flow` with in-file identifier `` `F5` `` (mismatch)
  WHEN `validate_spec.py <spec-dir> --approve spec` is run
  THEN the process exits with non-zero status and `spec.md` is not modified

- GIVEN a directory that fails the cross-check (any matrix FAIL above)
  WHEN `validate_spec.py <spec-dir> --approve design` OR `--approve tasks` is run
  THEN `check_dir_identifier` runs first (reading the identifier from `spec.md`) and the process exits non-zero before `design.md` / `tasks.md` is stamped — the directory gate applies to ALL three approve targets, not just `spec`

- GIVEN `--approve design` or `--approve tasks` is run in a directory where `spec.md` is missing or has no readable `**PLAN feature identifier:**` line
  WHEN `check_dir_identifier` runs
  THEN it emits a clear `cannot-cross-check` FAIL ("spec.md identifier is unreadable — approve spec first") and exits non-zero, rather than silently passing or crashing (in normal flow spec.md is already approved by this point, so this guards the out-of-order/corrupted case)

- GIVEN a hand-created bound directory whose slug portion exceeds 50 characters (e.g. `F3-this-slug-is-far-longer-than-the-fifty-character-hard-cap`)
  WHEN `validate_spec.py <spec-dir>` is run
  THEN the validator emits an `invalid-slug` FAIL with the rename guidance — closing the round-trip between the `slugify` ≤50 generator guarantee and the validator gate (the cross-check validates dir names users may have typed by hand, not only `slugify` output)

- GIVEN any directory-rename FAIL (`missing-slug`, `invalid-slug`, `dir-identifier-mismatch`)
  WHEN the message is rendered
  THEN it includes the reassurance that **renaming a spec directory does not invalidate any existing approval or content hash** — so an upgrading user who has already approved `spec.md` is not afraid to rename (the fact already holds per Boundaries; this AC routes it to where the user reads it)

### R3: `walk_specs` and `classify_spec` updated in `validate_blueprint.py`

As a blueprint author using CFC orphan detection, I want the blueprint validator to recognize `specs/F<n>-<slug>/` directories as bound spec directories and warn on malformed ones, so that the new grammar closes the silent-skip gap while maintaining backward compatibility.

> **Note on WARN plumbing.** `walk_specs(project_root)` currently returns `list[SpecState]` and has no `ValidationResult` to write a WARN into; it is called from multiple sites in `validate_plan`. The *requirement* below is "the validator's output includes a `malformed-spec-dirname` WARN" — the exact plumbing (thread a `result` into `walk_specs`, return a `(states, warnings)` tuple, or emit the WARN in the calling `validate_plan`) is a **design-phase decision** (see Deferred dispositions → design.md). The ACs are written against validator *output*, not against `walk_specs`' internal signature.

**Acceptance Criteria:**

- GIVEN a `specs/` directory containing `F3-checkout-flow/` with a `spec.md` whose in-file identifier is `` `F3` ``
  WHEN the blueprint validator walks specs
  THEN the directory resolves to a bound feature with `feature_id == 3` and is included in coverage/orphan analysis

- GIVEN a `specs/` directory containing `F3/` (bare token, old form, no slug)
  WHEN the blueprint validator walks specs
  THEN the directory still resolves with `feature_id == 3` (backward-compatible — it is NOT dropped) AND the validator's output includes a `malformed-spec-dirname` WARN naming the directory and instructing the user to rename it to `F3-<slug>`

- GIVEN a `specs/` directory containing `checkout-flow/` (standalone slug)
  WHEN the blueprint validator walks specs
  THEN the directory is skipped from feature resolution (standalone specs are correctly not PLAN-bound features) with no WARN

- GIVEN a `specs/` directory containing an invalid directory name such as `My_Feature/`
  WHEN the blueprint validator walks specs
  THEN the validator's output includes a `malformed-spec-dirname` WARN naming the directory, AND no malformed directory appears in the coverage map or orphan scan (it surfaces ONLY as a WARN) — so no unresolved-id sentinel can collide there

- GIVEN `classify_spec` now derives the id from `spec_dirname.parse_feature_number`, which returns `None` (not `-1`) for a non-bound name, while `SpecState.feature_id` is typed `int` and is used as a sort key (`sorted(..., key=lambda s: s.feature_id)`) and a dict key (`state_by_id`)
  WHEN a non-bound name reaches `classify_spec`
  THEN the boundary adapts `None` to the existing `-1` sentinel (`fid = parse_feature_number(name); feature_id = fid if fid is not None else -1`) so `feature_id` is NEVER `None` — a `None` would raise `TypeError` on the sort and behave wrongly as a dict/membership key. The R5 test suite asserts `classify_spec` never returns `feature_id is None`

- GIVEN a `specs/` entry that is a **symlink** whose name matches the bound or standalone grammar
  WHEN the blueprint validator walks specs
  THEN it remains skipped for the existing security reason (symlinks can point outside the project tree), and this is the one acknowledged carve-out from the no-silent-skip doctrine — recorded in Boundaries, not treated as a malformed-dir WARN

- GIVEN `classify_spec` is called with a `spec_dir` named `F3-checkout-flow`
  WHEN the function runs
  THEN it derives `feature_id` via `spec_dirname.parse_feature_number(spec_dir.name)` rather than the previous inline regex `re.match(r"F(\d+)$", spec_dir.name)`

- GIVEN `classify_spec` is called with a `spec_dir` named `F3` (bare token, backward-compat input)
  WHEN the function runs
  THEN it derives `feature_id == 3` via `spec_dirname.parse_feature_number("F3")` so that orphan detection continues to work on projects that have not yet migrated

### R4: Docs and templates updated to the new naming contract

As a first-time SDD user reading the documentation, I want every reference to the old free-form placeholder updated to reflect the new bound (`specs/F<n>-<slug>/`) and standalone (`specs/<slug>/`) forms, AND a short prose rule that actively teaches the distinction, so that I learn the convention from the docs rather than only from a validator FAIL.

The doc sweep must cover **both** placeholder spellings — `specs/<feature-name>/` AND `specs/<feature>/` — plus the literal example `specs/my-feature/` in `validate_spec.py`'s CLI help, plus the named-feature examples in `workflow-overview.md`. The complete confirmed inventory (from a repo-wide grep) is enumerated below; the design phase owns the exact replacement per file.

**Acceptance Criteria:**

- GIVEN the SDD doc set — `spec-driven-dev/SKILL.md`, `references/phase-specify.md`, `phase-design.md`, `phase-tasks.md`, `examples.md`, `hash-and-cascade.md`, `panel-review.md`
  WHEN each is searched for `specs/<feature-name>/` and `specs/<feature>/`
  THEN no instances remain; the bound form `specs/F<n>-<slug>/` and standalone form `specs/<slug>/` are used in their place

- GIVEN `spec-driven-dev/SKILL.md` after implementation (the NORMATIVE home — it is always loaded when the skill is relevant; `references/phase-specify.md` cross-links to it)
  WHEN a first-time user reads it
  THEN it contains an explicit prose rule, WITH a concrete example pairing a directory name to its `**PLAN feature identifier:**` line, distinguishing the two forms: **bound** = `F<n>-<slug>` for a feature that appears in `blueprint/PLAN.md` (in-file identifier `F<n>`); **standalone** = bare `<slug>` for a feature with no PLAN (in-file identifier `n/a`). It also states the one-line rationale for why the blueprint validator only WARNs while the spec validator FAILs on the same bare `F<n>` dir (blueprint stays non-blocking for backward-compatible coverage; the spec owns the authoring gate). Plus a migration note: pre-1.7.0 bare `specs/F<n>/` directories must be renamed to `specs/F<n>-<slug>/`, the rename is approval/hash-safe, and lowercase `f<digits>-...` standalone directories need NO migration (the bound form is uppercase-`F` only)

- GIVEN `validate_spec.py`'s argparse `epilog`, the `spec_dir` help string, and the module docstring usage block (the lines currently showing `specs/my-feature/`)
  WHEN they are read after implementation
  THEN they show a bound-form example (e.g. `specs/F1-checkout-flow/`) so the most-seen "documentation" — the CLI's own `--help` — models the new convention

- GIVEN `project-blueprint/references/workflow-overview.md`
  WHEN searched for the bound-feature examples (`specs/user-auth/`, `specs/data-models/`, `specs/api-endpoints/`, `specs/dashboard/`) and the `specs/feature-name/` prose references (lines 8 and 43)
  THEN they are updated to the new bound form (e.g. `specs/F1-user-auth/`, `specs/F2-data-models/`)

- GIVEN the repo root `CLAUDE.md` (line ~96, which uses `specs/<feature>/`) and `README.md` (line ~101 "Output dir" cell, which uses `specs/<feature-name>/`)
  WHEN read after implementation
  THEN both use the new forms (CLAUDE.md's `validate_spec.py` example shows `specs/F1-<slug>/`; README's Output-dir cell shows `specs/F<n>-<slug>/`)

- GIVEN both `telescoping-sdd/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` after implementation
  WHEN their `version` fields are read (and, as a manual human check, `claude plugin validate ./telescoping-sdd` is run)
  THEN both report version `1.7.0`, kept in lockstep (plugin.json authoritative per the repo's version-bump convention). [Note: `claude plugin validate` is an external CLI, not part of the pytest harness — it is a manual verification step, not a mechanical test.]

### R5: Test suite for `spec_dirname.py`

As a developer modifying the directory-name grammar, I want a test suite `telescoping-sdd/scripts/tests/test_spec_dirname.py` that asserts grammar correctness, `slugify` behavior, round-trips, and producer/consumer symmetry, so that accidental regex drift is caught mechanically.

**Acceptance Criteria:**

- GIVEN `test_spec_dirname.py` exists alongside `test_arch_config.py` and `test_cfc_parser_contract.py`
  WHEN `.venv/bin/pytest telescoping-sdd/scripts/tests/test_spec_dirname.py -q` is run
  THEN all tests pass — covering grammar correctness, the `slugify` cases in R1 (incl. empty-result, truncation-to-cap, uppercase-only `F`, `F0`/leading-zero, 50/51 boundary), round-trips, and the lenient-`parse_feature_number` pairing assertion

- GIVEN a test that loads both `validate_spec` and `validate_blueprint` and inspects that NEITHER defines its own inline directory-name regex that could drift from `spec_dirname` (scanning for BOTH former sites in `validate_blueprint.py` — `classify_spec` and `walk_specs`)
  WHEN the test runs
  THEN it passes, confirming producer/consumer grammar symmetry (analogous to the `test_blueprint_token_vocab_matches_spec_profiles` check in `test_arch_config.py`)

- GIVEN a doc-consistency test that defines ONE canonical forbidden-pattern regex (matching both `specs/<feature-name>/` and `specs/<feature>/`) and scans the whole repo
  WHEN it runs
  THEN it fails if any stale placeholder survives in a doc, EXCEPT an explicit allowlist anchored on **file path + the matched key string** (NOT a line number, which rots on reformat) — specifically `test_hash_and_cascade_parity.py`'s `VOCABULARY_SWAP_MAP` entry, which must retain the literal `specs/<feature-name>/` as a load-bearing SDD↔PB normalization key. The R4 AC grep and this test reference the SAME regex so they cannot drift.

- GIVEN the require-slug change makes bare `specs/F<n>/` directories emit a `malformed-spec-dirname` WARN
  WHEN the existing CFC test suites run (`project-blueprint/scripts/tests/test_cfc_validation.py` and `test_cfc_cli_integration.py`, which create ~18 bare-token fixtures like `specs/F1/`, `F11/`, `F36/`)
  THEN they still pass — achieved by **migrating those fixtures to the bound `F<n>-<slug>` form** (e.g. `specs/F1-alpha/`); migration is the chosen arm (NOT "tolerate the WARN") so the suite stays internally consistent — pass-2 review confirmed no assertion keys on the bare-token dir-name string (the only stdout check, `"F11" in proc.stdout`, survives as a substring of `F11-<slug>`, and feature-id assertions read the parsed int). The existing `specs/F99` symlink test (`test_cfc_validation.py:738`) continues to assert the symlink is skipped (the carve-out in R3).

- GIVEN the loosened walk + `parse_feature_number` boundary
  WHEN `test_spec_dirname.py` (or a blueprint-side test) exercises a `My_Feature/` directory and asserts `classify_spec`'s contract
  THEN it asserts (a) `My_Feature/` yields a `malformed-spec-dirname` WARN and contributes ZERO `SpecState` entries to coverage/orphan analysis, and (b) `classify_spec` NEVER returns `feature_id is None` (the `None`→`-1` adaptation from R3 holds), guarding the sort/dict-key `TypeError`

- GIVEN the slug CLI is invoked with no argument, or an argument the shell reduced to empty, or a title that slugifies to empty
  WHEN `python telescoping-sdd/scripts/spec_dirname.py slugify [...]` runs
  THEN it exits non-zero with an actionable message rather than emitting an empty/invalid slug or a traceback — covering the missing-argument case distinctly from the semantic-empty case in R1

- GIVEN the full test suite invoked as `.venv/bin/pytest telescoping-sdd/ -q`
  WHEN all tests run after this feature is implemented
  THEN no pre-existing tests regress

### R6: Fix the `archive_pass.py` multi-section reassembly corruption

As a user running the panel-review loop, I want `archive_pass.py` to correctly promote `Sealed` and `Deferred` dispositions in the same pass without corrupting the document, so that a panel artifact with deferrals never silently loses its `### Deferred dispositions` / `## Approval` headings or accumulates duplicate `[DEF-NN]` entries.

> **Root cause (reproduced).** In the reassembly block (`archive_pass.py`, the `replace_block`/insert sequence near the end of `main()`), the four section edits (Latest-clear, Sealed-promote, Deferred-promote, Trajectory-append) are applied to `new_lines` using line indices/anchors computed against the PRE-EDIT `lines`. The sections are ordered (top→bottom) Trajectory, Sealed, Deferred, Latest. Because the `Sealed` section sits ABOVE the `Deferred` section, promoting a new `[SEAL-NN]` entry changes the line count above the `Deferred` section, so the subsequent `Deferred` edit — still using pre-edit offsets — writes at the wrong place. Reproduced symptoms (they vary by which branches fire — replace-branch when a section already has entries vs insert-branch when it is empty, plus the legacy auto-insert of `### Deferred dispositions`): existing `[DEF-NN]` entries are **duplicated**, the `### Deferred dispositions` heading is **lost/misplaced**, DEF entries are **orphaned into the `### Sealed dispositions` section**, and/or the `## Approval` heading is overwritten. The bug only fires when a single pass promotes a new `Sealed` entry AND has `Deferred` entries to (re)write.

**Acceptance Criteria:**

- GIVEN a panel-review document whose `### Deferred dispositions` already contains `[DEF-01]` and `[DEF-02]`, and whose `### Latest pass detail` contains one new `Sealed` row AND one new `Deferred → <target>` row
  WHEN `archive_pass.py <doc> --phase 2` is run
  THEN the resulting document satisfies these STRUCTURAL invariants: `### Sealed dispositions`, `### Deferred dispositions`, `### Latest pass detail`, and `## Approval` each appear exactly once; every `[DEF-NN]` line appears exactly once and falls between the `### Deferred dispositions` heading and the next `###`/`##` heading (no DEF orphaned into the Sealed section); `### Deferred dispositions` ends with `[DEF-01]`, `[DEF-02]`, `[DEF-03]`

- GIVEN the same scenario
  WHEN the archive completes
  THEN the new `[SEAL-NN]` entry is correctly promoted into `### Sealed dispositions`, the `### Latest pass detail` table is cleared to an empty table, and the `### Trajectory` row is appended — i.e. all four section edits land correctly together

- GIVEN the fix must guarantee the INVARIANT that no section edit writes at an offset invalidated by an earlier edit (the exact mechanism — applying edits in descending pre-edit start-index order, or recomputing section indices after each splice — is chosen in design.md, not prescribed here; a bare swap of two statements is NOT sufficient because the insert branches use heading-anchor offsets that differ from the replace branches' table offsets, and the legacy `### Deferred dispositions` auto-insert already does manual index bookkeeping the mechanism must respect)
  WHEN any combination of {Sealed empty|populated} × {Deferred empty|populated|absent-legacy-auto-insert} occurs with a simultaneous new `Sealed` + new `Deferred` promotion in one pass
  THEN the structural invariants above hold for every combination

- GIVEN a `test_archive_pass.py` regression matrix covering at minimum {empty-Sealed + populated-Deferred} (the common heading-losing case), {populated-Sealed + populated-Deferred}, and the {legacy auto-insert of `### Deferred dispositions`} path — each with a simultaneous Sealed+Deferred promotion
  WHEN the suite runs
  THEN it fails against the pre-fix code and passes after the fix (locking the corruption out), and no existing `archive_pass`/`test_archive_pass` test regresses

- GIVEN R6 is a corruption fix bundled into the 1.7.0 release alongside the (logically independent) directory-naming feature
  WHEN the change is committed and the release is noted
  THEN R6 is a self-contained edit to `archive_pass.py` + `test_archive_pass.py` only (no file overlap with R1–R5, so it is independently revertable) and the 1.7.0 release notes name it as a distinct fix, not buried under the naming feature

## Project Structure

```
telescoping-sdd/
├── scripts/
│   ├── spec_dirname.py                  ← NEW: shared grammar + slugify + CLI
│   ├── arch_config.py                   (existing — no changes)
│   ├── cfc_parser.py                    (existing — no changes)
│   ├── blueprint_common.py              (existing — no changes)
│   └── tests/
│       ├── test_spec_dirname.py         ← NEW: grammar, slugify, round-trip, symmetry, doc-consistency
│       ├── test_hash_and_cascade_parity.py (modified — allowlist its VOCABULARY_SWAP_MAP key; key itself unchanged)
│       ├── test_arch_config.py          (existing — no changes)
│       └── test_cfc_parser_contract.py  (existing — no changes)
├── skills/
│   ├── spec-driven-dev/
│   │   ├── SKILL.md                     (modified — placeholders + bound-vs-standalone prose + migration note)
│   │   ├── scripts/
│   │   │   └── validate_spec.py         (modified — check_dir_identifier + approve gate + CLI help)
│   │   └── references/
│   │       ├── phase-specify.md         (modified — directory naming + prose rule)
│   │       ├── phase-design.md          (modified — directory naming)
│   │       ├── phase-tasks.md           (modified — directory naming)
│   │       ├── examples.md              (modified — directory naming)
│   │       ├── hash-and-cascade.md      (modified — directory naming)
│   │       └── panel-review.md          (modified — specs/<feature>/ refs)
│   └── project-blueprint/
│       ├── scripts/
│       │   ├── validate_blueprint.py    (modified — both inline regexes → spec_dirname; WARN; symlink skip kept)
│       │   └── tests/
│       │       ├── test_cfc_validation.py      (modified — migrate bare-token fixtures; keep symlink test)
│       │       └── test_cfc_cli_integration.py (modified — migrate bare-token fixtures)
│       └── references/
│           └── workflow-overview.md     (modified — feature→spec-dir examples, lines 8/43/81-84)
├── .claude-plugin/
│   └── plugin.json                      (modified — version bump 1.6.0 → 1.7.0)

.claude-plugin/
└── marketplace.json                     (modified — version bump 1.6.0 → 1.7.0)

CLAUDE.md   (modified — line ~96 validate_spec.py example)
README.md   (modified — line ~101 "Output dir" cell)
```

### New Files
- `telescoping-sdd/scripts/spec_dirname.py` — shared grammar module: `is_bound_form`, `is_standalone_form`, `is_valid_slug`, `parse_feature_number`, `slugify`, plus CLI entry point (exact interface is a Decision Point)
- `telescoping-sdd/scripts/tests/test_spec_dirname.py` — pytest suite covering grammar correctness, `slugify` output, round-trips, bare-token backward-compat behavior, and producer/consumer import symmetry

### Modified Files
- `telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py` — import `spec_dirname`; add standalone `check_dir_identifier(spec_dir)`; call it from `validate_spec()` and from the `--approve` path (spec/design/tasks) before `approve_document`; update CLI help/docstring examples to the bound form
- `telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py` — import `spec_dirname`; replace BOTH inline regexes (`classify_spec` + `walk_specs`); surface `malformed-spec-dirname` WARN in validator output (plumbing per design.md); keep symlink skip
- `spec-driven-dev/SKILL.md`, `phase-specify.md`, `phase-design.md`, `phase-tasks.md`, `examples.md`, `hash-and-cascade.md`, `panel-review.md` — replace `specs/<feature-name>/` / `specs/<feature>/` placeholders; add bound-vs-standalone prose rule + migration note
- `project-blueprint/references/workflow-overview.md` — update feature→spec-dir diagram (lines 8, 43, 81–84)
- `CLAUDE.md` (line ~96) and `README.md` (line ~101) — update to the new forms
- `telescoping-sdd/skills/project-blueprint/scripts/tests/test_cfc_validation.py`, `test_cfc_cli_integration.py` — migrate bare-token `specs/F<n>/` fixtures to `specs/F<n>-<slug>/` (the chosen arm per R5); preserve the symlink-skip test
- `telescoping-sdd/scripts/tests/test_hash_and_cascade_parity.py` — its `VOCABULARY_SWAP_MAP` key stays as-is; add it to the doc-consistency test's allowlist (do NOT rewrite the key)
- `telescoping-sdd/scripts/archive_pass.py` — fix the multi-section reassembly so block edits apply bottom-to-top (or recompute indices), eliminating the Sealed-shifts-Deferred corruption (R6)
- `telescoping-sdd/scripts/tests/test_archive_pass.py` — add a regression test for the both-promotions (Sealed + Deferred) corruption scenario
- `telescoping-sdd/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` — bump version to 1.7.0

## Commands

```bash
# Run the full test suite (python/pip are NOT on PATH — use the venv directly)
.venv/bin/pytest telescoping-sdd/ -q

# Run only the new spec_dirname tests
.venv/bin/pytest telescoping-sdd/scripts/tests/test_spec_dirname.py -q

# Validate the plugin after changes
claude plugin validate ./telescoping-sdd

# Validate a spec directory using the new naming (example)
python telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py specs/F1-my-feature/

# Slugify a feature title using the new CLI (file-path invocation, matching how
# validate_spec.py is called — avoids the `-m` sys.path resolution problem since
# telescoping-sdd/scripts/ is not on sys.path by default)
python telescoping-sdd/scripts/spec_dirname.py slugify "My Feature Title"
```

## Boundaries

### Always Do
- Keep the directory-name grammar in ONE shared module (`spec_dirname.py`) that both validators import — this is the load-bearing anti-drift principle, identical to how `cfc_parser.py` centralizes CFC grammar so producer and consumer cannot drift.
- Keep the directory-name contract out-of-band from content hashes and the `--approve`/CFC cascade. Content hashes and approval state are unaffected by a rename (the hash machinery hashes file *contents* only, same principle as the advisory-only architecture-config store). The one observable rename effect is cosmetic: orphan-message text embeds the directory name (`validate_blueprint.py` ~611/647/672), so the message string changes — but no hash, approval, or cascade outcome does.
- Skip symlinked `specs/` entries unconditionally (the existing security guard against symlinks pointing outside the project tree). This is the single acknowledged carve-out from the "nothing feature-ish is skipped silently" doctrine — document it so the contradiction is explicit, not latent.
- Invoke the slug CLI by file path (`python telescoping-sdd/scripts/spec_dirname.py slugify "..."`), NOT `python -m spec_dirname` — the shared scripts dir is not on `sys.path`, so `-m` would `ModuleNotFoundError`.
- Emit actionable FAIL messages that name the offending directory and state the exact rename required (e.g., "rename `specs/F3/` to `specs/F3-<slug>/`").
- Follow the existing `sys.path.append(str(_SHARED_SCRIPTS))` import pattern; do not use `sys.path.insert(0, ...)`, which displaces the caller's `sys.path[0]` (see the existing comment in `validate_blueprint.py`).
- Keep `spec_dirname.py` stdlib-only — no third-party dependencies — matching `cfc_parser.py` and `arch_config.py`.
- Add `from spec_dirname import ...` in both validators using the same style as the existing `from cfc_parser import ...` and `from arch_config import ...` import blocks.

### Ask First
- Any deviation from the four settled decisions in Decision Points (slug cap, CLI shape, approve-gate depth, WARN scope) — these were decided at spec time; re-opening them is a user call, not an implementation choice.
- Any change that would couple the directory-name contract to a content hash or persisted store (it must stay out-of-band).

### Never Do
- Never bump to 2.0.0 — this is a minor release; the target version is 1.7.0.
- Never change the in-file `**PLAN feature identifier:**` grammar (`F<n>` | `n/a`). The `PLAN_FEATURE_ID_LINE_RE` pattern in `validate_spec.py` stays unchanged; the directory name must agree with the identifier, not replace it.
- Never force standalone specs to bind to a PLAN — bare slug directories with in-file `n/a` must remain fully valid.
- Never fold directory-name state into any content hash or write it to any persisted store. It must remain out-of-band from the approval chain.
- Never silently drop a bare `F<n>` directory from `walk_specs` — it must still resolve to the correct `feature_id` (backward compatibility) while emitting a `malformed-spec-dirname` WARN.

## Open Questions

> All questions must be resolved before proceeding to the next phase.

- [x] Q1: **Resolved** — max slug length is **50 characters, a hard FAIL** (`is_valid_slug` returns `False` above the cap). No minimum beyond a single non-empty kebab segment.
- [x] Q2: **Resolved** — the `malformed-spec-dirname` WARN covers **both** bare `F<n>` tokens **and** invalid-slug directories (e.g. `My_Feature`). Nothing feature-ish is skipped silently; only valid standalone slugs are skipped (correctly).
- [x] Q3: **Resolved** — `slugify` is exposed as a **standalone CLI on the new module**, invoked by file path: `python telescoping-sdd/scripts/spec_dirname.py slugify "..."` (no subcommand is added to the validators). File-path invocation is used rather than `python -m spec_dirname` because `telescoping-sdd/scripts/` is not on `sys.path` by default, which would make `-m` fail — this matches how `validate_spec.py` is invoked.
- [x] Q4: **Resolved** — `validate_spec.py --approve` runs **only the directory cross-check** before stamping, not the full `validate_spec()`. Today's behavior (the skill runs validation before approving, by convention) is preserved; no `--force` escape hatch is needed.

## Decision Points

All open questions are resolved (see Open Questions). The settled decisions the design phase must honor:

- `spec_dirname` exposes a standalone CLI invoked by file path — `python telescoping-sdd/scripts/spec_dirname.py slugify "..."` (no validator subcommand; not `-m`, since the scripts dir is not on `sys.path`).
- Max slug length is **50 chars, hard FAIL**.
- `validate_spec.py --approve` runs **only the directory cross-check** before stamping — no `--force` flag is added.
- `walk_specs` emits a `malformed-spec-dirname` WARN for **both** bare `F<n>` tokens and invalid-slug directories.

## Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R1 | End-user projects with existing `specs/F<n>/` directories will hit `missing-slug` FAIL on their first validator run after upgrading to 1.7.0. | High | Med | FAIL message must state the exact rename; renaming does not invalidate any approval hash. Document the migration path ("rename `specs/F<n>/` to `specs/F<n>-<slug>/`") in the updated `spec-driven-dev/SKILL.md`. |
| R2 | End-user projects with free-form directory names (e.g. `specs/checkout-flow/` with in-file `F3`) are silently broken today and will fail loudly after this change. | Med | Med | Actionable FAIL message with exact rename instruction. The silent-skip is the bug being fixed; the FAIL is correct behavior. Document the migration path alongside R1. |
| R3 | The `--approve` path in `validate_spec.py` currently stamps without any validation gate. Adding the directory cross-check may refuse an approval the user expected to succeed. | Low | Low | The cross-check is the ONLY gate added (Q4 resolution) — structural validation is unchanged, so only a genuine dir/identifier mismatch blocks. The refusal message names the blocking check and the exact rename. No `--force` flag is added. |
| R4 | `spec_dirname.py` accidentally introduces a third-party import, breaking the import chain for both validators in stdlib-only environments. | Low | High | Enforce stdlib-only in the spec and in the test suite: `test_spec_dirname.py` should assert that `spec_dirname` imports cleanly without any third-party packages installed. `unicodedata` (stdlib, already used by `cfc_parser.py`) covers Unicode normalization needs. |
| R5 | Doc updates across 10+ files leave old `specs/<feature-name>/` (or `specs/<feature>/`) placeholders in place. | Med | Low | Doc-consistency test with ONE canonical regex matching both spellings, full-repo scan, allowlisting the parity-test `VOCABULARY_SWAP_MAP` key (R5 AC). |
| R6 | The require-slug breaking change silently breaks the existing CFC test suites, which create ~18 bare-token `specs/F<n>/` fixtures. | High | Med | Both CFC test files are in scope (Modified Files); fixtures migrated to `F<n>-<slug>` (the chosen arm — pass-2 review verified no assertion keys on the bare-token dir-name string); covered by an explicit R5 AC. This is the real blast radius of the breaking change — the test suite, not just docs. |
| R7 | `walk_specs` has no `ValidationResult` channel, so "emit a WARN" is not literally implementable without a signature/plumbing change touching 3 call sites. | Med | Med | R3 reworded to require the WARN in validator *output*; the plumbing choice (thread `result`, return tuple, or emit in `validate_plan`) is a design.md decision (Deferred). |

## Success Criteria

- [ ] `telescoping-sdd/scripts/spec_dirname.py` exists, is stdlib-only, and exports `is_bound_form`, `is_standalone_form`, `is_valid_slug`, `parse_feature_number`, and `slugify`
- [ ] `validate_spec.py` emits a blocking FAIL for every failing cell in the directory↔identifier matrix (R2 acceptance criteria), including when `--approve` is invoked
- [ ] `validate_blueprint.py` `walk_specs` resolves `F<n>-<slug>` directories correctly and emits a `malformed-spec-dirname` WARN for bare `F<n>` directories
- [ ] `.venv/bin/pytest telescoping-sdd/ -q` passes with no regressions against pre-existing tests
- [ ] `claude plugin validate ./telescoping-sdd` reports version `1.7.0`
- [ ] No instances of `specs/<feature-name>/` remain in any template, reference, SKILL.md, or CLAUDE.md file
- [ ] `archive_pass.py` no longer corrupts a document when a pass promotes both a `Sealed` and a `Deferred` entry; a `test_archive_pass.py` regression test locks it out (R6)
- [ ] All tests pass

## Panel Review

<!-- Populated by the skill across panel-review passes. archive_pass.py manages
     Trajectory and Sealed dispositions automatically; the synthesizer populates
     Latest pass detail per pass.

     Disposition vocabulary: Addressed / Deferred → <TARGET.md> / Sealed /
     Accepted as risk / User input needed / Halt and re-scope. Sealed and
     Accepted as risk must include "Defense: <reason>" in Notes. Severity tags
     in Latest pass detail are bracketed: [HIGH] / [MED] / [LOW], optionally
     [REGRESSION].

     See SKILL.md "Panel Review section format" for the normative spec. -->

### Trajectory

| Pass | Date       | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes              |
|------|------------|-------|-------------|-----------|----------|--------|--------------------|
| 1    | 2026-06-01 | 7     | 0           | 19        | 2        | 0      | —                  |
| 2    | 2026-06-01 | 0     | 0           | 13        | 1        | 1      | converged (0 HIGH) |
| 3    | 2026-06-02 | 2     | 0           | 8         | 0        | 0      | —                  |

### Sealed dispositions

- `[SEAL-01]` **R4/Modified-Files line numbers will drift if earlier lines…** (pass 2, accepted-as-risk) — Defense: line refs are advisory navigation hints; the regex-based doc-consistency test (R5), not line numbers, is the correctness net.

### Deferred dispositions

- `[DEF-01]` **Exact walk_specs WARN plumbing (thread result / return…** → design.md (pass 1) — Routed because: choosing the emission mechanism is a design-phase decision; R3 captures the output requirement.
- `[DEF-02]` **WARN (blueprint) vs FAIL (spec) on the same dir reads as…** → design.md (pass 1) — Routed because: this is a doc-wording detail to resolve when authoring the prose rule; not blocking and not at-this-phase.
- `[DEF-03]` **FAIL code names diverge across validators for the same…** → design.md (pass 2) — Routed because: adjacent to DEF-02 (WARN/FAIL wording); a cosmetic naming-consistency call for the design phase, not at-this-phase.

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [x] Approved to proceed to next phase
- **Content Hash:** `5440c5af0c680933`
