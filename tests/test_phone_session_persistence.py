"""手机号登录 30 天保持 + 设备静默续登的测试。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.auth as auth
from app.main import app


def _use_tmp_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", auth.AUTH_DIR / "auth_store.json")
    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", auth.AUTH_DIR / "admin_password.json")


def test_phone_direct_session_is_30_day_sliding(monkeypatch, tmp_path: Path) -> None:
    """手机号登录：30 天 TTL + 滑动续期（与其他正式登录一致）。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    login = client.post("/auth/phone/direct", json={"phone": "13800007777", "device_id": "device-phone-keep-01"}).json()
    assert login["expires_in_seconds"] == 30 * 24 * 3600

    store = json.loads(auth.AUTH_STORE_PATH.read_text(encoding="utf-8"))
    session = next(item for item in store["auth_sessions"] if item["token_hash"])
    assert session["ttl_hours"] == 30 * 24
    assert session["sliding"] is True
    assert session["auth_provider"] == "phone_direct"

    # 滑动续期：过期时间改到 8 天后（< 一半 TTL），任意鉴权请求触发顺延
    session["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()
    auth.AUTH_STORE_PATH.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"})
    assert me.status_code == 200

    renewed = json.loads(auth.AUTH_STORE_PATH.read_text(encoding="utf-8"))
    renewed_session = next(item for item in renewed["auth_sessions"] if item["token_hash"] == session["token_hash"])
    assert renewed_session["expires_at"] > session["expires_at"]


def test_phone_resume_via_device_binding(monkeypatch, tmp_path: Path) -> None:
    """token 过期后凭设备绑定静默续登同一手机号账号。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    login = client.post("/auth/phone/direct", json={"phone": "13800008888", "device_id": "device-resume-01"}).json()
    user_id = login["user"]["user_id"]

    # token 失效（模拟 30 天后回来）
    store = json.loads(auth.AUTH_STORE_PATH.read_text(encoding="utf-8"))
    for session in store["auth_sessions"]:
        if session["token_hash"]:
            session["expires_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    auth.AUTH_STORE_PATH.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"})
    assert me.status_code == 401

    # 凭设备静默续登：换到新 token，同账号
    resume = client.post("/auth/phone/resume", json={"device_id": "device-resume-01"})
    assert resume.status_code == 200
    payload = resume.json()
    assert payload["user"]["user_id"] == user_id
    assert payload["user"]["phone_e164"] == "+8613800008888"
    assert payload["expires_in_seconds"] == 30 * 24 * 3600

    # 新 token 可用
    me2 = client.get("/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert me2.status_code == 200

    # 未绑定设备 → 404
    unknown = client.post("/auth/phone/resume", json={"device_id": "device-never-bound-9999"})
    assert unknown.status_code == 404


def test_guest_session_stays_24h(monkeypatch, tmp_path: Path) -> None:
    """游客会话保持 24 小时短时效（无交互身份，不享受 30 天）。"""
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    guest = client.post("/auth/guest").json()
    assert guest["expires_in_seconds"] == 24 * 3600

    store = json.loads(auth.AUTH_STORE_PATH.read_text(encoding="utf-8"))
    session = next(item for item in store["auth_sessions"] if item["token_hash"])
    assert session["sliding"] is False
    assert session["ttl_hours"] == 24
