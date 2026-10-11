"""Parser for ingredients of Cookidoo recipes.

Turns raw ingredient text (e.g. "200 g hladká mouka") into structured data
with separate quantity, unit and ingredient name.

Also aggregates ingredients across recipes: it sums identical ingredients
and normalizes units (gramů -> g, kilogramů -> kg, ...).
"""

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass
class ParsedIngredient:
    """A single parsed recipe ingredient."""
    original: str        # Original text: "200 g hladká mouka"
    name: str            # Ingredient name: "hladká mouka"
    quantity: float | None  # Quantity: 200.0
    unit: str | None     # Unit: "g"
    search_term: str     # What to search for on Rohlik: "hladká mouka"


# Regex matching a quantity and unit at the start of the string
# Examples: "200 g", "1.5 kg", "100 ml", "2 lžíce", "3 ks"
# Covers abbreviations (g, kg) as well as full Czech forms (gramů, kilogramů)
QUANTITY_PATTERN = re.compile(
    r"^([\d.,]+(?:\s*/\s*[\d.,]+)?)"  # number (or a fraction: 1/2)
    r"\s+"
    r"(g|kg|mg|ml|l|dl|cl"  # abbreviations
    r"|gramů|gramu|gram|gramy"  # grams, all forms
    r"|kilogramů|kilogramu|kilogram|kilogramy"
    r"|mililitrů|mililitru|mililitr|mililitry"
    r"|litrů|litru|litr|litry"
    r"|decilitrů|decilitru|decilitr|decilitry"
    r"|lžíce|lžíci|lžic"  # tablespoon
    r"|lžička|lžičky|lžiček|lžičku"  # teaspoon
    r"|čajová\s+lžička|čajové\s+lžičky|čajových\s+lžiček|čajovou\s+lžičku"  # teaspoon (long form)
    r"|polévková\s+lžíce|polévkové\s+lžíce|polévkových\s+lžic"  # tablespoon (long form)
    r"|ks|kus|kusy|kusů|kusem"
    r"|hrst|hrstí|hrsti"
    r"|balení|bal"
    r"|plátek|plátky|plátků|plátkem"
    r"|stroužek|stroužky|stroužků|stroužkem"
    r"|svazek|svazky|svazků"
    r"|špetka|špetek|špetky"
    r"|kapka|kapky|kapek"
    r"|kousek|kousky|kousků"
    r"|snítka|snítky|snítek)"
    r"\s+"
    r"(.+)$",
    re.IGNORECASE,
)

# Pattern for ingredients without a quantity (e.g. "sůl", "pepř podle chuti")
PLAIN_PATTERN = re.compile(r"^(.+?)(?:\s+podle chuti)?$", re.IGNORECASE)


def _clean_search_term(name: str) -> str:
    """Clean an ingredient name for searching on Rohlik.

    - Drops adjectives after a comma: "kaparů, solených" -> "kaparů"
    - Drops text in parentheses: "mléko (plnotučné)" -> "mléko"
    """
    term = name.split(",")[0].strip()
    term = re.sub(r"\(.*?\)", "", term).strip()
    return term


def _parse_number(text: str) -> float:
    """Convert a textual number to float.

    Handles: "200", "1.5", "1,5", "1/2"
    """
    text = text.strip().replace(",", ".")
    if "/" in text:
        parts = text.split("/")
        return float(parts[0].strip()) / float(parts[1].strip())
    return float(text)


def parse_single_ingredient(text: str) -> ParsedIngredient:
    """Parse a single ingredient from a text string.

    Args:
        text: Ingredient text, e.g. "200 g hladká mouka"

    Returns:
        ParsedIngredient with the separated fields
    """
    text = text.strip()
    if not text:
        return ParsedIngredient(
            original=text, name="", quantity=None, unit=None, search_term=""
        )

    # Try to match quantity + unit + name
    match = QUANTITY_PATTERN.match(text)
    if match:
        quantity_str, unit, name = match.groups()
        quantity = _parse_number(quantity_str)
        name = name.strip()
        return ParsedIngredient(
            original=text,
            name=name,
            quantity=quantity,
            unit=unit.lower() if unit else None,
            search_term=_clean_search_term(name),
        )

    # Try just number + name (no unit, e.g. "3 vejce")
    number_match = re.match(r"^([\d.,]+)\s+(.+)$", text)
    if number_match:
        quantity = _parse_number(number_match.group(1))
        name = number_match.group(2).strip()
        return ParsedIngredient(
            original=text,
            name=name,
            quantity=quantity,
            unit=None,
            search_term=_clean_search_term(name),
        )

    # No quantity, only the ingredient name
    return ParsedIngredient(
        original=text,
        name=text,
        quantity=None,
        unit=None,
        search_term=_clean_search_term(text),
    )


def parse_ingredients(raw_ingredients: list[str]) -> list[ParsedIngredient]:
    """Parse a list of ingredients of a Cookidoo recipe.

    Args:
        raw_ingredients: List of ingredient texts

    Returns:
        List of ParsedIngredient objects
    """
    return [
        parse_single_ingredient(text)
        for text in raw_ingredients
        if text.strip()
    ]


@dataclass
class AggregatedIngredient:
    """An ingredient aggregated across recipes."""
    name: str                   # normalized name: "hladká mouka"
    total_quantity: float | None  # total quantity: 700.0
    unit: str | None            # canonical unit: "g"
    sources: list[str] = field(default_factory=list)  # ["Palačinky (500 g)", "Buchty (200 g)"]
    search_term: str = ""       # what to search for on Rohlik


# Unit normalization to canonical abbreviations
UNIT_CANONICAL: dict[str, str] = {
    # Grams
    "gramů": "g", "gramu": "g", "gram": "g", "gramy": "g",
    # Kilograms
    "kilogramů": "kg", "kilogramu": "kg", "kilogram": "kg", "kilogramy": "kg",
    # Millilitres
    "mililitrů": "ml", "mililitru": "ml", "mililitr": "ml", "mililitry": "ml",
    # Litres
    "litrů": "l", "litru": "l", "litr": "l", "litry": "l",
    # Decilitres
    "decilitrů": "dl", "decilitru": "dl", "decilitr": "dl", "decilitry": "dl",
    # Tablespoon
    "lžíci": "lžíce", "lžic": "lžíce",
    "polévková lžíce": "lžíce", "polévkové lžíce": "lžíce", "polévkových lžic": "lžíce",
    # Teaspoon
    "lžičky": "lžička", "lžiček": "lžička", "lžičku": "lžička",
    "čajová lžička": "lžička", "čajové lžičky": "lžička", "čajových lžiček": "lžička", "čajovou lžičku": "lžička",
    # Pieces
    "kus": "ks", "kusy": "ks", "kusů": "ks", "kusem": "ks",
    # Other
    "hrstí": "hrst", "hrsti": "hrst",
    "plátky": "plátek", "plátků": "plátek", "plátkem": "plátek",
    "stroužky": "stroužek", "stroužků": "stroužek", "stroužkem": "stroužek",
    "svazky": "svazek", "svazků": "svazek",
    "špetek": "špetka", "špetky": "špetka",
    "kapky": "kapka", "kapek": "kapka",
    "kousky": "kousek", "kousků": "kousek",
    "snítky": "snítka", "snítek": "snítka",
}

# Conversion factors to the base unit (g, ml)
UNIT_TO_GRAMS: dict[str, float] = {"g": 1.0, "kg": 1000.0, "mg": 0.001}
UNIT_TO_ML: dict[str, float] = {"ml": 1.0, "l": 1000.0, "dl": 100.0, "cl": 10.0}


def _normalize_name(text: str) -> str:
    """Strip diacritics and lowercase the text for name comparison."""
    normalized = unicodedata.normalize("NFD", text)
    without_diacritics = "".join(
        c for c in normalized if unicodedata.category(c) != "Mn"
    )
    return without_diacritics.lower().strip()


def _canonical_unit(unit: str | None) -> str | None:
    """Convert a unit to its canonical form (gramů -> g)."""
    if unit is None:
        return None
    lower = unit.lower().strip()
    return UNIT_CANONICAL.get(lower, lower)


def _to_base(quantity: float, unit: str) -> tuple[float, str]:
    """Convert a quantity to the base unit (kg -> g, l -> ml)."""
    if unit in UNIT_TO_GRAMS:
        return quantity * UNIT_TO_GRAMS[unit], "g"
    if unit in UNIT_TO_ML:
        return quantity * UNIT_TO_ML[unit], "ml"
    return quantity, unit


def _format_qty(qty: float | None, unit: str | None) -> str:
    """Format a quantity with its unit for display."""
    if qty is None:
        return "dle chuti"
    qty_str = str(int(qty)) if qty == int(qty) else f"{qty:.1f}"
    return f"{qty_str} {unit}" if unit else qty_str


def aggregate_ingredients(
    recipes_ingredients: list[tuple[str, list["ParsedIngredient"]]],
) -> list[AggregatedIngredient]:
    """Aggregate ingredients across recipes, summing shared ones.

    Args:
        recipes_ingredients: List of (recipe_name, [ParsedIngredient]) pairs

    Returns:
        List of AggregatedIngredient: each ingredient once, with the total
        quantity and an overview of its sources.
    """
    # Key: (normalized name, canonical unit or unit group)
    # Value: AggregatedIngredient
    aggregated: dict[tuple[str, str], AggregatedIngredient] = {}

    for recipe_name, ingredients in recipes_ingredients:
        for ing in ingredients:
            canonical_unit = _canonical_unit(ing.unit)
            norm_name = _normalize_name(ing.name)

            # Unit group used for summing (g+kg = "weight", ml+l = "volume")
            if canonical_unit in UNIT_TO_GRAMS:
                unit_group = "weight"
            elif canonical_unit in UNIT_TO_ML:
                unit_group = "volume"
            else:
                unit_group = canonical_unit or "none"

            key = (norm_name, unit_group)

            source_str = f"{recipe_name} ({_format_qty(ing.quantity, canonical_unit)})"

            if key not in aggregated:
                # Convert to the base unit for summing
                if ing.quantity is not None and canonical_unit:
                    base_qty, base_unit = _to_base(ing.quantity, canonical_unit)
                else:
                    base_qty, base_unit = ing.quantity, canonical_unit

                aggregated[key] = AggregatedIngredient(
                    name=ing.name,
                    total_quantity=base_qty,
                    unit=base_unit,
                    sources=[source_str],
                    search_term=ing.search_term,
                )
            else:
                existing = aggregated[key]
                existing.sources.append(source_str)
                if ing.quantity is not None and existing.total_quantity is not None:
                    if canonical_unit:
                        add_qty, _ = _to_base(ing.quantity, canonical_unit)
                    else:
                        add_qty = ing.quantity
                    existing.total_quantity += add_qty

    return list(aggregated.values())


def display_aggregated_ingredients(aggregated: list[AggregatedIngredient]) -> None:
    """Print aggregated ingredients, shared ones first."""
    shared = [a for a in aggregated if len(a.sources) > 1]
    unique = [a for a in aggregated if len(a.sources) == 1]

    if shared:
        print("\n=== Společné ingredience (z více receptů) ===")
        for a in shared:
            qty_str = _format_qty(a.total_quantity, a.unit)
            sources_str = ", ".join(a.sources)
            print(f"  {a.name}: {qty_str}  [{sources_str}]")

    print(f"\n=== Jedinečné ingredience ===")
    for a in unique:
        qty_str = _format_qty(a.total_quantity, a.unit)
        print(f"  {a.name}: {qty_str}  [{a.sources[0]}]")

    print(f"\nCelkem: {len(aggregated)} ingrediencí ({len(shared)} společných)")


def ingredient_lines_from_recipe(recipe: dict) -> list[str]:
    """Turn a recipe from the Cookidoo MCP server into ingredient text lines.

    Each ingredient is {"name": ..., "quantity": ...}; the result puts the
    quantity first ("200 g hladká mouka") so parse_ingredients can read it.

    Args:
        recipe: Result of the get_recipe_details tool

    Returns:
        List of ingredients as text strings
    """
    return [
        f"{ingredient.get('quantity', '')} {ingredient['name']}".strip()
        for ingredient in recipe.get("ingredients", [])
    ]
