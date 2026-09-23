"""Tests for the from-scratch / baked-goods filters (``src.filters``)."""

from src import filters


def test_from_scratch_kept():
    assert not filters.is_excluded(
        "Basic White Bread",
        ["500 g all-purpose flour", "300 g water", "1 tsp yeast", "1 tsp salt"],
    )


def test_prepared_dough_excluded():
    assert filters.is_excluded(
        "Easy Rolls", ["1 lb frozen bread dough, thawed"]
    )
    assert filters.is_excluded(
        "Quick Cookies", ["1 package refrigerated sugar cookie dough"]
    )


def test_cake_mix_excluded():
    assert filters.is_excluded("Box Cake", ["1 box yellow cake mix", "3 eggs"])


def test_no_bake_excluded():
    assert filters.is_excluded("No-Bake Balls", ["1 cup peanut butter", "1 cup sugar"])


def test_topping_only_excluded():
    assert filters.is_excluded("Vanilla Buttercream Frosting", ["1 cup butter", "4 cups powdered sugar"])


def test_topping_on_cake_kept():
    assert not filters.is_excluded(
        "Chocolate Cake With Frosting",
        ["2 cups flour", "1 cup sugar", "1/2 cup butter", "2 eggs"],
    )


def test_cornbread_kept():
    assert not filters.is_excluded(
        "Cornbread", ["1 1/2 cups cornmeal", "1 cup milk", "2 eggs"]
    )