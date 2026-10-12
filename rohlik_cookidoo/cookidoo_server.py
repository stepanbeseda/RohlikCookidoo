"""Cookidoo MCP server for RohlikCookidoo.

A thin read-only wrapper around the unofficial cookidoo-api library. It exposes
the weekly meal plan and recipe ingredients as structured data.

Run it with `python cookidoo_server.py` from the repository root.
Configuration comes from environment variables, with a `.env` file in the
repository root as a fallback:

    COOKIDOO_EMAIL, COOKIDOO_PASSWORD   account credentials (required)
    COOKIDOO_COUNTRY                    country code, default "cz"
    COOKIDOO_LANGUAGE                   language code, default "cs"
"""

import os
import re
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, CookieJar
from cookidoo_api import Cookidoo, CookidooConfig
from cookidoo_api.exceptions import CookidooAuthException, CookidooException
from cookidoo_api.helpers import get_localization_options
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

load_dotenv(Path(__file__).parent.parent / ".env")

mcp = FastMCP("cookidoo")

# Catalogue recipes have IDs like "r59322"; anything else is a user-created recipe
_CATALOGUE_RECIPE_ID = re.compile(r"r\d+")

_session: ClientSession | None = None
_api: Cookidoo | None = None


def week_start(today: date, week_offset: int = 0) -> date:
    """Return the Monday of the week `week_offset` weeks from `today`."""
    return today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)


def week_to_dict(days: list[Any], monday: date) -> dict:
    """Convert cookidoo-api calendar days to a plain dict."""
    result_days = []
    for day in days:
        if not day.recipes:
            continue
        custom_ids = set(getattr(day, "customer_recipe_ids", []) or [])
        result_days.append({
            "date": day.id,
            "title": day.title,
            "recipes": [
                {"id": r.id, "name": r.name, "custom": r.id in custom_ids}
                for r in day.recipes
            ],
        })
    return {
        "week_start": monday.isoformat(),
        "recipe_count": sum(len(d["recipes"]) for d in result_days),
        "days": result_days,
    }


def recipe_to_dict(recipe: Any) -> dict:
    """Convert a cookidoo-api catalogue recipe to a plain dict."""
    return {
        "id": recipe.id,
        "name": recipe.name,
        "servings": recipe.serving_size,
        "url": recipe.url,
        "ingredients": [
            {"name": i.name, "quantity": i.description} for i in recipe.ingredients
        ],
    }


def custom_recipe_to_dict(recipe: Any) -> dict:
    """Convert a user-created recipe to a plain dict.

    Its ingredients are free text, so the whole line goes to `name`.
    """
    return {
        "id": recipe.id,
        "name": recipe.name,
        "servings": recipe.serving_size,
        "url": recipe.url,
        "ingredients": [{"name": line, "quantity": ""} for line in recipe.ingredients],
    }


async def _login() -> Cookidoo:
    """Sign in to Cookidoo and keep the client for later calls."""
    global _session, _api

    email = os.getenv("COOKIDOO_EMAIL")
    password = os.getenv("COOKIDOO_PASSWORD")
    if not email or not password:
        raise ToolError("Missing COOKIDOO_EMAIL or COOKIDOO_PASSWORD.")

    country = os.getenv("COOKIDOO_COUNTRY", "cz")
    language = os.getenv("COOKIDOO_LANGUAGE", "cs")
    options = await get_localization_options(country=country, language=language)
    if not options:
        raise ToolError(
            f"Unknown Cookidoo localization: country={country!r}, language={language!r}."
        )

    if _session is not None:
        await _session.close()
    # The Cookidoo login flow sets cookies across domains
    _session = ClientSession(cookie_jar=CookieJar(unsafe=True))
    api = Cookidoo(
        _session,
        CookidooConfig(email=email, password=password, localization=options[0]),
    )
    try:
        await api.login()
    except CookidooException as e:
        raise ToolError(f"Cookidoo login failed: {e}") from e
    _api = api
    return api


async def _call(operation: Callable[[Cookidoo], Awaitable[Any]]) -> Any:
    """Run a Cookidoo call, signing in first and once more if the session expired."""
    api = _api or await _login()
    try:
        try:
            return await operation(api)
        except CookidooAuthException:
            return await operation(await _login())
    except CookidooException as e:
        raise ToolError(f"Cookidoo request failed: {e}") from e


@mcp.tool()
async def connect_to_cookidoo() -> dict:
    """Sign in to Cookidoo.

    Optional: the other tools sign in on their own. Use it to check that the
    credentials work.
    """
    api = await _login()
    return {"connected": True, "language": api.localization.language}


@mcp.tool()
async def get_planned_recipes_this_week(week_offset: int = 0) -> dict:
    """Get the recipes planned in the Cookidoo calendar for one week.

    Args:
        week_offset: 0 for the current week (default), 1 for next week, -1 for last week.

    Returns the days that have recipes, each with the recipe IDs and names.
    Pass the IDs to get_recipe_details to get the ingredients.
    """
    monday = week_start(date.today(), week_offset)
    days = await _call(lambda api: api.get_recipes_in_calendar_week(monday))
    return week_to_dict(days, monday)


@mcp.tool()
async def get_recipe_details(recipe_id: str) -> dict:
    """Get a recipe with its ingredients.

    Args:
        recipe_id: ID from the calendar or from the recipe URL, e.g. "r59322".

    Each ingredient has a `name` and a `quantity` such as "200 g". Recipes the
    user created themselves have free-text ingredients: the whole line is in
    `name` and `quantity` is empty. `servings` is the number of portions the
    quantities are for.
    """
    if _CATALOGUE_RECIPE_ID.fullmatch(recipe_id):
        recipe = await _call(lambda api: api.get_recipe_details(recipe_id))
        return recipe_to_dict(recipe)
    recipe = await _call(lambda api: api.get_custom_recipe(recipe_id))
    return custom_recipe_to_dict(recipe)


if __name__ == "__main__":
    mcp.run()
