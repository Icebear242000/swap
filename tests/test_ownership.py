from swap import ownership
from swap.checkpoints import FAIL, PASS, UNKNOWN, check_independent


def test_override_chain(conn):
    own = ownership.chain_for(conn, ownership.resolve_brand_key(conn, ["Tom's of Maine"]))
    assert [link.name for link in own.chain] == ["Tom's of Maine", "Colgate-Palmolive"]
    assert check_independent(own).status == FAIL


def test_siblings(conn):
    names = {d["name"] for d in ownership.descendants(conn, "colgate palmolive")}
    assert {"Colgate", "Tom's of Maine", "hello"} <= names


def test_unknown_brand(conn):
    own = ownership.chain_for(conn, ownership.resolve_brand_key(conn, ["Nobody Brand"]))
    assert not own.known and check_independent(own).status == UNKNOWN


def test_no_parent_is_independent(conn):
    ownership.upsert_org(conn, "Tiny Paste", "brand", "wikidata", "Q1")
    own = ownership.chain_for(conn, "tiny paste")
    assert check_independent(own).status == PASS


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
