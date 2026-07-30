{{ config(materialized='view') }}

WITH raw_data AS (
    SELECT *
    FROM {{ source('bronze', 'ecom_trends_flipkart') }}
    WHERE ingest_date = today()
)

SELECT
    product_id,
    'flipkart' AS source,
    ingest_date,
    ingest_ts,
    marketplace,
    search_term,
    category,
    toInt32(rank) AS rank,
    toInt32(rank_prev_day) AS rank_prev_day,
    (toInt32(rank_prev_day) - toInt32(rank)) AS rank_delta,
    product_title,
    brand,
    price_inr,
    mrp_inr,
    discount_pct,
    rating,
    rating_prev_day,
    (rating - rating_prev_day) AS rating_delta,
    review_count,
    review_count_prev_day,
    (review_count - review_count_prev_day) AS review_count_delta,
    seller,
    availability,
    product_url,
    image_url
FROM raw_data
