"""Tests for the kitchen MCP server logic (no MCP transport involved)."""

from rohlik_cookidoo.kitchen_server import build_shopping_list, plan_package_counts

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


def test_shopping_list_groups_by_pantry():
    result = build_shopping_list(RECIPES, ["sůl", "máslo", "olej"])

    assert [(i["name"], i["quantity"], i["unit"]) for i in result["to_buy"]] == [
        ("cibule", 300, "g")
    ]
    assert result["to_buy"][0]["sources"] == ["Zelný hrnec (200 g)", "Polévka (0.1 kg)"]
    assert [(i["name"], i["pantry_item"]) for i in result["check_at_home"]] == [
        ("sezamového oleje", "olej")
    ]
    assert {i["name"]: i["pantry_item"] for i in result["at_home"]} == {
        "másla": "máslo", "soli": "sůl",
    }


def test_shopping_list_without_pantry_buys_everything():
    result = build_shopping_list(RECIPES, [])
    assert len(result["to_buy"]) == 4
    assert result["check_at_home"] == result["at_home"] == []


def test_target_servings_scales_amounts():
    recipe = {**RECIPES[0], "target_servings": 3}
    result = build_shopping_list([recipe], [])
    assert result["to_buy"][0]["quantity"] == 100
    assert result["to_buy"][0]["display"] == "100 g"


def test_plan_package_counts():
    result = plan_package_counts([
        {"name": "cibule", "quantity": 300, "unit": "g", "package_amount": "1 kg"},
        {"name": "mléko", "quantity": 1500, "unit": "g", "package_amount": "1 l"},
        {"name": "sůl", "package_amount": "1 kg"},
    ])
    assert [(r["name"], r["packages"], r["exact"]) for r in result] == [
        ("cibule", 1, True), ("mléko", 2, False), ("sůl", 1, False),
    ]
