"""Tests for the shopping list module, through its entry point `prepare`."""

import asyncio
from types import SimpleNamespace

import aiohttp
import pytest

from rohlik_cookidoo.cookidoo import CookidooClient, CookidooError
from rohlik_cookidoo.shopping import ShoppingError, prepare

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
COOKIDOO = {
    "r1": {"id": "r1", "name": "Zelný hrnec", "servings": 6, "url": "u1", "ingredients": [
        {"name": "cibule", "quantity": "200 gramů"},
        {"name": "másla", "quantity": "50 gramů"},
    ]},
    "r2": {"id": "r2", "name": "Polévka", "servings": 4, "url": "u2", "ingredients": [
        {"name": "cibule, nakrájená", "quantity": "0.1 kg"},
        {"name": "soli", "quantity": ""},
    ]},
    # Cookidoo reports an unknown number of servings as 0; this one is not in WEEK
    "r0": {"id": "r0", "name": "Bez porcí", "servings": 0, "url": "u0", "ingredients": [
        {"name": "cibule", "quantity": "100 g"},
    ]},
}
RECIPES = [
    {
        "name": "Zelný hrnec",
        "servings": 6,
        "ingredients": [
            {"name": "cibule", "quantity": "200 gramů"},
            {"name": "másla", "quantity": "50 gramů"},
            {"name": "soli", "quantity": "1 čajová lžička"},
            {"name": "sezamového oleje", "quantity": "1 polévková lžíce"},
        ],
    },
    {
        "name": "Polévka",
        "servings": 4,
        "ingredients": [
            {"name": "cibule, nakrájená", "quantity": "0.1 kg"},
            {"name": "sůl", "quantity": ""},
        ],
    },
]
WEB = {"name": "Palačinky", "ingredients": [{"name": "hladká mouka", "quantity": "200 g"}]}
FIELDS_WEEK = [
    "source", "week_start", "failed", "recipes", "to_buy", "check_at_home", "at_home",
    "preferences", "pantry_setup_needed",
]
FIELDS_RECIPES = [field for field in FIELDS_WEEK if field != "week_start"]
NOTE = (
    "the recipe does not say how many servings it makes, so its amounts are not scaled to 8"
)


class FakeSource:
    def __init__(self, errors=None, week_error=None):
        self.errors = errors or {}
        self.week_error = week_error
        self.calls = []

    async def week(self, week_offset=0):
        self.calls.append(("week", week_offset))
        if self.week_error:
            raise self.week_error
        return WEEK

    async def recipe(self, recipe_id):
        self.calls.append(("recipe", recipe_id))
        if recipe_id in self.errors:
            raise self.errors[recipe_id]
        if recipe_id not in COOKIDOO:
            raise CookidooError(f"Recipe {recipe_id} not found")
        return COOKIDOO[recipe_id]


def shop(household, source=None, **request):
    return asyncio.run(prepare(source or FakeSource(), household, **request))


def names(items):
    return [item["name"] for item in items]


def ingredients(items):
    return [item["ingredient"] for item in items]


def amounts(items):
    return [(item["ingredient"], item["quantity"]) for item in items]


def test_the_week_plan_is_the_default_source(household):
    household.update_pantry(always_at_home=["sůl"])
    source = FakeSource()
    result = shop(household, source)

    assert list(result) == FIELDS_WEEK
    assert (result["source"], result["week_start"]) == ("week", "2026-10-12")
    assert names(result["recipes"]) == ["Zelný hrnec", "Polévka"]
    assert [(i["ingredient"], i["quantity"], i["unit"]) for i in result["to_buy"]] == [
        ("cibule", 300, "g"), ("másla", 50, "g"),
    ]
    assert ingredients(result["at_home"]) == ["soli"]
    assert result["pantry_setup_needed"] is False
    assert result["failed"] == []
    assert source.calls[0] == ("week", 0)


def test_next_week_and_an_empty_pantry(household):
    source = FakeSource()
    result = shop(household, source, week_offset=1)
    assert source.calls[0] == ("week", 1)
    assert result["pantry_setup_needed"] is True
    assert len(result["to_buy"]) == 3


def test_a_pantry_of_only_ask_first_items_needs_no_setup(household):
    household.update_pantry(ask_first=["máslo"])
    assert shop(household)["pantry_setup_needed"] is False


def test_given_recipe_ids_skip_the_calendar(household):
    source = FakeSource()
    result = shop(household, source, recipe_ids=["r1"], target_servings=3)
    assert not [call for call in source.calls if call[0] == "week"]
    assert list(result) == FIELDS_RECIPES
    assert result["source"] == "recipes"
    assert result["recipes"] == [{"id": "r1", "name": "Zelný hrnec", "servings": 3, "url": "u1"}]
    assert amounts(result["to_buy"]) == [("cibule", 100), ("másla", 25)]


def test_a_recipe_from_the_web_needs_no_recipe_source(household):
    source = FakeSource()
    recipe = {"name": "Palačinky", "servings": 4, "ingredients": [
        {"name": "hladká mouka", "quantity": "200 g"}, {"name": "vejce", "quantity": "2"},
    ]}
    result = shop(household, source, recipes=[recipe])
    assert source.calls == []
    assert [(i["ingredient"], i["display"]) for i in result["to_buy"]] == [
        ("hladká mouka", "200 g"), ("vejce", "2 ks"),
    ]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (CookidooError("Recipe r404 not found"), "Recipe r404 not found"),
        (
            aiohttp.ClientConnectionError("connection reset"),
            "Loading the recipe failed: ClientConnectionError: connection reset",
        ),
        (TimeoutError(), "Loading the recipe failed: TimeoutError"),
        (KeyError("servingSize"), "Loading the recipe failed: KeyError: 'servingSize'"),
    ],
)
def test_a_recipe_that_cannot_be_loaded_is_reported_as_failed(household, error, expected):
    source = FakeSource(errors={"r404": error})
    result = shop(household, source, recipe_ids=["r1", "r404"])
    assert names(result["recipes"]) == ["Zelný hrnec"]
    assert ingredients(result["to_buy"]) == ["cibule", "másla"]
    assert result["failed"] == [{"id": "r404", "error": expected}]


def test_a_timeout_through_the_cookidoo_client_ends_in_failed(household, monkeypatch):
    class FakeApi:
        async def get_recipe_details(self, recipe_id):
            if recipe_id == "r2":
                raise TimeoutError()
            return SimpleNamespace(
                id=recipe_id, name="A", serving_size=4, url="u",
                ingredients=[SimpleNamespace(name="sůl", description="")],
            )

    client = CookidooClient()

    async def fake_login():
        client._api = FakeApi()
        return client._api

    monkeypatch.setattr(client, "_login", fake_login)
    result = shop(household, client, recipe_ids=["r1", "r2"])
    assert names(result["recipes"]) == ["A"]
    assert result["failed"] == [{"id": "r2", "error": "Cookidoo request failed: TimeoutError"}]


def test_preferences_and_usual_products_come_along(household):
    household.set_preference("quality", "bio")
    household.remember_products([{"ingredient": "cibule", "product_id": 1298821,
                                  "product_name": "Cibule žlutá, síť", "package_amount": "1 kg"}])
    result = shop(household)
    assert result["preferences"] == {"quality": "bio"}
    assert result["to_buy"][0]["usual_product"]["product_id"] == 1298821


def test_shopping_list_groups_by_pantry(household):
    household.update_pantry(always_at_home=["sůl", "máslo", "olej"])
    result = shop(household, recipes=RECIPES)

    assert [(i["ingredient"], i["quantity"], i["unit"]) for i in result["to_buy"]] == [
        ("cibule", 300, "g")
    ]
    assert result["to_buy"][0]["sources"] == ["Zelný hrnec (200 g)", "Polévka (0.1 kg)"]
    assert [
        (i["ingredient"], i["pantry_item"], i["check_reason"]) for i in result["check_at_home"]
    ] == [("sezamového oleje", "olej", "similar_item")]
    assert {i["ingredient"]: i["pantry_item"] for i in result["at_home"]} == {
        "másla": "máslo", "soli": "sůl",
    }


def test_shopping_list_without_pantry_buys_everything(household):
    result = shop(household, recipes=RECIPES)
    assert len(result["to_buy"]) == 4
    assert result["check_at_home"] == result["at_home"] == []


def test_a_recipes_own_target_servings_scales_it(household):
    recipe = {**RECIPES[0], "target_servings": 3}
    result = shop(household, recipes=[recipe])
    assert result["to_buy"][0]["quantity"] == 100
    assert result["to_buy"][0]["display"] == "100 g"
    assert result["recipes"][0]["servings"] == 3


def test_the_requests_target_servings_wins_over_a_recipes_own(household):
    recipe = {**RECIPES[0], "target_servings": 3}
    result = shop(household, recipes=[recipe], target_servings=12)
    assert result["to_buy"][0]["quantity"] == 400
    assert result["recipes"][0]["servings"] == 12


def test_ask_first_items_go_to_check_with_a_reason(household):
    household.update_pantry(always_at_home=["sůl"], ask_first=["máslo"])
    result = shop(household, recipes=RECIPES)
    asked = [i for i in result["check_at_home"] if i["check_reason"] == "ask_user"]
    assert [(i["ingredient"], i["quantity"], i["pantry_item"]) for i in asked] == [
        ("másla", 50, "máslo")
    ]
    assert "másla" not in ingredients(result["to_buy"] + result["at_home"])


def test_usual_product_is_attached_in_any_case_form(household):
    household.remember_products([
        {"ingredient": "cibule", "product_id": 1298821, "product_name": "Cibule žlutá, síť",
         "package_amount": "1 kg"},
        {"ingredient": "máslo", "product_id": 1462148, "product_name": "Miil Máslo 82%",
         "package_amount": "250 g"},
    ])
    household.update_pantry(always_at_home=["máslo"])
    result = shop(household, recipes=RECIPES)

    onion = result["to_buy"][0]
    assert (onion["ingredient"], onion["usual_product"]["product_id"]) == ("cibule", 1298821)
    # nothing is attached to what is at home, and nothing is invented
    assert all("usual_product" not in i for i in result["at_home"])
    assert all("usual_product" not in i for i in result["to_buy"][1:])


@pytest.mark.parametrize(
    ("request_", "own_servings", "expected_amounts"),
    [
        ({"recipes": [WEB]}, None, [("hladká mouka", 200)]),
        ({"recipe_ids": ["r0"]}, 0, [("cibule", 100)]),
    ],
)
def test_a_recipe_without_servings_is_not_scaled_and_says_so(
    household, request_, own_servings, expected_amounts
):
    result = shop(household, target_servings=8, **request_)
    recipe = result["recipes"][0]
    assert recipe["servings"] == own_servings
    assert recipe["note"] == NOTE
    assert amounts(result["to_buy"]) == expected_amounts


def test_a_web_recipe_without_servings_keeps_its_exact_summary(household):
    result = shop(household, recipes=[WEB], target_servings=8)
    assert result["recipes"] == [
        {"id": None, "name": "Palačinky", "servings": None, "url": None, "note": NOTE}
    ]


def test_only_the_recipe_that_cannot_be_scaled_carries_a_note(household):
    result = shop(household, recipes=[WEB, RECIPES[0]], target_servings=3)
    assert "note" in result["recipes"][0]
    assert result["recipes"][0]["servings"] is None
    assert result["recipes"][1] == {"id": None, "name": "Zelný hrnec", "servings": 3, "url": None}
    amounts_ = dict(amounts(result["to_buy"]))
    assert amounts_["hladká mouka"] == 200
    assert amounts_["cibule"] == 100


@pytest.mark.parametrize("target", [0, -2])
def test_target_servings_below_one_is_refused_before_loading(household, target):
    source = FakeSource()
    with pytest.raises(ShoppingError) as error:
        shop(household, source, recipe_ids=["r1"], target_servings=target)
    assert str(error.value) == f"target_servings must be 1 or more, not {target}"
    assert source.calls == []


def test_a_recipes_own_target_servings_below_one_is_refused(household):
    recipe = {**RECIPES[0], "target_servings": 0}
    with pytest.raises(ShoppingError) as error:
        shop(household, recipes=[recipe])
    assert str(error.value) == 'recipe "Zelný hrnec": target_servings must be 1 or more, not 0'


def test_a_week_that_cannot_be_loaded_is_an_error(household):
    source = FakeSource(week_error=CookidooError("Cookidoo request failed: x"))
    with pytest.raises(CookidooError):
        shop(household, source)


def test_preparation_only_name_is_one_ingredient(household):
    household.remember_products([{"ingredient": "čerstvá", "product_id": 7, "product_name": "X"}])
    recipes = [
        {"name": "A", "ingredients": [{"name": "čerstvý", "quantity": "1"}]},
        {"name": "B", "ingredients": [{"name": "čerstvé", "quantity": "2"}]},
    ]
    [line] = shop(household, recipes=recipes)["to_buy"]
    assert (line["ingredient"], line["quantity"], line["usual_product"]["product_id"]) == (
        "čerstvý", 3, 7)
    household.update_pantry(always_at_home=["čerstvé"])
    result = shop(household, recipes=recipes)
    assert [(i["ingredient"], i["pantry_item"]) for i in result["at_home"]] == [
        ("čerstvý", "čerstvé")
    ]
    assert result["to_buy"] == result["check_at_home"] == []
