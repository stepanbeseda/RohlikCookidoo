"""Tests for the ingredient parser."""

from ingredient_parser import (
    parse_single_ingredient,
    parse_ingredients,
    ingredient_lines_from_recipe,
    aggregate_ingredients,
    AggregatedIngredient,
)


class TestParseSingleIngredient:
    """Tests for parsing single ingredients."""

    def test_with_quantity_and_unit(self):
        result = parse_single_ingredient("200 g hladká mouka")
        assert result.name == "hladká mouka"
        assert result.quantity == 200.0
        assert result.unit == "g"
        assert result.search_term == "hladká mouka"

    def test_with_kg(self):
        result = parse_single_ingredient("1.5 kg brambory")
        assert result.name == "brambory"
        assert result.quantity == 1.5
        assert result.unit == "kg"

    def test_with_ml(self):
        result = parse_single_ingredient("100 ml mléko")
        assert result.name == "mléko"
        assert result.quantity == 100.0
        assert result.unit == "ml"

    def test_with_pieces(self):
        result = parse_single_ingredient("3 ks vejce")
        assert result.name == "vejce"
        assert result.quantity == 3.0
        assert result.unit == "ks"

    def test_with_tablespoon(self):
        result = parse_single_ingredient("2 lžíce olivový olej")
        assert result.name == "olivový olej"
        assert result.quantity == 2.0
        assert result.unit == "lžíce"

    def test_with_comma_decimal(self):
        result = parse_single_ingredient("0,5 l voda")
        assert result.quantity == 0.5
        assert result.unit == "l"

    def test_with_fraction(self):
        result = parse_single_ingredient("1/2 lžička skořice")
        assert result.quantity == 0.5
        assert result.unit == "lžička"

    def test_number_without_unit(self):
        result = parse_single_ingredient("3 vejce")
        assert result.name == "vejce"
        assert result.quantity == 3.0
        assert result.unit is None

    def test_no_quantity(self):
        result = parse_single_ingredient("sůl")
        assert result.name == "sůl"
        assert result.quantity is None
        assert result.unit is None

    def test_no_quantity_with_pepper(self):
        result = parse_single_ingredient("pepř podle chuti")
        assert result.name == "pepř podle chuti"
        assert result.quantity is None

    def test_empty_string(self):
        result = parse_single_ingredient("")
        assert result.name == ""
        assert result.quantity is None

    def test_clove(self):
        result = parse_single_ingredient("2 stroužky česnek")
        assert result.name == "česnek"
        assert result.quantity == 2.0
        assert result.unit == "stroužky"


class TestParseIngredients:
    """Tests for parsing a list of ingredients."""

    def test_multiple_ingredients(self):
        raw = ["200 g mouka", "100 ml mléko", "sůl"]
        result = parse_ingredients(raw)
        assert len(result) == 3
        assert result[0].name == "mouka"
        assert result[1].name == "mléko"
        assert result[2].name == "sůl"

    def test_skips_empty_lines(self):
        raw = ["200 g mouka", "", "  ", "100 ml mléko"]
        result = parse_ingredients(raw)
        assert len(result) == 2


class TestIngredientLinesFromRecipe:
    """Tests for turning a Cookidoo MCP recipe into ingredient lines."""

    def test_quantity_goes_first(self):
        recipe = {
            "name": "Palačinky",
            "ingredients": [
                {"name": "hladká mouka", "quantity": "200 g"},
                {"name": "vejce", "quantity": "2"},
                {"name": "sůl", "quantity": ""},
            ],
        }
        result = ingredient_lines_from_recipe(recipe)
        assert result == ["200 g hladká mouka", "2 vejce", "sůl"]

    def test_name_with_dash_is_kept_whole(self):
        recipe = {"ingredients": [{"name": "rajčata - sušená", "quantity": "50 g"}]}
        assert ingredient_lines_from_recipe(recipe) == ["50 g rajčata - sušená"]

    def test_no_ingredients(self):
        assert ingredient_lines_from_recipe({"name": "Test"}) == []


class TestAggregateIngredients:
    """Tests for aggregating ingredients across recipes."""

    def _make(self, text: str):
        return parse_single_ingredient(text)

    def test_same_unit_sums(self):
        """200g mouka + 300g mouka = 500g mouka."""
        recipes = [
            ("Palačinky", [self._make("200 g hladká mouka")]),
            ("Buchty", [self._make("300 g hladká mouka")]),
        ]
        result = aggregate_ingredients(recipes)
        assert len(result) == 1
        assert result[0].total_quantity == 500.0
        assert result[0].unit == "g"

    def test_convertible_units_kg_and_g(self):
        """200g + 0.5kg = 700g (converted to grams)."""
        recipes = [
            ("Recept A", [self._make("200 g mouka")]),
            ("Recept B", [self._make("0.5 kg mouka")]),
        ]
        result = aggregate_ingredients(recipes)
        assert len(result) == 1
        assert result[0].total_quantity == 700.0
        assert result[0].unit == "g"

    def test_convertible_units_ml_and_l(self):
        """500ml + 1l = 1500ml."""
        recipes = [
            ("Recept A", [self._make("500 ml mléko")]),
            ("Recept B", [self._make("1 l mléko")]),
        ]
        result = aggregate_ingredients(recipes)
        assert len(result) == 1
        assert result[0].total_quantity == 1500.0
        assert result[0].unit == "ml"

    def test_different_units_kept_separate(self):
        """2 lžíce olej + 100g olej = 2 entries (cannot be summed)."""
        recipes = [
            ("Recept A", [self._make("2 lžíce olivový olej")]),
            ("Recept B", [self._make("100 g olivový olej")]),
        ]
        result = aggregate_ingredients(recipes)
        assert len(result) == 2

    def test_sources_tracked(self):
        """Every source is stored in sources."""
        recipes = [
            ("Palačinky", [self._make("500 g mouka")]),
            ("Buchty", [self._make("200 g mouka")]),
        ]
        result = aggregate_ingredients(recipes)
        assert len(result[0].sources) == 2
        assert any("Palačinky" in s for s in result[0].sources)
        assert any("Buchty" in s for s in result[0].sources)

    def test_unique_ingredient_one_source(self):
        """An ingredient from one recipe has one source."""
        recipes = [
            ("Tiramisu", [self._make("250 g mascarpone")]),
        ]
        result = aggregate_ingredients(recipes)
        assert len(result[0].sources) == 1

    def test_unit_normalization(self):
        """'gramů' is normalized to 'g' and summed correctly."""
        recipes = [
            ("Recept A", [self._make("200 gramů rýže")]),
            ("Recept B", [self._make("100 g rýže")]),
        ]
        result = aggregate_ingredients(recipes)
        assert len(result) == 1
        assert result[0].total_quantity == 300.0
        assert result[0].unit == "g"

    def test_no_quantity_ingredient(self):
        """Ingredients without a quantity (sůl, pepř) are kept."""
        recipes = [
            ("Recept A", [self._make("sůl")]),
            ("Recept B", [self._make("sůl")]),
        ]
        result = aggregate_ingredients(recipes)
        assert len(result) == 1
        assert result[0].total_quantity is None

    def test_multiple_recipes_multiple_ingredients(self):
        """Full test with several recipes and ingredients."""
        recipes = [
            ("Palačinky", parse_ingredients(["200 g hladká mouka", "300 ml mléko", "2 ks vejce"])),
            ("Omeleta", parse_ingredients(["4 ks vejce", "100 ml mléko", "sůl"])),
            ("Buchty", parse_ingredients(["300 g hladká mouka", "1 ks vejce"])),
        ]
        result = aggregate_ingredients(recipes)

        result_by_name = {r.name: r for r in result}

        # mouka: 200 + 300 = 500 g
        assert result_by_name["hladká mouka"].total_quantity == 500.0
        # mléko: 300 + 100 = 400 ml
        assert result_by_name["mléko"].total_quantity == 400.0
        # vejce: 2 + 4 + 1 = 7 (no unit, plain numbers)
        assert result_by_name["vejce"].total_quantity == 7.0
        # sůl: no quantity
        assert result_by_name["sůl"].total_quantity is None
