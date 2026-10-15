"""Tests for amounts: numbers, units, groups, package sizes and formatting."""

import pytest

from rohlik_cookidoo.amount import (
    COUNT,
    VOLUME,
    WEIGHT,
    Amount,
    canonical_unit,
    format_quantity,
    parse_amount,
    parse_package,
    split_unit,
    total,
)


class TestParseAmount:
    @pytest.mark.parametrize(
        ("text", "value", "unit"),
        [
            ("200 g", 200, "g"),
            ("250 gramů", 250, "g"),
            ("1.5 kg", 1.5, "kg"),
            ("0,5 l", 0.5, "l"),
            ("200g", 200, "g"),
            ("3", 3, None),
            ("3 ks", 3, "ks"),
            ("2 lžíce", 2, "lžíce"),
            ("2 PL", 2, "lžíce"),
            ("1 ČL", 1, "lžička"),
            ("5 cl", 5, "cl"),
            ("1 polévková lžíce", 1, "lžíce"),
            ("0.5 čajové lžičky", 0.5, "lžička"),
            ("1 vrchovatá čajová lžička", 1, "lžička"),
            ("2 stroužky", 2, "stroužek"),
            ("1 plechovka", 1, "plechovka"),
            # fractions
            ("1/2 lžičky", 0.5, "lžička"),
            ("½ lžičky", 0.5, "lžička"),
            ("1 1/2 lžíce", 1.5, "lžíce"),
            ("1½ lžíce", 1.5, "lžíce"),
            # ranges take the upper bound
            ("1-2 lžíce", 2, "lžíce"),
            ("2 - 3 stroužky", 3, "stroužek"),
            # a dot before exactly three digits is a thousands separator
            ("1.000 g", 1000, "g"),
            ("0.125 l", 0.125, "l"),
        ],
    )
    def test_value_and_unit(self, text, value, unit):
        amount, rest = parse_amount(text)
        assert (amount.value, amount.unit, rest) == (pytest.approx(value), unit, "")

    def test_no_number(self):
        assert parse_amount("podle chuti") == (None, "podle chuti")
        assert parse_amount("") == (None, "")

    def test_rest_is_returned(self):
        assert parse_amount("200 g hladká mouka") == (Amount(200, "g"), "hladká mouka")

    def test_size_word_without_unit_stays_in_the_name(self):
        assert parse_amount("1 velká cibule") == (Amount(1, None), "velká cibule")


def test_split_unit():
    assert split_unit("stroužky česneku") == ("stroužek", "česneku")
    assert split_unit("listové těsto") == (None, "listové těsto")


@pytest.mark.parametrize(
    ("text", "unit"),
    [("g", "g"), ("gramů", "g"), ("litr", "l"), ("kusy", "ks"), ("ČL", "lžička"),
     ("lžíce", "lžíce"), ("", None), (None, None), ("  ", None), ("hrnek mouky", "hrnek mouky"),
     ("šálek", "hrnek"), ("pytlík", "pytlík")],
)
def test_canonical_unit(text, unit):
    assert canonical_unit(text) == unit


class TestParsePackage:
    @pytest.mark.parametrize(
        ("text", "size"),
        [
            ("500 g", Amount(500, "g")),
            ("1 kg", Amount(1000, "g")),
            ("1,98 l", Amount(1980, "ml")),
            ("cca 130 g", Amount(130, "g")),
            ("cca 0,85 kg", Amount(850, "g")),
            ("4 x 125 g", Amount(500, "g")),
            ("6×0,5 l", Amount(3000, "ml")),
            ("10 ks", Amount(10, "ks")),
            # the same number parser and unit words as recipes
            ("1.000 g", Amount(1000, "g")),
            ("2 kusy", Amount(2, "ks")),
            ("1 litr", Amount(1000, "ml")),
            ("500 gramů", Amount(500, "g")),
            ("2 KG", Amount(2000, "g")),
            ("3 lžíce", Amount(3, "lžíce")),
            # the unit must follow the number
            ("500 g/ks", Amount(500, "g")),
            ("1,5 % 1 l", Amount(1000, "ml")),
            ("1 ks cca 150 g", Amount(1, "ks")),
            # float noise does not survive conversion
            ("2,01 kg", Amount(2010, "g")),
        ],
    )
    def test_size(self, text, size):
        assert parse_package(text) == size

    @pytest.mark.parametrize("text", ["", "velké balení", "balení", "10", "0 g", "2 x balení"])
    def test_no_size(self, text):
        assert parse_package(text) is None


@pytest.mark.parametrize(
    ("amount", "base", "group"),
    [
        (Amount(1.5, "kg"), Amount(1500, "g"), WEIGHT),
        (Amount(250, "mg"), Amount(0.25, "g"), WEIGHT),
        (Amount(2, "dl"), Amount(200, "ml"), VOLUME),
        (Amount(5, "cl"), Amount(50, "ml"), VOLUME),
        (Amount(3, None), Amount(3, "ks"), COUNT),
        (Amount(3, "ks"), Amount(3, "ks"), COUNT),
        (Amount(2, "lžíce"), Amount(2, "lžíce"), "lžíce"),
    ],
)
def test_base_and_group(amount, base, group):
    assert (amount.base(), amount.group, amount.base().group) == (base, group, group)


class TestTotal:
    def test_one_group_adds_in_the_base_unit(self):
        assert total([Amount(200, "g"), Amount(0.3, "kg")]) == Amount(500, "g")

    def test_plain_count_and_ks_add_up(self):
        assert total([Amount(2, None), Amount(3, "ks")]) == Amount(5, "ks")

    def test_mixed_groups_do_not_add(self):
        assert total([Amount(100, "ml"), Amount(2, "lžíce")]) is None
        assert total([Amount(100, "ml"), Amount(100, "g")]) is None

    def test_nothing_to_add(self):
        assert total([]) is None


class TestInUnitsOf:
    def test_same_group_is_exact(self):
        assert Amount(0.7, "kg").in_units_of(Amount(500, "g")) == (700, "")

    def test_weight_against_volume_is_an_estimate(self):
        assert Amount(1500, "g").in_units_of(Amount(1, "l")) == (1500, "assumed 1 g = 1 ml")
        assert Amount(2, "dl").in_units_of(Amount(1, "kg")) == (200, "assumed 1 g = 1 ml")

    @pytest.mark.parametrize(
        ("amount", "size"),
        [(Amount(3, None), Amount(1, "kg")), (Amount(2, "lžíce"), Amount(500, "ml")),
         (Amount(2, "lžíce"), Amount(2, "lžička"))],
    )
    def test_other_groups_do_not_compare(self, amount, size):
        assert amount.in_units_of(size) is None


def test_format_quantity():
    assert format_quantity(500, "g") == "500 g"
    assert format_quantity(1.5, "lžíce") == "1.5 lžíce"
    assert format_quantity(0.25, "lžička") == "0.25 lžička"
    assert format_quantity(2 / 3, "kg") == "0.67 kg"
    assert format_quantity(3, None) == "3"
    assert format_quantity(None, None) == "dle chuti"
    assert str(Amount(1.5, "kg")) == "1.5 kg"
