"""Tests for Slack digest formatters."""
from notifications.formatters.digest import format_daily_pulse, format_weekly_digest


def test_daily_pulse_empty():
    blocks = format_daily_pulse([])
    assert blocks[0]["type"] == "header"
    assert any(b.get("type") == "section" for b in blocks)


def test_daily_pulse_with_products():
    products = [
        {
            "canonical_title": "Royal Canin Dog Food",
            "normalized_brand": "royal canin",
            "category": "dog_food",
            "trend_score": 85.5,
            "trend_tier": "breakout",
        }
    ]
    blocks = format_daily_pulse(products)
    text_blocks = [b for b in blocks if b.get("type") == "section"]
    assert "Royal Canin Dog Food" in text_blocks[0]["text"]["text"]


def test_weekly_digest_structure():
    blocks = format_weekly_digest([], [], [])
    assert blocks[0]["type"] == "header"
    header_texts = [b["text"]["text"] for b in blocks if b.get("type") == "section" and "text" in b.get("text", {})]
    assert any("Top 10" in t for t in header_texts)
