"""Tests for TikTokShopGlobalClient orchestrator."""
from pathlib import Path

from scrapers.tiktok_shop_global.client import TikTokShopGlobalClient, DEFAULT_SAMPLE_CSV


def test_global_client_loads_demo_sample_by_default():
    if not DEFAULT_SAMPLE_CSV.exists():
        return
    client = TikTokShopGlobalClient(use_sample_fallback=True)
    rows = client.fetch_all()
    assert len(rows) >= 10
    assert all(r["source"] == "tiktok_shop_us" for r in rows)
    assert client.fetch_source_label().startswith("demo_sample")


def test_global_client_no_sample_returns_empty():
    client = TikTokShopGlobalClient(use_sample_fallback=False, csv_path="/nonexistent/x.csv")
    assert client.fetch_all() == []


def test_to_bronze_records_assigns_rank_by_sold_count():
    client = TikTokShopGlobalClient(use_sample_fallback=False)
    products = [
        {"product_id": "a", "product_title": "Dog Food Premium", "category": "dog_food", "sold_count": 100},
        {"product_id": "b", "product_title": "Cat Food Premium", "category": "cat_food", "sold_count": 500},
    ]
    records = client.to_bronze_records(products)
    assert records[0]["product_id"] == "b"
    assert records[0]["rank_position"] == 1
