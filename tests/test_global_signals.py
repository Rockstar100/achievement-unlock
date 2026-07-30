"""Tests for the global (US) supplementary pet-trend signal layer."""
from datetime import date

from transform.global_signals import (
    build_global_platform_daily,
    build_india_bridge,
    score_amazon_us_signal,
    score_tiktok_shop_signal,
)


def _amazon_us_row(**overrides):
    row = {
        "asin": "B0USDOG01",
        "product_title": "Blue Buffalo Life Protection Dry Dog Food",
        "brand": "Blue Buffalo",
        "category": "Dog Food",
        "rank_position": 1,
        "rating": 4.7,
        "review_count": 29000,
        "is_mover_shaker": 0,
        "price": 0,
        "currency": "USD",
        "product_url": "https://www.amazon.com/dp/B0USDOG01",
        "image_url": "",
        "fetch_method": "html_scrape",
        "compliance_status": "public_page_no_login",
    }
    row.update(overrides)
    return row


def _tiktok_row(**overrides):
    row = {
        "product_id": "tts_001",
        "product_title": "Tofu Cat Litter Breakout Bag",
        "brand": "TofuLitter",
        "category": "health_wellness",
        "rank_position": 1,
        "rating": 4.6,
        "review_count": 1200,
        "sold_count": 8000,
        "creator_count": 150,
        "video_count": 400,
        "engagement_count": 300,
        "price": 19.99,
        "currency": "USD",
        "product_url": "",
        "image_url": "",
        "fetch_method": "official_api",
        "compliance_status": "official_partner_api",
    }
    row.update(overrides)
    return row


def test_amazon_us_signal_rewards_rank_one():
    good = score_amazon_us_signal(_amazon_us_row(rank_position=1))
    bad = score_amazon_us_signal(_amazon_us_row(rank_position=30))
    assert good["global_signal_score"] > bad["global_signal_score"]


def test_tiktok_shop_signal_rewards_sold_count():
    hot = score_tiktok_shop_signal(_tiktok_row(sold_count=8000))
    cold = score_tiktok_shop_signal(_tiktok_row(sold_count=0))
    assert hot["global_signal_score"] > cold["global_signal_score"]


def test_build_global_platform_daily_tags_source_and_market():
    rows = build_global_platform_daily([_amazon_us_row()], [_tiktok_row()], snapshot_date=date(2026, 7, 7))
    sources = {r["source"] for r in rows}
    assert sources == {"amazon_us", "tiktok_shop_us"}
    assert all(r["source_market"] == "US" for r in rows)
    assert all(r["snapshot_date"] == "2026-07-07" for r in rows)
    # Ranked and re-ranked across both sources combined
    assert rows[0]["rank_position_global"] == 1


def test_build_global_platform_daily_never_touches_india_trend_score():
    rows = build_global_platform_daily([_amazon_us_row()], [], snapshot_date=date(2026, 7, 7))
    assert "trend_score" not in rows[0]
    assert "global_signal_score" in rows[0]


def test_bridge_marks_known_india_brand_as_available():
    rows = build_global_platform_daily([_amazon_us_row(brand="Pedigree")], [], snapshot_date=date(2026, 7, 7))
    bridge = build_india_bridge(rows, india_brands={"pedigree", "whiskas"})
    assert bridge[0]["india_availability"] is True
    assert bridge[0]["global_opportunity_bucket"] == "already_available_in_india"


def test_bridge_marks_unknown_brand_as_white_space_opportunity():
    rows = build_global_platform_daily([_amazon_us_row(brand="Blue Buffalo", category="Dog Food")], [], snapshot_date=date(2026, 7, 7))
    bridge = build_india_bridge(rows, india_brands={"pedigree", "whiskas"})
    assert bridge[0]["india_availability"] is False
    assert bridge[0]["global_opportunity_bucket"] == "not_yet_available_in_india"
