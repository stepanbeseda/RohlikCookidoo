"""Kontrola zlevnenych produktu z programu Zachran jidlo na Rohlik.cz.

Self-hosted MCP (@tomaspavlin/rohlik-mcp) nema filtr "sales" na search_products,
a textovy vystup neodlisi explicitne "Zachran jidlo" od ostatnich slev.
Pouzivame tedy get_discounted_items — stahne vsechny aktualni slevy naraz —
a krizime je s ingrediencemi podle nazvu.

Produkty s kratkodobou slevou (napr. "(-26 % do 19. 4.)") se povazuji
za Zachran jidlo, produkty s "(Vyhodna cena)" / "(Nabidka do ...)"
za dlouhodobe akce.
"""

import re
import unicodedata
from dataclasses import dataclass

from ingredient_parser import ParsedIngredient
from mcp_clients import MCPConnectionManager


@dataclass
class ZachranMatch:
    """Nalezena shoda mezi ingredienci a zlevnenym produktem."""
    ingredient_name: str
    product_name: str
    original_price: float
    discounted_price: float
    discount_percent: int
    product_id: str


# Format jednoho produktu v get_discounted_items:
#   • NAZEV (oznaceni slevy)
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

# "-26 % do 19. 4." — kratkodoba sleva = zachran jidlo
_SHORT_TERM_TAG_RE = re.compile(r"-\s*(\d+)\s*%\s*do\s*\d+\.\s*\d+\.?")


def _normalize(text: str) -> str:
    """Odstrani diakritiku a prevede na mala pismena."""
    normalized = unicodedata.normalize("NFD", text)
    without_diacritics = "".join(
        c for c in normalized if unicodedata.category(c) != "Mn"
    )
    return without_diacritics.lower().strip()


def _ingredient_matches_product(ingredient_name: str, product_name: str) -> bool:
    """Zjisti, zda nazev produktu odpovida ingredienci (fuzzy matching)."""
    norm_ingredient = _normalize(ingredient_name)
    norm_product = _normalize(product_name)

    if norm_ingredient in norm_product:
        return True

    ingredient_words = norm_ingredient.split()
    if len(ingredient_words) > 1:
        return any(word in norm_product for word in ingredient_words if len(word) > 2)

    return False


async def check_zachran_jidlo(
    mcp: MCPConnectionManager,
    ingredients: list[ParsedIngredient],
) -> list[ZachranMatch]:
    """Zkontroluje, zda jsou pro ingredience dostupne zlevnene produkty.

    Jedno volani get_discounted_items — stahne vsechny aktualni slevy
    a filtrujeme je proti ingredientum.
    """
    try:
        raw = await mcp.call_rohlik_tool("get_discounted_items", {})
    except Exception as e:
        print(f"  Nepodarilo se zkontrolovat Zachran jidlo: {e}")
        return []

    matches: list[ZachranMatch] = []

    for m in _DISCOUNT_BLOCK_RE.finditer(raw or ""):
        tag = m.group("tag") or ""
        short_term = _SHORT_TERM_TAG_RE.search(tag)
        if not short_term:
            # dlouhodoba akce — neni Zachran jidlo
            continue

        name = m.group("name").strip()
        price = float(m.group("price").replace(",", "."))
        orig = m.group("orig")
        orig_price = float(orig.replace(",", ".")) if orig else price
        discount_pct = int(short_term.group(1))
        product_id = m.group("id")

        for ing in ingredients:
            if _ingredient_matches_product(ing.name, name):
                matches.append(ZachranMatch(
                    ingredient_name=ing.name,
                    product_name=name,
                    original_price=orig_price,
                    discounted_price=price,
                    discount_percent=discount_pct,
                    product_id=product_id,
                ))
                break

    return matches


def display_zachran_matches(matches: list[ZachranMatch]) -> None:
    """Vypise nalezene shody se zlevnenymi produkty."""
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
