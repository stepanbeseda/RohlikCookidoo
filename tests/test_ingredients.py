"""Tests for ingredient parsing and aggregation."""

import pytest

from rohlik_cookidoo.ingredients import (
    aggregate_ingredients,
    parse_ingredient,
    parse_ingredients,
    parse_recipe_ingredients,
    scale_ingredients,
)


class TestParseIngredient:
    def test_name_and_quantity(self):
        result = parse_ingredient("másla, změklého", "50 gramů")
        assert (result.quantity, result.unit) == (50, "g")
        assert result.name == "másla, změklého"
        assert result.search_term == "másla"
        assert result.original == "50 gramů másla, změklého"

    def test_unit_inside_the_name(self):
        result = parse_ingredient("stroužek česneku", "2")
        assert (result.quantity, result.unit, result.name) == (2, "stroužek", "česneku")

    def test_name_that_only_looks_like_a_unit(self):
        result = parse_ingredient("listové těsto", "1")
        assert (result.quantity, result.unit, result.name) == (1, None, "listové těsto")

    def test_free_text(self):
        result = parse_ingredient("200 g hladká mouka")
        assert (result.quantity, result.unit, result.name) == (200, "g", "hladká mouka")

    def test_free_text_without_space_before_unit(self):
        result = parse_ingredient("200g mouka")
        assert (result.quantity, result.unit, result.name) == (200, "g", "mouka")

    def test_number_without_unit(self):
        result = parse_ingredient("3 vejce")
        assert (result.quantity, result.unit, result.name) == (3, None, "vejce")

    def test_no_quantity(self):
        result = parse_ingredient("sůl")
        assert (result.quantity, result.unit, result.name) == (None, None, "sůl")

    def test_to_taste(self):
        result = parse_ingredient("pepř podle chuti")
        assert result.quantity is None
        assert result.search_term == "pepř"

    def test_quantity_without_number_is_ignored(self):
        result = parse_ingredient("sůl", "podle chuti")
        assert (result.quantity, result.unit, result.name) == (None, None, "sůl")

    def test_parse_ingredients_skips_blank_lines(self):
        assert len(parse_ingredients(["200 g mouka", "", "  ", "100 ml mléko"])) == 2

    def test_recipe_from_cookidoo_server(self):
        recipe = {
            "name": "Zelný hrnec",
            "ingredients": [
                {"name": "cibule", "quantity": "200 gramů"},
                {"name": "rajčata - sušená", "quantity": "50 g"},
                {"name": "soli", "quantity": ""},
            ],
        }
        result = parse_recipe_ingredients(recipe)
        assert [(i.name, i.quantity, i.unit) for i in result] == [
            ("cibule", 200, "g"),
            ("rajčata - sušená", 50, "g"),
            ("soli", None, None),
        ]

    def test_recipe_without_ingredients(self):
        assert parse_recipe_ingredients({"name": "Test"}) == []


class TestAggregateIngredients:
    def _one(self, recipes):
        result = aggregate_ingredients(recipes)
        assert len(result) == 1
        return result[0]

    def test_same_unit_sums(self):
        item = self._one([
            ("Palačinky", [parse_ingredient("200 g hladká mouka")]),
            ("Buchty", [parse_ingredient("300 g hladká mouka")]),
        ])
        assert (item.total_quantity, item.unit) == (500, "g")

    def test_kg_and_g(self):
        item = self._one([
            ("A", [parse_ingredient("200 g mouka")]),
            ("B", [parse_ingredient("0.5 kg mouka")]),
        ])
        assert (item.total_quantity, item.unit) == (700, "g")

    def test_ml_and_l(self):
        item = self._one([
            ("A", [parse_ingredient("500 ml mléko")]),
            ("B", [parse_ingredient("1 l mléko")]),
        ])
        assert (item.total_quantity, item.unit) == (1500, "ml")

    def test_case_forms_are_the_same_ingredient(self):
        item = self._one([
            ("A", [parse_ingredient("másla", "50 gramů")]),
            ("B", [parse_ingredient("máslo", "200 g")]),
        ])
        assert item.total_quantity == 250

    def test_note_after_comma_does_not_split(self):
        item = self._one([
            ("A", [parse_ingredient("1 cibule, nakrájená")]),
            ("B", [parse_ingredient("1 cibule")]),
        ])
        assert (item.name, item.total_quantity) == ("cibule", 2)

    def test_plain_count_and_ks_are_the_same(self):
        item = self._one([
            ("A", [parse_ingredient("2 ks vejce")]),
            ("B", [parse_ingredient("3 vejce")]),
        ])
        assert (item.total_quantity, item.unit) == (5, "ks")

    def test_different_unit_groups_stay_separate(self):
        result = aggregate_ingredients([
            ("A", [parse_ingredient("2 lžíce olivový olej")]),
            ("B", [parse_ingredient("100 g olivový olej")]),
        ])
        assert len(result) == 2

    @pytest.mark.parametrize("order", [("vejce", "3 vejce"), ("3 vejce", "vejce")])
    def test_missing_amount_does_not_lose_the_total(self, order):
        item = self._one([
            ("A", [parse_ingredient(order[0])]),
            ("B", [parse_ingredient(order[1])]),
        ])
        assert item.total_quantity == 3
        assert item.unspecified_amount is True

    def test_no_amount_anywhere(self):
        item = self._one([
            ("A", [parse_ingredient("sůl")]),
            ("B", [parse_ingredient("soli")]),
        ])
        assert item.total_quantity is None
        assert item.unspecified_amount is True

    def test_sources_tracked(self):
        item = self._one([
            ("Palačinky", [parse_ingredient("500 g mouka")]),
            ("Buchty", [parse_ingredient("0.2 kg mouka")]),
        ])
        assert item.sources == ["Palačinky (500 g)", "Buchty (0.2 kg)"]

    def test_several_recipes(self):
        result = aggregate_ingredients([
            ("Palačinky", parse_ingredients(["200 g hladká mouka", "300 ml mléko", "2 ks vejce"])),
            ("Omeleta", parse_ingredients(["4 ks vejce", "100 ml mléko", "sůl"])),
            ("Buchty", parse_ingredients(["300 g hladká mouka", "1 ks vejce"])),
        ])
        totals = {item.name: item.total_quantity for item in result}
        assert totals == {"hladká mouka": 500, "mléko": 400, "vejce": 7, "sůl": None}


def test_scale_ingredients():
    scaled = scale_ingredients(parse_ingredients(["300 g mouka", "sůl"]), 4 / 6)
    assert scaled[0].quantity == pytest.approx(200)
    assert scaled[1].quantity is None
