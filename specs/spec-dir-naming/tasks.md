# Tasks: Strengthen spec-directory filenames across both skills

**Spec:** `specs/spec-dir-naming/spec.md`
**Design:** `specs/spec-dir-naming/design.md`

## Summary

| Task | Description | Requirement | Dependencies | Parallel | Status |
|------|-------------|-------------|--------------|----------|--------|
| T1 | Create `spec_dirname.py` — grammar predicates, `classify_dirname`, `slugify`, CLI | R1, R5 | None | No | Done |
| T2 | Create `test_spec_dirname.py` — full suite (grammar/slugify green at T2; symmetry/matrix/integration/doc-consistency green after T4/T5/T6 — see EXPECTED-RED roster) | R1, R5 | T1 | No | Done |
| T3 | Migrate CFC test fixtures from bare `F<n>` to bound `F<n>-<slug>` form | R5 | T1 | No | Done |
| T4 | Update `validate_blueprint.py` — replace both inline regexes, add WARN helpers | R1, R3 | T1, T3 | Yes (with T5) | Done |
| T5 | Update `validate_spec.py` — add `check_dir_identifier`, gate `--approve`, update CLI help | R1, R2 | T1 | Yes (with T4) | Done |
| T6 | Documentation sweep — update ten doc files to new naming convention | R4 | T4, T5 | No | Done |
| T7 | Version bump — `plugin.json` and `marketplace.json` to 1.7.0 | R4 | T6 | No | Done |
| T8 | Fix `archive_pass.py` reassembly corruption — `_apply_edits` helper + regression matrix | R6 | None | Yes (with T1–T7) | Done |
| T9 | Final integration verification — full suite green, no regressions | R1–R6 | T1–T8 | No | Done |

## Phase 1: Foundation

### - [x] T1: Create `spec_dirname.py` — shared grammar module

- **Requirement:** R1, R5
- **Description:** Create `telescoping-sdd/scripts/spec_dirname.py` with all public grammar predicates (`is_valid_slug`, `is_bound_form`, `is_standalone_form`, `classify_dirname`, `parse_feature_number`, `slugify`) and the `main()` CLI entry point. Stdlib-only; no third-party imports. Compiled patterns at module level. The module docstring must state the leniency contract ("Validity gating MUST use `classify_dirname` or `is_bound_form`, never `parse_feature_number != None`"). The `slugify` pipeline follows DM2 exactly: cap 4096, NFKD + drop `Mn`, lowercase, replace non-slug runs with `-`, strip hyphens, truncate at hyphen boundary to ≤50 chars (hard-truncate first segment if it alone exceeds 50), raise `ValueError` with `repr(title)` on empty result. The `main()` CLI dispatches the `slugify` subcommand with exit codes 0/1/2 per I1.
- **Files:**
  - Read: `telescoping-sdd/scripts/cfc_parser.py` — understand the stdlib-only module style, `unicodedata` usage, module docstring convention, and the `sys.path.append` pattern used when validators import shared modules
  - Read: `telescoping-sdd/scripts/arch_config.py` — understand shared-module style and validator import pattern
  - Create: `telescoping-sdd/scripts/spec_dirname.py`
- **Dependencies:** None
- **Parallel:** No — all R1–R5 tasks depend on this module existing
- **Acceptance Criteria:**
  - GIVEN a call to `spec_dirname.is_bound_form("F3-checkout-flow")`
    WHEN the function executes
    THEN it returns `True` and `spec_dirname.parse_feature_number("F3-checkout-flow")` returns `3`
  - GIVEN a call to `spec_dirname.is_standalone_form("cli-notes-app")`
    WHEN the function executes
    THEN it returns `True` and `spec_dirname.parse_feature_number("cli-notes-app")` returns `None`
  - GIVEN a call to `spec_dirname.is_bound_form("F3")` (bare token, no slug)
    WHEN the function executes
    THEN it returns `False`, but `parse_feature_number("F3")` returns `3` (lenient backward-compat)
  - GIVEN `classify_dirname("F3-checkout-flow")`, `classify_dirname("F3")`, `classify_dirname("cli-notes-app")`, `classify_dirname("My_Feature")`
    WHEN each executes
    THEN they return `"bound"`, `"bare"`, `"standalone"`, `"invalid"` respectively
  - GIVEN zero or leading-zero forms: `classify_dirname("F0")`, `classify_dirname("F007")`, `is_bound_form("F0-x")`, `is_bound_form("F007-x")`
    WHEN each executes
    THEN `classify_dirname("F0")` and `classify_dirname("F007")` return `"bare"`; `is_bound_form("F0-x")` and `is_bound_form("F007-x")` return `False`; `classify_dirname("F0-x")` and `classify_dirname("F007-x")` return `"invalid"`
  - GIVEN `slugify("Checkout Flow (v2)")`
    WHEN the function executes
    THEN it returns a lowercase kebab string satisfying `is_valid_slug(result) == True`
  - GIVEN `slugify("!!!")` or `slugify("🚀")`
    WHEN the function executes
    THEN it raises `ValueError` with a message including `repr(title)`
  - GIVEN `python telescoping-sdd/scripts/spec_dirname.py slugify "My Feature"` executed by file path
    WHEN it runs
    THEN it exits 0 and stdout contains `"my-feature"`; `slugify "!!!"` exits 1; `slugify` (no args) exits 2; `badcmd x` exits 2
- **Tests:** (all written in T2 — T1 and T2 are a TDD pair; T1 implements the module, T2 writes and runs the tests):
  - `test_is_valid_slug`, `test_is_bound_form`, `test_is_standalone_form`, `test_classify_dirname`, `test_parse_feature_number`, `test_parse_feature_number_leniency_documented`
  - `test_slugify_basic_cases`, `test_slugify_accent_folding`, `test_slugify_nfkd_expansion`, `test_slugify_control_character`, `test_slugify_empty_result_raises_value_error`, `test_slugify_truncation_at_hyphen_boundary`, `test_slugify_single_segment_hard_truncation`, `test_slugify_output_always_satisfies_is_valid_slug`
  - `test_slugify_cli_subcommand`, `test_slugify_cli_exit_codes_precise`
  - File: `telescoping-sdd/scripts/tests/test_spec_dirname.py` (created in T2)
- **Verification:** After T1 is written and before T2 is complete, verify the module imports cleanly and the CLI works: `.venv/bin/python telescoping-sdd/scripts/spec_dirname.py slugify "My Feature"` (should print `my-feature`; `python`/`pip` are NOT on PATH in this repo — use the venv interpreter directly). Full pytest verification in T2.

### - [x] T2: Create `test_spec_dirname.py` — full test suite

- **Requirement:** R1, R5
- **Description:** Create `telescoping-sdd/scripts/tests/test_spec_dirname.py` containing the complete test suite described in design.md § Testing Strategy. This is the TDD complement to T1. The file contains six groups of tests: (1) grammar-predicate parametrized tests; (2) `slugify` behavior tests including NFKD expansion, control-char, truncation edge cases, and CLI subprocess tests with exact exit-code assertions; (3) the AST-based producer/consumer symmetry test (`test_no_inline_dirname_regexes_in_validators`) that uses live-import comparison and AST walk to confirm no `F`-prefixed inline directory-name regex survives in `classify_spec` or `walk_specs`; (4) `check_dir_identifier` DM3 matrix tests (all cells, asserting on `result.checks[0][0]` tuple field, NOT on `str(c)` substring) plus the control-char escaping, non-UTF-8, missing-identifier-line, and over-50-char-slug tests — these will pass once T5 is complete; (5) `validate_plan`-level integration tests (`test_validate_plan_malformed_dirname_warns_and_zero_specstates` with `MINIMAL_PLAN` constant, `test_duplicate_feature_dirs_warn`, `test_duplicate_feature_dir_warn_escapes_control_chars`, `test_classify_spec_feature_id_never_none`) — these will pass once T4 is complete; (6) doc-consistency and CLI-help tests (`test_no_stale_placeholder_in_docs` using `DOC_INVENTORY` + `STALE_PLACEHOLDER_RE`, `test_validate_spec_py_no_my_feature_literal`) — these will pass once T5/T6 are complete.
- **Files:**
  - Read: `telescoping-sdd/scripts/spec_dirname.py` — the module under test (created in T1)
  - Read: `telescoping-sdd/scripts/tests/test_arch_config.py` — model for live-import comparison pattern (`test_blueprint_token_vocab_matches_spec_profiles`) used by the AST symmetry test
  - Read: `telescoping-sdd/scripts/tests/test_cfc_parser_contract.py` — model for the contract-symmetry test pattern
  - Read: `telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py` — understand `ValidationResult`, `PLAN_FEATURE_ID_LINE_RE`, and `check_previous_phase_approved` patterns for writing the `check_dir_identifier` matrix tests
  - Read: `telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py` — understand `walk_specs`, `classify_spec`, `validate_plan` signatures for writing the integration tests
  - Create: `telescoping-sdd/scripts/tests/test_spec_dirname.py`
- **Dependencies:** T1
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN `test_spec_dirname.py` exists alongside `test_arch_config.py` and `test_cfc_parser_contract.py`
    WHEN `.venv/bin/pytest telescoping-sdd/scripts/tests/test_spec_dirname.py -q -k "is_valid_slug or is_bound_form or is_standalone_form or classify_dirname or parse_feature or slugify"` is run immediately after T1
    THEN all grammar-predicate and slugify tests pass — this is the only subset green at T2's completion. The filter uses `classify_dirname`, **NOT** bare `classify`, so it cannot accidentally select the integration test `test_classify_spec_feature_id_never_none` (whose name contains the substring `classify`) and report a false-green
  - GIVEN the WHOLE file is run after T1 only (`.venv/bin/pytest telescoping-sdd/scripts/tests/test_spec_dirname.py -q`)
    WHEN it executes
    THEN exactly the EXPECTED-RED roster below is failing/erroring and nothing else — a red in that roster is an intended staging checkpoint, not a broken suite or a test to "fix"
  - **EXPECTED-RED roster** (tests authored here but intentionally red until their gating task lands):
    - green after **T4**: `test_no_inline_dirname_regexes_in_validators`, `test_classify_spec_feature_id_never_none`, `test_classify_spec_resolves_bound_and_bare_feature_id`, `test_validate_plan_malformed_dirname_warns_and_zero_specstates`, `test_duplicate_feature_dirs_warn`, `test_duplicate_feature_dir_warn_escapes_control_chars`
    - green after **T5**: `test_check_dir_identifier_matrix`, `test_check_dir_identifier_hand_typed_long_slug`, `test_check_dir_identifier_non_utf8_spec_md`, `test_check_dir_identifier_missing_identifier_line`, `test_check_dir_identifier_control_char_in_dirname`, `test_validate_spec_py_no_my_feature_literal`
    - green after **T6**: `test_no_stale_placeholder_in_docs`
  - GIVEN the downstream tasks T4/T5/T6 have all landed
    WHEN `.venv/bin/pytest telescoping-sdd/scripts/tests/test_spec_dirname.py -q` is run
    THEN every test in the file passes (the EXPECTED-RED roster is now fully green). The authoritative per-behavior pass/fail gate for each downstream test is owned by the task that implements that behavior (T4/T5/T6 ACs) — it is not re-asserted here, to avoid double-gating the same pytest invocation
- **Tests:**
  - `test_is_valid_slug`, `test_is_bound_form`, `test_is_standalone_form`, `test_classify_dirname`, `test_parse_feature_number`, `test_parse_feature_number_leniency_documented`
  - `test_slugify_basic_cases`, `test_slugify_accent_folding`, `test_slugify_nfkd_expansion`, `test_slugify_control_character`, `test_slugify_empty_result_raises_value_error`, `test_slugify_truncation_at_hyphen_boundary`, `test_slugify_single_segment_hard_truncation`, `test_slugify_output_always_satisfies_is_valid_slug`, `test_slugify_cli_subcommand`, `test_slugify_cli_exit_codes_precise`
  - `test_check_dir_identifier_matrix`, `test_check_dir_identifier_hand_typed_long_slug`, `test_check_dir_identifier_non_utf8_spec_md`, `test_check_dir_identifier_missing_identifier_line`, `test_check_dir_identifier_control_char_in_dirname`
  - `test_no_inline_dirname_regexes_in_validators`
  - `test_validate_spec_py_no_my_feature_literal`, `test_no_stale_placeholder_in_docs`
  - `test_classify_spec_feature_id_never_none`, `test_classify_spec_resolves_bound_and_bare_feature_id`, `test_validate_plan_malformed_dirname_warns_and_zero_specstates`, `test_duplicate_feature_dirs_warn`, `test_duplicate_feature_dir_warn_escapes_control_chars`
  - File: `telescoping-sdd/scripts/tests/test_spec_dirname.py`
- **Verification:** `.venv/bin/pytest telescoping-sdd/scripts/tests/test_spec_dirname.py -q -k "is_valid_slug or is_bound_form or is_standalone_form or classify_dirname or parse_feature or slugify"` passes immediately after T1 (note `classify_dirname`, not bare `classify`, to avoid selecting the integration test). Full file passes only after T4, T5, T6 complete — see the EXPECTED-RED roster above.

## Phase 2: Consumer Prerequisites

### - [x] T3: Migrate CFC test fixtures from bare `F<n>` to bound `F<n>-<slug>` form

- **Requirement:** R5
- **Description:** Migrate all `specs/F<n>/` fixture directory constructions in `test_cfc_validation.py` and `test_cfc_cli_integration.py` that pass through `walk_specs` to the bound `F<n>-<slug>` form, using the structural recipe from design.md C5. Four steps: (1) In `test_cfc_validation.py`, locate and rewrite the `for fid in (1, 2):` loop at ~line 578 that constructs `project_root / "specs" / f"F{fid}"` — replace the `f"F{fid}"` interpolation by adding `FEATURE_DIR_MAP = {1: "F1-alpha", 2: "F2-beta", 36: "F36-enforcement", 11: "F11-lock-order"}` and using `FEATURE_DIR_MAP[fid]` — migrate ONLY the directory-path interpolation; if the loop body also interpolates `F{fid}` into the spec_md content (e.g. a `**PLAN feature identifier:** \`F{fid}\`` line or `# Feature: F{fid}`), those content tokens stay bare `F{fid}` (same identifier-stays-bare rule as guardrail (b)); (2) migrate all literal `tmp_path / "specs" / "F<n>"` sites listed in design.md C5 table using the same map; (3) in `test_walk_specs_skips_symlinks`, migrate the real directory `specs/F1` → `specs/F1-alpha` while leaving the symlink target `specs/F99` bare; (4) in `test_cfc_cli_integration.py`, migrate `specs/F11` → `specs/F11-lock-order`. Do NOT migrate `classify_spec` direct-call tests (~lines 456–555 in `test_cfc_validation.py`) which use `tmp_path / "F1"` outside `specs/` — these call `classify_spec` directly and the backward-compat path is intentional. **Migration guardrails (verified against source — locate by structure, the line numbers are advisory):** (a) In `test_cfc_validation.py` the `specs/F<n>` directory constructions are 10 literal sites + the `f"F{fid}"` loop (~L578): migrate `F1` (L619), `F2` (L628), `F36` at **BOTH** L673 AND L715 (two sites — don't miss the second), the real dir `F1` in the symlink test (L733), and `F1` at L798/L828/L857/L888 — but do **NOT** migrate the `F99` symlink TARGET (L738, stays bare — the R3 symlink-skip carve-out) nor the L456–555 direct-call dirs. (b) In `test_cfc_cli_integration.py`, `F11` appears ~30 times but ONLY the directory construction `tmp_path / "specs" / "F11"` (~L399) migrates to `F11-lock-order`; the `**PLAN feature identifier:** \`F11\`` line (~L393) and EVERY `F11` token in PLAN.md fixture content (DAG edges, MVP tables, dependency rows, CFC participating-features at ~L57–170 and ~L377–442) MUST stay bare `F11` — a blind find-replace corrupts the fixture and breaks unrelated assertions.
- **Files:**
  - Read: `telescoping-sdd/skills/project-blueprint/scripts/tests/test_cfc_validation.py` — identify all `specs/F<n>` construction sites: the `f"F{fid}"` loop at ~line 578, all literal `tmp_path / "specs" / "F<n>"` sites, the symlink test at ~line 725; identify `classify_spec` direct-call tests at ~lines 456–555 to NOT migrate
  - Read: `telescoping-sdd/skills/project-blueprint/scripts/tests/test_cfc_cli_integration.py` — identify `specs/F11` fixture at ~line 399 and the `"F11" in proc.stdout` assertion at ~line 427
  - Modify: `telescoping-sdd/skills/project-blueprint/scripts/tests/test_cfc_validation.py`
  - Modify: `telescoping-sdd/skills/project-blueprint/scripts/tests/test_cfc_cli_integration.py`
- **Dependencies:** T1
- **Parallel:** No — must precede T4 so the CFC suite stays green when `validate_blueprint.py` starts emitting WARNs for bare `F<n>` directories
- **Acceptance Criteria:**
  - GIVEN the migrated test files (before T4 changes `validate_blueprint.py`)
    WHEN `.venv/bin/pytest telescoping-sdd/skills/project-blueprint/scripts/tests/ -q` is run
    THEN all existing CFC tests still pass — fixture migration has no net effect at this stage
  - GIVEN `test_walk_specs_skips_symlinks` after migration
    WHEN it runs
    THEN the real directory uses `specs/F1-alpha`; the symlink target `specs/F99` is unchanged
  - GIVEN the `"F11" in proc.stdout` assertion after migration to `F11-lock-order`
    WHEN it runs
    THEN it still passes because `"F11-lock-order"` contains `"F11"` as a substring
  - GIVEN `classify_spec` direct-call tests at ~lines 456–555
    WHEN inspected after migration
    THEN they use `tmp_path / "F1"` (outside `specs/`) and have not been migrated
- **Tests:** Existing CFC test suite (no new tests in this task)
- **Verification:** `.venv/bin/pytest telescoping-sdd/skills/project-blueprint/scripts/tests/test_cfc_validation.py telescoping-sdd/skills/project-blueprint/scripts/tests/test_cfc_cli_integration.py -q`

## Phase 3: Core Consumers

### - [x] T4: Update `validate_blueprint.py` — replace both inline regexes, add WARN helpers

- **Requirement:** R1, R3
- **Description:** Four changes to `telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py`: (1) Add `from spec_dirname import classify_dirname, parse_feature_number` after the existing `from cfc_parser import ...` block, using the existing `sys.path.append(_SHARED_SCRIPTS)` pattern. (2) In `classify_spec` (~line 354), replace the two lines `m = re.match(r"F(\d+)$", spec_dir.name); feature_id = int(m.group(1)) if m else -1` with `fid = parse_feature_number(spec_dir.name); feature_id = fid if fid is not None else -1`. (3) In `walk_specs` (~line 456), replace `if not re.match(r"F\d+$", entry.name): continue` with `classify_dirname`-dispatch per I5 (bound/bare admitted; standalone skipped silently; invalid skipped silently — WARN emitted separately) — leaving the pre-existing `if entry.is_symlink(): continue` skip (validate_blueprint.py:452) untouched, since per I5 it runs BEFORE name classification and is the acknowledged symlink carve-out from R3; update the `walk_specs` docstring to describe the four-category dispatch. (4) Add `_emit_malformed_dirname_warns(project_root, result)` helper per I3 (dispatches on `classify_dirname`, WARNs for `"bare"` and `"invalid"`, escapes names via `unicode_escape`, guards `specs/` existence internally) and `_emit_duplicate_feature_dir_warns(spec_states, result)` helper per AD8 (builds its OWN `feature_id → [dir names]` map — it must NOT rely on `compute_coverage`'s `state_by_id`, which is built inside a conditional that may not run; WARNs once, naming both dirs via `unicode_escape`, when two non-`-1` entries share a `feature_id`). **Wire the two helpers at DIFFERENT, structurally-located sites — do NOT co-locate them; locate by code structure, NOT the advisory ~line numbers (which are stale-prone, exactly the failure C5 warns about for fixtures):** call `_emit_malformed_dirname_warns(project_root, result)` immediately before EACH `walk_specs(project_root)` call — there are two, one in each branch of the first `if cfc_entries or plan_has_cfc_tags:` / `else:` block; exactly one branch runs per invocation, so it fires once. Call `_emit_duplicate_feature_dir_warns(spec_states, result)` exactly once IMMEDIATELY AFTER that first `if/else` closes (where `spec_states` is fully assigned), and CRITICALLY **outside / above the SEPARATE `if cfc_entries or has_any_cfc_tags:` block** that contains `compute_coverage` — nesting it inside that block silently suppresses the duplicate-dir WARN on non-CFC PLANs (the dogfooding case, which `test_duplicate_feature_dirs_warn`'s CFC-free `MINIMAL_PLAN` exercises). The design's AD8 phrase "before `compute_coverage`" is satisfied by this post-`if/else` placement; do not read it as "inside the coverage block."
- **Files:**
  - Read: `telescoping-sdd/scripts/spec_dirname.py` — `classify_dirname`, `parse_feature_number` public API (from T1)
  - Read: `telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py` — `classify_spec` (~line 354), `walk_specs` (~line 456), `validate_plan` (~lines 1590–1610) to understand exact call sites, `ValidationResult` add-WARN pattern, and `unicode_escape` usage in existing WARN messages
  - Modify: `telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py`
- **Dependencies:** T1, T3
- **Parallel:** Yes (with T5) — T4 modifies only `validate_blueprint.py`; T5 modifies only `validate_spec.py`; no file overlap
- **Acceptance Criteria:**
  - GIVEN a `specs/` directory containing `F3-checkout-flow/` with `spec.md` identifier `` `F3` ``
    WHEN the blueprint validator walks specs
    THEN the directory resolves to `feature_id == 3` and is included in coverage/orphan analysis
  - GIVEN a `specs/` directory containing `F3/` (bare token)
    WHEN the blueprint validator walks specs
    THEN it still resolves with `feature_id == 3` (backward-compat) AND the validator output includes a `malformed-spec-dirname` WARN naming `F3`
  - GIVEN a `specs/` directory containing `checkout-flow/` (standalone slug)
    WHEN the blueprint validator walks specs
    THEN the directory is skipped with no WARN
  - GIVEN a `specs/` directory containing `My_Feature/` (invalid)
    WHEN the blueprint validator walks specs
    THEN a `malformed-spec-dirname` WARN names `My_Feature` AND it contributes zero `SpecState` entries
  - GIVEN both `specs/F3-alpha/` and `specs/F3-beta/` (duplicate feature_id)
    WHEN the blueprint validator walks specs
    THEN exactly one `duplicate-feature-dir` WARN names both directories
  - GIVEN `classify_spec` is called with any standalone or invalid name
    WHEN it runs
    THEN `feature_id` is always `int`, never `None`
  - GIVEN `classify_spec` is called with `F1-alpha` (bound) and with `F1` (bare token)
    WHEN it runs
    THEN `feature_id == 1` in BOTH cases — proving `parse_feature_number` actually resolves the bound `F<n>-<slug>` form (the silent-skip bug R3 exists to kill), not just the bare token. A never-None-only assertion is INSUFFICIENT here: the OLD inline regex `re.match(r"F(\d+)$", "F1-alpha")` also returns a non-None int (`-1`), so the never-None test passes pre-fix AND post-fix and cannot detect the fix
- **Tests:**
  - `test_classify_spec_feature_id_never_none` — from T2, now passes (never-None guard)
  - `test_classify_spec_resolves_bound_and_bare_feature_id` — from T2, now passes (value check: `F1-alpha`→1 and `F1`→1; proves the parse_feature_number swap, not just non-None)
  - `test_validate_plan_malformed_dirname_warns_and_zero_specstates` — from T2, now passes
  - `test_duplicate_feature_dirs_warn` — from T2, now passes
  - `test_no_inline_dirname_regexes_in_validators` — from T2, now passes
  - Existing CFC test suite from T3 (migrated fixtures, must stay green)
  - File: `telescoping-sdd/scripts/tests/test_spec_dirname.py`; `telescoping-sdd/skills/project-blueprint/scripts/tests/`
- **Verification:** `.venv/bin/pytest telescoping-sdd/scripts/tests/test_spec_dirname.py telescoping-sdd/skills/project-blueprint/scripts/tests/ -q`

### - [x] T5: Update `validate_spec.py` — add `check_dir_identifier`, gate `--approve`, update CLI help

- **Requirement:** R1, R2
- **Description:** Three changes to `telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py`: (1) Add `from spec_dirname import classify_dirname` after the existing `from arch_config import ...` block, using the existing `sys.path.append(_SHARED_SCRIPTS)` pattern. (2) Add standalone function `check_dir_identifier(spec_dir: Path) -> ValidationResult` after `check_previous_phase_approved`, implementing the DM3 decision matrix: read `spec_dir.name`, classify via `classify_dirname`, read the `**PLAN feature identifier:**` line from `spec_dir / "spec.md"` via `PLAN_FEATURE_ID_LINE_RE` with `open(..., encoding="utf-8")` wrapped in `except (OSError, UnicodeDecodeError)` (NOT `errors="replace"`), apply the matrix, embed directory names in FAIL messages via `name.encode("unicode_escape").decode("ascii")`, use the five FAIL message templates from I2 verbatim (including decision-criterion prose and hash-safety reassurance). Call it from `validate_spec()` after the `validate_cfc_consumer` call (~line 576) and merge its result; call it from `main()`'s `--approve` path (~line 1096) before `approve_document(target)`, exiting non-zero if not passed. (3) Update the `specs/my-feature/` literal at ALL FIVE occurrences in `validate_spec.py` (three docstring lines ~L20/~L21/~L22, the argparse `epilog` ~L1039, and the `spec_dir` help string ~L1044 — "five occurrences across three regions," not "three sites") to a bound-form example such as `specs/F1-checkout-flow/`. The `test_validate_spec_py_no_my_feature_literal` guard asserts `count == 0`, so it catches any missed occurrence regardless. Locate the `check_dir_identifier` call sites STRUCTURALLY (immediately after the `validate_cfc_consumer(...)` call in `validate_spec()`; and in `main()`'s `--approve` branch immediately before `approve_document(target)`), NOT by the advisory ~line numbers.
- **Files:**
  - Read: `telescoping-sdd/scripts/spec_dirname.py` — `classify_dirname` public API (from T1)
  - Read: `telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py` — `ValidationResult` interface, `PLAN_FEATURE_ID_LINE_RE`, `check_previous_phase_approved` (pattern for standalone check function), `validate_spec()` result-merging at ~line 576, `--approve` path structure at ~line 1096, three `specs/my-feature/` sites at ~L20-22, ~L1039, ~L1044
  - Modify: `telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py`
- **Dependencies:** T1
- **Parallel:** Yes (with T4) — T5 modifies only `validate_spec.py`; T4 modifies only `validate_blueprint.py`; no file overlap
- **Acceptance Criteria:**
  - GIVEN a spec directory named `F3-checkout-flow` with in-file identifier `` `F3` `` (n==m)
    WHEN `validate_spec.py <spec-dir>` is run
    THEN the cross-check passes and validation continues normally
  - GIVEN a spec directory named `F3-checkout-flow` with in-file identifier `` `F5` `` (n≠m mismatch)
    WHEN `validate_spec.py <spec-dir>` is run
    THEN a `dir-identifier-mismatch` FAIL names both the directory-implied number (3) and the in-file identifier (F5), exits non-zero
  - GIVEN a spec directory named `F3-checkout-flow` with in-file identifier `` `n/a` ``
    WHEN `validate_spec.py <spec-dir>` is run
    THEN a `dir-identifier-mismatch` FAIL includes the decision-criterion message ("if this feature is part of a blueprint/PLAN.md, set the in-file identifier to `F3`; if it is standalone, rename the directory to the bare slug `checkout-flow`"), exits non-zero
  - GIVEN a spec directory named `checkout-flow` (standalone) with in-file identifier `` `F3` ``
    WHEN `validate_spec.py <spec-dir>` is run
    THEN a `dir-identifier-mismatch` FAIL includes the symmetric decision-criterion message, exits non-zero
  - GIVEN a spec directory named `F3` (bare token)
    WHEN `validate_spec.py <spec-dir>` is run
    THEN a `missing-slug` FAIL names the directory and points to the slug generator CLI, exits non-zero
  - GIVEN a spec directory named `F3-checkout-flow` with in-file identifier `` `F5` `` (mismatch) and `--approve spec` is run
    WHEN `validate_spec.py <spec-dir> --approve spec` executes
    THEN exits non-zero and `spec.md` is not modified
  - GIVEN `--approve design` or `--approve tasks` where `spec.md` is missing or lacks the identifier line
    WHEN `check_dir_identifier` runs
    THEN it emits `cannot-cross-check` FAIL and exits non-zero
  - GIVEN `validate_spec.py --help` after implementation
    WHEN the docstring, epilog, and help string are read
    THEN none contain `specs/my-feature/`; all show a bound-form example such as `specs/F1-checkout-flow/`
- **Tests:**
  - `test_check_dir_identifier_matrix` — all DM3 cells asserting `result.checks[0][0]` (from T2, now pass)
  - `test_check_dir_identifier_hand_typed_long_slug` — over-50-char slug → `"invalid-slug"` (from T2)
  - `test_check_dir_identifier_non_utf8_spec_md` — non-UTF-8 `spec.md` → `"cannot-cross-check"` (from T2)
  - `test_check_dir_identifier_missing_identifier_line` — missing identifier line → `"cannot-cross-check"` (from T2)
  - `test_check_dir_identifier_control_char_in_dirname` — escaped `\n` → `\\n` in FAIL detail (from T2)
  - `test_validate_spec_py_no_my_feature_literal` — `specs/my-feature/` literal gone (from T2)
  - File: `telescoping-sdd/scripts/tests/test_spec_dirname.py`
- **Verification:** `.venv/bin/pytest telescoping-sdd/scripts/tests/test_spec_dirname.py -q -k "check_dir_identifier or no_my_feature"` and `.venv/bin/pytest telescoping-sdd/skills/spec-driven-dev/scripts/tests/ -q` (existing spec validator tests must stay green)

## Phase 4: Documentation and Release

### - [x] T6: Documentation sweep — update ten doc files to new naming convention

- **Requirement:** R4
- **Description:** Replace `specs/<feature-name>/` and `specs/<feature>/` placeholder spellings in all ten R4-owned doc files with bound (`specs/F<n>-<slug>/`) and standalone (`specs/<slug>/`) forms. The normative update is to `spec-driven-dev/SKILL.md` (always loaded when the skill is relevant): add the explicit prose rule with concrete example pairings (e.g., `specs/F3-checkout-flow/` → in-file identifier `` `F3` `` for a PLAN-bound feature; `specs/checkout-flow/` → in-file identifier `` `n/a` `` for a standalone feature), the one-line rationale for WARN (blueprint) vs FAIL (spec) on the same bare `F<n>` dir, and the migration note (pre-1.7.0 bare `specs/F<n>/` must be renamed to `specs/F<n>-<slug>/`; renaming is hash-safe; lowercase `f<digits>-...` standalone dirs need no migration). Update `workflow-overview.md` bound-feature examples (`specs/user-auth/` → `specs/F1-user-auth/`, `specs/data-models/` → `specs/F2-data-models/`, `specs/api-endpoints/` → `specs/F3-api-endpoints/`, `specs/dashboard/` → `specs/F4-dashboard/`) and the `specs/feature-name/` prose references at lines 8 and 43. Update `CLAUDE.md` line ~96 and `README.md` line ~101 as specified in R4 ACs. Update the remaining five SDD references files to replace all `specs/<feature(-name)?>/` occurrences.
- **Files:**
  - Read: `telescoping-sdd/skills/spec-driven-dev/SKILL.md` — locate all `specs/<feature-name>/` and `specs/<feature>/` occurrences
  - Read: `telescoping-sdd/skills/spec-driven-dev/references/phase-specify.md` — locate occurrences
  - Read: `telescoping-sdd/skills/spec-driven-dev/references/phase-design.md` — locate occurrences
  - Read: `telescoping-sdd/skills/spec-driven-dev/references/phase-tasks.md` — locate occurrences
  - Read: `telescoping-sdd/skills/spec-driven-dev/references/examples.md` — locate occurrences
  - Read: `telescoping-sdd/skills/spec-driven-dev/references/hash-and-cascade.md` — locate occurrences
  - Read: `telescoping-sdd/skills/spec-driven-dev/references/panel-review.md` — locate occurrences
  - Read: `telescoping-sdd/skills/project-blueprint/references/workflow-overview.md` — locate bound-feature examples and `specs/feature-name/` prose at lines 8, 43, 81–84
  - Read: `CLAUDE.md` — locate line ~96
  - Read: `README.md` — locate line ~101
  - Modify: `telescoping-sdd/skills/spec-driven-dev/SKILL.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/phase-specify.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/phase-design.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/phase-tasks.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/examples.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/hash-and-cascade.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/panel-review.md`
  - Modify: `telescoping-sdd/skills/project-blueprint/references/workflow-overview.md`
  - Modify: `CLAUDE.md`
  - Modify: `README.md`
- **Dependencies:** T4, T5
- **Parallel:** No — doc sweep is written against final behavior; must follow the validator changes that define the final naming contract
- **Acceptance Criteria:**
  - GIVEN all ten doc files in `DOC_INVENTORY` after implementation
    WHEN each is searched for `specs/<feature-name>/` and `specs/<feature>/`
    THEN no instances remain (verified by `test_no_stale_placeholder_in_docs`)
  - GIVEN `spec-driven-dev/SKILL.md` after implementation
    WHEN read
    THEN it contains the explicit prose rule with concrete example pairings, the WARN-vs-FAIL rationale, and the migration note for pre-1.7.0 users
  - GIVEN `workflow-overview.md` after implementation
    WHEN searched for `specs/user-auth/`, `specs/data-models/`, `specs/api-endpoints/`, `specs/dashboard/`
    THEN none remain; replaced with `specs/F1-user-auth/`, `specs/F2-data-models/`, `specs/F3-api-endpoints/`, `specs/F4-dashboard/`
  - GIVEN `CLAUDE.md` (line ~96) and `README.md` (line ~101) after implementation
    WHEN read
    THEN `CLAUDE.md`'s `validate_spec.py` example shows `specs/F1-<slug>/`; README's Output-dir cell shows `specs/F<n>-<slug>/`
- **Tests:**
  - `test_no_stale_placeholder_in_docs` — from T2, passes after this task
  - File: `telescoping-sdd/scripts/tests/test_spec_dirname.py`
- **Verification:** `.venv/bin/pytest telescoping-sdd/scripts/tests/test_spec_dirname.py -q -k "no_stale_placeholder"`

### - [x] T7: Version bump — `plugin.json` and `marketplace.json` to 1.7.0

- **Requirement:** R4
- **Description:** Bump the `version` field from `1.6.0` to `1.7.0` in both `telescoping-sdd/.claude-plugin/plugin.json` (authoritative) and `.claude-plugin/marketplace.json` (mirror), in lockstep, per the repo's version-bump convention stated in `CLAUDE.md`. This is the last code/config task — bump only after the full feature is complete and green.
- **Files:**
  - Read: `telescoping-sdd/.claude-plugin/plugin.json` — current version field
  - Read: `.claude-plugin/marketplace.json` — current version field for the `telescoping-sdd` plugin entry
  - Modify: `telescoping-sdd/.claude-plugin/plugin.json`
  - Modify: `.claude-plugin/marketplace.json`
- **Dependencies:** T6
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN both files after implementation
    WHEN their `version` fields are read
    THEN both report `1.7.0` (lockstep). The manual `claude plugin validate` confirmation is consolidated into T9's final check, not repeated here
- **Tests:** None (version fields are not pytest-testable)
- **Verification:** `grep '"version"' telescoping-sdd/.claude-plugin/plugin.json .claude-plugin/marketplace.json` (both must show `1.7.0`); the `claude plugin validate ./telescoping-sdd` confirmation runs once in T9

## Phase 5: Independent Track — R6 Bug Fix

### - [x] T8: Fix `archive_pass.py` reassembly corruption — `_apply_edits` helper + regression matrix

- **Requirement:** R6
- **Description:** Independent track with zero file overlap with T1–T7. Internal order per the design: write the regression matrix tests FIRST (confirming they are red against current code), then refactor `archive_pass.py` until the matrix is green AND the existing archive_pass test suite (what the design calls the "T3–T10 archive_pass tests" — i.e. the pre-existing test functions in `test_archive_pass.py`, NOT to be confused with the T-numbered tasks in this document) stays green. Two deliverables: (A) In `test_archive_pass.py`, add five new tests: `test_reassembly_empty_sealed_populated_deferred` (the primary corruption case: `### Sealed dispositions` is empty/insert-branch; `### Deferred dispositions` has `[DEF-01]`/`[DEF-02]`/replace-branch; `### Latest pass detail` has one new Sealed row + one new Deferred row — this is the case that lost the heading in the wild); `test_reassembly_populated_sealed_populated_deferred` (both sections pre-populated, both replace branches, net-positive line delta in Sealed); `test_reassembly_legacy_auto_insert_deferred` (no `### Deferred dispositions` heading at all, triggers the auto-insert at ~L663–671, plus simultaneous Sealed + Deferred); plus two pure-unit tests: `test_apply_edits_rejects_overlapping_ranges` (asserts `AssertionError` on a synthetic overlapping list) and `test_apply_edits_applies_descending` (two disjoint edits land correctly regardless of input order). Matrix tests use `_run_archive_pass([str(artifact), "--phase", "2"])` subprocess then call a shared `_assert_panel_intact(text)` helper that checks each heading's count independently (`text.count(h) == 1`), locates the unique `### Deferred dispositions` window, asserts every `[DEF-NN]` token falls within that window and appears only once, and verifies `[SEAL-NN]`/cleared-Latest/appended-Trajectory. (B) In `archive_pass.py`, add module-level `_apply_edits(lines: list[str], edits: list[tuple[int, int, list[str]]]) -> list[str]` per I6 (assert pairwise non-overlap; sort by `start` descending; apply each as `lines[:start] + new_block + lines[end:]`; return fresh list). Refactor the reassembly block (~L954–988): after the existing auto-insert + index recomputation (unchanged), collect 1–4 `(start, end, new_block)` tuples conditionally (under their existing guards — `latest_to_clear`, `new_seals`, `new_defs and d_start is not None`, always-Trajectory), call `_apply_edits` once. Drop the now-redundant `new_lines = lines[:]` copy.
- **Files:**
  - Read: `telescoping-sdd/scripts/archive_pass.py` — `replace_block` helper (~L553), the full reassembly block (~L954–988), auto-insert bookkeeping (~L652–682) which runs before the reassembly and must remain unchanged
  - Read: `telescoping-sdd/scripts/tests/test_archive_pass.py` — existing test functions (the "T3–T10" suite in the design's terminology), `_run_archive_pass` subprocess helper, `_legacy_artifact_without_deferred_section` fixture, `_load_archive_pass` internal-function loader
  - Modify: `telescoping-sdd/scripts/archive_pass.py`
  - Modify: `telescoping-sdd/scripts/tests/test_archive_pass.py`
- **Dependencies:** None
- **Parallel:** Yes (with T1–T7) — zero file overlap; logically independent
- **Acceptance Criteria:**
  - GIVEN a document with `[DEF-01]`/`[DEF-02]` in `### Deferred dispositions` and one new Sealed + one new Deferred row in `### Latest pass detail`
    WHEN `archive_pass.py <doc> --phase 2` is run
    THEN `### Sealed dispositions`, `### Deferred dispositions`, `### Latest pass detail`, and `## Approval` each appear exactly once; every `[DEF-NN]` token appears exactly once within the Deferred window; `### Deferred dispositions` ends with `[DEF-01]`, `[DEF-02]`, `[DEF-03]`; the new `[SEAL-NN]` is correctly promoted; Latest is cleared; Trajectory row is appended
  - GIVEN any combination of {Sealed empty|populated} × {Deferred empty|populated|absent-legacy-auto-insert} with a simultaneous new Sealed + new Deferred
    WHEN `archive_pass.py` runs
    THEN the structural invariants hold (covered by all three matrix tests)
  - GIVEN `test_apply_edits_rejects_overlapping_ranges`
    WHEN it runs
    THEN it asserts `AssertionError` on a synthetic overlapping edit list
  - GIVEN all three R6 matrix tests run against pre-fix code
    WHEN checked
    THEN they FAIL; after the fix, they PASS — the regression is mechanically locked out
  - GIVEN the pre-existing archive_pass test suite
    WHEN `.venv/bin/pytest telescoping-sdd/scripts/tests/test_archive_pass.py -q` is run after the refactor
    THEN all pre-existing tests pass without modification — the refactor preserves all promotion semantics
- **Tests:**
  - `test_reassembly_empty_sealed_populated_deferred`
  - `test_reassembly_populated_sealed_populated_deferred`
  - `test_reassembly_legacy_auto_insert_deferred`
  - `test_apply_edits_rejects_overlapping_ranges`
  - `test_apply_edits_applies_descending`
  - File: `telescoping-sdd/scripts/tests/test_archive_pass.py`
- **Verification:** Red-before — BEFORE refactoring, run the three reassembly matrix tests against the UNMODIFIED `archive_pass.py` and confirm all three FAIL (the `_apply_edits` unit tests are also written first; `_apply_edits` is module-private, reached via `_load_archive_pass()`, not imported as public API). Green-after — `.venv/bin/pytest telescoping-sdd/scripts/tests/test_archive_pass.py -q`: all new matrix + unit tests pass AND every pre-existing test stays green.

## Phase 6: Integration Verification

### - [x] T9: Final integration verification — full suite green, no regressions

- **Requirement:** R1–R6
- **Description:** Verification-only task; no code changes. Run the complete test suite and confirm all tests pass with no regressions. Perform the manual `claude plugin validate ./telescoping-sdd` step to confirm the plugin manifest is valid at version 1.7.0. A passing full suite plus a clean `claude plugin validate` output satisfies all success criteria from spec.md.
- **Files:**
  - Read: Any modified/created file needed for debugging a failing test
- **Dependencies:** T1, T2, T3, T4, T5, T6, T7, T8
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN all tasks T1–T8 complete
    WHEN `.venv/bin/pytest telescoping-sdd/ -q` is run
    THEN all tests pass (incl. `test_spec_dirname.py` and the R6 matrix in `test_archive_pass.py`); no pre-existing test regresses
  - GIVEN spec.md § Success Criteria
    WHEN each checkbox is walked
    THEN every item is satisfied (per that list — not re-transcribed here). NOTE: the R3 blueprint-side WARN paths (`malformed-spec-dirname`, `duplicate-feature-dir`) are verified by the pytest suite ONLY — this repo has no `blueprint/PLAN.md`, so the manual `claude plugin validate` step does NOT exercise them; do not read a clean plugin-validate as end-to-end proof of R3
  - GIVEN this repo's own `specs/spec-dir-naming/` (standalone slug, in-file identifier `n/a`) under the now-active `check_dir_identifier` gate
    WHEN `.venv/bin/python telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py specs/spec-dir-naming/` is run
    THEN it PASSES the cross-check (standalone + `n/a` is the PASS cell), so enabling the approve-gate does not retroactively self-block re-approval of this feature's own artifacts
  - GIVEN `claude plugin validate ./telescoping-sdd` run manually (external CLI)
    WHEN it executes
    THEN it reports version `1.7.0` with no validation errors
- **Tests:** Full suite
- **Verification:** `.venv/bin/pytest telescoping-sdd/ -q` (automated); `claude plugin validate ./telescoping-sdd` (manual)

## Implementation Order

1. **T8** — Start immediately on the independent R6 track. Write the corruption regression matrix first (red against current `archive_pass.py`), then refactor the reassembly block with `_apply_edits` until the matrix is green and the existing archive_pass test suite stays green. No dependency on T1–T7.
2. **T1** — Create `spec_dirname.py`. The foundational grammar module; every subsequent R1–R5 task depends on it. No dependencies.
3. **T2** — Create `test_spec_dirname.py` immediately after T1 as the TDD pair. Grammar and slugify tests are green at this point. The `check_dir_identifier` matrix tests, integration tests, and doc-consistency tests are written now but pass only after T4/T5/T6 complete.
4. **T3** — Migrate the CFC test fixtures before touching `validate_blueprint.py`. No production-code changes; the existing CFC suite stays green. This step isolates the fixture migration as a safe pre-requisite.
5. **T4 and T5 (parallel)** — After T1, T2, T3 are complete, T4 and T5 can run concurrently: they modify disjoint files (`validate_blueprint.py` vs `validate_spec.py`) and depend on the same T1 foundation. After both are done, all symmetry, matrix, and integration tests in `test_spec_dirname.py` pass.
6. **T6** — Documentation sweep after T4 and T5, so the prose captures the final behavior. The `test_no_stale_placeholder_in_docs` test goes green at this step.
7. **T7** — Version bump last, once the feature is fully implemented and the test suite is green.
8. **T9** — Run the full suite and perform the manual `claude plugin validate` check as final confirmation.

## Open Questions

> All questions are resolved; no open questions block implementation.

- [x] Q1: `walk_specs` WARN plumbing — option (c): `_emit_malformed_dirname_warns` helper in `validate_plan`. Resolved in design.md AD2.
- [x] Q2: `None`→`-1` adaptation inside `classify_spec`. Resolved in design.md AD3/I4.
- [x] Q3: `slugify` raises `ValueError` on empty result; CLI catches, exits 1. Resolved in design.md AD4/I1.
- [x] Q4: NFKD accent folding, stdlib only, 4096-char input cap. Resolved in design.md AD5/DM2.
- [x] Q5: `check_dir_identifier` returns a `ValidationResult`. Resolved in design.md AD6/I2.
- [x] Q6: `classify_dirname` is the single dispatch point for walk and warn. Resolved in design.md AD2/DM1.
- [x] Q7: `except (OSError, UnicodeDecodeError)` guard, NOT `errors="replace"`. Resolved in design.md I2.
- [x] Q8: Doc-consistency test uses defined inventory (not rglob). Resolved in design.md Testing Strategy.

## Panel Review

<!-- Terminal Phase: must NOT contain a ### Deferred dispositions sub-section. archive_pass.py rejects --terminal archives with Deferred rows; validate_blueprint.py hard-fails for PLAN.md specifically. -->
<!-- Populated by the skill across panel-review passes. archive_pass.py manages
     Trajectory and Sealed dispositions automatically; the synthesizer populates
     Latest pass detail per pass.

     This is the last artifact phase before implementation; concerns cannot be
     deferred forward. Disposition vocabulary: Addressed / Sealed / Accepted as
     risk / User input needed / Halt and re-scope. Sealed and Accepted as risk
     must include "Defense: <reason>" in Notes. Severity tags in Latest pass
     detail are bracketed: [HIGH] / [MED] / [LOW], optionally [REGRESSION].

     See SKILL.md "Panel Review section format" for the normative spec. -->

### Trajectory

| Pass | Date       | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes                           |
|------|------------|-------|-------------|-----------|----------|--------|---------------------------------|
| 1    | 2026-06-02 | 5     | 0           | 16        | 0        | 2      | tags=d0u0c5                     |
| 2    | 2026-06-02 | 0     | 1           | 3         | 0        | 3      | converged (0 HIGH); tags=d0u0c0 |

### Sealed dispositions

- `[SEAL-01]` **T1/T2 split adds bookkeeping vs design's single step-1 unit** (pass 1, user-directed) — Defense: deliberate TDD-pair split keeps the tests-authored-early-green-late staging explicit (EXPECTED-RED roster) and each task within sizing; merging yields one ~28-test+module task.
- `[SEAL-02]` **T7 could fold into T6; duplicate plugin-validate AC across…** (pass 1, user-directed) — Defense: version bump kept as an independently-revertable release-hygiene step per repo convention; duplicate validate-AC removed (now only in T9).
- `[SEAL-03]` **T4 names only `is_symlink()` as the untouched pre-walk…** (pass 2, accepted-as-risk) — Defense: anything not named in the replace instruction stays untouched by default; the `is_dir()` guard is outside the edit scope and unaffected.
- `[SEAL-04]` **T4's "locate by structure, not line numbers" admonition…** (pass 2, accepted-as-risk) — Defense: the precision is correct and harmless; re-editing the load-bearing wiring paragraph in a converged doc to shave words risks a fresh regression for no functional gain.
- `[SEAL-05]` **Advisory `~line` numbers across T3/T4/T5 confirmed stale vs…** (pass 2, accepted-as-risk) — Defense: pass-1 made structural anchors the binding instruction and they all resolve to real unique sites; line numbers are explicitly advisory navigation hints.

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [x] Approved to proceed to implementation
- **Content Hash:** `65b3d96a87f70a82`
