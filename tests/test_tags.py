"""Tests for the Food.com tag taxonomy (``src.tags``)."""

import config

from src.preprocess import tags


def test_leaf_tag_resolves_to_class():
    assert tags.classify(["drop-cookies"]) == ("cookie", "drop-cookies", "strong")
    assert tags.classify(["sourdough"]) == ("bread", "sourdough", "strong")
    assert tags.classify(["muffins"]) == ("quick_bread", "muffins", "strong")
    assert tags.classify(["cupcakes"]) == ("cake", "cupcakes", "strong")
    assert tags.classify(["brownies"]) == ("brownies", "brownies", "strong")
    assert tags.classify(["pies"]) == ("pie_pastry", "pies", "strong")
    assert tags.classify(["danish"]) == ("pie_pastry", "danish", "strong")


def test_leaf_beats_parent():
    # "quick-breads" is also tagged "breads", but the leaf should win.
    result = tags.classify(["breads", "quick-breads"])
    assert result[0] == "quick_bread"


def test_parent_tag_gives_medium():
    assert tags.classify(["cakes"]) == ("cake", "cakes", "medium")
    assert tags.classify(["breads"]) == ("bread", "breads", "medium")


def test_desserts_umbrella_does_not_demote_real_class():
    # "desserts" co-occurs with everything; it must not create a competing class.
    result = tags.classify(["desserts", "cakes"])
    assert result[0] == "cake"
    assert result[2] == "medium"


def test_desserts_only_is_weak_tier():
    assert tags.classify(["desserts"]) == ("dessert_other", "desserts", "weak")


def test_dropped_facet_tags():
    # "yeast" is a facet, not a dish class; alone it resolves to nothing.
    assert tags.classify(["yeast"]) is None


def test_no_tags():
    assert tags.classify([]) is None


def test_pastry_title_rescue_keywords():
    assert tags.is_pastry_title("Butter Croissants")
    assert tags.is_pastry_title("Choux Puffs")
    assert not tags.is_pastry_title("Chocolate Chip Cookies")


def test_primary_classes_count():
    assert len(config.PRIMARY_CLASSES) == 7
    assert "dessert_other" not in config.PRIMARY_CLASSES
    assert {"pie_pastry", "brownies"} <= set(config.PRIMARY_CLASSES)