"""
Dagster assets for ingesting Amazon.in Pet Supplies data.
"""
from datetime import datetime

from dagster import AssetExecutionContext, Config, asset

from scrapers.amazon import AmazonScraper
from ..resources.file_store import FileStoreResource

TABLE = "bronze_ecom_trends_amazon"


class AmazonScraperConfig(Config):
    marketplace: str = "in"
    use_sample_fallback: bool = False
    skip_live_scrape: bool = False


def _allow_sample_fallback(config_flag: bool) -> bool:
    import os

    if os.getenv("ENVIRONMENT", "development").lower() in ("production", "prod"):
        return False
    return config_flag


@asset(
    description="Raw Amazon.in dog/cat bestsellers saved to CSV/JSON",
    group_name="ingestion",
    key_prefix=["bronze", "ecom_trends"],
)
def amazon_bestsellers(
    context: AssetExecutionContext,
    file_store: FileStoreResource,
    config: AmazonScraperConfig,
) -> None:
    scraper = AmazonScraper(marketplace=config.marketplace)
    if config.skip_live_scrape:
        if not _allow_sample_fallback(True):
            raise RuntimeError("skip_live_scrape is not allowed in production")
        context.log.info("Skipping live Amazon scrape (skip_live_scrape=True)")
        products = _sample_products()
    else:
        products = scraper.fetch_all()
        if not products and _allow_sample_fallback(config.use_sample_fallback):
            context.log.warning("No Amazon pet data scraped — using sample fallback")
            products = _sample_products()
        elif not products:
            context.log.error("Amazon scrape returned 0 rows (no sample fallback)")

    records = scraper.to_bronze_records(products) if products else []

    if records:
        path = file_store.insert(TABLE, records)
        context.add_output_metadata(
            {
                "record_count": len(records),
                "csv_path": str(path),
                "ingest_date": str(datetime.now().date()),
            }
        )
        context.log.info("Wrote %d pet Amazon records to %s", len(records), path)
    else:
        context.log.warning("No pet Amazon data to write")


def _sample_products():
    from scrapers.amazon.client import AmazonProduct

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
