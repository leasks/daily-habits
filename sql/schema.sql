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
