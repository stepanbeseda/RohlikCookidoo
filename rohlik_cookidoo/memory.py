"""Small JSON files that remember the user's shopping habits.

- products.json: which product the user bought last time for an ingredient
- preferences.json: free-form shopping preferences ("quality": "bio")

Both live next to the pantry file, so they follow PANTRY_PATH.
"""

import json
from datetime import date
from pathlib import Path

from rohlik_cookidoo.pantry import pantry_path
from rohlik_cookidoo.text import clean_name, name_key

_PRODUCTS = "products.json"
_PREFERENCES = "preferences.json"


def _file(name: str) -> Path:
    return pantry_path().parent / name


def _load(name: str) -> dict:
    file = _file(name)
    if not file.exists():
        return {}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _save(name: str, data: dict) -> None:
    file = _file(name)
    file.parent.mkdir(parents=True, exist_ok=True)
    temporary = file.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(file)


def _product_key(ingredient: str) -> str:
    """Key shared by all case forms of an ingredient name."""
    return " ".join(sorted(name_key(ingredient)))


def remember_product(
    ingredient: str, product_id: int | str, product_name: str, package_amount: str = ""
) -> dict | None:
    """Store the product chosen for an ingredient. Returns the stored entry."""
    key = _product_key(ingredient)
    if not key:
        return None
    entry = {
        "ingredient": clean_name(ingredient),
        "product_id": product_id,
        "product_name": product_name,
        "package_amount": package_amount,
        "updated": date.today().isoformat(),
    }
    products = _load(_PRODUCTS)
    products[key] = entry
    _save(_PRODUCTS, products)
    return entry


def recall_product(ingredient: str) -> dict | None:
    """Return the product remembered for an ingredient, in any case form."""
    return _load(_PRODUCTS).get(_product_key(ingredient))


def forget_product(ingredient: str) -> bool:
    """Drop the remembered product for an ingredient. Returns False if none."""
    products = _load(_PRODUCTS)
    if products.pop(_product_key(ingredient), None) is None:
        return False
    _save(_PRODUCTS, products)
    return True


def list_products() -> list[dict]:
    """Return all remembered products, sorted by ingredient."""
    return sorted(_load(_PRODUCTS).values(), key=lambda entry: entry["ingredient"])


def get_preferences() -> dict[str, str]:
    """Return the stored shopping preferences."""
    return {str(k): str(v) for k, v in _load(_PREFERENCES).items()}


def set_preference(key: str, value: str) -> dict[str, str]:
    """Store a preference; an empty value removes it. Returns all preferences."""
    key, value = key.strip(), value.strip()
    preferences = get_preferences()
    if not key:
        return preferences
    if value:
        preferences[key] = value
    else:
        preferences.pop(key, None)
    _save(_PREFERENCES, preferences)
    return preferences
