#!/usr/bin/env python
"""Remove stale non-pet bronze data and rebuild gold layer."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dagster_project.resources.file_store import CSV_ENCODING, FileStoreResource
from scrapers.filters.pet_filter import filter_pet_records, is_pet_product
from scrapers.flipkart.client import FlipkartScraper
from transform.pipeline import FACT_CANONICAL, FACT_PLATFORM, FACT_SEARCH, FACT_TRENDING, run_daily_pipeline


def main():
    data_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
    store = FileStoreResource(base_dir=str(data_dir))

    tables = [
        "bronze_ecom_trends_amazon",
        "bronze_ecom_trends_flipkart",
        "bronze_ecom_trends_gtrends",
    ]

    for table in tables:
        path = store.bronze_csv_path(table)
        if not path.exists():
            continue
        import pandas as pd
        df = pd.read_csv(path, encoding=CSV_ENCODING)
        before = len(df)
        records = filter_pet_records(df.to_dict(orient="records"))
        if table == "bronze_ecom_trends_flipkart":
            before_dedupe = len(records)
            records = FlipkartScraper.dedupe_bronze_records(records)
            if len(records) < before_dedupe:
                print(f"{table}: deduped {before_dedupe - len(records)} repeated listings")
        after = len(records)
        if after == 0 and before > 0:
            print(
                f"{table}: REFUSING to wipe {before} rows "
                f"(filter removed everything) — file left unchanged"
            )
            continue
        if after < before:
            print(f"{table}: removed {before - after} non-pet rows ({before} -> {after})")
            written = store._write_bronze_csv(table, pd.DataFrame(records))
            print(f"  wrote {written}")
        else:
            print(f"{table}: {after} rows (all pet or empty)")

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
            store.write_fact_table(table, rows, snapshot_date=snap)
    gold = result.legacy_snapshot
    if gold:
        store.write_gold(gold)
        print(f"Gold: {len(gold)} pet products written")
        for table, rows in (
            (FACT_PLATFORM, result.platform_daily),
            (FACT_SEARCH, result.search_daily),
            (FACT_CANONICAL, result.canonical_dim),
            (FACT_TRENDING, result.trending_daily),
        ):
            if rows:
                print(f"  {table}: {len(rows)} rows")
    else:
        print("Gold: no pet products — run pipeline with sample data:")
        print("  python scripts/run_local.py --skip-scrape")


if __name__ == "__main__":
    main()
