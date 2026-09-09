"""Cowork-injected PostgreSQL configuration. No application data is written to disk."""
from pathlib import Path
import psycopg
from psycopg.rows import dict_row


def connect():
    props = {}
    for line in Path('db.properties').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            props[key.strip()] = value.strip()
    return psycopg.connect(host=props['db.host'], port=int(props['db.port']),
        dbname=props['db.database'], user=props['db.username'], password=props['db.password'],
        row_factory=dict_row, connect_timeout=10)


def initialize():
    with connect() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS app_users (
            sso_id TEXT PRIMARY KEY, username TEXT, email TEXT, updated_at TIMESTAMPTZ DEFAULT NOW())''')
        conn.execute('''CREATE TABLE IF NOT EXISTS tryon_reviews (
            review_key TEXT PRIMARY KEY, decision TEXT NOT NULL DEFAULT 'pending'
                CHECK(decision IN ('pending','approved','redo')),
            note TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 0,
            reviewer_id TEXT REFERENCES app_users(sso_id), reviewer_name TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW())''')
        conn.execute('''CREATE TABLE IF NOT EXISTS tryon_review_events (
            event_id BIGSERIAL PRIMARY KEY, review_key TEXT NOT NULL,
            decision TEXT NOT NULL, note TEXT NOT NULL, revision INTEGER NOT NULL,
            reviewer_id TEXT NOT NULL, reviewer_name TEXT, created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(review_key, revision))''')


def upsert_user(conn, user):
    conn.execute('''INSERT INTO app_users (sso_id, username, email) VALUES (%s,%s,%s)
        ON CONFLICT(sso_id) DO UPDATE SET username=EXCLUDED.username,
        email=EXCLUDED.email, updated_at=NOW()''', (str(user['userId']), user['name'], user['email']))
