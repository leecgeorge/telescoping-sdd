"""Unit F — hash basis v3 (spec `unit-f-hash-basis-v3`).

This module grows task by task. T2 adds the structural half of AD3: a closure
check proving the frozen v2 block (`content_hash._content_for_hashing_v2_frozen`
/ `compute_content_hash_v2`) reaches nothing but its own `_v2_*` / `_V2_*`
copies and the stdlib `re` / `hashlib`, so no later edit to a shared helper can
move a v2 hash (AC-2.2). Every check is a function over a module or a source
string, so each one runs both on the real block and on a deliberately
contaminated positive-control sample.
"""
from __future__ import annotations

import ast
import builtins
import dis
import hashlib
import inspect
import re
import sys
import types
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _p in (str(_SCRIPTS), str(_TESTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import content_hash as ch  # noqa: E402
import trajectory as tr  # noqa: E402


# ---------------------------------------------------------------------------
# AD3 structural checks (T2)
# ---------------------------------------------------------------------------

V2_ENTRY_POINTS = ("compute_content_hash_v2", "_content_for_hashing_v2_frozen")
_STDLIB_OK = {"re": re, "hashlib": hashlib}
# Builtins a frozen function may name (design SEAL-23). Anything that can reach
# another module or rebind a name — __import__, eval, exec, getattr, globals,
# vars, compile, open — is deliberately absent.
BUILTINS_ALLOWLIST = frozenset({"enumerate", "range", "len"})
_BANNED_NODE_TYPES = (
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
)


def _is_frozen_name(name: str) -> bool:
    return name.startswith(("_v2_", "_V2_")) or name in V2_ENTRY_POINTS


def _frozen_functions(module) -> list:
    """Every frozen function reachable from the module's v2 entry points (or,
    for a sample module without them, every `_v2_*` function it defines)."""
    roots = [getattr(module, n) for n in V2_ENTRY_POINTS if hasattr(module, n)]
    if not roots:
        roots = [v for k, v in vars(module).items()
                 if k.startswith("_v2_") and inspect.isfunction(v)]
    seen, stack = [], list(roots)
    while stack:
        fn = stack.pop()
        if fn in seen:
            continue
        seen.append(fn)
        for name, val in inspect.getclosurevars(fn).globals.items():
            if inspect.isfunction(val) and _is_frozen_name(name):
                stack.append(val)
    return seen


def closure_global_violations(module) -> list:
    bad = []
    for fn in _frozen_functions(module):
        for name, val in inspect.getclosurevars(fn).globals.items():
            if _is_frozen_name(name):
                continue
            if name in _STDLIB_OK and val is _STDLIB_OK[name]:
                continue
            bad.append(f"{fn.__name__} -> {name}")
    return bad


def nested_code_violations(module) -> list:
    return [fn.__name__ for fn in _frozen_functions(module)
            if any(isinstance(c, types.CodeType) for c in fn.__code__.co_consts)]


def import_name_violations(module) -> list:
    return [fn.__name__ for fn in _frozen_functions(module)
            if any(i.opname == "IMPORT_NAME" for i in dis.get_instructions(fn))]


def builtins_violations(module) -> list:
    bad = []
    for fn in _frozen_functions(module):
        for name in inspect.getclosurevars(fn).builtins:
            if name not in BUILTINS_ALLOWLIST:
                bad.append(f"{fn.__name__} -> {name}")
    return bad


def _is_re_flags(node) -> bool:
    if isinstance(node, ast.Attribute):
        return isinstance(node.value, ast.Name) and node.value.id == "re"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _is_re_flags(node.left) and _is_re_flags(node.right)
    return False


def _is_literal_rhs(node) -> bool:
    if isinstance(node, ast.Constant) and type(node.value) in (str, int):
        return True
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"
            and node.func.attr == "compile" and not node.keywords
            and 1 <= len(node.args) <= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)):
        return len(node.args) == 1 or _is_re_flags(node.args[1])
    return False


def _target_names(target) -> list:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for elt in target.elts for n in _target_names(elt)]
    return []


def ast_violations(source: str) -> list:
    """The AD3 AST pass over a module source (DM3)."""
    bad = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                if _is_frozen_name(bound):
                    bad.append(f"import binds {bound}")
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            for n in _target_names(node.target):
                if _is_frozen_name(n):
                    bad.append(f"{type(node).__name__} binds {n}")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, (ast.Tuple, ast.List)):
                    for n in _target_names(target):
                        if _is_frozen_name(n):
                            bad.append(f"tuple-target binds {n}")
                elif (isinstance(target, ast.Name) and target.id.startswith("_V2_")
                        and not _is_literal_rhs(node.value)):
                    bad.append(f"non-literal RHS for {target.id}")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_frozen_name(node.name):
            if node.args.defaults or any(d is not None for d in node.args.kw_defaults):
                bad.append(f"{node.name} has defaults")
            for inner in ast.walk(node):
                if inner is not node and isinstance(inner, _BANNED_NODE_TYPES):
                    bad.append(f"{node.name} contains {type(inner).__name__}")
    return bad


def _sample_module(source: str):
    """Exec a contaminated sample as its own module, with shared names to reach."""
    mod = types.ModuleType("_v2_sample")
    mod.__dict__.update({
        "re": re, "hashlib": hashlib, "trajectory": tr,
        "SHARED": tr.TRAJECTORY_SEP_RE, "SHARED_A": 1, "SHARED_B": 2,
    })
    exec(compile(source, "<v2-sample>", "exec"), mod.__dict__)
    return mod


def _frozen_block_source() -> str:
    src = Path(ch.__file__).read_text(encoding="utf-8")
    start = src.index("# ----- FROZEN v2 basis")
    end = src.index("def compute_content_hash(content")
    return src[start:end]


# --- the real frozen block --------------------------------------------------


def test_v2_closure_globals_prefixed_or_allowlisted():
    fns = {f.__name__ for f in _frozen_functions(ch)}
    # The walk really reaches the helpers (not vacuously the two entry points).
    assert {"_v2_strip_trajectory_rows", "_v2_panel_trajectory_header_idx",
            "_v2_neutralize_milestone_state"} <= fns
    assert closure_global_violations(ch) == []


def test_v2_closure_no_nested_code_objects():
    assert nested_code_violations(ch) == []


def test_v2_closure_no_import_name_bytecode():
    assert import_name_violations(ch) == []


def test_v2_closure_ast_bans():
    assert ast_violations(Path(ch.__file__).read_text(encoding="utf-8")) == []


def test_v2_closure_builtins_allowlist():
    assert builtins_violations(ch) == []
    assert not {"__import__", "eval", "exec", "getattr", "globals", "vars"} & BUILTINS_ALLOWLIST


# --- positive controls: every check fires on a contaminated sample -----------


def _flagged_by_module_checks(source: str) -> list:
    mod = _sample_module(source)
    return (closure_global_violations(mod) + nested_code_violations(mod)
            + import_name_violations(mod) + builtins_violations(mod))


_POSITIVE_CONTROLS = {
    # The seven AD3 samples.
    "shared_attribute": ("module", "def _v2_f(line):\n    return trajectory.TRAJECTORY_SEP_RE.match(line)\n"),
    "local_import": ("module", "def _v2_f(line):\n    import trajectory\n    return line\n"),
    "compile_shared": ("ast", "_V2_X = re.compile(SHARED)\n"),
    "import_alias": ("ast", "from trajectory import TRAJECTORY_SEP_RE as _V2_SEP\n"),
    "tuple_target": ("ast", "_V2_A, _V2_B = SHARED_A, SHARED_B\n"),
    "annotated": ("ast", "_V2_X: object = SHARED\n"),
    "default_arg": ("ast", "def _v2_f(line, sep=SHARED):\n    return sep.match(line)\n"),
    # The four remaining-ban samples (pass-3 panel fix).
    "nested_def_and_lambda": ("ast", "def _v2_f(line):\n    def g():\n        return line\n    h = lambda: line\n    return g() + h()\n"),
    "list_comprehension": ("ast", "def _v2_f(lines):\n    return [x for x in lines]\n"),
    "builtin_escape": ("module", "def _v2_f(line):\n    return getattr(__import__('trajectory'), 'TRAJECTORY_SEP_RE')\n"),
    "aug_assign": ("ast", "_V2_X = 1\n_V2_X += 1\n"),
}


@pytest.mark.parametrize("name", sorted(_POSITIVE_CONTROLS))
def test_v2_closure_positive_controls(name):
    kind, source = _POSITIVE_CONTROLS[name]
    flagged = ast_violations(source) if kind == "ast" else _flagged_by_module_checks(source)
    assert flagged, f"contaminated sample {name!r} was not flagged"


def test_v2_closure_positive_control_nested_code_object():
    """The co_consts ban itself fires: a nested def compiles to a nested code
    object on every supported version."""
    mod = _sample_module(_POSITIVE_CONTROLS["nested_def_and_lambda"][1])
    assert nested_code_violations(mod) == ["_v2_f"]


def test_v2_closure_list_comprehension_flagged_by_ast_on_every_version():
    """AC-2.2: the comprehension ban must not rely on co_consts, which 3.12+
    inline (PEP 709); the AST pass flags it the same way on 3.10/3.12/3.13."""
    flagged = ast_violations(_POSITIVE_CONTROLS["list_comprehension"][1])
    assert flagged == ["_v2_f contains ListComp"]


def test_v2_closure_real_block_contamination_control():
    """Design SEAL-13: the real frozen block with ONE `_V2_*` literal swapped
    for a shared name is flagged."""
    block = _frozen_block_source()
    literal = '_V2_TRAJECTORY_HEADER = "### Trajectory"'
    assert literal in block
    assert ast_violations(block) == []
    contaminated = block.replace(literal, "_V2_TRAJECTORY_HEADER = TRAJECTORY_HEADER")
    assert ast_violations(contaminated) == ["non-literal RHS for _V2_TRAJECTORY_HEADER"]


# ---------------------------------------------------------------------------
# AD3 behavioural half (T3): monkeypatch sweep, vacuity control, completeness
# ---------------------------------------------------------------------------

from _fixtures import AC_2_1_FIXTURE, AC_2_1_GOLDEN  # noqa: E402

_GOLDEN_HASH = hashlib.sha256(AC_2_1_GOLDEN.encode("utf-8")).hexdigest()[:16]


class _RecordingProxy:
    """Delegating proxy for a compiled regex that records method calls."""

    def __init__(self, real):
        self._real = real
        self.calls = 0

    def __getattr__(self, attr):
        target = getattr(self._real, attr)
        if callable(target):
            def _rec(*a, **k):
                self.calls += 1
                return target(*a, **k)
            return _rec
        return target


def _recording_wrapper(real):
    def _wrap(*a, **k):
        _wrap.calls += 1
        return real(*a, **k)
    _wrap.calls = 0
    return _wrap


# (shared name, module attr holding it, kind, live?) — the AD3 sweep binding
# sites table, v2-path rows. "live" = compute_content_hash on AC_2_1_FIXTURE
# looks the name up at that site. T6 adds the v3-helper rows.
SWEEP_SITES = [
    ("_strip_trajectory_rows", "content_hash", "function", True),
    ("_strip_trajectory_rows", "trajectory", "function", False),
    ("_panel_trajectory_header_idx", "trajectory", "function", True),
    ("TRAJECTORY_HEADER", "trajectory", "str", True),
    ("TRAJECTORY_SEP_RE", "trajectory", "regex", True),
    ("_HASH_BASIS_REMOVAL_RE", "content_hash", "regex", True),
    ("_MILESTONES_HEADER", "content_hash", "regex", True),
    ("_MILESTONE_NEUTRALIZE_RE", "content_hash", "regex", True),
    ("_neutralize_milestone_state", "content_hash", "function", True),
    ("CONTENT_HASH_WIDTH", "content_hash", "int", True),
    # Inert row: reached only by verify_content_hash_any_basis's v1 fallback.
    ("trim_trajectory_table", "content_hash", "function", False),
    ("trim_trajectory_table", "trajectory", "function", False),
    # The v3 helpers (T6): step 4b and the shared locator.
    ("canonicalize_trajectory_header_rows", "content_hash", "function", True),
    ("canonicalize_trajectory_header_rows", "trajectory", "function", False),
    ("_canonical_trajectory_table", "trajectory", "function", True),
    ("canonical_trajectory_row", "trajectory", "function", True),
    ("_UNESCAPED_PIPE", "trajectory", "regex", True),
]
_MODULES = {"content_hash": ch, "trajectory": tr}
_SITE_IDS = [f"{n}@{m}" for n, m, _, _ in SWEEP_SITES]


def _hostile(kind, real):
    """A deliberately different behaviour for a shared name."""
    if kind == "function":
        return lambda *a, **k: "HOSTILE"
    if kind == "regex":
        return re.compile(r"(?!x)x|HOSTILE")
    if kind == "str":
        return "### Trajectory-x"
    return 8


@pytest.mark.parametrize("name,mod,kind,live", SWEEP_SITES, ids=_SITE_IDS)
def test_v2_sweep_frozen_output_unchanged_under_patch(monkeypatch, name, mod, kind, live):
    module = _MODULES[mod]
    assert hasattr(module, name), f"{mod}.{name} is not a binding site"
    monkeypatch.setattr(module, name, _hostile(kind, getattr(module, name)))
    assert ch._content_for_hashing_v2_frozen(AC_2_1_FIXTURE) == AC_2_1_GOLDEN
    assert ch.compute_content_hash_v2(AC_2_1_FIXTURE) == _GOLDEN_HASH


@pytest.mark.parametrize("name,mod,kind,live", SWEEP_SITES, ids=_SITE_IDS)
def test_v2_sweep_vacuity_live_sites_reached_inert_not(monkeypatch, name, mod, kind, live):
    """A sweep patch that is never looked up proves nothing. Observe each site:
    live sites are reached by compute_content_hash, inert ones are not, and
    frozen v2 reaches none."""
    module = _MODULES[mod]
    real = getattr(module, name)
    baseline = ch.compute_content_hash(AC_2_1_FIXTURE)
    if kind in ("function", "regex"):
        probe = _recording_wrapper(real) if kind == "function" else _RecordingProxy(real)
        monkeypatch.setattr(module, name, probe)
        ch.compute_content_hash_v2(AC_2_1_FIXTURE)
        assert probe.calls == 0, "frozen v2 reached a shared site"
        ch.compute_content_hash(AC_2_1_FIXTURE)
        assert (probe.calls > 0) is live
    else:
        monkeypatch.setattr(module, name, _hostile(kind, real))
        assert ch.compute_content_hash_v2(AC_2_1_FIXTURE) == _GOLDEN_HASH
        moved = ch.compute_content_hash(AC_2_1_FIXTURE)
        assert (moved != baseline) is live
        if kind == "int":
            assert len(moved) == 8


def _trajectory_import_names(source: str) -> set:
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == "trajectory":
            names.update(a.asname or a.name for a in node.names)
    return names


def _sweep_table_gaps(source: str) -> set:
    """Names content_hash binds from trajectory with no content_hash sweep row."""
    aliased = {n for n, m, _, _ in SWEEP_SITES if m == "content_hash"}
    return _trajectory_import_names(source) - aliased


def test_v2_sweep_binding_site_table_complete():
    """Design SEAL-05: every name content_hash.py binds through its own
    `from trajectory import …` is a sweep row (`re`, `Optional`, `annotations`
    are imported independently and so are not aliases)."""
    source = Path(ch.__file__).read_text(encoding="utf-8")
    assert {"_strip_trajectory_rows", "trim_trajectory_table"} <= _trajectory_import_names(source)
    assert _sweep_table_gaps(source) == set()


def test_v2_sweep_binding_site_table_complete_flags_added_alias():
    source = Path(ch.__file__).read_text(encoding="utf-8")
    old = "from trajectory import _strip_trajectory_rows, trim_trajectory_table"
    assert old in source
    contaminated = source.replace(old, old + ", _fake_shared_helper")
    assert _sweep_table_gaps(contaminated) == {"_fake_shared_helper"}


# --- DRK2: strip differential (refactored strip == frozen v2 strip) -----------

_PANEL_TABLE = (
    "| Pass | Date       | Notes |\n"
    "|------|------------|-------|\n"
    "| 1    | 2026-11-01 | a     |\n"
    "| 2    | 2026-11-02 | b     |\n"
)
STRIP_CORPUS = {
    "canonical_table": "# D\n\n## Panel Review\n\n### Trajectory\n\n" + _PANEL_TABLE + "\n### Sealed dispositions\n\n## Approval\n",
    "unrecognised_separator": "# D\n\n## Panel Review\n\n### Trajectory\n\n| Pass | Notes |\n| -- x -- |\n| 1 | a |\n\n## Approval\n",
    "heading_no_table": "# D\n\n## Panel Review\n\n### Trajectory\n\nNo passes yet.\n\n### Sealed dispositions\n",
    "unclosed_fence": "# D\n\n## Panel Review\n\n```\n### Trajectory\n\n" + _PANEL_TABLE,
    "crlf": ("# D\n\n## Panel Review\n\n### Trajectory\n\n" + _PANEL_TABLE + "\n## Approval\n").replace("\n", "\r\n"),
    "duplicate_headings": "# D\n\n## Panel Review\n\n### Trajectory\n\n" + _PANEL_TABLE + "\n### Trajectory\n\n" + _PANEL_TABLE,
    "heading_last_line": "# D\n\n## Panel Review\n\n### Trajectory",
    "fenced_quoted_panel_review": "# D\n\n```\n## Panel Review\n\n### Trajectory\n\n" + _PANEL_TABLE + "```\n\n## Panel Review\n\n### Trajectory\n\n" + _PANEL_TABLE,
}


@pytest.mark.parametrize("name", sorted(STRIP_CORPUS))
def test_strip_differential_refactored_equals_frozen_v2(name):
    doc = STRIP_CORPUS[name]
    assert tr._strip_trajectory_rows(doc) == ch._v2_strip_trajectory_rows(doc)


# ---------------------------------------------------------------------------
# C1 canonicaliser and locator (T4)
# ---------------------------------------------------------------------------

import itertools  # noqa: E402

# R1's seven examples: (input row, separator?, canonical form).
R1_EXAMPLES = [
    ("| Pass | Date       | HIGHs | Notes   |", False, "|Pass|Date|HIGHs|Notes|"),
    ("|------|------------|-------|---------|", True, "|-|-|-|-|"),
    ("   | Pass | Date |\r", False, "|Pass|Date|"),
    ("|:----:|:--:--:|", True, "|:-:|:-:-:|"),
    ("|------||------|", True, "|-||-|"),
    ("| a\\ | b |", False, "|a\\ |b|"),
    ("| a\\|b |", False, "|a\\|b|"),
]


@pytest.mark.parametrize("row,sep,expected", R1_EXAMPLES, ids=[str(i) for i in range(7)])
def test_canonical_row_r1_examples(row, sep, expected):
    assert tr.canonical_trajectory_row(row, separator=sep) == expected


def test_canonical_row_escaped_pipe_rows_stay_distinct():
    a = tr.canonical_trajectory_row("| a\\ | b |", separator=False)
    b = tr.canonical_trajectory_row("| a\\|b |", separator=False)
    assert a != b  # AC-1.8


_SWEEP_ALPHABET = "|\\ a-:"
_SWEEP_MAX_LEN = 7


def _sweep_rows():
    for n in range(_SWEEP_MAX_LEN + 1):
        for chars in itertools.product(_SWEEP_ALPHABET, repeat=n):
            yield "".join(chars)


def _rule2_cells(row: str) -> list:
    parts = tr._UNESCAPED_PIPE.split(row.strip())
    if parts and parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return parts


def _normalised_cells(row: str, separator: bool) -> list:
    out = []
    for cell in _rule2_cells(row):
        cell = cell.strip()
        if cell.endswith("\\"):
            cell += " "
        if separator:
            cell = re.sub(r"-+", "-", cell)
        out.append(cell)
    return out


def test_canonical_row_exhaustive_sweep():
    """Every row of length <= 7 over `|`, `\\`, space, `a`, `-`, `:`, both modes.

    Asserts: never raises; idempotent (f(f(x)) == f(x)); and PADDING-INVARIANT,
    defined precisely so it is never "fixed" by weakening it: take the cells as
    R1 rule 2 splits them from the original row (`_UNESCAPED_PIPE.split(row.strip())`,
    one empty edge part dropped at each end), rebuild the row as
    `"|" + "|".join(" " + c + " " for c in cells) + "|"`, and the canonical forms
    of the original and the rebuilt row are equal. Spaces are inserted only beside
    an unescaped delimiter, never between a backslash and the pipe after it.
    """
    f = tr.canonical_trajectory_row
    for row in _sweep_rows():
        for sep in (True, False):
            once = f(row, separator=sep)
            assert f(once, separator=sep) == once, (row, sep)
            rebuilt = "|" + "|".join(" " + c + " " for c in _rule2_cells(row)) + "|"
            assert f(rebuilt, separator=sep) == once, (row, sep, rebuilt)


def test_canonical_row_sweep_injective_except_degenerate():
    """Design SEAL-06 / SEAL-19: re-splitting a canonical form returns the
    normalised (trimmed, dash-collapsed) cells, so distinct cell lists keep
    distinct forms. The ONE known exception: zero cells (`|`, empty row) and one
    empty cell (`||`) both canonicalise to `||`."""
    exceptions = set()
    for row in _sweep_rows():
        for sep in (True, False):
            cells = _normalised_cells(row, sep)
            canonical = tr.canonical_trajectory_row(row, separator=sep)
            if _rule2_cells(canonical) != cells:
                exceptions.add((tuple(cells), canonical))
    assert exceptions == {((), "||")}


def test_canonical_row_nbsp_only_cell_equals_empty_cell():
    """The C1 `str.strip()` widening (Unicode whitespace), pinned."""
    nbsp = tr.canonical_trajectory_row("| a | |", separator=False)
    empty = tr.canonical_trajectory_row("| a ||", separator=False)
    assert nbsp == empty == "|a||"


def _panel_doc(table: str, *, before: str = "", heading_ok: bool = True) -> str:
    return (
        "# D\n\n" + before
        + ("## Panel Review\n\n### Trajectory\n\n" if heading_ok else "")
        + table + "\n### Sealed dispositions\n\n## Approval\n"
    )


_PADDED = "| Pass | Notes      |\n|------|------------|\n| 1    | a          |\n"


def test_canonical_table_no_fallback_outside_panel_review():
    outside = "# D\n\n### Trajectory\n\n" + _PADDED + "\n## Panel Review\n\n### Latest pass detail\n"
    no_panel = "# D\n\n### Trajectory\n\n" + _PADDED
    for doc in (outside, no_panel):
        assert tr._canonical_trajectory_table(doc.split("\n")) is None
        assert tr.canonicalize_trajectory_header_rows(doc) == doc


def test_canonical_table_indented_separator_not_recognised():
    doc = _panel_doc("| Pass | Notes |\n  |------|-------|\n| 1 | a |\n")
    assert tr._canonical_trajectory_table(doc.split("\n")) is None
    assert tr.canonicalize_trajectory_header_rows(doc) == doc


def test_canonical_table_none_when_header_is_last_line():
    doc = "# D\n\n## Panel Review\n\n### Trajectory\n\n| Pass | Notes |"
    assert tr._canonical_trajectory_table(doc.split("\n")) is None
    assert tr.canonicalize_trajectory_header_rows(doc) == doc


def test_canonicalize_header_rows_rewrites_only_two_rows():
    other = "| Severity | Notes   |\n|----------|---------|\n"
    doc = _panel_doc(_PADDED) + "\n### Latest pass detail\n\n" + other
    out = tr.canonicalize_trajectory_header_rows(doc)
    before, after = doc.split("\n"), out.split("\n")
    assert len(before) == len(after)
    changed = [i for i, (x, y) in enumerate(zip(before, after)) if x != y]
    assert [after[i] for i in changed] == ["|Pass|Notes|", "|-|-|"]
    assert other in out  # the other table is byte-identical


def test_canonicalize_header_rows_identity_without_canonical_table():
    doc = "# D\n\n## Panel Review\n\n### Trajectory\n\nNo passes yet.\n"
    assert tr.canonicalize_trajectory_header_rows(doc) == doc


def test_canonicalize_header_rows_idempotent():
    doc = _panel_doc(_PADDED).replace("\n", "\r\n")
    once = tr.canonicalize_trajectory_header_rows(doc)
    assert once != doc
    assert tr.canonicalize_trajectory_header_rows(once) == once


# ---------------------------------------------------------------------------
# The v3 basis (T6): step 4b wired, HASH_BASIS_CURRENT flipped
# ---------------------------------------------------------------------------

import blueprint_common as bc  # noqa: E402
import _fixtures as fx  # noqa: E402

_TRAJ_HEADER = ["Pass", "Date", "HIGHs", "Notes"]


def _doc(*, basis="v3", stored="pending", header_pad=0, rows=2, extra_tables=False,
         header=None):
    """An artifact whose `## Panel Review` -> `### Trajectory` header and
    separator padding (`header_pad` extra spaces per cell) is controlled
    independently of its data rows."""
    header = header or _TRAJ_HEADER
    pad = " " * header_pad
    head = "|" + "|".join(f" {h}{pad} " for h in header) + "|"
    sep = "|" + "|".join("-" * (len(h) + 2 + header_pad) for h in header) + "|"
    data = "".join(
        "| " + " | ".join([str(i + 1), "2026-11-0%d" % (i + 1)] + ["0"] * (len(header) - 3) + [f"n{i}"]) + " |\n"
        for i in range(rows)
    )
    extra = ""
    if extra_tables:
        extra = (
            "```text\n| Pass | Notes      |\n|------|------------|\n```\n\n"
            "### Trajectory\n\n| Pass | Notes   |\n|------|---------|\n\n"
        )
    basis_line = f"- **Hash basis:** {basis}\n" if basis != "v1" else ""
    return (
        "# Doc\n\n## Objective\n\nx\n\n" + extra
        + "## Panel Review\n\n### Trajectory\n\n" + head + "\n" + sep + "\n" + data
        + "\n### Latest pass detail\n\n| Severity | Source | Notes   |\n|----------|--------|---------|\n\n"
        "## Approval\n\n- [x] Approved to proceed to next phase\n"
        f"- **Content Hash:** `{stored}`\n" + basis_line
    )


def _raw_diff_lines(a: str, b: str) -> list:
    la, lb = a.split("\n"), b.split("\n")
    assert len(la) == len(lb)
    return [i for i, (x, y) in enumerate(zip(la, lb)) if x != y]


def test_v3_hash_equal_across_header_separator_padding():
    a, b = _doc(header_pad=0), _doc(header_pad=7)
    changed = _raw_diff_lines(a, b)
    assert [a.split("\n")[i].startswith("|") for i in changed] == [True, True]
    assert len(changed) == 2  # exactly the header and separator lines differ
    assert ch.compute_content_hash_v2(a) != ch.compute_content_hash_v2(b)  # non-vacuity
    assert ch.compute_content_hash(a) == ch.compute_content_hash(b)  # AC-1.1


def test_v3_hash_distinct_for_renamed_header_and_column_count():
    base = ch.compute_content_hash(_doc())
    renamed = ch.compute_content_hash(_doc(header=["Pass", "Date", "HIGHs", "Remarks"]))
    wider = ch.compute_content_hash(_doc(header=["Pass", "Date", "HIGHs", "Sealed", "Notes"]))
    assert len({base, renamed, wider}) == 3  # AC-1.2


@pytest.mark.parametrize("doc", [
    "# Doc\n\n### Trajectory\n\n| Pass   | Notes |\n|--------|-------|\n| 1 | a |\n\n## Approval\n",
    "# Doc\n\n## Panel Review\n\n### Trajectory\n\nNo passes yet.\n\n## Approval\n",
], ids=["no_panel_review", "no_canonical_table"])
def test_v3_equals_frozen_v2_without_canonical_table(doc):
    assert ch.content_for_hashing(doc) == ch._content_for_hashing_v2_frozen(doc)  # AC-1.3


@pytest.mark.parametrize("case", ["other_tables", "no_panel_review_padded"])
def test_v3_canonicalises_only_canonical_trajectory_table(case):
    if case == "other_tables":
        doc = _doc(header_pad=3, extra_tables=True)
        v3, v2 = ch.content_for_hashing(doc), ch._content_for_hashing_v2_frozen(doc)
        changed = _raw_diff_lines(v2, v3)
        assert [v3.split("\n")[i] for i in changed] == ["|Pass|Date|HIGHs|Notes|", "|-|-|-|-|"]
    else:
        doc = "# Doc\n\n### Trajectory\n\n| Pass     | Notes      |\n|----------|------------|\n\n## Approval\n"
        assert ch.content_for_hashing(doc) == ch._content_for_hashing_v2_frozen(doc)  # AC-1.4


_WS_SEP_DOC = (
    "# Doc\n\n## Panel Review\n\n### Trajectory\n\n| Pass |\n|      |\n{rows}"
    "\n### Latest pass detail\n\n## Approval\n"
)


def test_v3_content_for_hashing_idempotent_keeps_escaped_pipe():
    for variant in list(_AC_1_8_VARIANTS.values()) + [_WS_SEP_DOC.format(rows="| 1 |\n")]:
        once = ch.content_for_hashing(variant)
        assert ch.content_for_hashing(once) == once  # AC-1.5
    escaped = ch.content_for_hashing(_AC_1_8_VARIANTS["escaped_pipe_cell"])
    assert "|a\\|b|" in escaped


def test_v3_whitespace_only_separator_data_rows_hash_neutral():
    """AD10's order: strip (step 4) runs on the RAW separator before the
    canonicaliser (step 4b) turns `|      |` into `||`, so the data rows are
    still stripped. Canonicalise-first would leave them hashed."""
    with_rows = _WS_SEP_DOC.format(rows="| 1 |\n| 2 |\n")
    without = _WS_SEP_DOC.format(rows="")
    assert ch.content_for_hashing(with_rows) == ch.content_for_hashing(without)


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_approve_stamps_single_v3_basis_line_each_tier(tmp_path, tier):
    first = {"sdd": "spec", "blueprint": "scope"}[tier]
    out = fx.write_chain(tmp_path, tier, approve=[first], bind=False)
    text = next(iter(out.values())).read_text(encoding="utf-8")
    assert ch.HASH_BASIS_CURRENT == "v3"
    assert text.count("- **Hash basis:** v3") == 1
    assert "**Hash basis:** v2" not in text  # AC-1.6


def test_approve_two_basis_lines_rewrites_only_first(tmp_path):
    (tmp_path / ".git").mkdir()
    p = tmp_path / "spec.md"
    p.write_text(
        "# Doc\n\n## Objective\n\nx\n\n## Approval\n\n- [ ] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n- **Hash basis:** v2\n- **Hash basis:** v1\n",
        encoding="utf-8",
    )
    assert bc.approve_document(p, project_root=tmp_path)
    text = p.read_text(encoding="utf-8")
    assert "- **Hash basis:** v3\n- **Hash basis:** v1" in text  # AC-1.6


# --- AC-1.8: seven goldens, each HAND-DERIVED from R1's rules ----------------

_H = ("| Pass | Date       | HIGHs | Regressions | Addressed | Deferred | Sealed "
      "| Notes                                  |")
_S = ("|------|------------|-------|-------------|-----------|----------|--------"
      "|----------------------------------------|")
assert _H in AC_2_1_FIXTURE and _S in AC_2_1_FIXTURE
# R1 rules 1-5 applied by hand: trim each cell, drop padding, collapse dash runs.
_H_V3 = "|Pass|Date|HIGHs|Regressions|Addressed|Deferred|Sealed|Notes|"
_S_V3 = "|-|-|-|-|-|-|-|-|"

_AC_1_8_VARIANTS = {
    "fixture": AC_2_1_FIXTURE,
    "backslash_before_escaped_pipe": AC_2_1_FIXTURE.replace(_H, "| Pass | a\\\\|b | Notes |"),
    "escaped_final_pipe": AC_2_1_FIXTURE.replace(_H, "| Pass | Notes \\|"),
    "cell_ends_in_backslash": AC_2_1_FIXTURE.replace(_H, "| a\\ | b |"),
    "escaped_pipe_cell": AC_2_1_FIXTURE.replace(_H, "| a\\|b |"),
    "empty_separator_cell": AC_2_1_FIXTURE.replace(_S, "|------||------|"),
    "colon_dash_separator": AC_2_1_FIXTURE.replace(_S, "|:--:--:|------|"),
}
# (canonical header, canonical separator) per variant, derived by hand.
_AC_1_8_ROWS = {
    "fixture": (_H_V3, _S_V3),
    # `a\\|b`: the pipe is preceded by a backslash, so it does not split (rule 2).
    "backslash_before_escaped_pipe": ("|Pass|a\\\\|b|Notes|", _S_V3),
    # The final pipe is escaped, so the last fragment `Notes \|` is a cell.
    "escaped_final_pipe": ("|Pass|Notes \\||", _S_V3),
    # `a\` keeps one trailing space so the re-joined pipe still splits (rule 3).
    "cell_ends_in_backslash": ("|a\\ |b|", _S_V3),
    "escaped_pipe_cell": ("|a\\|b|", _S_V3),
    "empty_separator_cell": (_H_V3, "|-||-|"),
    "colon_dash_separator": (_H_V3, "|:-:-:|-|"),
}


def _v3_golden(name: str) -> str:
    h, s = _AC_1_8_ROWS[name]
    return AC_2_1_GOLDEN.replace(_H, h).replace(_S, s)


@pytest.mark.parametrize("name", sorted(_AC_1_8_VARIANTS))
def test_v3_goldens_ac_2_1_fixture_and_variants(name):
    assert ch.content_for_hashing(_AC_1_8_VARIANTS[name]) == _v3_golden(name)


def test_v3_backslash_cell_and_escaped_pipe_cell_differ():
    a = ch.content_for_hashing(_AC_1_8_VARIANTS["cell_ends_in_backslash"])
    b = ch.content_for_hashing(_AC_1_8_VARIANTS["escaped_pipe_cell"])
    assert a != b and "|a\\ |b|" in a and "|a\\|b|" in b


def _two_widths(transform):
    return transform(_doc(header_pad=0)), transform(_doc(header_pad=5))


_BOUNDARY = {
    "crlf": lambda d: d.replace("\n", "\r\n"),
    "bom": lambda d: "﻿" + d,
    "crlf_bom": lambda d: "﻿" + d.replace("\n", "\r\n"),
}


@pytest.mark.parametrize("form", sorted(_BOUNDARY))
def test_v3_boundary_cases_line_endings(form):
    a, b = _two_widths(_BOUNDARY[form])
    assert ch.compute_content_hash(a) == ch.compute_content_hash(b)
    assert "|Pass|Date|HIGHs|Notes|" in ch.content_for_hashing(a)


@pytest.mark.parametrize("case", [
    "zero_data_rows", "separator_last_line", "duplicate_headings_and_unclosed_fence",
    "decorated_panel_review_heading", "empty_header_cells",
])
def test_v3_boundary_cases(case):
    if case == "zero_data_rows":
        a, b = _doc(rows=0), _doc(rows=0, header_pad=4)
        assert ch.compute_content_hash(a) == ch.compute_content_hash(b)
    elif case == "separator_last_line":
        a = "# D\n\n## Panel Review\n\n### Trajectory\n\n| Pass | Notes |\n|------|-------|"
        b = "# D\n\n## Panel Review\n\n### Trajectory\n\n| Pass   | Notes   |\n|--------|---------|"
        assert ch.compute_content_hash(a) == ch.compute_content_hash(b)
        assert ch.content_for_hashing(a).endswith("|Pass|Notes|\n|-|-|")
    elif case == "duplicate_headings_and_unclosed_fence":
        tail = "\n### Trajectory\n\n| Pass  | Notes  |\n|-------|--------|\n\n```\n### Trajectory\n"
        a, b = _doc() + tail, _doc(header_pad=3) + tail
        assert ch.compute_content_hash(a) == ch.compute_content_hash(b)
        assert "| Pass  | Notes  |" in ch.content_for_hashing(a)  # only the first is canonical
    elif case == "decorated_panel_review_heading":
        doc = _doc(header_pad=3).replace("## Panel Review\n", "## Panel Review (pass 3)\n")
        assert ch.content_for_hashing(doc) == ch._content_for_hashing_v2_frozen(doc)
    else:
        a = "# D\n\n## Panel Review\n\n### Trajectory\n\n| Pass |  |   |\n|------|--|---|\n"
        b = "# D\n\n## Panel Review\n\n### Trajectory\n\n| Pass ||    |\n|---|-|-----|\n"
        assert ch.compute_content_hash(a) == ch.compute_content_hash(b)
        assert "|Pass|||\n|-|-|-|" in ch.content_for_hashing(a)


def test_v3_nbsp_padded_header_cell_golden():
    doc = "# D\n\n## Panel Review\n\n### Trajectory\n\n| Pass | Notes  |\n|------|-------|\n"
    assert ch.content_for_hashing(doc) == "# D\n\n## Panel Review\n\n### Trajectory\n\n|Pass|Notes|\n|-|-|"


# ---------------------------------------------------------------------------
# AC-1.7 (T10): archiving a widening pass keeps a v3 approval matching
# ---------------------------------------------------------------------------

import subprocess  # noqa: E402

_ARCHIVE = _SCRIPTS / "archive_pass.py"
_SKILLS = _SCRIPTS.parent / "skills"
_TIER_FIRST = {"sdd": ("spec.md", {"design": "spec.md"}, "design"),
               "blueprint": ("SCOPE.md", {"architecture": "SCOPE.md"}, "architecture")}
_WIDE = "a deliberately wide addressed-row note so the new Notes cell is the widest"
_MODE_ROWS = {
    "panel_roster": [f"| [MED] | user-advocate | widen | Addressed | {_WIDE} |"],
    "strict_bar": [f"| [MED] | critic | widen | Addressed | {_WIDE} |"],
    "halt_vote": ["| [MED] | critic | a deliberately long out-of-scope concern that widens the halt-vote Notes | Halt and re-scope | stop |"],
    "skip": [],
}


def _trajectory_header(text: str) -> str:
    lines = text.split("\n")
    i = lines.index("### Trajectory")
    return next(ln for ln in lines[i + 1:] if ln.startswith("|"))


def _stage_and_archive(tmp_path: Path, tier: str, mode: str) -> Path:
    name = _TIER_FIRST[tier][0]
    p = tmp_path / name
    flags = fx.stamp_then_stage_pass(p, tier, latest_rows=_MODE_ROWS[mode], mode=mode)
    before = p.read_text(encoding="utf-8")
    proc = subprocess.run([sys.executable, str(_ARCHIVE), str(p), "--phase", "1", *flags],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    after = p.read_text(encoding="utf-8")
    assert _trajectory_header(after) != _trajectory_header(before)  # really widened
    assert fx._STAGE_LATEST_HEADER + "\n" in after  # Latest back to the stamp-time render
    return p


@pytest.mark.parametrize("mode", ["panel_roster", "strict_bar", "halt_vote", "skip"])
@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_archive_widening_pass_keeps_v3_approval_matching(tmp_path, tier, mode):
    p = _stage_and_archive(tmp_path, tier, mode)
    _name, phase_order, current = _TIER_FIRST[tier]
    result = bc.ValidationResult()
    bc.check_previous_phase_approved(tmp_path, current, result, phase_order)
    checks = {name: sev for name, sev, _detail in result.checks}
    assert checks.get(f"previous phase ({p.name}) has not been modified since approval") == bc.Severity.PASS, checks
    assert result.passed, result.checks
    assert not (tmp_path / ".sdd" / "pending-review.json").exists()


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_archive_widening_pass_tier_validator_cli_hash_check_passes(tmp_path, tier):
    """AC-1.7 through the tier's validator CLI. Pins `[PASS]` on the exact check
    name rather than exit 0 (a deliberate departure from the design's Testing
    Strategy row: these minimal fixtures fail unrelated section checks)."""
    d = tmp_path / ("specs/F1-x" if tier == "sdd" else "blueprint")
    d.mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    p = _stage_and_archive(d, tier, "panel_roster")
    nxt, script, phase = (
        ("design.md", _SKILLS / "spec-driven-dev/scripts/validate_spec.py", "design") if tier == "sdd"
        else ("ARCHITECTURE.md", _SKILLS / "project-blueprint/scripts/validate_blueprint.py", "architecture")
    )
    (d / nxt).write_text("# Next\n\n## Goals\n\nx\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(script), str(d), "--phase", phase,
                           "--project-root", str(tmp_path)], capture_output=True, text=True)
    assert f"[PASS] previous phase ({p.name}) has not been modified since approval" in proc.stdout, proc.stdout
    assert "HASH-BASIS-MIGRATION:" not in proc.stdout
    assert "Traceback" not in proc.stderr


# ---------------------------------------------------------------------------
# is_pure_basis_migration (AD4) and the any-basis v2 branch (AD6) — T12
# ---------------------------------------------------------------------------


def _relabel(doc: str, label) -> str:
    doc = re.sub(r"- \*\*Hash basis:\*\* \S+\n", "", doc)
    if label is None:
        return doc
    return re.sub(r"(- \*\*Content Hash:\*\* `[^`]*`\n)", rf"\g<1>- **Hash basis:** {label}\n", doc, count=1)


def _restamp(doc: str, stored: str) -> str:
    return re.sub(r"(\*\*Content Hash:\*\* )`[^`]*`", rf"\g<1>`{stored}`", doc, count=1)


def _v2_coherent() -> str:
    """A v2-stamped artifact whose padded Trajectory table makes v2 != v3."""
    doc = _doc(basis="v2", header_pad=3)
    stored = ch.compute_content_hash_v2(tr.trim_trajectory_table(doc))
    out = _restamp(doc, stored)
    assert ch.compute_content_hash(out) != stored
    return out


def _v1_coherent(doc=None) -> str:
    doc = _relabel(doc or _doc(header_pad=3), None)
    return _restamp(doc, ch.compute_content_hash_v1(tr.trim_trajectory_table(doc)))


def _pure(doc: str, stored=None) -> bool:
    return ch.is_pure_basis_migration(
        original_content=doc,
        stored_hash=stored if stored is not None else bc.read_stored_hash(doc),
        content_trimmed=tr.trim_trajectory_table(doc),
    )


def _only(doc: str, stored=None) -> bool:
    return ch.is_basis_migration_only(
        original_content=doc,
        stored_hash=stored if stored is not None else bc.read_stored_hash(doc),
        content_trimmed=tr.trim_trajectory_table(doc),
    )


def test_pure_migration_v2_coherent_true():
    assert _pure(_v2_coherent()) is True


def test_pure_migration_v1_delegates_to_is_basis_migration_only():
    coherent = _v1_coherent()
    assert ch.compute_content_hash(coherent) != bc.read_stored_hash(coherent)  # v1 != v3
    edited = coherent.replace("## Objective\n\nx\n", "## Objective\n\nedited\n")
    for doc in (coherent, edited):
        assert _pure(doc) == _only(doc)
    assert _pure(coherent) is True and _pure(edited) is False


_NO_TABLE = "# Doc\n\n## Objective\n\nx\n\n## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"


def test_pure_migration_v1_equal_to_v3_false():
    doc = _v1_coherent(_NO_TABLE)
    assert ch.compute_content_hash(doc) == bc.read_stored_hash(doc)  # coincident v1 == v3
    assert _only(doc) is True
    assert _pure(doc) is False  # the v3-match short-circuit (AD4)


@pytest.mark.parametrize("case", ["pending", "non_hex", "unchecked", "v3_match"])
def test_pure_migration_fail_closed(case):
    doc = _v2_coherent()
    if case == "pending":
        assert _pure(_restamp(doc, "pending"), "pending") is False
    elif case == "non_hex":
        assert _pure(_restamp(doc, "zzzzzzzzzzzzzzzz")) is False
    elif case == "unchecked":
        assert _pure(doc.replace("- [x] Approved to proceed", "- [ ] Approved to proceed")) is False
    else:
        v3 = _restamp(doc, ch.compute_content_hash(tr.trim_trajectory_table(doc)))
        assert _pure(v3) is False


@pytest.mark.parametrize("label", ["v3", "v4", "v03", "v10"])
def test_pure_migration_false_for_v3_and_unrecognised_labels(label):
    assert _pure(_relabel(_v2_coherent(), label)) is False


@pytest.mark.parametrize("label", ["vNext", "v2.1"])
def test_pure_migration_out_of_grammar_label_judged_as_v1(label):
    doc = _relabel(_doc(header_pad=3), label)
    assert ch.read_hash_basis(doc) == "v1"
    doc = _restamp(doc, ch.compute_content_hash_v1(tr.trim_trajectory_table(doc)))
    assert _pure(doc) is True and _pure(doc) == _only(doc)


def test_pure_migration_upper_case_stored_hash_accepted():
    doc = _v2_coherent()
    upper = _restamp(doc, bc.read_stored_hash(doc).upper())
    assert _pure(upper) is True


def test_pure_migration_arguments_keyword_only():
    doc = _v2_coherent()
    with pytest.raises(TypeError):
        ch.is_pure_basis_migration(doc, bc.read_stored_hash(doc), tr.trim_trajectory_table(doc))


def _outside_panel_doc(n_rows: int) -> str:
    rows = "".join(f"| {i + 1} | 2026-11-01 | 0 | n |\n" for i in range(n_rows))
    return (
        "# Doc\n\n## Objective\n\nx\n\n### Trajectory\n\n| Pass   | Date       | HIGHs | Notes |\n"
        "|--------|------------|-------|-------|\n" + rows
        + "\n## Approval\n\n- [x] Approved to proceed to next phase\n- **Content Hash:** `pending`\n"
        "- **Hash basis:** v2\n"
    )


@pytest.mark.parametrize("n_rows", [tr.TRAJECTORY_KEEP_DEFAULT, tr.TRAJECTORY_KEEP_DEFAULT + 3])
def test_pure_migration_false_for_trajectory_outside_panel_review(n_rows):
    """Design SEAL-22: with no canonical table v3 == v2, so the v3-match
    short-circuit decides — the precondition is asserted first."""
    raw = _outside_panel_doc(n_rows)
    trimmed = tr.trim_trajectory_table(raw)
    stored = ch.compute_content_hash_v2(trimmed)
    doc = _restamp(raw, stored)
    assert ch.compute_content_hash(tr.trim_trajectory_table(doc)) == stored
    if n_rows > tr.TRAJECTORY_KEEP_DEFAULT:
        assert "earlier passes elided" in trimmed  # the trim really dropped rows
    assert _pure(doc) is False


def test_pure_migration_false_for_invalid_panel_review_table():
    """Design SEAL-22's second case: a Panel Review Trajectory heading with an
    invalid table (no recognised separator) has no canonical table and no
    fallback, so v3 == v2 and the v3-match short-circuit decides."""
    raw = (
        "# Doc\n\n## Objective\n\nx\n\n## Panel Review\n\n### Trajectory\n\n| Pass   | Notes |\n"
        "| not a separator |\n| 1 | n |\n\n## Approval\n\n- [x] Approved to proceed to next phase\n"
        "- **Content Hash:** `pending`\n- **Hash basis:** v2\n"
    )
    assert tr._canonical_trajectory_table(raw.split("\n")) is None
    stored = ch.compute_content_hash_v2(tr.trim_trajectory_table(raw))
    doc = _restamp(raw, stored)
    assert ch.compute_content_hash(tr.trim_trajectory_table(doc)) == stored
    assert _pure(doc) is False


def test_any_basis_accepts_v2_coherent_raw_content():
    doc = _doc(basis="v2", header_pad=3)
    doc = _restamp(doc, ch.compute_content_hash_v2(doc))
    assert not ch.verify_content_hash(doc, bc.read_stored_hash(doc))
    assert ch.verify_content_hash_any_basis(doc, bc.read_stored_hash(doc)) is True


@pytest.mark.parametrize("label", ["v3", None, "v4"], ids=["v3", "v1", "v4"])
def test_any_basis_v2_branch_gated_on_v2_label(label):
    doc = _doc(basis="v2", header_pad=3)
    doc = _relabel(_restamp(doc, ch.compute_content_hash_v2(doc)), label)
    assert ch.verify_content_hash_any_basis(doc, bc.read_stored_hash(doc)) is False


def _write_shipped_chain(tmp_path: Path, spec_text: str) -> Path:
    """A spec dir whose design.md and tasks.md are v3-approved and every task is
    ticked, so `is_shipped` turns on spec.md alone."""
    d = tmp_path / "specs" / "F1-x"
    d.mkdir(parents=True, exist_ok=True)
    approval = "## Approval\n\n- [ ] Approved to proceed\n- **Content Hash:** `pending`\n"
    (d / "design.md").write_text("# Design\n\nx\n\n" + approval, encoding="utf-8")
    (d / "tasks.md").write_text("# Tasks\n\n- [x] T1: done\n\n" + approval, encoding="utf-8")
    for name in ("design.md", "tasks.md"):
        fx.stamp_under_basis(d / name, "v3")
    (d / "spec.md").write_text(_NO_TABLE, encoding="utf-8")
    fx.stamp_under_basis(d / "spec.md", "v3")
    assert bc.is_shipped(d)  # the baseline chain ships
    (d / "spec.md").write_text(spec_text, encoding="utf-8")
    return d


def _read_paths(tmp_path: Path, text: str) -> dict:
    import importlib.util

    stored = bc.read_stored_hash(text)
    spec = importlib.util.spec_from_file_location(
        "render_business_brief", _SKILLS / "project-blueprint" / "scripts" / "render_business_brief.py")
    return {
        "verify_content_hash_any_basis": ch.verify_content_hash_any_basis(text, stored),
        "approval_hash_matches": ch.approval_hash_matches(text),
        "is_shipped": bc.is_shipped(_write_shipped_chain(tmp_path, text)),
        # render_business_brief.py:812 calls verify_content_hash_any_basis(content, stored)
        "render_business_brief": spec is not None and ch.verify_content_hash_any_basis(text, stored),
    }


def _ac_3_4_repadded() -> str:
    """AC-3.4's artifact: v2-coherent, then its Trajectory header and separator
    re-padded (as a widening archive would), so it verifies under neither basis."""
    narrow, wide = _doc(basis="v2", header_pad=1), _doc(basis="v2", header_pad=6)
    stamped = _restamp(narrow, ch.compute_content_hash_v2(narrow))
    changed = _raw_diff_lines(narrow, wide)
    assert len(changed) == 2
    lines = stamped.split("\n")
    for i in changed:
        lines[i] = wide.split("\n")[i]
    return "\n".join(lines)


@pytest.mark.parametrize("case,expected", [("v2_coherent", True), ("v1_coherent", True), ("ac_3_4_repadded", False)])
def test_read_paths_on_three_unmigrated_artifacts(tmp_path, case, expected):
    if case == "v2_coherent":
        text = _doc(basis="v2", header_pad=3)
        text = _restamp(text, ch.compute_content_hash_v2(text))
    elif case == "v1_coherent":
        text = _v1_coherent()
    else:
        text = _ac_3_4_repadded()
        stored = bc.read_stored_hash(text)
        assert ch.compute_content_hash_v2(text) != stored and ch.compute_content_hash(text) != stored
    assert set(_read_paths(tmp_path, text).values()) == {expected}  # AC-3.6


@pytest.mark.parametrize("basis", ["v2", "v1"])
def test_read_paths_on_v3_verifying_stamps(tmp_path, basis):
    text = _NO_TABLE if basis == "v1" else _relabel(_NO_TABLE, "v2")
    hasher = ch.compute_content_hash_v1 if basis == "v1" else ch.compute_content_hash_v2
    text = _restamp(text, hasher(text))
    assert ch.compute_content_hash(text) == bc.read_stored_hash(text)  # verifies under v3 too
    assert set(_read_paths(tmp_path, text).values()) == {True}  # AC-3.13


# ---------------------------------------------------------------------------
# C3 operator text (T14)
# ---------------------------------------------------------------------------


def _fail(**kw) -> str:
    args = dict(artifact="previous phase (spec.md)", stamped_basis="v2",
                artifact_dir=Path("specs/F1-x"), approve_phase="spec",
                validator_cmd="validate_spec.py")
    args.update(kw)
    return bc.format_hash_basis_migration_fail(**args)


@pytest.mark.parametrize("stamped", ["v2", "v1"])
def test_migration_fail_text_leads_with_outcome_and_names_bases(stamped):
    text = _fail(stamped_basis=stamped)
    assert text.startswith("HASH-BASIS-MIGRATION: one re-approval clears this")
    assert f"stamped under basis {stamped} and the current basis is v3" in text
    assert "no new panel review" in text and "though no edit you made caused it" in text
    assert "`validate_spec.py ./specs/F1-x --approve spec`" in text
    assert "The re-stamp creates no new pending-review obligation; an obligation already open stays open." in text
    assert "`--run-state`" in text and "STALE_MIGRATION" in text
    assert "newer-stamp" in text and "upstream-drift" in text
    assert "references/hash-and-cascade.md, section Hash-basis migration" in text


@pytest.mark.parametrize("bare,phase,cmd", [
    ("spec.md", "spec", "validate_spec.py"), ("SCOPE.md", "scope", "validate_blueprint.py"),
])
def test_migration_fail_prints_full_invocation_each_tier(bare, phase, cmd):
    text = _fail(artifact=f"previous phase ({bare})", approve_phase=phase,
                 validator_cmd=bc._ARTIFACT_VALIDATOR_CMD[bare], artifact_dir=Path("d"))
    assert f"Re-approve it once: `{cmd} ./d --approve {phase}`." in text


def test_migration_fail_relative_dash_dir_prints_dot_slash():
    assert "`validate_spec.py ./-x --approve spec`" in _fail(artifact_dir=Path("-x"))


def test_migration_fail_absolute_dir_printed_as_is():
    text = _fail(artifact_dir=Path("/srv/repo/specs/F1-x"))
    assert "`validate_spec.py /srv/repo/specs/F1-x --approve spec`" in text
    assert ".//" not in text


def test_migration_fail_refused_dir_prints_reason_no_command():
    """Design SEAL-03: the deliberate deviation — a directory display_arg refuses
    gets the --approve flag and the reason, never a backticked command."""
    text = _fail(artifact_dir=Path("specs/a`b"))
    assert bc.MIGRATION_REAPPROVE_REFUSED.format(
        phase="spec", reason="contains a backtick") in text
    assert "validate_spec.py" not in text


def test_migration_fail_none_inputs_print_placeholders():
    text = _fail(artifact_dir=None, approve_phase=None, validator_cmd=None)
    assert "`<validator> <artifact-dir> --approve <phase>`" in text
    assert not re.search(r"\{[a-z_]+\}", text)


def test_operator_text_braces_in_inputs_do_not_raise():
    """Design SEAL-14: single-stage formatting — braces in any input are data."""
    text = _fail(artifact="previous phase ({x}.md)", stamped_basis="v{2}",
                 artifact_dir=Path("specs/{dir}"), approve_phase="{p}", validator_cmd="{v}")
    assert "{x}" in text and "{dir}" in text
    detail = bc.stale_hash_detail(stored_hash="{a}", stamped_basis="{b}", current_hash="{c}")
    assert "{a}" in detail and "{b}" in detail


def test_stale_detail_labels_bases_and_v2_note_only():
    v2 = bc.stale_hash_detail(stored_hash="a" * 16, stamped_basis="v2", current_hash="b" * 16)
    assert v2.startswith(f"Stored: {'a' * 16} (basis v2), Current: {'b' * 16} (basis v3)")
    assert bc.STALE_V2_RESTAMP_NOTE in v2
    v1 = bc.stale_hash_detail(stored_hash="a" * 16, stamped_basis="v1", current_hash="b" * 16)
    assert "(basis v1)" in v1 and bc.STALE_V2_RESTAMP_NOTE not in v1


def test_stale_detail_long_basis_label_truncated():
    label = "v" + "9" * 5000
    detail = bc.stale_hash_detail(stored_hash="a" * 16, stamped_basis=label, current_hash="b" * 16)
    shown = re.search(r"\(basis ([^)]*)\), Current", detail).group(1)
    assert len(shown) == ar_BASIS_LABEL_MAX() and shown.endswith("…")


def ar_BASIS_LABEL_MAX() -> int:
    import approval_records as ar

    return ar.BASIS_LABEL_MAX


def test_artifact_validator_cmd_covers_six_bare_names():
    import approval_records as ar

    assert bc._ARTIFACT_VALIDATOR_CMD == {
        **{n: ar.TIER_VALIDATOR_CMD["sdd"] for n in ("spec.md", "design.md", "tasks.md")},
        **{n: ar.TIER_VALIDATOR_CMD["blueprint"] for n in ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md")},
    }


def test_check_approval_migration_fail_prints_placeholders_before_wiring():
    """Before T15 wires the real inputs, check_approval's migration FAIL is the
    formatter's output with placeholders — never the raw template."""
    doc = _v1_coherent()
    result = bc.ValidationResult()
    assert bc.check_approval(doc, "previous phase (spec.md)", result) is False
    detail = next(d for n, _s, d in result.checks if n.endswith("hash basis is current"))
    assert detail.startswith("HASH-BASIS-MIGRATION: one re-approval clears this")
    assert not re.search(r"\{[a-z_]+\}", detail)


# ---------------------------------------------------------------------------
# C3 wiring: check_approval / check_previous_phase_approved (T15)
# ---------------------------------------------------------------------------


def _prev_check(tmp_path: Path, name: str, text: str):
    (tmp_path / name).write_text(text, encoding="utf-8")
    result = bc.ValidationResult()
    bc.check_previous_phase_approved(tmp_path, "next", result, {"next": name})
    return result


def _fails(result) -> dict:
    return {n: d for n, sev, d in result.checks if sev == bc.Severity.FAIL}


_TIER_OF = {"spec.md": ("validate_spec.py", "spec"), "design.md": ("validate_spec.py", "design"),
            "SCOPE.md": ("validate_blueprint.py", "scope"),
            "ARCHITECTURE.md": ("validate_blueprint.py", "architecture")}


@pytest.mark.parametrize("name", sorted(_TIER_OF))
def test_previous_phase_v2_migration_fail_each_predecessor_kind(tmp_path, name):
    fails = _fails(_prev_check(tmp_path, name, _v2_coherent()))
    detail = fails[f"previous phase ({name}) hash basis is current"]
    validator, phase = _TIER_OF[name]
    assert detail.startswith("HASH-BASIS-MIGRATION:")
    assert f"`{validator} {tmp_path} --approve {phase}`" in detail  # absolute dir as-is
    assert f"previous phase ({name}) has not been modified since approval" not in fails


@pytest.mark.parametrize("name", ["spec.md", "SCOPE.md"])
def test_previous_phase_v1_migration_fail_names_v1_and_v3(tmp_path, name):
    detail = _fails(_prev_check(tmp_path, name, _v1_coherent()))[f"previous phase ({name}) hash basis is current"]
    validator, phase = _TIER_OF[name]
    assert "stamped under basis v1 and the current basis is v3" in detail
    assert f"`{validator} {tmp_path} --approve {phase}`" in detail


@pytest.mark.parametrize("basis", ["v2", "v1"])
def test_previous_phase_substantive_edit_generic_stale_with_labels(tmp_path, basis):
    doc = _v2_coherent() if basis == "v2" else _v1_coherent()
    doc = doc.replace("## Objective\n\nx\n", "## Objective\n\nedited\n")
    fails = _fails(_prev_check(tmp_path, "spec.md", doc))
    detail = fails["previous phase (spec.md) has not been modified since approval"]
    assert f"(basis {basis})" in detail and "(basis v3)" in detail
    assert (bc.STALE_V2_RESTAMP_NOTE in detail) is (basis == "v2")
    assert "previous phase (spec.md) hash basis is current" not in fails


@pytest.mark.parametrize("delta", ["roster_repad", "seal_promotion"])
def test_previous_phase_v2_repad_or_seal_generic_stale_not_migration(tmp_path, delta):
    if delta == "roster_repad":
        doc = _ac_3_4_repadded()
    else:
        doc = _v2_coherent().replace(
            "### Latest pass detail",
            "### Sealed dispositions\n\n- `[SEAL-01]` **a thing** (pass 2, user-directed) — Defense: fine.\n\n"
            "### Latest pass detail", 1)
    fails = _fails(_prev_check(tmp_path, "spec.md", doc))
    detail = fails["previous phase (spec.md) has not been modified since approval"]
    assert "(basis v2)" in detail and bc.STALE_V2_RESTAMP_NOTE in detail
    assert not any("HASH-BASIS-MIGRATION:" in d for d in fails.values())  # AC-3.4, spec Q3


@pytest.mark.parametrize("basis", ["v2", "v1"])
def test_previous_phase_v3_verifying_stamp_passes(tmp_path, basis):
    text = _NO_TABLE if basis == "v1" else _relabel(_NO_TABLE, "v2")
    hasher = ch.compute_content_hash_v1 if basis == "v1" else ch.compute_content_hash_v2
    result = _prev_check(tmp_path, "spec.md", _restamp(text, hasher(text)))
    assert result.passed and not _fails(result)  # AC-3.13


def test_previous_phase_outside_panel_review_trajectory_no_migration_fail(tmp_path):
    raw = _outside_panel_doc(3)
    doc = _restamp(raw, ch.compute_content_hash_v2(tr.trim_trajectory_table(raw)))
    result = _prev_check(tmp_path, "spec.md", doc)
    assert not any("HASH-BASIS-MIGRATION:" in (d or "") for _n, _s, d in result.checks)


def test_previous_phase_out_of_set_name_prints_placeholders_no_raise(tmp_path):
    detail = _fails(_prev_check(tmp_path, "notes.md", _v1_coherent()))[
        "previous phase (notes.md) hash basis is current"]
    assert f"`<validator> {tmp_path} --approve <phase>`" in detail


def test_check_approval_check_names_unchanged(tmp_path):
    (tmp_path / "a").mkdir()
    migr = {n for n, _s, _d in _prev_check(tmp_path / "a", "spec.md", _v2_coherent()).checks}
    assert {"previous phase (spec.md) has Approval section", "previous phase (spec.md) is approved",
            "previous phase (spec.md) hash basis is current"} <= migr
    (tmp_path / "b").mkdir()
    stale = {n for n, _s, _d in _prev_check(tmp_path / "b", "spec.md", _ac_3_4_repadded()).checks}
    assert "previous phase (spec.md) has not been modified since approval" in stale


# ---------------------------------------------------------------------------
# C4 approve-time migration arm (T17)
# ---------------------------------------------------------------------------

import pending_review as pr  # noqa: E402

_REMINDER_LINE = bc.REAPPROVAL_REMINDER.splitlines()[0]


def _marker(root: Path) -> list:
    m = root / ".sdd" / "pending-review.json"
    return sorted(__import__("json").loads(m.read_text(encoding="utf-8"))["pending"]) if m.exists() else []


def _approve(root: Path, p: Path, capsys, tier="sdd", **kw) -> str:
    (root / ".git").mkdir(exist_ok=True)
    capsys.readouterr()
    assert fx._load_validator(tier).approve_document(p, project_root=root, **kw)
    return capsys.readouterr().out


def _migrated_line(out: str) -> list:
    return [ln for ln in out.splitlines() if ln.startswith("hash-basis-migrated:")]


@pytest.mark.parametrize("tier,name", [("sdd", "spec.md"), ("blueprint", "SCOPE.md")])
def test_validate_then_approve_v2_migration_marker_free_each_tier(tmp_path, capsys, tier, name):
    p = tmp_path / name
    p.write_text(_v2_coherent(), encoding="utf-8")
    first = _fails(_prev_check(tmp_path, name, p.read_text(encoding="utf-8")))
    assert first[f"previous phase ({name}) hash basis is current"].startswith("HASH-BASIS-MIGRATION:")
    out = _approve(tmp_path, p, capsys, tier)
    text = p.read_text(encoding="utf-8")
    assert bc.read_stored_hash(text) == ch.compute_content_hash(text)
    assert text.count("- **Hash basis:** v3") == 1 and "**Hash basis:** v2" not in text
    assert _marker(tmp_path) == [] and _REMINDER_LINE not in out
    line = _migrated_line(out)
    assert line == [f"hash-basis-migrated: {name} re-stamped from basis v2 to basis v3; "
                    "no pending-review obligation written (basis-only migration; content otherwise unchanged)."]
    assert "re-stamped to basis v2" not in out
    after = _prev_check(tmp_path, name, text)
    checks = {n: sev for n, sev, _d in after.checks}
    assert checks[f"previous phase ({name}) has not been modified since approval"] == bc.Severity.PASS


def test_second_approve_after_migration_marker_free_no_migration_line(tmp_path, capsys):
    p = tmp_path / "spec.md"
    p.write_text(_v2_coherent(), encoding="utf-8")
    _approve(tmp_path, p, capsys)
    out = _approve(tmp_path, p, capsys)
    assert _migrated_line(out) == [] and _marker(tmp_path) == []


def test_approve_v1_migration_writes_v3_directly(tmp_path, capsys):
    p = tmp_path / "spec.md"
    p.write_text(_v1_coherent(), encoding="utf-8")
    out = _approve(tmp_path, p, capsys)
    text = p.read_text(encoding="utf-8")
    assert text.count("- **Hash basis:** v3") == 1 and "Hash basis:** v2" not in text
    assert _marker(tmp_path) == []
    assert _migrated_line(out)[0].startswith("hash-basis-migrated: spec.md re-stamped from basis v1 to basis v3;")


def test_approve_v2_substantive_edit_creates_fresh_obligation(tmp_path, capsys):
    p = tmp_path / "spec.md"
    p.write_text(_v2_coherent().replace("## Objective\n\nx\n", "## Objective\n\nedited\n"), encoding="utf-8")
    out = _approve(tmp_path, p, capsys)
    assert _marker(tmp_path) == ["spec.md"] and _REMINDER_LINE in out
    assert _migrated_line(out) == []


@pytest.mark.parametrize("edited", [False, True])
def test_task_tick_v2_tasks_restamps_v3_suppressed(tmp_path, capsys, edited):
    doc = _v2_coherent()
    if edited:
        doc = doc.replace("## Objective\n\nx\n", "## Objective\n\nedited\n")
    p = tmp_path / "tasks.md"
    p.write_text(doc, encoding="utf-8")
    out = _approve(tmp_path, p, capsys, task_tick=True)
    text = p.read_text(encoding="utf-8")
    assert bc.read_stored_hash(text) == ch.compute_content_hash(text)
    assert text.count("- **Hash basis:** v3") == 1
    assert "task-tick: pending-review suppressed" in out
    assert _marker(tmp_path) == [] and _REMINDER_LINE not in out and _migrated_line(out) == []  # AC-3.14


@pytest.mark.parametrize("case", ["pending", "unchecked"])
def test_approve_pending_or_unchecked_first_approval_no_marker(tmp_path, capsys, case):
    doc = _v2_coherent()
    doc = _restamp(doc, "pending") if case == "pending" else doc.replace(
        "- [x] Approved to proceed", "- [ ] Approved to proceed")
    p = tmp_path / "spec.md"
    p.write_text(doc, encoding="utf-8")
    out = _approve(tmp_path, p, capsys)
    assert _marker(tmp_path) == [] and _migrated_line(out) == []


@pytest.mark.parametrize("case", ["non_hex", "v4"])
def test_approve_non_hex_or_v4_changed_content_creates_marker(tmp_path, capsys, case):
    """Design SEAL-19: tested on an approved artifact whose content changed."""
    doc = _v2_coherent().replace("## Objective\n\nx\n", "## Objective\n\nedited\n")
    doc = _restamp(doc, "zzzzzzzzzzzzzzzz") if case == "non_hex" else _relabel(doc, "v4")
    p = tmp_path / "spec.md"
    p.write_text(doc, encoding="utf-8")
    out = _approve(tmp_path, p, capsys)
    assert _marker(tmp_path) == ["spec.md"] and _REMINDER_LINE in out


@pytest.mark.parametrize("label", ["vNext", "v2.1"])
def test_approve_out_of_grammar_label_inserts_v3_keeps_original(tmp_path, capsys, label):
    doc = _relabel(_doc(header_pad=3), label)
    doc = _restamp(doc, ch.compute_content_hash_v1(tr.trim_trajectory_table(doc)))
    p = tmp_path / "spec.md"
    p.write_text(doc, encoding="utf-8")
    _approve(tmp_path, p, capsys)
    text = p.read_text(encoding="utf-8")
    assert re.search(r"\*\*Content Hash:\*\* `[0-9a-f]{16}`\n- \*\*Hash basis:\*\* v3\n- \*\*Hash basis:\*\* " + re.escape(label), text)


def _bind_transform(p: Path):
    w = bc.ApprovalWrites(bindings=bc.collect_upstream_bindings(p.parent, "design.md"),
                          judged_hash=bc.judged_text_hash(p.read_text(encoding="utf-8")))
    return bc.compose_content_transforms(
        lambda c, f: bc.verify_judged_transform(c, f, writes=w),
        lambda c, f: bc.apply_approval_writes(c, f, writes=w))


@pytest.mark.parametrize("basis", ["v1", "v2", "v3"])
def test_approve_recognised_delta_carve_out_each_basis(tmp_path, capsys, basis):
    """AC-3.8 positive / design SEAL-09: a classifier-recognised delta re-approves
    marker-free under every recognised basis. The classifier hashes a v1 stamp
    with the CURRENT basis, so a v1 delta is recognisable only where v1 == v3 —
    a binding refresh on a document with no Trajectory table; v2 and v3 use a
    seal promotion through a real archive."""
    import test_seal_promotion_restamp as sp

    if basis == "v1":
        p = tmp_path / "design.md"
        p.write_text(_NO_TABLE, encoding="utf-8")
        fx.stamp_under_basis(p, "v1")
        assert ch.read_hash_basis(p.read_text(encoding="utf-8")) == "v1"
        (tmp_path / "spec.md").write_text(
            "# s\n\n## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `0123456789abcdef`\n",
            encoding="utf-8")
        (tmp_path / ".git").mkdir(exist_ok=True)
        capsys.readouterr()
        assert bc.approve_document(p, project_root=tmp_path, content_transform=_bind_transform(p))
        out = capsys.readouterr().out
    else:
        p = sp._approved(tmp_path, basis=None if basis == "v3" else basis)
        sp._add_latest(p, sp._seal())
        sp._archive(p)
        out = _approve(tmp_path, p, capsys)
    assert any(ln.startswith("restamp-carve-out:") for ln in out.splitlines()), out
    assert _marker(tmp_path) == []


@pytest.mark.parametrize("target", ["is_pure_basis_migration", "format_hash_basis_migrated",
                                    "format_restamp_carve_out"])
def test_post_stamp_exception_fails_closed(tmp_path, capsys, monkeypatch, target):
    if target == "format_restamp_carve_out":
        import test_seal_promotion_restamp as sp

        p = sp._approved(tmp_path)
        sp._add_latest(p, sp._seal())
        sp._archive(p)
    else:
        p = tmp_path / "spec.md"
        p.write_text(_v2_coherent(), encoding="utf-8")

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(pr, target, boom)
    out = _approve(tmp_path, p, capsys)
    assert _marker(tmp_path) == ["spec.md"] and _REMINDER_LINE in out
    assert _migrated_line(out) == [] and "restamp-carve-out:" not in out


@pytest.mark.parametrize("basis", ["v2", "v1"])
def test_approve_stamp_already_verifying_under_v3_no_migration_line(tmp_path, capsys, basis):
    text = _NO_TABLE if basis == "v1" else _relabel(_NO_TABLE, "v2")
    hasher = ch.compute_content_hash_v1 if basis == "v1" else ch.compute_content_hash_v2
    stored = hasher(text)
    p = tmp_path / "spec.md"
    p.write_text(_restamp(text, stored), encoding="utf-8")
    out = _approve(tmp_path, p, capsys)
    after = p.read_text(encoding="utf-8")
    assert bc.read_stored_hash(after) == stored
    assert after.rstrip().endswith("- **Hash basis:** v3") and after.count("**Hash basis:**") == 1
    assert _marker(tmp_path) == [] and _migrated_line(out) == []


@pytest.mark.parametrize("old", ["v2", "v1"])
def test_hash_basis_migrated_template_names_both_bases(old):
    line = pr.format_hash_basis_migrated("specs/F1-x/spec.md", from_basis=old,
                                         binding_refresh=False, producer_refresh=False)
    assert line == (f"hash-basis-migrated: specs/F1-x/spec.md re-stamped from basis {old} to basis v3; "
                    "no pending-review obligation written (basis-only migration; content otherwise unchanged).")
    assert not re.search(r"\{[a-z_]+\}", bc.HASH_BASIS_MIGRATION_SUPPRESS_MSG.format(
        doc_rel="d", from_basis="v2", to_basis="v3", refresh=""))


def test_hash_basis_migrated_doc_rel_displayed_safely():
    line = pr.format_hash_basis_migrated("spec\x1b[31m\x07.md", from_basis="v" + "9" * 50,
                                         binding_refresh=False, producer_refresh=False)
    assert "\x1b" not in line and "\x07" not in line and "\n" not in line
    assert "…" in line  # the long label is truncated to BASIS_LABEL_MAX


def test_marker_schema_version_unchanged():
    assert bc.MARKER_SCHEMA_VERSION == 1  # DM6


# ---------------------------------------------------------------------------
# C4 carve-out basis change, refresh naming, open obligation (T18)
# ---------------------------------------------------------------------------

_SDD_PANEL = "--panel-roster"


def _bind_approve(root: Path, p: Path, capsys) -> str:
    """Re-approve `p` writing its upstream bindings (the validator's approve)."""
    (root / ".git").mkdir(exist_ok=True)
    bare = bc.strip_artifact_prefix(p.name)
    w = bc.ApprovalWrites(bindings=bc.collect_upstream_bindings(p.parent, bare),
                          judged_hash=bc.judged_text_hash(p.read_text(encoding="utf-8")))
    capsys.readouterr()
    assert bc.approve_document(p, project_root=root, content_transform=bc.compose_content_transforms(
        lambda c, f: bc.verify_judged_transform(c, f, writes=w),
        lambda c, f: bc.apply_approval_writes(c, f, writes=w)))
    return capsys.readouterr().out


def _carve(out: str) -> list:
    return [ln for ln in out.splitlines() if ln.startswith("restamp-carve-out:")]


def _upstream_spec(root: Path, h: str) -> None:
    (root / "spec.md").write_text(
        f"# s\n\n## Approval\n\n- [x] Approved to proceed\n- **Content Hash:** `{h}`\n", encoding="utf-8")


@pytest.mark.parametrize("case", ["roster_repad", "seal_promotion", "repad_plus_binding", "seal_plus_binding"])
def test_carve_out_v2_repad_names_basis_change(tmp_path, capsys, case):
    """AC-3.4: a v2 stamp whose only delta is a classifier-recognised re-pad
    and/or seal promotion (optionally with a binding refresh) re-approves
    marker-free, and the carve-out line names `hash basis v2 → v3`."""
    import test_seal_promotion_restamp as sp

    binding = case.endswith("_binding")
    p = sp._approved(tmp_path, "design.md", basis=None)
    if binding:
        _upstream_spec(tmp_path, "0123456789abcdef")
        _bind_approve(tmp_path, p, capsys)
    fx.stamp_under_basis(p, "v2")
    if binding:
        _upstream_spec(tmp_path, "fedcba9876543210")
    if case.startswith("seal"):
        sp._add_latest(p, sp._seal())
        sp._archive(p, "--strict-bar")
        parts = ["seal promotion ([SEAL-01])"]
    else:
        # An Addressed row from a roster panelist: the archived Notes gain the
        # wider `panel=` token, so the header re-pads (an empty Latest archives
        # nothing). Addressed promotes nothing.
        sp._add_latest(p, "| [MED] | architect | widen | Addressed | fixed |")
        sp._archive(p, _SDD_PANEL, "architect,testability-reviewer,security-reviewer")
        parts = []
    if binding:
        parts.append("upstream binding refresh")
    parts.append("Trajectory table re-pad")
    out = _bind_approve(tmp_path, p, capsys) if binding else _approve(tmp_path, p, capsys)
    text = p.read_text(encoding="utf-8")
    assert text.count("- **Hash basis:** v3") == 1 and bc.read_stored_hash(text) == ch.compute_content_hash(text)
    assert _marker(tmp_path) == [] and _REMINDER_LINE not in out
    assert _carve(out) == [bc.RESTAMP_CARVE_OUT_PREFIX.format(doc_rel="design.md")
                           + " and ".join(parts) + "; hash basis v2 → v3"]


def test_carve_out_v3_stamp_no_basis_part(tmp_path, capsys):
    import test_seal_promotion_restamp as sp

    p = sp._approved(tmp_path)
    sp._add_latest(p, sp._seal())
    sp._archive(p)
    out = _approve(tmp_path, p, capsys)
    assert _carve(out) == [bc.RESTAMP_CARVE_OUT_PREFIX.format(doc_rel="spec.md") + "seal promotion ([SEAL-01])"]


def test_binding_refresh_alone_migrated_names_upstream_binding_refresh(tmp_path, capsys):
    chain = fx.write_v2_chain(tmp_path, "sdd")
    _approve(tmp_path, chain["spec.md"], capsys)  # migrate the upstream: its stamp moves
    out = _bind_approve(tmp_path, chain["design.md"], capsys)
    line = _migrated_line(out)
    assert line == ["hash-basis-migrated: specs/feat-x/design.md re-stamped from basis v2 to basis v3; "
                    "no pending-review obligation written (basis-only migration with upstream binding "
                    "refresh; content otherwise unchanged)."]
    assert _marker(tmp_path) == []


def test_migration_without_refresh_omits_refresh_clause(tmp_path, capsys):
    chain = fx.write_v2_chain(tmp_path, "sdd")
    out = _bind_approve(tmp_path, chain["design.md"], capsys)  # upstream unchanged: same bindings
    assert _migrated_line(out) == ["hash-basis-migrated: specs/feat-x/design.md re-stamped from basis v2 to "
                                   "basis v3; no pending-review obligation written (basis-only migration; "
                                   "content otherwise unchanged)."]


def test_plan_cfc_subblock_refresh_names_producer_refresh(tmp_path, capsys):
    chain = fx.write_v2_chain(tmp_path, "blueprint")
    out = _approve(tmp_path, chain["PLAN.md"], capsys, "blueprint")
    assert "CFC Content Hashes" in chain["PLAN.md"].read_text(encoding="utf-8")
    line = _migrated_line(out)
    assert len(line) == 1 and "with producer refresh" in line[0] and "upstream binding refresh" not in line[0]
    assert _marker(tmp_path) == []


def test_v3_verifying_v2_with_binding_refresh_takes_carve_out(tmp_path, capsys):
    """AC-3.12 converse: nothing to migrate, so the binding refresh goes to the
    classifier, which names it (and the basis change) — no migration line."""
    p = tmp_path / "design.md"
    text = _relabel(_NO_TABLE, "v2")
    p.write_text(_restamp(text, ch.compute_content_hash_v2(text)), encoding="utf-8")
    _upstream_spec(tmp_path, "0123456789abcdef")
    out = _bind_approve(tmp_path, p, capsys)
    assert _migrated_line(out) == []
    assert _carve(out) == [bc.RESTAMP_CARVE_OUT_PREFIX.format(doc_rel="design.md")
                           + "upstream binding refresh; hash basis v2 → v3"]
    assert _marker(tmp_path) == []


def test_open_obligation_migration_r9_preserve_keeps_obligation(tmp_path, capsys):
    """AC-3.11 / design SEAL-10: a pure migration with an obligation already
    open keeps it open with its closing condition preserved."""
    import run_state as rs

    chain = fx.write_v2_chain(tmp_path, "sdd")
    spec = chain["spec.md"]
    d = spec.parent
    pr.upsert_pending_entry(tmp_path, "specs/feat-x/spec.md", "a" * 16, "2026-11-01T00:00:00Z", 1)
    before = __import__("json").loads((tmp_path / ".sdd" / "pending-review.json").read_text())
    # validator
    result = bc.ValidationResult()
    bc.check_previous_phase_approved(d, "design", result, {"design": "spec.md"})
    assert _fails(result)["previous phase (spec.md) hash basis is current"].startswith("HASH-BASIS-MIGRATION:")
    # --run-state
    state = rs.derive_run_state(tier="sdd", artifact_dir=d, project_root=tmp_path,
                                phases=[("Specify", "spec.md"), ("Design", "design.md"), ("Tasks", "tasks.md")],
                                terminal_phase_label="Implement", tick_hint_artifact="tasks.md")
    assert next(a for a in state.artifacts if a.name == "spec.md").hash_status == rs.HashStatus.STALE_MIGRATION
    assert any("spec.md" in o.detail for o in state.obligations)
    # --approve
    out = _approve(tmp_path, spec, capsys)
    text = spec.read_text(encoding="utf-8")
    assert text.count("- **Hash basis:** v3") == 1 and bc.read_stored_hash(text) == ch.compute_content_hash(text)
    assert any(ln.startswith("r9-preserve:") for ln in out.splitlines())
    assert _migrated_line(out) == []
    after = __import__("json").loads((tmp_path / ".sdd" / "pending-review.json").read_text())
    assert after["pending"]["specs/feat-x/spec.md"]["hash"] == before["pending"]["specs/feat-x/spec.md"]["hash"]


def test_predicate_exception_with_binding_refresh_falls_to_classifier(tmp_path, capsys, monkeypatch):
    """Design SEAL-15: if the predicate raises, the classifier arm decides, as
    in v2.28.0 — a binding-refresh-only delta is still marker-free."""
    chain = fx.write_v2_chain(tmp_path, "sdd")
    _approve(tmp_path, chain["spec.md"], capsys)

    def boom(**k):
        raise RuntimeError("boom")

    monkeypatch.setattr(pr, "is_pure_basis_migration", boom)
    out = _bind_approve(tmp_path, chain["design.md"], capsys)
    assert _migrated_line(out) == []
    assert _carve(out) == [bc.RESTAMP_CARVE_OUT_PREFIX.format(doc_rel="specs/feat-x/design.md")
                           + "upstream binding refresh; hash basis v2 → v3"]
    assert _marker(tmp_path) == []


def test_restamp_delta_fields_unchanged():
    import dataclasses

    assert [f.name for f in dataclasses.fields(pr.RestampDelta)] == ["promoted_seals", "binding_refresh", "repad"]


# ---------------------------------------------------------------------------
# Bound-chain walk and read-path agreement, end to end (T19)
# ---------------------------------------------------------------------------

_CHAIN = {
    "sdd": (("spec.md", "design.md", "tasks.md"),
            _SKILLS / "spec-driven-dev" / "scripts" / "validate_spec.py"),
    "blueprint": (("SCOPE.md", "ARCHITECTURE.md", "PLAN.md"),
                  _SKILLS / "project-blueprint" / "scripts" / "validate_blueprint.py"),
}


def _tier_approve(root: Path, p: Path, tier: str, capsys) -> str:
    """The tier's in-process re-approval, writing upstream bindings (what the
    validator's --approve does after its structural gate)."""
    bare = bc.strip_artifact_prefix(p.name)
    if bare not in bc.UPSTREAM_SETS:
        return _approve(root, p, capsys, tier)
    capsys.readouterr()
    writes = bc.ApprovalWrites(bindings=bc.collect_upstream_bindings(p.parent, bare),
                               judged_hash=bc.judged_text_hash(p.read_text(encoding="utf-8")))
    assert fx._load_validator(tier).approve_document(p, project_root=root, approval_writes=writes) \
        if tier == "blueprint" else bc.approve_document(
            p, project_root=root, content_transform=bc.compose_content_transforms(
                lambda c, f: bc.verify_judged_transform(c, f, writes=writes),
                lambda c, f: bc.apply_approval_writes(c, f, writes=writes)))
    return capsys.readouterr().out


def _run_state(tier: str, d: Path, root: Path):
    import run_state as rs

    names, _script = _CHAIN[tier]
    labels = (("Specify", "Design", "Tasks") if tier == "sdd" else ("Scope", "Architecture", "Plan"))
    return rs.derive_run_state(
        tier=tier, artifact_dir=d, project_root=root, phases=list(zip(labels, names)),
        terminal_phase_label="Implement" if tier == "sdd" else None,
        tick_hint_artifact="tasks.md" if tier == "sdd" else None,
    )


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_bound_chain_walk_marker_free(tmp_path, capsys, tier):
    """AC-3.9: migrate the upstream; the downstream then reports its binding as
    superseded (newer-stamp) and an upstream-drift obligation until re-approved,
    and its re-approval is a marker-free migration with refreshed bindings."""
    (up, down, _third), _script = _CHAIN[tier]
    chain = fx.write_v2_chain(tmp_path, tier)
    d = chain[up].parent
    _tier_approve(tmp_path, chain[up], tier, capsys)
    result = bc.ValidationResult()
    bc.check_upstream_bindings(d, down, chain[down].read_text(encoding="utf-8"), result)
    fail = _fails(result)[f"{down} upstream binding current"]
    assert "newer-stamp" in fail
    drift = [o for o in _run_state(tier, d, tmp_path).obligations if o.kind == "upstream-drift"]
    assert any(down in o.detail for o in drift)
    out = _tier_approve(tmp_path, chain[down], tier, capsys)
    text = chain[down].read_text(encoding="utf-8")
    assert text.count("- **Hash basis:** v3") == 1 and bc.read_stored_hash(text) == ch.compute_content_hash(text)
    assert bc.read_bindings(text)[up] == (bc.read_stored_hash(chain[up].read_text(encoding="utf-8")),)
    assert _marker(tmp_path) == [] and _REMINDER_LINE not in out
    assert len(_migrated_line(out)) == 1


@pytest.mark.parametrize("tier", ["sdd", "blueprint"])
def test_run_state_cli_chain_stale_migration_then_all_clear(tmp_path, capsys, tier):
    names, script = _CHAIN[tier]
    chain = fx.write_v2_chain(tmp_path, tier)
    d = chain[names[0]].parent

    def cli():
        r = subprocess.run([sys.executable, str(script), str(d), "--run-state", "--project-root", str(tmp_path)],
                           capture_output=True, text=True)
        assert r.returncode == 0 and "Traceback" not in r.stderr, r.stderr
        return r.stdout

    before = cli()
    assert all(f"{n}: STALE_MIGRATION" in before for n in names)
    for n in names:
        _tier_approve(tmp_path, chain[n], tier, capsys)
    after = cli()
    assert "all clear" in after
    assert not re.search(r"^\s+\S+\.md: (STALE|STALE_MIGRATION)\b", after, re.MULTILINE), after
    assert _marker(tmp_path) == []


def test_plan_cfc_refresh_non_migration_takes_classifier_path(tmp_path, capsys):
    """AC-3.9's last sentence / design SEAL-27: a PLAN.md whose pre-refresh
    content is NOT a pure migration (here a seal promotion) and whose per-CFC
    sub-block refreshes at re-approval takes the classifier path, which does not
    recognise the producer delta — so a marker is created, as in v2.28.0."""
    import test_seal_promotion_restamp as sp

    chain = fx.write_v2_chain(tmp_path, "blueprint")
    plan = chain["PLAN.md"]
    sp._add_latest(plan, sp._seal())
    sp._archive(plan)
    trimmed = tr.trim_trajectory_table(plan.read_text(encoding="utf-8"))
    assert not _pure(plan.read_text(encoding="utf-8"))
    assert "CFC Content Hashes" not in trimmed  # the approve will add the sub-block
    out = _approve(tmp_path, plan, capsys, "blueprint")
    assert _migrated_line(out) == [] and "restamp-carve-out:" not in out
    assert _marker(tmp_path) == ["blueprint/PLAN.md"] and _REMINDER_LINE in out


@pytest.mark.parametrize("case", ["v2_coherent", "v1_coherent", "ac_3_4_repadded"])
def test_unmigrated_artifacts_agree_across_read_paths_validator_run_state(tmp_path, case):
    """AC-3.6 / AC-3.7: every surface agrees about each unmigrated artifact."""
    import run_state as rs

    text = {"v2_coherent": lambda: _restamp(_doc(basis="v2", header_pad=3),
                                            ch.compute_content_hash_v2(_doc(basis="v2", header_pad=3))),
            "v1_coherent": _v1_coherent, "ac_3_4_repadded": _ac_3_4_repadded}[case]()
    coherent = case != "ac_3_4_repadded"
    assert set(_read_paths(tmp_path / "r", text).values()) == {coherent}
    fails = _fails(_prev_check(tmp_path, "spec.md", text))
    assert ("previous phase (spec.md) hash basis is current" in fails) is coherent
    assert ("previous phase (spec.md) has not been modified since approval" in fails) is (not coherent)
    assert rs._classify_hash(text) == (rs.HashStatus.STALE_MIGRATION if coherent else rs.HashStatus.STALE)


# ---------------------------------------------------------------------------
# AC-6.4 stale-prose pin (T24, design DEF-01)
# ---------------------------------------------------------------------------

STALE_CURRENT_BASIS_PHRASES = (
    "STRICT v2",
    "the v2 strip removes every tag",
    "v1->v2 basis",
    "re-stamped to basis v2",
    "Under basis v2 the approval hash",
    "stored hash no longer matches under v2",
)


def _sweep_files() -> list:
    root = _SCRIPTS.parent
    files = [p for p in root.rglob("*") if p.suffix in (".py", ".md")
             and "/tests/" not in p.as_posix() and p.name != "CHANGELOG.md"]
    return files + [root.parent / "CLAUDE.md"]


@pytest.mark.parametrize("phrase", STALE_CURRENT_BASIS_PHRASES)
def test_no_stale_current_basis_phrases(phrase):
    hits = [str(p) for p in _sweep_files() if phrase in p.read_text(encoding="utf-8")]
    assert hits == [], hits
