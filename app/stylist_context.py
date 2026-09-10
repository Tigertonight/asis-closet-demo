"""AI 穿搭师上下文配置：内测用户专属画像 + 全局 prompt 调整。

管理后台「AI 上下文」Tab 维护两样东西：
1. ``prompt``：追加到 direct 通道 system prompt 的个性化指引（管理员可改）；
2. ``users``：手机号 / 小红书 uid → 画像纯文本。聊天时按登录 user_id 匹配，
   未配置的用户走普通问答，行为不变。

存储：``outputs/stylist_context_config.json``（服务器数据目录，不进 git）。
初始数据由 ``scripts/seed_stylist_context.py`` 从
``scripts/data/stylist_context_seed.json`` 物化。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
from pathlib import Path
from typing import Any

from app.storage import ROOT_DIR, sanitize_user_id

STYLIST_CONTEXT_CONFIG_PATH = ROOT_DIR / "outputs" / "stylist_context_config.json"
MAX_DOC_CHARS = 20000
MAX_PROMPT_CHARS = 8000

# 预制的画像使用指引：管理后台可改，这里只是初始值。
DEFAULT_STYLIST_CONTEXT_PROMPT = (
    "当 user_persona_doc（内测用户画像）存在时，你是一位本来就认识她的私人穿搭师：\n"
    "1. 把画像当作最高优先级的个性化依据：她的身份、审美偏好、消费习惯、雷区都要体现在推荐和措辞里，"
    "让建议像是专门为她准备的，而不是通用模板。\n"
    "2. 不要暴露「画像」「分析」「数据」「行为报告」等字眼，自然地体现你懂她；不要主动复述画像里的敏感信息"
    "（健康、情绪、情感状态），只用于让建议更贴心。\n"
    "3. 画像与衣橱、测试报告冲突时，以她当场的问题为先，画像用于解释「为什么适合她」。\n"
    "4. 当 latest_report（她最近的风格测试报告）存在时，结合报告的风格类型、关键词和推荐色给出呼应的建议，"
    "风格类型名和推荐色可以直接使用。\n"
    "5. 普通用户（没有画像、没有报告）按通用穿搭师标准回答，不提及任何配置的存在。"
)

_lock = threading.Lock()


def stylist_context_editable() -> bool:
    """画像内容在管理后台是否可见/可编辑。

    默认 False（隐私保护）：管理后台只展示手机号/uid 等索引信息，
    画像全文不出 API；AI 问答不受影响（直接读本地配置文件）。
    征得成员同意后在 .env.demo 设 SELFIT_STYLIST_CONTEXT_EDITABLE=1 打开。
    """

    return os.environ.get("SELFIT_STYLIST_CONTEXT_EDITABLE", "").strip().lower() in {"1", "true", "yes", "on"}


def _empty_config() -> dict[str, Any]:
    return {"version": 1, "prompt": DEFAULT_STYLIST_CONTEXT_PROMPT, "users": []}


def load_stylist_context_config() -> dict[str, Any]:
    with _lock:
        try:
            data = json.loads(STYLIST_CONTEXT_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _empty_config()
    if not isinstance(data, dict):
        return _empty_config()
    data.setdefault("version", 1)
    data.setdefault("prompt", DEFAULT_STYLIST_CONTEXT_PROMPT)
    users = data.get("users")
    data["users"] = [item for item in users if isinstance(item, dict)] if isinstance(users, list) else []
    return data


def write_stylist_context_config(data: dict[str, Any]) -> None:
    STYLIST_CONTEXT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        STYLIST_CONTEXT_CONFIG_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def get_stylist_context_prompt() -> str:
    prompt = str(load_stylist_context_config().get("prompt") or "").strip()
    return prompt[:MAX_PROMPT_CHARS] or DEFAULT_STYLIST_CONTEXT_PROMPT


def normalize_phone_e164(phone: str) -> str | None:
    """与 app.auth._normalize_phone 同口径的宽松版（管理后台输入容错）。"""

    text = str(phone or "").strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if text.startswith("+") and 8 <= len(digits) <= 15:
        return f"+{digits}"
    if re.fullmatch(r"1[3-9]\d{9}", digits):
        return f"+86{digits}"
    if 8 <= len(digits) <= 15:
        return f"+{digits}"
    return None


def user_id_from_phone(phone: str) -> str | None:
    """手机号 → selfit user_id（与 app.auth.verify_phone_direct_login 同算法）。"""

    phone_e164 = normalize_phone_e164(phone)
    if not phone_e164:
        return None
    return sanitize_user_id("u_" + hashlib.sha256(phone_e164.encode("utf-8")).hexdigest()[:16])


def _entry_user_ids(entry: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    direct = str(entry.get("user_id") or "").strip()
    if direct:
        ids.add(sanitize_user_id(direct))
    for field in ("phone", "phones"):
        raw = entry.get(field)
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            derived = user_id_from_phone(str(value or ""))
            if derived:
                ids.add(derived)
    return ids


def find_stylist_user_doc(user_id: str) -> dict[str, Any] | None:
    """按登录 user_id 匹配用户画像条目；未配置返回 None。"""

    safe_user_id = sanitize_user_id(user_id)
    if not safe_user_id or safe_user_id in {"local_user", "local-user"}:
        return None
    for entry in load_stylist_context_config()["users"]:
        if safe_user_id in _entry_user_ids(entry):
            doc = str(entry.get("doc") or "").strip()
            if doc:
                return {
                    "doc": doc[:MAX_DOC_CHARS],
                    "nickname": str(entry.get("nickname") or "").strip(),
                    "xhs_uid": str(entry.get("xhs_uid") or "").strip(),
                }
    return None


def latest_report_summary(user_id: str) -> dict[str, Any] | None:
    """用户最近一次风格测试报告的轻量摘要（供 AI 上下文）。"""

    from app.selfit_onboarding import _load_store

    safe_user_id = sanitize_user_id(user_id)
    reports = [
        report
        for report in _load_store()["reports"]
        if report.get("user_id") == safe_user_id
        and isinstance(report.get("data"), dict)
        and str((report.get("data") or {}).get("typeId") or "").strip()
    ]
    latest = max(reports, key=lambda item: str(item.get("created_at") or ""), default=None)
    if latest is None:
        return None
    data = latest.get("data") or {}
    colors = data.get("colors") if isinstance(data.get("colors"), list) else []

    def _color_name(color: Any) -> str:
        if not isinstance(color, dict):
            return ""
        return str(color.get("name") or color.get("label") or "").strip()

    return {
        "type_id": str(data.get("typeId") or "").strip(),
        "title": str(data.get("title") or "").strip(),
        "traits": [str(item) for item in (data.get("traits") or [])[:8] if str(item).strip()],
        "summary": str(data.get("summary") or "")[:400],
        "recommended_colors": [name for name in (_color_name(color) for color in colors[:6]) if name],
        "outfit_summary": str(data.get("outfitSummary") or "")[:300],
        "advice": [str(item) for item in (data.get("advice") or [])[:4] if str(item).strip()],
        "created_at": latest.get("created_at"),
    }


def upsert_stylist_context_user(payload: dict[str, Any]) -> dict[str, Any]:
    """新增或更新一条用户画像配置（按 xhs_uid 或 phone 幂等）。"""

    data = load_stylist_context_config()
    entry_id = str(payload.get("entry_id") or "").strip()
    phone = str(payload.get("phone") or "").strip()
    xhs_uid = str(payload.get("xhs_uid") or "").strip()
    nickname = str(payload.get("nickname") or "").strip()
    doc = str(payload.get("doc") or "").strip()
    if not (phone or xhs_uid or entry_id):
        raise ValueError("手机号和小红书 uid 至少填一个")
    if phone and not normalize_phone_e164(phone):
        raise ValueError("手机号格式不正确")
    if not doc:
        raise ValueError("画像文档不能为空")
    entry: dict[str, Any] | None = None
    if entry_id:
        entry = next((item for item in data["users"] if item.get("entry_id") == entry_id), None)
    if entry is None and xhs_uid:
        entry = next((item for item in data["users"] if str(item.get("xhs_uid") or "") == xhs_uid), None)
    if entry is None and phone:
        target_ids = _entry_user_ids({"phone": phone})
        entry = next((item for item in data["users"] if target_ids & _entry_user_ids(item)), None)
    if entry is None:
        entry = {"entry_id": "scu_" + secrets.token_urlsafe(8), "created_at": _now_iso()}
        data["users"].append(entry)
    if phone:
        entry["phone"] = phone
    if xhs_uid:
        entry["xhs_uid"] = xhs_uid
    if nickname:
        entry["nickname"] = nickname
    entry["doc"] = doc[:MAX_DOC_CHARS]
    entry["updated_at"] = _now_iso()
    write_stylist_context_config(data)
    return entry


def delete_stylist_context_user(entry_id: str) -> bool:
    data = load_stylist_context_config()
    remaining = [item for item in data["users"] if item.get("entry_id") != entry_id]
    if len(remaining) == len(data["users"]):
        return False
    data["users"] = remaining
    write_stylist_context_config(data)
    return True


def update_stylist_context_prompt(prompt: str) -> str:
    value = str(prompt or "").strip()
    if not value:
        raise ValueError("prompt 不能为空")
    data = load_stylist_context_config()
    data["prompt"] = value[:MAX_PROMPT_CHARS]
    data["prompt_updated_at"] = _now_iso()
    write_stylist_context_config(data)
    return data["prompt"]


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
