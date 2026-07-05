from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.storage import storage_context


LEGACY_SESSION_ID = "asis-inspiration"
DEFAULT_SESSION_TITLE = "新的穿搭灵感"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_dir() -> Path:
    path = storage_context().closet_output_dir / "stylist_sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_session_id(session_id: str | None) -> str:
    text = str(session_id or "").strip()
    if text == LEGACY_SESSION_ID:
        return LEGACY_SESSION_ID
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)[:80]
    return safe or secrets.token_urlsafe(10)


def _session_path(session_id: str) -> Path:
    return _session_dir() / f"{_safe_session_id(session_id)}.json"


def _read_session(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data.get("session_id"):
        return None
    data.setdefault("messages", [])
    data.setdefault("metadata", {})
    data.setdefault("status", "active")
    data.setdefault("title", DEFAULT_SESSION_TITLE)
    data.setdefault("message_count", len(data.get("messages", [])))
    data.setdefault("last_message_preview", _last_message_preview(data.get("messages", [])))
    return data


def _write_session(session: dict[str, Any]) -> dict[str, Any]:
    session_id = _safe_session_id(session.get("session_id"))
    session["session_id"] = session_id
    session["user_id"] = storage_context().user_id
    session["message_count"] = len(session.get("messages", []))
    session["last_message_preview"] = _last_message_preview(session.get("messages", []))
    path = _session_path(session_id)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return session


def _session_summary(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session.get("session_id"),
        "title": session.get("title") or DEFAULT_SESSION_TITLE,
        "status": session.get("status") or "active",
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "last_message_preview": session.get("last_message_preview") or "",
        "message_count": int(session.get("message_count") or len(session.get("messages", []))),
        "metadata": session.get("metadata") if isinstance(session.get("metadata"), dict) else {},
    }


def _last_message_preview(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages or []):
        content = str(message.get("content") or "").strip()
        if content:
            return content[:36]
    return ""


def _title_from_message(message: str) -> str:
    text = " ".join(str(message or "").split())
    if not text:
        return DEFAULT_SESSION_TITLE
    return text[:18]


def list_stylist_sessions(include_archived: bool = False) -> dict[str, Any]:
    sessions = []
    for path in _session_dir().glob("*.json"):
        session = _read_session(path)
        if not session:
            continue
        if not include_archived and session.get("status") != "active":
            continue
        sessions.append(_session_summary(session))
    sessions.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return {"sessions": sessions, "total": len(sessions)}


def create_stylist_session(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    now = _now_iso()
    session = {
        "session_id": _safe_session_id(payload.get("session_id")),
        "title": str(payload.get("title") or DEFAULT_SESSION_TITLE).strip()[:40] or DEFAULT_SESSION_TITLE,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "last_message_preview": "",
        "message_count": 0,
        "messages": [],
        "metadata": {
            "source": "asis_inspiration",
            **(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
        },
    }
    return _write_session(session)


def ensure_stylist_session(session_id: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    safe_id = _safe_session_id(session_id or "")
    existing = _read_session(_session_path(safe_id))
    if existing:
        return existing
    payload = payload if isinstance(payload, dict) else {}
    payload = {**payload, "session_id": safe_id}
    return create_stylist_session(payload)


def get_stylist_session(session_id: str) -> dict[str, Any]:
    session = _read_session(_session_path(session_id))
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


def update_stylist_session(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session = get_stylist_session(session_id)
    if "title" in payload:
        title = str(payload.get("title") or "").strip()[:40]
        if title:
            session["title"] = title
    if payload.get("status") in {"active", "archived"}:
        session["status"] = payload["status"]
    if isinstance(payload.get("metadata"), dict):
        session["metadata"] = {**(session.get("metadata") or {}), **payload["metadata"]}
    session["updated_at"] = _now_iso()
    return _write_session(session)


def delete_stylist_session(session_id: str) -> dict[str, Any]:
    return update_stylist_session(session_id, {"status": "archived"})


def append_stylist_message(session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    session = ensure_stylist_session(session_id)
    now = _now_iso()
    messages = session.setdefault("messages", [])
    message = {
        "id": secrets.token_urlsafe(10),
        "role": role if role in {"user", "assistant", "system"} else "assistant",
        "content": str(content or "").strip(),
        "created_at": now,
        "metadata": metadata if isinstance(metadata, dict) else {},
    }
    messages.append(message)
    if session.get("title") == DEFAULT_SESSION_TITLE and message["role"] == "user":
        session["title"] = _title_from_message(message["content"])
    session["updated_at"] = now
    return _write_session(session)


def recent_conversation(session_id: str, limit: int = 8) -> list[dict[str, str]]:
    try:
        session = get_stylist_session(session_id)
    except HTTPException:
        return []
    conversation = []
    for message in session.get("messages", [])[-limit:]:
        role = message.get("role")
        content = str(message.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            conversation.append({"role": role, "content": content})
    return conversation
