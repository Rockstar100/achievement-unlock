"""
Dagster assets for ingesting Flipkart product data.
"""
import os
from datetime import datetime
from typing import Any, Dict, List

from dagster import AssetExecutionContext, Config, asset

from scrapers.flipkart import FlipkartScraper
from ..resources.file_store import FileStoreResource

TABLE = "bronze_ecom_trends_flipkart"


class FlipkartScraperConfig(Config):
    results_per_page: int = 20
    api_base_url: str = ""
    use_sample_fallback: bool = False
    skip_live_scrape: bool = False


def _allow_sample_fallback(config_flag: bool) -> bool:
    if os.getenv("ENVIRONMENT", "development").lower() in ("production", "prod"):
        return False
    return config_flag


@asset(
    description="Raw Flipkart dog/cat product data saved to CSV/JSON",
    group_name="ingestion",
    key_prefix=["bronze", "ecom_trends"],
)
def flipkart_products(
    context: AssetExecutionContext,
    file_store: FileStoreResource,
    config: FlipkartScraperConfig,
) -> None:
    api_url = config.api_base_url or os.getenv("FLIPKART_SCRAPER_URL", "http://localhost:3001")
    scraper = FlipkartScraper(api_base_url=api_url, results_per_page=config.results_per_page)
    if config.skip_live_scrape:
        if not _allow_sample_fallback(True):
            raise RuntimeError("skip_live_scrape is not allowed in production")
        context.log.info("Skipping live Flipkart scrape (skip_live_scrape=True)")
        products = _sample_products()
    else:
        products = scraper.fetch_all()
        if not products and _allow_sample_fallback(config.use_sample_fallback):
            context.log.warning("No Flipkart data scraped — using sample fallback")
            products = _sample_products()
        elif not products:
            context.log.error("Flipkart scrape returned 0 rows (no sample fallback)")

    records = scraper.to_bronze_records(products)

    if records:
        unique = _dedupe(records)
        enriched = _enrich_with_history(unique, file_store, context)
        path = file_store.insert(TABLE, enriched)
        context.add_output_metadata(
            {
                "record_count": len(enriched),
                "csv_path": str(path),
                "search_terms": len({r["search_term"] for r in enriched}),
            }
        )
        context.log.info("Wrote %d Flipkart records to %s", len(enriched), path)
    else:
        context.log.warning("No Flipkart data to write")


def _sample_products():
    from scrapers.flipkart.client import FlipkartProduct

    return [
        FlipkartProduct(
            search_term="dog food", category="dog_food", rank=1, product_id="FK_PET_DOG",
            product_title="Pedigree Adult Dry Dog Food Chicken & Vegetables 3kg",
            brand="Pedigree", price_inr=1299.0, mrp_inr=1499.0, rating=4.2, review_count=5000,
            product_url="https://www.flipkart.com/pedigree-dog-food/p/itm",
        ),
        FlipkartProduct(
            search_term="cat food", category="cat_food", rank=1, product_id="FK_PET_CAT",
            product_title="Whiskas Kitten Dry Cat Food 1.1kg",
            brand="Whiskas", price_inr=499.0, mrp_inr=549.0, rating=4.4, review_count=3200,
            product_url="https://www.flipkart.com/whiskas-cat-food/p/itm",
        ),
    ]


def _dedupe(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return FlipkartScraper.dedupe_bronze_records(records)


def _history_key(rec: Dict[str, Any]) -> Any:
    pid = FlipkartScraper.flipkart_pid(str(rec.get("product_url", "")))
    if pid:
        return ("pid", pid)
    return ("legacy", rec.get("product_id"), rec.get("search_term"))


def _enrich_with_history(
    records: List[Dict[str, Any]], file_store: FileStoreResource, context: Any
) -> List[Dict[str, Any]]:
    prev_rows = file_store.read_yesterday(TABLE)
    if not prev_rows:
        return records

    prev_map = {
        _history_key(r): r
        for r in prev_rows
    }

    for rec in records:
        key = _history_key(rec)
        if key in prev_map:
            prev = prev_map[key]
            rec["rank_prev_day"] = int(prev.get("rank", rec["rank"]))
            rec["rank_delta"] = int(prev.get("rank", rec["rank"])) - int(rec["rank"])
            rec["rating_prev_day"] = float(prev.get("rating", rec["rating"]))
            rec["rating_delta"] = float(rec["rating"]) - float(prev.get("rating", rec["rating"]))
            rec["review_count_prev_day"] = int(prev.get("review_count", rec["review_count"]))

    return records
