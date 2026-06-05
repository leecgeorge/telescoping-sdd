# Phase 3: Implementation Plan

Drafts `blueprint/PLAN.md` — features, dependencies, MVP, milestones. Requires approved `blueprint/SCOPE.md` and `blueprint/ARCHITECTURE.md` as upstream context. This is the last blueprint phase — concerns cannot be deferred forward.

## Drafting

Delegate drafting to the `telescoping-sdd:project-plan-analyst` subagent via the Agent tool (`subagent_type: telescoping-sdd:project-plan-analyst`).

When invoking the agent, provide:
- The template path: `references/plan-template.md`
- The required sections (below) — the agent must produce exactly these
- The approved `blueprint/SCOPE.md` and `blueprint/ARCHITECTURE.md` as authoritative upstream context
- A clear instruction that each feature (F1, F2, etc.) must be described at enough detail to serve as input to a spec-driven development workflow
- A clear instruction to self-review the draft before returning (up to 5 passes, but stop immediately after the first pass that finds no issues — do not keep reviewing once clean), and to use the `Write` tool to write the complete `PLAN.md` to `blueprint/PLAN.md` and return only the canonical manifest: (1) the path written, (2) the line count, (3) the list of `##` section headings, (4) the open-questions / revision-points list — not the document body
- A clear instruction to reproduce the template's exact formatting for structural sections — in particular: feature checklists must use `- [ ] F1:` checkbox format, Open Questions must use `- [ ] Q1:` checkbox format, and the Approval section must be exactly `- [ ] Approved to proceed to feature development` followed by `- **Content Hash:** \`pending\`` (not a table or other format). The agent must read the template file and match its syntax precisely.

Required sections:
- **Feature Breakdown** — All features with descriptions and acceptance criteria, identified as F1, F2, etc.
- **MVP Definition** — Which features are in MVP vs. later phases
- **Feature Dependencies** — Dependency graph showing which features depend on which
- **Implementation Order** — Sequenced build order with rationale
- **Milestones** — Features grouped into delivery milestones

Each feature (F1, F2, etc.) should be described at enough detail to serve as input to a spec-driven development workflow for individual feature implementation.

### Optional: delegating a feature to another repo (`**Implemented by:**`)

Most features are implemented in this same repo. When a feature is instead **delegated to a different repo** — a master→derived link under Cross-Project Derivation — add an optional `**Implemented by:** <project>` field to that feature's `### F<n>` block:

```
### F7: Resident sync contract
- **Description:** …
- **Component:** …
- **Acceptance Criteria:**
  - …
- **Implemented by:** vps-edge
```

- **Grammar.** The value is a single **lowercase-kebab project alias** (`[a-z0-9]+(-[a-z0-9]+)*` — same shape as a slug), optionally backtick-wrapped. It names only the *derived project*, never a derived feature number: the derived feature reuses this master's own `F<n>`, so naming a separate number would falsely imply the feature is native to the derived repo. `validate_blueprint.py` parses the field positionally per feature block and FAILs `implemented-by-malformed` for a non-kebab value or `implemented-by-duplicate` for two occurrences in one block. **Absence is the normal case** ("implemented locally") and is silent — never add an empty or placeholder `Implemented by`.
- **Alias-stability rule (load-bearing).** A project alias is part of the join key. **Once a derivation link exists** (a derived repo carries a `specs/<project>--F<n>-<slug>/` directory pointing back here), the master-project alias and the value of every `**Implemented by:**` field **must not be renamed** — renaming silently orphans the link, and `reconcile` cannot distinguish a rename from a genuine deletion. If a rename is truly unavoidable, treat it as a coordinated cross-repo migration (update both sides in lockstep), not a one-side PLAN edit. The full reconcile/UCR workflow this feeds into lives in `references/workflow-overview.md § Cross-Project Derivation`.

The agent-written `PLAN.md` is already on disk. `Read` `blueprint/PLAN.md` (page with `offset`/`limit` as needed for large files), confirm the file is non-empty and its line count matches the manifest's reported line count before beginning self-review. If the file is missing or empty, treat it as a drafting failure and re-invoke the agent. On any re-invocation, re-`Read` `blueprint/PLAN.md` before re-reviewing — do not reuse a stale in-context copy. Present the artifact to the user before approval.

## Plan Self-Review

Review the PLAN.md you just wrote, checking for:

1. **Inconsistencies** — Do feature dependencies form a valid DAG (no circular dependencies)? Does the implementation order respect the dependency graph? Do milestones contain all their listed features?
2. **Inaccuracies** — Do feature descriptions match the components defined in the architecture? Are acceptance criteria testable and specific? Does the MVP definition align with the stated goals?
3. **Gaps** — Does every architectural component have at least one feature that builds or uses it? Are there missing features needed to deliver the MVP? Does every feature have acceptance criteria?

For each issue found:
- **Fix it directly** if the correct resolution is clear (e.g., a missing dependency, a feature that references a non-existent component, an incomplete acceptance criterion)
- **Stop and ask the user** if the resolution requires a judgment call (e.g., which features belong in MVP, how to split a large feature)

If any issues were fixed, repeat the self-review on the updated plan — fixes can introduce new issues. If a pass finds no issues, stop immediately. Do not exceed 5 review passes total.

## Scope-Architecture-Plan Consistency Check

After the plan self-review is complete, cross-reference PLAN.md against both SCOPE.md and ARCHITECTURE.md:

1. **Goal coverage** — Every goal in SCOPE.md must be achievable by the features in the plan. Flag any goals with no corresponding feature.
2. **Component coverage** — Every component in ARCHITECTURE.md must have at least one feature that builds or exercises it.
3. **Constraint compliance** — The implementation order and milestones must respect scope constraints (timeline, team size, etc.).
4. **MVP alignment** — The MVP feature set must be sufficient to meet the core goals and success criteria from the scope.
5. **Dependency consistency** — Feature dependencies should align with the component interactions defined in the architecture.

For each issue found:
- **Fix it directly** in PLAN.md if the scope and architecture are clearly authoritative (e.g., a missing feature for an uncovered goal, a dependency that contradicts the architecture)
- **Stop and ask the user** if the conflict is ambiguous (e.g., whether a goal is sufficiently covered by existing features, or how to prioritize features within constraints)

## Plan Panel Review

After the scope-architecture-plan consistency check is complete, run the plan panel against `blueprint/PLAN.md` following the loop described in `references/panel-review.md`.

Panelists: `telescoping-sdd:delivery-manager`, `telescoping-sdd:critic`, `telescoping-sdd:simplifier`.

Pass the current PLAN.md and the approved SCOPE.md and ARCHITECTURE.md. This is the last blueprint phase — concerns cannot be deferred forward. Concerns that would warrant deferral should instead be handled as `Addressed` in PLAN.md, `Sealed` (user-directed), or `Accepted as risk` (with explicit user sign-off and `Defense:` text in Notes).

**Exposure sequencing check.** When reviewing the Implementation Order, consult the Exposure Doctrine before approving the ordering; if any feature exposes a surface before the feature that installs/hardens/blocks it, the required response is ONE of: (i) raise it as an `[upstream]`-tagged concern (which routes to a halt vote via the existing Phase 2/3 concern-tagging machinery) when the missing hardening or gate lives in already-approved upstream content (e.g. an approved spec blesses the exposure), or (ii) resolve it in-phase by naming an interim mitigation or reordering the implementation — see `## Exposure Doctrine` in `phase-scope.md`. For a sequencing edge between two features both present in the CURRENT PLAN, the expected response is a reorder or interim-mitigation gate (not `[upstream]`, which routes to an earlier-phase artifact). Filing it as a soft MED that is dispositioned away without a gate or reorder is NOT an acceptable response in either case.

**Closed-feature-row constraint (Phase-3 panelist invocation).** Add the following constraint to each panelist's invocation prompt: *Before proposing a fix that involves editing content under an `### F<n>:` heading in PLAN.md, look up F<n>'s milestone checkbox in `## Milestones` (search for a line matching `^- \[[ xX]\] F<n>\b`; if F<n> appears in multiple milestone blocks, take the latest by milestone number). If the matched checkbox is `[x]`, do not propose direct edits to F<n>'s row — propose routing the obligation to an amending feature's per-feature AC inside a `## Cross-Feature Contracts` block, or to the relevant `M*N Deliverable` narrative instead. Closed-feature-row immutability is preserved by the deferred-amendment-avoidance pattern (canonical doctrine in `references/workflow-overview.md § Closed-Feature-Row Immutability`); treat `[x]`-bound feature rows as byte-frozen for all proposed-fix wording.* This panelist-prompt constraint complements the synthesizer-side Self-Check (e) in `references/panel-review.md` — defence in depth: the panelist proposes the right shape, and the synthesizer verifies before applying.

**Source-fidelity constraint (Phase-3 panelist invocation).** Also add the following constraint to each panelist's invocation prompt: *When proposing a fix that names participating features in a cross-feature contract, enumerates a consumer list, asserts a feature's code-shape commitment (e.g., "uses `publisher.publish()`", "writes to table X", "injects bean Y"), or seeds a registry with example entries, quote the authoritative source line verbatim in the finding. If the authoritative source is a feature's AC bullet, quote the bullet's relevant sentence. If the proposal extends or contradicts the cited text, mark the divergence explicitly (e.g., "F33 line 670 enumerates `(F33, F29, F32, F35, F25)`; my proposal adds F20 because…"). The synthesizer must be able to verify the proposal's premise from the quoted text alone, not from the citation's location.* This complements the synthesizer-side Self-Check (b)'s verbatim-quote requirement in `references/panel-review.md` — defence in depth: the panelist surfaces the cited text in the finding itself, and the synthesizer's self-check verifies the cited text supports the specific claim before applying. (Per the post-implementation field observation in `documentation/CFC.md § Domain-Ignorance in CFC Authoring`.)

## Validation and approval

After the panel review is complete, run validation:

```bash
python <script-path>/validate_blueprint.py blueprint/
```

**Stop and ask the user to review PLAN.md before proceeding.**

If the user requests a change at this gate (before approving), do not apply it silently — route it through `references/panel-review.md § "Handling change requests at the review gate"` (substantive change re-enters the panel loop; trivial wording is a synthesizer fix + Self-Check, panel-skip-eligible), then re-present. No hash exists yet, so there is no re-stamp or cascade. (PLAN.md is the terminal artifact — concerns surfaced by a re-run cannot be deferred forward; dispose them Addressed / Sealed / Accepted as risk. A re-run that edits a closed `[x]` feature row is still bound by Self-Check (e) — re-route, do not edit in place.)

When the user approves, run:

```bash
python <script-path>/validate_blueprint.py blueprint/ --approve plan
```
