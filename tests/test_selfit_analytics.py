"""埋点上报与管理后台聚合 API 的测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.auth as auth
import app.selfit_analytics as analytics
from app.main import app


def _use_tmp_stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", auth.AUTH_DIR / "auth_store.json")
    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", auth.AUTH_DIR / "admin_password.json")
    monkeypatch.setattr(analytics, "ANALYTICS_DIR", tmp_path / "outputs" / "analytics")
    monkeypatch.setattr(analytics, "EVENTS_PATH", analytics.ANALYTICS_DIR / "events.jsonl")


def _admin_login(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setenv("SELFIT_ADMIN_PASSWORD", "admin-test-pw")
    response = client.post("/admin/api/login", json={"password": "admin-test-pw"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_events_report_appends_whitelisted_events(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/v1/selfit/events",
        json={
            "events": [
                {"event": "screen_view", "screen": "suit", "sessionId": "ses_x", "userId": "u_1", "props": {"from": "intro"}},
                {"event": "not_a_real_event"},
                {"event": "login_success", "props": {"provider": "phone"}},
                {"event": "image_load_failed", "props": {"path": "/static/selfit/example.webp", "attempt": 1}},
                {"event": "image_load_recovered", "props": {"path": "/static/selfit/example.webp", "attempts": 1}},
                {"event": "report_resources_ready", "props": {"failedCount": 0}},
            ]
        },
    )

    assert response.status_code == 204
    lines = analytics.EVENTS_PATH.read_text(encoding="utf-8").strip().split("\n")
    records = [json.loads(line) for line in lines]
    # 白名单外的事件被丢弃
    assert [record["event"] for record in records] == [
        "screen_view",
        "login_success",
        "image_load_failed",
        "image_load_recovered",
        "report_resources_ready",
    ]
    assert records[0]["screen"] == "suit"
    assert records[0]["session_id"] == "ses_x"
    assert records[0]["client_ip"] == "testclient"
    assert "ts" in records[0]


def test_events_report_rejects_oversized_batch(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/v1/selfit/events",
        json={"events": [{"event": "screen_view"}] * 51},
    )

    assert response.status_code == 422


def test_admin_api_requires_invite_admin(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "ADMIN-TEST")
    client = TestClient(app)

    anonymous = client.get("/admin/api/analytics/summary")
    phone_user = client.post("/auth/phone/direct", json={"phone": "13800000001"})
    phone_headers = {"Authorization": f"Bearer {phone_user.json()['access_token']}"}
    as_phone_user = client.get("/admin/api/analytics/summary", headers=phone_headers)
    admin_headers = _admin_login(client, monkeypatch)
    as_admin = client.get("/admin/api/analytics/summary", headers=admin_headers)

    # 匿名与手机号登录用户都拿不到管理数据
    assert anonymous.status_code == 401
    assert as_phone_user.status_code == 403
    assert as_admin.status_code == 200
    assert as_admin.json()["totals"]["events"] == 0


def test_admin_summary_aggregates_funnel_and_users(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "ADMIN-TEST")
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    # 两个用户各走一程
    events = []
    for session_id, user_id, screens in (
        ("ses_a", "u_a", ["splash", "login", "phone-login", "intro", "suit", "like", "vibe", "loading", "report"]),
        ("ses_b", "u_b", ["splash", "login", "phone-login"]),
    ):
        for screen in screens:
            events.append({"event": "screen_view", "screen": screen, "sessionId": session_id, "userId": user_id})
    events.append({"event": "login_success", "sessionId": "ses_a", "userId": "u_a"})
    events.append({"event": "report_completed", "sessionId": "ses_a", "userId": "u_a"})
    events.append({"event": "mirror_capture_started", "props": {}})
    events.append({"event": "mirror_qr_claim_detected", "props": {}})
    response = client.post("/api/v1/selfit/events", json={"events": events})
    assert response.status_code == 204

    summary = client.get("/admin/api/analytics/summary", headers=admin_headers).json()

    assert summary["totals"]["events"] == len(events)
    assert summary["totals"]["sessions"] == 2
    assert summary["totals"]["users"] == 2
    assert summary["totals"]["reportsCompleted"] == 1
    assert summary["totals"]["mirrorCaptures"] == 1
    funnel = {row["screen"]: row["views"] for row in summary["appFunnel"]}
    assert funnel["splash"] == 2
    assert funnel["report"] == 1
    user_rows = {row["user_id"]: row for row in summary["users"]}
    assert user_rows["u_a"]["events"] == 11


def test_admin_users_endpoint_joins_phone(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_INVITE_CODES", "ADMIN-TEST")
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    client.post("/auth/phone/direct", json={"phone": "13800000002"})
    users = client.get("/admin/api/analytics/users", headers=admin_headers).json()["users"]

    phone_rows = [user for user in users if user.get("phone_e164") == "+8613800000002"]
    assert len(phone_rows) == 1
    assert phone_rows[0]["auth_provider"] == "phone_direct"


def test_admin_page_is_served(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.get("/admin")

    assert response.status_code == 200
    assert "管理后台" in response.text
    # 调试工具 tab 收纳内部页面入口
    assert "调试工具" in response.text
    assert "/report-builder" in response.text
    assert "/try-on/demo" in response.text
