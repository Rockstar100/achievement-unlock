"""Tests for scoring v2."""
import pandas as pd

from transform.scoring_v2 import _rank_momentum, score_product


def test_score_product_emits_reason_codes():
    prod = {
        "canonical_product_id": "abc123",
        "amazon_rank": 5,
        "flipkart_avg_rank": 8,
        "amazon_rating": 4.5,
        "amazon_review_count": 200,
        "amazon_is_mover_shaker": 1,
        "discount_pct": 20,
        "sources": "amazon|flipkart",
    }
    gt = {"gtrends_category_interest": 70, "gtrends_interest_delta_7d": 18}
    scored = score_product(prod, gt, __import__("pandas").DataFrame(), "2026-07-04")
    assert scored["trend_score"] >= 50, "baseline rank/rating should yield meaningful score"
    assert 0 <= scored["trend_score"] <= 100
    assert scored["recommended_action"] in ("BUY_TEST", "WATCHLIST", "MONITOR", "IGNORE", "REVIEW_MANUALLY")
    assert "reason_codes" in scored
    assert scored["trend_tier"] in ("breakout", "rising", "stable", "declining")


def test_low_rating_penalty():
    prod = {
        "canonical_product_id": "x",
        "amazon_rank": 50,
        "amazon_rating": 3.2,
        "amazon_review_count": 10,
        "sources": "amazon",
    }
    scored = score_product(prod, {}, __import__("pandas").DataFrame(), "2026-07-04")
    assert scored["penalty_score"] > 0
    assert "LOW_RATING_PENALTY" in scored["reason_codes"]
    assert scored["recommended_action"] == "REVIEW_MANUALLY"


def test_rank_momentum_positive_when_rank_improves():
    # Lower rank number is better: 50 -> 3 is a big improvement.
    assert _rank_momentum(3, 50) > 0


def test_rank_momentum_zero_when_rank_worsens_or_unchanged():
    assert _rank_momentum(50, 3) == 0.0
    assert _rank_momentum(10, 10) == 0.0
    assert _rank_momentum(5, None) == 0.0


def test_score_product_detects_rank_improvement_from_history():
    hist = pd.DataFrame([{
        "canonical_product_id": "abc123",
        "snapshot_date": "2026-07-06",
        "amazon_rank": 50,
        "flipkart_rank": None,
        "review_count": 100,
        "interest_index": 0,
    }])
    prod = {
        "canonical_product_id": "abc123",
        "amazon_rank": 3,
        "amazon_rating": 4.0,
        "amazon_review_count": 100,
        "sources": "amazon",
    }
    scored = score_product(prod, {}, hist, "2026-07-07")
    assert scored["amazon_rank_momentum"] > 0
    assert "RANK_UP_7D" in scored["reason_codes"]
