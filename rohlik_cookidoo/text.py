"""Ingredient identity: whether two ingredient names mean the same ingredient.

Cookidoo returns ingredients in the genitive ("másla", "soli", "žampiónů"),
while pantry files and people use the nominative ("máslo", "sůl", "žampióny").
`identity` turns a name into an `Identity` that ignores case forms, word order,
notes and preparation words, and `Identity.relation` tells the same ingredient
from a broader or narrower one. Summing, the pantry and usual products all ask
this module. `stem` is a light suffix stripper, not a lemmatizer: its results
are only for comparison, never shown to the user.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

# Longest first; a suffix is stripped only when at least 3 characters remain
_SUFFIXES = (
    "eho", "emu", "ymi", "imi", "ami", "emi", "ych", "ich", "iho", "imu",
    "ech", "ach", "ete", "eti", "ata", "ovi",
    "ou", "ym", "im", "em", "um",
    "u", "a", "y", "e", "i", "o",
)

# Forms the suffix rules cannot bring together
_IRREGULAR = {"sul": "sol", "vajec": "vejc", "rajcat": "rajc"}

# "česnek" / "česneku", "ocet" / "octa", "okurek" / "okurka": drop the fleeting e
_FLEETING_E = re.compile(r"^(.*[^aeiouy])e([kcvtnlr])$")

_WORD = re.compile(r"[^\W\d_]+")

# Words that describe preparation or size, not the product itself
_IGNORED_WORDS = (
    "mletý", "čerstvý", "sušený", "drcený", "strouhaný", "nastrouhaný",
    "nakrájený", "nasekaný", "změklý", "studený", "vlažný", "teplý", "celý",
    "velký", "malý", "střední", "větší", "menší", "jemně", "nahrubo", "najemno",
    "na", "do", "k", "a", "nebo", "podle", "dle", "chuti", "případně", "cca",
)


def normalize(text: str) -> str:
    """Strip diacritics and lowercase the text."""
    decomposed = unicodedata.normalize("NFD", text)
    without_diacritics = "".join(
        c for c in decomposed if unicodedata.category(c) != "Mn"
    )
    return without_diacritics.lower().strip()


def stem(word: str) -> str:
    """Reduce a Czech word to a comparison key shared by its common case forms."""
    word = normalize(word)
    if word in _IRREGULAR:
        return _IRREGULAR[word]
    if len(word) > 3:
        for suffix in _SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                word = word[: -len(suffix)]
                break
    if len(word) >= 4:
        match = _FLEETING_E.match(word)
        if match:
            word = match.group(1) + match.group(2)
    return _IRREGULAR.get(word, word)


_IGNORED_STEMS = frozenset(stem(word) for word in _IGNORED_WORDS)


def clean_name(name: str) -> str:
    """Drop the part after a comma and anything in parentheses.

    "másla, změklého" -> "másla", "mléko (plnotučné)" -> "mléko",
    "pepř podle chuti" -> "pepř"
    """
    name = re.sub(r"\(.*?\)", "", name)
    name = re.sub(r"\s+(?:po)?dle chuti\s*$", "", name.split(",")[0], flags=re.IGNORECASE)
    return name.strip()


class Relation(Enum):
    """How one ingredient name relates to another."""

    SAME = "same"  # "másla" and "máslo"
    BROADER = "broader"  # the other is more general: "olej" for "sezamový olej"
    NARROWER = "narrower"  # the other is more specific: "hladká mouka" for "mouka"
    UNRELATED = "unrelated"


@dataclass(frozen=True)
class Identity:
    """What makes two ingredient names the same ingredient.

    Use it as a dict key and through `relation`; callers never build or read
    the tokens. An empty identity (nothing left of the name after cleaning) is
    related to nothing.
    """

    tokens: frozenset[str]

    def __bool__(self) -> bool:
        return bool(self.tokens)

    def __str__(self) -> str:
        """The tokens as one sorted, space-separated string (the products.json key)."""
        return " ".join(sorted(self.tokens))

    def relation(self, other: "Identity") -> Relation:
        """How `other` relates to this ingredient."""
        if not self.tokens or not other.tokens:
            return Relation.UNRELATED
        if other.tokens == self.tokens:
            return Relation.SAME
        if other.tokens < self.tokens:
            return Relation.BROADER
        if self.tokens < other.tokens:
            return Relation.NARROWER
        return Relation.UNRELATED


def identity(name: str) -> Identity:
    """Return the identity of an ingredient name.

    Word order, case forms, notes after a comma or in parentheses and
    preparation words do not matter: "hladké mouky", "Mouka hladká, prosátá"
    and "hladká mouka" are one ingredient. A name made only of preparation
    words ("čerstvý") is identified by those words; a name without letters
    ("123") by its text.
    """
    name = clean_name(name)
    stems = {stem(word) for word in _WORD.findall(name)}
    tokens = stems - _IGNORED_STEMS or stems
    if not tokens:
        text = normalize(name)
        tokens = {text} if text else set()
    return Identity(frozenset(tokens))
