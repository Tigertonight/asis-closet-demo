"""内测门槛与试穿日额度。

- require_beta_user：主站消耗 token 的行为（试穿生成、问 AI、衣橱 AI 抠图）
  只对内测账号（邀请码解锁 / 升级）开放。
- 试穿日额度：每个内测账号每天最多 SELFIT_TRYON_DAILY_LIMIT（默认 30）次成功
  创建的试穿任务，北京时间 0 点刷新；失败重试不重复计数。
- 用量落在 outputs/auth/quota_usage.json（服务器数据目录，不入 git）。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import auth
from app.ops import env_int

CN_TZ = timezone(timedelta(hours=8))
QUOTA_RETENTION_DAYS = 7

_bearer = HTTPBearer(auto_error=False)


def _quota_path() -> Path:
    # 动态取 auth.AUTH_DIR（测试会 monkeypatch），不要在 import 时固化。
    return auth.AUTH_DIR / "quota_usage.json"


def daily_tryon_limit() -> int:
    return max(1, env_int("SELFIT_TRYON_DAILY_LIMIT", 30))


def _today_key() -> str:
    return datetime.now(CN_TZ).strftime("%Y-%m-%d")


def _load_usage() -> dict[str, dict[str, int]]:
    path = _quota_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _write_usage(usage: dict[str, dict[str, int]]) -> None:
    path = _quota_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{datetime.now(CN_TZ).strftime('%H%M%S')}.tmp")
    tmp_path.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _prune(usage: dict[str, dict[str, int]]) -> None:
    horizon = (datetime.now(CN_TZ) - timedelta(days=QUOTA_RETENTION_DAYS)).strftime("%Y-%m-%d")
    for user_id in list(usage.keys()):
        usage[user_id] = {day: count for day, count in usage[user_id].items() if day >= horizon}
        if not usage[user_id]:
            del usage[user_id]


def tryon_used_today(user_id: str) -> int:
    usage = _load_usage()
    return int(usage.get(user_id, {}).get(_today_key(), 0))


def tryon_remaining_today(user_id: str) -> int:
    return max(0, daily_tryon_limit() - tryon_used_today(user_id))


def quota_payload(user_id: str) -> dict[str, int]:
    limit = daily_tryon_limit()
    used = tryon_used_today(user_id)
    return {
        "tryon_daily_limit": limit,
        "tryon_used_today": used,
        "tryon_remaining_today": max(0, limit - used),
    }


def consume_tryon_quota(user_id: str) -> None:
    """试穿任务成功创建后 +1；超出当日额度抛 429。"""
    limit = daily_tryon_limit()
    usage = _load_usage()
    today = _today_key()
    used = int(usage.get(user_id, {}).get(today, 0))
    if used >= limit:
        raise HTTPException(status_code=429, detail=f"今日 {limit} 次试穿额度已用完，明天 0 点刷新")
    usage.setdefault(user_id, {})[today] = used + 1
    _prune(usage)
    _write_usage(usage)


async def require_beta_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    user = await auth.get_current_user(credentials)
    if not user.get("beta_qualified"):
        raise HTTPException(status_code=403, detail="内测名额有限，输入邀请码解锁完整体验")
    return user


async def require_beta_tryon(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    user = await require_beta_user(credentials)
    if tryon_remaining_today(str(user["user_id"])) <= 0:
        limit = daily_tryon_limit()
        raise HTTPException(status_code=429, detail=f"今日 {limit} 次试穿额度已用完，明天 0 点刷新")
    return user
