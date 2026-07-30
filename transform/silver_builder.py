"""Silver layer — typed daily facts from bronze snapshots."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List

import pandas as pd

from scrapers.filters.pet_filter import filter_pet_records, is_pet_product
from scrapers.flipkart.client import FlipkartScraper
from transform.gold_builder import _clean_image_url, _clean_title, _clean_url, _normalize_brand, _normalize_category


def _today_cutoff(df: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    if df.empty or "ingest_date" not in df.columns:
        return df
    cutoff = str(date.today() - pd.Timedelta(days=days))
    return df[df["ingest_date"].astype(str) >= cutoff]


def build_platform_daily(
    amazon_df: pd.DataFrame,
    flipkart_df: pd.DataFrame,
    snapshot_date: date | None = None,
) -> List[Dict[str, Any]]:
    """Parse bronze into gold_fact_product_platform_daily-shaped rows."""
    snap = snapshot_date or date.today()
    rows: List[Dict[str, Any]] = []

    for src_df, platform, id_field, rank_ctx in (
        (_today_cutoff(amazon_df), "amazon_in", "asin", "bestseller"),
        (_today_cutoff(flipkart_df), "flipkart", "product_id", "keyword_search"),
    ):
        if src_df.empty:
            continue
        for rec in filter_pet_records(src_df.to_dict(orient="records")):
            title = _clean_title(str(rec.get("product_title", "")))
            if not is_pet_product(
                title=title,
                url=str(rec.get("product_url", "")),
                search_term=str(rec.get("search_term", "")),
                category=str(rec.get("category", "")),
            ):
                continue
            pid = str(rec.get(id_field, "") or rec.get("product_id", ""))
            if platform == "flipkart":
                url = _clean_url(rec.get("product_url"))
                pid = FlipkartScraper.flipkart_pid(url) or pid
            rows.append(
                {
                    "snapshot_date": str(snap),
                    "platform": platform,
                    "platform_product_id": pid,
                    "canonical_product_id": "",
                    "source_url": _clean_url(rec.get("product_url")),
                    "rank_context": rank_ctx,
                    "rank_keyword": str(rec.get("search_term", "") or rec.get("category", "")),
                    "rank_position": int(rec.get("rank") or 0) or None,
                    "sponsored_flag": False,
                    "price": float(rec.get("price_inr") or 0) or None,
                    "mrp": float(rec.get("mrp_inr") or 0) or None,
                    "discount_pct": int(rec.get("discount_pct") or 0) or None,
                    "rating": float(rec.get("rating") or 0) or None,
                    "review_count": int(rec.get("review_count") or 0) or None,
                    "availability_status": str(rec.get("availability", "In Stock")),
                    "seller_name": str(rec.get("seller", "") or ""),
                    "delivery_speed_bucket": "",
                    "crawl_status": "ok",
                    "source_connector": str(rec.get("source_connector", "scrape")),
                    "image_url": _clean_image_url(rec.get("image_url")),
                    "brand": _normalize_brand(str(rec.get("brand", "")), title),
                    "canonical_title": title,
                    "category": _normalize_category(str(rec.get("category", "")), title),
                }
            )
    return rows


def build_search_demand_daily(
    gtrends_df: pd.DataFrame,
    snapshot_date: date | None = None,
) -> List[Dict[str, Any]]:
    snap = snapshot_date or date.today()
    rows: List[Dict[str, Any]] = []
    gt = _today_cutoff(gtrends_df)
    if gt.empty:
        return rows
    for rec in gt.to_dict(orient="records"):
        keyword = str(rec.get("keyword", "") or "")
        if not keyword:
            continue
        if not is_pet_product(title=keyword, category=str(rec.get("category", ""))):
            continue
        is_rising = int(rec.get("is_rising") or 0) == 1
        rows.append(
            {
                "snapshot_date": str(snap),
                "source": "google_trends",
                "query": keyword,
                "geo": "IN",
                "mapped_species": "",
                "mapped_category": _normalize_category(str(rec.get("category", ""))),
                "canonical_product_id": "",
                "interest_index": float(rec.get("interest_score") or rec.get("interest_avg_7d") or 0),
                "related_query": str(rec.get("rising_query", "") or ""),
                "rising_value": float(rec.get("rising_score") or 0),
                "breakout_flag": is_rising and float(rec.get("rising_score") or 0) >= 100,
                "confidence": 0.9,
            }
        )
    return rows
