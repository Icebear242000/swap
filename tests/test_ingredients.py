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


# Recorded from Open Beauty Facts: OCR of only the "Drug Facts (continued)" panel, so the
# active ingredient (fluoride) printed on the other panel is missing.
CREST_3D_WHITE = (
    "urpose nticavity othpaste ng is ht away. meals removes %06 01 dn of surface stains 96 "
    "drug facts (continued) supervise children's brushing until good habits are established "
    "children under 2 yrs.: ask a dentist starts whitening after 1 brush inactive ingredients "
    "water, sorbitol, hydrated silica, disodium pyrophosphate, sodium lauryl sulfate, flavor"
)
CREST_OCR_TYPO = (
    "drug facts (cotinued) surface staining cf • adequate toothbrushig may prevent these "
    "stains inactive ingredients głycerin, hydrated silica, sodium hexametaphosphate, water"
)
# Recorded from Open Beauty Facts: a volunteer attached a green tea drink's ingredients to
# "Colgate Maximum Cavity Protection".
GREEN_TEA = "Purified Water, Fresh Brew from Green Tea Leaves, Sugar, Acidity Regulators"


def test_no_fluoride_in_a_partial_label_is_unknown_not_fail():
    for text in (CREST_3D_WHITE, CREST_OCR_TYPO):
        r = check_fights_cavities(analyze(text, []))
        assert r.status == UNKNOWN and "incomplete" in r.summary


def test_claimed_cavity_protection_without_listed_fluoride_is_unknown():
    r = check_fights_cavities(analyze(GREEN_TEA, [], name="Maximum Cavity Protection"))
    assert r.status == UNKNOWN and "claims" in r.summary
    # No claim and a complete-looking list: still a real fail.
    assert check_fights_cavities(analyze(GREEN_TEA, [], name="Herbal Paste")).status == FAIL


def test_partial_label_with_fluoride_still_passes():
    text = (
        "drug facts (continued) active ingredient sodium fluoride 0.24% inactive ingredients water"
    )
    assert check_fights_cavities(analyze(text, [])).status == PASS


def test_restricted_caution_passes_with_note():
    f = analyze("Sodium fluoride, triclosan, water")
    r = check_ingredients(f)
    assert r.status == PASS and "triclosan" in r.summary


def test_quantity_parsing():
    assert parse_ounces("4.8 oz (136 g)") == (4.8, "oz")
    assert parse_ounces("136 g") == (round(136 / 28.349523125, 3), "oz")
    assert parse_ounces("75 ml")[1] == "fl oz"
    assert parse_ounces("big tube") is None
