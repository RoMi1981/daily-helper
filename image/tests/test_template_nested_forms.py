"""Templates must not nest <form> elements.

HTML forbids nested forms. The parser does not report it, it silently drops the
inner <form> start tag — and the inner </form> then closes the *outer* form. In
the snippet, link and task lists every row carried its own delete form inside
the bulk-delete form, with three effects nobody noticed:

- the first row's delete button submitted the bulk form without ids and without
  a confirmation, so the first entry could not be deleted on its own
- rows two and onwards, and the bulk toolbar, ended up outside the bulk form,
  so "Delete selected" did nothing at all
- the confirmation on the first row never ran

The check follows the nesting in the template source. Jinja blocks are removed
first; an {% include %} is resolved so a row template rendered inside a bulk
form is checked in that context.
"""

import re
from pathlib import Path

_here = Path(__file__).resolve().parent
TEMPLATES = next(p for p in (_here.parent / "app" / "templates", _here.parent / "templates") if p.is_dir())

_INCLUDE = re.compile(r"""\{%-?\s*include\s+["']([^"']+)["'][^%]*-?%\}""")
_JINJA = re.compile(r"\{#.*?#\}|\{%.*?%\}|\{\{.*?\}\}", re.S)
_FORM_TAG = re.compile(r"<(/?)form\b", re.I)


def _expanded(name: str, depth: int = 0) -> str:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    if depth > 5:
        return text
    return _INCLUDE.sub(lambda m: _expanded(m.group(1), depth + 1), text)


def _nested_forms(text: str) -> list[int]:
    """Line numbers of <form> tags opened while another form is still open."""
    text = _JINJA.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    depth, hits = 0, []
    for m in _FORM_TAG.finditer(text):
        if m.group(1):
            depth = max(depth - 1, 0)
        else:
            if depth:
                hits.append(text.count("\n", 0, m.start()) + 1)
            depth += 1
    return hits


def test_no_nested_forms():
    offenders = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = str(path.relative_to(TEMPLATES))
        lines = _nested_forms(_expanded(rel))
        if lines:
            offenders.append(f"{rel}: nested <form> at expanded line(s) {lines}")
    assert not offenders, (
        "Nested forms are dropped by the HTML parser; use formaction on a button "
        "inside the outer form instead:\n" + "\n".join(offenders)
    )


def test_check_sees_the_original_bulk_layout():
    bulk = """<form id="x-bulk" action="/x/bulk-delete">
  <div class="row">
    <form action="/x/{{ id }}/delete"><button type="submit">del</button></form>
  </div>
  <div class="bulk-toolbar"><button type="submit">Delete selected</button></div>
</form>"""
    assert _nested_forms(bulk) == [3]
    fixed = bulk.replace(
        '<form action="/x/{{ id }}/delete"><button type="submit">del</button></form>',
        '<button type="submit" formaction="/x/{{ id }}/delete">del</button>',
    )
    assert _nested_forms(fixed) == []
