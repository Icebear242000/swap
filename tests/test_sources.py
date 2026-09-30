from conftest import fixture_json

from swap.sources.openbeautyfacts import parse_product


def test_parse_real_obf_product_decodes_html_entities():
    # Recorded from the live API: Open Beauty Facts returns some text HTML-escaped.
    p = parse_product(fixture_json("obf_product_real.json")["product"])
    assert p["barcode"] == "0035000971593" and p["brand"] == "Colgate"
    assert p["category"] == "toothpaste" and p["quantity_oz"] == 3.2
    assert "&gt;" not in p["ingredients_text"]
    assert ">> If more than used for brushing" in p["ingredients_text"]
