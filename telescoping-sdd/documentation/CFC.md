# Cross-Feature Contracts (CFC)

> **Provenance note.** This document is the authoritative design spec for the CFC subsystem. It was **reconstructed from the shipped code, tests, and the ~30 in-repo citations** that point at it (the original file was referenced everywhere but absent). Mechanical claims — regex literals, state names, exit codes, severities, exact message strings — were read directly from `cfc_parser.py`, `validate_blueprint.py`, `validate_spec.py`, and the CFC test suites and are **observed fact**. Two narrative sections (`## Evidence`, the per-error prose in `## Domain-Ignorance in CFC Authoring`) are **evidence-grounded reconstruction** of prose that no longer survives verbatim; they are marked as such. The section headings here are chosen to match the anchors cited elsewhere (`§ Evidence`, `§ Validator`, `§ Bound-spec detection`, `§ Domain-Ignorance in CFC Authoring`, `## Deferred to v2`) so those references resolve.

A **Cross-Feature Contract** is an invariant committed at PLAN time that spans multiple features whose individual SDD cycles never see the whole set. PLAN.md's optional `## Cross-Feature Contracts` section carries one `### CFC-N` entry per contract; each entry binds several features and surfaces inside every participant's Specify → Design → Tasks cycle via `[CFC-N]` tags. The subsystem is **mechanical drift detection, not cascade**: v1 detects when a bound spec drifts from its contract and tells the author; it does not auto-propagate edits (see `## Deferred to v2`).

---

## Evidence

> **Reconstruction.** Verbatim originating text lives in `skills/project-blueprint/scripts/tests/test_cfc_cli_integration.py` (the fixture explicitly "mirrors the originating evidence"). The prose below reconstructs what `§ Evidence` recorded.

CFC exists because of a real project (codenamed **soc_coach**) where the per-feature SDD loop structurally could not express three invariants. Each binds features that ship in *different milestones*, so no single feature's cycle ever sees the whole set — the invariant must be committed at PLAN level, upfront, where every participant can author against it.

The three originating contracts (now the canonical CLI-integration fixture):

1. **Lock order across features (CFC-1).** Database locks must be acquired in a canonical order (`A→B→C→D→E→F`) to prevent deadlock. F11 ships in an early milestone while later lock-order participants (F13/F15/F17/F19) ship in M3+ — "no single feature's SDD cycle can see the full set." Enforcement is owned by **F36** (an ArchUnit rule), on behalf of participants that do not own the check.
2. **Single-writer for the audit log (CFC-2).** All writes route through `OperatorAuditLogWriter` (participants F2/F20/F29/F33/F34/F35).
3. **Advisory-lock-key registry (CFC-3).** Every caller of `pg_advisory_xact_lock(hashtext(...))` must register its key string in a shared registry. `hashtext` is 32-bit, so two independently-authored specs picking similar keys cannot detect collisions without a registry; collisions surface as random deadlocks under load. F2 owns the registry module and its initial entries; new entries are reviewed at PR time (documentation-driven — no ArchUnit rule).

These generalize into the rule of thumb for **when to write a CFC**: an invariant that (a) binds features shipping in different milestones, (b) cannot be expressed as a dependency-graph edge ("F1 and F2 must *agree on a rule*," not "F1 needs F2 first"), or (c) has more than one owner of enforcement.

---

## Overview and v1 Scope

The `## Cross-Feature Contracts` section in `PLAN.md` is **optional** — its absence is never a validation failure. When present, the subsystem has three layers:

- **Producer** — `skills/project-blueprint/scripts/validate_blueprint.py` parses the section, computes a per-CFC structured content hash, stores it under `## Approval`, and runs a coverage walk + orphan-tag scan over `specs/F<n>/`, emitting `orphaned-stale-content` (and sibling) WARNs.
- **Consumer** — `skills/spec-driven-dev/scripts/validate_spec.py` enforces that each participating feature's `spec.md` carries the `Per-feature AC` line `[CFC-N]`-tagged on a THEN clause, and that an Enforcement-owner feature's `tasks.md` carries a `[CFC-N]`-tagged task. See **§ Validator**.
- **Shared parser** — `scripts/cfc_parser.py` owns every CFC regex and the four-field `CFCEntry` so producer and consumer can never drift on format. See **decision C** in the **## Decision log**.

**v1 ships:** the shared parser, per-CFC structured-content hashing, the four-state bound-spec classifier (**§ Bound-spec detection**), and mechanical drift detection. Everything in **## Deferred to v2** (the cascade engine, interactive remediation, validator-driven scaffolding) is out of scope.

---

## Authoring discipline

> Authoritative authoring template: `skills/project-blueprint/references/plan-template.md § Cross-Feature Contracts`. Consumer-side obligations per phase: `skills/spec-driven-dev/references/phase-{specify,design,tasks}.md`.

Each contract is `### CFC-N: <short title>` with four required fields, **in this order**:

```
### CFC-1: Lock acquisition order

- **Participating features:** F11, F13, F15, F17, F19
- **Contract:** Locks are acquired in canonical order A→B→C→D→E→F. (Spans M2–M4; no single feature sees the full set.)
- **Per-feature AC:** THEN locks are acquired in the canonical order A→B→C→D→E→F [CFC-1]
- **Enforcement:** F36 owns the ArchUnit rule LockOrderCheck.
```

- **Participating features** — comma-separated `F<n>` only, no backticks, no prose. Must match `^F\d+(?:,\s*F\d+)*$`.
- **Contract** — the invariant in declarative language, plus one sentence on *why* it cannot be a single-feature concern (different milestones / multi-feature enforcement / no single owner). Free prose; **excluded from the content hash**.
- **Per-feature AC** — the exact, verbatim AC line each participant must copy into its `spec.md` and tag `[CFC-N]` on a **THEN** clause. Copy-paste fidelity is the point; the panel surfaces substantive rewordings.
- **Enforcement** — how the contract is verified (ArchUnit rule, CI grep/workflow, integration test, runbook gate). Name the owning feature's bare `F<n>` token **only if it owns the verifying artifact**; if none, write one of the accepted disclaimers — `no owning feature`, `co-owned by F<n>, F<m>`, `no single owner`, or `no owner`.

**CFC numbering.** Numbers are unique within the current PLAN, canonical decimal (no leading zeros, not `0`), and must **never be renumbered or re-used after deletion** — re-using a number silently re-targets `[CFC-N]` back-references in already-bound specs to a different contract.

**The Enforcement owner-detection trap.** Owner detection grabs *every* bare `F<n>` token in the Enforcement prose (word-boundary scan). Naming a feature that does not own the verifying artifact produces a spurious `tasks.md` obligation for that feature downstream. Name `F<n>` only for the actual owner.

CFC authoring is the most drift-prone surface in the workflow — it puts code-shape commitments (FQCNs, registry keys, owning-feature IDs) into prose an LLM tends to write from recall rather than from the source text. The catalog in **## Domain-Ignorance in CFC Authoring** records the observed failure modes; the panel synthesizer self-checks reference it directly.

---

## Data model and the shared parser

All section/entry/field/tag regexes and the `CFCEntry` data model live in one dependency-free module, `scripts/cfc_parser.py`, imported by both producer and consumer (**decision C**). Neither validator re-implements the format; a contract test pins their symmetry.

### Section and entry grammar

- **Section header** (canonical): `CFC_HEADER_PATTERN = re.compile(r"^##\s+Cross-Feature Contracts\s*$", re.MULTILINE)` — case-sensitive, H2, column-zero, no trailing colon. `extract_cfc_section(content)` returns `(start, end, body)` where `start` is just after the header line and `end` is the next `^## ` heading (or EOF); it returns `None` when the canonical header is absent.
- **Near-miss header** (**P6**): `detect_near_miss_cfc_header` returns `None` when the canonical header matches; otherwise it matches `r"^[ \t]*##\s*[Cc]ross[-\s][Ff]eature\s+[Cc]ontracts?[\s:]*$"` and returns the offending line. This catches leading indentation, case-drift on the C/F, a hyphen-or-space between *Cross* and *Feature*, an optional trailing *s*, and a stray colon/whitespace — turning a silent extractor failure (the entire section becoming invisible) into an explicit FAIL.
- **Entry header**: `CFC_ENTRY_PATTERN = re.compile(r"^###\s+CFC-(\d+):\s*(.+?)\s*$", re.MULTILINE)` captures `(number, title)`. The number is validated by `CFC_ENTRY_NUMBER_FORMAT = re.compile(r"^(0|[1-9]\d*)$")` **plus** an explicit `raw == "0"` reject, so the accepted set is positive integers with no leading zeros (`7`, `10`, `100` accepted; `0`, `007`, `01` rejected and surfaced as malformed). Rejected headings are dropped from `parse_cfc_entries()` and reported by `parse_cfc_entries_with_malformed`. The diagnostic message describes the accepted set in words ("canonical decimal integer with no leading zeros and not zero (i.e., 1, 2, 3, …)") rather than quoting a regex, so it cannot drift from the implementation.

### The four fields

`CFC_FIELD_ORDER = ("Participating features", "Contract", "Per-feature AC", "Enforcement")`. Each field is matched by `_FIELD_PREFIX + r"\*\*<Name>:\*\*[ \t]*(.+)$"` (MULTILINE), where `_FIELD_PREFIX = r"^[ \t]*(?:[-*][ \t]+)?"` — start of line, optional indent, optional `- `/`* ` bullet, the literal `**<Name>:**` marker, then the value.

- The post-marker whitespace is `[ \t]*` (horizontal only), **not** `\s*` — using `\s*` would let an empty value backtrack across the newline and slurp the next line into the captured group.
- `_parse_fields` keeps the **first** occurrence of each field (repeats counted into `field_duplicates`); a missing field is left `None` and is **not** itself a parse failure (field absence is a separate diagnostic).
- **Participating features** parses via `CFC_PARTICIPATING_VALUE_PATTERN = re.compile(r"^F\d+(?:,\s*F\d+)*$")` — the *whole* value must be `F<n>` lists; anything else (e.g. `F1, F2 and the writer`) parses to `[]`. On a match it returns integers in **source order, duplicates preserved** (`F1, F1` → `[1, 1]`); dedup happens only in the producer's hash. (Because `\s` matches U+00A0, an NBSP separator still parses identically on both sides — pinned by a contract test.)
- **Enforcement owners** are *not* a strict list — the field is free prose, and every **word-boundary** `\bF(\d+)\b` token in it is an owner. So `F36 owns the ArchUnit rule` → `[36]`; a token inside a larger word (`xF36y`) is not an owner. This is a **different set** from Participating features: a feature can be Participating without being an Enforcement owner, and vice versa.

### Token-matching discipline (M2)

All CFC-number matching is **whole-number / word-boundary**, never substring:

- Feature IDs: `\bF(\d+)\b`, so `F1` is never found inside `F11`.
- Tags: `CFC_TAG_PATTERN = re.compile(r"\[CFC-(\d+)\]")`, and the **captured integer** is compared — `[CFC-1]` never matches inside `[CFC-10]` or `[CFC-100]`.

A tag counts as a **binding** only on a THEN line: `_THEN_LINE = re.compile(r"^[ \t]*(?:[-*][ \t]+)?THEN\b[^\n]*$", re.MULTILINE)`. Before scanning, `extract_cfc_tags` strips fenced code blocks (` ``` ` or `~~~`, length ≥ 3, replaced by equal-count blank lines to preserve line numbers), so an illustrative `THEN … [CFC-N]` inside a code example does not bind. `find_misplaced_cfc_tags` returns `(cfc_number, offending_line)` for any tag outside a THEN line, so the consumer can emit a distinct "tag in wrong location" diagnostic instead of a misleading "missing tag."

### Content-hash normalization

`normalize_for_hash(text)` applies, in order: (1) Unicode **NFC**; (2) collapse runs of `[ \t]+` to a single space — **NBSP (U+00A0) is deliberately excluded** so a whitespace-trick edit still changes the hash; (3) per-line strip; (4) collapse three-or-more newlines to two; final `.strip()`.

The producer subclasses the shared `CFCEntry` to add `structured_content_hash()`: SHA-256 (64-hex) over `json.dumps({n, participating, per_feature_ac, enforcement}, sort_keys=True)`, where `participating = sorted(set(participating_features()))` and the two text fields are run through `normalize_for_hash`. **Contract prose and the title are excluded** — Contract is rationale, not a binding clause. Sorting + deduping participating features means reordering them or removing an accidental duplicate does not change the hash (no spurious drift warning).

### Producer/consumer symmetry contract

`scripts/tests/test_cfc_parser_contract.py` asserts producer and consumer return identical results for the same PLAN text: identical CFC numbers, identical Participating lists, identical Enforcement owners, identical THEN-line tags, identical empty results for an absent section, plus six named edge cases (leading-zero `CFC-007` rejected, near-miss header invisible, fenced-code THEN non-binding, NBSP participating value, multi-digit `[CFC-100]` non-collision, and a missing `Per-feature AC` field still parsing). **One regex is not shared:** the `tasks.md` checkbox-tag matcher (`^[ \t]*-\s+\[[ xX]\]\s+[^\n]*?\[CFC-(\d+)\]`) is kept byte-identical in each validator but is not routed through `cfc_parser.py`, so the contract test does not cover it — a latent drift surface worth noting.

---

## Validator

The full CFC ruleset. Severity vocabulary is literally `PASS` / `WARN` / `FAIL`; a result `passed` iff no `FAIL` rows exist (WARNs never flip it). Any FAIL exits `1`; WARNs report *PASSED (with warnings)* and exit `0`.

### Producer (`validate_blueprint.py`, validates `PLAN.md`)

Runs three layers; the cross-artifact layers only fire when CFCs exist or any `[CFC-N]` tag is present anywhere (a cheap substring short-circuit).

**1. Structural validation (FAIL-level)** of each `### CFC-N` entry:

- **Near-miss header** (P6).
- **Malformed CFC number** (leading-zero / zero, per the grammar above).
- **Duplicate CFC numbers** in the document.
- **Missing required field**, **wrong field order**, or a **duplicate field** within an entry.
- **Participating-features value** not matching `^F\d+(, F\d+)*$`, or containing **duplicate IDs**.

**WARN-level structural checks:** empty section (informational); **owner-silent Enforcement** — when Enforcement prose names a mechanism (matches `\b(ArchUnit rule|CI (check|workflow|grep)|integration test|runbook gate|pre-commit hook|ArchUnit)\b`, case-insensitive) but contains no `F<n>` token and no accepted disclaimer (`no owning feature` / `co-owned` / `no single owner` / `no owner`, case-insensitive), the validator warns the author to name `F<n>` so the consumer task-analyst knows whose `tasks.md` to bind.

**2. Coverage walk.** See **§ Bound-spec detection** for the per-feature state model. Per CFC the status is `fully-bound` (PASS row `PLAN.md CFC-N coverage`, detail `fully-bound: F<id>=[<state>], …`), `partially-bound` (WARN row, same name), or `unbound` (**no row at all** — work hasn't started, so suppressing it keeps output quiet). A participant is *covered* iff its spec is approved **and** carries `[CFC-N]` on a THEN line (`tagged-in-flight` or `tagged-shipped`).

**3. Orphan-tag scan (WARN-level).** See **§ Bound-spec detection** → orphan subtypes.

### Consumer (`validate_spec.py`, validates `spec.md` / `tasks.md`)

CFC logic is `validate_cfc_consumer(spec_dir, artifact_content, phase, result)`, invoked from `validate_spec` (`phase="spec"`, after the standard section/GWT/panel checks) and `validate_tasks` (`phase="tasks"`). **`design` has no validator-level CFC check** — design fidelity is panel-side judgement only. The binding signal is always read from `spec.md`, even in the tasks phase. `blueprint/PLAN.md` is located by `find_project_root`, which walks at most two levels up.

**The binding signal (M5):** `PLAN_FEATURE_ID_LINE_RE = re.compile(r"^\*\*PLAN feature identifier:\*\*\s*`(F\d+|n/a)`", re.MULTILINE)`. The value must be a backtick-wrapped `F<n>` or `n/a`; any malformed value degrades to `None` (treated as absent).

**The five-case identifier skip rule (M5 / P7 / Q11):**

1. **Absent or malformed** (`None`) → **FAIL** `spec.md PLAN feature identifier line` (*"…use `n/a` for standalone"*). Return.
2. **`n/a`** → emit Q11 / decision-B WARNs (below); binding checks **always skipped**. Return.
3. **`F<n>` but no PLAN** → **FAIL** `spec.md PLAN feature identifier resolves`. Return.
4. **`F<n>` not in PLAN's `## Feature Breakdown`** (P7 — the resolver scans only the `## Feature Breakdown` body and counts only `^###\s+F(\d+):` headings within it; a `### F99:` elsewhere does not resolve) → **FAIL** `spec.md PLAN feature identifier resolves`. Return.
5. **`F<n>` resolves but PLAN has no CFC section** → return, no checks.

Binding checks run only when the identifier resolves **and** a CFC section exists.

- **Q11 — silent-opt-out guard:** `n/a` + active CFC section → **WARN** `spec.md PLAN feature identifier coherence` (*"…set the identifier to `F<n>`; if standalone is correct, no action needed."*).
- **decision B — `n/a` with stale tags:** `n/a` while `spec.md` still carries `[CFC-N]` THEN-line tags → one **WARN** naming all tags (*"…restore the `F<n>` identifier so binding-checks run, or remove the stale tags."*).

**Spec binding (`phase="spec"`).** For each CFC whose **Participating** list includes this feature: tag present on a THEN line → **PASS** `spec.md carries [CFC-{n}] binding tag`; absent → **FAIL** same name (*"required: `[CFC-{n}]` on a THEN line within **Acceptance Criteria:**"*). A **misplaced tag** (any `[CFC-N]` outside a THEN line) yields a distinct **FAIL** `spec.md [CFC-{n}] tag location` quoting the offending line. Two **mid-stream drift WARNs**: a present tag whose CFC no longer exists, or whose feature is no longer Participating.

**Enforcement task (`phase="tasks"`).** For each CFC whose **Enforcement** prose names this feature (word-boundary `\bF(\d+)\b`): a `[CFC-N]`-tagged checkbox in `tasks.md` (`^[ \t]*-\s+\[[ xX]\]\s+[^\n]*?\[CFC-(\d+)\]`, accepting indented sub-tasks and checked boxes) → **PASS**; absent → **FAIL** `tasks.md carries [CFC-{n}] enforcement task`.

**GWT nuance.** The general AC gate `GWT_PATTERN = re.compile(r"GIVEN\s+.+\n\s*(?:[-*]\s+)?WHEN\s+.+\n\s*(?:[-*]\s+)?THEN\s+.+", re.MULTILINE)` matches three consecutive GIVEN/WHEN/THEN lines, each optionally led by a `- `/`* ` bullet. A **bullet-style** AC (`- GIVEN` / `- WHEN` / `- THEN … [CFC-1]`) therefore both *binds* under the CFC THEN-matcher and *passes* the general gate (the `(?:[-*]\s+)?` groups absorb the bullet). A **true single-line compression** (`WHEN … THEN … [CFC-1]`) is **not** a binding — the line does not start with `THEN`, so it is reported as a misplaced tag and the binding FAILs.

---

## Bound-spec detection

`classify_spec(spec_dir)` classifies each `specs/F<n>/` into exactly **four states**. The state strings are load-bearing — the code mirrors them verbatim, so report output and this doc must stay in sync:

| State | Meaning | Condition |
|---|---|---|
| **`not-started`** | No spec exists | `spec.md` missing |
| **`pre-Phase-1`** | Drafting, not yet approved | `spec.md` exists but its `## Approval` hash is absent / stale / `pending` |
| **`in-flight`** | Spec approved, not yet shipped | `spec.md` approved but not all of `design.md` + `tasks.md` approved-and-ticked |
| **`shipped`** | Phase 4 complete, immutable | all three approved **and** every task ticked **and** `tasks.md`'s stored hash matches current content |

A spec is **bound** precisely when it is `shipped`. Approval requires both a `## Approval` header and the literal `- [x] Approved to proceed` checkbox (matched case-insensitively, `[xX]`) plus a verifying Content Hash.

### Ship signal (Q4 + decision A)

There is **no separate ship-ceremony marker**. Per **Q4**, *the matching hash IS the ship signal*: `shipped` is derived from `all_tasks_ticked(tasks) AND approval_hash_matches(tasks)`. If an author ticks the last box *after* stamping — so the stored hash no longer matches — the feature stays `in-flight` (derived-coherence). Per **decision A**, `shipped` additionally requires **at least one ticked task checkbox**: a narrative-only `tasks.md` with zero checkboxes cannot ship (no implementation work to make immutable). Checkbox counting is scoped to boxes *before* the `## Approval` heading, so the approval marker is never miscounted.

### Per-CFC content-hash sub-block

To detect drift across PLAN re-approvals, the producer stores one structured hash per CFC inside `PLAN.md`'s `## Approval` section:

```
## Approval

- [x] Approved to proceed to feature development
- **Content Hash:** `<document hash>`
- **CFC Content Hashes:**
  - CFC-1: `<64-hex sha256>`
  - CFC-2: `<64-hex sha256>`
```

The block is parsed by `CFC_HASH_BLOCK_HEADER` / `CFC_HASH_LINE` and is rewritten on every `--approve plan` (**before** the document-level Content Hash is computed, so it is part of the approved content). All reads/writes are scoped to the **first** `## Approval` section body (a duplicate `## Approval` header triggers a stderr WARN; only the first is honoured); a re-stamp replaces only CFC-hash-shaped lines, so adjacent user metadata (`- **Reviewer:** Alice`) survives. When a PLAN has no CFCs, any existing block is removed. On the first PLAN approval the prior-hash map is empty.

### Orphan-tag scan (three subtypes)

Each orphan is a **WARN** named `PLAN.md orphan-tag scan: <subtype>` (never a FAIL). Specs in `not-started` / `pre-Phase-1` are skipped (nothing approved to orphan).

- **`orphaned-missing`** — the tag references a CFC number not in the current PLAN. Message names the artifact and offers up to two nearest existing numbers (*"— did you mean CFC-X, CFC-Y?"*).
- **`orphaned-departed`** — the CFC exists but the holder is no longer legitimate. **Membership differs by artifact:** a `spec.md` tag requires Participating membership; a `tasks.md` tag is legitimate for a Participating member **or** an Enforcement owner. Message: *"…F<id> is no longer in CFC-N's Participating features"* (plus *"(and is not named as an Enforcement owner)"* for `tasks.md`).
- **`orphaned-stale-content`** — the CFC exists and the feature is still Participating, but the CFC's `structured_content_hash()` no longer equals the hash recorded at the last PLAN approval. This is the drift detector. Message quotes both 12-char hashes and a state-dependent remediation hint (`shipped` → *"immutable; remediation via new feature or unbound-spec absorption"*; otherwise → *"in flight — amend in place via hash-and-cascade"*). **Never fires until the second PLAN approval** (the baseline is empty on the first).

> **Surfacing on approval.** The orphan/coverage WARNs are surfaced on **both** a plain `validate_blueprint.py blueprint/` run and the `--approve plan` path: on approval they are printed *before* `approve_document` re-stamps the per-CFC content-hash baseline, so drift is surfaced at approval time as intended. (The baseline is overwritten immediately after; that surface-before-overwrite ordering is the actual contract, since once the baseline moves a subsequent plain `validate` can no longer re-detect the same drift.)

---

## Domain-Ignorance in CFC Authoring

> **Reconstruction.** These are post-implementation **field observations** of how CFCs were mis-authored by an LLM lacking domain context. Each surviving entry drives a synthesizer self-check in `references/panel-review.md`; the OBSERVED self-check text is quoted, the per-error framing reconstructed. Only errors **#1, #2, #5** are cited anywhere in the repo (by `panel-review.md`); the original numbering is preserved so those citations stay accurate — **#3 and #4 have no surviving reference and their content was not recovered.**

1. **Class-vs-package scope mismatch** — *catches Self-Check (f), "Enforcement scope alignment".* The `Contract` commits a *class*-scoped invariant ("no class outside `com.foo.bar.Baz`") while the `Enforcement` mechanism is *package*-scoped (a grep/ArchUnit rule over `com.foo.bar..`), or vice versa — so the verifying artifact does not actually verify the stated rule. Remedy: quote both scope-nouns and reconcile them to the same scope.

2. **Counter-vs-publisher (wrong-registry) conflation** — *catches Self-Check (f), "Seed/registry traceability".* A registry is seeded with entries of the wrong *code-shape* — e.g. Micrometer counter names placed into a `publisher.publish(literal)` registry, or FQCNs / env-var names / SQL identifiers mixed together. Different code-shapes belong in different registries. Remedy: trace each seeded entry to its source code-shape and quote the source AC.

3. *(reserved — not referenced anywhere in the repo; content not recovered.)*

4. *(reserved — not referenced anywhere in the repo; content not recovered.)*

5. **Forward-feature seed coupling** — *catches Self-Check (f), "Seed/registry traceability".* A CFC's registry is seeded with key text drawn from a feature `F<m>` that ships *after* the seeding feature `F<n>` — a forward dependency the early feature cannot satisfy. The seed is really a coordination requirement. Remedy — the **CFC-3 precedent**: seed an *empty* registry; each feature adds its own key at its own merge.

A companion discipline — Self-Check (b)'s **symmetric application** ("apply the same source-check to every other item in a list before archiving") — is recorded as the **v2 acceptance-test residual finding**: even after per-claim verbatim quoting, the residual error was rigorous evidence for the items the synthesizer questioned and casual acceptance of the items it didn't.

---

## Deferred to v2

v1 deliberately stops at **detection**. Out of v1 scope:

- **The cascade machinery (`cfc_consistency.py`).** v1 ships only the shared *parser* layer; the cross-document consistency/cascade engine that would propagate a CFC edit across every bound spec is deferred. The parser was split out (decision C) precisely so producer and consumer cannot drift on file format while the cascade layer waits.
- **Interactive remediation prompts.** When `orphaned-stale-content` fires, v1 prints a WARN; it does not walk the user through a remediation choice.
- **Validator-driven scaffolding.** v1 does not auto-generate a remediation feature. Remediation is **author-driven**: read the WARN and apply one of three paths by hand — a new amending feature, folding into an in-flight unbound spec, or an `## Accepted Divergences` entry on the shipped spec.
- **Per-artifact structured-content hash** that would mechanically distinguish a typo fix from a substantive amendment on a shipped spec. v1 detects the *consequence* (orphan-tag drift on a re-stamped spec), not the immutability violation directly.

---

## Decision log

Decision IDs are cited as rationale comments throughout the code. They fall into families: **M-series** mechanism choices, **Q-series** resolved open questions, **lettered** post-implementation doctrine refinements, and a **P-series** post-implementation code-review refinement log. The CFC-cited IDs:

| ID | Title | What it commits |
|---|---|---|
| **M2** | Whole-number / word-boundary matching | `[CFC-1]` must not match inside `[CFC-10]`; `F1` must not match inside `F11`. Tags compare the captured integer; feature IDs use `\bF(\d+)\b`. |
| **M5 / P7** | Identifier-line skip rule (five cases) | Consumer keys off the `**PLAN feature identifier:**` line; M5 defines the binding signal, P7 refines it into the five enumerated cases (incl. resolution scoped to `## Feature Breakdown`). |
| **P6** | Silent-extractor-failure guard | A near-miss `## Cross-Feature Contracts` header FAILs instead of making the whole section parse as absent. |
| **Q4** | Derived-coherence ship signal | "shipped" is derived (all approved + all ticked + `tasks.md` hash matches); the matching hash *is* the ship signal — no ceremony marker. A stale stamp after a late tick keeps the feature in-flight. |
| **Q11** | Silent-opt-out guard | `n/a` identifier while PLAN has an active CFC section → WARN. |
| **decision A** | No vacuous ship | A narrative-only `tasks.md` (zero checkboxes) cannot be "shipped" even when fully approved. |
| **decision B** | `n/a` + stale tags | `n/a` identifier while `spec.md` still carries `[CFC-N]` THEN-line tags → per-tag WARN. |
| **decision C** | Shared parser + symmetry test | One parser module owns all regexes and `CFCEntry`; `test_cfc_parser_contract.py` locks producer/consumer symmetry. From an architect-A1 / code-quality-P1 review finding. |
| **decision E** | Approve gates on validation | `--approve` refuses to stamp a document whose validation FAILs (prints `Refusing to approve …: validation FAILed.`, exits non-zero) unless `--force` is passed. |

**P-series refinement log (code-local provenance, not separate anchors).** The post-implementation code review produced fine-grained refinements cited bare in comments — e.g. `P1-9` (use `[ \t]*` not `\s*` after the field marker), `P2-3` (misplaced-tag distinct diagnostic), `P2-4` (fenced-code THEN ignored), `P2-5` (THEN word-boundary), `P2-6` (indented sub-task checkboxes), `P2-7` (cheap substring short-circuit), `P2-9` (sort+dedupe participating before hashing), `P3-6` (indented header still flagged), `P3-8` (tightened `Approved to proceed` checkbox), `P3-9`/`P3-10` (rename `bound` → `tagged-in-flight`/`tagged-shipped`), `P3-12` (leading-zero/zero CFC-number reject), `P1-1`–`P1-5` (approval-section scoping). These are not cited as `CFC.md <id>` and need no anchor here; they are listed so a maintainer reading a bare `# P2-9` comment can locate the rationale.

---

## Test-case catalog

The test files cite "CFC.md test N" against a conceptual numbered matrix (`test_cfc_validation.py` covers 1–30; `test_cfc_consumer.py` covers the consumer cases). The cases referenced by number:

| Test(s) | Concern |
|---|---|
| 1–3, 17–19 | Producer section parsing + field validation (order, duplicates, missing) |
| 5, 6, 8 | Consumer spec `[CFC-N]` THEN-tag presence |
| 9, 16 | Whole-number tag matching / M2 prefix-collision (`[CFC-1]` ≠ `[CFC-10]`) |
| 11 | Mid-stream drift WARN (tag no longer resolves) |
| 13 | Owner-silent Enforcement WARN |
| 14 | `n/a` + active CFC section opt-out WARN (Q11) |
| 15 | Coverage walk + orphan-tag scan / `tasks.md` enforcement-task tag |
| 20 | Word-boundary feature-ID matching (`F1` not inside `F11`) |
| 21 | Per-CFC structured content hashing |
| 26 | Bound-spec classification incl. derived-coherence (ticked-without-restamp stays in-flight) |
| 27 | Content-hash stability: reorder/dedupe stable, substantive edit changes hash |

Unreferenced numbers in 1–30 are additional producer parse/field cases exercised by `test_cfc_validation.py` without an individual prose citation.
