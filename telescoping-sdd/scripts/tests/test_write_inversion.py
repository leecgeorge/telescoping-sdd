"""Regression guard for write-inversion drafting (feature: subagent-write-inversion).

Asserts the write-inversion pattern is PRESENT and the old return-the-draft pattern
is ABSENT across the 15 patched methodology files:
  - 6 phase reference files (EC-1 agent directive + EC-2 caller line)
  - 6 drafting agent definitions (EC-3 `## Iteration`)
  - 2 examples.md files (EC-5)
  - 1 shared self-review discipline file (EC-4, `## When You Are Done`)

Markers are checked WITHIN their section/block (not file-wide) where a file-wide check
could pass on a half-applied patch — the caller line legitimately contains "manifest",
so the agent-directive marker is scoped to the invoking block / `## Iteration` /
`## When You Are Done`. The `Write` token is matched as a tool reference (not 'rewrite'/
'wrote'). Caller-side checks key on the token "agent-written" (zero pre-patch occurrences).

See specs/subagent-write-inversion/{spec,design}.md (R4; AD2-AD9; DEF-01).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

# --- Forbidden phrases (copied verbatim from the source files) ---
FORBIDDEN_RETURN_DRAFT = "return a complete, clean draft"
FORBIDDEN_RETURN_CLEAN = "return a clean, complete document — not a diff"  # U+2014 em-dash, NOT a hyphen
FORBIDDEN_RETURN_DRAFT_TO_CLAUDE = "return your draft to the calling Claude"
FORBIDDEN_RETURN_COMPLETE_DOC = "Return the complete, reviewed document"
FORBIDDEN_RETURN_DRAFT_FOR_CLAUDE = "return the draft for the calling Claude to resolve"
FORBIDDEN_BEFORE_RETURNING = "Before returning a draft to the calling skill"
FORBIDDEN_WRITE_RETURNED = "Write the returned draft"

# --- Old caller stem (file-wide absence check; unique to the caller line) ---
OLD_CALLER_STEM = "After the agent returns the draft, write it to"

# --- Presence markers ---
MARKER_WRITE_TOOL_REGEX = re.compile(r"(?<![a-z])Write(?![a-z])")  # tool ref; excludes rewrite/overwrite/wrote
MARKER_MANIFEST_TOKEN = "manifest"  # section-scoped only — caller line uses it too
MARKER_AGENT_WRITTEN = "agent-written"  # zero pre-patch occurrences; guards caller lines + examples.md
# DEF-01 re-read-after-revision guard: verbatim EC-2 phrase, zero pre-patch in all six phase files.
MARKER_REREAD_CLAUSE = "On any re-invocation, re-`Read`"


class SectionMissingError(AssertionError):
    """Raised when an expected section/block is absent — surfaces as a named test failure."""

    def __init__(self, path: Path, target: str) -> None:
        super().__init__(f"{path}: expected section/block not found: {target!r}")


def extract_invoking_block(text: str, path: Path = Path("<unknown>")) -> str:
    """Return the contiguous bullet run beginning at 'When invoking the agent, provide:'.

    Matches bullets at ANY indent (``^\\s*-\\s``) so the indented stack-profile
    sub-bullets are included; stops at the first blank line, '##' heading, or
    non-indented non-bullet line (e.g. 'Required sections:'). Raises rather than
    returning '' so an absence assertion cannot pass vacuously on a structural break.
    """
    bullet_re = re.compile(r"^\s*-\s")
    lines = text.splitlines(keepends=True)
    header = "When invoking the agent, provide:"
    start = None
    for i, line in enumerate(lines):
        if header in line:
            start = i + 1
            break
    if start is None:
        raise SectionMissingError(path, header)
    block_lines = []
    for line in lines[start:]:
        stripped = line.rstrip("\n")
        if not stripped.strip() or stripped.startswith("##") or not bullet_re.match(stripped):
            break
        block_lines.append(line)
    if not block_lines:
        raise SectionMissingError(path, f"bullet block after {header!r}")
    return "".join(block_lines)


def extract_section(text: str, heading: str, path: Path = Path("<unknown>")) -> str:
    """Return a '##'-level section body (heading line excluded), bounded by the next '##'.

    Heading match is full-line, so '## Iteration' does not collide with '## Iteration Rules'.
    Raises SectionMissingError (not pytest.fail; not '') if the heading is absent.
    """
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.rstrip("\n\r ") == heading.rstrip():
            start = i + 1
            break
    if start is None:
        raise SectionMissingError(path, heading)
    section_lines = []
    for line in lines[start:]:
        if line.startswith("##"):
            break
        section_lines.append(line)
    return "".join(section_lines)


def has_write_tool_ref(text: str) -> bool:
    """True if text contains a tool-reference `Write` (case-sensitive, word-boundary)."""
    return bool(MARKER_WRITE_TOOL_REGEX.search(text))


def has_manifest(text: str) -> bool:
    return MARKER_MANIFEST_TOKEN in text


def has_agent_directive_marker(text: str) -> bool:
    """True iff section-scoped text contains BOTH the Write tool ref AND 'manifest'."""
    return has_write_tool_ref(text) and has_manifest(text)


# --- Path / case constants ---
_SDD_REFS = _REPO_ROOT / "telescoping-sdd/skills/spec-driven-dev/references"
_PB_REFS = _REPO_ROOT / "telescoping-sdd/skills/project-blueprint/references"
_AGENTS = _REPO_ROOT / "telescoping-sdd/agents"

PHASE_FILE_CASES = [
    pytest.param(_SDD_REFS / "phase-specify.md", id="phase-specify"),
    pytest.param(_SDD_REFS / "phase-design.md", id="phase-design"),
    pytest.param(_SDD_REFS / "phase-tasks.md", id="phase-tasks"),
    pytest.param(_PB_REFS / "phase-scope.md", id="phase-scope"),
    pytest.param(_PB_REFS / "phase-architecture.md", id="phase-architecture"),
    pytest.param(_PB_REFS / "phase-plan.md", id="phase-plan"),
]

AGENT_FILE_CASES = [
    pytest.param(_AGENTS / "feature-spec-analyst.md", id="agent-feature-spec"),
    pytest.param(_AGENTS / "feature-architecture-analyst.md", id="agent-feature-arch"),
    pytest.param(_AGENTS / "feature-task-analyst.md", id="agent-feature-task"),
    pytest.param(_AGENTS / "project-spec-analyst.md", id="agent-project-spec"),
    pytest.param(_AGENTS / "project-architecture-analyst.md", id="agent-project-arch"),
    pytest.param(_AGENTS / "project-plan-analyst.md", id="agent-project-plan"),
]

EXAMPLES_FILE_CASES = [
    pytest.param(_SDD_REFS / "examples.md", id="examples-sdd"),
    pytest.param(_PB_REFS / "examples.md", id="examples-pb"),
]

SHARED_SELF_REVIEW_PATH = _REPO_ROOT / "telescoping-sdd/agent-references/agent-self-review-instructions.md"


@pytest.mark.parametrize("path", PHASE_FILE_CASES)
def test_phase_file_write_inversion(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    block = extract_invoking_block(text, path)
    # (a) old agent-directive phrase absent from the invoking block (section-scoped)
    assert FORBIDDEN_RETURN_DRAFT not in block, f"{path}: old phrase still present in invoking block"
    # (b) agent-directive marker present in the invoking block (section-scoped)
    assert has_agent_directive_marker(block), f"{path}: Write+manifest marker absent from invoking block"
    # (c) caller anchor present file-wide AND absent from the invoking block (pins it to the caller region)
    assert MARKER_AGENT_WRITTEN in text, f"{path}: '{MARKER_AGENT_WRITTEN}' caller token absent (file-wide)"
    assert MARKER_AGENT_WRITTEN not in block, (
        f"{path}: '{MARKER_AGENT_WRITTEN}' must live on the caller line, not the invoking block"
    )
    # (d) old caller stem absent file-wide
    assert OLD_CALLER_STEM not in text, f"{path}: old caller stem still present (file-wide)"
    # (e) pairwise: both sides of the patch present in disjoint regions
    assert has_agent_directive_marker(block) and MARKER_AGENT_WRITTEN in text and MARKER_AGENT_WRITTEN not in block, (
        f"{path}: pairwise check failed — one side of the patch may be missing"
    )
    # (f) DEF-01 re-read-after-revision guard (file-wide; verbatim EC-2 phrase, zero pre-patch)
    assert MARKER_REREAD_CLAUSE in text, (
        f"{path}: re-read-after-revision clause ({MARKER_REREAD_CLAUSE!r}) absent (file-wide)"
    )


@pytest.mark.parametrize("path", AGENT_FILE_CASES)
def test_agent_iteration_write_inversion(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    section = extract_section(text, "## Iteration", path)
    assert has_agent_directive_marker(section), f"{path}: Write+manifest marker absent from ## Iteration"
    assert FORBIDDEN_RETURN_CLEAN not in section, f"{path}: forbidden phrase (em-dash) still present"
    assert FORBIDDEN_RETURN_DRAFT_TO_CLAUDE not in section, f"{path}: 'return your draft' phrase still present"


@pytest.mark.parametrize("path", EXAMPLES_FILE_CASES)
def test_examples_write_inversion(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert FORBIDDEN_WRITE_RETURNED not in text, f"{path}: 'Write the returned draft' still present"
    assert MARKER_AGENT_WRITTEN in text, f"{path}: 'agent-written' token absent"


def test_shared_self_review_write_inversion() -> None:
    text = SHARED_SELF_REVIEW_PATH.read_text(encoding="utf-8")
    section = extract_section(text, "## When You Are Done", SHARED_SELF_REVIEW_PATH)
    assert has_agent_directive_marker(section), (
        f"{SHARED_SELF_REVIEW_PATH}: Write+manifest marker absent from ## When You Are Done"
    )
    # All forbidden phrases checked file-wide: EC-4c lives in '## When You Are Done',
    # EC-4b in '## Iteration Rules', EC-4a in the line-3 intro — section-scoping would pass vacuously.
    assert FORBIDDEN_RETURN_COMPLETE_DOC not in text, (
        f"{SHARED_SELF_REVIEW_PATH}: 'Return the complete, reviewed document' still present"
    )
    assert FORBIDDEN_RETURN_DRAFT_FOR_CLAUDE not in text, (
        f"{SHARED_SELF_REVIEW_PATH}: 'return the draft for the calling Claude' still present"
    )
    assert FORBIDDEN_BEFORE_RETURNING not in text, f"{SHARED_SELF_REVIEW_PATH}: EC-4a intro stem still present"
