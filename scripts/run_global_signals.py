#!/usr/bin/env python
"""
Global supplementary pet-trend signals: Amazon US + TikTok Shop US.

Separate from the India-native pipeline (run_local.py) by design — this
never touches the India trend_score. Writes:
    data/bronze/bronze_global_amazon_us.csv
    data/bronze/bronze_global_tiktok_shop_us.csv
    data/gold/gold_fact_global_pet_trend_signals_daily.csv
    data/gold/gold_bridge_global_to_india_pet_opportunities.csv

Usage:
    python scripts/run_global_signals.py
    python scripts/run_global_signals.py --tiktok-csv path/to/export.csv
    python scripts/run_global_signals.py --skip-amazon-us
    python scripts/run_global_signals.py --tiktok-sample      # dev-only demo CSV
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dagster_project.resources.file_store import FileStoreResource
from scrapers.amazon_global.client import AmazonUSScraper
from scrapers.tiktok_shop_global.client import TikTokShopGlobalClient
from transform.global_signals import (
    FACT_GLOBAL_BRIDGE,
    FACT_GLOBAL_SIGNALS,
    build_global_platform_daily,
    build_india_bridge,
)

BRONZE_AMAZON_US = "bronze_global_amazon_us"
BRONZE_TIKTOK_US = "bronze_global_tiktok_shop_us"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run global (US) supplementary pet-trend signals")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--skip-amazon-us", action="store_true")
    parser.add_argument("--tiktok-csv", default="", help="Path to a licensed/exported TikTok Shop CSV")
    parser.add_argument(
        "--tiktok-sample",
        action="store_true",
        help="Fall back to bundled demo TikTok sample when API/CSV unavailable (dev only)",
    )
    parser.add_argument(
        "--no-tiktok-sample",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    store = FileStoreResource(base_dir=args.data_dir)
    print(f"Data directory: {store.root.resolve()}")

    # --- Amazon US (live scrape) ---
    amazon_records = []
    if not args.skip_amazon_us:
        print("\n[1/4] Amazon US bronze (live scrape)...")
        scraper = AmazonUSScraper()
        products = scraper.fetch_all()
        amazon_records = scraper.to_global_bronze_records(products)
        if amazon_records:
            path = store.insert(BRONZE_AMAZON_US, amazon_records)
            print(f"  Fetched {len(amazon_records)} pet-filtered US products -> {path}")
        else:
            print("  WARNING: Amazon US scrape returned 0 rows")
    else:
        print("\n[1/4] Amazon US bronze... skipped")
        existing = store.read_table(BRONZE_AMAZON_US)
        if not existing.empty:
            amazon_records = existing.to_dict(orient="records")
            print(f"  Loaded {len(amazon_records)} rows from existing bronze")

    # --- TikTok Shop (API -> CSV -> demo sample) ---
    print("\n[2/4] TikTok Shop US bronze...")
    tiktok_client = TikTokShopGlobalClient(
        csv_path=args.tiktok_csv or None,
        use_sample_fallback=args.tiktok_sample and not args.no_tiktok_sample,
    )
    tiktok_products = tiktok_client.fetch_all()
    source_label = tiktok_client.fetch_source_label()
    tiktok_records = tiktok_client.to_bronze_records(tiktok_products)
    if tiktok_records:
        path = store.insert(BRONZE_TIKTOK_US, tiktok_records)
        print(f"  Loaded {len(tiktok_records)} products via {source_label} -> {path}")
        if source_label.startswith("demo_sample"):
            print(
                "  NOTE: Demo sample data — not live TikTok Shop. "
                "Set TIKTOK_SHOP_APP_KEY/SECRET/ACCESS_TOKEN for real API data, "
                "or pass --tiktok-csv with a licensed export."
            )
    else:
        print(
            "  0 TikTok Shop rows. TikTok is blocked in India; this project never scrapes "
            "tiktok.com directly. Provide Partner API credentials or --tiktok-csv."
        )

    # --- Score + build fact tables ---
    print("\n[3/4] Scoring global signals...")
    global_rows = build_global_platform_daily(amazon_records, tiktok_records)
    india_gold = store.read_gold()
    india_brands = {str(r.get("normalized_brand", "")) for r in india_gold if r.get("normalized_brand")}
    bridge_rows = build_india_bridge(global_rows, india_brands)

    print("\n[4/4] Writing gold fact tables...")
    if global_rows:
        by_source = {}
        for r in global_rows:
            by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        p1 = store.write_fact_table(FACT_GLOBAL_SIGNALS, global_rows)
        print(f"  {FACT_GLOBAL_SIGNALS}: {len(global_rows)} rows -> {p1}")
        print(f"    by source: {by_source}")
    if bridge_rows:
        p2 = store.write_fact_table(FACT_GLOBAL_BRIDGE, bridge_rows)
        print(f"  {FACT_GLOBAL_BRIDGE}: {len(bridge_rows)} rows -> {p2}")

    if bridge_rows:
        print("\nGlobal Pet Trend Watch (top 10)\n")
        for i, r in enumerate(bridge_rows[:10], start=1):
            src = "TikTok Shop US" if r["source"] == "tiktok_shop_us" else "Amazon US"
            print(f"{i}. [{src}] {r['product_title'][:65]}")
            print(f"   Category: {r['mapped_india_category']} | Score: {r['global_opportunity_score']}")
            print(f"   Bucket: {r['global_opportunity_bucket']}")
            print(f"   {r['reason']}\n")
    else:
        print("\nNo global signal rows produced.")


if __name__ == "__main__":
    main()
