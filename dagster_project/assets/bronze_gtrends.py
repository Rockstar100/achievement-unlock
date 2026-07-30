"""
Dagster assets for ingesting Google Trends data.
"""
from dagster import AssetExecutionContext, Config, asset

from scrapers.trends import get_trends_provider
from ..resources.file_store import FileStoreResource

TABLE = "bronze_ecom_trends_gtrends"


class GTrendsConfig(Config):
    geo: str = "IN"
    timeframe: str = "now 7-d"
    use_sample_fallback: bool = False
    skip_live_scrape: bool = False


def _allow_sample_fallback(config_flag: bool) -> bool:
    import os

    if os.getenv("ENVIRONMENT", "development").lower() in ("production", "prod"):
        return False
    return config_flag


@asset(
    description="Raw Google Trends dog/cat data saved to CSV/JSON",
    group_name="ingestion",
    key_prefix=["bronze", "ecom_trends"],
)
def google_trends(
    context: AssetExecutionContext,
    file_store: FileStoreResource,
    config: GTrendsConfig,
) -> None:
    if config.skip_live_scrape:
        if not _allow_sample_fallback(True):
            raise RuntimeError("skip_live_scrape is not allowed in production")
        context.log.info("Skipping live GTrends fetch (skip_live_scrape=True)")
        records = _sample_gtrends_records()
    else:
        provider = get_trends_provider(geo=config.geo, timeframe=config.timeframe)
        records_raw = provider.fetch_all()
        records = provider.to_bronze_records(records_raw)
        if not records and _allow_sample_fallback(config.use_sample_fallback):
            context.log.warning("No GTrends data — using sample fallback")
            records = _sample_gtrends_records()
        elif not records:
            context.log.error("GTrends fetch returned 0 rows (no sample fallback)")

    if records:
        unique = _dedupe(records)
        path = file_store.insert(TABLE, unique)
        context.add_output_metadata(
            {
                "record_count": len(unique),
                "csv_path": str(path),
                "rising_count": sum(1 for r in unique if r.get("is_rising")),
            }
        )
        context.log.info("Wrote %d Google Trends records to %s", len(unique), path)
    else:
        context.log.warning("No Google Trends data to write")


def _sample_gtrends_records():
    from datetime import datetime

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


def _dedupe(records):
    seen = set()
    result = []
    for rec in reversed(records):
        key = (str(rec["ingest_date"]), rec["category"], rec["keyword"])
        if key not in seen:
            seen.add(key)
            result.append(rec)
    result.reverse()
    return result
