"""selfit 轻量埋点：JSONL 追加存储 + 管理后台聚合查询。

设计原则：
- 埋点数据不可信：客户端只上报事件名与属性，服务端补时间戳/IP/UA；
  user_id 仅作"自称"参考，分析时以 auth_store / 业务记录为准；
- 事件名白名单：防止任意字符串撑爆磁盘；
- JSONL 只追加不修改，路演结束后用脚本离线分析，量大了再迁 SQLite。
"""

from __future__ import annotations

import json
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import (
    ADMIN_COOKIE_NAME,
    TOKEN_TTL_HOURS,
    get_admin_user,
    issue_admin_session,
    revoke_admin_sessions,
    set_admin_password,
    verify_admin_password,
)
from app.storage import ROOT_DIR

ANALYTICS_DIR = ROOT_DIR / "outputs" / "analytics"
EVENTS_PATH = ANALYTICS_DIR / "events.jsonl"
MAX_BATCH_EVENTS = 50
MAX_EVENT_NAME_LEN = 64
MAX_PROPS_BYTES = 2048

# 事件白名单：app 端 + 镜子端。新事件需在此登记。
EVENT_WHITELIST = frozenset(
    {
        # 通用
        "screen_view",
        # app 登录
        "login_success",
        "login_failed",
        # app onboarding
        "photo_upload_result",
        "manual_saved",
        "preferences_saved",
        "vibe_saved",
        "report_started",
        "report_resources_ready",
        "report_completed",
        "report_failed",
        "image_load_failed",
        "image_load_recovered",
        "share_opened",
        "share_saved",
        "retake_clicked",
        "mirror_handoff_claimed",
        # 镜子端
        "mirror_capture_started",
        "mirror_capture_confirmed",
        "mirror_capture_retaken",
        "mirror_qr_generated",
        "mirror_qr_expired",
        "mirror_qr_claim_detected",
        "mirror_reset",
    }
)

# 漏斗顺序（app 主流程）
APP_FUNNEL = [
    ("splash", "进入"),
    ("login", "登录方式"),
    ("phone-login", "手机号登录"),
    ("intro", "介绍页"),
    ("suit", "上传照片"),
    ("like", "偏好选择"),
    ("vibe", "问卷"),
    ("loading", "生成中"),
    ("report", "查看报告"),
]

# 镜子端漏斗
MIRROR_FUNNEL = [
    ("mirror_capture_started", "开始拍照"),
    ("mirror_capture_confirmed", "确认照片"),
    ("mirror_qr_generated", "二维码生成"),
    ("mirror_qr_claim_detected", "用户已扫码领取"),
]

_write_lock = threading.Lock()

router = APIRouter(prefix="/api/v1/selfit", tags=["selfit-analytics"])
admin_router = APIRouter(prefix="/admin/api", tags=["selfit-admin"])


class EventItem(BaseModel):
    event: str = Field(max_length=MAX_EVENT_NAME_LEN)
    screen: str | None = Field(default=None, max_length=32)
    sessionId: str | None = Field(default=None, max_length=64)
    userId: str | None = Field(default=None, max_length=80)
    props: dict[str, Any] = Field(default_factory=dict)


class EventsPayload(BaseModel):
    events: list[EventItem] = Field(max_length=MAX_BATCH_EVENTS)


class AdminLoginPayload(BaseModel):
    password: str


class AdminPasswordChangePayload(BaseModel):
    current_password: str
    new_password: str


@admin_router.post("/login")
async def admin_login(request: Request, payload: AdminLoginPayload) -> JSONResponse:
    """管理后台密码登录：发 Bearer token + admin cookie（供 QA 页面复用）。"""

    from app.auth import client_ip_from_request

    if not verify_admin_password(payload.password):
        return JSONResponse(
            status_code=401,
            content={"detail": "管理员密码不正确"},
        )
    token = issue_admin_session(client_ip_from_request(request))
    response = JSONResponse(
        content={
            "status": "ok",
            "access_token": token,
            "token_type": "bearer",
            "expires_in_seconds": TOKEN_TTL_HOURS * 3600,
        }
    )
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        token,
        max_age=TOKEN_TTL_HOURS * 3600,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@admin_router.put("/password")
async def admin_change_password(
    payload: AdminPasswordChangePayload,
    admin: dict[str, Any] = Depends(get_admin_user),
) -> JSONResponse:
    if not verify_admin_password(payload.current_password):
        return JSONResponse(
            status_code=401,
            content={"detail": "当前密码不正确"},
        )
    set_admin_password(payload.new_password)
    revoke_admin_sessions()
    return JSONResponse(content={"status": "ok", "message": "密码已更新，请用新密码重新登录"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_events(lines: list[str]) -> None:
    with _write_lock:
        ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
        with EVENTS_PATH.open("a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")


def _load_events() -> list[dict[str, Any]]:
    if not EVENTS_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    with EVENTS_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


@router.post("/events", status_code=204)
async def report_events(request: Request, payload: EventsPayload) -> Response:
    client_ip = (
        (request.headers.get("x-real-ip") or "").strip()
        or (request.headers.get("x-forwarded-for") or "").split(",")[-1].strip()
        or (request.client.host if request.client else "unknown")
    )
    user_agent = (request.headers.get("user-agent") or "")[:256]
    lines: list[str] = []
    for item in payload.events:
        if item.event not in EVENT_WHITELIST:
            continue
        record = {
            "ts": _now_iso(),
            "event": item.event,
            "screen": item.screen,
            "session_id": item.sessionId,
            "user_id": item.userId,
            "client_ip": client_ip,
            "ua": user_agent,
            "props": item.props if _props_size_ok(item.props) else {},
        }
        lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    if lines:
        _append_events(lines)
    return Response(status_code=204)


def _props_size_ok(props: dict[str, Any]) -> bool:
    try:
        return len(json.dumps(props, ensure_ascii=False)) <= MAX_PROPS_BYTES
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# 管理后台聚合 API
# ---------------------------------------------------------------------------


def _screen_view_counts(events: list[dict[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for event in events:
        if event.get("event") == "screen_view" and event.get("screen"):
            counts[str(event["screen"])] += 1
    return counts


def _event_sessions(events: list[dict[str, Any]], event_name: str) -> set[str]:
    result: set[str] = set()
    for event in events:
        if event.get("event") == event_name:
            key = event.get("session_id") or event.get("client_ip") or event.get("ts")
            if key:
                result.add(str(key))
    return result


def _dwell_seconds(events: list[dict[str, Any]]) -> dict[str, list[float]]:
    """按 session 计算每屏停留：相邻事件时间差归属前一个 screen_view 的屏。"""

    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("session_id"):
            by_session[str(event["session_id"])].append(event)
    dwell: dict[str, list[float]] = defaultdict(list)
    for session_events in by_session.values():
        session_events.sort(key=lambda item: str(item.get("ts") or ""))
        for index, event in enumerate(session_events[:-1]):
            if event.get("event") != "screen_view" or not event.get("screen"):
                continue
            started = _parse_ts(event.get("ts"))
            # 会话内下一个 screen_view 或 30 分钟内的事件作为离开时刻
            ended = None
            for following in session_events[index + 1 :]:
                if following.get("event") == "screen_view":
                    ended = _parse_ts(following.get("ts"))
                    break
                ended = _parse_ts(following.get("ts"))
            if started is None or ended is None:
                continue
            seconds = (ended - started).total_seconds()
            if 0 <= seconds <= 1800:
                dwell[str(event["screen"])].append(seconds)
    return dwell


def _hourly_activity(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: Counter = Counter()
    for event in events:
        ts = _parse_ts(event.get("ts"))
        if ts is None:
            continue
        # 展示用东八区小时
        local = ts + timedelta(hours=8)
        buckets[local.strftime("%m-%d %H:00")] += 1
    return [
        {"hour": hour, "count": count}
        for hour, count in sorted(buckets.items())
    ][-48:]


def _user_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """手机号维度的活跃统计（user_id → 手机号由前端 join /admin/api/users）。"""

    by_user: dict[str, dict[str, Any]] = {}
    for event in events:
        user_id = event.get("user_id")
        if not user_id:
            continue
        row = by_user.setdefault(
            str(user_id),
            {"user_id": str(user_id), "events": 0, "first_seen": event.get("ts"), "last_seen": event.get("ts"), "phones": set()},
        )
        row["events"] += 1
        if str(event.get("ts") or "") > str(row["last_seen"] or ""):
            row["last_seen"] = event.get("ts")
        if str(event.get("ts") or "") < str(row["first_seen"] or "￿"):
            row["first_seen"] = event.get("ts")
    rows = list(by_user.values())
    for row in rows:
        row.pop("phones", None)
    rows.sort(key=lambda row: str(row.get("last_seen") or ""), reverse=True)
    return rows[:200]


@admin_router.get("/analytics/summary")
async def analytics_summary(admin: dict[str, Any] = Depends(get_admin_user)) -> JSONResponse:
    events = _load_events()
    screen_counts = _screen_view_counts(events)
    funnel = [
        {
            "screen": screen,
            "label": label,
            "views": screen_counts.get(screen, 0),
        }
        for screen, label in APP_FUNNEL
    ]
    mirror_funnel = []
    previous: int | None = None
    for event_name, label in MIRROR_FUNNEL:
        sessions = len(_event_sessions(events, event_name))
        row: dict[str, Any] = {"event": event_name, "label": label, "count": sessions}
        if previous is not None and previous > 0:
            row["conversion"] = round(sessions / previous, 3)
        previous = sessions
        mirror_funnel.append(row)

    dwell = _dwell_seconds(events)
    dwell_summary = {
        screen: {
            "samples": len(values),
            "avgSeconds": round(sum(values) / len(values), 1) if values else 0,
            "medianSeconds": round(sorted(values)[len(values) // 2], 1) if values else 0,
        }
        for screen, values in sorted(dwell.items())
        if values
    }

    return JSONResponse(
        content={
            "totals": {
                "events": len(events),
                "sessions": len({e.get("session_id") for e in events if e.get("session_id")}),
                "users": len({e.get("user_id") for e in events if e.get("user_id")}),
                "mirrorCaptures": len(_event_sessions(events, "mirror_capture_started")),
                "mirrorClaims": len(_event_sessions(events, "mirror_qr_claim_detected")),
                "reportsCompleted": len(_event_sessions(events, "report_completed")),
                "logins": len(_event_sessions(events, "login_success")),
            },
            "appFunnel": funnel,
            "mirrorFunnel": mirror_funnel,
            "dwell": dwell_summary,
            "hourly": _hourly_activity(events),
            "users": _user_rows(events),
        },
        headers={"Cache-Control": "no-store"},
    )


@admin_router.get("/analytics/users")
async def analytics_users(admin: dict[str, Any] = Depends(get_admin_user)) -> JSONResponse:
    """user_id → 手机号映射（管理员可见），供看板把行为数据和手机号 join 起来。"""

    from app.auth import _load_store

    data = _load_store()
    rows = [
        {
            "user_id": user.get("user_id"),
            "phone_e164": user.get("phone_e164"),
            "auth_provider": user.get("auth_provider"),
            "created_at": user.get("created_at"),
            "last_login_at": user.get("last_login_at"),
        }
        for user in data.get("users", [])
    ]
    rows.sort(key=lambda row: str(row.get("last_login_at") or ""), reverse=True)
    return JSONResponse(content={"users": rows}, headers={"Cache-Control": "no-store"})
