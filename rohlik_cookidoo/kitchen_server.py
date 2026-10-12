"""Kitchen MCP server for RohlikCookidoo.

Deterministic helpers for turning recipes into a shopping list: summing
ingredients across recipes, checking them against the home pantry, working
out how many packages to buy and what is still missing from the cart. It also
remembers the user's usual products and preferences. It needs no credentials
and no network.

Run it with `python kitchen_server.py` from the repository root.
PANTRY_PATH overrides the pantry file location (default: pantry.txt in the
repository root); products.json and preferences.json are kept next to it.
"""

from typing import NotRequired, TypedDict

from fastmcp import FastMCP

from rohlik_cookidoo import memory
from rohlik_cookidoo.cart import DEFAULT_MINIMUM_ORDER, plan_cart_additions
from rohlik_cookidoo.ingredients import (
    aggregate_ingredients,
    format_quantity,
    parse_recipe_ingredients,
    scale_ingredients,
)
from rohlik_cookidoo.packages import packages_needed
from rohlik_cookidoo.pantry import (
    ASK,
    CHECK,
    HAVE,
    add_pantry_item,
    match_pantry,
    read_pantry_lines,
    remove_pantry_item,
    split_marker,
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


class WantedProduct(TypedDict):
    name: str
    packages: int
    product_id: NotRequired[int]
    productId: NotRequired[int]
    price: NotRequired[float]


class CartLine(TypedDict):
    product_id: NotRequired[int]
    productId: NotRequired[int]
    quantity: NotRequired[float]


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
        "items": [name for name, ask in items if not ask],
        "ask_first": [name for name, ask in items if ask],
    }


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
    - `check_at_home`: read `check_reason`. "similar_item": the pantry has
      something similar (`pantry_item`), e.g. "olej" for "sezamový olej";
      decide per item and tell the user. "ask_user": the user usually has it
      but it runs out; ask them before buying or skipping.
    - `at_home`: in the pantry, do not buy. The pantry has no amounts, so
      mention items needed in a large quantity (e.g. 300 g of butter).

    Ingredient names keep the form used by the recipe (often the Czech
    genitive, "másla"); convert them to the nominative when searching a shop.
    `unspecified_amount` means a recipe asks for it "to taste" on top of the total.
    `usual_product` is the product the user bought for this ingredient last
    time; prefer it when it is still on offer.
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
    and use your own judgement. `leftover` is what remains after cooking.
    """
    return plan_package_counts(items)


@mcp.tool()
def plan_cart(
    items: list[WantedProduct],
    cart: list[CartLine] | None = None,
    cart_total: float = 0,
    minimum_order: float = DEFAULT_MINIMUM_ORDER,
) -> dict:
    """Work out what to add to the cart and what it costs. Do not do this sum yourself.

    Pass the chosen products (`name`, `product_id`, `packages`, `price` per
    package) and the current cart (`product_id`, `quantity`) with its total.
    `productId` works in place of `product_id`. Pass the shop's own minimum
    order as `minimum_order` when the cart reports it.

    Returns `to_add`, ready for the shop's add-to-cart tool and already
    reduced by what the cart holds, the per-product `lines`, `added_total`,
    `cart_total_after` and `missing_to_minimum` (above zero means the order
    would be below the shop's minimum).
    """
    return plan_cart_additions(items, cart, cart_total, minimum_order)


@mcp.tool()
def remember_product(
    ingredient: str, product_id: int, product_name: str, package_amount: str = ""
) -> dict:
    """Remember which product the user bought for an ingredient.

    Call it for each product after the user confirmed the cart. The next
    shopping list returns it as `usual_product`.
    """
    return {"remembered": memory.remember_product(ingredient, product_id, product_name, package_amount)}


@mcp.tool()
def forget_product(ingredient: str) -> dict:
    """Forget the usual product for an ingredient, e.g. when the user did not like it."""
    return {"forgotten": memory.forget_product(ingredient)}


@mcp.tool()
def get_shopping_preferences() -> dict:
    """Get what the user told you earlier about how they shop.

    `preferences` are free-form, e.g. {"quality": "bio", "diet": "bez lepku"}.
    `usual_products` are the products bought before, by ingredient.
    """
    return {
        "preferences": memory.get_preferences(),
        "usual_products": memory.list_products(),
    }


@mcp.tool()
def set_shopping_preference(key: str, value: str) -> dict:
    """Store a lasting shopping preference; an empty value removes it.

    Use short keys such as "quality" (bio / cheapest / best value / Rohlik
    brands), "diet" or "avoid". Store only what the user asked you to keep.
    """
    return {"preferences": memory.set_preference(key, value)}


@mcp.tool()
def get_pantry_items() -> dict:
    """List what the user keeps at home.

    `items` are always at home and never bought. `ask_first` are usually at
    home but run out (butter, eggs); the user is asked about them.
    """
    return pantry_overview(read_pantry_lines())


@mcp.tool()
def add_to_pantry(item: str, ask_first: bool = False) -> dict:
    """Add an ingredient to the pantry.

    Use `ask_first: true` for things the user usually has but that run out;
    otherwise the ingredient is never bought. Calling it again for an existing
    item changes its mode.
    """
    changed = add_pantry_item(item, ask=ask_first)
    return {"changed": changed, **pantry_overview(read_pantry_lines())}


@mcp.tool()
def remove_from_pantry(item: str) -> dict:
    """Remove an ingredient from the pantry, e.g. when the user no longer keeps it."""
    removed = remove_pantry_item(item)
    return {"removed": removed, **pantry_overview(read_pantry_lines())}


if __name__ == "__main__":
    mcp.run()
