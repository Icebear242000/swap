from swap.checkpoints import FAIL, PASS, UNKNOWN, check_fights_cavities, check_ingredients
from swap.ingredients import analyze, split_ingredients
from swap.quantity import parse_ounces


def test_split_handles_active_inactive_labels():
    items = split_ingredients(
        "Active ingredient: Sodium fluoride 0.24%. Inactive ingredients: "
        "water, sorbitol (humectant)"
    )
    assert "sodium fluoride 0.24%" in items
    assert "water" in items and "humectant" in items


def test_fluoride_is_not_pfas():
    f = analyze("Sodium fluoride, stannous fluoride, sodium monofluorophosphate", [])
    assert f.fluoride and not f.pfas
    assert check_ingredients(f).status == PASS


def test_ptfe_fails_ingredients():
    f = analyze("Sodium fluoride, PTFE, water", [])
    r = check_ingredients(f)
    assert r.status == FAIL and "ptfe" in r.summary.lower()


def test_cavities_rules():
    assert check_fights_cavities(analyze("stannous fluoride, water", [])).status == PASS
    assert check_fights_cavities(analyze("hydroxyapatite, water", [])).status == UNKNOWN
    assert check_fights_cavities(analyze("baking soda, water", [])).status == FAIL
    assert check_fights_cavities(analyze(None, [])).status == UNKNOWN


def test_restricted_caution_passes_with_note():
    f = analyze("Sodium fluoride, triclosan, water")
    r = check_ingredients(f)
    assert r.status == PASS and "triclosan" in r.summary


def test_quantity_parsing():
    assert parse_ounces("4.8 oz (136 g)") == (4.8, "oz")
    assert parse_ounces("136 g") == (round(136 / 28.349523125, 3), "oz")
    assert parse_ounces("75 ml")[1] == "fl oz"
    assert parse_ounces("big tube") is None
