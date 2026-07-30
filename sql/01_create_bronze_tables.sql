-- ClickHouse bronze layer DDL for pet trend intelligence pipeline
-- Run: clickhouse-client --multiquery < sql/01_create_bronze_tables.sql

CREATE DATABASE IF NOT EXISTS default;

-- Amazon.in Best Sellers / Movers & Shakers
CREATE TABLE IF NOT EXISTS bronze_ecom_trends_amazon (
    ingest_date       Date,
    ingest_ts         DateTime,
    marketplace       LowCardinality(String),
    category          LowCardinality(String),
    subcategory       LowCardinality(String),
    rank              UInt16,
    rank_prev_day     UInt16,
    asin              String,
    product_title     String,
    brand             String,
    price_inr         Float64,
    mrp_inr           Float64,
    discount_pct      UInt8,
    rating            Float32,
    review_count      UInt32,
    is_mover_shaker   UInt8,
    rank_delta        Int16,
    product_url       String,
    image_url         String,
    _raw_json         String
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(ingest_date)
ORDER BY (ingest_date, category, rank);

-- Google Trends
CREATE TABLE IF NOT EXISTS bronze_ecom_trends_gtrends (
    ingest_date              Date,
    ingest_ts                DateTime,
    category                 LowCardinality(String),
    keyword                  String,
    interest_score           UInt8,
    interest_score_prev_day  UInt8,
    interest_delta           Int16,
    is_rising                UInt8,
    rising_query             String,
    rising_score             UInt32,
    related_topics_json      String,
    _raw_json                String
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(ingest_date)
ORDER BY (ingest_date, category, keyword);

-- Flipkart search rankings
CREATE TABLE IF NOT EXISTS bronze_ecom_trends_flipkart (
    ingest_date            Date,
    ingest_ts              DateTime,
    marketplace            LowCardinality(String),
    search_term            String,
    category               LowCardinality(String),
    rank                   UInt8,
    rank_prev_day          UInt8,
    rank_delta             Int16 DEFAULT 0,
    product_id             String,
    product_title          String,
    brand                  String,
    price_inr              Float64,
    mrp_inr                Float64,
    discount_pct           UInt8,
    rating                 Float32,
    rating_prev_day        Float32,
    rating_delta           Float32 DEFAULT 0,
    review_count           UInt32,
    review_count_prev_day  UInt32,
    seller                 String,
    availability           LowCardinality(String),
    product_url            String,
    image_url              String,
    _raw_json              String
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(ingest_date)
ORDER BY (ingest_date, search_term, rank);
