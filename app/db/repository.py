"""SQL for employees, skill profiles, and role profiles.

The API routers call these functions instead of writing SQL themselves, so the database layer
stays in app/db and every query is parameterized in one place.
"""

import psycopg

PROFILE_FIELDS = (
    "id", "full_name", "email", "department", "skills", "summary", "model_version", "created_at"
)
ROLE_FIELDS = ("id", "title", "description", "required_skills", "status", "model_version", "created_at")


class DuplicateEmail(ValueError):
    pass


def _profile(row) -> dict:
    return dict(zip(PROFILE_FIELDS, row, strict=True))


def _role(row) -> dict:
    return dict(zip(ROLE_FIELDS, row, strict=True))


def get_profile(conn: psycopg.Connection, employee_id: int) -> dict | None:
    row = conn.execute(
        "SELECT e.id, e.full_name, e.email, e.department, sp.skills, sp.summary, sp.model_version, "
        "e.created_at "
        "FROM employees e JOIN skill_profiles sp ON sp.employee_id = e.id WHERE e.id = %s",
        (employee_id,),
    ).fetchone()
    return _profile(row) if row else None


def list_profiles(conn: psycopg.Connection, limit: int, offset: int) -> list[dict]:
    rows = conn.execute(
        "SELECT e.id, e.full_name, e.email, e.department, sp.skills, sp.summary, sp.model_version, "
        "e.created_at "
        "FROM employees e JOIN skill_profiles sp ON sp.employee_id = e.id "
        "ORDER BY e.id LIMIT %s OFFSET %s",
        (limit, offset),
    ).fetchall()
    return [_profile(r) for r in rows]


def create_profile(conn: psycopg.Connection, data: dict, embedding, model_version: str | None) -> int:
    """Insert a new employee and skill profile. Raises DuplicateEmail if the email is taken."""
    try:
        with conn.transaction():
            employee_id = conn.execute(
                "INSERT INTO employees (full_name, email, department) VALUES (%s, %s, %s) RETURNING id",
                (data["full_name"], data["email"], data.get("department")),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO skill_profiles (employee_id, skills, summary, embedding, model_version) "
                "VALUES (%s, %s, %s, %s, %s)",
                (employee_id, data["skills"], data.get("summary", ""), embedding, model_version),
            )
    except psycopg.errors.UniqueViolation as exc:
        raise DuplicateEmail(data["email"]) from exc
    return employee_id


def upsert_profile(conn: psycopg.Connection, data: dict, embedding, model_version: str | None) -> bool:
    """Create the profile, or update it if the email already exists. Returns True when created."""
    row = conn.execute(
        """
        INSERT INTO employees (full_name, email, department) VALUES (%s, %s, %s)
        ON CONFLICT (email) DO UPDATE SET full_name = EXCLUDED.full_name, department = EXCLUDED.department
        RETURNING id, (xmax = 0) AS created
        """,
        (data["full_name"], data["email"], data.get("department")),
    ).fetchone()
    employee_id, created = row
    conn.execute(
        """
        INSERT INTO skill_profiles (employee_id, skills, summary, embedding, model_version)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (employee_id) DO UPDATE SET
            skills = EXCLUDED.skills, summary = EXCLUDED.summary, embedding = EXCLUDED.embedding,
            model_version = EXCLUDED.model_version, updated_at = now()
        """,
        (employee_id, data["skills"], data.get("summary", ""), embedding, model_version),
    )
    return bool(created)


def create_role(conn: psycopg.Connection, data: dict, embedding, model_version: str | None) -> dict:
    row = conn.execute(
        """
        INSERT INTO role_profiles (title, description, required_skills, status, embedding, model_version)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, title, description, required_skills, status, model_version, created_at
        """,
        (
            data["title"],
            data.get("description", ""),
            data["required_skills"],
            data.get("status", "open"),
            embedding,
            model_version,
        ),
    ).fetchone()
    return _role(row)


def get_role(conn: psycopg.Connection, role_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, title, description, required_skills, status, model_version, created_at "
        "FROM role_profiles WHERE id = %s",
        (role_id,),
    ).fetchone()
    return _role(row) if row else None


def list_roles(conn: psycopg.Connection, status: str | None) -> list[dict]:
    if status:
        rows = conn.execute(
            "SELECT id, title, description, required_skills, status, model_version, created_at "
            "FROM role_profiles WHERE status = %s ORDER BY id",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, title, description, required_skills, status, model_version, created_at "
            "FROM role_profiles ORDER BY id"
        ).fetchall()
    return [_role(r) for r in rows]
