{{ config(materialized='view') }}

WITH flipkart_raw AS (
    SELECT * FROM {{ ref('stg_flipkart_bestsellers') }}
),

cleaned AS (
    SELECT
        product_id,
        source,
        ingest_date,
        ingest_ts,
        marketplace,
        search_term,
        category,
        rank,
        rank_prev_day,
        (rank - rank_prev_day) AS rank_delta,
        replaceRegexpAll(product_title, '[^a-zA-Z0-9\\s]', '') AS clean_title,
        lower(trim(brand)) AS brand_raw,
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
    FROM flipkart_raw
)

SELECT
    product_id,
    'flipkart' AS source,
    ingest_date,
    ingest_ts,
    marketplace,
    search_term,
    category,
    rank,
    rank_prev_day,
    rank_delta,
    clean_title AS product_title,
    multiIf(
        brand_raw IN ('royal canin', 'royalcanin', 'royal-canine'), 'royal canin',
        brand_raw IN ('farmina', 'farmina pet foods'), 'farmina',
        brand_raw IN ('pedigree', 'pedigreedog'), 'pedigree',
        brand_raw IN ('whiskas', 'whiskascat'), 'whiskas',
        brand_raw IN ('drools', 'droolspetfood'), 'drools',
        brand_raw IN ('himalaya', 'himalayapet'), 'himalaya',
        positionCaseInsensitive(brand_raw, 'pedigree') > 0, 'pedigree',
        positionCaseInsensitive(brand_raw, 'royal canin') > 0, 'royal canin',
        positionCaseInsensitive(brand_raw, 'farmina') > 0, 'farmina',
        positionCaseInsensitive(brand_raw, 'whiskas') > 0, 'whiskas',
        positionCaseInsensitive(brand_raw, 'drools') > 0, 'drools',
        positionCaseInsensitive(brand_raw, 'himalaya') > 0, 'himalaya',
        brand_raw
    ) AS brand,
    price_inr,
    mrp_inr,
    discount_pct,
    rating,
    rating_delta,
    review_count,
    review_count_delta,
    seller,
    availability,
    product_url,
    image_url
FROM cleaned
WHERE product_id IS NOT NULL AND product_id != ''
