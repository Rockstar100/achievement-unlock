"""Google Trends explore API provider (wraps GTrendsClient)."""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Dict, List

from scrapers.gtrends.client import GTrendsClient
from scrapers.trends.base import TrendRecord, TrendsProvider


class ExploreTrendsProvider(TrendsProvider):
    name = "explore"

    def __init__(self, geo: str = "IN", timeframe: str = "now 7-d"):
        self.geo = geo
        self.timeframe = timeframe
        self._client = GTrendsClient(geo=geo, timeframe=timeframe)

    def fetch_all(self) -> List[TrendRecord]:
        raw = self._client.fetch_all()
        out: List[TrendRecord] = []
        for r in raw:
            out.append(
                TrendRecord(
                    category=r.category,
                    keyword=r.keyword,
                    interest_score=float(r.interest_score or 0),
                    interest_delta=float(r.interest_delta or 0),
                    interest_avg_7d=float(r.interest_avg_7d or 0),
                    interest_peak_7d=float(r.interest_peak_7d or 0),
                    is_rising=bool(r.is_rising),
                    rising_query=str(r.rising_query or ""),
                    rising_score=float(r.rising_score or 0),
                    related_topics_json=str(r.related_topics_json or "{}"),
                    raw_json=json.dumps(r._raw, default=str) if r._raw else "{}",
                )
            )
        return out

    def to_bronze_records(self, records: List[TrendRecord]) -> List[Dict[str, Any]]:
        now = datetime.now()
        bronze: List[Dict[str, Any]] = []
        for r in records:
            bronze.append(
                {
                    "ingest_date": now.date(),
                    "ingest_ts": now,
                    "category": r.category,
                    "keyword": r.keyword,
                    "interest_score": r.interest_score,
                    "interest_score_prev_day": max(0, r.interest_score - r.interest_delta),
                    "interest_delta": r.interest_delta,
                    "interest_avg_7d": r.interest_avg_7d,
                    "interest_peak_7d": r.interest_peak_7d,
                    "is_rising": int(r.is_rising),
                    "rising_query": r.rising_query,
                    "rising_score": r.rising_score,
                    "related_topics_json": r.related_topics_json,
                    "_raw_json": r.raw_json,
                    "source_connector": self.name,
                }
            )
        return bronze
