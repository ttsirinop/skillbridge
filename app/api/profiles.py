"""Employee skill-profile endpoints, including CSV import."""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.api.csv_import import CsvFormatError, parse_profiles_csv
from app.config import get_settings
from app.db import repository
from app.db.connection import get_connection
from app.matching.encoder import profile_text, try_encode
from app.schemas import ImportResult, Profile, ProfileCreate, ProfileList

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("", response_model=Profile, status_code=status.HTTP_201_CREATED)
def create_profile(body: ProfileCreate) -> dict:
    """Create an employee and their skill profile. The profile is embedded for matching right away."""
    vectors, model_version = try_encode([profile_text(body.skills, body.summary, body.department)])
    with get_connection() as conn:
        try:
            employee_id = repository.create_profile(
                conn, body.model_dump(), vectors[0] if vectors else None, model_version
            )
        except repository.DuplicateEmail as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "An employee with this email already exists."
            ) from exc
        return repository.get_profile(conn, employee_id)


@router.get("", response_model=ProfileList)
def list_profiles(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> dict:
    with get_connection() as conn:
        return {"items": repository.list_profiles(conn, limit, offset), "limit": limit, "offset": offset}


@router.get("/{employee_id}", response_model=Profile)
def get_profile(employee_id: int) -> dict:
    with get_connection() as conn:
        profile = repository.get_profile(conn, employee_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found.")
    return profile


@router.post("/import", response_model=ImportResult)
def import_profiles(
    file: Annotated[UploadFile, File(description="UTF-8 CSV, up to 1,000 rows")],
) -> dict:
    """Bulk-load profiles from CSV. Existing emails are updated; bad rows are reported, not fatal."""
    # Plain def (not async) so the model and database work run in FastAPI's thread pool
    # instead of blocking the event loop for every other request.
    # Check the extension, not the content type: browsers on Windows send Excel's type for .csv files.
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload must be a .csv file.")
    max_bytes = get_settings().max_upload_bytes
    content = file.file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File is larger than {max_bytes:,} bytes."
        )
    try:
        profiles, errors = parse_profiles_csv(content)
    except CsvFormatError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    texts = [profile_text(p.skills, p.summary, p.department) for p in profiles]
    vectors, model_version = try_encode(texts) if texts else (None, None)

    created = updated = 0
    with get_connection() as conn:  # one transaction: all valid rows land, or none do
        for i, profile in enumerate(profiles):
            vector = vectors[i] if vectors else None
            if repository.upsert_profile(conn, profile.model_dump(), vector, model_version):
                created += 1
            else:
                updated += 1
    return {"created": created, "updated": updated, "errors": [e.model_dump() for e in errors]}
