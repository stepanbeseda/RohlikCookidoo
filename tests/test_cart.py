"""Tests for working out cart additions."""

from rohlik_cookidoo.cart import plan_cart_additions, plan_purchase

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


def test_product_id_spelling_of_the_official_server_is_accepted():
    items = [{"name": "cibule", "productId": 1349783, "packages": 3, "price": 2.53}]
    plan = plan_cart_additions(items, [{"productId": 1349783, "quantity": 1}], minimum_order=749)
    assert plan["to_add"] == [{"product_id": 1349783, "quantity": 2}]


def test_missing_price_counts_as_zero():
    plan = plan_cart_additions([{"name": "x", "product_id": 1, "packages": 2}])
    assert plan["to_add"] == [{"product_id": 1, "quantity": 2}]
    assert plan["added_total"] == 0


class TestPlanPurchase:
    def test_packages_leftovers_and_cart_in_one_step(self):
        plan = plan_purchase(
            [
                {"name": "vepřová plec", "productId": 1408929, "price": 222.49,
                 "package_amount": "cca 0,89 kg", "quantity": 700, "unit": "g"},
                {"name": "cibule", "productId": 1349783, "price": 2.53,
                 "package_amount": "cca 120 g", "quantity": 200, "unit": "g"},
            ],
            cart=[{"productId": 1408929, "quantity": 1}],
            cart_total=222.49,
        )
        meat, onion = plan["lines"]
        assert (meat["packages"], meat["add"], meat["leftover"]) == (1, 0, "190 g")
        assert (onion["packages"], onion["add"], onion["leftover"]) == (2, 2, "40 g")
        assert plan["to_add"] == [{"product_id": 1349783, "quantity": 2}]
        assert plan["cart_total_after"] == 227.55

    def test_ingredients_sharing_a_product_are_summed_before_rounding(self):
        items = [
            {"name": "cibule", "product_id": 1, "price": 10, "package_amount": "500 g",
             "quantity": 200, "unit": "g"},
            {"name": "žlutá cibule", "product_id": 1, "price": 10, "package_amount": "500 g",
             "quantity": 0.3, "unit": "kg"},
        ]
        line = plan_purchase(items, minimum_order=0)["lines"][0]
        assert (line["name"], line["packages"], line["leftover"]) == (
            "cibule, žlutá cibule", 1, "0 g",
        )

    def test_explicit_packages_override_the_calculation(self):
        items = [{"name": "cibule", "product_id": 1, "price": 19.9, "package_amount": "1 kg",
                  "quantity": 3, "unit": None, "packages": 1}]
        line = plan_purchase(items, minimum_order=0)["lines"][0]
        assert (line["packages"], line["exact"]) == (1, True)

    def test_uncomparable_amount_is_flagged(self):
        items = [{"name": "cibule", "product_id": 1, "price": 19.9, "package_amount": "1 kg",
                  "quantity": 3, "unit": None}]
        line = plan_purchase(items, minimum_order=0)["lines"][0]
        assert (line["packages"], line["exact"]) == (1, False)
        assert "cannot compare" in line["note"]

    def test_shared_product_with_mixed_units_is_counted_separately(self):
        items = [
            {"name": "olej", "product_id": 1, "price": 50, "package_amount": "1 l",
             "quantity": 100, "unit": "ml"},
            {"name": "oleje", "product_id": 1, "price": 50, "package_amount": "1 l",
             "quantity": 2, "unit": "lžíce"},
        ]
        line = plan_purchase(items, minimum_order=0)["lines"][0]
        assert (line["packages"], line["exact"]) == (2, False)
