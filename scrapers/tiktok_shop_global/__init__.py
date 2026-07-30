"""TikTok Shop (US/global) — global supplementary pet-product source (not India-native).

TikTok is blocked in India by Indian government order (IT Act, June 2020) and
remains blocked as of 2026. This module deliberately does NOT scrape
tiktok.com/shop.tiktok.com directly — that would mean circumventing an active
government block, which this project will not do, from any network.

The only supported data paths are:
  1. Official TikTok Shop Partner/Open API (requires your own Partner Center
     app + credentials — see client_official_api.py)
  2. A CSV export from a licensed data vendor or your own lawful export
     (see client_csv_import.py)

Both return an empty list gracefully if unconfigured — this module is safe
to import and call with zero setup; it just won't produce data until you
provide credentials or a CSV.
"""
from .client import TikTokShopGlobalClient
from .client_csv_import import TikTokShopCSVImporter
from .client_official_api import TikTokShopAPIClient

__all__ = ["TikTokShopGlobalClient", "TikTokShopAPIClient", "TikTokShopCSVImporter"]
