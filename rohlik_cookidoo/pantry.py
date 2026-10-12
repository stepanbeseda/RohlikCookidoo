"""The home pantry: ingredients the user keeps at home and does not buy.

The pantry is a text file with one item per line; blank lines and lines
starting with # are ignored. Its location is PANTRY_PATH, or pantry.txt in
the repository root.
"""

import os
from pathlib import Path

from rohlik_cookidoo.text import name_key

HAVE = "have"
CHECK = "check"


def pantry_path(path: str | None = None) -> Path:
    """Return the pantry file location."""
    return Path(
        path or os.getenv("PANTRY_PATH") or Path(__file__).parent.parent / "pantry.txt"
    )


def read_pantry_lines(path: str | None = None) -> list[str]:
    """Return the pantry items as written; an empty list if the file is missing."""
    file = pantry_path(path)
    if not file.exists():
        return []
    lines = [line.strip() for line in file.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def match_pantry(name: str, pantry_items: list[str]) -> tuple[str | None, str | None]:
    """Compare an ingredient with the pantry.

    Returns (status, pantry item):
    - ("have", item): the same thing, in any case form ("másla" vs "máslo")
    - ("check", item): the pantry has something more general or more specific
      ("sezamový olej" vs "olej"); it may or may not be the right product
    - (None, None): not in the pantry
    """
    key = name_key(name)
    if not key:
        return None, None

    maybe = None
    for item in pantry_items:
        item_key = name_key(item)
        if not item_key:
            continue
        if item_key == key:
            return HAVE, item
        if maybe is None and (item_key < key or key < item_key):
            maybe = item
    return (CHECK, maybe) if maybe else (None, None)


def add_pantry_item(item: str, path: str | None = None) -> bool:
    """Append an item to the pantry file. Returns False if it is already there."""
    item = item.strip()
    if not item or match_pantry(item, read_pantry_lines(path))[0] == HAVE:
        return False
    file = pantry_path(path)
    existing = file.read_text(encoding="utf-8") if file.exists() else ""
    separator = "" if not existing or existing.endswith("\n") else "\n"
    file.write_text(f"{existing}{separator}{item}\n", encoding="utf-8")
    return True


def remove_pantry_item(item: str, path: str | None = None) -> bool:
    """Remove an item from the pantry file, keeping comments. Returns False if absent."""
    file = pantry_path(path)
    if not file.exists():
        return False
    key = name_key(item)
    kept, removed = [], False
    for line in file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and name_key(stripped) == key:
            removed = True
        else:
            kept.append(line)
    if removed:
        file.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return removed
