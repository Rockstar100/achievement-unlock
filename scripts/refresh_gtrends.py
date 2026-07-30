#!/usr/bin/env python
"""Live Google Trends refresh for dog/cat keywords."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dagster_project.resources.file_store import FileStoreResource
from scrapers.gtrends import GTrendsClient
from scrapers.logging_config import setup_logging
from transform.gold_builder import build_gold_from_bronze


def main() -> int:
    log = setup_logging("refresh_gtrends")
    client = GTrendsClient(request_delay=2.5, fetch_related=True)
    records = client.fetch_all()
    bronze = client.to_bronze_records(records)
    if not bronze:
        log.error("No GTrends records returned")
        return 1

    store = FileStoreResource(base_dir="data")
    path = store.insert("bronze_ecom_trends_gtrends", bronze)
    print(f"Wrote {len(bronze)} rows -> {path}")

    interest = [r for r in bronze if not r.get("rising_query")]
    interest.sort(key=lambda r: int(r.get("interest_score") or 0), reverse=True)
    print("\nTop interest keywords (India, 7d):")
    for r in interest[:15]:
        print(
            f"  {r['interest_score']:3d}  avg={r['interest_avg_7d']:3d}  "
            f"d={r['interest_delta']:+3d}  {r['category']:16s}  {r['keyword']}"
        )

    rising = [r for r in bronze if r.get("rising_query")]
    print(f"\nRising queries: {len(rising)}")
    for r in rising[:10]:
        print(f"  +{r['rising_score']:<5} {r['rising_query']}  [{r['category']}]")

    gold = build_gold_from_bronze(
        store.read_table("bronze_ecom_trends_amazon"),
        store.read_table("bronze_ecom_trends_gtrends"),
        store.read_table("bronze_ecom_trends_flipkart"),
    )
    if gold:
        store.write_gold(gold)
        print(f"\nGold rebuilt: {len(gold)} products")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
