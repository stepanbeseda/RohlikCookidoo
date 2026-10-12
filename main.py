"""RohlikCookidoo: application entry point.

Connects Cookidoo (Thermomix recipes) with Rohlik.cz (grocery shopping).

Usage:
    python main.py              # One recipe -> ingredients -> cart
    python main.py --week       # Weekly plan -> aggregated ingredients -> cart
    python main.py --discover   # List available MCP tools
"""

import asyncio
import json
import re
import sys

from config import get_quality_preference, load_config
from food_rescue import check_food_rescue, display_food_rescue_matches
from mcp_clients import MCPConnectionManager
from rohlik_cookidoo.ingredients import (
    AggregatedIngredient,
    aggregate_ingredients,
    display_aggregated_ingredients,
    format_quantity,
    parse_recipe_ingredients,
)
from rohlik_cookidoo.packages import packages_needed
from rohlik_cookidoo.pantry import CHECK, HAVE, match_pantry, read_pantry_lines
from rohlik_mapper import (
    add_to_cart,
    filter_by_preference,
    search_products_batch,
    select_product_interactive,
)


def _print_cart_result(result: str, cart_items: list) -> None:
    """Print the result of adding to the cart with a clear status."""
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


async def _run_shopping_flow(
    mcp: MCPConnectionManager,
    aggregated: list[AggregatedIngredient],
) -> None:
    """Shared part of the shopping flow: search -> food rescue -> selection -> cart."""
    # Filter out ingredients we have at home
    pantry = read_pantry_lines()
    if pantry:
        matches = [(a, *match_pantry(a.name, pantry)) for a in aggregated]
        at_home = [(a, item) for a, status, item in matches if status == HAVE]
        to_check = [(a, item) for a, status, item in matches if status == CHECK]
        # Only exact matches are skipped; similar items are bought and pointed out
        aggregated = [a for a, status, _ in matches if status != HAVE]

        if at_home:
            print("\n=== Doma by mely byt ===")
            for a, _ in at_home:
                print(f"  {a.name} ({format_quantity(a.total_quantity, a.unit)})")
            print(f"  -> {len(at_home)} surovin preskoceno (nekupujeme)\n")
        if to_check:
            print("=== Zkontroluj doma (ve spizi je neco podobneho) ===")
            for a, item in to_check:
                print(f"  {a.name} — ve spizi: {item}")
            print("  -> tyto suroviny nabidnu k nakupu, muzes je preskocit\n")

    if not aggregated:
        print("Vsechny suroviny jsou v domaci zasobarni, nic neni treba nakoupit.")
        return

    preference = get_quality_preference()

    # Batch search of all ingredients (MCP calls happen before the interaction)
    search_terms = [a.search_term for a in aggregated]
    print(f"\nVyhledavam {len(search_terms)} ingredienci na Rohlik.cz...")
    all_products = await search_products_batch(mcp, search_terms)

    print("Kontroluji Zachran jidlo nabidky...")
    food_rescue_matches = await check_food_rescue(mcp, aggregated)
    display_food_rescue_matches(food_rescue_matches)

    # Interactive selection (no MCP calls; the connection may sit idle)
    cart_items = []  # list[(RohlikProduct, quantity)]
    for agg in aggregated:
        products = filter_by_preference(all_products.get(agg.search_term, []), preference)
        qty_label = format_quantity(agg.total_quantity, agg.unit)
        selected = select_product_interactive(products, f"{agg.name} ({qty_label} celkem)")
        if selected:
            qty = packages_needed(agg.total_quantity, agg.unit, selected.amount)["packages"]
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


def planned_recipe_ids(plan: dict) -> list[tuple[str, str]]:
    """Extract (recipe_id, recipe_name) pairs from a get_planned_recipes_this_week result."""
    return [
        (recipe["id"], recipe["name"])
        for day in plan.get("days", [])
        for recipe in day["recipes"]
    ]


async def weekly_shopping_flow(mcp: MCPConnectionManager) -> None:
    """Fetch the weekly plan from Cookidoo, aggregate ingredients and add them to the cart."""
    print("\nStahuji tydenny plan z Cookidoo...")
    plan = await mcp.call_cookidoo_tool("get_planned_recipes_this_week")
    for day in plan.get("days", []):
        print(f"{day['title']}:")
        for recipe in day["recipes"]:
            print(f"  • {recipe['id']} — {recipe['name']}")

    recipe_ids = planned_recipe_ids(plan)
    if not recipe_ids:
        print("Zadne recepty nejsou naplanovany na tento tyden.")
        return

    print(f"\nNalezeno {len(recipe_ids)} receptu. Stahuji ingredience...")

    # Fetch ingredients of all recipes
    recipes_ingredients = []
    for recipe_id, recipe_name in recipe_ids:
        print(f"  • {recipe_name} ({recipe_id})...")
        recipe = await mcp.call_cookidoo_tool(
            "get_recipe_details", {"recipe_id": recipe_id}
        )
        ingredients = parse_recipe_ingredients(recipe)
        recipes_ingredients.append((recipe_name, ingredients))

    # Aggregation
    aggregated = aggregate_ingredients(recipes_ingredients)
    display_aggregated_ingredients(aggregated)

    await _run_shopping_flow(mcp, aggregated)


async def single_recipe_flow(mcp: MCPConnectionManager) -> None:
    """Fetch one recipe by ID and add its ingredients to the cart."""
    recipe_id = input("\nZadej ID receptu z Cookidoo (napr. r59322): ").strip()
    if not recipe_id:
        print("Zadne ID nezadano.")
        return
    if not re.fullmatch(r"r\d+", recipe_id):
        print("Neplatne ID receptu. Ocekavany format: r59322")
        return

    print(f"\nStahuji recept {recipe_id}...")
    recipe = await mcp.call_cookidoo_tool(
        "get_recipe_details", {"recipe_id": recipe_id}
    )
    print(f"{recipe['name']} ({recipe['servings']} porci)")

    ingredients = parse_recipe_ingredients(recipe)
    if not ingredients:
        print("\nRecept nema zadne ingredience.")
        return

    print(f"\nNalezeno {len(ingredients)} ingredienci:")
    for i, ing in enumerate(ingredients, 1):
        qty = f"{ing.quantity} {ing.unit or ''}" if ing.quantity else "dle chuti"
        print(f"  {i}. {ing.name} ({qty.strip()})")

    aggregated = aggregate_ingredients([(recipe["name"], ingredients)])

    await _run_shopping_flow(mcp, aggregated)


async def discover_tools(mcp: MCPConnectionManager) -> None:
    """List all tools available on the connected MCP servers."""
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
    """Application entry point."""
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
