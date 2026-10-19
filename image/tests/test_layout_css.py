"""Guards for CSS rules whose effect is only observable in a browser.

The E2E suite proves these rules work, but it is skipped whenever the deploy key
for the test repo is missing. These checks keep the rules from being dropped
silently in the fast test job.
"""

import os
import re

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if not os.path.isdir(APP_DIR):
    APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STYLE_CSS = os.path.join(APP_DIR, "static", "style.css")


def _rule(selector: str) -> str:
    """Return the declarations of a single-line rule, e.g. '.content { … }'."""
    css = open(STYLE_CSS, encoding="utf-8").read()
    match = re.search(rf"^{re.escape(selector)}\s*\{{([^}}]*)\}}", css, re.MULTILINE)
    assert match, f"Rule for {selector} not found in style.css"
    return match.group(1)


def test_content_column_can_shrink():
    """.content needs min-width:0 to shrink inside the `220px 1fr` layout grid.

    A grid item defaults to min-width:auto, so without this the column grows to
    the min-content width of its contents — one `white-space: nowrap` snippet
    command pushed the whole page past the viewport, and `html { overflow-x: clip }`
    then cut it off at the right edge instead of scrolling.
    """
    assert "min-width: 0" in _rule(".content")


def test_search_snippets_break_long_tokens():
    """Search excerpts are up to 200 monospace chars and may be a single URL.

    Without a break rule such a snippet is wider than its card at common desktop
    widths and spills over the card's right edge.
    """
    assert "overflow-wrap: anywhere" in _rule(".result-snippet")


def _rules(css: str | None = None) -> dict[str, str]:
    """Map every selector to its declarations; a later rule wins, as in the browser."""
    if css is None:
        css = open(STYLE_CSS, encoding="utf-8").read()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules: dict[str, str] = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for sel in selectors.split(","):
            sel = " ".join(sel.split())
            rules[sel] = rules.get(sel, "") + ";" + body
    return rules


def _prop(decls: str, name: str) -> str | None:
    found = re.findall(rf"(?:^|;)\s*{re.escape(name)}\s*:\s*([^;]+)", decls)
    return found[-1].strip() if found else None


def _rgb(value: str, theme_vars: dict[str, str]) -> tuple[tuple[int, int, int], float]:
    while var := re.fullmatch(r"var\((--[\w-]+)\)", value):
        assert theme_vars.get(var.group(1)), f"{var.group(1)} is not loaded by this test or not defined"
        value = theme_vars[var.group(1)]
    if re.fullmatch(r"#[0-9a-fA-F]{3}", value):
        value = "#" + "".join(c * 2 for c in value[1:])
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5)), 1.0
    rgba = re.fullmatch(r"rgba?\(([^)]*)\)", value)
    assert rgba, f"Colour format not understood by this test: {value!r} (use #rgb, #rrggbb, rgb() or rgba())"
    r, g, b, *a = (float(x) for x in rgba.group(1).split(","))
    return (int(r), int(g), int(b)), a[0] if a else 1.0


def _luminance(rgb) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_messages_are_readable_in_both_themes():
    """Every message type needs WCAG AA contrast (4.5:1) on cards in both themes.

    The pastel text colours were chosen for the dark theme. In the light theme
    nothing overrode them, and the error text sat at 1.7:1 on its pink tint, so
    a failed save or import was hard to read. Warning and info messages had no
    rule at all and looked like body text.
    """
    rules = _rules()
    dark_vars = {k: _prop(rules[":root"], k) for k in ("--bg-card", "--danger", "--success")}
    light_vars = {**dark_vars, **{k: v for k in dark_vars if (v := _prop(rules['[data-theme="light"]'], k))}}
    too_faint = []
    for cls in (".alert-success", ".alert-error", ".alert-warning", ".alert-info", ".qc-error"):
        base = rules.get(cls)
        if not base or not _prop(base, "color"):
            too_faint.append(f"{cls}: no rule with a text colour, renders as body text")
            continue
        for theme, theme_vars, prefix in (("dark", dark_vars, ""), ("light", light_vars, '[data-theme="light"] ')):
            text = _prop(rules.get(prefix + cls, ""), "color") if prefix else None
            fg, _ = _rgb(text or _prop(base, "color"), theme_vars)
            tint, alpha = _rgb(_prop(base, "background"), theme_vars)
            card, _ = _rgb(theme_vars["--bg-card"], theme_vars)
            bg = tuple(round(alpha * t + (1 - alpha) * c) for t, c in zip(tint, card, strict=True))
            hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
            ratio = (hi + 0.05) / (lo + 0.05)
            if ratio < 4.5:
                too_faint.append(f"{cls} in {theme} theme: {ratio:.2f}:1")
    assert not too_faint, "Message text below WCAG AA 4.5:1:\n" + "\n".join(too_faint)


def test_links_in_messages_use_the_message_colour():
    """The accent colour reaches only about 3:1 on the tinted dark message
    backgrounds, so links inside a message inherit its tested text colour and are
    underlined to stay recognisable."""
    decls = _rules().get(".alert a", "")
    assert _prop(decls, "color") == "inherit"
    assert _prop(decls, "text-decoration") == "underline"


def _contrast(fg, bg) -> float:
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_accent_text_is_readable_in_both_themes():
    """Small text in the accent colour needs WCAG AA 4.5:1 on every background.

    The dark theme's --accent (#5f56f5) reaches only 3.3:1 on cards. It stays
    the colour of buttons, borders and icons; text takes --accent-text, which is
    lighter in the dark theme only. The hover shade must pass as well.
    """
    rules = _rules()
    names = ("--bg", "--bg-card", "--bg-sidebar", "--accent-text", "--accent-text-hover")
    dark_vars = {k: _prop(rules[":root"], k) for k in names}
    light_vars = {**dark_vars, **{k: v for k in names if (v := _prop(rules['[data-theme="light"]'], k))}}
    too_faint = []
    for theme, theme_vars in (("dark", dark_vars), ("light", light_vars)):
        for text in ("--accent-text", "--accent-text-hover"):
            assert theme_vars[text], f"{text} is not defined in style.css"
            for bg in ("--bg", "--bg-card", "--bg-sidebar"):
                ratio = _contrast(_rgb(f"var({text})", theme_vars)[0], _rgb(f"var({bg})", theme_vars)[0])
                if ratio < 4.5:
                    too_faint.append(f"{text} on {bg} in {theme} theme: {ratio:.2f}:1")
    assert not too_faint, "Accent text below WCAG AA 4.5:1:\n" + "\n".join(too_faint)


# Text that may keep --accent: icons need only 3:1 (non-text contrast), and bold
# text from 18.7px counts as large text, which needs 3:1 as well.
ACCENT_ICONS = {
    ".icon-accent",
    ".nav-brand .icon",
    ".nav-brand .icon-xs",
    ".nav-brand .icon-sm",
    ".nav-link .icon",
    ".nav-link .icon-xs",
    ".nav-link .icon-sm",
    ".sidebar-desktop-link .icon",
    ".sidebar-desktop-link .icon-xs",
    ".sidebar-desktop-link .icon-sm",
    ".sidebar-mobile-link .icon",
    ".sidebar-mobile-link .icon-xs",
    ".sidebar-mobile-link .icon-sm",
    ".radio-option .icon-xs",
    ".settings-group .form-group > label .icon-xs",
    ".widget-stats-icon",
}
ACCENT_LARGE_TEXT = {
    ".home-stat-value",
    ".vacation-stat-highlight .vacation-stat-value",
    ".widget-sprint-count",
    ".widget-vac-remaining",
    ".widget-next-vac-date",
}


def _template_style_blocks() -> str:
    blocks = []
    for root, _, files in os.walk(os.path.join(APP_DIR, "templates")):
        for name in files:
            html = open(os.path.join(root, name), encoding="utf-8").read()
            blocks += re.findall(r"<style[^>]*>(.*?)</style>", html, re.S)
    return "\n".join(blocks)


def test_small_text_does_not_use_the_button_accent():
    """A new rule with `color: var(--accent)` would bring the 3.3:1 text back.

    Some templates carry their own <style> block; those rules count as well.
    """
    offenders = [
        sel
        for rules in (_rules(), _rules(_template_style_blocks()))
        for sel, decls in rules.items()
        if re.match(r"var\(--accent(-hover)?\)", _prop(decls, "color") or "")
        and sel not in ACCENT_ICONS | ACCENT_LARGE_TEXT
    ]
    assert not offenders, "Use var(--accent-text) for text:\n" + "\n".join(sorted(offenders))


def test_templates_do_not_colour_small_text_with_the_button_accent():
    """Inline styles bypass the stylesheet, so they are checked separately.

    Allowed are icons (<i>) and large bold text such as the countdown number.
    """
    offenders = []
    for root, _, files in os.walk(os.path.join(APP_DIR, "templates")):
        for name in files:
            path = os.path.join(root, name)
            html = open(path, encoding="utf-8").read()
            for tag in re.finditer(r"<(\w+)[^>]*?(?<![-\w])color:\s*var\(--accent(?:-hover)?\)[^>]*>", html, re.S):
                size = re.search(r"font-size:\s*([\d.]+)rem", tag.group(0))
                large = size and float(size.group(1)) >= 1.25 and "font-weight:700" in tag.group(0).replace(" ", "")
                if tag.group(1) != "i" and not large:
                    line = html.count("\n", 0, tag.start()) + 1
                    offenders.append(f"{os.path.relpath(path, APP_DIR)}:{line}")
    assert not offenders, "Use var(--accent-text) for text:\n" + "\n".join(offenders)


def test_white_text_on_accent_fills_is_readable():
    """Buttons, active tabs and badges put white text on --accent, the hover
    state on --accent-hover; both need 4.5:1 in both themes.

    The dark theme's --accent-hover used to be lighter than --accent and left
    white text at 3.1:1. --accent also colours icons, borders and progress bars,
    which need 3:1 against the page, card, sidebar and --bg-secondary (bar track).
    """
    rules = _rules()
    names = ("--bg", "--bg-card", "--bg-sidebar", "--bg-secondary", "--accent", "--accent-hover")
    dark_vars = {k: _prop(rules[":root"], k) for k in names}
    light_vars = {**dark_vars, **{k: v for k in names if (v := _prop(rules['[data-theme="light"]'], k))}}
    white = (255, 255, 255)
    too_faint = []
    for theme, theme_vars in (("dark", dark_vars), ("light", light_vars)):
        for fill in ("--accent", "--accent-hover"):
            ratio = _contrast(white, _rgb(f"var({fill})", theme_vars)[0])
            if ratio < 4.5:
                too_faint.append(f"white on {fill} in {theme} theme: {ratio:.2f}:1")
        # --bg-secondary carries progress bars in the accent colour.
        for bg in ("--bg", "--bg-card", "--bg-sidebar", "--bg-secondary"):
            ratio = _contrast(_rgb("var(--accent)", theme_vars)[0], _rgb(f"var({bg})", theme_vars)[0])
            if ratio < 3:
                too_faint.append(f"--accent on {bg} in {theme} theme: {ratio:.2f}:1 (icons need 3:1)")
    assert not too_faint, "\n".join(too_faint)


def test_every_css_variable_used_is_defined():
    """An undefined var() without a fallback makes the whole declaration invalid,
    so the property silently falls back to its initial value: dashboard widgets
    had no card background for months because they asked for --card-bg instead
    of --bg-card.
    """
    sources = {STYLE_CSS: open(STYLE_CSS, encoding="utf-8").read()}
    for root, _, files in os.walk(os.path.join(APP_DIR, "templates")):
        for name in files:
            path = os.path.join(root, name)
            sources[path] = open(path, encoding="utf-8").read()
    # A note like "/* --card-bg: renamed */" must not count as a definition.
    sources = {path: re.sub(r"/\*.*?\*/|<!--.*?-->|\{#.*?#\}", "", text, flags=re.S) for path, text in sources.items()}
    defined = {m for text in sources.values() for m in re.findall(r"(--[\w-]+)\s*:", text)}
    undefined = sorted(
        f"{os.path.relpath(path, APP_DIR)}: {name}"
        for path, text in sources.items()
        for name in set(re.findall(r"var\(\s*(--[\w-]+)\s*\)", text))
        if name not in defined
    )
    assert not undefined, "var() without a definition or fallback:\n" + "\n".join(undefined)


def test_text_colours_are_readable_on_every_surface():
    """Body, muted and accent text appear on all five surfaces, so each pair
    needs WCAG AA 4.5:1 in both themes.

    The dark --text-muted reached only 4.3:1 on cards, which nobody noticed
    while --bg-secondary was undefined; once the widget headers got their
    background, their muted titles dropped to 3.8:1.

    --text-dim is left out on purpose: it sits near 2:1 and is an open ROADMAP
    item, not a regression this test should hide.
    """
    rules = _rules()
    texts = ("--text", "--text-muted", "--accent-text")
    surfaces = ("--bg", "--bg-card", "--bg-sidebar", "--bg-secondary", "--bg-hover")
    # Load every custom property, so a surface defined as var(--border) resolves.
    names = set(re.findall(r"(--[\w-]+)\s*:", rules[":root"]))
    dark_vars = {k: _prop(rules[":root"], k) for k in names}
    light_vars = {**dark_vars, **{k: v for k in names if (v := _prop(rules['[data-theme="light"]'], k))}}
    too_faint = []
    for theme, theme_vars in (("dark", dark_vars), ("light", light_vars)):
        for text in texts:
            for bg in surfaces:
                ratio = _contrast(_rgb(f"var({text})", theme_vars)[0], _rgb(f"var({bg})", theme_vars)[0])
                if ratio < 4.5:
                    too_faint.append(f"{text} on {bg} in {theme} theme: {ratio:.2f}:1")
    assert not too_faint, "Text below WCAG AA 4.5:1:\n" + "\n".join(too_faint)
