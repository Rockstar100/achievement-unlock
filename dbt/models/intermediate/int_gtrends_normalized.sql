{{ config(materialized='view') }}

WITH gtrends_raw AS (
    SELECT * FROM {{ ref('stg_gtrends') }}
),

category_aggregated AS (
    SELECT
        ingest_date,
        ingest_ts,
        category,
        avg(interest_score) AS avg_interest_score,
        avg(interest_score_prev_day) AS avg_interest_score_prev_day,
        avg(interest_score - interest_score_prev_day) AS avg_interest_delta,
        sum(if(is_rising = 1, 1, 0)) AS rising_keyword_count,
        groupArray(if(is_rising = 1, rising_query, '')) AS rising_queries_arr,
        groupArray(if(rising_score >= 5000, rising_query, '')) AS breakout_queries_arr
    FROM gtrends_raw
    GROUP BY ingest_date, ingest_ts, category
),

final AS (
    SELECT
        *,
        avg_interest_score AS interest_score_0_100,
        if(
            avg_interest_score_prev_day = 0, 0,
            (avg_interest_score - avg_interest_score_prev_day) / avg_interest_score_prev_day * 100
        ) AS interest_pct_change
    FROM category_aggregated
)

SELECT
    concat('gtrends_', category) AS category_id,
    'gtrends' AS source,
    ingest_date,
    ingest_ts,
    category,
    interest_score_0_100 AS gtrends_category_interest,
    avg_interest_delta AS gtrends_interest_delta_1d,
    round(avg_interest_delta, 2) AS gtrends_interest_delta_7d,
    arrayStringConcat(arrayFilter(x -> x != '', rising_queries_arr), ', ') AS gtrends_rising_queries,
    arrayStringConcat(arrayFilter(x -> x != '', breakout_queries_arr), ', ') AS gtrends_breakout_queries,
    rising_keyword_count
FROM final
