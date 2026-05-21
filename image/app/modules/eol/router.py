"""EOL Tracker module — router."""

import logging

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.module_guard import require_module
from core.module_repos import get_module_stores, get_primary_store
from core.state import get_storage
from core.templates import templates
from modules.eol import api_client
from modules.eol.storage import EolStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eol", dependencies=[require_module("eol")])


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _get_storage() -> EolStorage | None:
    store = get_primary_store("eol", get_storage())
    return EolStorage(store) if store else None


def _get_all_storages() -> list[EolStorage]:
    return [EolStorage(s) for s in get_module_stores("eol", get_storage())]


def _find_storage(entry_id: str) -> EolStorage | None:
    for es in _get_all_storages():
        if es.get_entry(entry_id):
            return es
    return None


def _list_all_entries() -> list[dict]:
    seen: set[str] = set()
    entries: list[dict] = []
    for es in _get_all_storages():
        for e in es.list_entries():
            if e["id"] not in seen:
                seen.add(e["id"])
                entries.append(e)
    return sorted(entries, key=lambda x: (x.get("product", ""), x.get("cycle", "")))


# ---------------------------------------------------------------------------
# Status enrichment
# ---------------------------------------------------------------------------


def _enrich_entries(entries: list[dict]) -> list[dict]:
    """Fetch live API data for each entry and attach status info."""
    # Group by product to batch API calls
    products_needed: set[str] = {e["product"] for e in entries}
    cycles_by_product: dict[str, dict] = {}

    for product in products_needed:
        api_cycles = api_client.get_product_cycles(product)
        cycles_by_product[product] = {c.get("cycle"): c for c in api_cycles}

    result = []
    for e in entries:
        product_cycles = cycles_by_product.get(e["product"], {})
        cycle_data = product_cycles.get(e["cycle"])

        if cycle_data:
            eol_val = cycle_data.get("eol")
            status = api_client.get_cycle_status(eol_val)
            eol_date = str(eol_val) if eol_val and eol_val is not False else None
            latest = cycle_data.get("latest")
            ext_val = cycle_data.get("extendedSupport")
            ext_date = str(ext_val) if ext_val and ext_val is not False else None
        else:
            status = "unknown"
            eol_date = None
            latest = None
            ext_date = None

        result.append(
            {
                **e,
                "status": status,
                "eol_date": eol_date,
                "ext_date": ext_date,
                "latest": latest,
                "api_available": cycle_data is not None,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def eol_list(request: Request):
    entries = _enrich_entries(_list_all_entries())

    # Group by product for display
    products: dict[str, list[dict]] = {}
    for e in entries:
        products.setdefault(e["product"], []).append(e)

    return templates.TemplateResponse(
        request,
        "modules/eol/list.html",
        {
            "active_module": "eol",
            "entries": entries,
            "products": products,
        },
    )


@router.get("/add", response_class=HTMLResponse)
async def eol_add_page(request: Request):
    return templates.TemplateResponse(
        request,
        "modules/eol/search.html",
        {"active_module": "eol", "results": [], "q": ""},
    )


@router.get("/search", response_class=HTMLResponse)
async def eol_search(request: Request, q: str = ""):
    results = api_client.search_products(q) if q.strip() else []
    return templates.TemplateResponse(
        request,
        "modules/eol/_search_results.html",
        {"results": results, "q": q},
    )


@router.get("/product/{product}", response_class=HTMLResponse)
async def eol_product_cycles(request: Request, product: str):
    cycles_raw = api_client.get_product_cycles(product)
    if not cycles_raw:
        raise HTTPException(status_code=404, detail=f"Product '{product}' not found")

    # Find already-tracked cycles for this product (across all storages)
    tracked_cycles: set[str] = set()
    for es in _get_all_storages():
        for e in es.list_entries():
            if e.get("product") == product:
                tracked_cycles.add(e.get("cycle", ""))

    # Enrich cycles with status
    today = __import__("datetime").date.today()
    cycles = []
    for c in cycles_raw:
        eol_val = c.get("eol")
        status = api_client.get_cycle_status(eol_val)
        ext_val = c.get("extendedSupport")
        cycles.append(
            {
                **c,
                "status": status,
                "eol_str": str(eol_val) if eol_val and eol_val is not False else "No EOL",
                "ext_str": str(ext_val) if ext_val and ext_val is not False else None,
                "already_tracked": c.get("cycle") in tracked_cycles,
            }
        )

    return templates.TemplateResponse(
        request,
        "modules/eol/cycles.html",
        {
            "active_module": "eol",
            "product": product,
            "cycles": cycles,
        },
    )


@router.get("/timeline/{product}", response_class=HTMLResponse)
async def eol_timeline(request: Request, product: str):
    cycles_raw = api_client.get_product_cycles(product)
    if not cycles_raw:
        raise HTTPException(status_code=404, detail=f"Product '{product}' not found")

    timeline = api_client.compute_timeline(cycles_raw)

    return templates.TemplateResponse(
        request,
        "modules/eol/timeline.html",
        {
            "active_module": "eol",
            "product": product,
            "timeline": timeline,
        },
    )


@router.post("/add", response_class=RedirectResponse)
async def eol_add(
    request: Request,
    product: str = Form(...),
    cycle: str = Form(...),
    label: str = Form(""),
    notes: str = Form(""),
):
    es = _get_storage()
    if not es:
        raise HTTPException(status_code=503, detail="No storage configured")
    if not label.strip():
        label = f"{product} {cycle}"
    es.create_entry(product=product, cycle=cycle, label=label.strip(), notes=notes.strip())
    return RedirectResponse("/eol", status_code=303)


@router.post("/{entry_id}/notes", response_class=RedirectResponse)
async def eol_update_notes(request: Request, entry_id: str, notes: str = Form("")):
    es = _find_storage(entry_id)
    if not es:
        raise HTTPException(status_code=404)
    es.update_notes(entry_id, notes)
    return RedirectResponse("/eol", status_code=303)


@router.post("/{entry_id}/delete", response_class=RedirectResponse)
async def eol_delete(request: Request, entry_id: str):
    es = _find_storage(entry_id)
    if not es:
        raise HTTPException(status_code=404)
    es.delete_entry(entry_id)
    return RedirectResponse("/eol", status_code=303)
