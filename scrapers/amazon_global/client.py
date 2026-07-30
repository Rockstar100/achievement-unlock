"""
Amazon.com (US) pet-supplies bestsellers — GLOBAL SUPPLEMENTARY SOURCE.

Not part of the India-native pipeline. Used only as an early-signal input
for transform/global_signals.py, which maps it back to India categories
with an explicit relevance score. Never blended directly into the India
trend_score.

Reuses AmazonScraper's HTML parsing (same underlying Amazon platform,
same CSS class conventions) with a US base URL and US category config.

Note: amazon.com bestseller list pages do not render a price at all
(Amazon dropped it from this page type) — price_usd will be 0 for every
row here. Rank, rating, and review count are real signals.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List

from scrapers.amazon.client import AmazonProduct, AmazonScraper
from scrapers.config_loader import load_amazon_us_categories

logger = logging.getLogger(__name__)

AMAZON_US_BASE = "https://www.amazon.com"

US_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}


class AmazonUSScraper(AmazonScraper):
    """Fetch amazon.com pet-supplies bestseller listings (US, global supplementary)."""

    def __init__(self, request_delay: float = 2.0, use_playwright: str = "auto"):
        super().__init__(
            marketplace="us",
            request_delay=request_delay,
            use_playwright=use_playwright,
            base_url=AMAZON_US_BASE,
            config_loader=load_amazon_us_categories,
            headers=US_HEADERS,
        )

    def to_global_bronze_records(self, products: List[AmazonProduct]) -> List[Dict[str, Any]]:
        """gold_fact_global_pet_trend_signals_daily-shaped records (bronze layer)."""
        now = datetime.now()
        records = []
        for p in products:
            if not self._is_valid_pet_product(p):
                continue
            d = asdict(p)
            raw = d.pop("_raw", {})
            records.append(
                {
                    "ingest_date": now.date(),
                    "ingest_ts": now,
                    "source": "amazon_us",
                    "source_market": "US",
                    "marketplace": "us",
                    "category": p.category,
                    "rank_position": p.rank,
                    "is_mover_shaker": p.is_mover_shaker,
                    "asin": p.asin,
                    "product_title": p.product_title,
                    "brand": p.brand,
                    "price": p.price_inr,  # amazon.com bestseller pages show no price; 0
                    "currency": "USD",
                    "rating": p.rating,
                    "review_count": p.review_count,
                    "product_url": p.product_url,
                    "image_url": p.image_url,
                    "fetch_method": "html_scrape",
                    "compliance_status": "public_page_no_login",
                }
            )
        return records
