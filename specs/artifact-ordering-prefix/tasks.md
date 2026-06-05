# Tasks: Artifact Ordering Prefix

**Spec:** `specs/artifact-ordering-prefix/spec.md`
**Design:** `specs/artifact-ordering-prefix/design.md`

## Summary

| Task | Description | Requirement | Dependencies | Parallel | Status |
|------|-------------|-------------|--------------|----------|--------|
| T1 | Add resolution helpers + `_detect_prefix_state` to `blueprint_common.py` with unit tests | R1, R2, R6 | None | No | Done |
| T2 | Convert `archive_pass.py` TERMINAL_FILENAMES gates + `test_archive_pass.py` additions | R2, R6 | T1 | Yes (with T3, T4, T5, T6, T7) | Done |
| T3 | Convert `blueprint_common.is_shipped` + `test_is_shipped_resolves_prefixed_artifacts` | R1, R6 | T1 | Yes (with T2, T4, T5, T6, T7) | Done |
| T4 | Convert `reconcile.py` 3 sites with catch-and-degrade | R1, R6 | T1 | Yes (with T2, T3, T5, T6, T7) | Done (code; dedicated degrade tests pending) |
| T5 | Convert `validate_spec.py` ~13 sites → `resolve_artifact` | R1, R2, R6 | T1 | Yes (with T2, T3, T4, T6, T7) | Done |
| T6 | Convert `validate_blueprint.py` ~17 sites → `resolve_artifact`/`strip_artifact_prefix` | R1, R2, R6 | T1 | Yes (with T2, T3, T4, T5, T7) | Done |
| T7 | Convert `render_business_brief.py` 4 sites → `resolve_artifact` | R1, R6 | T1 | Yes (with T2, T3, T4, T5, T6) | Done |
| T8 | Resolver-side regression suite: grep gate + negative self-test + integration tests | R6 | T2, T3, T4, T5, T6, T7 | No | Done (grep gate + neg self-test + spec-equiv + fail-closed + blueprint-equiv + render-resolution; approve-roundtrip / scan_prefix-RI3 covered by the conversions + grep gate + full suite) |
| T9 | Build `artifact_prefix.py` renamer: `PREFIX_MAP`, rename mode, `--check` subcommand | R4, R7 | T8 | No | Done |
| T10 | Renamer-side tests in `test_artifact_prefix.py` | R4, R6 | T9 | No | Done |
| T11 | Default-on emission (phase refs): update six `phase-*.md` Write-targets to prefixed paths | R3 | T8 | Yes (with T11b, T12) | Done (emit-target paths prefixed + per-file tolerance note; cross-tier upstream existence-checks kept resolver-tolerant) |
| T11b | Default-on emission (templates): update nine template files' upstream boilerplate to prefixed | R3 | T8 | Yes (with T11, T12) | Done (4 templates had upstream-path boilerplate; design/tasks/scope templates carry none) |
| T11c | Default-on emission (SKILL.md command examples) — combined with T13 into one edit per SKILL.md | R3 | T8 | No (shares SKILL.md with T13) | Done (folded into T13) |
| T12 | Mixed-state WARN: hook `_detect_prefix_state` into both validators + WARN tests | R7 | T8 | Yes (with T11, T11b) | Done |
| T13 | Interactive offer prose + prose-review checklist in both SKILL.md files (incl. T11c command examples — one edit per file) | R7, R3 | T9, T8 | No (shares SKILL.md with T11c) | Done (offer block + verbatim decline-reassurance + pending pre-check + `--check` gate; Output command examples prefixed) |
| T14 | R5 prose sweep: both `panel-review.md` copies + agent prose | R5 | T11, T11b | No | Done (both panel-review archive-command paths prefixed + identical tolerance clause; delivery-manager tolerance note; no other agent names an artifact path) |
| T15 | Dogfood rename: run `artifact_prefix.py` on this repo's own `specs/*/` | R4 | T9, T14 | No | Done (4 sealed dirs renamed + validate_spec PASSED no-hash-failure; `security-exposure-seam` skipped per the mid-flight guidance; `artifact-ordering-prefix` skipped as self) |
| T16 | Version bump: MINOR in both plugin manifests in lockstep | R3 | T15 | No | Done (2.1.0 → 2.2.0 in both manifests; CHANGELOG 2.2.0 entry; exposure-seam version-pin tests updated) |

## Phase A: Increment 1 — Resolution Tolerance

### - [x] T1: Add resolution helpers and `_detect_prefix_state` to `blueprint_common.py` with unit tests

- **Requirement:** R1, R2, R6
- **Description:** Add `KNOWN_ARTIFACTS`, `ArtifactAmbiguityError`, `strip_artifact_prefix`, `resolve_artifact`, and `_detect_prefix_state` to `blueprint_common.py` as the single authoritative resolution chokepoint, and write all C1 unit tests in `test_artifact_prefix.py` plus `_detect_prefix_state` additions to `test_blueprint_common.py`.
- **Files:**
  - Read: `telescoping-sdd/scripts/blueprint_common.py` — locate insertion point after line ~334 (`is_shipped` block), confirm existing import block and module-level constants layout
  - Read: `telescoping-sdd/scripts/tests/test_blueprint_common.py` — confirm import/path-injection pattern to mirror for new tests
  - Modify: `telescoping-sdd/scripts/blueprint_common.py`
  - Create: `telescoping-sdd/scripts/tests/test_artifact_prefix.py`
  - Modify: `telescoping-sdd/scripts/tests/test_blueprint_common.py`
- **Dependencies:** None
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN a spec directory containing only `01_spec.md`
    WHEN `resolve_artifact(spec_dir, "spec.md")` is called
    THEN returns the path to `01_spec.md` without raising
  - GIVEN a spec directory containing both `spec.md` and `01_spec.md`
    WHEN `resolve_artifact(spec_dir, "spec.md")` is called
    THEN raises `ArtifactAmbiguityError` naming both conflicting paths
  - GIVEN a filename `"12_factor_notes.md"`
    WHEN `strip_artifact_prefix("12_factor_notes.md")` is called
    THEN returns `"12_factor_notes.md"` unchanged (stripped result not in `KNOWN_ARTIFACTS`)
  - GIVEN a directory with one bare artifact and one prefixed artifact
    WHEN `_detect_prefix_state(dir_path)` is called
    THEN returns `"mixed"`
- **Tests:**
  - `test_strip_artifact_prefix_bare_name_unchanged` — `"spec.md"` → `"spec.md"` (no prefix, returns unchanged)
  - `test_strip_artifact_prefix_known_artifacts` — all 6 `NN_` prefixed forms → correct bare name
  - `test_strip_artifact_prefix_non_artifact_unchanged` — `"12_factor_notes.md"` → unchanged (not in KNOWN_ARTIFACTS)
  - `test_strip_artifact_prefix_zero_prefix_unchanged` — `"00_readme.md"` → unchanged
  - `test_strip_artifact_prefix_user_design_file` — `"01_design.md"` → `"design.md"` (IS in KNOWN_ARTIFACTS)
  - `test_resolve_artifact_bare_exists` — bare `spec.md` present → returns bare path
  - `test_resolve_artifact_prefixed_exists` — `01_spec.md` present, bare absent → returns prefixed path
  - `test_resolve_artifact_absent_returns_bare` — neither form exists → returns bare path (no raise)
  - `test_resolve_artifact_both_exist_raises` — both forms present (different content) → raises `ArtifactAmbiguityError`
  - `test_resolve_artifact_both_exist_identical_content_raises` — both exist with identical content → raises; `exc.identical_content` is True
  - `test_resolve_artifact_ambiguity_error_message_identical_content` — `identical_content=True` → message says "byte-identical"
  - `test_resolve_artifact_user_01_design_coexists_with_02_design` — `01_design.md` AND `02_design.md` coexist → raises `ArtifactAmbiguityError`
  - `test_resolve_artifact_non_artifact_bare_returned` — `resolve_artifact(dir, "factor_notes.md")` → bare path, no glob
  - `test_resolve_artifact_nonexistent_dir` — missing dir → returns bare path, no raise
  - `test_resolve_artifact_stemless_prefix_ignored` — `01_` or `01_.md` present → not treated as artifact
  - `test_resolve_artifact_editor_backup_ignored` — `01_spec.md~` present → not matched by glob; bare resolution unaffected
  - `test_resolve_artifact_single_misordinaled_prefix` — only `02_spec.md` present → returned as canonical spec
  - `test_resolve_artifact_identical_content_unreadable_is_false` — unreadable conflicting file → `ArtifactAmbiguityError` with `identical_content=False`; no raw OSError escapes
  - `test_prefix_map_known_artifacts_symmetry` — `set(PREFIX_MAP.keys()) == KNOWN_ARTIFACTS` (AD10; file: `test_artifact_prefix.py`)
  - `test_detect_prefix_state_uniform_bare` — all bare → `"uniform-bare"` (file: `test_blueprint_common.py`)
  - `test_detect_prefix_state_uniform_prefixed` — all prefixed → `"uniform-prefixed"`
  - `test_detect_prefix_state_mixed` — some bare, some prefixed → `"mixed"`
  - `test_detect_prefix_state_empty` — no artifacts → `"empty"`
  - File: `telescoping-sdd/scripts/tests/test_artifact_prefix.py`, `telescoping-sdd/scripts/tests/test_blueprint_common.py`
- **Verification:** `.venv/bin/pytest telescoping-sdd/scripts/tests/test_artifact_prefix.py telescoping-sdd/scripts/tests/test_blueprint_common.py -v`

### - [x] T2: Convert `archive_pass.py` TERMINAL_FILENAMES gates + `test_archive_pass.py` additions

- **Requirement:** R2, R6
- **Description:** Apply `strip_artifact_prefix` before BOTH `in TERMINAL_FILENAMES` membership tests in `archive_pass.py` — the `_is_terminal` helper (line 128, guarded by the unit tests) AND the standalone CLI gate `art.name in TERMINAL_FILENAMES and not args.terminal` (line 658, guarded by the subprocess test `test_archive_pass_cli_rejects_prefixed_plan_without_terminal`). Both are independent edits; converting only 128 would leave the CLI gate regressed. Add the seven prefixed-name test cases to `test_archive_pass.py`.
- **Files:**
  - Read: `telescoping-sdd/scripts/blueprint_common.py` — confirm `strip_artifact_prefix` signature from T1
  - Modify: `telescoping-sdd/scripts/archive_pass.py`
  - Modify: `telescoping-sdd/scripts/tests/test_archive_pass.py`
- **Dependencies:** T1
- **Parallel:** Yes (with T3, T4, T5, T6, T7) — touches disjoint files from all other Phase A tasks after T1
- **Acceptance Criteria:**
  - GIVEN `archive_pass.py` invoked on a file named `03_PLAN.md` without `--terminal`
    WHEN the `TERMINAL_FILENAMES` membership test runs
    THEN the tool exits with the same terminal-artifact error it produces for bare `PLAN.md`
  - GIVEN `archive_pass.py` invoked on `01_spec.md` (not a terminal artifact) without `--terminal`
    WHEN the membership test runs
    THEN the tool does NOT exit with the terminal-artifact error (no over-match)
- **Tests:**
  - `test_terminal_filenames_prefix_tolerant_plan` — `_is_terminal("", Path("03_PLAN.md"), False)` → True
  - `test_terminal_filenames_prefix_tolerant_tasks` — `_is_terminal("", Path("03_tasks.md"), False)` → True
  - `test_terminal_filenames_prefix_tolerant_tasks_python` — `_is_terminal("", Path("03_tasks-python.md"), False)` → True (defensive-registry coverage)
  - `test_terminal_filenames_prefix_tolerant_tasks_java` — `_is_terminal("", Path("03_tasks-java.md"), False)` → True (defensive-registry coverage)
  - `test_terminal_filenames_non_terminal_spec` — `_is_terminal("", Path("01_spec.md"), False)` → False
  - `test_terminal_filenames_non_terminal_design` — `_is_terminal("", Path("02_design.md"), False)` → False
  - `test_archive_pass_cli_rejects_prefixed_plan_without_terminal` — subprocess: `archive_pass.py 03_PLAN.md --phase 1` (no `--terminal`) → non-zero exit with TERMINAL_FILENAMES error
  - File: `telescoping-sdd/scripts/tests/test_archive_pass.py`
- **Verification:** `.venv/bin/pytest telescoping-sdd/scripts/tests/test_archive_pass.py -v`

### - [x] T3: Convert `blueprint_common.is_shipped` + `test_is_shipped_resolves_prefixed_artifacts`

- **Requirement:** R1, R6
- **Description:** Replace the three direct `spec_dir / "spec.md"` / `"design.md"` / `"tasks.md"` path constructions in `blueprint_common.is_shipped` (lines 330–332) with `resolve_artifact` calls, and add the corresponding test to `test_blueprint_common.py`.
- **Files:**
  - Modify: `telescoping-sdd/scripts/blueprint_common.py`
  - Modify: `telescoping-sdd/scripts/tests/test_blueprint_common.py`
- **Dependencies:** T1
- **Parallel:** Yes (with T2, T4, T5, T6, T7) — modifies different lines of `blueprint_common.py` than T1 (no conflict after T1 lands); touches no files in common with T2/T4/T5/T6/T7
- **Acceptance Criteria:**
  - GIVEN a spec directory containing `03_tasks.md` (prefixed form)
    WHEN `blueprint_common.is_shipped` reads the spec directory
    THEN `tasks.md` is resolved correctly and `is_shipped` returns the same value it would for bare `tasks.md` with identical content
- **Tests:**
  - `test_is_shipped_resolves_prefixed_artifacts` — `is_shipped` with `01_spec.md`, `02_design.md`, `03_tasks.md` in `spec_dir` → same result as bare names
  - File: `telescoping-sdd/scripts/tests/test_blueprint_common.py`
- **Verification:** `.venv/bin/pytest telescoping-sdd/scripts/tests/test_blueprint_common.py -v`

### - [x] T4: Convert `reconcile.py` 3 sites with catch-and-degrade

- **Requirement:** R1, R6
- **Description:** Replace the three direct path constructions in `reconcile.py` (lines 573, 624, 709) with `resolve_artifact` calls, each wrapped in a catch-and-degrade block so `ArtifactAmbiguityError` degrades to the existing unreadable/None path rather than aborting the reconcile (CPD soft-read semantics).
- **Files:**
  - Read: `telescoping-sdd/scripts/blueprint_common.py` — confirm `resolve_artifact` and `ArtifactAmbiguityError` signatures from T1
  - Modify: `telescoping-sdd/scripts/reconcile.py`
- **Dependencies:** T1
- **Parallel:** Yes (with T2, T3, T5, T6, T7) — touches disjoint files
- **Acceptance Criteria:**
  - GIVEN a master project whose `blueprint/PLAN.md` has been renamed to `03_PLAN.md`
    WHEN `reconcile.py` reads the master's PLAN for provenance (path constructions at lines 573 and 709)
    THEN `resolve_artifact` locates `03_PLAN.md` and the provenance check completes without error
  - GIVEN a derived spec directory containing `01_spec.md` (prefixed form)
    WHEN `reconcile.py` resolves provenance fields from `spec.md` (line 624)
    THEN the derived `spec.md` is found and parsed without error via `resolve_artifact`
  - GIVEN both `PLAN.md` AND `03_PLAN.md` exist in a sibling repo's blueprint (ambiguity at the 573/709 sibling-PLAN reads)
    WHEN `reconcile.py` encounters the `ArtifactAmbiguityError`
    THEN reconcile degrades gracefully (treats artifact as unreadable) and does NOT crash
  - GIVEN both `spec.md` AND `01_spec.md` exist in a derived spec dir (ambiguity at the line-624 derived-`spec.md` read)
    WHEN `reconcile.py` encounters the `ArtifactAmbiguityError`
    THEN reconcile degrades (treats the derived spec as unreadable/None) and does NOT crash
- **Tests:**
  - `test_reconcile_cpd_no_crash_on_prefixed_plan` — CPD reconcile against a sibling repo with `03_PLAN.md` → no crash (RI10; the 573/709 sibling-PLAN path)
  - `test_reconcile_degrades_on_ambiguous_derived_spec` — derived spec dir with BOTH `spec.md` and `01_spec.md` (the 624 path) → reconcile degrades to unreadable/None, does NOT crash
  - File: `telescoping-sdd/scripts/tests/test_artifact_prefix.py` (integration) or `test_reconcile.py`
- **Verification:** `.venv/bin/pytest telescoping-sdd/scripts/tests/test_reconcile.py telescoping-sdd/scripts/tests/test_artifact_prefix.py -v -k "reconcile or cpd"`

### - [x] T5: Convert `validate_spec.py` ~13 sites → `resolve_artifact`

- **Requirement:** R1, R2, R6
- **Description:** Replace all construct-then-stat path constructions in `validate_spec.py` (~13 sites at lines 613, 644, 864, 1049, 1110, 1149, 1242, 1313, 1364, 1384, 1674, 1743) with `resolve_artifact` calls, applying the **per-site catch policy**: **(a) sites WITH a `result` in scope** (613, 644, 864, 1049, 1110, 1149, 1242, 1364) catch `ArtifactAmbiguityError` → `result.add(..., False)` (a fail-closed FAIL entry); **(b) the no-`result` sites** — `find_project_root` (1313, returns `Optional[Path]`), `expected_file` (1743, the `continue` path before `result` is assigned), and the **`main()`-level `--approve` target (1674)** (no `result` exists there) — **must let `ArtifactAmbiguityError` PROPAGATE** (do NOT `result.add` — there is no `result`); the approve-target may instead print + `sys.exit(1)` mirroring the adjacent `not target.is_file()` gate at 1675. Either way reaches a non-zero exit before any hash stamp. Propagation reaches `main()` and exits non-zero, which IS the fail-closed behavior (design.md:349); catching-into-a-FAIL is impossible where no `result` exists yet.
- **Files:**
  - Read: `telescoping-sdd/scripts/blueprint_common.py` — confirm `resolve_artifact`, `ArtifactAmbiguityError`, `strip_artifact_prefix` signatures from T1
  - Modify: `telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py`
- **Dependencies:** T1
- **Parallel:** Yes (with T2, T3, T4, T6, T7) — touches disjoint files
- **Acceptance Criteria:**
  - GIVEN a spec directory containing `01_spec.md` (prefixed form)
    WHEN `validate_spec.py` is invoked on that directory
    THEN the validator locates and parses `01_spec.md` and reports the same pass/fail result it would for bare `spec.md` with identical content
  - GIVEN a spec directory containing bare `spec.md` (no prefix)
    WHEN `validate_spec.py` is invoked on that directory
    THEN the validator locates and parses `spec.md` without error (no regression)
  - GIVEN `validate_spec.py` `find_project_root` with `blueprint/PLAN.md` present only as `03_PLAN.md`
    WHEN `find_project_root` executes the gate at line 1313
    THEN `resolve_artifact` locates `03_PLAN.md` and the project root is found (CFC consumer walk fires)
  - GIVEN `validate_spec.py` line 1743 (`expected_file`) with file present only as `02_design.md`
    WHEN the existence check runs
    THEN the check succeeds and validation proceeds
  - GIVEN a spec directory containing BOTH `spec.md` and `01_spec.md` (ambiguity)
    WHEN `validate_spec.py` (and `--approve spec`) is invoked via the CLI
    THEN the `ArtifactAmbiguityError` propagates to a non-zero exit and NO content hash is stamped (fail-closed invariant, design.md:349) — verified by T8's `test_validate_spec_ambiguity_exits_nonzero_no_hash`
- **Tests:** (covered by T8 integration tests — see T8)
- **Verification:** `.venv/bin/pytest telescoping-sdd/ -q` — full suite must be green after this task

### - [x] T6: Convert `validate_blueprint.py` ~17 sites → `resolve_artifact`/`strip_artifact_prefix`

- **Requirement:** R1, R2, R6
- **Description:** Replace all construct-then-stat path constructions and exact-equality gates in `validate_blueprint.py` (~17 sites: equality gates at 1381/908/928; `check_previous_phase_approved` at 1539; `classify_spec` at 449–451; `validate_*` at 1561/1659/1745/2090; approve/phase file_maps at 2127/2211/2244) with `resolve_artifact` / `strip_artifact_prefix`. **Per-site catch policy:** sites with a `result` in scope (1561/1659/1745/2090) catch `ArtifactAmbiguityError` → FAIL result; the **no-`result` sites** — `classify_spec` (449–451, returns `SpecState`) and the `main()`-level `--approve` target (2127) — must let `ArtifactAmbiguityError` PROPAGATE (`classify_spec` must NOT swallow into `STATE_NOT_STARTED`; the approve-target may print + `sys.exit(1)` mirroring the adjacent `not target.is_file()` gate at 2128). Propagation → non-zero exit = fail-closed. **RI3 (line 2244):** build the `scan_prefix` key from the RESOLVED name — `f"{bp_rel}/{resolve_artifact(blueprint_dir, phase_file_map[args.phase]).name}"` — because `upsert_pending_entry` wrote the key with the resolved file path (`blueprint/03_PLAN.md`); a bare or `strip`-ed name would not match.
- **Files:**
  - Read: `telescoping-sdd/scripts/blueprint_common.py` — confirm `resolve_artifact`, `ArtifactAmbiguityError`, `strip_artifact_prefix` signatures from T1
  - Modify: `telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py`
- **Dependencies:** T1
- **Parallel:** Yes (with T2, T3, T4, T5, T7) — touches disjoint files
- **Acceptance Criteria:**
  - GIVEN `validate_blueprint.py` line 1381 (`if file_path.name == "PLAN.md":`) and the file being approved is `03_PLAN.md`
    WHEN the CFC-hash sub-block refresh check runs
    THEN the gate triggers exactly as it would for bare `PLAN.md`
  - GIVEN a spec directory containing `03_tasks.md` and a CFC consumer walk
    WHEN `validate_blueprint.py` lines 908/928 (`artifact_name == "tasks.md"`) execute
    THEN the CFC enforcement-owner check is applied (gate uses `strip_artifact_prefix` before comparing)
  - GIVEN a `blueprint/` directory containing `02_ARCHITECTURE.md` and `03_PLAN.md`
    WHEN `validate_blueprint.py` is invoked on that directory
    THEN the validator locates and parses both files as architecture and plan artifacts respectively
  - GIVEN a spec directory containing `01_spec.md` reached via `validate_blueprint.py:550` `sorted(specs_root.iterdir())` → `classify_spec`
    WHEN `classify_spec` constructs `spec_dir / "spec.md"` etc. (lines 449–451)
    THEN `01_spec.md` resolves and the feature is classified to its true state, NOT `STATE_NOT_STARTED`
  - GIVEN `--approve plan` invoked on a project whose PLAN artifact is `03_PLAN.md`
    WHEN the approve target is resolved (line 2127) and the `scan_prefix` key is built (line 2244)
    THEN the target resolves to `03_PLAN.md`, AND the `scan_prefix` key equals `<bp_rel>/03_PLAN.md` (built from `resolve_artifact(...).name`, NOT the bare `PLAN.md`) so it matches the pending key `upsert_pending_entry` wrote
  - GIVEN a `blueprint/` containing BOTH `PLAN.md` and `03_PLAN.md` (ambiguity) reached via `classify_spec` or a soft-gate
    WHEN `validate_blueprint.py` runs via the CLI
    THEN the `ArtifactAmbiguityError` propagates to a non-zero exit (the soft-gate sites do not swallow it)
- **Tests:** (covered by T8 integration tests — see T8)
- **Verification:** `.venv/bin/pytest telescoping-sdd/ -q` — full suite must be green after this task

### - [x] T7: Convert `render_business_brief.py` 4 sites → `resolve_artifact`

- **Requirement:** R1, R6
- **Description:** Replace the four artifact path constructions in `render_business_brief.py` (missing-artifact gate at line 144 and `_read_artifact` calls at lines 817–819) with `resolve_artifact` calls; add `ArtifactAmbiguityError` → `sys.exit(1)` handling in `validate_blueprint_dir`; preserve the `_RENDER_TARGETS`/`_ARTIFACTS` drift-guard assert at lines 661–666.
- **Files:**
  - Read: `telescoping-sdd/scripts/blueprint_common.py` — confirm `resolve_artifact`, `ArtifactAmbiguityError` signatures from T1
  - Modify: `telescoping-sdd/skills/project-blueprint/scripts/render_business_brief.py`
- **Dependencies:** T1
- **Parallel:** Yes (with T2, T3, T4, T5, T6) — touches disjoint files
- **Acceptance Criteria:**
  - GIVEN a `blueprint/` directory containing `01_SCOPE.md`, `02_ARCHITECTURE.md`, `03_PLAN.md`
    WHEN `render_business_brief.py` runs
    THEN all three resolve via `resolve_artifact` applied to `_REQUIRED_ARTIFACTS`, the gate at line 144, and `_read_artifact` calls at lines 817–819; the HTML render proceeds without reporting any artifact as missing
  - GIVEN the `_RENDER_TARGETS`/`_ARTIFACTS` drift-guard assert (lines 661–666)
    WHEN `render_business_brief.py` runs after T7 changes
    THEN the assert continues to hold (no drift introduced)
- **Tests:** (covered by T8 `test_render_business_brief_prefixed_blueprint` — see T8)
- **Verification:** `.venv/bin/pytest telescoping-sdd/ -q` — full suite green; the render-specific proof is T8's `test_render_business_brief_prefixed_blueprint`

### - [x] T8: Resolver-side test suite — grep gate, negative self-test, and integration tests

- **Requirement:** R6
- **Description:** Add the definition-of-done grep gate (`test_no_bare_artifact_constructions` + negative self-test `test_grep_gate_catches_known_bad`) and all five named integration tests to `test_artifact_prefix.py`; the full suite must be green before Phase B begins.
- **Files:**
  - Read: `telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py` — confirm converted sites for grep gate coverage
  - Read: `telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py` — confirm converted sites
  - Read: `telescoping-sdd/skills/project-blueprint/scripts/render_business_brief.py` — confirm converted sites
  - Modify: `telescoping-sdd/scripts/tests/test_artifact_prefix.py`
- **Dependencies:** T2, T3, T4, T5, T6, T7
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN the six modified non-test source files (`validate_spec.py`, `validate_blueprint.py`, `archive_pass.py`, `blueprint_common.py`, `reconcile.py`, `render_business_brief.py`)
    WHEN `test_no_bare_artifact_constructions` greps for un-wrapped bare-artifact constructions (literal equality gates, unstripped `in TERMINAL_FILENAMES` membership, literal path constructions, variable/map-indexed constructions NOT wrapped in `resolve_artifact`)
    THEN the grep finds zero matches (all sites converted). The pattern set matches UN-resolved constructions only — a `dir / "X.md"` immediately inside a `resolve_artifact(` call, and the post-resolve `.is_file()` / `.exists()` / `.name` accessors on a `resolve_artifact(...)` return, are expected and excluded (the negative self-test includes a `resolve_artifact(dir, "spec.md").is_file()` line that must NOT be flagged)
  - GIVEN a fixture containing known-bad `dir / "spec.md"` and `dir / file_map[k]` constructions
    WHEN `test_grep_gate_catches_known_bad` runs
    THEN the grep gate flags those patterns (proves the gate's own correctness)
  - GIVEN a `tmp_path` with `01_spec.md`/`02_design.md`/`03_tasks.md`
    WHEN `test_validate_spec_prefixed_dir_equiv` runs `validate_spec.py` via subprocess
    THEN the result is identical pass/fail to the bare-name equivalent
  - GIVEN a `blueprint/` with `01_SCOPE.md`/`02_ARCHITECTURE.md`/`03_PLAN.md`
    WHEN `test_validate_blueprint_prefixed_dir_equiv` runs `validate_blueprint.py` via subprocess
    THEN the result is identical to the bare equivalent
  - GIVEN a prefixed `01_spec.md` with a valid hash
    WHEN `test_validate_spec_approve_prefixed_roundtrip` runs `--approve spec`
    THEN the approve target resolves to `01_spec.md` and a hash is stamped
  - GIVEN a prefixed `03_PLAN.md` with a stamped pending entry
    WHEN `test_validate_blueprint_scan_prefix_prefixed_plan` runs
    THEN the `scan_prefix` key equals `<bp_rel>/03_PLAN.md` (resolved `.name`), and a bare-`PLAN.md` key would NOT match (RI3 is load-bearing)
  - GIVEN a prefixed blueprint directory
    WHEN `test_render_business_brief_prefixed_blueprint` runs `render_business_brief.py`
    THEN it renders with no "missing artifact" error (RI2)
  - GIVEN a dir with BOTH `spec.md` and `01_spec.md` (ambiguity)
    WHEN `test_validate_spec_ambiguity_exits_nonzero_no_hash` runs validate + `--approve spec` via subprocess
    THEN the exit code is non-zero AND no content hash is stamped (the fail-closed CLI invariant, design.md:349)
- **Tests:**
  - `test_no_bare_artifact_constructions` — grep gate across 6 source files; zero matches required
  - `test_grep_gate_catches_known_bad` — negative self-test: fixture with known-bad patterns; gate must flag them
  - `test_validate_spec_prefixed_dir_equiv` — subprocess: prefixed spec dir → same result as bare
  - `test_validate_blueprint_prefixed_dir_equiv` — subprocess: prefixed blueprint → same result as bare
  - `test_validate_spec_approve_prefixed_roundtrip` — `--approve spec` on prefixed `01_spec.md` → hash stamped
  - `test_validate_blueprint_scan_prefix_prefixed_plan` — approve a prefixed `03_PLAN.md`, stamp a pending entry; assert the `scan_prefix` key == `<bp_rel>/03_PLAN.md` (resolved `.name`), with a negative leg asserting a bare-`PLAN.md` scan_prefix would NOT match the prefixed pending key (proves RI3 is load-bearing)
  - `test_validate_spec_ambiguity_exits_nonzero_no_hash` — a dir with BOTH `spec.md` and `01_spec.md`, run `validate_spec.py` and `--approve spec` via subprocess → non-zero exit AND no content hash stamped (the fail-closed CLI invariant, design.md:349)
  - `test_render_business_brief_prefixed_blueprint` — `render_business_brief.py` on prefixed blueprint → renders
  - File: `telescoping-sdd/scripts/tests/test_artifact_prefix.py`
- **Verification:** `.venv/bin/pytest telescoping-sdd/ -q` — full suite green (Increment 1 complete gate)

## Phase B: Increment 2 — Default-On Emission, Renamer, R7

### - [x] T9: Build `artifact_prefix.py` renamer with `PREFIX_MAP`, rename mode, and `--check` subcommand

- **Requirement:** R4, R7
- **Description:** Create `telescoping-sdd/scripts/artifact_prefix.py` with `PREFIX_MAP`, `main`/`_check_mode`/`_resolve_dir_and_root`/`_check_pending_refusal`/`_check_ambiguity_preflight`/`_rename_artifacts` functions, and the `--check` subcommand that prints `OFFER`/`SUPPRESS` — all per the C3/AD5 design; imports from `blueprint_common` and `arch_config`.
- **Files:**
  - Read: `telescoping-sdd/scripts/blueprint_common.py` — confirm `KNOWN_ARTIFACTS`, `_detect_prefix_state`, `read_pending_review`, `MarkerCorruptError`, `_key_is_contained`, `_prefix_in_scope`, `verify_content_hash` are present and their signatures
  - Read: `telescoping-sdd/scripts/arch_config.py` — confirm `find_project_root` signature
  - Create: `telescoping-sdd/scripts/artifact_prefix.py`
- **Dependencies:** T8
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN a `blueprint/` directory containing approved `SCOPE.md`, `ARCHITECTURE.md`, and `PLAN.md`
    WHEN the renamer is invoked (`python telescoping-sdd/scripts/artifact_prefix.py blueprint/`)
    THEN each file is renamed to its prefixed form and exits 0
  - GIVEN a directory containing partially prefixed artifacts (e.g. `01_SCOPE.md` already renamed, `ARCHITECTURE.md` bare)
    WHEN the renamer is invoked
    THEN it renames only the bare artifacts and leaves already-prefixed artifacts untouched (idempotent)
  - GIVEN a `.sdd/pending-review.json` entry keyed to an artifact in the target directory
    WHEN the renamer is invoked
    THEN it exits non-zero, names the pending artifact, and tells the user to resolve or decline the pending review first
  - GIVEN both `spec.md` AND `01_spec.md` exist in the target directory
    WHEN the renamer is invoked
    THEN it exits non-zero and names both conflicting files
  - GIVEN a directory containing no recognizable bare artifacts
    WHEN the renamer is invoked
    THEN it exits 0 with a message indicating nothing to rename
  - GIVEN a mixed-state dir with tty + non-CI environment
    WHEN `python artifact_prefix.py --check <dir>` is run
    THEN it prints `OFFER` and exits 0
  - GIVEN a non-interactive/CI invocation (`CI=true` or piped stdin)
    WHEN `--check <dir>` is run
    THEN it prints `SUPPRESS` and exits 0
  - GIVEN `set(PREFIX_MAP.keys()) == KNOWN_ARTIFACTS`
    WHEN the symmetry is asserted
    THEN both sets are equal (AD10)
- **Tests:** (covered by T10 — see T10)
- **Verification:** `python /Users/lgeorge/Projects/telescoping-sdd/telescoping-sdd/scripts/artifact_prefix.py --help` exits 0; `python /Users/lgeorge/Projects/telescoping-sdd/telescoping-sdd/scripts/artifact_prefix.py --check .` exits 0

### - [x] T10: Renamer-side tests in `test_artifact_prefix.py`

- **Requirement:** R4, R6
- **Description:** Add all renamer-side tests to `test_artifact_prefix.py`, covering hash-safety (pinned 3-step), idempotency, nothing-to-rename, corrupt-marker-refuses, sibling-no-bleed, per-file-key-match, symlink-refused, relative-path, nested-dir-root, ambiguity-refusal, rename-failure-halts, midfailure-leaves-mixed, and all four `--check` subprocess tests.
- **Files:**
  - Read: `telescoping-sdd/scripts/artifact_prefix.py` — confirm renamer public surface from T9
  - Modify: `telescoping-sdd/scripts/tests/test_artifact_prefix.py`
- **Dependencies:** T9
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN a directory with approved bare-name artifacts
    WHEN `test_renamer_hash_safety` runs the 3-step (write with real `compute_content_hash`, rename, verify)
    THEN `verify_content_hash(new_content, original_stored_hash)` is True for every renamed file
  - GIVEN a corrupt `.sdd/pending-review.json`
    WHEN `test_renamer_corrupt_marker_refuses` runs the renamer
    THEN the renamer exits 1 and renames nothing (fail-closed, `strict=True`)
  - GIVEN the renamer run on `specs/foo/` with a pending entry for `specs/foobar/spec.md`
    WHEN `test_renamer_pending_entry_sibling_dir_no_bleed` checks sibling non-bleed
    THEN the renamer proceeds (boundary-safe `_prefix_in_scope` check)
  - GIVEN a forced mid-rename OSError
    WHEN `test_renamer_midfailure_leaves_mixed_state` checks the directory state
    THEN `_detect_prefix_state(dir) == "mixed"` (RI4 WARN-routes-back mitigation)
  - GIVEN `CI=true` and a mixed-state dir
    WHEN `test_renamer_check_suppress_ci` runs `--check` via subprocess
    THEN stdout is `SUPPRESS` and exit code is 0
- **Tests:**
  - `test_renamer_renames_all_bare_artifacts` — bare dir → all renamed to prefixed form
  - `test_renamer_hash_safety` — 3-step hash-safety end-to-end
  - `test_renamer_idempotent_all_prefixed` — already-prefixed → exit 0, nothing to rename
  - `test_renamer_idempotent_partial` — 2-of-3 prefixed → renames only bare remainder
  - `test_renamer_nothing_to_rename_exit_zero` — empty dir → exit 0
  - `test_renamer_pending_review_refusal` — pending entry → exit 1, names artifact
  - `test_renamer_pending_entry_different_dir_no_refusal` — pending for different dir → proceeds
  - `test_renamer_ambiguity_refusal` — both `spec.md` and `01_spec.md` → exit 1, names both
  - `test_renamer_rename_failure_halts` — first rename fails → exit 1, no further renames
  - `test_renamer_corrupt_marker_refuses` — corrupt marker → exit 1, renames nothing
  - `test_renamer_pending_entry_sibling_dir_no_bleed` — sibling dir pending → proceeds
  - `test_renamer_pending_entry_per_file_key_match` — per-file key under dir prefix → refuses
  - `test_renamer_symlink_artifact_refused` — symlink artifact → refused
  - `test_renamer_dir_relative_path_resolves` — relative/`..` path → resolved; key matching correct
  - `test_renamer_finds_root_from_nested_dir` — nested dir → `arch_config.find_project_root` walk-up locates marker
  - `test_renamer_check_offer_mixed_interactive` — mixed + tty + no CI → prints `OFFER`, exit 0
  - `test_renamer_check_suppress_ci` — `CI=true` → prints `SUPPRESS`, exit 0
  - `test_renamer_check_suppress_no_tty` — piped stdin → prints `SUPPRESS`, exit 0
  - `test_renamer_check_suppress_uniform` — uniform-bare or uniform-prefixed → prints `SUPPRESS`, exit 0
  - `test_renamer_midfailure_leaves_mixed_state` — forced mid-failure → `_detect_prefix_state(dir) == "mixed"`
  - File: `telescoping-sdd/scripts/tests/test_artifact_prefix.py`
- **Verification:** `.venv/bin/pytest telescoping-sdd/scripts/tests/test_artifact_prefix.py -v`

> **Filename-segment Boundary (applies to T11, T11b, T11c, T14):** prefix the FILENAME segment only — `specs/<dir>/01_spec.md`, `blueprint/03_PLAN.md`. NEVER modify the `specs/F<n>-<slug>/` directory-grammar segment (a spec "Never do" Boundary — file naming inside a dir is independent of the dir grammar). The two rules are compatible: the `01_` goes on the file, the `F<n>-<slug>/` dir is untouched.

### - [x] T11: Default-on emission — update the six phase references to prefixed Write-targets

- **Requirement:** R3
- **Description:** Update all six `phase-*.md` Write-target instructions and their command examples to prefixed forms (filename segment only, per the Boundary above).
- **Files:**
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/phase-specify.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/phase-design.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/phase-tasks.md`
  - Modify: `telescoping-sdd/skills/project-blueprint/references/phase-scope.md`
  - Modify: `telescoping-sdd/skills/project-blueprint/references/phase-architecture.md`
  - Modify: `telescoping-sdd/skills/project-blueprint/references/phase-plan.md`
- **Dependencies:** T8
- **Parallel:** Yes (with T11b, T12) — disjoint files
- **Acceptance Criteria:**
  - GIVEN a fresh `spec-driven-dev` session generating a spec
    WHEN the skill generates the spec artifact
    THEN `phase-specify.md` instructs the drafting agent to write to `specs/<dir>/01_spec.md` (filename prefixed; `F<n>-<slug>/` dir segment untouched)
  - GIVEN the `--set-language` / `--approve` command examples in phase references
    WHEN they reference artifact paths
    THEN they use the prefixed form (e.g. `03_PLAN.md`)
- **Tests:** (prose review — no automated test)
- **Verification:** (count-based, whole-file) for EACH of the six files, `grep -cE "0[123]_(spec|design|tasks|SCOPE|ARCHITECTURE|PLAN)\.md"` ≥ the count of intended emit-targets, AND a **substring-safe** negative grep confirms no standalone emit-target basename survives OUTSIDE a `specs/F<n>-<slug>/` dir-grammar path. The negative pattern must be context-aware: a bare `grep spec.md` self-matches the prefixed `01_spec.md` and the legitimate `specs/F<n>-<slug>/spec.md` dir-grammar path — use a negative look-behind / `grep -vE "0[123]_|F<n>-<slug>/"`-style exclusion or assert the count of NON-prefixed, NON-dir-grammar occurrences is zero. A single-pattern spot-check is NOT acceptable — the whole file must be provably converted.

### - [x] T11b: Default-on emission — update the nine template files' upstream boilerplate to prefixed paths

- **Requirement:** R3
- **Description:** Update the upstream artifact-path boilerplate in all nine template files to prefixed forms (filename segment only, per the Boundary above).
- **Files:**
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/spec-template-python.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/spec-template-java.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/design-template-python.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/design-template-java.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/tasks-template-python.md`
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/tasks-template-java.md`
  - Modify: `telescoping-sdd/skills/project-blueprint/references/scope-template.md`
  - Modify: `telescoping-sdd/skills/project-blueprint/references/architecture-template.md`
  - Modify: `telescoping-sdd/skills/project-blueprint/references/plan-template.md`
- **Dependencies:** T8
- **Parallel:** Yes (with T11, T12) — disjoint files
- **Acceptance Criteria:**
  - GIVEN the spec/design/tasks templates
    WHEN they reference upstream artifact paths in their boilerplate
    THEN those references use the prefixed form (filename prefixed; dir grammar untouched)
- **Tests:** (prose review — no automated test)
- **Verification:** (count-based, whole-file) for EACH template, a positive grep confirms every upstream artifact-path reference is prefixed AND a negative grep confirms no standalone bare emit-target basename survives outside a `specs/F<n>-<slug>/` path.

> **T11c (SKILL.md command examples) is folded into T13** — both T11c and T13 edit the same two `SKILL.md` files, so to avoid a write conflict the command-example prefixing and the interactive-offer prose are applied as **one combined edit per SKILL.md** in T13. (Resolves Q1.)

### - [x] T12: Mixed-state WARN — hook `_detect_prefix_state` into both validators + tests

- **Requirement:** R7
- **Description:** Call `_detect_prefix_state` in both `validate_spec.py` and `validate_blueprint.py` main dispatch and emit a non-blocking `warn_only=True` WARN only on a mixed state; add the two `test_detect_prefix_state_warn_*` tests to `test_blueprint_common.py` (or `test_artifact_prefix.py`).
- **Files:**
  - Read: `telescoping-sdd/scripts/blueprint_common.py` — confirm `_detect_prefix_state` signature from T1
  - Modify: `telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py`
  - Modify: `telescoping-sdd/skills/project-blueprint/scripts/validate_blueprint.py`
  - Modify: `telescoping-sdd/scripts/tests/test_artifact_prefix.py`
- **Dependencies:** T8
- **Parallel:** Yes (with T11, T13) — touches disjoint files from T11/T13 (validator files vs. phase refs vs. SKILL.md offer prose)
- **Acceptance Criteria:**
  - GIVEN a `specs/<dir>/` in a mixed state (at least one bare AND at least one prefixed artifact)
    WHEN `validate_spec.py` runs on that directory
    THEN a non-blocking WARN is emitted naming the bare artifacts and pointing to `artifact_prefix.py`
  - GIVEN a uniformly-bare directory (no prefixed artifact)
    WHEN a validator runs on that directory
    THEN no mixed-state WARN is emitted
  - GIVEN a uniformly-prefixed directory (no bare artifact)
    WHEN a validator runs on that directory
    THEN no mixed-state WARN is emitted
- **Tests:**
  - `test_validator_warn_present_on_mixed` — validator output contains WARN for a mixed dir
  - `test_validator_warn_absent_on_uniform_bare` — no WARN for uniformly-bare dir
  - File: `telescoping-sdd/scripts/tests/test_artifact_prefix.py`
- **Verification:** `.venv/bin/pytest telescoping-sdd/scripts/tests/test_artifact_prefix.py -v -k "warn"`

### - [x] T13: Interactive offer prose + command-example prefixing in both SKILL.md files (T11c folded in)

- **Requirement:** R7, R3
- **Description:** In ONE combined edit per SKILL.md file (both `project-blueprint/SKILL.md` and `spec-driven-dev/SKILL.md`), do BOTH: (a) **[T11c, R3]** prefix the artifact-path command examples to the prefixed form (filename segment only, per the T11 Boundary); and (b) **[R7]** add the interactive renamer offer prose block, gated on `artifact_prefix.py --check <dir>` stdout, including the decline-reassurance sentence, the pending-review pre-check, and the prose-review checklist (C5). Combining (a)+(b) into one edit per file resolves the Q1 write-conflict; the testable half of (b) is the `--check` CLI already proven by T10.
- **Files:**
  - Read: `telescoping-sdd/skills/spec-driven-dev/SKILL.md` — locate insertion point at workflow entry / context-assessment step
  - Read: `telescoping-sdd/skills/project-blueprint/SKILL.md` — same
  - Modify: `telescoping-sdd/skills/spec-driven-dev/SKILL.md`
  - Modify: `telescoping-sdd/skills/project-blueprint/SKILL.md`
- **Dependencies:** T9, T8
- **Parallel:** No — T13 solely owns both `SKILL.md` files; the command-example prefixing (folded-in T11c) and the offer prose are applied as one combined edit per file (Q1 resolved, no remaining write-conflict)
- **Acceptance Criteria:**
  - GIVEN the artifact-path command examples in both SKILL.md files (the folded-in T11c, R3)
    WHEN they reference artifact paths
    THEN they use the prefixed form (filename segment only) — applied in the SAME edit as the offer prose, one combined edit per SKILL.md
  - GIVEN a mixed-state project AND an interactive session
    WHEN the skill flow reaches the workflow-entry context-assessment step
    THEN the skill runs `python telescoping-sdd/scripts/artifact_prefix.py --check <dir>` and offers the renamer ONLY when stdout is `OFFER`; the offer text contains the decline-reassurance sentence verbatim
  - GIVEN a non-interactive / CI invocation (no TTY or `CI` env set)
    WHEN the `--check` CLI runs
    THEN it prints `SUPPRESS` and the offer is provably absent (proven by `test_renamer_check_suppress_ci` / `..._no_tty` from T10 — the testable half)
  - GIVEN the pending-review pre-check before the offer
    WHEN a pending entry exists for the directory
    THEN the skill surfaces the pending obligation instead of presenting the offer as actionable
- **Tests:** (attested via prose-review checklist — the testable half is `test_renamer_check_suppress_ci` and `test_renamer_check_suppress_no_tty` from T10)
- **Verification:** Prose-review checklist — read both SKILL.md files and confirm: (1) prose runs `--check` before any offer text; (2) offer text contains the decline-reassurance sentence; (3) pending-review pre-check is present before the offer; (4) no re-offer after decline within same session. `claude plugin validate ./telescoping-sdd` exits 0.

### - [x] T14: R5 prose sweep — both `panel-review.md` copies and agent prose

- **Requirement:** R5
- **Description:** Update both copies of `panel-review.md` (blueprint and SDD tiers) so Deferred targets and command examples use prefixed forms; update agent prose in `telescoping-sdd/agents/` that references literal artifact paths to use prefixed forms or state both forms accepted; confirm both `panel-review.md` copies are identical in their treatment of the resolution rule.
- **Files:**
  - Modify: `telescoping-sdd/skills/spec-driven-dev/references/panel-review.md`
  - Modify: `telescoping-sdd/skills/project-blueprint/references/panel-review.md`
  - Modify: `telescoping-sdd/agents/` — selectively: agents whose prompts reference literal artifact paths (read agents/ to determine which files require edits)
  - Read: `telescoping-sdd/agents/` — scan for literal artifact path references to identify which files need edits
- **Dependencies:** T11, T11b
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN both copies of `panel-review.md`
    WHEN they reference artifact filenames as Deferred targets or command examples
    THEN both copies use the prefixed forms (e.g. `Deferred → 02_design.md`) and are identical in their treatment of the resolution rule
  - GIVEN the agents in `telescoping-sdd/agents/` that reference artifact paths
    WHEN an agent reads or writes an artifact by literal path in its prose
    THEN the path uses the prefixed form or the prose states both forms are accepted
- **Tests:** (prose review — no automated test)
- **Verification:** `diff <(grep -n "Deferred" telescoping-sdd/skills/spec-driven-dev/references/panel-review.md) <(grep -n "Deferred" telescoping-sdd/skills/project-blueprint/references/panel-review.md)` → identical Deferred lines (or empty if no Deferred targets reference artifact paths); `grep -r "spec\.md\|design\.md\|tasks\.md\|PLAN\.md\|SCOPE\.md\|ARCHITECTURE\.md" telescoping-sdd/agents/ --include="*.md" -l` → review each file listed

### - [x] T15: Dogfood rename — run `artifact_prefix.py` on this repo's own `specs/*/`

- **Requirement:** R4
- **Description:** Run `artifact_prefix.py` on an **explicit allowlist** of this repo's sibling spec dirs (NOT a bare `specs/*` glob), excluding `specs/artifact-ordering-prefix/` (its own `tasks.md` is mid-tick); before each rename, assert the dir has no open `.sdd/pending-review.json` entry; verify `validate_spec.py` on each renamed dir with no hash failure. Runs LAST. The allowlist to enumerate at implementation time = the sibling spec dirs present then (at design time: `cross-project-derivation`, `reapproval-gate`, `security-exposure-seam`, `spec-dir-naming`, `subagent-write-inversion`) — re-enumerate at run time and SKIP any dir that is itself mid-flight/awaiting approval (e.g. `security-exposure-seam` per project memory) until it is sealed.
- **Files:**
  - Read: `telescoping-sdd/scripts/artifact_prefix.py` — confirm renamer is ready from T9
  - Read: `specs/` — enumerate the sibling dirs into an explicit allowlist (exclude `artifact-ordering-prefix/` and any mid-flight dir)
- **Dependencies:** T9, T14
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN the explicit allowlist of sibling spec dirs (excluding `artifact-ordering-prefix/` and any dir awaiting its own approval)
    WHEN `artifact_prefix.py` is run on each
    THEN each file is renamed to the prefixed form (or nothing-to-rename if already prefixed) and exits 0
  - GIVEN any allowlisted dir that has an open `.sdd/pending-review.json` entry
    WHEN the per-dir pending-clear assertion runs BEFORE the rename
    THEN that dir is skipped (the renamer's `strict=True` refusal is the backstop, but the allowlist gates it explicitly) — the rename does not orphan an in-flight obligation
  - GIVEN each renamed spec directory
    WHEN `validate_spec.py` is run on it
    THEN validation reports no hash failure (hash-safe rename confirmed)
- **Tests:** (manual / runnable check)
- **Verification:** for each dir D in the explicit allowlist: `test -f "<D>/.sdd-clear"` (or confirm no pending entry for D), then `python telescoping-sdd/scripts/artifact_prefix.py "<D>"` exits 0, then `.venv/bin/python telescoping-sdd/skills/spec-driven-dev/scripts/validate_spec.py "<D>"` → no hash failure. Do NOT use a bare `specs/*` glob — enumerate the allowlist explicitly and skip `artifact-ordering-prefix/` plus any mid-flight dir.

### - [x] T16: Version bump — MINOR in both plugin manifests in lockstep

- **Requirement:** R3 (the MINOR release that ships default-on emission; version-lockstep per CLAUDE.md)
- **Description:** Increment the MINOR version in both `telescoping-sdd/.claude-plugin/plugin.json` (authoritative) and `.claude-plugin/marketplace.json` (mirror) in lockstep; validate the plugin manifests.
- **Files:**
  - Modify: `telescoping-sdd/.claude-plugin/plugin.json`
  - Modify: `.claude-plugin/marketplace.json`
- **Dependencies:** T15
- **Parallel:** No
- **Acceptance Criteria:**
  - GIVEN the current version in `telescoping-sdd/.claude-plugin/plugin.json`
    WHEN the MINOR is incremented
    THEN both `plugin.json` and `marketplace.json` reflect the same bumped version (in lockstep, per CLAUDE.md)
  - GIVEN `claude plugin validate ./telescoping-sdd`
    WHEN run after the version bump
    THEN the command exits 0 with no validation errors
- **Tests:** (runnable check)
- **Verification:** `claude plugin validate ./telescoping-sdd` exits 0; `grep '"version"' telescoping-sdd/.claude-plugin/plugin.json .claude-plugin/marketplace.json` → both show the same new version string

## Implementation Order

1. **T1** — foundational: all helpers live here; nothing in T2–T16 can proceed without `strip_artifact_prefix`, `resolve_artifact`, `ArtifactAmbiguityError`, `_detect_prefix_state`, and `KNOWN_ARTIFACTS`.
2. **T2, T3, T4, T5, T6, T7** — parallel after T1: all touch disjoint files; all convert call sites in Increment 1; run in parallel for speed (note: T3 modifies `blueprint_common.py` same as T1, but on different lines — apply after T1 is committed; T5 and T6 both import from `blueprint_common.py` but only read it).
3. **T8** — after T2–T7: grep gate and integration tests can only run once all call sites are converted; full suite green here is the Increment 1 gate before Phase B begins.
4. **T9** — after T8 is green: builds the renamer; `artifact_prefix.py` imports from `blueprint_common.py` (needs T1 complete and T8 confirming green).
5. **T10** — after T9: renamer-side tests require `artifact_prefix.py` to exist.
6. **T11, T11b, T12** — parallel after T8: phase-ref sweep (T11), template sweep (T11b), and the validator WARN hook (T12) touch fully disjoint files. **T13** — after T9 (needs the `--check` CLI) and T8: it solely owns both `SKILL.md` files, doing the command-example prefixing (folded-in T11c) AND the offer prose in one combined edit per file (Q1 resolved). No SKILL.md write-conflict remains.
7. **T14** — after T11 and T11b: remaining prose sweep (panel-review.md copies + agent prose) depends on the phase-ref/template decisions being settled first.
8. **T15** — last: dogfood rename; must run after T9, T14, and all panel-review obligations closed; re-run `validate_spec.py` to confirm hash-safety.
9. **T16** — after T15: version bump and final plugin validation.

## Open Questions

> All questions must be resolved before proceeding to implementation.

_None remaining._ Q1 (the SKILL.md write-conflict) is **resolved**: the command-example prefixing (formerly T11c) and the interactive-offer prose are applied as ONE combined edit per `SKILL.md` file under T13. T11 (phase refs) and T11b (templates) touch disjoint files and run in parallel; the two `SKILL.md` files are owned solely by T13, so there is no remaining write conflict.

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
| 1    | 2026-06-05 | 7     | 0           | 14        | 0        | 0      | tags=d1u0c6                     |
| 2    | 2026-06-05 | 0     | 0           | 5         | 0        | 0      | converged (0 HIGH); tags=d0u0c0 |

### Sealed dispositions

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|

## Approval

- [x] Approved to proceed to implementation
- **Content Hash:** `a700bf72a1231f14`
