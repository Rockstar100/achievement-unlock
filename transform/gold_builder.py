"""
Build gold trending products table from bronze CSV files.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from scrapers.filters.pet_filter import filter_pet_records, is_pet_product
from scrapers.flipkart.client import FlipkartScraper

BRAND_MAP = {
    "royal canin": "royal canin",
    "royalcanin": "royal canin",
    "farmina": "farmina",
    "pedigree": "pedigree",
    "whiskas": "whiskas",
    "drools": "drools",
    "himalaya": "himalaya",
    "me-o": "me-o",
    "meo": "me-o",
    "purepet": "purepet",
    "meat up": "meat up",
    "chappi": "chappi",
    "sheba": "sheba",
    "fancy feast": "fancy feast",
    "purina": "purina",
    "kong": "kong",
    "beaphar": "beaphar",
    "jerhigh": "jerhigh",
    "amazon basics": "amazon basics",
    "amazonbasics": "amazon basics",
}

CATEGORY_ALIASES = {
    # Keys are matched against `raw` in _normalize_category, which has already
    # had "&" replaced with "and" and commas/whitespace collapsed — keys must
    # be in that same post-normalized form or the lookup silently never hits.
    "dog food": "dog_food",
    "cat food": "cat_food",
    "dog toys": "dog_toys",
    "cat toys": "cat_toys",
    "pet grooming": "grooming",
    "beds and accessories": "beds_accessories",
    "health and wellness": "health_wellness",
    "collars leashes and harnesses": "collars_leashes",
    "collars and leashes": "collars_leashes",
    "training and behavior": "training",
}

# Title patterns → canonical category (order matters: more specific first)
CATEGORY_PATTERNS: List[Tuple[str, str]] = [
    (r"\b(dog|puppy)\b.*\b(food|treat|meal|kibble|gravy)\b", "dog_food"),
    (r"\b(food|treat|meal|kibble|gravy)\b.*\b(dog|puppy)\b", "dog_food"),
    (r"\b(cat|kitten)\b.*\b(food|treat|meal|kibble|gravy)\b", "cat_food"),
    (r"\b(food|treat|meal|kibble|gravy)\b.*\b(cat|kitten)\b", "cat_food"),
    (r"\b(dog|puppy)\b.*\b(toy|toys|chew|tunnel|ball)\b", "dog_toys"),
    (r"\b(toy|toys|chew|tunnel|ball)\b.*\b(dog|puppy)\b", "dog_toys"),
    (r"\b(cat|kitten)\b.*\b(toy|toys|catnip|scratch|tunnel|ball)\b", "cat_toys"),
    (r"\b(toy|toys|catnip|scratch|tunnel|ball)\b.*\b(cat|kitten)\b", "cat_toys"),
    (r"\b(shampoo|conditioner|brush|groom|nail\s*cutter|nail\s*clipper|deshedding)\b", "grooming"),
    (r"\b(flea|tick|deworm|supplement|vitamin|joint)\b", "health_wellness"),
    (r"\b(collar|leash|harness)\b", "collars_leashes"),
    (r"\b(bed|crate|carrier|kennel)\b", "beds_accessories"),
    (r"\b(training\s*pad|training\s*treat|clicker|anti[\s-]?bark)\b", "training"),
    (r"\b(litter|litter\s*box)\b", "health_wellness"),
    (r"\b(dog|puppy)\b", "dog_food"),
    (r"\b(cat|kitten)\b", "cat_food"),
]


def _normalize_brand(brand: str, title: str = "") -> str:
    blob = f"{brand or ''} {title or ''}".strip().lower()
    blob = blob.replace("®", "").replace("™", "")
    if not blob:
        return ""
    # Longer keys first
    for key, val in sorted(BRAND_MAP.items(), key=lambda kv: -len(kv[0])):
        if key in blob:
            return val
    brand_clean = re.sub(r"[^a-z0-9\s\-]", "", (brand or "").strip().lower())
    brand_clean = brand_clean.strip()
    if brand_clean and brand_clean not in ("meat", "amazon", "p", "for", "pet", "the"):
        return brand_clean
    first = (title or "").split()[0].lower() if title else ""
    first = re.sub(r"[^a-z0-9\-]", "", first)
    if first in ("pet", "the", "for", "buy"):
        return ""
    return first


def _normalize_category(category: str, title: str = "") -> str:
    raw = str(category or "").strip().lower().replace("&", "and")
    raw = re.sub(r"[\s,]+", " ", raw).strip()
    key = raw.replace(" ", "_")
    known = {
        "dog_food", "cat_food", "dog_toys", "cat_toys", "grooming",
        "beds_accessories", "health_wellness", "collars_leashes", "training",
    }

    def _prefer_title(listing: str, inferred: str) -> str:
        if not inferred or inferred == listing:
            return listing
        # Amazon often mis-buckets shampoo/toys under food lists
        if listing in ("dog_food", "cat_food", "dog_toys", "cat_toys") and inferred != listing:
            return inferred
        return listing

    if key in known:
        return _prefer_title(key, _infer_category_from_title(title))

    alias = CATEGORY_ALIASES.get(raw)
    if alias:
        return _prefer_title(alias, _infer_category_from_title(title))

    inferred = _infer_category_from_title(title)
    return inferred or key or "unknown"


def _infer_category_from_title(title: str) -> str:
    t = (title or "").lower()
    if not t:
        return ""
    # Disambiguate dog vs cat when both appear (use earlier / more frequent signal)
    dog_n = len(re.findall(r"\b(dog|dogs|puppy|puppies)\b", t))
    cat_n = len(re.findall(r"\b(cat|cats|kitten|kittens|kitty|feline)\b", t))
    for pattern, cat in CATEGORY_PATTERNS:
        if not re.search(pattern, t):
            continue
        if cat in ("dog_toys", "cat_toys") and dog_n and cat_n:
            return "cat_toys" if cat_n >= dog_n else "dog_toys"
        if cat in ("dog_food", "cat_food") and dog_n and cat_n:
            return "cat_food" if cat_n >= dog_n else "dog_food"
        return cat
    return ""


def _tier(score: float) -> str:
    if score >= 80:
        return "breakout"
    if score >= 60:
        return "rising"
    if score >= 40:
        return "stable"
    return "declining"


def _rank_to_score(rank: Optional[float]) -> float:
    if rank is None or rank <= 0:
        return 35.0
    return max(0.0, min(100.0, 100.0 - (float(rank) - 1.0) * 2.5))


def _rating_score(rating: Optional[float], reviews: Optional[float]) -> float:
    r = float(rating or 0)
    n = float(reviews or 0)
    if r <= 0:
        return 35.0
    base = (r / 5.0) * 70.0
    volume = min(30.0, (n ** 0.5) / 2.0)
    return min(100.0, base + volume)


def _tokens(text: str) -> List[str]:
    text = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    stop = {
        "with", "and", "for", "the", "pack", "adult", "dry", "wet", "food",
        "ml", "kg", "gm", "g", "free", "buy", "get", "of", "in", "by",
    }
    return [t for t in text.split() if len(t) > 2 and t not in stop]


def _match_key(title: str, brand: str = "") -> str:
    """Stable key for cross-marketplace / near-duplicate matching."""
    brand_n = _normalize_brand(brand, title)
    toks = _tokens(title)
    # Prefer brand + first distinctive tokens
    core = []
    if brand_n:
        core.append(brand_n.replace(" ", ""))
    for t in toks:
        if brand_n and t in brand_n:
            continue
        core.append(t)
        if len(core) >= 5:
            break
    return " ".join(core)


def _token_overlap(a: str, b: str) -> float:
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", str(title or "")).strip()
    t = t.replace("®", "").replace("™", "").replace("\ufffd", "")
    # Drop trailing truncation artifacts
    t = re.sub(r"\|?\s*(Prom|Nut|A|Reduc|I)\s*$", "", t).strip(" |")
    return t


def _clean_subcategory(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() in ("", "nan", "none", "null"):
        return ""
    return s


def _clean_url(value: Any) -> str:
    s = str(value or "").strip()
    if s.lower() in ("", "nan", "none", "null"):
        return ""
    return s


def _clean_image_url(value: Any) -> str:
    """Return a product image URL only when it looks like a real http(s) image."""
    url = _clean_url(value)
    if not url.startswith("http"):
        return ""
    lower = url.lower()
    if any(bad in lower for bad in ("placeholder", "no-image", "blank.gif", "data:image")):
        return ""
    return url


def _primary_image_url(prod: Dict[str, Any]) -> str:
    """Prefer Amazon image, then Flipkart."""
    for key in ("amazon_image_url", "flipkart_image_url"):
        img = _clean_image_url(prod.get(key))
        if img:
            return img
    return ""


def _amazon_asin(prod: Dict[str, Any]) -> str:
    asin = str(prod.get("amazon_asin") or "").strip()
    if asin:
        return asin
    pid = str(prod.get("product_id", "")).strip()
    if pid.startswith("B"):
        return pid
    return ""


def _flipkart_pid(prod: Dict[str, Any]) -> str:
    url = str(prod.get("flipkart_url") or prod.get("product_url") or "")
    pid = FlipkartScraper.flipkart_pid(url)
    if pid:
        return pid
    fk_id = str(prod.get("flipkart_product_id") or prod.get("product_id") or "").strip()
    if len(fk_id) == 32 and all(c in "0123456789abcdef" for c in fk_id.lower()):
        return ""
    if fk_id and not fk_id.startswith("B"):
        return fk_id
    return ""


def _should_fuzzy_merge(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Merge near-duplicates without collapsing distinct marketplace listings."""
    a_asin, b_asin = _amazon_asin(a), _amazon_asin(b)
    if a_asin and b_asin and a_asin != b_asin:
        return False
    a_fk, b_fk = _flipkart_pid(a), _flipkart_pid(b)
    if a_fk and b_fk and a_fk != b_fk:
        return False
    title_a = a.get("canonical_title", "")
    title_b = b.get("canonical_title", "")
    brand = a.get("normalized_brand", "")
    if brand and brand != b.get("normalized_brand"):
        return False
    return _token_overlap(title_a, title_b) >= 0.55


def _dedupe_flipkart_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse repeated Flipkart listings scraped across search terms."""
    merged: Dict[str, Dict[str, Any]] = {}
    fallback: List[Dict[str, Any]] = []
    for row in rows:
        pid = FlipkartScraper.flipkart_pid(str(row.get("product_url", "")))
        if not pid:
            fallback.append(row)
            continue
        row = {**row, "product_id": pid, "flipkart_product_id": pid}
        if pid not in merged:
            merged[pid] = row
            continue
        existing = merged[pid]
        if int(row.get("rank") or 999) < int(existing.get("rank") or 999):
            merged[pid] = _merge_product(row, existing)
        else:
            merged[pid] = _merge_product(existing, row)
    return list(merged.values()) + fallback


def _gold_identity_fields(prod: Dict[str, Any]) -> Dict[str, Any]:
    """Marketplace IDs, URLs, and images for product identification."""
    fields: Dict[str, Any] = {
        "amazon_asin": "",
        "amazon_url": "",
        "amazon_image_url": "",
        "flipkart_product_id": "",
        "flipkart_url": "",
        "flipkart_image_url": "",
        "image_url": "",
    }

    asin = str(prod.get("amazon_asin") or "").strip()
    if not asin and str(prod.get("product_id", "")).startswith("B"):
        asin = str(prod.get("product_id", "")).strip()
    if asin:
        fields["amazon_asin"] = asin

    fk_id = _flipkart_pid(prod)
    if not fk_id:
        pid = str(prod.get("product_id", "")).strip()
        if pid and not pid.startswith("B") and len(pid) == 32 and all(
            c in "0123456789abcdef" for c in pid.lower()
        ):
            fk_id = pid
    if fk_id:
        fields["flipkart_product_id"] = fk_id

    fields["amazon_url"] = _clean_url(prod.get("amazon_url"))
    fields["flipkart_url"] = _clean_url(prod.get("flipkart_url"))
    fields["amazon_image_url"] = _clean_image_url(prod.get("amazon_image_url"))
    fields["flipkart_image_url"] = _clean_image_url(prod.get("flipkart_image_url"))
    fields["image_url"] = _primary_image_url(prod)
    return fields


def _category_key(category: str) -> str:
    return _normalize_category(category)


def _gtrends_lookup(
    category: str, gtrends_by_category: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    cat_key = _category_key(category)
    if cat_key in gtrends_by_category:
        return gtrends_by_category[cat_key]
    # Exact-ish alias only (avoid loose substring matches attaching wrong trends)
    for k, v in gtrends_by_category.items():
        if k.replace("_", "") == cat_key.replace("_", ""):
            return v
    return {}


def _resolve_gold_product_id(prod: Dict[str, Any]) -> str:
    asin = _amazon_asin(prod)
    if asin:
        return asin
    fk = _flipkart_pid(prod)
    if fk:
        return fk
    return str(prod.get("product_id", "")).strip()


def _merge_product(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Merge marketplace rows; prefer richer Amazon fields when present."""
    out = dict(existing)
    for k, v in incoming.items():
        if k in ("product_id", "match_key", "sources"):
            continue
        if k in ("amazon_asin", "flipkart_product_id"):
            if not v:
                continue
            if k == "amazon_asin" and out.get(k) and out[k] != v:
                continue
            if k == "flipkart_product_id" and out.get(k) and out[k] != v:
                continue
            out[k] = v
            continue
        if v in (None, "", 0, 0.0):
            continue
        # Prefer longer title
        if k == "canonical_title":
            if len(str(v)) > len(str(out.get(k, ""))):
                out[k] = v
            continue
        if k in ("amazon_rank", "flipkart_avg_rank", "rank"):
            cur = out.get(k)
            try:
                cur_f = float(cur) if cur not in (None, "", 0, 0.0) else None
                new_f = float(v) if v not in (None, "", 0, 0.0) else None
            except (TypeError, ValueError):
                cur_f, new_f = None, None
            if new_f is not None and (cur_f is None or new_f < cur_f):
                out[k] = v
            continue
        # Prefer non-unknown category from title inference already applied
        if k == "category" and out.get(k) and out[k] != "unknown":
            continue
        if k not in out or out[k] in (None, "", 0, 0.0):
            out[k] = v
    sources = list(dict.fromkeys(existing.get("sources", []) + incoming.get("sources", [])))
    out["sources"] = sources
    out["product_id"] = (
        _resolve_gold_product_id(out)
        or _resolve_gold_product_id(incoming)
        or out.get("product_id")
        or incoming.get("product_id")
    )
    return out


def _dedupe_products(products: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Collapse near-duplicates by match_key and high title overlap + brand."""
    by_key: Dict[str, str] = {}
    merged: Dict[str, Dict[str, Any]] = {}

    for pid, prod in products.items():
        mk = prod.get("match_key") or _match_key(
            prod.get("canonical_title", ""), prod.get("normalized_brand", "")
        )
        prod["match_key"] = mk

        target = by_key.get(mk)
        if target:
            merged[target] = _merge_product(merged[target], {**prod, "product_id": pid, "sources": prod.get("sources", [])})
            continue

        # Fuzzy: same brand + high token overlap
        brand = prod.get("normalized_brand", "")
        title = prod.get("canonical_title", "")
        found = None
        for other_pid, other in merged.items():
            if _should_fuzzy_merge(prod, other):
                found = other_pid
                break
        if found:
            merged[found] = _merge_product(
                merged[found], {**prod, "product_id": pid, "sources": prod.get("sources", [])}
            )
            by_key[mk] = found
        else:
            merged[pid] = {**prod, "product_id": pid}
            by_key[mk] = pid

    return merged


def build_gold_from_bronze(
    amazon_df: pd.DataFrame,
    gtrends_df: pd.DataFrame,
    flipkart_df: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """Transform bronze DataFrames into gold trending product records."""
    today = date.today()
    cutoff = str(today - pd.Timedelta(days=7))

    amazon_rows: List[Dict[str, Any]] = []
    if not amazon_df.empty and "ingest_date" in amazon_df.columns:
        am = amazon_df[amazon_df["ingest_date"].astype(str) >= cutoff]
        if not am.empty:
            for row in filter_pet_records(am.to_dict(orient="records")):
                title = _clean_title(str(row.get("product_title", "")))
                if not is_pet_product(title=title, url=str(row.get("product_url", "")), category=str(row.get("category", ""))):
                    continue
                brand = _normalize_brand(str(row.get("brand", "")), title)
                category = _normalize_category(str(row.get("category", "")), title)
                amazon_rows.append(
                    {
                        "product_id": str(row.get("asin", row.get("product_id", ""))),
                        "amazon_asin": str(row.get("asin", "") or ""),
                        "amazon_url": _clean_url(row.get("product_url")),
                        "amazon_image_url": _clean_image_url(row.get("image_url")),
                        "canonical_title": title,
                        "normalized_brand": brand,
                        "category": category,
                        "subcategory": _clean_subcategory(row.get("subcategory")),
                        "amazon_rank": float(row.get("rank") or 0) or None,
                        "amazon_rank_delta_1d": float(row.get("rank_delta", 0) or 0),
                        "amazon_is_mover_shaker": int(row.get("is_mover_shaker", 0) or 0),
                        "amazon_rating": float(row.get("rating", 0) or 0) or None,
                        "amazon_review_count": int(row.get("review_count", 0) or 0) or None,
                        "amazon_price_inr": float(row.get("price_inr", 0) or 0) or None,
                        "match_key": _match_key(title, brand),
                        "sources": ["amazon"],
                    }
                )

    gtrends_by_category: Dict[str, Dict[str, Any]] = {}
    if not gtrends_df.empty and "ingest_date" in gtrends_df.columns:
        gt = gtrends_df[gtrends_df["ingest_date"].astype(str) >= cutoff]
        if not gt.empty:
            interest = gt
            if "is_rising" in gt.columns:
                interest_rows = gt[gt["is_rising"].fillna(0).astype(int) == 0]
                if not interest_rows.empty:
                    interest = interest_rows
            if not interest.empty:
                work = interest.copy()
                if "interest_avg_7d" in work.columns:
                    work["_score"] = work.apply(
                        lambda r: float(r["interest_avg_7d"] or r.get("interest_score") or 0),
                        axis=1,
                    )
                else:
                    work["_score"] = work["interest_score"].fillna(0)
                work["category"] = work["category"].map(lambda c: _normalize_category(str(c)))
                agg = (
                    work.groupby("category")
                    .agg(
                        gtrends_category_interest=("_score", "mean"),
                        gtrends_interest_delta_7d=("interest_delta", "mean"),
                    )
                    .reset_index()
                )
                for _, row in agg.iterrows():
                    gtrends_by_category[str(row["category"])] = {
                        "gtrends_category_interest": round(float(row["gtrends_category_interest"] or 0), 2),
                        "gtrends_interest_delta_7d": round(float(row["gtrends_interest_delta_7d"] or 0), 2),
                    }

    flipkart_rows: List[Dict[str, Any]] = []
    if not flipkart_df.empty and "ingest_date" in flipkart_df.columns:
        fk = flipkart_df[flipkart_df["ingest_date"].astype(str) >= cutoff]
        if not fk.empty:
            for row in filter_pet_records(fk.to_dict(orient="records")):
                title = _clean_title(str(row.get("product_title", "")))
                if not is_pet_product(
                    title=title,
                    url=str(row.get("product_url", "")),
                    search_term=str(row.get("search_term", "")),
                    category=str(row.get("category", "")),
                ):
                    continue
                brand = _normalize_brand(str(row.get("brand", "")), title)
                category = _normalize_category(str(row.get("category", "")), title)
                product_url = _clean_url(row.get("product_url"))
                fk_pid = FlipkartScraper.flipkart_pid(product_url)
                legacy_id = str(row.get("product_id", ""))
                product_id = fk_pid or legacy_id
                flipkart_rows.append(
                    {
                        "product_id": product_id,
                        "flipkart_product_id": product_id,
                        "flipkart_url": product_url,
                        "flipkart_image_url": _clean_image_url(row.get("image_url")),
                        "canonical_title": title,
                        "normalized_brand": brand,
                        "category": category,
                        "subcategory": "",
                        "flipkart_avg_rank": float(row.get("rank") or 0) or None,
                        "flipkart_rank_delta_7d": float(row.get("rank_delta", 0) or 0),
                        "flipkart_rating_delta_1d": float(row.get("rating_delta", 0) or 0),
                        "flipkart_rating": float(row.get("rating", 0) or 0) or None,
                        "flipkart_review_count": int(row.get("review_count", 0) or 0) or None,
                        "flipkart_price_inr": float(row.get("price_inr", 0) or 0) or None,
                        "match_key": _match_key(title, brand),
                        "sources": ["flipkart"],
                    }
                )

    flipkart_rows = _dedupe_flipkart_rows(flipkart_rows)

    products: Dict[str, Dict[str, Any]] = {}
    match_index: Dict[str, str] = {}

    for row in amazon_rows:
        pid = row["product_id"] or f"amazon_{abs(hash(row['canonical_title'])) % 10**10}"
        products[pid] = {**row, "product_id": pid}
        mk = row.get("match_key") or ""
        if mk:
            match_index[mk] = pid

    for row in flipkart_rows:
        mk = row.get("match_key") or ""
        pid = (
            match_index.get(mk)
            or _resolve_gold_product_id(row)
            or f"fk_{abs(hash(row['canonical_title'])) % 10**10}"
        )
        if pid in products:
            products[pid] = _merge_product(products[pid], row)
        else:
            # Try brand+overlap merge against amazon rows
            merged_into = None
            for apid, aprod in products.items():
                if _should_fuzzy_merge(row, aprod):
                    products[apid] = _merge_product(aprod, row)
                    merged_into = apid
                    break
            if not merged_into:
                products[pid] = {**row, "product_id": pid}
                if mk:
                    match_index[mk] = pid

    products = _dedupe_products(products)

    gold: List[Dict[str, Any]] = []
    seen_titles: set = set()

    for pid, prod in products.items():
        title = prod.get("canonical_title", "")
        if not is_pet_product(title=title, category=prod.get("category", "")):
            continue

        # Final title-level dedupe (case-insensitive exact)
        title_key = re.sub(r"\s+", " ", title.lower()).strip()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        category = _normalize_category(prod.get("category", ""), title)
        gt = _gtrends_lookup(category, gtrends_by_category)
        sources = list(prod.get("sources", []))
        if gt:
            sources = list(dict.fromkeys(sources + ["gtrends"]))

        am_rank = prod.get("amazon_rank")
        fk_rank = prod.get("flipkart_avg_rank")
        ranks = [r for r in (am_rank, fk_rank) if r not in (None, 0, 0.0)]
        best_rank = min(ranks) if ranks else None
        rank_score = _rank_to_score(best_rank)

        rank_vel = float(prod.get("amazon_rank_delta_1d") or prod.get("flipkart_rank_delta_7d") or 0)
        velocity_score = min(100.0, max(0.0, 50.0 + rank_vel * 2.0))

        rating = prod.get("amazon_rating") or prod.get("flipkart_rating")
        reviews = prod.get("amazon_review_count") or prod.get("flipkart_review_count")
        social_score = _rating_score(rating, reviews)

        gt_momentum = float(gt.get("gtrends_interest_delta_7d", 0) or 0)
        gt_interest = float(gt.get("gtrends_category_interest", 0) or 0)
        gt_score = min(100.0, max(0.0, 50.0 + gt_momentum * 2.0))
        if gt_interest:
            gt_score = max(gt_score, min(100.0, gt_interest))

        mover_bonus = 15.0 if prod.get("amazon_is_mover_shaker") else 0.0
        # Only count marketplace sources for bonus (gtrends is category-level)
        market_sources = [s for s in sources if s in ("amazon", "flipkart")]
        source_bonus = min(15.0, len(market_sources) * 7.5)

        score = (
            0.40 * rank_score
            + 0.20 * velocity_score
            + 0.20 * social_score
            + 0.10 * gt_score
            + 0.05 * mover_bonus
            + 0.05 * (source_bonus / 15.0 * 100.0)
        )
        score = round(min(100.0, max(0.0, score)), 2)
        identity = _gold_identity_fields(prod)

        gold.append(
            {
                "product_id": pid,
                "canonical_title": title,
                "normalized_brand": prod.get("normalized_brand", ""),
                "category": category,
                "subcategory": _clean_subcategory(prod.get("subcategory")),
                **identity,
                "amazon_rank": prod.get("amazon_rank"),
                "amazon_is_mover_shaker": int(prod.get("amazon_is_mover_shaker") or 0),
                "amazon_rating": prod.get("amazon_rating"),
                "amazon_review_count": prod.get("amazon_review_count"),
                "amazon_price_inr": prod.get("amazon_price_inr"),
                "flipkart_avg_rank": prod.get("flipkart_avg_rank"),
                "flipkart_rank_delta_7d": prod.get("flipkart_rank_delta_7d"),
                "flipkart_rating": prod.get("flipkart_rating"),
                "flipkart_review_count": prod.get("flipkart_review_count"),
                "flipkart_price_inr": prod.get("flipkart_price_inr"),
                "gtrends_category_interest": gt.get("gtrends_category_interest"),
                "gtrends_interest_delta_7d": gt.get("gtrends_interest_delta_7d"),
                "trend_score": score,
                "trend_tier": _tier(score),
                "sources": "|".join(sorted(sources)),
                "computed_date": str(today),
                "computed_ts": datetime.now().isoformat(),
            }
        )

    if not gold and gtrends_by_category:
        for cat, gt in gtrends_by_category.items():
            score = min(100.0, max(0.0, float(gt.get("gtrends_category_interest") or 50)))
            gold.append(
                {
                    "product_id": f"gtrends_{cat}",
                    "canonical_title": f"Category trend: {cat}",
                    "normalized_brand": "",
                    "category": cat,
                    "subcategory": "",
                    "gtrends_category_interest": gt.get("gtrends_category_interest"),
                    "gtrends_interest_delta_7d": gt.get("gtrends_interest_delta_7d"),
                    "trend_score": round(score, 2),
                    "trend_tier": _tier(score),
                    "sources": "gtrends",
                    "computed_date": str(today),
                    "computed_ts": datetime.now().isoformat(),
                }
            )

    gold.sort(key=lambda x: (-x.get("trend_score", 0), x.get("canonical_title", "")))
    for i, row in enumerate(gold, start=1):
        row["rank_position"] = i

    return gold
