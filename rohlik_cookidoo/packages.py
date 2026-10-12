"""How many packages of a product cover a required amount."""

import math
import re

from rohlik_cookidoo.ingredients import to_base_unit

_NUM = r"\d+(?:[.,]\d+)?"
# "500 g", "1,98 l", "cca 130 g", "4 x 125 g", "6×0,5 l", "10 ks"
_PACKAGE = re.compile(
    rf"(?:(\d+)\s*[x×]\s*)?({_NUM})\s*(kg|mg|g|ml|dl|cl|l|ks)\b", re.IGNORECASE
)


def parse_package_amount(text: str) -> tuple[float, str] | None:
    """Parse a product's package size into (amount, group).

    The group is "weight" (grams), "volume" (millilitres) or "count" (pieces).
    Returns None when the text has no recognisable size.
    """
    match = _PACKAGE.search(text or "")
    if not match:
        return None
    multiplier = int(match[1]) if match[1] else 1
    amount = float(match[2].replace(",", "."))
    base, _, group = to_base_unit(amount, match[3].lower())
    return multiplier * base, group


def packages_needed(
    quantity: float | None, unit: str | None, package_amount: str
) -> dict:
    """Estimate how many packages cover the required quantity.

    Returns {"packages": int, "exact": bool, "note": str}. `exact` is False
    when the result is a fallback of one package or relies on treating
    1 g as 1 ml (fine for water and milk, off for oil, honey or flour).
    """
    if quantity is None:
        return {"packages": 1, "exact": False, "note": "recipe gives no amount"}

    package = parse_package_amount(package_amount)
    if package is None:
        return {"packages": 1, "exact": False, "note": "package size not recognised"}

    package_base, package_group = package
    needed_base, _, needed_group = to_base_unit(quantity, unit)
    packages = max(1, math.ceil(needed_base / package_base - 1e-9))

    if needed_group == package_group:
        return {"packages": packages, "exact": True, "note": ""}
    if {needed_group, package_group} == {"weight", "volume"}:
        return {"packages": packages, "exact": False, "note": "assumed 1 g = 1 ml"}
    return {
        "packages": 1,
        "exact": False,
        "note": f"cannot compare {needed_group} with {package_group}",
    }
