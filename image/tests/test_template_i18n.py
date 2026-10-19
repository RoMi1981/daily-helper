"""Templates must not carry hardcoded UI text.

Seven widget templates shipped with English labels baked in ("Total", "High",
"Starts today", "New task..."), so a German user saw them untranslated while
every surrounding string honoured the locale. Nothing failed — the strings
simply rendered as-is — which is why this needs a test rather than review
attention.

The check covers every template under `templates/`. VERBATIM lists the
strings that stay in English on purpose — product names, OAuth scope names,
config paths, placeholder sample values — because translating them would be
wrong, not missing. Everything else must go through t().
"""

import re
from pathlib import Path

import pytest

_here = Path(__file__).resolve().parent
TEMPLATES = next(p for p in (_here.parent / "app" / "templates", _here.parent / "templates") if p.is_dir())

# Text node between tags, and placeholder/title attribute values (both quote styles).
_TEXT_NODE = re.compile(r">([^<>{}]+)<")
_ATTR = re.compile(r"""\b(?:placeholder|title|aria-label)=(?:"([^"{}]+)"|'([^'{}]+)')""")
# String literals a script writes into the page: btn.title = 'Show / hide'.
_SCRIPT_TEXT = re.compile(r"""\.(?:textContent|innerText|title|placeholder)\s*=\s*(['"])([^'"]+)\1""")

# A run of letters containing at least one lowercase letter is a word, not an
# acronym — this keeps RW / RO / CA / GPG badges out of the results.
_WORD = re.compile(r"[A-Za-z]*[a-z][A-Za-z]*")

# Deliberately not translated. These are identifiers a user types or reads
# verbatim, so a German rendering would be wrong rather than helpful:
# product names, OAuth scope names, config values, paths, sample data.
VERBATIM = {
    "Daily Helper",  # product name
    "Nextcloud Bookmarks",  # product name
    "PFM Sprint",  # sprint scheme name, used verbatim in tickets
    "Chrome:",
    "Firefox:",
    "Windows:",
    "ca.crt",  # browser/file names
    "chrome://settings/certificates",
    "about:preferences#privacy",
    "DevOps",
    "Linux",
    "Networking",  # sample category names in a hint
    "recipient@example.com, …",
    "cc@example.com, …",  # sample addresses
    "glpat-xxxxxxxxxxxxxxxxxxxx",  # sample token shape
    "localhost, 127.0.0.1, 192.168.1.10, myserver.local",  # sample host list
    "user",  # sample username
    "read",
    "write",  # permission values stored in settings.json
    "gitea",
    "github",
    "gitlab",
    "generic",  # platform option values
    "&#123;&#123;from&#125;&#125;",  # template placeholder syntax
    "&#123;&#123;working_days&#125;&#125;",
    "[b]bold[/b]",
    "[i]italic[/i]",
    "[u]underline[/u]",  # markup syntax
    "Floccus:",  # product name, followed by the configured username
    "(ASCII-armored,  )",  # GPG key format name
}


# Not user-facing prose: HTML entities, e-mail/URL sample values, and bare
# identifiers that appear verbatim in the UI on purpose (scope names, hosts).
_NOT_PROSE = re.compile(r"^(?:&[a-z]+;|https?://\S*|\S+@\S+\.\w+|[\w.]+\.(?:de|com|org|net)|&nbsp;)$")


# <script>/<style> bodies are code, not UI text.
_CODE_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
# Jinja statements contain comparison operators that look like tags
# ({% set x = a >= b and c <= d %}), so they are stripped first.
_JINJA_STMT = re.compile(r"\{%.*?%\}|\{#.*?#\}", re.S)  # statements and comments
# Output expressions are masked rather than skipped: "Step {{ loop.index }}" or
# title="Task: {{ task.title }}" must still be checked for the words around them.
_JINJA_EXPR = re.compile(r"\{\{.*?\}\}", re.S)
_MASK = "\u00a7"
# &nbsp; / &lt; are markup, not words.
_ENTITY = re.compile(r"&[a-z]+;|&#\d+;")


def _hardcoded_strings(text: str) -> list[str]:
    text = _JINJA_EXPR.sub(_MASK, _JINJA_STMT.sub("", text))
    scripts = " ".join(m.group(0) for m in _CODE_BLOCK.finditer(text))
    text = _CODE_BLOCK.sub("", text)
    candidates = _TEXT_NODE.findall(text) + [a or b for a, b in _ATTR.findall(text)]
    candidates += [lit for _, lit in _SCRIPT_TEXT.findall(scripts)]
    found = []
    for raw in candidates:
        s = raw.replace(_MASK, " ").strip()
        if len(s) < 3 or _NOT_PROSE.match(s):
            continue
        words = _WORD.findall(_ENTITY.sub(" ", s))
        # Require two words, or one word of 4+ chars — filters out stray
        # units and fragments like "px" or "of".
        if len(words) >= 2 or (words and len(words[0]) >= 4):
            found.append(s)
    return found


@pytest.mark.parametrize("template", sorted(TEMPLATES.rglob("*.html")), ids=lambda p: str(p.relative_to(TEMPLATES)))
def test_no_hardcoded_ui_text(template):
    leftovers = [s for s in _hardcoded_strings(template.read_text(encoding="utf-8")) if s not in VERBATIM]
    assert not leftovers, (
        f"{template.name} has untranslated text: {leftovers}. "
        'Wrap it in t("...") and add the key to locales/en.json and de.json.'
    )
