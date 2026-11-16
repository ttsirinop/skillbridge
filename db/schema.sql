-- SkillBridge database schema (PostgreSQL 16 + pgvector)
-- Owner: Lead Architect. Change via pull request only.
--
-- Embedding size is 384 to match Sentence-BERT all-MiniLM-L6-v2.
-- If the Integration Lead changes the model, change the vector size here
-- and re-embed every row (see model_version columns).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS employees (
    id          SERIAL PRIMARY KEY,
    full_name   TEXT        NOT NULL CHECK (length(full_name) BETWEEN 1 AND 200),
    email       TEXT        NOT NULL UNIQUE,
    department  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One skill profile per employee: the standardized "skill profile" from our pitch.
CREATE TABLE IF NOT EXISTS skill_profiles (
    employee_id    INTEGER     PRIMARY KEY REFERENCES employees(id) ON DELETE CASCADE,
    skills         TEXT[]      NOT NULL DEFAULT '{}',
    summary        TEXT        NOT NULL DEFAULT '',
    embedding      vector(384),
    model_version  TEXT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The standardized "role profile" a project manager creates.
CREATE TABLE IF NOT EXISTS role_profiles (
    id               SERIAL PRIMARY KEY,
    title            TEXT        NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    description      TEXT        NOT NULL DEFAULT '',
    required_skills  TEXT[]      NOT NULL DEFAULT '{}',
    status           TEXT        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'filled', 'closed')),
    embedding        vector(384),
    model_version    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stored recommendations so results can be audited and explained later.
CREATE TABLE IF NOT EXISTS match_results (
    id             SERIAL PRIMARY KEY,
    role_id        INTEGER     NOT NULL REFERENCES role_profiles(id) ON DELETE CASCADE,
    employee_id    INTEGER     NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    score          REAL        NOT NULL CHECK (score BETWEEN -1 AND 1),
    model_version  TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (role_id, employee_id, model_version)
);

-- Approximate nearest-neighbor index for cosine similarity (scalability risk mitigation).
CREATE INDEX IF NOT EXISTS skill_profiles_embedding_hnsw
    ON skill_profiles USING hnsw (embedding vector_cosine_ops);
