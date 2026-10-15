"""The shopping list module: the first shopping step, from a request to the list.

`prepare` is the only entry point. It collects the recipes (given ones,
Cookidoo IDs, or the week's plan from the recipe source), decides once per
recipe how many servings it is shopped for, sums the ingredients and sorts
them by what the household has at home, and adds the household's
preferences. A recipe that cannot be loaded is reported in `failed`; it does
not stop the others.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import NotRequired, Protocol, TypedDict

from rohlik_cookidoo.amount import format_quantity
from rohlik_cookidoo.cookidoo import CookidooError
from rohlik_cookidoo.household import ASK, CHECK, HAVE, Household
from rohlik_cookidoo.ingredients import (
    aggregate_ingredients,
    parse_recipe_ingredients,
    scale_ingredients,
)

logger = logging.getLogger(__name__)


class RecipeIngredient(TypedDict):
    name: str
    quantity: NotRequired[str]


class Recipe(TypedDict):
    name: str
    ingredients: list[RecipeIngredient]
    servings: NotRequired[int]
    target_servings: NotRequired[int]


class RecipeSource(Protocol):
    """Where recipes come from: `CookidooClient` in production, a fake in tests.

    Both methods raise `CookidooError` when the source fails.
    """

    async def week(self, week_offset: int = 0) -> dict: ...

    async def recipe(self, recipe_id: str) -> dict: ...


class ShoppingError(ValueError):
    """The request cannot be served as asked; the message says what to fix."""


@dataclass(frozen=True)
class _Portion:
    """One recipe as it is shopped for."""

    recipe: dict
    factor: float  # multiply the recipe's amounts by this
    summary: dict  # the entry in the result's `recipes`


async def prepare(
    source: RecipeSource,
    household: Household,
    *,
    week_offset: int = 0,
    recipe_ids: list[str] | None = None,
    recipes: list[Recipe] | None = None,
    target_servings: int | None = None,
) -> dict:
    """Build the first shopping step's result for the given recipes.

    Without `recipe_ids` and `recipes` it shops for the week `week_offset`
    weeks from now. Raises `ShoppingError` for a request it cannot serve and
    `CookidooError` when the week cannot be loaded.
    """
    _check_targets(recipes, target_servings)
    request, collected, failed = await _collect(source, week_offset, recipe_ids, recipes)
    portions = [_portion(recipe, target_servings) for recipe in collected]
    pantry = household.pantry()
    return {
        **request,
        "failed": failed,
        "recipes": [portion.summary for portion in portions],
        **_shopping_list(portions, household),
        "preferences": household.preferences(),
        "pantry_setup_needed": not (pantry["always_at_home"] or pantry["ask_first"]),
    }


def _check_targets(recipes: list[Recipe] | None, target_servings: int | None) -> None:
    """Refuse a number of servings below one before anything is loaded."""
    if target_servings is not None:
        if target_servings < 1:
            raise ShoppingError(f"target_servings must be 1 or more, not {target_servings}")
        return
    for recipe in recipes or []:
        own = recipe.get("target_servings")
        if own is not None and own < 1:
            raise ShoppingError(
                f'recipe "{recipe["name"]}": target_servings must be 1 or more, not {own}'
            )


async def _collect(
    source: RecipeSource,
    week_offset: int,
    recipe_ids: list[str] | None,
    recipes: list[Recipe] | None,
) -> tuple[dict, list[dict], list[dict]]:
    """Gather the recipes: given ones, Cookidoo IDs, or the weekly plan.

    Returns (where they came from, the recipes, the ones that failed).
    """
    request: dict = {"source": "recipes"}
    ids = list(recipe_ids or [])
    if not ids and not recipes:
        week = await source.week(week_offset)
        request = {"source": "week", "week_start": week["week_start"]}
        ids = [recipe["id"] for day in week["days"] for recipe in day["recipes"]]

    fetched = await asyncio.gather(
        *(source.recipe(recipe_id) for recipe_id in ids), return_exceptions=True
    )
    collected, failed = [], []
    for recipe_id, outcome in zip(ids, fetched, strict=True):
        if isinstance(outcome, CookidooError):
            failed.append({"id": recipe_id, "error": str(outcome)})
        elif isinstance(outcome, Exception):
            # One recipe that cannot be loaded must not cost the whole list
            logger.warning("Loading recipe %s failed", recipe_id, exc_info=outcome)
            error = f"Loading the recipe failed: {_describe(outcome)}"
            failed.append({"id": recipe_id, "error": error})
        elif isinstance(outcome, BaseException):
            raise outcome
        else:
            collected.append(outcome)
    collected.extend(recipes or [])
    return request, collected, failed


def _describe(error: Exception) -> str:
    """Name an unexpected error: its type, and its text when it has one."""
    text = str(error)
    return f"{type(error).__name__}: {text}" if text else type(error).__name__


def _portion(recipe: dict, target_servings: int | None) -> _Portion:
    """Decide how many servings a recipe is shopped for; the one place that does."""
    servings = recipe.get("servings")
    target = target_servings if target_servings is not None else recipe.get("target_servings")
    summary = {
        "id": recipe.get("id"),
        "name": recipe["name"],
        "servings": servings,
        "url": recipe.get("url"),
    }
    if target is None:
        return _Portion(recipe, 1, summary)
    if not servings or servings < 1:
        summary["note"] = (
            "the recipe does not say how many servings it makes,"
            f" so its amounts are not scaled to {target}"
        )
        return _Portion(recipe, 1, summary)
    return _Portion(recipe, target / servings, {**summary, "servings": target})


def _shopping_list(portions: list[_Portion], household: Household) -> dict:
    """Sum the recipes' ingredients and sort them by what the pantry covers."""
    parsed = []
    for portion in portions:
        ingredients = parse_recipe_ingredients(portion.recipe)
        if portion.factor != 1:
            ingredients = scale_ingredients(ingredients, portion.factor)
        parsed.append((portion.recipe["name"], ingredients))

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
