"""openFDA drug enforcement reports. Fluoride toothpaste is an OTC drug in the US,
so toothpaste recalls are published here.

API docs: https://open.fda.gov/apis/drug/enforcement/
"""

from __future__ import annotations

import unicodedata
from typing import Any

import httpx

from swap.sources.http import get_json

ENDPOINT = "https://api.fda.gov/drug/enforcement.json"


def parse_result(r: dict[str, Any]) -> dict[str, Any] | None:
    number = r.get("recall_number")
    firm = r.get("recalling_firm")
    if not number or not firm:
        return None
    return {
        "recall_number": number,
        "firm": firm,
        "product": r.get("product_description"),
        "reason": r.get("reason_for_recall"),
        "classification": r.get("classification"),
        "date": r.get("recall_initiation_date"),
        "status": r.get("status"),
        "source": "openfda",
        "url": f"{ENDPOINT}?search=recall_number:%22{number}%22",
    }


def fetch_firm_recalls(client: httpx.Client, firm: str, limit: int = 100) -> list[dict[str, Any]]:
    # openFDA answers 404 when nothing matches; get_json turns that into None.
    # It rejects non-ASCII searches with a 400, and its firm names are ASCII anyway.
    term = unicodedata.normalize("NFKD", firm).encode("ascii", "ignore").decode()
    term = term.replace('"', "")
    data = get_json(client, ENDPOINT, {"search": f'recalling_firm:"{term}"', "limit": limit})
    if not data:
        return []
    return [p for p in (parse_result(r) for r in data.get("results", [])) if p]
