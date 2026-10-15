"""Shared test setup."""

import pytest

from rohlik_cookidoo.household import Household


@pytest.fixture
def household(tmp_path):
    """The user's files in a temporary data directory (created on first write)."""
    return Household(tmp_path / "data")
