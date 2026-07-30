"""
Flipkart product search scraper.

Primary: dvishal485/flipkart-scraper-api HTTP service.
Fallback: Direct search page HTML scrape.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from scrapers.config_loader import load_flipkart_search_terms
from scrapers.filters.pet_filter import is_pet_product

logger = logging.getLogger(__name__)

FLIPKART_BASE = "https://www.flipkart.com"
SEARCH_URL = "https://www.flipkart.com/search?q={query}&page={page}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}


@dataclass
class FlipkartProduct:
    search_term: str
    category: str
    rank: int = 0
    product_id: str = ""
    product_title: str = ""
    brand: str = ""
    price_inr: float = 0.0
    mrp_inr: float = 0.0
    discount_pct: int = 0
    rating: float = 0.0
    review_count: int = 0
    seller: str = ""
    availability: str = "In Stock"
    product_url: str = ""
    image_url: str = ""
    _raw: Dict[str, Any] = field(default_factory=dict)


class FlipkartScraper:
    """Fetch Flipkart search rankings for configured pet search terms."""

    def __init__(
        self,
        api_base_url: Optional[str] = None,
        results_per_page: int = 20,
        request_delay: float = 2.0,
        use_api: Optional[str] = None,
    ):
        self.api_base_url = (
            api_base_url or os.getenv("FLIPKART_SCRAPER_URL", "http://localhost:3001")
        ).rstrip("/")
        self.results_per_page = results_per_page
        self.request_delay = request_delay
        # auto | always | never — Docker API often returns empty; HTML is reliable
        self.use_api = (use_api or os.getenv("FLIPKART_USE_API", "auto")).lower()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._api_ok: Optional[bool] = None

    def fetch_all(self) -> List[FlipkartProduct]:
        config = load_flipkart_search_terms()
        settings = config.get("search_settings", {})
        results = int(settings.get("results_per_page", self.results_per_page))

        products: List[FlipkartProduct] = []
        for category, cat_config in config.get("categories", {}).items():
            for term in cat_config.get("search_terms", []):
                batch = self._fetch_search(term, category, results)
                products.extend(batch)
                time.sleep(self.request_delay)

        return products

    def _fetch_search(
        self, search_term: str, category: str, limit: int
    ) -> List[FlipkartProduct]:
        affiliate = self._fetch_via_affiliate(search_term, category, limit)
        if affiliate:
            return affiliate
        if self._api_available():
            return self._fetch_via_api(search_term, category, limit)
        return self._fetch_via_html(search_term, category, limit)

    def _fetch_via_affiliate(
        self, search_term: str, category: str, limit: int
    ) -> List[FlipkartProduct]:
        """Official Flipkart Affiliate API when FLIPKART_AFFILIATE_* env is set."""
        try:
            from scrapers.flipkart.affiliate_client import FlipkartAffiliateClient

            client = FlipkartAffiliateClient(request_delay=self.request_delay)
            if not client.is_configured():
                return []
            products = client.search(search_term, category, limit)
            if products:
                logger.info(
                    "Flipkart Affiliate returned %d results for %r",
                    len(products),
                    search_term,
                )
            return products
        except Exception as exc:
            logger.debug("Flipkart Affiliate unavailable: %s", exc)
            return []

    def _api_available(self) -> bool:
        """Probe dvishal485/flipkart-scraper-api (GET /search/{query})."""
        if self.use_api in ("never", "false", "0", "html"):
            self._api_ok = False
            return False
        if self.use_api in ("always", "true", "1", "api"):
            return True
        if self._api_ok is not None:
            return self._api_ok
        try:
            resp = self.session.get(
                f"{self.api_base_url}/search/{quote_plus('dog food')}",
                timeout=8,
            )
            if resp.status_code != 200:
                self._api_ok = False
                return False
            data = resp.json()
            items = data.get("result") or data.get("products") or []
            self._api_ok = bool(items)
            if not self._api_ok:
                logger.info("Flipkart API reachable but empty — using HTML scrape")
        except (requests.RequestException, ValueError):
            self._api_ok = False
        return self._api_ok

    def _fetch_via_api(
        self, search_term: str, category: str, limit: int
    ) -> List[FlipkartProduct]:
        products: List[FlipkartProduct] = []
        try:
            # Official API: GET /search/${product_name}
            resp = self.session.get(
                f"{self.api_base_url}/search/{quote_plus(search_term)}",
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                raise requests.RequestException(str(data["error"]))
            items = data.get("result") or data.get("products") or []
            for rank, item in enumerate(items[:limit], start=1):
                product = self._parse_api_item(item, search_term, category, rank)
                if is_pet_product(
                    title=product.product_title,
                    url=product.product_url,
                    search_term=search_term,
                    category=category,
                ):
                    products.append(product)
            if not products:
                logger.info(
                    "Flipkart API returned 0 items for '%s' — HTML fallback", search_term
                )
                return self._fetch_via_html(search_term, category, limit)
            if all(p.price_inr <= 0 for p in products):
                logger.info(
                    "Flipkart API returned 0 prices for '%s' — HTML fallback", search_term
                )
                html_products = self._fetch_via_html(search_term, category, limit)
                if html_products and any(p.price_inr > 0 for p in html_products):
                    return html_products
        except requests.RequestException as exc:
            logger.warning("Flipkart API failed for '%s': %s — HTML fallback", search_term, exc)
            self._api_ok = False
            return self._fetch_via_html(search_term, category, limit)
        return products

    def _parse_api_item(
        self, item: Dict[str, Any], search_term: str, category: str, rank: int
    ) -> FlipkartProduct:
        # Supports dvishal485 API (name/link/current_price) and legacy shapes
        title = item.get("name") or item.get("title", "") or ""
        brand = item.get("brand", "") or self._extract_brand(title)
        url = (
            item.get("link")
            or item.get("productUrl")
            or item.get("product_url")
            or item.get("query_url")
            or ""
        )
        if url and not url.startswith("http"):
            url = urljoin(FLIPKART_BASE, url)
        pid = self._resolve_product_id(title, brand, url, explicit_pid=item.get("pid", ""))
        price = self._coerce_price(
            item.get("current_price")
            or item.get("discountedPrice")
            or item.get("selling_price")
            or item.get("final_price")
            or item.get("price_inr")
            or item.get("price")
            or 0
        )
        mrp = self._coerce_price(
            item.get("original_price")
            or item.get("mrp_inr")
            or item.get("mrp")
            or item.get("list_price")
            or price
        )
        discount = int(item.get("discountPercentage") or item.get("discount_percent") or 0)
        if not discount and mrp > 0 and price > 0:
            discount = int(round((1 - price / mrp) * 100))

        return FlipkartProduct(
            search_term=search_term,
            category=category,
            rank=rank,
            product_id=pid,
            product_title=title,
            brand=brand,
            price_inr=price,
            mrp_inr=mrp,
            discount_pct=discount,
            rating=float(item.get("averageRating", item.get("rating", 0)) or 0),
            review_count=int(item.get("noOfRatings", item.get("review_count", 0)) or 0),
            seller=item.get("seller", "") if isinstance(item.get("seller"), str) else "",
            availability=item.get("availability", "In Stock"),
            product_url=url,
            image_url=item.get("thumbnail") or item.get("image") or item.get("image_url") or "",
            _raw=item,
        )

    def _fetch_via_html(
        self, search_term: str, category: str, limit: int
    ) -> List[FlipkartProduct]:
        products: List[FlipkartProduct] = []
        url = SEARCH_URL.format(query=quote_plus(search_term), page=1)
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Flipkart HTML fetch failed for '%s': %s", search_term, exc)
            return products

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = self._product_cards(soup)

        for rank, card in enumerate(cards[:limit], start=1):
            title = self._card_title(card)
            link_el = card.select_one("a[href*='/p/']")
            href = link_el.get("href", "") if link_el else ""
            product_url = urljoin(FLIPKART_BASE, href) if href else ""

            price_el = card.select_one("div.hZ3P6w") or card.select_one("div._30jeq3") or card.select_one("div.Nx9bqj")
            price = self._parse_price(price_el.get_text() if price_el else "0")

            mrp_el = card.select_one("div.kRYCnD") or card.select_one("div._3I9_wc") or card.select_one("div.yRaYJf")
            mrp = self._parse_price(mrp_el.get_text() if mrp_el else str(price))

            rating = self._card_rating(card)
            review_count = self._card_review_count(card)

            img_el = card.select_one("img")
            image_url = img_el.get("src", "") if img_el else ""

            if not title:
                continue
            if not is_pet_product(title=title, url=product_url, search_term=search_term, category=category):
                continue

            products.append(
                FlipkartProduct(
                    search_term=search_term,
                    category=category,
                    rank=rank,
                    product_id=self._resolve_product_id(title, "", product_url),
                    product_title=title,
                    brand=self._extract_brand(title),
                    price_inr=price,
                    mrp_inr=mrp,
                    discount_pct=int(round((1 - price / mrp) * 100)) if mrp > 0 else 0,
                    rating=rating,
                    review_count=review_count,
                    product_url=product_url,
                    image_url=image_url,
                    _raw={"title": title, "url": product_url},
                )
            )

        return products

    @staticmethod
    def _product_cards(soup: BeautifulSoup) -> List[Any]:
        """Product tiles from search results (2024–2026 markup)."""
        cards = [
            c for c in soup.select("div[data-id]")
            if c.select_one("a[href*='/p/']")
        ]
        if cards:
            return cards
        return soup.select("div._1AtVbE div._13oc-S") or []

    @staticmethod
    def _card_title(card) -> str:
        for sel in (
            "a[title]",
            "div.RG5Slk",
            "div._4rR01T",
            "div.k7wcnx",
            "div.jIjQ8S",
            "a[href*='/p/']",
        ):
            el = card.select_one(sel)
            if not el:
                continue
            title = (el.get("title") or "").strip() or el.get_text(strip=True)
            if title and len(title) > 5:
                return title
        return ""

    @staticmethod
    def _card_rating(card) -> float:
        rating_el = card.select_one("div.MKiFS6") or card.select_one("div._3LWZlK")
        if not rating_el:
            return 0.0
        m = re.search(r"([\d.]+)", rating_el.get_text())
        return float(m.group(1)) if m else 0.0

    @staticmethod
    def _card_review_count(card) -> int:
        review_el = card.select_one("span.PvbNMB") or card.select_one("span._2_R_DZ span")
        if not review_el:
            return 0
        m = re.search(r"([\d,]+)\s*Rating", review_el.get_text(), re.I)
        return int(m.group(1).replace(",", "")) if m else 0

    @staticmethod
    def _coerce_price(val: Any) -> float:
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        return FlipkartScraper._parse_price(str(val))

    @staticmethod
    def flipkart_pid(url: str) -> str:
        """Stable Flipkart listing id from product URL query param."""
        if not url:
            return ""
        match = re.search(r"[?&]pid=([A-Z0-9]+)", url, re.I)
        return match.group(1).upper() if match else ""

    @staticmethod
    def _resolve_product_id(
        title: str, brand: str, url: str, explicit_pid: str = ""
    ) -> str:
        pid = (explicit_pid or FlipkartScraper.flipkart_pid(url) or "").strip().upper()
        if pid:
            return pid
        return hashlib.md5(f"{title}|{brand}|{url}".encode()).hexdigest()

    @staticmethod
    def _product_id(title: str, brand: str, url: str) -> str:
        return FlipkartScraper._resolve_product_id(title, brand, url)

    @staticmethod
    def dedupe_bronze_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """One row per Flipkart listing per ingest day (best rank wins)."""
        best: Dict[Any, Dict[str, Any]] = {}
        order: List[Any] = []
        for rec in records:
            ingest = str(rec.get("ingest_date", ""))
            pid = FlipkartScraper.flipkart_pid(str(rec.get("product_url", "")))
            key = (ingest, pid) if pid else (
                ingest,
                rec.get("product_id"),
                rec.get("search_term"),
            )
            if key not in best:
                best[key] = rec
                order.append(key)
                continue
            existing = best[key]
            if int(rec.get("rank", 999) or 999) < int(existing.get("rank", 999) or 999):
                best[key] = rec
        return [best[k] for k in order]

    @staticmethod
    def _parse_price(text: str) -> float:
        cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _extract_brand(title: str) -> str:
        known = ["Royal Canin", "Farmina", "Pedigree", "Whiskas", "Drools", "Himalaya"]
        for brand in known:
            if brand.lower() in title.lower():
                return brand
        return title.split()[0] if title else ""

    def to_bronze_records(self, products: List[FlipkartProduct]) -> List[Dict[str, Any]]:
        now = __import__("datetime").datetime.now()
        records = []
        for p in products:
            if not is_pet_product(
                title=p.product_title,
                url=p.product_url,
                search_term=p.search_term,
                category=p.category,
            ):
                continue
            d = asdict(p)
            raw = d.pop("_raw", {})
            records.append(
                {
                    "ingest_date": now.date(),
                    "ingest_ts": now,
                    "marketplace": "in",
                    "search_term": p.search_term,
                    "category": p.category,
                    "rank": p.rank,
                    "rank_prev_day": p.rank,
                    "rank_delta": 0,
                    "product_id": p.product_id,
                    "product_title": p.product_title,
                    "brand": p.brand,
                    "price_inr": p.price_inr,
                    "mrp_inr": p.mrp_inr,
                    "discount_pct": p.discount_pct,
                    "rating": p.rating,
                    "rating_prev_day": p.rating,
                    "rating_delta": 0.0,
                    "review_count": p.review_count,
                    "review_count_prev_day": p.review_count,
                    "seller": p.seller,
                    "availability": p.availability,
                    "product_url": p.product_url,
                    "image_url": p.image_url,
                    "_raw_json": json.dumps(raw),
                }
            )
        return records
