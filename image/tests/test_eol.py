"""Tests for the EOL Tracker module — api_client, storage, router."""

import importlib
import json
import os
import sys
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("REDIS_URL", "redis://localhost:9999")
os.environ.setdefault("DATA_DIR", "/tmp/daily-helper-test")

_candidate = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
APP_DIR = (
    _candidate
    if os.path.isdir(_candidate)
    else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

import main as _main_module

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared FakeGit
# ---------------------------------------------------------------------------


class FakeGit:
    def __init__(self, path):
        self.local_path = str(path)
        self._committed = []

    def _pull(self):
        pass

    def _commit_and_push(self, msg):
        self._committed.append(msg)

    def read_committed(self, path):
        full = os.path.join(self.local_path, path)
        try:
            with open(full, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def list_committed(self, directory):
        full = os.path.join(self.local_path, directory)
        if not os.path.isdir(full):
            return []
        return os.listdir(full)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    from core import settings_store

    importlib.reload(settings_store)
    from core import settings_store as ss

    _main_module.settings_store = ss
    yield
    from core.state import reset_storage

    reset_storage()


@pytest.fixture()
def eol_client(isolated_settings, tmp_path):
    from core.state import reset_storage

    reset_storage()
    fake = FakeGit(tmp_path)
    with (
        patch("modules.eol.router.get_storage", return_value=None),
        patch("modules.eol.router.get_primary_store", return_value=fake),
        patch("modules.eol.router.get_module_stores", return_value=[fake]),
    ):
        yield TestClient(_main_module.app)


@pytest.fixture()
def eol_storage(tmp_path):
    from modules.eol.storage import EolStorage

    return EolStorage(FakeGit(tmp_path))


# ---------------------------------------------------------------------------
# api_client unit tests (no HTTP calls)
# ---------------------------------------------------------------------------


class TestApiClientStatus:
    def test_active_when_eol_false(self):
        from modules.eol.api_client import get_cycle_status

        assert get_cycle_status(False) == "active"

    def test_active_when_eol_none(self):
        from modules.eol.api_client import get_cycle_status

        assert get_cycle_status(None) == "active"

    def test_active_when_far_future(self):
        from modules.eol.api_client import get_cycle_status

        assert get_cycle_status("2099-01-01") == "active"

    def test_soon_within_90_days(self):
        from modules.eol.api_client import get_cycle_status
        from datetime import timedelta

        soon = (date.today() + timedelta(days=45)).isoformat()
        assert get_cycle_status(soon) == "soon"

    def test_eol_when_past(self):
        from modules.eol.api_client import get_cycle_status

        assert get_cycle_status("2020-01-01") == "eol"

    def test_unknown_on_invalid_date(self):
        from modules.eol.api_client import get_cycle_status

        assert get_cycle_status("not-a-date") == "unknown"

    def test_today_boundary_soon(self):
        from modules.eol.api_client import get_cycle_status

        assert get_cycle_status(date.today().isoformat()) == "soon"


class TestApiClientSearch:
    def test_search_empty_returns_empty(self):
        from modules.eol.api_client import search_products

        with patch("modules.eol.api_client.get_all_products", return_value=["python", "nodejs"]):
            assert search_products("") == []

    def test_search_filters_by_substring(self):
        from modules.eol.api_client import search_products

        products = ["python", "pypy", "nodejs", "ubuntu"]
        with patch("modules.eol.api_client.get_all_products", return_value=products):
            results = search_products("py")
            assert "python" in results
            assert "pypy" in results
            assert "nodejs" not in results

    def test_search_case_insensitive(self):
        from modules.eol.api_client import search_products

        with patch("modules.eol.api_client.get_all_products", return_value=["Python", "NODEJS"]):
            assert "Python" in search_products("python")

    def test_search_limits_to_20_results(self):
        from modules.eol.api_client import search_products

        products = [f"pkg-{i}" for i in range(50)]
        with patch("modules.eol.api_client.get_all_products", return_value=products):
            assert len(search_products("pkg")) == 20

    def test_search_api_error_returns_empty(self):
        from modules.eol.api_client import search_products

        with patch("modules.eol.api_client.get_all_products", return_value=[]):
            assert search_products("python") == []


class TestComputeTimeline:
    def _cycle(self, cycle, release, support, eol, ext=None, lts=False):
        c = {
            "cycle": cycle,
            "releaseDate": release,
            "support": support,
            "eol": eol,
            "lts": lts,
            "latest": cycle,
            "latestReleaseDate": release,
        }
        if ext is not None:
            c["extendedSupport"] = ext
        else:
            c["extendedSupport"] = False
        return c

    def test_empty_cycles_returns_empty(self):
        from modules.eol.api_client import compute_timeline

        result = compute_timeline([])
        assert result["cycles"] == []

    def test_returns_required_keys(self):
        from modules.eol.api_client import compute_timeline

        cycles = [self._cycle("3.11", "2022-10-24", "2024-04-01", "2027-10-31")]
        result = compute_timeline(cycles)
        assert "cycles" in result
        assert "year_marks" in result
        assert "today_pct" in result

    def test_two_phase_bar_with_support(self):
        from modules.eol.api_client import compute_timeline

        cycles = [self._cycle("3.11", "2022-01-01", "2024-01-01", "2026-01-01")]
        result = compute_timeline(cycles)
        bars = result["cycles"][0]["bars"]
        phases = [b["phase"] for b in bars]
        assert "active" in phases
        assert "security" in phases

    def test_single_phase_without_support(self):
        from modules.eol.api_client import compute_timeline

        cycles = [self._cycle("3.7", "2018-06-27", False, "2023-06-27")]
        result = compute_timeline(cycles)
        bars = result["cycles"][0]["bars"]
        assert len(bars) == 1
        assert bars[0]["phase"] == "active"

    def test_extended_support_bar(self):
        from modules.eol.api_client import compute_timeline

        cycles = [
            self._cycle(
                "22.04", "2022-04-21", "2027-04-02", "2027-04-02", ext="2032-04-02", lts=True
            )
        ]
        result = compute_timeline(cycles)
        phases = [b["phase"] for b in result["cycles"][0]["bars"]]
        assert "extended" in phases

    def test_today_pct_between_0_and_100(self):
        from modules.eol.api_client import compute_timeline

        cycles = [self._cycle("3.11", "2022-10-24", "2024-04-01", "2027-10-31")]
        result = compute_timeline(cycles)
        assert 0 <= result["today_pct"] <= 100

    def test_bar_widths_sum_within_100(self):
        from modules.eol.api_client import compute_timeline

        cycles = [self._cycle("3.11", "2022-10-24", "2024-04-01", "2027-10-31")]
        result = compute_timeline(cycles)
        total = sum(b["width"] for b in result["cycles"][0]["bars"])
        assert total <= 100.1  # small float tolerance

    def test_no_eol_bar_extends_to_edge(self):
        from modules.eol.api_client import compute_timeline

        cycles = [self._cycle("3.14", "2025-10-07", False, False)]
        result = compute_timeline(cycles)
        bars = result["cycles"][0]["bars"]
        assert bars[0]["phase"] == "unknown"
        assert bars[0]["width"] > 0

    def test_lts_flag_preserved(self):
        from modules.eol.api_client import compute_timeline

        cycles = [self._cycle("22.04", "2022-04-21", "2027-04-02", "2027-04-02", lts=True)]
        result = compute_timeline(cycles)
        assert result["cycles"][0]["lts"] is True

    def test_year_marks_contain_integers(self):
        from modules.eol.api_client import compute_timeline

        cycles = [self._cycle("3.11", "2022-10-24", "2024-04-01", "2027-10-31")]
        result = compute_timeline(cycles)
        for mark in result["year_marks"]:
            assert isinstance(mark["year"], int)
            assert 0 <= mark["pct"] <= 100


# ---------------------------------------------------------------------------
# EolStorage unit tests
# ---------------------------------------------------------------------------


class TestEolStorage:
    def test_list_empty(self, eol_storage):
        assert eol_storage.list_entries() == []

    def test_create_and_list(self, eol_storage):
        eol_storage.create_entry("python", "3.11", "Python 3.11")
        entries = eol_storage.list_entries()
        assert len(entries) == 1
        e = entries[0]
        assert e["product"] == "python"
        assert e["cycle"] == "3.11"
        assert e["label"] == "Python 3.11"

    def test_create_sets_id_and_created(self, eol_storage):
        e = eol_storage.create_entry("python", "3.11", "Python 3.11")
        assert len(e["id"]) == 8
        assert e["created"] == date.today().isoformat()

    def test_create_with_notes(self, eol_storage):
        e = eol_storage.create_entry("python", "3.11", "Python 3.11", notes="In prod")
        assert e["notes"] == "In prod"

    def test_get_entry(self, eol_storage):
        e = eol_storage.create_entry("python", "3.11", "Python 3.11")
        fetched = eol_storage.get_entry(e["id"])
        assert fetched["product"] == "python"

    def test_get_missing_returns_none(self, eol_storage):
        assert eol_storage.get_entry("doesnotexist") is None

    def test_update_notes(self, eol_storage):
        e = eol_storage.create_entry("python", "3.11", "Python 3.11")
        updated = eol_storage.update_notes(e["id"], "Updated note")
        assert updated["notes"] == "Updated note"
        assert eol_storage.get_entry(e["id"])["notes"] == "Updated note"

    def test_update_notes_missing_returns_none(self, eol_storage):
        assert eol_storage.update_notes("badid", "x") is None

    def test_delete_entry(self, eol_storage):
        e = eol_storage.create_entry("python", "3.11", "Python 3.11")
        assert eol_storage.delete_entry(e["id"]) is True
        assert eol_storage.list_entries() == []

    def test_delete_missing_returns_false(self, eol_storage):
        assert eol_storage.delete_entry("notexist") is False

    def test_is_tracked_true(self, eol_storage):
        eol_storage.create_entry("python", "3.11", "Python 3.11")
        assert eol_storage.is_tracked("python", "3.11") is True

    def test_is_tracked_false(self, eol_storage):
        assert eol_storage.is_tracked("python", "3.11") is False

    def test_sorted_by_product_then_cycle(self, eol_storage):
        eol_storage.create_entry("ubuntu", "22.04", "Ubuntu 22.04")
        eol_storage.create_entry("python", "3.12", "Python 3.12")
        eol_storage.create_entry("python", "3.11", "Python 3.11")
        entries = eol_storage.list_entries()
        products = [e["product"] for e in entries]
        assert products == sorted(products)

    def test_commit_on_create(self, eol_storage):
        eol_storage.create_entry("python", "3.11", "Python 3.11")
        assert any("track" in m for m in eol_storage._git._committed)

    def test_commit_on_delete(self, eol_storage):
        e = eol_storage.create_entry("python", "3.11", "Python 3.11")
        eol_storage._git._committed.clear()
        eol_storage.delete_entry(e["id"])
        assert len(eol_storage._git._committed) == 1


# ---------------------------------------------------------------------------
# Router tests
# ---------------------------------------------------------------------------

FAKE_CYCLES = [
    {
        "cycle": "3.11",
        "releaseDate": "2022-10-24",
        "eol": "2027-10-31",
        "support": "2024-04-01",
        "extendedSupport": False,
        "lts": False,
        "latest": "3.11.9",
        "latestReleaseDate": "2024-03-19",
    },
    {
        "cycle": "3.10",
        "releaseDate": "2021-10-04",
        "eol": "2026-10-04",
        "support": "2023-04-05",
        "extendedSupport": False,
        "lts": False,
        "latest": "3.10.14",
        "latestReleaseDate": "2024-03-19",
    },
]


class TestEolListRoute:
    def test_list_returns_200(self, eol_client):
        with patch("modules.eol.router._list_all_entries", return_value=[]):
            resp = eol_client.get("/eol")
        assert resp.status_code == 200

    def test_list_shows_empty_state(self, eol_client):
        with patch("modules.eol.router._list_all_entries", return_value=[]):
            resp = eol_client.get("/eol")
        assert "No software tracked yet" in resp.text

    def test_list_shows_tracked_entry(self, eol_client):
        entry = {
            "id": "abc123",
            "product": "python",
            "cycle": "3.11",
            "label": "Python 3.11",
            "notes": "",
            "created": "2026-01-01",
        }
        with (
            patch("modules.eol.router._list_all_entries", return_value=[entry]),
            patch("modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES),
        ):
            resp = eol_client.get("/eol")
        assert "python" in resp.text
        assert "3.11" in resp.text


class TestEolSearchRoute:
    def test_search_returns_200(self, eol_client):
        with patch("modules.eol.api_client.search_products", return_value=[]):
            resp = eol_client.get("/eol/search")
        assert resp.status_code == 200

    def test_search_shows_results(self, eol_client):
        with patch("modules.eol.api_client.search_products", return_value=["python", "pypy"]):
            resp = eol_client.get("/eol/search?q=py")
        assert "python" in resp.text
        assert "pypy" in resp.text

    def test_search_htmx_partial(self, eol_client):
        with patch("modules.eol.api_client.search_products", return_value=["ubuntu"]):
            resp = eol_client.get("/eol/search?q=ubu")
        assert resp.status_code == 200
        assert "ubuntu" in resp.text


class TestEolProductRoute:
    def test_product_returns_200(self, eol_client):
        with (
            patch("modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES),
            patch("modules.eol.router._get_all_storages", return_value=[]),
        ):
            resp = eol_client.get("/eol/product/python")
        assert resp.status_code == 200

    def test_product_shows_cycles(self, eol_client):
        with (
            patch("modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES),
            patch("modules.eol.router._get_all_storages", return_value=[]),
        ):
            resp = eol_client.get("/eol/product/python")
        assert "3.11" in resp.text
        assert "3.10" in resp.text

    def test_product_not_found_returns_404(self, eol_client):
        with patch("modules.eol.api_client.get_product_cycles", return_value=[]):
            resp = eol_client.get("/eol/product/doesnotexist")
        assert resp.status_code == 404

    def test_already_tracked_shown(self, eol_client, tmp_path):
        from modules.eol.storage import EolStorage

        fake = FakeGit(tmp_path)
        es = EolStorage(fake)
        es.create_entry("python", "3.11", "Python 3.11")
        with (
            patch("modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES),
            patch("modules.eol.router._get_all_storages", return_value=[es]),
        ):
            resp = eol_client.get("/eol/product/python")
        assert "Tracked" in resp.text


class TestEolTimelineRoute:
    def test_timeline_returns_200(self, eol_client):
        with patch("modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES):
            resp = eol_client.get("/eol/timeline/python")
        assert resp.status_code == 200

    def test_timeline_shows_product_name(self, eol_client):
        with patch("modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES):
            resp = eol_client.get("/eol/timeline/python")
        assert "python" in resp.text

    def test_timeline_shows_today_line(self, eol_client):
        with patch("modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES):
            resp = eol_client.get("/eol/timeline/python")
        assert "eol-today-line" in resp.text

    def test_timeline_shows_legend(self, eol_client):
        with patch("modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES):
            resp = eol_client.get("/eol/timeline/python")
        assert "Active Support" in resp.text

    def test_timeline_not_found_returns_404(self, eol_client):
        with patch("modules.eol.api_client.get_product_cycles", return_value=[]):
            resp = eol_client.get("/eol/timeline/doesnotexist")
        assert resp.status_code == 404


class TestEolAddRoute:
    def test_add_redirects(self, eol_client, tmp_path):
        from modules.eol.storage import EolStorage

        fake = FakeGit(tmp_path)
        es = EolStorage(fake)
        with patch("modules.eol.router._get_storage", return_value=es):
            resp = eol_client.post(
                "/eol/add",
                data={"product": "python", "cycle": "3.11", "label": "Python 3.11", "notes": ""},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/eol"

    def test_add_creates_entry(self, eol_client, tmp_path):
        from modules.eol.storage import EolStorage

        fake = FakeGit(tmp_path)
        es = EolStorage(fake)
        with patch("modules.eol.router._get_storage", return_value=es):
            eol_client.post(
                "/eol/add",
                data={"product": "python", "cycle": "3.11", "label": "", "notes": ""},
                follow_redirects=False,
            )
        entries = es.list_entries()
        assert len(entries) == 1
        assert entries[0]["product"] == "python"

    def test_add_auto_label_when_empty(self, eol_client, tmp_path):
        from modules.eol.storage import EolStorage

        fake = FakeGit(tmp_path)
        es = EolStorage(fake)
        with patch("modules.eol.router._get_storage", return_value=es):
            eol_client.post(
                "/eol/add",
                data={"product": "python", "cycle": "3.11", "label": "", "notes": ""},
                follow_redirects=False,
            )
        assert es.list_entries()[0]["label"] == "python 3.11"

    def test_add_no_storage_returns_503(self, eol_client):
        with patch("modules.eol.router._get_storage", return_value=None):
            resp = eol_client.post(
                "/eol/add",
                data={"product": "python", "cycle": "3.11", "label": "", "notes": ""},
                follow_redirects=False,
            )
        assert resp.status_code == 503


class TestEolDeleteRoute:
    def test_delete_redirects(self, eol_client, tmp_path):
        from modules.eol.storage import EolStorage

        fake = FakeGit(tmp_path)
        es = EolStorage(fake)
        e = es.create_entry("python", "3.11", "Python 3.11")
        with patch("modules.eol.router._find_storage", return_value=es):
            resp = eol_client.post(f"/eol/{e['id']}/delete", follow_redirects=False)
        assert resp.status_code == 303

    def test_delete_removes_entry(self, eol_client, tmp_path):
        from modules.eol.storage import EolStorage

        fake = FakeGit(tmp_path)
        es = EolStorage(fake)
        e = es.create_entry("python", "3.11", "Python 3.11")
        with patch("modules.eol.router._find_storage", return_value=es):
            eol_client.post(f"/eol/{e['id']}/delete", follow_redirects=False)
        assert es.list_entries() == []

    def test_delete_not_found_returns_404(self, eol_client):
        with patch("modules.eol.router._find_storage", return_value=None):
            resp = eol_client.post("/eol/badid/delete", follow_redirects=False)
        assert resp.status_code == 404


class TestEolNotesRoute:
    def test_update_notes_redirects(self, eol_client, tmp_path):
        from modules.eol.storage import EolStorage

        fake = FakeGit(tmp_path)
        es = EolStorage(fake)
        e = es.create_entry("python", "3.11", "Python 3.11")
        with patch("modules.eol.router._find_storage", return_value=es):
            resp = eol_client.post(
                f"/eol/{e['id']}/notes",
                data={"notes": "In prod since 2023"},
                follow_redirects=False,
            )
        assert resp.status_code == 303

    def test_update_notes_saves(self, eol_client, tmp_path):
        from modules.eol.storage import EolStorage

        fake = FakeGit(tmp_path)
        es = EolStorage(fake)
        e = es.create_entry("python", "3.11", "Python 3.11")
        with patch("modules.eol.router._find_storage", return_value=es):
            eol_client.post(
                f"/eol/{e['id']}/notes",
                data={"notes": "In prod since 2023"},
                follow_redirects=False,
            )
        assert es.get_entry(e["id"])["notes"] == "In prod since 2023"

    def test_update_notes_not_found_returns_404(self, eol_client):
        with patch("modules.eol.router._find_storage", return_value=None):
            resp = eol_client.post("/eol/badid/notes", data={"notes": "x"}, follow_redirects=False)
        assert resp.status_code == 404


class TestEolApiClientCaching:
    def test_get_product_cycles_uses_redis_cache(self):
        from modules.eol.api_client import get_product_cycles

        cached = json.dumps(FAKE_CYCLES)
        mock_redis = MagicMock()
        mock_redis.get.return_value = cached
        with patch("modules.eol.api_client._redis", return_value=mock_redis):
            result = get_product_cycles("python")
        assert result == FAKE_CYCLES
        mock_redis.get.assert_called_once_with("eol:product:python")

    def test_get_product_cycles_stores_in_redis(self):
        from modules.eol.api_client import get_product_cycles

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with (
            patch("modules.eol.api_client._redis", return_value=mock_redis),
            patch("httpx.get") as mock_get,
        ):
            mock_resp = MagicMock()
            mock_resp.json.return_value = FAKE_CYCLES
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp
            result = get_product_cycles("python")
        assert result == FAKE_CYCLES
        mock_redis.setex.assert_called_once()

    def test_get_product_cycles_returns_empty_on_404(self):
        import httpx
        from modules.eol.api_client import get_product_cycles

        with patch("modules.eol.api_client._redis", return_value=None):
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            with patch(
                "httpx.get",
                side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=mock_resp),
            ):
                result = get_product_cycles("doesnotexist")
        assert result == []

    def test_get_product_cycles_returns_empty_on_network_error(self):
        import httpx
        from modules.eol.api_client import get_product_cycles

        with patch("modules.eol.api_client._redis", return_value=None):
            with patch("httpx.get", side_effect=httpx.ConnectError("timeout")):
                result = get_product_cycles("python")
        assert result == []

    def test_get_all_products_uses_redis_cache(self):
        from modules.eol.api_client import get_all_products

        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(["python", "nodejs"])
        with patch("modules.eol.api_client._redis", return_value=mock_redis):
            result = get_all_products()
        assert result == ["python", "nodejs"]
        mock_redis.get.assert_called_once_with("eol:all")

    def test_get_all_products_returns_empty_on_error(self):
        import httpx
        from modules.eol.api_client import get_all_products

        with patch("modules.eol.api_client._redis", return_value=None):
            with patch("httpx.get", side_effect=httpx.ConnectError("timeout")):
                result = get_all_products()
        assert result == []


# ---------------------------------------------------------------------------
# GET /eol/add — full search page
# ---------------------------------------------------------------------------


class TestEolAddPage:
    def test_add_page_loads(self, eol_client):
        resp = eol_client.get("/eol/add")
        assert resp.status_code == 200

    def test_add_page_has_search_input(self, eol_client):
        resp = eol_client.get("/eol/add")
        assert "eol-search-input" in resp.text

    def test_add_page_with_query_shows_results(self, eol_client):
        with patch("modules.eol.api_client.search_products", return_value=["python"]):
            resp = eol_client.get("/eol/add?q=python")
        assert "python" in resp.text


# ---------------------------------------------------------------------------
# _enrich_entries — status enrichment
# ---------------------------------------------------------------------------


class TestEnrichEntries:
    def _entry(self, product="python", cycle="3.11"):
        return {
            "id": "abc123",
            "product": product,
            "cycle": cycle,
            "label": f"{product} {cycle}",
            "notes": "",
            "created": "2026-01-01",
        }

    def test_status_attached(self):
        from modules.eol.router import _enrich_entries

        with patch("modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES):
            enriched = _enrich_entries([self._entry("python", "3.11")])
        assert enriched[0]["status"] in ("active", "soon", "eol")

    def test_unknown_when_api_unavailable(self):
        from modules.eol.router import _enrich_entries

        with patch("modules.eol.api_client.get_product_cycles", return_value=[]):
            enriched = _enrich_entries([self._entry("python", "3.11")])
        assert enriched[0]["status"] == "unknown"
        assert enriched[0]["api_available"] is False

    def test_eol_date_attached(self):
        from modules.eol.router import _enrich_entries

        with patch("modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES):
            enriched = _enrich_entries([self._entry("python", "3.11")])
        assert enriched[0]["eol_date"] == "2027-10-31"

    def test_latest_version_attached(self):
        from modules.eol.router import _enrich_entries

        with patch("modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES):
            enriched = _enrich_entries([self._entry("python", "3.11")])
        assert enriched[0]["latest"] == "3.11.9"

    def test_batches_api_calls_per_product(self):
        from modules.eol.router import _enrich_entries

        entries = [self._entry("python", "3.11"), self._entry("python", "3.10")]
        with patch(
            "modules.eol.api_client.get_product_cycles", return_value=FAKE_CYCLES
        ) as mock_api:
            _enrich_entries(entries)
        # Both python entries → only one API call for "python"
        assert mock_api.call_count == 1
