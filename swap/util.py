from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def parse_date(value: str | None) -> date | None:
    """Accepts '2024-03-01', '20240301', '03/01/2024' and ISO datetimes."""
    if not value:
        return None
    v = value.strip()
    attempts = ((v[:10], "%Y-%m-%d"), (v, "%Y%m%d"), (v, "%m/%d/%Y"))
    for text, fmt in attempts:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def years_ago(years: int, today: date | None = None) -> date:
    t = today or date.today()
    return t - timedelta(days=int(365.25 * years))


def is_older_than(iso: str | None, days: int) -> bool:
    if not iso:
        return True
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return True
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return datetime.now(UTC) - then > timedelta(days=days)
