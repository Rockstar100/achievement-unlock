"""Load YAML configuration files for scrapers."""
from pathlib import Path
from typing import Any, Dict

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_yaml(name: str) -> Dict[str, Any]:
    path = CONFIG_DIR / name
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_settings() -> Dict[str, Any]:
    return load_yaml("settings.yaml")


def load_amazon_categories() -> Dict[str, Any]:
    return load_yaml("amazon_categories.yaml")


def load_amazon_us_categories() -> Dict[str, Any]:
    """Global supplementary source — amazon.com, not part of the India pipeline."""
    return load_yaml("amazon_us_categories.yaml")


def load_gtrends_keywords() -> Dict[str, Any]:
    return load_yaml("gtrends_keywords.yaml")


def load_flipkart_search_terms() -> Dict[str, Any]:
    return load_yaml("flipkart_search_terms.yaml")


def load_tiktok_shop_us_keywords() -> Dict[str, Any]:
    """Global supplementary source — TikTok Shop US, not part of the India pipeline."""
    return load_yaml("tiktok_shop_us_keywords.yaml")
