"""Settings read from environment variables, so nothing is hardcoded."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    embedding_model: str
    embedding_dim: int


def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql://skillbridge:skillbridge@localhost:5432/skillbridge"
        ),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        embedding_dim=int(os.environ.get("EMBEDDING_DIM", "384")),
    )
