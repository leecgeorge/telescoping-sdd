# Phase 1: Scope

Drafts `blueprint/SCOPE.md` — what we're building and why. This is the first blueprint artifact; the architecture and plan phases depend on its approval.

## Drafting

Delegate drafting to the `telescoping-sdd:project-spec-analyst` subagent via the Agent tool (`subagent_type: telescoping-sdd:project-spec-analyst`).

When invoking the agent, provide:
- The template path: `references/scope-template.md`
- The required sections (below) — the agent must produce exactly these
- Everything the user has told you about the project so far
- Any prior artifacts in `blueprint/` if the user is resuming mid-stream
- A clear instruction to self-review the draft before returning (up to 5 passes, but stop immediately after the first pass that finds no issues — do not keep reviewing once clean), and to use the `Write` tool to write the complete `SCOPE.md` to `blueprint/SCOPE.md` and return only the canonical manifest: (1) the path written, (2) the line count, (3) the list of `##` section headings, (4) the open-questions / revision-points list — not the document body
- A clear instruction to reproduce the template's exact formatting for structural sections — in particular: Success Criteria must use `- [ ]` checkboxes (not numbered lists), Open Questions must use `- [ ] Q1:` checkbox format, and the Approval section must be exactly `- [ ] Approved to proceed to next phase` followed by `- **Content Hash:** \`pending\`` (not a table or other format). The agent must read the template file and match its syntax precisely.

Required sections:
- **Problem Statement** — What problem exists and why it needs solving
- **Target Users** — Who will use this and what are their needs
- **Goals** — What success looks like for this project
- **Non-Goals** — What is explicitly out of scope
- **Constraints** — Technical, timeline, team, budget, or regulatory constraints
- **Success Criteria** — Measurable conditions that define "done"

The agent-written `SCOPE.md` is already on disk. `Read` `blueprint/SCOPE.md` (page with `offset`/`limit` as needed for large files), confirm the file is non-empty and its line count matches the manifest's reported line count before beginning self-review. If the file is missing or empty, treat it as a drafting failure and re-invoke the agent. On any re-invocation, re-`Read` `blueprint/SCOPE.md` before re-reviewing — do not reuse a stale in-context copy. Present the artifact to the user before approval.

## Network Exposure Triage

Before proceeding to self-review, apply the following screening question to the **deliverables** (not stated goals) of this scope:

> Could any scope item plausibly expose a public surface — a new domain, DNS record, route, port, or publicly-resolving endpoint — before the scope item that installs, hardens, or blocks it? If yes: what is served there, and in what hardened state, during the window before the hardening item lands? An un-installed or un-hardened intermediate state served publicly is a FINDING, not a PASS.

**The answer is YES when any scope item's deliverables include any of the following:**

- Creates or registers a new domain or DNS record
- Adds a new public-facing route, vhost, or listener
- Opens or forwards a new network port accessible from an untrusted network
- Routes a publicly-resolving hostname to a backend service
- Exposes any endpoint that becomes reachable before a LATER scope item installs, hardens, or blocks it

**Branch (a) — no new surface:** Record the declaration as: "No scope item creates a new public domain, route, port, or endpoint — the surfaces touched already existed and are unchanged — checked: [enumerate the specific domains/routes/ports/endpoints screened]." A bare "no exposure" is NOT acceptable — enumerate the specific surfaces checked. Branch (a) is UNAVAILABLE to any scope whose deliverables include a new public domain, route, port, or cert.

**Branch (b) — exposure found:** When the deliverables match any trigger above, branch (b) is MANDATORY. The executor must state:

1. The specific public surface (e.g., `new.example.com:443`)
2. The specific later scope item or feature that installs or hardens it
3. A present-tense observable **success criterion** stating the gate condition — the observable WHAT that blocks the exposure until the hardening item lands

A gate phrased as future intention with no present-tense blocking condition is itself a FINDING. An un-installed or un-hardened intermediate state served publicly is a FINDING, not a PASS.

**A FINDING obligates the executor to:**

1. Document the interim exposure explicitly in the scope
2. Name a blocking gate as an observable success criterion
3. Treat the scope as NOT approvable until that criterion is present

This is a real gate, not advisory. The `devils-advocate` panelist independently audits this declaration during the Scope panel review.

## Exposure Doctrine

A feature that newly exposes a surface to an untrusted network must either (i) ship its own hardening in the same feature, or (ii) declare and gate the interim exposure (e.g. do not route the live domain to the backend until the install/harden step is verified). The gate must be an observable acceptance criterion, not an assumption.

**Worked example:** A live domain fronting an un-installed install wizard, before the feature that runs the install lands, is a FINDING. The correct gate: "do not route the live domain to the backend until the install/harden step is verified." This is the F3→F4→F5 shape: F3 goes public, F4 installs, F5 hardens. The doctrine obligation applies at F3 — gate or ship hardening in F3 (generally: any feature that exposes a surface before the feature that hardens it — the `F<n>` labels are illustrative).

**Exposure-FINDING under this doctrine:** Any acceptance criterion that blesses an un-hardened or un-installed service endpoint as an expected PASS state without a named blocking gate is a FINDING under this doctrine. The artifact is not approvable until either (i) or (ii) is present.

## Scope Self-Review

Review the SCOPE.md you just wrote, checking for:

1. **Inconsistencies** — Do goals contradict non-goals? Do constraints conflict with success criteria? Are terms used consistently throughout?
2. **Inaccuracies** — Are assumptions about the target users, technical environment, or constraints correct based on what the user has told you?
3. **Gaps** — Is every goal measurable via at least one success criterion? Are there obvious user needs not addressed? Are constraints complete (technical, timeline, team, budget, regulatory)?

For each issue found:
- **Fix it directly** if the correct resolution is clear (e.g., a missing success criterion for a stated goal, a constraint that contradicts itself)
- **Stop and ask the user** if the resolution requires a judgment call (e.g., conflicting goals where you don't know which takes priority, unclear target user needs)

If any issues were fixed, repeat the self-review on the updated scope — fixes can introduce new issues. If a pass finds no issues, stop immediately. Do not exceed 5 review passes total.

## Scope Panel Review

After the scope self-review is complete, run the scope panel against `blueprint/SCOPE.md` following the loop described in `references/panel-review.md`.

Panelists: `telescoping-sdd:user-advocate`, `telescoping-sdd:devils-advocate`, `telescoping-sdd:pragmatist`.

There are no upstream approved artifacts at this phase — pass the current SCOPE.md only. Deferred concerns from this panel can target `ARCHITECTURE.md` or `PLAN.md`.

## Validation and approval

After the panel review is complete, run validation:

```bash
python <script-path>/validate_blueprint.py blueprint/
```

**Stop and ask the user to review SCOPE.md before proceeding.**

If the user requests a change at this gate (before approving), do not apply it silently — route it through `references/panel-review.md § "Handling change requests at the review gate"` (substantive change re-enters the panel loop; trivial wording is a synthesizer fix + Self-Check, panel-skip-eligible), then re-present. No hash exists yet, so there is no re-stamp or cascade.

When the user approves, run:

```bash
python <script-path>/validate_blueprint.py blueprint/ --approve scope
```

This marks the scope as approved with a content hash. If the scope is edited after approval, the hash will no longer match — the skill detects this on next entry (or immediately, if Claude made the edit) and triggers the auto-cascade flow described in `hash-and-cascade.md` § "Re-Approval After Edits": structural validity is checked, the hash is re-stamped silently, and the consistency check ripples downstream. Cosmetic edits proceed without interruption; substantive edits halt at the consistency-check boundary so the user can decide whether to revise the downstream artifacts.
