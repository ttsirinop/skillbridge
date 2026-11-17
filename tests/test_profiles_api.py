import pytest

pytestmark = pytest.mark.db

VALID = {
    "full_name": "Avery Brooks",
    "email": "Avery.Brooks@Example.com",
    "department": "Engineering",
    "skills": ["Python", " fastapi ", "python", "PostgreSQL"],
    "summary": "Backend developer.",
}


def test_create_profile_returns_201_and_cleans_input(clean_db, client):
    resp = client.post("/profiles", json=VALID)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "avery.brooks@example.com"
    assert body["skills"] == ["Python", "fastapi", "PostgreSQL"]  # trimmed, duplicate removed
    assert body["model_version"] == "hashing-v1"


def test_duplicate_email_returns_409(clean_db, client):
    assert client.post("/profiles", json=VALID).status_code == 201
    resp = client.post("/profiles", json={**VALID, "full_name": "Someone Else"})
    assert resp.status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"email": "not-an-email"},
        {"skills": []},
        {"skills": ["  "]},
        {"full_name": ""},
        {"skills": ["x" * 51]},
        {"unexpected_field": "rejected"},
    ],
)
def test_invalid_profiles_return_422(clean_db, client, change):
    resp = client.post("/profiles", json={**VALID, **change})
    assert resp.status_code == 422


def test_get_and_list_profiles(clean_db, client):
    created = client.post("/profiles", json=VALID).json()
    assert client.get(f"/profiles/{created['id']}").json()["full_name"] == "Avery Brooks"
    listing = client.get("/profiles?limit=5").json()
    assert [p["id"] for p in listing["items"]] == [created["id"]]
    assert client.get("/profiles/9999").status_code == 404
    assert client.get("/profiles?limit=500").status_code == 422
