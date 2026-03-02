-- Migration 003: Enable Row Level Security on all tables
--
-- Without RLS any database user that can connect to the database is able to
-- read and modify every row in every table, regardless of which application
-- user the data belongs to.  Enabling RLS closes this gap by ensuring that
-- only the designated application role ('app') can access rows.
--
-- Prerequisites:
--   The application's DATABASE_URL must authenticate as a role that has been
--   granted the 'app' role (or is named 'app').  Example:
--
--     CREATE ROLE app LOGIN PASSWORD '...';
--     GRANT app TO <your_db_user>;   -- if using a different login role
--
-- This migration is idempotent: re-running it on a database where RLS is
-- already enabled will not cause errors.

-- ── 1. Create the application role if it does not already exist ──────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app') THEN
    CREATE ROLE app;
  END IF;
END$$;

-- ── 2. Grant the app role access to all existing tables and sequences ────────
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app;

-- ── 3. Enable Row Level Security ─────────────────────────────────────────────
-- FORCE ROW LEVEL SECURITY ensures the policy applies even to the table owner.
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

-- ── 4. Allow the app role full access to all rows ────────────────────────────
-- The application manages per-user data isolation at the query level;
-- the policy here simply gates access to the trusted application role.
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
