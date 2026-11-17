"""Text encoders that turn skill and role profiles into fixed-size vectors.

The rest of the app only calls get_encoder().encode(...), so the model can change without touching
the API or database code. Two backends exist:

- SentenceBertEncoder: the real AI feature (Sentence-BERT, all-MiniLM-L6-v2, 384 dimensions).
- HashingEncoder: a deterministic bag-of-words stand-in for tests and CI, so the main pipeline
  doesn't have to install PyTorch on every run. It is not used for real recommendations.
"""

import hashlib
import logging
import re
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.config import get_settings

logger = logging.getLogger("skillbridge.matching")

HASHING_VERSION = "hashing-v1"
TOKEN_PATTERN = re.compile(r"[a-z0-9+#.]+")


class EncoderUnavailable(RuntimeError):
    """Raised when the configured model can't be loaded (for example, missing dependencies)."""


class Encoder(Protocol):
    model_version: str
    dim: int

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return an array of shape (len(texts), dim) with L2-normalized rows."""
        ...


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class HashingEncoder:
    """Feature-hashing encoder: same text in, same vector out, on every machine."""

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.model_version = HASHING_VERSION

    def _bucket(self, token: str) -> tuple[int, float]:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % self.dim, 1.0 if (value >> 63) & 1 else -1.0

    def encode(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in TOKEN_PATTERN.findall(text.lower()):
                index, sign = self._bucket(token)
                matrix[row, index] += sign
        return _normalize(matrix)


class SentenceBertEncoder:
    """Wraps sentence-transformers. The model loads once, on first use."""

    def __init__(self, model_name: str, dim: int) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise EncoderUnavailable(
                "Sentence-BERT isn't installed. Run: pip install -r requirements-ai.txt "
                "(see README), or set EMBEDDING_BACKEND=hashing for tests."
            ) from exc

        logger.info("Loading Sentence-BERT model %s", model_name)
        self._model = SentenceTransformer(model_name, device="cpu")
        actual_dim = self._model.get_sentence_embedding_dimension()
        if actual_dim != dim:
            raise EncoderUnavailable(
                f"Model {model_name} produces {actual_dim}-dimension vectors, but the schema expects {dim}."
            )
        self.dim = dim
        self.model_version = f"sbert:{model_name}"

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(
            texts, batch_size=32, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)


@lru_cache(maxsize=1)
def get_encoder() -> Encoder:
    """Return the configured encoder. Cached, so the model loads only once per process."""
    settings = get_settings()
    if settings.embedding_backend == "hashing":
        return HashingEncoder(settings.embedding_dim)
    if settings.embedding_backend == "sbert":
        return SentenceBertEncoder(settings.embedding_model, settings.embedding_dim)
    raise EncoderUnavailable(f"Unknown EMBEDDING_BACKEND: {settings.embedding_backend!r}")


def profile_text(skills: list[str], summary: str = "", department: str | None = None) -> str:
    """The text that represents an employee's skill profile for embedding."""
    parts = [f"Skills: {', '.join(skills)}."]
    if department:
        parts.append(f"Department: {department}.")
    if summary:
        parts.append(summary)
    return " ".join(parts)


def role_text(title: str, required_skills: list[str], description: str = "") -> str:
    """The text that represents a role profile for embedding."""
    parts = [f"Role: {title}.", f"Skills: {', '.join(required_skills)}."]
    if description:
        parts.append(description)
    return " ".join(parts)


def try_encode(texts: list[str]) -> tuple[list | None, str | None]:
    """Encode texts, or return (None, None) if the model isn't available.

    Saving a profile shouldn't fail just because the AI model is down. Rows saved without a vector
    are picked up by refresh_profile_embeddings() the next time matching runs.
    """
    try:
        encoder = get_encoder()
        return list(encoder.encode(texts)), encoder.model_version
    except (EncoderUnavailable, OSError) as exc:
        logger.warning("Embedding skipped, model unavailable: %s", exc)
        return None, None
