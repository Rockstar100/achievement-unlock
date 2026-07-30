"""Tests for file-based storage."""
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from dagster_project.resources.file_store import FileStoreResource


@pytest.fixture
def store(tmp_path):
    return FileStoreResource(base_dir=str(tmp_path / "data"))


def test_insert_and_read_today(store):
    records = [
        {
            "ingest_date": date.today(),
            "ingest_ts": datetime.now(),
            "category": "dog_food",
            "rank": 1,
            "product_title": "Royal Canin Dog Food 4kg",
            "product_url": "https://www.amazon.in/dp/B0PETTEST01",
        }
    ]
    path = store.insert("bronze_ecom_trends_amazon", records)
    assert path.exists()
    assert store.count_today("bronze_ecom_trends_amazon") == 1

    today_rows = store.read_today("bronze_ecom_trends_amazon")
    assert today_rows[0]["product_title"] == "Royal Canin Dog Food 4kg"


def test_json_snapshot_created(store):
    records = [{"ingest_date": date.today(), "ingest_ts": datetime.now(), "keyword": "dog food"}]
    store.insert("bronze_ecom_trends_gtrends", records)
    json_dir = store.bronze_json_dir("bronze_ecom_trends_gtrends")
    snapshots = list(json_dir.glob("*.json"))
    assert len(snapshots) == 1
    with open(snapshots[0], encoding="utf-8") as f:
        data = json.load(f)
    assert data[0]["keyword"] == "dog food"


def test_write_and_read_gold(store):
    gold = [
        {
            "product_id": "p1",
            "canonical_title": "Test",
            "trend_score": 85.0,
            "trend_tier": "breakout",
            "computed_date": str(date.today()),
        }
    ]
    store.write_gold(gold)
    assert store.gold_csv_path().exists()
    assert store.gold_json_path().exists()
    rows = store.read_gold_today()
    assert len(rows) == 1
    assert rows[0]["trend_score"] == 85.0


def test_reinsert_same_day_replaces(store):
    store.insert("bronze_ecom_trends_amazon", [{
        "ingest_date": date.today(),
        "rank": 1,
        "product_title": "Pedigree Puppy Food",
        "product_url": "https://www.amazon.in/dp/B0TEST001",
    }])
    store.insert("bronze_ecom_trends_amazon", [{
        "ingest_date": date.today(),
        "rank": 2,
        "product_title": "Whiskas Cat Food",
        "product_url": "https://www.amazon.in/dp/B0TEST002",
    }])
    df = store.read_table("bronze_ecom_trends_amazon")
    assert len(df) == 1
    assert int(df.iloc[0]["rank"]) == 2


def test_read_recent_and_gold_fallback(store, monkeypatch):
    from datetime import timedelta

    old = date.today() - timedelta(days=3)
    store.insert("bronze_ecom_trends_amazon", [{
        "ingest_date": str(old),
        "rank": 1,
        "product_title": "Pedigree Puppy Food",
        "product_url": "https://www.amazon.in/dp/B0TEST001",
    }])
    monkeypatch.setenv("HEALTH_FRESHNESS_DAYS", "7")
    assert store.count_today("bronze_ecom_trends_amazon") == 0
    assert store.count_recent("bronze_ecom_trends_amazon") == 1

    store.write_gold([{
        "product_id": "p1",
        "canonical_title": "Test",
        "trend_score": 85.0,
        "trend_tier": "breakout",
        "computed_date": str(old),
    }])
    assert store.read_gold_today() == []
    recent = store.read_gold_recent()
    assert len(recent) == 1
    assert recent[0]["product_id"] == "p1"


def test_csv_preserves_unicode_title(store):
    title = "Qpets® 3 Way Rainbow Tunnel Cat Toys"
    store.write_gold([{
        "product_id": "p_unicode",
        "canonical_title": title,
        "trend_score": 70.0,
        "trend_tier": "rising",
        "computed_date": str(date.today()),
    }])
    rows = store.read_gold()
    assert rows[0]["canonical_title"] == title
