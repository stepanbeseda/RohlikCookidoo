"""Shared test setup."""

import pytest

from rohlik_cookidoo.household import Household


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Keep the pantry and memory files of every test in a temporary directory."""
    monkeypatch.setenv("PANTRY_PATH", str(tmp_path / "data" / "pantry.txt"))
    return tmp_path / "data"


@pytest.fixture
def household(tmp_path):
    """The user's files in a temporary data directory (created on first write)."""
    return Household(tmp_path / "data")
