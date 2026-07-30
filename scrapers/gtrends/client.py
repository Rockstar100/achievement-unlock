"""
Google Trends ingestion for India dog/cat keywords.

Uses the public Trends explore API directly (pytrends breaks on urllib3 v2).
Fetches one keyword at a time so scores are absolute (0-100), not relative.
Bronze: one summary row per keyword (+ optional rising-query rows).
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from scrapers.config_loader import load_gtrends_keywords
from scrapers.filters.pet_filter import is_pet_product

logger = logging.getLogger(__name__)

EXPLORE_URL = "https://trends.google.com/trends/api/explore"
MULTILINE_URL = "https://trends.google.com/trends/api/widgetdata/multiline"
RELATED_QUERIES_URL = "https://trends.google.com/trends/api/widgetdata/relatedsearches"


@dataclass
class GTrendsRecord:
    category: str
    keyword: str
    interest_score: int = 0
    interest_score_prev_day: int = 0
    interest_delta: int = 0
    interest_avg_7d: int = 0
    interest_peak_7d: int = 0
    is_rising: int = 0
    rising_query: str = ""
    rising_score: int = 0
    related_topics_json: str = "{}"
    _raw: Dict[str, Any] = field(default_factory=dict)


class GTrendsClient:
    """Fetch Google Trends interest and rising queries for dog/cat categories."""

    def __init__(
        self,
        geo: str = "IN",
        timeframe: str = "now 7-d",
        hl: str = "en-IN",
        tz: int = 330,
        request_delay: float = 4.5,
        fetch_related: bool = True,
    ):
        self.geo = geo
        self.timeframe = timeframe
        self.hl = hl
        self.tz = tz
        self.request_delay = request_delay
        self.fetch_related = fetch_related
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-IN,en;q=0.9",
            }
        )
        try:
            self.session.get(
                "https://trends.google.com/trends/explore",
                params={"geo": self.geo},
                timeout=20,
            )
        except requests.RequestException:
            pass

    def fetch_all(self) -> List[GTrendsRecord]:
        config = load_gtrends_keywords()
        self.geo = config.get("geo", self.geo)
        timeframe = config.get("timeframe", {}).get("interest_over_time", self.timeframe)

        jobs: List[tuple[str, str, bool]] = []
        for category, cat_config in config.get("categories", {}).items():
            keywords = list(cat_config.get("keywords", []))
            for i, kw in enumerate(keywords):
                # Rising queries only for the primary keyword per category (rate limits)
                jobs.append((category, kw, self.fetch_related and i == 0))

        for kw in config.get("general_keywords") or []:
            jobs.append(("general", kw, False))

        all_records: List[GTrendsRecord] = []
        failed: List[tuple[str, str, bool]] = []

        for category, keyword, want_related in jobs:
            try:
                batch = self._fetch_keyword(category, keyword, timeframe, want_related)
                if self._is_empty_batch(batch):
                    failed.append((category, keyword, want_related))
                all_records.extend(batch)
            except Exception as exc:
                logger.error("GTrends error for %s/%s: %s", category, keyword, exc)
                failed.append((category, keyword, want_related))
            time.sleep(self.request_delay + random.uniform(0.5, 1.5))

        # One retry pass for rate-limited / empty keywords
        if failed:
            logger.info("Retrying %d GTrends keywords after cooldown", len(failed))
            time.sleep(15)
            for category, keyword, want_related in failed:
                try:
                    batch = self._fetch_keyword(category, keyword, timeframe, want_related)
                    if not self._is_empty_batch(batch):
                        all_records = [
                            r
                            for r in all_records
                            if not (r.category == category and r.keyword == keyword and not r.rising_query)
                        ]
                        all_records.extend(batch)
                except Exception as exc:
                    logger.error("GTrends retry failed for %s/%s: %s", category, keyword, exc)
                time.sleep(self.request_delay + 2 + random.uniform(0.5, 1.5))

        logger.info("GTrends fetched %d records across %d keywords", len(all_records), len(jobs))
        return all_records

    @staticmethod
    def _is_empty_batch(batch: List[GTrendsRecord]) -> bool:
        interest = [r for r in batch if not r.rising_query]
        if not interest:
            return True
        return all(
            r._raw.get("note") in ("no_widgets", "no_interest_data")
            or (r.interest_score == 0 and r.interest_avg_7d == 0 and r.interest_peak_7d == 0)
            for r in interest
        )

    def _fetch_keyword(
        self,
        category: str,
        keyword: str,
        timeframe: str,
        want_related: bool,
    ) -> List[GTrendsRecord]:
        widgets = self._explore([keyword], timeframe)
        if not widgets:
            logger.warning("No widgets for %s", keyword)
            return [
                GTrendsRecord(
                    category=category,
                    keyword=keyword,
                    _raw={"note": "no_widgets"},
                )
            ]

        timeline_widget = next((w for w in widgets if w.get("id") == "TIMESERIES"), None)
        points = (
            self._interest_series(timeline_widget, [keyword]).get(keyword, [])
            if timeline_widget
            else []
        )

        records: List[GTrendsRecord] = []
        if not points:
            records.append(
                GTrendsRecord(
                    category=category,
                    keyword=keyword,
                    _raw={"note": "no_interest_data"},
                )
            )
        else:
            scores = [p["value"] for p in points]
            current, prev, avg_7d, peak = self._summarize_scores(scores)
            delta = current - prev
            # interest_score = 7d average (stable, comparable within self-normalized series)
            records.append(
                GTrendsRecord(
                    category=category,
                    keyword=keyword,
                    interest_score=avg_7d,
                    interest_score_prev_day=prev,
                    interest_delta=delta,
                    interest_avg_7d=avg_7d,
                    interest_peak_7d=peak,
                    is_rising=1 if prev > 0 and (delta / max(prev, 1)) > 0.25 else 0,
                    _raw={
                        "current_1d": current,
                        "prior_1d": prev,
                        "avg_7d": avg_7d,
                        "peak_7d": peak,
                        "n_points": len(points),
                        "points": points[-12:],
                    },
                )
            )

        if want_related:
            related_widget = next(
                (w for w in widgets if w.get("id") == "RELATED_QUERIES"), None
            )
            if related_widget:
                time.sleep(1.0)
                for item in self._rising_from_widget(related_widget)[:8]:
                    query = item["query"]
                    if not is_pet_product(title=query, category=category):
                        continue
                    records.append(
                        GTrendsRecord(
                            category=category,
                            keyword=keyword,
                            is_rising=1,
                            rising_query=query,
                            rising_score=item["value"],
                            _raw=item,
                        )
                    )

        return records

    @staticmethod
    def _summarize_scores(scores: List[int]) -> tuple[int, int, int, int]:
        """
        Summarize hourly interest series into stable bronze fields.

        Each single-keyword series is self-normalized (peak=100), so rare
        terms spike to 100 on one hour. We use window *means including zeros*
        so interest_score reflects typical level, not a one-hour spike.
        """
        if not scores:
            return 0, 0, 0, 0

        def _mean(vals: List[int]) -> int:
            return int(round(sum(vals) / len(vals))) if vals else 0

        avg_7d = _mean(scores)
        peak = max(scores)

        # Recent ~24 points (~1 day hourly) vs prior day
        recent_n = min(24, len(scores))
        recent = scores[-recent_n:]
        latest = _mean(recent)

        if len(scores) > recent_n:
            prior = scores[-(recent_n * 2) : -recent_n]
            prev = _mean(prior) if prior else latest
        else:
            prev = latest

        # Primary score: prefer 7d average (most stable for ranking)
        # Keep latest as the "current day" level for delta.
        return latest, prev, avg_7d, peak

    def _explore(self, keywords: List[str], timeframe: str) -> List[Dict[str, Any]]:
        req = {
            "comparisonItem": [
                {"keyword": kw, "geo": self.geo, "time": timeframe} for kw in keywords
            ],
            "category": 0,
            "property": "",
        }
        data = self._get_json(
            EXPLORE_URL,
            {"hl": self.hl, "tz": self.tz, "req": json.dumps(req)},
        )
        return data.get("widgets", []) if data else []

    def _interest_series(
        self, widget: Dict[str, Any], keywords: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        data = self._get_json(
            MULTILINE_URL,
            {
                "hl": self.hl,
                "tz": self.tz,
                "req": json.dumps(widget.get("request", {})),
                "token": widget.get("token", ""),
            },
        )
        if not data:
            return {}

        timeline = data.get("default", {}).get("timelineData", [])
        series: Dict[str, List[Dict[str, Any]]] = {kw: [] for kw in keywords}

        for point in timeline:
            values = point.get("value", [])
            formatted = (
                point.get("formattedTime")
                or point.get("formattedAxisTime")
                or str(point.get("time", ""))
            )
            ts = point.get("time")
            for i, keyword in enumerate(keywords):
                if i >= len(values):
                    break
                series[keyword].append(
                    {
                        "time": ts,
                        "date": formatted,
                        "value": int(values[i] or 0),
                    }
                )
        return series

    def _rising_from_widget(self, widget: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = self._get_json(
            RELATED_QUERIES_URL,
            {
                "hl": self.hl,
                "tz": self.tz,
                "req": json.dumps(widget.get("request", {})),
                "token": widget.get("token", ""),
            },
        )
        if not data:
            return []

        ranked = data.get("default", {}).get("rankedList", [])
        # Prefer rising list (index 1); fall back to top (index 0)
        rising_list = ranked[1] if len(ranked) > 1 else (ranked[0] if ranked else {})
        rows = rising_list.get("rankedKeyword", []) if isinstance(rising_list, dict) else []
        out: List[Dict[str, Any]] = []
        for row in rows:
            value = row.get("value", 0)
            if value == "Breakout":
                value = 5000
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = 0
            query = row.get("query", "")
            if query:
                out.append({"query": query, "value": value})
        return out

    def _get_json(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 429:
                    wait = 8 * (attempt + 1)
                    logger.warning("GTrends rate limited — sleep %ss", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                text = resp.text
                if text.startswith(")]}'"):
                    text = text.split("\n", 1)[1]
                return json.loads(text)
            except (requests.RequestException, json.JSONDecodeError, IndexError) as exc:
                logger.warning("GTrends request failed %s: %s", url, exc)
                time.sleep(2)
        return None

    def to_bronze_records(self, records: List[GTrendsRecord]) -> List[Dict[str, Any]]:
        now = datetime.now()
        bronze = []
        for r in records:
            is_rising_query = bool(r.rising_query)
            bronze.append(
                {
                    "ingest_date": now.date(),
                    "ingest_ts": now,
                    "category": r.category,
                    "keyword": r.rising_query if is_rising_query else r.keyword,
                    "interest_score": r.interest_score,
                    "interest_score_prev_day": r.interest_score_prev_day,
                    "interest_delta": r.interest_delta,
                    "interest_avg_7d": r.interest_avg_7d,
                    "interest_peak_7d": r.interest_peak_7d,
                    "is_rising": 1 if is_rising_query else r.is_rising,
                    "rising_query": r.rising_query,
                    "rising_score": r.rising_score,
                    "related_topics_json": r.related_topics_json,
                    "_raw_json": json.dumps(r._raw, default=str),
                }
            )
        return bronze
