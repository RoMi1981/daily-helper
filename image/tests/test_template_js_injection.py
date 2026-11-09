"""Guard against template values breaking out of JavaScript in HTML attributes.

Jinja autoescaping turns `'` into `&#39;`, but the browser decodes entities in an
attribute *before* it runs the JavaScript inside. So

    onsubmit="return confirm('Delete \\'{{ link.title }}\\'?')"

runs any code a link title carries: a title of `x'+(document.title='PWNED')+'`
executed on the delete click. Link titles arrive from browser bookmarks via
Floccus, so they are not trusted input.

Rules enforced here:
- inside an `on*` handler, a template value is either `| tojson`, a server-made
  id (`*.id`, `*_id`), or `loop.index0`
- `hx-vals` is built with `| tojson` — hand-written JSON with `| e` broke on the
  first `"` in a title and the favourite star silently stopped working
- confirmation prompts use `data-confirm`, never an inline `confirm(...)` call
"""

import os
import re
import sys

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if not os.path.isdir(APP_DIR):
    APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_HANDLER = re.compile(r"""\son[a-z]+=(?:"([^"]*)"|'([^']*)')""")
_HX_VALS = re.compile(r"""\shx-vals=(?:"([^"]*)"|'([^']*)')""")
_EXPR = re.compile(r"\{\{(.*?)\}\}")
_SAFE_EXPR = re.compile(r"^\s*(?:[\w.]+\.id|[\w.]*_id|loop\.index0|.*\|\s*tojson)\s*$")


def _templates():
    root = os.path.join(APP_DIR, "templates")
    for dirpath, _, files in os.walk(root):
        for name in files:
            if name.endswith(".html"):
                path = os.path.join(dirpath, name)
                yield os.path.relpath(path, APP_DIR), open(path, encoding="utf-8").read()


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _masked(text):
    """Replace every {{ ... }} by a quote-free placeholder.

    Expressions may contain quotes themselves (`replace("'", "\\'")`), which would
    otherwise end the attribute early and hide the rest of the handler from the
    regex. Returns the masked text and the expressions by placeholder index.
    """
    exprs = []

    def _sub(m):
        exprs.append(m.group(1))
        return f"{{{{#{len(exprs) - 1}#}}}}"

    return _EXPR.sub(_sub, text), exprs


def _unsafe_in_handlers(text):
    masked, exprs = _masked(text)
    for m in _HANDLER.finditer(masked):
        body = m.group(1) or m.group(2) or ""
        for idx in re.findall(r"\{\{#(\d+)#\}\}", body):
            expr = exprs[int(idx)]
            if not _SAFE_EXPR.match(expr):
                yield _line(masked, m.start()), expr.strip()


def test_no_raw_template_values_in_event_handlers():
    offenders = [
        f"{path}:{line}: {{{{ {expr} }}}}" for path, text in _templates() for line, expr in _unsafe_in_handlers(text)
    ]
    assert not offenders, "Pass values into on*-handlers with | tojson (or use data-*):\n" + "\n".join(offenders)


def test_hx_vals_are_serialised_with_tojson():
    offenders = []
    for path, text in _templates():
        masked, exprs = _masked(text)
        for m in _HX_VALS.finditer(masked):
            body = (m.group(1) or m.group(2) or "").strip()
            whole = re.fullmatch(r"\{\{#(\d+)#\}\}", body)
            if "{{" in body and not (whole and re.search(r"\|\s*tojson\s*$", exprs[int(whole.group(1))])):
                offenders.append(f"{path}:{_line(masked, m.start())}")
    assert not offenders, "Build hx-vals with {{ {...} | tojson }}:\n" + "\n".join(offenders)


def test_no_inline_confirm_calls():
    offenders = [
        f"{path}:{_line(text, m.start())}"
        for path, text in _templates()
        for m in _HANDLER.finditer(_masked(text)[0])
        if "confirm(" in (m.group(1) or m.group(2) or "")
    ]
    assert not offenders, "Use data-confirm instead of an inline confirm(...):\n" + "\n".join(offenders)


def test_rules_catch_the_original_patterns():
    """The checks must flag exactly the markup that caused both bugs."""
    link_delete = """<form onsubmit="return confirm('Delete \\'{{ link.title }}\\'?')">"""
    assert list(_unsafe_in_handlers(link_delete)) == [(1, "link.title")]
    assert not list(_unsafe_in_handlers("""<b onclick="toggle('{{ e.id }}')">"""))
    assert not list(_unsafe_in_handlers("""<b onclick='copy(this, {{ step.command | tojson }})'>"""))
    holiday = """<b onclick="dl('{{ hdate }}', '{{ day.holiday_name|replace("'", "\\'") }}')">"""
    flagged = [e for _, e in _unsafe_in_handlers(holiday)]
    assert flagged[0] == "hdate" and flagged[1].startswith("day.holiday_name")


def test_hx_vals_rule_flags_hand_written_json(tmp_path, monkeypatch):
    tpl = tmp_path / "templates"
    tpl.mkdir()
    (tpl / "fav.html").write_text("""<b hx-vals='{"title":"{{ n.subject | e }}"}'>""")
    (tpl / "ok.html").write_text("""<b hx-vals='{{ {"title": n.subject} | tojson }}'>""")
    monkeypatch.setattr(sys.modules[__name__], "APP_DIR", str(tmp_path))
    try:
        test_hx_vals_are_serialised_with_tojson()
    except AssertionError as e:
        assert "fav.html" in str(e) and "ok.html" not in str(e)
    else:
        raise AssertionError("hand-written hx-vals JSON was not flagged")
