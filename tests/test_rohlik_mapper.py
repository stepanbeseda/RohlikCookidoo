"""Tests for the Rohlik product helpers used by the CLI."""

import pytest

from rohlik_mapper import _is_bio_product, _parse_products_from_text


@pytest.mark.parametrize(
    ("name", "brand", "expected"),
    [
        ("BIO Mléko", "", True),
        ("Jogurt bílý Bio", "", True),
        ("Pernerka BIO Špaldová mouka", "Pernerka", True),
        ("Mléko", "Bio-Farma", True),
        ("Symbio jogurt", "", False),
        ("Biokoláč", "", False),
        ("Mléko", "", False),
    ],
)
def test_is_bio_product(name, brand, expected):
    assert _is_bio_product(name, brand) is expected


def test_parse_products_from_search_text():
    text = """Found 2 products:

• Kitchin Pšeničná mouka hladká (Kitchin)
  Price: 8.91 Kč (was 9.9 Kč, -10%)
  Amount: 1 kg
  ID: 1480974

• Pernerka Pšeničná hladká mouka (Pernerka)
  Price: 28.9 Kč
  Amount: 1 kg
  ID: 1367687
"""
    first, second = _parse_products_from_text(text)
    assert (first.id, first.name, first.brand, first.price, first.amount) == (
        "1480974", "Kitchin Pšeničná mouka hladká", "Kitchin", 8.91, "1 kg",
    )
    assert (first.original_price, first.discount_percent) == (9.9, 10)
    assert (second.is_discounted, second.price) == (False, 28.9)
