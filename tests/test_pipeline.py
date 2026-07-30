"""Tests for daily production pipeline."""
from datetime import date

import pandas as pd

from transform.pipeline import run_daily_pipeline


def _amazon_df():
    return pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "asin": "B001",
                "product_title": "Royal Canin Dog Food 4kg",
                "brand": "Royal Canin",
                "category": "Dog Food",
                "rank": 1,
                "rank_delta": 3,
                "rating": 4.5,
                "review_count": 100,
                "price_inr": 999,
                "is_mover_shaker": 1,
            }
        ]
    )


def _gtrends_df():
    return pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "category": "dog_food",
                "keyword": "dog food",
                "interest_score": 80,
                "interest_delta": 10,
                "is_rising": 0,
            }
        ]
    )


def _flipkart_df():
    return pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "product_id": "FK001",
                "product_title": "Royal Canin Maxi Adult Dog Food",
                "brand": "Royal Canin",
                "category": "dog_food",
                "rank": 2,
                "rating": 4.4,
                "review_count": 50,
                "price_inr": 1200,
                "product_url": "https://www.flipkart.com/p/fk001",
            }
        ]
    )


def test_run_daily_pipeline_outputs_facts():
    result = run_daily_pipeline(_amazon_df(), _gtrends_df(), _flipkart_df())
    assert result.legacy_snapshot
    assert result.trending_daily
    assert result.platform_daily
    assert result.search_daily
    assert result.canonical_dim
    row = result.legacy_snapshot[0]
    assert "reason_codes" in row
    assert "recommended_action" in row
    assert "canonical_product_id" in row
    assert row.get("trend_score_v2") is not None
