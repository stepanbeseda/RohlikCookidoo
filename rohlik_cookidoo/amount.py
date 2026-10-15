"""Amounts as recipes and the shop write them: numbers, units and unit groups.

One number parser (decimal comma, thousands dot, fractions, ranges) and one unit table
serve recipe quantities ("250 gramů", "1 vrchovatá čajová lžička") and package sizes
("4 x 125 g", "cca 0,85 kg", "2 kusy"). An `Amount` converts to its base unit, adds up
within its unit group, measures itself against a package size and formats itself. The
only estimate across groups, 1 g = 1 ml, lives here.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from rohlik_cookidoo.text import normalize, stem

# Unit groups. Units that do not convert (spoons, cloves) are a group of their own,
# named by the unit itself.
WEIGHT = "weight"
VOLUME = "volume"
COUNT = "count"

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

# Units that convert: unit -> (group, base unit, factor to the base unit)
_TO_BASE: dict[str, tuple[str, str, float]] = {
    "mg": (WEIGHT, "g", 0.001),
    "g": (WEIGHT, "g", 1.0),
    "kg": (WEIGHT, "g", 1000.0),
    "ml": (VOLUME, "ml", 1.0),
    "cl": (VOLUME, "ml", 10.0),
    "dl": (VOLUME, "ml", 100.0),
    "l": (VOLUME, "ml", 1000.0),
    "ks": (COUNT, "ks", 1.0),
}

# "1 vrchovatá čajová lžička": words allowed between the number and the unit
_UNIT_QUALIFIER_STEMS = frozenset(
    stem(word) for word in ("vrchovatá", "zarovnaná", "malá", "velká", "menší", "větší", "plná")
)

_UNICODE_FRACTIONS = {"½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4"}

_NUM = r"\d+(?:[.,]\d+)?"
_MIXED = re.compile(r"^(\d+)\s+(\d+)\s*/\s*(\d+)")
_FRACTION = re.compile(r"^(\d+)\s*/\s*(\d+)")
_RANGE = re.compile(rf"^({_NUM})\s*[-–—]\s*({_NUM})")
_SINGLE = re.compile(rf"^({_NUM})")
_THOUSANDS = re.compile(r"^[1-9]\d{0,2}\.\d{3}$")

# Package sizes: a number not inside another number, an optional "4 x" before it, and the
# words right after it ("500 g/ks" -> "g"; "1,5 % 1 l" does not read "%" as a unit)
_NUMBER_START = re.compile(r"(?<![\d.,/])\d")
_MULTIPLIER = re.compile(r"(\d+)\s*[x×]\s*(?=\d)")
_LEADING_WORDS = re.compile(r"\s*([^\W\d_]+(?:\s+[^\W\d_]+)*)")

# Package sizes are rounded to this many decimals: "2,01 kg" is 2010 g, not 2009.9999999999998
_DECIMALS = 6

_GRAMS_AS_MILLILITRES = "assumed 1 g = 1 ml"


@dataclass(frozen=True)
class Amount:
    """A number with a canonical unit ("g", "lžíce"); no unit is a plain count."""
    value: float
    unit: str | None = None

    @property
    def group(self) -> str:
        """WEIGHT, VOLUME, COUNT, or the unit itself for units that do not convert."""
        if self.unit is None:
            return COUNT
        return _TO_BASE[self.unit][0] if self.unit in _TO_BASE else self.unit

    def base(self) -> "Amount":
        """The amount in g, ml or ks; units that do not convert stay as they are."""
        if self.unit is None:
            return Amount(self.value, "ks")
        if self.unit not in _TO_BASE:
            return self
        _, base_unit, factor = _TO_BASE[self.unit]
        return Amount(self.value * factor, base_unit)

    def in_units_of(self, size: "Amount") -> tuple[float, str] | None:
        """This amount in the base unit of `size`, with a note when it is an estimate.

        The note is empty within one group and "assumed 1 g = 1 ml" between weight and
        volume (fine for water and milk, off for oil, honey or flour). None when the two
        cannot be compared (pieces against grams, spoons against millilitres).
        """
        mine, theirs = self.base(), size.base()
        if mine.group == theirs.group:
            return mine.value, ""
        if {mine.group, theirs.group} == {WEIGHT, VOLUME}:
            return mine.value, _GRAMS_AS_MILLILITRES
        return None

    def __str__(self) -> str:
        return format_quantity(self.value, self.unit)


def parse_amount(text: str) -> tuple[Amount | None, str]:
    """Split a leading amount off the text: "250 gramů", "1-2 lžíce", "½ lžičky", "200g mouky".

    Returns the amount and the remaining text. Ranges give their upper bound; a dot before
    exactly three digits is a thousands separator ("1.000 g"). The amount is None when the
    text does not start with a number; its unit is None for a plain count.
    """
    value, rest = _split_number(text)
    if value is None:
        return None, text.strip()
    unit, rest = split_unit(rest)
    return Amount(value, unit), rest


def split_unit(text: str) -> tuple[str | None, str]:
    """Split a leading unit word off the text, skipping qualifiers like "vrchovatá".

    Returns the canonical unit (or None) and the remaining text: "stroužky česneku" ->
    ("stroužek", "česneku").
    """
    words = text.split()
    start = 0
    while start < len(words) and stem(words[start]) in _UNIT_QUALIFIER_STEMS:
        start += 1

    for length in (2, 1):
        candidate = words[start:start + length]
        if len(candidate) < length:
            continue
        unit = _unit_word(" ".join(candidate))
        if unit:
            return unit, " ".join(words[start + length:])
    return None, text.strip()


def canonical_unit(text: str | None) -> str | None:
    """The canonical form of a unit given on its own: "gramů" -> "g", "kusy" -> "ks".

    None or a blank text is no unit (a plain count); an unknown word is kept as given, so it
    stays a group of its own.
    """
    text = (text or "").strip()
    if not text:
        return None
    unit, rest = split_unit(text)
    return unit if unit and not rest else text


def parse_package(text: str) -> Amount | None:
    """Read a package size as the shop writes it, in its base unit.

    "500 g", "cca 0,85 kg", "4 x 125 g" (500 g), "6×0,5 l" (3000 ml), "2 kusy", "1 litr".
    The first number followed by a unit counts; None when there is none or the size is zero.
    The size is rounded to 6 decimals, so sizes written differently compare equal.
    """
    text = text or ""
    for start in _NUMBER_START.finditer(text):
        position, count = start.start(), 1
        if multiplier := _MULTIPLIER.match(text, position):
            position, count = multiplier.end(), int(multiplier[1])
        value, rest = _split_number(text[position:])
        words = _LEADING_WORDS.match(rest)
        unit = split_unit(words[1])[0] if words else None
        if value and unit:
            base = Amount(value, unit).base()
            return Amount(round(base.value * count, _DECIMALS), base.unit)
    return None


def total(amounts: Iterable[Amount]) -> Amount | None:
    """Add amounts of one unit group in their base unit; None when empty or mixed."""
    bases = [amount.base() for amount in amounts]
    if not bases or len({amount.group for amount in bases}) > 1:
        return None
    return Amount(sum(amount.value for amount in bases), bases[0].unit)


def format_quantity(quantity: float | None, unit: str | None) -> str:
    """Format an amount with its unit for display; no amount is "dle chuti"."""
    if quantity is None:
        return "dle chuti"
    text = f"{quantity:.2f}".rstrip("0").rstrip(".")
    return f"{text} {unit}" if unit else text


def _unit_word(raw: str) -> str | None:
    """The canonical unit for one or two words, or None."""
    raw = raw.rstrip(".")
    # "ČL" is a teaspoon, "cl" a centilitre; they differ only by the háček
    return "lžička" if raw.lower() == "čl" else _UNIT_LOOKUP.get(normalize(raw))


def _split_number(text: str) -> tuple[float | None, str]:
    """Split a leading number off the text. Ranges give their upper bound."""
    for symbol, fraction in _UNICODE_FRACTIONS.items():
        text = re.sub(rf"(\d)\s*{symbol}", rf"\1 {fraction}", text).replace(symbol, fraction)
    text = text.strip()

    # "1/0" is not a number, whatever follows
    if (m := _MIXED.match(text) or _FRACTION.match(text)) and int(m[m.lastindex]) == 0:
        return None, text
    if m := _MIXED.match(text):
        return int(m[1]) + int(m[2]) / int(m[3]), text[m.end():]
    if m := _FRACTION.match(text):
        return int(m[1]) / int(m[2]), text[m.end():]
    if m := _RANGE.match(text):
        return max(_to_float(m[1]), _to_float(m[2])), text[m.end():]
    if m := _SINGLE.match(text):
        return _to_float(m[1]), text[m.end():]
    return None, text


def _to_float(text: str) -> float:
    """Convert "200", "1.5", "1,5" or "1.000" (thousands) to a float."""
    if _THOUSANDS.match(text):
        text = text.replace(".", "")
    return float(text.replace(",", "."))
