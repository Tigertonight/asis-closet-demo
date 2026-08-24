from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def deployment_mode() -> str:
    return (os.getenv("SELFIT_ENV") or os.getenv("APP_ENV") or "local").strip().lower()


def is_public_demo_mode() -> bool:
    return deployment_mode() in {"production", "prod", "demo", "staging"} or env_flag("SELFIT_PUBLIC_DEMO", False)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class LimitRule:
    name: str
    paths: tuple[str, ...]
    max_requests: int
    window_seconds: int
    contains: tuple[str, ...] = field(default_factory=tuple)


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, client_id: str, rule: LimitRule) -> tuple[bool, int]:
        now = time.monotonic()
        key = (client_id, rule.name)
        hits = self._hits[key]
        while hits and now - hits[0] > rule.window_seconds:
            hits.popleft()
        if len(hits) >= rule.max_requests:
            retry_after = max(1, int(rule.window_seconds - (now - hits[0]))) if hits else rule.window_seconds
            return False, retry_after
        hits.append(now)
        return True, 0


_limiter = InMemoryRateLimiter()


def _client_id(request: Request) -> str:
    # 登录用户按 user_id 计数，避免办公室/出口 NAT 下多同事共用 IP 被误伤；
    # 匿名流量仍按 IP 计数。惰性 import 避免与 app.auth 的循环依赖。
    try:
        from app.auth import current_token_from_request, resolve_token

        token = current_token_from_request(request)
        if token:
            user = resolve_token(token)
            user_id = str(user.get("user_id") or "").strip()
            if user_id:
                return f"user:{user_id}"
    except Exception:
        pass
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def _rate_rules() -> list[LimitRule]:
    return [
        LimitRule(
            "selfit_upload",
            ("/api/v1/selfit/sessions",),
            env_int("SELFIT_UPLOAD_RATE_LIMIT", 60),
            env_int("SELFIT_UPLOAD_RATE_WINDOW_SECONDS", 3600),
            contains=("/photos/",),
        ),
        LimitRule(
            "selfit_api",
            ("/api/v1/selfit",),
            env_int("SELFIT_API_RATE_LIMIT", 240),
            env_int("SELFIT_API_RATE_WINDOW_SECONDS", 3600),
        ),
        LimitRule(
            "auth",
            ("/auth/phone/start", "/auth/phone/verify"),
            env_int("SELFIT_AUTH_RATE_LIMIT", 20),
            env_int("SELFIT_AUTH_RATE_WINDOW_SECONDS", 3600),
        ),
        LimitRule(
            "upload",
            ("/analyze", "/demo/analyze", "/closet/import/upload", "/try-on", "/try-on/", "/selfit/try-on/"),
            env_int("SELFIT_UPLOAD_RATE_LIMIT", 60),
            env_int("SELFIT_UPLOAD_RATE_WINDOW_SECONDS", 3600),
        ),
        LimitRule(
            "ai",
            ("/stylist/chat", "/try-on/from-", "/selfit/try-on/from-"),
            env_int("SELFIT_AI_RATE_LIMIT", 30),
            env_int("SELFIT_AI_RATE_WINDOW_SECONDS", 3600),
        ),
    ]


def _matching_rule(path: str) -> LimitRule | None:
    for rule in _rate_rules():
        if rule.paths and not any(path == prefix or path.startswith(prefix) for prefix in rule.paths):
            continue
        if any(fragment not in path for fragment in rule.contains):
            continue
        return rule
    return None


def _json_error(status_code: int, code: str, message: str, headers: dict[str, str] | None = None, **extra: Any) -> JSONResponse:
    payload: dict[str, Any] = {
        "status": "failed",
        "error": {"code": code, "message": message},
    }
    payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload, headers=headers)


def _is_selfit_contract_path(path: str) -> bool:
    return path.startswith("/api/v1/selfit")


def _contract_error(status_code: int, code: str, message: str, *, retryable: bool, details: dict[str, Any], headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "requestId": "req_" + secrets.token_urlsafe(12),
            "error": {"code": code, "message": message, "retryable": retryable, "details": details},
        },
        headers=headers,
    )


async def request_guard_middleware(request: Request, call_next: Callable[[Request], Any]) -> Response:
    path = request.url.path
    max_body_mb = env_int("SELFIT_MAX_REQUEST_BODY_MB", 36)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_body_mb * 1024 * 1024:
                if _is_selfit_contract_path(path):
                    return _contract_error(
                        413,
                        "request.too_large",
                        f"单次上传暂时不能超过 {max_body_mb}MB，请减少图片数量或压缩后再试。",
                        retryable=False,
                        details={},
                    )
                return _json_error(
                    413,
                    "request.too_large",
                    f"单次上传暂时不能超过 {max_body_mb}MB，请减少图片数量或压缩后再试。",
                )
        except ValueError:
            pass

    rule = _matching_rule(path)
    if rule and not env_flag("SELFIT_DISABLE_RATE_LIMIT", False):
        allowed, retry_after = _limiter.check(_client_id(request), rule)
        if not allowed:
            if _is_selfit_contract_path(path):
                return _contract_error(
                    429,
                    "rate_limited",
                    "访问太频繁了，请稍后再试。",
                    retryable=True,
                    details={"retryAfterSeconds": retry_after},
                    headers={"Retry-After": str(retry_after)},
                )
            return _json_error(
                429,
                "request.rate_limited",
                "访问太频繁了，请稍后再试。",
                retry_after_seconds=retry_after,
                headers={"Retry-After": str(retry_after)},
            )

    return await call_next(request)


def deployment_guard_report() -> dict[str, Any]:
    auth_secret = os.getenv("SELFIT_AUTH_SECRET", "")
    return {
        "mode": deployment_mode(),
        "public_demo": is_public_demo_mode(),
        "limits": {
            "max_request_body_mb": env_int("SELFIT_MAX_REQUEST_BODY_MB", 36),
            "auth_per_window": env_int("SELFIT_AUTH_RATE_LIMIT", 20),
            "upload_per_window": env_int("SELFIT_UPLOAD_RATE_LIMIT", 60),
            "ai_per_window": env_int("SELFIT_AI_RATE_LIMIT", 30),
        },
        "auth": {
            "secret_configured": bool(auth_secret),
            "secret_is_default": auth_secret in {"", "selfit-local-auth-secret"},
            "returns_dev_code": env_flag("SELFIT_AUTH_RETURN_DEV_CODE", not is_public_demo_mode()),
            "mock_codes_allowed": env_flag("SELFIT_AUTH_ALLOW_MOCK_CODES", not is_public_demo_mode()),
        },
    }
