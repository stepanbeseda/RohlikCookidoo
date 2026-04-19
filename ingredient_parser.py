"""Parser ingrediencí z Cookidoo receptů.

Převádí surový text ingrediencí (např. "200 g hladká mouka") na strukturovaná data
s odděleným množstvím, jednotkou a názvem suroviny.

Také podporuje agregaci ingrediencí z více receptů — sčítá stejné suroviny
a normalizuje jednotky (gramů → g, kilogramů → kg, ...).
"""

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass
class ParsedIngredient:
    """Jedna zparsovaná ingredience z receptu."""
    original: str        # Původní text: "200 g hladká mouka"
    name: str            # Název suroviny: "hladká mouka"
    quantity: float | None  # Množství: 200.0
    unit: str | None     # Jednotka: "g"
    search_term: str     # Co hledat na Rohlíku: "hladká mouka"


# Regex pro rozpoznání množství a jednotky na začátku řetězce
# Příklady: "200 g", "1.5 kg", "100 ml", "2 lžíce", "3 ks"
# Zahrnuje jak zkratky (g, kg) tak plné české tvary (gramů, kilogramů)
QUANTITY_PATTERN = re.compile(
    r"^([\d.,]+(?:\s*/\s*[\d.,]+)?)"  # číslo (nebo zlomek: 1/2)
    r"\s+"
    r"(g|kg|mg|ml|l|dl|cl"  # zkratky
    r"|gramů|gramu|gram|gramy"  # gramy — všechny tvary
    r"|kilogramů|kilogramu|kilogram|kilogramy"
    r"|mililitrů|mililitru|mililitr|mililitry"
    r"|litrů|litru|litr|litry"
    r"|decilitrů|decilitru|decilitr|decilitry"
    r"|lžíce|lžíci|lžic"  # lžíce
    r"|lžička|lžičky|lžiček|lžičku"  # lžička
    r"|čajová\s+lžička|čajové\s+lžičky|čajových\s+lžiček|čajovou\s+lžičku"  # čajová lžička
    r"|polévková\s+lžíce|polévkové\s+lžíce|polévkových\s+lžic"  # polévková lžíce
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

# Vzor pro ingredience bez množství (např. "sůl", "pepř podle chuti")
PLAIN_PATTERN = re.compile(r"^(.+?)(?:\s+podle chuti)?$", re.IGNORECASE)


def _clean_search_term(name: str) -> str:
    """Vyčistí název ingredience pro vyhledávání na Rohlíku.

    - Odstraní přídavná jména za čárkou: "kaparů, solených" → "kaparů"
    - Odstraní obsah v závorkách: "mléko (plnotučné)" → "mléko"
    """
    term = name.split(",")[0].strip()
    term = re.sub(r"\(.*?\)", "", term).strip()
    return term


def _parse_number(text: str) -> float:
    """Převede textové číslo na float.

    Zvládá: "200", "1.5", "1,5", "1/2"
    """
    text = text.strip().replace(",", ".")
    if "/" in text:
        parts = text.split("/")
        return float(parts[0].strip()) / float(parts[1].strip())
    return float(text)


def parse_single_ingredient(text: str) -> ParsedIngredient:
    """Zparsuje jednu ingredienci z textového řetězce.

    Args:
        text: Text ingredience, např. "200 g hladká mouka"

    Returns:
        ParsedIngredient s rozdělenými údaji
    """
    text = text.strip()
    if not text:
        return ParsedIngredient(
            original=text, name="", quantity=None, unit=None, search_term=""
        )

    # Zkusíme rozpoznat množství + jednotku + název
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

    # Zkusíme jen číslo + název (bez jednotky, např. "3 vejce")
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

    # Žádné množství — jen název suroviny
    return ParsedIngredient(
        original=text,
        name=text,
        quantity=None,
        unit=None,
        search_term=_clean_search_term(text),
    )


def parse_ingredients(raw_ingredients: list[str]) -> list[ParsedIngredient]:
    """Zparsuje seznam ingrediencí z Cookidoo receptu.

    Args:
        raw_ingredients: Seznam textových ingrediencí

    Returns:
        Seznam ParsedIngredient objektů
    """
    return [
        parse_single_ingredient(text)
        for text in raw_ingredients
        if text.strip()
    ]


@dataclass
class AggregatedIngredient:
    """Agregovaná ingredience z více receptů."""
    name: str                   # normalizovaný název: "hladká mouka"
    total_quantity: float | None  # celkové množství: 700.0
    unit: str | None            # kanonická jednotka: "g"
    sources: list[str] = field(default_factory=list)  # ["Palačinky (500 g)", "Buchty (200 g)"]
    search_term: str = ""       # co hledat na Rohlíku


# Normalizace jednotek na kanonické zkratky
UNIT_CANONICAL: dict[str, str] = {
    # Gramy
    "gramů": "g", "gramu": "g", "gram": "g", "gramy": "g",
    # Kilogramy
    "kilogramů": "kg", "kilogramu": "kg", "kilogram": "kg", "kilogramy": "kg",
    # Mililitry
    "mililitrů": "ml", "mililitru": "ml", "mililitr": "ml", "mililitry": "ml",
    # Litry
    "litrů": "l", "litru": "l", "litr": "l", "litry": "l",
    # Decilitry
    "decilitrů": "dl", "decilitru": "dl", "decilitr": "dl", "decilitry": "dl",
    # Lžíce
    "lžíci": "lžíce", "lžic": "lžíce",
    "polévková lžíce": "lžíce", "polévkové lžíce": "lžíce", "polévkových lžic": "lžíce",
    # Lžička
    "lžičky": "lžička", "lžiček": "lžička", "lžičku": "lžička",
    "čajová lžička": "lžička", "čajové lžičky": "lžička", "čajových lžiček": "lžička", "čajovou lžičku": "lžička",
    # Kusy
    "kus": "ks", "kusy": "ks", "kusů": "ks", "kusem": "ks",
    # Ostatní
    "hrstí": "hrst", "hrsti": "hrst",
    "plátky": "plátek", "plátků": "plátek", "plátkem": "plátek",
    "stroužky": "stroužek", "stroužků": "stroužek", "stroužkem": "stroužek",
    "svazky": "svazek", "svazků": "svazek",
    "špetek": "špetka", "špetky": "špetka",
    "kapky": "kapka", "kapek": "kapka",
    "kousky": "kousek", "kousků": "kousek",
    "snítky": "snítka", "snítek": "snítka",
}

# Převodní koeficienty na základní jednotku (g, ml)
UNIT_TO_GRAMS: dict[str, float] = {"g": 1.0, "kg": 1000.0, "mg": 0.001}
UNIT_TO_ML: dict[str, float] = {"ml": 1.0, "l": 1000.0, "dl": 100.0, "cl": 10.0}


def _normalize_name(text: str) -> str:
    """Odstraní diakritiku a převede na malá písmena pro porovnávání jmen."""
    normalized = unicodedata.normalize("NFD", text)
    without_diacritics = "".join(
        c for c in normalized if unicodedata.category(c) != "Mn"
    )
    return without_diacritics.lower().strip()


def _canonical_unit(unit: str | None) -> str | None:
    """Převede jednotku na kanonický tvar (gramů → g)."""
    if unit is None:
        return None
    lower = unit.lower().strip()
    return UNIT_CANONICAL.get(lower, lower)


def _to_base(quantity: float, unit: str) -> tuple[float, str]:
    """Převede množství na základní jednotku (kg→g, l→ml)."""
    if unit in UNIT_TO_GRAMS:
        return quantity * UNIT_TO_GRAMS[unit], "g"
    if unit in UNIT_TO_ML:
        return quantity * UNIT_TO_ML[unit], "ml"
    return quantity, unit


def _format_qty(qty: float | None, unit: str | None) -> str:
    """Formátuje množství s jednotkou pro zobrazení."""
    if qty is None:
        return "dle chuti"
    qty_str = str(int(qty)) if qty == int(qty) else f"{qty:.1f}"
    return f"{qty_str} {unit}" if unit else qty_str


def aggregate_ingredients(
    recipes_ingredients: list[tuple[str, list["ParsedIngredient"]]],
) -> list[AggregatedIngredient]:
    """Agreguje ingredience z více receptů — sčítá společné suroviny.

    Args:
        recipes_ingredients: Seznam dvojic (název_receptu, [ParsedIngredient])

    Returns:
        Seznam AggregatedIngredient — každá ingredience jen jednou,
        s celkovým množstvím a přehledem zdrojů.
    """
    # Klíč: (normalizované jméno, kanonická jednotka nebo skupina)
    # Hodnota: AggregatedIngredient
    aggregated: dict[tuple[str, str], AggregatedIngredient] = {}

    for recipe_name, ingredients in recipes_ingredients:
        for ing in ingredients:
            canonical_unit = _canonical_unit(ing.unit)
            norm_name = _normalize_name(ing.name)

            # Určíme skupinu jednotky pro sčítání (g+kg = "weight", ml+l = "volume")
            if canonical_unit in UNIT_TO_GRAMS:
                unit_group = "weight"
            elif canonical_unit in UNIT_TO_ML:
                unit_group = "volume"
            else:
                unit_group = canonical_unit or "none"

            key = (norm_name, unit_group)

            source_str = f"{recipe_name} ({_format_qty(ing.quantity, canonical_unit)})"

            if key not in aggregated:
                # Převedeme na základní jednotku pro sčítání
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
    """Vypíše agregované ingredience — společné i jedinečné."""
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


def extract_ingredients_from_recipe_text(recipe_text: str) -> list[str]:
    """Extrahuje seznam ingrediencí z textového výstupu Cookidoo MCP.

    Cookidoo get_recipe_details vrací text obsahující sekci "Ingredients:"
    s odrážkami (•). Tato funkce je extrahuje.

    Args:
        recipe_text: Surový text z get_recipe_details

    Returns:
        Seznam ingrediencí jako textové řetězce
    """
    ingredients = []
    in_ingredients_section = False

    for line in recipe_text.split("\n"):
        line = line.strip()

        # Detekce začátku sekce ingrediencí
        if line.lower().startswith("ingredients:"):
            in_ingredients_section = True
            continue

        # Detekce konce sekce (začátek další sekce)
        if in_ingredients_section and line.endswith(":") and not line.startswith("•"):
            break

        # Extrakce ingrediencí z odrážek
        if in_ingredients_section and line.startswith("•"):
            ingredient = line.lstrip("• ").strip()
            # Cookidoo formát: "název - popis(množství+jednotka)" nebo "název"
            # Pozn.: server.py musí používat ingredient.description (ne .quantity)
            if " - " in ingredient:
                name_part, quantity_part = ingredient.rsplit(" - ", 1)
                # Přeformátujeme na "množství název"
                ingredients.append(f"{quantity_part} {name_part}".strip())
            else:
                ingredients.append(ingredient)

    return ingredients
