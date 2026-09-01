"""selfit report template editor — SSO + PostgreSQL + PG Large Objects."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import psycopg
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field


MAX_IMAGE_BYTES = 8 * 1024 * 1024
DATA_IMAGE_RE = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,(.+)$", re.DOTALL)
IMAGE_PATHS = (
    ("hero",),
    ("source", "avatars", "imageUrl"),
)
IMAGE_LIST_PATHS = ("makeup", "hair", "outfits")


def _load_props(path: str = "db.properties") -> dict[str, str]:
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


def _get_db_conn() -> psycopg.Connection:
    props = _load_props()
    if not props.get("db.host"):
        raise HTTPException(status_code=503, detail="db.properties 未配置")
    return psycopg.connect(
        host=props["db.host"],
        port=int(props["db.port"]),
        dbname=props["db.database"],
        user=props["db.username"],
        password=props["db.password"],
        row_factory=dict_row,
    )


def _parse_sso_user(decrypted_userinfo: Optional[str]) -> Optional[dict[str, Any]]:
    if not decrypted_userinfo:
        return None
    try:
        fixed = decrypted_userinfo.encode("latin-1").decode("utf-8")
        data = json.loads(fixed)
    except Exception:
        return None
    user_id = data.get("userId") or data.get("id")
    if not user_id:
        return None
    return {
        "userId": str(user_id),
        "username": data.get("username") or data.get("name") or data.get("displayName"),
        "email": data.get("email") or data.get("workEmail"),
    }


def _require_user(decrypted_userinfo: Optional[str]) -> dict[str, Any]:
    user = _parse_sso_user(decrypted_userinfo)
    if not user:
        raise HTTPException(status_code=401, detail="unauthenticated")
    return user


def _upsert_user(conn: psycopg.Connection, user: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO app_users (sso_id, email, username)
        VALUES (%s, %s, %s)
        ON CONFLICT (sso_id) DO UPDATE SET
            email = EXCLUDED.email,
            username = EXCLUDED.username,
            updated_at = NOW()
        """,
        (user["userId"], user.get("email"), user.get("username")),
    )


def _set_nested(payload: dict[str, Any], path: tuple[str, ...], value: str) -> None:
    cursor: Any = payload
    for key in path[:-1]:
        cursor = cursor.get(key)
        if not isinstance(cursor, dict):
            return
    if isinstance(cursor, dict):
        cursor[path[-1]] = value


def _get_nested(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    cursor: Any = payload
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def _save_data_image(
    conn: psycopg.Connection,
    source: Any,
    filename: str,
    user_id: str,
) -> Any:
    if not isinstance(source, str) or not source.startswith("data:image/"):
        return source
    match = DATA_IMAGE_RE.match(source)
    if not match:
        raise HTTPException(status_code=422, detail="图片格式不支持")
    try:
        blob = base64.b64decode(match.group(2), validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="图片数据损坏") from exc
    if len(blob) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="单张图片不能超过 8MB")
    content_type = match.group(1)
    asset_id = uuid.uuid4().hex
    oid = conn.execute("SELECT lo_from_bytea(0, %s) AS oid", (blob,)).fetchone()["oid"]
    conn.execute(
        """
        INSERT INTO report_assets
            (id, filename, content_type, oid, size, sha256, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            asset_id,
            filename,
            content_type,
            oid,
            len(blob),
            hashlib.sha256(blob).hexdigest(),
            user_id,
        ),
    )
    return f"/api/assets/{asset_id}"


def _materialize_images(
    conn: psycopg.Connection,
    data: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    result = deepcopy(data)
    code = str(result.get("code") or "template").lower()
    for image_path in IMAGE_PATHS:
        value = _get_nested(result, image_path)
        stable = _save_data_image(conn, value, f"{code}-{'-'.join(image_path)}", user_id)
        _set_nested(result, image_path, stable)
    for group in IMAGE_LIST_PATHS:
        items = result.get(group)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item["image"] = _save_data_image(
                conn,
                item.get("image"),
                f"{code}-{group}-{index + 1}",
                user_id,
            )
    return result


class TemplateSaveIn(BaseModel):
    expectedRevision: int = Field(ge=0)
    data: dict[str, Any]


class TemplateDeleteIn(BaseModel):
    expectedRevision: int = Field(ge=1)


def _template_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "code": row["code"],
        "data": row["data"],
        "revision": row["revision"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "createdBy": row["created_by"],
        "updatedBy": row["updated_by"],
    }


app = FastAPI(title="selfit 风格报告配置后台")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/bootstrap")
def bootstrap(
    decrypted_userinfo: Optional[str] = Header(None, alias="Decrypted-Userinfo"),
) -> dict[str, Any]:
    user = _require_user(decrypted_userinfo)
    with _get_db_conn() as conn:
        _upsert_user(conn, user)
        rows = conn.execute(
            """
            SELECT id, code, data, revision, created_by, updated_by, created_at, updated_at
            FROM report_templates
            WHERE deleted_at IS NULL
            ORDER BY COALESCE(NULLIF(data #>> '{masterData,index}', '')::INTEGER, 999), code
            """
        ).fetchall()
        conn.commit()
    return {"user": user, "templates": [_template_payload(row) for row in rows]}


@app.put("/api/templates/{template_id}")
def save_template(
    template_id: str,
    body: TemplateSaveIn,
    decrypted_userinfo: Optional[str] = Header(None, alias="Decrypted-Userinfo"),
) -> dict[str, Any]:
    user = _require_user(decrypted_userinfo)
    code = str(body.data.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(status_code=422, detail="英文代号不能为空")

    with _get_db_conn() as conn:
        _upsert_user(conn, user)
        current = conn.execute(
            """
            SELECT id, code, data, revision, created_by, updated_by, created_at, updated_at
            FROM report_templates
            WHERE id = %s AND deleted_at IS NULL
            FOR UPDATE
            """,
            (template_id,),
        ).fetchone()
        if current and current["revision"] != body.expectedRevision:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "模板已被其他页面更新",
                    "currentRevision": current["revision"],
                    "updatedBy": current["updated_by"],
                    "updatedAt": current["updated_at"].isoformat(),
                },
            )
        if not current and body.expectedRevision != 0:
            raise HTTPException(status_code=409, detail={"message": "模板版本已变化"})

        data = _materialize_images(conn, body.data, user["userId"])
        data["code"] = code
        data["updatedAt"] = datetime.now(timezone.utc).isoformat()
        if current:
            row = conn.execute(
                """
                UPDATE report_templates SET
                    code = %s,
                    data = %s,
                    revision = revision + 1,
                    updated_by = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, code, data, revision, created_by, updated_by, created_at, updated_at
                """,
                (code, Jsonb(data), user["userId"], template_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                INSERT INTO report_templates
                    (id, code, data, revision, created_by, updated_by)
                VALUES (%s, %s, %s, 1, %s, %s)
                RETURNING id, code, data, revision, created_by, updated_by, created_at, updated_at
                """,
                (template_id, code, Jsonb(data), user["userId"], user["userId"]),
            ).fetchone()
        conn.commit()
    return {"template": _template_payload(row), "savedBy": user}


@app.delete("/api/templates/{template_id}")
def delete_template(
    template_id: str,
    body: TemplateDeleteIn,
    decrypted_userinfo: Optional[str] = Header(None, alias="Decrypted-Userinfo"),
) -> dict[str, bool]:
    user = _require_user(decrypted_userinfo)
    with _get_db_conn() as conn:
        _upsert_user(conn, user)
        result = conn.execute(
            """
            UPDATE report_templates SET deleted_at = NOW(), updated_by = %s, updated_at = NOW()
            WHERE id = %s AND revision = %s AND deleted_at IS NULL
            """,
            (user["userId"], template_id, body.expectedRevision),
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=409, detail="模板已被其他页面更新")
        conn.commit()
    return {"ok": True}


@app.get("/api/assets/{asset_id}")
def get_asset(
    asset_id: str,
    decrypted_userinfo: Optional[str] = Header(None, alias="Decrypted-Userinfo"),
) -> Response:
    _require_user(decrypted_userinfo)
    with _get_db_conn() as conn:
        row = conn.execute(
            "SELECT content_type, oid, sha256 FROM report_assets WHERE id = %s",
            (asset_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="asset not found")
        blob = conn.execute("SELECT lo_get(%s) AS data", (row["oid"],)).fetchone()["data"]
    return Response(
        content=bytes(blob),
        media_type=row["content_type"],
        headers={"Cache-Control": "private, max-age=31536000, immutable", "ETag": row["sha256"]},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(Path("web/assets/selfit-wordmark.svg"), media_type="image/svg+xml")


app.mount("/", StaticFiles(directory="web", html=True), name="web")
