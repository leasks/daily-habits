-- Application role ─────────────────────────────────────────────────────────
-- All application connections must authenticate as (or be granted) this role.
-- See README.md for setup instructions.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app') THEN
    CREATE ROLE app;
  END IF;
END$$;

-- Users
CREATE TABLE IF NOT EXISTS users (
    id                 SERIAL PRIMARY KEY,
    channel            VARCHAR(50)  NOT NULL,
    channel_user_id    VARCHAR(100) NOT NULL,
    pending_reply_type VARCHAR(20)  DEFAULT 'checkin',
    telegram_from_id   VARCHAR(100),
    created_at         TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (channel, channel_user_id)
);

-- Daily check-ins (morning)
CREATE TABLE IF NOT EXISTS daily_checkins (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER REFERENCES users(id),
    checkin_date  DATE NOT NULL,
    raw_message   TEXT,
    goals         JSONB,
    goal_updates  JSONB,
    importance    TEXT,
    constraints   TEXT,
    blocker       TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, checkin_date)
);

-- End-of-day reflections
CREATE TABLE IF NOT EXISTS daily_reflections (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER REFERENCES users(id),
    reflection_date  DATE NOT NULL,
    raw_message      TEXT,
    goals_progress   TEXT,
    wins             TEXT,
    challenges       TEXT,
    learnings        TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, reflection_date)
);

-- Durable memories for coaching context
CREATE TABLE IF NOT EXISTS memories (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    kind        VARCHAR(50),
    content     TEXT,
    importance  INTEGER DEFAULT 5,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Coaching outputs
CREATE TABLE IF NOT EXISTS coach_outputs (
    id            SERIAL PRIMARY KEY,
    checkin_id    INTEGER REFERENCES daily_checkins(id),
    model         VARCHAR(100),
    coaching_text TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security ──────────────────────────────────────────────────────────
-- Grant the app role access to all tables and sequences.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app;

-- Enable RLS on every table; FORCE ensures it applies to the table owner too.
ALTER TABLE users             ENABLE ROW LEVEL SECURITY;
ALTER TABLE users             FORCE ROW LEVEL SECURITY;

ALTER TABLE daily_checkins    ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_checkins    FORCE ROW LEVEL SECURITY;

ALTER TABLE daily_reflections ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_reflections FORCE ROW LEVEL SECURITY;

ALTER TABLE memories          ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories          FORCE ROW LEVEL SECURITY;

ALTER TABLE coach_outputs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE coach_outputs     FORCE ROW LEVEL SECURITY;

-- Allow the app role unrestricted row access.
-- Per-user data isolation is enforced at the application query level.
-- CREATE POLICY does not support IF NOT EXISTS, so each policy is created
-- inside a DO block that checks pg_policies first.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'users' AND policyname = 'app_all') THEN
    CREATE POLICY app_all ON users TO app USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'daily_checkins' AND policyname = 'app_all') THEN
    CREATE POLICY app_all ON daily_checkins TO app USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'daily_reflections' AND policyname = 'app_all') THEN
    CREATE POLICY app_all ON daily_reflections TO app USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'memories' AND policyname = 'app_all') THEN
    CREATE POLICY app_all ON memories TO app USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'coach_outputs' AND policyname = 'app_all') THEN
    CREATE POLICY app_all ON coach_outputs TO app USING (true) WITH CHECK (true);
  END IF;
END$$;
