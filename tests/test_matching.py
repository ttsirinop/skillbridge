import os

import numpy as np
import pytest

from app.matching.encoder import HashingEncoder, profile_text, role_text


def cosine(a, b):
    return float(np.dot(a, b))


def test_hashing_encoder_is_deterministic_and_normalized():
    enc = HashingEncoder(384)
    first = enc.encode(["Python FastAPI PostgreSQL", ""])
    second = enc.encode(["Python FastAPI PostgreSQL", ""])
    assert first.shape == (2, 384)
    assert np.array_equal(first, second)
    assert np.linalg.norm(first[0]) == pytest.approx(1.0, abs=1e-6)
    assert np.linalg.norm(first[1]) == 0.0  # empty text stays a zero vector instead of NaN


def test_profile_and_role_text_include_the_skills():
    assert "Python, SQL" in profile_text(["Python", "SQL"], "Analyst", "Data Science")
    assert role_text("Data Analyst", ["SQL"], "Reports").startswith("Role: Data Analyst. Skills: SQL.")


@pytest.mark.ai
def test_sentence_bert_ranks_related_skills_closer():
    """Runs the real model: related skills should score higher than unrelated ones."""
    from app.matching.encoder import SentenceBertEncoder

    enc = SentenceBertEncoder(os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"), 384)
    role, related, unrelated = enc.encode(
        [
            role_text("Backend Developer", ["Python", "REST APIs", "PostgreSQL"]),
            profile_text(["Python", "FastAPI", "SQL databases"]),
            profile_text(["Forklift operation", "Inventory", "Warehouse safety"]),
        ]
    )
    assert enc.model_version == "sbert:all-MiniLM-L6-v2"
    assert cosine(role, related) > cosine(role, unrelated) + 0.1
    again = enc.encode([role_text("Backend Developer", ["Python", "REST APIs", "PostgreSQL"])])[0]
    assert np.allclose(role, again, atol=1e-5)  # same input, same output
