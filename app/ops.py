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


# ---------------------------------------------------------------------------
# 内部页面网关：线上只对用户开放主流程页，其余页面一律要求管理员登录。
# 本地开发（SELFIT_ENV 缺省）不启用，避免影响日常调试。
# ---------------------------------------------------------------------------

# 对外（用户）可访问的页面路径前缀/精确路径。API/静态资源走各自鉴权。
PUBLIC_PAGE_PREFIXES = ("/selfit", "/static", "/user-assets")
PUBLIC_PAGE_EXACT = ("/", "/favicon.ico", "/admin")

# 需要管理员登录的内部页面（页面级；数据 API 由各自路由的鉴权保护）。
INTERNAL_PAGE_RULES = (
    "/demo",
    "/wearwow",
    "/closet",
    "/try-on",
    "/tryon",
    "/mvp",
    "/qa",
    "/self-test",
    "/fixtures",
    "/fixture-images",
    "/report-builder",
    "/ori",
    "/analyze",
)


def is_internal_page(path: str) -> bool:
    if path in PUBLIC_PAGE_EXACT or path.startswith(PUBLIC_PAGE_PREFIXES):
        return False
    return any(path == rule or path.startswith(rule + "/") or path.startswith(rule + "?") for rule in INTERNAL_PAGE_RULES)


# 页面网关的 API 豁免：这些前缀下全是数据接口，没有 HTML 页面。
# 浏览器导航只会 GET 确切的页面 URL，REST API 走各自路由的鉴权（含内测门禁）。
_INTERNAL_GATE_API_PREFIXES = ("/api/", "/auth/", "/admin/", "/stylist/", "/user-assets/")


def _is_gate_target_page(path: str) -> bool:
    """页面网关只拦「确切的页面 URL」。

    /closet、/try-on 等前缀下页面（/xxx/demo）与 REST API 混布，
    必须精确到页面路径，否则 /closet/items 这类 GET API 会被误 307 到 /admin。
    """

    if path.startswith(_INTERNAL_GATE_API_PREFIXES):
        return False
    for page_rule, api_prefix in (("/closet/demo", "/closet/"), ("/try-on/demo", "/try-on/"), ("/tryon/demo", "/tryon/")):
        if path.startswith(api_prefix) and path != page_rule:
            return False
    return is_internal_page(path)


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
    methods: tuple[str, ...] = field(default_factory=tuple)


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
            "mirror_upload",
            ("/api/v1/selfit/mirror/analyze",),
            env_int("SELFIT_UPLOAD_RATE_LIMIT", 60),
            env_int("SELFIT_UPLOAD_RATE_WINDOW_SECONDS", 3600),
        ),
        LimitRule(
            "selfit_upload",
            ("/api/v1/selfit/sessions",),
            env_int("SELFIT_UPLOAD_RATE_LIMIT", 60),
            env_int("SELFIT_UPLOAD_RATE_WINDOW_SECONDS", 3600),
            contains=("/photos/",),
        ),
        LimitRule(
            # 镜子结果页会持续查询 handoff 是否已被手机领取。它使用短时、
            # 不可猜测且会过期的 token，不应与普通 selfit API 共用较低额度，
            # 否则轮询会误伤同一页面随后加载的二维码 PNG。
            "mirror_handoff",
            ("/api/v1/selfit/mirror/handoffs",),
            env_int("SELFIT_MIRROR_HANDOFF_RATE_LIMIT", 3600),
            env_int("SELFIT_MIRROR_HANDOFF_RATE_WINDOW_SECONDS", 3600),
        ),
        LimitRule(
            "selfit_api",
            ("/api/v1/selfit",),
            env_int("SELFIT_API_RATE_LIMIT", 240),
            env_int("SELFIT_API_RATE_WINDOW_SECONDS", 3600),
        ),
        LimitRule(
            # 手机号直接登录单列：内测手机号登录无验证码、无账号资产可盗，
            # 且线下路演场景大量用户共享同一出口 IP（商场 WiFi），必须放宽；
            # admin 登录仍走下方 auth 规则（保持严格，防密码枚举）。
            "phone_login",
            ("/auth/phone/start", "/auth/phone/verify", "/auth/phone/direct"),
            env_int("SELFIT_PHONE_LOGIN_RATE_LIMIT", 600),
            env_int("SELFIT_PHONE_LOGIN_RATE_WINDOW_SECONDS", 3600),
        ),
        LimitRule(
            "auth",
            ("/auth/invite/verify", "/admin/api/login"),
            env_int("SELFIT_AUTH_RATE_LIMIT", 20),
            env_int("SELFIT_AUTH_RATE_WINDOW_SECONDS", 3600),
        ),
        LimitRule(
            # 异步试穿通常需要数十秒，前端会持续读取任务状态。
            # 查询不触发模型或上传，不应消耗生成请求的限额。
            "tryon_job_status",
            ("/selfit/try-on/jobs/",),
            env_int("SELFIT_TRYON_STATUS_RATE_LIMIT", 3600),
            env_int("SELFIT_TRYON_STATUS_RATE_WINDOW_SECONDS", 3600),
            methods=("GET",),
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


def _matching_rule(path: str, method: str = "GET") -> LimitRule | None:
    normalized_method = str(method or "GET").upper()
    for rule in _rate_rules():
        if rule.methods and normalized_method not in rule.methods:
            continue
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


def _internal_page_redirect(request: Request) -> Response | None:
    """线上内部页面网关：管理员或内测白名单用户可访问，其余 307 到 /admin 登录后跳回。"""

    if not is_public_demo_mode():
        return None
    path = request.url.path
    if request.method not in {"GET", "HEAD"} or not _is_gate_target_page(path):
        return None
    # 数据/操作 API 不在此拦截（各自路由已有鉴权），只拦页面浏览。
    if path.startswith(("/api/", "/auth/")):
        return None
    from app.auth import admin_token_from_request, resolve_admin_user, user_token_from_request

    admin_token = admin_token_from_request(request)
    if admin_token:
        try:
            resolve_admin_user(admin_token)
            return None
        except Exception:
            pass
    # 内测用户：登录 cookie/Bearer 对应的手机号在白名单里，
    # 放行后续功能页面（服装拆款、电子衣橱、AI 试穿等）。
    user_token = user_token_from_request(request)
    if user_token:
        from app.auth import resolve_token

        try:
            user = resolve_token(user_token)
            if user.get("beta_access"):
                return None
        except Exception:
            pass
    from urllib.parse import quote

    next_target = quote(path + (f"?{request.url.query}" if request.url.query else ""), safe="/?=&")
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=f"/admin?next={next_target}", status_code=307)


async def request_guard_middleware(request: Request, call_next: Callable[[Request], Any]) -> Response:
    path = request.url.path
    internal_gate = _internal_page_redirect(request)
    if internal_gate is not None:
        return internal_gate
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

    rule = _matching_rule(path, request.method)
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
            "tryon_status_per_window": env_int("SELFIT_TRYON_STATUS_RATE_LIMIT", 3600),
            "mirror_handoff_per_window": env_int("SELFIT_MIRROR_HANDOFF_RATE_LIMIT", 3600),
            "ai_per_window": env_int("SELFIT_AI_RATE_LIMIT", 30),
        },
        "auth": {
            "secret_configured": bool(auth_secret),
            "secret_is_default": auth_secret in {"", "selfit-local-auth-secret"},
            "returns_dev_code": env_flag("SELFIT_AUTH_RETURN_DEV_CODE", not is_public_demo_mode()),
            "mock_codes_allowed": env_flag("SELFIT_AUTH_ALLOW_MOCK_CODES", not is_public_demo_mode()),
        },
    }
