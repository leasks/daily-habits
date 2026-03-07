-- Migration 004: add goal_updates column to daily_checkins
-- Stores intraday goal updates without overwriting the original morning goals.
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS goal_updates JSONB;
