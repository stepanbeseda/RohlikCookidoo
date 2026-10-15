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


class PurchasePlanError(ValueError):
    """An item or cart line the plan cannot use; the message names it."""


def plan_purchase(
    items: list[dict],
    cart: list[dict] | None = None,
    cart_total: float = 0.0,
    minimum_order: float = DEFAULT_MINIMUM_ORDER,
) -> dict:
    """Turn chosen products into package counts and cart additions in one step.

    Args:
        items: one per ingredient: {"name", "product_id", "package_amount",
            "price", "quantity", "unit"}. `productId` is accepted in place of
            `product_id`. An explicit "packages" (0 included) is used as given;
            the other items of that product are counted. Ingredients sharing a
            product are combined before rounding up, so 200 g + 300 g from a
            500 g package is one package. They should agree on `price` and
            `package_amount`; otherwise the line uses the package size of the
            first item and the first price given, and is marked inexact.
        cart: current cart lines: {"product_id", "quantity"}; a missing
            quantity counts as one.
        cart_total: current cart value.
        minimum_order: order value below which the shop will not deliver.

    Returns the lines (package count, what is already in the cart, what to add,
    cost, `exact`, `note` and `leftover`), `to_add` ready to pass to an
    add-to-cart tool, and the totals. Raises PurchasePlanError naming an item or
    cart line without a product ID, or an item with negative `packages`.
    """
    groups: dict[str, list[dict]] = {}
    for index, item in enumerate(items, start=1):
        label = f'item {index} ("{item.get("name", "")}")'
        key = str(_product_id(item, label))
        packages = item.get("packages")
        if packages is not None and packages < 0:
            raise PurchasePlanError(f"{label} has packages {packages}; use 0 or more")
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
            to_add.append({"product_id": line["product_id"], "quantity": line["add"]})

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


def _plan_line(group: list[dict], in_cart: float) -> dict:
    """One product: agreed size and price, package count, cart comparison, cost."""
    package_amount, price, conflicts = _agreed(group)
    count = _count_packages(group, package_amount)
    packages = count["packages"]
    already = int(min(in_cart, packages))
    add = packages - already
    notes = [*conflicts, count["note"]]
    return {
        "name": ", ".join(item.get("name", "") for item in group),
        "product_id": _product_id(group[0], ""),
        "packages": packages,
        "already_in_cart": already,
        "add": add,
        "cost": round(add * price, 2),
        "exact": count["exact"] and not conflicts,
        "note": "; ".join(note for note in notes if note),
        "leftover": count["leftover"],
    }


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
            size = _parse_package_amount(text) or " ".join(text.lower().split())
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
    """Packages for items without explicit `packages`, summed before rounding."""
    if len(counted) == 1:
        item = counted[0]
        return _packages_needed(item.get("quantity"), item.get("unit"), package_amount)

    amounts = [
        to_base_unit(i["quantity"], i.get("unit")) for i in counted if i.get("quantity") is not None
    ]
    if len(amounts) == len(counted) and len({kind for _, _, kind in amounts}) == 1:
        total = sum(amount for amount, _, _ in amounts)
        return _packages_needed(total, amounts[0][1], package_amount)

    parts = [_packages_needed(i.get("quantity"), i.get("unit"), package_amount) for i in counted]
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
