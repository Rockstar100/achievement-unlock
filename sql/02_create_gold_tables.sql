-- Gold layer DDL (ClickHouse / reference schema for file-based gold tables)
-- Partitioned by snapshot_date; append daily snapshots (do not overwrite history).

CREATE TABLE IF NOT EXISTS gold_dim_product_canonical
(
    canonical_product_id String,
    product_cluster_id String,
    canonical_title String,
    brand String,
    species LowCardinality(String),
    category LowCardinality(String),
    subcategory String,
    life_stage LowCardinality(String),
    breed_size LowCardinality(String),
    form_factor LowCardinality(String),
    flavor String,
    functional_claim String,
    pack_size_value Nullable(Float64),
    pack_size_unit LowCardinality(String),
    price_per_kg_last Nullable(Float64),
    dog_cat_confidence Float32,
    taxonomy_confidence Float32,
    first_seen_date Date,
    last_seen_date Date,
    is_active UInt8
)
ENGINE = ReplacingMergeTree(last_seen_date)
ORDER BY canonical_product_id;

CREATE TABLE IF NOT EXISTS gold_fact_product_platform_daily
(
    snapshot_date Date,
    platform LowCardinality(String),
    platform_product_id String,
    canonical_product_id String,
    source_url String,
    rank_context LowCardinality(String),
    rank_keyword String,
    rank_position Nullable(UInt32),
    sponsored_flag UInt8,
    price Nullable(Float64),
    mrp Nullable(Float64),
    discount_pct Nullable(UInt8),
    rating Nullable(Float32),
    review_count Nullable(UInt32),
    availability_status LowCardinality(String),
    seller_name String,
    delivery_speed_bucket LowCardinality(String),
    crawl_status LowCardinality(String),
    source_connector LowCardinality(String),
    image_url String,
    brand String,
    canonical_title String,
    category LowCardinality(String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(snapshot_date)
ORDER BY (snapshot_date, platform, platform_product_id);

CREATE TABLE IF NOT EXISTS gold_fact_search_demand_daily
(
    snapshot_date Date,
    source LowCardinality(String),
    query String,
    geo LowCardinality(String),
    mapped_species LowCardinality(String),
    mapped_category LowCardinality(String),
    canonical_product_id String,
    interest_index Float32,
    related_query String,
    rising_value Float32,
    breakout_flag UInt8,
    confidence Float32
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(snapshot_date)
ORDER BY (snapshot_date, source, query);

CREATE TABLE IF NOT EXISTS gold_fact_trending_pet_products_daily
(
    snapshot_date Date,
    canonical_product_id String,
    canonical_title String,
    normalized_brand String,
    category LowCardinality(String),
    species LowCardinality(String),
    amazon_rank Nullable(UInt32),
    flipkart_rank Nullable(UInt32),
    amazon_rating Nullable(Float32),
    flipkart_rating Nullable(Float32),
    review_count Nullable(UInt32),
    interest_index Nullable(Float32),
    amazon_price_inr Nullable(Float64),
    flipkart_price_inr Nullable(Float64),
    image_url String,
    sources String,
    trend_score Float32,
    trend_score_v2 Float32,
    trend_velocity_7d Nullable(Float32),
    trend_velocity_14d Nullable(Float32),
    trend_confidence Float32,
    penalty_score Float32,
    reason_codes String,
    recommended_action LowCardinality(String),
    trend_tier LowCardinality(String),
    rank_position UInt32,
    computed_ts DateTime
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(snapshot_date)
ORDER BY (snapshot_date, rank_position);

-- Legacy snapshot (latest view for dashboards)
CREATE TABLE IF NOT EXISTS gold_dim_trending_pet_products
(
    product_id String,
    canonical_product_id String,
    canonical_title String,
    normalized_brand String,
    category LowCardinality(String),
    trend_score Float32,
    trend_score_v2 Float32,
    trend_tier LowCardinality(String),
    trend_velocity_7d Nullable(Float32),
    trend_confidence Float32,
    penalty_score Float32,
    reason_codes String,
    recommended_action LowCardinality(String),
    sources String,
    computed_date Date,
    computed_ts DateTime,
    rank_position UInt32
)
ENGINE = ReplacingMergeTree(computed_ts)
ORDER BY product_id;
