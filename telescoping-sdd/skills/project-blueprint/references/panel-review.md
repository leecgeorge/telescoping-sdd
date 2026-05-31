<!--
SHARED REFERENCE — keep in sync with the spec-driven-dev copy at
skills/spec-driven-dev/references/panel-review.md. Edits to the shared panel-review machinery must be mirrored in BOTH copies.

Intentional asymmetries vs the sibling (do NOT "sync" these away):
- Phase names differ (Scope/Architecture/Plan vs Specify/Design/Tasks); spec-driven-dev also has a panel-less Phase 4 (Implement) that blueprint lacks.
- Terminal Phase-3 artifact is PLAN.md (blueprint) vs tasks.md (spec-driven-dev); the three --terminal archive-command sites differ ONLY in that filename.
- Synthesizer Self-Check is (a)-(f) in blueprint (adds (e) closed-feature-row integrity and (f) CFC authoring fidelity — the CFC PRODUCER role) vs (a)-(d) in spec-driven-dev; the [SELF-CHECK] (a|b|c|d|e|f) vs (a|b|c|d) Source tags follow.
- The "## CFC Compliance Check" section and "Per-feature AC alignment" rubric are spec-driven-dev-only (the CFC CONSUMER check against PLAN.md); blueprint has no counterpart.
- Architecture/Design middle panelist differs: telescoping-sdd:ops-reviewer (blueprint) vs telescoping-sdd:testability-reviewer (spec-driven-dev), including in example tables.
- Halt-and-rescope routes to the user revising project scope/phase boundary (blueprint) vs to the project-blueprint amendment workflow then a spec-loop restart (spec-driven-dev).
- Upstream-halt / sibling-artifact targets are SCOPE.md / ARCHITECTURE.md (blueprint) vs spec.md / design.md (spec-driven-dev).
- Blueprint-only: the two-paragraph "Cap-pressure caveat" inside `## The Loop` (cap-pressure / domain-ignorance discipline leaning on Self-Check (e)/(f) and CFC-producer authoring) has no spec-driven-dev counterpart.
Otherwise the copies differ only cosmetically (phase-vocabulary mapping, filenames, illustrative example values).
-->

# Panel Review

This reference defines the shared panel-review mechanism used by every phase of the project-blueprint workflow. The same loop runs in Phase 1 (Scope), Phase 2 (Architecture), and Phase 3 (Plan) — only the panelists change.

The agent's self-review catches internal issues. The cross-doc consistency check catches conversation-context issues. The panel catches blind-spot and quality issues. Run this loop after the self-review and any cross-doc check, before validation and the human review gate.

## Path placeholders

This reference uses two script-root placeholders defined in the main `SKILL.md` Overview:

* `<script-path>` — the skill's own `scripts/` directory.
* `<shared-script-path>` — the plugin-wide `telescoping-sdd/scripts/` directory containing `archive_pass.py`.

## Minimum to run the NORMAL loop

First-pass digest — the rest of this file loads when a trigger fires. To run one normal panel pass:

1. Pick the three panelists for this phase (`## Panelists per phase` below) and dispatch all three in one message, by their `telescoping-sdd:` prefix.
2. Ask each for a ranked list of concerns, each tagged `[HIGH]` / `[MED]` / `[LOW]` with a one-line description and rationale.
3. Synthesize in-thread; dispose each concern as `Addressed` / `Deferred → <target>` / `Sealed` / `Accepted as risk` / `User input needed`. (Phase 2/3: prefix each HIGH Concern with `[contract]` / `[detail]` / `[upstream]` — see `## Concern tagging`.)
4. Run the **Synthesizer Self-Check** (§ below), then `python <shared-script-path>/archive_pass.py <artifact> --phase <N>` (add `--terminal` for `PLAN.md`).
5. Exit when a pass returns no new HIGH concerns; otherwise loop (cap 5 passes).

Load on demand: **strict-bar** mode (only when `archive_pass.py` emits `STRICT-BAR-SIGNAL:`), **halt-and-rescope** (only on `[upstream]` tags / two consecutive halt votes), the **exit cross-check** (only when leaving strict-bar), **lightweight mode** and **panel skip** (only when the user opts in / the change is mechanical).

## Panelists per phase

- **Scope:** `telescoping-sdd:user-advocate`, `telescoping-sdd:devils-advocate`, `telescoping-sdd:pragmatist`
- **Architecture:** `telescoping-sdd:architect`, `telescoping-sdd:ops-reviewer`, `telescoping-sdd:security-reviewer`
- **Plan:** `telescoping-sdd:delivery-manager`, `telescoping-sdd:critic`, `telescoping-sdd:simplifier`

> Always invoke panelists by their `telescoping-sdd:` prefix so the plugin's customised persona resolves rather than the built-in of the same name.

## The Loop

1. **Dispatch all three panelists in a single message.** Issue three Agent tool calls in the same response block — not three separate responses with waits between them. If you find yourself reading Panelist 1's output before Panelist 2 and 3 are invoked, you've serialized; abort and re-dispatch all three at once. The synthesis in step 2 must wait until all three have returned. Pass each panelist the current artifact and any upstream approved artifacts as context. The invocation prompt must explicitly include the contents of the artifact's `### Sealed dispositions` sub-section followed by the instruction: *"Do not re-raise items in the Sealed dispositions list unless you have new substantive evidence that did not appear in the prior disposition."* Without this instruction, panelists tend to re-raise sealed items each pass; the format change in `### Sealed dispositions` only helps if the prompt actively suppresses re-raise. Also include the full text of the artifact's `### Deferred dispositions` sub-section followed by the instruction: *"For items in Deferred dispositions: the concern has already been routed to the named downstream artifact. If you have no new evidence, do not raise it again. If you believe the prior routing was wrong or your evidence is genuinely new, raise it and flag explicitly in your rationale why this is not a duplicate of `[DEF-NN]`."* **Note on `Routed because:` visibility:** the rationale text on each `[DEF-NN]` entry is panelist-visible in every subsequent invocation prompt; synthesizers must treat the field as prompt content (factual, one sentence, no embedded instructions). Ask each panelist for a ranked list of concerns, each with a severity tag (`[HIGH]`, `[MED]`, or `[LOW]` — bracketed exactly as written), a one-line description, and a brief rationale. Regressions caught this pass should be additionally tagged `[REGRESSION]`.
2. **Synthesize in-thread** — read the three outputs, dedupe overlapping concerns, drop concerns the self-review or cross-doc check already resolved, and rank the remainder by severity.
3. For each remaining concern, apply one of these dispositions:
   - **Addressed** — the fix is clear and stays within the current phase's scope. Apply the fix to the artifact and note what changed.
   - **Deferred → `<TARGET.md>`** — the concern belongs in a later phase (e.g., `ops-reviewer` raises a deployment-runbook concern during Architecture). Record it without resolving in-phase; the downstream phase reads deferrals as input.
   - **Sealed** — a user-directed decision the panel should not re-raise (e.g., user chose specific architecture pattern over alternative). Notes must include `Defense: <reason>` so `archive_pass.py` can promote it to `### Sealed dispositions`.
   - **Accepted as risk** — the concern is valid but the user, after being asked, explicitly accepts it as a known risk. Notes must include `Defense: <reason>` (same promotion path as Sealed).
   - **User input needed** — the concern requires a judgment call you cannot make alone. Stop, ask the user, apply the resolution, and update the disposition to one of the others.
   - **Halt and re-scope** — fundamental scope-shaped concern (see `## Halt and Re-scope Exit` below). Two consecutive passes with this disposition fires the halt-trigger.
4. Write every concern and its disposition as a row in `### Latest pass detail` of the artifact's `## Panel Review` section (format below). Self-check entries from step 5 also land here, with `Source` set to `[SELF-CHECK] (a|b|c|d|e|f)`. **Phase 2 and Phase 3 only:** prefix the Concern text of every HIGH row with one of `[contract]`, `[detail]` (Phase 3 only), or `[upstream]` — see `## Concern tagging (Phase 2 and 3)` below.
5. Run the **Synthesizer Self-Check** (see § below) against the just-applied fixes. If issues are found, fix them and re-run the checklist; only proceed when every item is answered with cited evidence and any issues found are fixed.
6. Run `python <shared-script-path>/archive_pass.py <artifact> --phase <N>` (where `<N>` is `1`, `2`, or `3` matching the current phase) to archive this pass — promotes any newly-sealed items into `### Sealed dispositions`, appends a row to `### Trajectory` (with HIGH / regression / disposition counts; halt votes recorded in Notes), and clears `### Latest pass detail`. For Phase 2 and 3, the script also stashes a `tags=dXuYcZ` substring in the Notes column recording the count of `[detail]`/`[upstream]`/`[contract]` tags in the just-archived Latest. If the script exits 1, 2, or 3, fix the reported issue and re-invoke; do not proceed with unresolved violations.

   **Terminal-archive invocation.** For PLAN.md (the terminal Phase-3 artifact), invoke `python <shared-script-path>/archive_pass.py blueprint/PLAN.md --phase 3 --terminal`. The `--terminal` flag suppresses `### Deferred dispositions` auto-insert and row promotion, rejects any Deferred-disposed row in Latest as a format violation, and suppresses the strict-bar trigger.
7. **Halt-trigger check.** Read the last two rows of `### Trajectory`. If both rows' Notes column contains "halt vote" (case-insensitive substring match), the halt-trigger has fired — see `## Halt and Re-scope Exit` below for what to do. Otherwise proceed to step 8.
8. If this pass returned no new HIGH-severity concerns, exit the loop and proceed to validation (the trajectory row gets `converged (0 HIGH)` stamped in Notes by `archive_pass.py` to mark convergence in the historical record) — **unless this was a STRICT-BAR pass, which exits through the cross-check in `## Strict-Bar Convergence Mode` instead of exiting directly.** MEDIUM and LOW concerns from the final pass are still synthesized, disposed, and recorded in `### Latest pass detail` before archive — they just do not block exit. Rationale: HIGH issues are convergence-blocking (contradictions, regressions, unimplementable claims); MEDIUM/LOW are polish that surfaces in PR and implementation review anyway, so looping for them has diminishing value. **Cap: 5 passes.** If HIGH concerns remain after 5 passes, stop and ask the user: continue reviewing, or move on. Otherwise (HIGHs remain, cap not yet reached), repeat from step 1 against the updated artifact. Each new pass reads the full doc fresh — including the cleared `### Latest pass detail` and the cumulative `### Sealed dispositions` list (panelists are instructed not to re-raise sealed items unless they have new substantive evidence).

   **Handling re-raised deferred concerns.** When a panelist raises a concern that substantively matches an existing `[DEF-NN]` entry in `### Deferred dispositions`:

   - **If no new evidence is presented:** dispose as **Sealed** with Notes containing **exactly** `Defense: rerouted [DEF-NN]` (substituting the zero-padded two-digit ID, e.g., `Defense: rerouted [DEF-07]`). No other text in the Notes field. `archive_pass.py` recognises this marker at archive time via `MARKER_STRICT_PAT` and expands it to canonical Defense prose; do not write the canonical prose by hand. The marker must match exactly — case-sensitive `Defense: rerouted`, no hyphen in `rerouted`, two-digit zero-padded ID in square brackets. Near-miss forms (`re-routed`, `defense: rerouted`, single-digit ID `[DEF-1]`, smart-quote brackets) cause a hard-fail at archive time.
   - **If genuinely new evidence is presented:** dispose normally — `Addressed` if fixable in-phase, or `Deferred → <TARGET>` with Notes `Routed because: <new rationale>. See also [DEF-NN].` The Trajectory's Deferred count increments if re-deferred.

   *Positive example.* Panelist: "spec.md logging section has no structured-field spec." Check `### Deferred dispositions`: `[DEF-03]` **Logging structure detail** → tasks.md (pass 2) — Routed because: structured-log field design belongs in tasks. No new evidence. Synthesizer writes: `Disposition = Sealed`, `Notes = Defense: rerouted [DEF-03]`. Archive expands to: `Defense: already routed to tasks.md as [DEF-03]; no new evidence presented this pass.`

   *Negative example.* Same concern, but panelist cites a new regulatory requirement making the omission a compliance gap. The cite is genuinely new. Correct disposition: `Deferred → tasks.md` with `Notes = Routed because: compliance gap not present at pass 2; escalate in tasks. See also [DEF-03].` The concern re-enters `### Deferred dispositions` as `[DEF-04]`; the Trajectory Deferred column increments.

**Mode.** The loop runs in NORMAL mode by default. When the trajectory shows the panel spinning on downstream-deferrable findings, `archive_pass.py` emits a `STRICT-BAR-SIGNAL:` advisory and the synthesizer asks the user whether to switch the next pass to STRICT-BAR mode — see `## Strict-Bar Convergence Mode` below. Mode changes the panelist prompts and adds an exit cross-check; it does not change the step sequence above. When counting passes against the 5-pass cap, count NORMAL, STRICT-BAR, and skipped passes; **exclude** cross-check passes (their `### Trajectory` Notes contain `cross-check pass`).

**Cap-pressure caveat.** In re-entered loops (after `--skip`, after a re-stamp cascade, or any restart that does not reset the cap counter), the 5-pass cap counter advances quickly and may bias the synthesizer toward "address every panelist finding with prose" in pursuit of convergence. **Resist this.** The synthesizer's job is to *judge* each panelist proposal against existing doctrine (seals, immutability, CFC structure, the Self-Check (a)–(f) categories), not to apply every proposal. **Accepting-as-risk** a finding with a documented `Defense:` is a first-class disposition; it is often the *correct* outcome when accepting prevents a regression cascade (the panelist's proposal would introduce a new bug, or violate an existing invariant). The 5-pass cap is a stopping point, not a deadline. If the cap is about to be reached and HIGH concerns remain, the right move is to stop, escalate to the user, and accept the un-converged state — not to pattern-match on a panelist's proposed-fix wording and apply it without examining the doctrinal premise. Closed-feature-row immutability (Self-Check (e)) is one of the most common doctrinal premises to lose under cap pressure: a panelist sees a CFC binding obligation and proposes editing the closed feature's row; the doctrinal-correct response is to re-route, not to apply.

Cap-pressure also tilts toward **domain ignorance**: authoring contract prose that names code-shape commitments (e.g., "this CFC binds 6 consumers including F<n>", "the seed list contains these 5 keys") without grep-verifying each named feature or mechanism against the source text. Sharpened Self-Check (b) extends to claims about the project's own approved artifacts (PLAN.md, SCOPE.md, ARCHITECTURE.md, sibling specs); for intra-artifact claims, "the citation exists" is not sufficient — the cited text must literally support the specific claim. When in doubt under cap pressure: **quote the source verbatim in the self-check record before applying the fix**. The verbatim quote is the forcing function — without it, the synthesizer can pattern-match on adjacency; with it, the source text is physically in front of the synthesizer and the gap (e.g., a Participating-features list that names a feature the cited authoritative enumeration excludes) becomes visible. CFC authoring is the most drift-prone surface for this class — see Self-Check (f) for the two structural sub-checks (Enforcement scope alignment, seed/registry traceability) that (b) cannot cover.

## Panel Review section format

Each artifact ends with a `## Panel Review` section placed immediately before the Approval section. The section has four sub-sections, in this order (the terminal Phase-3 artifact `PLAN.md` omits `### Deferred dispositions` — the `--terminal` archive suppresses it, since a terminal artifact has no later phase to defer to):

```
## Panel Review

### Trajectory

| Pass | Date | HIGHs | Regressions | Addressed | Deferred | Sealed | Notes |
|------|------|-------|-------------|-----------|----------|--------|-------|

### Sealed dispositions

(bullet list of `[SEAL-NN]` entries; empty until the first sealed item)

### Deferred dispositions

(bullet list of `[DEF-NN]` entries; empty until the first deferred item — omitted on terminal Phase-3 `PLAN.md`)

### Latest pass detail

| Severity | Source | Concern | Disposition | Notes |
|----------|--------|---------|-------------|-------|
```

`scripts/archive_pass.py` is built to this layout — it parses, promotes, and clears these sub-sections. The format below is normative; the script will reject violations.

**Trajectory** — one row per archived pass. `Pass` and `Date` are filled in by `archive_pass.py`; the count columns come from parsing the latest pass detail at archive time. For skipped passes (`archive_pass.py --skip`), all count columns are dashed (`—`) and `Notes` is `skipped (mechanical: <reason>)`.

**Trajectory trim on approval.** When the document is approved (`validate_blueprint.py --approve <scope|architecture|plan>`), the Trajectory table is trimmed to the latest 15 data rows. Older rows are replaced with a single elided summary row at the top of the data section:

```
| … | … | — | — | — | — | — | N earlier passes elided |
```

`N` is the count of rows that were elided. Re-approval merges the existing elided count with new elisions (so the count is cumulative across multiple approvals). The trim runs before content-hash computation, so the hash reflects the trimmed state. Documents with ≤ 15 data rows are unchanged. The motivation is long-lived docs (re-entered loops, multi-phase amendments) whose trajectory tables grow unboundedly and dominate the rendered panel-review section; the trim preserves the audit-trail headline via the elided count without losing the recent context the synthesizer actually reads (halt-trigger, strict-bar trigger, cap counting all read the latest 1–2 rows).

**Sealed dispositions** — durable decisions that survive across passes. Each entry has the form:

```
- `[SEAL-NN]` **<Title>** (pass <N>, <user-directed | accepted-as-risk>) — Defense: <reason>.
```

`[SEAL-NN]` is sequential, two-digit zero-padded, assigned by `archive_pass.py` when it promotes an entry from Latest pass detail. Panelist prompts in subsequent passes include this list with the instruction *"do not re-raise sealed items unless you have new substantive evidence."*

**Deferred dispositions** — concerns routed to a named downstream artifact, surviving across passes so panelists do not re-raise them. Each entry has the form `` `[DEF-NN]` **<Title>** → <TARGET.md> (pass <N>) — Routed because: <reason>. `` `[DEF-NN]` is sequential, two-digit zero-padded, assigned by `archive_pass.py` when it promotes a `Deferred → <target>` row from Latest pass detail. Panelist prompts in subsequent passes include this list with the re-raise-suppression instruction (see § The Loop, step 1). On a legacy non-terminal artifact missing the sub-section, `archive_pass.py` auto-inserts the heading. The terminal Phase-3 artifact `PLAN.md` does not carry this sub-section — `--terminal` suppresses both the auto-insert and promotion, and rejects any `Deferred`-disposed row in Latest.

**Latest pass detail** — the most recent panel pass's concerns + dispositions. `archive_pass.py` clears this table at the start of each new pass; the synthesizer (you) populates it as the panel raises concerns. Format contract:

- `Severity` — exactly one of `[HIGH]`, `[MED]`, `[LOW]`. Optionally followed by `[REGRESSION]` for regressions caught this pass (e.g. `[HIGH] [REGRESSION]`).
- `Source` — panelist name (e.g. `devils-advocate`) or `[SELF-CHECK] (a|b|c|d|e|f)` for synthesizer self-check entries.
- `Concern` — one-line concern text. Escape any literal pipe as `\|` — an unescaped `|` adds a phantom cell, and `archive_pass.py`'s `parse_table` silently drops a row whose cell count differs from the header.
- `Disposition` — exactly one of: `Addressed`, `Deferred → <target>`, `Sealed`, `Accepted as risk`, `User input needed`, `Halt and re-scope`.
- `Notes` — rationale, fix description, target. For `Sealed` and `Accepted as risk`, **must include** `Defense: <reason>` — `archive_pass.py` lifts this verbatim into `### Sealed dispositions`.

Example rows:

| Severity            | Source           | Concern                                              | Disposition          | Notes                                                                              |
|---------------------|------------------|------------------------------------------------------|----------------------|------------------------------------------------------------------------------------|
| [HIGH]              | devils-advocate  | Goal G3 assumes integration X is free                | Addressed            | Added constraint C2 in §2.4                                                        |
| [HIGH] [REGRESSION] | [SELF-CHECK] (b) | Cloud Run cold-start budget unrealistic for runtime  | Addressed            | Switched to Cloud Functions Gen 2; cited Cloud Run docs                            |
| [MED]               | ops-reviewer     | No rollback plan for component C4                    | Deferred → PLAN.md   | Pick up in Milestone M3                                                            |
| [LOW]               | pragmatist       | Success criterion S2 is aspirational                 | Accepted as risk     | Defense: user accepted vagueness; tightened wording would block scope discussion.  |

An artifact with any concern still in `User input needed` disposition fails validation — every concern must land on `Addressed`, `Deferred`, `Sealed`, or `Accepted as risk` before approval (`Halt and re-scope` disposition rows do not survive into approved artifacts — `archive_pass.py` clears them with the rest of `### Latest pass detail`; the Trajectory may still carry historical `halt vote` notes from passes the user chose to override, which is intentional and does not block approval). `archive_pass.py` blocks archiving any pass with unresolved `User input needed` rows. For `PLAN.md` (the last artifact phase), concerns cannot be deferred forward; they must land on `Addressed`, `Sealed`, or `Accepted as risk`.

## Concern tagging (Phase 2 and 3)

For NORMAL passes in Phase 2 (Architecture) and Phase 3 (Plan), each HIGH-severity row in `### Latest pass detail` must prefix its `Concern` text with one of three scope tags. Phase 1 (Scope) does not use tags — its existing `User input needed` and `Deferred → DOWNSTREAM` dispositions handle every routing case it needs.

The tags are advisory labels chosen by the synthesizer (you) based on what the finding actually is. They are **orthogonal** to dispositions: a `[contract]` finding can be `Addressed` or `Accepted as risk`; an `[upstream]` finding can be `Addressed` or `Halt and re-scope`. Tags affect routing of triggers (halt and strict-bar); dispositions remain the panel's response to each individual concern.

- **`[contract]`** — this finding is an at-this-phase cross-feature or cross-component decision. In Phase 2 (Architecture): a component boundary that affects multiple features; a cross-component invariant; a system-wide quality-attribute commitment. In Phase 3 (Plan): an FQCN that another feature's ArchUnit rule references; an env-var naming convention shared across features; dependency-order sequencing across multiple features. Phase-3 `[contract]`-tagged findings have a prescribed home in PLAN's `## Cross-Feature Contracts` section (see `references/plan-template.md` for the four-field entry format; see `references/strict-bar-prompts.md` § Phase 3 for the full self-check that a `[contract]` finding fits the CFC shape).
- **`[detail]`** — Phase 3 only: this finding is a single-feature SDD-cycle concern (single-feature class naming, regex tuning, CODEOWNERS, runbook authoring, migration version numbering inside one feature). Phase 2 does not use `[detail]`; its existing `Deferred → DOWNSTREAM` disposition handles the "belongs in a later phase" case directly.
- **`[upstream]`** — this finding exposes a gap in an earlier-phase artifact. In Phase 2: shaped like a Scope decision that `SCOPE.md` doesn't commit. In Phase 3: shaped like a Scope or Architecture decision that the respective artifact doesn't commit (a goal/non-goal not expressed in SCOPE.md; an architectural component or risk that ARCHITECTURE.md doesn't cover).

**Tagging affects two triggers:**

1. **Halt-and-rescope trigger.** A `[upstream]`-tagged row auto-routes to a halt vote, alongside the existing `Halt and re-scope` disposition. Two consecutive NORMAL passes with at least one halt vote each fires the halt-trigger — see `## Halt and Re-scope Exit`.
2. **Strict-bar trigger.** In Phase 3, the strict-bar signal switches from `Deferred → DOWNSTREAM` accumulation to `[detail]`-tag accumulation (Phase 3 has no further blueprint phase to defer to, so `[detail]` is the Phase-3 analogue). Phase 1 and Phase 2 keep the deferred-based signal — see `## Strict-Bar Convergence Mode`.

`[contract]`-tagged findings contribute to neither trigger. They are the legitimate work product of an at-this-phase panel and flow through the disposition vocabulary normally (`Addressed`, `Accepted as risk`, `Sealed`, `User input needed`).

**Tag format.** The tag is the first thing in the `Concern` cell, in lowercase, square-bracketed. Examples:

```
| [HIGH] | architect    | [contract] DataStore must enforce tenant isolation at the query layer        | Addressed | added in §4.2 |
| [HIGH] | critic       | [detail] F33 AC doesn't name OperatorAlertRetrySweep class                  | Addressed | named in F33  |
| [HIGH] | ops-reviewer | [upstream] ARCH assumes multi-region deployment but SCOPE doesn't commit it | Halt and re-scope | escalate |
```

`archive_pass.py` parses the leading tag substring; missing or malformed tags are silently uncounted (the synthesizer self-check verifies their presence — see § Synthesizer Self-Check check (d)).

## Synthesizer Self-Check

After applying fixes from a pass and **before triggering the next panel pass**, you (the calling Claude — the synthesizer) must verify your own work against three categories of regression that the panel caught after-the-fact in prior real-world cycles. The panel is an effective independent reviewer for design issues, but it is wasteful to use a full panel cycle to catch bugs your own fixes just introduced. Run the self-check first; the panel can then focus on what only it can catch.

**Why this exists:** in observed cycles, three classes of synthesizer-introduced regressions were the load-bearing convergence blockers — claims that turned out to be unimplementable on the target stack, fixes that silently broke contracts elsewhere in the doc, and bulk-substitution edits that left tautologies and orphaned references. Each one burned a full panel cycle to catch. Self-check would have caught all three at synthesizer time.

**Seven checks:**

**(a) Contract preservation** — for each fix you applied, did it change an interface, component boundary, dependency edge, milestone deliverable, or invariant referenced elsewhere in the artifact (or a sibling artifact like `SCOPE.md` / `ARCHITECTURE.md` / `PLAN.md`)? If yes, are all references still valid? Did your fix contradict a previously sealed disposition (`Accepted as risk` or user-directed decision)?

**(b-i) Implementability AND intra-artifact fidelity** — for each new technical claim you added — whether about external stack / library / framework / cloud-platform behaviour OR about content in approved project artifacts (`PLAN.md`, `SCOPE.md`, `ARCHITECTURE.md`, sibling specs) — verify the cited source actually supports the *specific* claim, not just adjacent text. **Quote the supporting passage verbatim in the self-check record.** "Citation exists" is not sufficient — the cited text must literally say what your claim says. For intra-artifact claims, run `grep` and paste the matching line(s) in the self-check entry's Notes. For external claims, paste the docs URL or code reference plus the specific sentence or code-shape that supports the claim. Do not rely on training-data recall for stack-specific behaviour or paraphrased recall for artifact content. The verbatim-quote requirement is a forcing function: without a quote, the check can't pass cleanly; with a quote, the synthesizer is physically confronted with the cited text and can't pattern-match on adjacency. (Per the post-implementation field observation in `documentation/CFC.md § Domain-Ignorance in CFC Authoring`.)

**(b-ii) Symmetric application** (recorded under the same `[SELF-CHECK] (b)` Source tag as (b-i)) — when a fix excludes, drops, differentiates, or otherwise treats one item differently from others in a list, set, or enumeration based on cited evidence, apply the same source-check to every other item in the same list before archiving. Example: if `F35` is dropped from a CFC's Participating list because grepping F35's AC shows no binding-mechanism reference, run the same grep against every other feature in the same Participating list and either (i) drop them too, or (ii) record a verbatim quote in the self-check Notes showing why their evidence shape *is* different. Per-claim verbatim quotes prove individual claims; symmetric application prevents the most common residual error — rigorous evidence for the items the synthesizer questioned, casual acceptance of the items the synthesizer didn't think to question. (Per the v2 acceptance-test residual finding recorded in `documentation/CFC.md § Domain-Ignorance in CFC Authoring`.)

**(c) String-substitution hygiene** — after any rename / sed-class change / bulk edit: are there tautologies (e.g., `F26 + F26`, `F26/F26`, "F26 were merged")? Orphaned cross-references (`see §X` where §X has been removed)? Unbalanced markers (e.g., `[BEGIN ...]` without `[END ...]`)? Run `grep` and cite the result.

**(d) Tag presence (Phase 2 and 3 only)** — for each HIGH row from a panelist source in `### Latest pass detail` this pass, verify the `Concern` text begins with one of `[contract]`, `[detail]` (Phase 3 only), or `[upstream]` (per `## Concern tagging (Phase 2 and 3)`). `[SELF-CHECK]` rows are exempt — they describe synthesizer-side self-check findings (any of categories a/b/c/d/e/f), not at-this-phase panelist routing decisions, and `archive_pass.py` does not count their tags for halt/strict-bar routing. MED and LOW rows are also exempt (they don't block convergence). Missing or wrong-format tags on HIGH panel rows silently break the halt-and-rescope and strict-bar triggers; fix any missing tag before archiving — the panelist chose a wrong tag, or the synthesizer dropped one during synthesis. Cite each tagged row.

**(e) Closed-feature-row integrity (Phase 3 only)** — for each fix you applied that edits content under an `### F<n>:` heading inside PLAN.md, locate F<n>'s milestone checkbox in `## Milestones` using the lookup mechanic from `references/workflow-overview.md § Closed-Feature-Row Immutability` (search `## Milestones` for a line matching `^- \[[ xX]\] F<n>\b`; if F<n> appears in multiple milestone blocks, take the latest by milestone number). If the matched checkbox is `[x]`, the fix has edited a closed feature row — **halt, revert the edit, and re-route the obligation** to (i) the per-feature AC of the earliest amending feature inside a `## Cross-Feature Contracts` block, or (ii) the relevant `M*N Deliverable` narrative explaining who actually ships the artefact. If F<n> is not found in any milestone block, the feature has not been milestoned yet — the row remains editable; proceed. **Why this exists:** Phase-3 panelists routinely propose edits to feature rows when they spot a binding obligation (e.g., a CFC's per-feature AC that names F<n>), without checking F<n>'s milestone state. The synthesizer must verify the milestone state before applying the proposal; doctrine forbids in-place edits to closed feature rows even when a panelist proposes them. Cite each fixed row + the milestone-checkbox state you verified.

**(f) CFC authoring fidelity (Phase 3 only; fires when this pass's fixes added or edited content inside a `### CFC-N` block)** — for every CFC entry created or modified this pass, before archiving, run these two structural checks beyond sharpened (b)'s verbatim-quote rule:

  - **Enforcement scope alignment**: if the CFC's `**Contract:**` paragraph uses class-scoped wording (e.g., "outside *this component*", "no class outside `com.foo.bar.Baz`") but the `**Enforcement:**` mechanism is package-scoped (e.g., a grep guard over `com.foo.bar..`, an ArchUnit rule over a package), or vice versa, the two must be reconciled to the same scope. Quote both the Contract scope-noun and the Enforcement scope-noun in the self-check record; they must match. Catches the class-vs-package mismatch class observed in `documentation/CFC.md § Domain-Ignorance in CFC Authoring` error #1.

  - **Seed/registry traceability**: for any CFC that seeds a registry with example entries (e.g., "currently issued alert_keys: …"), trace each seeded entry back to its source code-shape — distinguish `publisher.publish(literal)` arguments from Micrometer counter names from ArchUnit FQCNs from env-var names from SQL identifiers. Different code-shapes belong in different registries; do not seed counter names into a publisher.publish registry, or vice versa. If F<n>'s key text comes from F<m>'s AC where F<m> ships *after* F<n>, the seed is a coordination requirement and CFC-3's "seed an empty registry; each feature adds its own key at its own merge" precedent applies — do not seed forward-feature keys. Quote each seeded entry's source AC bullet in the self-check record. Catches the counter-vs-publisher conflation and forward-feature seed coupling classes observed in `documentation/CFC.md § Domain-Ignorance in CFC Authoring` errors #2 and #5.

  Sub-checks for Participating-features enumeration and Per-feature-AC code-shape commitments are intentionally absent from (f); they fold into sharpened (b)'s verbatim-quote rule applied to intra-artifact claims. (f) covers only the two structural checks (b) cannot.

**Forcing function (structured checklist):** answer this checklist explicitly, citing evidence for every item. Do not write "looks fine" — show your work.

```
For each fix applied this pass:
  1. What did it change? (1-line description)
  2. (a) Is it referenced elsewhere in the doc or in sibling artifacts?
     `grep` proves yes/no. If yes, does each reference still hold?
     List each reference and its status.
  3. (b) Does it make a technical claim about the target stack OR a claim
     about content in approved project artifacts (PLAN.md, SCOPE.md,
     ARCHITECTURE.md, sibling specs)? If yes, verify against the actual
     source (docs / file path / grep result) AND **quote the supporting
     passage verbatim** in the self-check record. "Citation exists" is
     not sufficient — the cited text must literally say what the claim
     says.
  3a. (b-ii) Symmetric application: does the fix exclude, drop, or
      differentiate one item from a list/set based on cited evidence?
      If yes, run the same source-check on every other item in the
      same list before archiving. Drop them too, or record a verbatim
      quote showing why their evidence shape is different.
  4. (c) Did it involve string substitution / rename / bulk edit? If yes,
     run pattern-match for tautologies, orphans, and unbalanced markers,
     and cite the grep results.

Phase 2 and 3 only — for every HIGH row in Latest pass detail:
  5. (d) Does the Concern text begin with [contract], [detail] (Phase 3
     only), or [upstream]? List each row + tag, or "no tag" with the row.

Phase 3 only — for each fix:
  6. (e) Did the fix edit content under an ### F<n>: heading in PLAN.md?
     If yes, search `## Milestones` for `^- \[[ xX]\] F<n>\b` and report
     the matched checkbox state. If `[x]`: halt, revert, re-route to an
     amending feature or M*N Deliverable narrative; never apply.
  7. (f) Did the fix add or edit content inside a ### CFC-N block?
     If yes, run two structural checks beyond (b)'s verbatim-quote:
       - Enforcement scope alignment: quote both the Contract paragraph's
         scope-noun (class/component vs package/module) and the
         Enforcement mechanism's scope-noun; they must match.
       - Seed/registry traceability: for each seeded entry, identify its
         source code-shape (publisher arg / counter name / ArchUnit FQCN /
         env-var / SQL identifier). Different code-shapes belong in
         different registries. If a seed's source AC belongs to a feature
         that ships after the CFC's owner, treat as a forward-feature
         coordination requirement (apply CFC-3's "seed empty" precedent).

For each issue found: apply the fix and re-run the checklist from step 1.

Only proceed to the next panel pass when the checklist runs clean
on every fix from this pass.
```

**Recording:** write each self-check finding into `### Latest pass detail` as a separate row, with `Source` set to `[SELF-CHECK] (a)`, `(b)`, `(c)`, `(d)`, `(e)`, or `(f)` matching the check it came from:

| Severity | Source                | Concern                                                              | Disposition | Notes                                |
|----------|-----------------------|----------------------------------------------------------------------|-------------|--------------------------------------|
| [HIGH]   | [SELF-CHECK] (b)      | Cloud Run cold-start budget unrealistic for chosen runtime           | Addressed   | Switched to Cloud Functions Gen 2    |
| [HIGH]   | [SELF-CHECK] (e)      | Applied AC bullet to F1 row but F1 is `[x]` in M3 — closed-row edit  | Addressed   | Reverted; re-routed to F37 amending feature's per-feature AC under CFC-3 |
| [HIGH]   | [SELF-CHECK] (f)      | CFC-5 Contract says "outside this component" but Enforcement is package-scoped grep | Addressed   | Reconciled both to package scope; quoted Contract+Enforcement scope-nouns |
| [MED]    | [SELF-CHECK] (a)      | Removed component C3 still referenced in PLAN.md milestone M2        | Addressed   | Updated M2 deliverable list          |
| [LOW]    | [SELF-CHECK] (c)      | Found 2 `F4 + F4` tautologies after feature-merge edit               | Addressed   | Cleaned up                           |

**What self-check does not replace:**
- The panel review — self-check catches synthesizer regressions; the panel catches design-level and blind-spot issues. Different failure modes.
- The validator — self-check is per-fix, the validator checks the artifact globally. Both still run.

**Interaction with panel skip (When to Skip the Panel, below):** self-check runs *before* the skip decision. If self-check finds a semantic issue (anything in (a) or (b)), the change is no longer purely mechanical — abort the skip and run a normal panel pass. The (c) hygiene check overlaps with the lint step in panel skip; that redundancy is cheap and intentional — same checks at different stages.

## Halt and Re-scope Exit

The panel can signal that an artifact's problems are scope-shaped — that the project itself, or this phase's framing of it, is fundamentally too big or too misaligned for the panel loop to converge. When that signal fires across two consecutive passes, the loop halts and routes back to the user for project-level scope reconsideration before continuing.

This is the **scope-pivot exit** — distinct from the soft pass budget (a fallback for general convergence failure) and distinct from the HIGH-count exit (which fires on successful convergence).

**When to use the `Halt and re-scope` disposition.** When a panelist raises a scope-shaped concern, judge:

- *Tightening-shaped* (e.g., "narrow this constraint", "split this milestone") → `Addressed`
- *Defer-shaped* (e.g., "this concern belongs in PLAN.md not ARCHITECTURE.md") → `Deferred → <target>`
- *Fundamental* (e.g., "this project spans multiple platforms with no shared foundation", "the chosen architecture cannot meet stated goals") → `Halt and re-scope`

The third disposition is a **vote**, not a final decision. A single halt vote does not halt the loop. **Two consecutive passes**, each with at least one halt vote, fires the trigger. Multiple halt votes within a single pass count as one halt vote for trigger purposes.

**A halt vote is recorded when EITHER:**
- a panelist disposes a finding as `Halt and re-scope` (the explicit case), OR
- a panelist tags a finding `[upstream]` in Phase 2 or Phase 3 (auto-routed by `archive_pass.py` regardless of the panelist's chosen disposition — per `## Concern tagging (Phase 2 and 3)`).

The `[upstream]` auto-route exists because the explicit `Halt and re-scope` disposition is rare in practice — panelists default to `Addressed` (which silently papers over the upstream gap) or `Accepted as risk` (which seals the gap as deliberate). Neither response surfaces the upstream gap to the user. Auto-routing on `[upstream]` catches the pattern even when the panelist doesn't choose the disposition explicitly.

**Halt-trigger check (loop step 7).** After `archive_pass.py` runs, read the last two rows of `### Trajectory`. If both rows' Notes column contains "halt vote" (case-insensitive substring match), the halt-trigger has fired. Stop — do **not** invoke the next panel pass.

**Halt summary and user confirmation.** Draft a brief halt summary citing both halt votes (Pass numbers, source panelists, concern titles, and whether each was an explicit `Halt and re-scope` disposition or an auto-routed `[upstream]` tag) and what re-scoping is needed. Present to the user.

For an explicit-disposition halt (scope-shaped framing problem):

```
Halt-and-rescope triggered. Two consecutive passes voted halt:
  - Pass <N>:   <source> — <concern>
  - Pass <N+1>: <source> — <concern>
The panel believes this artifact's framing is fundamentally wrong.
Revise project scope (SCOPE.md) or phase boundary, then restart? [y/n]
```

For an `[upstream]`-tag halt (Phase 2 or 3 panel surfacing earlier-phase gaps):

```
Halt-and-rescope triggered. Two consecutive passes raised [upstream]
concerns indicating the <PHASE> panel is exposing gaps in <UPSTREAM>:
  - Pass <N>:   <source> — <concern>
  - Pass <N+1>: <source> — <concern>
Update <UPSTREAM> to commit these decisions, then re-cascade and
restart this phase. [acknowledge / override]
```

`<UPSTREAM>` is `SCOPE.md` (for a Phase-2 halt) or `SCOPE.md` and/or `ARCHITECTURE.md` (for a Phase-3 halt — the `[upstream]` tag's concern should indicate which).

- **On user confirmation (explicit Halt):** stop the current phase. The user revises the project-level scope or phase boundary, then restarts the affected phase(s) with fresh Trajectories.
- **On user confirmation (`[upstream]` halt):** stop the current phase. The user updates the upstream artifact (`SCOPE.md` for Phase-2 halts; `SCOPE.md` or `ARCHITECTURE.md` for Phase-3 halts), the cascade machinery (see `references/hash-and-cascade.md`) re-stamps it and checks the downstream link that exposed the gap, then this phase restarts with a fresh Trajectory.
- **On user override:** continue the loop. The user has out-of-band context. The trigger will re-fire if halt votes keep coming on subsequent passes — each pass is a fresh opportunity to halt.

**Why two consecutive (not one):** a single panelist having a bad day shouldn't blow up the workflow. Two consecutive passes saying "halt" is durable signal that scope, not phrasing, is the problem. The synthesizer can manually halt for non-consecutive patterns and present the halt summary to the user even if `archive_pass.py` hasn't auto-detected the trigger.

**Interaction with skipped passes (panel skip, below):** the trigger check reads the last two trajectory rows literally. A skipped row (`skipped (mechanical: ...)` in Notes) breaks the consecutive-halt sequence — the auto-detection won't fire if a halt-voted pass is followed by a skipped pass. If you see a halt pattern interrupted by a skip and believe scope is still the issue, manually present the halt summary to the user even though `archive_pass.py` didn't auto-trigger.

**What the synthesizer must not do:**
- Auto-execute the re-scope without user confirmation.
- Manually clear halt votes from the Trajectory to suppress the trigger.
- Treat halt votes as `Addressed` without a real fix that changes the underlying scope problem.

## Strict-Bar Convergence Mode

On a moderately rich artifact, the panel reliably finds 2–4 HIGH concerns per pass even after many iterations — but past a certain point most of what it raises is real *and* legitimately belongs in a later phase (a scope-phase panelist surfacing a feature acceptance criterion that belongs in PLAN; an architecture-phase panelist surfacing a test-strategy gap that belongs in PLAN's test sections). Each such concern gets disposed `Deferred → <DOWNSTREAM>` and the doc never converges. The panel is doing honest work; the loop just can't tell "still finding *this-phase* concerns" from "fully converged, grinding on downstream-deferrable items."

Strict-bar mode recalibrates the panel from "find concerns" to "find concerns that need a decision at *this* phase." It is a **convergence tool, not a default** — the early NORMAL passes are where the panel earns its keep (contradictions, exploits, ambiguities, missing constraints). Switching too early suppresses real findings.

### Trigger condition (the signal to watch for)

The synthesizer watches `### Trajectory` for this two-part signal:

- **HIGH-count not meaningfully dropping (delta ≥ -1) across the last two NORMAL passes** — i.e. the panel isn't making real progress closing HIGH concerns. A drop of 2 or more is genuine convergence and the trigger does *not* fire there; only stable or rising HIGH-count qualifies as the spinning pattern this mode is for.
- **AND a phase-dependent ratio condition exceeds 0.5 across those two passes:**
  - **Phase 1 and Phase 2:** >50% of disposed concerns are `Deferred → <DOWNSTREAM>` — i.e. the panel is mostly producing downstream work, not this-phase fixes.
  - **Phase 3 (Plan, the last blueprint phase):** >50% of disposed concerns are tagged `[detail]` (per `## Concern tagging (Phase 2 and 3)`). Phase 3 has no further blueprint phase to defer to; `[detail]` is the Phase-3 analogue of "belongs in a later phase" (it identifies single-feature SDD-cycle concerns that the relevant feature's spec-driven-dev cycle will naturally surface). `archive_pass.py` reads `[detail]` counts from the `tags=dXuYcZ` substring it stashes in the Trajectory Notes at archive time.

**`[upstream]` tags do NOT contribute to the strict-bar trigger.** They route to the halt-and-rescope trigger instead (see § Halt and Re-scope Exit). Strict-bar is "find concerns at *this* phase" — `[upstream]` concerns belong at an *earlier* phase, so filtering them in strict-bar would silently let the upstream gap persist. The two triggers are deliberately disjoint.


> **Worked example (R7).** A Phase-1 pass shows: 4 Addressed, 0 literal Deferred, 3 Sealed — 2 of those 3 Sealed rows were expanded by `archive_pass.py` from `Defense: rerouted [DEF-NN]` markers (i.e., they are re-routed-deferral rows, each beginning `Defense: already routed to …`). Trajectory's Sealed column records 3. Trigger's deferred-equivalent for this pass = 2 (the `rerouted_def_count`). Pooled over two passes where the previous pass had 4 literal Deferred (and 4 Addressed, 0 Sealed): `pooled_deferred = 4 + 2 = 6`; `pooled_total = (4+4+0) + (4+0+3) = 15`; `ratio = 6/15 = 40%`, below the >50% threshold — trigger does not fire. If the previous pass had 6 literal Deferred (and 1 Addressed, 0 Sealed) and the current has 2 rerouted + 1 Addressed: `pooled_deferred = 6 + 2 = 8`; `pooled_total = (1+6+0) + (1+0+2) = 10`; `ratio = 8/10 = 80%` — trigger fires.

### Auto-detection (fire-and-ask) and manual invocation

After every NORMAL archive, `archive_pass.py` checks both trigger conditions against the last two NORMAL trajectory rows (the just-archived row plus the most recent prior NORMAL row, stepping over any intervening strict-bar / cross-check / skipped rows). When both conditions are met, the script emits a `STRICT-BAR-SIGNAL:` line on stdout summarising the HIGH delta and the phase-appropriate ratio (deferred-downstream percentage for Phase 1/2; `[detail]`-tag percentage for Phase 3). The synthesizer reads that advisory and **asks the user**, citing the same ratio:

> Phase 1 or 2:
> "Strict-bar trigger fired (HIGH delta ..., XX% deferred downstream). Switch the next pass to strict-bar mode? (yes / no)"

> Phase 3:
> "Strict-bar trigger fired (HIGH delta ..., XX% of disposed concerns tagged [detail]). The panel is finding real concerns but most are single-feature SDD-cycle-natural and will be caught in the relevant feature's SDD design/tasks phase. Switch the next pass to strict-bar mode? (yes / no)"

- **User says yes** — the next pass runs in STRICT-BAR mode.
- **User says no** — the next pass stays NORMAL. If the trigger fires again on the following pass, ask again; the advisory is never silently auto-applied.

The user can also request strict-bar without waiting for the trigger — saying "strict bar" at any time switches the next pass, including before the trigger has fired (e.g. for an artifact the user already believes is converged).

### Running a strict-bar pass

Same panelists, same loop steps 1–7. The only change is the invocation prompt: load `references/strict-bar-prompts.md` and append the core filter rule, the current phase's excluded/required lists, and the inspectability instruction to every panelist's prompt. Synthesize, dispose, self-check, and archive as normal — but archive with `python <shared-script-path>/archive_pass.py <artifact> --phase <N> --strict-bar` so the Trajectory Notes record the mode. (For the terminal Phase-3 artifact `PLAN.md`, add `--terminal` as well — `archive_pass.py` hard-rejects that filename without it; see the Terminal-archive invocation in `## The Loop`, step 6.)

If a strict-bar pass returns HIGHs, those are genuine this-phase decisions — dispose them normally (often `Sealed`, `Accepted as risk`, or `User input needed`) and run another pass. Mode stays STRICT-BAR.

### Exit cross-check

When a STRICT-BAR pass returns **zero HIGHs**, do not exit directly. Run **one** final NORMAL panel pass as an audit, and archive it with `--cross-check` (this pass does **not** count toward the 5-pass cap). Then judge its HIGHs:

- **Cross-check returns 0 HIGHs** → exit the loop. Proceed to validation.
- **Cross-check returns HIGHs that all match the strict-bar prompt's exclusion categories** (Phase 1/2: UX surfaces, feature ACs, ARCH patterns, test strategy, etc.; Phase 3: all tagged `[detail]` per `## Concern tagging (Phase 2 and 3)`) → exit the loop, validated. The cross-check confirmed the strict bar filtered correctly; record and dispose its concerns exactly as a normal pass would (§ The Loop, step 3) before archiving.
- **Cross-check returns any `[upstream]`-tagged HIGH** (Phase 2 or 3 only) → halt-and-rescope. `archive_pass.py` auto-routes the `[upstream]` row to a halt vote; the cross-check trajectory row will carry "halt vote" in Notes. Surface this to the user using the `[upstream]`-tag halt prompt in `## Halt and Re-scope Exit`. Do not silently filter `[upstream]` concerns as "strict-bar exclusion match."
- **Cross-check returns HIGHs that do *not* match the excluded categories** (Phase 1/2: a real at-this-phase concern slipped past strict bar; Phase 3: a `[contract]`-tagged concern slipped past) → the strict bar over-filtered. Set mode back to NORMAL, dispose the cross-check's concerns normally, and continue the loop from step 1. **The 5-pass cap counter does NOT reset** — something unusual is happening, so the user-decision gate stays where it is.

### Exit paths by mode

| Mode | Pass result | Path |
|---|---|---|
| NORMAL | 0 HIGHs | Exit directly (strict bar never ran, so no cross-check needed) |
| NORMAL | HIGHs remain | At the 5-pass cap → stop at the cap gate (ask user: continue or move on). Under cap → stay NORMAL, or (trigger fired and user confirms / user requested) switch the next pass to STRICT-BAR |
| STRICT-BAR | 0 HIGHs | Run the exit cross-check (above) before exiting |
| STRICT-BAR | HIGHs remain | At the 5-pass cap → stop at the cap gate (ask user: continue or move on). Under cap → dispose the strict HIGHs and stay STRICT-BAR |

### Cap accounting

| Pass type | Counts toward 5-pass cap? |
|---|---|
| NORMAL pass | Yes |
| STRICT-BAR pass | Yes — same single counter; mode-switching mid-loop must not buy extra cycles |
| Cross-check pass | No — exit ceremony, not a convergence attempt |
| Skipped pass (`--skip`) | Yes — a skip is still a loop iteration |

| Event | Counter resets? |
|---|---|
| Mode switch NORMAL → STRICT-BAR | No |
| Cross-check kickback STRICT-BAR → NORMAL (filter over-fired) | No |
| Halt-and-rescope confirmed by user (phase restarts) | Yes — fresh Trajectory, fresh counter |
| User confirms "continue" at the 5-pass cap gate | Yes — cost already accepted; don't re-ask every pass |
| User chooses "move on" / accepts remaining HIGHs at the 5-pass cap gate | N/A — the loop exits |

Because cross-check passes still get a `Pass` number from `archive_pass.py`, the synthesizer counts against the cap by reading Trajectory Notes — count every row *except* those whose Notes contain `cross-check pass`.

### Interaction with other exits

- **Halt-and-rescope** takes priority over everything — the step-7 halt-trigger check runs every pass regardless of mode. A strict-bar panelist that sees a fundamental scope problem still votes `Halt and re-scope`.
- **Panel skip** is orthogonal — a mechanical-only change can be skipped in either mode. A skipped pass does not change the current mode. Its `### Trajectory` row carries dashed counts, so it contributes nothing to the trigger's HIGH-count or deferral-rate read; the synthesizer judges the trigger from the last two *panel* passes, stepping over any `skipped` rows.

## Lightweight Mode (single-pass panel)

The default loop — drafting subagent (≤5 self-review passes) plus a ≤5-pass convergence panel of three personas, with strict-bar, halt-and-rescope, and the exit cross-check layered on — is calibrated for **substantial, long-lived, multi-feature work**: a blueprint other people will build a whole project against, that will be re-entered and amended, where a missed contradiction or unmet goal is expensive to discover late. On a small single-component project, a throwaway prototype, or an exploratory spike, that machinery is disproportionate — the strict-bar/halt/cross-check apparatus exists to *reach* convergence on rich documents, and there is little to converge on.

For those cases the user may opt into **lightweight mode**: one panel pass, then exit. This is distinct from `## When to Skip the Panel` below — skip is gated on *mechanical re-edits* of an already-reviewed artifact and explicitly cannot apply to a fresh draft; lightweight mode is the opposite, a single *genuine* panel pass on a fresh small artifact. The default stays the full loop; lightweight mode is **opt-in only** and never auto-selected.

**When it fits (the user says so):** the user describes the work as small, throwaway, exploratory, a prototype/spike, or a single-component project, and explicitly asks for a lighter review (e.g. "this is a throwaway prototype, do a light review", "single-pass panel", "lightweight mode"). If the user hasn't said the work is small, run the full loop. If you believe a nominally-small project is actually load-bearing (it will spawn many features, it commits a Cross-Feature Contract, it is the foundation other work depends on), say so and recommend the full loop before accepting the opt-in.

**The single pass:**

1. Run **one** NORMAL panel pass exactly as `## The Loop` steps 1–4 describe — same three panelists, dispatched together, synthesized in-thread, each concern disposed (`Addressed` / `Deferred → <target>` / `Sealed` / `Accepted as risk` / `User input needed`), every row written to `### Latest pass detail`. Phase 2/3 concern tagging still applies.
2. Run the **Synthesizer Self-Check** (§ above) against the fixes — this is *not* skipped; it is the cheap catch for synthesizer-introduced regressions and stays mandatory in lightweight mode.
3. Archive the pass with `python <shared-script-path>/archive_pass.py <artifact> --phase <N>` (add `--terminal` for the terminal Phase-3 artifact `PLAN.md`). No special flag exists for lightweight mode — it is an ordinary NORMAL archive; the single Trajectory row is the audit trail.
4. **Exit to validation regardless of remaining HIGHs.** Do not loop. Before exiting, surface any unresolved HIGH concerns to the user in one line each so the lighter bar is an informed choice ("Lightweight pass left 2 HIGH concerns unresolved: … — proceed to approval, or switch to the full loop?"). `User input needed` rows must still be resolved before validation can pass — lightweight mode does not relax the validator.

**What lightweight mode turns off:** the convergence loop (no second pass to drive HIGHs to zero), the strict-bar trigger and STRICT-BAR mode, the exit cross-check, and the 5-pass cap (there is only one pass). The `STRICT-BAR-SIGNAL:` advisory `archive_pass.py` may emit after the archive is informational only here — do not act on it.

**What it keeps:** the drafting subagent and its self-review, your own re-review and any cross-doc consistency check, the full disposition vocabulary, the Synthesizer Self-Check, the format contract for `## Panel Review`, validation, and the human approval gate. The halt-and-rescope *disposition* is still available on the single pass — if the one pass surfaces a fundamentally-wrong scope (or an `[upstream]` tag in Phase 2/3), present the halt summary from `## Halt and Re-scope Exit` rather than waving it through; a project too big to review lightly is exactly the signal lightweight mode must not suppress.

**Mid-stream and re-approval interaction:** lightweight mode governs only the *fresh-artifact* panel. Re-Approval After Edits and mid-stream entry (their upstream panel re-review step) are governed by their own flow in `references/hash-and-cascade.md` and are unaffected; a small artifact's later edits still route through that flow normally.

## When to Skip the Panel

If the only edits since the last panel pass are **mechanical** — string substitutions, file moves, validator-driven changes, or removed-already-decided content with no new semantic content — replace the panel with an automated lint check. Lint-class work doesn't need a design review; running a full panel on a sed cleanup wastes cycles and risks the panel objecting to phrasing artifacts of the cleanup itself.

**Mechanical vs. not:**

| ✅ Mechanical (eligible to skip)                     | ❌ Not mechanical (run panel)                  |
|------------------------------------------------------|------------------------------------------------|
| Rename throughout the doc                            | Add or remove a goal / constraint              |
| Fix typos, formatting, table alignment               | Reword to change intent                        |
| Drop sections already deferred to a later artifact   | Restructure features (split / merge / collapse) |
| Apply validator-flagged edits                        | Change a dep-table edge or milestone scope     |
| Cross-reference cleanup after a rename               | Add or remove a feature                        |

**Skip flow (no user gate; the Trajectory row is the audit trail):**

1. Synthesizer applies the fix and declares the change category: `Mechanical: <reason>` (e.g., "rename F26 → F26.1, 15 occurrences").
2. **Lint runs automatically:**
   - Run the validator (`<script-path>/validate_blueprint.py`) — must pass.
   - `grep` for sed-damage patterns: tautologies (e.g., `F26 + F26`, `F26/F26`), orphaned references (`see §X` where §X has been removed), unbalanced markers.
   - Synthesizer self-reads the diff — every changed line must be traceable to the declared rule. If any line introduces new semantic content, the change isn't mechanical; abort the skip and run a panel.
   - Cross-doc consistency — references in sibling artifacts (e.g., `SCOPE.md`, `ARCHITECTURE.md`, `PLAN.md`) still resolve.
3. **If lint fails:** auto-fall-back to a normal panel pass. The lint failure means the declaration was wrong.
4. **If lint passes:** invoke `python <shared-script-path>/archive_pass.py <artifact> --phase <N> --skip "<reason>"` to record a skipped row in `### Trajectory` (all count columns dashed; Notes set to `skipped (mechanical: <reason>)`). No confirm prompt — the trajectory row is the audit trail. (For the terminal Phase-3 artifact `PLAN.md`, add `--terminal` to the command above — `archive_pass.py` hard-rejects that filename without it; see the Terminal-archive invocation in `## The Loop`, step 6.) Proceed to the next pass (or to validation if convergence is met).

**User override (out-of-band, optional):**
- *Pre-empt:* user instructs "run a panel even though this is mechanical" before the pass starts (e.g., for fragile areas where they want extra eyes).
- *Retro-challenge:* user questions a recorded skip after the fact and requests a panel pass on the affected change.

**What the synthesizer must NOT do:**
- Skip without declaring the change category (no silent skips).
- Skip when the change is partly mechanical and partly semantic — split into two passes (mechanical first, semantic second).
- Skip when the synthesizer self-check flagged a new issue that wasn't fixed.
- Skip without lint actually running.

## Handling change requests at the review gate

The phase docs end with **"Stop and ask the user to review `<artifact>` before proceeding"** (`phase-{scope,architecture,plan}.md` § Validation and approval). The common case at that gate is the user reading the presented artifact and saying *"no, change X"* **before** approving. This is still a panel-relevant change, so it routes back into the loop above — it does **not** get applied silently and re-presented.

The artifact has **not been approved yet**, so it has no content hash. This is the load-bearing difference from `hash-and-cascade.md § "Re-Approval After Edits"` (which fires only on an *already-approved* document): there is **no re-stamp and no downstream cascade** at the pre-approval gate. You just incorporate the change, re-converge the panel, and re-present. (`Re-Approval After Edits` is the post-approval analogue — same idea, but it adds the hash re-stamp and the consistency-check cascade because approved downstreams may now be measured against stale upstream content.)

**Route by the size of the requested change** (the same trivial-vs-substantive cut the loop already uses):

| Requested change | Route | Records a Trajectory pass? |
|---|---|---|
| **Substantive** — adds/removes/reshapes a goal, constraint, requirement, AC, scope boundary, component, dependency edge, or any intent-bearing content | Treat as a new panel-relevant change. Re-enter the loop: apply the change (re-drafting via the phase's drafting agent if the change is large enough to warrant it), then run a fresh panel pass (§ The Loop). | **Yes** — a normal NORMAL pass via `archive_pass.py <artifact> --phase <N>`. |
| **Trivial wording** — typo, phrasing, formatting, or other change with no new semantic content | Apply as a synthesizer fix, then run the **Synthesizer Self-Check** (§ above) against it. If the Self-Check stays clean (nothing in (a)/(b)), it is mechanical and **panel-skip-eligible** under `## When to Skip the Panel` — record a skipped Trajectory row, do not run a full panel. | **Yes** — either a NORMAL pass or a `--skip` row; never a silent edit. |

**Rule of thumb:** if the change could alter what a panelist would say (a goal, a constraint, a component, a contract, a boundary), re-run the panel. If it only changes how existing intent is *worded*, it is a candidate for the panel skip — but the Synthesizer Self-Check decides: a "wording" change that the Self-Check finds touches a contract or an implementability claim is no longer trivial, and the skip aborts to a full panel (per `## When to Skip the Panel`, "abort the skip and run a normal panel pass").

**Either way, the change is recorded as a Trajectory pass** — it is another panel-relevant change to a not-yet-approved artifact, so it counts against the 5-pass cap exactly like any other pass (a skip is still a loop iteration). Dispose any concerns it surfaces with the normal vocabulary (`Addressed` / `Deferred` / `Sealed` / `Accepted as risk`). Then re-present the updated artifact at the same gate. Only when the user approves does the phase run its validator (`validate_blueprint.py --approve <phase>`) and stamp the first content hash — at which point any *later* edit becomes a `Re-Approval After Edits` event, not a gate change request.

**What the synthesizer must not do:** apply a gate change request silently without a Trajectory row (no audit trail); re-stamp or run a cascade (no hash exists yet — those belong to the post-approval flow); or treat a substantive scope/requirement change as trivial to avoid a panel pass.
