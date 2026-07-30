"""
Flipkart Affiliate API client (primary when credentials are configured).

Requires env:
  FLIPKART_AFFILIATE_ID
  FLIPKART_AFFILIATE_TOKEN

Docs: https://affiliate.flipkart.com/
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests

from scrapers.flipkart.client import FlipkartProduct, HEADERS

logger = logging.getLogger(__name__)

AFFILIATE_BASE = "https://affiliate-api.flipkart.net/affiliate/1.0"


class FlipkartAffiliateClient:
  """Search Flipkart catalog via official Affiliate API."""

  def __init__(
      self,
      affiliate_id: Optional[str] = None,
      affiliate_token: Optional[str] = None,
      request_delay: float = 1.0,
  ):
      self.affiliate_id = affiliate_id or os.getenv("FLIPKART_AFFILIATE_ID", "")
      self.affiliate_token = affiliate_token or os.getenv("FLIPKART_AFFILIATE_TOKEN", "")
      self.request_delay = request_delay
      self.session = requests.Session()
      self.session.headers.update(HEADERS)
      self.session.headers.update(
          {
              "Fk-Affiliate-Id": self.affiliate_id,
              "Fk-Affiliate-Token": self.affiliate_token,
          }
      )

  def is_configured(self) -> bool:
      return bool(self.affiliate_id and self.affiliate_token)

  def search(self, query: str, category: str, limit: int = 20) -> List[FlipkartProduct]:
      if not self.is_configured():
          return []
      url = f"{AFFILIATE_BASE}/search.json"
      params = {"query": query, "resultCount": min(limit, 20)}
      try:
          resp = self.session.get(url, params=params, timeout=15)
          if resp.status_code != 200:
              logger.warning("Flipkart Affiliate search HTTP %s for %r", resp.status_code, query)
              return []
          data = resp.json()
      except Exception as exc:
          logger.warning("Flipkart Affiliate search failed: %s", exc)
          return []

      products: List[FlipkartProduct] = []
      items = data.get("products") or data.get("productInfoList") or []
      for i, item in enumerate(items[:limit], start=1):
          pinfo = item.get("productBaseInfoV1") or item
          title = (
              pinfo.get("title")
              or pinfo.get("productTitle")
              or item.get("title")
              or ""
          )
          pid = str(pinfo.get("productId") or item.get("productId") or "")
          price_block = pinfo.get("flipkartSellingPrice") or pinfo.get("maximumRetailPrice") or {}
          price = float(price_block.get("amount") or price_block.get("value") or 0)
          mrp_block = pinfo.get("maximumRetailPrice") or {}
          mrp = float(mrp_block.get("amount") or mrp_block.get("value") or 0)
          discount = int(pinfo.get("discountPercentage") or 0)
          rating = float(pinfo.get("productRating") or pinfo.get("averageRating") or 0)
          review_count = int(pinfo.get("reviewCount") or pinfo.get("numberOfReviews") or 0)
          product_url = (
              pinfo.get("productUrl")
              or pinfo.get("productLandingUrl")
              or item.get("productUrl")
              or ""
          )
          image_url = ""
          images = pinfo.get("imageUrls") or pinfo.get("images") or {}
          if isinstance(images, dict):
              image_url = images.get("400x400") or images.get("200x200") or ""
          elif isinstance(images, list) and images:
              image_url = images[0].get("url", "") if isinstance(images[0], dict) else str(images[0])

          brand = str(pinfo.get("productBrand") or pinfo.get("brand") or "")
          products.append(
              FlipkartProduct(
                  search_term=query,
                  category=category,
                  rank=i,
                  product_id=pid,
                  product_title=title,
                  brand=brand,
                  price_inr=price,
                  mrp_inr=mrp,
                  discount_pct=discount,
                  rating=rating,
                  review_count=review_count,
                  product_url=product_url,
                  image_url=image_url,
                  _raw={"source": "flipkart_affiliate", **item},
              )
          )
      time.sleep(self.request_delay)
      return products
