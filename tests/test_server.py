"""Tests for the MCP server, called in-process through the MCP protocol."""

import asyncio

import pytest
from fastmcp import Client

from rohlik_cookidoo import memory, server
from rohlik_cookidoo.cookidoo import CookidooError
from rohlik_cookidoo.pantry import add_pantry_item

WEEK = {
    "week_start": "2026-10-12",
    "recipe_count": 2,
    "days": [
        {"date": "2026-10-12", "title": "Pondělí",
         "recipes": [{"id": "r1", "name": "Zelný hrnec", "custom": False}]},
        {"date": "2026-10-14", "title": "Středa",
         "recipes": [{"id": "r2", "name": "Polévka", "custom": False}]},
    ],
}
RECIPES = {
    "r1": {"id": "r1", "name": "Zelný hrnec", "servings": 6, "url": "u1", "ingredients": [
        {"name": "cibule", "quantity": "200 gramů"},
        {"name": "másla", "quantity": "50 gramů"},
    ]},
    "r2": {"id": "r2", "name": "Polévka", "servings": 4, "url": "u2", "ingredients": [
        {"name": "cibule, nakrájená", "quantity": "0.1 kg"},
        {"name": "soli", "quantity": ""},
    ]},
}


class FakeCookidoo:
    def __init__(self):
        self.week_offsets = []

    async def week(self, week_offset=0):
        self.week_offsets.append(week_offset)
        return WEEK

    async def recipe(self, recipe_id):
        if recipe_id not in RECIPES:
            raise CookidooError(f"Recipe {recipe_id} not found")
        return RECIPES[recipe_id]


@pytest.fixture
def fake(monkeypatch):
    client = FakeCookidoo()
    monkeypatch.setattr(server, "cookidoo", client)
    return client


def call(tool, arguments=None):
    async def run():
        async with Client(server.mcp) as client:
            return (await client.call_tool(tool, arguments or {})).data
    return asyncio.run(run())


def names(items):
    return [item["name"] for item in items]


def test_server_ships_its_instructions():
    async def run():
        async with Client(server.mcp) as client:
            return client.initialize_result.instructions
    assert "prepare_shopping" in asyncio.run(run())
    assert "prepare_shopping" in call("get_shopping_guide")


def test_prepare_shopping_for_the_week(fake):
    add_pantry_item("sůl")
    result = call("prepare_shopping")

    assert (result["source"], result["week_start"]) == ("week", "2026-10-12")
    assert names(result["recipes"]) == ["Zelný hrnec", "Polévka"]
    assert [(i["name"], i["quantity"], i["unit"]) for i in result["to_buy"]] == [
        ("cibule", 300, "g"), ("másla", 50, "g"),
    ]
    assert names(result["at_home"]) == ["soli"]
    assert result["pantry_setup_needed"] is False
    assert result["failed"] == []
    assert fake.week_offsets == [0]


def test_prepare_shopping_next_week_and_empty_pantry(fake):
    result = call("prepare_shopping", {"week_offset": 1})
    assert fake.week_offsets == [1]
    assert result["pantry_setup_needed"] is True
    assert len(result["to_buy"]) == 3


def test_prepare_shopping_for_given_recipes_skips_the_calendar(fake):
    result = call("prepare_shopping", {"recipe_ids": ["r1"], "target_servings": 3})
    assert fake.week_offsets == []
    assert result["source"] == "recipes"
    assert result["recipes"] == [{"id": "r1", "name": "Zelný hrnec", "servings": 3, "url": "u1"}]
    assert [(i["name"], i["quantity"]) for i in result["to_buy"]] == [("cibule", 100), ("másla", 25)]


def test_prepare_shopping_with_a_recipe_from_the_web_needs_no_cookidoo(fake):
    recipe = {"name": "Palačinky", "servings": 4, "ingredients": [
        {"name": "hladká mouka", "quantity": "200 g"}, {"name": "vejce", "quantity": "2"},
    ]}
    result = call("prepare_shopping", {"recipes": [recipe]})
    assert fake.week_offsets == []
    assert [(i["name"], i["display"]) for i in result["to_buy"]] == [
        ("hladká mouka", "200 g"), ("vejce", "2 ks"),
    ]


def test_prepare_shopping_reports_a_recipe_that_failed(fake):
    result = call("prepare_shopping", {"recipe_ids": ["r1", "r404"]})
    assert names(result["recipes"]) == ["Zelný hrnec"]
    assert result["failed"] == [{"id": "r404", "error": "Recipe r404 not found"}]


def test_prepare_shopping_returns_preferences_and_usual_products(fake):
    memory.set_preference("quality", "bio")
    memory.remember_product("cibule", 1298821, "Cibule žlutá, síť", "1 kg")
    result = call("prepare_shopping")
    assert result["preferences"] == {"quality": "bio"}
    assert result["to_buy"][0]["usual_product"]["product_id"] == 1298821


def test_update_pantry_adds_switches_and_removes():
    call("update_pantry", {"always_at_home": ["sůl", "rýže", "máslo"]})
    result = call("update_pantry", {"ask_first": ["máslo", "vejce"], "remove": ["rýže"]})
    assert result == {"always_at_home": ["sůl"], "ask_first": ["máslo", "vejce"]}
    assert call("get_pantry") == result


def test_questionnaire_has_steps_categories_and_current_state():
    call("update_pantry", {"always_at_home": ["sůl"]})
    result = call("get_pantry_questionnaire")
    assert len(result["steps"]) >= 4
    modes = {category["suggested_mode"] for category in result["categories"]}
    assert modes == {"always", "ask_first"}
    assert all(category["items"] for category in result["categories"])
    assert result["current_pantry"]["always_at_home"] == ["sůl"]


def test_record_purchase_and_forget_product(fake):
    result = call("record_purchase", {"products": [
        {"ingredient": "cibule", "product_id": 1298821, "product_name": "Cibule žlutá, síť",
         "package_amount": "1 kg"},
        {"ingredient": "másla", "product_id": 1462148, "product_name": "Miil Máslo 82%"},
    ]})
    assert len(result["remembered"]) == 2
    usual = call("get_shopping_preferences")["usual_products"]
    assert [p["ingredient"] for p in usual] == ["cibule", "másla"]
    assert call("forget_product", {"ingredient": "máslo"}) == {"forgotten": True}
    assert len(call("get_shopping_preferences")["usual_products"]) == 1


def test_plan_purchase_tool():
    plan = call("plan_purchase", {
        "items": [{"name": "cibule", "productId": 1349783, "price": 2.53,
                   "package_amount": "cca 120 g", "quantity": 200, "unit": "g"}],
        "cart": [], "cart_total": 0, "minimum_order": 749,
    })
    assert plan["to_add"] == [{"product_id": 1349783, "quantity": 2}]
    assert plan["missing_to_minimum"] == 743.94
