"""PostgreSQL connection helpers. Other modules use these instead of opening their own connections."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from app.config import get_settings

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Open a connection with pgvector types registered. Commits on success, rolls back on error."""
    conn = psycopg.connect(get_settings().database_url)
    try:
        register_vector(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    """Create the extension, tables, and indexes. Safe to run more than once."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        conn.execute(sql)


if __name__ == "__main__":
    init_schema()
    print("Schema is ready.")
