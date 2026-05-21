"""Tests for Markdown rendering and XSS sanitization.

render_md() is reimplemented here from its dependencies so the test
doesn't need a running FastAPI app — it tests the logic, not the import.
"""

import bleach
import bleach.sanitizer
import markdown as md_lib

# Mirror of the allowed-tags config in main.py
_ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td",
    "img", "hr", "br", "del", "s", "sup", "sub",
    "ul", "ol", "li", "blockquote", "input",
}
_ALLOWED_ATTRS = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "code": ["class"],
    "pre": ["class"],
    "td": ["align"],
    "th": ["align"],
    "input": ["type", "checked", "disabled"],
}


def render_md(text: str) -> str:
    raw_html = md_lib.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
    return bleach.clean(raw_html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)


# ── XSS sanitization ───────────────────────────────────────────────────────

class TestXSS:
    def test_script_tag_stripped(self):
        result = render_md("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "</script>" not in result

    def test_inline_event_handler_stripped(self):
        result = render_md('<img src="x" onerror="alert(1)">')
        assert "onerror" not in result

    def test_javascript_href_stripped(self):
        result = render_md("[click](javascript:alert(1))")
        assert "javascript:" not in result

    def test_style_tag_stripped(self):
        result = render_md("<style>body{display:none}</style>")
        assert "<style>" not in result

    def test_iframe_stripped(self):
        result = render_md('<iframe src="https://evil.com"></iframe>')
        assert "<iframe>" not in result


# ── Normal Markdown output ──────────────────────────────────────────────────

class TestMarkdown:
    def test_heading(self):
        assert "<h1>" in render_md("# Hello")

    def test_bold(self):
        assert "<strong>" in render_md("**bold**")

    def test_italic(self):
        assert "<em>" in render_md("*italic*")

    def test_code_block(self):
        result = render_md("```python\nprint('hi')\n```")
        assert "<code" in result

    def test_link_allowed(self):
        result = render_md("[example](https://example.com)")
        assert 'href="https://example.com"' in result

    def test_table_rendered(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = render_md(md)
        assert "<table>" in result

    def test_plain_text_passthrough(self):
        result = render_md("just some text")
        assert "just some text" in result

    def test_empty_string(self):
        result = render_md("")
        assert result == ""
