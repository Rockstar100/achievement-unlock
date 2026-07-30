"""Gold layer asset checks."""
from dagster import AssetCheckResult, asset_check

from transform.pipeline import FACT_TRENDING
from ..assets.gold_trending import gold_trending_products
from ..resources.file_store import FileStoreResource


@asset_check(asset=gold_trending_products, description="Gold snapshot has rows for today")
def gold_has_today_rows(file_store: FileStoreResource) -> AssetCheckResult:
    rows = file_store.read_gold_today()
    passed = len(rows) > 0
    return AssetCheckResult(
        passed=passed,
        metadata={"gold_today_rows": len(rows)},
        description="At least one gold row with computed_date=today",
    )


@asset_check(asset=gold_trending_products, description="Trending facts include reason codes")
def gold_has_reason_codes(file_store: FileStoreResource) -> AssetCheckResult:
    df = file_store.read_fact_table(FACT_TRENDING)
    if df.empty:
        return AssetCheckResult(passed=False, metadata={"fact_rows": 0})
    today = str(__import__("datetime").date.today())
    subset = df[df["snapshot_date"].astype(str) == today] if "snapshot_date" in df.columns else df
    with_reason = 0
    if not subset.empty and "reason_codes" in subset.columns:
        with_reason = int(subset["reason_codes"].fillna("").astype(str).str.len().gt(0).sum())
    passed = with_reason > 0 or len(subset) == 0
    return AssetCheckResult(
        passed=passed,
        metadata={"fact_rows_today": len(subset), "rows_with_reason_codes": with_reason},
    )


@asset_check(asset=gold_trending_products, description="No duplicate canonical IDs in today's trending facts")
def gold_no_duplicate_canonical_ids(file_store: FileStoreResource) -> AssetCheckResult:
    df = file_store.read_fact_table(FACT_TRENDING)
    if df.empty or "canonical_product_id" not in df.columns:
        return AssetCheckResult(passed=True, metadata={"fact_rows": 0})
    today = str(__import__("datetime").date.today())
    subset = df[df["snapshot_date"].astype(str) == today] if "snapshot_date" in df.columns else df
    dupes = int(subset.duplicated(subset=["canonical_product_id"]).sum()) if not subset.empty else 0
    return AssetCheckResult(
        passed=dupes == 0,
        metadata={"duplicate_canonical_ids": dupes, "fact_rows_today": len(subset)},
    )
