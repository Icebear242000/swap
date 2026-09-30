from fastapi.testclient import TestClient

from swap.api import create_app


def make(settings, client):
    return TestClient(create_app(settings, client))


def test_health_and_demo_seed(settings, client):
    with make(settings, client) as t:
        body = t.get("/api/health").json()
        assert body["ok"] and body["products"] == 8
        assert "demo_labor" in body["datasets"]
        assert t.get("/").status_code == 200
        assert t.get("/static/app.js").status_code == 200


def test_demo_product_report(settings, client):
    with make(settings, client) as t:
        r = t.get("/api/products/2000000000060").json()  # Brightmore
        status = {c["id"]: c["status"] for c in r["checkpoints"]}
        assert status == {"fights_cavities": "pass", "ingredients": "pass", "workers": "fail"}
        # Ownership is still shown, as information rather than a checkpoint.
        assert r["ownership"]["siblings"] == ["Lumen"]
        assert r["price"]["per_oz"] == round(2.99 / 6.0, 2)


def test_checkpoints_judge_conduct_not_ownership(settings, client):
    with make(settings, client) as t:
        ids = [c["id"] for c in t.get("/api/checkpoints").json()["checkpoints"]]
        assert ids == ["fights_cavities", "ingredients", "workers"]


def test_recall_banner(settings, client):
    with make(settings, client) as t:
        r = t.get("/api/products/2000000000039").json()  # Kindred
        assert r["recall"]["level"] == "product"


def test_live_lookup_saves_product(settings, client):
    with make(settings, client) as t:
        r = t.get("/api/products/0123456789012").json()
        assert r["product"]["source"] == "openbeautyfacts"
        assert [c["name"] for c in r["ownership"]["chain"]] == ["Colgate", "Colgate-Palmolive"]
        assert r["price"]["price"] == 3.9 and r["price"]["per_oz"] == 0.65  # median of USD only
        # Second request is served from the database.
        assert t.get("/api/search?q=Fixture").json()["results"][0]["barcode"] == "0123456789012"


def test_not_found_and_bad_barcode(settings, client):
    with make(settings, client) as t:
        assert t.get("/api/products/9999999999999").status_code == 404
        assert t.get("/api/products/abc").status_code == 400


def test_alternatives_gate_and_rank(settings, client):
    with make(settings, client) as t:
        r = t.get("/api/products/2000000000060/alternatives").json()  # from Brightmore
        shown = [a["product"]["name"] for a in r["shown"]]
        hidden = {h["product"]["name"]: h["reasons"] for h in r["hidden"]}
        assert "Plainfield Baking Soda Paste" in hidden  # no fluoride, required
        assert "Lumen Glide Whitening" in hidden  # PTFE
        # Same owner isn't a reason to hide by default; that's an opt-in filter.
        assert not any("same company" in x for x in hidden["Lumen Glide Whitening"])
        # Three score equally; the recalled one drops, then cheaper per ounce wins.
        assert shown[:3] == [
            "Tidewell Fresh Mint Toothpaste",
            "Harbor & Pine Stannous Care",
            "Kindred Everyday Clean",
        ]
        assert "Fernleaf Mineral Paste" in shown  # unknown is not hidden
        fern = next(a for a in r["shown"] if a["product"]["name"] == "Fernleaf Mineral Paste")
        assert fern["unverified"] == ["Fights cavities"]


def test_preferences_change_results(settings, client):
    with make(settings, client) as t:
        r = t.get(
            "/api/products/2000000000060/alternatives",
            params={"required": "fights_cavities,ingredients,workers"},
        ).json()
        names = [a["product"]["name"] for a in r["shown"]]
        assert "Sprigg Kids Berry" in names  # unknown worker records aren't a failure
        r2 = t.get("/api/products/2000000000060/alternatives", params={"required": ""}).json()
        assert "Lumen Glide Whitening" in [a["product"]["name"] for a in r2["shown"]]
        r3 = t.get(
            "/api/products/2000000000060/alternatives",
            params={"required": "", "hide_same_owner": "true"},
        ).json()
        hidden = {h["product"]["name"]: h["reasons"] for h in r3["hidden"]}
        assert any("same company" in x for x in hidden["Lumen Glide Whitening"])
