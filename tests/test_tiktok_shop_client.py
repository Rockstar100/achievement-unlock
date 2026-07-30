"""Tests for the TikTok Shop connector scaffold - must never call tiktok.com."""
from scrapers.tiktok_shop_global.client_official_api import TikTokShopAPIClient
from scrapers.tiktok_shop_global.client_csv_import import TikTokShopCSVImporter


def test_api_client_unconfigured_by_default():
    client = TikTokShopAPIClient(app_key="", app_secret="", access_token="")
    assert client.is_configured() is False
    assert client.search("dog toys", "dog_toys") == []


def test_api_client_configured_flag():
    client = TikTokShopAPIClient(app_key="k", app_secret="s", access_token="t")
    assert client.is_configured() is True


def test_csv_importer_missing_file_returns_empty():
    importer = TikTokShopCSVImporter()
    assert importer.load("/nonexistent/path/export.csv") == []


def test_csv_importer_loads_real_file(tmp_path):
    csv_path = tmp_path / "tiktok_export.csv"
    csv_path.write_text(
        "product_id,product_title,category,price,currency,sold_count,rating,review_count\n"
        "abc123,Tofu Cat Litter,health_wellness,19.99,USD,8000,4.6,1200\n",
        encoding="utf-8",
    )
    importer = TikTokShopCSVImporter()
    rows = importer.load(str(csv_path))
    assert len(rows) == 1
    assert rows[0]["source"] == "tiktok_shop_us"
    assert rows[0]["fetch_method"] == "csv_import"
    assert rows[0]["sold_count"] == 8000
