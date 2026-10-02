"""Tests for the Aid builder: data compilation + packing."""

import json
import re

import pandas as pd
import pytest

import config
from src.aid import pack as aid_pack
from src.aid import web as aid_web
from src.dataset import PROPORTION_COLUMNS


def make_frame(n: int = 4) -> pd.DataFrame:
    ings = ["['butter', 'chocolate chips']", "['butter']",
            "['yeast', 'firmly packed brown sugar']", "['vanilla']"]
    rows = []
    for i in range(n):
        row = {"recipe_id": str(100 + i), "name": f"Recipe {i}",
               "tag_coarse": ["cake", "cookie"][i % 2], "tag_fine": "x",
               "flour_g": 100.0, "sugar_g": 50.0, "fat_g": 25.0,
               "egg_g": 10.0, "milk_g": 5.0, "water_g": 0.0,
               "salt_g": 1.0, "leavener_g": 2.0, "yeast_g": 0.0,
               "ingredients_raw": ings[i % len(ings)],
               "url": "www.food.com/recipe/r-" + str(100 + i)}
        for j, col in enumerate(PROPORTION_COLUMNS):
            row[col] = round(0.1 + 0.2 * j, 6)
        rows.append(row)
    df = pd.DataFrame(rows)
    total = df[PROPORTION_COLUMNS].sum(axis=1)
    for col in PROPORTION_COLUMNS:
        df[col] = df[col] / total
    return df


def parse_data_js(text: str) -> dict:
    assert text.startswith("AID_DATA = ") and text.endswith(";\n")
    return json.loads(text[len("AID_DATA = "):-2])


def test_build_data_roundtrip(tmp_path):
    df = make_frame()
    path = aid_web.build_data(df, str(tmp_path))
    data = parse_data_js(open(path, encoding="utf-8").read())

    assert data["meta"]["n"] == 4
    assert data["meta"]["partNames"] == ["flour", "liquid", "egg", "fat", "sugar"]
    assert data["recipes"]["name"] == [f"Recipe {i}" for i in range(4)]
    assert data["recipes"]["cls"] == ["cake", "cookie", "cake", "cookie"]
    assert all(u.startswith("https://") for u in data["recipes"]["url"])
    for row in data["recipes"]["P"]:
        assert abs(sum(row) - 1.0) < 1e-3


def test_build_data_ingredient_index(tmp_path):
    df = make_frame()
    path = aid_web.build_data(df, str(tmp_path))
    data = parse_data_js(open(path, encoding="utf-8").read())

    assert data["heads"] == ["brown sugar", "butter", "chocolate chips",
                             "vanilla", "yeast"]
    assert data["index"]["butter"] == [0, 1]
    assert data["index"]["chocolate chips"] == [0]
    assert data["index"]["brown sugar"] == [2]
    assert data["index"]["yeast"] == [2]
    assert data["index"]["vanilla"] == [3]


def test_build_data_index_parses_and_dedupes(tmp_path):
    """Heads come from parsing ingredients_raw (prep words stripped, deduped).

    The index no longer touches recipe_id, so integer ids are safe here.
    """
    df = make_frame()
    df["recipe_id"] = df["recipe_id"].astype(int)
    df.loc[0, "ingredients_raw"] = "['1/2 cup firmly packed brown sugar', 'brown sugar']"
    path = aid_web.build_data(df, str(tmp_path))
    data = parse_data_js(open(path, encoding="utf-8").read())

    assert data["index"]["brown sugar"] == [0, 2]


def test_build_data_percentiles_and_archetypes(tmp_path):
    df = make_frame()
    path = aid_web.build_data(df, str(tmp_path))
    data = parse_data_js(open(path, encoding="utf-8").read())

    for cls, parts in data["percentiles"].items():
        for part, qs in parts.items():
            assert qs == sorted(qs)
    assert {a["name"] for a in data["archetypes"]}
    for a in data["archetypes"]:
        assert abs(sum(a["P"]) - 1.0) < 1e-3


def test_build_data_deterministic(tmp_path):
    df = make_frame()
    a = aid_web.build_data(df, str(tmp_path / "a"))
    b = aid_web.build_data(df, str(tmp_path / "b"))
    assert open(a, "rb").read() == open(b, "rb").read()


def test_pack_inlines_everything(tmp_path):
    df = make_frame()
    aid_web.build_data(df, str(tmp_path))
    path = aid_pack.pack(str(tmp_path))
    html = open(path, encoding="utf-8").read()

    assert 'src="' not in html and 'href="style.css"' not in html
    assert "AID_DATA = " in html
    assert "Baker's Aid" in html


def test_pack_deterministic_and_escapes_script(tmp_path):
    df = make_frame()
    df.loc[0, "name"] = 'Cake </script><script>alert(1)</script>'
    out_a, out_b = str(tmp_path / "a"), str(tmp_path / "b")
    aid_web.build_data(df, out_a)
    aid_web.build_data(df, out_b)
    a = aid_pack.pack(out_a)
    b = aid_pack.pack(out_b)
    raw = open(a, "rb").read()
    assert raw == open(b, "rb").read()

    html = raw.decode("utf-8")
    data_js = re.search(r"AID_DATA = (.*?);\n</script>", html, re.S).group(1)
    # the hostile name must survive as escaped JSON, decoded intact
    payload = json.loads(data_js)
    assert payload["recipes"]["name"][0] == 'Cake </script><script>alert(1)</script>'

def test_real_dataset_index_is_populated():
    """Integration: the committed dataset must yield a populated index.

    Runs in the normal checkout; skips on a fresh clone without the dataset.
    """
    import os
    if not os.path.exists(config.PROCESSED_RECIPES_CSV):
        pytest.skip("dataset not built")
    from src import dataset
    df, _ = dataset.load_recipes(config.PROCESSED_RECIPES_CSV)
    heads, index = aid_web._ingredient_index(df)

    assert len(heads) > 1000
    assert all(index[h] for h in heads)
    assert index["flour"] and index["sugar"] and index["butter"]
    # positions are valid recipe rows
    assert max(index["flour"]) < len(df)
