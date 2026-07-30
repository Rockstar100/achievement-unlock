"""
Global supplementary pet-trend signals (Amazon US, TikTok Shop US) and their
bridge to India categories.

This is deliberately a SEPARATE layer from the India-native gold tables:
global_signal_score never feeds into India's trend_score. It only produces
an india_relevance_score / global_opportunity_score used for a "things to
watch" list, per gold_fact_global_pet_trend_signals_daily and
gold_bridge_global_to_india_pet_opportunities.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Set

from transform.canonical import infer_species
from transform.gold_builder import _normalize_brand, _normalize_category

FACT_GLOBAL_SIGNALS = "gold_fact_global_pet_trend_signals_daily"
FACT_GLOBAL_BRIDGE = "gold_bridge_global_to_india_pet_opportunities"

INDIA_CATEGORIES = {
    "dog_food", "cat_food", "dog_toys", "cat_toys", "grooming",
    "beds_accessories", "health_wellness", "collars_leashes", "training",
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _rank_score(rank: Optional[float]) -> float:
    if not rank or rank <= 0:
        return 35.0
    return _clamp(100.0 - (float(rank) - 1.0) * 3.0)


def _rating_score(rating: Optional[float], reviews: Optional[float]) -> float:
    r = float(rating or 0)
    n = float(reviews or 0)
    if r <= 0:
        return 30.0
    base = (r / 5.0) * 70.0
    volume = min(30.0, (n**0.5) / 3.0)
    return _clamp(base + volume)


def score_amazon_us_signal(row: Dict[str, Any]) -> Dict[str, Any]:
    """Level-based score (no cross-day history yet for this new source)."""
    rank_s = _rank_score(row.get("rank_position"))
    rating_s = _rating_score(row.get("rating"), row.get("review_count"))
    mover_bonus = 10.0 if row.get("is_mover_shaker") else 0.0
    score = round(_clamp(0.55 * rank_s + 0.35 * rating_s + mover_bonus), 2)
    return {"global_signal_score": score, "signal_basis": "rank+rating (no price on amazon.com list page)"}


def score_tiktok_shop_signal(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Momentum-style weights from the design brief, applied as a level score
    since this is a new source with no prior-day history yet:
        0.30 sold_count | 0.20 creator_count | 0.20 video/engagement
        0.15 search rank | 0.10 review volume | 0.05 rating
    """
    sold = min(1.0, float(row.get("sold_count") or 0) / 5000.0)
    creators = min(1.0, float(row.get("creator_count") or 0) / 200.0)
    engagement = min(1.0, float(row.get("engagement_count") or row.get("video_count") or 0) / 500.0)
    rank_s = _rank_score(row.get("rank_position")) / 100.0
    reviews = min(1.0, float(row.get("review_count") or 0) / 2000.0)
    rating_q = min(1.0, float(row.get("rating") or 0) / 5.0)

    raw = 0.30 * sold + 0.20 * creators + 0.20 * engagement + 0.15 * rank_s + 0.10 * reviews + 0.05 * rating_q
    score = round(_clamp(raw * 100.0), 2)
    return {"global_signal_score": score, "signal_basis": "sold+creator+engagement+rank+reviews+rating"}


def build_global_platform_daily(
    amazon_us_records: Iterable[Dict[str, Any]],
    tiktok_shop_records: Iterable[Dict[str, Any]],
    snapshot_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """gold_fact_global_pet_trend_signals_daily rows."""
    snap = str(snapshot_date or date.today())
    now = datetime.now().isoformat()
    rows: List[Dict[str, Any]] = []

    for rec in amazon_us_records:
        title = str(rec.get("product_title", ""))
        category = _normalize_category(str(rec.get("category", "")), title)
        scored = score_amazon_us_signal(rec)
        rows.append(
            {
                "snapshot_date": snap,
                "source": "amazon_us",
                "source_market": "US",
                "product_id": str(rec.get("asin", "")),
                "product_title": title,
                "brand": _normalize_brand(str(rec.get("brand", "")), title),
                "species": infer_species(title, category),
                "category": category,
                "rank_position": rec.get("rank_position"),
                "price": rec.get("price") or None,
                "currency": rec.get("currency", "USD"),
                "rating": rec.get("rating"),
                "review_count": rec.get("review_count"),
                "sold_count": None,
                "video_count": None,
                "creator_count": None,
                "engagement_score": None,
                "source_url": rec.get("product_url", ""),
                "image_url": rec.get("image_url", ""),
                "fetch_method": rec.get("fetch_method", "html_scrape"),
                "compliance_status": rec.get("compliance_status", ""),
                "computed_ts": now,
                **scored,
            }
        )

    for rec in tiktok_shop_records:
        title = str(rec.get("product_title", ""))
        category = _normalize_category(str(rec.get("category", "")), title)
        scored = score_tiktok_shop_signal(rec)
        rows.append(
            {
                "snapshot_date": snap,
                "source": "tiktok_shop_us",
                "source_market": rec.get("source_market", "US"),
                "product_id": str(rec.get("product_id", "")),
                "product_title": title,
                "brand": _normalize_brand(str(rec.get("brand", "")), title),
                "species": infer_species(title, category),
                "category": category,
                "rank_position": rec.get("rank_position"),
                "price": rec.get("price") or None,
                "currency": rec.get("currency", "USD"),
                "rating": rec.get("rating"),
                "review_count": rec.get("review_count"),
                "sold_count": rec.get("sold_count"),
                "video_count": rec.get("video_count"),
                "creator_count": rec.get("creator_count"),
                "engagement_score": rec.get("engagement_count"),
                "source_url": rec.get("product_url", ""),
                "image_url": rec.get("image_url", ""),
                "fetch_method": rec.get("fetch_method", ""),
                "compliance_status": rec.get("compliance_status", ""),
                "computed_ts": now,
                **scored,
            }
        )

    rows.sort(key=lambda r: -(r.get("global_signal_score") or 0))
    for i, row in enumerate(rows, start=1):
        row["rank_position_global"] = i
    return rows


def build_india_bridge(
    global_rows: Iterable[Dict[str, Any]],
    india_brands: Set[str],
    snapshot_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """
    gold_bridge_global_to_india_pet_opportunities rows.

    india_relevance_score: how cleanly this maps to an India category we
    already track (taxonomy match), independent of whether it's sold here.
    india_availability: whether the brand already appears in today's India
    gold table — used for the "already available" vs "not yet available"
    dashboard split, not folded into a single opaque score.
    """
    snap = str(snapshot_date or date.today())
    india_brands_lower = {b.lower() for b in india_brands if b}
    rows: List[Dict[str, Any]] = []

    for r in global_rows:
        category = r.get("category", "")
        brand = str(r.get("brand", "") or "")
        category_relevance = 1.0 if category in INDIA_CATEGORIES else 0.4
        available = brand.lower() in india_brands_lower if brand else False
        availability_match = 1.0 if available else 0.5

        global_score = float(r.get("global_signal_score") or 0)
        opportunity_score = round(
            _clamp(0.60 * global_score + 0.25 * (category_relevance * 100) + 0.15 * (availability_match * 100)),
            2,
        )

        if available:
            bucket = "already_available_in_india"
            reason = f"Brand '{brand}' already tracked in India gold data; global signal may indicate a rising SKU/variant to prioritize."
        elif category_relevance >= 1.0:
            bucket = "not_yet_available_in_india"
            reason = f"Category '{category}' already sold in India; brand '{brand or 'unknown'}' not seen in today's India gold data - potential white-space opportunity."
        else:
            bucket = "watch_only"
            reason = "Category doesn't map cleanly to a tracked India category - treat as a low-confidence early signal."

        rows.append(
            {
                "snapshot_date": snap,
                "source": r.get("source"),
                "product_id": r.get("product_id"),
                "product_title": r.get("product_title"),
                "brand": brand,
                "mapped_india_category": category,
                "india_category_relevance": category_relevance,
                "india_availability": available,
                "global_opportunity_bucket": bucket,
                "global_opportunity_score": opportunity_score,
                "reason": reason,
            }
        )

    rows.sort(key=lambda r: -(r.get("global_opportunity_score") or 0))
    return rows
