"""endoflife.date API v1 client with Redis caching (24 h TTL)."""

import json
import logging
from datetime import date

import httpx

from core import cache

logger = logging.getLogger(__name__)

_BASE = "https://endoflife.date/api"
_TTL = 86400  # 24 hours


def _redis():
    return cache.get_client()


def get_all_products() -> list[str]:
    r = _redis()
    if r:
        cached = r.get("eol:all")
        if cached:
            return json.loads(cached)
    try:
        resp = httpx.get(f"{_BASE}/all.json", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if r:
            r.setex("eol:all", _TTL, json.dumps(data))
        return data
    except Exception as e:
        logger.warning("EOL API error (all): %s", e)
        return []


def get_product_cycles(product: str) -> list[dict]:
    r = _redis()
    key = f"eol:product:{product}"
    if r:
        cached = r.get(key)
        if cached:
            return json.loads(cached)
    try:
        resp = httpx.get(f"{_BASE}/{product}.json", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if r:
            r.setex(key, _TTL, json.dumps(data))
        return data
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return []
        logger.warning("EOL API error (product %s): %s", product, e)
        return []
    except Exception as e:
        logger.warning("EOL API error (product %s): %s", product, e)
        return []


def search_products(q: str) -> list[str]:
    q = q.lower().strip()
    if not q:
        return []
    products = get_all_products()
    return [p for p in products if q in p.lower()][:20]


def _parse_date(val) -> date | None:
    if not val or val is False:
        return None
    try:
        return date.fromisoformat(str(val))
    except Exception:
        return None


def get_cycle_status(eol_value, today: date | None = None) -> str:
    """Return 'active', 'soon', 'eol', or 'unknown'."""
    if today is None:
        today = date.today()
    if eol_value is False or eol_value is None:
        return "active"
    eol_date = _parse_date(eol_value)
    if eol_date is None:
        return "unknown"
    days_left = (eol_date - today).days
    if days_left < 0:
        return "eol"
    if days_left <= 90:
        return "soon"
    return "active"


def compute_timeline(cycles: list[dict]) -> dict:
    """Compute percentage-based bar positions for the timeline chart."""
    today = date.today()
    all_dates: list[date] = []
    parsed = []

    for c in cycles:
        rd = _parse_date(c.get("releaseDate"))
        sup = _parse_date(c.get("support"))
        eol = _parse_date(c.get("eol"))
        ext = _parse_date(c.get("extendedSupport"))

        for d in [rd, sup, eol, ext]:
            if d:
                all_dates.append(d)
        parsed.append(
            {
                "cycle": c.get("cycle", ""),
                "lts": c.get("lts", False),
                "latest": c.get("latest", ""),
                "latestReleaseDate": c.get("latestReleaseDate"),
                "releaseDate": rd,
                "support": sup,
                "eol": eol,
                "extendedSupport": ext,
                "eol_raw": c.get("eol"),
            }
        )

    if not all_dates:
        return {"cycles": [], "year_marks": [], "today_pct": 50}

    min_date = min(all_dates)
    max_date = max(all_dates)
    total_days = max((max_date - min_date).days, 1)

    today_pct = max(0.0, min(100.0, (today - min_date).days / total_days * 100))

    # Year marks on x-axis
    year_marks = []
    for year in range(min_date.year, max_date.year + 2):
        d = date(year, 1, 1)
        if min_date <= d <= max_date:
            pct = (d - min_date).days / total_days * 100
            year_marks.append({"year": year, "pct": round(pct, 2)})

    def _pct(d: date) -> float:
        return round((d - min_date).days / total_days * 100, 2)

    result_cycles = []
    for p in parsed:
        rd = p["releaseDate"]
        if not rd:
            continue

        bars = []
        eol = p["eol"]
        sup = p["support"]
        ext = p["extendedSupport"]

        if sup and eol and sup < eol:
            # 3-phase: active → security → (optional extended)
            bars.append({"left": _pct(rd), "width": _pct(sup) - _pct(rd), "phase": "active"})
            bars.append({"left": _pct(sup), "width": _pct(eol) - _pct(sup), "phase": "security"})
            if ext and ext > eol:
                bars.append({"left": _pct(eol), "width": _pct(ext) - _pct(eol), "phase": "extended"})
        elif eol:
            # 1 or 2-phase: active → eol
            bars.append({"left": _pct(rd), "width": _pct(eol) - _pct(rd), "phase": "active"})
            if ext and ext > eol:
                bars.append({"left": _pct(eol), "width": _pct(ext) - _pct(eol), "phase": "extended"})
        else:
            # No EOL defined — bar to right edge
            bars.append({"left": _pct(rd), "width": 100.0 - _pct(rd), "phase": "unknown"})

        eol_date_str = eol.isoformat() if eol else (ext.isoformat() if ext else None)
        status = get_cycle_status(p["eol_raw"])

        result_cycles.append(
            {
                "cycle": p["cycle"],
                "lts": p["lts"],
                "latest": p["latest"],
                "latestReleaseDate": p["latestReleaseDate"],
                "bars": bars,
                "status": status,
                "eol_date": eol_date_str,
                "release_date": rd.isoformat() if rd else None,
            }
        )

    return {
        "cycles": result_cycles,
        "year_marks": year_marks,
        "today_pct": round(today_pct, 2),
    }
