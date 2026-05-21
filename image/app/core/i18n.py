"""Lightweight i18n — loads JSON locale files, falls back to English."""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_LOCALES_DIR = Path(__file__).parent.parent / "locales"
_LOCALES: dict[str, dict] = {}

_lang_cache: str | None = None
_lang_cache_ts: float = 0.0
_LANG_CACHE_TTL = 30.0  # seconds


def _load_locale(lang: str) -> dict:
    if lang not in _LOCALES:
        path = _LOCALES_DIR / f"{lang}.json"
        if path.exists():
            try:
                _LOCALES[lang] = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to load locale %s: %s", lang, exc)
                _LOCALES[lang] = {}
        else:
            _LOCALES[lang] = {}
    return _LOCALES[lang]


def t(key: str, lang: str = "en", **kwargs) -> str:
    """Translate key to lang, falling back to English, then the key itself."""
    text = _load_locale(lang).get(key) or _load_locale("en").get(key) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def get_current_lang() -> str:
    """Return the configured UI language (cached for 30 s)."""
    global _lang_cache, _lang_cache_ts
    now = time.monotonic()
    if _lang_cache is None or now - _lang_cache_ts > _LANG_CACHE_TTL:
        from core import settings_store  # late import to avoid circles

        cfg = settings_store.load()
        _lang_cache = cfg.get("language", "en")
        _lang_cache_ts = now
    return _lang_cache


def invalidate_lang_cache() -> None:
    global _lang_cache
    _lang_cache = None
