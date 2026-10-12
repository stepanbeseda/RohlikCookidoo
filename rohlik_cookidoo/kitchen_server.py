"""Kitchen MCP server for RohlikCookidoo.

Deterministic helpers for turning recipes into a shopping list: summing
ingredients across recipes, checking them against the home pantry and working
out how many packages to buy. It needs no credentials and no network.

Run it with `fastmcp run kitchen_server.py` from the repository root.
PANTRY_PATH overrides the pantry file location (default: pantry.txt in the
repository root).
"""

from typing import NotRequired, TypedDict

from fastmcp import FastMCP

from rohlik_cookidoo.ingredients import (
    aggregate_ingredients,
    format_quantity,
    parse_recipe_ingredients,
    scale_ingredients,
)
from rohlik_cookidoo.packages import packages_needed
from rohlik_cookidoo.pantry import (
    CHECK,
    HAVE,
    add_pantry_item,
    match_pantry,
    read_pantry_lines,
    remove_pantry_item,
)

mcp = FastMCP("kitchen")


class RecipeIngredient(TypedDict):
    name: str
    quantity: NotRequired[str]


class Recipe(TypedDict):
    name: str
    ingredients: list[RecipeIngredient]
    servings: NotRequired[int]
    target_servings: NotRequired[int]


class PackageRequest(TypedDict):
    name: str
    package_amount: str
    quantity: NotRequired[float | None]
    unit: NotRequired[str | None]


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
        elif status == CHECK:
            result["check_at_home"].append({**entry, "pantry_item": pantry_item})
        else:
            result["to_buy"].append(entry)
    return result


def plan_package_counts(items: list[PackageRequest]) -> list[dict]:
    """Work out the package count for each requested item."""
    return [
        {
            "name": item["name"],
            **packages_needed(item.get("quantity"), item.get("unit"), item["package_amount"]),
        }
        for item in items
    ]


@mcp.tool()
def aggregate_ingredients_for_shopping(recipes: list[Recipe]) -> dict:
    """Turn recipes into one shopping list. Use this instead of adding amounts up yourself.

    Pass each recipe as returned by the Cookidoo get_recipe_details tool
    (`name`, `servings`, `ingredients` with `name` and `quantity`). Set
    `target_servings` on a recipe to scale it to a different number of portions.

    Returns three lists of ingredients, each with the total `quantity`, `unit`,
    a `display` text and the `sources` it came from:
    - `to_buy`: not in the pantry
    - `check_at_home`: the pantry has something similar (`pantry_item`), e.g.
      "olej" for "sezamový olej". Decide per item, and tell the user.
    - `at_home`: in the pantry, do not buy. The pantry has no amounts, so
      mention items needed in a large quantity (e.g. 300 g of butter).

    Ingredient names keep the form used by the recipe (often the Czech
    genitive, "másla"); convert them to the nominative when searching a shop.
    `unspecified_amount` means a recipe asks for it "to taste" on top of the total.
    """
    return build_shopping_list(recipes, read_pantry_lines())


@mcp.tool()
def plan_packages(items: list[PackageRequest]) -> list[dict]:
    """Work out how many packages of a chosen product to buy.

    For each item pass its `name`, the needed `quantity` and `unit` from the
    shopping list, and the product's `package_amount` as shown by the shop
    ("500 g", "4 x 125 g", "1 l").

    Each result has `packages`, and `exact`: when false, read `note` (for
    example grams compared with litres, or pieces compared with kilograms)
    and use your own judgement.
    """
    return plan_package_counts(items)


@mcp.tool()
def get_pantry_items() -> dict:
    """List the ingredients the user keeps at home and does not want to buy."""
    return {"items": read_pantry_lines()}


@mcp.tool()
def add_to_pantry(item: str) -> dict:
    """Add an ingredient to the pantry file, e.g. after the user says they always have it."""
    return {"added": add_pantry_item(item), "items": read_pantry_lines()}


@mcp.tool()
def remove_from_pantry(item: str) -> dict:
    """Remove an ingredient from the pantry file, e.g. when the user has run out."""
    return {"removed": remove_pantry_item(item), "items": read_pantry_lines()}


if __name__ == "__main__":
    mcp.run()
