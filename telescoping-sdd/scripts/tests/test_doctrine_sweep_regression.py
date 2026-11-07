"""Unit D (T32): persistent doctrine sweep-regression tripwire (R1, R5, R7).

A tripwire heuristic, not a proof: it catches reintroduced phrasing, not
every paraphrase. It runs the widened sweep patterns (design Testing
Strategy § Sweeps) over both tiers' `SKILL.md` and `references/*.md` plus
`README.md`, and for each match checks its *unit*:

- inside `panel-review-modes.md` § Lightweight Mode, an R7 match's unit is
  the whole section;
- a match on a top-level numbered step, or in one of its indented
  sub-paragraphs, has the whole step as its unit;
- otherwise a list item (with its deeper-indented lines), a fenced block,
  or a blank-line-delimited paragraph.

The unit must carry a tier-home pointer or an allowed-context phrase, or the
match must sit inside a reviewed exemption sentence (pinned verbatim below,
so an exemption cannot outlive the text it excuses), or inside one of the
three tier-home sections themselves, which state the rule rather than point
at it. R1 is also checked at clause level: a match's own sentence may not
assert that in-loop fixes are orchestrator-direct.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SKILLS = _REPO / "telescoping-sdd" / "skills"
_TIER_DIR = {"sdd": "spec-driven-dev", "blueprint": "project-blueprint"}


def _swept_files() -> list[Path]:
    out: list[Path] = []
    for d in _TIER_DIR.values():
        out.append(_SKILLS / d / "SKILL.md")
        out.extend(sorted((_SKILLS / d / "references").glob("*.md")))
    out.append(_REPO / "README.md")
    return out


SWEPT_FILES = _swept_files()


def _rel(p: Path) -> str:
    return p.relative_to(_REPO).as_posix()


# Widened sweep patterns (case-insensitive substrings).
SWEEPS = {
    "R1": ["orchestrator-direct", "orchestrator directly", "applied by the orchestrator",
           "apply the fix to the artifact", "in-loop per-concern", "not delegated to an analyst",
           "having applied", "stays orchestrator-direct", "apply the fix and re-run the checklist",
           "fix you applied", "fixes you applied", "apply the resolution"],
    "R5": ["three panelists", "three-persona", "3 persona", "all three", "three personas",
           "3 panelists", "three agent", "× 3 persona"],
    "R7": ["opt-in only", "opts in", "opts into", "never auto-selected", "lightweight mode",
           "the user may opt into", "user opts into", "ask for a lighter review",
           "load it only when"],
}

TIER_HOME_POINTERS = ("§ Applying a pass's fixes", "§ Tapered roster", "§ Rigour posture")
ALLOWED_CONTEXT = ("out-of-loop", "a loop's first", "full roster",
                   "persisted posture is `vibe`", "user-directed fix (SEAL-08)")
# The tier homes themselves (panel-review.md sections): they state the rule.
HOME_SECTIONS = ("## Applying a pass's fixes", "## Tapered roster", "## Rigour posture")
LIGHTWEIGHT_HEADING = "## Lightweight Mode (single-pass panel)"

_SDD = "telescoping-sdd/skills/spec-driven-dev/"
_BP = "telescoping-sdd/skills/project-blueprint/"
_BOTH = (_SDD, _BP)


@dataclass(frozen=True)
class Exemption:
    file: str
    sentence: str
    reason: str


def _both(rel: str, sentence: str, reason: str) -> list[Exemption]:
    return [Exemption(t + rel, sentence, reason) for t in _BOTH]


_LW_OPENING_HEAD = ("The default loop — drafting subagent (≤5 self-review passes) plus a ≤5-pass "
                    "convergence panel of three personas, with strict-bar, halt-and-rescope, and "
                    "the exit cross-check layered on — is calibrated for **substantial, "
                    "long-lived, multi-feature work**: ")

# The reviewed exemption list: the design's three step-1 entries plus one
# entry per "pinned exemption in T32" row of the sweep-ownership table.
EXEMPTIONS: list[Exemption] = [
    # Design Testing Strategy: step 1 (panel-review.md:64), kept verbatim
    # because the step-1 extracts anchor on it; the unit carries the taper
    # sentence after the bold lead.
    *_both("references/panel-review.md",
           "1. **Dispatch all three panelists in a single message.**",
           "step 1 bold lead, anchored on verbatim by the step-1 extracts"),
    *_both("references/panel-review.md",
           "If you find yourself reading Panelist 1's output before Panelist 2 and 3 are "
           "invoked, you've serialized; abort and re-dispatch all three at once.",
           "step 1 parallel-dispatch rule; 'all three' means every seat on the roster"),
    *_both("references/panel-review.md",
           "Issue three Agent tool calls in the same response block — not three separate "
           "responses with waits between them.",
           "step 1 parallel-dispatch rule on a full-roster pass"),
    # R1: out-of-loop backport triviality carve-out, unchanged by R1.
    *_both("references/hash-and-cascade.md",
           "A trivial backport (typo, rename, single-sentence reword — no behavior change) "
           "stays orchestrator-direct per the existing triviality carve-out; a substantial one "
           "supplies the delegation brief and runs the scope-verify + content-preservation "
           "check before *Re-Approval After Edits* runs (both are defined in § \"Revise the "
           "downstream\" — Substantial, above).",
           "out-of-loop triviality carve-out, kept unchanged by R1"),
    # R1: scoped late pass evidence condition. An evidence-preload rule for
    # the next pass's dispatch, not a fix-routing claim; "already holds" is
    # pinned by test_plan_driven_thin_spec.py. Judgement call: "having
    # applied the fixes" reads slightly stale now the drafter applies them.
    *_both("references/panel-review-modes.md",
           "**Evidence condition.** The orchestrator may pre-load evidence it **already "
           "holds** from having applied the fixes — supplying evidence is structural (it is "
           "context), not behavioural (it is not depth).",
           "evidence-preload rule, not a fix-routing claim"),
    # R5: counts regression classes, not panelists.
    *_both("references/panel-review.md",
           "Self-check would have caught all three at synthesizer time.",
           "'all three' counts regression classes"),
    # R5: substring false positive ("Phase-3 panelists").
    Exemption(_BP + "references/panel-review.md",
              "**Why this exists:** Phase-3 panelists routinely propose edits to feature rows "
              "when they spot a binding obligation (e.g., a CFC's per-feature AC that names "
              "F<n>), without checking F<n>'s milestone state.",
              "substring false positive: 'Phase-3 panelists' matches '3 panelists'"),
    # R5: § Lightweight Mode opening describes the default loop's panel.
    Exemption(_SDD + "references/panel-review-modes.md",
              _LW_OPENING_HEAD + "artifacts other features will build against, that will be "
              "re-entered and amended, where a missed contradiction or untestable AC is "
              "expensive to discover late.",
              "describes the default loop's three-persona panel, in contrast to lightweight mode"),
    Exemption(_BP + "references/panel-review-modes.md",
              _LW_OPENING_HEAD + "a blueprint other people will build a whole project against, "
              "that will be re-entered and amended, where a missed contradiction or unmet goal "
              "is expensive to discover late.",
              "describes the default loop's three-persona panel, in contrast to lightweight mode"),
    # R5: a lightweight pass is a loop's first and only pass (full roster).
    *_both("references/panel-review-modes.md",
           "Run **one** NORMAL panel pass exactly as `## The Loop` steps 1–4 describe — same "
           "three panelists, dispatched together, synthesized in-thread, each concern disposed "
           "(`Addressed` / `Deferred → <target>` / `Sealed` / `Accepted as risk` / `User input "
           "needed`), every row written to `### Latest pass detail`.",
           "a lightweight pass is a loop's first and only pass, so it runs the full roster"),
    # R5: counts carve-out actions.
    Exemption(_SDD + "references/hash-and-cascade.md",
              "All three actions are explicit — the new step's suppression is named directly "
              "here so a future text edit cannot accidentally drop it by re-ordering.",
              "'all three' counts carve-out actions"),
    # R5: counts phase artifacts; also pinned by test_cli_integration.py.
    Exemption(_BP + "SKILL.md",
              "If all three phase artifacts (SCOPE.md, ARCHITECTURE.md, PLAN.md) are already "
              "approved on entry, offer the Phase 4 prompt directly rather than re-entering "
              "Phase 1.",
              "'all three' counts phase artifacts"),
    # R5: counts documents.
    Exemption(_BP + "references/examples.md",
              "Verify all three documents exist and are approved",
              "'all three' counts documents"),
    # R5: counts upstream artifacts.
    Exemption(_BP + "references/phase-business-brief.md",
              "Before any rendering work, the script verifies all three upstream artifacts are "
              "present, approved (checkbox ticked), and have a content hash matching their "
              "current content.",
              "'all three' counts upstream artifacts"),
    # R7: file-locator sentence (where the mode lives), not a selection
    # trigger; the blueprint keeps it (the SDD copy was cut for budget).
    Exemption(_BP + "SKILL.md",
              "The situational modes load on demand from two siblings: strict-bar convergence "
              "and halt-and-rescope exit in `references/panel-review-convergence.md`, and "
              "lightweight mode, panel skip, and gate change requests in "
              "`references/panel-review-modes.md`.**",
              "file-locator sentence, not a lightweight-mode selection trigger"),
    # R7: the convergence sibling's load trigger, unrelated to Lightweight Mode.
    *_both("references/panel-review-convergence.md",
           "Load it only when a convergence trigger fires: `archive_pass.py` emits a "
           "`STRICT-BAR-SIGNAL:` advisory, or an `[upstream]` tag / two consecutive halt votes "
           "appear.",
           "convergence load trigger, unrelated to Lightweight Mode"),
    # R7: scope note on the priced-edit rule; pinned by
    # test_severity_and_exit_predicate.py.
    *_both("references/panel-review.md",
           "The 5-pass cap gate is **not** a convergence exit — it is the user electing to "
           "move on with unresolved HIGHs outstanding — so the priced-edit rule does not apply "
           "to it, and neither does it apply to `panel-review-modes.md`'s lightweight mode, "
           "where the loop is switched off after a single pass.",
           "scope note on the priced-edit rule, not a selection trigger"),
]

PREAMBLE_VIBE = ("Load it only when: the user opts into a single-pass review (lightweight mode) "
                 "or the project's persisted posture is `vibe` (`panel-review.md` § Rigour "
                 "posture),")

# A clause asserting that in-loop / per-concern fixes are orchestrator-applied.
_R1_CLAIM_SUBJECT = re.compile(r"in-loop|per-concern", re.I)
_R1_CLAIM_VERB = re.compile(
    r"orchestrator-direct|orchestrator directly|applied by the orchestrator|"
    r"not delegated to an analyst", re.I)


# --------------------------------------------------------------------------- #
# Sweep engine (pure functions over text, so a planted text can be checked)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Match:
    file: str
    sweep: str
    pattern: str
    line: int          # 1-based
    offset: int        # absolute char offset in the file text
    unit: str
    in_home: bool


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _section_bounds(lines: list[str], i: int) -> tuple[int, int, str]:
    h = next((k for k in range(i, -1, -1) if lines[k].startswith("## ")), -1)
    head = lines[h] if h >= 0 else ""
    e = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
    return max(h, 0), e - 1, head


def _unit_bounds(lines: list[str], i: int, rel: str, sweep: str) -> tuple[int, int]:
    fences = [k for k, l in enumerate(lines) if l.lstrip().startswith("```")]
    for a, b in zip(fences[::2], fences[1::2]):
        if a <= i <= b:
            return a, b
    if sweep == "R7" and rel.endswith("panel-review-modes.md"):
        a, b, head = _section_bounds(lines, i)
        if head == LIGHTWEIGHT_HEADING:
            return a, b
    step = None
    if re.match(r"^\d+\. ", lines[i]):
        step = i
    elif lines[i].strip() and _indent(lines[i]) > 0:
        k = next((k for k in range(i - 1, -1, -1)
                  if lines[k].strip() and _indent(lines[k]) == 0), None)
        if k is not None and re.match(r"^\d+\. ", lines[k]):
            step = k
    if step is not None:
        e = step + 1
        while e < len(lines) and (not lines[e].strip() or _indent(lines[e]) > 0):
            e += 1
        while e - 1 > step and not lines[e - 1].strip():
            e -= 1
        return step, e - 1
    m = re.match(r"^(\s*)(?:[-*] |\d+\. )", lines[i])
    if m:
        ind, e = len(m.group(1)), i + 1
        while e < len(lines) and lines[e].strip() and _indent(lines[e]) > ind:
            e += 1
        return i, e - 1
    a = i
    while a > 0 and lines[a - 1].strip():
        a -= 1
    b = i
    while b < len(lines) - 1 and lines[b + 1].strip():
        b += 1
    return a, b


def sweep_text(rel: str, text: str) -> list[Match]:
    lines = text.split("\n")
    starts, pos = [], 0
    for l in lines:
        starts.append(pos)
        pos += len(l) + 1
    out: list[Match] = []
    is_panel_review = rel.endswith("references/panel-review.md")
    for i, line in enumerate(lines):
        low = line.lower()
        for sweep, pats in SWEEPS.items():
            for pat in pats:
                j = low.find(pat)
                while j != -1:
                    a, b = _unit_bounds(lines, i, rel, sweep)
                    _sa, _sb, head = _section_bounds(lines, i)
                    out.append(Match(rel, sweep, pat, i + 1, starts[i] + j,
                                     "\n".join(lines[a:b + 1]),
                                     is_panel_review and head in HOME_SECTIONS))
                    j = low.find(pat, j + len(pat))
    return out


def _exemption_spans(rel: str, text: str, exemptions=EXEMPTIONS) -> list[tuple[int, int]]:
    spans = []
    for ex in exemptions:
        if ex.file != rel:
            continue
        k = text.find(ex.sentence)
        while k != -1:
            spans.append((k, k + len(ex.sentence)))
            k = text.find(ex.sentence, k + 1)
    return spans


def _exempt(m: Match, spans) -> bool:
    return any(a <= m.offset and m.offset + len(m.pattern) <= b for a, b in spans)


def _carries_context(unit: str) -> bool:
    return any(p in unit for p in TIER_HOME_POINTERS + ALLOWED_CONTEXT)


def unit_failures(rel: str, text: str, sweep: str, exemptions=EXEMPTIONS) -> list[str]:
    spans = _exemption_spans(rel, text, exemptions)
    return [f"{m.file}:{m.line} [{m.pattern}]"
            for m in sweep_text(rel, text)
            if m.sweep == sweep and not m.in_home and not _exempt(m, spans)
            and not _carries_context(m.unit)]


_SENT_END = re.compile(r"[.!?](?=\s+[A-Z*`(\"])")


def _sentence_at(text: str, offset: int) -> str:
    """The sentence holding `offset`, bounded by its line (paragraphs are
    single lines in these files) and by `.`/`!`/`?` before a capital-ish
    start."""
    a = max(text.rfind("\n", 0, offset), 0)
    starts = [a] + [a + mm.end() for mm in _SENT_END.finditer(text[a:offset])]
    s = starts[-1]
    nl = text.find("\n", offset)
    nl = len(text) if nl == -1 else nl
    end_m = re.search(r"[.!?](?=\s+[A-Z*`(\"]|\s*$)", text[offset:nl])
    e = offset + end_m.end() if end_m else nl
    return text[s:e].strip()


def r1_claim_sentences(rel: str, text: str) -> list[str]:
    bad = []
    for m in sweep_text(rel, text):
        if m.sweep != "R1":
            continue
        sentence = _sentence_at(text, m.offset)
        for clause in re.split(r";|—", sentence):
            if (_R1_CLAIM_SUBJECT.search(clause) and _R1_CLAIM_VERB.search(clause)
                    and "out-of-loop" not in clause):
                bad.append(f"{m.file}:{m.line}: {clause.strip()[:160]}")
    return bad


def _texts() -> dict[str, str]:
    return {_rel(p): p.read_text(encoding="utf-8") for p in SWEPT_FILES}


_FILE_IDS = [_rel(p) for p in SWEPT_FILES]


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rel", _FILE_IDS)
def test_r1_sweep_matches_point_or_are_out_of_loop(rel):
    assert unit_failures(rel, _texts()[rel], "R1") == []


@pytest.mark.parametrize("rel", _FILE_IDS)
def test_r1_match_sentence_never_restates_carve_out(rel):
    assert r1_claim_sentences(rel, _texts()[rel]) == []


@pytest.mark.parametrize("rel", _FILE_IDS)
def test_r5_sweep_matches_point_or_describe_full_roster(rel):
    assert unit_failures(rel, _texts()[rel], "R5") == []


@pytest.mark.parametrize("rel", _FILE_IDS)
def test_r7_sweep_matches_name_persisted_vibe(rel):
    assert unit_failures(rel, _texts()[rel], "R7") == []


def _lightweight_section(text: str) -> str:
    i = text.index(LIGHTWEIGHT_HEADING)
    j = text.find("\n## ", i + 1)
    return text[i:] if j == -1 else text[i:j]


@pytest.mark.parametrize("tier", sorted(_TIER_DIR))
def test_lightweight_mode_section_carries_vibe_pointer_at_least_once(tier):
    p = _SKILLS / _TIER_DIR[tier] / "references" / "panel-review-modes.md"
    assert "persisted posture is `vibe`" in _lightweight_section(p.read_text(encoding="utf-8"))


@pytest.mark.parametrize("tier", sorted(_TIER_DIR))
def test_modes_preamble_trigger_names_persisted_vibe(tier):
    p = _SKILLS / _TIER_DIR[tier] / "references" / "panel-review-modes.md"
    text = p.read_text(encoding="utf-8")
    preamble = text[:text.index(LIGHTWEIGHT_HEADING)]
    trigger = next(l for l in preamble.split("\n") if l.startswith("> **Loaded on demand.**"))
    assert PREAMBLE_VIBE in trigger


@pytest.mark.parametrize("ex", EXEMPTIONS, ids=lambda e: f"{e.file}:{e.sentence[:40]}")
def test_exemption_entries_still_occur_verbatim(ex):
    text = (_REPO / ex.file).read_text(encoding="utf-8")
    assert ex.sentence in text, f"stale exemption in {ex.file}: {ex.reason}"
    assert ex.reason
    # Each entry must excuse at least one sweep match, or it is dead weight.
    spans = _exemption_spans(ex.file, text, [ex])
    assert any(_exempt(m, spans) for m in sweep_text(ex.file, text)), ex.sentence[:60]


def test_tripwire_catches_planted_reintroduction():
    texts = _texts()
    # R1: the old workflow-overview carve-out sentence, planted back.
    wo = _SDD + "references/workflow-overview.md"
    planted = texts[wo] + (
        "\n\nA *substantive in-loop per-concern fix* during an active panel pass stays "
        "orchestrator-direct (the next pass of the same loop re-reviews it).\n")
    assert unit_failures(wo, planted, "R1")
    assert r1_claim_sentences(wo, planted)
    # R1 sentence check is not excused by a pointer elsewhere in the unit.
    pr = _SDD + "references/panel-review.md"
    planted = texts[pr].replace(
        "1. **Dispatch all three panelists in a single message.**",
        "1. **Dispatch all three panelists in a single message.** In-loop per-concern fixes "
        "are applied by the orchestrator directly.", 1)
    assert r1_claim_sentences(pr, planted)
    # R5: a bare three-panelist claim in a new paragraph.
    sk = _SDD + "SKILL.md"
    planted = texts[sk] + "\n\nEvery pass dispatches three panelists.\n"
    assert unit_failures(sk, planted, "R5")
    # R7: the old opt-in-only rule, planted back into SKILL.md.
    planted = texts[sk] + "\n\nDefault stays the full loop; lightweight mode is opt-in only.\n"
    assert unit_failures(sk, planted, "R7")
    # An exemption whose sentence is edited no longer excuses its match.
    bp_skill = _BP + "SKILL.md"
    edited = texts[bp_skill].replace("If all three phase artifacts", "If all three artifacts", 1)
    assert unit_failures(bp_skill, edited, "R5")
