"""Tests for dog/cat product filter."""
from scrapers.filters.pet_filter import filter_pet_records, is_pet_product


def test_accepts_dog_cat_products():
    assert is_pet_product(title="Royal Canin Dog Food 4kg", category="dog_food")
    assert is_pet_product(title="Whiskas Cat Food", search_term="cat food")
    assert is_pet_product(title="Pedigree Puppy Food", category="Dog Food")
    assert is_pet_product(title="Amazon Basics Cat Litter 10kg", category="cat_food")
    assert is_pet_product(
        title="Himalaya Erina-EP Shampoo Tick & Flea Control for Dogs & Cats"
    )


def test_rejects_other_pets_and_livestock():
    assert not is_pet_product(title="Taiyo Fish Food Flakes", category="fish_aquatics")
    assert not is_pet_product(title="Vitapol Bird Food for Budgies", category="birds")
    assert not is_pet_product(search_term="hamster food", title="Hamster Food Mix")
    assert not is_pet_product(title="Purepet Adult Dry Cat Food", category="Pet Supplies")
    assert not is_pet_product(
        title="REFIT ANIMAL CARE Vitamin for Cow, Cattle, Goat, Chicken, Poultry"
    )
    assert not is_pet_product(
        title="BOLTZ Guinea Pellet Pig Food For All Life Stages"
    )
    assert not is_pet_product(
        title="Foodie Puppies Polished White Pebbles for Aquarium Vase Fillers"
    )


def test_rejects_unrelated_flipkart_ads():
    assert not is_pet_product(
        title="Golden Oldie Herbs Rhukot Liniment-100Ml",
        search_term="joint supplement for dogs",
        category="health_wellness",
    )
    assert not is_pet_product(
        title="Golden Oldie Herbs Rhukot Liniment-100Ml",
        category="cat_food",
    )
    assert not is_pet_product(
        title="Nibbler Papad Drying Cloth with Net Zip | Food Drying Cloth",
        category="cat_food",
    )
    assert not is_pet_product(
        title="Samsung Galaxy Smartphone",
        search_term="dog food",
        category="dog_food",
    )


def test_rejects_non_pet_products():
    assert not is_pet_product(
        title="Jockey Womens Hipster",
        url="https://www.amazon.in/Jockey-Womens-Hipster/dp/B010FMJKFS",
    )
    assert not is_pet_product(title="Samsung Galaxy Smartphone 5G")
    assert not is_pet_product(title="KLOSIA Printed Anarkali Dupatta")


def test_filter_pet_records():
    records = [
        {"product_title": "Pedigree Dog Food", "product_url": "", "category": "dog_food"},
        {"product_title": "Allen Solly T Shirt", "product_url": "", "category": "dog_food"},
        {"product_title": "Whiskas Cat Treats", "product_url": "", "category": "cat_food"},
        {"product_title": "Taiyo Fish Food", "product_url": "", "category": "fish_aquatics"},
        {
            "product_title": "Decorative Stones for Aquarium",
            "product_url": "",
            "category": "cat_toys",
        },
    ]
    filtered = filter_pet_records(records)
    assert len(filtered) == 2
    titles = {r["product_title"] for r in filtered}
    assert "Pedigree Dog Food" in titles
    assert "Whiskas Cat Treats" in titles
