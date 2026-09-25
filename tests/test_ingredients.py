"""Tests for the ingredient decomposition lexicon."""

import pytest

from src.preprocess import ingredients


def test_flour_variants():
    assert ingredients.primary_part(ingredients.resolve("all-purpose flour")[0]) == "flour"
    assert ingredients.primary_part(ingredients.resolve("cake flour")[0]) == "flour"
    assert ingredients.primary_part(ingredients.resolve("whole wheat flour")[0]) == "flour"
    assert ingredients.primary_part(ingredients.resolve("self-rising flour")[0]) == "flour"


def test_cornmeal_is_flour():
    assert ingredients.primary_part(ingredients.resolve("cornmeal")[0]) == "flour"
    assert ingredients.primary_part(ingredients.resolve("corn meal")[0]) == "flour"
    assert ingredients.primary_part(ingredients.resolve("masa harina")[0]) == "flour"
    assert ingredients.primary_part(ingredients.resolve("polenta")[0]) == "flour"
    # cornstarch is nearly pure starch -> flour part (USDA reference)
    assert ingredients.primary_part(ingredients.resolve("cornstarch")[0]) == "flour"


def test_fat_variants():
    assert ingredients.primary_part(ingredients.resolve("unsalted butter")[0]) == "fat"
    assert ingredients.primary_part(ingredients.resolve("butter")[0]) == "fat"
    assert ingredients.primary_part(ingredients.resolve("margarine")[0]) == "fat"
    assert ingredients.primary_part(ingredients.resolve("vegetable oil")[0]) == "fat"


def test_buttermilk_is_milk_not_butter():
    assert ingredients.primary_part(ingredients.resolve("buttermilk")[0]) == "milk"
    assert ingredients.primary_part(ingredients.resolve("milk")[0]) == "milk"


def test_peanut_butter_resolves_to_fat():
    vec, role = ingredients.resolve("peanut butter")
    assert role == "addin"
    assert vec["fat"] == pytest.approx(0.50)
    assert vec["sugar"] == pytest.approx(0.10)
    assert ingredients.decompose("peanut butter") == {}


def test_milk_chocolate_resolves_to_sugar_and_fat():
    vec, role = ingredients.resolve("milk chocolate")
    assert role == "addin"
    assert vec["sugar"] == pytest.approx(0.55)
    assert vec["fat"] == pytest.approx(0.30)
    assert "milk" not in vec
    assert ingredients.decompose("milk chocolate") == {}


def test_cream_cheese_decomposes_to_fat_and_liquid():
    vec = ingredients.decompose("cream cheese")
    # USDA: cream cheese is ~34% fat and ~53% water
    assert vec["fat"] == pytest.approx(0.344, abs=1e-2)
    assert vec["water"] == pytest.approx(0.526, abs=1e-2)


def test_condensed_milk_decomposes_to_sugar():
    vec = ingredients.decompose("sweetened condensed milk")
    # USDA: sweetened condensed milk is ~54% sugar
    assert vec["sugar"] == pytest.approx(0.544, abs=1e-2)


def test_leaveners():
    assert ingredients.primary_part(ingredients.resolve("baking powder")[0]) == "leavener"
    assert ingredients.primary_part(ingredients.resolve("baking soda")[0]) == "leavener"


def test_sugars():
    assert ingredients.primary_part(ingredients.resolve("brown sugar")[0]) == "sugar"
    assert ingredients.primary_part(ingredients.resolve("powdered sugar")[0]) == "sugar"
    assert ingredients.primary_part(ingredients.resolve("sugar")[0]) == "sugar"


def test_eggs():
    assert ingredients.primary_part(ingredients.resolve("egg")[0]) == "egg"
    assert ingredients.primary_part(ingredients.resolve("eggs")[0]) == "egg"
    assert ingredients.primary_part(ingredients.resolve("egg whites")[0]) == "egg"


def test_or_resolution():
    assert ingredients.primary_part(ingredients.resolve("butter or margarine")[0]) == "fat"


def test_produce_resolves_to_water():
    vec, _ = ingredients.resolve("bananas")
    assert vec["water"] > 0.5
    vec, _ = ingredients.resolve("canned pumpkin")
    assert vec["water"] == pytest.approx(0.90, abs=1e-2)


def test_other():
    assert ingredients.primary_part(ingredients.resolve("vanilla extract")[0]) == "other"
    assert ingredients.primary_part(ingredients.resolve("")[0]) == "other"


def test_nuts_decompose_to_fat():
    # USDA: pecans are ~74% fat (add-in, zeroed in the structural decomposition)
    assert ingredients.primary_part(ingredients.resolve("pecans")[0]) == "fat"
    assert ingredients.resolve("pecans")[1] == "addin"
    assert ingredients.decompose("pecans") == {}


def test_structural_decomposition_zeroes_addins():
    assert ingredients.decompose("chocolate chips") == {}
    assert ingredients.resolve("chocolate chips")[0]["sugar"] > 0
    # base ingredients are unchanged
    assert ingredients.decompose("butter") == {"fat": 1.0}


def test_yeast_and_salt_and_water():
    assert ingredients.primary_part(ingredients.resolve("instant yeast")[0]) == "yeast"
    assert ingredients.primary_part(ingredients.resolve("salt")[0]) == "salt"
    assert ingredients.primary_part(ingredients.resolve("water")[0]) == "water"


def test_weights_sum_to_at_most_one():
    for name in ["cream cheese", "sweetened condensed milk", "chocolate chips",
                 "butter", "flour", "honey", "tomato soup", "banana"]:
        vec, _ = ingredients.resolve(name)
        assert sum(vec.values()) <= 1.0 + 1e-9, name

def test_bare_cream_resolves_as_heavy_cream():
    vec = ingredients.decompose("cream")
    assert vec["fat"] > 0.30
    assert "flour" not in vec


def test_self_rising_flour_splits_leavener():
    vec = ingredients.decompose("self-rising flour")
    assert vec["flour"] == pytest.approx(0.92)
    assert vec["leavener"] == pytest.approx(0.055)
    assert vec["salt"] == pytest.approx(0.025)


def test_ice_cream_vector():
    vec = ingredients.decompose("vanilla ice cream")
    assert vec["fat"] == pytest.approx(0.11)
    assert vec["sugar"] == pytest.approx(0.21)
