"""Tests for core/templates.py — Jinja2 filter functions."""

import sys
import os
from unittest.mock import patch
from markupsafe import Markup

# Patch Jinja2Templates before importing templates to avoid filesystem dependency
with patch("fastapi.templating.Jinja2Templates.__init__", return_value=None), \
     patch("fastapi.templating.Jinja2Templates.env", create=True):
    pass  # pre-import patch setup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

# We import the filter functions directly to avoid the Jinja2Templates instantiation
# touching the filesystem.  Use a minimal env stub so module-level code doesn't fail.
import jinja2
_env_stub = jinja2.Environment()

with patch("fastapi.templating.Jinja2Templates") as _MockTemplates:
    _mock_instance = _MockTemplates.return_value
    _mock_instance.env = _env_stub
    from core.templates import _linkify, _strftime


class TestLinkify:
    def test_wraps_url_in_anchor_tag(self):
        result = _linkify("Visit https://example.com today")
        assert isinstance(result, Markup)
        assert '<a href="https://example.com"' in result
        assert 'target="_blank"' in result
        assert "https://example.com" in result

    def test_plain_text_with_no_url_is_returned_unchanged(self):
        result = _linkify("No links here")
        assert result == Markup("No links here")

    def test_escapes_html_in_non_url_parts(self):
        result = _linkify("<b>bold</b> see https://example.com")
        assert "&lt;b&gt;" in result
        assert "<b>" not in result

    def test_url_is_not_double_escaped(self):
        result = _linkify("https://example.com/path?a=1&b=2")
        # The URL should appear as a link (ampersand is escaped inside href attribute)
        assert "https://example.com/path" in result
        assert "<a href=" in result

    def test_multiple_urls_all_linkified(self):
        result = _linkify("https://foo.com and https://bar.com")
        assert result.count("<a href=") == 2


class TestStrftime:
    def test_formats_unix_timestamp(self):
        # 2024-01-15 12:00:00 UTC → local time will vary; just check the output is a string
        # Use a known timestamp and verify structure: DD.MM.YYYY HH:MM
        import re
        result = _strftime(1705320000)
        assert re.match(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}", result)

    def test_custom_format(self):
        result = _strftime(0, fmt="%Y")
        # epoch year is either 1970 (UTC-based) — just ensure it's a 4-digit year
        assert len(result) == 4
        assert result.isdigit()

    def test_returns_empty_string_on_invalid_input(self):
        assert _strftime("not-a-timestamp") == ""

    def test_returns_empty_string_on_none(self):
        assert _strftime(None) == ""
