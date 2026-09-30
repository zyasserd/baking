"""Tests for the quantity/unit parser."""

import pytest

from src.preprocess import units


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


def test_quantity_range_midpoint():
    assert units.parse_ingredient_amount("2 -3 cups flour") == (2.5, "cup")
    assert units.parse_ingredient_amount("1 1/2 - 2 cups strawberries")[0] == 1.75
    assert units.parse_ingredient_amount("1 -2 tablespoon oil") == (1.5, "tbsp")
    assert units.parse_ingredient_amount("3 -4 eggs") == (3.5, None)
    assert units.parse_ingredient_amount("1 to 2 cups milk") == (1.5, "cup")
    assert units.parse_ingredient_amount("1/2 -1 cup sugar") == (0.75, "cup")


def test_quantity_range_with_mangled_first_number():
    # "1/2 - 2 cups" appears mangled as "12 -2 cups".
    assert units.parse_ingredient_amount("12 -2 cups flour") == (1.25, "cup")


def test_range_strip_amount():
    assert units.strip_amount("2 -3 cups all-purpose flour") == "all-purpose flour"
    assert units.strip_amount("1 1/2 - 2 cups sliced strawberries") == "sliced strawberries"


def test_mangled_fraction_ranges():
    # "1/4 - 1/2 cup" and "3/8 - 3/4 cup" arrive slash-less as "14-12" / "38-34".
    assert units.parse_ingredient_amount("14-12 cup unsalted butter") == (0.375, "cup")
    assert units.parse_ingredient_amount("38-34 cup unsalted butter") == (0.5625, "cup")
    assert units.parse_ingredient_amount("34-38 cup sugar") == (0.5625, "cup")


def test_package_size_fraction():
    assert units.parse_ingredient_amount("1 (10 5/8 oz) box pasta") == (10.625, "oz")
    assert units.parse_ingredient_amount("2 (3 1/2 oz.) pkg. candy")[0] == 7.0


def test_range_span_endpoints():
    amount, unit, low, high = units.parse_amount_span("1 1/2 - 2 cups flour")
    assert amount == pytest.approx(1.75)
    assert unit == "cup"
    assert low == pytest.approx(1.5)
    assert high == pytest.approx(2.0)


def test_range_span_mangled_endpoints():
    # "1/4 - 1/2 cup" arrives slash-less as "14-12 cup".
    _, _, low, high = units.parse_amount_span("14-12 cup unsalted butter")
    assert low == pytest.approx(0.25)
    assert high == pytest.approx(0.5)


def test_span_none_for_non_range():
    _, _, low, high = units.parse_amount_span("2 cups flour")
    assert low is None and high is None
    _, _, low, high = units.parse_amount_span("1/2 tsp salt")
    assert low is None and high is None


def test_span_none_for_unparseable():
    amount, unit, low, high = units.parse_amount_span("salt to taste")
    assert amount is None and unit is None and low is None and high is None


def test_parse_ingredient_amount_delegates():
    assert units.parse_ingredient_amount("1 1/2 - 2 cups flour") == (1.75, "cup")


def test_strip_amount_mangled_mixed_number():
    # "1 12 cups oil" is a mangled "1 1/2 cups oil": the amount parses as 1.5
    # cups, so the name must not keep the mangled digits.
    assert units.strip_amount("1 12 cups oil") == "oil"
    assert units.strip_amount("1 34 cups cream cheese") == "cream cheese"


def test_quantified_line_with_trailing_phrase_keeps_amount():
    # "for frying"/"to taste" must not kill a line that HAS an amount.
    assert units.parse_ingredient_amount("1 cup vegetable oil (for frying)") == (1.0, "cup")
    assert units.parse_ingredient_amount("1/2 tsp salt, to taste") == (0.5, "tsp")
    assert units.parse_ingredient_amount("1 cup powdered sugar, for dusting")[0] == 1.0


def test_genuine_no_quantity_lines_stay_none():
    assert units.parse_ingredient_amount("salt to taste") == (None, None)
    assert units.parse_ingredient_amount("fresh ground black pepper") == (None, None)
    assert units.parse_ingredient_amount("oil, for deep frying") == (None, None)


def test_pinch_dash_are_units():
    amount, unit = units.parse_ingredient_amount("1 pinch salt")
    assert (amount, unit) == (1.0, "pinch")
    amount, unit = units.parse_ingredient_amount("2 dashes nutmeg")
    assert (amount, unit) == (2.0, "dash")
