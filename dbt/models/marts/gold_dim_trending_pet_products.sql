{{ config(materialized='table') }}

WITH amazon_data AS (
    SELECT
        product_id,
        ingest_date,
        product_title AS canonical_title,
        brand AS normalized_brand,
        category,
        subcategory,
        rank AS amazon_rank,
        lagInFrame(rank) OVER (PARTITION BY product_id ORDER BY ingest_date) AS amazon_rank_prev_day,
        (lagInFrame(rank) OVER (PARTITION BY product_id ORDER BY ingest_date) - rank) AS amazon_rank_delta_1d,
        avg(rank) OVER (
            PARTITION BY product_id ORDER BY ingest_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS amazon_rank_7d_avg,
        is_mover_shaker AS amazon_is_mover_shaker,
        rating AS amazon_rating,
        review_count AS amazon_review_count,
        price_inr AS amazon_price_inr
    FROM {{ ref('int_amazon_normalized') }}
    WHERE ingest_date >= today() - 7
),

gtrends_data AS (
    SELECT
        category,
        ingest_date,
        gtrends_category_interest,
        gtrends_interest_delta_7d,
        gtrends_rising_queries,
        gtrends_breakout_queries
    FROM {{ ref('int_gtrends_normalized') }}
    WHERE ingest_date >= today() - 7
),

flipkart_data AS (
    SELECT
        product_id,
        ingest_date,
        product_title AS canonical_title,
        brand AS normalized_brand,
        category,
        avg(rank) OVER (
            PARTITION BY product_id ORDER BY ingest_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS flipkart_avg_rank_7d,
        avg(rank - lagInFrame(rank) OVER (PARTITION BY product_id ORDER BY ingest_date)) OVER (
            PARTITION BY product_id ORDER BY ingest_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS flipkart_avg_rank_delta_7d,
        avg(rating - lagInFrame(rating) OVER (PARTITION BY product_id ORDER BY ingest_date)) OVER (
            PARTITION BY product_id ORDER BY ingest_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS flipkart_rating_delta_7d,
        avg(
            (review_count - lagInFrame(review_count) OVER (PARTITION BY product_id ORDER BY ingest_date))
            / nullIf(lagInFrame(review_count) OVER (PARTITION BY product_id ORDER BY ingest_date), 0)
        ) OVER (
            PARTITION BY product_id ORDER BY ingest_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS flipkart_review_velocity_7d
    FROM {{ ref('int_flipkart_normalized') }}
    WHERE ingest_date >= today() - 7
),

combined AS (
    SELECT
        coalesce(a.product_id, f.product_id) AS product_id,
        coalesce(a.canonical_title, f.canonical_title) AS canonical_title,
        coalesce(a.normalized_brand, f.normalized_brand) AS normalized_brand,
        coalesce(a.category, f.category, g.category) AS category,
        a.subcategory,
        a.amazon_rank,
        a.amazon_rank_7d_avg,
        a.amazon_rank_delta_1d,
        a.amazon_is_mover_shaker,
        a.amazon_rating,
        a.amazon_review_count,
        a.amazon_price_inr,
        g.gtrends_category_interest,
        g.gtrends_interest_delta_7d,
        g.gtrends_rising_queries,
        g.gtrends_breakout_queries,
        f.flipkart_avg_rank_7d AS flipkart_avg_rank,
        f.flipkart_avg_rank_delta_7d AS flipkart_rank_delta_7d,
        f.flipkart_rating_delta_7d AS flipkart_rating_delta_1d,
        f.flipkart_review_velocity_7d AS flipkart_review_velocity
    FROM amazon_data a
    FULL OUTER JOIN gtrends_data g ON lower(a.category) = lower(g.category)
        AND a.ingest_date = g.ingest_date
    FULL OUTER JOIN flipkart_data f ON a.product_id = f.product_id
        AND a.ingest_date = f.ingest_date
),

scored AS (
    SELECT
        *,
        if(amazon_rank IS NOT NULL, least(100, greatest(0, 50 + (25 - amazon_rank) * 2)), 50) AS amazon_rank_score,
        if(amazon_rank_delta_1d IS NOT NULL, least(100, greatest(0, 50 + amazon_rank_delta_1d * 2)), 50) AS amazon_rank_velocity_score,
        if(amazon_is_mover_shaker = 1, 20, 0) AS amazon_mover_shaker_bonus,
        if(gtrends_category_interest IS NOT NULL, least(100, greatest(0, gtrends_category_interest * 1.2)), 50) AS gtrends_interest_score,
        if(gtrends_interest_delta_7d IS NOT NULL, least(100, greatest(0, 50 + gtrends_interest_delta_7d * 2)), 50) AS gtrends_momentum_score,
        if(gtrends_breakout_queries != '', 15, 0) AS gtrends_breakout_bonus,
        if(flipkart_avg_rank IS NOT NULL, least(100, greatest(0, 50 + (25 - flipkart_avg_rank) * 2)), 50) AS flipkart_rank_score,
        if(flipkart_rank_delta_7d IS NOT NULL, least(100, greatest(0, 50 + flipkart_rank_delta_7d * 2)), 50) AS flipkart_rank_velocity_score,
        if(flipkart_rating_delta_1d IS NOT NULL, least(100, greatest(0, 50 + flipkart_rating_delta_1d * 25)), 50) AS flipkart_rating_velocity_score,
        if(flipkart_review_velocity IS NOT NULL, least(100, greatest(0, 50 + least(flipkart_review_velocity * 100, 50))), 50) AS flipkart_review_velocity_score
    FROM combined
),

final_scores AS (
    SELECT
        *,
        (
            0.35 * coalesce(amazon_rank_velocity_score, flipkart_rank_velocity_score, 50)
            + 0.25 * coalesce(gtrends_momentum_score, 50)
            + 0.20 * coalesce(flipkart_rating_velocity_score, 50)
            + 0.15 * coalesce(amazon_mover_shaker_bonus, 0)
            + 0.05 * (
                (if(amazon_rank IS NOT NULL, 1, 0)
                + if(gtrends_category_interest IS NOT NULL, 1, 0)
                + if(flipkart_avg_rank IS NOT NULL, 1, 0)) * 33.33
            )
        ) AS trend_score_raw
    FROM scored
)

SELECT
    product_id,
    canonical_title,
    normalized_brand,
    category,
    subcategory,
    amazon_rank,
    amazon_rank_7d_avg,
    amazon_rank_delta_1d,
    amazon_is_mover_shaker,
    amazon_rating,
    amazon_review_count,
    amazon_price_inr,
    gtrends_category_interest,
    gtrends_interest_delta_7d,
    gtrends_rising_queries,
    gtrends_breakout_queries,
    flipkart_avg_rank,
    flipkart_rank_delta_7d,
    flipkart_rating_delta_1d,
    flipkart_review_velocity,
    round(least(100, greatest(0, trend_score_raw)), 2) AS trend_score,
    multiIf(
        trend_score_raw >= 80, 'breakout',
        trend_score_raw >= 60, 'rising',
        trend_score_raw >= 40, 'stable',
        'declining'
    ) AS trend_tier,
    row_number() OVER (PARTITION BY category ORDER BY trend_score_raw DESC) AS rank_position,
    today() AS computed_date,
    now() AS computed_ts,
    arrayFilter(
        x -> x != '',
        [
            if(amazon_rank IS NOT NULL, 'amazon', ''),
            if(gtrends_category_interest IS NOT NULL, 'gtrends', ''),
            if(flipkart_avg_rank IS NOT NULL, 'flipkart', '')
        ]
    ) AS sources
FROM final_scores
WHERE trend_score_raw IS NOT NULL
ORDER BY trend_score DESC
