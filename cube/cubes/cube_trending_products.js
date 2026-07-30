cube(`cube_trending_products`, {
  sql: `SELECT * FROM gold_dim_trending_pet_products`,

  measures: {
    count: {
      type: `count`,
      description: `Number of trending products`,
    },
    avgTrendScore: {
      sql: `trend_score`,
      type: `avg`,
      description: `Average composite trend score`,
    },
    maxTrendScore: {
      sql: `trend_score`,
      type: `max`,
      description: `Highest trend score`,
    },
    minRankPosition: {
      sql: `rank_position`,
      type: `min`,
      description: `Best rank within category`,
    },
    breakoutCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.trend_tier = 'breakout'` }],
      description: `Products in breakout tier`,
    },
    risingCount: {
      type: `count`,
      filters: [{ sql: `${CUBE}.trend_tier = 'rising'` }],
      description: `Products in rising tier`,
    },
  },

  dimensions: {
    productId: {
      sql: `product_id`,
      type: `string`,
      primaryKey: true,
    },
    canonicalTitle: {
      sql: `canonical_title`,
      type: `string`,
    },
    brand: {
      sql: `normalized_brand`,
      type: `string`,
    },
    category: {
      sql: `category`,
      type: `string`,
    },
    subcategory: {
      sql: `subcategory`,
      type: `string`,
    },
    trendTier: {
      sql: `trend_tier`,
      type: `string`,
    },
    trendScore: {
      sql: `trend_score`,
      type: `number`,
    },
    rankPosition: {
      sql: `rank_position`,
      type: `number`,
    },
    computedDate: {
      sql: `computed_date`,
      type: `time`,
    },
    amazonRank: {
      sql: `amazon_rank`,
      type: `number`,
    },
    flipkartAvgRank: {
      sql: `flipkart_avg_rank`,
      type: `number`,
    },
    gtrendsInterest: {
      sql: `gtrends_category_interest`,
      type: `number`,
    },
    isMoverShaker: {
      sql: `amazon_is_mover_shaker`,
      type: `boolean`,
    },
  },

  preAggregations: {
    dailyByCategory: {
      measures: [count, avgTrendScore, breakoutCount, risingCount],
      dimensions: [category, trendTier, computedDate],
      timeDimension: computedDate,
      granularity: `day`,
      refreshKey: {
        every: `1 hour`,
      },
    },
  },
});
