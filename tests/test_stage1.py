"""Tests for the stage-1 recipe decomposition (pipeline.analyze_ingredients)."""

import pytest

import config
from src.preprocess.pipeline import analyze_ingredients


def test_frying_oil_recorded_but_excluded_from_ratio():
    _, struct, _, _, _, _ = analyze_ingredients(
        ["1 cup flour", "1/2 cup sugar", "1 cup vegetable oil (for frying)"]
    )
    assert struct["flour_g"] == pytest.approx(125.0)
    assert struct["sugar_g"] == pytest.approx(100.0)
    assert struct["fat_g"] == pytest.approx(0.0)  # frying oil is not structure


def test_dusting_flour_with_extra_guard_stays_structural():
    _, struct, _, _, _, _ = analyze_ingredients(
        ["2 1/2 cups flour, plus extra for dusting", "1 cup water"]
    )
    assert struct["flour_g"] == pytest.approx(2.5 * 125.0)


def test_plain_dusting_line_excluded_from_ratio():
    interim, struct, _, _, _, _ = analyze_ingredients(
        ["1 cup flour", "1 tablespoon sugar, for dusting"]
    )
    assert struct["sugar_g"] == pytest.approx(0.0)
    rows = {r["raw"]: r for r in interim}
    assert rows["1 tablespoon sugar, for dusting"]["grams"] > 0  # still recorded
    assert rows["1 tablespoon sugar, for dusting"]["significant"] == 0


def test_pinch_dash_have_mass():
    _, struct, _, _, _, _ = analyze_ingredients(["1 cup flour", "1 pinch salt"])
    assert struct["salt_g"] == pytest.approx(config.PINCH_GRAMS)
    _, struct, _, _, _, _ = analyze_ingredients(["1 cup flour", "2 dashes salt"])
    assert struct["salt_g"] == pytest.approx(2 * config.DASH_GRAMS)


def test_range_endpoints_in_interim_rows():
    interim, _, _, _, _, _ = analyze_ingredients(["1 1/2 - 2 cups flour"])
    assert interim[0]["qty"] == pytest.approx(1.75)
    assert interim[0]["qty_low"] == pytest.approx(1.5)
    assert interim[0]["qty_high"] == pytest.approx(2.0)


def test_water_dominant_addin_contributes_water():
    interim, struct, _, _, _, _ = analyze_ingredients(
        ["1 cup flour", "1/2 cup unsweetened applesauce"]
    )
    vec = interim[1]["_vec"]
    frac = vec["water"] / sum(vec.values())
    assert frac > config.ADDIN_WATER_DOMINANT_SHARE
    assert struct["water_g"] == pytest.approx(interim[1]["grams"] * vec["water"])
    assert struct["flour_g"] == pytest.approx(125.0)
    assert struct["sugar_g"] == pytest.approx(0.0)  # produce sugars stay zeroed
    assert interim[1]["structural"] == 1


def test_non_water_addin_stays_zeroed():
    _, struct, _, _, _, _ = analyze_ingredients(
        ["1 cup flour", "1 cup chocolate chips"]
    )
    assert struct["fat_g"] == pytest.approx(0.0)
    assert struct["water_g"] == pytest.approx(0.0)
    assert struct["sugar_g"] == pytest.approx(0.0)
