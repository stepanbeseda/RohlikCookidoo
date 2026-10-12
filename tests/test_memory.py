"""Tests for remembered products and preferences."""

import json

from rohlik_cookidoo import memory


def test_remember_and_recall_in_any_case_form():
    entry = memory.remember_product("másla, změklého", 1462148, "Miil Máslo 82%", "250 g")
    assert entry["ingredient"] == "másla"
    recalled = memory.recall_product("máslo")
    assert (recalled["product_id"], recalled["product_name"], recalled["package_amount"]) == (
        1462148, "Miil Máslo 82%", "250 g",
    )
    assert memory.recall_product("arašídové máslo") is None


def test_remember_replaces_the_previous_product():
    memory.remember_product("máslo", 1, "První")
    memory.remember_product("másla", 2, "Druhé")
    assert memory.recall_product("máslo")["product_id"] == 2
    assert len(memory.list_products()) == 1


def test_forget_product():
    memory.remember_product("máslo", 1, "Máslo")
    assert memory.forget_product("másla") is True
    assert memory.forget_product("máslo") is False
    assert memory.recall_product("máslo") is None


def test_name_without_letters_is_not_stored():
    assert memory.remember_product("123", 1, "X") is None
    assert memory.list_products() == []


def test_files_live_next_to_the_pantry(isolated_data_dir):
    memory.remember_product("máslo", 1, "Máslo")
    memory.set_preference("quality", "bio")
    assert (isolated_data_dir / "products.json").exists()
    stored = json.loads((isolated_data_dir / "preferences.json").read_text(encoding="utf-8"))
    assert stored == {"quality": "bio"}


def test_preferences_set_update_and_remove():
    assert memory.get_preferences() == {}
    memory.set_preference("quality", "bio")
    assert memory.set_preference("diet", "bez lepku") == {"quality": "bio", "diet": "bez lepku"}
    assert memory.set_preference("quality", "") == {"diet": "bez lepku"}
    assert memory.set_preference("  ", "x") == {"diet": "bez lepku"}


def test_corrupted_file_is_treated_as_empty(isolated_data_dir):
    isolated_data_dir.mkdir(parents=True)
    (isolated_data_dir / "products.json").write_text("{not json", encoding="utf-8")
    assert memory.list_products() == []
    memory.remember_product("máslo", 1, "Máslo")
    assert memory.recall_product("máslo")["product_id"] == 1
