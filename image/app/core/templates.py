import os
import re
from markupsafe import Markup, escape
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

_version = os.environ.get("APP_VERSION", "dev")
templates.env.globals["app_version"] = _version[:7] if len(_version) > 7 else _version

_URL_RE = re.compile(r'(https?://\S+)')

def _linkify(text: str) -> Markup:
    """Convert URLs in plain text to clickable links."""
    parts = _URL_RE.split(str(text))
    result = []
    for part in parts:
        if _URL_RE.match(part):
            url = escape(part)
            result.append(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>')
        else:
            result.append(str(escape(part)))
    return Markup("".join(result))

templates.env.filters["linkify"] = _linkify


def _strftime(ts, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Format a unix timestamp as a local datetime string."""
    from datetime import datetime
    try:
        return datetime.fromtimestamp(int(ts)).strftime(fmt)
    except Exception:
        return ""

templates.env.filters["strftime"] = _strftime


def _get_modules() -> dict:
    from core import settings_store
    return settings_store.load().get("modules_enabled", {"knowledge": True, "tasks": True, "vacations": True})

templates.env.globals["get_modules"] = _get_modules


def _get_repo_count() -> int:
    from core import settings_store
    return sum(1 for r in settings_store.load().get("repos", []) if r.get("enabled", True))

templates.env.globals["get_repo_count"] = _get_repo_count


def _get_theme_mode() -> str:
    from core import settings_store
    return settings_store.load().get("theme_mode", "auto")

templates.env.globals["get_theme_mode"] = _get_theme_mode
