"""Cowork fastapi-only scaffold — minimal hello + /health.

按 Cowork Guard 子应用规范开发：
  - 用 Decrypted-Userinfo header 拿用户身份（_parse_sso_user）
  - 持久化用 db.properties + psycopg[binary] (PostgreSQL)
  - /health 返 JSON 给 health.sh 探测
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import BaseModel, Field
from db import connect, initialize, upsert_user

ROOT = Path(__file__).resolve().parent
CATALOG = json.loads((ROOT / 'seeds/catalog.json').read_text())
RESULTS = {r['reviewKey']: r for o in CATALOG['outfits'] for r in o['results']}


def _load_db_properties(path: str = "db.properties") -> dict[str, str]:
    p = Path(__file__).resolve().parent / path
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _parse_sso_user(decrypted_userinfo: Optional[str]) -> Optional[dict]:
    """从 Decrypted-Userinfo header 解 SSO 用户（latin-1 → JSON 两步）。

    生产环境上 Cowork Guard 网关会注入 header；header 值是被 HTTP 层用 latin-1
    解码过的 UTF-8 字节，必须重编码后才能 json.loads。

    本地 dev 调试时 header 缺失，不走任何环境变量 bypass，请用浏览器插件
    （ModHeader / Header Editor）手动注入一段 mock JSON。安全规范不允许
    “生产跳 SSO”类后门（precheck 会拦）。
    """
    if not decrypted_userinfo:
        return None
    try:
        fixed = decrypted_userinfo.encode("latin-1").decode("utf-8")
        data = json.loads(fixed)
    except Exception:
        return None
    if not isinstance(data, dict) or not (data.get('userId') or data.get('id')):
        return None
    return {
        "email": data.get("email") or data.get("workEmail"),
        "name": data.get("username") or data.get("name") or data.get("displayName"),
        "userId": data.get("userId") or data.get("id"),
        "raw": data,
    }


def _require_user(decrypted_userinfo: Optional[str]) -> dict:
    """拿不到用户 → 401，Cowork Guard 会自动跳 SSO 登录页。所有业务路由 MUST 调。"""
    user = _parse_sso_user(decrypted_userinfo)
    if not user:
        raise HTTPException(status_code=401, detail="unauthenticated")
    return user


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="selfit 试穿素材审核", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/")
def index(decrypted_userinfo: Optional[str] = Header(None, alias='Decrypted-Userinfo')):
    _require_user(decrypted_userinfo)
    return FileResponse(ROOT / 'web/index.html')


@app.get('/web/{filename}')
def web_asset(filename: str):
    if filename not in {'app.js', 'style.css'}:
        raise HTTPException(404)
    return FileResponse(ROOT / 'web' / filename)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": "1.1.0"}


@app.get("/whoami")
def whoami(
    decrypted_userinfo: Optional[str] = Header(None, alias="Decrypted-Userinfo"),
) -> JSONResponse:
    user = _require_user(decrypted_userinfo)
    return JSONResponse({"email": user["email"], "name": user["name"], "userId": user["userId"]})


@app.get('/api/catalog')
def catalog(decrypted_userinfo: Optional[str] = Header(None, alias='Decrypted-Userinfo')):
    user = _require_user(decrypted_userinfo)
    with connect() as conn:
        upsert_user(conn, user)
        reviews = conn.execute('SELECT * FROM tryon_reviews').fetchall()
    return {**CATALOG,
            'user': {'name': user['name'] or user['email']},
            'reviews': {r['review_key']: r for r in reviews if r['review_key'] in RESULTS}}


class ReviewUpdate(BaseModel):
    reviewKey: str = Field(max_length=300)
    decision: Literal['pending', 'approved', 'redo']
    note: str = Field(default='', max_length=2000)
    revision: int = Field(ge=0)


def validate_review(body):
    result = RESULTS.get(body.reviewKey)
    if result is None:
        raise HTTPException(404, '这张图片已更新，请刷新后重试。')
    if body.decision == 'approved' and not result['image']:
        raise HTTPException(422, '缺少试穿结果，无法标记通过。')
    if body.decision == 'redo' and not body.note.strip():
        raise HTTPException(422, '请说明需要重做的原因。')


@app.put('/api/review')
def save_review(body: ReviewUpdate, decrypted_userinfo: Optional[str] = Header(None, alias='Decrypted-Userinfo')):
    user = _require_user(decrypted_userinfo)
    validate_review(body)
    with connect() as conn:
        upsert_user(conn, user)
        conn.execute('''INSERT INTO tryon_reviews(review_key) VALUES (%s)
            ON CONFLICT(review_key) DO NOTHING''', (body.reviewKey,))
        current = conn.execute('SELECT * FROM tryon_reviews WHERE review_key=%s FOR UPDATE', (body.reviewKey,)).fetchone()
        if current['revision'] != body.revision:
            raise HTTPException(409, '其他审核人已更新这张图片，请刷新后查看最新记录。')
        row = conn.execute('''UPDATE tryon_reviews SET decision=%s, note=%s,
            revision=revision+1, reviewer_id=%s, reviewer_name=%s, updated_at=NOW()
            WHERE review_key=%s RETURNING *''',
            (body.decision, body.note.strip(), str(user['userId']), user['name'] or user['email'], body.reviewKey)).fetchone()
        conn.execute('''INSERT INTO tryon_review_events
            (review_key,decision,note,revision,reviewer_id,reviewer_name) VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT(review_key,revision) DO NOTHING''',
            (row['review_key'],row['decision'],row['note'],row['revision'],row['reviewer_id'],row['reviewer_name']))
    return row


@app.get('/api/export')
def export(decrypted_userinfo: Optional[str] = Header(None, alias='Decrypted-Userinfo')):
    _require_user(decrypted_userinfo)
    with connect() as conn:
        reviews = conn.execute('SELECT * FROM tryon_reviews ORDER BY review_key').fetchall()
        events = conn.execute('SELECT * FROM tryon_review_events ORDER BY event_id').fetchall()
    return Response(json.dumps({'schemaVersion': 1, 'batchId': CATALOG['batchId'],
        'outfits': CATALOG['outfits'], 'reviews': reviews, 'history': events}, ensure_ascii=False, default=str, indent=2),
        media_type='application/json', headers={'Content-Disposition': 'attachment; filename="selfit-tryon-reviews.json"'})
