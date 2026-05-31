"""T6/T7/T8/T9 — write_output, project_name cascade, HTML template, CSS readability, provenance/escape, render_all orchestration.

Split from the original test_render_business_brief.py per P3-15. Shared
helpers and constants live in `common.py`; shared fixtures (tiny PNG path,
approved-triple fixtures, panel-review fixture) live in `conftest.py`.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

import string
from common import (  # type: ignore[import-not-found]
    _contrast_ratio,
    _hex_to_rgb,
)

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(_SCRIPTS_DIR))

import render_business_brief  # noqa: E402


def test_write_output_creates_directory_and_file(tmp_path):
    out_dir = tmp_path / "out"
    assert not out_dir.exists()
    p = render_business_brief.write_output(
        out_dir, "scope.html", "<html>scope</html>"
    )
    assert out_dir.is_dir()
    assert p == (out_dir / "scope.html").resolve()
    assert p.read_text(encoding="utf-8") == "<html>scope</html>"


def test_write_output_overwrites_silently(tmp_path):
    out_dir = tmp_path / "out"
    first_marker = "FIRST" + "x" * 5000
    second_marker = "SECOND_SHORT"
    p1 = render_business_brief.write_output(out_dir, "scope.html", first_marker)
    p2 = render_business_brief.write_output(out_dir, "scope.html", second_marker)
    assert p1 == p2
    written = p2.read_text(encoding="utf-8")
    assert second_marker in written
    assert "FIRST" not in written, "first-content marker leaked — overwrite failed"
    assert p2.stat().st_size == len(second_marker.encode("utf-8"))


def test_write_output_utf8_bytes(tmp_path):
    """Em-dash and smart quotes survive the round-trip as UTF-8."""
    html = "<p>Hello — world “fancy”</p>"
    p = render_business_brief.write_output(tmp_path, "scope.html", html)
    assert p.read_bytes().decode("utf-8") == html


def test_write_output_oserror_exits_cleanly(monkeypatch, tmp_path, capsys):
    """P2-9: an OSError from `write_bytes` (disk full, EROFS, EACCES, quota)
    produces a friendly `path: write failed: <reason>` message on stderr and
    exit-1 — not a raw Python traceback."""
    target_dir = tmp_path / "out"

    real_write_bytes = Path.write_bytes

    def boom(self, data):
        if self.name == "scope.html":
            raise OSError(28, "No space left on device")  # ENOSPC
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", boom)
    with pytest.raises(SystemExit) as exc:
        render_business_brief.write_output(target_dir, "scope.html", "<p>x</p>")
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "scope.html" in captured.err
    assert "write failed" in captured.err
    assert "No space left on device" in captured.err


def test_main_undecodable_artifact_exits_cleanly(
    monkeypatch, tmp_path, capsys
):
    """P2-9: a SCOPE/ARCH/PLAN file with invalid UTF-8 produces a friendly
    `path: not valid UTF-8 (...)` message — not a raw UnicodeDecodeError."""
    for name in ("SCOPE.md", "ARCHITECTURE.md", "PLAN.md"):
        (tmp_path / name).write_text("placeholder", encoding="utf-8")
    # Overwrite SCOPE with bytes that are not valid UTF-8 (lone continuation
    # byte 0x80 with no leading byte).
    (tmp_path / "SCOPE.md").write_bytes(b"\xff\xfe not utf-8 \x80 \x81")
    monkeypatch.setattr(sys, "argv", ["rbb.py", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        render_business_brief.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not valid UTF-8" in captured.err
    assert "SCOPE.md" in captured.err



@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Foo", "Foo"),
        ("Foo\nBar", "Foo Bar"),
        ("Foo--Bar", "Foo-Bar"),
        ("Foo---Bar", "Foo-Bar"),
        ("Foo----Bar", "Foo-Bar"),
        ("   Foo   ", "Foo"),
        ("  Foo   Bar  ", "Foo Bar"),
        ("Foo\r\nBar", "Foo Bar"),
        ("a\tb\t\tc", "a b c"),
        ("x" * 250, "x" * 200),
        ("   ", ""),
        ("", ""),
    ],
)
def test_normalize_project_name_parametrized(raw, expected):
    assert render_business_brief._normalize_project_name(raw) == expected


def test_resolve_project_name_tier1_explicit_override(tmp_path):
    result = render_business_brief.resolve_project_name(
        tmp_path, "# Some H1", "Explicit"
    )
    assert result == "Explicit"


def test_resolve_project_name_tier2_scope_h1(tmp_path):
    result = render_business_brief.resolve_project_name(
        tmp_path, "# My Project\n\nBody\n", None
    )
    assert result == "My Project"


def test_resolve_project_name_tier3_parent_dir_basename(tmp_path):
    sub = tmp_path / "blueprint"
    sub.mkdir()
    result = render_business_brief.resolve_project_name(sub, "", None)
    # Tier 3 uses parent of resolved blueprint; the parent of `tmp_path/blueprint`
    # is `tmp_path` whose basename is the random pytest tmp dir name.
    assert result == tmp_path.resolve().name


def test_resolve_project_name_tier4_fallback_warns(tmp_path, monkeypatch, capsys):
    """Force all three upstream tiers to be empty."""
    # blueprint_dir whose .parent.name is empty — root dir.
    monkeypatch.setattr(
        render_business_brief, "_normalize_project_name", lambda x: ""
    )
    result = render_business_brief.resolve_project_name(tmp_path, "", "anything")
    assert result == "Untitled Project"
    captured = capsys.readouterr()
    assert "Untitled Project" in captured.err


def test_resolve_project_name_empty_fall_through_integration(tmp_path):
    """Whitespace-only override falls through to tier 2."""
    result = render_business_brief.resolve_project_name(
        tmp_path, "# My Project\n\nBody\n", "   "
    )
    assert result == "My Project"


def test_resolve_project_name_h1_placeholder_falls_through(tmp_path):
    """Literal placeholder `Project Name` is treated as absent → tier 3."""
    sub = tmp_path / "blueprint"
    sub.mkdir()
    result = render_business_brief.resolve_project_name(
        sub, "# Project Name\n\nBody\n", None
    )
    assert result == tmp_path.resolve().name


@pytest.mark.parametrize(
    "h1,expected",
    [
        ("# My Project", "My Project"),
        ("# Project: My Project", "My Project"),
        ("# **Project: My Project**", "My Project"),
        ("# Project:My Project", "Project:My Project"),  # no space after colon
        ("# Project: ", None),  # empty after prefix → falls through
        ("# project: my project", "project: my project"),  # case-sensitive
    ],
)
def test_resolve_project_name_tier2_subcases_parametrized(h1, expected, tmp_path):
    sub = tmp_path / "blueprint"
    sub.mkdir()
    result = render_business_brief.resolve_project_name(sub, h1, None)
    if expected is None:
        # Empty H1 fall through → tier 3
        assert result == tmp_path.resolve().name
    else:
        assert result == expected



def test_html_template_structural_contract():
    """_HTML_TEMPLATE is a module-level string with the committed slot set."""
    tmpl = render_business_brief._HTML_TEMPLATE
    assert isinstance(tmpl, str)
    # string.Template.get_identifiers() is 3.11+; extract identifiers via the
    # public .pattern regex so this test runs on 3.9+ (this is what
    # get_identifiers() does internally — collect the named/braced groups).
    ids = {
        mo.group("named") or mo.group("braced")
        for mo in string.Template(tmpl).pattern.finditer(tmpl)
        if mo.group("named") or mo.group("braced")
    }
    assert ids == {"title", "project_name", "render_ts", "css", "body", "logo", "lang"}
    assert tmpl.startswith("<!DOCTYPE html>")
    assert tmpl.rstrip().endswith("</html>")
    assert '<div class="brand">' in tmpl
    assert '<meta name="generator"' in tmpl
    assert "Derived artifact" in tmpl


def test_html_lang_defaults_to_en_and_is_overridable():
    """`<html lang=...>` defaults to en but is set by the --lang option / lang
    arg, so a non-English brief announces its language to assistive tech
    (review finding Critic C1-5)."""
    base = dict(md_content="# X", title="T", project_name="P", render_ts="2026-01-01 00:00 UTC")
    assert '<html lang="en">' in render_business_brief.render_to_html(**base)
    assert '<html lang="fr">' in render_business_brief.render_to_html(**base, lang="fr")


def test_html_template_round_trip():
    out = render_business_brief.render_to_html(
        md_content="# Test",
        title="T",
        project_name="P",
        render_ts="2026-01-01 00:00 UTC",
    )
    assert out.startswith("<!DOCTYPE html>")
    assert out.rstrip().endswith("</html>")
    assert "<title>T · Business Brief · P</title>" in out
    # markdown's toc extension injects `id="..."` on headings
    import re as _re

    assert _re.search(r"<h1[^>]*>Test</h1>", out)
    assert "P · Business Brief · Rendered 2026-01-01 00:00 UTC" in out


def test_html_template_safe_substitute_brace_and_dollar_safety():
    """safe_substitute does not interpret {} and does not re-substitute
    user-content $identifier. Single test, mixed payloads — both safety
    properties verified once via the same mechanism.

    NOTE: markdown's fenced_code extension HTML-escapes `"`/`<`/`>` inside
    code blocks; this test pins the post-escape SUBSTRINGS, not pre-escape.
    """
    md_body = (
        "# Title\n\n"
        "```\n"
        "key foo\n"
        "{ foo: 1 }\n"
        "{{ var }}\n"
        "${HOME:-/tmp}\n"
        "print $1\n"
        "literal $title $body $project_name\n"
        "```\n"
    )
    out = render_business_brief.render_to_html(
        md_body, title="T", project_name="P", render_ts="ts"
    )
    # No exception raised — that alone proves brace + dollar safety
    # (safe_substitute does NOT raise on stray `$` or interpret `{}`)
    # Check the chars that pass through markdown un-escaped:
    for payload in [
        "{ foo: 1 }",
        "{{ var }}",
        "${HOME:-/tmp}",
        "print $1",
        "literal $title $body $project_name",
    ]:
        assert payload in out, f"missing literal payload: {payload!r}"


def test_html_template_tweak_independence(monkeypatch):
    """Body content is byte-identical regardless of scaffold layout — proves
    AD3's separation of scaffold (template) from rendered body.

    Both outputs must contain the same `<main>...</main>` content; only the
    surrounding scaffold differs.
    """
    canonical_out = render_business_brief.render_to_html(
        "# X\n\nbody", title="T", project_name="P", render_ts="ts"
    )
    minimal = (
        "<!DOCTYPE html><html><body><main>$body</main>"
        '<footer><div class="brand">$logo</div>'
        "<p>$project_name · Business Brief · Rendered $render_ts</p></footer>"
        "</body></html>"
    )
    monkeypatch.setattr(render_business_brief, "_HTML_TEMPLATE", minimal)
    minimal_out = render_business_brief.render_to_html(
        "# X\n\nbody", title="T", project_name="P", render_ts="ts"
    )
    import re as _re

    def extract_main(s):
        m = _re.search(r"<main>(.*?)</main>", s, _re.DOTALL)
        return m.group(1) if m else None

    assert extract_main(canonical_out) is not None
    # Compare body content after stripping the surrounding template whitespace
    # (the canonical template wraps `$body` in newlines; minimal does not).
    assert extract_main(canonical_out).strip() == extract_main(minimal_out).strip()



def test_css_readability_floors():
    css = render_business_brief._CSS
    # 1. Body font-size floor
    has_floor = (
        "font-size: 16px" in css
        or "font-size: 1rem" in css
        or "font-size: 12pt" in css
    )
    assert has_floor, "body font-size floor not committed"
    # 2. Max-width rule on body content (main or body)
    import re as _re

    # Look for max-width rules in 60-100ch or 700-900px range
    max_width_matches = _re.findall(
        r"max-width:\s*(\d+)(ch|px)", css
    )
    assert max_width_matches, "no max-width rule found in CSS"
    in_range = False
    for value, unit in max_width_matches:
        v = int(value)
        if (unit == "ch" and 60 <= v <= 100) or (unit == "px" and 700 <= v <= 900):
            in_range = True
            break
    assert in_range, f"no max-width rule in [60-100ch] or [700-900px]: {max_width_matches}"
    # 3. WCAG AA contrast (≥4.5:1) for body text and link colors against bg.
    # P2-1: extract from `_CSS` rather than hardcoding hex pairs, so a
    # maintainer who changes `--fg` to `#888888` (a WCAG-AA failure against
    # `#ffffff`) gets a loud failure instead of a passing test against the
    # frozen-hex pair.
    css_vars = dict(_re.findall(r"--(\w+):\s*(#[0-9a-fA-F]{3,8})", css))
    assert "bg" in css_vars and "fg" in css_vars and "link" in css_vars, (
        f"expected --bg, --fg, --link in _CSS; got: {list(css_vars.keys())}"
    )
    bg = _hex_to_rgb(css_vars["bg"])
    fg = _hex_to_rgb(css_vars["fg"])
    ratio = _contrast_ratio(fg, bg)
    assert ratio >= 4.5, (
        f"body contrast {ratio:.2f} below WCAG AA (--fg={css_vars['fg']} "
        f"on --bg={css_vars['bg']})"
    )
    link = _hex_to_rgb(css_vars["link"])
    link_ratio = _contrast_ratio(link, bg)
    assert link_ratio >= 4.5, (
        f"link contrast {link_ratio:.2f} below WCAG AA (--link={css_vars['link']} "
        f"on --bg={css_vars['bg']})"
    )


def test_css_source_no_external_url():
    import re as _re

    assert (
        _re.search(r"url\((?!data:|#)", render_business_brief._CSS) is None
    ), "external url() reference present in _CSS"


def test_self_contained_output():
    """Rendered HTML must not load anything external. The author cannot smuggle
    an external image in via markdown `![alt](http://...)`: P1-3 dropped `img`
    from `_ALLOWED_TAGS`, so the body must contain no `<img>` tags at all
    (the brand logo `<img>` lives in the footer, injected via `$logo` after
    bleach runs)."""
    import re as _re

    # Mix in every shape an author could try: external https image, external
    # http image, relative-path image. None should survive the allowlist.
    md = (
        "# Doc\n\n"
        "External https image: ![Diagram](https://example.com/diagram.png)\n\n"
        "External http image: ![Other](http://example.org/other.png)\n\n"
        "Relative image: ![Local](./img.png)\n\n"
        "Root-relative image: ![Logo](/static/logo.png)\n\n"
        "And a plain link: [link](https://example.com)\n"
    )
    out = render_business_brief.render_to_html(
        md,
        title="T",
        project_name="P",
        render_ts="ts",
        logo_img_tag=render_business_brief._load_logo_img_tag(),
    )
    assert "<link rel=\"stylesheet\"" not in out
    assert "<script src=" not in out
    assert _re.search(r"@import\s+url\(", out, _re.IGNORECASE) is None
    # @font-face url() pointing at remote — there's no @font-face at all
    assert "@font-face" not in out
    # Body must contain NO <img> tags at all (after the brand logo, which
    # lives in the footer). Strip the footer first to isolate the body.
    body_match = _re.search(r"<main>(.*?)</main>", out, _re.DOTALL)
    assert body_match, "rendered <main> body section missing"
    body = body_match.group(1)
    assert "<img" not in body, f"author-supplied <img> leaked into body: {body!r}"
    # Belt-and-braces: no external img anywhere in the document (the brand
    # logo uses a data: URL).
    for src_match in _re.finditer(r'<img[^>]*src="([^"]+)"', out):
        assert src_match.group(1).startswith("data:"), (
            f"non-data: <img src> survived: {src_match.group(0)!r}"
        )


def test_utf8_charset_and_generator_meta():
    out = render_business_brief.render_to_html(
        "# Test\n\nEm—dash and “quotes”",
        title="T",
        project_name="P",
        render_ts="ts",
    )
    assert '<meta charset="utf-8">' in out
    # No BOM at start of output bytes
    assert not out.encode("utf-8").startswith(b"\xef\xbb\xbf")
    assert '<meta name="generator" content="render_business_brief.py">' in out


def test_provenance_footer():
    out = render_business_brief.render_to_html(
        "# X", title="T", project_name="MyProj", render_ts="2026-05-21 09:00 UTC"
    )
    assert "MyProj" in out
    assert "Business Brief" in out
    import re as _re

    assert _re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", out)


def test_derived_artifact_note():
    out = render_business_brief.render_to_html(
        "# X", title="T", project_name="P", render_ts="ts"
    )
    # Footer stakeholder-readable warning
    assert "edits made directly to this HTML will be lost" in out
    # HTML head comment
    assert (
        "<!-- Derived artifact — do not hand-edit. "
        "Regenerate via render_business_brief.py. -->" in out
    )


def test_html_template_escape_of_interpolated_values_injection():
    """`--><script>...<!--` project_name: after _normalize collapses `--+→-`,
    the rendered <title> and footer must NOT contain a `<script>` tag or `-->`
    sequence (separately from the template's own intrinsic `-->` head-comment
    terminator)."""
    project_name = "--><script>alert(1)</script><!--"
    normalized = render_business_brief._normalize_project_name(project_name)
    out = render_business_brief.render_to_html(
        "# X", title="T", project_name=normalized, render_ts="ts"
    )
    # Inspect the title and footer (the two interpolation sites for project_name)
    import re as _re

    title_m = _re.search(r"<title>(.*?)</title>", out, _re.DOTALL)
    title_body = title_m.group(1)
    assert "<script>" not in title_body
    assert "-->" not in title_body
    # Footer paragraph containing the provenance line
    footer_paras = _re.findall(r"<p>([^<]*Business Brief[^<]*)</p>", out)
    assert footer_paras, "provenance footer paragraph missing"
    for paragraph in footer_paras:
        assert "<script>" not in paragraph
        assert "-->" not in paragraph


def test_html_template_escape_of_interpolated_values_apostrophe():
    """Apostrophes survive html.escape(quote=True) as `&#x27;` and render
    visibly without breaking attribute quoting."""
    normalized = render_business_brief._normalize_project_name("O'Reilly's")
    out = render_business_brief.render_to_html(
        "# X", title="T", project_name=normalized, render_ts="ts"
    )
    import re as _re

    title_m = _re.search(r"<title>(.*?)</title>", out)
    assert title_m, "title missing"
    # html.escape(quote=True) renders ' as &#x27;
    assert "&#x27;" in title_m.group(1) or "O&#39;Reilly" in title_m.group(1)


def test_html_template_escape_of_interpolated_values_dashes_collapse():
    """`name -- inside` collapses to `name - inside` via _normalize_project_name
    before reaching the template (defends against the HTML-comment terminator
    surface). The CSS variables (`--bg`/`--fg`/`--link`) are template
    intrinsics and are not subject to this check."""
    normalized = render_business_brief._normalize_project_name("name -- inside")
    assert "--" not in normalized
    out = render_business_brief.render_to_html(
        "# X", title="T", project_name=normalized, render_ts="ts"
    )
    # Scope the dash-collapse check to the title (a project_name interpolation site)
    import re as _re

    title_body = _re.search(r"<title>(.*?)</title>", out).group(1)
    assert "--" not in title_body


def test_trust_boundary_acknowledgment():
    out = render_business_brief.render_to_html(
        "# X", title="T", project_name="P", render_ts="ts"
    )
    assert (
        "Derived artifact — do not hand-edit. "
        "Regenerate via render_business_brief.py." in out
    )
    # No HTML-comment terminator sequence (`-->` inside the comment text would
    # break parsing)
    import re as _re

    # The comment itself ends with `-->`. We're checking that no second `-->`
    # is in the head comment content.
    head_match = _re.search(r"<!-- (.*?) -->", out, _re.DOTALL)
    assert head_match, "head comment not found"
    assert "-->" not in head_match.group(1)



def test_render_all_timestamp_invariant_part_a(
    monkeypatch, tmp_path, fixture_tiny_png_path
):
    """Fixed timestamp via monkeypatch — all three output files contain it
    byte-identically."""
    monkeypatch.setattr(
        render_business_brief, "_get_render_ts", lambda: "2026-01-01 00:00 UTC"
    )
    monkeypatch.setattr(
        render_business_brief, "_LOGO_ASSET_PATH", fixture_tiny_png_path
    )
    paths = render_business_brief.render_all(
        blueprint_dir=tmp_path,
        project_name="MyProj",
        render_ts="2026-01-01 00:00 UTC",
        scope_content="# Scope\n\nbody.\n",
        arch_content="# Arch\n\nbody.\n",
        plan_content="# Plan\n\nbody.\n",
    )
    assert len(paths) == 3
    for p in paths:
        assert "2026-01-01 00:00 UTC" in p.read_text(encoding="utf-8")


def test_render_all_timestamp_single_call_part_b(
    monkeypatch, tmp_path, fixture_tiny_png_path
):
    """Counter monkeypatch on `_get_render_ts`: render_all does NOT call it
    per-file (`render_ts` is passed in as a positional argument). Each file
    must show the same passed-in timestamp."""
    import itertools

    counter = itertools.count(start=100)

    def counting_ts():
        return f"ts-{next(counter)}"

    monkeypatch.setattr(render_business_brief, "_get_render_ts", counting_ts)
    monkeypatch.setattr(
        render_business_brief, "_LOGO_ASSET_PATH", fixture_tiny_png_path
    )
    paths = render_business_brief.render_all(
        blueprint_dir=tmp_path,
        project_name="P",
        render_ts="FIXED",
        scope_content="# S\nbody",
        arch_content="# A\nbody",
        plan_content="# P\nbody",
    )
    # Exactly one timestamp value (the one passed in) across all three files
    for p in paths:
        assert "FIXED" in p.read_text(encoding="utf-8")
        # No "ts-" value leaked (the counter shouldn't have been advanced)
        assert "ts-" not in p.read_text(encoding="utf-8")


def test_render_all_output_filenames_ordered(monkeypatch, tmp_path, fixture_tiny_png_path):
    monkeypatch.setattr(
        render_business_brief, "_LOGO_ASSET_PATH", fixture_tiny_png_path
    )
    paths = render_business_brief.render_all(
        blueprint_dir=tmp_path,
        project_name="P",
        render_ts="ts",
        scope_content="# S",
        arch_content="# A",
        plan_content="# P",
    )
    assert [p.name for p in paths] == ["scope.html", "architecture.html", "plan.html"]


def test_logo_single_load_contract(monkeypatch, tmp_path, fixture_tiny_png_path):
    """`_load_logo_img_tag` is invoked exactly once across all three renders."""
    from unittest.mock import MagicMock

    monkeypatch.setattr(
        render_business_brief, "_LOGO_ASSET_PATH", fixture_tiny_png_path
    )
    real = render_business_brief._load_logo_img_tag
    mock = MagicMock(wraps=real)
    monkeypatch.setattr(render_business_brief, "_load_logo_img_tag", mock)
    render_business_brief.render_all(
        blueprint_dir=tmp_path,
        project_name="P",
        render_ts="ts",
        scope_content="# S",
        arch_content="# A",
        plan_content="# P",
    )
    assert mock.call_count == 1


def test_get_render_ts_format_via_inspect():
    """The injection point uses `timezone.utc` (per AD14)."""
    src = inspect.getsource(render_business_brief._get_render_ts)
    assert "timezone.utc" in src

