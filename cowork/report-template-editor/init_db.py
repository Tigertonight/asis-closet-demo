"""Idempotent schema creation for the report template editor."""
from __future__ import annotations

import psycopg


def load_db_props(path: str = "db.properties") -> dict[str, str]:
    props: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                props[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return props


SCHEMA = """
CREATE TABLE IF NOT EXISTS app_users (
    sso_id TEXT PRIMARY KEY,
    email TEXT,
    username TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS report_templates (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    data JSONB NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    seed_version INTEGER NOT NULL DEFAULT 0,
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_report_templates_updated_at
    ON report_templates (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_templates_deleted_at
    ON report_templates (deleted_at);

CREATE TABLE IF NOT EXISTS report_assets (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    oid OID NOT NULL,
    size BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_report_assets_created_at
    ON report_assets (created_at DESC);
"""


def main() -> None:
    props = load_db_props()
    if not props.get("db.host"):
        print("[init_db] db.properties 未找到或为空 — 跳过")
        return
    with psycopg.connect(
        host=props["db.host"],
        port=int(props["db.port"]),
        dbname=props["db.database"],
        user=props["db.username"],
        password=props["db.password"],
    ) as conn:
        conn.execute(SCHEMA)
        conn.commit()
    print("[init_db] done")


if __name__ == "__main__":
    main()
