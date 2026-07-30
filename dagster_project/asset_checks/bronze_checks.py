"""Data quality asset checks for bronze file storage."""
from datetime import date

from dagster import AssetCheckExecutionContext, AssetCheckResult, AssetCheckSeverity, asset_check

from ..assets.bronze_amazon import amazon_bestsellers
from ..assets.bronze_flipkart import flipkart_products
from ..assets.bronze_gtrends import google_trends

AMAZON_TABLE = "bronze_ecom_trends_amazon"
GTRENDS_TABLE = "bronze_ecom_trends_gtrends"
FLIPKART_TABLE = "bronze_ecom_trends_flipkart"


@asset_check(
    asset=amazon_bestsellers,
    description="Amazon bronze has rows for today",
    required_resource_keys={"file_store"},
)
def amazon_bronze_not_empty(context: AssetCheckExecutionContext) -> AssetCheckResult:
    count = context.resources.file_store.count_today(AMAZON_TABLE)
    passed = count > 0
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        metadata={"row_count": count, "ingest_date": str(date.today())},
        description=f"Amazon bronze row count: {count}",
    )


@asset_check(
    asset=amazon_bestsellers,
    description="Amazon ranks are within valid range",
    required_resource_keys={"file_store"},
)
def amazon_rank_valid(context: AssetCheckExecutionContext) -> AssetCheckResult:
    rows = context.resources.file_store.read_today(AMAZON_TABLE)
    invalid = sum(1 for r in rows if int(r.get("rank", 0) or 0) < 1 or int(r.get("rank", 0) or 0) > 500)
    return AssetCheckResult(
        passed=invalid == 0,
        metadata={"invalid_rank_count": invalid},
        description=f"Invalid Amazon ranks: {invalid}",
    )


@asset_check(
    asset=google_trends,
    description="Google Trends bronze has rows for today",
    required_resource_keys={"file_store"},
)
def gtrends_bronze_not_empty(context: AssetCheckExecutionContext) -> AssetCheckResult:
    count = context.resources.file_store.count_today(GTRENDS_TABLE)
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR if count == 0 else AssetCheckSeverity.WARN,
        metadata={"row_count": count},
    )


@asset_check(
    asset=google_trends,
    description="Interest scores are 0-100",
    required_resource_keys={"file_store"},
)
def gtrends_score_valid(context: AssetCheckExecutionContext) -> AssetCheckResult:
    rows = context.resources.file_store.read_today(GTRENDS_TABLE)
    invalid = 0
    for r in rows:
        if int(r.get("is_rising", 0) or 0) == 1:
            continue
        for field in ("interest_score", "interest_avg_7d", "interest_peak_7d"):
            if field not in r or r.get(field) in (None, ""):
                continue
            val = float(r.get(field) or 0)
            if val < 0 or val > 100:
                invalid += 1
                break
    return AssetCheckResult(passed=invalid == 0, metadata={"invalid_score_count": invalid})


@asset_check(
    asset=flipkart_products,
    description="Flipkart bronze has rows for today",
    required_resource_keys={"file_store"},
)
def flipkart_bronze_not_empty(context: AssetCheckExecutionContext) -> AssetCheckResult:
    count = context.resources.file_store.count_today(FLIPKART_TABLE)
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR if count == 0 else AssetCheckSeverity.WARN,
        metadata={"row_count": count},
    )


@asset_check(
    asset=flipkart_products,
    description="Flipkart ranks are 1-100",
    required_resource_keys={"file_store"},
)
def flipkart_rank_valid(context: AssetCheckExecutionContext) -> AssetCheckResult:
    rows = context.resources.file_store.read_today(FLIPKART_TABLE)
    invalid = sum(1 for r in rows if int(r.get("rank", 0) or 0) < 1 or int(r.get("rank", 0) or 0) > 100)
    return AssetCheckResult(passed=invalid == 0, metadata={"invalid_rank_count": invalid})


@asset_check(
    asset=amazon_bestsellers,
    description="Amazon rows are dog/cat products only",
    required_resource_keys={"file_store"},
)
def amazon_dog_cat_only(context: AssetCheckExecutionContext) -> AssetCheckResult:
    from scrapers.filters.pet_filter import is_pet_product

    rows = context.resources.file_store.read_today(AMAZON_TABLE)
    bad = [
        r
        for r in rows
        if not is_pet_product(
            title=str(r.get("product_title", "")),
            url=str(r.get("product_url", "")),
            category=str(r.get("category", "")),
        )
    ]
    return AssetCheckResult(
        passed=len(bad) == 0,
        severity=AssetCheckSeverity.ERROR if bad else AssetCheckSeverity.WARN,
        metadata={"non_dog_cat_count": len(bad)},
        description=f"Non dog/cat Amazon rows: {len(bad)}",
    )
