"""
Dog & cat product validation — keep only dog/cat items in the pipeline.
"""
from __future__ import annotations

import re
from urllib.parse import unquote

DOG_CAT_KEYWORDS = [
    "dog", "puppy", "puppies", "canine",
    "cat", "kitten", "kittens", "feline", "kitty",
    "dog food", "cat food", "dog treat", "cat treat",
    "dog toy", "cat toy", "dog bed", "cat bed",
    "dog collar", "cat collar", "dog leash", "dog harness",
    "dog shampoo", "cat shampoo",
    "litter box", "cat litter", "catnip",
    "royal canin", "pedigree", "whiskas", "drools", "farmina",
    "himalaya", "me-o", "meo", "kong", "nylabone", "purina",
    "purepet", "chappi", "sheba", "meat up", "jerhigh", "beaphar",
]

# Non dog/cat animals and decor that often pollute pet bestseller lists
OTHER_PET_KEYWORDS = [
    "bird", "budgie", "parrot", "cockatiel", "avian", "pigeon", "canary",
    "fish", "aquarium", "aquatic", "betta", "goldfish", "taiyo",
    "hamster", "rabbit", "guinea", "rodent", "small animal",
    "reptile", "turtle", "tortoise", "vitapol",
    "cow", "cattle", "goat", "poultry", "broiler", "layers",
    "livestock", "horse", "horses", "pig food", "pigs,",
    "vase filler", "vase fillers", "decorative stone", "decorative stones",
    "polished white pebble", "multicolor stone", "glossy stone",
    "pebble", "pebbles", "home decorative", "art & craft", "outdoor decoration",
]

NON_PET_KEYWORDS = [
    "smartphone", "mobile phone", "iphone", "samsung galaxy", "oneplus",
    "laptop", "macbook", "chromebook", "earbuds", "headphone",
    "power bank", "trimmer for men", "shaver men",
    "kurti", "saree", "anarkali", "dupatta", "jeans", "sneakers",
    "t shirt", "polo", "hipster", "trunks", "bra", "lingerie",
    "raincoat", "rainwear", "rainsuit", "mixer grinder", "air fryer",
    "vacuum cleaner", "water purifier", "coffee maker", "yoga mat",
    "dumbbell", "cricket bat", "protein powder", "face wash", "lipstick",
    "perfume", "sunscreen", "jockey", "van heusen", "allen solly",
    "symbol polo", "trackpants", "joggers", "shapewear", "petticoat",
    "palazzo", "viscose", "denim", "western", "streetwear", "oversized",
    "bikini", "waistband", "cotton trunks", "mens cotton", "womens",
    "kotty", "gosriki", "mehrang", "parthvi", "shasmi",
    "xyxx", "lux cozi", "trylo", "nifty", "swagr", "zeel", "klosia",
    "citizen eco", "water fighter", "jelly cat", "for kids",
    # Human health / kitchen items that pollute Amazon pet-food lists
    "liniment", "pain killer", "minyak urut", "ayurveda", "kottakkal",
    "papad", "drying cloth", "drying mat", "sun drying", "mesh drying",
    "sallaki", "rhukot", "herbal oil for human", "joint pain relief oil",
    # Human food that matches "dog" in Trends rising queries
    "corn dog", "corn dogs", "korean corn", "hot dog bun", "hot dogs",
]

NON_PET_URL_SEGMENTS = [
    "/fashion/", "/clothing/", "/apparel/", "/shoes/",
    "/electronics/", "/computers/", "/mobile-phones/",
    "/beauty/", "/grocery/", "/home-kitchen/",
    "/sports/", "/books/", "/office-products/",
]

EXCLUDED_CATEGORIES = {
    "birds", "fish_aquatics", "fish & aquatics", "small_animals", "small animals",
    "pet supplies",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unquote(text or "").lower()).strip()


def title_from_url(url: str) -> str:
    """Derive a readable title from Amazon/Flipkart product URL slug."""
    if not url:
        return ""
    if "/dp/" in url:
        slug = url.split("/dp/")[-1].split("/")[0]
    elif "/p/" in url:
        slug = url.split("/p/")[-1].split("?")[0]
    else:
        return ""
    slug = re.sub(r"-ref=.*", "", slug)
    return slug.replace("-", " ").strip()


def _category_signals_dog_or_cat(category: str) -> bool:
    cat = _normalize(category).replace("_", " ")
    if cat in EXCLUDED_CATEGORIES:
        return False
    return "dog" in cat or "cat" in cat


def _has_dog_or_cat_signal(text: str) -> bool:
    t = _normalize(text)
    if not t:
        return False
    # Word-boundary-ish checks for short tokens
    if re.search(r"\b(dog|dogs|puppy|puppies|canine)\b", t):
        return True
    if re.search(r"\b(cat|cats|kitten|kittens|feline|kitty)\b", t):
        return True
    brands = (
        "royal canin", "pedigree", "whiskas", "drools", "purepet", "chappi",
        "meat up", "sheba", "me-o", "meo ", "kong ", "himalaya erina",
    )
    return any(b in t for b in brands)


def is_pet_product(
    title: str = "",
    url: str = "",
    search_term: str = "",
    category: str = "",
) -> bool:
    """Return True only if the product is dog- or cat-related."""
    if len(_normalize(title)) < 3 and url:
        title = title_from_url(url)

    title_clean = _normalize(title)
    search_clean = _normalize(search_term)
    category_clean = _normalize(category).replace("_", " ")

    if category_clean in EXCLUDED_CATEGORIES:
        return False

    if len(title_clean) < 3 and len(search_clean) < 3 and not _category_signals_dog_or_cat(category):
        return False

    blob = _normalize(f"{title} {url} {search_term}")

    for bad in NON_PET_KEYWORDS + OTHER_PET_KEYWORDS:
        if bad in blob:
            return False

    url_lower = _normalize(url)
    for seg in NON_PET_URL_SEGMENTS:
        if seg in url_lower:
            return False

    # Title/URL must explicitly signal dog or cat — category metadata alone is not enough
    # (Amazon cat-food lists often include human ayurveda / kitchen items).
    title_url = f"{title_clean} {url_lower}"
    if _has_dog_or_cat_signal(title_url):
        return True

    return False


def filter_pet_records(records: list, title_key: str = "product_title") -> list:
    """Filter bronze records to dog/cat-only products."""
    kept = []
    for rec in records:
        title = str(rec.get(title_key, "") or "")
        if not title:
            title = str(rec.get("keyword", "") or "")
        url = str(rec.get("product_url", "") or "")
        if is_pet_product(
            title=title,
            url=url,
            search_term=str(rec.get("search_term", "") or rec.get("keyword", "")),
            category=str(rec.get("category", "") or ""),
        ):
            kept.append(rec)
    return kept
