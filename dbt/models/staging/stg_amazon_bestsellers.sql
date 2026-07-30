{{ config(materialized='view') }}

WITH raw_data AS (
    SELECT *
    FROM {{ source('bronze', 'ecom_trends_amazon') }}
    WHERE ingest_date = today()
)

SELECT
    asin AS product_id,
    'amazon' AS source,
    ingest_date,
    ingest_ts,
    marketplace,
    category,
    subcategory,
    toInt32(rank) AS rank,
    toInt32(rank_prev_day) AS rank_prev_day,
    (toInt32(rank_prev_day) - toInt32(rank)) AS rank_delta,
    product_title,
    brand,
    price_inr,
    mrp_inr,
    discount_pct,
    rating,
    review_count,
    is_mover_shaker,
    product_url,
    image_url
FROM raw_data
