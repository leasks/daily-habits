-- Migration 002: add telegram_from_id column to users table
-- Stores the Telegram sender user ID (from.id) so that incoming
-- replies can be validated against the registered sender.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS telegram_from_id VARCHAR(100);
