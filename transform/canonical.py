"""Canonical product identity helpers (species, IDs, taxonomy)."""
from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any, Dict, Optional

SPECIES_DOG = "dog"
SPECIES_CAT = "cat"
SPECIES_BOTH = "both"


def infer_species(title: str = "", category: str = "") -> str:
    t = (title or "").lower()
    c = (category or "").lower().replace("_", " ")
    dog = bool(re.search(r"\b(dog|dogs|puppy|puppies|canine)\b", t))
    cat = bool(re.search(r"\b(cat|cats|kitten|kittens|feline|kitty)\b", t))
    if dog and cat:
        return SPECIES_BOTH
    if dog or "dog" in c:
        return SPECIES_DOG
    if cat or "cat" in c:
        return SPECIES_CAT
    return SPECIES_DOG if "dog" in c else SPECIES_CAT if "cat" in c else SPECIES_BOTH


def canonical_product_id(match_key: str, brand: str = "", title: str = "") -> str:
    blob = (match_key or f"{brand}|{title}").strip().lower()
    if not blob:
        blob = title or brand or "unknown"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_canonical_record(prod: Dict[str, Any], snapshot_date: Optional[date] = None) -> Dict[str, Any]:
    """Map merged marketplace product dict to gold_dim_product_canonical row."""
    today = snapshot_date or date.today()
    title = str(prod.get("canonical_title", ""))
    brand = str(prod.get("normalized_brand", "") or "")
    category = str(prod.get("category", "") or "")
    match_key = str(prod.get("match_key", "") or "")
    cid = prod.get("canonical_product_id") or canonical_product_id(match_key, brand, title)
    species = infer_species(title, category)
    return {
        "canonical_product_id": cid,
        "product_cluster_id": cid,
        "canonical_title": title,
        "brand": brand,
        "species": species,
        "category": category,
        "subcategory": prod.get("subcategory") or "",
        "life_stage": "",
        "breed_size": "",
        "form_factor": "",
        "flavor": "",
        "functional_claim": "",
        "pack_size_value": None,
        "pack_size_unit": "",
        "price_per_kg_last": None,
        "dog_cat_confidence": 0.95 if species in (SPECIES_DOG, SPECIES_CAT) else 0.75,
        "taxonomy_confidence": 0.85,
        "first_seen_date": str(prod.get("first_seen_date") or today),
        "last_seen_date": str(today),
        "is_active": True,
    }
