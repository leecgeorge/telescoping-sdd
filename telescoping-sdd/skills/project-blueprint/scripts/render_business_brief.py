"""Phase 4 — Business Brief renderer for the project-blueprint skill.

Renders approved SCOPE.md, ARCHITECTURE.md, and PLAN.md documents into
three self-contained HTML files (scope.html, architecture.html, plan.html)
under `<blueprint-dir>/business-brief/`.

Invoked by the project-blueprint skill after PLAN approval, or directly
from the command line against any blueprint directory whose three artifacts
are all approved.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
_VALIDATE_DIR = Path(__file__).resolve().parent

sys.path.append(str(_SHARED_SCRIPTS))
sys.path.append(str(_VALIDATE_DIR))

import argparse  # noqa: E402
import base64  # noqa: E402
import html  # noqa: E402
import re  # noqa: E402

import blueprint_common  # noqa: E402  (artifact NN_-prefix resolution)
import shlex  # noqa: E402
import string  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from html.parser import HTMLParser  # noqa: E402
from urllib.parse import urlparse  # noqa: E402

from blueprint_common import verify_content_hash_any_basis  # noqa: E402
from validate_blueprint import approval_hash, has_approval  # noqa: E402


_ARTIFACTS = (
    ("SCOPE.md", "scope"),
    ("ARCHITECTURE.md", "architecture"),
    ("PLAN.md", "plan"),
)

_MARKDOWN_FLOOR = "3.4"
_BLEACH_FLOOR = "6.0"
_BLEACH_CEILING = "7.0"


def _installed_markdown_version() -> str:
    """Return the installed `markdown` library's version string.

    Thin wrapper around `importlib.metadata.version("markdown")` so tests
    can monkeypatch this symbol directly (per AD9).
    """
    from importlib.metadata import version

    return version("markdown")


def _installed_bleach_version() -> str:
    """Return the installed `bleach` library's version string. Monkeypatchable
    twin of `_installed_markdown_version` (per AD9 + P2-4 runtime version check)."""
    from importlib.metadata import version

    return version("bleach")


def check_markdown_dependency(script_path: str, blueprint_dir_arg: str) -> None:
    """Verify `markdown>=3.4` and `bleach>=6.0,<7.0` are importable and
    version-compliant.

    On any failure, prints the committed R3 error shape to stderr — naming
    both packages, pointing at `requirements.txt`, and quoting the user-supplied
    `blueprint_dir_arg` so the copy-pasteable re-run command is shell-safe
    — and exits 1.
    """
    script_dir = Path(__file__).resolve().parent
    blueprint_quoted = shlex.quote(blueprint_dir_arg)
    script_quoted = shlex.quote(script_path)

    def _fail() -> None:
        msg = (
            f"Phase 4 requires markdown>={_MARKDOWN_FLOOR} and "
            f"bleach>={_BLEACH_FLOOR},<{_BLEACH_CEILING}. "
            f"Install with: pip install -r {script_dir}/requirements.txt, "
            f"then re-run: python {script_quoted} {blueprint_quoted}"
        )
        print(msg, file=sys.stderr)
        sys.exit(1)

    try:
        from packaging.version import Version
    except ImportError:
        _fail()
        return  # _fail exits; this satisfies type-checkers

    try:
        import markdown  # noqa: F401
    except ImportError:
        _fail()

    try:
        import bleach  # noqa: F401
    except ImportError:
        _fail()

    try:
        installed_md = Version(_installed_markdown_version())
    except Exception:
        _fail()
        return

    if installed_md < Version(_MARKDOWN_FLOOR):
        _fail()

    try:
        installed_bleach = Version(_installed_bleach_version())
    except Exception:
        _fail()
        return

    if installed_bleach < Version(_BLEACH_FLOOR) or installed_bleach >= Version(_BLEACH_CEILING):
        _fail()


_REQUIRED_ARTIFACTS = ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md")


def validate_blueprint_dir(path_arg: str) -> Path:
    """Resolve `path_arg` and assert SCOPE / ARCHITECTURE / PLAN are present.

    On failure, prints one of the committed R4 error shapes to stderr and
    calls sys.exit(1). On success, returns the resolved blueprint Path.
    """
    if "\n" in path_arg or "\r" in path_arg:
        print(f"{path_arg!r}: path contains newline characters", file=sys.stderr)
        sys.exit(1)
    p = Path(path_arg)
    if not p.exists():
        print(f"{path_arg}: not found", file=sys.stderr)
        sys.exit(1)
    if not p.is_dir():
        print(f"{path_arg}: not a directory", file=sys.stderr)
        sys.exit(1)
    try:
        missing = [
            name for name in _REQUIRED_ARTIFACTS
            if not blueprint_common.resolve_artifact(p, name).is_file()
        ]
    except blueprint_common.ArtifactAmbiguityError as exc:
        print(f"{path_arg}: {exc}", file=sys.stderr)
        sys.exit(1)
    if missing:
        print(
            f"{path_arg}: missing required artifacts: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)
    return p.resolve()


# ---------------------------------------------------------------------------
# Content filter (C5)
# ---------------------------------------------------------------------------

_FILTER_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n", re.DOTALL)
_FILTER_PANEL_REVIEW_SECTION = re.compile(
    r"^## Panel Review[ \t]*\r?$.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL
)
_FILTER_APPROVAL_SECTION = re.compile(
    r"^## Approval[ \t]*\r?$.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL
)
_FILTER_INLINE_TOKENS = re.compile(r" ?\[(SEAL|DEF|SCOPE|ARCH|CFC)-\d+\]")
_FILTER_CONTENT_HASH = re.compile(r"\*\*Content Hash:\*\*[ \t]*`[0-9a-f]{16}`")


def filter_content(content: str) -> str:
    """Strip workflow-internal material per R2 (frontmatter, Panel Review,
    Approval, inline `[TAG-NN]` tokens, `**Content Hash:** ...`).

    Ordering contract:
      1. _FILTER_FRONTMATTER
      2. _FILTER_PANEL_REVIEW_SECTION
      3. _FILTER_APPROVAL_SECTION
      4. _FILTER_INLINE_TOKENS
      5. _FILTER_CONTENT_HASH

    Rules 1-3 are order-required (structural regions before in-prose strips).
    Rules 4 and 5 are order-independent on canonical input — documented here
    rather than over-claimed.
    """
    out = _FILTER_FRONTMATTER.sub("", content)
    out = _FILTER_PANEL_REVIEW_SECTION.sub("", out)
    out = _FILTER_APPROVAL_SECTION.sub("", out)
    out = _FILTER_INLINE_TOKENS.sub("", out)
    out = _FILTER_CONTENT_HASH.sub("", out)
    return out


# ---------------------------------------------------------------------------
# Brand-logo loader (C10)
# ---------------------------------------------------------------------------

_LOGO_ASSET_PATH = _VALIDATE_DIR / "assets" / "neon-ghost-logo.png"
_LOGO_DATA_URL_MAX_BYTES = 200_000
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _load_logo_img_tag(logo_path: Path | None = None) -> str:
    """Read the brand-logo PNG, base64-encode, return `<img>` tag substring.

    Called ONCE per `render_all` invocation (NOT at module import time).
    Graceful degradation: on any read failure (missing, directory, permission,
    OS error, non-PNG content) prints a stderr warning and returns the empty
    string. Symlinks are followed via `resolve()` so the warning names the
    final target.
    """
    path = (logo_path if logo_path is not None else _LOGO_ASSET_PATH)
    try:
        resolved = path.resolve()
        raw = resolved.read_bytes()
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError):
        print(
            f"WARNING: brand logo not found or unreadable at "
            f"{path}; rendering without logo",
            file=sys.stderr,
        )
        return ""
    if not raw.startswith(_PNG_MAGIC):
        print(
            f"WARNING: brand logo at {path} is not a PNG "
            f"(magic bytes missing); rendering without logo",
            file=sys.stderr,
        )
        return ""
    if len(raw) > _LOGO_DATA_URL_MAX_BYTES:
        print(
            f"WARNING: brand logo at {path} is {len(raw)} bytes, exceeding the "
            f"{_LOGO_DATA_URL_MAX_BYTES}-byte data-URL cap (base64 would inflate "
            f"each rendered file by ~4/3 of that); rendering without logo",
            file=sys.stderr,
        )
        return ""
    encoded = base64.b64encode(raw).decode("ascii")
    return (
        f'<img alt="Neon Ghost" class="brand-logo" '
        f'src="data:image/png;base64,{encoded}">'
    )


# ---------------------------------------------------------------------------
# Project-name resolver (C8)
# ---------------------------------------------------------------------------

_MAX_PROJECT_NAME_LEN = 200
_H1_PROJECT_PREFIX_RE = re.compile(r"^Project:\s+")
_H1_EMPHASIS_CHARS = "*_`"
_PLACEHOLDER_PROJECT_NAME = "Project Name"


def _normalize_project_name(name: str) -> str:
    """Defensive normalization: newlines → space; `--+` → `-`; collapse
    whitespace; strip; cap to _MAX_PROJECT_NAME_LEN."""
    if not name:
        return ""
    out = name.replace("\r", " ").replace("\n", " ")
    out = re.sub(r"-{2,}", "-", out)
    out = re.sub(r"\s+", " ", out)
    out = out.strip()
    if len(out) > _MAX_PROJECT_NAME_LEN:
        out = out[:_MAX_PROJECT_NAME_LEN]
    return out


def _extract_scope_h1(scope_content: str) -> str:
    """Tier-2 cascade input: first H1 in SCOPE.md with `Project: ` prefix
    stripped and emphasis chars (`* _ \\``) stripped. Returns '' if the H1
    is absent, equal to the literal placeholder `Project Name`, or empty
    after normalization."""
    if not scope_content:
        return ""
    m = re.search(r"^# (.+)$", scope_content, re.MULTILINE)
    if not m:
        return ""
    raw = m.group(1)
    # Strip emphasis chars FIRST so a `**Project: Foo**` H1 collapses to
    # `Project: Foo` and is then prefix-stripped below.
    for ch in _H1_EMPHASIS_CHARS:
        raw = raw.replace(ch, "")
    # Strip the literal `Project: ` prefix (requires whitespace after colon).
    raw = _H1_PROJECT_PREFIX_RE.sub("", raw, count=1)
    raw = raw.strip()
    if raw == _PLACEHOLDER_PROJECT_NAME:
        return ""
    return raw


def resolve_project_name(
    blueprint_dir: Path, scope_content: str, override: str | None
) -> str:
    """Four-tier cascade (per AD7):
      1. `override` (if not None and non-empty after normalization)
      2. SCOPE.md first H1 (with prefix/emphasis strip)
      3. `blueprint_dir.resolve().parent.name`
      4. 'Untitled Project' (with stderr warning)
    """
    # Tier 1: explicit override
    if override is not None:
        norm = _normalize_project_name(override)
        if norm:
            return norm
    # Tier 2: SCOPE H1
    h1 = _normalize_project_name(_extract_scope_h1(scope_content))
    if h1:
        return h1
    # Tier 3: parent dir basename
    basename = _normalize_project_name(blueprint_dir.resolve().parent.name)
    if basename:
        return basename
    # Tier 4: fallback + warning
    print(
        "WARNING: could not resolve project name from SCOPE H1, blueprint "
        "parent dir, or --project-name; using 'Untitled Project'",
        file=sys.stderr,
    )
    return "Untitled Project"


def write_output(output_dir: Path, filename: str, html_str: str) -> Path:
    """Write `html_str` to `output_dir/filename` as UTF-8 bytes (silent overwrite).

    Creates `output_dir` (and parents) if absent. Returns the resolved
    output path. On OSError (disk full, permission denied, read-only FS),
    prints a stderr message naming the path and the OS error code, then
    exits 1 (no traceback).
    """
    output_path = output_dir / filename
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(html_str.encode("utf-8"))
    except OSError as exc:
        print(
            f"{output_path}: write failed: {exc.strerror or exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    return output_path.resolve()


# ---------------------------------------------------------------------------
# HTML renderer (C6)
# ---------------------------------------------------------------------------

_ALLOWED_TAGS = frozenset({
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "code", "pre", "blockquote",
    "ul", "ol", "li",
    "a",
    "table", "thead", "tbody", "tr", "th", "td",
    "div", "span",
})

# NOTE: `img` is intentionally absent. The only permitted <img> in rendered
# output is the brand logo, injected via the $logo template placeholder AFTER
# bleach runs (see _HTML_TEMPLATE). Allowing `img` here would let any author
# `![Diagram](http://...)` smuggle an external image URL into the brief and
# defeat R4's self-contained promise.
_ALLOWED_ATTRS = {
    "a": ["href", "title", "rel"],
    "*": ["id", "class"],
}

_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

# Pre-bleach strip for tag-and-content rawtext elements. Bleach with
# strip=True removes the tag but preserves text content; the design
# commits "zero visible alert(1) text" for `<script>`/`<style>`-class
# elements, so we drop them outright before bleach runs.
_RAWTEXT_TAGS_STRIP = re.compile(
    r"<\s*(script|style|noscript|noembed|noframes|iframe|svg|math|object|embed|form)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_VOID_RAWTEXT_TAGS_STRIP = re.compile(
    r"<\s*(script|style|noscript|noembed|noframes|iframe|svg|math|object|embed|form|base|meta|link)\b[^>]*/?\s*>",
    re.IGNORECASE,
)

# Upper bound on rawtext-strip fixed-point iterations. 8 is generous: real
# nested-mutation payloads converge in 2-3 passes; the cap exists to prevent
# pathological backtracking on adversarial input rather than to limit normal
# convergence.
_RAWTEXT_STRIP_MAX_ITERATIONS = 8

_CSS = """:root { --bg: #ffffff; --fg: #1a1a1a; --link: #1450a3; }
body {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 16px;
  line-height: 1.5;
  color: var(--fg);
  background: var(--bg);
  margin: 0;
  padding: 0;
}
main {
  max-width: 70ch;
  margin: 2rem auto;
  padding: 0 1rem;
}
h1, h2, h3, h4, h5, h6 { color: #111111; }
a { color: var(--link); }
code, pre {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: #f3f3f3;
}
code { padding: 0.1rem 0.3rem; border-radius: 3px; }
pre { padding: 0.75rem; overflow-x: auto; }
pre code { background: transparent; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border-bottom: 1px solid #cccccc; padding: 0.5rem; text-align: left; }
th { background: #f9f9f9; font-weight: 600; }
blockquote {
  border-left: 3px solid #cccccc;
  margin: 0;
  padding: 0.25rem 0 0.25rem 1rem;
  color: #444444;
}
footer {
  position: relative;
  max-width: 70ch;
  margin: 3rem auto 2rem;
  padding: 1.5rem 1rem;
  border-top: 1px solid #dddddd;
  color: #555555;
  font-size: 0.875rem;
}
.brand { margin-bottom: 0.75rem; }
.brand-logo {
  max-width: 200px;
  max-height: 100px;
  height: auto;
  width: auto;
}
"""


# NOTE: this template contains an em-dash (U+2014) and middle-dot (U+00B7).
# Test suite asserts on the exact characters; do not replace with ASCII `--`
# or `-` without updating the matching tests in test_render_business_brief.py.
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="$lang">
<head>
<meta charset="utf-8">
<meta name="generator" content="render_business_brief.py">
<title>$title · Business Brief · $project_name</title>
<style>$css</style>
<!-- Derived artifact — do not hand-edit. Regenerate via render_business_brief.py. -->
</head>
<body>
<main>
$body
</main>
<footer>
<div class="brand">$logo</div>
<p>$project_name · Business Brief · Rendered $render_ts</p>
<p>Generated artifact — edits made directly to this HTML will be lost on re-render. Ask the project engineer to update the source markdown instead.</p>
</footer>
</body>
</html>"""


class _ExternalLinkHardener(HTMLParser):
    """HTML-aware walker that adds rel='noopener noreferrer' to http/https
    anchors. Does NOT modify anchors inside <code> or <pre> blocks. Idempotent."""

    _VOID = frozenset({
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    })

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        self._code_depth = 0

    def get_output(self) -> str:
        return "".join(self._parts)

    @staticmethod
    def _format_tag(tag: str, attrs, *, self_closing: bool) -> str:
        rendered = [tag]
        for name, value in attrs:
            if value is None:
                rendered.append(name)
            else:
                rendered.append(f'{name}="{html.escape(value, quote=True)}"')
        body = " ".join(rendered)
        return f"<{body} />" if self_closing else f"<{body}>"

    @staticmethod
    def _harden_anchor_attrs(attrs):
        href = None
        existing_rel = None
        for name, value in attrs:
            if name == "href" and href is None:
                href = value
            elif name == "rel" and existing_rel is None:
                existing_rel = value
        if not href:
            return attrs
        scheme = urlparse(href.strip()).scheme.lower()
        if scheme not in ("http", "https"):
            return attrs
        existing_tokens = existing_rel.split() if existing_rel else []
        new_tokens = list(existing_tokens)
        for needed in ("noopener", "noreferrer"):
            if needed not in new_tokens:
                new_tokens.append(needed)
        new_rel = " ".join(new_tokens)
        out, rel_set = [], False
        for name, value in attrs:
            if name == "rel":
                out.append((name, new_rel))
                rel_set = True
            else:
                out.append((name, value))
        if not rel_set:
            out.append(("rel", new_rel))
        return out

    def handle_starttag(self, tag, attrs):
        if tag in ("code", "pre"):
            self._code_depth += 1
        emit_attrs = attrs
        if tag == "a" and self._code_depth == 0:
            emit_attrs = self._harden_anchor_attrs(attrs)
        self._parts.append(self._format_tag(tag, emit_attrs, self_closing=False))

    def handle_startendtag(self, tag, attrs):
        emit_attrs = attrs
        if tag == "a" and self._code_depth == 0:
            emit_attrs = self._harden_anchor_attrs(attrs)
        # Use void-element form for void tags; self-closing form otherwise.
        if tag in self._VOID:
            self._parts.append(self._format_tag(tag, emit_attrs, self_closing=False))
        else:
            self._parts.append(self._format_tag(tag, emit_attrs, self_closing=True))

    def handle_endtag(self, tag):
        if tag in ("code", "pre") and self._code_depth > 0:
            self._code_depth -= 1
        self._parts.append(f"</{tag}>")

    def handle_data(self, data):
        self._parts.append(data)

    def handle_entityref(self, name):
        self._parts.append(f"&{name};")

    def handle_charref(self, name):
        self._parts.append(f"&#{name};")

    def handle_comment(self, data):
        self._parts.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        self._parts.append(f"<!{decl}>")

    def handle_pi(self, data):
        self._parts.append(f"<?{data}>")

    def unknown_decl(self, data):
        self._parts.append(f"<![{data}]>")


def _harden_external_links(html_str: str) -> str:
    """Inject rel='noopener noreferrer' on http/https anchors via HTMLParser."""
    parser = _ExternalLinkHardener()
    parser.feed(html_str)
    parser.close()
    return parser.get_output()


def render_to_html(
    md_content: str,
    title: str,
    project_name: str,
    render_ts: str,
    logo_img_tag: str = "",
    lang: str = "en",
) -> str:
    """Convert filtered markdown to a complete, sanitized HTML document.

    Pipeline: markdown → bleach.clean (strip=True) → link-hardening →
    string.Template.safe_substitute into _HTML_TEMPLATE.
    """
    import bleach
    import markdown as md_lib

    md_converter = md_lib.Markdown(extensions=["tables", "fenced_code", "toc"])
    raw_body = md_converter.convert(md_content)

    # Pre-bleach: drop rawtext tags AND their content (bleach's strip=True
    # keeps content of script/style/iframe-class tags; the design contract
    # forbids that visible text leak).
    #
    # Two-stage strategy:
    #   1. Loop _RAWTEXT_TAGS_STRIP (closed-form shapes like `<script>x</script>`)
    #      to a fixed point with a small iteration cap. A single re.sub pass is
    #      bypassable by nested mutation — e.g. `<sc<script></script>ript>x</script>`
    #      where the inner match synthesises a valid outer that the same regex
    #      running once would never re-scan. Iterating until the string stops
    #      changing closes this class of bypass; the cap prevents catastrophic
    #      backtracking on adversarial input.
    #   2. Once the form-shape loop has converged, run _VOID_RAWTEXT_TAGS_STRIP
    #      ONCE to remove orphan rawtext-class openings (`<meta>`, `<base>`,
    #      `<link>`, and unclosed `<script>`/`<style>`). The void strip runs
    #      after the loop — not inside it — because it removes only the opening
    #      tag, leaving content behind, which would prematurely break the loop's
    #      ability to clean up synthesised outer tags from the loop step.
    rawtext_stripped = raw_body
    for _ in range(_RAWTEXT_STRIP_MAX_ITERATIONS):
        next_pass = _RAWTEXT_TAGS_STRIP.sub("", rawtext_stripped)
        if next_pass == rawtext_stripped:
            break
        rawtext_stripped = next_pass
    rawtext_stripped = _VOID_RAWTEXT_TAGS_STRIP.sub("", rawtext_stripped)

    sanitized = bleach.clean(
        rawtext_stripped,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    hardened = _harden_external_links(sanitized)

    return string.Template(_HTML_TEMPLATE).safe_substitute(
        title=html.escape(title, quote=True),
        project_name=html.escape(project_name, quote=True),
        render_ts=html.escape(render_ts, quote=True),
        css=_CSS,
        body=hardened,
        logo=logo_img_tag,
        lang=html.escape(lang, quote=True),
    )


# ---------------------------------------------------------------------------
# Render orchestrator (C9) + render-timestamp injection point (AD14)
# ---------------------------------------------------------------------------


def _get_render_ts() -> str:
    """Return the current UTC render timestamp in `YYYY-MM-DD HH:MM UTC` format.

    Monkeypatchable: tests patch this symbol directly to assert identical
    timestamp invariants across all three output files.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


_RENDER_TARGETS = (
    ("Scope", "scope.html"),
    ("Architecture", "architecture.html"),
    ("Plan", "plan.html"),
)

# Drift guard (P3-14): _RENDER_TARGETS and _ARTIFACTS must stay in phase order.
# If a future change reorders one without the other, output files would be
# written from the wrong source. Caught at module load.
assert tuple(out.removesuffix(".html") for _, out in _RENDER_TARGETS) == tuple(
    phase for _, phase in _ARTIFACTS
), "render_business_brief: _RENDER_TARGETS / _ARTIFACTS phase ordering drift"


def render_all(
    blueprint_dir: Path,
    project_name: str,
    render_ts: str,
    scope_content: str,
    arch_content: str,
    plan_content: str,
    logo_path: Path | None = None,
    lang: str = "en",
) -> list[Path]:
    """Run the full filter → render → write pipeline for all three artifacts.

    Loads the brand-logo `<img>` substring ONCE at the start (per C10's
    single-load contract) and interpolates the same string into all three
    output files. Returns the three output paths in the guaranteed positional
    order [scope.html, architecture.html, plan.html].

    `logo_path` overrides the default `_LOGO_ASSET_PATH` (used by --logo).
    """
    output_dir = blueprint_dir / "business-brief"
    logo_img_tag = _load_logo_img_tag(logo_path)
    sources = (scope_content, arch_content, plan_content)
    paths: list[Path] = []
    for (title, filename), src in zip(_RENDER_TARGETS, sources):
        filtered = filter_content(src)
        rendered = render_to_html(
            md_content=filtered,
            title=title,
            project_name=project_name,
            render_ts=render_ts,
            logo_img_tag=logo_img_tag,
            lang=lang,
        )
        paths.append(write_output(output_dir, filename, rendered))
    return paths


# ---------------------------------------------------------------------------
# CLI entry point (C1)
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render_business_brief.py",
        description=(
            "Render approved SCOPE.md / ARCHITECTURE.md / PLAN.md into three "
            "self-contained HTML files (Phase 4 of project-blueprint)."
        ),
    )
    parser.add_argument(
        "blueprint_dir",
        help="Path to the blueprint directory containing the three .md artifacts.",
    )
    parser.add_argument(
        "--project-name",
        default=None,
        help=(
            "Override the auto-resolved project name (tier 1 of the cascade). "
            "Recommended for externally-shared briefs."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Run the full pipeline (approval gate, filter, render) without "
            "writing any output files. Prints the paths that would be "
            "written to stdout. Useful for previewing on read-only filesystems "
            "or in CI."
        ),
    )
    parser.add_argument(
        "--logo",
        default=None,
        metavar="PATH",
        help=(
            "Override the default brand-logo PNG path. Used by third-party "
            "redistributors who want their own branding instead of Neon Ghost."
        ),
    )
    parser.add_argument(
        "--lang",
        default="en",
        metavar="BCP47",
        help=(
            "BCP-47 language tag for the rendered HTML `<html lang=...>` "
            "attribute (default: en). Set when the brief content is authored "
            "in another language so assistive tech announces it correctly."
        ),
    )
    return parser


def check_upstream_approvals(
    scope_content: str, arch_content: str, plan_content: str
) -> None:
    """Verify SCOPE, ARCHITECTURE, and PLAN are approved with matching hashes.

    Fail-fast in declaration order [SCOPE, ARCHITECTURE, PLAN]. On any failure
    prints a message of the committed shape to stderr and calls sys.exit(1).
    """
    contents = (scope_content, arch_content, plan_content)
    for (filename, phase), content in zip(_ARTIFACTS, contents):
        if not has_approval(content):
            print(
                f"{filename}: unapproved — complete the panel review for {phase}",
                file=sys.stderr,
            )
            sys.exit(1)
        stored = approval_hash(content)
        if stored is None:
            print(
                f"{filename}: absent hash — run validate_blueprint.py --approve {phase}",
                file=sys.stderr,
            )
            sys.exit(1)
        if not verify_content_hash_any_basis(content, stored):
            print(
                f"{filename}: stale hash — re-run validate_blueprint.py --approve {phase}",
                file=sys.stderr,
            )
            sys.exit(1)


def _read_artifact(path: Path) -> str:
    """Read a SCOPE/ARCHITECTURE/PLAN file with friendly error on OS errors
    or undecodable bytes. Exits 1 (no traceback) on failure."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        print(f"{path}: read failed: {exc.strerror or exc}", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError as exc:
        print(
            f"{path}: not valid UTF-8 ({exc.reason} at byte {exc.start})",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    blueprint_path = validate_blueprint_dir(args.blueprint_dir)
    check_markdown_dependency(sys.argv[0], args.blueprint_dir)

    scope_md = _read_artifact(blueprint_common.resolve_artifact(blueprint_path, "SCOPE.md"))
    arch_md = _read_artifact(blueprint_common.resolve_artifact(blueprint_path, "ARCHITECTURE.md"))
    plan_md = _read_artifact(blueprint_common.resolve_artifact(blueprint_path, "PLAN.md"))

    check_upstream_approvals(scope_md, arch_md, plan_md)

    render_ts = _get_render_ts()
    project_name = resolve_project_name(blueprint_path, scope_md, args.project_name)
    logo_path = Path(args.logo) if args.logo else None

    if args.dry_run:
        output_dir = blueprint_path / "business-brief"
        for _, filename in _RENDER_TARGETS:
            print(output_dir / filename)
        return

    paths = render_all(
        blueprint_dir=blueprint_path,
        project_name=project_name,
        render_ts=render_ts,
        scope_content=scope_md,
        arch_content=arch_md,
        plan_content=plan_md,
        logo_path=logo_path,
        lang=args.lang,
    )
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()
