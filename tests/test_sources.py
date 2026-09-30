import httpx
from conftest import fixture_json

from swap.sources.openbeautyfacts import parse_product
from swap.sources.openfda import fetch_firm_recalls


def test_openfda_search_term_is_ascii():
    # Recorded from the live API: openFDA answers 400 "Search not supported" to any
    # non-ASCII search, and firm names there are ASCII ("Nestle"), so we fold accents.
    def fda(request: httpx.Request) -> httpx.Response:
        search = request.url.params["search"]
        if not search.isascii():
            return httpx.Response(400, json=fixture_json("openfda_bad_request.json"))
        assert search == 'recalling_firm:"Colgate-Palmolive"'
        return httpx.Response(200, json=fixture_json("openfda_real.json"))

    with httpx.Client(transport=httpx.MockTransport(fda)) as client:
        recalls = fetch_firm_recalls(client, "Colgäte-Palmolive")
    assert [r["recall_number"] for r in recalls] == ["D-0521-2017", "D-1084-2023"]
    assert recalls[0]["firm"] == "Colgate Palmolive Co" and recalls[0]["date"] == "20170213"


def test_parse_real_obf_product_decodes_html_entities():
    # Recorded from the live API: Open Beauty Facts returns some text HTML-escaped.
    p = parse_product(fixture_json("obf_product_real.json")["product"])
    assert p["barcode"] == "0035000971593" and p["brand"] == "Colgate"
    assert p["category"] == "toothpaste" and p["quantity_oz"] == 3.2
    assert "&gt;" not in p["ingredients_text"]
    assert ">> If more than used for brushing" in p["ingredients_text"]
