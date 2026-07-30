{{ config(materialized='view') }}

WITH amazon_raw AS (
    SELECT * FROM {{ ref('stg_amazon_bestsellers') }}
),

cleaned AS (
    SELECT
        product_id,
        source,
        ingest_date,
        ingest_ts,
        marketplace,
        category,
        subcategory,
        rank,
        rank_prev_day,
        rank_delta,
        replaceRegexpAll(product_title, '[^a-zA-Z0-9\\s]', '') AS clean_title,
        lower(trim(brand)) AS brand_raw,
        price_inr,
        mrp_inr,
        discount_pct,
        rating,
        review_count,
        is_mover_shaker,
        product_url,
        image_url
    FROM amazon_raw
),

brand_normalized AS (
    SELECT
        *,
        multiIf(
            brand_raw IN ('royal canin', 'royalcanin', 'royal-canine'), 'royal canin',
            brand_raw IN ('farmina', 'farmina pet foods'), 'farmina',
            brand_raw IN ('pedigree', 'pedigreedog'), 'pedigree',
            brand_raw IN ('whiskas', 'whiskascat'), 'whiskas',
            brand_raw IN ('drools', 'droolspetfood'), 'drools',
            brand_raw IN ('himalaya', 'himalayapet'), 'himalaya',
            brand_raw IN ('meo', 'meo cat food', 'meo&me'), 'meo',
            brand_raw IN ('simparico', 'simparicochewables'), 'simparico',
            positionCaseInsensitive(brand_raw, 'pedigree') > 0, 'pedigree',
            positionCaseInsensitive(brand_raw, 'royal canin') > 0, 'royal canin',
            positionCaseInsensitive(brand_raw, 'farmina') > 0, 'farmina',
            positionCaseInsensitive(brand_raw, 'whiskas') > 0, 'whiskas',
            positionCaseInsensitive(brand_raw, 'drools') > 0, 'drools',
            positionCaseInsensitive(brand_raw, 'himalaya') > 0, 'himalaya',
            brand_raw
        ) AS normalized_brand
    FROM cleaned
)

SELECT
    product_id,
    source,
    ingest_date,
    ingest_ts,
    marketplace,
    category,
    subcategory,
    rank,
    rank_prev_day,
    rank_delta,
    clean_title AS product_title,
    normalized_brand AS brand,
    price_inr,
    mrp_inr,
    discount_pct,
    rating,
    review_count,
    is_mover_shaker,
    product_url,
    image_url
FROM brand_normalized
WHERE normalized_brand IS NOT NULL AND normalized_brand != ''
