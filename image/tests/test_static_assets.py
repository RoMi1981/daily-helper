"""Front-end assets are served by the app itself.

htmx, Lucide and highlight.js used to come from unpkg and cdnjs at runtime —
without integrity checks, and Lucide as `@latest`, so every new release reached
the page unreviewed. On a LAN without internet the UI lost all interactivity and
icons. They now live in `static/vendor/`; these checks keep it that way and make
sure every referenced file is actually there.
"""

import re
from pathlib import Path

_here = Path(__file__).resolve().parent
APP = next(p for p in (_here.parent / "app", _here.parent) if (p / "templates").is_dir())
TEMPLATES = APP / "templates"

_EXTERNAL_ASSET = re.compile(
    r"""<script[^>]+src=["']https?://|<link[^>]+rel=["']stylesheet["'][^>]+href=["']https?://"""
    r"""|<link[^>]+href=["']https?://[^"']+["'][^>]+rel=["']stylesheet|['"]https?://(?:unpkg\.com|cdnjs\.|cdn\.jsdelivr)""",
    re.I,
)
_STATIC_REF = re.compile(r"""["'](/static/[^"'?#{}]+)""")


def _templates():
    return sorted(TEMPLATES.rglob("*.html"))


def test_no_assets_from_external_hosts():
    offenders = [
        f"{p.relative_to(TEMPLATES)}: {m.group(0)}"
        for p in _templates()
        for m in _EXTERNAL_ASSET.finditer(p.read_text())
    ]
    assert not offenders, "Vendor the file into static/vendor/ instead:\n" + "\n".join(offenders)


def test_every_referenced_static_file_exists():
    missing = sorted(
        {
            f"{p.relative_to(TEMPLATES)}: {ref}"
            for p in _templates()
            for ref in _STATIC_REF.findall(p.read_text())
            if not (APP / ref.lstrip("/")).is_file()
        }
    )
    assert not missing, "Referenced static files are missing:\n" + "\n".join(missing)


def test_rules_catch_the_old_cdn_tags():
    old = '<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>'
    assert _EXTERNAL_ASSET.search(old)
    theme_swap = "? 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css'"
    assert _EXTERNAL_ASSET.search(theme_swap)
    assert not _EXTERNAL_ASSET.search('<a href="https://endoflife.date">endoflife.date</a>')
