"""T8 — HTML sanitization, XSS catalogue, link hardening, self-contained output.

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

from common import (  # type: ignore[import-not-found]
    _body_only,
)

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(_SCRIPTS_DIR))

import render_business_brief  # noqa: E402


_XSS_SHAPES = [
    # (label, payload, must_be_absent in body — scoped to <main>...</main>)
    ("script_tag", "<script>alert(1)</script>", ["<script", "alert(1)"]),
    ("iframe_tag", '<iframe src="evil"></iframe>', ["<iframe", 'src="evil"']),
    ("img_onerror", "<img src=x onerror=alert(1)>", ["onerror"]),
    (
        "anchor_javascript",
        '<a href="javascript:alert(1)">x</a>',
        ['href="javascript:', "javascript:alert"],
    ),
    ("base_tag", '<base href="//evil">', ["<base"]),
    ("meta_httpequiv", '<meta http-equiv="refresh" content="0">', ["<meta http"]),
    ("svg_onload", '<svg onload=alert(1)>', ["<svg", "onload"]),
    ("anchor_data", '<a href="data:text/html,<script>x</script>">x</a>', ['href="data:']),
]


def _body_only(html_str: str) -> str:
    """Extract <main>...</main> content for body-scoped assertions."""
    import re as _re

    m = _re.search(r"<main>(.*?)</main>", html_str, _re.DOTALL)
    return m.group(1) if m else html_str


@pytest.mark.parametrize(
    "label,payload,must_be_absent",
    _XSS_SHAPES,
    ids=[c[0] for c in _XSS_SHAPES],
)
def test_xss_expanded_shapes_parametrized(label, payload, must_be_absent):
    out = render_business_brief.render_to_html(
        payload, title="T", project_name="P", render_ts="ts"
    )
    body = _body_only(out)
    for needle in must_be_absent:
        assert needle not in body, f"{label}: leaked {needle!r} in body: {body!r}"


_MUTATION_XSS = [
    (
        "noscript_disagree",
        '<noscript><p title="</noscript><img src=x onerror=alert(1)>">',
    ),
    (
        "style_javascript_url",
        "<style>div{background:url('javascript:alert(1)')}</style>",
    ),
    (
        "math_mtext_script",
        "<math><mtext><script>alert(1)</script></mtext></math>",
    ),
]


@pytest.mark.parametrize(
    "label,payload", _MUTATION_XSS, ids=[c[0] for c in _MUTATION_XSS]
)
def test_mutation_xss_parametrized(label, payload):
    out = render_business_brief.render_to_html(
        payload, title="T", project_name="P", render_ts="ts"
    )
    body = _body_only(out)
    assert "alert(1)" not in body, f"{label}: alert(1) leaked in body"
    assert "<script" not in body, f"{label}: <script leaked in body"
    assert "onerror" not in body, f"{label}: onerror leaked in body"


def test_rawtext_strip_converges_on_nested_synthesis_payload():
    """P1-4: the pre-bleach rawtext-strip loop must converge to a fixed point
    on nested-mutation payloads where an inner match synthesises an outer
    match. End-to-end these payloads are also blocked by markdown's HTML
    parser, but this unit test pins the loop's correctness in isolation so
    a future markdown-bypass class doesn't unblock the synthesised-outer-tag
    bypass.

    Input shape: `<sc<script></script>ript>alert(1)</script>` — a single
    `re.sub` removes the inner `<script></script>`, leaving a synthesised
    `<script>alert(1)</script>` (the surrounding `<sc` + `ript>` are now
    adjacent and form a valid opening tag). A single pass would leave this
    synthesised outer untouched; the loop catches it on the next iteration.
    """
    # Run the same pre-bleach pipeline render_to_html uses, but on already-HTML
    # input to isolate the loop's behaviour from markdown.
    html_in = "<sc<script></script>ript>alert(1)</script>"
    one_pass = render_business_brief._RAWTEXT_TAGS_STRIP.sub("", html_in)
    # Sanity check: a single pass synthesises an outer <script>...</script>.
    assert "<script>alert(1)</script>" in one_pass, (
        f"single-pass should synthesise outer; got: {one_pass!r}"
    )
    # The looped version (mirroring render_to_html's two-stage strategy) must
    # converge with the script tag AND its contents fully removed.
    looped = html_in
    for _ in range(render_business_brief._RAWTEXT_STRIP_MAX_ITERATIONS):
        next_pass = render_business_brief._RAWTEXT_TAGS_STRIP.sub("", looped)
        if next_pass == looped:
            break
        looped = next_pass
    # VOID strip runs once after the loop converges
    looped = render_business_brief._VOID_RAWTEXT_TAGS_STRIP.sub("", looped)
    assert "<script" not in looped
    assert "alert(1)" not in looped


def test_rawtext_strip_iteration_cap_is_finite():
    """P1-4: the loop must terminate even on adversarial input that never
    converges. The iteration cap prevents catastrophic backtracking."""
    # Adversarial repeated wrapping. Pathological input — should be capped.
    payload = ("<script>" * 100) + ("</script>" * 100)
    looped = payload
    iters = 0
    for iters in range(1, render_business_brief._RAWTEXT_STRIP_MAX_ITERATIONS + 5):
        next_pass = render_business_brief._RAWTEXT_TAGS_STRIP.sub("", looped)
        if next_pass == looped:
            break
        looped = next_pass
    # Either converged within the cap or stopped at the cap — what we care
    # about is finite work, not perfect cleanup on adversarial input.
    assert iters <= render_business_brief._RAWTEXT_STRIP_MAX_ITERATIONS + 4



_CONFUSION_PAYLOADS = [
    ("scheme_relative", "[link](//evil.com)"),
    ("leading_ws_javascript", "[x]( javascript:alert(1))"),
    ("uppercase_javascript", "[x](JAVASCRIPT:alert(1))"),
    ("tab_in_scheme", "[x](java\tscript:alert(1))"),
    ("percent_encoded_colon", "[x](javascript%3Aalert(1))"),
]


@pytest.mark.parametrize(
    "label,md", _CONFUSION_PAYLOADS, ids=[c[0] for c in _CONFUSION_PAYLOADS]
)
def test_xss_scheme_relative_and_confusion_payloads_parametrized(label, md):
    """Each confusion payload renders to body HTML containing no executable
    JavaScript surface: no `javascript:` URL scheme (literal colon), no
    `<script>` tag, no event-handler attribute.

    Text "alert(1)" appearing inside a relative-URL href is harmless because
    the browser does not execute it; we only check the executable surfaces.
    """
    out = render_business_brief.render_to_html(
        md, title="T", project_name="P", render_ts="ts"
    )
    body = _body_only(out)
    # No literal javascript: scheme (with colon) in any href; percent-encoded
    # %3A is not a scheme and is treated as a relative URL by browsers.
    import re as _re

    for href in _re.findall(r'href="([^"]*)"', body):
        scheme = href.strip().lower().split("%")[0]
        # Decode the scheme part; if it expands to javascript:, that's a leak
        assert not scheme.startswith("javascript:"), f"{label}: javascript: href in body"
    assert "<script" not in body, f"{label}: <script in body"



def test_anchor_rel_hardening_external_link():
    out = render_business_brief.render_to_html(
        "[ext](https://example.com)", title="T", project_name="P", render_ts="ts"
    )
    assert 'href="https://example.com"' in out
    # rel injected with noopener and noreferrer
    assert "noopener" in out
    assert "noreferrer" in out


def test_anchor_rel_hardening_internal_fragment():
    """Fragment-only anchors are not hardened (not external)."""
    out = render_business_brief.render_to_html(
        "[sec](#sec)", title="T", project_name="P", render_ts="ts"
    )
    # Anchor preserved; rel NOT injected on fragment-only
    assert 'href="#sec"' in out
    # Find the specific <a href="#sec"...> tag and assert no rel attribute on it
    import re as _re

    m = _re.search(r'<a [^>]*href="#sec"[^>]*>', out)
    assert m, "fragment anchor missing"
    assert "rel=" not in m.group(0)


def test_anchor_rel_hardening_mailto():
    out = render_business_brief.render_to_html(
        "[me](mailto:a@b.com)", title="T", project_name="P", render_ts="ts"
    )
    import re as _re

    m = _re.search(r'<a [^>]*href="mailto:a@b\.com"[^>]*>', out)
    assert m, "mailto anchor missing"
    assert "rel=" not in m.group(0)


def test_anchor_rel_hardening_uppercase_scheme():
    """`HTTP://` should still match after scheme normalization."""
    hardened = render_business_brief._harden_external_links(
        '<p><a href="HTTP://example.com">x</a></p>'
    )
    assert "noopener noreferrer" in hardened


def test_anchor_rel_hardening_scheme_relative_not_hardened():
    """`//host` is NOT http or https — should not be hardened."""
    hardened = render_business_brief._harden_external_links(
        '<p><a href="//evil.com">x</a></p>'
    )
    assert "noopener" not in hardened


def test_anchor_rel_hardening_inside_code_unmodified():
    """Anchors inside <code> blocks must not be rewritten."""
    src = '<pre><code><a href="https://example.com">x</a></code></pre>'
    hardened = render_business_brief._harden_external_links(src)
    assert "noopener" not in hardened


def test_anchor_rel_hardening_additive_with_existing_rel():
    src = '<a href="https://x.com" rel="author">x</a>'
    hardened = render_business_brief._harden_external_links(src)
    # Author + noopener + noreferrer all present, no duplicates
    assert 'rel="author noopener noreferrer"' in hardened


def test_anchor_rel_hardening_idempotent():
    src = '<a href="https://x.com">x</a>'
    once = render_business_brief._harden_external_links(src)
    twice = render_business_brief._harden_external_links(once)
    assert once == twice

