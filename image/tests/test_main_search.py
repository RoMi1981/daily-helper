"""Unit tests for search helpers in main.py — _highlight() and _date_in_range()."""

import html
import os
import sys

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"

from main import _highlight, _date_in_range


# ──────────────────────────── _highlight ────────────────────────────

class TestHighlight:
    def test_returns_empty_for_empty_text(self):
        assert _highlight("", "foo") == ""

    def test_returns_empty_for_empty_query(self):
        assert _highlight("some text", "") == ""

    def test_returns_empty_when_no_match(self):
        assert _highlight("hello world", "xyz") == ""

    def test_wraps_match_in_mark(self):
        result = _highlight("hello world", "world")
        assert "<mark>world</mark>" in result

    def test_case_insensitive_match(self):
        result = _highlight("Hello World", "world")
        assert "<mark>" in result
        assert "World" in result

    def test_includes_context_around_match(self):
        text = "a" * 80 + "TARGET" + "b" * 80
        result = _highlight(text, "TARGET")
        assert "<mark>TARGET</mark>" in result
        # Should include some context around the match
        assert "a" in result
        assert "b" in result

    def test_adds_ellipsis_when_truncated_left(self):
        text = "x" * 100 + "MATCH" + "y" * 10
        result = _highlight(text, "MATCH")
        assert result.startswith("…")

    def test_adds_ellipsis_when_truncated_right(self):
        text = "MATCH" + "y" * 100
        result = _highlight(text, "MATCH")
        assert result.endswith("…")

    def test_no_ellipsis_for_short_text(self):
        result = _highlight("MATCH here", "MATCH")
        assert not result.startswith("…")

    def test_html_escapes_surrounding_text(self):
        result = _highlight("<b>hello</b> world", "world")
        assert "&lt;b&gt;" in result
        assert "<mark>world</mark>" in result

    def test_html_escapes_do_not_break_mark(self):
        # Ensure the mark tag itself is not double-escaped
        result = _highlight("find me here", "find")
        assert "<mark>" in result
        assert "&lt;mark&gt;" not in result

    def test_match_at_start_of_text(self):
        result = _highlight("start of text", "start")
        assert "<mark>start</mark>" in result
        assert not result.startswith("…")

    def test_match_at_end_of_text(self):
        result = _highlight("text at end MATCH", "MATCH")
        assert "<mark>MATCH</mark>" in result
        assert not result.endswith("…")


# ──────────────────────────── _date_in_range ────────────────────────────

class TestDateInRange:
    def test_empty_date_str_always_passes(self):
        assert _date_in_range("", "2026-01-01", "2026-12-31") is True

    def test_no_bounds_always_passes(self):
        assert _date_in_range("2026-06-15", "", "") is True

    def test_within_range(self):
        assert _date_in_range("2026-06-15", "2026-01-01", "2026-12-31") is True

    def test_before_from_fails(self):
        assert _date_in_range("2025-12-31", "2026-01-01", "") is False

    def test_after_to_fails(self):
        assert _date_in_range("2027-01-01", "", "2026-12-31") is False

    def test_exactly_on_from_boundary(self):
        assert _date_in_range("2026-01-01", "2026-01-01", "") is True

    def test_exactly_on_to_boundary(self):
        assert _date_in_range("2026-12-31", "", "2026-12-31") is True

    def test_only_from_bound(self):
        assert _date_in_range("2026-03-01", "2026-01-01", "") is True
        assert _date_in_range("2025-12-01", "2026-01-01", "") is False

    def test_only_to_bound(self):
        assert _date_in_range("2026-03-01", "", "2026-12-31") is True
        assert _date_in_range("2027-01-01", "", "2026-12-31") is False
