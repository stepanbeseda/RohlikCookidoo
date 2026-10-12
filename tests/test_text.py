"""Tests for the Czech text helpers."""

import pytest

from rohlik_cookidoo.text import clean_name, name_key, normalize, stem


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


def test_name_key_ignores_order_case_form_and_preparation():
    key = name_key("hladká mouka")
    assert name_key("hladké mouky") == key
    assert name_key("Mouka hladká, prosátá") == key
    assert name_key("mletého černého pepře") == name_key("černý pepř")


def test_name_key_keeps_qualifiers_that_change_the_product():
    assert name_key("sezamový olej") != name_key("olej")
    assert name_key("arašídové máslo") != name_key("máslo")
