"""
Amazon.in Pet Supplies Best Sellers scraper.
All categories are under amazon.in/gp/bestsellers/pet-supplies/
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scrapers.config_loader import load_amazon_categories
from scrapers.filters.pet_filter import is_pet_product

logger = logging.getLogger(__name__)

AMAZON_IN_BASE = "https://www.amazon.in"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

PET_BRANDS = [
    "Royal Canin", "Farmina", "Pedigree", "Whiskas", "Drools",
    "Himalaya", "Meo", "Kong", "Nylabone", "Purina", "SmartHeart",
    "Drools", "JerHigh", "Chip Chops", "Beaphar", "Savavet",
]


@dataclass
class AmazonProduct:
    category: str
    subcategory: str = ""
    rank: int = 0
    rank_prev_day: int = 0
    asin: str = ""
    product_title: str = ""
    brand: str = ""
    price_inr: float = 0.0
    mrp_inr: float = 0.0
    discount_pct: int = 0
    rating: float = 0.0
    review_count: int = 0
    is_mover_shaker: int = 0
    rank_delta: int = 0
    product_url: str = ""
    image_url: str = ""
    _raw: Dict[str, Any] = field(default_factory=dict)


class AmazonScraper:
    """Fetch Amazon.in pet-supplies bestseller listings."""

    def __init__(
        self,
        marketplace: str = "in",
        apify_token: Optional[str] = None,
        apify_actor_id: Optional[str] = None,
        request_delay: float = 2.0,
        use_playwright: Optional[str] = None,
        base_url: str = AMAZON_IN_BASE,
        config_loader: Optional[Callable[[], Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.marketplace = marketplace
        self.apify_token = apify_token or os.getenv("APIFY_API_TOKEN")
        self.apify_actor_id = apify_actor_id or os.getenv(
            "APIFY_ACTOR_ID", "m-murasovs/amazon-bestsellers-scraper"
        )
        self.request_delay = request_delay
        # auto | always | never — Playwright used when requests HTML is empty/blocked
        self.use_playwright = (
            use_playwright or os.getenv("AMAZON_USE_PLAYWRIGHT", "auto")
        ).lower()
        self.base_url = base_url
        self.config_loader = config_loader or load_amazon_categories
        self.session = requests.Session()
        self.session.headers.update(headers or HEADERS)

    @staticmethod
    def _as_path_list(value: Any) -> List[str]:
        """Category paths may be a single string or a list (dog+cat sub-nodes merged into one category)."""
        if not value:
            return []
        if isinstance(value, str):
            return [value]
        return list(value)

    def fetch_all(self, category_keys: Optional[List[str]] = None) -> List[AmazonProduct]:
        config = self.config_loader()
        max_items = int(config.get("defaults", {}).get("max_items_per_category", 30))
        categories = config.get("categories", {})
        products: List[AmazonProduct] = []

        for cat_key, cat_cfg in categories.items():
            if category_keys and cat_key not in category_keys:
                continue

            display_name = cat_cfg.get("display_name", cat_key)
            bs_paths = self._as_path_list(cat_cfg.get("bestsellers_path", ""))
            ms_paths = self._as_path_list(cat_cfg.get("movers_path", ""))

            for bs_path in bs_paths:
                batch = self._fetch_page(
                    urljoin(self.base_url, bs_path),
                    category=display_name,
                    category_key=cat_key,
                    is_mover=0,
                    max_items=max_items,
                )
                products.extend(batch)
                time.sleep(self.request_delay)

            for ms_path in ms_paths:
                batch = self._fetch_page(
                    urljoin(self.base_url, ms_path),
                    category=display_name,
                    category_key=cat_key,
                    is_mover=1,
                    max_items=max_items,
                )
                products.extend(batch)
                time.sleep(self.request_delay)

        return self._dedupe_products(products)

    def _fetch_page(
        self,
        url: str,
        category: str,
        category_key: str,
        is_mover: int,
        max_items: int,
    ) -> List[AmazonProduct]:
        if self.apify_token:
            return self._fetch_via_apify(url, category, is_mover, max_items)

        return self._scrape_listing_page(url, category, category_key, is_mover, max_items)

    def _fetch_via_apify(
        self, url: str, category: str, is_mover: int, max_items: int
    ) -> List[AmazonProduct]:
        api_url = f"https://api.apify.com/v2/acts/{self.apify_actor_id}/run-sync-get-dataset-items"
        payload = {"categoryUrls": [url], "maxItems": max_items, "countryCode": "IN"}
        try:
            resp = self.session.post(
                api_url, params={"token": self.apify_token}, json=payload, timeout=120
            )
            resp.raise_for_status()
            items = resp.json()
            products = [self._parse_apify_item(item, category, is_mover) for item in items]
            return [p for p in products if self._is_valid_pet_product(p)]
        except requests.RequestException as exc:
            logger.warning("Apify failed for %s: %s", category, exc)
            return []

    def _parse_apify_item(self, item: Dict[str, Any], category: str, is_mover: int) -> AmazonProduct:
        price = float(item.get("price", 0) or 0)
        mrp = float(item.get("listPrice", price) or price)
        title = item.get("title", "")
        return AmazonProduct(
            category=category,
            rank=int(item.get("rank", 0) or 0),
            asin=item.get("asin", ""),
            product_title=title,
            brand=item.get("brand", self._extract_brand(title)),
            price_inr=price,
            mrp_inr=mrp,
            discount_pct=int(round((1 - price / mrp) * 100)) if mrp > 0 else 0,
            rating=float(item.get("rating", 0) or 0),
            review_count=int(item.get("reviewsCount", 0) or 0),
            is_mover_shaker=is_mover,
            product_url=item.get("url", ""),
            image_url=item.get("image", ""),
            _raw=item,
        )

    def _fetch_page_html(self, url: str) -> str:
        """Fetch listing HTML via requests, with optional Playwright fallback."""
        html = ""
        if self.use_playwright != "always":
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                if "pet-supplies" not in resp.url and "pet-supplies" not in url:
                    logger.warning("URL is not pet-supplies: %s", resp.url)
                    return ""
                html = resp.text
            except requests.RequestException as exc:
                logger.warning("Requests fetch failed for %s: %s", url, exc)

        has_items = any(
            marker in html
            for marker in ("zg-grid-general-faceout", "zg-item-immersion", "data-asin")
        )
        if has_items and self.use_playwright != "always":
            return html

        if self.use_playwright in ("auto", "always", "1", "true", "yes"):
            pw_html = self._fetch_html_playwright(url)
            if pw_html:
                return pw_html

        return html

    @staticmethod
    def _fetch_html_playwright(url: str) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning(
                "Playwright not installed — run: pip install playwright && playwright install chromium"
            )
            return ""

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=HEADERS["User-Agent"],
                    locale="en-IN",
                    extra_http_headers={"Accept-Language": HEADERS["Accept-Language"]},
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(1500)
                html = page.content()
                browser.close()
                return html
        except Exception as exc:
            logger.warning("Playwright fetch failed for %s: %s", url, exc)
            return ""

    def _scrape_listing_page(
        self, url: str, category: str, category_key: str, is_mover: int, max_items: int
    ) -> List[AmazonProduct]:
        products: List[AmazonProduct] = []
        html = self._fetch_page_html(url)
        if not html:
            logger.error("Failed to fetch %s", url)
            return products

        soup = BeautifulSoup(html, "html.parser")
        items = (
            soup.select("div.zg-grid-general-faceout")
            or soup.select("li.zg-item-immersion")
            or soup.select("div[data-asin]")
        )

        rank = 0
        for item in items:
            if rank >= max_items:
                break

            link_el = item.select_one("a.a-link-normal[href*='/dp/']") or item.select_one("a[href*='/dp/']")
            href = link_el.get("href", "") if link_el else ""
            product_url = urljoin(self.base_url, href) if href else ""

            asin = item.get("data-asin", "") if item.name == "div" else ""
            if not asin:
                m = re.search(r"/dp/([A-Z0-9]{10})", product_url)
                asin = m.group(1) if m else ""

            title = self._extract_title(item, link_el, product_url)
            if not title:
                continue

            if not is_pet_product(title=title, url=product_url, category=category_key):
                logger.debug("Skipping non-pet item: %s", title[:60])
                continue

            rank += 1
            price = self._extract_price(item)

            rating_el = item.select_one("span.a-icon-alt")
            rating = 0.0
            if rating_el:
                m = re.search(r"([\d.]+)", rating_el.get_text())
                rating = float(m.group(1)) if m else 0.0

            review_count = 0
            for sel in ("span.a-size-small", "a.a-size-small"):
                review_el = item.select_one(sel)
                if review_el:
                    m = re.search(r"([\d,]+)", review_el.get_text())
                    if m:
                        review_count = int(m.group(1).replace(",", ""))
                        break

            img_el = item.select_one("img")
            image_url = img_el.get("src", "") if img_el else ""

            rank_delta = 0
            if is_mover:
                pct_el = item.select_one("span.zg-percent-change")
                if pct_el:
                    m = re.search(r"([\d.]+)", pct_el.get_text())
                    rank_delta = int(float(m.group(1))) if m else 0

            products.append(
                AmazonProduct(
                    category=category,
                    rank=rank,
                    asin=asin or hashlib.md5(title.encode()).hexdigest()[:10].upper(),
                    product_title=title,
                    brand=self._extract_brand(title),
                    price_inr=price,
                    mrp_inr=price,
                    rating=rating,
                    review_count=review_count,
                    is_mover_shaker=is_mover,
                    rank_delta=rank_delta,
                    product_url=product_url,
                    image_url=image_url,
                    _raw={"title": title, "url": product_url, "category_key": category_key},
                )
            )

        return products

    def _extract_title(self, item, link_el, product_url: str) -> str:
        for el in (
            item.select_one("div.p13n-sc-truncated"),
            item.select_one("div.p13n-sc-truncate"),
            item.select_one("span.zg-text-center-align"),
            link_el,
        ):
            if el:
                text = el.get("title") or el.get("aria-label") or el.get_text(strip=True)
                if text and len(text) > 3:
                    return text.strip()

        img = item.select_one("img")
        if img and img.get("alt") and img["alt"] not in ("", "Product image"):
            return img["alt"].strip()

        # Fallback: parse product name from URL slug
        from scrapers.filters.pet_filter import title_from_url
        slug_title = title_from_url(product_url)
        if slug_title and len(slug_title) > 3:
            return slug_title.title()

        return ""

    @staticmethod
    def _is_valid_pet_product(product: AmazonProduct) -> bool:
        return is_pet_product(
            title=product.product_title,
            url=product.product_url,
            category=product.category,
        )

    @staticmethod
    def _dedupe_products(products: List[AmazonProduct]) -> List[AmazonProduct]:
        seen = set()
        result = []
        for p in products:
            key = p.asin or p.product_title
            if key and key not in seen:
                seen.add(key)
                result.append(p)
        return result

    @staticmethod
    def _extract_price(item) -> float:
        for sel in (
            "span.a-price span.a-offscreen",
            "span.a-size-base.a-color-price",
            "span[class*='p13n-sc-price']",
            "span.a-color-price",
        ):
            el = item.select_one(sel)
            if el:
                price = AmazonScraper._parse_price(el.get_text())
                if price > 0:
                    return price
        text = item.get_text(" ")
        matches = re.findall(r"[\u20b9]\s*([\d,]+(?:\.\d+)?)", text)
        for m in matches:
            price = AmazonScraper._parse_price(m)
            if price > 0:
                return price
        return 0.0

    @staticmethod
    def _parse_price(text: str) -> float:
        cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _extract_brand(title: str) -> str:
        for brand in PET_BRANDS:
            if brand.lower() in title.lower():
                return brand
        return title.split()[0] if title else ""

    def to_bronze_records(self, products: List[AmazonProduct]) -> List[Dict[str, Any]]:
        from datetime import datetime

        now = datetime.now()
        records = []
        for p in products:
            if not self._is_valid_pet_product(p):
                continue
            d = asdict(p)
            raw = d.pop("_raw", {})
            records.append(
                {
                    "ingest_date": now.date(),
                    "ingest_ts": now,
                    "marketplace": self.marketplace,
                    "category": p.category,
                    "subcategory": p.subcategory,
                    "rank": p.rank,
                    "rank_prev_day": p.rank_prev_day or p.rank,
                    "asin": p.asin,
                    "product_title": p.product_title,
                    "brand": p.brand,
                    "price_inr": p.price_inr,
                    "mrp_inr": p.mrp_inr,
                    "discount_pct": p.discount_pct,
                    "rating": p.rating,
                    "review_count": p.review_count,
                    "is_mover_shaker": p.is_mover_shaker,
                    "rank_delta": p.rank_delta,
                    "product_url": p.product_url,
                    "image_url": p.image_url,
                    "_raw_json": json.dumps(raw),
                }
            )
        return records
