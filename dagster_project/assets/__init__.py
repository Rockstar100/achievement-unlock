"""Dagster bronze ingestion and gold transformation assets."""
from .bronze_amazon import amazon_bestsellers
from .bronze_flipkart import flipkart_products
from .bronze_gtrends import google_trends
from .gold_trending import gold_trending_products

__all__ = [
    "amazon_bestsellers",
    "flipkart_products",
    "google_trends",
    "gold_trending_products",
]
