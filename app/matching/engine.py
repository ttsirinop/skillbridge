"""Matching engine: keeps embeddings current and ranks employees for a role.

Ranking uses pgvector's cosine distance operator (<=>) and the HNSW index from db/schema.sql.
Every result is saved to match_results with the model version, so recommendations can be audited
later and traced back to the model that produced them.
"""

import logging

import psycopg

from app.matching.encoder import Encoder, profile_text, role_text

logger = logging.getLogger("skillbridge.matching")


class RoleNotFound(LookupError):
    pass


def refresh_profile_embeddings(conn: psycopg.Connection, encoder: Encoder) -> int:
    """Embed any profile that has no vector yet or was embedded by a different model version."""
    rows = conn.execute(
        """
        SELECT sp.employee_id, sp.skills, sp.summary, e.department
        FROM skill_profiles sp JOIN employees e ON e.id = sp.employee_id
        WHERE sp.embedding IS NULL OR sp.model_version IS DISTINCT FROM %s
        ORDER BY sp.employee_id
        """,
        (encoder.model_version,),
    ).fetchall()
    if not rows:
        return 0

    vectors = encoder.encode([profile_text(skills, summary, dept) for _, skills, summary, dept in rows])
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE skill_profiles SET embedding = %s, model_version = %s, updated_at = now() "
            "WHERE employee_id = %s",
            [(vec, encoder.model_version, row[0]) for row, vec in zip(rows, vectors, strict=True)],
        )
    logger.info("Re-embedded %d profile(s) with %s", len(rows), encoder.model_version)
    return len(rows)


def _role_vector(conn: psycopg.Connection, encoder: Encoder, role_id: int):
    row = conn.execute(
        "SELECT title, description, required_skills, embedding, model_version "
        "FROM role_profiles WHERE id = %s",
        (role_id,),
    ).fetchone()
    if row is None:
        raise RoleNotFound(role_id)

    title, description, required_skills, embedding, model_version = row
    if embedding is None or model_version != encoder.model_version:
        embedding = encoder.encode([role_text(title, required_skills, description)])[0]
        conn.execute(
            "UPDATE role_profiles SET embedding = %s, model_version = %s WHERE id = %s",
            (embedding, encoder.model_version, role_id),
        )
    return embedding, required_skills


def rank_candidates(conn: psycopg.Connection, encoder: Encoder, role_id: int, limit: int = 10) -> list[dict]:
    """Return the top `limit` employees for a role, best match first.

    Ties are broken by employee id, so the same data always produces the same order.
    """
    refresh_profile_embeddings(conn, encoder)
    role_vector, required_skills = _role_vector(conn, encoder, role_id)

    rows = conn.execute(
        """
        SELECT e.id, e.full_name, e.email, sp.skills, 1 - (sp.embedding <=> %s) AS score
        FROM skill_profiles sp JOIN employees e ON e.id = sp.employee_id
        WHERE sp.embedding IS NOT NULL AND sp.model_version = %s
        ORDER BY sp.embedding <=> %s, e.id
        LIMIT %s
        """,
        (role_vector, encoder.model_version, role_vector, limit),
    ).fetchall()

    required_lower = {skill.lower() for skill in required_skills}
    matches = []
    for employee_id, full_name, email, skills, score in rows:
        score = max(-1.0, min(1.0, float(score)))  # guard against floating-point drift past the CHECK
        matches.append(
            {
                "employee_id": employee_id,
                "full_name": full_name,
                "email": email,
                "score": round(score, 4),
                "matched_skills": [s for s in skills if s.lower() in required_lower],
            }
        )

    if matches:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO match_results (role_id, employee_id, score, model_version)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (role_id, employee_id, model_version)
                DO UPDATE SET score = EXCLUDED.score, created_at = now()
                """,
                [(role_id, m["employee_id"], m["score"], encoder.model_version) for m in matches],
            )
    return matches
