"""A small HTTP helper: timeouts, a User-Agent, and a couple of retries.

Outside services have outages and rate limits. Callers get None on failure and
decide what "unknown" means for them, so one flaky API never breaks a scan.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger("swap.http")

RETRY_STATUS = {429, 500, 502, 503, 504}


def get_json(
    client: httpx.Client,
    url: str,
    params: dict[str, Any] | None = None,
    *,
    retries: int = 2,
    backoff_s: float = 0.6,
) -> Any | None:
    for attempt in range(retries + 1):
        try:
            resp = client.get(url, params=params)
        except httpx.HTTPError as exc:
            log.warning("GET %s failed: %s", url, exc)
        else:
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    log.warning("GET %s returned non-JSON", url)
                    return None
            if resp.status_code == 404:
                return None
            if resp.status_code not in RETRY_STATUS:
                log.warning("GET %s -> %s", url, resp.status_code)
                return None
        if attempt < retries:
            time.sleep(backoff_s * (2**attempt))
    return None


def make_client(user_agent: str, timeout_s: float) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        timeout=timeout_s,
        follow_redirects=True,
    )
