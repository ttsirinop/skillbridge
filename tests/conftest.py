import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip database tests when DATABASE_URL isn't set (CI always sets it)."""
    if os.environ.get("DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="DATABASE_URL not set")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)
