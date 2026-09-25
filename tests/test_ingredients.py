"""Tests for the ingredient decomposition lexicon."""

import pytest

from src import ingredients


def test_flour_variants():
    assert ingredients.classify("all-purpose flour") == "flour"
    assert ingredients.classify("cake flour") == "flour"
    assert ingredients.classify("whole wheat flour") == "flour"
    assert ingredients.classify("self-rising flour") == "flour"


def test_cornmeal_is_flour():
    assert ingredients.classify("cornmeal") == "flour"
    assert ingredients.classify("corn meal") == "flour"
    assert ingredients.classify("masa harina") == "flour"
    assert ingredients.classify("polenta") == "flour"
    # cornstarch is nearly pure starch -> flour part (USDA reference)
    assert ingredients.classify("cornstarch") == "flour"


def test_fat_variants():
    assert ingredients.classify("unsalted butter") == "fat"
    assert ingredients.classify("butter") == "fat"
    assert ingredients.classify("margarine") == "fat"
    assert ingredients.classify("vegetable oil") == "fat"


def test_buttermilk_is_milk_not_butter():
    assert ingredients.classify("buttermilk") == "milk"
    assert ingredients.classify("milk") == "milk"


def test_peanut_butter_decomposes_to_fat():
    vec = ingredients.decompose("peanut butter")
    assert vec["fat"] == pytest.approx(0.50)
    assert vec["sugar"] == pytest.approx(0.10)


def test_milk_chocolate_decomposes_to_sugar_and_fat():
    vec = ingredients.decompose("milk chocolate")
    assert vec["sugar"] == pytest.approx(0.55)
    assert vec["fat"] == pytest.approx(0.30)
    assert "milk" not in vec


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
    assert ingredients.classify("baking powder") == "leavener"
    assert ingredients.classify("baking soda") == "leavener"


def test_sugars():
    assert ingredients.classify("brown sugar") == "sugar"
    assert ingredients.classify("powdered sugar") == "sugar"
    assert ingredients.classify("sugar") == "sugar"


def test_eggs():
    assert ingredients.classify("egg") == "egg"
    assert ingredients.classify("eggs") == "egg"
    assert ingredients.classify("egg whites") == "egg"


def test_or_resolution():
    assert ingredients.classify("butter or margarine") == "fat"


def test_produce_decomposes_to_water():
    vec = ingredients.decompose("bananas")
    assert vec["water"] > 0.5
    vec = ingredients.decompose("canned pumpkin")
    assert vec["water"] == pytest.approx(0.90, abs=1e-2)


def test_other():
    assert ingredients.classify("vanilla extract") == "other"
    assert ingredients.classify("") == "other"


def test_nuts_decompose_to_fat():
    # USDA: pecans are ~74% fat (add-in, zeroed in structural mode)
    assert ingredients.classify("pecans") == "fat"
    assert ingredients.role("pecans") == "addin"
    assert ingredients.decompose("pecans", "structural") == {}


def test_structural_mode_zeroes_addins():
    assert ingredients.decompose("chocolate chips", "structural") == {}
    assert ingredients.decompose("chocolate chips", "full")["sugar"] > 0
    # base ingredients survive both modes
    assert ingredients.decompose("butter", "structural") == {"fat": 1.0}


def test_yeast_and_salt_and_water():
    assert ingredients.classify("instant yeast") == "yeast"
    assert ingredients.classify("salt") == "salt"
    assert ingredients.classify("water") == "water"


def test_weights_sum_to_at_most_one():
    for name in ["cream cheese", "sweetened condensed milk", "chocolate chips",
                 "butter", "flour", "honey", "tomato soup", "banana"]:
        vec = ingredients.decompose(name)
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
