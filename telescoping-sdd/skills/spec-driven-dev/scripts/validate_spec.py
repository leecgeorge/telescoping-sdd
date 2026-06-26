#!/usr/bin/env python3
"""Validate and approve spec-driven development artifacts.

Checks that spec.md, design.md, and tasks.md have required sections
and follow the expected structure. Can also approve documents for
phase transitions using content hashes to detect post-approval edits.

Supports Python and Java projects via --language flag, plus an
architecture-neutral "generic" profile for everything else (infra,
static sites, Claude-skill authoring, etc.). If --language is omitted,
auto-detects by looking for pom.xml/build.gradle (Java) or
pyproject.toml/setup.py (Python) in the project root; when no recognized
language marker is found it resolves to "generic" rather than assuming
Python. The "generic" profile disables the two language-specific advisory
checks (type annotations, test-function names) so they do not misfire on
non-code or non-Python/Java deliverables.

Usage:
    python validate_spec.py <spec-directory>
    python validate_spec.py specs/F1-checkout-flow/ --phase spec
    python validate_spec.py specs/F1-checkout-flow/ --approve spec
    python validate_spec.py specs/F1-checkout-flow/ --language java
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# sys.path bootstrap — skill entry point (audit R3.5: one idiom across entry
# points). Put telescoping-sdd/scripts/ (the shared helpers, sibling of
# telescoping-sdd/skills/) on sys.path via an idempotent guarded APPEND. Append,
# never insert(0): a skill validator runs under the plugin/marketplace runtime,
# where displacing the caller's sys.path[0] would break its module resolution
# (regression-guarded). The `not in` guard stops repeated imports from stacking
# duplicate entries. Shared-script entry points (reconcile.py, artifact_prefix.py)
# use a guarded insert(0) instead — nothing else bootstraps them, so they must
# take precedence.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.append(str(_SHARED_SCRIPTS))

from blueprint_common import (  # noqa: E402
    APPROVAL_HASH_LINE_STRICT,
    HASH_BASIS_MIGRATION_MSG,
    REAPPROVAL_REMINDER,
    TBD_PATTERN,
    UNCHECKED_QUESTION_PATTERN,
    UNRESOLVED_MARKERS,
    MarkerCorruptError,
    Severity,
    ValidationResult,
    approval_section_bounds,
    approve_document as _approve_document_core,
    changed_since_stamp,
    check_approval,
    check_previous_phase_approved,
    clear_pending_entries_for_prefix,
    compute_content_hash,
    content_for_hashing,
    has_section,
    is_basis_migration_only,
    mixed_state_warning,
    now_iso_utc,
    read_file,
    read_hash_basis,
    read_stored_hash,
    reconcile_to_result,
    resolve_artifact,
    restamp_or_suppress,
    restore_anchor_for_prefix,
    run_cli_failclosed,
    stamped_at_pass_from_content,
    sweep_sdd_cruft,
    trim_trajectory_table,
    upsert_pending_entry,
    validate_panel_review,
    verify_content_hash,
    _resolve_marker_root_and_key,
    _upsert_basis_line,
)
from cfc_parser import (  # noqa: E402
    CFC_HEADER_PATTERN as CFC_HEADER_RE,
    CFC_TAG_PATTERN as CFC_TAG_RE,
    FEATURE_ID_WORD_PATTERN as FEATURE_ID_WORD_RE,
    PLAN_FEATURE_ID_PATTERN as PLAN_FEATURE_ID_LINE_RE,
    TASKS_CHECKBOX_CFC_PATTERN as TASKS_CHECKBOX_WITH_CFC_RE,
    extract_cfc_section,
    extract_cfc_tags,
    feature_breakdown_numbers,
    find_misplaced_cfc_tags,
    parse_cfc_entries,
)
from arch_config import (  # noqa: E402
    find_project_root as arch_find_project_root,
    resolve_language,
    write_arch_config,
)
from downstream_ref_guard import PolicyConfig, scan_for_downstream_refs  # noqa: E402
from spec_dirname import (  # noqa: E402
    SLUGIFY_CLI_HINT,
    classify_dirname,
    display_safe,
    is_derived_spec,
    parse_bound,
    parse_feature_number,
)
from project_link import (  # noqa: E402
    DERIVED_FROM_LINE_RE,
    MASTER_CONTRACT_HASH_LINE_RE,
    MASTER_HASH_UNBOUND,
    MASTER_HASH_VALUE_RE,
    parse_derived_dirname,
    parse_qualified_id,
)
from ucr import parse_ucr_stanza  # noqa: E402


# ---------------------------------------------------------------------------
# Language profiles — add new languages here
# ---------------------------------------------------------------------------

LANGUAGE_PROFILES: dict[str, dict] = {
    "python": {
        "label": "Python",
        "project_markers": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"],
        "dir_markers": [],  # no directory-based detection needed
        "type_pattern": re.compile(r":\s*(str|int|float|bool|list|dict|Optional)"),
        # AD8 (force-tdd-in-phase-4): the trailing `()` is OPTIONAL — the real
        # authoring convention writes `` `test_foo` `` (no parens), which the
        # parens-required form false-missed. R3 (now a FAIL) and R5 both reuse
        # this pattern, so it is broadened once here in the profile.
        "test_name_pattern": re.compile(r"`test_\w+(?:\(\))?`"),
        "test_framework": "pytest",
        "test_command": "pytest tests/ -v",
        "source_layout": "src/",
        "test_layout": "tests/",
        # AD7: test-layout globs for the R5 completion-gate existence check.
        "test_file_globs": ["**/test_*.py", "**/*_test.py"],
    },
    "java": {
        "label": "Java",
        "project_markers": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "dir_markers": ["src/main/java"],
        "type_pattern": re.compile(
            r"\b(String|int|Integer|long|Long|boolean|Boolean|double|Double|float|Float"
            r"|List|Map|Set|Optional|void|byte|short|char)\b"
        ),
        # AD8: parens optional, mirroring the python profile above.
        "test_name_pattern": re.compile(
            r"`test[a-zA-Z0-9]+(?:\(\))?`|`[a-zA-Z0-9]+Test(?:\(\))?`"
        ),
        "test_framework": "JUnit 5",
        "test_command": "mvn test / gradle test",
        "source_layout": "src/main/java/",
        "test_layout": "src/test/java/",
        # AD7: test-layout globs for the R5 completion-gate existence check.
        "test_file_globs": ["**/*Test.java", "**/*Tests.java"],
    },
    # Architecture-neutral fallback for stacks that are neither Python nor Java
    # (infrastructure, static sites, Claude-skill authoring, TypeScript before a
    # dedicated profile exists, etc.). It carries NO marker lists, so it is never
    # auto-detected — it is only ever selected as the explicit fallback when no
    # recognized language marker is found, or via `--language generic`. Its
    # `type_pattern`/`test_name_pattern` are None, which the two advisory checks
    # treat as "skip this check" rather than misfiring a Python/Java regex against
    # a stack that has neither type annotations nor xUnit-style test names.
    "generic": {
        "label": "generic (architecture-neutral)",
        "project_markers": [],
        "dir_markers": [],
        "type_pattern": None,
        "test_name_pattern": None,
        "test_framework": None,
        "test_command": None,
        "source_layout": None,
        "test_layout": None,
        "test_file_globs": [],
    },
}

# The language key used when auto-detection finds no recognized marker. A
# neutral profile, NOT "python" — defaulting an unknown stack to Python stamps a
# wrong "Language: python" banner and fires two spurious advisory warnings.
NEUTRAL_LANGUAGE = "generic"


# ---------------------------------------------------------------------------
# Required sections per phase
# ---------------------------------------------------------------------------

SPEC_REQUIRED_SECTIONS = [
    "Objective",
    "Requirements",
    "Acceptance Criteria",
    "Project Structure",
    "Boundaries",
    "Success Criteria",
    "Panel Review",
]

DESIGN_REQUIRED_SECTIONS = [
    "Goals and Non-Goals",
    "Architecture Decisions",
    "Component Design",
    "Data Models",
    "Interfaces",
    "Error Handling",
    "Testing Strategy",
    "File Structure",
    "Dependencies",
    "Integration Points",
    "Risks",
    "Implementation Sequence",
    "Panel Review",
]

# Regex to match task entries like "### T1:", "### - [ ] T1:", or "### - [x] T1:".
# Accept [ xX] so a task ticked with an uppercase [X] is still counted (audit
# R2.4) — consistent with blueprint_common._TASK_CHECKBOX_LINE / APPROVAL_CHECKBOX.
TASK_ENTRY_PATTERN = re.compile(r"^###\s+(?:- \[[ xX]\] )?T\d+:", re.MULTILINE)

# SDD-tier policy for the shared downstream-identifier guard (T<n>; minted in
# 03_tasks.md). v1: heading form blocks --approve, bare token is a non-blocking WARN.
SDD_DOWNSTREAM_POLICY = PolicyConfig(
    letter="T",
    heading_warn_only=False,
    bare_warn_only=True,
    troubleshooting_ref=(
        "See spec-driven-dev/references/troubleshooting.md "
        "'Downstream identifier in upstream artifact'."
    ),
    noun="task",
    downstream_artifact="03_tasks.md",
)

# Regex to match GIVEN/WHEN/THEN patterns
GWT_PATTERN = re.compile(
    r"GIVEN\s+.+\n\s*(?:[-*]\s+)?WHEN\s+.+\n\s*(?:[-*]\s+)?THEN\s+.+", re.MULTILINE
)

# UNCHECKED_QUESTION_PATTERN, TBD_PATTERN, and UNRESOLVED_MARKERS are imported
# from blueprint_common (audit R2.1) — they were byte-identical local copies.

# Regex to extract requirement IDs (R1, R2, etc.)
REQUIREMENT_ID_PATTERN = re.compile(r"^###\s+R(\d+):", re.MULTILINE)

# Regex to extract requirement references from task Requirement lines (supports comma-separated like "R1, R3")
TASK_REQUIREMENT_REF_PATTERN = re.compile(r"\*\*Requirement:\*\*\s*((?:R\d+(?:,\s*)?)+)")

# Panel-review parsing (regexes + validate_panel_review) lives in
# blueprint_common so both validators behave identically — including the R10
# orphaned-Trajectory-row diagnostic (C7), which the prior local copy omitted.


# ---------------------------------------------------------------------------
# Force-TDD-in-Phase-4 (R3/R4/R5) — code-touching classifier + Tests-field grammar
# ---------------------------------------------------------------------------
#
# These power the Phase-3 R3/R4 gate in validate_tasks() and the Phase-4 R5
# completion gate. The whole cluster is FIELD-SCOPED (it reads a task's
# `**Tests:**` field value, never the whole task body) and the classifier is
# VERB-SCOPED (only Create:/Modify: paths make a task code-touching — a Read:
# reference for context does not — AD2). Both scopings are load-bearing:
# verb-scope keeps prose tasks that merely read a `.py` from mis-classifying as
# code (migration safety, RISK-5); field-scope stops an incidental `test_foo`
# token in Description prose from satisfying the gate.

# Extensions that make a task "code-touching" — the only stacks with an xUnit
# test_name_pattern. A `.sh`/`.sql`/`Dockerfile`/`.yaml` helper a python task
# creates is non-code (no test pattern to satisfy).
_CODE_EXTENSIONS: frozenset = frozenset({".py", ".java"})

# Extract the `**Files:**` field value: from the field BULLET to the next
# `- **Field:**` bullet (any indentation) or end-of-body. DOTALL so it spans
# sub-bullets. The field marker is anchored to a line-leading list bullet
# (`^[ \t]*-[ \t]*`) so an incidental `**Files:**` mention in another field's
# prose is NOT mistaken for the field itself (field-scoped, Contracts).
_FILES_SECTION_PATTERN = re.compile(
    r"^[ \t]*-[ \t]*\*\*Files:\*\*[ \t]*\n?(.*?)(?=\n\s*-\s*\*\*[A-Z]|\Z)",
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)
# Same shape for the `**Tests:**` field value (multi-line capture — the real
# convention puts test tokens on indented sub-bullets UNDER the Tests line).
# Bullet-anchored for the same reason: a task whose Description/Acceptance-
# Criteria prose literally mentions `**Tests:**` (this feature's own tasks.md
# does) must still extract from the REAL field bullet, not the prose mention.
_TESTS_SECTION_PATTERN = re.compile(
    r"^[ \t]*-[ \t]*\*\*Tests:\*\*[ \t]*\n?(.*?)(?=\n\s*-\s*\*\*[A-Z]|\Z)",
    re.DOTALL | re.MULTILINE,
)
# A backtick-quoted path with an extension, e.g. `` `src/x.py` ``.
_BACKTICK_PATH_PATTERN = re.compile(r"`([^`]+\.[a-zA-Z0-9]+)`")
# Leading verb of a Files sub-bullet. AD2: only Create/Modify count toward
# code-touching; Read/Delete do not.
_FILES_VERB_PATTERN = re.compile(
    r"^\s*-\s*(Create|Modify|Read|Delete)\s*:", re.IGNORECASE
)
# R4 override sentinel: `**Tests:** none — <reason>`. The `[ \t]*` (NOT `\s*`)
# before/around `none`, and the `(?:\n|$)` terminator, keep the match on the
# Tests field's FIRST line so it cannot span into an adjacent sub-bullet (AD1) —
# deliberately the OPPOSITE line-scope from the whole-block by-name extraction.
_R4_OVERRIDE_PATTERN = re.compile(
    r"^[ \t]*-[ \t]*\*\*Tests:\*\*[ \t]*none[ \t]*[-–—][ \t]*(.*?)(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
# A sibling task identifier (AD10 cross-reference), e.g. `T6`.
_TASK_ID_TOKEN_PATTERN = re.compile(r"\bT\d+\b")


def _extract_tests_field(task_body: str) -> str:
    """Return the `**Tests:**` field value (multi-line block), or '' if absent."""
    m = _TESTS_SECTION_PATTERN.search(task_body)
    return m.group(1) if m else ""


def _extract_test_names(task_body: str, pattern) -> list:
    """Extract test identifiers from the task's `**Tests:**` FIELD (not the whole
    body — Contracts: field-scoped). Strips backticks and an optional trailing
    `()`. A `none — <reason>` override field yields [] (no by-name token)."""
    field = _extract_tests_field(task_body)
    names = []
    for m in pattern.finditer(field):
        tok = m.group(0).strip("`")
        if tok.endswith("()"):
            tok = tok[:-2]
        names.append(tok)
    return names


def _is_code_touching(task_body: str) -> bool:
    """True iff a Create:/Modify: sub-bullet of `**Files:**` references a
    `.py`/`.java` path. Read: (read-for-context) paths are ignored (AD2)."""
    m = _FILES_SECTION_PATTERN.search(task_body)
    if not m:
        return False
    for line in m.group(1).splitlines():
        vm = _FILES_VERB_PATTERN.match(line)
        if not vm or vm.group(1).lower() not in ("create", "modify"):
            continue
        for pm in _BACKTICK_PATH_PATTERN.finditer(line):
            if os.path.splitext(pm.group(1))[1].lower() in _CODE_EXTENSIONS:
                return True
    return False


def _r4_override_reason(task_body: str):
    """Return the R4 override reason, or None.

    None — no `**Tests:** none — …` override present.
    ''   — override present but the reason is absent/whitespace-only (FAIL).
    str  — a non-empty reason (valid override).
    """
    m = _R4_OVERRIDE_PATTERN.search(task_body)
    if not m:
        return None
    return m.group(1).strip()


def _audit_test_requirements(task_bodies: list, pattern) -> tuple:
    """Classify code-touching tasks by `**Tests:**`-field compliance (AD10).

    Returns (failing_no_test, failing_bad_override, overrides, crossrefs) — each
    a list of task IDs. A code-touching task PASSES when its Tests field carries
    a by-name token (AD8), OR a VALID sibling cross-reference (a `T<n>` that is
    not its own ID and resolves to a task that is itself code-touching AND names
    a real test — so R5 genuinely existence-checks the referent), OR a valid R4
    override. Non-code tasks are never required to name a test.
    """
    # Pass 1: by-name + code-touching set (the only valid cross-ref referents).
    by_name_code: set = set()
    info: dict = {}
    for tid, body in task_bodies:
        code = _is_code_touching(body)
        names = _extract_test_names(body, pattern)
        info[tid] = (code, bool(names), body)
        if code and names:
            by_name_code.add(tid)

    failing_no_test: list = []
    failing_bad_override: list = []
    overrides: list = []
    crossrefs: list = []

    # Pass 2: classify each code-touching task.
    for tid, body in task_bodies:
        code, has_name, _ = info[tid]
        if not code:
            continue
        if has_name:
            continue  # a real test name satisfies the gate (R4 AC#3: name wins)
        reason = _r4_override_reason(body)
        if reason is not None:
            if reason == "":
                failing_bad_override.append(tid)
            else:
                overrides.append(tid)
            continue
        # No name, no override — try a valid sibling cross-reference (AD10).
        field = _extract_tests_field(body)
        refs = [t for t in _TASK_ID_TOKEN_PATTERN.findall(field) if t != tid]
        if any(t in by_name_code for t in refs):
            crossrefs.append(tid)
            continue
        failing_no_test.append(tid)

    return failing_no_test, failing_bad_override, overrides, crossrefs


def _collect_task_bodies(content: str) -> list:
    """Split tasks.md into (task_id, body) pairs.

    Each task body spans its `### T<n>:` heading to the next task heading or the
    next `## ` section, whichever comes first. Shared by validate_tasks() (R3/R4)
    and validate_completion_gate() (R5) so the two gates parse identically.
    """
    task_matches = list(TASK_ENTRY_PATTERN.finditer(content))
    section_break = re.compile(r"^## ", re.MULTILINE)
    bodies: list = []
    for i, m in enumerate(task_matches):
        id_match = re.search(r"T\d+", content[m.start() : m.end()])
        task_id = id_match.group(0) if id_match else f"task#{i + 1}"
        body_end = (
            task_matches[i + 1].start() if i + 1 < len(task_matches) else len(content)
        )
        sec = section_break.search(content, m.end(), body_end)
        if sec:
            body_end = sec.start()
        bodies.append((task_id, content[m.start() : body_end]))
    return bodies


def _find_test_files(project_root: Path, language: str) -> list:
    """Return test-layout files under project_root matching the language globs
    (AD7). Generic / unknown languages have no globs → []."""
    globs = get_profile(language).get("test_file_globs") or []
    files: list = []
    for pat in globs:
        try:
            files.extend(project_root.rglob(pat))
        except OSError:
            continue
    return files


def _test_name_exists(name: str, language: str, project_root: Path,
                      preferred_scope: Optional[Path] = None) -> bool:
    """True if a test function/method named `name` is defined in a test-layout
    file. Python matches `def <name>`, java matches `<name>(`. Searches
    `preferred_scope` (the feature's own test dir, if any) first, then repo-wide
    — a repo-wide-only match is a documented cross-feature-collision boundary
    (AD9). Returns False (never raises) on OSError. `re.escape` is defence in
    depth at a self-declared-input boundary."""
    if language == "java":
        needle = re.compile(rf"\b{re.escape(name)}\s*\(")
    else:
        needle = re.compile(rf"def\s+{re.escape(name)}\b")
    seen: set = set()
    scopes = [s for s in (preferred_scope, project_root) if s is not None]
    for scope in scopes:
        for f in _find_test_files(scope, language):
            if f in seen:
                continue
            seen.add(f)
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return False
            if needle.search(text):
                return True
    return False


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def _matching_languages(base: Path) -> list[str]:
    """Languages whose markers are present in `base`, in profile-declaration order.

    The neutral profile has no markers, so this only ever returns marker-bearing
    stacks (python/java) — never 'generic'.
    """
    matched = []
    for lang, profile in LANGUAGE_PROFILES.items():
        has_file = any((base / f).exists() for f in profile["project_markers"])
        has_dir = any((base / d).is_dir() for d in profile["dir_markers"])
        if has_file or has_dir:
            matched.append(lang)
    return matched


def _pick_language(matched: list[str], where: Path) -> str:
    """Pick the winning language from `matched` (first by declaration order).

    On a tie (markers for more than one stack in the same directory — e.g. a Java
    service with a Python tooling layer) print a one-line notice so the silent
    declaration-order tie-break is visible and the user can override with
    --set-language (audit I3.3).
    """
    if len(matched) > 1:
        print(
            f"Note: markers for multiple stacks were found in {where}: "
            f"{', '.join(matched)}. Auto-detect chose '{matched[0]}' by "
            f"declaration order. Run `--set-language` to choose explicitly.",
            file=sys.stderr,
        )
    return matched[0]


def detect_language(spec_dir: Path, project_root: Optional[Path] = None) -> str:
    """Auto-detect project language from project root markers.

    If project_root is given, checks only that directory.
    Otherwise walks up from spec_dir looking for markers.
    """
    if project_root is not None:
        matched = _matching_languages(project_root)
        return _pick_language(matched, project_root) if matched else NEUTRAL_LANGUAGE

    search_dir = spec_dir.resolve()
    for _ in range(10):  # max 10 levels up
        matched = _matching_languages(search_dir)
        if matched:
            return _pick_language(matched, search_dir)
        parent = search_dir.parent
        if parent == search_dir:
            break
        search_dir = parent
    return NEUTRAL_LANGUAGE  # neutral fallback — not "python"


def get_profile(language: str) -> dict:
    """Get the language profile, falling back to the neutral 'generic' profile.

    An unknown key resolves to 'generic' (advisory checks disabled), NOT to
    'python' — falling back to Python is what silently mislabels a non-Python
    project and fires spurious advisory warnings against it.
    """
    return LANGUAGE_PROFILES.get(language, LANGUAGE_PROFILES[NEUTRAL_LANGUAGE])


# Severity and ValidationResult are imported from blueprint_common (above)
# to avoid the prior duplicate definitions. Same interface, same behaviour;
# both validators now share one canonical implementation.

# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
#
# read_file and has_section are imported from blueprint_common (audit R2.1) —
# they were byte-identical local copies. validate_resolved stays local: it
# diverges from the blueprint validator's (which uses scan_unresolved_markers).


def validate_resolved(content: str, filename: str, result: ValidationResult) -> None:
    """Check that all questions, decisions, and markers are resolved."""
    # Unchecked open questions
    unchecked = UNCHECKED_QUESTION_PATTERN.findall(content)
    result.add(
        f"{filename} has no unresolved open questions",
        len(unchecked) == 0,
        f"{len(unchecked)} unchecked question(s) found" if unchecked else "",
    )

    # TBD decisions
    tbds = TBD_PATTERN.findall(content)
    result.add(
        f"{filename} has no [TBD] decisions",
        len(tbds) == 0,
        f"{len(tbds)} [TBD] marker(s) found" if tbds else "",
    )

    # General unresolved markers (TODO, FIXME, XXX, HACK, ???)
    markers = UNRESOLVED_MARKERS.findall(content)
    result.add(
        f"{filename} has no unresolved markers (TODO/FIXME/???)",
        len(markers) == 0,
        f"Found: {', '.join(markers)}" if markers else "",
        warn_only=True,
    )


# validate_panel_review is imported from blueprint_common (see import block).
# The prior local copy was a pre-R10 fork that silently omitted the
# orphaned-Trajectory-row check; sharing the canonical implementation is what
# makes spec/design/tasks behave identically to SCOPE/ARCHITECTURE/PLAN (C7/R5).


# ---------------------------------------------------------------------------
# Approval helpers
# ---------------------------------------------------------------------------
#
# The approval-detection constants and check_approval now live in
# blueprint_common (audit R2.1); approve_document below scopes its rewrites via
# the shared approval_section_bounds. Hash comparison routes through the shared
# blueprint_common.verify_content_hash; content_for_hashing / compute_content_hash
# are likewise imported, so the approval-hash grammar cannot drift between the
# two validators.


# check_approval and _resolve_marker_root_and_key are imported from
# blueprint_common (audit R2.1) — both validators shared byte-identical copies.


def approve_document(
    file_path: Path,
    *,
    task_tick: bool = False,
    project_root: Optional[Path] = None,
) -> bool:
    """Mark a document as approved (thin wrapper over the shared core, audit 3.5a).

    Delegates to ``blueprint_common.approve_document``. The SDD side has no
    producer hook (the PLAN.md per-CFC hash refresh is blueprint-only), so this
    passes ``content_transform=None`` and forwards the Phase-4 ``task_tick``
    carve-out. Signature is preserved byte-for-byte so all in-process callers and
    tests keep working; see the core for the full contract (R1.5 / R2.6).
    """
    return _approve_document_core(
        file_path,
        task_tick=task_tick,
        project_root=project_root,
    )


# check_previous_phase_approved is imported from blueprint_common (audit R2.1);
# the SDD phase ordering is passed in via SDD_PHASE_ORDER.
SDD_PHASE_ORDER = {"design": "spec.md", "tasks": "design.md"}


def _read_plan_identifier(
    spec_dir: Path, spec_content: Optional[str] = None
) -> Optional[str]:
    """Return the in-file PLAN feature identifier ('F<n>' or 'n/a') from
    spec.md, or None if spec.md is absent/unreadable or has no identifier line.

    If ``spec_content`` (already-read spec.md text) is supplied, it is parsed
    directly — avoiding a redundant disk read on the ``validate_spec()`` path,
    which already holds the content. When reading from disk it uses
    encoding='utf-8' with an `except (OSError, UnicodeDecodeError)` guard — a
    non-UTF-8 spec.md is treated as unreadable (None), NOT decoded with
    errors='replace' (which could let the identifier line parse as garbage and
    produce a wrong result instead of cannot-cross-check). Never raises.
    """
    if spec_content is None:
        try:
            with open(resolve_artifact(spec_dir, "spec.md"), encoding="utf-8-sig") as fh:
                spec_content = fh.read()
        except (OSError, UnicodeDecodeError):
            return None
    m = PLAN_FEATURE_ID_LINE_RE.search(spec_content)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Cross-Project Derivation (CPD) field grammar
# ---------------------------------------------------------------------------
#
# A derived spec.md carries two CPD provenance fields plus an optional UCR
# stanza. The two fields are validated by `_check_cpd_fields` (I5); the
# `**Derived from:**` value also feeds `check_dir_identifier`'s derived branch
# (I4). The four field constants below (`DERIVED_FROM_LINE_RE`,
# `MASTER_CONTRACT_HASH_LINE_RE`, `MASTER_HASH_VALUE_RE`, `MASTER_HASH_UNBOUND`)
# are imported from `project_link` — the single CPD-grammar owner — so this
# authoring gate and `reconcile` (the integrator) can never drift on the field
# shapes (the value captures are loose `[^`]*`; well-formedness is decided
# downstream, so a malformed-but-present field is still detected as present).


def _extract_cpd_field_values(
    content: str,
) -> "tuple[bool, bool, Optional[str], Optional[str]]":
    """Return (has_derived_from, has_master_hash, derived_from_value,
    master_hash_value) for the CPD provenance fields in spec.md.

    A value of None means the field's line is absent; an empty string means the
    line is present with an empty backtick value (still "present"). Never raises.
    """
    df = DERIVED_FROM_LINE_RE.search(content)
    mh = MASTER_CONTRACT_HASH_LINE_RE.search(content)
    derived_from_value = df.group(1) if df else None
    master_hash_value = mh.group(1) if mh else None
    return (df is not None, mh is not None, derived_from_value, master_hash_value)


def _check_cpd_fields(
    spec_dir: Path, content: str, result: ValidationResult
) -> None:
    """Validate the `**Derived from:**` + `**Master contract hash:**` fields (I5).

    SOLE owner of the malformed-value, co-occurrence, and non-derived-dir FAILs.
    Runs BEFORE `check_dir_identifier` so well-formedness is established first.
    Implements the precedence ladder — first match wins, at most one FAIL — so a
    value that is both malformed AND mismatched yields exactly one FAIL (the
    malformed one; `check_dir_identifier`'s derived branch then short-circuits on
    the same `parse_qualified_id is None`). Never raises.

    Ladder:
      1. A CPD field present on a non-`derived` dir -> `derived-fields-on-non-derived-dir`
         (stop — the other checks are moot off a non-derived dir).
      2. Exactly one of the two fields present -> `derived-fields-incomplete`.
      3. `**Derived from:**` malformed (not a backtick-wrapped qualified id)
         -> `derived-from-malformed`.
      4. `**Master contract hash:**` neither 64-hex nor `unbound`
         -> `master-hash-malformed`.
      Both fields absent -> PASS (non-derived spec, no CPD fields expected).
    """
    (
        has_derived_from,
        has_master_hash,
        derived_from_value,
        master_hash_value,
    ) = _extract_cpd_field_values(content)

    # Both absent: nothing to validate (non-derived spec).
    if not has_derived_from and not has_master_hash:
        return

    escaped = display_safe(spec_dir.name)

    # Step 1: a CPD field on a non-derived directory. Off a non-derived dir the
    # remaining CPD checks are moot, so this is the sole FAIL.
    if not is_derived_spec(spec_dir):
        result.add(
            "derived-fields-on-non-derived-dir", False,
            f"spec directory '{escaped}' carries a CPD provenance field "
            f"(`**Derived from:**` and/or `**Master contract hash:**`) but its "
            f"name is not a derived-form directory (`<project>--F<n>-<slug>`). "
            f"Either rename the directory to the derived form, or remove the "
            f"CPD fields if this is not a cross-project derived spec.",
        )
        return

    # Step 2: co-occurrence — both fields must appear together.
    if has_derived_from != has_master_hash:
        result.add(
            "derived-fields-incomplete", False,
            "`**Derived from:**` and `**Master contract hash:**` must appear "
            "together. Add the missing field; use `unbound` for the hash if not "
            "yet reconciled against the master project.",
        )
        return

    # Step 3: `Derived from` well-formedness (backtick-wrapped qualified id).
    if parse_qualified_id(derived_from_value or "") is None:
        result.add(
            "derived-from-malformed", False,
            "`**Derived from:**` value is malformed — must be a backtick-wrapped "
            "qualified id like `project:F7` (lowercase project alias, `F`, a "
            "positive feature number with no leading zero).",
        )
        return

    # Step 4: `Master contract hash` well-formedness (64-hex or `unbound`).
    value = master_hash_value or ""
    if value != MASTER_HASH_UNBOUND and not MASTER_HASH_VALUE_RE.match(value):
        result.add(
            "master-hash-malformed", False,
            "`**Master contract hash:**` value is malformed — must be 64 "
            "lowercase hex characters (a SHA-256 digest) or the literal "
            "`unbound` if not yet reconciled against the master project.",
        )
        return


def _validate_ucr_stanza(content: str, result: ValidationResult) -> None:
    """Validate the `## Upstream Change Requests` stanza if present (I6).

    Delegates parsing to the shared `ucr.parse_ucr_stanza` (so `validate_spec.py`
    and `reconcile.py` can never drift on the grammar) and emits a FAIL for each
    structural problem: malformed UCR id, duplicate id, invalid status, missing
    required field, or a malformed `Target` qualified id. A no-op when the stanza
    is absent. The stanza's presence never causes a FAIL and never hard-halts
    validation; an `## Accepted Divergences` section may coexist. Never raises.
    """
    parsed = parse_ucr_stanza(content)
    if not parsed.present:
        return

    # Malformed ids (leading zero / `0`) — rejected at parse time, never entries.
    for raw_id in parsed.malformed_ids:
        result.add(
            "ucr-id-malformed", False,
            f"`### UCR-{display_safe(raw_id)}` has a malformed id — UCR ids use "
            f"the same canonical-decimal grammar as `### CFC-N` (a positive "
            f"integer with no leading zero).",
        )

    # Duplicate ids within this spec.
    for num in parsed.duplicate_ids:
        result.add(
            "duplicate-ucr-id", False,
            f"`### UCR-{num}` appears more than once. Each UCR id must be unique "
            f"within a single spec.",
        )

    # Missing required fields.
    for num, field_name in parsed.missing_field_ids:
        result.add(
            "ucr-missing-field", False,
            f"`### UCR-{num}` is missing the required `**{field_name}:**` field. "
            f"Each UCR entry needs Target, Status, Proposed change, and Rationale.",
        )

    # Invalid status values.
    for num in parsed.invalid_status_ids:
        result.add(
            "ucr-invalid-status", False,
            f"`### UCR-{num}` has an invalid status. Status must be one of "
            f"`open`, `applied`, or `withdrawn`.",
        )

    # Malformed `Target` qualified ids — only for entries whose Target is present
    # (a missing Target is already covered by ucr-missing-field above). The raw
    # value is backtick-wrapped on disk; strip the wrapping before the parse.
    for entry in parsed.entries:
        target = entry.target()
        if target is None:
            continue
        unwrapped = target.strip()
        if unwrapped.startswith("`") and unwrapped.endswith("`") and len(unwrapped) >= 2:
            unwrapped = unwrapped[1:-1]
        if parse_qualified_id(unwrapped) is None:
            result.add(
                "ucr-target-malformed", False,
                f"`### UCR-{entry.number}` has a malformed `**Target:**` value — "
                f"must be a backtick-wrapped qualified id like `project:F7`.",
            )


def check_dir_identifier(
    spec_dir: Path, spec_content: Optional[str] = None
) -> ValidationResult:
    """Cross-check the spec directory name against the in-file PLAN feature
    identifier (R2). Returns a ValidationResult with zero checks (PASS) or one
    FAIL check. Never raises.

    Dispatches through `classify_dirname`; the bound (number, slug) pair comes
    from `spec_dirname.parse_bound` — the single grammar-owned decomposition, so
    no second interpretation of the bound form lives here. Names embedded in
    messages are escaped via `spec_dirname.display_safe` so a control char in a
    directory name cannot spoof the validator's stdout. Feature-number
    comparison is numeric (so a non-canonical `F03` identifier vs an `F3`
    directory is not a false mismatch). If `spec_content` (already-read spec.md
    text) is supplied, the identifier is parsed from it instead of re-reading
    the file. FAIL codes: dir-identifier-mismatch / missing-slug / invalid-slug
    / cannot-cross-check / derived-provenance-mismatch.
    """
    result = ValidationResult()
    name = spec_dir.name
    escaped = display_safe(name)
    category = classify_dirname(name)
    hash_safe = (
        "Renaming a spec directory does not invalidate any existing approval or "
        "content hash."
    )

    if category == "derived":
        # Derived form `<project>--F<n>-<slug>` (I4). Coherence between the
        # directory's encoded provenance and the in-file `**Derived from:**`
        # line. The directory decomposition is grammar-owned by
        # `project_link.parse_derived_dirname`; the malformed-value, co-occurrence
        # and non-derived-dir FAILs are owned by `_check_cpd_fields` (I5), so this
        # branch never re-emits them.
        content = spec_content
        if content is None:
            content = read_file(resolve_artifact(spec_dir, "spec.md")) or ""
        dir_parsed = parse_derived_dirname(name)
        # Classification (`classify_dirname` -> "derived") and decomposition
        # (`parse_derived_dirname`) now share ONE compiled grammar
        # (`spec_dirname.DERIVED_DIRNAME_PATTERN`), so a "derived" category
        # implies a non-None parse. Guard the unpack anyway: defence-in-depth so
        # any future grammar skew surfaces as a clean FAIL instead of a
        # `TypeError` raised mid-validation.
        if dir_parsed is None:
            result.add(
                "derived-provenance-mismatch", False,
                f"spec directory '{escaped}' classifies as derived but cannot be "
                f"decomposed into `<project>--F<n>-<slug>`. {hash_safe}",
            )
            return result
        dir_project, dir_number, _dir_slug = dir_parsed

        (
            has_derived_from,
            _has_master_hash,
            derived_from_value,
            _master_hash_value,
        ) = _extract_cpd_field_values(content)

        # Step 1 — well-formedness short-circuit. A malformed (or absent-value)
        # `**Derived from:**` is already FAILed by `_check_cpd_fields`
        # (`derived-from-malformed` / `derived-fields-incomplete`); this branch
        # returns WITHOUT a second FAIL so a both-malformed-and-mismatched value
        # yields exactly one FAIL through the full `validate_spec()` path (I5).
        parsed_from = (
            parse_qualified_id(derived_from_value)
            if has_derived_from and derived_from_value is not None
            else None
        )

        # Step 2 — presence: the `**Derived from:**` line is absent entirely.
        if not has_derived_from:
            result.add(
                "derived-provenance-mismatch", False,
                f"spec directory '{escaped}' uses the derived form but the "
                f"`**Derived from:**` line is missing. A derived spec records its "
                f"master-project provenance on a `**Derived from:** "
                f"`<project>:F<n>`` line. {hash_safe}",
            )
            return result

        # Malformed value -> owned by `_check_cpd_fields`; do not double-FAIL.
        if parsed_from is None:
            return result

        from_project, from_number = parsed_from

        # Step 3 — identifier must be `n/a` (provenance is on the Derived from line).
        identifier = _read_plan_identifier(spec_dir, content)
        if identifier is not None and identifier != "n/a":
            result.add(
                "derived-provenance-mismatch", False,
                f"spec directory '{escaped}' uses the derived form, so its "
                f"`**PLAN feature identifier:**` must be `n/a` (provenance lives on "
                f"the `**Derived from:**` line), but it is '{display_safe(identifier)}'. "
                f"Set the identifier to `n/a`. {hash_safe}",
            )
            return result

        # Step 4 — project mismatch.
        if from_project != dir_project:
            result.add(
                "derived-provenance-mismatch", False,
                f"spec directory '{escaped}' encodes master project "
                f"'{display_safe(dir_project)}' but `**Derived from:**` names "
                f"'{display_safe(from_project)}'. Make the directory project prefix "
                f"and the Derived from project match. {hash_safe}",
            )
            return result

        # Step 5 — number mismatch.
        if from_number != dir_number:
            result.add(
                "derived-provenance-mismatch", False,
                f"spec directory '{escaped}' encodes feature F{dir_number} but "
                f"`**Derived from:**` names F{from_number}. Make the directory "
                f"feature number and the Derived from feature number match. "
                f"{hash_safe}",
            )
            return result

        # Step 6 — all checks clear -> PASS (no check added).
        return result

    if category == "bare":
        # Bare token F<n>. Suggest the CANONICAL bound rename: parse_feature_number
        # strips a leading zero (F03 -> 3). Feature 0 (F0/F00) has no valid bound
        # form (the bound grammar is F[1-9]\d*), so steer those to n>=1 or a bare
        # standalone slug rather than the impossible 'F0-<slug>'.
        num = parse_feature_number(name)
        if num and num >= 1:
            result.add(
                "missing-slug", False,
                f"spec directory '{escaped}' is missing a slug. Rename it to "
                f"'F{num}-<slug>' (e.g. 'F{num}-checkout-flow'). To generate a "
                f"slug from the feature title, run:\n  {SLUGIFY_CLI_HINT}\n{hash_safe}",
            )
        else:
            result.add(
                "missing-slug", False,
                f"spec directory '{escaped}' is missing a slug and implies feature "
                f"number 0, which is not a valid feature number (bound names start "
                f"at F1). Rename it to 'F<n>-<slug>' with n >= 1 for a PLAN-bound "
                f"feature, or to a bare '<slug>' for a standalone feature. To "
                f"generate a slug, run:\n  {SLUGIFY_CLI_HINT}\n{hash_safe}",
            )
        return result
    if category == "invalid":
        result.add(
            "invalid-slug", False,
            f"spec directory '{escaped}' is not a valid name. Valid forms are "
            f"'F<n>-<slug>' (bound, e.g. 'F3-checkout-flow') or '<slug>' "
            f"(standalone, e.g. 'cli-notes-app') where <slug> is lowercase "
            f"kebab-case, max 50 characters. To generate a slug, run:\n  {SLUGIFY_CLI_HINT}\n"
            f"{hash_safe}",
        )
        return result

    # "bound" or "standalone": the decision depends on the in-file identifier.
    identifier = _read_plan_identifier(spec_dir, spec_content)
    if identifier is None:
        result.add(
            "cannot-cross-check", False,
            "cannot read the PLAN feature identifier from spec.md. Ensure spec.md "
            "has a '**PLAN feature identifier:**' line with its value filled in — "
            "`F<n>` for a PLAN-bound feature or `n/a` for a standalone feature. "
            "The spec template ships with the literal placeholder `F<n>`; replace "
            "it with your feature number or `n/a`. (If spec.md is missing "
            "entirely, approve the spec phase first.)",
        )
        return result

    if category == "bound":
        dir_num, slug = parse_bound(name)  # name is classified bound -> never None
        if identifier == "n/a":
            result.add(
                "dir-identifier-mismatch", False,
                f"spec directory '{escaped}' uses the bound form (implying PLAN "
                f"feature F{dir_num}) but the in-file identifier is 'n/a'. "
                f"Decision: if this feature is part of a blueprint/PLAN.md, set "
                f"the in-file identifier to `F{dir_num}`; if it is standalone, "
                f"rename the directory to the bare slug '{slug}'. {hash_safe}",
            )
        else:
            id_num = int(identifier[1:])  # identifier is 'F<digits>' (n/a handled above)
            if id_num != dir_num:
                result.add(
                    "dir-identifier-mismatch", False,
                    f"spec directory '{escaped}' implies feature F{dir_num} but the "
                    f"in-file identifier is '{identifier}'. Rename the directory to "
                    f"'F{id_num}-{slug}' or correct the in-file identifier. {hash_safe}",
                )
            # else same feature number -> PASS (no check added)
        return result

    # category == "standalone"
    if identifier != "n/a":
        id_num = int(identifier[1:])
        result.add(
            "dir-identifier-mismatch", False,
            f"spec directory '{escaped}' uses the standalone form but the in-file "
            f"identifier is '{identifier}'. Decision: if this feature is part of a "
            f"blueprint/PLAN.md, rename the directory to 'F{id_num}-{escaped}'; "
            f"if it is standalone, change the in-file identifier to `n/a`. {hash_safe}",
        )
    return result


# ---------------------------------------------------------------------------
# Phase validators
# ---------------------------------------------------------------------------

def validate_spec(spec_dir: Path) -> ValidationResult:
    """Validate spec.md for required sections.

    Note: the R2 pending-review gate is NOT checked here — it is reconciled ONCE
    at dispatch level in main() (so it fires under every --phase, and an absent
    spec.md does not make the obligation vanish). See main().
    """
    result = ValidationResult()
    spec_path = resolve_artifact(spec_dir, "spec.md")
    content = read_file(spec_path)

    result.add("spec.md exists", content is not None, str(spec_path))
    if content is None:
        return result

    for section in SPEC_REQUIRED_SECTIONS:
        result.add(
            f"spec.md has '{section}' section",
            has_section(content, section),
        )

    # Check for at least one GIVEN/WHEN/THEN block
    has_gwt = bool(GWT_PATTERN.search(content))
    result.add(
        "spec.md has GIVEN/WHEN/THEN acceptance criteria",
        has_gwt,
        "At least one GIVEN/WHEN/THEN block expected" if not has_gwt else "",
    )

    # Check for success criteria checkboxes ([ xX] — accept uppercase, audit R2.4)
    has_checkboxes = bool(re.search(r"- \[[ xX]\]", content))
    result.add(
        "spec.md has success criteria checkboxes",
        has_checkboxes,
    )

    validate_resolved(content, "spec.md", result)
    validate_panel_review(content, "spec.md", result)

    # CFC consumer-side checks. Run after standard validation so a structurally
    # broken spec.md fails for the right reason first. See
    # documentation/CFC.md § Validator for the full ruleset.
    validate_cfc_consumer(spec_dir, content, "spec", result)

    # Cross-Project Derivation field well-formedness (I5). Runs BEFORE
    # check_dir_identifier so the malformed-value / co-occurrence / non-derived-dir
    # FAILs are established first and the derived branch never double-FAILs a
    # value it already rejected (exactly-one-FAIL precedence ladder).
    _check_cpd_fields(spec_dir, content, result)

    # UCR stanza structural validation (I6). A no-op when the
    # `## Upstream Change Requests` stanza is absent; never hard-halts.
    _validate_ucr_stanza(content, result)

    # Directory<->identifier cross-check (R2). Runs AFTER the spec.md-exists
    # early-return above, so a missing spec.md does not reach cannot-cross-check
    # via this path — only the --approve path (which has no such guard) can.
    result.checks.extend(check_dir_identifier(spec_dir, spec_content=content).checks)

    for finding in scan_for_downstream_refs(content, "spec.md", SDD_DOWNSTREAM_POLICY):
        result.add(finding.check_name, False, finding.detail, warn_only=finding.warn_only)

    return result


def validate_design(spec_dir: Path, language: str = NEUTRAL_LANGUAGE) -> ValidationResult:
    """Validate design.md for required sections."""
    result = ValidationResult()
    profile = get_profile(language)

    check_previous_phase_approved(spec_dir, "design", result, SDD_PHASE_ORDER)

    design_path = resolve_artifact(spec_dir, "design.md")
    content = read_file(design_path)

    result.add("design.md exists", content is not None, str(design_path))
    if content is None:
        return result

    for section in DESIGN_REQUIRED_SECTIONS:
        result.add(
            f"design.md has '{section}' section",
            has_section(content, section),
        )

    # Check for type annotations (language-aware, advisory). Skipped entirely
    # for profiles with no type_pattern (e.g. "generic") — an architecture-neutral
    # deliverable need not contain language type annotations, so the check would
    # only emit noise.
    if profile["type_pattern"] is not None:
        has_types = bool(profile["type_pattern"].search(content))
        result.add(
            f"design.md includes {profile['label']} type annotations in models/interfaces",
            has_types,
            "Expected type annotations in code blocks" if not has_types else "",
            warn_only=True,
        )

    validate_resolved(content, "design.md", result)
    validate_panel_review(content, "design.md", result)

    for finding in scan_for_downstream_refs(content, "design.md", SDD_DOWNSTREAM_POLICY):
        result.add(finding.check_name, False, finding.detail, warn_only=finding.warn_only)

    return result


def validate_tasks(spec_dir: Path, language: str = NEUTRAL_LANGUAGE) -> ValidationResult:
    """Validate tasks.md for proper task entries."""
    result = ValidationResult()
    profile = get_profile(language)

    check_previous_phase_approved(spec_dir, "tasks", result, SDD_PHASE_ORDER)

    tasks_path = resolve_artifact(spec_dir, "tasks.md")
    content = read_file(tasks_path)

    result.add("tasks.md exists", content is not None, str(tasks_path))
    if content is None:
        return result

    # Count task entries
    task_matches = list(TASK_ENTRY_PATTERN.finditer(content))
    result.add(
        "tasks.md has task entries (### T1:, T2:, ...)",
        len(task_matches) > 0,
        f"Found {len(task_matches)} task(s)" if task_matches else "No tasks found",
    )

    # Check for summary table
    has_summary = bool(re.search(r"\|\s*Task\s*\|.*Status\s*\|", content, re.IGNORECASE))
    result.add(
        "tasks.md has summary table with status",
        has_summary,
    )

    # Per-task field checks. These run PER TASK rather than document-wide: a
    # document-wide `re.search` passes when ANY single task carries the field,
    # silently masking other tasks that omit it. Each task body spans its
    # `### T<n>:` heading to the next task heading or the next `## ` section,
    # whichever comes first; a failing check names the offending task IDs.
    task_bodies: list[tuple[str, str]] = _collect_task_bodies(content)

    def _tasks_missing(pattern):
        return [tid for tid, body in task_bodies if not pattern.search(body)]

    # Required per-task fields (FAIL). Mirrors the tasks template and the
    # "Required per-task fields" list in SKILL.md / phase-tasks.md. (Test
    # function names are checked separately, below, as an advisory warning.)
    required_task_fields = [
        ("Requirement", re.compile(r"\*\*Requirement:\*\*\s*R\d+")),
        ("Description", re.compile(r"\*\*Description:\*\*")),
        ("Files", re.compile(r"\*\*Files:\*\*")),
        ("Dependencies", re.compile(r"\*\*Dependencies:\*\*")),
        ("Parallel", re.compile(r"\*\*Parallel:\*\*")),
        ("Verification", re.compile(r"\*\*Verification:\*\*")),
    ]
    for field_name, field_pattern in required_task_fields:
        missing = _tasks_missing(field_pattern) if task_bodies else []
        result.add(
            f"tasks.md every task has **{field_name}:**",
            not missing,
            f"Missing in: {', '.join(missing)}" if missing else "",
        )

    # Acceptance Criteria + GIVEN/WHEN/THEN, per task.
    ac_missing = (
        _tasks_missing(re.compile(r"\*\*Acceptance Criteria")) if task_bodies else []
    )
    result.add(
        "tasks.md every task has **Acceptance Criteria**",
        not ac_missing,
        f"Missing in: {', '.join(ac_missing)}" if ac_missing else "",
    )
    gwt_missing = _tasks_missing(GWT_PATTERN) if task_bodies else []
    result.add(
        "tasks.md every task's acceptance criteria use GIVEN/WHEN/THEN format",
        not gwt_missing,
        f"Missing GIVEN/WHEN/THEN in: {', '.join(gwt_missing)}" if gwt_missing else "",
    )

    # Test function/method names (language-aware) — R3/R4 FAIL for code-touching
    # tasks (force-tdd-in-phase-4). Skipped entirely for profiles with no
    # test_name_pattern (e.g. "generic"): a static site, infra, or skill-authoring
    # task is verified by a command/manual check, not an xUnit-style test function.
    # A code-touching task (Create/Modify a .py/.java — AD2) must name a test, OR
    # carry a valid sibling cross-reference (AD10), OR a reason-bearing R4 override;
    # a task touching only non-code files auto-passes. The override count and any
    # cross-reference delegations are surfaced as audit PASS checks (R4 AC#4).
    if profile["test_name_pattern"] is not None:
        failing_no_test, failing_bad_override, overrides, crossrefs = (
            _audit_test_requirements(task_bodies, profile["test_name_pattern"])
            if task_bodies else ([], [], [], [])
        )
        result.add(
            "tasks.md every task names test functions/methods",
            not failing_no_test,
            f"Missing in: {', '.join(failing_no_test)}" if failing_no_test else "",
            warn_only=False,
        )
        if failing_bad_override:
            result.add(
                "tasks.md R4 override requires non-empty reason",
                False,
                f"Empty reason in: {', '.join(failing_bad_override)}",
                warn_only=False,
            )
        if overrides:
            result.add(
                "tasks.md R4 test-exempt overrides",
                True,
                f"Count: {len(overrides)}, tasks: {', '.join(overrides)}",
            )
        if crossrefs:
            result.add(
                "tasks.md cross-reference test delegations",
                True,
                f"Count: {len(crossrefs)}, tasks: {', '.join(crossrefs)}",
            )

    # Requirement coverage — check all spec R-numbers are covered by tasks
    has_req = bool(TASK_REQUIREMENT_REF_PATTERN.search(content))
    spec_content = read_file(resolve_artifact(spec_dir, "spec.md"))
    if spec_content is not None and has_req:
        spec_reqs = set(REQUIREMENT_ID_PATTERN.findall(spec_content))
        # Extract individual R-numbers from Requirement lines (e.g., "R1, R2, R3")
        task_reqs = set()
        for match in TASK_REQUIREMENT_REF_PATTERN.finditer(content):
            for r_num in re.findall(r"R(\d+)", match.group(1)):
                task_reqs.add(r_num)
        uncovered = spec_reqs - task_reqs
        if uncovered:
            missing_labels = ", ".join(f"R{r}" for r in sorted(uncovered, key=int))
            result.add(
                "tasks.md covers all requirements from spec.md",
                False,
                f"Missing tasks for: {missing_labels}",
                warn_only=True,
            )
        else:
            result.add(
                "tasks.md covers all requirements from spec.md",
                True,
                f"All {len(spec_reqs)} requirement(s) covered",
            )

    validate_resolved(content, "tasks.md", result)
    validate_panel_review(content, "tasks.md", result)

    # CFC consumer-side checks for tasks.md (Phase 3): if this feature is named
    # as the owning feature in any CFC's Enforcement prose, tasks.md must
    # contain a `[CFC-N]`-tagged task. See documentation/CFC.md.
    validate_cfc_consumer(spec_dir, content, "tasks", result)

    return result


def validate_completion_gate(
    spec_dir: Path,
    project_root: Path,
    language: Optional[str] = None,
    strict_r5: bool = False,
) -> ValidationResult:
    """R5: at the Phase-4 completion gate, verify that the test names declared in
    each code-touching task's `**Tests:**` field actually exist in the codebase.

    Also re-emits the R4 override + AD10 cross-reference audits so both counts
    surface at the gate (R4 AC#4) — the single `--completion-gate` command is
    self-contained, no separate plain re-run required.

    `language` is the resolved stack key (passed in by `_handle_completion_gate`,
    which applies the shared `resolve_language` precedence — NOT bare auto-detect).
    Generic profiles return a single skip-PASS. Missing tests WARN by default and
    FAIL under `strict_r5` (AD4). Read-only — no content hash is touched.
    """
    result = ValidationResult()
    profile = get_profile(language)
    pattern = profile["test_name_pattern"]
    if pattern is None:
        result.add(
            "R5: completion-gate skipped",
            True,
            "generic profile — no test_name_pattern",
        )
        return result

    tasks_path = resolve_artifact(spec_dir, "tasks.md")
    content = read_file(tasks_path)
    result.add("tasks.md exists", content is not None, str(tasks_path))
    if content is None:
        return result

    task_bodies = _collect_task_bodies(content)

    # Re-emit the R4 override + AD10 cross-reference audits (both-gates, R4 AC#4).
    _no_test, _bad_override, overrides, crossrefs = _audit_test_requirements(
        task_bodies, pattern
    )
    if overrides:
        result.add(
            "tasks.md R4 test-exempt overrides",
            True,
            f"Count: {len(overrides)}, tasks: {', '.join(overrides)}",
        )
    if crossrefs:
        result.add(
            "tasks.md cross-reference test delegations",
            True,
            f"Count: {len(crossrefs)}, tasks: {', '.join(crossrefs)}",
        )

    # R5 existence check: each by-name token of a code-touching task must resolve
    # to a test definition in a test-layout file. Override/cross-ref tasks yield
    # zero by-name tokens → nothing to existence-check (their referent task is
    # checked on its own row). AD9: preferred_scope is None in this centralized
    # repo (tests are not per-feature) → search repo-wide.
    any_r5 = False
    for tid, body in task_bodies:
        if not _is_code_touching(body):
            continue
        names = _extract_test_names(body, pattern)
        if not names:
            continue
        for name in names:
            any_r5 = True
            exists = _test_name_exists(name, language, project_root)
            result.add(
                f"R5: test function exists — {tid}/{name}",
                exists,
                "" if exists else f"Not found under {project_root}",
                warn_only=not strict_r5,
            )
    if not any_r5:
        result.add(
            "R5: completion-gate — no code-touching tasks with declared tests",
            True,
            "nothing to existence-check",
        )

    return result


# ---------------------------------------------------------------------------
# CFC consumer-side validation
# ---------------------------------------------------------------------------
#
# Reads `blueprint/PLAN.md`'s `## Cross-Feature Contracts` section (if present)
# and applies:
#   - Identifier-line skip rule (5 cases per CFC.md M5/P7)
#   - Spec.md THEN-line CFC tag presence (if feature is in CFC's Participating)
#   - Tasks.md checkbox CFC tag presence (if feature is in CFC's Enforcement owners)
#   - Mid-stream drift WARN (tag references CFC that no longer exists or
#     no longer lists this feature)
#
# Parser primitives — extract_cfc_section, parse_cfc_entries, CFC tag regex,
# feature-ID matcher — are imported from telescoping-sdd/scripts/cfc_parser.py
# (shared with validate_blueprint.py). The producer/consumer split for the
# cascade machinery is preserved (no `cfc_consistency.py` in v1); only the
# file-format parser is shared.

# PLAN_FEATURE_ID_LINE_RE, TASKS_CHECKBOX_WITH_CFC_RE, and the Feature-Breakdown
# feature resolution all come from cfc_parser now (the shared format owner), so
# the producer and consumer can't drift on these cross-skill seam grammars
# (audit R2.3). They are imported above (the first two under their historical
# local aliases; feature resolution via feature_breakdown_numbers).


def find_plan_root(spec_dir: Path) -> Optional[Path]:
    """Walk upward from spec_dir for the dir holding `blueprint/PLAN.md`.

    This locates the PLAN (the consumer's upstream), NOT the project root — do not
    confuse it with arch_config.find_project_root (imported as
    arch_find_project_root), which resolves the `.sdd/` marker root by walking up
    for .git/.sdd/specs/blueprint markers (AD3). Renamed from find_project_root to
    remove that name collision (audit R3.3).
    """
    for candidate in (spec_dir.parent, spec_dir.parent.parent):
        if candidate is None:
            continue
        if resolve_artifact(candidate / "blueprint", "PLAN.md").is_file():
            return candidate
    return None


def _parse_cfc_section(plan_content: str) -> list[dict]:
    """Return a list of CFC dicts with keys: number, participating, enforcement.

    Wraps the shared `parse_cfc_entries` from `cfc_parser` to produce the
    dict shape the consumer-side validator works with. Returns an empty list
    if no `## Cross-Feature Contracts` section is present.
    """
    section = extract_cfc_section(plan_content)
    if section is None:
        return []
    _start, _end, body = section
    entries: list[dict] = []
    for entry in parse_cfc_entries(body):
        entries.append(
            {
                "number": entry.number,
                "participating": entry.participating_features(),
                "enforcement_text": entry.fields.get("Enforcement") or "",
                "enforcement_owners": entry.enforcement_owners(),
            }
        )
    return entries


def _spec_then_line_cfc_tags(spec_content: str) -> list[int]:
    """Extract CFC numbers from `[CFC-N]` tags on THEN lines in spec.md."""
    return extract_cfc_tags(spec_content)


def _tasks_checkbox_cfc_tags(tasks_content: str) -> list[int]:
    """Extract CFC numbers from `[CFC-N]` tags on tasks.md checkbox lines."""
    return [int(m.group(1)) for m in TASKS_CHECKBOX_WITH_CFC_RE.finditer(tasks_content)]


def validate_cfc_consumer(
    spec_dir: Path,
    artifact_content: str,
    phase: str,
    result: ValidationResult,
) -> None:
    """Apply consumer-side CFC checks based on the artifact phase.

    phase ∈ {"spec", "tasks"}. The "design" phase has no validator-level CFC
    checks (design fidelity is panel-side judgement per CFC.md).
    """
    # Parse the identifier line from spec.md, which is the binding signal.
    spec_path = resolve_artifact(spec_dir, "spec.md")
    spec_content = read_file(spec_path)
    if spec_content is None:
        return

    # Derived-spec exemption (I7). A derived-form directory is exempt from ALL
    # `n/a`-standalone CFC-coherence behaviors (the `n/a`+active-CFC WARN AND the
    # `n/a`+stale-`[CFC-N]`-tag WARN) and from local-PLAN feature-id resolution:
    # its provenance lives in the master project's PLAN, not the local one. Gate
    # on the SHARED `is_derived_spec` predicate (NOT the identifier value) so this
    # exemption and the I4 derived branch can never drift on what "derived" means.
    # A derived spec legitimately carries `identifier == "n/a"`.
    if is_derived_spec(spec_dir):
        return

    id_match = PLAN_FEATURE_ID_LINE_RE.search(spec_content)
    identifier = id_match.group(1) if id_match else None

    plan_root = find_plan_root(spec_dir)
    plan_content = (
        read_file(resolve_artifact(plan_root / "blueprint", "PLAN.md")) if plan_root else None
    )
    has_cfc_section = bool(plan_content and CFC_HEADER_RE.search(plan_content))

    # M5 / P7 / Q11 skip rule.
    if identifier is None:
        # Line absent entirely → FAIL.
        result.add(
            "spec.md PLAN feature identifier line",
            False,
            "spec.md missing required `**PLAN feature identifier:**` line; "
            "use `n/a` for standalone",
        )
        return
    if identifier == "n/a":
        if has_cfc_section:
            # Q11 — silent opt-out vector guard. passed=False+warn_only emits WARN.
            result.add(
                "spec.md PLAN feature identifier coherence",
                False,
                "spec declares `n/a` but blueprint/PLAN.md has an active "
                "Cross-Feature Contracts section. If this feature should "
                "bind to one or more CFCs, set the identifier to `F<n>`; "
                "if standalone is correct, no action needed.",
                warn_only=True,
            )
        # Decision B — n/a + stale [CFC-N] tags in spec.md guard.
        # A user downgrading from F<n> to n/a (intentional or accidental) may
        # leave stale tags in spec.md. Without this WARN the binding silently
        # dies until the producer-side orphan-tag scan picks it up at the next
        # PLAN re-approval. Emit a per-CFC WARN naming the orphaned tags.
        stale_tags = sorted(set(_spec_then_line_cfc_tags(spec_content)))
        if stale_tags:
            tag_list = ", ".join(f"[CFC-{n}]" for n in stale_tags)
            result.add(
                "spec.md `n/a` identifier with stale CFC tags",
                False,
                f"spec declares `n/a` but carries {tag_list} on THEN lines. "
                "Either restore the `F<n>` identifier so binding-checks run, "
                "or remove the stale tags. Tags on an `n/a` spec are silently "
                "ignored by the binding validator otherwise.",
                warn_only=True,
            )
        return  # n/a → skip CFC binding checks regardless of PLAN presence

    # identifier is F<n> here.
    feature_number = int(identifier[1:])

    if not plan_content:
        result.add(
            "spec.md PLAN feature identifier resolves",
            False,
            f"spec claims {identifier} binding but no blueprint/PLAN.md exists",
        )
        return

    # Check identifier resolves to a feature in PLAN's Feature Breakdown.
    # Per P1-2: scope to the `## Feature Breakdown` section body so a `### F<n>:`
    # heading anywhere else in PLAN.md (inside `## Open Questions`, an
    # illustrative quote, a code block, etc.) does not silently satisfy the
    # resolver. Resolution goes through the shared cfc_parser helper so the
    # producer's feature operations and this consumer agree byte-for-byte (R2.3).
    plan_feature_ids = set(feature_breakdown_numbers(plan_content))
    if feature_number not in plan_feature_ids:
        result.add(
            "spec.md PLAN feature identifier resolves",
            False,
            f"PLAN feature identifier {identifier} not found in "
            f"blueprint/PLAN.md Feature Breakdown",
        )
        return

    if not has_cfc_section:
        # PLAN exists but has no CFC section → no checks to run.
        return

    # CFC binding checks.
    cfc_entries = _parse_cfc_section(plan_content)
    binding_cfcs = [
        e for e in cfc_entries if feature_number in e["participating"]
    ]
    spec_tags = _spec_then_line_cfc_tags(spec_content)

    # Phase-1 checks: every binding CFC must have a corresponding [CFC-N] tag
    # on a THEN line in spec.md.
    if phase == "spec":
        # Per P2-3 from the post-implementation review: surface "tag in
        # wrong location" distinctly from "missing tag". A `[CFC-N]` on a
        # GIVEN/WHEN line, in a requirement header, or in body prose outside
        # an AC block is a different bug from "the author never wrote the
        # tag" and deserves its own diagnostic.
        misplaced = find_misplaced_cfc_tags(spec_content)
        # A misplaced tag still counts as "present" for the purposes of the
        # binding check below — but ALSO emit a FAIL pointing the author at
        # the correct location.
        for n, line in misplaced:
            result.add(
                f"spec.md [CFC-{n}] tag location",
                False,
                f"[CFC-{n}] appears outside an acceptance criterion THEN line "
                f"(offending line: {line!r}). Move the tag to the THEN line "
                f"of the AC that materially implements the contract, e.g. "
                f"`THEN <assertion> [CFC-{n}]`. Tags on GIVEN/WHEN lines, "
                f"requirement headers, body prose, or single-line GWT "
                f"compressions are not recognised as bindings.",
            )

        for entry in binding_cfcs:
            n = entry["number"]
            if n in spec_tags:
                result.add(
                    f"spec.md carries [CFC-{n}] binding tag",
                    True,
                )
            else:
                result.add(
                    f"spec.md carries [CFC-{n}] binding tag",
                    False,
                    f"feature {identifier} appears in CFC-{n}'s Participating "
                    f"features; required: `[CFC-{n}]` on a THEN line within "
                    f"**Acceptance Criteria:**",
                )

        # Mid-stream drift WARN: tags present in spec.md that no longer
        # resolve cleanly in current PLAN.
        for n in set(spec_tags):
            entry = next((e for e in cfc_entries if e["number"] == n), None)
            if entry is None:
                result.add(
                    f"spec.md [CFC-{n}] tag still resolves",
                    False,
                    f"spec.md carries `[CFC-{n}]` but CFC-{n} no longer "
                    f"exists in current PLAN.md (mid-stream drift). "
                    f"Remove the tag, or restore CFC-{n} to PLAN.md.",
                    warn_only=True,
                )
            elif feature_number not in entry["participating"]:
                result.add(
                    f"spec.md [CFC-{n}] tag still resolves",
                    False,
                    f"spec.md carries `[CFC-{n}]` but {identifier} is no "
                    f"longer in CFC-{n}'s Participating features. "
                    f"Remove the tag, or restore {identifier} to "
                    f"CFC-{n}'s Participating list.",
                    warn_only=True,
                )

    # Phase-3 checks: if this feature is an Enforcement owner of any CFC,
    # tasks.md must contain a [CFC-N]-tagged task.
    if phase == "tasks":
        # artifact_content is tasks.md here.
        tasks_tags = _tasks_checkbox_cfc_tags(artifact_content)
        owning_cfcs = [
            e for e in cfc_entries
            if feature_number in e["enforcement_owners"]
        ]
        for entry in owning_cfcs:
            n = entry["number"]
            if n in tasks_tags:
                result.add(
                    f"tasks.md carries [CFC-{n}] enforcement task",
                    True,
                )
            else:
                result.add(
                    f"tasks.md carries [CFC-{n}] enforcement task",
                    False,
                    f"feature {identifier} is named in CFC-{n}'s Enforcement "
                    f"prose as artifact owner; tasks.md must contain a "
                    f"`[CFC-{n}]`-tagged task implementing the verifying "
                    f"artifact named in that Enforcement field",
                )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _handle_decline_pending(spec_dir: Path, project_root: Optional[Path]) -> int:
    """`--decline-pending` mode (audit R3.2 — extracted from main).

    Clear this spec dir's pending-review obligations — an auditable user decision
    (logged to stdout), the validator-owned marker lifecycle (no hand-edited
    JSON). DEF-01/RI-11 v1-posture: the bypass trace is stdout-audited +
    fail-closed (the gate fires by default). Returns a process exit code.
    """
    root, spec_rel = _resolve_marker_root_and_key(spec_dir, project_root)
    try:
        removed = clear_pending_entries_for_prefix(root, spec_rel)
    except MarkerCorruptError as exc:
        print(
            f"Cannot decline: {exc}. The marker is corrupt; inspect or delete "
            f".sdd/pending-review.json manually."
        )
        return 1
    if removed:
        noun = "entry" if len(removed) == 1 else "entries"
        print(
            f"Declined upstream panel re-review; cleared {len(removed)} pending "
            f"{noun}: {', '.join(removed)}"
        )
    else:
        print(f"No pending-review entries found for {spec_dir}.")
    return 0


def _handle_restore_anchor(spec_dir: Path, project_root: Optional[Path]) -> int:
    """`--restore-anchor` mode (audit R3.2 — extracted from main).

    Clear a legacy re-anchored (UNSATISFIABLE) obligation whose genuine
    `upstream-panel` tag is already archived. Content-attested — clears ONLY where
    the real tag is present (never asserts a panel ran), so it is strictly
    stronger than --decline-pending. Returns a process exit code.
    """
    root, spec_rel = _resolve_marker_root_and_key(spec_dir, project_root)
    try:
        restored = restore_anchor_for_prefix(root, spec_rel)
    except MarkerCorruptError as exc:
        print(
            f"Cannot restore: {exc}. The marker is corrupt; inspect or delete "
            f".sdd/pending-review.json manually."
        )
        return 1
    if restored:
        noun = "obligation" if len(restored) == 1 else "obligations"
        print(
            f"Restored anchor; cleared {len(restored)} satisfied {noun} "
            f"(genuine upstream-panel tag present): {', '.join(restored)}"
        )
    else:
        print(
            f"No restorable obligations for {spec_dir} (none carry a genuine "
            f"upstream-panel tag yet)."
        )
    return 0


def _handle_approve(args, spec_dir: Path, project_root: Optional[Path]) -> int:
    """`--approve {spec,design,tasks}` mode (audit R3.2 — extracted from main).

    Gates on the directory↔identifier cross-check (all three targets) and, unless
    --force/--task-tick, the matching phase validator (Decision E), then stamps
    via approve_document. Returns a process exit code.
    """
    file_map = {"spec": "spec.md", "design": "design.md", "tasks": "tasks.md"}
    target = resolve_artifact(spec_dir, file_map[args.approve])
    if not target.is_file():
        print(f"Error: {target} does not exist")
        return 2
    # Directory<->identifier cross-check gates ALL three approve targets
    # (spec/design/tasks). It reads the identifier from spec.md, so it runs
    # for design/tasks approvals too; a mismatch blocks approval before any
    # file is written.
    dir_check = check_dir_identifier(spec_dir)
    if not dir_check.passed:
        print(dir_check.summary())
        print(
            f"Refusing to approve {target.name}: spec-directory cross-check "
            f"FAILed. Fix the directory name or in-file identifier above."
        )
        return 1

    # Decision E (mirrored from validate_blueprint) — gate approval on the
    # matching phase validator. Approving a structurally-broken document
    # (missing sections, unresolved [TBD]s, a panel that never ran, an
    # unapproved upstream phase) silently corrupts state and recreates the
    # "approved, but next validate FAILs" 3am scenario the blueprint gate
    # exists to prevent. The design/tasks validators also run
    # check_previous_phase_approved, so this gate additionally enforces the
    # Specify -> Design -> Tasks ordering on the approve path. --force
    # overrides after the user has read the FAIL items.
    #
    # Skipped under --task-tick: that is the Phase-4 carve-out for
    # re-stamping tasks.md after ticking already-approved tasks; the content
    # was gated at the initial `--approve tasks`, and re-validating each tick
    # would risk blocking the interactive implement loop.
    if not args.force and not args.task_tick:
        if args.approve == "spec":
            pre_result = validate_spec(spec_dir)
        else:
            gate_language, _ = resolve_language(
                spec_dir,
                explicit=args.language,
                detector=detect_language,
                known_languages=list(LANGUAGE_PROFILES.keys()),
                project_root=project_root,
            )
            if args.approve == "design":
                pre_result = validate_design(spec_dir, gate_language)
            else:
                pre_result = validate_tasks(spec_dir, gate_language)
        if not pre_result.passed:
            print(f"Refusing to approve {target.name}: validation FAILed.")
            print(pre_result.summary())
            print(
                "\nFix the FAIL items above, OR re-run with --force to "
                "approve anyway (you take responsibility for the "
                "approved-but-invalid state)."
            )
            return 1

    try:
        stamped = approve_document(
            target, task_tick=args.task_tick, project_root=project_root
        )
    except MarkerCorruptError as exc:
        # The document was stamped (atomic) before restamp_or_suppress hit the
        # corrupt marker — surface it cleanly instead of a traceback, and exit
        # non-zero so the operator re-records the obligation (audit R2.6).
        print(
            f"WARNING: {target} was stamped, but its re-approval obligation "
            f"was NOT recorded: {exc}. The .sdd/pending-review.json marker is "
            f"corrupt (e.g. unresolved git conflict markers). Fix it and "
            f"re-run --approve so the obligation for this edit is recorded.",
            file=sys.stderr,
        )
        return 1
    return 0 if stamped else 1


def _handle_set_language(args, spec_dir: Path, project_root: Optional[Path]) -> int:
    """`--set-language` mode (audit R3.2 — extracted from main).

    The single, explicit write path for the declare-once store. Deliberately
    separate from --approve — it touches NO content hash and does NOT run during
    approval, so it cannot collide with the CFC cascade. Returns a process exit
    code.
    """
    root = arch_find_project_root(spec_dir, project_root)
    written = write_arch_config(
        root,
        args.set_language,
        list(LANGUAGE_PROFILES.keys()),
        source="user",
    )
    print(f"Persisted stack '{args.set_language}' to {written}")
    return 0


def _handle_completion_gate(args, spec_dir: Path, project_root: Path) -> int:
    """`--completion-gate` mode (R5). Resolves the stack via the shared
    `resolve_language` precedence — exactly as `_run_validation` does, so R5
    cannot drift from R3/R4 on the stack — then runs the test-existence
    cross-check. Returns a process exit code (1 if anything FAILed, else 0;
    missing tests are WARN by default and only FAIL under `--strict-r5`)."""
    language, language_source = resolve_language(
        spec_dir,
        explicit=args.language,
        detector=detect_language,
        known_languages=list(LANGUAGE_PROFILES.keys()),
        project_root=project_root,
    )
    result = validate_completion_gate(
        spec_dir, project_root, language, strict_r5=args.strict_r5
    )
    print(f"Completion gate: {spec_dir}")
    print(f"Language:        {language} (from {language_source})\n")
    print(result.summary())
    print()
    if result.passed and not result.has_warnings:
        print("Completion gate passed.")
    elif result.passed:
        print("Completion gate passed with warnings. Review WARN items above.")
    else:
        print("Completion gate failed. See FAIL items above.")
    return 0 if result.passed else 1


def _run_validation(args, spec_dir: Path, project_root: Optional[Path]) -> int:
    """Default mode: validate the requested phase(s), reconcile pending-review,
    print the summary (audit R3.2 — extracted from main). Returns a process exit
    code (1 if anything FAILed, else 0)."""
    # Resolve the stack via the shared resolver: explicit flag > persisted config
    # > marker auto-detect (which itself falls back to the neutral profile). This
    # is the SAME code path any other consumer uses, so the prose layer and the
    # script layer cannot drift to different answers.
    language, language_source = resolve_language(
        spec_dir,
        explicit=args.language,
        detector=detect_language,
        known_languages=list(LANGUAGE_PROFILES.keys()),
        project_root=project_root,
    )
    use_json = args.output == "json"

    if not use_json:
        print(f"Validating: {spec_dir}")
        print(f"Language:   {language} (from {language_source})\n")

    all_passed = True
    has_any_warnings = False
    json_output: dict = {
        "spec_dir": str(spec_dir),
        "language": language,
        "language_source": language_source,
        "phases": {},
    }
    validators = {
        "spec": ("Spec (spec.md)", lambda d: validate_spec(d)),
        "design": ("Design (design.md)", lambda d: validate_design(d, language)),
        "tasks": ("Tasks (tasks.md)", lambda d: validate_tasks(d, language)),
    }

    for phase_key, (label, validator) in validators.items():
        if args.phase not in ("all", phase_key):
            continue

        # In "all" mode, skip phases whose files don't exist yet
        _bare = "spec.md" if phase_key == "spec" else f"{phase_key}.md"
        expected_file = resolve_artifact(spec_dir, _bare)
        if args.phase == "all" and not expected_file.exists():
            continue

        result = validator(spec_dir)

        if not result.passed:
            status = "FAILED"
        elif result.has_warnings:
            status = "PASSED (with warnings)"
        else:
            status = "PASSED"

        if use_json:
            json_output["phases"][phase_key] = {
                "status": status,
                "checks": result.to_dict(),
            }
        else:
            print(f"{label}: {status}")
            print(result.summary())
            print()

        if not result.passed:
            all_passed = False
        if result.has_warnings:
            has_any_warnings = True

    # R2 (dispatch-level): reconcile pending-review ONCE for this spec dir,
    # regardless of --phase (so --phase design/tasks can't bypass the gate, and
    # an absent spec.md doesn't make a design/tasks obligation vanish). Surfaced
    # as a top-level `pending_review` result — uniform with validate_blueprint.
    root, spec_rel = _resolve_marker_root_and_key(spec_dir, project_root)
    pending_result = reconcile_to_result(
        root,
        spec_rel,
        decline_cmd=f"validate_spec.py {spec_dir} --decline-pending",
        restore_cmd=f"validate_spec.py {spec_dir} --restore-anchor",
    )
    if pending_result.checks:
        if use_json:
            json_output["pending_review"] = pending_result.to_dict()
        else:
            print(
                f"Pending-review: "
                f"{'FAILED' if not pending_result.passed else 'PASSED'}"
            )
            print(pending_result.summary())
            print()
        if not pending_result.passed:
            all_passed = False

    if use_json:
        if all_passed and not has_any_warnings:
            json_output["result"] = "passed"
        elif all_passed:
            json_output["result"] = "passed_with_warnings"
        else:
            json_output["result"] = "failed"
        print(json.dumps(json_output, indent=2))
    else:
        if all_passed and not has_any_warnings:
            print("All validations passed.")
        elif all_passed and has_any_warnings:
            print("All validations passed with warnings. Review WARN items above.")
        else:
            print("Some validations failed. See FAIL items above.")

    return 1 if not all_passed else 0


def main():
    parser = argparse.ArgumentParser(
        description="Validate spec-driven development artifacts.",
        epilog="Example: python validate_spec.py specs/F1-checkout-flow/",
    )
    parser.add_argument(
        "spec_dir",
        type=Path,
        help="Path to the spec directory (e.g., specs/F1-checkout-flow/)",
    )
    parser.add_argument(
        "--phase",
        choices=["spec", "design", "tasks", "all"],
        default="all",
        help="Which phase to validate (default: all existing files)",
    )
    # Mode flags are mutually exclusive: each selects a distinct operation, and
    # argparse rejects any combination (exit 2) rather than silently resolving by
    # if-ordering — e.g. `--approve spec --set-language java` previously approved
    # and silently dropped the language write (audit I3.2). --task-tick / --force
    # are modifiers of --approve, and --language modifies validation, so they stay
    # on the main parser.
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--approve",
        choices=["spec", "design", "tasks"],
        help="Approve a phase document (marks it approved with content hash)",
    )
    mode_group.add_argument(
        "--completion-gate",
        action="store_true",
        help="Phase-4 R5 mode: verify each code-touching task's declared test "
        "names actually exist in the codebase. Requires --project-root. Missing "
        "tests WARN by default; add --strict-r5 to make them FAIL.",
    )
    parser.add_argument(
        "--strict-r5",
        action="store_true",
        help="With --completion-gate: a declared-but-absent test FAILs (exit 1) "
        "instead of the default WARN (only valid with --completion-gate).",
    )
    parser.add_argument(
        "--task-tick",
        action="store_true",
        help="Phase-4 task-tick re-stamp of tasks.md: suppress the re-approval "
        "reminder + pending-review marker (only valid with --approve tasks).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --approve: stamp even when the phase validator FAILs (you "
        "take responsibility for the approved-but-invalid state). Mirrors "
        "validate_blueprint.py's Decision-E override.",
    )
    mode_group.add_argument(
        "--decline-pending",
        action="store_true",
        help="Clear this spec dir's pending-review obligations — an explicit, "
        "auditable decision to skip the upstream panel re-review.",
    )
    mode_group.add_argument(
        "--restore-anchor",
        action="store_true",
        help="Clear an UNSATISFIABLE (legacy re-anchored) pending-review "
        "obligation whose genuine `upstream-panel` tag is already present on an "
        "archived Trajectory row. Content-attested: clears ONLY when the real tag "
        "exists (never asserts a panel ran); no marker-cache editing.",
    )
    parser.add_argument(
        "--language",
        choices=list(LANGUAGE_PROFILES.keys()),
        default=None,
        help="Project language for THIS run (default: persisted config, else "
        "auto-detect). Does not persist; use --set-language to persist.",
    )
    mode_group.add_argument(
        "--set-language",
        choices=list(LANGUAGE_PROFILES.keys()),
        default=None,
        help="Persist the project's stack to .sdd/architecture.json (the "
        "declare-once store) and exit. The single, explicit write path.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory for language detection (default: walk up from spec_dir)",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

    spec_dir = args.spec_dir.resolve()
    if not spec_dir.is_dir():
        print(f"Error: {spec_dir} is not a directory")
        sys.exit(2)

    # R7 mixed-state surfacing: a non-blocking nudge ONLY when a mixed dir is
    # actually renamer-fixable (the helper suppresses the nudge on a same-artifact
    # collision, where the validator is about to FAIL with the ambiguity detail).
    _warn = mixed_state_warning(str(args.spec_dir), spec_dir)
    if _warn:
        print(_warn)

    project_root = args.project_root.resolve() if args.project_root else None
    if project_root is not None and not project_root.is_dir():
        print(f"Error: --project-root {project_root} is not a directory")
        sys.exit(2)

    # --task-tick is the Phase-4 carve-out; it is meaningful ONLY on a tasks
    # re-stamp. Reject it anywhere else (fail-closed; Never-Do).
    if args.task_tick and args.approve != "tasks":
        print("Error: --task-tick is only valid with --approve tasks")
        sys.exit(2)

    # R5 completion-gate guards (AD3), mirroring the --task-tick guard's exit-2
    # behaviour. --completion-gate needs a repo root to scan; --strict-r5 only
    # modifies --completion-gate.
    if args.completion_gate and project_root is None:
        parser.error("--completion-gate requires --project-root")
    if args.strict_r5 and not args.completion_gate:
        parser.error("--strict-r5 is only valid with --completion-gate")

    # Best-effort .sdd/ cruft cleanup at process exit (WORKING-NOTES Item 2).
    # Registered AFTER the arg-validation sys.exit(2)/parser.error guards above
    # (a malformed invocation exits before registering) and before the mode
    # dispatch. Uses _resolve_marker_root_and_key(...)[0] — the SAME write-side
    # root the run's marker ops use — NOT raw arch_find_project_root, which would
    # sweep an unrelated .sdd/ under a non-ancestor --project-root (AD1).
    atexit.register(
        sweep_sdd_cruft, _resolve_marker_root_and_key(spec_dir, project_root)[0]
    )

    # Mode dispatch (audit R3.2). The mode flags are argparse-mutually-exclusive,
    # so at most one of these is set; each handler returns a process exit code.
    # The default (no mode flag) runs validation.
    if args.decline_pending:
        sys.exit(_handle_decline_pending(spec_dir, project_root))
    if args.restore_anchor:
        sys.exit(_handle_restore_anchor(spec_dir, project_root))
    if args.approve:
        sys.exit(_handle_approve(args, spec_dir, project_root))
    if args.completion_gate:
        sys.exit(_handle_completion_gate(args, spec_dir, project_root))
    if args.set_language:
        sys.exit(_handle_set_language(args, spec_dir, project_root))

    sys.exit(_run_validation(args, spec_dir, project_root))


if __name__ == "__main__":
    # Fail-closed (design.md:349): an uncaught ArtifactAmbiguityError from any
    # resolve_artifact site — including the no-`result` soft gates
    # (find_project_root, expected_file) and the --approve target — exits
    # non-zero BEFORE any content hash is stamped. The boundary is shared so a
    # new entrypoint can't forget it.
    run_cli_failclosed(main)
