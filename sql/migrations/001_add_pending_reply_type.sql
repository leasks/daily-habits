-- Migration 001: add pending_reply_type column to users table
-- This column tracks what kind of reply is expected from a user
-- so the webhook can route incoming messages correctly.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS pending_reply_type VARCHAR(20) DEFAULT 'checkin';
