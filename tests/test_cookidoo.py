"""Tests for the Cookidoo client: its pure helpers and its error handling (no network)."""

import asyncio
from datetime import date
from types import SimpleNamespace

import aiohttp
import pytest
from cookidoo_api.exceptions import CookidooRequestException

from rohlik_cookidoo import cookidoo as cookidoo_module
from rohlik_cookidoo.cookidoo import (
    CookidooClient,
    CookidooError,
    custom_recipe_to_dict,
    recipe_to_dict,
    week_start,
    week_to_dict,
)


def _day(day_id, title, recipes, custom_ids=()):
    return SimpleNamespace(
        id=day_id,
        title=title,
        recipes=[SimpleNamespace(id=i, name=n) for i, n in recipes],
        customer_recipe_ids=list(custom_ids),
    )


class TestWeekStart:
    def test_monday_stays(self):
        assert week_start(date(2026, 10, 12)) == date(2026, 10, 12)

    def test_sunday_goes_back_to_monday(self):
        assert week_start(date(2026, 10, 18)) == date(2026, 10, 12)

    def test_next_week(self):
        assert week_start(date(2026, 10, 14), 1) == date(2026, 10, 19)

    def test_previous_week_across_year(self):
        assert week_start(date(2027, 1, 1), -1) == date(2026, 12, 21)


class TestWeekToDict:
    def test_skips_days_without_recipes(self):
        days = [
            _day("2026-10-12", "Pondělí", [("r1", "Svíčková")]),
            _day("2026-10-13", "Úterý", []),
        ]
        result = week_to_dict(days, date(2026, 10, 12))
        assert result["week_start"] == "2026-10-12"
        assert result["recipe_count"] == 1
        assert [d["title"] for d in result["days"]] == ["Pondělí"]

    def test_marks_custom_recipes(self):
        days = [_day("2026-10-12", "Pondělí", [("r1", "A"), ("01ABC", "B")], ["01ABC"])]
        recipes = week_to_dict(days, date(2026, 10, 12))["days"][0]["recipes"]
        assert recipes == [
            {"id": "r1", "name": "A", "custom": False},
            {"id": "01ABC", "name": "B", "custom": True},
        ]

    def test_empty_week(self):
        result = week_to_dict([], date(2026, 10, 12))
        assert result == {"week_start": "2026-10-12", "recipe_count": 0, "days": []}


class TestRecipeToDict:
    def test_catalogue_recipe(self):
        recipe = SimpleNamespace(
            id="r1",
            name="Palačinky",
            serving_size=4,
            url="https://cookidoo.cz/recipes/recipe/cs/r1",
            ingredients=[
                SimpleNamespace(name="hladká mouka", description="200 g"),
                SimpleNamespace(name="sůl", description=""),
            ],
        )
        result = recipe_to_dict(recipe)
        assert result["servings"] == 4
        assert result["ingredients"] == [
            {"name": "hladká mouka", "quantity": "200 g"},
            {"name": "sůl", "quantity": ""},
        ]

    def test_custom_recipe_keeps_free_text(self):
        recipe = SimpleNamespace(
            id="01ABC", name="Moje", serving_size=2, url="u", ingredients=["200 g mouky"]
        )
        assert custom_recipe_to_dict(recipe)["ingredients"] == [
            {"name": "200 g mouky", "quantity": ""}
        ]


class TestSignIn:
    """Sign-in must happen once even when several calls arrive together."""

    def _client(self, monkeypatch, expire_first=0):
        import asyncio

        from cookidoo_api.exceptions import CookidooAuthException

        from rohlik_cookidoo.cookidoo import CookidooClient

        client = CookidooClient()
        logins = []
        expired = {"left": expire_first}

        async def fake_login():
            await asyncio.sleep(0.01)  # give other callers time to pile up
            client._api = SimpleNamespace(number=len(logins) + 1)
            logins.append(client._api)
            return client._api

        async def operation(api):
            await asyncio.sleep(0)
            if api.number == 1 and expired["left"] > 0:
                expired["left"] -= 1
                raise CookidooAuthException("expired")
            return api.number

        monkeypatch.setattr(client, "_login", fake_login)
        return client, logins, operation

    def test_concurrent_first_calls_sign_in_once(self, monkeypatch):
        import asyncio

        client, logins, operation = self._client(monkeypatch)

        async def run():
            return await asyncio.gather(*(client._call(operation) for _ in range(5)))

        assert asyncio.run(run()) == [1, 1, 1, 1, 1]
        assert len(logins) == 1

    def test_expired_session_is_renewed_once_for_all_callers(self, monkeypatch):
        import asyncio

        client, logins, operation = self._client(monkeypatch, expire_first=3)

        async def run():
            return await asyncio.gather(*(client._call(operation) for _ in range(3)))

        assert asyncio.run(run()) == [2, 2, 2]
        assert len(logins) == 2


class TestErrors:
    """Every way a request or a login can fail ends as a CookidooError."""

    @staticmethod
    def _client(monkeypatch, api):
        client = CookidooClient()

        async def fake_login():
            client._api = api
            return api

        monkeypatch.setattr(client, "_login", fake_login)
        return client

    @pytest.mark.parametrize(
        ("error", "message"),
        [
            (
                aiohttp.ClientConnectionError("connection reset"),
                "Cookidoo request failed: connection reset",
            ),
            (TimeoutError(), "Cookidoo request failed: TimeoutError"),
            (
                CookidooRequestException("Loading recipe details failed due to connection timeout."),
                "Cookidoo request failed: Loading recipe details failed due to connection timeout.",
            ),
        ],
    )
    def test_a_request_that_fails_becomes_a_cookidoo_error(self, monkeypatch, error, message):
        async def get_recipe_details(recipe_id):
            raise error

        client = self._client(monkeypatch, SimpleNamespace(get_recipe_details=get_recipe_details))
        with pytest.raises(CookidooError) as raised:
            asyncio.run(client.recipe("r1"))
        assert str(raised.value) == message

    def test_a_week_that_fails_becomes_a_cookidoo_error(self, monkeypatch):
        async def get_recipes_in_calendar_week(monday):
            raise aiohttp.ClientConnectionError("x")

        api = SimpleNamespace(get_recipes_in_calendar_week=get_recipes_in_calendar_week)
        client = self._client(monkeypatch, api)
        with pytest.raises(CookidooError) as raised:
            asyncio.run(client.week(0))
        assert str(raised.value) == "Cookidoo request failed: x"

    def test_a_login_that_cannot_reach_cookidoo_closes_its_session(self, monkeypatch):
        monkeypatch.setenv("COOKIDOO_EMAIL", "a@example.invalid")
        monkeypatch.setenv("COOKIDOO_PASSWORD", "x")
        monkeypatch.delenv("COOKIDOO_COUNTRY", raising=False)
        monkeypatch.delenv("COOKIDOO_LANGUAGE", raising=False)
        sessions = []

        class FakeCookidoo:
            def __init__(self, session, config):
                sessions.append(session)

            async def login(self):
                raise aiohttp.ClientConnectionError("no route")

        monkeypatch.setattr(cookidoo_module, "Cookidoo", FakeCookidoo)
        with pytest.raises(CookidooError) as raised:
            asyncio.run(CookidooClient().recipe("r1"))
        assert str(raised.value) == "Cookidoo login failed: no route"
        assert [session.closed for session in sessions] == [True]
