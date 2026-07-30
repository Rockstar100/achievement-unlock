"""Trends provider abstraction (Google Trends explore + future official API)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class TrendRecord:
    category: str
    keyword: str
    interest_score: float
    interest_delta: float
    interest_avg_7d: float
    interest_peak_7d: float
    is_rising: bool
    rising_query: str
    rising_score: float
    related_topics_json: str
    raw_json: str


class TrendsProvider(ABC):
    name: str = "base"

    @abstractmethod
    def fetch_all(self) -> List[TrendRecord]:
        ...

    @abstractmethod
    def to_bronze_records(self, records: List[TrendRecord]) -> List[Dict[str, Any]]:
        ...


def get_trends_provider(
    provider: Optional[str] = None,
    geo: str = "IN",
    timeframe: str = "now 7-d",
) -> TrendsProvider:
    import os

    name = (provider or os.getenv("TRENDS_PROVIDER", "explore")).lower()
    if name in ("explore", "google", "gtrends"):
        from scrapers.trends.explore_provider import ExploreTrendsProvider

        return ExploreTrendsProvider(geo=geo, timeframe=timeframe)
    if name in ("official", "alpha"):
        from scrapers.trends.explore_provider import ExploreTrendsProvider

        # Stub: official alpha not yet wired; fall back to explore
        return ExploreTrendsProvider(geo=geo, timeframe=timeframe)
    raise ValueError(f"Unknown trends provider: {name}")
