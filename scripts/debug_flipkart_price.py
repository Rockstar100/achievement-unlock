#!/usr/bin/env python
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.flipkart.client import FlipkartScraper

query = "dog food"
url = f"https://www.flipkart.com/search?q={quote_plus(query)}&page=1"
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}
r = requests.get(url, headers=headers, timeout=30)
print("status", r.status_code, "len", len(r.text))
soup = BeautifulSoup(r.text, "html.parser")
for sel in ["div[data-id]", "div._1AtVbE div._13oc-S", "a[title]", "div.hZ3P6w", "div._30jeq3", "div.Nx9bqj"]:
    print(sel, len(soup.select(sel)))

cards = soup.select("div[data-id]")
if cards:
    card = cards[0]
    text = card.get_text(" ", strip=True)[:200]
    print("card sample text:", text.encode("ascii", "replace").decode())
    for el in card.select("[class]")[:20]:
        t = el.get_text(strip=True)
        if "₹" in t or re.search(r"\d{2,}", t):
            print("  class", el.get("class"), "->", t[:40])

scraper = FlipkartScraper(use_api="never")
products = scraper._fetch_via_html(query, "dog_food", 5)
print("parsed", len(products))
for p in products:
    print(p.rank, p.price_inr, p.product_title[:50])
