"""Request and response models shared by the API modules.

These models are the data contracts in the OpenAPI spec (docs/openapi.json), so any change here
is an interface change and needs the Interface Designer's review (see .github/CODEOWNERS).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
MAX_SKILLS = 50
MAX_SKILL_LENGTH = 50

RoleStatus = Literal["open", "filled", "closed"]


def clean_skills(values: list[str]) -> list[str]:
    """Trim whitespace, drop blanks, and remove case-insensitive duplicates, keeping first spelling."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in values:
        skill = " ".join(str(raw).split())
        if not skill:
            continue
        if len(skill) > MAX_SKILL_LENGTH:
            raise ValueError(f"each skill must be {MAX_SKILL_LENGTH} characters or fewer")
        key = skill.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(skill)
    if len(cleaned) > MAX_SKILLS:
        raise ValueError(f"no more than {MAX_SKILLS} skills are allowed")
    return cleaned


class StrictModel(BaseModel):
    """Rejects unknown fields so typos in requests fail loudly instead of being ignored."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------- Profiles ----------


class ProfileCreate(StrictModel):
    full_name: str = Field(min_length=1, max_length=200, examples=["Avery Brooks"])
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN, examples=["avery.brooks@example.com"])
    department: str | None = Field(default=None, max_length=100, examples=["Engineering"])
    skills: list[str] = Field(min_length=1, examples=[["Python", "FastAPI", "PostgreSQL"]])
    summary: str = Field(default="", max_length=2000)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value: list[str]) -> list[str]:
        cleaned = clean_skills(value)
        if not cleaned:
            raise ValueError("at least one skill is required")
        return cleaned


class Profile(BaseModel):
    id: int
    full_name: str
    email: str
    department: str | None
    skills: list[str]
    summary: str
    model_version: str | None = Field(
        description="Embedding model that produced this profile's vector, or null if not embedded yet."
    )
    created_at: datetime


class ProfileList(BaseModel):
    items: list[Profile]
    limit: int
    offset: int


class ImportRowError(BaseModel):
    row: int = Field(description="Line number in the CSV file, counting the header as line 1.")
    field: str | None
    message: str


class ImportResult(BaseModel):
    created: int
    updated: int
    errors: list[ImportRowError]


# ---------- Roles ----------


class RoleCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200, examples=["Backend Developer"])
    description: str = Field(default="", max_length=2000)
    required_skills: list[str] = Field(min_length=1, examples=[["Python", "FastAPI", "PostgreSQL"]])
    status: RoleStatus = "open"

    @field_validator("required_skills")
    @classmethod
    def validate_skills(cls, value: list[str]) -> list[str]:
        cleaned = clean_skills(value)
        if not cleaned:
            raise ValueError("at least one required skill is needed")
        return cleaned


class Role(BaseModel):
    id: int
    title: str
    description: str
    required_skills: list[str]
    status: RoleStatus
    model_version: str | None
    created_at: datetime


class RoleList(BaseModel):
    items: list[Role]


# ---------- Matching ----------


class Match(BaseModel):
    employee_id: int
    full_name: str
    email: str
    score: float = Field(description="Cosine similarity between the profile and role embeddings (-1 to 1).")
    matched_skills: list[str] = Field(description="Required skills that also appear on the profile.")


class MatchResponse(BaseModel):
    role_id: int
    model_version: str
    matches: list[Match]
