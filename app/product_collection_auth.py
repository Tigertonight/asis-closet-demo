"""Independent password/session store for the merchant intake administration."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

AUTH_DB = Path(__file__).resolve().parents[1] / 'outputs/product_collection/admin.sqlite3'
COOKIE = 'product_collection_admin_session'
PREFIX = '/product-collection-admin'
SESSION_SECONDS = 24 * 3600
PRIVATE = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'}
_login_slots = anyio.CapacityLimiter(2)
router = APIRouter(prefix=PREFIX + '/api', tags=['product-collection-admin'])


@contextmanager
def database():
    AUTH_DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(AUTH_DB, timeout=10)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS password (id INTEGER PRIMARY KEY CHECK(id=1), salt TEXT NOT NULL, digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, expires REAL NOT NULL);
        ''')
        AUTH_DB.chmod(0o600)
        with db:
            yield db
    finally:
        db.close()


def password_digest(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()


def configure_password(password):
    if not 16 <= len(password) <= 128:
        raise ValueError('管理员密码需为 16–128 位')
    salt = secrets.token_hex(16)
    digest = password_digest(password, salt)
    with database() as db:
        db.execute('INSERT OR REPLACE INTO password VALUES(1,?,?)', (salt, digest))
        db.execute('DELETE FROM sessions')


def issue_session(password):
    with database() as db:
        record = db.execute('SELECT salt,digest FROM password WHERE id=1').fetchone()
    if record is None:
        raise HTTPException(503, '管理入口尚未配置，请联系活动负责人。', headers=PRIVATE)
    if not hmac.compare_digest(password_digest(password, record[0]), record[1]):
        raise HTTPException(401, '密码不正确，请重新输入。', headers=PRIVATE)
    token = 'pca_' + secrets.token_urlsafe(32)
    with database() as db:
        # Serialize with password rotation so it also invalidates in-flight logins.
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT salt,digest FROM password WHERE id=1').fetchone() != record:
            raise HTTPException(401, '密码已更新，请重新登录。', headers=PRIVATE)
        db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
        db.execute('INSERT INTO sessions VALUES(?,?)', (hashlib.sha256(token.encode()).hexdigest(), time.time() + SESSION_SECONDS))
    return token


def require_collection_admin(request: Request):
    token = request.cookies.get(COOKIE, '')
    if not token.startswith('pca_') or len(token) != 47:
        raise HTTPException(401, '请先登录商品信息管理后台。', headers=PRIVATE)
    with database() as db:
        row = db.execute('SELECT expires FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if row is None or row[0] <= time.time():
        raise HTTPException(401, '登录已失效，请重新登录。', headers=PRIVATE)
    return {'role': 'product_collection_admin'}


def check_origin(request):
    origin = request.headers.get('origin')
    if (origin and origin != str(request.base_url).rstrip('/')) or request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, '请从商品信息管理页面操作。', headers=PRIVATE)


class LoginPayload(BaseModel):
    password: str = Field(min_length=1, max_length=128)


@router.post('/login')
async def login(request: Request, payload: LoginPayload):
    check_origin(request)
    # Bound password hashing independently from photo workers and default threads.
    token = await anyio.to_thread.run_sync(issue_session, payload.password, limiter=_login_slots)
    response = JSONResponse({'status': 'ok', 'expiresInSeconds': SESSION_SECONDS}, headers=PRIVATE)
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=request.url.scheme == 'https', samesite='strict', path=PREFIX)
    return response


@router.get('/session')
def session(admin=Depends(require_collection_admin)):
    return JSONResponse(admin, headers=PRIVATE)


@router.post('/logout')
def logout(request: Request):
    check_origin(request)
    token = request.cookies.get(COOKIE, '')
    if token:
        with database() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
    response = JSONResponse({'status': 'ok'}, headers=PRIVATE)
    response.delete_cookie(COOKIE, path=PREFIX, httponly=True, secure=request.url.scheme == 'https', samesite='strict')
    return response
