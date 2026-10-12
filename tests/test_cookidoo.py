"""Tests for the pure helpers of the Cookidoo client (no network)."""

from datetime import date
from types import SimpleNamespace

from rohlik_cookidoo.cookidoo import (
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
