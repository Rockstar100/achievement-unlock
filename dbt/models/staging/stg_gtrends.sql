{{ config(materialized='view') }}

WITH raw_data AS (
    SELECT *
    FROM {{ source('bronze', 'ecom_trends_gtrends') }}
    WHERE ingest_date = today()
)

SELECT
    category,
    keyword,
    ingest_date,
    ingest_ts,
    interest_score,
    interest_score_prev_day,
    (interest_score - interest_score_prev_day) AS interest_delta,
    is_rising,
    rising_query,
    rising_score,
    CASE
        WHEN rising_score >= 5000 THEN 'breakout'
        ELSE 'rising'
    END AS rising_category,
    related_topics_json
FROM raw_data
WHERE category IN (
    'dog_food', 'cat_food', 'pet_toys', 'grooming',
    'beds_accessories', 'health_wellness', 'collars_leashes',
    'training_behavior', 'training'
)
