"""Router tests for the widget dashboard."""

import os
import sys

import pytest

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = _candidate if os.path.isdir(_candidate) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

os.environ["REDIS_URL"] = "redis://localhost:9999"
os.environ.setdefault("DATA_DIR", "/tmp/daily-helper-test")

import main as _main_module


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import importlib

    from core import settings_store

    importlib.reload(settings_store)
    _main_module.settings_store = settings_store
    yield
    from core.state import reset_storage

    reset_storage()


@pytest.fixture()
def client(isolated_settings):
    from fastapi.testclient import TestClient

    return TestClient(_main_module.app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# GET /widgets — _get_layout behaviour (tested via HTTP)
# ---------------------------------------------------------------------------


class TestGetLayout:
    def test_returns_defaults_when_never_configured(self, client):
        """First-time user gets default widgets — page contains a default active widget."""
        from modules.widgets.registry import _DEFAULT_LAYOUT

        r = client.get("/widgets")
        assert r.status_code == 200
        default_active = [e["id"] for e in _DEFAULT_LAYOUT if e.get("enabled", True)]
        assert any(wid in r.text for wid in default_active)

    def test_empty_saved_layout_not_replaced_by_defaults(self, client):
        """Empty saved layout is respected — defaults are NOT re-added after remove-all."""
        client.post("/widgets/layout", json=[])
        r = client.get("/widgets")
        assert r.status_code == 200
        # add-panel must render so the user can add widgets back
        assert "add-widget-panel" in r.text

    def test_returns_exactly_what_was_saved(self, client):
        """Only the saved widget is active — no silent merging with defaults."""
        client.post("/widgets/layout", json=[{"id": "motd", "enabled": True}])
        r = client.get("/widgets")
        assert r.status_code == 200
        assert 'data-id="motd"' in r.text


# ---------------------------------------------------------------------------
# GET /widgets — available_widgets panel
# ---------------------------------------------------------------------------


class TestWidgetsDashboard:
    def test_page_loads(self, client):
        r = client.get("/widgets")
        assert r.status_code == 200

    def test_available_widgets_shown_when_layout_empty(self, client):
        """After remove-all the add-widget panel must still render."""
        client.post("/widgets/layout", json=[])
        r = client.get("/widgets")
        assert r.status_code == 200
        assert "add-widget-panel" in r.text

    def test_active_widget_not_in_add_panel(self, client):
        """A widget active in the grid must NOT appear as a checkbox in the add-panel."""
        client.post("/widgets/layout", json=[{"id": "motd", "enabled": True}])
        r = client.get("/widgets")
        assert r.status_code == 200
        # avail-widget-cb is the class used only in the add-panel
        assert 'class="avail-widget-cb" data-id="motd"' not in r.text

    def test_default_layout_on_first_visit(self, client):
        """First visit shows the default active widgets."""
        from modules.widgets.registry import _DEFAULT_LAYOUT

        r = client.get("/widgets")
        assert r.status_code == 200
        default_active = [e["id"] for e in _DEFAULT_LAYOUT if e.get("enabled", True)]
        for wid in default_active[:3]:
            assert wid in r.text


# ---------------------------------------------------------------------------
# POST /widgets/layout — save_layout
# ---------------------------------------------------------------------------


class TestSaveLayout:
    def test_save_empty_layout(self, client):
        """Remove-all: saving [] persists empty layout."""
        r = client.post("/widgets/layout", json=[])
        assert r.status_code == 200
        assert r.json() == {"ok": True}

        # Verify by loading the page — no active widgets, add-panel present
        r2 = client.get("/widgets")
        assert "add-widget-panel" in r2.text

    def test_save_preserves_order(self, client):
        """Layout order from client is stored and returned in the same order."""
        payload = [
            {"id": "motd", "enabled": True},
            {"id": "calendar_mini", "enabled": True},
        ]
        client.post("/widgets/layout", json=payload)
        r = client.get("/widgets")
        assert r.status_code == 200
        # motd should appear before calendar_mini in the HTML
        assert r.text.index('data-id="motd"') < r.text.index('data-id="calendar_mini"')

    def test_unknown_widget_ids_are_ignored(self, client):
        """Widgets not in WIDGET_REGISTRY must not be saved."""
        r = client.post("/widgets/layout", json=[{"id": "nonexistent_widget", "enabled": True}])
        assert r.status_code == 200
        # No active widget in the grid (unknown id filtered out)
        r2 = client.get("/widgets")
        assert 'data-id="nonexistent_widget"' not in r2.text

    def test_remove_all_then_add_back(self, client):
        """Full round-trip: remove all, then add one back — widget appears in grid."""
        client.post("/widgets/layout", json=[])
        client.post("/widgets/layout", json=[{"id": "motd", "enabled": True}])
        r = client.get("/widgets")
        assert r.status_code == 200
        assert 'data-id="motd"' in r.text

    def test_omitted_widgets_not_re_added(self, client):
        """Widgets absent from the save payload are not silently added back."""
        client.post(
            "/widgets/layout",
            json=[
                {"id": "motd", "enabled": True},
                {"id": "calendar_mini", "enabled": True},
            ],
        )
        # Save with only motd
        client.post("/widgets/layout", json=[{"id": "motd", "enabled": True}])
        r = client.get("/widgets")
        assert r.status_code == 200
        assert 'data-id="motd"' in r.text
        # calendar_mini must NOT be in the active grid
        assert 'class="avail-widget-cb" data-id="calendar_mini"' in r.text

    def test_save_widget_settings_in_payload(self, client):
        """Settings passed in payload are persisted."""
        client.post(
            "/widgets/layout",
            json=[{"id": "tasks_due", "enabled": True, "settings": {"max_items": 3}}],
        )
        # Re-save same widget — settings should survive a round-trip
        r = client.post(
            "/widgets/layout",
            json=[{"id": "tasks_due", "enabled": True, "settings": {"max_items": 3}}],
        )
        assert r.json()["ok"] is True


# ---------------------------------------------------------------------------
# POST /widgets/{widget_id}/settings
# ---------------------------------------------------------------------------


class TestSaveWidgetSettings:
    def test_unknown_widget_returns_404(self, client):
        r = client.post("/widgets/bogus_widget/settings", json={})
        assert r.status_code == 404

    def test_updates_settings_for_known_widget(self, client):
        # Add widget to layout first
        client.post("/widgets/layout", json=[{"id": "tasks_due", "enabled": True}])
        r = client.post("/widgets/tasks_due/settings", json={"max_items": 10})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_non_dict_settings_rejected(self, client):
        client.post("/widgets/layout", json=[{"id": "tasks_due", "enabled": True}])
        r = client.post("/widgets/tasks_due/settings", json=["not", "a", "dict"])
        assert r.status_code == 400

    def test_oversized_settings_rejected(self, client):
        client.post("/widgets/layout", json=[{"id": "tasks_due", "enabled": True}])
        r = client.post("/widgets/tasks_due/settings", json={"max_items": "x" * 20_000})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Unit tests — _load_countdown
# ---------------------------------------------------------------------------


class TestWidgetLoaderCountdown:
    def _fn(self, settings):
        from modules.widgets.loaders import _load_countdown

        return _load_countdown(settings)

    def test_no_date_configured(self):
        result = self._fn({})
        assert result == {"configured": False}

    def test_empty_string_date(self):
        result = self._fn({"target_date": ""})
        assert result == {"configured": False}

    def test_invalid_date(self):
        result = self._fn({"target_date": "not-a-date"})
        assert result == {"configured": False}

    def test_future_date(self):
        from datetime import date, timedelta

        future = (date.today() + timedelta(days=10)).isoformat()
        result = self._fn({"target_date": future})
        assert result["configured"] is True
        assert result["days"] > 0

    def test_today_date(self):
        from datetime import date

        result = self._fn({"target_date": date.today().isoformat()})
        assert result["configured"] is True
        assert result["days"] == 0

    def test_past_date(self):
        from datetime import date, timedelta

        past = (date.today() - timedelta(days=5)).isoformat()
        result = self._fn({"target_date": past})
        assert result["configured"] is True
        assert result["days"] < 0

    def test_label_is_used(self):
        from datetime import date, timedelta

        future = (date.today() + timedelta(days=1)).isoformat()
        result = self._fn({"target_date": future, "label": "Release Day"})
        assert result["label"] == "Release Day"

    def test_default_label_when_empty(self):
        from datetime import date, timedelta

        future = (date.today() + timedelta(days=1)).isoformat()
        result = self._fn({"target_date": future, "label": ""})
        assert result["label"] == "Countdown"


# ---------------------------------------------------------------------------
# Unit tests — _load_tmp_usage
# ---------------------------------------------------------------------------


class TestWidgetLoaderTmpUsage:
    def test_returns_expected_keys(self):
        from modules.widgets.loaders import _load_tmp_usage

        result = _load_tmp_usage()
        assert result is not None
        assert "total" in result
        assert "used" in result
        assert "free" in result

    def test_values_are_positive(self):
        from modules.widgets.loaders import _load_tmp_usage

        result = _load_tmp_usage()
        assert result["total"] > 0
        assert result["used"] <= result["total"]


# ---------------------------------------------------------------------------
# Unit tests — _load_app_version
# ---------------------------------------------------------------------------


class TestWidgetLoaderAppVersion:
    def test_returns_version_key(self):
        from modules.widgets.loaders import _load_app_version

        result = _load_app_version()
        assert "version" in result

    def test_uses_env_var(self, monkeypatch):
        monkeypatch.setenv("APP_VERSION", "v1.2.3-test")
        # Reload to pick up env var (function reads os.environ at call time)
        from modules.widgets.loaders import _load_app_version

        result = _load_app_version()
        assert result["version"] == "v1.2.3-test"

    def test_default_when_env_var_absent(self, monkeypatch):
        monkeypatch.delenv("APP_VERSION", raising=False)
        from modules.widgets.loaders import _load_app_version

        result = _load_app_version()
        assert result["version"] == "dev"


# ---------------------------------------------------------------------------
# Unit tests — _load_repos_widget
# ---------------------------------------------------------------------------


class TestWidgetLoaderRepos:
    def test_none_storage_returns_empty(self):
        from modules.widgets.loaders import _load_repos_widget

        assert _load_repos_widget(None) == []

    def test_storage_without_stores_returns_empty(self):
        from modules.widgets.loaders import _load_repos_widget

        class FakeStorage:
            pass

        assert _load_repos_widget(FakeStorage()) == []

    def test_storage_with_empty_stores(self):
        from modules.widgets.loaders import _load_repos_widget

        class FakeStorage:
            _stores = {}

        assert _load_repos_widget(FakeStorage()) == []


# ---------------------------------------------------------------------------
# Unit tests — _load_counts
# ---------------------------------------------------------------------------


class TestLoadCounts:
    def test_no_storage_returns_empty(self):
        from modules.widgets.loaders import _load_counts

        assert _load_counts({}, None) == {}

    def test_needed_restricts_computed_modules(self, monkeypatch):
        """Only stats widgets actually on the dashboard should be counted —
        enabling one stats widget must not compute all ~13 module counts."""
        from unittest.mock import MagicMock

        import modules.widgets.loaders as widgets_router

        fake_storage = MagicMock()
        fake_storage._stores = {"repo1": MagicMock()}

        calls: list[str] = []

        def fake_get_module_stores(module, storage):
            calls.append(module)
            return []

        monkeypatch.setattr(widgets_router, "get_module_stores", fake_get_module_stores)

        counts = widgets_router._load_counts({}, fake_storage, needed={"tasks"})

        assert counts == {"tasks": 0}
        assert calls == ["tasks"]

    def test_knowledge_counts_md_files_only(self, monkeypatch):
        """Knowledge count must count .md entries directly (cheap listing),
        not parse every file's frontmatter via get_entries()."""
        from unittest.mock import MagicMock

        import modules.widgets.loaders as widgets_router

        fake_store = MagicMock()
        fake_store.list_committed_recursive.return_value = [
            "a.md",
            "b.md",
            "notes.yaml",
        ]
        fake_storage = MagicMock()
        fake_storage._stores = {"repo1": fake_store}
        monkeypatch.setattr(widgets_router, "get_module_stores", lambda module, storage: [fake_store])

        counts = widgets_router._load_counts({}, fake_storage, needed={"knowledge"})

        assert counts == {"knowledge": 2}
        fake_store.get_entries.assert_not_called()

    def test_every_stats_widget_module_is_counted(self, monkeypatch):
        """Every stats_* widget in WIDGET_REGISTRY must have a counter in
        _load_counts. Registering the widget without adding its count makes
        the tile silently render 0 with no error anywhere — that is exactly
        how stats_eol shipped broken."""
        from unittest.mock import MagicMock

        import modules.widgets.loaders as widgets_router
        from modules.widgets.registry import WIDGET_REGISTRY

        fake_store = MagicMock()
        fake_store.list_committed.return_value = ["x.yaml"]
        fake_store.list_committed_recursive.return_value = ["x.yaml", "x.md"]
        fake_storage = MagicMock()
        fake_storage._stores = {"repo1": fake_store}
        monkeypatch.setattr(widgets_router, "get_module_stores", lambda module, storage: [fake_store])

        stats_modules = {
            spec["module"] for wid, spec in WIDGET_REGISTRY.items() if wid.startswith("stats_") and spec.get("module")
        }
        counts = widgets_router._load_counts({}, fake_storage, needed=stats_modules)

        missing = sorted(stats_modules - set(counts))
        assert not missing, f"stats widget(s) without a count in _load_counts: {missing}"

    def test_eol_entries_are_counted(self, monkeypatch):
        """Regression: stats_eol rendered 0 despite existing entries because
        _load_counts had no `eol` branch at all."""
        from unittest.mock import MagicMock

        import modules.widgets.loaders as widgets_router

        fake_store = MagicMock()
        fake_store.list_committed.return_value = ["a.yaml", "b.yaml", "README.md"]
        fake_storage = MagicMock()
        fake_storage._stores = {"repo1": fake_store}
        monkeypatch.setattr(widgets_router, "get_module_stores", lambda module, storage: [fake_store])

        counts = widgets_router._load_counts({}, fake_storage, needed={"eol"})

        assert counts == {"eol": 2}
        fake_store.list_committed.assert_called_with("eol")


# ---------------------------------------------------------------------------
# Unit tests — _load_calendar_widget
# ---------------------------------------------------------------------------


class TestWidgetLoaderCalendarWidget:
    def test_none_year_month_uses_today(self):
        from datetime import date

        from modules.widgets.loaders import _load_calendar_widget

        today = date.today()
        result = _load_calendar_widget(None, None, {}, None)
        assert result["year"] == today.year
        assert result["month"] == today.month

    def test_specific_year_month(self):
        from modules.widgets.loaders import _load_calendar_widget

        result = _load_calendar_widget(2025, 6, {}, None)
        assert result["year"] == 2025
        assert result["month"] == 6

    def test_month_name_returned(self):
        from modules.widgets.loaders import _load_calendar_widget

        result = _load_calendar_widget(2026, 1, {}, None)
        assert result["month_name"] == "Januar"

    def test_all_expected_keys_present(self):
        from modules.widgets.loaders import _load_calendar_widget

        result = _load_calendar_widget(2026, 3, {}, None)
        for key in (
            "year",
            "month",
            "month_name",
            "weeks",
            "prev_year",
            "prev_month",
            "next_year",
            "next_month",
            "weekday_headers",
        ):
            assert key in result, f"Missing key: {key}"

    def test_january_prev_is_december_prior_year(self):
        from modules.widgets.loaders import _load_calendar_widget

        result = _load_calendar_widget(2026, 1, {}, None)
        assert result["prev_month"] == 12
        assert result["prev_year"] == 2025

    def test_december_next_is_january_next_year(self):
        from modules.widgets.loaders import _load_calendar_widget

        result = _load_calendar_widget(2025, 12, {}, None)
        assert result["next_month"] == 1
        assert result["next_year"] == 2026

    def test_none_storage_no_exception(self):
        from modules.widgets.loaders import _load_calendar_widget

        # Must not raise — storage=None is a valid "no repos" scenario
        result = _load_calendar_widget(2026, 4, {}, None)
        assert result["year"] == 2026

    def test_weeks_is_list_of_lists(self):
        from modules.widgets.loaders import _load_calendar_widget

        result = _load_calendar_widget(2026, 1, {}, None)
        assert isinstance(result["weeks"], list)
        assert all(isinstance(week, list) for week in result["weeks"])

    def test_weekday_headers_has_seven_entries(self):
        from modules.widgets.loaders import _load_calendar_widget

        result = _load_calendar_widget(2026, 1, {}, None)
        assert len(result["weekday_headers"]) == 7


# ---------------------------------------------------------------------------
# Unit tests — _load_redis_status
# ---------------------------------------------------------------------------


class TestWidgetLoaderRedisStatus:
    def test_not_connected_when_redis_unreachable(self):
        # REDIS_URL points to localhost:9999 which is not running
        from modules.widgets.loaders import _load_redis_status

        result = _load_redis_status()
        assert result == {"connected": False}

    def test_monkeypatched_not_connected(self, monkeypatch):
        import core.cache as _cache
        from modules.widgets.loaders import _load_redis_status

        monkeypatch.setattr(_cache, "is_connected", lambda: False)
        result = _load_redis_status()
        assert result["connected"] is False


# ---------------------------------------------------------------------------
# HTTP — GET /widgets/calendar-partial
# ---------------------------------------------------------------------------


class TestCalendarPartial:
    def test_returns_200(self, client):
        r = client.get("/widgets/calendar-partial")
        assert r.status_code == 200

    def test_january_contains_januar(self, client):
        r = client.get("/widgets/calendar-partial?year=2026&month=1")
        assert r.status_code == 200
        assert "Januar" in r.text

    def test_december_contains_dezember(self, client):
        r = client.get("/widgets/calendar-partial?year=2026&month=12")
        assert r.status_code == 200
        assert "Dezember" in r.text

    def test_contains_hx_get_prev_next_buttons(self, client):
        r = client.get("/widgets/calendar-partial?year=2026&month=6")
        assert r.status_code == 200
        assert "hx-get" in r.text

    def test_contains_seven_weekday_headers(self, client):
        r = client.get("/widgets/calendar-partial?year=2026&month=1")
        assert r.status_code == 200
        # Default locale is "de" — headers are Mo, Di, Mi, Do, Fr, Sa, So
        weekday_headers_de = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        for header in weekday_headers_de:
            assert header in r.text

    def test_invalid_month_rejected(self, client):
        r = client.get("/widgets/calendar-partial?year=2026&month=13")
        assert r.status_code == 400

    def test_negative_month_rejected(self, client):
        r = client.get("/widgets/calendar-partial?year=2026&month=-5")
        assert r.status_code == 400

    def test_year_out_of_range_rejected(self, client):
        r = client.get("/widgets/calendar-partial?year=99999&month=1")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# HTTP — widget rendering (parametrized)
# ---------------------------------------------------------------------------

from modules.widgets.registry import WIDGET_REGISTRY

_RENDERABLE_WIDGETS = list(WIDGET_REGISTRY.keys())


class TestWidgetRendering:
    @pytest.mark.parametrize("widget_id", _RENDERABLE_WIDGETS)
    def test_widget_renders_without_crash(self, client, widget_id):
        """Each widget can be activated and the dashboard loads without 500."""
        r = client.post("/widgets/layout", json=[{"id": widget_id, "enabled": True}])
        assert r.status_code == 200
        r2 = client.get("/widgets")
        assert r2.status_code == 200
        assert f'data-id="{widget_id}"' in r2.text


# ---------------------------------------------------------------------------
# HTTP — countdown widget settings round-trip
# ---------------------------------------------------------------------------


class TestCountdownWidgetSettings:
    def test_settings_persisted_and_visible_in_popover(self, client):
        """Activate countdown, save settings, reload page — settings appear in popover."""
        # 1. Activate the countdown widget
        client.post("/widgets/layout", json=[{"id": "countdown", "enabled": True}])

        # 2. Save settings via the dedicated endpoint
        from datetime import date, timedelta

        target = (date.today() + timedelta(days=30)).isoformat()
        r = client.post(
            "/widgets/countdown/settings",
            json={"label": "Launch Day", "target_date": target},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # 3. Reload the page — settings must be visible in the widget/popover
        r2 = client.get("/widgets")
        assert r2.status_code == 200
        assert "Launch Day" in r2.text
        assert target in r2.text


# ---------------------------------------------------------------------------
# Unit tests for widget loader functions
# ---------------------------------------------------------------------------


class TestLoadMotd:
    def test_returns_empty_when_no_storage(self):
        from modules.widgets.loaders import _load_motd

        assert _load_motd(None) == ""

    def test_uses_date_based_seed(self):
        """Result matches today_int % len(entries) — not always index 0."""
        from datetime import date
        from unittest.mock import MagicMock, patch

        import modules.widgets.loaders as wr

        entries = [{"id": str(i), "active": True, "text": f"msg{i}"} for i in range(7)]
        fake_store = MagicMock()
        fake_storage = MagicMock()
        fake_storage._stores = [fake_store]

        with patch("modules.widgets.loaders.get_module_stores", return_value=[fake_store]):
            from modules.motd.storage import MotdStorage

            with patch.object(MotdStorage, "list_entries", return_value=entries):
                result = wr._load_motd(fake_storage)

        today_int = int(date.today().strftime("%Y%m%d"))
        expected = entries[today_int % len(entries)]["text"]
        assert result == expected

    def test_returns_empty_when_no_active_entries(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        import modules.widgets.loaders as wr

        fake_store = MagicMock()
        fake_storage = MagicMock()
        fake_storage._stores = [fake_store]

        with patch("modules.widgets.loaders.get_module_stores", return_value=[fake_store]):
            from modules.motd.storage import MotdStorage

            with patch.object(
                MotdStorage,
                "list_entries",
                return_value=[{"id": "x", "active": False, "text": "hi"}],
            ):
                result = wr._load_motd(fake_storage)

        assert result == ""


class TestVacationEntriesCached:
    def test_second_call_with_same_cache_skips_refetch(self, monkeypatch):
        """Widgets sharing one request's vac_cache must only hit storage once."""
        from unittest.mock import MagicMock, patch

        import modules.widgets.loaders as widgets_router

        fake_store = MagicMock()
        fake_storage = MagicMock()
        fake_storage._stores = {"repo1": fake_store}
        monkeypatch.setattr(widgets_router, "get_module_stores", lambda module, storage: [fake_store])

        with patch("modules.vacations.storage.VacationStorage") as MockVS:
            MockVS.return_value.list_entries.return_value = [{"id": "v1", "start_date": "2026-01-01"}]
            cache: dict = {}
            first = widgets_router._vacation_entries_cached(fake_storage, cache)
            second = widgets_router._vacation_entries_cached(fake_storage, cache)

        assert first == second == [{"id": "v1", "start_date": "2026-01-01"}]
        MockVS.return_value.list_entries.assert_called_once()

    def test_different_years_are_not_conflated(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        import modules.widgets.loaders as widgets_router

        fake_store = MagicMock()
        fake_storage = MagicMock()
        fake_storage._stores = {"repo1": fake_store}
        monkeypatch.setattr(widgets_router, "get_module_stores", lambda module, storage: [fake_store])

        with patch("modules.vacations.storage.VacationStorage") as MockVS:
            MockVS.return_value.list_entries.side_effect = lambda year=None: [
                {"id": f"v-{year}", "start_date": f"{year}-01-01"}
            ]
            cache: dict = {}
            all_entries = widgets_router._vacation_entries_cached(fake_storage, cache)
            year_entries = widgets_router._vacation_entries_cached(fake_storage, cache, 2026)

        assert all_entries != year_entries
        assert MockVS.return_value.list_entries.call_count == 2


class TestLoadVacationBalance:
    def test_returns_none_when_no_storage(self):
        from modules.widgets.loaders import _load_vacation_balance

        assert _load_vacation_balance({}, None) is None

    def test_carryover_added_to_total(self, monkeypatch):
        """vacation_carryover must be included in total_days."""
        from unittest.mock import MagicMock, patch

        from modules.widgets.loaders import _load_vacation_balance

        cfg = {
            "vacation_days_per_year": 30,
            "vacation_carryover": 5,
            "vacation_state": "BY",
        }
        fake_storage = MagicMock()
        fake_storage._stores = [MagicMock()]

        with patch("modules.widgets.loaders.get_module_stores", return_value=[MagicMock()]):
            with patch("modules.vacations.storage.VacationStorage") as MockVS:
                instance = MockVS.return_value
                instance.list_entries.return_value = []
                instance.get_account.side_effect = lambda yr, total, state, entries=None: {
                    "year": yr,
                    "total_days": total,
                    "used_days": 0,
                    "planned_days": 0,
                    "remaining_days": total,
                    "remaining_after_planned": total,
                    "entries": [],
                }
                result = _load_vacation_balance(cfg, fake_storage)

        assert result is not None
        assert result["total_days"] == 35  # 30 + 5 carryover


class TestLoadPotd:
    def test_returns_none_when_no_entries(self):
        from unittest.mock import patch

        from modules.widgets.loaders import _load_potd

        with patch("modules.widgets.loaders.get_module_stores", return_value=[]):
            result = _load_potd()

        assert result is None

    def test_returns_entry_with_ext_field(self):
        from unittest.mock import MagicMock, patch

        from modules.widgets.loaders import _load_potd

        fake_entry = {
            "id": "abc123",
            "ext": "jpg",
            "filename": "abc123.jpg",
            "page": None,
            "source": None,
        }
        with patch("modules.widgets.loaders.get_module_stores", return_value=[MagicMock()]):
            with patch("modules.potd.router.get_daily_all", return_value=fake_entry):
                result = _load_potd()

        assert result is not None
        assert result["ext"] == "jpg"


# ---------------------------------------------------------------------------
# Unit — _load_eol_expiring
# ---------------------------------------------------------------------------


class TestLoadEolExpiring:
    def test_returns_empty_when_no_storage(self):
        from modules.widgets.loaders import _load_eol_expiring

        assert _load_eol_expiring({}, None) == []

    def test_returns_empty_when_storage_has_no_stores(self):
        from unittest.mock import MagicMock

        from modules.widgets.loaders import _load_eol_expiring

        storage = MagicMock()
        del storage._stores
        assert _load_eol_expiring({}, storage) == []

    def test_expiring_item_returned(self, monkeypatch):
        """Item expiring within days_ahead window is included in results."""
        from datetime import date, timedelta
        from unittest.mock import MagicMock, patch

        from modules.widgets.loaders import _load_eol_expiring

        today = date.today()
        eol_soon = today + timedelta(days=30)

        fake_storage = MagicMock()
        fake_storage._stores = [MagicMock()]

        entries = [{"id": "e1", "product": "ubuntu", "cycle": "20.04", "label": "Ubuntu 20.04"}]

        with patch("modules.widgets.loaders.get_primary_store", return_value=MagicMock()):
            with patch("modules.eol.storage.EolStorage") as MockEol:
                MockEol.return_value.list_entries.return_value = entries
                with patch(
                    "modules.eol.api_client.get_product_cycles",
                    return_value=[{"cycle": "20.04", "eol": eol_soon.isoformat()}],
                ):
                    with patch("modules.eol.api_client._parse_date", return_value=eol_soon):
                        result = _load_eol_expiring({"days_ahead": 90}, fake_storage)

        assert len(result) == 1
        assert result[0]["product"] == "ubuntu"
        assert result[0]["days_left"] == 30
        assert result[0]["expired"] is False

    def test_item_beyond_cutoff_excluded(self, monkeypatch):
        """Item expiring after days_ahead window is not included."""
        from datetime import date, timedelta
        from unittest.mock import MagicMock, patch

        from modules.widgets.loaders import _load_eol_expiring

        today = date.today()
        eol_far = today + timedelta(days=200)

        fake_storage = MagicMock()
        fake_storage._stores = [MagicMock()]

        entries = [{"id": "e1", "product": "ubuntu", "cycle": "20.04", "label": "Ubuntu 20.04"}]

        with patch("modules.widgets.loaders.get_primary_store", return_value=MagicMock()):
            with patch("modules.eol.storage.EolStorage") as MockEol:
                MockEol.return_value.list_entries.return_value = entries
                with patch(
                    "modules.eol.api_client.get_product_cycles",
                    return_value=[{"cycle": "20.04", "eol": eol_far.isoformat()}],
                ):
                    with patch("modules.eol.api_client._parse_date", return_value=eol_far):
                        result = _load_eol_expiring({"days_ahead": 90}, fake_storage)

        assert result == []

    def test_expired_item_included_with_negative_days_left(self):
        """Already-expired item (eol in past) is included and marked expired."""
        from datetime import date, timedelta
        from unittest.mock import MagicMock, patch

        from modules.widgets.loaders import _load_eol_expiring

        today = date.today()
        eol_past = today - timedelta(days=10)

        fake_storage = MagicMock()
        fake_storage._stores = [MagicMock()]

        entries = [{"id": "e1", "product": "ubuntu", "cycle": "18.04", "label": "Ubuntu 18.04"}]

        with patch("modules.widgets.loaders.get_primary_store", return_value=MagicMock()):
            with patch("modules.eol.storage.EolStorage") as MockEol:
                MockEol.return_value.list_entries.return_value = entries
                with patch(
                    "modules.eol.api_client.get_product_cycles",
                    return_value=[{"cycle": "18.04", "eol": eol_past.isoformat()}],
                ):
                    with patch("modules.eol.api_client._parse_date", return_value=eol_past):
                        result = _load_eol_expiring({"days_ahead": 90}, fake_storage)

        assert len(result) == 1
        assert result[0]["expired"] is True
        assert result[0]["days_left"] == -10

    def test_results_sorted_by_days_left(self):
        """Results are sorted ascending by days_left (most urgent first)."""
        from datetime import date, timedelta
        from unittest.mock import MagicMock, patch

        from modules.widgets.loaders import _load_eol_expiring

        today = date.today()
        eol_a = today + timedelta(days=60)
        eol_b = today + timedelta(days=10)

        fake_storage = MagicMock()
        fake_storage._stores = [MagicMock()]

        entries = [
            {"id": "e1", "product": "prod_a", "cycle": "1.0", "label": "Prod A"},
            {"id": "e2", "product": "prod_b", "cycle": "2.0", "label": "Prod B"},
        ]

        def mock_cycles(product):
            if product == "prod_a":
                return [{"cycle": "1.0", "eol": eol_a.isoformat()}]
            return [{"cycle": "2.0", "eol": eol_b.isoformat()}]

        def mock_parse(val):
            if "+" in val or str(eol_a.isoformat()) == val:
                return eol_a
            return eol_b

        with patch("modules.widgets.loaders.get_primary_store", return_value=MagicMock()):
            with patch("modules.eol.storage.EolStorage") as MockEol:
                MockEol.return_value.list_entries.return_value = entries
                with patch("modules.eol.api_client.get_product_cycles", side_effect=mock_cycles):
                    with patch(
                        "modules.eol.api_client._parse_date",
                        side_effect=lambda v: eol_a if v == eol_a.isoformat() else eol_b,
                    ):
                        result = _load_eol_expiring({"days_ahead": 90}, fake_storage)

        assert len(result) == 2
        assert result[0]["days_left"] < result[1]["days_left"]


class TestLoaderDispatch:
    """The dispatch table replaced an if/elif cascade. A widget that falls out
    of it renders empty without any error, so the link between registry and
    table has to be checked here rather than in the browser."""

    def test_every_data_widget_has_a_loader(self):
        from modules.widgets.loaders import _WIDGET_LOADERS
        from modules.widgets.registry import WIDGET_REGISTRY

        # stats_* widgets render from `counts`, quick_capture is a pure form.
        expected = {wid for wid in WIDGET_REGISTRY if not wid.startswith("stats_") and wid != "quick_capture"}
        assert set(_WIDGET_LOADERS) == expected

    def test_loaders_return_a_mapping_of_template_variables(self):
        from modules.widgets.loaders import _WIDGET_LOADERS, _LoaderContext

        ctx = _LoaderContext(cfg={}, storage=None, vac_cache={}, task_cache={}, appt_cache={})
        result = _WIDGET_LOADERS["countdown"]({"target_date": "2099-01-01"}, ctx)
        assert isinstance(result, dict)
        assert "countdown" in result


class TestParallelLoading:
    """Loaders run in a thread pool via asyncio.gather. Sequential loading was
    the whole point of DASH-10, so the test has to prove overlap, not just that
    the page renders."""

    def test_loaders_run_concurrently(self, client, monkeypatch):
        import threading

        from modules.widgets import router as widgets_router

        started = threading.Barrier(2, timeout=5)
        overlapped = []

        def blocking_loader(settings, ctx):
            try:
                started.wait()  # only returns once a second loader is also inside
                overlapped.append(True)
            except threading.BrokenBarrierError:
                pass
            return {}

        monkeypatch.setattr(
            widgets_router,
            "_WIDGET_LOADERS",
            {"motd": blocking_loader, "tasks_due": blocking_loader},
        )
        client.post("/widgets/layout", json=[{"id": "motd"}, {"id": "tasks_due"}])

        resp = client.get("/widgets")
        assert resp.status_code == 200
        assert len(overlapped) == 2, "loaders ran one after the other"

    def test_one_failing_loader_does_not_take_down_the_dashboard(self, client, monkeypatch):
        from modules.widgets import router as widgets_router

        def boom(settings, ctx):
            raise RuntimeError("git unreachable")

        monkeypatch.setattr(
            widgets_router,
            "_WIDGET_LOADERS",
            {"motd": boom, "app_version": lambda s, c: {"app_version_info": {"version": "1.2.3"}}},
        )
        client.post("/widgets/layout", json=[{"id": "motd"}, {"id": "app_version"}])

        resp = client.get("/widgets")
        assert resp.status_code == 200
        assert "1.2.3" in resp.text
