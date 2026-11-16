from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_db_down_returns_503(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:wrong@127.0.0.1:1/none")
    response = client.get("/health/db")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
