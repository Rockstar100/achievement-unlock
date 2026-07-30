"""Tests for canonical helpers."""
from transform.canonical import canonical_product_id, infer_species


def test_infer_species_dog():
    assert infer_species("Pedigree Adult Dog Food", "dog_food") == "dog"


def test_infer_species_cat():
    assert infer_species("Whiskas Kitten Food", "cat_food") == "cat"


def test_canonical_product_id_stable():
    a = canonical_product_id("royal canin|dog food", "royal canin", "Royal Canin Dog Food")
    b = canonical_product_id("royal canin|dog food", "royal canin", "Royal Canin Dog Food")
    assert a == b
    assert len(a) == 16
