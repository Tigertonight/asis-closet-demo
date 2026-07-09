from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def deployment_mode() -> str:
    return (os.getenv("ASIS_ENV") or os.getenv("APP_ENV") or "local").strip().lower()


def is_public_demo_mode() -> bool:
    return deployment_mode() in {"production", "prod", "demo", "staging"} or env_flag("ASIS_PUBLIC_DEMO", False)


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
            "auth",
            ("/auth/phone/start", "/auth/phone/verify"),
            env_int("ASIS_AUTH_RATE_LIMIT", 20),
            env_int("ASIS_AUTH_RATE_WINDOW_SECONDS", 3600),
        ),
        LimitRule(
            "upload",
            ("/analyze", "/demo/analyze", "/closet/import/upload", "/try-on", "/try-on/", "/asis/try-on/"),
            env_int("ASIS_UPLOAD_RATE_LIMIT", 60),
            env_int("ASIS_UPLOAD_RATE_WINDOW_SECONDS", 3600),
        ),
        LimitRule(
            "ai",
            ("/stylist/chat", "/try-on/from-", "/asis/try-on/from-"),
            env_int("ASIS_AI_RATE_LIMIT", 30),
            env_int("ASIS_AI_RATE_WINDOW_SECONDS", 3600),
        ),
    ]


def _matching_rule(path: str) -> LimitRule | None:
    for rule in _rate_rules():
        if any(path == prefix or path.startswith(prefix) for prefix in rule.paths):
            return rule
    return None


def _json_error(status_code: int, code: str, message: str, headers: dict[str, str] | None = None, **extra: Any) -> JSONResponse:
    payload: dict[str, Any] = {
        "status": "failed",
        "error": {"code": code, "message": message},
    }
    payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload, headers=headers)


async def request_guard_middleware(request: Request, call_next: Callable[[Request], Any]) -> Response:
    max_body_mb = env_int("ASIS_MAX_REQUEST_BODY_MB", 36)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_body_mb * 1024 * 1024:
                return _json_error(
                    413,
                    "request.too_large",
                    f"单次上传暂时不能超过 {max_body_mb}MB，请减少图片数量或压缩后再试。",
                )
        except ValueError:
            pass

    rule = _matching_rule(request.url.path)
    if rule and not env_flag("ASIS_DISABLE_RATE_LIMIT", False):
        allowed, retry_after = _limiter.check(_client_id(request), rule)
        if not allowed:
            return _json_error(
                429,
                "request.rate_limited",
                "访问太频繁了，请稍后再试。",
                retry_after_seconds=retry_after,
                headers={"Retry-After": str(retry_after)},
            )

    return await call_next(request)


def deployment_guard_report() -> dict[str, Any]:
    auth_secret = os.getenv("ASIS_AUTH_SECRET", "")
    return {
        "mode": deployment_mode(),
        "public_demo": is_public_demo_mode(),
        "limits": {
            "max_request_body_mb": env_int("ASIS_MAX_REQUEST_BODY_MB", 36),
            "auth_per_window": env_int("ASIS_AUTH_RATE_LIMIT", 20),
            "upload_per_window": env_int("ASIS_UPLOAD_RATE_LIMIT", 60),
            "ai_per_window": env_int("ASIS_AI_RATE_LIMIT", 30),
        },
        "auth": {
            "secret_configured": bool(auth_secret),
            "secret_is_default": auth_secret in {"", "asis-local-auth-secret"},
            "returns_dev_code": env_flag("ASIS_AUTH_RETURN_DEV_CODE", not is_public_demo_mode()),
            "mock_codes_allowed": env_flag("ASIS_AUTH_ALLOW_MOCK_CODES", not is_public_demo_mode()),
        },
    }
