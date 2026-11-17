"""Role-profile endpoints and the AI matching endpoint."""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.db import repository
from app.db.connection import get_connection
from app.matching.encoder import EncoderUnavailable, get_encoder, role_text, try_encode
from app.matching.engine import RoleNotFound, rank_candidates
from app.schemas import MatchResponse, Role, RoleCreate, RoleList, RoleStatus

logger = logging.getLogger("skillbridge")
router = APIRouter(prefix="/roles", tags=["roles"])


@router.post("", response_model=Role, status_code=status.HTTP_201_CREATED)
def create_role(body: RoleCreate) -> dict:
    """Create a role profile that a project manager wants to fill."""
    vectors, model_version = try_encode([role_text(body.title, body.required_skills, body.description)])
    with get_connection() as conn:
        return repository.create_role(conn, body.model_dump(), vectors[0] if vectors else None, model_version)


@router.get("", response_model=RoleList)
def list_roles(status_filter: Annotated[RoleStatus | None, Query(alias="status")] = None) -> dict:
    with get_connection() as conn:
        return {"items": repository.list_roles(conn, status_filter)}


@router.get("/{role_id}", response_model=Role)
def get_role(role_id: int) -> dict:
    with get_connection() as conn:
        role = repository.get_role(conn, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found.")
    return role


@router.get("/{role_id}/matches", response_model=MatchResponse)
def get_matches(role_id: int, limit: Annotated[int, Query(ge=1, le=50)] = 10) -> dict:
    """AI feature: rank internal candidates for a role by Sentence-BERT similarity, best first."""
    try:
        encoder = get_encoder()
    except (EncoderUnavailable, OSError) as exc:
        logger.error("Matching unavailable: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI model unavailable.") from exc

    with get_connection() as conn:
        try:
            matches = rank_candidates(conn, encoder, role_id, limit)
        except RoleNotFound as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found.") from exc
    return {"role_id": role_id, "model_version": encoder.model_version, "matches": matches}
