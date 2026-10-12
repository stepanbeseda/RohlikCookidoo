"""The home pantry: ingredients the user keeps at home and does not buy.

The pantry is a text file with one item per line; blank lines and lines
starting with # are ignored. A line starting with "?" marks something that is
usually at home but runs out ("? máslo"): it is not skipped silently, the user
is asked first.

The file is PANTRY_PATH, or pantry.txt in DATA_DIR, or pantry.txt in the
repository root. The memory files are kept in the same directory.
"""

import os
from pathlib import Path

from rohlik_cookidoo.text import name_key

HAVE = "have"
CHECK = "check"
ASK = "ask"

_ASK_MARKER = "?"


def pantry_path(path: str | None = None) -> Path:
    """Return the pantry file location."""
    if path or os.getenv("PANTRY_PATH"):
        return Path(path or os.environ["PANTRY_PATH"])
    data_dir = os.getenv("DATA_DIR")
    return Path(data_dir) / "pantry.txt" if data_dir else Path(__file__).parent.parent / "pantry.txt"


def read_pantry_lines(path: str | None = None) -> list[str]:
    """Return the pantry items as written; an empty list if the file is missing."""
    file = pantry_path(path)
    if not file.exists():
        return []
    lines = [line.strip() for line in file.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def split_marker(line: str) -> tuple[str, bool]:
    """Split a pantry line into (item, ask first)."""
    line = line.strip()
    if line.startswith(_ASK_MARKER):
        return line[len(_ASK_MARKER):].strip(), True
    return line, False


def match_pantry(name: str, pantry_items: list[str]) -> tuple[str | None, str | None]:
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
    for line in pantry_items:
        item, ask = split_marker(line)
        item_key = name_key(item)
        if not item_key:
            continue
        if item_key == key:
            return (ASK if ask else HAVE), item
        if maybe is None and (item_key < key or key < item_key):
            maybe = item
    return (CHECK, maybe) if maybe else (None, None)


def add_pantry_item(item: str, path: str | None = None, ask: bool = False) -> bool:
    """Add an item to the pantry file, or change whether it is asked about first.

    Returns False if the file already has it in the same form.
    """
    item, marked = split_marker(item)
    ask = ask or marked
    if not item:
        return False
    line = f"{_ASK_MARKER} {item}" if ask else item

    status, _ = match_pantry(item, read_pantry_lines(path))
    if status == (ASK if ask else HAVE):
        return False
    if status in (HAVE, ASK):
        remove_pantry_item(item, path)

    file = pantry_path(path)
    existing = file.read_text(encoding="utf-8") if file.exists() else ""
    separator = "" if not existing or existing.endswith("\n") else "\n"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(f"{existing}{separator}{line}\n", encoding="utf-8")
    return True


def remove_pantry_item(item: str, path: str | None = None) -> bool:
    """Remove an item from the pantry file, keeping comments. Returns False if absent."""
    file = pantry_path(path)
    if not file.exists():
        return False
    key = name_key(split_marker(item)[0])
    kept, removed = [], False
    for line in file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        is_item = stripped and not stripped.startswith("#")
        if is_item and name_key(split_marker(stripped)[0]) == key:
            removed = True
        else:
            kept.append(line)
    if removed:
        file.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")
    return removed
