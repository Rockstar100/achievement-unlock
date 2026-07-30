#!/usr/bin/env python
"""
Run the full pipeline locally using CSV/JSON files (no ClickHouse).

Usage:
    python scripts/run_local.py
    python scripts/run_local.py --skip-gtrends   # skip live Google Trends API
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Project root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dagster_project.resources.file_store import FileStoreResource
from scrapers.amazon import AmazonScraper
from scrapers.amazon.client import AmazonProduct
from scrapers.flipkart import FlipkartScraper
from scrapers.flipkart.client import FlipkartProduct
from scrapers.logging_config import is_production, setup_logging
from transform.pipeline import FACT_CANONICAL, FACT_PLATFORM, FACT_SEARCH, FACT_TRENDING, run_daily_pipeline


def sample_amazon():
    return [
        AmazonProduct(
            category="Dog Food", subcategory="Dry Food", rank=1, asin="B0PETDOG01",
            product_title="Royal Canin Maxi Adult Dry Dog Food 4kg", brand="Royal Canin",
            price_inr=3499.0, mrp_inr=3999.0, discount_pct=12, rating=4.5,
            review_count=1250, product_url="https://www.amazon.in/dp/B0PETDOG01",
        ),
        AmazonProduct(
            category="Cat Food", subcategory="Dry Food", rank=1, asin="B0PETCAT01",
            product_title="Whiskas Adult Dry Cat Food Ocean Fish 3kg", brand="Whiskas",
            price_inr=899.0, mrp_inr=999.0, rating=4.3, review_count=3200,
            is_mover_shaker=1, rank_delta=50, product_url="https://www.amazon.in/dp/B0PETCAT01",
        ),
    ]


def sample_flipkart():
    return [
        FlipkartProduct(
            search_term="dog food", category="dog_food", rank=1, product_id="FK_PET_DOG",
            product_title="Pedigree Adult Dry Dog Food 3kg", brand="Pedigree",
            price_inr=1299.0, mrp_inr=1499.0, rating=4.2, review_count=5000,
            product_url="https://www.flipkart.com/pedigree-dog-food/p/itm",
        ),
        FlipkartProduct(
            search_term="cat food", category="cat_food", rank=1, product_id="FK_PET_CAT",
            product_title="Whiskas Kitten Dry Cat Food 1.1kg", brand="Whiskas",
            price_inr=499.0, rating=4.4, review_count=3200,
            product_url="https://www.flipkart.com/whiskas-cat-food/p/itm",
        ),
    ]


def sample_gtrends_records():
    now = datetime.now()
    return [
        {"ingest_date": now.date(), "ingest_ts": now, "category": "dog_food",
         "keyword": "dog food", "interest_score": 71, "interest_score_prev_day": 51,
         "interest_delta": 20, "interest_avg_7d": 52, "interest_peak_7d": 90,
         "is_rising": 0, "rising_query": "", "rising_score": 0,
         "related_topics_json": "{}", "_raw_json": "{}"},
        {"ingest_date": now.date(), "ingest_ts": now, "category": "cat_food",
         "keyword": "cat food", "interest_score": 64, "interest_score_prev_day": 58,
         "interest_delta": 6, "interest_avg_7d": 55, "interest_peak_7d": 88,
         "is_rising": 0, "rising_query": "", "rising_score": 0,
         "related_topics_json": "{}", "_raw_json": "{}"},
    ]


def main():
    log = setup_logging("run_local")
    parser = argparse.ArgumentParser(description="Run local file-based pipeline")
    parser.add_argument("--data-dir", default="data", help="Output data directory")
    parser.add_argument("--skip-gtrends", action="store_true", help="Use sample GTrends data")
    parser.add_argument("--skip-scrape", action="store_true", help="Use all sample data")
    parser.add_argument(
        "--sample-fallback",
        action="store_true",
        help="Fall back to sample data when live scrape returns no rows",
    )
    args = parser.parse_args()

    if is_production() and (args.skip_scrape or args.sample_fallback):
        raise SystemExit("ERROR: --skip-scrape / --sample-fallback blocked when ENVIRONMENT=production")

    store = FileStoreResource(base_dir=args.data_dir)
    print(f"Data directory: {store.root.resolve()}")
    log.info("Starting pipeline env=%s", "production" if is_production() else "development")

    # --- Bronze: Amazon ---
    print("\n[1/4] Amazon bronze...")
    amazon_scraper = AmazonScraper()
    if args.skip_scrape:
        products = sample_amazon()
        print("  Using sample Amazon data (--skip-scrape)")
    else:
        products = amazon_scraper.fetch_all()
        if not products and args.sample_fallback:
            print("  Live scrape empty — using sample Amazon data")
            products = sample_amazon()
        elif not products:
            print("  WARNING: Live Amazon scrape returned 0 rows")
    amazon_records = amazon_scraper.to_bronze_records(products)
    amazon_path = store.insert("bronze_ecom_trends_amazon", amazon_records)
    print(f"  Wrote {len(amazon_records)} rows -> {amazon_path}")

    # --- Bronze: Google Trends ---
    print("\n[2/4] Google Trends bronze...")
    if args.skip_gtrends or args.skip_scrape:
        gtrends_records = sample_gtrends_records()
        print("  Using sample GTrends data")
    else:
        from scrapers.trends import get_trends_provider

        provider = get_trends_provider()
        gtrends_records = provider.to_bronze_records(provider.fetch_all())
    if gtrends_records:
        gt_path = store.insert("bronze_ecom_trends_gtrends", gtrends_records)
        print(f"  Wrote {len(gtrends_records)} rows -> {gt_path}")
    else:
        print("  No GTrends data")

    # --- Bronze: Flipkart ---
    print("\n[3/4] Flipkart bronze...")
    flipkart_scraper = FlipkartScraper()
    if args.skip_scrape:
        fk_products = sample_flipkart()
        print("  Using sample Flipkart data (--skip-scrape)")
    else:
        fk_products = flipkart_scraper.fetch_all()
        if not fk_products and args.sample_fallback:
            print("  Live scrape empty — using sample Flipkart data")
            fk_products = sample_flipkart()
        elif not fk_products:
            print("  WARNING: Live Flipkart scrape returned 0 rows")
    flipkart_records = flipkart_scraper.to_bronze_records(fk_products)
    fk_path = store.insert("bronze_ecom_trends_flipkart", flipkart_records)
    print(f"  Wrote {len(flipkart_records)} rows -> {fk_path}")

    # --- Gold ---
    print("\n[4/4] Gold transformation (daily facts + snapshot)...")
    hist = store.read_fact_table(FACT_TRENDING)
    result = run_daily_pipeline(
        store.read_table("bronze_ecom_trends_amazon"),
        store.read_table("bronze_ecom_trends_gtrends"),
        store.read_table("bronze_ecom_trends_flipkart"),
        historical_trending=hist,
    )
    snap = result.snapshot_date
    for table, rows in (
        (FACT_PLATFORM, result.platform_daily),
        (FACT_SEARCH, result.search_daily),
        (FACT_CANONICAL, result.canonical_dim),
        (FACT_TRENDING, result.trending_daily),
    ):
        if rows:
            p = store.write_fact_table(table, rows, snapshot_date=snap)
            print(f"  {table}: {len(rows)} rows -> {p}")
    gold = result.legacy_snapshot
    gold_path = store.write_gold(gold)
    print(f"  Wrote {len(gold)} gold rows -> {gold_path}")
    print(f"  JSON -> {store.gold_json_path()}")

    if gold:
        print("\nTop 5 trending products:")
        for i, row in enumerate(gold[:5], 1):
            print(
                f"  {i}. [{row['trend_score']:.1f}] {row['canonical_title']} "
                f"({row['trend_tier']})"
            )

    print("\nDone. Output files:")
    for p in sorted(store.root.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(store.root)} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
