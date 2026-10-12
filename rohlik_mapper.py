"""Maps ingredients to products on Rohlik.cz.

Rohlik MCP tools (@tomaspavlin/rohlik-mcp, self-hosted):
- search_products(product_name, limit): one query at a time, returns formatted text
- add_to_cart(products=[{product_id, quantity}]): adds to the cart
- get_cart_content(): cart content

Format of the search_products response (plain text):
    Found 3 products:

    • Kitchin Rýže jasmínová (Kitchin)
      Price: 22.41 Kč (was 24.9 Kč, -10%)
      Amount: 500 g
      ID: 1454459
"""

import re
from dataclasses import dataclass

from config import QualityPreference
from mcp_clients import MCPConnectionManager
from rohlik_cookidoo.ingredients import ParsedIngredient


@dataclass
class RohlikProduct:
    """A product found on Rohlik.cz."""
    id: str
    name: str
    price: float
    amount: str = ""
    brand: str = ""
    is_bio: bool = False
    is_discounted: bool = False
    discount_percent: int = 0
    original_price: float | None = None
    is_food_rescue: bool = False
    in_stock: bool = True


# Whole words only, so that "Symbio" or "Biokoláč" do not count
_BIO_WORD = re.compile(r"\b(?:bio|organic|eko)\b", re.IGNORECASE)


def _is_bio_product(name: str, brand: str) -> bool:
    """Check whether a product is organic (bio)."""
    return bool(_BIO_WORD.search(f"{name} {brand}"))


# Regex for one product block in the search_products response:
#   • <name> (<brand>)
#     Price: <price> Kč [(was <orig> Kč, -<pct>%)]
#     Amount: <amount>
#     ID: <id>
_PRODUCT_BLOCK_RE = re.compile(
    r"•\s*(?P<name>.+?)(?:\s*\((?P<brand>[^()]+)\))?\s*\n"
    r"\s*Price:\s*(?P<price>[\d.,]+)\s*Kč"
    r"(?:\s*\(was\s*(?P<orig>[\d.,]+)\s*Kč,\s*-(?P<pct>\d+)%\))?"
    r"[^\n]*\n"
    r"\s*Amount:\s*(?P<amount>[^\n]*)\n"
    r"\s*ID:\s*(?P<id>\d+)",
    re.MULTILINE,
)


def _parse_products_from_text(text: str) -> list[RohlikProduct]:
    """Parse the formatted text response of search_products into a list of products."""
    products = []
    for m in _PRODUCT_BLOCK_RE.finditer(text or ""):
        name = m.group("name").strip()
        brand = (m.group("brand") or "").strip()
        price = float(m.group("price").replace(",", "."))
        orig = m.group("orig")
        pct = m.group("pct")
        original_price = float(orig.replace(",", ".")) if orig else None
        discount_pct = int(pct) if pct else 0
        is_discounted = original_price is not None

        products.append(RohlikProduct(
            id=m.group("id"),
            name=name,
            price=price,
            amount=m.group("amount").strip(),
            brand=brand,
            is_bio=_is_bio_product(name, brand),
            is_discounted=is_discounted,
            discount_percent=discount_pct,
            original_price=original_price,
            # the self-hosted MCP does not mark "Zachraň jídlo" (food rescue)
            # explicitly; any discount is used as a proxy (a better heuristic
            # would cross-check with get_discounted_items)
            is_food_rescue=is_discounted,
            in_stock=True,
        ))
    return products


def filter_by_preference(
    products: list[RohlikProduct],
    preference: QualityPreference,
) -> list[RohlikProduct]:
    """Sort/filter products by the user's preference."""
    # In-stock products only
    products = [p for p in products if p.in_stock]

    if preference == QualityPreference.BIO:
        return sorted(products, key=lambda p: (not p.is_bio, p.price))
    elif preference == QualityPreference.FOOD_RESCUE:
        return sorted(products, key=lambda p: (not p.is_food_rescue, p.price))
    elif preference == QualityPreference.CHEAPEST:
        return sorted(products, key=lambda p: p.price)
    else:  # STANDARD
        return products


async def search_products_batch(
    mcp: MCPConnectionManager,
    search_terms: list[str],
) -> dict[str, list[RohlikProduct]]:
    """Search for products on Rohlik.

    The self-hosted MCP supports only one query at a time (search_products),
    so the calls are sequential. Returns dict[term, list[products]].
    """
    all_results: dict[str, list[RohlikProduct]] = {}

    for term in search_terms:
        raw_result = await mcp.call_rohlik_tool(
            "search_products",
            {"product_name": term, "limit": 10},
        )
        all_results[term] = _parse_products_from_text(raw_result)

    return all_results


async def find_products_for_ingredient(
    mcp: MCPConnectionManager,
    ingredient: ParsedIngredient,
    preference: QualityPreference,
) -> list[RohlikProduct]:
    """Search Rohlik for products matching the given ingredient."""
    batch_results = await search_products_batch(mcp, [ingredient.search_term])
    products = batch_results.get(ingredient.search_term, [])
    return filter_by_preference(products, preference)


async def add_to_cart(
    mcp: MCPConnectionManager,
    items: list[dict],
) -> str:
    """Add products to the cart on Rohlik.cz.

    Args:
        items: List of {"product_id": int|str, "quantity": int}.
               product_id is converted to int (required by the API).
    """
    products = [
        {"product_id": int(it["product_id"]), "quantity": int(it.get("quantity", 1))}
        for it in items
    ]
    result = await mcp.call_rohlik_tool(
        "add_to_cart",
        {"products": products},
    )
    return result


async def get_cart(mcp: MCPConnectionManager) -> str:
    """Return the cart content."""
    return await mcp.call_rohlik_tool("get_cart_content", {})


def select_product_interactive(
    products: list[RohlikProduct],
    ingredient_name: str,
) -> RohlikProduct | None:
    """Let the user pick a product from the offered ones."""
    if not products:
        print(f"  Zadne produkty nalezeny pro: {ingredient_name}")
        return None

    print(f"\n  Produkty pro '{ingredient_name}':")
    shown = products[:5]
    for i, p in enumerate(shown, 1):
        tags = []
        if p.is_bio:
            tags.append("[BIO]")
        if p.is_food_rescue:
            tags.append("[ZACHRAN]")
        tag_str = " ".join(tags)
        if tag_str:
            tag_str = f" {tag_str}"

        discount_str = ""
        if p.is_discounted and p.original_price:
            discount_str = f" (puv. {p.original_price} Kc, -{p.discount_percent}%)"

        print(f"    {i}. {p.name} ({p.amount}){tag_str} -- {p.price} Kc{discount_str}")

    print("    0. Preskocit")

    while True:
        choice = input(f"  Vyber produkt (0-{len(shown)}) [1]: ").strip() or "1"
        try:
            idx = int(choice)
            if idx == 0:
                return None
            if 1 <= idx <= len(shown):
                return shown[idx - 1]
        except ValueError:
            pass
        print("  Neplatna volba, zkus to znovu.")
