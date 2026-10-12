"""Parsing and aggregation of recipe ingredients.

Turns an ingredient (a name plus a quantity such as "250 gramů" or
"1 vrchovatá čajová lžička") into structured data, and sums the same
ingredient across recipes.
"""

import re
from dataclasses import dataclass, field

from rohlik_cookidoo.text import clean_name, name_key, normalize, stem


@dataclass
class ParsedIngredient:
    """A single parsed recipe ingredient."""
    original: str           # Text as received: "200 g hladká mouka"
    name: str               # Ingredient name: "hladká mouka"
    quantity: float | None  # Amount: 200.0
    unit: str | None        # Canonical unit: "g"
    search_term: str        # Name without notes: "hladká mouka"


@dataclass
class AggregatedIngredient:
    """An ingredient summed across recipes."""
    name: str
    total_quantity: float | None
    unit: str | None
    sources: list[str] = field(default_factory=list)  # ["Palačinky (200 g)", ...]
    search_term: str = ""
    # True when some recipe lists it without an amount ("sůl podle chuti")
    unspecified_amount: bool = False


# Canonical unit -> accepted forms (compared without diacritics, lowercase)
_UNIT_FORMS: dict[str, tuple[str, ...]] = {
    "g": ("g", "gram", "gramu", "gramy"),
    "kg": ("kg", "kilogram", "kilogramu", "kilogramy", "kilo", "kila"),
    "mg": ("mg",),
    "ml": ("ml", "mililitr", "mililitru", "mililitry"),
    "l": ("l", "litr", "litru", "litry"),
    "dl": ("dl", "decilitr", "decilitru", "decilitry"),
    "cl": ("cl",),
    "lžíce": ("lzice", "lzici", "lzic", "pl",
              "polevkova lzice", "polevkove lzice", "polevkovych lzic", "polevkovou lzici"),
    "lžička": ("lzicka", "lzicky", "lzicek", "lzicku",
               "cajova lzicka", "cajove lzicky", "cajovych lzicek", "cajovou lzicku"),
    "ks": ("ks", "kus", "kusy", "kusu", "kusem"),
    "hrst": ("hrst", "hrsti"),
    "balení": ("baleni", "bal", "balicek", "balicky", "balicku"),
    "plátek": ("platek", "platky", "platku", "platkem"),
    "stroužek": ("strouzek", "strouzky", "strouzku", "strouzkem"),
    "svazek": ("svazek", "svazky", "svazku"),
    "špetka": ("spetka", "spetek", "spetky", "spetku"),
    "kapka": ("kapka", "kapky", "kapek"),
    "kousek": ("kousek", "kousky", "kousku"),
    "snítka": ("snitka", "snitky", "snitek"),
    "plechovka": ("plechovka", "plechovky", "plechovek", "konzerva", "konzervy", "konzerv"),
    "kelímek": ("kelimek", "kelimky", "kelimku"),
    "hrnek": ("hrnek", "hrnky", "hrnku", "salek", "salky", "salku"),
    "kostka": ("kostka", "kostky", "kostek"),
    "sáček": ("sacek", "sacky", "sacku"),
    "list": ("list", "listy", "listu"),
}
_UNIT_LOOKUP = {form: unit for unit, forms in _UNIT_FORMS.items() for form in forms}

# "1 vrchovatá čajová lžička": words allowed between the number and the unit
_UNIT_QUALIFIER_STEMS = frozenset(
    stem(word) for word in ("vrchovatá", "zarovnaná", "malá", "velká", "menší", "větší", "plná")
)

_TO_GRAMS = {"g": 1.0, "kg": 1000.0, "mg": 0.001}
_TO_ML = {"ml": 1.0, "l": 1000.0, "dl": 100.0, "cl": 10.0}

_UNICODE_FRACTIONS = {"½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4"}

_NUM = r"\d+(?:[.,]\d+)?"
_MIXED = re.compile(r"^(\d+)\s+(\d+)\s*/\s*(\d+)")
_FRACTION = re.compile(r"^(\d+)\s*/\s*(\d+)")
_RANGE = re.compile(rf"^({_NUM})\s*[-–—]\s*({_NUM})")
_SINGLE = re.compile(rf"^({_NUM})")
_THOUSANDS = re.compile(r"^[1-9]\d{0,2}\.\d{3}$")


def _to_float(text: str) -> float:
    """Convert "200", "1.5", "1,5" or "1.000" (thousands) to a float."""
    if _THOUSANDS.match(text):
        text = text.replace(".", "")
    return float(text.replace(",", "."))


def _split_amount(text: str) -> tuple[float | None, str]:
    """Split a leading amount off the text. Ranges give their upper bound."""
    for symbol, fraction in _UNICODE_FRACTIONS.items():
        text = re.sub(rf"(\d)\s*{symbol}", rf"\1 {fraction}", text).replace(symbol, fraction)
    text = text.strip()

    if m := _MIXED.match(text):
        return int(m[1]) + int(m[2]) / int(m[3]), text[m.end():]
    if m := _FRACTION.match(text):
        return int(m[1]) / int(m[2]), text[m.end():]
    if m := _RANGE.match(text):
        return max(_to_float(m[1]), _to_float(m[2])), text[m.end():]
    if m := _SINGLE.match(text):
        return _to_float(m[1]), text[m.end():]
    return None, text


def _split_unit(text: str) -> tuple[str | None, str]:
    """Split a leading unit off the text, skipping qualifiers like "vrchovatá"."""
    words = text.split()
    start = 0
    while start < len(words) and stem(words[start]) in _UNIT_QUALIFIER_STEMS:
        start += 1

    for length in (2, 1):
        candidate = words[start:start + length]
        if len(candidate) < length:
            continue
        raw = " ".join(candidate).rstrip(".")
        # "ČL" is a teaspoon, "cl" a centilitre; they differ only by the háček
        unit = "lžička" if raw.lower() == "čl" else _UNIT_LOOKUP.get(normalize(raw))
        if unit:
            return unit, " ".join(words[start + length:])
    return None, text.strip()


def parse_quantity(text: str) -> tuple[float | None, str | None, str]:
    """Parse "250 gramů", "1-2 lžíce", "½ lžičky", "200g mouky".

    Returns (amount, canonical unit, remaining text). The amount is None when
    the text does not start with a number; the unit is None for plain counts.
    """
    amount, rest = _split_amount(text)
    if amount is None:
        return None, None, text.strip()
    unit, rest = _split_unit(rest)
    return amount, unit, rest


def parse_ingredient(name: str, quantity: str = "") -> ParsedIngredient:
    """Parse an ingredient given as a name and an optional quantity text.

    Without a quantity, the amount is read from the start of the name
    ("200 g hladká mouka"), which covers free-text recipes.
    """
    name = name.strip()
    quantity = quantity.strip()
    original = f"{quantity} {name}".strip()

    if quantity:
        amount, unit, _ = parse_quantity(quantity)
        if amount is not None and unit is None:
            # Cookidoo sometimes keeps the unit in the name: "2" + "stroužek česneku"
            name_unit, rest = _split_unit(name)
            if name_unit and rest:
                unit, name = name_unit, rest
    else:
        amount, unit, rest = parse_quantity(name)
        if amount is not None and rest:
            name = rest

    return ParsedIngredient(
        original=original,
        name=name,
        quantity=amount,
        unit=unit,
        search_term=clean_name(name),
    )


def parse_single_ingredient(text: str) -> ParsedIngredient:
    """Parse one free-text ingredient line, e.g. "200 g hladká mouka"."""
    return parse_ingredient(text)


def parse_ingredients(raw_ingredients: list[str]) -> list[ParsedIngredient]:
    """Parse free-text ingredient lines, skipping blank ones."""
    return [parse_ingredient(text) for text in raw_ingredients if text.strip()]


def parse_recipe_ingredients(recipe: dict) -> list[ParsedIngredient]:
    """Parse the ingredients of a recipe from the Cookidoo MCP server.

    Each ingredient is {"name": ..., "quantity": ...}.
    """
    return [
        parse_ingredient(ingredient["name"], ingredient.get("quantity") or "")
        for ingredient in recipe.get("ingredients", [])
        if ingredient.get("name", "").strip()
    ]


def scale_ingredients(
    ingredients: list[ParsedIngredient], factor: float
) -> list[ParsedIngredient]:
    """Multiply all amounts, e.g. by target servings / recipe servings."""
    return [
        ParsedIngredient(
            original=i.original,
            name=i.name,
            quantity=None if i.quantity is None else i.quantity * factor,
            unit=i.unit,
            search_term=i.search_term,
        )
        for i in ingredients
    ]


def to_base_unit(quantity: float, unit: str | None) -> tuple[float, str, str]:
    """Convert to a base unit and name its group.

    Returns (quantity, unit, group) where the group is "weight" (g),
    "volume" (ml), "count" (ks) or the unit itself for spoons, cloves etc.
    """
    if unit in _TO_GRAMS:
        return quantity * _TO_GRAMS[unit], "g", "weight"
    if unit in _TO_ML:
        return quantity * _TO_ML[unit], "ml", "volume"
    if unit is None or unit == "ks":
        return quantity, "ks", "count"
    return quantity, unit, unit


def format_quantity(quantity: float | None, unit: str | None) -> str:
    """Format an amount with its unit for display."""
    if quantity is None:
        return "dle chuti"
    text = str(int(quantity)) if quantity == int(quantity) else f"{quantity:.1f}"
    return f"{text} {unit}" if unit else text


def aggregate_ingredients(
    recipes_ingredients: list[tuple[str, list[ParsedIngredient]]],
) -> list[AggregatedIngredient]:
    """Sum ingredients across recipes.

    Args:
        recipes_ingredients: List of (recipe_name, [ParsedIngredient]) pairs

    Returns:
        One AggregatedIngredient per ingredient and unit group. Case forms and
        word order do not matter ("másla" + "máslo"), g/kg and ml/l are
        converted, plain counts and "ks" are the same thing. Amounts in
        different groups (grams and spoons) stay separate.
    """
    # An ingredient without an amount joins whatever entry already exists for it
    by_name: dict[frozenset[str], list[AggregatedIngredient]] = {}
    by_group: dict[tuple[frozenset[str], str], AggregatedIngredient] = {}
    result: list[AggregatedIngredient] = []

    for recipe_name, ingredients in recipes_ingredients:
        for ing in ingredients:
            key = name_key(ing.name) or frozenset({normalize(ing.name)})

            if ing.quantity is None:
                source = f"{recipe_name} ({format_quantity(None, None)})"
                if by_name.get(key):
                    entry = by_name[key][0]
                    entry.sources.append(source)
                    entry.unspecified_amount = True
                    continue
                quantity, unit, group = None, None, "unspecified"
            else:
                quantity, unit, group = to_base_unit(ing.quantity, ing.unit)
                source = f"{recipe_name} ({format_quantity(ing.quantity, ing.unit)})"

            entry = by_group.get((key, group))
            if entry is None and quantity is not None:
                # Adopt an entry that so far has no amount
                entry = by_group.pop((key, "unspecified"), None)
                if entry is not None:
                    entry.total_quantity, entry.unit = 0.0, unit
                    by_group[(key, group)] = entry

            if entry is None:
                entry = AggregatedIngredient(
                    name=clean_name(ing.name),
                    total_quantity=quantity,
                    unit=unit,
                    sources=[source],
                    search_term=ing.search_term,
                    unspecified_amount=quantity is None,
                )
                by_group[(key, group)] = entry
                by_name.setdefault(key, []).append(entry)
                result.append(entry)
            else:
                entry.sources.append(source)
                entry.total_quantity += quantity

    return result


def display_aggregated_ingredients(aggregated: list[AggregatedIngredient]) -> None:
    """Print aggregated ingredients, shared ones first."""
    shared = [a for a in aggregated if len(a.sources) > 1]
    unique = [a for a in aggregated if len(a.sources) == 1]

    if shared:
        print("\n=== Společné ingredience (z více receptů) ===")
        for a in shared:
            print(f"  {a.name}: {format_quantity(a.total_quantity, a.unit)}  [{', '.join(a.sources)}]")

    print("\n=== Jedinečné ingredience ===")
    for a in unique:
        print(f"  {a.name}: {format_quantity(a.total_quantity, a.unit)}  [{a.sources[0]}]")

    print(f"\nCelkem: {len(aggregated)} ingrediencí ({len(shared)} společných)")
