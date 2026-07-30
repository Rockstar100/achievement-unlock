#!/usr/bin/env python
"""Serve a local data-checker dashboard (gold + bronze)."""
from __future__ import annotations

import json
import math
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
sys.path.insert(0, str(ROOT))

from dagster_project.resources.file_store import FileStoreResource


def get_store() -> FileStoreResource:
    return FileStoreResource(base_dir=os.getenv("DATA_DIR", "data"))


def _sanitize_value(value):
    """Make pandas/numpy values safe for strict JSON (no NaN/Infinity)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    return value


def _sanitize_records(records: list[dict]) -> list[dict]:
    return [_sanitize_value(row) for row in records]


def _json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    clean = _sanitize_value(payload)
    body = json.dumps(clean, default=str, allow_nan=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _read_gold_rows(store: FileStoreResource) -> list[dict]:
    """Gold snapshot sorted by trend_score (recalculated rank for display)."""
    rows = _sanitize_records(store.read_gold())
    rows.sort(key=lambda r: (-float(r.get("trend_score") or 0), str(r.get("canonical_title", ""))))
    for i, row in enumerate(rows, start=1):
        row["rank_position"] = i
        if not row.get("reason_codes"):
            row["reason_codes"] = ""
        if not row.get("recommended_action"):
            row["recommended_action"] = "IGNORE"
    return rows


def _read_bronze_rows(store: FileStoreResource, table: str) -> list[dict]:
    df = store.read_table(table)
    if df.empty:
        return []
    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    return _sanitize_records(records)


def _is_live_global_row(row: dict) -> bool:
    """Exclude bundled demo TikTok sample rows and placeholder images."""
    source = str(row.get("source") or "")
    pid = str(row.get("product_id") or "")
    img = str(row.get("image_url") or "")
    if "placehold.co" in img:
        return False
    if source == "tiktok_shop_us" and pid.startswith("tt_us_"):
        return False
    if source == "tiktok_shop_us" and str(row.get("fetch_method") or "") == "csv_import":
        return False
    return True


def _read_global_products(store: FileStoreResource) -> list[dict]:
    """US market products with images — live Amazon US (+ TikTok when credentialed)."""
    signals_df = store.read_fact_table("gold_fact_global_pet_trend_signals_daily")
    bridge_df = store.read_fact_table("gold_bridge_global_to_india_pet_opportunities")
    signals = _sanitize_records(signals_df.to_dict(orient="records") if not signals_df.empty else [])
    bridge = _sanitize_records(bridge_df.to_dict(orient="records") if not bridge_df.empty else [])

    if signals:
        latest_snap = max(str(r.get("snapshot_date") or "") for r in signals)
        signals = [r for r in signals if str(r.get("snapshot_date") or "") == latest_snap]
        bridge = [r for r in bridge if str(r.get("snapshot_date") or "") == latest_snap]

    bridge_by_key = {
        f"{b.get('source')}:{b.get('product_id')}": b
        for b in bridge
        if _is_live_global_row(b)
    }

    products = [r for r in signals if _is_live_global_row(r)]
    for row in products:
        bridge_row = bridge_by_key.get(f"{row.get('source')}:{row.get('product_id')}")
        if bridge_row:
            row["global_opportunity_score"] = bridge_row.get("global_opportunity_score")
            row["global_opportunity_bucket"] = bridge_row.get("global_opportunity_bucket")
            row["reason"] = bridge_row.get("reason")
            row["india_brand_match"] = bridge_row.get("india_brand_match")
            row["mapped_india_category"] = bridge_row.get("mapped_india_category") or row.get("category")

    products.sort(
        key=lambda r: (
            -float(r.get("global_signal_score") or 0),
            str(r.get("product_title") or ""),
        )
    )
    for i, row in enumerate(products, start=1):
        row["rank_position"] = i
    return products


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        if args and str(args[1]).startswith("2"):
            return
        super().log_message(fmt, *args)

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path.startswith("/api/"):
            self._handle_api(path)
            return

        if path in ("/", ""):
            path = "/index.html"

        file_path = (FRONTEND / path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(FRONTEND.resolve())):
            self.send_error(403)
            return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return

        content = file_path.read_bytes()
        ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_api(self, path: str) -> None:
        store = get_store()
        try:
            if path == "/api/gold":
                rows = _read_gold_rows(store)
                computed = rows[0].get("computed_ts") if rows else None
                _json_response(self, {"count": len(rows), "rows": rows, "computed_ts": computed})
            elif path == "/api/bronze/amazon":
                rows = _read_bronze_rows(store, "bronze_ecom_trends_amazon")
                _json_response(self, {"count": len(rows), "rows": rows})
            elif path == "/api/bronze/flipkart":
                rows = _read_bronze_rows(store, "bronze_ecom_trends_flipkart")
                _json_response(self, {"count": len(rows), "rows": rows})
            elif path == "/api/bronze/gtrends":
                rows = _read_bronze_rows(store, "bronze_ecom_trends_gtrends")
                _json_response(self, {"count": len(rows), "rows": rows})
            elif path == "/api/facts/trending":
                df = store.read_fact_table("gold_fact_trending_pet_products_daily")
                rows = _sanitize_records(df.to_dict(orient="records") if not df.empty else [])
                rows.sort(key=lambda r: (-float(r.get("trend_score") or 0), str(r.get("canonical_title", ""))))
                for i, row in enumerate(rows, start=1):
                    row["rank_position"] = i
                _json_response(self, {"count": len(rows), "rows": rows})
            elif path == "/api/facts/platform":
                df = store.read_fact_table("gold_fact_product_platform_daily")
                rows = _sanitize_records(df.to_dict(orient="records") if not df.empty else [])
                _json_response(self, {"count": len(rows), "rows": rows})
            elif path == "/api/global":
                products = _read_global_products(store)
                computed = products[0].get("computed_ts") if products else None
                _json_response(
                    self,
                    {
                        "count": len(products),
                        "rows": products,
                        "computed_ts": computed,
                        "sources": {
                            "amazon_us": sum(1 for s in products if s.get("source") == "amazon_us"),
                            "tiktok_shop_us": sum(1 for s in products if s.get("source") == "tiktok_shop_us"),
                        },
                    },
                )
            elif path == "/api/summary":
                gold = _read_gold_rows(store)
                fact_trend = store.read_fact_table("gold_fact_trending_pet_products_daily")
                fact_plat = store.read_fact_table("gold_fact_product_platform_daily")
                actions: dict = {}
                tiers: dict = {}
                scores = []
                for r in gold:
                    act = str(r.get("recommended_action") or "IGNORE")
                    actions[act] = actions.get(act, 0) + 1
                    tier = str(r.get("trend_tier") or "unknown")
                    tiers[tier] = tiers.get(tier, 0) + 1
                    try:
                        scores.append(float(r.get("trend_score") or 0))
                    except (TypeError, ValueError):
                        pass
                _json_response(
                    self,
                    {
                        "gold_rows": len(gold),
                        "fact_trending_rows": len(fact_trend),
                        "fact_platform_rows": len(fact_plat),
                        "actions": actions,
                        "tiers": tiers,
                        "max_score": max(scores) if scores else 0,
                        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
                        "with_reason_codes": sum(
                            1 for r in gold if str(r.get("reason_codes") or "").strip()
                        ),
                    },
                )
            elif path == "/api/health":
                from dagster_project.resources.file_store import freshness_days
                from scrapers.filters.pet_filter import is_pet_product

                report: dict = {
                    "environment": os.getenv("ENVIRONMENT", "development"),
                    "checks": [],
                    "ok": True,
                    "freshness_days": freshness_days(),
                }
                health = store.health()
                report["data"] = health
                for table, meta in health["tables"].items():
                    report["checks"].append(
                        {"name": f"bronze:{table}:exists", "passed": meta["exists"], "detail": meta["path"]}
                    )
                    recent = meta.get("recent_rows", 0)
                    report["checks"].append(
                        {
                            "name": f"bronze:{table}:recent_rows",
                            "passed": recent > 0,
                            "detail": f"recent={recent}",
                        }
                    )
                report["checks"].append(
                    {
                        "name": "gold:recent_rows",
                        "passed": health["gold_rows"] > 0,
                        "detail": str(health["gold_rows"]),
                    }
                )
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
                report["checks"].append(
                    {"name": "amazon:dog_cat_only", "passed": len(bad) == 0, "detail": f"bad={len(bad)}"}
                )
                report["ok"] = all(c["passed"] for c in report["checks"])
                _json_response(self, report)
            else:
                self.send_error(404)
        except Exception as exc:
            _json_response(self, {"error": str(exc)}, status=500)


def main() -> int:
    # Render injects PORT; local dev uses DASHBOARD_PORT
    port = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "8765")))
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
    # ThreadingHTTPServer allows address reuse; avoid stacking duplicate listeners
    class ReuseHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = True

    server = ReuseHTTPServer((host, port), DashboardHandler)
    print(f"Pet Trends dashboard: http://{host}:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
