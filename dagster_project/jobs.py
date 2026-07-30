"""Dagster jobs for ingestion, transformation, and Slack delivery."""
from dagster import AssetSelection, OpExecutionContext, define_asset_job, job, op

from .assets import (
    amazon_bestsellers,
    flipkart_products,
    gold_trending_products,
    google_trends,
)

daily_ingestion_job = define_asset_job(
    name="daily_ingestion_job",
    selection=AssetSelection.assets(
        amazon_bestsellers,
        google_trends,
        flipkart_products,
    ),
    description="Daily bronze-layer ingestion to CSV/JSON files",
)

transformation_job = define_asset_job(
    name="transformation_job",
    selection=AssetSelection.assets(gold_trending_products),
    description="Build gold trending products from bronze CSV files",
)

full_pipeline_job = define_asset_job(
    name="full_pipeline_job",
    selection=AssetSelection.assets(
        amazon_bestsellers,
        google_trends,
        flipkart_products,
        gold_trending_products,
    ),
    description="Ingest bronze data and build gold layer in one run",
)


@op(required_resource_keys={"file_store", "slack_daily"})
def send_daily_pulse(context: OpExecutionContext) -> str:
    from notifications.formatters.digest import format_daily_pulse

    file_store = context.resources.file_store
    slack = context.resources.slack_daily

    rows = file_store.read_gold_recent()
    rows.sort(key=lambda r: float(r.get("trend_score", 0) or 0), reverse=True)
    rows = rows[:5]

    blocks = format_daily_pulse(rows)
    slack.send_blocks(blocks, text="Daily Pet Trends Pulse")
    return f"Sent daily pulse with {len(rows)} products"


@op(required_resource_keys={"file_store", "slack_weekly"})
def send_weekly_digest(context: OpExecutionContext) -> str:
    from datetime import date, timedelta

    from notifications.formatters.digest import format_weekly_digest

    file_store = context.resources.file_store
    slack = context.resources.slack_weekly

    all_gold = file_store.read_gold()
    week_ago = str(date.today() - timedelta(days=7))
    top_products = sorted(
        [r for r in all_gold if str(r.get("computed_date", "")) >= week_ago],
        key=lambda r: float(r.get("trend_score", 0) or 0),
        reverse=True,
    )[:10]

    today = str(date.today())
    by_category: dict = {}
    for r in file_store.read_gold_recent():
        cat = r.get("category", "unknown")
        by_category.setdefault(cat, []).append(float(r.get("trend_score", 0) or 0))
    category_summary = [
        {
            "category": cat,
            "product_count": len(scores),
            "avg_score": sum(scores) / len(scores) if scores else 0,
        }
        for cat, scores in by_category.items()
    ]
    category_summary.sort(key=lambda x: x["avg_score"], reverse=True)

    gtrends_df = file_store.read_table("bronze_ecom_trends_gtrends")
    rising_keywords = []
    if not gtrends_df.empty:
        subset = gtrends_df[
            (gtrends_df["ingest_date"].astype(str) >= week_ago)
            & (gtrends_df.get("is_rising", 0).fillna(0).astype(int) == 1)
        ]
        rising_keywords = subset.sort_values("rising_score", ascending=False).head(10).to_dict(
            orient="records"
        )

    blocks = format_weekly_digest(top_products, category_summary, rising_keywords)
    slack.send_blocks(blocks, text="Weekly Pet Trends Digest")
    return f"Sent weekly digest with {len(top_products)} products"


@job
def daily_pulse_job():
    send_daily_pulse()


@job
def weekly_digest_job():
    send_weekly_digest()
