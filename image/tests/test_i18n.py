"""Tests for core/i18n.py — translation lookup, fallback, formatting, cache."""

import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core import i18n


def _reset_i18n():
    i18n._LOCALES.clear()
    i18n._lang_cache = None
    i18n._lang_cache_ts = 0.0


class TestTranslate:
    def setup_method(self):
        _reset_i18n()

    def test_returns_known_translation(self):
        i18n._LOCALES["en"] = {"greeting": "Hello"}
        assert i18n.t("greeting", lang="en") == "Hello"

    def test_falls_back_to_key_when_missing(self):
        i18n._LOCALES["en"] = {}
        i18n._LOCALES["de"] = {}
        result = i18n.t("nonexistent.key", lang="de")
        assert result == "nonexistent.key"

    def test_falls_back_to_english_when_lang_missing(self):
        i18n._LOCALES["de"] = {}
        i18n._LOCALES["en"] = {"save": "Save"}
        result = i18n.t("save", lang="de")
        assert result == "Save"

    def test_string_formatting_with_kwargs(self):
        i18n._LOCALES["en"] = {"welcome": "Hello, {name}!"}
        result = i18n.t("welcome", lang="en", name="Alice")
        assert result == "Hello, Alice!"

    def test_missing_format_key_returns_unformatted(self):
        i18n._LOCALES["en"] = {"msg": "Hello, {name}!"}
        result = i18n.t("msg", lang="en")  # no name kwarg
        assert result == "Hello, {name}!"


class TestLangCache:
    def setup_method(self):
        _reset_i18n()

    def test_invalidate_lang_cache_forces_reload_on_next_call(self):
        mock_cfg = {"language": "de"}
        with patch("core.settings_store.load", return_value=mock_cfg):
            lang1 = i18n.get_current_lang()
        assert lang1 == "de"
        assert i18n._lang_cache == "de"

        i18n.invalidate_lang_cache()
        assert i18n._lang_cache is None

        mock_cfg2 = {"language": "fr"}
        with patch("core.settings_store.load", return_value=mock_cfg2):
            lang2 = i18n.get_current_lang()
        assert lang2 == "fr"

    def test_get_current_lang_defaults_to_en(self):
        with patch("core.settings_store.load", return_value={}):
            lang = i18n.get_current_lang()
        assert lang == "en"
