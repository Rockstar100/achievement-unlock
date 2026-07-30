"""Momentum-centered scoring with reason codes (production v2)."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import pandas as pd

from transform.gold_builder import _rank_to_score, _rating_score

WEIGHTS = {
    "rank_momentum": 0.25,
    "search_momentum": 0.20,
    "cross_platform": 0.15,
    "review_velocity": 0.15,
    "discount": 0.10,
    "novelty": 0.10,
    "sentiment": 0.05,
}

BASELINE_WEIGHTS = {
    "rank": 0.40,
    "velocity": 0.20,
    "social": 0.20,
    "gtrends": 0.10,
    "mover": 0.05,
    "sources": 0.05,
}


def _tier(score: float) -> str:
    if score >= 80:
        return "breakout"
    if score >= 60:
        return "rising"
    if score >= 40:
        return "stable"
    return "declining"


def _rank_momentum(current: Optional[float], prior: Optional[float]) -> float:
    """Positive only when rank improved (lower rank number = better)."""
    if not current or current <= 0:
        return 0.0
    cur = float(current)
    prev = float(prior) if prior and prior > 0 else cur
    if cur <= prev:
        return max(0.0, math.log(prev + 1) - math.log(cur + 1))
    return 0.0


def _baseline_score(prod: Dict[str, Any], gtrends: Dict[str, Any]) -> float:
    """Marketplace strength score (aligned with gold_builder v1)."""
    am_rank = prod.get("amazon_rank")
    fk_rank = prod.get("flipkart_avg_rank")
    ranks = [r for r in (am_rank, fk_rank) if r not in (None, 0, 0.0)]
    best_rank = min(ranks) if ranks else None
    rank_score = _rank_to_score(best_rank)

    rank_vel = float(prod.get("amazon_rank_delta_1d") or prod.get("flipkart_rank_delta_7d") or 0)
    velocity_score = min(100.0, max(0.0, 50.0 + rank_vel * 2.0))

    rating = prod.get("amazon_rating") or prod.get("flipkart_rating")
    reviews = prod.get("amazon_review_count") or prod.get("flipkart_review_count")
    social_score = _rating_score(rating, reviews)

    gt_momentum = float(gtrends.get("gtrends_interest_delta_7d") or 0)
    gt_interest = float(gtrends.get("gtrends_category_interest") or 0)
    gt_score = min(100.0, max(0.0, 50.0 + gt_momentum * 2.0))
    if gt_interest:
        gt_score = max(gt_score, min(100.0, gt_interest))

    mover_bonus = 15.0 if prod.get("amazon_is_mover_shaker") else 0.0
    sources = str(prod.get("sources", "") or "").split("|")
    market_sources = [s for s in sources if s in ("amazon", "flipkart")]
    source_bonus = min(15.0, len(market_sources) * 7.5)

    score = (
        BASELINE_WEIGHTS["rank"] * rank_score
        + BASELINE_WEIGHTS["velocity"] * velocity_score
        + BASELINE_WEIGHTS["social"] * social_score
        + BASELINE_WEIGHTS["gtrends"] * gt_score
        + BASELINE_WEIGHTS["mover"] * mover_bonus
        + BASELINE_WEIGHTS["sources"] * (source_bonus / 15.0 * 100.0)
    )
    return round(min(100.0, max(0.0, score)), 2)


def _momentum_bonus(
    rank_momentum: float,
    search_momentum: float,
    cross_platform: float,
    review_velocity: float,
    discount_signal: float,
    novelty: float,
    sentiment: float,
) -> float:
    """0–25 point boost from momentum signals."""
    raw = (
        WEIGHTS["rank_momentum"] * min(rank_momentum, 1.0)
        + WEIGHTS["search_momentum"] * min(search_momentum, 1.0)
        + WEIGHTS["cross_platform"] * cross_platform
        + WEIGHTS["review_velocity"] * min(review_velocity, 1.0)
        + WEIGHTS["discount"] * discount_signal
        + WEIGHTS["novelty"] * novelty
        + WEIGHTS["sentiment"] * sentiment
    )
    return round(raw * 25.0, 2)


def _recommended_action(score: float, penalty: float, reasons: List[str]) -> str:
    if penalty >= 0.1:
        return "REVIEW_MANUALLY"
    if score >= 80 and "GOOGLE_BREAKOUT_QUERY" in reasons:
        return "BUY_TEST"
    if score >= 65:
        return "WATCHLIST"
    if score >= 45:
        return "MONITOR"
    return "IGNORE"


def score_product(
    prod: Dict[str, Any],
    gtrends: Dict[str, Any],
    hist_platform: pd.DataFrame,
    snapshot_date: str,
) -> Dict[str, Any]:
    """Score one canonical product for snapshot_date."""
    cid = prod.get("canonical_product_id") or prod.get("product_id")
    am_rank = prod.get("amazon_rank")
    fk_rank = prod.get("flipkart_avg_rank")
    rating = prod.get("amazon_rating") or prod.get("flipkart_rating")
    reviews = prod.get("amazon_review_count") or prod.get("flipkart_review_count") or 0
    discount = prod.get("discount_pct") or 0

    am_prior = fk_prior = None
    reviews_prior = None
    interest_prior = None
    if not hist_platform.empty and cid:
        hist = hist_platform[
            (hist_platform["canonical_product_id"].astype(str) == str(cid))
            & (hist_platform["snapshot_date"].astype(str) < str(snapshot_date))
        ]
        if not hist.empty:
            hist = hist.sort_values("snapshot_date")
            last = hist.iloc[-1]
            am_prior = last.get("amazon_rank") if "amazon_rank" in hist.columns else None
            fk_prior = last.get("flipkart_rank") if "flipkart_rank" in hist.columns else None
            reviews_prior = last.get("review_count") if "review_count" in hist.columns else None
            interest_prior = last.get("interest_index") if "interest_index" in hist.columns else None

    amazon_mom = _rank_momentum(am_rank, am_prior)
    flipkart_mom = _rank_momentum(fk_rank, fk_prior)
    rank_momentum = max(amazon_mom, flipkart_mom)

    interest = float(gtrends.get("gtrends_category_interest") or 0)
    interest_delta = float(gtrends.get("gtrends_interest_delta_7d") or 0)
    search_momentum = max(0.0, (interest - float(interest_prior or interest)) / 100.0)
    if interest_delta > 0:
        search_momentum = max(search_momentum, min(1.0, interest_delta / 50.0))

    has_am = am_rank not in (None, 0, 0.0)
    has_fk = fk_rank not in (None, 0, 0.0)
    cross_platform = 1.0 if has_am and has_fk else 0.5 if has_am or has_fk else 0.0

    review_velocity = max(0.0, float(reviews) - float(reviews_prior or reviews)) / 50.0
    discount_signal = min(float(discount or 0) / 100.0, 1.0)
    novelty = 1.0 if interest_delta >= 15 or prod.get("amazon_is_mover_shaker") else 0.0
    sentiment = 1.0 if float(rating or 0) >= 4.2 else 0.5 if float(rating or 0) >= 3.8 else 0.0

    penalty_pts = 10.0 if rating and float(rating) < 3.8 else 0.0

    baseline = _baseline_score(prod, gtrends)
    momentum = _momentum_bonus(
        rank_momentum, search_momentum, cross_platform,
        review_velocity, discount_signal, novelty, sentiment,
    )
    trend_score = round(max(0.0, min(100.0, baseline + momentum - penalty_pts)), 2)

    reasons: List[str] = []
    if rank_momentum > 0.05:
        reasons.append("RANK_UP_7D")
    if search_momentum > 0.08:
        reasons.append("SEARCH_DEMAND_UP")
    if novelty >= 1.0:
        reasons.append("GOOGLE_BREAKOUT_QUERY")
    if cross_platform >= 1.0:
        reasons.append("CROSS_PLATFORM_VISIBLE")
    if discount_signal >= 0.15:
        reasons.append("PRICE_DROP")
    if review_velocity >= 0.1:
        reasons.append("REVIEW_VELOCITY_UP")
    if penalty_pts > 0:
        reasons.append("LOW_RATING_PENALTY")

    reason_codes = "|".join(reasons)
    penalty = penalty_pts / 100.0
    action = _recommended_action(trend_score, penalty, reasons)
    confidence = round(min(0.99, 0.5 + 0.15 * cross_platform + 0.1 * len(reasons) + baseline / 200.0), 2)

    return {
        "trend_score": trend_score,
        "trend_score_v2": trend_score,
        "trend_score_baseline": baseline,
        "trend_momentum_bonus": momentum,
        "trend_velocity_7d": round(rank_momentum * 100, 2),
        "trend_velocity_14d": None,
        "trend_confidence": confidence,
        "penalty_score": penalty,
        "reason_codes": reason_codes,
        "recommended_action": action,
        "trend_tier": _tier(trend_score),
        "amazon_rank_momentum": round(amazon_mom, 4),
        "flipkart_rank_momentum": round(flipkart_mom, 4),
        "search_momentum": round(search_momentum, 4),
        "cross_platform_signal": cross_platform,
        "review_velocity_signal": round(review_velocity, 4),
        "discount_signal": round(discount_signal, 4),
        "novelty_signal": novelty,
        "sentiment_signal": sentiment,
    }
