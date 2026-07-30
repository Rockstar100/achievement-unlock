"""
TikTok Shop Partner/Open API client.

Requires a TikTok Shop Partner Center app (https://partner.tiktokshop.com/doc)
with product-search scope, configured via env vars:

    TIKTOK_SHOP_APP_KEY
    TIKTOK_SHOP_APP_SECRET
    TIKTOK_SHOP_ACCESS_TOKEN
    TIKTOK_SHOP_SHOP_CIPHER      (per-shop identifier from your Partner Center app)

Without those, `is_configured()` is False and `search()` returns an empty
list — this is intentional so the rest of the pipeline can call this
unconditionally.

This implements TikTok Shop's documented request-signing scheme (HMAC-SHA256
over sorted query params, per their Partner Center API reference). Endpoint
paths follow the 202309 product-search API version at time of writing —
verify against the current Partner Center docs before relying on this in
production, since TikTok revises API versions periodically.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

TIKTOK_SHOP_API_BASE = "https://open-api.tiktokglobalshop.com"


class TikTokShopAPIClient:
    """Official TikTok Shop Partner API — product search."""

    def __init__(
        self,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        shop_cipher: Optional[str] = None,
        request_delay: float = 1.0,
    ):
        self.app_key = app_key or os.getenv("TIKTOK_SHOP_APP_KEY", "")
        self.app_secret = app_secret or os.getenv("TIKTOK_SHOP_APP_SECRET", "")
        self.access_token = access_token or os.getenv("TIKTOK_SHOP_ACCESS_TOKEN", "")
        self.shop_cipher = shop_cipher or os.getenv("TIKTOK_SHOP_SHOP_CIPHER", "")
        self.request_delay = request_delay
        self.session = requests.Session()

    def is_configured(self) -> bool:
        return bool(self.app_key and self.app_secret and self.access_token)

    def _sign(self, path: str, params: Dict[str, str], body: str = "") -> str:
        """HMAC-SHA256 signature per TikTok Shop's request-signing scheme."""
        base = path
        for key in sorted(params):
            base += f"{key}{params[key]}"
        base = f"{self.app_secret}{base}{body}{self.app_secret}"
        return hmac.new(
            self.app_secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def search(self, keyword: str, category: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search TikTok Shop products by keyword. Empty list if unconfigured."""
        if not self.is_configured():
            logger.debug("TikTok Shop API not configured — skipping (no credentials)")
            return []

        path = "/product/202309/products/search"
        timestamp = str(int(time.time()))
        params = {
            "app_key": self.app_key,
            "access_token": self.access_token,
            "timestamp": timestamp,
        }
        if self.shop_cipher:
            params["shop_cipher"] = self.shop_cipher
        body = {"keyword": keyword, "page_size": min(limit, 50)}
        import json as _json

        body_str = _json.dumps(body, separators=(",", ":"), sort_keys=True)
        params["sign"] = self._sign(path, params, body_str)

        try:
            resp = self.session.post(
                f"{TIKTOK_SHOP_API_BASE}{path}",
                params=params,
                json=body,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") not in (0, None):
                logger.warning("TikTok Shop API error for %r: %s", keyword, data.get("message"))
                return []
            products = (data.get("data") or {}).get("products", [])
            return [self._normalize(item, keyword, category) for item in products]
        except requests.RequestException as exc:
            logger.warning("TikTok Shop API request failed for %r: %s", keyword, exc)
            return []

    @staticmethod
    def _normalize(item: Dict[str, Any], keyword: str, category: str) -> Dict[str, Any]:
        return {
            "source": "tiktok_shop_us",
            "source_market": "US",
            "keyword": keyword,
            "category": category,
            "product_id": item.get("id") or item.get("product_id", ""),
            "product_title": item.get("title", ""),
            "price": float(((item.get("price") or {}).get("original_price")) or 0),
            "currency": (item.get("price") or {}).get("currency", "USD"),
            "sold_count": int(item.get("sold_count") or item.get("sales_volume") or 0),
            "rating": float(item.get("rating") or 0),
            "review_count": int(item.get("review_count") or 0),
            "product_url": item.get("product_url", ""),
            "image_url": (item.get("main_images") or [{}])[0].get("url", "")
            if item.get("main_images")
            else "",
            "fetch_method": "official_api",
            "compliance_status": "official_partner_api",
            "_raw": item,
        }
