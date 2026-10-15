"""Parsing and aggregation of recipe ingredients.

Turns an ingredient (a name plus a quantity such as "250 gramů" or
"1 vrchovatá čajová lžička") into structured data, and sums the same
ingredient across recipes. Numbers and units are read by `rohlik_cookidoo.amount`.
"""

from dataclasses import dataclass, field

from rohlik_cookidoo.amount import Amount, format_quantity, parse_amount, split_unit
from rohlik_cookidoo.text import clean_name, name_key, normalize


@dataclass
class ParsedIngredient:
    """A single parsed recipe ingredient."""
    original: str           # Text as received: "200 g hladká mouka"
    name: str               # Ingredient name: "hladká mouka"
    quantity: float | None  # Amount: 200.0
    unit: str | None        # Canonical unit: "g"
    search_term: str        # Name without notes: "hladká mouka"


@dataclass
class AggregatedIngredient:
    """An ingredient summed across recipes."""
    name: str
    total_quantity: float | None
    unit: str | None
    sources: list[str] = field(default_factory=list)  # ["Palačinky (200 g)", ...]
    search_term: str = ""
    # True when some recipe lists it without an amount ("sůl podle chuti")
    unspecified_amount: bool = False


def parse_ingredient(name: str, quantity: str = "") -> ParsedIngredient:
    """Parse an ingredient given as a name and an optional quantity text.

    Without a quantity, the amount is read from the start of the name
    ("200 g hladká mouka"), which covers free-text recipes.
    """
    name = name.strip()
    quantity = quantity.strip()
    original = f"{quantity} {name}".strip()

    if quantity:
        amount, _ = parse_amount(quantity)
        if amount is not None and amount.unit is None:
            # Cookidoo sometimes keeps the unit in the name: "2" + "stroužek česneku"
            name_unit, rest = split_unit(name)
            if name_unit and rest:
                amount, name = Amount(amount.value, name_unit), rest
    else:
        amount, rest = parse_amount(name)
        if amount is not None and rest:
            name = rest

    return ParsedIngredient(
        original=original,
        name=name,
        quantity=None if amount is None else amount.value,
        unit=None if amount is None else amount.unit,
        search_term=clean_name(name),
    )


def parse_ingredients(raw_ingredients: list[str]) -> list[ParsedIngredient]:
    """Parse free-text ingredient lines, skipping blank ones."""
    return [parse_ingredient(text) for text in raw_ingredients if text.strip()]


def parse_recipe_ingredients(recipe: dict) -> list[ParsedIngredient]:
    """Parse the ingredients of a recipe from the Cookidoo MCP server.

    Each ingredient is {"name": ..., "quantity": ...}.
    """
    return [
        parse_ingredient(ingredient["name"], ingredient.get("quantity") or "")
        for ingredient in recipe.get("ingredients", [])
        if ingredient.get("name", "").strip()
    ]


def scale_ingredients(
    ingredients: list[ParsedIngredient], factor: float
) -> list[ParsedIngredient]:
    """Multiply all amounts, e.g. by target servings / recipe servings."""
    return [
        ParsedIngredient(
            original=i.original,
            name=i.name,
            quantity=None if i.quantity is None else i.quantity * factor,
            unit=i.unit,
            search_term=i.search_term,
        )
        for i in ingredients
    ]


def aggregate_ingredients(
    recipes_ingredients: list[tuple[str, list[ParsedIngredient]]],
) -> list[AggregatedIngredient]:
    """Sum ingredients across recipes.

    Args:
        recipes_ingredients: List of (recipe_name, [ParsedIngredient]) pairs

    Returns:
        One AggregatedIngredient per ingredient and unit group. Case forms and
        word order do not matter ("másla" + "máslo"), g/kg and ml/l are
        converted, plain counts and "ks" are the same thing. Amounts in
        different groups (grams and spoons) stay separate.
    """
    # An ingredient without an amount joins whatever entry already exists for it;
    # until some recipe gives an amount, its entry is filed under the group None.
    by_name: dict[frozenset[str], list[AggregatedIngredient]] = {}
    by_group: dict[tuple[frozenset[str], str | None], AggregatedIngredient] = {}
    result: list[AggregatedIngredient] = []

    for recipe_name, ingredients in recipes_ingredients:
        for ing in ingredients:
            key = name_key(ing.name) or frozenset({normalize(ing.name)})

            if ing.quantity is None:
                source = f"{recipe_name} ({format_quantity(None, None)})"
                if by_name.get(key):
                    entry = by_name[key][0]
                    entry.sources.append(source)
                    entry.unspecified_amount = True
                    continue
                quantity, unit, group = None, None, None
            else:
                base = Amount(ing.quantity, ing.unit).base()
                quantity, unit, group = base.value, base.unit, base.group
                source = f"{recipe_name} ({format_quantity(ing.quantity, ing.unit)})"

            entry = by_group.get((key, group))
            if entry is None and quantity is not None:
                # Adopt an entry that so far has no amount
                entry = by_group.pop((key, None), None)
                if entry is not None:
                    entry.total_quantity, entry.unit = 0.0, unit
                    by_group[(key, group)] = entry

            if entry is None:
                entry = AggregatedIngredient(
                    name=clean_name(ing.name),
                    total_quantity=quantity,
                    unit=unit,
                    sources=[source],
                    search_term=ing.search_term,
                    unspecified_amount=quantity is None,
                )
                by_group[(key, group)] = entry
                by_name.setdefault(key, []).append(entry)
                result.append(entry)
            else:
                entry.sources.append(source)
                entry.total_quantity += quantity

    return result
