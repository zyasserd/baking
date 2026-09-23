"""Tests for the ingredient parser (standard form: qty/unit/head/props/note)."""

import pytest

from src import parse


def test_plain_ingredient():
    p = parse.parse_ingredient("1/2 cup flour")
    assert p.qty == pytest.approx(0.5)
    assert p.unit == "cup"
    assert p.head == "flour"
    assert p.props == []


def test_prep_props_stripped_from_head():
    p = parse.parse_ingredient("1 cup firmly packed brown sugar")
    assert p.head == "brown sugar"
    assert "firmly" in p.props and "packed" in p.props


def test_trailing_comma_prop():
    p = parse.parse_ingredient("2 cups grated parmesan cheese, grated")
    assert p.head == "parmesan cheese"
    assert "grated" in p.props


def test_compositional_modifiers_kept():
    assert parse.parse_ingredient("2 cups whole wheat flour").head == "whole wheat flour"
    assert parse.parse_ingredient("1 cup powdered sugar").head == "powdered sugar"
    assert parse.parse_ingredient("1 cup unsweetened cocoa").head == "unsweetened cocoa"


def test_parenthetical_note():
    p = parse.parse_ingredient("1 (8 oz.) pkg. cream cheese, softened")
    assert p.head == "cream cheese"
    assert p.note is not None and "8 oz" in p.note


def test_or_resolution():
    p = parse.parse_ingredient("1/2 cup butter or margarine")
    assert p.head == "butter"


def test_no_quantity():
    p = parse.parse_ingredient("salt to taste")
    assert p.qty is None
    assert p.unit is None
