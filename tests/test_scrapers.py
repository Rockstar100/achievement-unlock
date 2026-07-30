"""Tests for scraper modules."""
import pytest

from scrapers.amazon.client import AmazonProduct, AmazonScraper
from scrapers.flipkart.client import FlipkartProduct, FlipkartScraper
from scrapers.gtrends.client import GTrendsClient, GTrendsRecord


class TestAmazonScraper:
    def test_extract_brand(self):
        assert AmazonScraper._extract_brand("Royal Canin Maxi Adult") == "Royal Canin"
        assert AmazonScraper._extract_brand("Unknown Brand Product") == "Unknown"

    def test_parse_price(self):
        assert AmazonScraper._parse_price("₹1,299.00") == 1299.0
        assert AmazonScraper._parse_price("") == 0.0

    def test_to_bronze_records(self):
        scraper = AmazonScraper()
        products = [
            AmazonProduct(
                category="Dog Food",
                rank=1,
                asin="B0TEST1234",
                product_title="Royal Canin Dog Food 4kg",
                brand="Royal Canin",
                price_inr=999.0,
                product_url="https://www.amazon.in/dp/B0TEST1234",
            )
        ]
        records = scraper.to_bronze_records(products)
        assert len(records) == 1
        assert records[0]["asin"] == "B0TEST1234"
        assert records[0]["marketplace"] == "in"


class TestFlipkartScraper:
    def test_product_id_consistency(self):
        pid1 = FlipkartScraper._product_id("Title", "Brand", "http://url")
        pid2 = FlipkartScraper._product_id("Title", "Brand", "http://url")
        assert pid1 == pid2

    def test_product_id_uses_url_pid(self):
        url = (
            "https://www.flipkart.com/example/p/itm?pid=PCLGWNKQZDSQVVDX"
            "&lid=LSTPCLGWNKQZDSQVVDXIIY0CL"
        )
        pid = FlipkartScraper._product_id("Different Title", "", url)
        assert pid == "PCLGWNKQZDSQVVDX"

    def test_dedupe_bronze_records_keeps_best_rank(self):
        url = "https://www.flipkart.com/example/p/itm?pid=PCLGWNKQZDSQVVDX"
        records = [
            {
                "ingest_date": "2026-07-07",
                "product_id": "old_hash_1",
                "search_term": "dog food",
                "product_url": url,
                "rank": 3,
            },
            {
                "ingest_date": "2026-07-07",
                "product_id": "old_hash_2",
                "search_term": "dog treats",
                "product_url": url + "&qH=abc",
                "rank": 1,
            },
        ]
        out = FlipkartScraper.dedupe_bronze_records(records)
        assert len(out) == 1
        assert out[0]["rank"] == 1
        assert out[0]["product_id"] == "old_hash_2"

    def test_api_disabled_when_empty_result(self, monkeypatch):
        class FakeResp:
            status_code = 200

            @staticmethod
            def json():
                return {"result": []}

        scraper = FlipkartScraper(use_api="auto")
        monkeypatch.setattr(scraper.session, "get", lambda *a, **k: FakeResp())
        assert scraper._api_available() is False

    def test_parse_dvishal_api_item(self):
        scraper = FlipkartScraper()
        product = scraper._parse_api_item(
            {
                "name": "Pedigree Adult Dog Food 3kg",
                "link": "/pedigree-dog-food/p/itm123",
                "current_price": 1299,
                "original_price": 1499,
                "discounted": True,
                "thumbnail": "https://img.example/t.jpg",
            },
            search_term="dog food",
            category="dog_food",
            rank=1,
        )
        assert product.product_title.startswith("Pedigree")
        assert product.price_inr == 1299.0
        assert product.mrp_inr == 1499.0
        assert "flipkart.com" in product.product_url

    def test_to_bronze_records(self):
        scraper = FlipkartScraper()
        products = [
            FlipkartProduct(
                search_term="dog food",
                category="dog_food",
                rank=1,
                product_id="abc123",
                product_title="Test Dog Food",
                brand="TestBrand",
                price_inr=500.0,
            )
        ]
        records = scraper.to_bronze_records(products)
        assert len(records) == 1
        assert records[0]["search_term"] == "dog food"


class TestGTrendsClient:
    def test_summarize_scores_uses_window_means(self):
        # Rare-term spike: one 100 among zeros should not dominate the mean
        current, prev, avg, peak = GTrendsClient._summarize_scores(
            [0] * 20 + [100] + [0] * 3
        )
        assert peak == 100
        assert avg < 20
        assert current < 50

    def test_to_bronze_records_interest(self):
        client = GTrendsClient()
        records = client.to_bronze_records(
            [
                GTrendsRecord(
                    category="dog_food",
                    keyword="dog food",
                    interest_score=71,
                    interest_score_prev_day=51,
                    interest_delta=20,
                    interest_avg_7d=52,
                    interest_peak_7d=90,
                )
            ]
        )
        assert records[0]["interest_score"] == 71
        assert records[0]["interest_delta"] == 20
        assert records[0]["interest_avg_7d"] == 52
        assert records[0]["category"] == "dog_food"
        assert records[0]["is_rising"] == 0

    def test_to_bronze_records_rising_query(self):
        client = GTrendsClient()
        records = client.to_bronze_records(
            [
                GTrendsRecord(
                    category="dog_food",
                    keyword="dog food",
                    is_rising=1,
                    rising_query="best dog food india",
                    rising_score=120,
                )
            ]
        )
        assert records[0]["keyword"] == "best dog food india"
        assert records[0]["rising_score"] == 120
        assert records[0]["is_rising"] == 1
