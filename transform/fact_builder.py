"""Daily gold facts orchestration (canonical dim + platform/search facts + trending)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from transform.canonical import build_canonical_record, canonical_product_id, infer_species
from transform.gold_builder import build_gold_from_bronze
from transform.scoring_v2 import score_product
from transform.silver_builder import build_platform_daily, build_search_demand_daily


def _attach_canonical_ids(legacy_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for row in legacy_rows:
        brand = str(row.get("normalized_brand", "") or "")
        title = str(row.get("canonical_title", "") or "")
        mk = f"{brand}|{title[:80]}".lower()
        row["canonical_product_id"] = canonical_product_id(mk, brand, title)
        row["match_key"] = mk
    return legacy_rows


def _link_platform_rows(
    platform_rows: List[Dict[str, Any]],
    legacy_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_asin: Dict[str, str] = {}
    by_fk: Dict[str, str] = {}
    by_title: Dict[str, str] = {}
    for row in legacy_rows:
        cid = str(row.get("canonical_product_id", ""))
        if row.get("amazon_asin"):
            by_asin[str(row["amazon_asin"])] = cid
        if row.get("flipkart_product_id"):
            by_fk[str(row["flipkart_product_id"])] = cid
        tkey = str(row.get("canonical_title", "")).lower()[:80]
        if tkey:
            by_title[tkey] = cid

    for prow in platform_rows:
        pid = str(prow.get("platform_product_id", ""))
        plat = prow.get("platform", "")
        title_key = str(prow.get("canonical_title", "")).lower()[:80]
        cid = ""
        if plat == "amazon_in" and pid in by_asin:
            cid = by_asin[pid]
        elif plat == "flipkart" and pid in by_fk:
            cid = by_fk[pid]
        elif title_key in by_title:
            cid = by_title[title_key]
        prow["canonical_product_id"] = cid
    return platform_rows


def _hist_from_trending_facts(fact_df: pd.DataFrame) -> pd.DataFrame:
    if fact_df.empty:
        return pd.DataFrame()
    cols = [c for c in (
        "snapshot_date", "canonical_product_id", "amazon_rank", "flipkart_rank",
        "review_count", "interest_index",
    ) if c in fact_df.columns]
    return fact_df[cols].copy() if cols else pd.DataFrame()


def build_daily_facts(
    amazon_df: pd.DataFrame,
    gtrends_df: pd.DataFrame,
    flipkart_df: pd.DataFrame,
    historical_trending: Optional[pd.DataFrame] = None,
    snapshot_date: Optional[date] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Full daily transform: silver → legacy gold → canonical + trending facts."""
    snap = snapshot_date or date.today()
    snap_str = str(snap)

    platform_daily = build_platform_daily(amazon_df, flipkart_df, snap)
    search_daily = build_search_demand_daily(gtrends_df, snap)

    legacy = build_gold_from_bronze(amazon_df, gtrends_df, flipkart_df)
    legacy = _attach_canonical_ids(legacy)
    platform_daily = _link_platform_rows(platform_daily, legacy)

    canonical_dim: List[Dict[str, Any]] = []
    trending_daily: List[Dict[str, Any]] = []
    hist = _hist_from_trending_facts(
        historical_trending if historical_trending is not None and not historical_trending.empty else pd.DataFrame()
    )

    for row in legacy:
        cid = str(row.get("canonical_product_id", ""))
        prod_for_canon = {**row, "match_key": row.get("match_key", "")}
        canon = build_canonical_record(prod_for_canon, snap)
        canonical_dim.append(canon)

        gt = {
            "gtrends_category_interest": row.get("gtrends_category_interest"),
            "gtrends_interest_delta_7d": row.get("gtrends_interest_delta_7d"),
        }
        scored = score_product(row, gt, hist, snap_str)
        trend_row = {
            "snapshot_date": snap_str,
            "canonical_product_id": cid,
            "canonical_title": row.get("canonical_title", ""),
            "normalized_brand": row.get("normalized_brand", ""),
            "category": row.get("category", ""),
            "species": canon.get("species", ""),
            "amazon_rank": row.get("amazon_rank"),
            "flipkart_rank": row.get("flipkart_avg_rank"),
            "amazon_rating": row.get("amazon_rating"),
            "flipkart_rating": row.get("flipkart_rating"),
            "review_count": row.get("amazon_review_count") or row.get("flipkart_review_count"),
            "interest_index": row.get("gtrends_category_interest"),
            "amazon_price_inr": row.get("amazon_price_inr"),
            "flipkart_price_inr": row.get("flipkart_price_inr"),
            "image_url": row.get("image_url"),
            "sources": row.get("sources", ""),
            **scored,
            "rank_position": row.get("rank_position"),
            "computed_ts": datetime.now().isoformat(),
        }
        trending_daily.append(trend_row)

        # Merge v2 fields back into legacy snapshot for dashboard / Slack
        row["trend_score_v1"] = row.get("trend_score")
        row["trend_score"] = scored["trend_score"]
        row["trend_score_v2"] = scored["trend_score_v2"]
        row["trend_score_baseline"] = scored.get("trend_score_baseline")
        row["trend_momentum_bonus"] = scored.get("trend_momentum_bonus")
        row["trend_tier"] = scored["trend_tier"]
        row["trend_velocity_7d"] = scored["trend_velocity_7d"]
        row["trend_confidence"] = scored["trend_confidence"]
        row["penalty_score"] = scored["penalty_score"]
        row["reason_codes"] = scored["reason_codes"] or ""
        row["recommended_action"] = scored["recommended_action"]

    trending_daily.sort(
        key=lambda r: (-float(r.get("trend_score") or 0), r.get("canonical_title", ""))
    )
    for i, tr in enumerate(trending_daily, start=1):
        tr["rank_position"] = i

    legacy.sort(key=lambda x: (-x.get("trend_score", 0), x.get("canonical_title", "")))
    for i, row in enumerate(legacy, start=1):
        row["rank_position"] = i

    return {
        "platform_daily": platform_daily,
        "search_daily": search_daily,
        "canonical_dim": canonical_dim,
        "trending_daily": trending_daily,
        "legacy_snapshot": legacy,
    }
