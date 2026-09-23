"""Tests for the quantity/unit parser."""

import pytest

from src import units


def test_half_cup():
    assert units.parse_ingredient_amount("1/2 c. flour") == (0.5, "cup")


def test_tablespoon():
    assert units.parse_ingredient_amount("2 Tbsp. butter or margarine") == (2.0, "tbsp")


def test_mixed_number():
    assert units.parse_ingredient_amount("3 1/2 c. bite size rice biscuits") == (3.5, "cup")


def test_teaspoon():
    assert units.parse_ingredient_amount("1 tsp. salt") == (1.0, "tsp")


def test_integer_cup():
    assert units.parse_ingredient_amount("1 c. firmly packed brown sugar") == (1.0, "cup")


def test_no_quantity_phrase():
    assert units.parse_ingredient_amount("salt to taste") == (None, None)


def test_egg_count_has_no_unit():
    assert units.parse_ingredient_amount("2 eggs") == (2.0, None)


def test_package_size():
    assert units.parse_ingredient_amount("1 (8 oz.) pkg. cream cheese") == (8.0, "oz")
    assert units.parse_ingredient_amount("2 (16 oz.) pkg. frozen corn") == (32.0, "oz")


def test_weight_unit():
    amount, unit = units.parse_ingredient_amount("500 g flour")
    assert amount == 500.0
    assert unit == "g"


def test_leading_word_stripped():
    assert units.parse_ingredient_amount("about 2 cups water") == (2.0, "cup")


def test_strip_amount_keeps_name():
    assert units.strip_amount("1 c. firmly packed brown sugar") == "firmly packed brown sugar"
    assert units.strip_amount("2 eggs") == "eggs"


def test_mangled_fraction_reconstructed():
    assert units.parse_ingredient_amount("14 cup flour") == (0.25, "cup")
    assert units.parse_ingredient_amount("34 cup brown sugar") == (0.75, "cup")
    assert units.parse_ingredient_amount("14 teaspoon salt") == (0.25, "tsp")
    assert units.parse_ingredient_amount("12 teaspoon salt") == (0.5, "tsp")


def test_mangled_mixed_number_reconstructed():
    assert units.parse_ingredient_amount("1 23 cups sugar")[0] == pytest.approx(1 + 2 / 3)
    assert units.parse_ingredient_amount("1 34 cups cream")[0] == pytest.approx(1.75)


def test_mangled_weight_amounts_left_alone():
    # "12 oz" and "16 oz" are real whole weights, not 1/2 or 1/6 of an ounce.
    assert units.parse_ingredient_amount("12 oz chocolate") == (12.0, "oz")
    assert units.parse_ingredient_amount("16 oz package") == (16.0, "oz")
