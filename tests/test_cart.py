"""Tests for the purchase plan, all through `plan_purchase`."""

import pytest

from rohlik_cookidoo.cart import PurchasePlanError, plan_purchase

ITEMS = [
    {"name": "vepřová plec", "product_id": 1408929, "packages": 1, "price": 211.29,
     "package_amount": "cca 0,89 kg"},
    {"name": "cibule", "product_id": 1349783, "packages": 3, "price": 2.3,
     "package_amount": "cca 120 g"},
]


def plan_one(package_amount, quantity, unit, **extra):
    """Plan a single item and return its line."""
    item = {"name": "x", "product_id": 1, "price": 10, "package_amount": package_amount,
            "quantity": quantity, "unit": unit, **extra}
    return plan_purchase([item], minimum_order=0)["lines"][0]


def counted(line):
    return line["packages"], line["exact"], line["note"], line["leftover"]


@pytest.mark.parametrize(
    ("package", "quantity", "unit", "leftover"),
    [
        ("500 g", 100, "g", "400 g"),
        ("1 kg", 100, "g", "900 g"),
        ("1,98 l", 1, "l", "980 ml"),
        ("cca 130 g", 100, "g", "30 g"),
        ("cca 0,85 kg", 100, "g", "750 g"),
        ("4 x 125 g", 100, "g", "400 g"),
        ("6×0,5 l", 1, "l", "2000 ml"),
        ("10 ks", 4, None, "6 ks"),
    ],
)
def test_package_size_is_read(package, quantity, unit, leftover):
    # The parsed size shows in what is left of one package after cooking.
    assert counted(plan_one(package, quantity, unit)) == (1, True, "", leftover)


@pytest.mark.parametrize("package", ["", "velké balení"])
def test_unrecognised_package_size_falls_back_to_one_package(package):
    line = plan_one(package, 200, "g")
    assert counted(line) == (1, False, "package size not recognised", None)


@pytest.mark.parametrize(
    ("quantity", "unit", "package", "packages", "leftover"),
    [
        (700, "g", "500 g", 2, "300 g"),
        (500, "g", "500 g", 1, "0 g"),
        (501, "g", "500 g", 2, "499 g"),
        (0.7, "kg", "500 g", 2, "300 g"),
        (300, "g", "4 x 125 g", 1, "200 g"),
        (2, "l", "6×0,5 l", 1, "1000 ml"),
        (12, "ks", "10 ks", 2, "8 ks"),
        (12, None, "10 ks", 2, "8 ks"),
    ],
)
def test_same_unit_group_is_exact(quantity, unit, package, packages, leftover):
    line = plan_one(package, quantity, unit)
    assert counted(line) == (packages, True, "", leftover)


def test_grams_against_litres_is_an_estimate():
    line = plan_one("1 l", 1500, "g")
    assert counted(line) == (2, False, "assumed 1 g = 1 ml", "500 ml")


@pytest.mark.parametrize(
    ("quantity", "unit", "package", "note"),
    [
        (3, None, "1 kg", "cannot compare count with weight"),
        (2, "lžíce", "500 ml", "cannot compare lžíce with volume"),
        (None, None, "1 kg", "recipe gives no amount"),
        (200, "g", "balení", "package size not recognised"),
    ],
)
def test_falls_back_to_one_package_with_a_note(quantity, unit, package, note):
    assert counted(plan_one(package, quantity, unit)) == (1, False, note, None)


def test_empty_cart_adds_everything():
    plan = plan_purchase(ITEMS)
    assert plan["to_add"] == [
        {"product_id": 1408929, "quantity": 1},
        {"product_id": 1349783, "quantity": 3},
    ]
    assert plan["added_total"] == 218.19
    assert plan["cart_total_after"] == 218.19
    assert plan["missing_to_minimum"] == 530.81


def test_products_in_the_cart_are_not_added_twice():
    cart = [{"product_id": 1408929, "quantity": 1}, {"product_id": 1349783, "quantity": 1}]
    plan = plan_purchase(ITEMS, cart, cart_total=213.59)
    assert plan["to_add"] == [{"product_id": 1349783, "quantity": 2}]
    assert [(line["already_in_cart"], line["add"]) for line in plan["lines"]] == [(1, 0), (1, 2)]
    assert plan["added_total"] == 4.6
    assert plan["cart_total_after"] == 218.19


def test_running_twice_adds_nothing():
    cart = [{"product_id": "1408929", "quantity": 2}, {"product_id": 1349783, "quantity": 3}]
    plan = plan_purchase(ITEMS, cart, cart_total=800)
    assert plan["to_add"] == []
    assert plan["added_total"] == 0
    assert plan["missing_to_minimum"] == 0


def test_same_product_with_explicit_packages_is_merged():
    items = [
        {"name": "cibule", "product_id": 1, "packages": 2, "price": 10, "package_amount": "1 kg"},
        {"name": "žlutá cibule", "product_id": 1, "packages": 1, "price": 10,
         "package_amount": "1 kg"},
    ]
    plan = plan_purchase(items, minimum_order=0)
    assert plan["to_add"] == [{"product_id": 1, "quantity": 3}]
    assert plan["lines"][0]["name"] == "cibule, žlutá cibule"
    assert plan["added_total"] == 30


def test_product_id_spelling_of_the_official_server_is_accepted():
    items = [{"name": "cibule", "productId": 1349783, "packages": 3, "price": 2.53,
              "package_amount": "cca 120 g"}]
    plan = plan_purchase(items, [{"productId": 1349783, "quantity": 1}], minimum_order=749)
    assert plan["to_add"] == [{"product_id": 1349783, "quantity": 2}]


def test_missing_price_counts_as_zero():
    plan = plan_purchase(
        [{"name": "x", "product_id": 1, "packages": 2, "package_amount": "1 kg"}]
    )
    assert plan["to_add"] == [{"product_id": 1, "quantity": 2}]
    assert plan["added_total"] == 0


def test_packages_leftovers_and_cart_in_one_step():
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


def test_ingredients_sharing_a_product_are_summed_before_rounding():
    items = [
        {"name": "cibule", "product_id": 1, "price": 10, "package_amount": "500 g",
         "quantity": 200, "unit": "g"},
        {"name": "žlutá cibule", "product_id": 1, "price": 10, "package_amount": "500 g",
         "quantity": 0.3, "unit": "kg"},
    ]
    line = plan_purchase(items, minimum_order=0)["lines"][0]
    assert (line["name"], line["packages"], line["leftover"], line["exact"]) == (
        "cibule, žlutá cibule", 1, "0 g", True,
    )


def test_explicit_packages_override_the_calculation():
    line = plan_one("1 kg", 3, None, packages=1)
    assert (line["packages"], line["exact"]) == (1, True)


def test_uncomparable_amount_is_flagged():
    line = plan_one("1 kg", 3, None)
    assert (line["packages"], line["exact"]) == (1, False)
    assert "cannot compare" in line["note"]


def test_shared_product_with_mixed_units_is_counted_separately():
    items = [
        {"name": "olej", "product_id": 1, "price": 50, "package_amount": "1 l",
         "quantity": 100, "unit": "ml"},
        {"name": "oleje", "product_id": 1, "price": 50, "package_amount": "1 l",
         "quantity": 2, "unit": "lžíce"},
    ]
    line = plan_purchase(items, minimum_order=0)["lines"][0]
    assert (line["packages"], line["exact"], line["note"]) == (
        2, False, "amounts in different units were counted separately",
    )


def test_conflicting_package_amount_is_flagged():
    items = [
        {"name": "cibule", "product_id": 1, "price": 10, "package_amount": "500 g",
         "quantity": 300, "unit": "g"},
        {"name": "žlutá cibule", "product_id": 1, "price": 10, "package_amount": "1 kg",
         "quantity": 300, "unit": "g"},
    ]
    line = plan_purchase(items, minimum_order=0)["lines"][0]
    assert (line["packages"], line["exact"], line["leftover"]) == (2, False, "400 g")
    assert line["note"] == (
        'items for this product give different package_amount ("500 g", "1 kg");'
        ' counted with "500 g"'
    )


def test_conflicting_price_is_flagged():
    items = [
        {"name": "cibule", "product_id": 1, "price": 10, "package_amount": "500 g",
         "quantity": 200, "unit": "g"},
        {"name": "žlutá cibule", "product_id": 1, "price": 12.5, "package_amount": "500 g",
         "quantity": 200, "unit": "g"},
    ]
    plan = plan_purchase(items, minimum_order=0)
    line = plan["lines"][0]
    assert (line["packages"], line["exact"], line["cost"]) == (1, False, 10)
    assert plan["added_total"] == 10
    assert line["note"] == "items for this product give different price (10, 12.5); priced at 10"


def test_same_package_size_written_differently_is_no_conflict():
    items = [
        {"name": "a", "product_id": 1, "price": 10, "package_amount": "1 kg",
         "quantity": 300, "unit": "g"},
        {"name": "b", "product_id": 1, "price": 10.0, "package_amount": "1000 g",
         "quantity": 300, "unit": "g"},
        {"name": "c", "product_id": 1, "package_amount": "", "quantity": 100, "unit": "g"},
    ]
    line = plan_purchase(items, minimum_order=0)["lines"][0]
    assert counted(line) == (1, True, "", "300 g")
    assert line["cost"] == 10


def test_conflict_and_estimate_notes_are_joined():
    items = [
        {"name": "mléko", "product_id": 1, "price": 20, "package_amount": "1 l",
         "quantity": 500, "unit": "g"},
        {"name": "mléka", "product_id": 1, "price": 25, "package_amount": "1 l",
         "quantity": 200, "unit": "g"},
    ]
    line = plan_purchase(items, minimum_order=0)["lines"][0]
    assert line["exact"] is False
    assert line["note"] == (
        "items for this product give different price (20, 25); priced at 20;"
        " assumed 1 g = 1 ml"
    )


def test_zero_packages_buys_nothing():
    item = {"name": "cibule", "product_id": 1, "price": 10, "package_amount": "1 kg",
            "quantity": 300, "unit": "g", "packages": 0}
    plan = plan_purchase(
        [item], cart=[{"product_id": 1, "quantity": 2}], cart_total=20, minimum_order=0
    )
    line = plan["lines"][0]
    assert (line["packages"], line["already_in_cart"], line["add"], line["cost"]) == (0, 0, 0, 0)
    assert (line["exact"], line["leftover"]) == (True, None)
    assert plan["to_add"] == []
    assert plan["added_total"] == 0
    assert plan["cart_total_after"] == 20


def test_zero_packages_without_an_amount():
    assert counted(plan_one("1 kg", None, None, packages=0)) == (0, True, "", None)


def test_explicit_packages_keep_the_counted_part_inexact():
    items = [
        {"name": "sůl", "product_id": 1, "price": 10, "package_amount": "1 kg", "packages": 1},
        {"name": "soli", "product_id": 1, "price": 10, "package_amount": "1 kg",
         "quantity": None, "unit": None},
    ]
    line = plan_purchase(items, minimum_order=0)["lines"][0]
    assert counted(line) == (2, False, "recipe gives no amount", None)


def test_counted_items_next_to_explicit_packages_are_summed():
    items = [
        {"name": "a", "product_id": 1, "price": 10, "package_amount": "500 g", "packages": 1},
        {"name": "b", "product_id": 1, "price": 10, "package_amount": "500 g",
         "quantity": 200, "unit": "g"},
        {"name": "c", "product_id": 1, "price": 10, "package_amount": "500 g",
         "quantity": 200, "unit": "g"},
    ]
    line = plan_purchase(items, minimum_order=0)["lines"][0]
    assert counted(line) == (2, True, "", None)


def test_item_without_product_id_is_named():
    items = [
        {"name": "máslo", "product_id": 2, "package_amount": "250 g"},
        {"name": "cibule", "package_amount": "1 kg", "quantity": 1, "unit": "kg"},
    ]
    with pytest.raises(PurchasePlanError) as error:
        plan_purchase(items)
    assert str(error.value) == 'item 2 ("cibule") has no product_id or productId'


@pytest.mark.parametrize("ids", [{"product_id": None}, {"productId": " "}])
def test_blank_product_id_is_missing(ids):
    with pytest.raises(PurchasePlanError, match=r'^item 1 \("x"\)'):
        plan_purchase([{"name": "x", "package_amount": "", **ids}])


def test_zero_is_a_valid_product_id():
    plan = plan_purchase([{"name": "x", "product_id": 0, "packages": 1, "package_amount": ""}])
    assert plan["to_add"] == [{"product_id": 0, "quantity": 1}]


def test_cart_line_without_product_id_is_named():
    with pytest.raises(PurchasePlanError) as error:
        plan_purchase(ITEMS, cart=[{"quantity": 1}])
    assert str(error.value) == "cart line 1 has no product_id or productId"


def test_negative_packages_are_refused():
    with pytest.raises(PurchasePlanError) as error:
        plan_one("1 kg", 1, "kg", packages=-1)
    assert str(error.value) == 'item 1 ("x") has packages -1; use 0 or more'


@pytest.mark.parametrize("line", [{"product_id": 1349783, "quantity": None},
                                  {"product_id": 1349783}])
def test_cart_line_without_quantity_counts_as_one(line):
    plan = plan_purchase(ITEMS, cart=[line], minimum_order=0)
    assert plan["to_add"][1] == {"product_id": 1349783, "quantity": 2}


def test_item_without_a_package_size_keeps_the_count_an_estimate():
    # The first item decides the package size, as before: the count stays a flagged
    # estimate instead of silently growing once a later item names the size.
    items = [
        {"name": "a", "product_id": 1, "price": 10, "package_amount": "", "packages": 1},
        {"name": "b", "product_id": 1, "price": 10, "package_amount": "1 kg",
         "quantity": 3, "unit": "kg"},
    ]
    line = plan_purchase(items, minimum_order=0)["lines"][0]
    assert counted(line) == (2, False, "package size not recognised", None)


def test_price_comes_from_the_first_item_that_has_one():
    items = [
        {"name": "a", "product_id": 1, "package_amount": "1 kg", "packages": 1},
        {"name": "b", "product_id": 1, "price": 10, "package_amount": "1 kg", "packages": 1},
    ]
    plan = plan_purchase(items, minimum_order=0)
    assert (plan["lines"][0]["cost"], plan["lines"][0]["exact"]) == (20, True)


def test_price_zero_is_a_price():
    items = [
        {"name": "a", "product_id": 1, "price": 0, "package_amount": "1 kg", "packages": 1},
        {"name": "b", "product_id": 1, "price": 10, "package_amount": "1 kg", "packages": 1},
    ]
    line = plan_purchase(items, minimum_order=0)["lines"][0]
    assert (line["cost"], line["exact"]) == (0, False)
    assert line["note"] == "items for this product give different price (0, 10); priced at 0"
