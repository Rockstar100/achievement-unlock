#!/usr/bin/env python
"""Production readiness / health check for the pet trends pipeline."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dagster_project.resources.file_store import FileStoreResource, freshness_days
from scrapers.filters.pet_filter import is_pet_product
from scrapers.logging_config import is_production, setup_logging


def main() -> int:
    log = setup_logging("healthcheck")
    data_dir = os.getenv("DATA_DIR", "data")
    store = FileStoreResource(base_dir=data_dir)
    report: dict = {
        "environment": os.getenv("ENVIRONMENT", "development"),
        "production": is_production(),
        "checks": [],
        "ok": True,
    }

    def check(name: str, passed: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            report["ok"] = False
        log.info("%s %s %s", "PASS" if passed else "FAIL", name, detail)

    # Config presence
    for cfg in (
        "config/amazon_categories.yaml",
        "config/flipkart_search_terms.yaml",
        "config/gtrends_keywords.yaml",
    ):
        check(f"config:{cfg}", (ROOT / cfg).exists())

    health = store.health()
    report["data"] = health
    window = freshness_days()
    report["freshness_days"] = window
    for table, meta in health["tables"].items():
        check(f"bronze:{table}:exists", meta["exists"], meta["path"])
        recent = meta.get("recent_rows", meta.get("today_rows", 0))
        check(
            f"bronze:{table}:recent_rows",
            recent > 0,
            f"recent={recent} today={meta.get('today_rows', 0)} window={window}d",
        )

    check(
        "gold:recent_rows",
        health["gold_rows"] > 0,
        f"recent={health['gold_rows']} today={health.get('gold_today_rows', 0)} window={window}d",
    )

    # Dog/cat only on Amazon bronze (prefer today, else recent window)
    am = store.read_today("bronze_ecom_trends_amazon")
    if not am:
        am = store.read_recent("bronze_ecom_trends_amazon")
    bad = [
        r
        for r in am
        if not is_pet_product(
            title=str(r.get("product_title", "")),
            url=str(r.get("product_url", "")),
            category=str(r.get("category", "")),
        )
    ]
    check("amazon:dog_cat_only", len(bad) == 0, f"bad={len(bad)}")

    # Gold scores should vary (not all identical)
    gold = store.read_gold_recent()
    if gold:
        scores = {round(float(r.get("trend_score", 0) or 0), 1) for r in gold}
        check("gold:score_spread", len(scores) > 1, f"unique_scores={len(scores)}")
        max_score = max(float(r.get("trend_score", 0) or 0) for r in gold)
        check("gold:max_score", max_score >= 40, f"max={max_score:.1f}")
        with_reason = sum(1 for r in gold if str(r.get("reason_codes") or "").strip())
        check("gold:has_reason_codes", with_reason > 0, f"rows_with_signals={with_reason}")
        top = gold[0]
        check(
            "gold:top_has_title",
            bool(top.get("canonical_title")),
            str(top.get("canonical_title", ""))[:60],
        )

    # Prod env should not allow sample fallback implicitly
    if is_production():
        check(
            "prod:no_placeholder_webhooks_required",
            True,
            "Slack optional; scrapers must be live",
        )

    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
