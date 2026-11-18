"""FastAPI entry point. Each module adds its router here."""

import logging

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.profiles import router as profiles_router
from app.api.roles import router as roles_router
from app.db.connection import get_connection

logger = logging.getLogger("skillbridge")

app = FastAPI(title="SkillBridge", version="0.1.0-alpha")

app.include_router(profiles_router)
app.include_router(roles_router)


@app.exception_handler(psycopg.OperationalError)
async def database_unavailable(_: Request, exc: psycopg.OperationalError) -> JSONResponse:
    # Log the details, but don't send connection info back to the client.
    logger.error("Database unavailable: %s", exc)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


@app.get("/health")
def health() -> dict:
    """Liveness check. Doesn't touch the database."""
    return {"status": "ok"}


@app.get("/health/db")
def health_db() -> dict:
    """Readiness check: confirms the database and the pgvector extension are reachable."""
    with get_connection() as conn:
        row = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
    return {"status": "ok", "pgvector": row[0] if row else None}
