# Phase 2: Architecture

Drafts `blueprint/ARCHITECTURE.md` — how the system fits together. Requires an approved `blueprint/SCOPE.md` as upstream context.

## Drafting

Delegate drafting to the `telescoping-sdd:project-architecture-analyst` subagent via the Agent tool (`subagent_type: telescoping-sdd:project-architecture-analyst`).

When invoking the agent, provide:
- The template path: `references/architecture-template.md`
- The required sections (below) — the agent must produce exactly these
- The approved `blueprint/SCOPE.md` as authoritative upstream context
- A clear instruction to self-review the draft before returning (up to 5 passes, but stop immediately after the first pass that finds no issues — do not keep reviewing once clean), and to return a complete, clean draft of `ARCHITECTURE.md` that addresses every goal and respects every constraint from the scope
- A clear instruction to reproduce the template's exact formatting for structural sections — in particular: Open Questions must use `- [ ] Q1:` checkbox format, and the Approval section must be exactly `- [ ] Approved to proceed to next phase` followed by `- **Content Hash:** \`pending\`` (not a table or other format). The agent must read the template file and match its syntax precisely.

Required sections:
- **System Overview** — High-level description of the system and its purpose
- **Components** — Major system components with responsibilities and boundaries
- **Component Interactions** — How components communicate with each other
- **Technology Choices** — Tech stack selections with rationale and alternatives considered
- **Data Architecture** — How data flows through the system and where it's stored
- **External Dependencies** — Third-party services, APIs, and infrastructure
- **Risks** — Technical risks with likelihood, impact, and mitigation strategies

After the agent returns the draft, write it to `blueprint/ARCHITECTURE.md` and perform the self-review yourself before presenting it to the user.

## Architecture Self-Review

Review the ARCHITECTURE.md you just wrote, checking for:

1. **Inconsistencies** — Do components have overlapping responsibilities? Do technology choices conflict with each other? Are component interactions consistent with the component definitions?
2. **Inaccuracies** — Do technology choices match the constraints from the scope? Are external dependency assumptions correct? Does the data architecture support the stated goals?
3. **Gaps** — Is every goal from the scope addressable by at least one component? Are all data flows accounted for? Are risks identified for key architectural decisions?

For each issue found:
- **Fix it directly** if the correct resolution is clear (e.g., a missing component interaction, a technology choice that violates a constraint)
- **Stop and ask the user** if the resolution requires a judgment call (e.g., choosing between competing technology stacks, unclear scalability requirements)

If any issues were fixed, repeat the self-review on the updated architecture — fixes can introduce new issues. If a pass finds no issues, stop immediately. Do not exceed 5 review passes total.

## Scope-Architecture Consistency Check

After the architecture self-review is complete, cross-reference ARCHITECTURE.md against the approved SCOPE.md:

1. **Goal coverage** — Every goal in SCOPE.md must be addressable by at least one component or capability in the architecture.
2. **Constraint compliance** — The architecture must not violate any constraints from the scope (technical, timeline, team, budget, regulatory).
3. **User needs alignment** — The system overview and components must serve the target users defined in the scope.
4. **Non-goal respect** — The architecture should not introduce capabilities that fall under the scope's non-goals.
5. **Risk alignment** — Architectural risks should be consistent with the scope's constraints and not introduce unscoped concerns.

For each issue found:
- **Fix it directly** in ARCHITECTURE.md if the scope is clearly authoritative (e.g., a missing component for a stated goal, a technology choice that violates a constraint)
- **Stop and ask the user** if the conflict is ambiguous (e.g., the scope is underspecified and the architecture made a reasonable but uncertain assumption)

## Architecture Panel Review

After the scope-architecture consistency check is complete, run the architecture panel against `blueprint/ARCHITECTURE.md` following the loop described in `references/panel-review.md`.

Panelists: `telescoping-sdd:architect`, `telescoping-sdd:ops-reviewer`, `telescoping-sdd:security-reviewer`.

Pass the current ARCHITECTURE.md and the approved SCOPE.md. Deferred concerns from this panel can target `PLAN.md`.

## Validation and approval

After the panel review is complete, run validation:

```bash
python <script-path>/validate_blueprint.py blueprint/
```

**Stop and ask the user to review ARCHITECTURE.md before proceeding.**

If the user requests a change at this gate (before approving), do not apply it silently — route it through `references/panel-review.md § "Handling change requests at the review gate"` (substantive change re-enters the panel loop; trivial wording is a synthesizer fix + Self-Check, panel-skip-eligible), then re-present. No hash exists yet, so there is no re-stamp or cascade.

When the user approves, run:

```bash
python <script-path>/validate_blueprint.py blueprint/ --approve architecture
```
