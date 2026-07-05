"""Shared leaf: the RESET-CHECKPOINT reset-at-gate advisory (both validators). [C1]

Owns the tier→gate→re-read-list table (`RESET_READ_LISTS`, DM1), a pure message
builder (`build_reset_checkpoint_advisory`, I1), and a thin guarded printer
(`emit_reset_checkpoint`, I2) that both validators call after a successful
phase-gate `--approve` stamp — and `validate_spec.py` after a successful
`--completion-gate` pass — to print a one-line `RESET-CHECKPOINT:` stdout
advisory. The advisory turns each approval gate into a high-fidelity `/clear`
resume recipe by naming the just-approved gate, the next step, and the exact
files to re-read on resume (R1, R2, R4).

Dependency direction (AD2 — leaf discipline, acyclic): this module imports only
stdlib (`sys`, `pathlib`) and NEVER a validator. The re-read table is
self-contained static data, so no validator import is needed; the phase-name
`next_step_label`s are kept as static display strings (deriving them would force
a validator import) and are instead guarded against drift at the test layer
(`test_reset_checkpoint.py::test_next_step_label_matches_validator_phase_constants`).
The import-guard test asserts the no-validator-import rule.

The advisory is decoration: it is emitted AFTER the load-bearing stamp/gate
returns, feeds no content hash, writes no file, and its failure can never change
a caller's exit code (`emit_reset_checkpoint` swallows every BaseException,
R8/R9). Modeled on `archive_pass.py`'s `STRICT-BAR-SIGNAL:` (builder-prints-
caller) and `run_state.safe_print`'s `except BaseException` swallow.
"""

from __future__ import annotations

import sys
from pathlib import Path

# telescoping-sdd/ — the base every re-read path resolves against (R7 guard).
# reset_checkpoint.py lives at telescoping-sdd/scripts/, so parents[1] is the
# plugin root in both `--plugin-dir` dev mode and a marketplace cache install
# (only the absolute prefix differs; `.resolve()` absorbs it — SEAL-05).
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]

# DM1 — the re-read table. Keyed by (tier, gate) where `gate` is the
# just-approved gate (same name as the function parameter). Value is
# (next_step_label, [plugin-root-relative reread paths]). Exactly six keys; the
# SDD completion gate is deliberately absent (terminal, no list — built via
# completion_gate=True). Every path is asserted on disk by the R7 guard.
RESET_READ_LISTS = {
    ("sdd", "spec"): (
        "Design",
        [
            "skills/spec-driven-dev/references/phase-design.md",
            "skills/spec-driven-dev/references/hash-and-cascade.md",
            "skills/spec-driven-dev/references/panel-review.md",
        ],
    ),
    ("sdd", "design"): (
        "Tasks",
        [
            "skills/spec-driven-dev/references/phase-tasks.md",
            "skills/spec-driven-dev/references/hash-and-cascade.md",
            "skills/spec-driven-dev/references/panel-review.md",
        ],
    ),
    ("sdd", "tasks"): (
        "Implement",
        [
            "skills/spec-driven-dev/references/hash-and-cascade.md",
            "skills/spec-driven-dev/references/workflow-overview.md",
        ],
    ),
    ("blueprint", "scope"): (
        "Architecture",
        [
            "skills/project-blueprint/references/phase-architecture.md",
            "skills/project-blueprint/references/hash-and-cascade.md",
            "skills/project-blueprint/references/panel-review.md",
        ],
    ),
    ("blueprint", "architecture"): (
        "Plan",
        [
            "skills/project-blueprint/references/phase-plan.md",
            "skills/project-blueprint/references/hash-and-cascade.md",
            "skills/project-blueprint/references/panel-review.md",
        ],
    ),
    # Terminal-for-its-tier yet still carries a handoff list — the re-read list
    # deliberately points into the *destination* SDD skill's references (H02;
    # the builder adds the terminal framing sentence).
    ("blueprint", "plan"): (
        "hand off to per-feature spec-driven-dev",
        [
            "skills/spec-driven-dev/references/phase-specify.md",
            "skills/spec-driven-dev/references/workflow-overview.md",
        ],
    ),
}

# Display label for the just-approved gate (the "<X> gate approved" clause).
# Kept static (runtime-deriving would import a validator, breaking AD2);
# test_gate_display_matches_validator_phase_constants guards against drift.
_GATE_DISPLAY = {
    "spec": "Specify",
    "design": "Design",
    "tasks": "Tasks",
    "scope": "Scope",
    "architecture": "Architecture",
    "plan": "Plan",
}

_SKILLS_PREFIX = "skills/"


def reread_list_for(tier: str, gate: str):
    """Return (next_step_label, [plugin-root-relative reread paths]) or KeyError.

    The raw (unstripped) table value — the R7/consistency guards resolve these
    plugin-root-relative paths against `_PLUGIN_ROOT` directly (DEF-01: public).
    """
    return RESET_READ_LISTS[(tier, gate)]


def _render_paths(paths):
    """Strip the leading `skills/` prefix and join comma-separated for display."""
    rendered = [
        p[len(_SKILLS_PREFIX):] if p.startswith(_SKILLS_PREFIX) else p
        for p in paths
    ]
    return ", ".join(rendered)


def build_reset_checkpoint_advisory(
    tier: str, gate: str, *, completion_gate: bool = False
) -> str:
    """Build the one-line RESET-CHECKPOINT advisory (pure — no I/O).

    See module docstring / design I1. `completion_gate=True` yields the terminal,
    list-free SDD completion variant; `(tier, gate) == ("blueprint", "plan")`
    yields the terminal-framed handoff variant that STILL carries its re-read
    list (H02). Every other gate gets the generic per-gate framing. Raises
    KeyError on an unknown (tier, gate) when completion_gate is False.
    """
    if completion_gate:
        return (
            "RESET-CHECKPOINT: Implement completion gate passed for this run "
            "(gate checks only — not an assertion of overall feature completion; "
            "immediate post-completion housekeeping may still benefit from "
            "current context). Highest-value reset point — offer the user a "
            "context reset before starting new work."
        )

    next_label, paths = reread_list_for(tier, gate)
    gate_label = _GATE_DISPLAY.get(gate, gate)
    rendered = _render_paths(paths)

    if (tier, gate) == ("blueprint", "plan"):
        return (
            f"RESET-CHECKPOINT: {gate_label} gate approved (terminal blueprint "
            f"gate); next {next_label}. Re-read on resume: {rendered}. "
            f"Highest-value blueprint reset point — offer the user a context "
            f"reset before handing off."
        )

    return (
        f"RESET-CHECKPOINT: {gate_label} gate approved; next phase {next_label}. "
        f"Re-read on resume: {rendered}. Offer the user a context reset before "
        f"starting {next_label}."
    )


def emit_reset_checkpoint(
    tier: str, gate: str, *, completion_gate: bool = False
) -> None:
    """Best-effort: build + print the advisory to stdout. NEVER raises (I2, R9).

    On ANY BaseException (KeyError from a bad table key, BrokenPipeError on the
    write, anything) the failure is swallowed and a minimal, exception-text-free
    trace is written to stderr: `RESET-CHECKPOINT-DEBUG: <ExceptionTypeName>`
    (type name only — never `str(exc)`, avoiding the control-char/newline spoof
    channel). The stderr write is itself guarded so a broken stderr cannot
    resurrect the exception. Returns None unconditionally, so it can never change
    a caller's exit code (R9). Writes no file (R8).

    The builder is invoked through the module-global name so a test can
    `monkeypatch.setattr` it to a raiser (DEF-10).
    """
    try:
        message = build_reset_checkpoint_advisory(
            tier, gate, completion_gate=completion_gate
        )
        print(message)
    except BaseException as exc:  # noqa: BLE001 — mirrors run_state.safe_print
        try:
            print(
                f"RESET-CHECKPOINT-DEBUG: {type(exc).__name__}", file=sys.stderr
            )
        except BaseException:  # noqa: BLE001 — innermost guard; never resurrect
            pass
    return None
