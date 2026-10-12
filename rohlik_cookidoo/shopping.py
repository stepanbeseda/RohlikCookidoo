"""Building a shopping list from recipes, the pantry and the user's memory."""

from typing import NotRequired, TypedDict

from rohlik_cookidoo import memory
from rohlik_cookidoo.ingredients import (
    aggregate_ingredients,
    format_quantity,
    parse_recipe_ingredients,
    scale_ingredients,
)
from rohlik_cookidoo.pantry import ASK, CHECK, HAVE, match_pantry, split_marker


class RecipeIngredient(TypedDict):
    name: str
    quantity: NotRequired[str]


class Recipe(TypedDict):
    name: str
    ingredients: list[RecipeIngredient]
    servings: NotRequired[int]
    target_servings: NotRequired[int]


def build_shopping_list(recipes: list[Recipe], pantry_items: list[str]) -> dict:
    """Sum the recipes' ingredients and sort them by what the pantry covers."""
    parsed = []
    for recipe in recipes:
        ingredients = parse_recipe_ingredients(recipe)
        servings, target = recipe.get("servings"), recipe.get("target_servings")
        if servings and target and servings != target:
            ingredients = scale_ingredients(ingredients, target / servings)
        parsed.append((recipe["name"], ingredients))

    result: dict[str, list[dict]] = {"to_buy": [], "check_at_home": [], "at_home": []}
    for item in aggregate_ingredients(parsed):
        status, pantry_item = match_pantry(item.name, pantry_items)
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

        usual = memory.recall_product(item.name)
        if usual:
            entry["usual_product"] = usual
        if status in (ASK, CHECK):
            entry["pantry_item"] = pantry_item
            entry["check_reason"] = "ask_user" if status == ASK else "similar_item"
            result["check_at_home"].append(entry)
        else:
            result["to_buy"].append(entry)
    return result


def pantry_overview(lines: list[str]) -> dict:
    """Split pantry lines into always-at-home items and ask-first items."""
    items = [split_marker(line) for line in lines]
    return {
        "always_at_home": [name for name, ask in items if not ask],
        "ask_first": [name for name, ask in items if ask],
    }
