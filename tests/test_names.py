from swap.names import best_match, normalize


def test_normalize_strips_legal_forms_and_punctuation():
    assert normalize("Tom's of Maine, Inc.") == "toms maine"
    assert normalize("COLGATE-PALMOLIVE COMPANY INC") == "colgate palmolive"
    assert normalize("Colgate-Palmolive Co.") == "colgate palmolive"
    assert normalize("Procter & Gamble") == "procter gamble"
    assert normalize("Acme L.L.C.") == "acme"
    assert normalize(None) == ""


def test_exact_match_after_normalization():
    m = best_match("COLGATE PALMOLIVE COMPANY INC", ["colgate palmolive", "colgate"])
    assert m and m.org_key == "colgate palmolive" and m.method == "exact"


def test_token_match_requires_same_first_token():
    keys = ["procter gamble"]
    assert best_match("Gamble Procter Holdings", keys) is None


def test_token_match_accepts_close_variant():
    m = best_match("Consolidated Home Brands Group", ["consolidated home brands"])
    assert m and m.org_key == "consolidated home brands" and m.method == "token"


def test_ambiguous_match_is_rejected():
    keys = ["acme home care", "acme home goods"]
    assert best_match("Acme Home", keys) is None


def test_unrelated_names_do_not_match():
    assert best_match("Joe's Diner LLC", ["colgate palmolive", "procter gamble"]) is None
