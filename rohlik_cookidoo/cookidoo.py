"""Read-only access to Cookidoo: the weekly meal plan and recipes.

A thin wrapper around the unofficial cookidoo-api library. Configuration comes
from environment variables:

    COOKIDOO_EMAIL, COOKIDOO_PASSWORD   account credentials (required)
    COOKIDOO_COUNTRY                    country code, default "cz"
    COOKIDOO_LANGUAGE                   language code, default "cs"
"""

import os
import re
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

from aiohttp import ClientSession, CookieJar
from cookidoo_api import Cookidoo, CookidooConfig
from cookidoo_api.exceptions import CookidooAuthException, CookidooException
from cookidoo_api.helpers import get_localization_options

# Catalogue recipes have IDs like "r59322"; anything else is a user-created recipe
_CATALOGUE_RECIPE_ID = re.compile(r"r\d+")


class CookidooError(Exception):
    """Cookidoo is not configured or a request to it failed."""


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


class CookidooClient:
    """Signs in on first use and once more when the session expires."""

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._api: Cookidoo | None = None

    async def _login(self) -> Cookidoo:
        email = os.getenv("COOKIDOO_EMAIL")
        password = os.getenv("COOKIDOO_PASSWORD")
        if not email or not password:
            raise CookidooError("Missing COOKIDOO_EMAIL or COOKIDOO_PASSWORD.")

        country = os.getenv("COOKIDOO_COUNTRY", "cz")
        language = os.getenv("COOKIDOO_LANGUAGE", "cs")
        options = await get_localization_options(country=country, language=language)
        if not options:
            raise CookidooError(
                f"Unknown Cookidoo localization: country={country!r}, language={language!r}."
            )

        if self._session is not None:
            await self._session.close()
        # The Cookidoo login flow sets cookies across domains
        self._session = ClientSession(cookie_jar=CookieJar(unsafe=True))
        api = Cookidoo(
            self._session,
            CookidooConfig(email=email, password=password, localization=options[0]),
        )
        try:
            await api.login()
        except CookidooException as e:
            raise CookidooError(f"Cookidoo login failed: {e}") from e
        self._api = api
        return api

    async def _call(self, operation: Callable[[Cookidoo], Awaitable[Any]]) -> Any:
        api = self._api or await self._login()
        try:
            try:
                return await operation(api)
            except CookidooAuthException:
                return await operation(await self._login())
        except CookidooException as e:
            raise CookidooError(f"Cookidoo request failed: {e}") from e

    async def week(self, week_offset: int = 0) -> dict:
        """Return the recipes planned in the calendar for one week."""
        monday = week_start(date.today(), week_offset)
        days = await self._call(lambda api: api.get_recipes_in_calendar_week(monday))
        return week_to_dict(days, monday)

    async def recipe(self, recipe_id: str) -> dict:
        """Return a catalogue or user-created recipe with its ingredients."""
        if _CATALOGUE_RECIPE_ID.fullmatch(recipe_id):
            recipe = await self._call(lambda api: api.get_recipe_details(recipe_id))
            return recipe_to_dict(recipe)
        recipe = await self._call(lambda api: api.get_custom_recipe(recipe_id))
        return custom_recipe_to_dict(recipe)
