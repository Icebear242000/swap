"""Settings, read from environment variables so deploys need no code changes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default) == "1"


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.environ.get("SWAP_DB", "data/swap.db")))
    # Open Food Facts projects ask every client to identify itself.
    user_agent: str = field(
        default_factory=lambda: os.environ.get(
            "SWAP_USER_AGENT", "Swap/0.1 (https://github.com/Icebear242000/swap)"
        )
    )
    # Seed fictional sample products into an empty database so a fresh deploy is usable.
    seed_demo_if_empty: bool = field(default_factory=lambda: _env_flag("SWAP_SEED_DEMO"))
    # Allow live calls to Open Beauty Facts / Open Prices / Wikidata on a cache miss.
    live_lookups: bool = field(default_factory=lambda: _env_flag("SWAP_LIVE_LOOKUPS"))
    http_timeout_s: float = 8.0
    price_max_age_days: int = 14

    # Worker checkpoint thresholds. These are judgment calls, so they live in config
    # and every result shows the underlying records, not just the verdict.
    labor_lookback_years: int = 5
    whd_back_wages_fail_usd: float = 10_000.0

    recall_lookback_years: int = 3


def get_settings() -> Settings:
    return Settings()
