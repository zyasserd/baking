"""Tests for the density/conversion layer."""

import pytest

from src.preprocess import density


def test_weight_units_direct():
    assert density.to_grams("flour", 1.0, "kg", "flour") == pytest.approx(1000.0)
    assert density.to_grams("flour", 16.0, "oz", "flour") == pytest.approx(16 * 28.3495)


def test_volume_via_density():
    assert density.to_grams("flour", 1.0, "cup", "flour") == pytest.approx(125.0)
    assert density.to_grams("sugar", 1.0, "cup", "sugar") == pytest.approx(200.0)
    assert density.to_grams("fat", 1.0, "cup", "butter") == pytest.approx(227.0)
    assert density.to_grams("fat", 1.0, "cup", "vegetable oil") == pytest.approx(218.0)


def test_tsp_tbsp_scaling():
    assert density.to_grams("salt", 1.0, "tsp", "salt") == pytest.approx(288.0 / 48.0)
    assert density.to_grams("salt", 1.0, "tbsp", "salt") == pytest.approx(288.0 / 16.0)


def test_egg_count_and_parts():
    assert density.to_grams("egg", 2.0, None, "eggs") == pytest.approx(100.0)
    assert density.to_grams("egg", None, None, "egg") == pytest.approx(50.0)
    assert density.to_grams("egg", 1.0, None, "egg yolk") == pytest.approx(17.0)


def test_stick_of_butter():
    assert density.to_grams("fat", 1.0, "stick", "butter") == pytest.approx(113.0)
    assert density.to_grams("flour", 1.0, "stick", "flour") is None


def test_container_name_aware():
    assert density.to_grams("milk", 1.0, "can", "evaporated milk") == pytest.approx(354.0)
    assert density.to_grams("flour", 2.0, "can", "pumpkin") == pytest.approx(850.0)
    # parenthetical size hint wins over the default
    assert density.to_grams("milk", 1.0, "can", "tomatoes", "14.5 oz") == pytest.approx(14.5 * 28.3495)


def test_container_unknown_pkg():
    assert density.to_grams("milk", 1.0, "pkg", "mystery mix") is None