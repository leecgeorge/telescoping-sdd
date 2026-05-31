"""T5 — Brand-logo loader (C10) tests for render_business_brief.py.

Split from the original test_render_business_brief.py per P3-15. Shared
helpers and constants live in `common.py`; shared fixtures (tiny PNG path,
approved-triple fixtures, panel-review fixture) live in `conftest.py`.
"""

from __future__ import annotations

import base64
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(_SCRIPTS_DIR))

import render_business_brief  # noqa: E402


def test_logo_asset_file_exists_and_size():
    """Committed brand logo exists, is a real PNG, and is ≤150 KB raw."""
    p = render_business_brief._LOGO_ASSET_PATH
    assert p.exists(), f"brand logo missing at {p}"
    size = p.stat().st_size
    assert 100 < size <= 150_000, f"logo size out of range: {size} bytes"
    head = p.read_bytes()[:8]
    assert head == b"\x89PNG\r\n\x1a\n", f"not a PNG file: {head!r}"


def test_load_logo_img_tag_happy_path_unit(monkeypatch, fixture_tiny_png_path):
    """Tiny-PNG fixture monkeypatched in; output is the committed <img> shape."""
    monkeypatch.setattr(
        render_business_brief, "_LOGO_ASSET_PATH", fixture_tiny_png_path
    )
    tag = render_business_brief._load_logo_img_tag()
    assert tag.startswith('<img alt="Neon Ghost" class="brand-logo" src="data:image/png;base64,')
    assert tag.endswith('">')
    # Extract base64 payload and assert it decodes to the fixture bytes
    prefix = 'src="data:image/png;base64,'
    start = tag.index(prefix) + len(prefix)
    end = tag.index('"', start)
    payload = tag[start:end]
    decoded = base64.b64decode(payload)
    assert decoded == fixture_tiny_png_path.read_bytes()


def test_logo_payload_size_within_cap(monkeypatch):
    """Real committed logo, base64-encoded, is within the data-URL cap."""
    tag = render_business_brief._load_logo_img_tag()
    prefix = 'src="data:image/png;base64,'
    start = tag.index(prefix) + len(prefix)
    end = tag.index('"', start)
    payload = tag[start:end]
    assert len(payload) <= render_business_brief._LOGO_DATA_URL_MAX_BYTES


def test_logo_payload_oversized_case(monkeypatch, tmp_path, capsys):
    """An oversized PNG (over `_LOGO_DATA_URL_MAX_BYTES`) is NOT embedded: the
    loader warns and returns the empty string, so the rendered HTML is not
    bloated by an unbounded base64 payload. The cap is enforced, not a dead
    constant (review finding Scripts D5-3)."""
    oversized = tmp_path / "oversized.png"
    oversized.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500_000)
    monkeypatch.setattr(render_business_brief, "_LOGO_ASSET_PATH", oversized)
    tag = render_business_brief._load_logo_img_tag()
    assert tag == ""
    captured = capsys.readouterr()
    assert "exceeding the" in captured.err and "data-URL cap" in captured.err
    assert str(len(b"\x89PNG\r\n\x1a\n") + 500_000) in captured.err


def test_load_logo_img_tag_missing_file_degrades(monkeypatch, tmp_path, capsys):
    """Missing file: stderr warning + empty-string return (R3 graceful degradation)."""
    missing = tmp_path / "missing.png"
    monkeypatch.setattr(render_business_brief, "_LOGO_ASSET_PATH", missing)
    result = render_business_brief._load_logo_img_tag()
    assert result == ""
    captured = capsys.readouterr()
    assert "WARNING: brand logo not found or unreadable at" in captured.err
    assert str(missing) in captured.err


def test_load_logo_img_tag_directory_at_path_degrades(monkeypatch, tmp_path, capsys):
    """Path-is-a-directory: same graceful degradation as missing-file."""
    dir_path = tmp_path / "asset-as-dir"
    dir_path.mkdir()
    monkeypatch.setattr(render_business_brief, "_LOGO_ASSET_PATH", dir_path)
    result = render_business_brief._load_logo_img_tag()
    assert result == ""
    captured = capsys.readouterr()
    assert "WARNING: brand logo not found or unreadable at" in captured.err


def test_load_logo_img_tag_rejects_non_png_magic_bytes(monkeypatch, tmp_path, capsys):
    """P3-4: file present and readable but NOT a PNG → stderr warning +
    empty `<img>` (graceful degradation, no base64 of arbitrary content)."""
    fake = tmp_path / "fake.png"
    fake.write_bytes(b"GIF89a..." + b"\x00" * 100)
    monkeypatch.setattr(render_business_brief, "_LOGO_ASSET_PATH", fake)
    result = render_business_brief._load_logo_img_tag()
    assert result == ""
    captured = capsys.readouterr()
    assert "is not a PNG" in captured.err
    assert str(fake) in captured.err


def test_load_logo_img_tag_accepts_logo_path_override(
    monkeypatch, tmp_path, capsys, fixture_tiny_png_path
):
    """P3-7: the optional `logo_path` arg to `_load_logo_img_tag` lets
    callers (and the --logo CLI flag) override `_LOGO_ASSET_PATH`."""
    # Move the module default to a missing file so we'd notice if the
    # override didn't take effect.
    monkeypatch.setattr(
        render_business_brief, "_LOGO_ASSET_PATH", tmp_path / "no-such.png"
    )
    result = render_business_brief._load_logo_img_tag(fixture_tiny_png_path)
    assert result.startswith('<img alt="Neon Ghost"')
    captured = capsys.readouterr()
    assert captured.err == ""  # no warning when override is valid

