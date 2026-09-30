"""Open Prices: crowd-sourced shelf prices keyed by barcode (Open Food Facts project).

API docs: https://prices.openfoodfacts.org/api/docs
"""

from __future__ import annotations

from typing import Any

import httpx

from swap.sources.http import get_json

BASE = "https://prices.openfoodfacts.org/api/v1"


def fetch_prices(client: httpx.Client, barcode: str, size: int = 10) -> list[dict[str, Any]]:
    data = get_json(
        client, f"{BASE}/prices", {"product_code": barcode, "order_by": "-date", "size": size}
    )
    if not data:
        return []
    out = []
    for item in data.get("items", []):
        price, currency = item.get("price"), item.get("currency")
        if price is None or not currency:
            continue
        loc = item.get("location") or {}
        out.append(
            {
                "barcode": barcode,
                "price": float(price),
                "currency": currency,
                "date": item.get("date"),
                "location": loc.get("osm_name") or loc.get("osm_address_city"),
                "source": "openprices",
            }
        )
    return out
