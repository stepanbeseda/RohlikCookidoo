"""The user's household: what is kept at home, usual products and preferences.

Three files in one data directory:

- pantry.txt: one item per line; blank lines and lines starting with # are
  ignored. A line starting with "?" marks something that is usually at home
  but runs out ("? máslo"): it is not skipped silently, the user is asked
  first.
- products.json: which product the user bought last time for an ingredient.
- preferences.json: free-form shopping preferences ("quality": "bio").

The pantry file is PANTRY_PATH, or pantry.txt in DATA_DIR, or pantry.txt in
the repository root; the JSON files live next to it. `Household.from_env` is
the only place that reads these variables. Every call reads the files afresh,
so hand edits are picked up, and every write replaces a file atomically.
"""

import json
import logging
import os
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from rohlik_cookidoo.text import clean_name, name_key

HAVE = "have"
CHECK = "check"
ASK = "ask"

_ASK_MARKER = "?"
_PANTRY = "pantry.txt"
_PRODUCTS = "products.json"
_PREFERENCES = "preferences.json"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Lookup:
    """What the household knows about one ingredient name."""

    name: str  # the name asked about, unchanged
    pantry_status: str | None  # HAVE, ASK, CHECK or None
    pantry_item: str | None  # the pantry item (without "?") that matched
    usual_product: dict | None  # the stored products.json entry, as stored


def _split_marker(line: str) -> tuple[str, bool]:
    """Split a pantry line into (item, ask first)."""
    line = line.strip()
    if line.startswith(_ASK_MARKER):
        return line[len(_ASK_MARKER):].strip(), True
    return line, False


def _is_item(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _match(name: str, items: list[str]) -> tuple[str | None, str | None]:
    """Compare an ingredient with the pantry lines.

    Returns (status, pantry item):
    - ("have", item): the same thing, in any case form ("másla" vs "máslo")
    - ("ask", item): the same thing, but the pantry line is marked with "?"
    - ("check", item): the pantry has something more general or more specific
      ("sezamový olej" vs "olej"); it may or may not be the right product
    - (None, None): not in the pantry
    """
    key = name_key(name)
    if not key:
        return None, None

    maybe = None
    for line in items:
        item, ask = _split_marker(line)
        item_key = name_key(item)
        if not item_key:
            continue
        if item_key == key:
            return (ASK if ask else HAVE), item
        if maybe is None and (item_key < key or key < item_key):
            maybe = item
    return (CHECK, maybe) if maybe else (None, None)


def _product_key(ingredient: str) -> str:
    """Key shared by all case forms of an ingredient name."""
    return " ".join(sorted(name_key(ingredient)))


def _write_atomic(path: Path, text: str) -> None:
    """Replace `path` with `text` so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Household:
    """The pantry, usual products and preferences of one data directory."""

    def __init__(self, data_dir: Path | str, pantry_file: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.pantry_file = Path(pantry_file) if pantry_file else self.data_dir / _PANTRY
        self.products_file = self.data_dir / _PRODUCTS
        self.preferences_file = self.data_dir / _PREFERENCES

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Household":
        """Find the household's files from PANTRY_PATH or DATA_DIR; an empty value is unset."""
        pantry_file = env.get("PANTRY_PATH")
        if pantry_file:
            return cls(Path(pantry_file).parent, pantry_file)
        data_dir = env.get("DATA_DIR")
        return cls(data_dir if data_dir else Path(__file__).parent.parent)

    # Pantry

    def _lines(self) -> list[str]:
        """The pantry file's lines as written; empty if the file is missing."""
        if not self.pantry_file.exists():
            return []
        return self.pantry_file.read_text(encoding="utf-8").splitlines()

    def pantry(self) -> dict[str, list[str]]:
        """The pantry split into always-at-home items and ask-first items."""
        items = [_split_marker(line) for line in self._lines() if _is_item(line)]
        return {
            "always_at_home": [name for name, ask in items if not ask],
            "ask_first": [name for name, ask in items if ask],
        }

    def update_pantry(
        self,
        always_at_home: Iterable[str] = (),
        ask_first: Iterable[str] = (),
        remove: Iterable[str] = (),
    ) -> dict[str, list[str]]:
        """Remove items, then add or switch the mode of items; returns the whole pantry.

        Comments, blank lines and untouched items keep their text. The file is
        written once, and only when it changed.
        """
        original = self._lines()
        lines = list(original)

        def drop(item: str) -> None:
            key = name_key(_split_marker(item)[0])
            lines[:] = [
                line for line in lines
                if not (_is_item(line) and name_key(_split_marker(line)[0]) == key)
            ]

        def add(item: str, ask: bool) -> None:
            item, marked = _split_marker(item)
            ask = ask or marked
            if not item:
                return
            status, _ = _match(item, [line.strip() for line in lines if _is_item(line)])
            if status == (ASK if ask else HAVE):
                return
            if status in (HAVE, ASK):
                drop(item)
            lines.append(f"{_ASK_MARKER} {item}" if ask else item)

        for item in remove:
            drop(item)
        for item in always_at_home:
            add(item, ask=False)
        for item in ask_first:
            add(item, ask=True)

        if lines != original:
            _write_atomic(self.pantry_file, "".join(f"{line}\n" for line in lines))
        return self.pantry()

    # Questions about ingredients

    def look_up(self, names: Iterable[str]) -> list[Lookup]:
        """Answer, for each name in order, whether it is at home and what the user usually buys."""
        items = [line.strip() for line in self._lines() if _is_item(line)]
        products = self._load_json(self.products_file)
        found = []
        for name in names:
            status, item = _match(name, items)
            found.append(Lookup(name, status, item, products.get(_product_key(name))))
        return found

    # Usual products

    def usual_products(self) -> list[dict]:
        """All remembered products, sorted by ingredient."""
        products = self._load_json(self.products_file)
        return sorted(products.values(), key=lambda entry: entry["ingredient"])

    def remember_products(self, products: Iterable[Mapping[str, Any]]) -> list[dict]:
        """Store the product chosen for each ingredient; returns the stored entries.

        Names without letters are skipped. The file is written once, and only
        when something was stored.
        """
        stored = self._load_json(self.products_file)
        remembered = []
        for product in products:
            key = _product_key(product["ingredient"])
            if not key:
                continue
            entry = {
                "ingredient": clean_name(product["ingredient"]),
                "product_id": product["product_id"],
                "product_name": product["product_name"],
                "package_amount": product.get("package_amount", ""),
                "updated": date.today().isoformat(),
            }
            stored[key] = entry
            remembered.append(entry)
        if remembered:
            self._save_json(self.products_file, stored)
        return remembered

    def forget_product(self, ingredient: str) -> bool:
        """Drop the remembered product for an ingredient. Returns False if none."""
        stored = self._load_json(self.products_file)
        if stored.pop(_product_key(ingredient), None) is None:
            return False
        self._save_json(self.products_file, stored)
        return True

    # Preferences

    def preferences(self) -> dict[str, str]:
        """The stored shopping preferences."""
        return {str(k): str(v) for k, v in self._load_json(self.preferences_file).items()}

    def set_preference(self, key: str, value: str) -> dict[str, str]:
        """Store a preference; an empty value removes it. Returns all preferences."""
        key, value = key.strip(), value.strip()
        preferences = self.preferences()
        if not key:
            return preferences
        if value:
            preferences[key] = value
        else:
            preferences.pop(key, None)
        self._save_json(self.preferences_file, preferences)
        return preferences

    # Files

    @staticmethod
    def _load_json(file: Path) -> dict:
        """The JSON object in `file`; empty if missing, or unreadable (with a warning)."""
        if not file.exists():
            return {}
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = None
        if not isinstance(data, dict):
            logger.warning("%s is not a JSON object; treating it as empty", file.name)
            return {}
        return data

    @staticmethod
    def _save_json(file: Path, data: dict) -> None:
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        _write_atomic(file, text)
