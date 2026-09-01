"""内测功能白名单：管理后台配置手机号，白名单用户可体验 onboarding 之外的后续功能。

定位（内测期产品规则）：
- onboarding 主流程（风格测试 / 报告）对所有用户开放，持续收集测试数据；
- 服装拆款、电子衣橱、AI 试穿、AI 穿搭师等后续功能只对内测用户（白名单手机号）开放；
- 管理员和邀请码内部账号天然具备内测资格，方便日常验证；
- 本地开发模式（SELFIT_ENV 缺省）不做 gating，避免影响调试与测试。

数据归属：白名单是运营数据，存服务器 `outputs/auth/beta_allowlist.json`（不进 git），
与 auth_store 同目录；线上通过管理后台增删，部署回滚不会丢配置。
"""

from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import get_admin_user
from app.ops import is_public_demo_mode
from app.storage import ROOT_DIR

BETA_ALLOWLIST_PATH = ROOT_DIR / "outputs" / "auth" / "beta_allowlist.json"
MAX_NOTE_LEN = 80

_write_lock = threading.Lock()

admin_router = APIRouter(prefix="/admin/api", tags=["selfit-beta-access"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_allowlist() -> dict[str, Any]:
    if not BETA_ALLOWLIST_PATH.exists():
        return {"version": 1, "users": []}
    try:
        data = json.loads(BETA_ALLOWLIST_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("version", 1)
            data.setdefault("users", [])
            return data
    except json.JSONDecodeError:
        pass
    return {"version": 1, "users": []}


def _save_allowlist(data: dict[str, Any]) -> None:
    with _write_lock:
        BETA_ALLOWLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = BETA_ALLOWLIST_PATH.with_name(f"{BETA_ALLOWLIST_PATH.name}.{secrets.token_urlsafe(8)}.tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(BETA_ALLOWLIST_PATH)


def list_beta_users() -> list[dict[str, Any]]:
    users = list(_load_allowlist().get("users", []))
    users.sort(key=lambda item: str(item.get("added_at") or ""), reverse=True)
    return users


def add_beta_user(phone: str, note: str = "") -> dict[str, Any]:
    """添加（或更新备注）内测手机号；输入与登录同口径归一化到 E.164。"""

    from app.auth import _normalize_phone

    phone_e164 = _normalize_phone(phone)
    note = str(note or "").strip()[:MAX_NOTE_LEN]
    data = _load_allowlist()
    for item in data["users"]:
        if item.get("phone_e164") == phone_e164:
            item["note"] = note
            _save_allowlist(data)
            return item
    entry = {"phone_e164": phone_e164, "note": note, "added_at": _now_iso()}
    data["users"].append(entry)
    _save_allowlist(data)
    return entry


def remove_beta_user(phone_e164: str) -> bool:
    data = _load_allowlist()
    before = len(data["users"])
    data["users"] = [item for item in data["users"] if item.get("phone_e164") != phone_e164]
    if len(data["users"]) == before:
        return False
    _save_allowlist(data)
    return True


def is_beta_phone(phone_e164: str | None) -> bool:
    if not phone_e164:
        return False
    return any(item.get("phone_e164") == phone_e164 for item in _load_allowlist().get("users", []))


def beta_gating_enabled() -> bool:
    """内测 gating 仅线上（demo/production）模式生效；本地开发一律放行。"""

    return is_public_demo_mode()


def beta_access_for_user(user: dict[str, Any]) -> bool:
    """判断一个用户（auth store 完整记录）是否具备内测资格。

    管理员 / 邀请码内部账号直接放行；普通用户看手机号白名单。
    """

    if not beta_gating_enabled():
        return True
    if user.get("auth_provider") in {"admin", "invite"}:
        return True
    return is_beta_phone(user.get("phone_e164"))


class BetaUserPayload(BaseModel):
    phone: str = Field(min_length=1, max_length=32)
    note: str = Field(default="", max_length=MAX_NOTE_LEN)


def _public_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "phone": entry.get("phone_e164"),
        "note": entry.get("note") or "",
        "addedAt": entry.get("added_at"),
    }


@admin_router.get("/beta-users")
async def admin_list_beta_users(admin: dict[str, Any] = Depends(get_admin_user)) -> JSONResponse:
    return JSONResponse(
        content={"betaUsers": [_public_entry(entry) for entry in list_beta_users()]},
        headers={"Cache-Control": "no-store"},
    )


@admin_router.post("/beta-users", status_code=201)
async def admin_add_beta_user(
    payload: BetaUserPayload,
    admin: dict[str, Any] = Depends(get_admin_user),
) -> dict[str, Any]:
    entry = add_beta_user(payload.phone, payload.note)
    return {"status": "ok", "betaUser": _public_entry(entry)}


@admin_router.delete("/beta-users/{phone_e164}")
async def admin_remove_beta_user(
    phone_e164: str,
    admin: dict[str, Any] = Depends(get_admin_user),
) -> JSONResponse:
    from urllib.parse import unquote

    normalized = unquote(phone_e164).strip()
    if not remove_beta_user(normalized):
        raise HTTPException(status_code=404, detail="这个手机号不在内测名单中")
    return JSONResponse(content={"status": "ok"})
