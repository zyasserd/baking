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


def test_purchased_baked_goods_excluded():
    # Any finished baked good as an ingredient makes the recipe an assembly.
    assert filters.is_excluded("Cheese Bread", ["1 loaf French bread, halved"])
    assert filters.is_excluded("Breadsticks", ["1 box refrigerated breadsticks"])
    assert filters.is_excluded("Biscuit Pie", ["1 cup biscuit crumbs"])
    assert filters.is_excluded("Pretzel Salad", ["2 cups crushed pretzels"])
    assert filters.is_excluded("Pudding Cake", ["1 box angel food cake"])
    assert filters.is_excluded("Cookie Crust Bars", ["24 oreo cookies"])
    assert filters.is_excluded("Graham Bars", ["1 1/2 cups graham cracker crumbs"])
    assert filters.is_excluded("Shepherd's Pie", ["1 cup breadcrumbs"])
    assert filters.is_excluded("Crumb Pie", ["1 prepared pie crust"])


def test_bread_flour_and_breaded_kept():
    # Raw ingredients that merely contain the word.
    assert not filters.is_excluded("Sandwich Loaf", ["4 cups bread flour", "1 tsp yeast"])
    assert not filters.is_excluded("Chicken Bakes", ["1 lb breaded chicken"])
    assert not filters.is_excluded("Ginger Spice Bread", ["2 tsp gingerbread spice"])


def test_pancake_syrup_and_crustless_kept():
    assert not filters.is_excluded("Syrup Cake", ["1 cup pancake syrup"])
    assert not filters.is_excluded("Crustless Quiche", ["6 eggs", "1 cup cream"])
    assert not filters.is_excluded("Pancake Bites", ["2 cups flour", "1 egg"])


def test_homemade_two_part_bakes_kept():
    # A shortbread crust made from scratch in the same recipe is from-scratch.
    assert not filters.is_excluded(
        "Caramel Bars",
        ["1 1/2 cups flour", "1/2 cup butter", "1 cup brown sugar", "1/4 cup cream"],
    )
    assert not filters.is_excluded(
        "Upside-Down Cake",
        ["1 cup brown sugar", "1/4 cup butter", "2 cups flour", "1 egg", "2 bananas"],
    )