"""Tests for package count estimates."""

import pytest

from rohlik_cookidoo.packages import packages_needed, parse_package_amount


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("500 g", (500, "weight")),
        ("1 kg", (1000, "weight")),
        ("1,98 l", (1980, "volume")),
        ("cca 130 g", (130, "weight")),
        ("cca 0,85 kg", (850, "weight")),
        ("4 x 125 g", (500, "weight")),
        ("6×0,5 l", (3000, "volume")),
        ("10 ks", (10, "count")),
    ],
)
def test_parse_package_amount(text, expected):
    amount, group = parse_package_amount(text)
    assert (pytest.approx(amount), group) == expected


def test_parse_package_amount_unknown():
    assert parse_package_amount("") is None
    assert parse_package_amount("velké balení") is None


@pytest.mark.parametrize(
    ("quantity", "unit", "package", "packages", "leftover"),
    [
        (700, "g", "500 g", 2, "300 g"),
        (500, "g", "500 g", 1, "0 g"),
        (501, "g", "500 g", 2, "499 g"),
        (0.7, "kg", "500 g", 2, "300 g"),
        (300, "g", "4 x 125 g", 1, "200 g"),
        (2, "l", "6×0,5 l", 1, "1000 ml"),
        (12, "ks", "10 ks", 2, "8 ks"),
        (12, None, "10 ks", 2, "8 ks"),
    ],
)
def test_same_kind_is_exact(quantity, unit, package, packages, leftover):
    assert packages_needed(quantity, unit, package) == {
        "packages": packages, "exact": True, "note": "", "leftover": leftover,
    }


def test_grams_against_litres_is_an_estimate():
    result = packages_needed(1500, "g", "1 l")
    assert (result["packages"], result["exact"]) == (2, False)
    assert "1 g = 1 ml" in result["note"]
    assert result["leftover"] == "500 ml"


@pytest.mark.parametrize(
    ("quantity", "unit", "package"),
    [(3, None, "1 kg"), (2, "lžíce", "500 ml"), (None, None, "1 kg"), (200, "g", "balení")],
)
def test_falls_back_to_one_package_with_a_note(quantity, unit, package):
    result = packages_needed(quantity, unit, package)
    assert (result["packages"], result["exact"]) == (1, False)
    assert result["note"]
    assert result["leftover"] is None
