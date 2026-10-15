"""Building a shopping list from recipes and the user's household."""

from typing import NotRequired, TypedDict

from rohlik_cookidoo.household import ASK, CHECK, HAVE, Household
from rohlik_cookidoo.ingredients import (
    aggregate_ingredients,
    format_quantity,
    parse_recipe_ingredients,
    scale_ingredients,
)


class RecipeIngredient(TypedDict):
    name: str
    quantity: NotRequired[str]


class Recipe(TypedDict):
    name: str
    ingredients: list[RecipeIngredient]
    servings: NotRequired[int]
    target_servings: NotRequired[int]


def build_shopping_list(recipes: list[Recipe], household: Household) -> dict:
    """Sum the recipes' ingredients and sort them by what the pantry covers."""
    parsed = []
    for recipe in recipes:
        ingredients = parse_recipe_ingredients(recipe)
        servings, target = recipe.get("servings"), recipe.get("target_servings")
        if servings and target and servings != target:
            ingredients = scale_ingredients(ingredients, target / servings)
        parsed.append((recipe["name"], ingredients))

    result: dict[str, list[dict]] = {"to_buy": [], "check_at_home": [], "at_home": []}
    items = aggregate_ingredients(parsed)
    for item, found in zip(items, household.look_up(i.name for i in items), strict=True):
        status, pantry_item = found.pantry_status, found.pantry_item
        entry = {
            "name": item.name,
            "quantity": item.total_quantity,
            "unit": item.unit,
            "display": format_quantity(item.total_quantity, item.unit),
            "unspecified_amount": item.unspecified_amount,
            "sources": item.sources,
        }
        if status == HAVE:
            result["at_home"].append({**entry, "pantry_item": pantry_item})
            continue

        if found.usual_product:
            entry["usual_product"] = found.usual_product
        if status in (ASK, CHECK):
            entry["pantry_item"] = pantry_item
            entry["check_reason"] = "ask_user" if status == ASK else "similar_item"
            result["check_at_home"].append(entry)
        else:
            result["to_buy"].append(entry)
    return result
