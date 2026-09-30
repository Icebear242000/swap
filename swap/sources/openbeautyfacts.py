"""Open Beauty Facts: a free, volunteer-built product database queried by barcode.

API docs: https://openfoodfacts.github.io/openfoodfacts-server/api/
"""

from __future__ import annotations

from typing import Any

import httpx

from swap.quantity import parse_ounces
from swap.sources.http import get_json

BASE = "https://world.openbeautyfacts.org"
FIELDS = ",".join(
    [
        "code",
        "product_name",
        "product_name_en",
        "brands",
        "categories_tags",
        "ingredients_text",
        "ingredients_text_en",
        "quantity",
        "image_front_url",
        "image_url",
    ]
)

# Open Beauty Facts category tag -> our category. Extend this to support more.
CATEGORY_TAGS = {
    "en:toothpastes": "toothpaste",
    "en:toothpaste": "toothpaste",
}


def product_url(barcode: str) -> str:
    return f"{BASE}/product/{barcode}"


def to_category(tags: list[str] | None) -> str | None:
    for tag in tags or []:
        if tag in CATEGORY_TAGS:
            return CATEGORY_TAGS[tag]
    return None


def first_brand(brands: str | None) -> str | None:
    if not brands:
        return None
    first = brands.split(",")[0].strip()
    return first or None


def parse_product(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Turn an Open Beauty Facts product into our row shape, or None if unusable."""
    code = str(raw.get("code") or "").strip()
    name = (raw.get("product_name_en") or raw.get("product_name") or "").strip()
    if not code or not name:
        return None
    qty = raw.get("quantity")
    parsed = parse_ounces(qty)
    return {
        "barcode": code,
        "name": name,
        "brand": first_brand(raw.get("brands")),
        "brands_all": [b.strip() for b in (raw.get("brands") or "").split(",") if b.strip()],
        "category": to_category(raw.get("categories_tags")),
        "ingredients_text": (raw.get("ingredients_text_en") or raw.get("ingredients_text") or None),
        "quantity_text": qty,
        "quantity_oz": parsed[0] if parsed else None,
        "quantity_unit": parsed[1] if parsed else None,
        "image_url": raw.get("image_front_url") or raw.get("image_url"),
        "source": "openbeautyfacts",
        "source_url": product_url(code),
    }


def fetch_product(client: httpx.Client, barcode: str) -> dict[str, Any] | None:
    data = get_json(client, f"{BASE}/api/v2/product/{barcode}.json", {"fields": FIELDS})
    if not data or data.get("status") != 1 or not data.get("product"):
        return None
    return parse_product(data["product"])


def search_category(
    client: httpx.Client, tag: str = "en:toothpastes", page: int = 1, page_size: int = 100
) -> list[dict[str, Any]]:
    data = get_json(
        client,
        f"{BASE}/api/v2/search",
        {"categories_tags": tag, "fields": FIELDS, "page": page, "page_size": page_size},
    )
    if not data:
        return []
    return [p for p in (parse_product(r) for r in data.get("products", [])) if p]
