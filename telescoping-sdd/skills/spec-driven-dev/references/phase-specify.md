# Phase 1: Specify

Drafts `specs/F<n>-<slug>/01_spec.md` — what to build and why. This is the first artifact; design and tasks depend on its approval.

> **Artifact filenames.** This skill emits artifacts with an `NN_` ordinal prefix (`01_spec.md`, `02_design.md`, `03_tasks.md`; blueprint tier: `01_SCOPE.md`, `02_ARCHITECTURE.md`, `03_PLAN.md`) so a directory listing sorts in phase order. The prefixed form is the emit default; **both** the bare and the prefixed form are accepted on read (the validators and scripts resolve either). Wherever a path below names an artifact file — including an upstream existence check such as `blueprint/PLAN.md` — read it as "bare **or** `NN_`-prefixed" (`blueprint/PLAN.md` or `blueprint/03_PLAN.md`).

## Drafting

Delegate drafting to the `telescoping-sdd:feature-spec-analyst` subagent via the Agent tool (`subagent_type: telescoping-sdd:feature-spec-analyst`).

When invoking the agent, provide:
- The resolved stack profile and the matching template path:
  - Python: `references/spec-template-python.md`
  - Java: `references/spec-template-java.md`
  - Generic (architecture-neutral — infra, static sites, config, docs, skill authoring): there is no `-generic` template; use `references/spec-template-python.md` for the structural skeleton (identical across profiles), but instruct the agent to ignore its Python-specific examples — the Project Structure and Commands content must reflect the actual stack (e.g. `docker-compose.yml`/`nginx.conf` paths, `nginx -t`/`terraform validate` commands), not `src/*.py`/`pytest`. The structural sections, GIVEN/WHEN/THEN, and the hash/approval blocks are unchanged.
- The required sections (below) — the agent must produce exactly these
- Everything the user has told you about the feature so far
- Any prior artifacts in `specs/F<n>-<slug>/` if the user is resuming mid-stream
- The PLAN feature identifier for this feature (`F<n>`), if this feature originated from a `blueprint/PLAN.md`'s Feature Breakdown. If the feature is standalone (no upstream PLAN), pass `n/a`. The agent writes this verbatim into the `**PLAN feature identifier:**` line at the top of the spec.
- If `blueprint/PLAN.md` exists at the project root, also pass the contents of its `## Cross-Feature Contracts` section (if any). The agent's CFC binding obligation (below) requires this input.
- A clear instruction to self-review the draft before returning (up to 5 passes, but stop immediately after the first pass that finds no issues — do not keep reviewing once clean), and to use the `Write` tool to write the complete `spec.md` to `specs/F<n>-<slug>/01_spec.md` and return only the canonical manifest: (1) the path written, (2) the line count, (3) the list of `##` section headings, (4) the open-questions / revision-points list — not the document body
- A clear instruction to reproduce the template's exact formatting for structural sections — in particular: Success Criteria must use `- [ ]` checkboxes (not numbered lists), Open Questions must use `- [ ] Q1:` checkbox format, and the Approval section must be exactly `- [ ] Approved to proceed to next phase` followed by `- **Content Hash:** \`pending\`` (not a table or other format). The agent must read the template file and match its syntax precisely.

## Is this feature derived from another repo's PLAN?

Before drafting, answer one intake question: **does this feature implement a master feature defined in a *different* repo's `blueprint/PLAN.md`?** (Cross-Project Derivation — e.g. a `vps-edge` feature that implements `residents` `F7`, where the `residents` `### F7` row carries `**Implemented by:** vps-edge`.) If **no**, ignore this section and use the bound/standalone identifier as usual. If **yes**, drive the *derived flow* instead:

- **Directory form.** Create the spec under `specs/<project>--F<n>-<slug>/`, where `<project>` is the master-project alias and `F<n>` is the master's own feature number (the `--` sentinel separates the two). Example: `specs/residents--F7-resident-sync/`. Generate the slug as usual; the master-project alias and feature number come from the master PLAN.
- **The identifier line is `n/a`.** Pass `n/a` as the PLAN feature identifier so the agent writes `**PLAN feature identifier:** `n/a``. The cue to record alongside it: **`n/a` here means "standalone within THIS repo" — the feature is not native to this repo's PLAN; its provenance lives on the `Derived from` line, not on the identifier line.** (Do not pass the master's `F<n>` as the identifier — `check_dir_identifier` FAILs `derived-provenance-mismatch` if a derived spec's identifier is anything but `n/a`.)
- **Two provenance fields.** Instruct the agent to add, near the `**PLAN feature identifier:**` line:
  - `**Derived from:** `<project>:F<n>`` — the backtick-wrapped master qualified id (e.g. `` `residents:F7` ``). This is the authoritative join key and must match the directory's `<project>--F<n>` prefix.
  - `**Master contract hash:** `<hash>`` — the master feature's contract hash at bind time. **Bootstrap:** if the master repo is not yet reachable (different org, not yet cloned), write the literal `` `unbound` `` — it passes structural validation, and the first real 64-hex hash is stamped later from `python <shared-script-path>/reconcile.py --print-link <project>:F<n>`. The two fields must appear together (one without the other FAILs `derived-fields-incomplete`).
- **Local CFC.** A derived spec is exempt from this repo's `## Cross-Feature Contracts` coherence (the CFC binding obligation below targets *local* PLAN contracts, which a derived feature does not participate in). If the master feature is wrong, do not silently diverge — record an Upstream Change Request and proceed; see `references/workflow-overview.md § Cross-Project Derivation`.

**CFC binding obligation.** If `blueprint/PLAN.md` exists and contains a `## Cross-Feature Contracts` section, the agent must read it. For every `### CFC-N` whose `**Participating features:**` list includes this feature's identifier (`F<n>`), the spec's acceptance criteria must contain the corresponding `**Per-feature AC:**` line tagged `[CFC-N]` on a THEN line. Specifically, append the bracketed tag to the THEN clause that materially implements the contract: `THEN <assertion> [CFC-N]`. Verbatim copying is preferred; non-substantive editing for tense/voice agreement is permitted, but substantive rewording is not — the panel will surface it as a mismatch.

If the agent believes a CFC's `Per-feature AC` is wrong for this feature (the Participating-features list is mistaken, the AC text is unworkable as written, the Enforcement is infeasible), the agent must NOT edit the AC text locally. Instead, surface the concern as a candidate `Halt and re-scope` for the spec panel — the CFC lives in PLAN and must be revised at PLAN level via project-blueprint's amendment workflow, not silently dropped from the feature.

Required sections:
- **Objective** — One paragraph on what and why
- **Requirements** — User stories in format: "As a [role], I want [action], so that [benefit]"
- **Acceptance Criteria** — GIVEN/WHEN/THEN for each requirement
- **Project Structure** — Where new code fits in the existing codebase
- **Boundaries** — "Always do", "Ask first", "Never do" lists
- **Success Criteria** — Measurable conditions for done

The agent-written `spec.md` is already on disk. `Read` `specs/F<n>-<slug>/01_spec.md` (page with `offset`/`limit` as needed for large files), confirm the file is non-empty and its line count matches the manifest's reported line count before beginning self-review. If the file is missing or empty, treat it as a drafting failure and re-invoke the agent. On any re-invocation, re-`Read` `specs/F<n>-<slug>/01_spec.md` before re-reviewing — do not reuse a stale in-context copy. Present the artifact to the user before approval.

## Network Exposure Triage

Before proceeding to self-review, apply the following screening question to the **deliverables** (not the author's intent) of this feature:

> "Does this feature/scope create, route, or expose any new domain, DNS record, route, port, or publicly-resolving endpoint (i.e. anything that becomes reachable from the public internet)? If yes: what is served there, and in what hardened state, during the window before downstream features land? An un-installed or un-hardened intermediate state served publicly is a FINDING, not a PASS."

**The answer is YES when the feature's deliverables include any of the following:**

- Creates or registers a new domain or DNS record
- Adds a new public-facing route, vhost, or listener
- Opens or forwards a new network port accessible from an untrusted network
- Routes a publicly-resolving hostname to a backend service
- Exposes any endpoint that becomes reachable before a LATER feature or task installs, hardens, or blocks it

**Branch (a) — no new surface:** Record the declaration as: "Introduces no new domain/route/port; the surfaces it touches already existed and are unchanged — checked: [enumerate the specific domains/routes/ports/endpoints that were screened]." A bare "No new network surface exposed" is NOT acceptable — the declaration must enumerate the specific surfaces checked, so the independent audit has a concrete set to contradict. Branch (a) is UNAVAILABLE to any feature whose deliverables include a new public domain, route, port, or cert.

**Branch (b) — exposure found:** When the deliverables match any trigger above, branch (b) is MANDATORY. The executor must state:

1. The specific public surface (e.g., `new.example.com:443`)
2. The specific later feature or task that installs or hardens it (e.g., "F4 installs the application")
3. A present-tense observable **acceptance criterion** stating the gate condition (e.g., "do not activate the route to the backend until F4's install step is verified as complete") — the gate's mechanism (firewall rule, route toggle) is designed at Design/Tasks, but the observable WHAT must be an AC here

A gate phrased as future intention ("will be hardened once F4 lands") with no present-tense blocking mechanism stated as an observable AC is itself a FINDING.

**A FINDING obligates the executor to:**

1. Document the interim exposure explicitly
2. Name a blocking gate as an observable acceptance criterion
3. Treat the artifact as NOT approvable until that AC is present

The `devils-advocate` panelist independently re-runs this trigger list against the artifact's deliverables during the panel review — this is an independent audit, not a repetition of the drafter's answer.

## Exposure Doctrine

A feature that newly exposes a surface to an untrusted network must either (i) ship its own hardening in the same feature, or (ii) declare and gate the interim exposure (e.g. do not route the live domain to the backend until the install/harden step is verified). The gate must be an observable acceptance criterion, not an assumption.

**Worked example:** A live domain fronting an un-installed install wizard, before the feature that runs the install lands, is a FINDING. The correct gate: "do not route the live domain to the backend until the install/harden step is verified." This is the F3→F4→F5 shape: F3 goes public, F4 installs, F5 hardens. The doctrine obligation applies at F3 — gate or ship hardening in F3 (generally: any feature that exposes a surface before the feature that hardens it — the `F<n>` labels are illustrative).

**Exposure-FINDING under this doctrine:** Any acceptance criterion that blesses an un-hardened or un-installed service endpoint as an expected PASS state without a named blocking gate is a FINDING under this doctrine. The artifact is not approvable until either (i) or (ii) is present.

## Spec Self-Review

Review the spec.md you just wrote, checking for:

1. **Inconsistencies** — Do requirements contradict each other? Do acceptance criteria match their corresponding requirements? Are terms used consistently throughout?
2. **Inaccuracies** — Do file paths, module names, or API references match the actual codebase? Are assumptions about existing code correct?
3. **Gaps** — Is every requirement covered by at least one acceptance criterion? Are there edge cases or error scenarios not addressed? Are boundaries (Always/Ask/Never) complete?

For each issue found:
- **Fix it directly** if the correct resolution is clear (e.g., a typo, a wrong file path, a missing edge case you can infer)
- **Stop and ask the user** if the resolution requires a judgment call (e.g., conflicting requirements where you don't know which takes priority, ambiguous scope, or missing domain knowledge)

If any issues were fixed, repeat the self-review on the updated spec — fixes can introduce new issues. If a pass finds no issues, stop immediately. Do not exceed 5 review passes total.

## Spec Panel Review

After the spec self-review is complete, run the spec panel against `specs/F<n>-<slug>/01_spec.md` following the loop described in `references/panel-review.md`.

Panelists: `telescoping-sdd:user-advocate`, `telescoping-sdd:devils-advocate`, `telescoping-sdd:pragmatist`.

There are no upstream approved artifacts at this phase — pass the current spec.md only. Deferred concerns from this panel can target `design.md` or `tasks.md`.

## Validation and approval

After the panel review is complete, run validation:

```bash
python <script-path>/validate_spec.py specs/F<n>-<slug>/
```

Where `<script-path>` is the skill's own `scripts/` directory at the plugin install root, resolved as defined in `SKILL.md` (marketplace cache or `--plugin-dir`). It is NOT project-relative — there is no `scripts/` directory under the project itself.

**Stop and ask the user to review spec.md before proceeding.**

If the user requests a change at this gate (before approving), do not apply it silently — route it through `references/panel-review.md § "Handling change requests at the review gate"` (substantive change re-enters the panel loop; trivial wording is a synthesizer fix + Self-Check, panel-skip-eligible), then re-present. No hash exists yet, so there is no re-stamp or cascade.

When the user approves, run:

```bash
python <script-path>/validate_spec.py specs/F<n>-<slug>/ --approve spec
```

This marks the spec as approved with a content hash. If the spec is edited after approval, the hash will no longer match — the skill detects this on next entry (or immediately, if Claude made the edit) and triggers the auto-cascade flow described in `hash-and-cascade.md` § "Re-Approval After Edits": structural validity is checked, the hash is re-stamped silently, and the consistency check ripples downstream. Cosmetic edits proceed without interruption; substantive edits halt at the consistency-check boundary so the user can decide whether to revise the downstream artifacts.
