from pathlib import Path

from swap import ownership, records
from swap.checkpoints import FAIL, PASS, UNKNOWN, check_workers, recall_warning
from swap.config import Settings

FIX = Path(__file__).parent / "fixtures"
S = Settings(db_path=Path(":memory:"))


def test_workers_unknown_without_datasets(conn):
    own = ownership.chain_for(conn, "colgate")
    assert check_workers(conn, own, S).status == UNKNOWN


def test_whd_load_matches_and_fails_on_back_wages(conn):
    n = records.load_whd(conn, FIX / "whd.csv")
    assert n == 2  # both Colgate-Palmolive rows; Joe's Diner is not tracked
    own = ownership.chain_for(conn, "toms maine")  # sibling brand, same parent
    r = check_workers(conn, own, S)
    assert r.status == FAIL and "25,000" in r.summary
    assert len(r.evidence) == 1  # the 2012 case is outside the 5-year window


def test_osha_repeat_violation_fails_and_deleted_rows_ignored(conn):
    n = records.load_osha(conn, FIX / "osha_inspection.csv", FIX / "osha_violation.csv")
    assert n == 1
    case = conn.execute("SELECT * FROM labor_cases").fetchone()
    assert case["severity"] == "repeat"  # the willful row is flagged deleted
    assert case["violations"] == 2 and case["penalty"] == 55625
    r = check_workers(conn, ownership.chain_for(conn, "crest"), S)
    assert r.status == FAIL


def test_loaded_dataset_with_no_records_passes(conn):
    records.load_whd(conn, FIX / "whd.csv")
    r = check_workers(conn, ownership.chain_for(conn, "sensodyne"), S)
    assert r.status == PASS and "No cases" in r.summary


def test_recalls_match_tracked_firms_only(conn, client):
    n = records.load_recalls(conn, client)
    assert conn.execute("SELECT COUNT(*) FROM recalls").fetchone()[0] == 1
    assert n >= 1
    own = ownership.chain_for(conn, "colgate")
    w = recall_warning(conn, own, "Fixture", "Colgate", S)
    assert w and w["level"] == "company"
