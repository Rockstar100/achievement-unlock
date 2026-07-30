"""Central logging setup for scrapers and scripts."""
from __future__ import annotations

import logging
import os
import sys


def setup_logging(name: str | None = None) -> logging.Logger:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        root.addHandler(handler)
    root.setLevel(level)

    return logging.getLogger(name or "pet_trends")


def is_production() -> bool:
    return os.getenv("ENVIRONMENT", "development").lower() in ("production", "prod")
