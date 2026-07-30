"""Tests for gold transformation from bronze files."""
from datetime import date

import pandas as pd

from transform.gold_builder import build_gold_from_bronze


def _amazon_df():
    return pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "asin": "B001",
                "product_title": "Royal Canin Dog Food",
                "brand": "Royal Canin",
                "category": "Dog Food",
                "subcategory": "dry",
                "rank": 1,
                "rank_delta": 3,
                "rating": 4.5,
                "review_count": 100,
                "price_inr": 999,
                "is_mover_shaker": 1,
            }
        ]
    )


def _gtrends_df():
    return pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "category": "dog_food",
                "keyword": "dog food",
                "interest_score": 80,
                "interest_delta": 10,
                "is_rising": 0,
            }
        ]
    )


def _flipkart_df():
    return pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "product_id": "FK001",
                "product_title": "Pedigree Dog Food Chicken",
                "brand": "Pedigree",
                "category": "dog_food",
                "rank": 2,
                "rank_delta": 1,
                "rating_delta": 0.1,
            }
        ]
    )


def test_build_gold_produces_records():
    gold = build_gold_from_bronze(_amazon_df(), _gtrends_df(), _flipkart_df())
    assert len(gold) >= 1
    assert "trend_score" in gold[0]
    assert "trend_tier" in gold[0]
    assert gold[0]["trend_score"] > 0
    assert gold[0]["trend_score"] >= 50
    assert gold[0]["category"] == "dog_food"
    assert "amazon" in gold[0]["sources"]


def test_build_gold_gtrends_only():
    gold = build_gold_from_bronze(pd.DataFrame(), _gtrends_df(), pd.DataFrame())
    assert len(gold) >= 1
    assert gold[0]["sources"] == "gtrends"


def test_rank_one_scores_higher_than_rank_thirty():
    am = _amazon_df()
    am2 = am.copy()
    am2.loc[0, "asin"] = "B002"
    am2.loc[0, "rank"] = 30
    am2.loc[0, "product_title"] = "Generic Dog Treats"
    am2.loc[0, "is_mover_shaker"] = 0
    am2.loc[0, "rank_delta"] = 0
    combined = pd.concat([am, am2], ignore_index=True)
    gold = build_gold_from_bronze(combined, _gtrends_df(), pd.DataFrame())
    by_id = {r["product_id"]: r["trend_score"] for r in gold}
    assert by_id["B001"] > by_id["B002"]


def test_dedupes_near_duplicate_titles():
    am = pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "asin": "B073RVF88P",
                "product_title": "Himalaya Erina-EP Shampoo | Tick & Flea Control for Dogs & Cats",
                "brand": "Himalaya",
                "category": "Dog Food",
                "rank": 9,
                "rating": 4.4,
                "review_count": 100,
                "price_inr": 235,
            }
        ]
    )
    fk = pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "product_id": "fk_himalaya",
                "product_title": "HIMALAYA Erina-EP Shampoo Flea and Tick Lemon Dog, Cat Shampoo",
                "brand": "Himalaya",
                "category": "grooming",
                "rank": 1,
                "rating": 4.3,
                "review_count": 50,
            }
        ]
    )
    gold = build_gold_from_bronze(am, pd.DataFrame(), fk)
    assert len(gold) == 1
    assert gold[0]["category"] == "grooming"
    assert "amazon" in gold[0]["sources"] and "flipkart" in gold[0]["sources"]


def test_does_not_merge_distinct_amazon_asins():
    am = pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "asin": "B0CFLRSTY6",
                "product_title": "Drools Adult Wet Dog Food 0.9kg (150g x 6) Pack of 6",
                "brand": "Drools",
                "category": "Dog Food",
                "rank": 2,
                "rating": 4.3,
                "review_count": 9482,
            },
            {
                "ingest_date": str(date.today()),
                "asin": "B0CP61Q4G7",
                "product_title": "Drools Puppy Wet Dog Food 0.9kg (150g x 6 Packs)",
                "brand": "Drools",
                "category": "Dog Food",
                "rank": 13,
                "rating": 4.3,
                "review_count": 5965,
            },
        ]
    )
    gold = build_gold_from_bronze(am, pd.DataFrame(), pd.DataFrame())
    assert len(gold) == 2
    by_id = {r["product_id"]: r for r in gold}
    assert by_id["B0CFLRSTY6"]["amazon_asin"] == "B0CFLRSTY6"
    assert by_id["B0CP61Q4G7"]["amazon_asin"] == "B0CP61Q4G7"


def test_dedupes_flipkart_rows_by_url_pid():
    url = (
        "https://www.flipkart.com/whiskas-cat-food/p/itm?pid=PFDEGNF2TH339M2Z"
        "&lid=LSTPFDEGNF2TH339M2Z"
    )
    fk = pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "product_id": "hash_a",
                "product_title": "Whiskas (1+ Years) Tuna 1.2 kg Dry Adult Cat Food",
                "brand": "Whiskas",
                "category": "cat_food",
                "rank": 3,
                "product_url": url,
            },
            {
                "ingest_date": str(date.today()),
                "product_id": "hash_b",
                "product_title": "Whiskas (1+ Years) Tuna 1.2 kg Dry Adult Cat Food",
                "brand": "Whiskas",
                "category": "cat_food",
                "rank": 1,
                "product_url": url + "&qH=abc",
            },
        ]
    )
    gold = build_gold_from_bronze(pd.DataFrame(), pd.DataFrame(), fk)
    assert len(gold) == 1
    assert gold[0]["product_id"] == "PFDEGNF2TH339M2Z"
    assert gold[0]["flipkart_product_id"] == "PFDEGNF2TH339M2Z"
    assert gold[0]["flipkart_avg_rank"] == 1


def test_rejects_livestock_and_aquarium_decor():
    am = pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "asin": "B_BAD1",
                "product_title": "REFIT ANIMAL CARE Vitamin for Cow, Cattle, Goat, Chicken, Poultry",
                "brand": "Refit",
                "category": "Dog Toys",
                "rank": 1,
                "rating": 4.1,
                "review_count": 10,
            },
            {
                "ingest_date": str(date.today()),
                "asin": "B_BAD2",
                "product_title": "Foodie Puppies Polished White Pebbles for Aquarium and Vase Fillers",
                "brand": "Foodie",
                "category": "Cat Toys",
                "rank": 1,
                "rating": 4.2,
                "review_count": 10,
            },
            {
                "ingest_date": str(date.today()),
                "asin": "B_GOOD",
                "product_title": "Pedigree Adult Dry Dog Food 3kg",
                "brand": "Pedigree",
                "category": "Dog Food",
                "rank": 1,
                "rating": 4.4,
                "review_count": 100,
            },
        ]
    )
    gold = build_gold_from_bronze(am, pd.DataFrame(), pd.DataFrame())
    ids = {r["product_id"] for r in gold}
    assert "B_GOOD" in ids
    assert "B_BAD1" not in ids
    assert "B_BAD2" not in ids


def test_normalizes_meo_brand():
    fk = pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "product_id": "FK_MEO",
                "product_title": "Me-O Adult Dry Cat Food Mackerel 1.2kg",
                "brand": "Meo",
                "category": "cat_food",
                "rank": 1,
            }
        ]
    )
    gold = build_gold_from_bronze(pd.DataFrame(), pd.DataFrame(), fk)
    assert gold[0]["normalized_brand"] == "me-o"


def test_clean_title_strips_replacement_char():
    from transform.gold_builder import _clean_title

    assert "®" not in _clean_title("Qpets® Tunnel")
    assert "\ufffd" not in _clean_title("Qpets\ufffd Tunnel")


def test_gold_includes_images_and_marketplace_ids():
    am = pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "asin": "B079T88XLM",
                "product_title": "Meat Up Dog Treats Biscuits 2kg",
                "brand": "Meat Up",
                "category": "Dog Food",
                "rank": 1,
                "rating": 4.2,
                "review_count": 100,
                "price_inr": 385,
                "product_url": "https://www.amazon.in/dp/B079T88XLM",
                "image_url": "https://images-eu.ssl-images-amazon.com/images/I/71pZLyhZFKL.jpg",
            }
        ]
    )
    fk = pd.DataFrame(
        [
            {
                "ingest_date": str(date.today()),
                "product_id": "fk123",
                "product_title": "Pedigree Dog Food Chicken",
                "brand": "Pedigree",
                "category": "dog_food",
                "rank": 2,
                "product_url": "https://www.flipkart.com/pedigree/p/itm",
                "image_url": "https://rukminim2.flixcart.com/image.jpg",
            }
        ]
    )
    gold = build_gold_from_bronze(am, pd.DataFrame(), fk)
    by_id = {r["product_id"]: r for r in gold}
    assert by_id["B079T88XLM"]["amazon_asin"] == "B079T88XLM"
    assert by_id["B079T88XLM"]["image_url"].startswith("https://")
    assert by_id["B079T88XLM"]["amazon_image_url"].startswith("https://")
    assert by_id["fk123"]["flipkart_product_id"] == "fk123"
    assert by_id["fk123"]["flipkart_image_url"].startswith("https://")
    assert by_id["fk123"]["image_url"] == by_id["fk123"]["flipkart_image_url"]
