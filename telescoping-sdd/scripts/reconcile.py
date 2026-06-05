"""Cross-repo reconcile integrator for Cross-Project Derivation (CPD C5 / R8 / I11).

`reconcile.py` is a SHARED-SCRIPT ENTRY POINT (run by path:
``python telescoping-sdd/scripts/reconcile.py``), not a skill validator. Because
nothing else puts the shared `scripts/` directory on `sys.path` for it, `main()`
performs the `sys.path` bootstrap itself BEFORE importing the CPD shared modules
(`project_link`, `project_registry`, `master_feature`, `ucr`, `blueprint_common`,
`spec_dirname`).

What it does (default mode), given two repos linked by `.sdd/projects.json`:

  * **Bijection** — every master feature with an `**Implemented by:** <alias>`
    line must have a matching derived directory `<master>--F<n>-<slug>` in the
    derived repo, and vice-versa. A dangling `Implemented by` (no derived dir),
    a one-sided derived dir (no `Implemented by`), and a likely-rename (the
    feature number exists under a DIFFERENT alias) each emit a FAIL.
  * **Contract drift** — the current master contract hash
    (`master_feature.compute_master_contract_hash`) is compared against the
    author-pasted `**Master contract hash:**` in the derived `spec.md`. A real
    64-hex mismatch is a WARN; `unbound` is "needs first stamp" (not shipped) or
    the louder `shipped-but-unbound` WARN (shipped); an unparseable master block
    surfaces "could not compute master hash" — never a crash, never false drift.
  * **Open UCRs** — `## Upstream Change Requests` entries with `status: open` in
    the derived `spec.md` are surfaced (via the `display_safe`-wrapped accessors).

ROBUSTNESS & SANITIZATION (design I11):

  * READ-ONLY — never writes `spec.md` / `PLAN.md`; it prints values to paste.
  * Sibling files (untrusted) are read ONLY through
    `project_registry.safe_read_sibling` (the I3 O_NOFOLLOW + fstat + S_ISREG +
    bounded-read + commonpath guard). No `eval` / `import` / `exec`.
  * Every untrusted string reaching stdout (UCR free text, sibling names,
    derived dir names) passes through `spec_dirname.display_safe`, so a control
    character cannot forge a FAIL/WARN line.
  * When the sibling/registry is absent or asymmetric, reconcile emits a
    visually distinct ``SKIPPED — ... nothing was reconciled`` line and exits 0:
    a true "nothing was checked" signal, never a false all-clear, never a FAIL.

Exit codes: 0 on a clean result, a WARN-skip, a needs-first-stamp, or any WARN;
1 on any FAIL (dangling link, one-sided derivation).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# sys.path bootstrap. `reconcile.py` is a shared-script ENTRY POINT — nothing
# else sets the path for it (unlike the skill validators, which are bootstrapped
# by their skill). Insert the shared `scripts/` dir BEFORE importing the CPD
# modules. This runs at import time so the helpers below can be imported by the
# test suite (which already inserts the path), and `main()` re-asserts it for the
# direct-invocation path.
# ---------------------------------------------------------------------------
_SHARED_SCRIPTS = str(Path(__file__).resolve().parent)
if _SHARED_SCRIPTS not in sys.path:
    sys.path.insert(0, _SHARED_SCRIPTS)

import blueprint_common  # noqa: E402
import master_feature  # noqa: E402
import project_link  # noqa: E402
import project_registry  # noqa: E402
import spec_dirname  # noqa: E402
import ucr  # noqa: E402

from blueprint_common import ValidationResult  # noqa: E402

# The derived-spec provenance FIELD grammar is owned by `project_link` (the
# single CPD-grammar owner) so this integrator and the `validate_spec` authoring
# gate read byte-identical field shapes — a shared script must not import a skill
# validator, so without this single owner the two kept duplicate copies that
# could silently drift. Only the constants reconcile actually uses are imported.
from project_link import (  # noqa: E402
    MASTER_CONTRACT_HASH_LINE_RE,
    MASTER_HASH_UNBOUND,
    MASTER_HASH_VALUE_RE,
)

# ---------------------------------------------------------------------------
# Field grammar (reconcile-local — the master-side `**Implemented by:**` line;
# the derived-spec field grammar above is shared, and the `### F<n>` block
# boundary comes from master_feature.iter_feature_blocks, not a local copy).
# ---------------------------------------------------------------------------

# `**Implemented by:** <alias>` inside a master feature block.
IMPLEMENTED_BY_LINE_RE = re.compile(
    r"^[ \t]*(?:[-*][ \t]+)?\*\*Implemented by:\*\*[ \t]*(.+?)[ \t]*$",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe(s: str) -> str:
    """Sanitize an untrusted string for stdout (the single choke point)."""
    return spec_dirname.display_safe(s)


def _strip_backticks(value: str) -> str:
    """Strip ONE balanced surrounding backtick pair from a captured field value.

    The master PLAN documents `**Implemented by:**` as "optionally backtick-wrapped"
    (`phase-plan.md`), and the producer pattern `validate_blueprint.IMPLEMENTED_BY_PATTERN`
    captures the BARE alias (its `` (`?)…\1 `` strips the backticks). reconcile's
    presence-detecting `IMPLEMENTED_BY_LINE_RE` deliberately captures the RAW value
    (so a malformed value is still seen as present for the bijection check), so it
    must normalize the same way before comparing against the registry's bare project
    alias — otherwise a valid `` `vps-edge` `` reads as != `vps-edge` and produces a
    spurious bijection FAIL.
    """
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def _load_master_features(master_plan_content: str) -> dict:
    """Return ``{feature_number: {"implemented_by": str|None}}``.

    One entry per ``### F<n>`` feature block in the master PLAN. ``implemented_by``
    is the block's ``**Implemented by:**`` value with any backtick wrap stripped
    (matching the producer), or ``None`` when absent. Used by the bijection check.

    The contract HASH is deliberately NOT computed here: it is needed exactly once
    per DERIVED dir (in `_check_contract_drift`, which recomputes it for that
    feature), so computing it for every master feature here was dead + doubled
    work — M wasted full-PLAN hash walks where D (<= M) suffice.

    Feature blocks come from `master_feature.iter_feature_blocks` (the single
    owner of the `### F<n>` block-boundary rule), so reconcile no longer
    re-derives that boundary with its own heading regexes. Never raises.
    """
    features: dict = {}
    for number, block in master_feature.iter_feature_blocks(master_plan_content):
        impl_m = IMPLEMENTED_BY_LINE_RE.search(block)
        # Normalize the captured value the SAME way the producer does (strip an
        # optional backtick wrap) so a documented `` `vps-edge` `` compares equal
        # to the registry's bare alias and does not false-FAIL the bijection.
        implemented_by = _strip_backticks(impl_m.group(1)) if impl_m is not None else None
        # A duplicate/reused feature number: the LAST PLAN block wins (the current
        # PLAN is authoritative — a reused number resolves to the live feature).
        features[number] = {"implemented_by": implemented_by}
    return features


def _load_derived_dirs(derived_specs_root: Path) -> dict:
    """Return ``{(master_project, feature_number): spec_dir}`` for derived dirs.

    Matches on the ``<master>--F<n>`` PREFIX only (via
    ``project_link.parse_derived_dirname``); the slug portion is ignored, so a
    slug difference never reads as a dangling link. Non-derived directory names
    are skipped. Never raises.
    """
    derived: dict = {}
    try:
        entries = sorted(derived_specs_root.iterdir())
    except OSError:
        return derived

    for entry in entries:
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        parsed = project_link.parse_derived_dirname(entry.name)
        if parsed is None:
            continue
        master_project, feature_number, _slug = parsed
        derived[(master_project, feature_number)] = entry

    return derived


def _check_bijection(
    master_features: dict,
    derived_dirs: dict,
    master_project: str,
    derived_project: str,
    result: ValidationResult,
) -> None:
    """Emit FAILs for dangling ``Implemented by`` links and one-sided derived dirs.

    * A master feature whose ``Implemented by`` names ``derived_project`` but has
      NO matching ``<master>--F<n>`` derived dir → dangling FAIL.
    * A derived dir keyed ``(master_project, F<n>)`` with no master feature that
      ``Implemented by``-points back → one-sided FAIL, UNLESS the feature number
      exists in the master PLAN under a DIFFERENT ``Implemented by`` alias, in
      which case it is a distinct likely-rename FAIL pointing at the
      alias-immutability remediation.

    The bijection is per FEATURE (``F<n>``), so two master features both
    ``Implemented by: <derived_project>`` resolve independently.
    """
    # Master → derived: every feature implemented by the derived project must
    # have a matching derived dir.
    for number, info in sorted(master_features.items()):
        implemented_by = info["implemented_by"]
        if implemented_by != derived_project:
            continue
        if (master_project, number) not in derived_dirs:
            result.add(
                "bijection: dangling implemented-by",
                False,
                detail=(
                    f"master feature F{number} is `**Implemented by:** "
                    f"{_safe(implemented_by)}` but no derived directory "
                    f"`{_safe(master_project)}--F{number}-<slug>` exists in "
                    f"`{_safe(derived_project)}`. Either create the derived "
                    f"feature or remove the `Implemented by` line."
                ),
            )

    # Derived → master: every derived dir must point back at a master feature
    # whose `Implemented by` names this derived project.
    for (dir_master, number), spec_dir in sorted(derived_dirs.items()):
        if dir_master != master_project:
            # The derived dir names a DIFFERENT master project than the one this
            # registry links; not part of this reconcile pair.
            continue
        info = master_features.get(number)
        bound_here = info is not None and info["implemented_by"] == derived_project
        if bound_here:
            continue

        if info is not None and info["implemented_by"] not in (None, derived_project):
            # The feature number exists, but `Implemented by` names a DIFFERENT
            # alias — most likely the project alias was renamed (forbidden once a
            # derivation link exists). Distinct, remediation-pointing FAIL.
            result.add(
                "bijection: likely rename",
                False,
                detail=(
                    f"derived directory `{_safe(spec_dir.name)}` points at "
                    f"master feature F{number}, but that feature is "
                    f"`**Implemented by:** {_safe(info['implemented_by'])}`, not "
                    f"`{_safe(derived_project)}`. This looks like a renamed "
                    f"project alias — renaming an alias once a derivation link "
                    f"exists is forbidden; restore the original alias rather "
                    f"than renaming."
                ),
            )
        else:
            # No master feature binds back (absent, or present with no/other-not-
            # this-project `Implemented by`) → one-sided derived dir.
            result.add(
                "bijection: one-sided derived dir",
                False,
                detail=(
                    f"derived directory `{_safe(spec_dir.name)}` has no matching "
                    f"master feature F{number} with `**Implemented by:** "
                    f"{_safe(derived_project)}` in `{_safe(master_project)}`. "
                    f"Either add the `Implemented by` line to the master feature "
                    f"or remove the derived directory."
                ),
            )


def _stored_derived_hash(derived_spec_content: str) -> Optional[str]:
    """Return the raw `**Master contract hash:**` value, or None if absent."""
    m = MASTER_CONTRACT_HASH_LINE_RE.search(derived_spec_content)
    return m.group(1) if m is not None else None


def _check_contract_drift(
    master_plan_content: str,
    derived_spec_content: str,
    master_feature_number: int,
    result: ValidationResult,
    *,
    derived_spec_dir: Optional[Path] = None,
) -> None:
    """Emit a drift WARN, surface unbound status, or report an unparseable block.

    Compares the CURRENT master contract hash for ``F<master_feature_number>``
    (computed via the single producer ``compute_master_contract_hash``) against
    the author-pasted ``**Master contract hash:**`` in the derived ``spec.md``:

    * master hash is ``None`` (feature block unparseable) → surface "could not
      compute master hash — verify PLAN feature-block format" (NOT a drift WARN,
      NOT a crash).
    * stored is ``unbound`` and the derived spec has NOT shipped → "needs first
      stamp", printing the current hash; no drift WARN.
    * stored is ``unbound`` and the derived spec HAS shipped
      (``blueprint_common.is_shipped``) → distinct louder ``shipped-but-unbound``
      WARN.
    * stored is a real 64-hex digest that differs from the current hash → drift
      WARN. Equal → PASS (no WARN).
    """
    current_hash = master_feature.compute_master_contract_hash(
        master_plan_content, master_feature_number
    )

    if current_hash is None:
        result.add(
            "contract drift: master hash unavailable",
            True,
            detail=(
                f"could not compute master hash for F{master_feature_number} — "
                f"verify the PLAN feature-block format. Drift detection is "
                f"inert for this feature until the block parses."
            ),
            warn_only=True,
        )
        return

    stored = _stored_derived_hash(derived_spec_content)

    if stored == MASTER_HASH_UNBOUND:
        try:
            shipped = (
                derived_spec_dir is not None
                and blueprint_common.is_shipped(derived_spec_dir)
            )
        except blueprint_common.ArtifactAmbiguityError:
            # A derived dir with both a bare and a prefixed form of spec/design/
            # tasks is unreadable for the shipped check; degrade to "not shipped"
            # (the quieter needs-first-stamp path) rather than letting the
            # ambiguity abort the whole cross-repo reconcile — matching the
            # degrade-not-abort discipline of the other reconcile reads.
            shipped = False
        if shipped:
            result.add(
                "contract drift: shipped-but-unbound",
                False,
                detail=(
                    f"derived feature F{master_feature_number} has SHIPPED with "
                    f"`**Master contract hash:** `unbound`` — drift "
                    f"detection is permanently disabled for a shipped feature. "
                    f"Stamp the current master hash now: `{_safe(current_hash)}`."
                ),
                warn_only=True,
            )
        else:
            result.add(
                "contract drift: needs first stamp",
                True,
                detail=(
                    f"derived feature F{master_feature_number} is `unbound` and "
                    f"not yet shipped — needs first stamp. Current master hash: "
                    f"`{_safe(current_hash)}`."
                ),
                warn_only=False,
            )
        return

    if stored is None:
        # No `**Master contract hash:**` line at all — treat as needs-first-stamp
        # so the author gets the current hash to paste (structural absence is the
        # validator's concern, not reconcile's).
        result.add(
            "contract drift: hash field absent",
            True,
            detail=(
                f"derived feature F{master_feature_number} has no "
                f"`**Master contract hash:**` line — stamp the current master "
                f"hash: `{_safe(current_hash)}`."
            ),
            warn_only=False,
        )
        return

    if not MASTER_HASH_VALUE_RE.match(stored):
        # A non-64-hex, non-`unbound` stored value is malformed; surface it but do
        # not call it drift (the structural FAIL belongs to validate_spec).
        result.add(
            "contract drift: stored hash malformed",
            True,
            detail=(
                f"derived feature F{master_feature_number} stored hash "
                f"`{_safe(stored)}` is not a 64-hex digest — cannot compare. "
                f"Current master hash: `{_safe(current_hash)}`."
            ),
            warn_only=True,
        )
        return

    if stored != current_hash:
        result.add(
            "contract drift: hash mismatch",
            False,
            detail=(
                f"master feature F{master_feature_number} contract drifted: "
                f"derived spec stamped `{_safe(stored)}` but the current master "
                f"hash is `{_safe(current_hash)}`. Re-review the master contract "
                f"and re-stamp the derived `**Master contract hash:**`."
            ),
            warn_only=True,
        )
    else:
        result.add(
            f"contract drift: F{master_feature_number} in sync",
            True,
            detail="derived hash matches the current master contract hash.",
        )


def _surface_open_ucrs(
    derived_spec_content: str,
    result: ValidationResult,
) -> None:
    """Print ``status: open`` UCR entries from the derived spec stanza.

    Parses via ``ucr.parse_ucr_stanza`` and surfaces ONLY ``open`` entries; an
    ``applied`` / ``withdrawn`` entry is intentionally NOT surfaced. Free-text
    fields are emitted through the ``display_safe``-wrapped accessors only, so a
    control character in a UCR body cannot forge a validator line.
    """
    parsed = ucr.parse_ucr_stanza(derived_spec_content)
    if not parsed.present:
        return

    for entry in parsed.entries:
        if entry.status() != "open":
            continue
        target = entry.target()
        target_safe = _safe(target) if target is not None else "<none>"
        proposed = entry.safe_proposed_change()
        rationale = entry.safe_rationale()
        detail = f"open UCR-{entry.number} targeting `{target_safe}`"
        if proposed:
            detail += f"; proposed change: {proposed}"
        if rationale:
            detail += f"; rationale: {rationale}"
        result.add(
            f"open UCR-{entry.number}",
            True,
            detail=detail,
            warn_only=True,
        )


def _print_link_mode(
    qualified_id: str,
    title: str,
    master_plan_content: Optional[str],
) -> int:
    """Print the derived dir name (+ master hash if reachable); return exit code.

    The ``<project>:F<n>`` argument is validated via ``parse_qualified_id`` FIRST;
    on ``None`` it prints an error and returns a non-zero exit code WITHOUT emitting
    a half-formed dir name. The printed ``<project>--F<n>-<slug>`` name round-trips
    through ``parse_derived_dirname`` (asserted by tests). When ``master_plan_content``
    is provided and the feature parses, the current master contract hash is also
    printed; otherwise the hash line is omitted (offline).
    """
    parsed = project_link.parse_qualified_id(qualified_id)
    if parsed is None:
        print(
            f"Error: `--print-link` argument {_safe(qualified_id)!r} is not a "
            f"valid `<project>:F<n>` qualified id; refusing to emit a "
            f"half-formed derived directory name."
        )
        return 2

    project, feature_number = parsed
    try:
        slug = spec_dirname.slugify(title)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    dirname = f"{project}--F{feature_number}-{slug}"

    # The generated name MUST round-trip through the derived-dirname parser.
    if project_link.parse_derived_dirname(dirname) is None:
        print(
            f"Error: generated directory name {_safe(dirname)!r} does not parse "
            f"as a derived directory name; check the title."
        )
        return 1

    print(f"Derived directory name: {_safe(dirname)}")
    print(f"  Add to the derived spec.md:")
    print(f"    **PLAN feature identifier:** `n/a`")
    print(f"    **Derived from:** `{project}:F{feature_number}`")

    if master_plan_content is not None:
        master_hash = master_feature.compute_master_contract_hash(
            master_plan_content, feature_number
        )
        if master_hash is not None:
            print(f"    **Master contract hash:** `{_safe(master_hash)}`")
        else:
            print(
                f"    **Master contract hash:** `unbound`  "
                f"(could not compute F{feature_number} master hash — verify the "
                f"PLAN feature-block format)"
            )
    else:
        print(
            f"    **Master contract hash:** `unbound`  "
            f"(master not reachable; run reconcile from the linked repo to stamp)"
        )

    return 0


# ---------------------------------------------------------------------------
# Default (reconcile) mode plumbing
# ---------------------------------------------------------------------------


def _find_sdd_root(start: Path) -> Optional[Path]:
    """Walk upward from ``start`` looking for a ``.sdd/projects.json`` registry.

    Returns the directory CONTAINING ``.sdd/`` — the same root the registry's
    relative sibling paths resolve against (design seam: the registry's relative
    paths resolve against the SAME root the registry was read from). Returns
    ``None`` if no registry is found before the filesystem root.
    """
    current = start.resolve()
    while True:
        if project_registry.config_path(current).is_file():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _skip(result: ValidationResult, message: str) -> None:
    """Emit a visually distinct WARN-skip line (never a false all-clear).

    A skip is a WARN (`passed=False, warn_only=True`), NOT a PASS — it must be
    visually distinct from a clean all-clear so a reader can never mistake "no
    sibling was reachable" for "bijection holds". It is NOT a FAIL, so the exit
    code stays 0.
    """
    result.add(
        "SKIPPED",
        False,
        detail=f"{message} — nothing was reconciled.",
        warn_only=True,
    )


def _run_reconcile(project_root: Path, result: ValidationResult) -> None:
    """Run the default cross-repo reconcile from ``project_root`` (the .sdd root).

    Resolves the registry, locates each named sibling, reads its PLAN.md through
    the safe sibling reader, and runs the bijection / drift / open-UCR checks.
    WARN-skips (no FAIL, exit 0) when the registry is missing or asymmetric or a
    sibling path is absent.
    """
    config = project_registry.read_projects_config(project_root)
    if config is None:
        _skip(
            result,
            f"no usable `.sdd/projects.json` registry under "
            f"`{_safe(str(project_root))}`",
        )
        return

    derived_project = config.get("thisProject")
    siblings = config.get("siblings") or []
    if not siblings:
        _skip(result, "registry names no siblings")
        return

    reconciled_any = False
    for sibling in siblings:
        name = sibling.get("name")
        if not isinstance(name, str):
            continue
        sibling_root = project_registry.find_sibling(config, name, project_root)
        if sibling_root is None:
            _skip(
                result,
                f"configured sibling `{_safe(name)}` was not found on disk or "
                f"does not look like a project root",
            )
            continue

        try:
            master_plan_path = blueprint_common.resolve_artifact(
                sibling_root / "blueprint", "PLAN.md"
            )
            master_plan_content = project_registry.safe_read_sibling(
                master_plan_path, sibling_root
            )
        except blueprint_common.ArtifactAmbiguityError:
            # CPD soft-read: a sibling repo carrying both PLAN.md and 03_PLAN.md
            # degrades to "unreadable" rather than aborting the whole reconcile.
            master_plan_content = None
        if master_plan_content is None:
            _skip(
                result,
                f"sibling `{_safe(name)}` has no readable `blueprint/PLAN.md`",
            )
            continue

        _reconcile_pair(
            master_project=name,
            derived_project=derived_project if isinstance(derived_project, str) else "",
            master_plan_content=master_plan_content,
            derived_root=project_root,
            result=result,
        )
        reconciled_any = True

    if not reconciled_any and result.passed and not result.has_warnings:
        # Defensive: should not happen (each branch above emits a skip), but never
        # leave a silent all-clear when nothing was actually reconciled.
        _skip(result, "no sibling could be reconciled")


def _reconcile_pair(
    master_project: str,
    derived_project: str,
    master_plan_content: str,
    derived_root: Path,
    result: ValidationResult,
) -> None:
    """Run all checks for ONE (master, derived) repo pair."""
    master_features = _load_master_features(master_plan_content)
    derived_specs_root = derived_root / "specs"
    derived_dirs = _load_derived_dirs(derived_specs_root)

    _check_bijection(
        master_features,
        derived_dirs,
        master_project,
        derived_project,
        result,
    )

    # Per-feature drift + open-UCR surfacing for every derived dir that points at
    # THIS master project.
    for (dir_master, number), spec_dir in sorted(derived_dirs.items()):
        if dir_master != master_project:
            continue
        try:
            spec_content = blueprint_common.read_file(
                blueprint_common.resolve_artifact(spec_dir, "spec.md")
            )
        except blueprint_common.ArtifactAmbiguityError:
            spec_content = None  # degrade (treat the derived spec as unreadable)
        if spec_content is None:
            continue
        _check_contract_drift(
            master_plan_content,
            spec_content,
            number,
            result,
            derived_spec_dir=spec_dir,
        )
        _surface_open_ucrs(spec_content, result)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit(result: ValidationResult) -> None:
    """Print the result in the validators' header/PASS-WARN-FAIL line style."""
    print("Reconcile:")
    if result.checks:
        print(result.summary())
    else:
        print("  [PASS] reconcile — nothing to report.")
    print()
    if not result.passed:
        print("Reconcile FAILED — resolve the FAIL items above.")
    elif result.has_warnings:
        print("Reconcile completed with WARN/skip items — review the output above.")
    else:
        print("Reconcile clean — bijection holds and no drift detected.")


def main(argv: Optional[list] = None) -> int:
    """CLI entry point. Returns the process exit code (0 clean/skip, 1 any FAIL).

    Default mode reconciles both repos located via the nearest enclosing
    ``.sdd/projects.json``. ``--print-link <project>:F<n> --title "..."`` mode
    prints the derived directory name and (if the master is reachable) the
    current master contract hash, then exits.
    """
    # Re-assert the sys.path bootstrap for the direct-invocation path (idempotent
    # with the import-time insert above).
    if _SHARED_SCRIPTS not in sys.path:
        sys.path.insert(0, _SHARED_SCRIPTS)

    parser = argparse.ArgumentParser(
        prog="reconcile.py",
        description="Cross-repo reconcile integrator for Cross-Project Derivation.",
    )
    parser.add_argument(
        "--print-link",
        metavar="<project>:F<n>",
        help="Print the derived directory name (and master hash, if reachable) "
        "for a master feature; does not reconcile.",
    )
    parser.add_argument(
        "--title",
        metavar='"Feature title"',
        help="Feature title used to generate the slug for --print-link.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Override the project root (the directory containing .sdd/); "
        "defaults to the nearest enclosing .sdd/projects.json from the cwd.",
    )
    args = parser.parse_args([] if argv is None else list(argv))

    if args.print_link is not None:
        if not args.title:
            print("Error: --print-link requires --title \"<feature title>\".")
            return 2
        master_plan_content: Optional[str] = None
        root = args.project_root or _find_sdd_root(Path(os.getcwd()))
        if root is not None:
            config = project_registry.read_projects_config(root)
            parsed = project_link.parse_qualified_id(args.print_link)
            if config is not None and parsed is not None:
                project, _fn = parsed
                sibling_root = project_registry.find_sibling(config, project, root)
                if sibling_root is not None:
                    try:
                        master_plan_content = project_registry.safe_read_sibling(
                            blueprint_common.resolve_artifact(
                                sibling_root / "blueprint", "PLAN.md"
                            ),
                            sibling_root,
                        )
                    except blueprint_common.ArtifactAmbiguityError:
                        master_plan_content = None
        return _print_link_mode(args.print_link, args.title, master_plan_content)

    if args.title is not None:
        print("Error: --title is only valid with --print-link.")
        return 2

    root = args.project_root or _find_sdd_root(Path(os.getcwd()))
    result = ValidationResult()
    if root is None:
        _skip(
            result,
            "no `.sdd/projects.json` registry found in this directory or any "
            "parent",
        )
        _emit(result)
        return 0

    _run_reconcile(root, result)
    _emit(result)
    return 0 if result.passed else 1


if __name__ == "__main__":
    # Defensive backstop: the per-dir reads degrade on ambiguity, but this turns
    # any OTHER unguarded ArtifactAmbiguityError into a clean fail-closed exit
    # instead of a traceback (the boundary lives in one shared place).
    blueprint_common.run_cli_failclosed(lambda: main(sys.argv[1:]))
