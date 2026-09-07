"""Insert missing personality templates without overwriting existing rows."""
from __future__ import annotations

import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from init_db import load_db_props


def main() -> None:
    props = load_db_props()
    if not props.get("db.host"):
        print("[seed_db] db.properties 未找到或为空 — 跳过")
        return

    payload = json.loads(
        Path("web/assets/16-personality-templates.json").read_text(encoding="utf-8")
    )
    seed_version = int(payload.get("seedVersion") or 0)

    with psycopg.connect(
        host=props["db.host"],
        port=int(props["db.port"]),
        dbname=props["db.database"],
        user=props["db.username"],
        password=props["db.password"],
    ) as conn:
        for template in payload.get("templates", []):
            type_id = str(template.get("masterData", {}).get("typeId") or "").strip()
            code = str(template.get("code") or "").strip().upper()
            body_profile = template.get("bodyProfile") or "standard"
            gender = template.get("gender") or "unisex"
            template_id = type_id or code.lower()
            if body_profile != "standard":
                template_id += "-" + body_profile
            if gender != "unisex":
                template_id += "-" + gender
            if not template_id or not code:
                continue
            conn.execute(
                """
                INSERT INTO report_templates
                    (id, code, data, revision, seed_version, created_by, updated_by)
                SELECT %s, %s, %s, 1, %s, 'system:seed', 'system:seed'
                WHERE NOT EXISTS (
                    SELECT 1 FROM report_templates WHERE code = %s
                    AND COALESCE(data->>'bodyProfile', 'standard') = %s
                    AND COALESCE(data->>'gender', 'unisex') = %s
                )
                ON CONFLICT (id) DO NOTHING
                """,
                (template_id, code, Jsonb(template), seed_version, code, body_profile, gender),
            )
        conn.commit()
    print("[seed_db] inserted missing templates only")


if __name__ == "__main__":
    main()
