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
ADMIN_PASSWORD_PATH = AUTH_DIR / "admin_password.json"
ADMIN_COOKIE_NAME = "selfit_admin_session"
USER_COOKIE_NAME = "selfit_user_session"
ADMIN_CONSOLE_USER_ID = "admin_console"
ADMIN_MIN_PASSWORD_LEN = 6
DEFAULT_LOCAL_PHONE = "+8600000000000"
# 登录态保留 30 天：未主动退出时刷新/重进不再重新输入手机号（退出登录
# 会吊销服务端会话并清 cookie/localStorage）。
TOKEN_TTL_HOURS = 24 * 30
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
    # 带显式 + 前缀的按 E.164 国际号码处理（如海外用户）。
    if text.startswith("+") and 8 <= len(digits) <= 15:
        return f"+{digits}"
    # 不带前缀的裸输入按中国大陆手机号校验：1 + 第二位 3-9 + 共 11 位。
    # 只认 1 开头会放行 10x/12x 等未启用号段，位数不对也会被误当国际号建号。
    if re.fullmatch(r"1[3-9]\d{9}", digits):
        return f"+86{digits}"
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


def client_ip_from_request(request: Request) -> str:
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _invite_codes() -> list[str]:
    raw = os.getenv("SELFIT_INVITE_CODES", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _issue_session(data: dict[str, Any], user: dict[str, Any], now: datetime, provider: str, client_ip: str | None) -> str:
    token = secrets.token_urlsafe(32)
    session = {
        "session_id": secrets.token_urlsafe(12),
        "user_id": user["user_id"],
        "token_hash": _hash_secret(token),
        "status": "active",
        "auth_provider": provider,
        "source_ip": client_ip,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=TOKEN_TTL_HOURS)).isoformat(),
        "revoked_at": None,
    }
    data["auth_sessions"].append(session)
    return token


def verify_invite_login(invite_code: str, client_ip: str) -> dict[str, Any]:
    submitted = str(invite_code or "").strip()
    allowed = _invite_codes()
    if not allowed:
        raise HTTPException(status_code=503, detail="邀请码登录未配置，请联系管理员")
    if not submitted or not any(hmac.compare_digest(submitted, item) for item in allowed):
        raise HTTPException(status_code=400, detail="邀请码不正确，请检查后重试")

    now = datetime.now(timezone.utc)
    data = _load_store()
    user = next(
        (
            item
            for item in data["users"]
            if item.get("auth_provider") == "invite" and item.get("source_ip") == client_ip and item.get("status") == "active"
        ),
        None,
    )
    if user is None:
        user_id = sanitize_user_id("u_g" + hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:16])
        user = next((item for item in data["users"] if item.get("user_id") == user_id), None)
        if user is None:
            user = {
                "user_id": user_id,
                "phone_e164": None,
                "status": "active",
                "auth_provider": "invite",
                "source_ip": client_ip,
                "created_at": now.isoformat(),
                "last_login_at": now.isoformat(),
            }
            data["users"].append(user)
    else:
        user["last_login_at"] = now.isoformat()

    hydrate_user_from_demo_data(str(user["user_id"]))
    token = _issue_session(data, user, now, "invite", client_ip)
    _write_store(data)
    return {
        "status": "ok",
        "access_token": token,
        "token_type": "bearer",
        "expires_in_seconds": TOKEN_TTL_HOURS * 3600,
        "user": _public_user(user),
    }


def _phone_direct_enabled() -> bool:
    # 线下路演默认放开免短信验证码的手机号直接登录；正式运营可设 SELFIT_AUTH_ALLOW_PHONE_DIRECT=0 关闭。
    return env_flag("SELFIT_AUTH_ALLOW_PHONE_DIRECT", True)


def verify_phone_direct_login(phone: str, client_ip: str) -> dict[str, Any]:
    """手机号直接登录（无短信验证码、无 PIN）。

    适用前提：账号当前是"一次性测试 + 数据收集"定位——登录只为把测试资料
    挂到手机号上（user_id = 手机号哈希），账号内无历史回看等资产可盗。
    正式版接入短信验证码/微信登录后应设 SELFIT_AUTH_ALLOW_PHONE_DIRECT=0。

    账号规则：手机号即唯一账号（跨设备、跨 IP 同一手机号同一账号）。
    """

    if not _phone_direct_enabled():
        raise HTTPException(status_code=503, detail="手机号直接登录未开启，请使用验证码登录")
    phone_e164 = _normalize_phone(phone)
    now = datetime.now(timezone.utc)
    data = _load_store()
    user = next(
        (
            item
            for item in data["users"]
            if item.get("phone_e164") == phone_e164 and item.get("status") == "active"
        ),
        None,
    )
    if user is None:
        user_id = sanitize_user_id(
            "u_" + hashlib.sha256(phone_e164.encode("utf-8")).hexdigest()[:16]
        )
        user = next(
            (item for item in data["users"] if item.get("user_id") == user_id),
            None,
        )
        if user is None:
            user = {
                "user_id": user_id,
                "phone_e164": phone_e164,
                "status": "active",
                "auth_provider": "phone_direct",
                "source_ip": client_ip,
                "created_at": now.isoformat(),
                "last_login_at": now.isoformat(),
            }
            data["users"].append(user)
        else:
            user["phone_e164"] = phone_e164
            user["status"] = "active"

    user["last_login_at"] = now.isoformat()
    if not user.get("source_ip"):
        user["source_ip"] = client_ip

    hydrate_user_from_demo_data(str(user["user_id"]))
    token = _issue_session(data, user, now, "phone_direct", client_ip)
    _write_store(data)
    return {
        "status": "ok",
        "access_token": token,
        "token_type": "bearer",
        "expires_in_seconds": TOKEN_TTL_HOURS * 3600,
        "user": _public_user(user),
    }


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
    from app.beta_access import beta_access_for_user

    return {
        "user_id": user.get("user_id"),
        "phone_e164": user.get("phone_e164"),
        "status": user.get("status"),
        "created_at": user.get("created_at"),
        "last_login_at": user.get("last_login_at"),
        # 内测资格：登录后前端据此展示「后续功能」入口（服装拆款、AI 试穿等）。
        "beta_access": beta_access_for_user(user),
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


async def require_beta_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    """内测功能门禁：onboarding 之外的后续功能（服装拆款、电子衣橱、AI 试穿、AI 穿搭师）。

    线上（demo）模式只有内测白名单手机号和内部账号（admin/invite）可用；
    本地开发模式一律放行，保证调试与测试不被拦。
    普通用户被拦时返回 403 + 用户可读文案，前端引导等待正式开放。
    """

    user = await get_current_user(credentials)
    if user.get("beta_access"):
        return user
    raise HTTPException(status_code=403, detail="该功能正在内测中，暂未对你开放，敬请期待")


def _load_admin_password_record() -> dict[str, Any] | None:
    if not ADMIN_PASSWORD_PATH.exists():
        return None
    try:
        data = json.loads(ADMIN_PASSWORD_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("hash"):
            return data
    except json.JSONDecodeError:
        pass
    return None


def set_admin_password(new_password: str) -> None:
    """写入新的管理员密码哈希（后台修改密码用，立即生效）。"""

    text = str(new_password or "")
    if len(text) < ADMIN_MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"新密码至少 {ADMIN_MIN_PASSWORD_LEN} 位",
        )
    ADMIN_PASSWORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"hash": _hash_secret(text), "updated_at": _now_iso()}
    ADMIN_PASSWORD_PATH.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def verify_admin_password(password: str) -> bool:
    """管理员密码校验。

    优先级：后台修改过的密码文件 > SELFIT_ADMIN_PASSWORD 环境变量（初始种子）。
    env 密码首次验证成功后固化到文件，此后后台修改的密码优先生效。
    """

    text = str(password or "")
    record = _load_admin_password_record()
    if record is not None:
        return hmac.compare_digest(str(record.get("hash")), _hash_secret(text))
    env_password = os.getenv("SELFIT_ADMIN_PASSWORD", "")
    if env_password:
        set_admin_password(env_password)
        return hmac.compare_digest(_hash_secret(text), _hash_secret(env_password))
    return False


def admin_password_configured() -> bool:
    return _load_admin_password_record() is not None or bool(os.getenv("SELFIT_ADMIN_PASSWORD"))


def issue_admin_session(client_ip: str) -> str:
    """签发管理后台 session（auth_provider=admin，单例虚拟用户）。"""

    now = datetime.now(timezone.utc)
    data = _load_store()
    if not any(item.get("user_id") == ADMIN_CONSOLE_USER_ID for item in data["users"]):
        data["users"].append(
            {
                "user_id": ADMIN_CONSOLE_USER_ID,
                "phone_e164": None,
                "status": "active",
                "auth_provider": "admin",
                "created_at": now.isoformat(),
                "last_login_at": now.isoformat(),
            }
        )
    token = _issue_session(data, {"user_id": ADMIN_CONSOLE_USER_ID}, now, "admin", client_ip)
    _write_store(data)
    return token


def revoke_admin_sessions() -> None:
    """改密码后吊销全部管理员 session，强制重新登录。"""

    data = _load_store()
    changed = False
    for session in data["auth_sessions"]:
        if session.get("auth_provider") == "admin" and session.get("status") == "active":
            session["status"] = "revoked"
            session["revoked_at"] = _now_iso()
            changed = True
    if changed:
        _write_store(data)


def admin_token_from_request(request: Request) -> str | None:
    """管理后台 token 解析：Bearer header 优先，其次 admin cookie（QA 页面用）。"""

    value = request.headers.get("authorization") or ""
    scheme, _, token = value.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return request.cookies.get(ADMIN_COOKIE_NAME)


def user_token_from_request(request: Request) -> str | None:
    """普通用户 token 解析：Bearer header 优先，其次用户 session cookie。

    页面级网关（直接 GET /closet/demo 等）拿不到 Bearer header，
    登录时下发的 cookie 让浏览器导航也能带上内测身份。
    """

    value = request.headers.get("authorization") or ""
    scheme, _, token = value.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return request.cookies.get(USER_COOKIE_NAME)


def resolve_admin_user(token: str) -> dict[str, Any]:
    """校验 admin/invite session 并返回用户；普通用户 token 一律 403。"""

    user = resolve_token(token)
    data = _load_store()
    token_hash = _hash_secret(token)
    session = next(
        (
            item
            for item in data["auth_sessions"]
            if item.get("token_hash") == token_hash and item.get("status") == "active"
        ),
        None,
    )
    if session is None or session.get("auth_provider") not in {"admin", "invite"}:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def get_admin_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    """管理后台鉴权：仅 admin 密码登录或邀请码登录的内部账号可访问。

    普通用户（手机号登录）即使拿到 token 也无权访问 /admin/api/*。
    """

    token = (credentials.credentials if credentials else "") or request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录管理后台")
    return resolve_admin_user(token)


def current_token_from_request(request: Request) -> str | None:
    value = request.headers.get("authorization") or ""
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()
