from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.ops import env_flag, is_public_demo_mode
from app.storage import LOCAL_USER_ID, ROOT_DIR, hydrate_user_from_demo_data, sanitize_user_id


AUTH_DIR = ROOT_DIR / "outputs" / "auth"
AUTH_STORE_PATH = AUTH_DIR / "auth_store.json"
DEFAULT_LOCAL_PHONE = "+8600000000000"
TOKEN_TTL_HOURS = 24
CODE_TTL_MINUTES = 10
MAX_CODE_ATTEMPTS = 5

_bearer = HTTPBearer(auto_error=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_phone(phone: str) -> str:
    text = str(phone or "").strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("+") and 8 <= len(digits) <= 15:
        return f"+{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+86{digits}"
    if 8 <= len(digits) <= 15:
        return f"+{digits}"
    raise HTTPException(status_code=400, detail="手机号格式不正确")


def _hash_secret(secret: str) -> str:
    salt = os.getenv("SELFIT_AUTH_SECRET", "selfit-local-auth-secret")
    if is_public_demo_mode() and salt == "selfit-local-auth-secret":
        raise HTTPException(status_code=500, detail="认证密钥未配置，请联系 demo 管理员。")
    return hmac.new(salt.encode("utf-8"), secret.encode("utf-8"), hashlib.sha256).hexdigest()


def _load_store() -> dict[str, Any]:
    if not AUTH_STORE_PATH.exists():
        return {"version": 1, "users": [], "phone_login_codes": [], "auth_sessions": []}
    try:
        data = json.loads(AUTH_STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("version", 1)
            data.setdefault("users", [])
            data.setdefault("phone_login_codes", [])
            data.setdefault("auth_sessions", [])
            return data
    except json.JSONDecodeError:
        pass
    return {"version": 1, "users": [], "phone_login_codes": [], "auth_sessions": []}


def _write_store(data: dict[str, Any]) -> None:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = AUTH_STORE_PATH.with_name(f"{AUTH_STORE_PATH.name}.{secrets.token_urlsafe(8)}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(AUTH_STORE_PATH)


def ensure_local_user() -> dict[str, Any]:
    data = _load_store()
    for user in data["users"]:
        if user.get("user_id") == LOCAL_USER_ID:
            return user
    now = _now_iso()
    user = {
        "user_id": LOCAL_USER_ID,
        "phone_e164": DEFAULT_LOCAL_PHONE,
        "status": "active",
        "created_at": now,
        "last_login_at": now,
    }
    data["users"].append(user)
    _write_store(data)
    return user


def start_phone_login(phone: str) -> dict[str, Any]:
    phone_e164 = _normalize_phone(phone)
    code = os.getenv("SELFIT_AUTH_DEV_CODE", "0000")
    now = datetime.now(timezone.utc)
    code_id = secrets.token_urlsafe(12)
    data = _load_store()
    data["phone_login_codes"].append(
        {
            "code_id": code_id,
            "phone_e164": phone_e164,
            "code_hash": _hash_secret(code),
            "expires_at": (now + timedelta(minutes=CODE_TTL_MINUTES)).isoformat(),
            "attempt_count": 0,
            "consumed_at": None,
            "created_at": now.isoformat(),
        }
    )
    _write_store(data)
    response = {
        "status": "sent",
        "phone_e164": phone_e164,
        "code_id": code_id,
        "expires_in_seconds": CODE_TTL_MINUTES * 60,
    }
    if env_flag("SELFIT_AUTH_RETURN_DEV_CODE", not is_public_demo_mode()):
        response["dev_code"] = code
    return response


def verify_phone_login(phone: str, code: str) -> dict[str, Any]:
    phone_e164 = _normalize_phone(phone)
    submitted_code = str(code or "").strip()
    now = datetime.now(timezone.utc)
    data = _load_store()
    candidates = [
        item
        for item in data["phone_login_codes"]
        if item.get("phone_e164") == phone_e164 and not item.get("consumed_at")
    ]
    candidates.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    login_code = candidates[0] if candidates else None
    if login_code is None:
        raise HTTPException(status_code=400, detail="验证码不存在或已失效")
    expires_at = _parse_iso(login_code.get("expires_at"))
    if expires_at is None or expires_at < now:
        raise HTTPException(status_code=400, detail="验证码已过期")
    if int(login_code.get("attempt_count") or 0) >= MAX_CODE_ATTEMPTS:
        raise HTTPException(status_code=400, detail="验证码尝试次数过多")
    mock_codes = set()
    if env_flag("SELFIT_AUTH_ALLOW_MOCK_CODES", not is_public_demo_mode()):
        mock_codes = {item.strip() for item in os.getenv("SELFIT_AUTH_MOCK_CODES", "0000,0001").split(",") if item.strip()}
    code_matches = submitted_code in mock_codes or hmac.compare_digest(str(login_code.get("code_hash") or ""), _hash_secret(submitted_code))
    if not code_matches:
        login_code["attempt_count"] = int(login_code.get("attempt_count") or 0) + 1
        _write_store(data)
        raise HTTPException(status_code=400, detail="验证码不正确")

    user = _find_or_create_user(data, phone_e164, now)
    hydrate_user_from_demo_data(str(user["user_id"]))
    login_code["consumed_at"] = now.isoformat()
    token = secrets.token_urlsafe(32)
    session = {
        "session_id": secrets.token_urlsafe(12),
        "user_id": user["user_id"],
        "token_hash": _hash_secret(token),
        "status": "active",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=TOKEN_TTL_HOURS)).isoformat(),
        "revoked_at": None,
    }
    data["auth_sessions"].append(session)
    _write_store(data)
    return {
        "status": "ok",
        "access_token": token,
        "token_type": "bearer",
        "expires_in_seconds": TOKEN_TTL_HOURS * 3600,
        "user": _public_user(user),
    }


def _find_or_create_user(data: dict[str, Any], phone_e164: str, now: datetime) -> dict[str, Any]:
    if phone_e164 == DEFAULT_LOCAL_PHONE:
        for user in data["users"]:
            if user.get("user_id") == LOCAL_USER_ID:
                user["phone_e164"] = DEFAULT_LOCAL_PHONE
                user["last_login_at"] = now.isoformat()
                return user
        user = {
            "user_id": LOCAL_USER_ID,
            "phone_e164": DEFAULT_LOCAL_PHONE,
            "status": "active",
            "created_at": now.isoformat(),
            "last_login_at": now.isoformat(),
        }
        data["users"].append(user)
        return user
    for user in data["users"]:
        if user.get("phone_e164") == phone_e164:
            user["last_login_at"] = now.isoformat()
            return user
    user_id = sanitize_user_id("u_" + hashlib.sha256(phone_e164.encode("utf-8")).hexdigest()[:16])
    user = {
        "user_id": user_id,
        "phone_e164": phone_e164,
        "status": "active",
        "created_at": now.isoformat(),
        "last_login_at": now.isoformat(),
    }
    data["users"].append(user)
    return user


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user.get("user_id"),
        "phone_e164": user.get("phone_e164"),
        "status": user.get("status"),
        "created_at": user.get("created_at"),
        "last_login_at": user.get("last_login_at"),
    }


def resolve_token(token: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    data = _load_store()
    token_hash = _hash_secret(token)
    session = next(
        (
            item
            for item in data["auth_sessions"]
            if item.get("token_hash") == token_hash and item.get("status") == "active" and not item.get("revoked_at")
        ),
        None,
    )
    if session is None:
        raise HTTPException(status_code=401, detail="请先登录")
    expires_at = _parse_iso(session.get("expires_at"))
    if expires_at is None or expires_at < now:
        session["status"] = "expired"
        _write_store(data)
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = next((item for item in data["users"] if item.get("user_id") == session.get("user_id")), None)
    if user is None or user.get("status") != "active":
        raise HTTPException(status_code=401, detail="用户不可用")
    return _public_user(user)


def revoke_token(token: str) -> dict[str, Any]:
    data = _load_store()
    token_hash = _hash_secret(token)
    for session in data["auth_sessions"]:
        if session.get("token_hash") == token_hash and session.get("status") == "active":
            session["status"] = "revoked"
            session["revoked_at"] = _now_iso()
            _write_store(data)
            return {"status": "logged_out"}
    return {"status": "logged_out"}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="请先登录")
    return resolve_token(credentials.credentials)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any] | None:
    if credentials is None or not credentials.credentials:
        return None
    return resolve_token(credentials.credentials)


def current_token_from_request(request: Request) -> str | None:
    value = request.headers.get("authorization") or ""
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()
