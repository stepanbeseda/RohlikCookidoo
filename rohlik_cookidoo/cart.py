"""Working out what to add to a cart that may already hold some of it."""

# Rohlik.cz minimum order for home delivery, as published in October 2026
DEFAULT_MINIMUM_ORDER = 749.0


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
        cart: current cart lines: {"product_id", "quantity"}.
        cart_total: current cart value.
        minimum_order: order value below which the shop will not deliver.

    Returns the lines with what is already in the cart and what to add,
    `to_add` ready to pass to an add-to-cart tool, and the totals.
    """
    in_cart: dict[str, float] = {}
    for line in cart or []:
        key = str(line["product_id"])
        in_cart[key] = in_cart.get(key, 0) + line.get("quantity", 1)

    wanted: dict[str, dict] = {}
    for item in items:
        key = str(item["product_id"])
        if key in wanted:
            wanted[key]["packages"] += item["packages"]
            wanted[key]["name"] += f", {item['name']}"
        else:
            wanted[key] = {
                "name": item["name"],
                "product_id": item["product_id"],
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
