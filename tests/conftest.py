"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Keep the pantry and memory files of every test in a temporary directory."""
    monkeypatch.setenv("PANTRY_PATH", str(tmp_path / "data" / "pantry.txt"))
    return tmp_path / "data"
