"""Czech-aware text helpers for comparing ingredient names.

Cookidoo returns ingredients in the genitive ("másla", "soli", "žampiónů"),
while pantry files and people use the nominative ("máslo", "sůl", "žampióny").
`stem` reduces both to the same key. It is a light suffix stripper, not a
lemmatizer: the result is only meant for comparison, never for display.
"""

import re
import unicodedata

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


def name_key(name: str) -> frozenset[str]:
    """Return the set of word stems that identifies an ingredient.

    Word order, case forms and preparation words do not matter:
    "hladké mouky", "mouka hladká" and "Hladká mouka, prosátá" share one key.
    """
    stems = {stem(word) for word in _WORD.findall(clean_name(name))}
    return frozenset(stems - _IGNORED_STEMS)
