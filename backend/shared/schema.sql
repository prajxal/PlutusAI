-- PlutusAI schema.
--
-- Shape of the bargain: anything we filter, join or sort on is a real column
-- with a real type; everything else lives in a JSONB payload. Adding a field
-- to a record, a scenario or a business therefore needs no DDL and no
-- migration -- which is where schema churn actually comes from.
--
-- Safe to run repeatedly; the application runs it at startup.

CREATE TABLE IF NOT EXISTS businesses (
    business_id TEXT PRIMARY KEY,
    name        TEXT,
    meta        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    email         TEXT UNIQUE,
    password_hash TEXT,
    business_id   TEXT NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One product's trading on one day, optionally split by a further dimension
-- such as store or channel. That UNIQUE constraint is the whole reason two
-- outlets selling the same item on the same day do not overwrite each other.
CREATE TABLE IF NOT EXISTS records (
    id          BIGSERIAL PRIMARY KEY,
    business_id TEXT  NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    record_date DATE  NOT NULL,
    product     TEXT  NOT NULL,
    dimension   TEXT  NOT NULL DEFAULT '',
    payload     JSONB NOT NULL,
    UNIQUE (business_id, record_date, product, dimension)
);
CREATE INDEX IF NOT EXISTS records_business_date ON records (business_id, record_date);
CREATE INDEX IF NOT EXISTS records_business_product ON records (business_id, product);

CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload     JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS scenarios_business_recent ON scenarios (business_id, created_at DESC);

-- business_id is stored on every turn so ownership can be checked before a
-- conversation is loaded, not after.
CREATE TABLE IF NOT EXISTS session_turns (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    business_id TEXT NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    tool_calls  JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '30 days'
);
CREATE INDEX IF NOT EXISTS session_turns_session ON session_turns (session_id, created_at);
