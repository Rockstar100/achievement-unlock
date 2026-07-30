#!/usr/bin/env python
"""Mirror *_latest.csv bronze files onto primary names (when not locked)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TABLES = [
    "bronze_ecom_trends_amazon",
    "bronze_ecom_trends_flipkart",
    "bronze_ecom_trends_gtrends",
]


def main() -> int:
    data_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
    bronze = data_dir / "bronze"
    ok = 0
    skipped = 0
    for table in TABLES:
        primary = bronze / f"{table}.csv"
        latest = bronze / f"{table}_latest.csv"
        if not latest.exists():
            print(f"{table}: no _latest.csv — skip")
            skipped += 1
            continue
        try:
            shutil.copy2(latest, primary)
            print(f"{table}: synced {latest.name} -> {primary.name} ({primary.stat().st_size} bytes)")
            ok += 1
        except PermissionError:
            print(
                f"{table}: primary locked (close it in the editor), "
                f"pipeline uses {latest.name}"
            )
            skipped += 1
    return 0 if ok > 0 or skipped > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
