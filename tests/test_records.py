from pathlib import Path

from swap import ownership, records
from swap.checkpoints import FAIL, PASS, UNKNOWN, check_workers, recall_warning
from swap.cli import check_columns
from swap.config import Settings

FIX = Path(__file__).parent / "fixtures"
S = Settings(db_path=Path(":memory:"))


def test_workers_unknown_without_datasets(conn):
    own = ownership.chain_for(conn, "colgate")
    assert check_workers(conn, own, S).status == UNKNOWN


def test_whd_load_matches_and_fails_on_back_wages(conn):
    n = records.load_whd(conn, [FIX / "whd.csv"])
    assert n == 2  # both Colgate-Palmolive rows; Joe's Diner is not tracked
    own = ownership.chain_for(conn, "toms maine")  # sibling brand, same parent
    r = check_workers(conn, own, S)
    assert r.status == FAIL and "25,000" in r.summary
    assert len(r.evidence) == 1  # the 2012 case is outside the 5-year window


def test_whd_real_download_chunks(conn):
    # Recorded from the real DOL download: uppercase headers, timestamp dates, and the
    # data split across several chunk files that together make one dataset.
    paths = [FIX / "whd_real_1.csv", FIX / "whd_real_2.csv"]
    assert all(check_columns("whd", p) == 0 for p in paths)
    assert records.load_whd(conn, paths) == 2  # P&G and Church & Dwight
    ids = {r["id"]: r for r in conn.execute("SELECT * FROM labor_cases")}
    # Not "Colgate 2 STLC AFC Home", and not "C.R.E.S.T., Inc" (a care provider): records
    # name employers, so they're matched to companies, never to a brand like Crest.
    assert set(ids) == {"WHD:1940837", "WHD:1797996"}
    assert ids["WHD:1940837"]["date"] == "2021-08-23"
    loaded = conn.execute("SELECT rows FROM datasets WHERE name='whd'").fetchone()
    assert loaded["rows"] == 2  # marked once, for all chunks


def test_osha_repeat_violation_fails_and_deleted_rows_ignored(conn):
    n = records.load_osha(conn, FIX / "osha_inspection.csv", FIX / "osha_violation.csv")
    assert n == 1
    case = conn.execute("SELECT * FROM labor_cases").fetchone()
    assert case["severity"] == "repeat"  # the willful row is flagged deleted
    assert case["violations"] == 2 and case["penalty"] == 55625
    r = check_workers(conn, ownership.chain_for(conn, "crest"), S)
    assert r.status == FAIL


def test_loaded_dataset_with_no_records_passes(conn):
    records.load_whd(conn, [FIX / "whd.csv"])
    r = check_workers(conn, ownership.chain_for(conn, "sensodyne"), S)
    assert r.status == PASS and "No cases" in r.summary


def test_recalls_match_tracked_firms_only(conn, client):
    n = records.load_recalls(conn, client)
    assert conn.execute("SELECT COUNT(*) FROM recalls").fetchone()[0] == 1
    assert n >= 1
    own = ownership.chain_for(conn, "colgate")
    w = recall_warning(conn, own, "Fixture", "Colgate", S)
    assert w and w["level"] == "company"
