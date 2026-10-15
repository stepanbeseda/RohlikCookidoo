"""Tests for the household: pantry, usual products and preferences."""

import json
import logging
import os
from datetime import date
from pathlib import Path

import pytest

from rohlik_cookidoo import household as household_module
from rohlik_cookidoo import text as text_module
from rohlik_cookidoo.household import Household

PANTRY = ["sůl", "pepř", "voda", "olej", "máslo", "hladká mouka"]

# The three files as the current release writes them (the pantry is hand-written in
# the accepted syntax and has no final newline on purpose). Literals, not files:
# .gitignore ignores these file names at any depth.
CURRENT_PANTRY = "# Spíž – co mám vždy doma\nsůl\n  hladká mouka  \n\n? máslo\n?vejce\nolej"
CURRENT_PRODUCTS = """{
  "cibul": {
    "ingredient": "cibule",
    "package_amount": "1 kg",
    "product_id": 1298821,
    "product_name": "Cibule žlutá, síť",
    "updated": "2026-10-01"
  },
  "hladk mouk": {
    "ingredient": "hladké mouky",
    "package_amount": "",
    "product_id": "2001",
    "product_name": "Mouka hladká",
    "updated": "2026-10-01"
  },
  "masl": {
    "ingredient": "másla",
    "package_amount": "250 g",
    "product_id": 1462148,
    "product_name": "Miil Máslo 82%",
    "updated": "2026-10-01"
  }
}
"""
CURRENT_PREFERENCES = '{\n  "diet": "bez lepku",\n  "quality": "bio"\n}\n'
CURRENT_FILES = {
    "pantry.txt": CURRENT_PANTRY,
    "products.json": CURRENT_PRODUCTS,
    "preferences.json": CURRENT_PREFERENCES,
}
MRKEV = {"ingredient": "mrkev", "product_id": 5, "product_name": "Mrkev"}


def write_pantry(household, text):
    household.pantry_file.parent.mkdir(parents=True, exist_ok=True)
    household.pantry_file.write_text(text, encoding="utf-8")


def write_current_files(household):
    household.data_dir.mkdir(parents=True, exist_ok=True)
    for name, text in CURRENT_FILES.items():
        (household.data_dir / name).write_bytes(text.encode())


def status(household, name):
    found = household.look_up([name])[0]
    return found.pantry_status, found.pantry_item


@pytest.fixture
def replaced(monkeypatch):
    """The names of the files replaced through os.replace, in order."""
    names = []
    real = os.replace

    def spy(source, destination):
        names.append(Path(destination).name)
        real(source, destination)

    monkeypatch.setattr(os, "replace", spy)
    return names


@pytest.fixture
def full_disk(monkeypatch):
    def fail(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)


@pytest.mark.parametrize(
    ("ingredient", "item"),
    [("másla", "máslo"), ("soli", "sůl"), ("vody", "voda"), ("hladké mouky", "hladká mouka"),
     ("Sůl, jemná", "sůl")],
)
def test_same_ingredient_is_at_home(household, ingredient, item):
    write_pantry(household, "\n".join(PANTRY) + "\n")
    assert status(household, ingredient) == ("have", item)


@pytest.mark.parametrize(
    ("ingredient", "item"),
    [("arašídové máslo", "máslo"), ("kokosová voda", "voda"), ("sezamový olej", "olej"),
     ("mletého černého pepře", "pepř"), ("mouka", "hladká mouka")],
)
def test_similar_ingredient_needs_a_check(household, ingredient, item):
    write_pantry(household, "\n".join(PANTRY) + "\n")
    assert status(household, ingredient) == ("check", item)


@pytest.mark.parametrize(
    "ingredient", ["podmáslí", "olejovky", "peprmint", "vepřové plece", "mandlové mléko", ""]
)
def test_unrelated_ingredient_is_not_in_pantry(household, ingredient):
    write_pantry(household, "\n".join(PANTRY) + "\n")
    assert status(household, ingredient) == (None, None)


def test_question_mark_means_ask_first(household):
    write_pantry(household, "sůl\n? máslo\n?vejce\n")
    assert status(household, "másla") == ("ask", "máslo")
    assert status(household, "vajec") == ("ask", "vejce")
    assert status(household, "soli") == ("have", "sůl")
    assert status(household, "arašídové máslo") == ("check", "máslo")


def test_exact_match_wins_over_similar(household):
    write_pantry(household, "slunečnicový olej\nolej\n")
    assert status(household, "oleje") == ("have", "olej")


def test_preparation_only_name_is_at_home(household):
    write_pantry(household, "čerstvý\n")
    assert status(household, "čerstvé") == ("have", "čerstvý")


def test_look_up_answers_every_name_in_order(household):
    write_pantry(household, "sůl\n")
    household.remember_products([{"ingredient": "cibule", "product_id": 1, "product_name": "C"}])
    found = household.look_up(["cibule", "soli", ""])
    assert [(f.name, f.pantry_status, f.pantry_item) for f in found] == [
        ("cibule", None, None), ("soli", "have", "sůl"), ("", None, None),
    ]
    assert [f.usual_product and f.usual_product["product_id"] for f in found] == [1, None, None]


class TestPantry:
    def test_skips_comments_and_blank_lines(self, household):
        write_pantry(household, "# doma\nsůl\n\n  hladká mouka  \n")
        assert household.pantry() == {"always_at_home": ["sůl", "hladká mouka"], "ask_first": []}

    def test_missing_file_is_an_empty_pantry(self, household):
        assert household.pantry() == {"always_at_home": [], "ask_first": []}
        assert not household.data_dir.exists()

    def test_add_creates_file_and_skips_duplicates(self, household):
        assert household.update_pantry(always_at_home=["sůl"]) == {
            "always_at_home": ["sůl"], "ask_first": [],
        }
        assert household.pantry_file.read_text(encoding="utf-8") == "sůl\n"
        assert household.update_pantry(always_at_home=["soli"])["always_at_home"] == ["sůl"]
        assert household.pantry_file.read_text(encoding="utf-8") == "sůl\n"
        assert household.update_pantry(always_at_home=["rýže"])["always_at_home"] == [
            "sůl", "rýže",
        ]
        assert household.pantry_file.read_text(encoding="utf-8") == "sůl\nrýže\n"

    def test_add_creates_missing_directory(self, tmp_path):
        household = Household(tmp_path / "data" / "plugin")
        household.update_pantry(always_at_home=["sůl"])
        assert household.pantry() == {"always_at_home": ["sůl"], "ask_first": []}

    def test_add_ask_first_and_switch_mode(self, household):
        household.update_pantry(ask_first=["máslo"])
        assert household.pantry_file.read_text(encoding="utf-8") == "? máslo\n"
        household.update_pantry(ask_first=["másla"])
        assert household.pantry_file.read_text(encoding="utf-8") == "? máslo\n"
        # the same item without the flag switches it to "always at home"
        household.update_pantry(always_at_home=["máslo"])
        assert household.pantry_file.read_text(encoding="utf-8") == "máslo\n"
        household.update_pantry(always_at_home=["? máslo"])
        assert household.pantry() == {"always_at_home": [], "ask_first": ["máslo"]}

    def test_remove_ask_first_item(self, household):
        write_pantry(household, "sůl\n? máslo\n")
        assert household.update_pantry(remove=["máslo"]) == {
            "always_at_home": ["sůl"], "ask_first": [],
        }

    def test_add_to_file_without_trailing_newline(self, household):
        write_pantry(household, "sůl")
        household.update_pantry(always_at_home=["pepř"])
        assert household.pantry_file.read_text(encoding="utf-8") == "sůl\npepř\n"

    def test_remove_keeps_comments(self, household):
        write_pantry(household, "# doma\nsůl\nmáslo\n")
        household.update_pantry(remove=["másla"])
        assert household.pantry_file.read_text(encoding="utf-8") == "# doma\nsůl\n"
        household.update_pantry(remove=["rýže"])
        assert household.pantry_file.read_text(encoding="utf-8") == "# doma\nsůl\n"

    def test_add_preparation_only_name_twice_keeps_one_line(self, household):
        household.update_pantry(always_at_home=["čerstvý"])
        household.update_pantry(always_at_home=["čerstvé"])
        assert household.pantry_file.read_text(encoding="utf-8") == "čerstvý\n"

    def test_remove_drops_only_the_same_item(self, household):
        write_pantry(household, "čerstvý\n123\n456\n(poznámka)\nsůl\n")
        assert household.update_pantry(remove=["123", ", nic"]) == {
            "always_at_home": ["čerstvý", "456", "(poznámka)", "sůl"], "ask_first": [],
        }

    def test_overview_splits_modes(self, household):
        write_pantry(household, "sůl\n? máslo\npepř\n")
        assert household.pantry() == {
            "always_at_home": ["sůl", "pepř"], "ask_first": ["máslo"],
        }

    def test_one_call_removes_then_adds_then_asks(self, household):
        write_pantry(household, "# doma\nsůl\nrýže\nmáslo\n")
        result = household.update_pantry(
            always_at_home=["pepř"], ask_first=["máslo", "vejce"], remove=["rýže", "sůl"]
        )
        assert result == {"always_at_home": ["pepř"], "ask_first": ["máslo", "vejce"]}
        assert household.pantry_file.read_text(encoding="utf-8") == (
            "# doma\npepř\n? máslo\n? vejce\n"
        )


class TestProducts:
    def test_remember_and_recall_in_any_case_form(self, household):
        [entry] = household.remember_products([{
            "ingredient": "másla, změklého", "product_id": 1462148,
            "product_name": "Miil Máslo 82%", "package_amount": "250 g",
        }])
        assert entry["ingredient"] == "másla"
        recalled = household.look_up(["máslo"])[0].usual_product
        assert (recalled["product_id"], recalled["product_name"], recalled["package_amount"]) == (
            1462148, "Miil Máslo 82%", "250 g",
        )
        assert household.look_up(["arašídové máslo"])[0].usual_product is None

    def test_remember_replaces_the_previous_product(self, household):
        household.remember_products([{"ingredient": "máslo", "product_id": 1, "product_name": "První"}])
        household.remember_products([{"ingredient": "másla", "product_id": 2, "product_name": "Druhé"}])
        assert household.look_up(["máslo"])[0].usual_product["product_id"] == 2
        assert len(household.usual_products()) == 1
        # both in one call: the last one wins, and both are reported
        stored = household.remember_products([
            {"ingredient": "máslo", "product_id": 3, "product_name": "Třetí"},
            {"ingredient": "másla", "product_id": 4, "product_name": "Čtvrté"},
        ])
        assert [e["product_id"] for e in stored] == [3, 4]
        assert household.look_up(["máslo"])[0].usual_product["product_id"] == 4
        assert len(household.usual_products()) == 1

    def test_forget_product(self, household):
        household.remember_products([{"ingredient": "máslo", "product_id": 1, "product_name": "M"}])
        assert household.forget_product("másla") is True
        assert household.forget_product("máslo") is False
        assert household.look_up(["máslo"])[0].usual_product is None

    def test_forgetting_what_is_not_stored_writes_nothing(self, household, replaced):
        assert household.forget_product("máslo") is False
        assert replaced == []

    def test_preparation_only_name_is_remembered(self, household):
        [entry] = household.remember_products([
            {"ingredient": "čerstvý", "product_id": 7, "product_name": "X"}])
        assert entry["ingredient"] == "čerstvý"
        assert household.look_up(["čerstvé"])[0].usual_product["product_id"] == 7

    def test_name_without_identity_is_not_stored(self, household):
        stored = household.remember_products([
            {"ingredient": "", "product_id": 1, "product_name": "X"},
            {"ingredient": " (volitelně) ", "product_id": 2, "product_name": "Y"},
            {"ingredient": ", nakrájená", "product_id": 3, "product_name": "Z"},
        ])
        assert stored == []
        assert household.usual_products() == []
        assert not household.products_file.exists()
        [entry] = household.remember_products([
            {"ingredient": "123", "product_id": 4, "product_name": "W"}])
        assert household.look_up(["123"])[0].usual_product == entry

    def test_entries_without_an_ingredient_are_skipped_and_kept(self, household):
        household.data_dir.mkdir(parents=True)
        household.products_file.write_text(json.dumps({
            "x": 1, "y": {"product_id": 2}, "z": {"ingredient": ""},
            "masl": {"ingredient": "másla", "product_id": 3, "product_name": "M",
                     "updated": "2026-01-01"},
        }), encoding="utf-8")
        assert [e["product_id"] for e in household.usual_products()] == [3]
        household.remember_products([{"ingredient": "mrkev", "product_id": 5, "product_name": "R"}])
        stored = json.loads(household.products_file.read_text(encoding="utf-8"))
        assert sorted(stored) == ["masl", "mrkv", "x", "y", "z"]

    def test_the_latest_of_two_entries_for_one_ingredient_wins(self, household):
        household.data_dir.mkdir(parents=True)
        household.products_file.write_text(json.dumps({
            "maslo": {"ingredient": "máslo", "product_id": 1, "product_name": "Old",
                      "updated": "2026-09-01"},
            "masl": {"ingredient": "másla", "product_id": 2, "product_name": "New",
                     "updated": "2026-10-01"},
            "masl x": {"ingredient": "Máslo", "product_id": 3, "product_name": "Older",
                       "updated": "2026-08-01"},
        }), encoding="utf-8")
        assert household.look_up(["máslo"])[0].usual_product["product_id"] == 2
        assert [e["product_id"] for e in household.usual_products()] == [2]
        household.remember_products([{"ingredient": "mrkev", "product_id": 5, "product_name": "R"}])
        stored = json.loads(household.products_file.read_text(encoding="utf-8"))
        assert {k: e["product_id"] for k, e in stored.items()} == {"masl": 2, "mrkv": 5}


class TestPreferences:
    def test_set_update_and_remove(self, household):
        assert household.preferences() == {}
        household.set_preference("quality", "bio")
        assert household.set_preference("diet", "bez lepku") == {
            "quality": "bio", "diet": "bez lepku",
        }
        assert household.set_preference("quality", "") == {"diet": "bez lepku"}
        assert household.set_preference("  ", "x") == {"diet": "bez lepku"}
        assert household.preferences() == {"diet": "bez lepku"}


class TestFromEnv:
    def test_pantry_file_variable(self, tmp_path):
        pantry = tmp_path / "x" / "spiz.txt"
        household = Household.from_env({"PANTRY_PATH": str(pantry)})
        assert household.pantry_file == pantry
        assert household.products_file == tmp_path / "x" / "products.json"
        assert household.preferences_file == tmp_path / "x" / "preferences.json"

    def test_data_dir(self, tmp_path):
        household = Household.from_env({"DATA_DIR": str(tmp_path / "state")})
        assert household.pantry_file == tmp_path / "state" / "pantry.txt"
        assert household.products_file == tmp_path / "state" / "products.json"
        assert household.preferences_file == tmp_path / "state" / "preferences.json"

    def test_pantry_file_variable_wins_over_data_dir(self, tmp_path):
        household = Household.from_env({
            "PANTRY_PATH": str(tmp_path / "x" / "spiz.txt"), "DATA_DIR": str(tmp_path / "state"),
        })
        assert household.pantry_file == tmp_path / "x" / "spiz.txt"
        assert household.products_file == tmp_path / "x" / "products.json"

    def test_default_is_the_repository_root(self):
        household = Household.from_env({})
        root = Path(household_module.__file__).parent.parent
        assert household.pantry_file == root / "pantry.txt"
        assert household.products_file == root / "products.json"

    def test_empty_values_count_as_unset(self, tmp_path):
        household = Household.from_env({"PANTRY_PATH": "", "DATA_DIR": str(tmp_path)})
        assert household.pantry_file == tmp_path / "pantry.txt"
        household = Household.from_env({"PANTRY_PATH": "", "DATA_DIR": ""})
        assert household.pantry_file == Household.from_env({}).pantry_file

    def test_json_files_live_next_to_the_pantry(self, tmp_path):
        household = Household.from_env({"PANTRY_PATH": str(tmp_path / "d" / "spiz.txt")})
        household.remember_products([{"ingredient": "máslo", "product_id": 1, "product_name": "M"}])
        household.set_preference("quality", "bio")
        household.update_pantry(always_at_home=["sůl"])
        assert sorted(p.name for p in (tmp_path / "d").iterdir()) == [
            "preferences.json", "products.json", "spiz.txt",
        ]
        stored = json.loads((tmp_path / "d" / "preferences.json").read_text(encoding="utf-8"))
        assert stored == {"quality": "bio"}


@pytest.fixture(params=["new irregular form", "new preparation word"])
def changed_stemmer(request, monkeypatch):
    """Simulate a later release whose stemming rules differ."""
    if request.param == "new irregular form":
        monkeypatch.setitem(text_module._IRREGULAR, "masl", "maslo")
    else:
        monkeypatch.setattr(
            text_module, "_IGNORED_STEMS", text_module._IGNORED_STEMS | {"hladk"}
        )


class TestCurrentReleaseFiles:
    def test_load(self, household):
        write_current_files(household)
        assert household.pantry() == {
            "always_at_home": ["sůl", "hladká mouka", "olej"], "ask_first": ["máslo", "vejce"],
        }
        found = household.look_up(["másla", "hladké mouky", "cibulí", "mrkve"])
        assert [
            (f.pantry_status, f.pantry_item, f.usual_product and f.usual_product["product_id"])
            for f in found
        ] == [("ask", "máslo", 1462148), ("have", "hladká mouka", "2001"),
              (None, None, 1298821), (None, None, None)]
        assert [p["ingredient"] for p in household.usual_products()] == [
            "cibule", "hladké mouky", "másla",
        ]
        assert household.preferences() == {"diet": "bez lepku", "quality": "bio"}

    def test_writes_keep_what_they_do_not_change(self, household):
        write_current_files(household)
        household.update_pantry(always_at_home=["rýže"])
        assert household.pantry_file.read_bytes() == (CURRENT_PANTRY + "\nrýže\n").encode()

        household.set_preference("quality", "bio")
        assert household.preferences_file.read_bytes() == CURRENT_PREFERENCES.encode()

        before = json.loads(CURRENT_PRODUCTS)
        household.remember_products([MRKEV])
        after = json.loads(household.products_file.read_text(encoding="utf-8"))
        added = [entry for key, entry in after.items() if key not in before]
        assert {key: after[key] for key in before} == before
        assert len(after) == len(before) + 1
        assert (added[0]["ingredient"], added[0]["updated"]) == ("mrkev", date.today().isoformat())

    def test_recalled_in_any_case_form(self, household):
        write_current_files(household)
        names = ["máslo", "másla", "MÁSLO", "máslem", "hladká mouka", "mouky hladké",
                 "hladkou mouku", "Hladká mouka, prosátá", "cibule", "cibulí", "cibuli (červená)"]
        assert [f.usual_product["product_id"] for f in household.look_up(names)] == (
            [1462148] * 4 + ["2001"] * 4 + [1298821] * 3)

    def test_usual_products_survive_a_stemmer_change(self, household, changed_stemmer):
        write_current_files(household)
        found = household.look_up(["máslo", "hladká mouka", "cibule"])
        assert [f.usual_product["product_id"] for f in found] == [1462148, "2001", 1298821]
        household.remember_products([
            {"ingredient": "máslo", "product_id": 9, "product_name": "N"},
            {"ingredient": "hladká mouka", "product_id": 8, "product_name": "M"},
        ])
        stored = json.loads(household.products_file.read_text(encoding="utf-8"))
        assert sorted(e["product_id"] for e in stored.values()) == [8, 9, 1298821]
        assert household.forget_product("cibulí") is True
        assert sorted(e["product_id"] for e in household.usual_products()) == [8, 9]


def test_update_pantry_without_a_change_writes_nothing(household, replaced):
    write_current_files(household)
    before = household.pantry_file.stat().st_mtime_ns
    household.update_pantry(always_at_home=["soli"], ask_first=["másla"], remove=["mrkev"])
    assert replaced == []
    assert household.pantry_file.read_bytes() == CURRENT_PANTRY.encode()
    assert household.pantry_file.stat().st_mtime_ns == before


@pytest.mark.parametrize(
    ("operation", "target"),
    [
        pytest.param(lambda h: h.update_pantry(always_at_home=["rýže"]), "pantry.txt", id="pantry"),
        pytest.param(lambda h: h.remember_products([MRKEV]), "products.json", id="remember"),
        pytest.param(lambda h: h.forget_product("máslo"), "products.json", id="forget"),
        pytest.param(lambda h: h.set_preference("diet", "vegan"), "preferences.json",
                     id="preference"),
    ],
)
def test_a_failed_write_leaves_the_file_as_it_was(household, full_disk, operation, target):
    write_current_files(household)
    with pytest.raises(OSError, match="disk full"):
        operation(household)
    assert (household.data_dir / target).read_bytes() == CURRENT_FILES[target].encode()
    assert sorted(p.name for p in household.data_dir.iterdir()) == sorted(CURRENT_FILES)


@pytest.mark.parametrize(
    ("operation", "name"),
    [
        pytest.param(lambda h: h.update_pantry(always_at_home=["rýže"]), "pantry.txt", id="pantry"),
        pytest.param(lambda h: h.remember_products([MRKEV]), "products.json", id="remember"),
        pytest.param(lambda h: h.set_preference("diet", "vegan"), "preferences.json",
                     id="preference"),
    ],
)
def test_a_write_follows_a_symlinked_file(household, tmp_path, operation, name):
    write_current_files(household)
    target = tmp_path / "synced" / name
    target.parent.mkdir()
    (household.data_dir / name).rename(target)
    (household.data_dir / name).symlink_to(target)
    before = target.read_bytes()
    operation(household)
    assert (household.data_dir / name).is_symlink()
    assert target.read_bytes() != before
    assert sorted(p.name for p in target.parent.iterdir()) == [name]


@pytest.mark.parametrize("content", [b"{not json", b"[1, 2]", b"\xff\xfe"])
def test_unreadable_json_is_empty_with_a_warning(household, caplog, content):
    household.data_dir.mkdir(parents=True)
    household.products_file.write_bytes(content)
    with caplog.at_level(logging.WARNING, logger="rohlik_cookidoo.household"):
        assert household.usual_products() == []
    assert [r for r in caplog.records
            if r.name == "rohlik_cookidoo.household" and r.levelno == logging.WARNING
            and "products.json" in r.getMessage()]
    household.remember_products([{"ingredient": "máslo", "product_id": 1, "product_name": "M"}])
    assert household.look_up(["másla"])[0].usual_product["product_id"] == 1


def test_remember_products_writes_once(household, replaced):
    stored = household.remember_products([
        {"ingredient": "máslo", "product_id": 1, "product_name": "M"},
        {"ingredient": "cibule", "product_id": 2, "product_name": "C"},
        {"ingredient": "", "product_id": 3, "product_name": "X"},
        {"ingredient": "mléko", "product_id": 4, "product_name": "L"},
    ])
    assert replaced == ["products.json"]
    assert len(stored) == 3
