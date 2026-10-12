"""Checks discounted products from the Zachraň jídlo (food rescue) program on Rohlik.cz.

The self-hosted MCP (@tomaspavlin/rohlik-mcp) has no "sales" filter on
search_products, and its text output does not explicitly tell "Zachraň jídlo"
apart from other discounts. So get_discounted_items is called (it returns one
page of current discounts) and the results are matched against the
ingredients by name.

Products with a short-term discount (e.g. "(-26 % do 19. 4.)") are treated
as food rescue, products tagged "(Výhodná cena)" / "(Nabídka do ...)"
as long-term promotions.
"""

import re
from dataclasses import dataclass

from mcp_clients import MCPConnectionManager
from rohlik_cookidoo.ingredients import AggregatedIngredient
from rohlik_cookidoo.text import normalize


@dataclass
class FoodRescueMatch:
    """A match between an ingredient and a discounted product."""
    ingredient_name: str
    product_name: str
    original_price: float
    discounted_price: float
    discount_percent: int
    product_id: str


# Format of one product in get_discounted_items:
#   • NAME (discount tag)
#     Price: X CZK (was Y CZK)
#     Unit price: ...
#     Amount: ...
#     ID: 1234567
_DISCOUNT_BLOCK_RE = re.compile(
    r"•\s*(?P<name>.+?)\s*\((?P<tag>[^()]*)\)\s*\n"
    r"\s*Price:\s*(?P<price>[\d.,]+)\s*CZK"
    r"(?:\s*\(was\s*(?P<orig>[\d.,]+)\s*CZK\))?"
    r"[^\n]*\n"
    r"(?:\s*Unit price:[^\n]*\n)?"
    r"\s*Amount:\s*[^\n]*\n"
    r"\s*ID:\s*(?P<id>\d+)",
    re.MULTILINE,
)

# "-26 % do 19. 4.": a short-term discount = food rescue
_SHORT_TERM_TAG_RE = re.compile(r"-\s*(\d+)\s*%\s*do\s*\d+\.\s*\d+\.?")


def _ingredient_matches_product(ingredient_name: str, product_name: str) -> bool:
    """Check whether a product name matches an ingredient (fuzzy matching)."""
    norm_ingredient = normalize(ingredient_name)
    norm_product = normalize(product_name)

    if norm_ingredient in norm_product:
        return True

    ingredient_words = norm_ingredient.split()
    if len(ingredient_words) > 1:
        return any(word in norm_product for word in ingredient_words if len(word) > 2)

    return False


async def check_food_rescue(
    mcp: MCPConnectionManager,
    ingredients: list[AggregatedIngredient],
) -> list[FoodRescueMatch]:
    """Check whether discounted products are available for the ingredients.

    Makes a single get_discounted_items call (one page of current discounts)
    and matches the results against the ingredients.
    """
    try:
        raw = await mcp.call_rohlik_tool("get_discounted_items", {})
    except Exception as e:  # noqa: BLE001 - a failed discount check must not stop the shopping flow
        print(f"  Nepodarilo se zkontrolovat Zachran jidlo: {e}")
        return []

    matches: list[FoodRescueMatch] = []

    for m in _DISCOUNT_BLOCK_RE.finditer(raw or ""):
        tag = m.group("tag") or ""
        short_term = _SHORT_TERM_TAG_RE.search(tag)
        if not short_term:
            # long-term promotion, not food rescue
            continue

        name = m.group("name").strip()
        price = float(m.group("price").replace(",", "."))
        orig = m.group("orig")
        orig_price = float(orig.replace(",", ".")) if orig else price
        discount_pct = int(short_term.group(1))
        product_id = m.group("id")

        for ing in ingredients:
            if _ingredient_matches_product(ing.name, name):
                matches.append(FoodRescueMatch(
                    ingredient_name=ing.name,
                    product_name=name,
                    original_price=orig_price,
                    discounted_price=price,
                    discount_percent=discount_pct,
                    product_id=product_id,
                ))
                break

    return matches


def display_food_rescue_matches(matches: list[FoodRescueMatch]) -> None:
    """Print matches with discounted products."""
    if not matches:
        print("  Zadne Zachran jidlo produkty nenalezeny pro tyto ingredience.")
        return

    print("\n" + "=" * 50)
    print("  ZACHRAN JIDLO — Zlevnene produkty!")
    print("=" * 50)

    for match in matches:
        print(
            f"  {match.ingredient_name}: {match.product_name}\n"
            f"    {match.original_price} Kc"
            f" -> {match.discounted_price} Kc"
            f" (sleva {match.discount_percent}%)"
        )

    print()
