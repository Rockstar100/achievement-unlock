"""
TikTok Shop US — unified fetch orchestrator.

Priority:
  1. Official Partner API (if TIKTOK_SHOP_* env vars set)
  2. Explicit CSV path (--tiktok-csv or TIKTOK_SHOP_CSV_PATH)
  3. Bundled demo sample (development only — clearly labeled)

Never scrapes tiktok.com / shop.tiktok.com directly.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from scrapers.config_loader import load_tiktok_shop_us_keywords
from scrapers.filters.pet_filter import is_pet_product

from .client_csv_import import TikTokShopCSVImporter
from .client_official_api import TikTokShopAPIClient

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SAMPLE_CSV = ROOT / "data" / "samples" / "tiktok_shop_us_pet_sample.csv"


class TikTokShopGlobalClient:
    """Fetch TikTok Shop US pet products via API, CSV, or demo sample."""

    def __init__(
        self,
        csv_path: Optional[str] = None,
        use_sample_fallback: bool = False,
    ):
        self.csv_path = csv_path or os.getenv("TIKTOK_SHOP_CSV_PATH", "")
        self.use_sample_fallback = use_sample_fallback
        self.api = TikTokShopAPIClient()
        self.importer = TikTokShopCSVImporter()

    def fetch_all(self) -> List[Dict[str, Any]]:
        if self.api.is_configured():
            return self._fetch_via_api()
        if self.csv_path:
            rows = self.importer.load(self.csv_path)
            if rows:
                return self._pet_filter(rows)
        if self.use_sample_fallback and DEFAULT_SAMPLE_CSV.exists():
            rows = self.importer.load(str(DEFAULT_SAMPLE_CSV))
            if rows:
                logger.info(
                    "Using demo TikTok Shop sample (%s) — not live data",
                    DEFAULT_SAMPLE_CSV.name,
                )
                return self._pet_filter(rows)
        return []

    def fetch_source_label(self) -> str:
        if self.api.is_configured():
            return "official_api"
        if self.csv_path:
            return f"csv:{self.csv_path}"
        if self.use_sample_fallback and DEFAULT_SAMPLE_CSV.exists():
            return f"demo_sample:{DEFAULT_SAMPLE_CSV.name}"
        return "none"

    def _fetch_via_api(self) -> List[Dict[str, Any]]:
        cfg = load_tiktok_shop_us_keywords()
        max_per = int((cfg.get("defaults") or {}).get("max_items_per_keyword", 20))
        rows: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for cat_key, cat_cfg in (cfg.get("keywords") or {}).items():
            for term in cat_cfg.get("search_terms") or [cat_cfg.get("display_name", cat_key)]:
                for item in self.api.search(term, cat_key, limit=max_per):
                    pid = str(item.get("product_id") or "")
                    if pid and pid in seen:
                        continue
                    if pid:
                        seen.add(pid)
                    rows.append(item)
        return self._pet_filter(rows)

    @staticmethod
    def _pet_filter(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for row in rows:
            title = str(row.get("product_title", ""))
            category = str(row.get("category", ""))
            if not title:
                continue
            if not is_pet_product(title=title, category=category):
                continue
            out.append(row)
        return out

    def to_bronze_records(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = datetime.now()
        sorted_products = sorted(
            products,
            key=lambda r: -(float(r.get("sold_count") or 0)),
        )
        records = []
        for rank, p in enumerate(sorted_products, start=1):
            records.append(
                {
                    "ingest_date": now.date(),
                    "ingest_ts": now,
                    "source": "tiktok_shop_us",
                    "source_market": p.get("source_market", "US"),
                    "rank_position": rank,
                    "keyword": p.get("keyword", ""),
                    "category": p.get("category", ""),
                    "product_id": p.get("product_id", ""),
                    "product_title": p.get("product_title", ""),
                    "brand": p.get("brand", ""),
                    "price": p.get("price") or 0,
                    "currency": p.get("currency", "USD"),
                    "sold_count": p.get("sold_count") or 0,
                    "video_count": p.get("video_count") or 0,
                    "creator_count": p.get("creator_count") or 0,
                    "engagement_count": p.get("engagement_count") or 0,
                    "rating": p.get("rating") or 0,
                    "review_count": p.get("review_count") or 0,
                    "product_url": p.get("product_url", ""),
                    "image_url": p.get("image_url", ""),
                    "fetch_method": p.get("fetch_method", ""),
                    "compliance_status": p.get("compliance_status", ""),
                }
            )
        return records
