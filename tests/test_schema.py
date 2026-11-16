import pytest

from app.db.connection import get_connection, init_schema

pytestmark = pytest.mark.db


@pytest.fixture(scope="module", autouse=True)
def schema():
    init_schema()
    init_schema()  # running twice must not fail


def test_tables_exist():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    names = {r[0] for r in rows}
    assert {"employees", "skill_profiles", "role_profiles", "match_results"} <= names


def test_cosine_search_orders_by_similarity():
    """Smoke test for the matching path: the closest vector comes back first."""
    import numpy as np

    near = np.zeros(384, dtype=np.float32)
    near[0] = 1.0
    far = np.zeros(384, dtype=np.float32)
    far[1] = 1.0

    with get_connection() as conn:
        e1 = conn.execute(
            "INSERT INTO employees (full_name, email) VALUES ('Near', 'near@test.local') RETURNING id"
        ).fetchone()[0]
        e2 = conn.execute(
            "INSERT INTO employees (full_name, email) VALUES ('Far', 'far@test.local') RETURNING id"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO skill_profiles (employee_id, embedding, model_version) "
            "VALUES (%s, %s, 'test'), (%s, %s, 'test')",
            (e1, near, e2, far),
        )
        ranked = conn.execute(
            "SELECT employee_id, 1 - (embedding <=> %s) AS score FROM skill_profiles "
            "WHERE employee_id IN (%s, %s) ORDER BY embedding <=> %s",
            (near, e1, e2, near),
        ).fetchall()
        conn.rollback()  # leave the database clean

    assert ranked[0][0] == e1
    assert ranked[0][1] == pytest.approx(1.0)
