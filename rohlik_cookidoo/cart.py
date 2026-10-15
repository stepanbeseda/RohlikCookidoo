"""The purchase plan: from chosen products to package counts, cart additions and totals.

`plan_purchase` is the module's interface. It groups the wanted items by product once
and, for each product, works out the package count and leftover, compares it with the
cart and prices what is missing; then it adds up the totals against the minimum order.
Package sizes as the shop writes them ("4 x 125 g", "cca 0,85 kg") are parsed here too.
"""

import math
import re

from rohlik_cookidoo.ingredients import format_quantity, to_base_unit

# Fallback only: Rohlik.cz minimum order for home delivery in October 2026.
# The official Rohlik MCP reports the current value in the cart.
DEFAULT_MINIMUM_ORDER = 749.0

_BASE_UNIT = {"weight": "g", "volume": "ml", "count": "ks"}

_NUM = r"\d+(?:[.,]\d+)?"
# "500 g", "1,98 l", "cca 130 g", "4 x 125 g", "6×0,5 l", "10 ks"
_PACKAGE = re.compile(
    rf"(?:(\d+)\s*[x×]\s*)?({_NUM})\s*(kg|mg|g|ml|dl|cl|l|ks)\b", re.IGNORECASE
)


def _product_id(line: dict) -> int | str:
    """Read the product ID under either spelling used by Rohlik servers."""
    return line["product_id"] if "product_id" in line else line["productId"]


def plan_purchase(
    items: list[dict],
    cart: list[dict] | None = None,
    cart_total: float = 0.0,
    minimum_order: float = DEFAULT_MINIMUM_ORDER,
) -> dict:
    """Turn chosen products into package counts and cart additions in one step.

    Args:
        items: one per ingredient: {"name", "product_id", "package_amount",
            "price", "quantity", "unit"}. An explicit "packages" overrides the
            calculation. Ingredients sharing a product are combined before
            rounding up, so 200 g + 300 g from a 500 g package is one package.
        cart: current cart lines: {"product_id", "quantity"}. `productId` is
            accepted in place of `product_id` in both lists.
        cart_total: current cart value.
        minimum_order: order value below which the shop will not deliver.

    Returns the lines (package count, what is already in the cart, what to add,
    cost, `exact`, `note` and `leftover`), `to_add` ready to pass to an
    add-to-cart tool, and the totals.
    """
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(str(_product_id(item)), []).append(item)

    in_cart: dict[str, float] = {}
    for line in cart or []:
        key = str(_product_id(line))
        in_cart[key] = in_cart.get(key, 0) + line.get("quantity", 1)

    lines, to_add, added_total = [], [], 0.0
    for key, group in groups.items():
        first = group[0]
        count = _count_packages(group, first.get("package_amount") or "")
        packages = count["packages"]
        already = int(min(in_cart.get(key, 0), packages))
        add = packages - already
        cost = round(add * float(first.get("price") or 0), 2)
        added_total += cost
        lines.append({
            "name": ", ".join(item["name"] for item in group),
            "product_id": _product_id(first),
            "packages": packages,
            "already_in_cart": already,
            "add": add,
            "cost": cost,
            "exact": count["exact"],
            "note": count["note"],
            "leftover": count["leftover"],
        })
        if add > 0:
            to_add.append({"product_id": _product_id(first), "quantity": add})

    new_total = round(cart_total + added_total, 2)
    return {
        "lines": lines,
        "to_add": to_add,
        "added_total": round(added_total, 2),
        "cart_total_after": new_total,
        "minimum_order": minimum_order,
        "missing_to_minimum": round(max(0.0, minimum_order - new_total), 2),
    }


def _count_packages(group: list[dict], package_amount: str) -> dict:
    """Package count for one product needed by one or more ingredients."""
    explicit = [item["packages"] for item in group if item.get("packages")]
    if explicit:
        counted = [item for item in group if not item.get("packages")]
        extra = sum(
            _packages_needed(i.get("quantity"), i.get("unit"), package_amount)["packages"]
            for i in counted
        )
        return {"packages": sum(explicit) + extra, "exact": True, "note": "", "leftover": None}

    if len(group) == 1:
        item = group[0]
        return _packages_needed(item.get("quantity"), item.get("unit"), package_amount)

    amounts = [
        to_base_unit(i["quantity"], i.get("unit")) for i in group if i.get("quantity") is not None
    ]
    kinds = {kind for _, _, kind in amounts}
    if len(amounts) == len(group) and len(kinds) == 1:
        total = sum(amount for amount, _, _ in amounts)
        return _packages_needed(total, amounts[0][1], package_amount)

    parts = [_packages_needed(i.get("quantity"), i.get("unit"), package_amount) for i in group]
    return {
        "packages": sum(part["packages"] for part in parts),
        "exact": False,
        "note": "amounts in different units were counted separately",
        "leftover": None,
    }


def _parse_package_amount(text: str) -> tuple[float, str] | None:
    """Parse a product's package size into (amount, group).

    The group is "weight" (grams), "volume" (millilitres) or "count" (pieces).
    Returns None when the text has no recognisable size.
    """
    match = _PACKAGE.search(text or "")
    if not match:
        return None
    multiplier = int(match[1]) if match[1] else 1
    amount = float(match[2].replace(",", "."))
    base, _, group = to_base_unit(amount, match[3].lower())
    return multiplier * base, group


def _packages_needed(
    quantity: float | None, unit: str | None, package_amount: str
) -> dict:
    """Estimate how many packages cover the required quantity.

    Returns {"packages": int, "exact": bool, "note": str, "leftover": str | None}.
    `exact` is False when the result is a fallback of one package or relies on
    treating 1 g as 1 ml (fine for water and milk, off for oil, honey or
    flour). `leftover` is what remains after cooking, e.g. "300 g", or None
    when it cannot be worked out.
    """
    def fallback(note: str) -> dict:
        return {"packages": 1, "exact": False, "note": note, "leftover": None}

    if quantity is None:
        return fallback("recipe gives no amount")

    package = _parse_package_amount(package_amount)
    if package is None:
        return fallback("package size not recognised")

    package_base, package_group = package
    needed_base, _, needed_group = to_base_unit(quantity, unit)
    same_group = needed_group == package_group
    if not same_group and {needed_group, package_group} != {"weight", "volume"}:
        return fallback(f"cannot compare {needed_group} with {package_group}")

    packages = max(1, math.ceil(needed_base / package_base - 1e-9))
    left = max(0.0, packages * package_base - needed_base)
    return {
        "packages": packages,
        "exact": same_group,
        "note": "" if same_group else "assumed 1 g = 1 ml",
        "leftover": format_quantity(round(left, 2), _BASE_UNIT[package_group]),
    }
