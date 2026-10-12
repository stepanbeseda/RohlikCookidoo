"""Tests for the home pantry."""

import pytest

from rohlik_cookidoo.pantry import (
    add_pantry_item,
    match_pantry,
    read_pantry_lines,
    remove_pantry_item,
)

PANTRY = ["sůl", "pepř", "voda", "olej", "máslo", "hladká mouka"]


@pytest.mark.parametrize(
    ("ingredient", "item"),
    [("másla", "máslo"), ("soli", "sůl"), ("vody", "voda"), ("hladké mouky", "hladká mouka"),
     ("Sůl, jemná", "sůl")],
)
def test_same_ingredient_is_at_home(ingredient, item):
    assert match_pantry(ingredient, PANTRY) == ("have", item)


@pytest.mark.parametrize(
    ("ingredient", "item"),
    [("arašídové máslo", "máslo"), ("kokosová voda", "voda"), ("sezamový olej", "olej"),
     ("mletého černého pepře", "pepř"), ("mouka", "hladká mouka")],
)
def test_similar_ingredient_needs_a_check(ingredient, item):
    assert match_pantry(ingredient, PANTRY) == ("check", item)


@pytest.mark.parametrize(
    "ingredient", ["podmáslí", "olejovky", "peprmint", "vepřové plece", "mandlové mléko", ""]
)
def test_unrelated_ingredient_is_not_in_pantry(ingredient):
    assert match_pantry(ingredient, PANTRY) == (None, None)


def test_exact_match_wins_over_similar():
    assert match_pantry("oleje", ["slunečnicový olej", "olej"]) == ("have", "olej")


class TestPantryFile:
    def test_skips_comments_and_blank_lines(self, tmp_path):
        pantry = tmp_path / "pantry.txt"
        pantry.write_text("# doma\nsůl\n\n  hladká mouka  \n", encoding="utf-8")
        assert read_pantry_lines(str(pantry)) == ["sůl", "hladká mouka"]

    def test_missing_file(self, tmp_path):
        assert read_pantry_lines(str(tmp_path / "none.txt")) == []

    def test_path_from_environment(self, tmp_path, monkeypatch):
        pantry = tmp_path / "p.txt"
        pantry.write_text("pepř\n", encoding="utf-8")
        monkeypatch.setenv("PANTRY_PATH", str(pantry))
        assert read_pantry_lines() == ["pepř"]

    def test_add_creates_file_and_skips_duplicates(self, tmp_path):
        pantry = str(tmp_path / "pantry.txt")
        assert add_pantry_item("sůl", pantry) is True
        assert add_pantry_item("soli", pantry) is False
        assert add_pantry_item("rýže", pantry) is True
        assert read_pantry_lines(pantry) == ["sůl", "rýže"]

    def test_add_to_file_without_trailing_newline(self, tmp_path):
        pantry = tmp_path / "pantry.txt"
        pantry.write_text("sůl", encoding="utf-8")
        add_pantry_item("pepř", str(pantry))
        assert read_pantry_lines(str(pantry)) == ["sůl", "pepř"]

    def test_remove_keeps_comments(self, tmp_path):
        pantry = tmp_path / "pantry.txt"
        pantry.write_text("# doma\nsůl\nmáslo\n", encoding="utf-8")
        assert remove_pantry_item("másla", str(pantry)) is True
        assert pantry.read_text(encoding="utf-8") == "# doma\nsůl\n"
        assert remove_pantry_item("rýže", str(pantry)) is False
