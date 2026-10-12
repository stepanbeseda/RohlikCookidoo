"""Working out what to add to a cart that may already hold some of it."""

from rohlik_cookidoo.ingredients import to_base_unit
from rohlik_cookidoo.packages import packages_needed

# Fallback only: Rohlik.cz minimum order for home delivery in October 2026.
# The official Rohlik MCP reports the current value in the cart.
DEFAULT_MINIMUM_ORDER = 749.0


def _product_id(line: dict) -> int | str:
    """Read the product ID under either spelling used by Rohlik servers."""
    return line["product_id"] if "product_id" in line else line["productId"]


def plan_cart_additions(
    items: list[dict],
    cart: list[dict] | None = None,
    cart_total: float = 0.0,
    minimum_order: float = DEFAULT_MINIMUM_ORDER,
) -> dict:
    """Compare the wanted products with the cart and price what is missing.

    Args:
        items: wanted products: {"name", "product_id", "packages", "price"}.
            The same product listed twice is merged.
        cart: current cart lines: {"product_id", "quantity"}. `productId` is
            accepted in place of `product_id` in both lists.
        cart_total: current cart value.
        minimum_order: order value below which the shop will not deliver.

    Returns the lines with what is already in the cart and what to add,
    `to_add` ready to pass to an add-to-cart tool, and the totals.
    """
    in_cart: dict[str, float] = {}
    for line in cart or []:
        key = str(_product_id(line))
        in_cart[key] = in_cart.get(key, 0) + line.get("quantity", 1)

    wanted: dict[str, dict] = {}
    for item in items:
        key = str(_product_id(item))
        if key in wanted:
            wanted[key]["packages"] += item["packages"]
            wanted[key]["name"] += f", {item['name']}"
        else:
            wanted[key] = {
                "name": item["name"],
                "product_id": _product_id(item),
                "packages": item["packages"],
                "price": float(item.get("price") or 0),
            }

    lines, to_add, added_total = [], [], 0.0
    for key, item in wanted.items():
        already = int(min(in_cart.get(key, 0), item["packages"]))
        add = item["packages"] - already
        cost = round(add * item["price"], 2)
        added_total += cost
        lines.append({
            "name": item["name"],
            "product_id": item["product_id"],
            "packages": item["packages"],
            "already_in_cart": already,
            "add": add,
            "cost": cost,
        })
        if add > 0:
            to_add.append({"product_id": item["product_id"], "quantity": add})

    new_total = round(cart_total + added_total, 2)
    return {
        "lines": lines,
        "to_add": to_add,
        "added_total": round(added_total, 2),
        "cart_total_after": new_total,
        "minimum_order": minimum_order,
        "missing_to_minimum": round(max(0.0, minimum_order - new_total), 2),
    }


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
        cart, cart_total, minimum_order: as in plan_cart_additions.

    Returns the plan of plan_cart_additions; each line also has `exact`,
    `note` and `leftover` from the package calculation.
    """
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(str(_product_id(item)), []).append(item)

    wanted, details = [], {}
    for key, group in groups.items():
        first = group[0]
        detail = _package_plan(group)
        details[key] = detail
        wanted.append({
            "name": ", ".join(item["name"] for item in group),
            "product_id": _product_id(first),
            "packages": detail["packages"],
            "price": first.get("price"),
        })

    plan = plan_cart_additions(wanted, cart, cart_total, minimum_order)
    for line in plan["lines"]:
        detail = details[str(line["product_id"])]
        line.update(exact=detail["exact"], note=detail["note"], leftover=detail["leftover"])
    return plan


def _package_plan(group: list[dict]) -> dict:
    """Package count for one product needed by one or more ingredients."""
    package_amount = group[0].get("package_amount") or ""
    explicit = [item["packages"] for item in group if item.get("packages")]
    if explicit:
        counted = [item for item in group if not item.get("packages")]
        extra = sum(
            packages_needed(i.get("quantity"), i.get("unit"), package_amount)["packages"]
            for i in counted
        )
        return {"packages": sum(explicit) + extra, "exact": True, "note": "", "leftover": None}

    if len(group) == 1:
        item = group[0]
        return packages_needed(item.get("quantity"), item.get("unit"), package_amount)

    amounts = [
        to_base_unit(i["quantity"], i.get("unit")) for i in group if i.get("quantity") is not None
    ]
    kinds = {kind for _, _, kind in amounts}
    if len(amounts) == len(group) and len(kinds) == 1:
        total = sum(amount for amount, _, _ in amounts)
        return packages_needed(total, amounts[0][1], package_amount)

    parts = [packages_needed(i.get("quantity"), i.get("unit"), package_amount) for i in group]
    return {
        "packages": sum(part["packages"] for part in parts),
        "exact": False,
        "note": "amounts in different units were counted separately",
        "leftover": None,
    }
