"""Production daily transform entry point."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd

from transform.fact_builder import build_daily_facts

FACT_PLATFORM = "gold_fact_product_platform_daily"
FACT_SEARCH = "gold_fact_search_demand_daily"
FACT_CANONICAL = "gold_dim_product_canonical"
FACT_TRENDING = "gold_fact_trending_pet_products_daily"
LEGACY_GOLD = "gold_dim_trending_pet_products"


@dataclass
class TransformResult:
    platform_daily: List[Dict[str, Any]] = field(default_factory=list)
    search_daily: List[Dict[str, Any]] = field(default_factory=list)
    canonical_dim: List[Dict[str, Any]] = field(default_factory=list)
    trending_daily: List[Dict[str, Any]] = field(default_factory=list)
    legacy_snapshot: List[Dict[str, Any]] = field(default_factory=list)
    snapshot_date: str = ""


def run_daily_pipeline(
    amazon_df: pd.DataFrame,
    gtrends_df: pd.DataFrame,
    flipkart_df: pd.DataFrame,
    historical_trending: Optional[pd.DataFrame] = None,
    snapshot_date: Optional[date] = None,
) -> TransformResult:
    snap = snapshot_date or date.today()
    out = build_daily_facts(
        amazon_df, gtrends_df, flipkart_df, historical_trending, snap
    )
    return TransformResult(
        platform_daily=out["platform_daily"],
        search_daily=out["search_daily"],
        canonical_dim=out["canonical_dim"],
        trending_daily=out["trending_daily"],
        legacy_snapshot=out["legacy_snapshot"],
        snapshot_date=str(snap),
    )
