"""Tests for the Czech text helpers."""

import pytest

from rohlik_cookidoo.text import Relation, clean_name, identity, normalize, stem


def test_normalize_strips_diacritics_and_case():
    assert normalize("  Žampióny ") == "zampiony"


@pytest.mark.parametrize(
    ("nominative", "other_form"),
    [
        ("máslo", "másla"), ("sůl", "soli"), ("cukr", "cukru"),
        ("žampióny", "žampiónů"), ("mouka", "mouky"), ("vejce", "vajec"),
        ("ocet", "octa"), ("česnek", "česneku"), ("rajče", "rajčata"),
        ("kuře", "kuřete"), ("cibule", "cibuli"), ("okurka", "okurek"),
        ("jablko", "jablek"), ("mrkev", "mrkve"), ("smetana", "smetany"),
        ("pepř", "pepře"), ("olej", "oleje"), ("mléko", "mléka"),
        ("hovězí", "hovězího"), ("sýr", "sýra"), ("brambory", "brambor"),
    ],
)
def test_stem_joins_case_forms(nominative, other_form):
    assert stem(nominative) == stem(other_form)


@pytest.mark.parametrize(
    ("first", "second"),
    [("máslo", "maso"), ("mouka", "mák"), ("sůl", "sýr"), ("olej", "ocet"), ("rýže", "řepa")],
)
def test_stem_keeps_different_words_apart(first, second):
    assert stem(first) != stem(second)


def test_clean_name():
    assert clean_name("másla, změklého") == "másla"
    assert clean_name("mléko (plnotučné)") == "mléko"
    assert clean_name("pepř podle chuti") == "pepř"


SAME, BROADER, NARROWER, UNRELATED = (
    Relation.SAME, Relation.BROADER, Relation.NARROWER, Relation.UNRELATED)
REVERSE = {SAME: SAME, BROADER: NARROWER, NARROWER: BROADER, UNRELATED: UNRELATED}

TABLE = [
    ("másla", "máslo", SAME), ("soli", "Sůl", SAME), ("vajec", "vejce", SAME),
    ("žampiónů", "žampióny", SAME), ("česneku", "česnek", SAME),
    ("hladké mouky", "mouka hladká", SAME), ("Mouka hladká, prosátá", "hladká mouka", SAME),
    ("mléko (plnotučné)", "mléko", SAME), ("pepř podle chuti", "pepř", SAME),
    ("mletého černého pepře", "černý pepř", SAME), ("nakrájená cibule", "cibule", SAME),
    ("čerstvý", "čerstvé", SAME), ("čerstvý, nasekaný", "čerstvý", SAME), ("123", "123", SAME),
    ("sezamový olej", "olej", BROADER), ("arašídové máslo", "máslo", BROADER),
    ("mletého černého pepře", "pepř", BROADER), ("hladká mouka", "mouka", BROADER),
    ("mouka", "hladká mouka", NARROWER), ("olej", "olivový olej", NARROWER),
    ("máslo", "maso", UNRELATED), ("olej", "ocet", UNRELATED), ("podmáslí", "máslo", UNRELATED),
    ("olejovky", "olej", UNRELATED), ("čerstvý", "čerstvý sýr", UNRELATED),
    ("123", "456", UNRELATED), ("", "", UNRELATED), ("", "máslo", UNRELATED),
    (" (volitelně) ", "(volitelně)", UNRELATED),
]


@pytest.mark.parametrize(("name", "other", "relation"), TABLE)
def test_identity_table(name, other, relation):
    assert identity(name).relation(identity(other)) is relation
    assert identity(other).relation(identity(name)) is REVERSE[relation]
    if identity(name):
        assert (identity(name) == identity(other)) is (relation is SAME)


@pytest.mark.parametrize(("name", "key"), [
    ("másla", "masl"), ("hladké mouky", "hladk mouk"), ("cibule", "cibul"), ("čerstvý", "cerstv"),
    ("123, nakrájené", "123"), ("(volitelně)", ""),
])
def test_identity_text_is_the_products_key(name, key):
    assert str(identity(name)) == key
    assert bool(identity(name)) is bool(key)
