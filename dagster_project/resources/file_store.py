"""
Local file storage resource — CSV + JSON instead of ClickHouse.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from scrapers.filters.pet_filter import filter_pet_records
from scrapers.flipkart.client import FlipkartScraper
from scrapers.logging_config import is_production
from dagster import ConfigurableResource

CSV_ENCODING = "utf-8-sig"


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _records_to_serializable(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: _serialize(v) for k, v in row.items()} for row in records]


def freshness_days() -> int:
    """How many days of ingest/computed dates count as fresh for health checks."""
    explicit = os.getenv("HEALTH_FRESHNESS_DAYS")
    if explicit:
        try:
            return max(1, int(explicit))
        except ValueError:
            pass
    return 1 if is_production() else 7


class FileStoreResource(ConfigurableResource):
    """Read/write pipeline data as CSV and JSON files under data/."""

    base_dir: str = "data"

    @classmethod
    def from_env(cls) -> "FileStoreResource":
        return cls(base_dir=os.getenv("DATA_DIR", "data"))

    @property
    def root(self) -> Path:
        return Path(self.base_dir)

    def bronze_csv_path(self, table: str) -> Path:
        """Prefer *_latest.csv (canonical when primary is locked by an editor)."""
        primary = self.root / "bronze" / f"{table}.csv"
        latest = primary.with_name(primary.stem + "_latest.csv")
        if latest.exists():
            return latest
        return primary

    def bronze_json_dir(self, table: str) -> Path:
        return self.root / "bronze" / table

    def gold_csv_path(self) -> Path:
        return self.root / "gold" / "gold_dim_trending_pet_products.csv"

    def gold_json_path(self) -> Path:
        return self.root / "gold" / "gold_dim_trending_pet_products.json"

    def fact_csv_path(self, table: str) -> Path:
        return self.root / "gold" / f"{table}.csv"

    def fact_json_path(self, table: str) -> Path:
        return self.root / "gold" / f"{table}.json"

    def _ensure_dirs(self, table: str) -> None:
        self.bronze_csv_path(table).parent.mkdir(parents=True, exist_ok=True)
        self.bronze_json_dir(table).mkdir(parents=True, exist_ok=True)
        self.gold_csv_path().parent.mkdir(parents=True, exist_ok=True)

    def _safe_write_csv(self, path: Path, df: pd.DataFrame) -> Path:
        """Write CSV via temp file. Falls back to *_latest.csv if target is locked."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_csv(tmp, index=False, encoding=CSV_ENCODING)
        try:
            tmp.replace(path)
            return path
        except PermissionError:
            fallback = path.with_name(path.stem + "_latest.csv")
            try:
                tmp.replace(fallback)
            except OSError:
                df.to_csv(fallback, index=False, encoding=CSV_ENCODING)
                tmp.unlink(missing_ok=True)
            return fallback

    def _write_bronze_csv(self, table: str, df: pd.DataFrame) -> Path:
        """Write canonical *_latest.csv, then mirror to primary when unlocked."""
        if df is None or df.empty:
            raise ValueError(f"Refusing to write empty bronze table: {table}")
        primary = self.root / "bronze" / f"{table}.csv"
        latest = primary.with_name(primary.stem + "_latest.csv")
        written = self._safe_write_csv(latest, df)
        if written.resolve() != primary.resolve():
            try:
                df.to_csv(primary, index=False, encoding=CSV_ENCODING)
            except PermissionError:
                pass
        return written

    def insert(self, table: str, records: List[Dict[str, Any]]) -> Path:
        """Append records to bronze CSV and save a daily JSON snapshot."""
        if not records:
            return self.bronze_csv_path(table)

        self._ensure_dirs(table)
        serializable = _records_to_serializable(records)

        # Safety net: only keep pet products in bronze tables
        if table.startswith("bronze_ecom_trends_"):
            serializable = filter_pet_records(serializable)
            if not serializable:
                return self.bronze_csv_path(table)

        new_df = pd.DataFrame(serializable)

        read_path = self.bronze_csv_path(table)
        if read_path.exists():
            existing = pd.read_csv(read_path, encoding=CSV_ENCODING)
            ingest_dates = {str(r.get("ingest_date", "")) for r in serializable}
            if "ingest_date" in existing.columns and ingest_dates:
                existing = existing[~existing["ingest_date"].astype(str).isin(ingest_dates)]
            combined = pd.concat([existing, new_df], ignore_index=True)
        else:
            combined = new_df

        # Re-filter combined data in case old rows were non-pet
        if table.startswith("bronze_ecom_trends_"):
            combined = pd.DataFrame(filter_pet_records(combined.to_dict(orient="records")))

        if table == "bronze_ecom_trends_flipkart":
            combined = pd.DataFrame(
                FlipkartScraper.dedupe_bronze_records(combined.to_dict(orient="records"))
            )

        written = self._write_bronze_csv(table, combined)

        snapshot_date = str(serializable[0].get("ingest_date", date.today()))
        json_path = self.bronze_json_dir(table) / f"{snapshot_date}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, default=str)

        return written

    def read_table(self, table: str) -> pd.DataFrame:
        path = self.bronze_csv_path(table)
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path, encoding=CSV_ENCODING)

    def read_today(self, table: str) -> List[Dict[str, Any]]:
        df = self.read_table(table)
        if df.empty or "ingest_date" not in df.columns:
            return []
        today = str(date.today())
        subset = df[df["ingest_date"].astype(str) == today]
        return subset.to_dict(orient="records")

    def count_today(self, table: str) -> int:
        return len(self.read_today(table))

    def read_recent(self, table: str, days: Optional[int] = None) -> List[Dict[str, Any]]:
        """Rows with ingest_date within the last `days` (defaults to freshness_days())."""
        window = freshness_days() if days is None else max(1, days)
        df = self.read_table(table)
        if df.empty or "ingest_date" not in df.columns:
            return []
        cutoff = str(date.today() - pd.Timedelta(days=window - 1))
        subset = df[df["ingest_date"].astype(str) >= cutoff]
        return subset.to_dict(orient="records")

    def count_recent(self, table: str, days: Optional[int] = None) -> int:
        return len(self.read_recent(table, days=days))

    def read_yesterday(self, table: str) -> List[Dict[str, Any]]:
        df = self.read_table(table)
        if df.empty or "ingest_date" not in df.columns:
            return []
        yesterday = str(date.today() - pd.Timedelta(days=1))
        subset = df[df["ingest_date"].astype(str) == yesterday]
        return subset.to_dict(orient="records")

    def write_gold(self, records: List[Dict[str, Any]]) -> Path:
        self.gold_csv_path().parent.mkdir(parents=True, exist_ok=True)
        serializable = _records_to_serializable(records)
        df = pd.DataFrame(serializable)
        self._safe_write_csv(self.gold_csv_path(), df)
        with open(self.gold_json_path(), "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, default=str)
        return self.gold_csv_path()

    def write_fact_table(
        self,
        table: str,
        records: List[Dict[str, Any]],
        snapshot_date: Optional[str] = None,
        replace_snapshot: bool = True,
    ) -> Path:
        """Append daily fact rows; replace rows for snapshot_date when replace_snapshot=True."""
        if not records:
            return self.fact_csv_path(table)
        self.fact_csv_path(table).parent.mkdir(parents=True, exist_ok=True)
        serializable = _records_to_serializable(records)
        new_df = pd.DataFrame(serializable)
        path = self.fact_csv_path(table)
        snap = snapshot_date or str(date.today())
        if path.exists():
            existing = pd.read_csv(path, encoding=CSV_ENCODING)
            if replace_snapshot and "snapshot_date" in existing.columns:
                existing = existing[existing["snapshot_date"].astype(str) != str(snap)]
            elif replace_snapshot and "last_seen_date" in existing.columns and table.endswith("canonical"):
                existing = existing[existing["last_seen_date"].astype(str) != str(snap)]
            combined = pd.concat([existing, new_df], ignore_index=True)
        else:
            combined = new_df
        self._safe_write_csv(path, combined)
        with open(self.fact_json_path(table), "w", encoding="utf-8") as f:
            json.dump(combined.to_dict(orient="records"), f, indent=2, default=str)
        return path

    def read_fact_table(self, table: str) -> pd.DataFrame:
        path = self.fact_csv_path(table)
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path, encoding=CSV_ENCODING)

    def read_gold(self) -> List[Dict[str, Any]]:
        path = self.gold_csv_path()
        if not path.exists():
            return []
        return pd.read_csv(path, encoding=CSV_ENCODING).to_dict(orient="records")

    def read_gold_today(self) -> List[Dict[str, Any]]:
        rows = self.read_gold()
        today = str(date.today())
        return [r for r in rows if str(r.get("computed_date", "")) == today]

    def read_gold_recent(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        """Gold rows within freshness window; falls back to the latest computed_date batch."""
        window = freshness_days() if days is None else max(1, days)
        rows = self.read_gold()
        if not rows:
            return []
        cutoff = str(date.today() - pd.Timedelta(days=window - 1))
        recent = [r for r in rows if str(r.get("computed_date", "")) >= cutoff]
        if recent:
            return recent
        dates = sorted(
            {str(r.get("computed_date", "")) for r in rows if r.get("computed_date")},
            reverse=True,
        )
        if dates:
            latest = dates[0]
            return [r for r in rows if str(r.get("computed_date", "")) == latest]
        return rows

    def max_ingest_ts(self, table: str) -> Optional[datetime]:
        df = self.read_table(table)
        if df.empty or "ingest_ts" not in df.columns:
            return None
        try:
            return pd.to_datetime(df["ingest_ts"]).max().to_pydatetime()
        except Exception:
            return None

    def prune_bronze(self, table: str, retain_days: int = 30) -> int:
        """Drop bronze rows older than retain_days. Returns rows removed."""
        path = self.bronze_csv_path(table)
        if not path.exists() or retain_days < 1:
            return 0
        df = pd.read_csv(path, encoding=CSV_ENCODING)
        if df.empty or "ingest_date" not in df.columns:
            return 0
        cutoff = str(date.today() - pd.Timedelta(days=retain_days))
        before = len(df)
        kept = df[df["ingest_date"].astype(str) >= cutoff]
        removed = before - len(kept)
        if removed > 0:
            self._write_bronze_csv(table, kept)
        return removed

    def health(self) -> Dict[str, Any]:
        """Lightweight readiness snapshot for ops checks."""
        tables = [
            "bronze_ecom_trends_amazon",
            "bronze_ecom_trends_gtrends",
            "bronze_ecom_trends_flipkart",
        ]
        window = freshness_days()
        status = {
            "ok": True,
            "freshness_days": window,
            "tables": {},
            "gold_rows": 0,
            "gold_today_rows": 0,
        }
        for table in tables:
            path = self.bronze_csv_path(table)
            today_count = self.count_today(table)
            recent_count = self.count_recent(table, days=window)
            max_ts = self.max_ingest_ts(table)
            status["tables"][table] = {
                "path": str(path),
                "exists": path.exists(),
                "today_rows": today_count,
                "recent_rows": recent_count,
                "max_ingest_ts": max_ts.isoformat() if max_ts else None,
            }
            if not path.exists() or recent_count == 0:
                status["ok"] = False
        gold_recent = self.read_gold_recent(days=window)
        status["gold_rows"] = len(gold_recent)
        status["gold_today_rows"] = len(self.read_gold_today())
        if not gold_recent:
            status["ok"] = False
        return status
