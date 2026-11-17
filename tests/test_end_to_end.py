"""End-to-end: CSV import -> role creation -> AI matching, through the public API only.

This is the integration test for all three modules (API, matching, database) working together.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.db

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample_profiles.csv"


def test_import_role_and_match(clean_db, client):
    with SAMPLE_CSV.open("rb") as fh:
        imported = client.post("/profiles/import", files={"file": ("sample.csv", fh, "text/csv")}).json()
    assert imported["created"] == 50 and not imported["errors"]

    role = client.post(
        "/roles",
        json={
            "title": "Security Analyst",
            "description": "Monitor alerts and lead incident response.",
            "required_skills": ["Incident Response", "SIEM", "Splunk", "Threat Hunting"],
        },
    )
    assert role.status_code == 201
    role_id = role.json()["id"]

    resp = client.get(f"/roles/{role_id}/matches?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    matches = body["matches"]
    assert len(matches) == 5
    assert body["model_version"] == "hashing-v1"

    scores = [m["score"] for m in matches]
    assert scores == sorted(scores, reverse=True)
    assert matches[0]["matched_skills"], "top match should share required skills"

    # Every top match should come from the cybersecurity track in the sample data.
    profiles = {p["id"]: p for p in client.get("/profiles?limit=200").json()["items"]}
    assert all(profiles[m["employee_id"]]["department"] == "Cybersecurity" for m in matches)

    # Same data, same ranking (reliable output), and results are stored for auditing.
    assert client.get(f"/roles/{role_id}/matches?limit=5").json() == body

    from app.db.connection import get_connection

    with get_connection() as conn:
        stored = conn.execute("SELECT count(*) FROM match_results WHERE role_id = %s", (role_id,)).fetchone()
    assert stored[0] == 5


def test_matches_for_missing_role_returns_404(clean_db, client):
    assert client.get("/roles/999/matches").status_code == 404


def test_roles_create_list_and_validate(clean_db, client):
    created = client.post("/roles", json={"title": "Data Analyst", "required_skills": ["SQL"]})
    assert created.status_code == 201
    assert created.json()["status"] == "open"
    assert client.get("/roles?status=open").json()["items"][0]["title"] == "Data Analyst"
    assert client.get("/roles?status=filled").json()["items"] == []
    assert client.get(f"/roles/{created.json()['id']}").status_code == 200
    assert client.get("/roles/999").status_code == 404
    assert client.post("/roles", json={"title": "X", "required_skills": []}).status_code == 422
    bad_status = {"title": "X", "required_skills": ["A"], "status": "maybe"}
    assert client.post("/roles", json=bad_status).status_code == 422


def test_profiles_saved_without_a_model_are_embedded_at_match_time(clean_db, client, monkeypatch):
    """If the AI model is down when a profile is saved, matching fills the vector in later."""
    import app.api.profiles as profiles_api

    monkeypatch.setattr(profiles_api, "try_encode", lambda texts: (None, None))
    created = client.post(
        "/profiles", json={"full_name": "Late Embed", "email": "late@example.com", "skills": ["SQL"]}
    ).json()
    assert created["model_version"] is None

    role_id = client.post("/roles", json={"title": "Analyst", "required_skills": ["SQL"]}).json()["id"]
    matches = client.get(f"/roles/{role_id}/matches").json()["matches"]
    assert [m["employee_id"] for m in matches] == [created["id"]]
    assert client.get(f"/profiles/{created['id']}").json()["model_version"] == "hashing-v1"
