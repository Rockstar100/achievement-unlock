"""
TikTok Shop CSV importer — loads a lawfully-obtained export (licensed data
vendor, or your own export from an allowed workflow) into the same schema
the official API client produces, so downstream code doesn't care which
path the data came from.

Expected CSV columns (extras are ignored, missing ones default sensibly):
    product_id, product_title, keyword, category, price, currency,
    rating, review_count, sold_count, video_count, creator_count,
    engagement_count, product_url, image_url
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


class TikTokShopCSVImporter:
    """Load a TikTok Shop product export CSV into normalized records."""

    def load(self, csv_path: str) -> List[Dict[str, Any]]:
        path = Path(csv_path)
        if not path.exists():
            logger.info("TikTok Shop CSV import path does not exist: %s", csv_path)
            return []

        df = pd.read_csv(path)
        if df.empty:
            return []

        records = []
        for row in df.to_dict(orient="records"):
            records.append(
                {
                    "source": "tiktok_shop_us",
                    "source_market": str(row.get("source_market") or "US"),
                    "keyword": str(row.get("keyword", "") or ""),
                    "category": str(row.get("category", "") or ""),
                    "product_id": str(row.get("product_id", "") or ""),
                    "product_title": str(row.get("product_title", "") or ""),
                    "brand": str(row.get("brand", "") or ""),
                    "price": float(row.get("price") or 0),
                    "currency": str(row.get("currency") or "USD"),
                    "sold_count": int(row.get("sold_count") or 0),
                    "video_count": int(row.get("video_count") or 0),
                    "creator_count": int(row.get("creator_count") or 0),
                    "engagement_count": int(row.get("engagement_count") or 0),
                    "rating": float(row.get("rating") or 0),
                    "review_count": int(row.get("review_count") or 0),
                    "product_url": str(row.get("product_url", "") or ""),
                    "image_url": str(row.get("image_url", "") or ""),
                    "fetch_method": "csv_import",
                    "compliance_status": "licensed_or_manual_export",
                }
            )
        return records
