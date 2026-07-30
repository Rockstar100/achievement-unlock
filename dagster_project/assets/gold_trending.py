"""Gold layer asset — daily facts + legacy snapshot from bronze CSV files."""
from dagster import AssetExecutionContext, asset

from transform.pipeline import (
    FACT_CANONICAL,
    FACT_PLATFORM,
    FACT_SEARCH,
    FACT_TRENDING,
    run_daily_pipeline,
)
from .bronze_amazon import amazon_bestsellers
from .bronze_flipkart import flipkart_products
from .bronze_gtrends import google_trends
from ..resources.file_store import FileStoreResource

AMAZON_TABLE = "bronze_ecom_trends_amazon"
GTRENDS_TABLE = "bronze_ecom_trends_gtrends"
FLIPKART_TABLE = "bronze_ecom_trends_flipkart"


@asset(
    description="Gold trending pet products — daily facts + legacy snapshot",
    group_name="transformation",
    deps=[amazon_bestsellers, google_trends, flipkart_products],
)
def gold_trending_products(
    context: AssetExecutionContext,
    file_store: FileStoreResource,
) -> None:
    amazon_df = file_store.read_table(AMAZON_TABLE)
    gtrends_df = file_store.read_table(GTRENDS_TABLE)
    flipkart_df = file_store.read_table(FLIPKART_TABLE)
    hist_trending = file_store.read_fact_table(FACT_TRENDING)

    result = run_daily_pipeline(
        amazon_df, gtrends_df, flipkart_df, historical_trending=hist_trending
    )
    snap = result.snapshot_date

    for table, rows in (
        (FACT_PLATFORM, result.platform_daily),
        (FACT_SEARCH, result.search_daily),
        (FACT_CANONICAL, result.canonical_dim),
        (FACT_TRENDING, result.trending_daily),
    ):
        if rows:
            p = file_store.write_fact_table(table, rows, snapshot_date=snap)
            context.log.info("Wrote %d rows to %s", len(rows), p)

    gold_records = result.legacy_snapshot

    for table in (AMAZON_TABLE, GTRENDS_TABLE, FLIPKART_TABLE):
        removed = file_store.prune_bronze(table, retain_days=30)
        if removed:
            context.log.info("Pruned %d old rows from %s", removed, table)

    if gold_records:
        path = file_store.write_gold(gold_records)
        tiers = {}
        actions = {}
        for r in gold_records:
            tiers[r.get("trend_tier", "unknown")] = tiers.get(r.get("trend_tier", "unknown"), 0) + 1
            act = r.get("recommended_action", "IGNORE")
            actions[act] = actions.get(act, 0) + 1
        context.add_output_metadata(
            {
                "record_count": len(gold_records),
                "csv_path": str(path),
                "json_path": str(file_store.gold_json_path()),
                "top_score": gold_records[0].get("trend_score"),
                "top_title": gold_records[0].get("canonical_title", "")[:80],
                "top_reason_codes": gold_records[0].get("reason_codes", ""),
                "tiers": tiers,
                "recommended_actions": actions,
                "platform_fact_rows": len(result.platform_daily),
                "trending_fact_rows": len(result.trending_daily),
            }
        )
        context.log.info("Wrote %d gold records to %s", len(gold_records), path)
    else:
        context.log.warning("No gold records produced")
