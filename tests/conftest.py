import json
from pathlib import Path

import httpx
import pytest

from swap.config import Settings
from swap.db import connect, init_schema
from swap.ownership import load_overrides

FIX = Path(__file__).parent / "fixtures"


def fixture_json(name: str):
    return json.loads((FIX / name).read_text())


def router(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    if host == "world.openbeautyfacts.org" and path.startswith("/api/v2/product/"):
        if "0123456789012" in path:
            return httpx.Response(200, json=fixture_json("obf_product.json"))
        return httpx.Response(200, json=fixture_json("obf_notfound.json"))
    if host == "prices.openfoodfacts.org":
        return httpx.Response(200, json=fixture_json("openprices.json"))
    if host == "query.wikidata.org":
        q = request.url.params.get("query", "")
        name = "wikidata_labels.json" if "rdfs:label" in q else "wikidata_ids.json"
        return httpx.Response(200, json=fixture_json(name))
    if host == "api.fda.gov":
        return httpx.Response(200, json=fixture_json("openfda.json"))
    return httpx.Response(404)


@pytest.fixture
def client():
    with httpx.Client(transport=httpx.MockTransport(router)) as c:
        yield c


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=tmp_path / "t.db", seed_demo_if_empty=True, live_lookups=True)


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_schema(c)
    load_overrides(c)
    yield c
    c.close()
