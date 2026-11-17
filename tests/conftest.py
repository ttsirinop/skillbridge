import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip database tests without DATABASE_URL, and real-model tests without sentence-transformers."""
    try:
        import sentence_transformers  # noqa: F401

        has_sbert = True
    except ImportError:
        has_sbert = False

    if os.environ.get("REQUIRE_SBERT") == "1" and not has_sbert:
        raise pytest.UsageError("REQUIRE_SBERT=1 but sentence-transformers isn't installed.")

    skip_db = pytest.mark.skip(reason="DATABASE_URL not set")
    skip_ai = pytest.mark.skip(reason="sentence-transformers not installed (see requirements-ai.txt)")
    for item in items:
        if "db" in item.keywords and not os.environ.get("DATABASE_URL"):
            item.add_marker(skip_db)
        if "ai" in item.keywords and not has_sbert:
            item.add_marker(skip_ai)


def pytest_configure(config):
    # Tests use the deterministic hashing encoder unless a test opts into the real model.
    os.environ.setdefault("EMBEDDING_BACKEND", "hashing")


@pytest.fixture
def clean_db():
    """Fresh schema and empty tables for API tests that write data."""
    from app.db.connection import get_connection, init_schema
    from app.matching.encoder import get_encoder

    get_encoder.cache_clear()
    init_schema()
    with get_connection() as conn:
        conn.execute(
            "TRUNCATE match_results, skill_profiles, role_profiles, employees RESTART IDENTITY CASCADE"
        )
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)
