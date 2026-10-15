"""Tests for the MCP server, called in-process through the MCP protocol."""

import asyncio
import os
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from rohlik_cookidoo import server
from rohlik_cookidoo.cookidoo import CookidooError

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
        self.recipe_ids = []
        self.error = None

    async def week(self, week_offset=0):
        if self.error:
            raise self.error
        self.week_offsets.append(week_offset)
        return WEEK

    async def recipe(self, recipe_id):
        if self.error:
            raise self.error
        self.recipe_ids.append(recipe_id)
        if recipe_id not in RECIPES:
            raise CookidooError(f"Recipe {recipe_id} not found")
        return RECIPES[recipe_id]


@pytest.fixture(autouse=True)
def home(household, monkeypatch):
    """Point the server at the temporary household instead of the environment's."""
    monkeypatch.setattr(server, "household", household)
    return household


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


def test_server_ships_its_instructions():
    async def run():
        async with Client(server.mcp) as client:
            return client.initialize_result.instructions
    assert "prepare_shopping" in asyncio.run(run())
    assert "prepare_shopping" in call("get_shopping_guide")


def test_prepare_shopping_passes_every_argument(fake, home):
    home.update_pantry(always_at_home=["sůl"])
    result = call("prepare_shopping", {
        "recipe_ids": ["r1"],
        "recipes": [{"name": "Palačinky", "servings": 4, "ingredients": [
            {"name": "hladká mouka", "quantity": "200 g"},
        ]}],
        "target_servings": 3,
    })
    assert [(r["name"], r["servings"]) for r in result["recipes"]] == [
        ("Zelný hrnec", 3), ("Palačinky", 3),
    ]
    assert ("hladká mouka", 150) in [(i["ingredient"], i["quantity"]) for i in result["to_buy"]]
    assert result["pantry_setup_needed"] is False
    assert fake.week_offsets == []

    result = call("prepare_shopping", {"week_offset": 1})
    assert fake.week_offsets == [1]
    assert result["source"] == "week"


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("prepare_shopping", {}),
        ("get_planned_recipes", {"week_offset": 1}),
        ("get_recipe_details", {"recipe_id": "r1"}),
    ],
)
def test_cookidoo_errors_reach_the_model_as_tool_errors(fake, tool, arguments):
    fake.error = CookidooError("Cookidoo request failed: boom")
    with pytest.raises(ToolError) as error:
        call(tool, arguments)
    # The whole text: an unmapped error would arrive with an "Error calling tool" prefix.
    assert str(error.value) == "Cookidoo request failed: boom"


def test_prepare_shopping_refuses_target_servings_below_one(fake):
    with pytest.raises(ToolError) as error:
        call("prepare_shopping", {"recipe_ids": ["r1"], "target_servings": 0})
    assert str(error.value) == "target_servings must be 1 or more, not 0"
    assert fake.recipe_ids == []


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
        {"ingredients": ["cibule"], "product_id": 1298821, "product_name": "Cibule žlutá, síť",
         "package_amount": "1 kg"},
        {"ingredients": ["másla"], "product_id": 1462148, "product_name": "Miil Máslo 82%"},
    ]})
    assert len(result["remembered"]) == 2
    usual = call("get_shopping_preferences")["usual_products"]
    assert [p["ingredient"] for p in usual] == ["cibule", "másla"]
    assert call("forget_product", {"ingredient": "máslo"}) == {"forgotten": True}
    assert len(call("get_shopping_preferences")["usual_products"]) == 1


def test_plan_purchase_tool():
    plan = call("plan_purchase", {
        "items": [{"ingredient": "cibule", "productId": 1349783, "price": 2.53,
                   "package_amount": "cca 120 g", "quantity": 200, "unit": "g"}],
        "cart": [], "cart_total": 0, "minimum_order": 749,
    })
    assert plan["to_add"] == [{"productId": 1349783, "quantity": 2}]
    assert plan["missing_to_minimum"] == 743.94


def test_plan_purchase_tool_names_an_item_without_product_id():
    with pytest.raises(ToolError) as error:
        call("plan_purchase", {"items": [
            {"ingredient": "máslo", "product_id": 2, "package_amount": "250 g"},
            {"ingredient": "cibule", "package_amount": "1 kg", "quantity": 1, "unit": "kg"},
        ]})
    # The whole text: an unmapped ValueError would arrive with a "Error calling tool" prefix.
    assert str(error.value) == 'item 2 ("cibule") has no product_id or productId'


def test_plan_purchase_tool_zero_packages():
    plan = call("plan_purchase", {
        "items": [{"ingredient": "cibule", "productId": 1349783, "price": 2.53,
                   "package_amount": "cca 120 g", "quantity": 200, "unit": "g",
                   "packages": 0}],
        "minimum_order": 0,
    })
    assert plan["lines"][0]["packages"] == 0
    assert plan["to_add"] == []


def test_household_is_resolved_once_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "household", None)
    monkeypatch.delenv("PANTRY_PATH", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "first"))
    (tmp_path / "first").mkdir()
    (tmp_path / "first" / "pantry.txt").write_text("sůl\n", encoding="utf-8")
    assert call("get_pantry")["always_at_home"] == ["sůl"]

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "second"))
    call("update_pantry", {"always_at_home": ["rýže"]})
    assert not (tmp_path / "second").exists()
    assert (tmp_path / "first" / "pantry.txt").read_text(encoding="utf-8") == "sůl\nrýže\n"


def test_update_pantry_and_record_purchase_write_each_file_once(home, monkeypatch):
    replaced = []
    real = os.replace

    def spy(source, destination):
        if Path(destination).parent == home.data_dir:
            replaced.append(Path(destination).name)
        real(source, destination)

    monkeypatch.setattr(os, "replace", spy)
    call("update_pantry", {
        "always_at_home": ["sůl", "rýže"], "ask_first": ["máslo", "vejce"], "remove": ["pepř"],
    })
    assert replaced == ["pantry.txt"]

    replaced.clear()
    call("record_purchase", {"products": [
        {"ingredients": ["cibule", "žluté cibule"], "product_id": 1, "product_name": "Cibule"},
        {"ingredients": ["másla"], "product_id": 2, "product_name": "Máslo"},
        {"ingredients": ["mléka"], "product_id": 3, "product_name": "Mléko"},
    ]})
    assert replaced == ["products.json"]


# Product data as the model takes it from the Rohlik connector
ROHLIK = {
    "cibule": {"productId": 1298821, "product_name": "Cibule žlutá, síť", "price": 29.9,
               "package_amount": "1 kg"},
    "žlutá cibule": {"productId": 1298821, "product_name": "Cibule žlutá, síť", "price": 29.9,
                     "package_amount": "1 kg"},
    "másla": {"productId": 1462148, "product_name": "Miil Máslo 82%", "price": 54.9,
              "package_amount": "250 g"},
}
SALAD = {"name": "Salát", "ingredients": [{"name": "žlutá cibule", "quantity": "100 g"}]}


def test_a_shopping_list_line_goes_through_all_three_tools_unchanged(fake):
    shopping = call("prepare_shopping", {"recipe_ids": ["r1"], "recipes": [SALAD]})
    items = [{**entry, **ROHLIK[entry["ingredient"]]} for entry in shopping["to_buy"]]
    plan = call("plan_purchase", {"items": items, "cart": [], "cart_total": 0})
    assert [line["ingredients"] for line in plan["lines"]] == [
        ["cibule", "žlutá cibule"], ["másla"],
    ]
    assert plan["to_add"] == [
        {"productId": 1298821, "quantity": 1}, {"productId": 1462148, "quantity": 1},
    ]

    call("record_purchase", {"products": plan["lines"]})

    usual = call("get_shopping_preferences")["usual_products"]
    assert [(p["ingredient"], p["product_id"], p["product_name"], p["package_amount"])
            for p in usual] == [
        ("cibule", 1298821, "Cibule žlutá, síť", "1 kg"),
        ("másla", 1462148, "Miil Máslo 82%", "250 g"),
        ("žlutá cibule", 1298821, "Cibule žlutá, síť", "1 kg"),
    ]
    again = call("prepare_shopping", {"recipe_ids": ["r1"], "recipes": [SALAD]})
    assert {e["ingredient"]: e["usual_product"]["product_id"] for e in again["to_buy"]} == {
        "cibule": 1298821, "másla": 1462148, "žlutá cibule": 1298821,
    }


def test_two_ingredients_of_one_product_are_both_remembered():
    plan = call("plan_purchase", {"items": [
        {"ingredient": "cibule", "product_id": 1298821, "product_name": "Cibule žlutá, síť",
         "price": 29.9, "package_amount": "1 kg", "quantity": 200, "unit": "g"},
        {"ingredient": "žlutá cibule", "product_id": 1298821, "product_name": "Cibule žlutá, síť",
         "price": 29.9, "package_amount": "1 kg", "quantity": 100, "unit": "g"},
    ], "minimum_order": 0})
    [line] = plan["lines"]
    remembered = call("record_purchase", {"products": [line]})["remembered"]
    assert [entry["ingredient"] for entry in remembered] == ["cibule", "žlutá cibule"]
    usual = call("get_shopping_preferences")["usual_products"]
    assert [entry["ingredient"] for entry in usual] == ["cibule", "žlutá cibule"]


def test_old_input_field_names_are_still_accepted():
    plan = call("plan_purchase", {"items": [
        {"name": "cibule", "product_id": 1298821, "price": 29.9, "package_amount": "1 kg",
         "quantity": 200, "unit": "g"},
    ], "minimum_order": 0})
    assert plan["lines"][0]["ingredients"] == ["cibule"]

    remembered = call("record_purchase", {"products": [
        {"ingredient": "másla", "productId": 1462148, "product_name": "Miil Máslo 82%",
         "package_amount": "250 g"},
    ]})["remembered"]
    assert [(e["ingredient"], e["product_id"]) for e in remembered] == [("másla", 1462148)]


def test_tool_schemas_show_only_the_new_field_names():
    async def run():
        async with Client(server.mcp) as client:
            return {tool.name: tool.inputSchema for tool in await client.list_tools()}
    schemas = asyncio.run(run())
    item = schemas["plan_purchase"]["properties"]["items"]["items"]
    product = schemas["record_purchase"]["properties"]["products"]["items"]
    assert "ingredient" in item["required"] and "name" not in item["properties"]
    assert "product_name" in item["properties"]
    assert "ingredients" in product["required"] and "ingredient" not in product["properties"]
    assert {"product_id", "productId"} <= set(product["properties"])


@pytest.mark.parametrize(
    ("product", "message"),
    [
        ({"ingredients": ["másla"], "product_name": "Máslo"},
         'product 2 ("Máslo") has no product_id or productId'),
        ({"ingredients": [], "product_id": 2, "product_name": "Máslo"},
         'product 2 ("Máslo") has no ingredients'),
    ],
)
def test_record_purchase_refuses_a_bad_product_and_stores_nothing(home, product, message):
    good = {"ingredients": ["cibule"], "product_id": 1, "product_name": "Cibule"}
    with pytest.raises(ToolError) as error:
        call("record_purchase", {"products": [good, product]})
    assert str(error.value) == message
    assert not home.products_file.exists()
