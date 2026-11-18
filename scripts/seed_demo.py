"""Load the sample profiles and a few roles, then print the AI's top matches for each role.

    python -m scripts.seed_demo

Uses the same API the app exposes, so this doubles as a quick manual integration check.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.db.connection import init_schema
from app.main import app

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample_profiles.csv"

DEMO_ROLES = [
    {
        "title": "Backend Developer",
        "description": "Build the SkillBridge API and database layer.",
        "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    },
    {
        "title": "Security Analyst",
        "description": "Monitor alerts and lead incident response.",
        "required_skills": ["Incident Response", "SIEM", "Splunk", "Threat Hunting"],
    },
    {
        "title": "Data Scientist",
        "description": "Build and evaluate predictive models.",
        "required_skills": ["Python", "scikit-learn", "Machine Learning", "Statistics"],
    },
]


def main() -> None:
    init_schema()
    client = TestClient(app)
    with SAMPLE_CSV.open("rb") as fh:
        result = client.post("/profiles/import", files={"file": ("sample.csv", fh, "text/csv")})
    result.raise_for_status()
    print(f"Imported profiles: {result.json()}")

    for role in DEMO_ROLES:
        created = client.post("/roles", json=role)
        created.raise_for_status()
        matches = client.get(f"/roles/{created.json()['id']}/matches?limit=5")
        matches.raise_for_status()
        body = matches.json()
        print(f"\n{role['title']} (model: {body['model_version']})")
        for rank, m in enumerate(body["matches"], start=1):
            shared = ", ".join(m["matched_skills"])
            print(f"  {rank}. {m['full_name']:<22} score={m['score']:.3f}  shared: {shared}")


if __name__ == "__main__":
    main()
