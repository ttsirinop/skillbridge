# SkillBridge (Alpha)

SkillBridge matches employees to open internal project roles. It turns each employee's skill profile
and each role's requirements into Sentence-BERT embeddings, then uses pgvector similarity search to
recommend the closest internal candidates.

CMSC 495 team project. Alpha release for Unit 5.

| Team member | Role | Owns |
|---|---|---|
| Thitti | Lead Architect | Repo structure, database schema, CI pipeline, README |
| Jamari | Interface Designer | Profile and role API, CSV import, OpenAPI spec |
| Camden | Integration Lead | AI matching engine (embeddings and ranking) |

## Architecture

```
Client ──HTTP──> FastAPI app (app/main.py)
                   ├── app/api/        profile, role, and CSV import endpoints
                   ├── app/matching/   Sentence-BERT embeddings + top-N ranking
                   └── app/db/         connections and schema setup
                                 │
                                 v
                   PostgreSQL 16 + pgvector (db/schema.sql)
```

Each module talks to the others only through function calls in its package, and only `app/db`
opens database connections. The engine works on the standardized skill-profile and role-profile
tables, never on raw resumes.

## Requirements

- Python 3.11 or newer
- Docker (for the local PostgreSQL + pgvector database)
- Git

## Install

```bash
git clone <repo-url>
cd skillbridge

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # then edit if needed
docker compose up -d db            # start PostgreSQL + pgvector
python -m app.db.connection        # create the tables and indexes
```

## Usage

Start the API:

```bash
uvicorn app.main:app --reload
```

- Interactive API docs: http://localhost:8000/docs
- Liveness check: `GET /health`
- Database check: `GET /health/db`

## Running tests and lint

```bash
ruff check .
pytest -v
```

Tests marked `db` need a running database and `DATABASE_URL` set. Without it they're skipped locally.
GitHub Actions runs all of them on every push and pull request to `main` and `develop`, using a
pgvector service container.

## Branching and pull requests

- `main`: release-ready code only (tagged releases, e.g. `v0.1.0-alpha`)
- `develop`: integration branch; all feature work merges here first
- `feature/<short-name>`: one branch per task, branched from `develop`

Every pull request needs a passing CI run and one teammate's approval. Use the PR template, and mark
any AI-generated code in it.

## Error handling

- If the database can't be reached, the API returns `503 {"detail": "Database unavailable"}` and
  logs the details on the server, without exposing connection info to the client.
- The schema enforces data rules: required fields, unique employee emails, length limits, allowed
  role statuses, and score ranges.
- Database writes run in a transaction that rolls back on any error, so a failed request doesn't
  leave partial data behind.

## Security considerations

- Configuration and credentials come from environment variables (`.env`, never committed). The
  credentials in `docker-compose.yml` and `.env.example` are for local development only.
- SQL uses parameterized queries only, never string formatting, to prevent SQL injection.
- `ruff` runs Bandit security rules (`S`) in CI.
- Employee skill data is personal data. The Alpha uses sample data only; real deployments would need
  authentication, access control by role, and encryption in transit.
- Match results store the model version, so recommendations can be audited for bias and traced to
  the model that produced them.

## Known limitations (Alpha)

- No authentication yet.
- Changing the embedding model requires re-embedding all stored profiles (tracked by `model_version`).
