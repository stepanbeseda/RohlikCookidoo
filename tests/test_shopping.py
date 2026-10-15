"""Tests for building the shopping list."""

from rohlik_cookidoo.shopping import build_shopping_list

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


def test_shopping_list_groups_by_pantry(household):
    household.update_pantry(always_at_home=["sůl", "máslo", "olej"])
    result = build_shopping_list(RECIPES, household)

    assert [(i["name"], i["quantity"], i["unit"]) for i in result["to_buy"]] == [
        ("cibule", 300, "g")
    ]
    assert result["to_buy"][0]["sources"] == ["Zelný hrnec (200 g)", "Polévka (0.1 kg)"]
    assert [
        (i["name"], i["pantry_item"], i["check_reason"]) for i in result["check_at_home"]
    ] == [("sezamového oleje", "olej", "similar_item")]
    assert {i["name"]: i["pantry_item"] for i in result["at_home"]} == {
        "másla": "máslo", "soli": "sůl",
    }


def test_shopping_list_without_pantry_buys_everything(household):
    result = build_shopping_list(RECIPES, household)
    assert len(result["to_buy"]) == 4
    assert result["check_at_home"] == result["at_home"] == []


def test_target_servings_scales_amounts(household):
    recipe = {**RECIPES[0], "target_servings": 3}
    result = build_shopping_list([recipe], household)
    assert result["to_buy"][0]["quantity"] == 100
    assert result["to_buy"][0]["display"] == "100 g"


def test_ask_first_items_go_to_check_with_a_reason(household):
    household.update_pantry(always_at_home=["sůl"], ask_first=["máslo"])
    result = build_shopping_list(RECIPES, household)
    asked = [i for i in result["check_at_home"] if i["check_reason"] == "ask_user"]
    assert [(i["name"], i["quantity"], i["pantry_item"]) for i in asked] == [
        ("másla", 50, "máslo")
    ]
    assert "másla" not in [i["name"] for i in result["to_buy"] + result["at_home"]]


def test_usual_product_is_attached_in_any_case_form(household):
    household.remember_products([
        {"ingredient": "cibule", "product_id": 1298821, "product_name": "Cibule žlutá, síť",
         "package_amount": "1 kg"},
        {"ingredient": "máslo", "product_id": 1462148, "product_name": "Miil Máslo 82%",
         "package_amount": "250 g"},
    ])
    household.update_pantry(always_at_home=["máslo"])
    result = build_shopping_list(RECIPES, household)

    onion = result["to_buy"][0]
    assert (onion["name"], onion["usual_product"]["product_id"]) == ("cibule", 1298821)
    # nothing is attached to what is at home, and nothing is invented
    assert all("usual_product" not in i for i in result["at_home"])
    assert all("usual_product" not in i for i in result["to_buy"][1:])
