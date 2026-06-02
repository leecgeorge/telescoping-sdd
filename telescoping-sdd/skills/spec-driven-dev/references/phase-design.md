# Phase 2: Design

Drafts `specs/F<n>-<slug>/design.md` — how to build the feature. Requires an approved `spec.md` as upstream context.

## Drafting

Delegate drafting to the `telescoping-sdd:feature-architecture-analyst` subagent via the Agent tool (`subagent_type: telescoping-sdd:feature-architecture-analyst`).

When invoking the agent, provide:
- The resolved stack profile and the matching template path:
  - Python: `references/design-template-python.md`
  - Java: `references/design-template-java.md`
  - Generic (architecture-neutral — infra, static sites, config, docs, skill authoring): there is no `-generic` template; use `references/design-template-python.md` for the structural skeleton (the section list is identical across profiles), but instruct the agent to *reinterpret* the stack-shaped sections for the actual deliverable rather than inventing code — e.g. Data Models → config-file schemas / resource topology, Interfaces → shell-script or cross-component contracts, Testing Strategy → the command/manual/review checks the stack supports. All required section headings stay present (the validator checks presence); only their content adapts.
- The required sections (below) — the agent must produce exactly these
- The approved `specs/F<n>-<slug>/spec.md` as authoritative upstream context
- A clear instruction that the design must address every requirement and respect every boundary from the spec
- If `blueprint/PLAN.md` exists and contains a `## Cross-Feature Contracts` section, pass its contents (or at minimum the CFC entries naming this feature in their Participating features). The agent's CFC obligation (below) requires this input.
- A clear instruction to self-review the draft before returning (up to 5 passes, but stop immediately after the first pass that finds no issues — do not keep reviewing once clean), and to return a complete, clean draft of `design.md` that fits into the existing codebase (the agent will read the repo to ground file paths and integration points)
- A clear instruction to reproduce the template's exact formatting for structural sections — in particular: Open Questions must use `- [ ] Q1:` checkbox format, and the Approval section must be exactly `- [ ] Approved to proceed to next phase` followed by `- **Content Hash:** \`pending\`` (not a table or other format). The agent must read the template file and match its syntax precisely.

**CFC obligation.** For every `### CFC-N` in `blueprint/PLAN.md`'s Cross-Feature Contracts section that names this feature in its Participating features, the design must demonstrably honor the contract — code paths described in Architecture Decisions / Component Design / Interfaces / Error Handling must not contradict the CFC's `Contract` clause or its `Per-feature AC`. If this feature is named (as the bare token `F<n>` verbatim, word-boundary) in the CFC's `Enforcement` prose, the design must additionally specify how the verifying artifact named in Enforcement (ArchUnit rule, CI workflow, integration test, etc.) will be implemented and where it lives in the codebase (concrete file paths in File Structure, sequencing in Implementation Sequence). If the design cannot honor a binding CFC for this feature, the agent surfaces a candidate `Halt and re-scope` for the design panel rather than silently dropping the obligation.

Required sections:
- **Goals and Non-Goals** — What is in scope and what is explicitly excluded
- **Architecture Decisions** — Key choices with rationale, alternatives rejected, and consequences
- **Component Design** — Modules/classes with responsibilities
- **Data Models** — Fields, types, constraints, and relationships between models
- **Interfaces** — Function signatures with type annotations and contracts
- **Error Handling** — Exception strategy, custom exceptions, logging approach
- **Testing Strategy** — Framework, mocking approach, coverage expectations, fixtures
- **File Structure** — Concrete file paths for all new and modified files
- **Dependencies** — External packages needed
- **Integration Points** — How new code connects to existing code, with direction and change required
- **Risks** — What could go wrong and concrete mitigation actions
- **Implementation Sequence** — High-level build order for components

After the agent returns the draft, write it to `specs/F<n>-<slug>/design.md` and perform the self-review yourself before presenting it to the user.

## Design Self-Review

Review the design.md you just wrote, checking for:

1. **Inconsistencies** — Does the design contradict the approved spec? Do component designs align with the data models and interfaces? Are naming conventions consistent throughout?
2. **Inaccuracies** — Do file paths, class names, and package structures match the actual codebase? Are dependency versions and API signatures correct? Does the architecture fit the existing project structure?
3. **Gaps** — Is every spec requirement addressed by at least one component? Are error handling paths complete? Are integration points fully specified? Does the implementation sequence cover all components?

For each issue found:
- **Fix it directly** if the correct resolution is clear (e.g., a wrong file path, a missing error case, an interface that doesn't match the data model)
- **Stop and ask the user** if the resolution requires a judgment call (e.g., choosing between architectural approaches, unclear performance requirements, or scope questions)

If any issues were fixed, repeat the self-review on the updated design — fixes can introduce new issues. If a pass finds no issues, stop immediately. Do not exceed 5 review passes total.

## Spec-Design Consistency Check

After the design self-review is complete, cross-reference design.md against the approved spec.md:

1. **Requirement coverage** — Every requirement (R1, R2, etc.) in spec.md must be addressed by at least one component or interface in design.md. Flag any requirements with no corresponding design entry.
2. **Acceptance criteria alignment** — The design's testing strategy and component behavior must be capable of satisfying every GIVEN/WHEN/THEN criterion in the spec.
3. **Boundary compliance** — The design must not violate any "Never do" boundaries from the spec, and must incorporate all "Always do" items.
4. **Terminology and naming** — Names for modules, classes, and concepts should match between spec and design. Flag any divergences.
5. **Scope drift** — The design should not introduce capabilities or components that go beyond what the spec requires without justification.

For each issue found:
- **Fix it directly** in design.md if the spec is clearly authoritative (e.g., a missing requirement, a naming mismatch, a boundary violation)
- **Stop and ask the user** if the conflict is ambiguous (e.g., the spec is underspecified and the design made a reasonable but uncertain assumption, or a spec requirement may need revision based on what the design revealed)

## Design Panel Review

After the spec-design consistency check is complete, run the design panel against `specs/F<n>-<slug>/design.md` following the loop described in `references/panel-review.md`.

Panelists: `telescoping-sdd:architect`, `telescoping-sdd:testability-reviewer`, `telescoping-sdd:security-reviewer`.

Pass the current design.md and the approved spec.md. Deferred concerns from this panel can target `tasks.md`.

## Validation and approval

After the panel review is complete, run validation:

```bash
python <script-path>/validate_spec.py specs/F<n>-<slug>/
```

**Stop and ask the user to review design.md before proceeding.**

If the user requests a change at this gate (before approving), do not apply it silently — route it through `references/panel-review.md § "Handling change requests at the review gate"` (substantive change re-enters the panel loop; trivial wording is a synthesizer fix + Self-Check, panel-skip-eligible), then re-present. No hash exists yet, so there is no re-stamp or cascade.

When the user approves, run:

```bash
python <script-path>/validate_spec.py specs/F<n>-<slug>/ --approve design
```
