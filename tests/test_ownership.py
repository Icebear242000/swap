import httpx
from conftest import fixture_json

from swap import ownership


def test_override_chain(conn):
    own = ownership.chain_for(conn, ownership.resolve_brand_key(conn, ["Tom's of Maine"]))
    assert [link.name for link in own.chain] == ["Tom's of Maine", "Colgate-Palmolive"]


def test_siblings(conn):
    names = {d["name"] for d in ownership.descendants(conn, "colgate palmolive")}
    assert {"Colgate", "Tom's of Maine", "hello"} <= names


def test_unknown_brand(conn):
    own = ownership.chain_for(conn, ownership.resolve_brand_key(conn, ["Nobody Brand"]))
    assert not own.known


def test_ambiguous_wikidata_label_is_skipped(conn):
    # Recorded from the live API: "Signal" matches a record label, the toothpaste brand
    # and a third item. Picking one would be a guess (and would attach the wrong company's
    # records), so the brand stays unknown.
    real = fixture_json("wikidata_labels_real.json")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=real))
    with httpx.Client(transport=transport) as client:
        ownership.load_from_wikidata(conn, client, ["Signal"])
    assert ownership.resolve_brand_key(conn, ["Signal"]) is None
    assert ownership.was_looked_up(conn, "signal")


def test_cycle_is_cut(conn):
    a = ownership.upsert_org(conn, "Alpha", "company", "wikidata")
    b = ownership.upsert_org(conn, "Beta", "company", "wikidata")
    ownership.add_parent(conn, a, b, "wikidata", None)
    ownership.add_parent(conn, b, a, "wikidata", None)
    own = ownership.chain_for(conn, a)
    assert [link.key for link in own.chain] == ["alpha", "beta"]
    assert "loop" in (own.note or "")


def test_wikidata_multilevel_load(conn, client):
    ownership.load_from_wikidata(conn, client, ["Glimmer"])
    own = ownership.chain_for(conn, "glimmer")
    assert [link.name for link in own.chain] == ["Glimmer", "Mid Holdings", "Top Group"]
    assert ownership.was_looked_up(conn, "glimmer")
