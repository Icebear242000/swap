from pathlib import Path

from swap import ownership, records
from swap.checkpoints import FAIL, PASS, UNKNOWN, check_environment
from swap.cli import check_columns
from swap.config import Settings
from swap.sources import epa

# Real rows from EPA's ICIS FE&C download (case_downloads.zip), values left as published,
# trailing spaces included.
EPA = Path(__file__).parent / "fixtures" / "epa_real"
# A 10-year window keeps these 2022-2026 cases inside it as the calendar moves on.
S = Settings(db_path=Path(":memory:"), env_lookback_years=10)


def test_epa_columns_match_the_real_files():
    for kind, filename in epa.FILES.items():
        assert check_columns(f"epa-{kind}", EPA / filename) == 0


def test_load_keeps_concluded_cases_of_tracked_companies_except_superfund(conn):
    assert records.load_epa(conn, EPA) == 3
    rows = {r["id"]: r for r in conn.execute("SELECT * FROM env_cases")}
    # Not the Superfund case (155 defendants), not the case with no conclusion yet,
    # and not the untracked company.
    assert set(rows) == {"EPA:02-2026-9242", "EPA:02-2022-5093", "EPA:05-2023-0072"}
    big = rows["EPA:02-2026-9242"]
    # The case file's own penalty column is blank; the amount is in CASE_PENALTIES.
    assert big["penalty"] == 930000 and big["law"] == "TSCA" and big["date"] == "2026-08-31"
    assert big["raw_name"] == "Colgate-Palmolive Company"  # padding stripped
    loaded = conn.execute("SELECT rows FROM datasets WHERE name='epa'").fetchone()
    assert loaded["rows"] == 3


def test_environment_unknown_until_epa_data_is_loaded(conn):
    r = check_environment(conn, ownership.chain_for(conn, "crest"), S)
    assert r.status == UNKNOWN


def test_large_penalty_fails_through_the_parent_company(conn):
    records.load_epa(conn, EPA)
    r = check_environment(conn, ownership.chain_for(conn, "toms maine"), S)
    assert r.status == FAIL and "$930,000" in r.summary and "Colgate-Palmolive" in r.summary
    assert any("47 chemical substances" in e.text for e in r.evidence)


def test_cases_below_the_line_pass_with_a_note(conn):
    records.load_epa(conn, EPA)
    r = check_environment(conn, ownership.chain_for(conn, "burts bees"), S)  # Clorox
    assert r.status == PASS and "below our limit" in r.summary and r.evidence


def test_no_cases_passes(conn):
    records.load_epa(conn, EPA)
    r = check_environment(conn, ownership.chain_for(conn, "crest"), S)  # Procter & Gamble
    assert r.status == PASS and "No federal" in r.summary


def test_brand_with_no_known_company_is_unknown(conn):
    records.load_epa(conn, EPA)
    ownership.upsert_org(conn, "Tiny Paste", "brand", "wikidata", "Q1")
    r = check_environment(conn, ownership.chain_for(conn, "tiny paste"), S)
    assert r.status == UNKNOWN
