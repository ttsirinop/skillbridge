# SkillBridge (Alpha)

SkillBridge matches employees to open internal project roles. It turns each employee's skill profile
and each role's requirements into Sentence-BERT embeddings, then uses pgvector similarity search to
recommend the closest internal candidates.

CMSC 495 team project. Alpha release for Unit 5.

| Team member | Role | Owns |
|---|---|---|
| Thitti | Lead Architect | Repo structure, database schema, CI pipeline, README |
| Jamari | Interface Designer | Profile and role API, CSV import, OpenAPI spec, matching endpoint |
| Camden | Integration Lead | AI matching engine (covered by Thitti and Jamari for the Alpha) |

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

Install the AI model (Sentence-BERT). The CPU build of PyTorch keeps the download small:

```bash
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-ai.txt
```

The first run downloads the `all-MiniLM-L6-v2` model (about 90 MB) and caches it.

## Usage

Start the API:

```bash
uvicorn app.main:app --reload
```

- Interactive API docs: http://localhost:8000/docs
- Liveness check: `GET /health`
- Database check: `GET /health/db`

Load the sample data and see the AI's top matches for three demo roles:

```bash
python -m scripts.seed_demo
```

### Endpoints

| Method and path | What it does |
|---|---|
| `POST /profiles` | Create an employee and skill profile (409 if the email exists) |
| `GET /profiles?limit=&offset=` | List profiles |
| `GET /profiles/{employee_id}` | Get one profile |
| `POST /profiles/import` | Upload a CSV of profiles; creates new ones, updates existing emails |
| `POST /roles` | Create a role profile with required skills |
| `GET /roles?status=open` | List roles, optionally by status |
| `GET /roles/{role_id}` | Get one role |
| `GET /roles/{role_id}/matches?limit=10` | **AI feature:** top internal candidates for the role, best first |

The full contract, with every field, type, and limit, is in `docs/openapi.json`. After changing an
endpoint or a model in `app/schemas.py`, run `python -m scripts.export_openapi` and commit the result;
CI fails if the code and the committed spec disagree.

### CSV import format

UTF-8, up to 1,000 rows and 1 MB. Columns: `full_name`, `email`, `skills` (required) and
`department`, `summary` (optional). Separate skills with semicolons. See `data/sample_profiles.csv`.

```csv
full_name,email,department,skills,summary
Avery Brooks,avery.brooks@example.com,Engineering,Python; FastAPI; PostgreSQL,Backend developer
```

Bad rows don't stop the import. The response lists each one with its line number and field:

```json
{"created": 49, "updated": 0, "errors": [{"row": 7, "field": "email", "message": "..."}]}
```

### How matching works

1. Each profile and role is turned into text (title, skills, summary) and embedded with Sentence-BERT.
2. `GET /roles/{id}/matches` ranks profiles by cosine similarity using pgvector's HNSW index.
3. Each result includes the score and the required skills the employee shares, so a manager can see
   why someone was recommended. Results are saved to `match_results` with the model version.

If the model is unavailable when a profile is saved, the profile is still stored, and its vector is
filled in the next time matching runs. If the model is unavailable at match time, the API returns
`503 {"detail": "AI model unavailable"}`.

## Running tests and lint

```bash
ruff check .
pytest -v
```

Tests marked `db` need a running database and `DATABASE_URL` set. Without it they're skipped locally.
GitHub Actions runs all of them on every push and pull request to `main` and `develop`, using a
pgvector service container.

The test suite uses `EMBEDDING_BACKEND=hashing`, a deterministic stand-in for the model, so most tests
run in seconds without PyTorch. A second CI job, `ai-model`, installs the real Sentence-BERT model and
runs the tests marked `ai` (`pytest -m ai`) on every push, so the AI feature itself is always tested.

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
- All input is validated before it reaches the database: email format, name and text lengths,
  at most 50 skills of 50 characters each, unknown fields rejected, and CSV uploads must be `.csv`
  files, capped at 1 MB and 1,000 rows by default (`MAX_UPLOAD_BYTES`, `MAX_IMPORT_ROWS`).
- Employee skill data is personal data. The Alpha uses sample data only; real deployments would need
  authentication, access control by role, and encryption in transit.
- Match results store the model version, so recommendations can be audited for bias and traced to
  the model that produced them.

## Known limitations and technical debt (Alpha)

- No authentication yet, so any client can read and write profiles.
- Embeddings are created on the request path. If the model changes, the first match request
  re-embeds every stale profile, which is fine for hundreds of rows but slow for tens of thousands.
  A background job should handle this before real deployment.
- `role_profiles.embedding` has no vector index yet; roles are looked up by id, so it isn't needed
  until roles are searched by similarity.
- ~~The CSV file limits are constants in code, not configuration.~~ Fixed after peer review: they are
  now `MAX_UPLOAD_BYTES` and `MAX_IMPORT_ROWS` environment variables (see `.env.example`).
