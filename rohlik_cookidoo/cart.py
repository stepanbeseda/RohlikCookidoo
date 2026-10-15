"""The purchase plan: from chosen products to package counts, cart additions and totals.

`plan_purchase` is the module's interface. It groups the wanted items by product once
and, for each product, works out the package count and leftover, compares it with the
cart and prices what is missing; then it adds up the totals against the minimum order.
Package sizes and amounts are read and compared by `rohlik_cookidoo.amount`.

A plan line keeps its ingredients as a list and carries the product's ID, name and
package size, so it can be handed back as it is: `bought_products` turns such lines into
one usual-product entry per ingredient.
"""

import math
from collections.abc import Iterable, Mapping
from typing import TypedDict

from rohlik_cookidoo.amount import Amount, canonical_unit, format_quantity, parse_package, total

# Fallback only: Rohlik.cz minimum order for home delivery in October 2026.
# The official Rohlik MCP reports the current value in the cart.
DEFAULT_MINIMUM_ORDER = 749.0


class PurchasePlanError(ValueError):
    """An item, cart line or bought product the plan cannot use; the message names it."""


class PlanLine(TypedDict):
    """One product of the plan; `record_purchase` takes it back as it is."""

    ingredients: list[str]
    product_id: int | str
    product_name: str
    package_amount: str
    packages: int
    already_in_cart: int
    add: int
    cost: float
    exact: bool
    note: str
    leftover: str | None


def plan_purchase(
    items: list[dict],
    cart: list[dict] | None = None,
    cart_total: float = 0.0,
    minimum_order: float = DEFAULT_MINIMUM_ORDER,
) -> dict:
    """Turn chosen products into package counts and cart additions in one step.

    Args:
        items: one per ingredient: {"ingredient", "product_id", "product_name",
            "package_amount", "price", "quantity", "unit"}. `productId` is
            accepted in place of `product_id`; `unit` may be any unit word ("g", "gramů", "kusy").
            A `quantity` of 0 needs no package. An explicit "packages" (0
            included) is used as given; the other items of that product are
            counted. Ingredients sharing a product are combined before rounding
            up, so 200 g + 300 g from a 500 g package is one package. They
            should agree on `price` and `package_amount`; otherwise the line
            uses the package size of the first item and the first price given,
            and is marked inexact.
        cart: current cart lines: {"product_id", "quantity"}; a missing
            quantity counts as one.
        cart_total: current cart value.
        minimum_order: order value below which the shop will not deliver.

    Returns the lines (`PlanLine`: the ingredients, the product's ID, name and
    package size, package count, what is already in the cart, what to add, cost,
    `exact`, `note` and `leftover`), `to_add` as {"productId", "quantity"} for
    the shop's add-to-cart tool, and the totals. Raises PurchasePlanError naming an item or
    cart line without a product ID, or an item with negative `packages` or `quantity`.
    """
    groups: dict[str, list[dict]] = {}
    for index, item in enumerate(items, start=1):
        label = f'item {index} ("{item.get("ingredient", "")}")'
        key = str(_product_id(item, label))
        packages = item.get("packages")
        if packages is not None and packages < 0:
            raise PurchasePlanError(f"{label} has packages {packages}; use 0 or more")
        quantity = item.get("quantity")
        if quantity is not None and quantity < 0:
            raise PurchasePlanError(f"{label} has quantity {quantity}; use 0 or more")
        groups.setdefault(key, []).append(item)

    in_cart: dict[str, float] = {}
    for index, line in enumerate(cart or [], start=1):
        key = str(_product_id(line, f"cart line {index}"))
        quantity = line.get("quantity")
        in_cart[key] = in_cart.get(key, 0) + (1 if quantity is None else quantity)

    lines, to_add, added_total = [], [], 0.0
    for key, group in groups.items():
        line = _plan_line(group, in_cart.get(key, 0))
        added_total += line["cost"]
        lines.append(line)
        if line["add"] > 0:
            to_add.append({"productId": line["product_id"], "quantity": line["add"]})

    new_total = round(cart_total + added_total, 2)
    return {
        "lines": lines,
        "to_add": to_add,
        "added_total": round(added_total, 2),
        "cart_total_after": new_total,
        "minimum_order": minimum_order,
        "missing_to_minimum": round(max(0.0, minimum_order - new_total), 2),
    }


def _product_id(line: dict, label: str) -> int | str:
    """Read the product ID under either spelling used by Rohlik servers."""
    for field in ("product_id", "productId"):
        value = line.get(field)
        if value is not None and str(value).strip():
            return value
    raise PurchasePlanError(f"{label} has no product_id or productId")


def _plan_line(group: list[dict], in_cart: float) -> PlanLine:
    """One product: agreed size and price, package count, cart comparison, cost."""
    package_amount, price, conflicts = _agreed(group)
    count = _count_packages(group, package_amount)
    packages = count["packages"]
    already = int(min(in_cart, packages))
    add = packages - already
    notes = [*conflicts, count["note"]]
    return {
        "ingredients": [item.get("ingredient", "") for item in group],
        "product_id": _product_id(group[0], ""),
        "product_name": next(
            (name for item in group if (name := (item.get("product_name") or "").strip())), ""
        ),
        "package_amount": package_amount,
        "packages": packages,
        "already_in_cart": already,
        "add": add,
        "cost": round(add * price, 2),
        "exact": count["exact"] and not conflicts,
        "note": "; ".join(note for note in notes if note),
        "leftover": count["leftover"],
    }


def bought_products(products: Iterable[Mapping]) -> list[dict]:
    """One usual-product entry per ingredient of each bought product.

    A product is a plan line handed back as it is, or any mapping with
    `ingredients`, `product_id` (or `productId`), `product_name` and
    `package_amount`. Every product is checked before any entry is returned, so
    one bad product stores nothing. Raises PurchasePlanError naming a product
    without a product ID or without ingredients.
    """
    entries = []
    for index, product in enumerate(products, start=1):
        label = f'product {index} ("{product.get("product_name", "")}")'
        product_id = _product_id(product, label)
        ingredients = list(product.get("ingredients") or [])
        if not ingredients:
            raise PurchasePlanError(f"{label} has no ingredients")
        entries.extend(
            {
                "ingredient": ingredient,
                "product_id": product_id,
                "product_name": product.get("product_name", ""),
                "package_amount": product.get("package_amount", ""),
            }
            for ingredient in ingredients
        )
    return entries


def _agreed(group: list[dict]) -> tuple[str, float, list[str]]:
    """The package size and price used for a product, and notes on disagreement.

    The size is the first item's, as it always was: an item that leaves it out
    makes the count a flagged estimate rather than a silent one. Sizes are
    compared by value ("1 kg" is "1000 g"), empty ones are ignored. The price is
    the first one given (none means zero); a price of 0 is a price.
    """
    package_amount = (group[0].get("package_amount") or "").strip()
    sizes: dict = {}
    for item in group:
        text = (item.get("package_amount") or "").strip()
        if text:
            size = parse_package(text) or " ".join(text.lower().split())
            sizes.setdefault(size, text)
    prices: dict[float, float] = {}
    for item in group:
        if item.get("price") is not None:
            prices.setdefault(float(item["price"]), item["price"])

    price = next(iter(prices), 0.0)
    conflicts = []
    if len(sizes) > 1:
        shown = ", ".join(f'"{text}"' for text in sizes.values())
        conflicts.append(
            f'items for this product give different package_amount ({shown});'
            f' counted with "{package_amount}"'
        )
    if len(prices) > 1:
        shown = ", ".join(f"{value:g}" for value in prices)
        conflicts.append(
            f"items for this product give different price ({shown}); priced at {price:g}"
        )
    return package_amount, price, conflicts


def _count_packages(group: list[dict], package_amount: str) -> dict:
    """Package count for one product: explicit `packages` plus the counted items."""
    explicit = [item["packages"] for item in group if item.get("packages") is not None]
    counted = [item for item in group if item.get("packages") is None]
    if not counted:
        return {"packages": sum(explicit), "exact": True, "note": "", "leftover": None}
    part = _count_needed(counted, package_amount)
    if explicit:
        return {**part, "packages": sum(explicit) + part["packages"], "leftover": None}
    return part


def _count_needed(counted: list[dict], package_amount: str) -> dict:
    """Packages for items without explicit `packages`, summed before rounding.

    Items without an amount add no package of their own when others have one; the
    count is then marked inexact. Amounts of different unit groups are counted
    one by one.
    """
    amounts = [
        Amount(item["quantity"], canonical_unit(item.get("unit")))
        for item in counted
        if item.get("quantity") is not None
    ]
    if not amounts:
        return _packages_needed(None, package_amount)

    together = total(amounts)
    if together is not None:
        part = _packages_needed(together, package_amount)
    else:
        parts = [_packages_needed(amount, package_amount) for amount in amounts]
        part = {
            "packages": sum(p["packages"] for p in parts),
            "exact": False,
            "note": "amounts in different units were counted separately",
            "leftover": None,
        }
    if len(amounts) < len(counted):
        notes = [part["note"], "some items give no amount; only the others were counted"]
        part = {**part, "exact": False, "note": "; ".join(n for n in notes if n),
                "leftover": None}
    return part


def _packages_needed(needed: Amount | None, package_amount: str) -> dict:
    """Estimate how many packages cover the required amount.

    Returns {"packages": int, "exact": bool, "note": str, "leftover": str | None}.
    `exact` is False when the result is a fallback of one package or an estimate
    between weight and volume (the note says which). An amount of zero needs no
    package. `leftover` is what remains after cooking, e.g. "300 g", or None
    when it cannot be worked out.
    """
    def fallback(note: str) -> dict:
        return {"packages": 1, "exact": False, "note": note, "leftover": None}

    if needed is None:
        return fallback("recipe gives no amount")
    if needed.value == 0:
        return {"packages": 0, "exact": True, "note": "", "leftover": None}

    package = parse_package(package_amount)
    if package is None:
        return fallback("package size not recognised")

    measured = needed.in_units_of(package)
    if measured is None:
        return fallback(f"cannot compare {needed.group} with {package.group}")

    value, note = measured
    packages = max(1, math.ceil(value / package.value - 1e-9))
    left = max(0.0, packages * package.value - value)
    return {
        "packages": packages,
        "exact": not note,
        "note": note,
        "leftover": format_quantity(round(left, 2), package.unit),
    }
