"""RohlikCookidoo — hlavní vstupní bod aplikace.

Propojuje Cookidoo (recepty z Thermomixu) s Rohlik.cz (nákup potravin).

Použití:
    python main.py              # Jeden recept → ingredience → košík
    python main.py --week       # Týdenní plán → agregované ingredience → košík
    python main.py --discover   # Vypíše dostupné MCP nástroje
"""

import asyncio
import re
import sys
import json
import math

from config import load_config, get_quality_preference, load_pantry, is_pantry_item
from mcp_clients import MCPConnectionManager
from ingredient_parser import (
    parse_ingredients,
    extract_ingredients_from_recipe_text,
    aggregate_ingredients,
    display_aggregated_ingredients,
    AggregatedIngredient,
    _format_qty,
)
from rohlik_mapper import search_products_batch, add_to_cart, select_product_interactive, filter_by_preference, RohlikProduct
from zachran_jidlo import check_zachran_jidlo, display_zachran_matches


def _print_cart_result(result: str, cart_items: list) -> None:
    """Zobrazí výsledek přidání do košíku s jasným status."""
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        print("\nProdukty pridany do kosiku. Zkontroluj Rohlik.cz.")
        return

    added = len(data.get("items", []))
    failed_ids = data.get("items_failed_to_add", [])
    total = data.get("totalPrice", 0)

    if data.get("success") and added > 0:
        print(f"\nPridano do kosiku: {added} produktu (celkem {total} Kc)")
    elif failed_ids:
        id_to_name = {str(item[0].id): item[0].name for item in cart_items}
        print(f"\nNepodařilo se pridat {len(failed_ids)} produktu do kosiku.")
        print("Mozne priciny: produkt neni dostupny ve vasi dorucovaci zone.")
        print("\nSelhane produkty:")
        for fid in failed_ids:
            name = id_to_name.get(str(fid), fid)
            print(f"  - {name}")
        if added > 0:
            print(f"\nUspesne pridano: {added} produktu.")
    else:
        print("\nProdukty pridany do kosiku. Zkontroluj Rohlik.cz.")


def _calculate_packages_needed(agg: AggregatedIngredient, product: RohlikProduct) -> int:
    """Odhadne počet balení potřebných pro požadované množství.

    Např. potřeba 700g, balení 500g → 2 balení.
    Pokud nelze odhadnout, vrátí 1.
    """
    if agg.total_quantity is None or not product.amount:
        return 1

    # Zkusíme vytáhnout číslo z product.amount (např. "500 g", "1 kg", "0.5 l")
    amount_match = re.search(r"([\d.,]+)\s*(g|kg|ml|l|dl)", product.amount, re.IGNORECASE)
    if not amount_match:
        return 1

    pkg_qty = float(amount_match.group(1).replace(",", "."))
    pkg_unit = amount_match.group(2).lower()

    # Normalizujeme na stejnou jednotku jako agg
    from ingredient_parser import UNIT_TO_GRAMS, UNIT_TO_ML, _to_base
    needed = agg.total_quantity
    needed_unit = agg.unit or ""

    try:
        needed_base, needed_u = _to_base(needed, needed_unit)
        pkg_base, pkg_u = _to_base(pkg_qty, pkg_unit)
        if needed_u == pkg_u:
            return max(1, math.ceil(needed_base / pkg_base))
    except Exception:
        pass

    return 1


async def _run_shopping_flow(
    mcp: MCPConnectionManager,
    aggregated: list[AggregatedIngredient],
) -> None:
    """Společná část nákupního flow: search → zachraň jídlo → výběr → košík."""
    # Filtruj suroviny, ktere mame doma
    pantry = load_pantry()
    if pantry:
        pantry_items = [a for a in aggregated if is_pantry_item(a.name, pantry)]
        aggregated = [a for a in aggregated if not is_pantry_item(a.name, pantry)]

        if pantry_items:
            print("\n=== Doma by mely byt ===")
            for a in pantry_items:
                qty = _format_qty(a.total_quantity, a.unit)
                print(f"  {a.name} ({qty})")
            print(f"  -> {len(pantry_items)} surovin preskoceno (nekupujeme)\n")

    if not aggregated:
        print("Vsechny suroviny jsou v domaci zasobarni, nic neni treba nakoupit.")
        return

    preference = get_quality_preference()

    # Batch search všech ingrediencí (jedno MCP volání před interakcí)
    search_terms = [a.search_term for a in aggregated]
    print(f"\nVyhledavam {len(search_terms)} ingredienci na Rohlik.cz...")
    all_products = await search_products_batch(mcp, search_terms)

    print("Kontroluji Zachran jidlo nabidky...")
    zachran_matches = await check_zachran_jidlo(mcp, aggregated)
    display_zachran_matches(zachran_matches)

    # Interaktivní výběr (bez MCP — spojení může být nečinné)
    cart_items = []  # list[(RohlikProduct, quantity)]
    for agg in aggregated:
        products = filter_by_preference(all_products.get(agg.search_term, []), preference)
        qty_label = _format_qty(agg.total_quantity, agg.unit)
        selected = select_product_interactive(products, f"{agg.name} ({qty_label} celkem)")
        if selected:
            qty = _calculate_packages_needed(agg, selected)
            cart_items.append((selected, qty))

    if not cart_items:
        print("\nZadne produkty nebyly vybrany.")
        return

    confirm = input(
        f"\nPridat {len(cart_items)} produktu do kosiku? (a/n) [a]: "
    ).strip().lower() or "a"

    if confirm == "a":
        print("Pridavam do kosiku...")
        items = [
            {"product_id": int(p.id), "quantity": qty}
            for p, qty in cart_items
        ]
        result = await add_to_cart(mcp, items)
        _print_cart_result(result, cart_items)
    else:
        print("Zruseno.")


def parse_recipe_ids_from_plan(plan_text: str) -> list[tuple[str, str]]:
    """Vytáhne seznam (recipe_id, recipe_name) z textu get_planned_recipes_this_week.

    Formát řádku: '  • r59322 — Název receptu'
    """
    pattern = re.compile(r"•\s+(r\w+)\s+—\s+(.+)")
    return [(m.group(1).strip(), m.group(2).strip()) for m in pattern.finditer(plan_text)]


async def weekly_shopping_flow(mcp: MCPConnectionManager) -> None:
    """Stáhne týdenní plán z Cookidoo, agreguje ingredience a přidá do košíku."""
    print("\nPripojuji se ke Cookidoo...")
    auth_result = await mcp.call_cookidoo_tool("connect_to_cookidoo")
    print(f"  {auth_result}")
    if "Error" in auth_result or "Failed" in auth_result:
        return

    print("Stahuji tydenny plan z Cookidoo...")
    plan_text = await mcp.call_cookidoo_tool("get_planned_recipes_this_week")
    print(plan_text)

    recipe_ids = parse_recipe_ids_from_plan(plan_text)
    if not recipe_ids:
        print("Zadne recepty nejsou naplanovany na tento tyden.")
        return

    print(f"\nNalezeno {len(recipe_ids)} receptu. Stahuji ingredience...")

    # Stáhni ingredience ze všech receptů
    recipes_ingredients = []
    for recipe_id, recipe_name in recipe_ids:
        print(f"  • {recipe_name} ({recipe_id})...")
        recipe_text = await mcp.call_cookidoo_tool(
            "get_recipe_details", {"recipe_id": recipe_id}
        )
        raw = extract_ingredients_from_recipe_text(recipe_text)
        ingredients = parse_ingredients(raw)
        recipes_ingredients.append((recipe_name, ingredients))

    # Agregace
    aggregated = aggregate_ingredients(recipes_ingredients)
    display_aggregated_ingredients(aggregated)

    await _run_shopping_flow(mcp, aggregated)


async def single_recipe_flow(mcp: MCPConnectionManager) -> None:
    """Stáhne jeden recept dle ID a přidá ingredience do košíku."""
    print("\nPripojuji se ke Cookidoo...")
    auth_result = await mcp.call_cookidoo_tool("connect_to_cookidoo")
    print(f"  {auth_result}")
    if "Error" in auth_result or "Failed" in auth_result:
        return

    recipe_id = input("\nZadej ID receptu z Cookidoo (napr. r59322): ").strip()
    if not recipe_id:
        print("Zadne ID nezadano.")
        return
    if not re.fullmatch(r"r\d+", recipe_id):
        print("Neplatne ID receptu. Ocekavany format: r59322")
        return

    print(f"\nStahuji recept {recipe_id}...")
    recipe_text = await mcp.call_cookidoo_tool(
        "get_recipe_details", {"recipe_id": recipe_id}
    )
    print(recipe_text)

    raw_ingredients = extract_ingredients_from_recipe_text(recipe_text)
    if not raw_ingredients:
        print("\nNepodarilo se extrahovat ingredience z receptu.")
        return

    ingredients = parse_ingredients(raw_ingredients)
    print(f"\nNalezeno {len(ingredients)} ingredienci:")
    for i, ing in enumerate(ingredients, 1):
        qty = f"{ing.quantity} {ing.unit or ''}" if ing.quantity else "dle chuti"
        print(f"  {i}. {ing.name} ({qty.strip()})")

    # Zabalíme jako AggregatedIngredient pro jednotné flow
    from ingredient_parser import AggregatedIngredient
    aggregated = [
        AggregatedIngredient(
            name=ing.name,
            total_quantity=ing.quantity,
            unit=ing.unit,
            sources=[recipe_id],
            search_term=ing.search_term,
        )
        for ing in ingredients
    ]

    await _run_shopping_flow(mcp, aggregated)


async def discover_tools(mcp: MCPConnectionManager) -> None:
    """Vypíše všechny dostupné nástroje z připojených MCP serverů."""
    tools = await mcp.list_tools()
    for server_name, server_tools in tools.items():
        print(f"\n{'='*60}")
        print(f"  {server_name.upper()} — dostupné nástroje")
        print(f"{'='*60}")
        for tool in server_tools:
            desc = tool['description'][:100] if tool.get('description') else ''
            print(f"\n  {tool['name']}")
            print(f"    {desc}...")
            if tool.get("schema", {}).get("properties"):
                params = list(tool["schema"]["properties"].keys())
                print(f"    Parametry: {', '.join(params)}")


async def main() -> None:
    """Hlavní funkce aplikace."""
    week_mode = "--week" in sys.argv
    discover_mode = "--discover" in sys.argv

    try:
        config = load_config()
    except ValueError as e:
        print(f"Chyba konfigurace: {e}")
        sys.exit(1)

    mcp = MCPConnectionManager(config)

    try:
        print("Pripojuji se k MCP serverum...")
        await mcp.connect_cookidoo()
        await mcp.connect_rohlik()

        if discover_mode:
            await discover_tools(mcp)
        elif week_mode:
            await weekly_shopping_flow(mcp)
        else:
            await single_recipe_flow(mcp)

    except KeyboardInterrupt:
        print("\n\nPreruseno uzivatelem.")
    except Exception as e:
        print(f"\nChyba: {e}")
        if "--debug" in sys.argv:
            raise
    finally:
        await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
