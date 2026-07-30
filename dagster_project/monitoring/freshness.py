"""Monitoring utilities for file-based pipeline."""
from datetime import datetime
from typing import Any, Dict, List

import yaml
from pathlib import Path


def load_alerting_config() -> Dict[str, Any]:
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
    with open(config_path, encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    return settings.get("alerting", {})


def check_data_freshness(file_store, table: str, max_hours: int = 25) -> Dict[str, Any]:
    last_ingest = file_store.max_ingest_ts(table)
    if not last_ingest:
        return {"table": table, "fresh": False, "reason": "no data"}

    age_hours = (datetime.now() - last_ingest).total_seconds() / 3600
    return {
        "table": table,
        "fresh": age_hours <= max_hours,
        "last_ingest": str(last_ingest),
        "age_hours": round(age_hours, 1),
        "max_hours": max_hours,
    }


def run_all_freshness_checks(file_store) -> List[Dict[str, Any]]:
    config = load_alerting_config()
    max_hours = int(config.get("data_freshness_max_hours", 25))
    tables = [
        "bronze_ecom_trends_amazon",
        "bronze_ecom_trends_gtrends",
        "bronze_ecom_trends_flipkart",
    ]
    return [check_data_freshness(file_store, t, max_hours) for t in tables]
