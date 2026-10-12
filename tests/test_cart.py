"""Tests for working out cart additions."""

from rohlik_cookidoo.cart import plan_cart_additions

ITEMS = [
    {"name": "vepřová plec", "product_id": 1408929, "packages": 1, "price": 211.29},
    {"name": "cibule", "product_id": 1349783, "packages": 3, "price": 2.3},
]


def test_empty_cart_adds_everything():
    plan = plan_cart_additions(ITEMS)
    assert plan["to_add"] == [
        {"product_id": 1408929, "quantity": 1},
        {"product_id": 1349783, "quantity": 3},
    ]
    assert plan["added_total"] == 218.19
    assert plan["cart_total_after"] == 218.19
    assert plan["missing_to_minimum"] == 530.81


def test_products_in_the_cart_are_not_added_twice():
    cart = [{"product_id": 1408929, "quantity": 1}, {"product_id": 1349783, "quantity": 1}]
    plan = plan_cart_additions(ITEMS, cart, cart_total=213.59)
    assert plan["to_add"] == [{"product_id": 1349783, "quantity": 2}]
    assert [(line["already_in_cart"], line["add"]) for line in plan["lines"]] == [(1, 0), (1, 2)]
    assert plan["added_total"] == 4.6
    assert plan["cart_total_after"] == 218.19


def test_running_twice_adds_nothing():
    cart = [{"product_id": "1408929", "quantity": 2}, {"product_id": 1349783, "quantity": 3}]
    plan = plan_cart_additions(ITEMS, cart, cart_total=800)
    assert plan["to_add"] == []
    assert plan["added_total"] == 0
    assert plan["missing_to_minimum"] == 0


def test_same_product_for_two_ingredients_is_merged():
    items = [
        {"name": "cibule", "product_id": 1, "packages": 2, "price": 10},
        {"name": "žlutá cibule", "product_id": 1, "packages": 1, "price": 10},
    ]
    plan = plan_cart_additions(items, minimum_order=0)
    assert plan["to_add"] == [{"product_id": 1, "quantity": 3}]
    assert plan["lines"][0]["name"] == "cibule, žlutá cibule"
    assert plan["added_total"] == 30


def test_missing_price_counts_as_zero():
    plan = plan_cart_additions([{"name": "x", "product_id": 1, "packages": 2}])
    assert plan["to_add"] == [{"product_id": 1, "quantity": 2}]
    assert plan["added_total"] == 0
