-- 001: core GTM tables for the outbound campaign.
-- Applied by scripts/data.py (`python3 scripts/data.py migrate`).

CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT NOT NULL UNIQUE,
    name            TEXT,
    industry        TEXT,
    employee_count  INTEGER,
    country         TEXT,
    icp_tier        TEXT,            -- A / B / C
    source          TEXT,            -- clay, apollo, manual, ...
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER REFERENCES accounts(id),
    first_name      TEXT,
    last_name       TEXT,
    title           TEXT,
    email           TEXT UNIQUE,
    email_status    TEXT,            -- valid / risky / invalid / unknown
    linkedin_url    TEXT,
    persona         TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS campaigns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    channel         TEXT,            -- email / linkedin / multi
    status          TEXT DEFAULT 'draft',
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outreach_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id     INTEGER REFERENCES campaigns(id),
    contact_id      INTEGER REFERENCES contacts(id),
    event_type      TEXT NOT NULL,   -- sent / opened / replied / bounced / meeting_booked / unsubscribed
    step            INTEGER,
    occurred_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename        TEXT PRIMARY KEY,
    applied_at      TEXT DEFAULT (datetime('now'))
);
