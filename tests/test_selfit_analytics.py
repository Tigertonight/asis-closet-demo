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

    # 两个用户各走一程（主流程实际顺序：login → intro → like → suit → vibe）
    events = []
    for session_id, user_id, screens in (
        ("ses_a", "u_a", ["login", "intro", "like", "suit", "vibe", "loading", "report"]),
        ("ses_b", "u_b", ["login", "intro", "like"]),
        # u_a 重复登录：登录 KPI 按去重用户，不应把她算成 2 人
        ("ses_c", "u_a", ["login"]),
    ):
        for screen in screens:
            events.append({"event": "screen_view", "screen": screen, "sessionId": session_id, "userId": user_id})
    events.append({"event": "login_success", "sessionId": "ses_a", "userId": "u_a"})
    events.append({"event": "login_success", "sessionId": "ses_c", "userId": "u_a"})
    events.append({"event": "login_success", "sessionId": "ses_b", "userId": "u_b"})
    events.append({"event": "report_completed", "sessionId": "ses_a", "userId": "u_a"})
    # 镜子端：同一台镜子（同 IP）拍照两次——按次数统计应为 2，不是 1
    events.append({"event": "mirror_capture_started", "props": {}})
    events.append({"event": "mirror_capture_confirmed", "props": {}})
    events.append({"event": "mirror_capture_confirmed", "props": {}})
    events.append({"event": "mirror_qr_claim_detected", "props": {}})
    response = client.post("/api/v1/selfit/events", json={"events": events})
    assert response.status_code == 204

    summary = client.get("/admin/api/analytics/summary", headers=admin_headers).json()

    assert summary["totals"]["events"] == len(events)
    assert summary["totals"]["sessions"] == 3
    assert summary["totals"]["users"] == 2
    # 登录 KPI 按去重用户：u_a 两次登录只算 1
    assert summary["totals"]["logins"] == 2
    assert summary["totals"]["reportsCompleted"] == 1
    # 镜子 KPI 按次数：确认照片 2 张（started 试拍不计）
    assert summary["totals"]["mirrorCaptures"] == 2
    assert summary["totals"]["mirrorClaims"] == 1
    # 漏斗按去重人数：u_a 到过 report，u_b 只到 like
    funnel = {row["screen"]: row for row in summary["appFunnel"]}
    assert funnel["report"]["reach"] == 1
    assert funnel["like"]["reach"] == 2
    assert funnel["like"]["views"] == 2
    # 漏斗顺序 = 实际问卷顺序 like → suit → vibe
    screens = [row["screen"] for row in summary["appFunnel"]]
    assert screens.index("like") < screens.index("suit") < screens.index("vibe")
    assert "splash" not in screens and "phone-login" not in screens
    # 镜子漏斗按次数
    mirror = {row["event"]: row["count"] for row in summary["mirrorFunnel"]}
    assert mirror["mirror_capture_confirmed"] == 2
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
    # 导航整理：AI agent / 智能评测；MVP 状态入口已移除
    assert "AI agent" in response.text
    assert "智能评测" in response.text
    assert 'href="/mvp"' not in response.text
    # 调试工具 tab 只保留三个入口；十六型人格在当前页打开
    assert "调试工具" in response.text
    assert "/report-builder" in response.text
    assert "十二季型色彩诊断" in response.text
    assert 'data-tab="personas"' in response.text
    assert "/try-on/demo" not in response.text
    assert "/closet/demo" not in response.text
    # 用户报告两个列表的统计条（数量 + 占比）
    assert 'id="submissionsStats"' in response.text
    assert 'id="capturesStats"' in response.text
    assert "报告已生成" in response.text
    assert "报告未生成" in response.text


def _use_tmp_stylist_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import app.stylist_context as stylist_context

    monkeypatch.setattr(
        stylist_context, "STYLIST_CONTEXT_CONFIG_PATH", tmp_path / "stylist_context_config.json"
    )


def test_admin_stylist_context_crud(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    _use_tmp_stylist_context(monkeypatch, tmp_path)
    monkeypatch.setenv("SELFIT_STYLIST_CONTEXT_EDITABLE", "1")
    client = TestClient(app)

    # 未登录不可见（登录前先验证，TestClient 登录后会带 admin cookie）
    assert client.get("/admin/api/stylist-context").status_code == 401

    admin_headers = _admin_login(client, monkeypatch)

    # 初始：默认 prompt + 空列表
    initial = client.get("/admin/api/stylist-context", headers=admin_headers).json()
    assert initial["users"] == []
    assert "画像" in initial["prompt"]

    # 更新 prompt
    updated = client.put(
        "/admin/api/stylist-context/prompt",
        headers=admin_headers,
        json={"prompt": "测试指引 v2"},
    )
    assert updated.status_code == 200
    assert client.get("/admin/api/stylist-context", headers=admin_headers).json()["prompt"] == "测试指引 v2"
    assert client.put(
        "/admin/api/stylist-context/prompt", headers=admin_headers, json={"prompt": " "}
    ).status_code == 400

    # 新增用户画像
    created = client.post(
        "/admin/api/stylist-context/users",
        headers=admin_headers,
        json={"phone": "13800001111", "xhs_uid": "uid-a", "nickname": "小画像", "doc": "她喜欢洛丽塔。"},
    )
    assert created.status_code == 200
    entry_id = created.json()["entry"]["entry_id"]

    # 手机号非法 / 文档为空被拒
    assert client.post(
        "/admin/api/stylist-context/users",
        headers=admin_headers,
        json={"phone": "123", "doc": "x"},
    ).status_code == 400
    assert client.post(
        "/admin/api/stylist-context/users",
        headers=admin_headers,
        json={"phone": "13800002222"},
    ).status_code == 400

    # 同 uid 再次提交走更新（幂等）
    again = client.post(
        "/admin/api/stylist-context/users",
        headers=admin_headers,
        json={"xhs_uid": "uid-a", "doc": "更新后的画像。"},
    )
    assert again.status_code == 200
    assert again.json()["entry"]["entry_id"] == entry_id

    listing = client.get("/admin/api/stylist-context", headers=admin_headers).json()
    assert len(listing["users"]) == 1
    assert listing["users"][0]["doc"] == "更新后的画像。"

    # 删除
    assert client.delete(f"/admin/api/stylist-context/users/{entry_id}", headers=admin_headers).status_code == 200
    assert client.get("/admin/api/stylist-context", headers=admin_headers).json()["users"] == []
    assert client.delete(f"/admin/api/stylist-context/users/{entry_id}", headers=admin_headers).status_code == 404


def test_admin_stylist_context_locked_by_default(monkeypatch, tmp_path: Path) -> None:
    """画像内容默认锁定：API 不返回画像全文，写操作 403，索引信息保留。"""

    _use_tmp_stores(monkeypatch, tmp_path)
    _use_tmp_stylist_context(monkeypatch, tmp_path)
    monkeypatch.delenv("SELFIT_STYLIST_CONTEXT_EDITABLE", raising=False)
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    import app.stylist_context as stylist_context

    stylist_context.upsert_stylist_context_user(
        {"phone": "13800003333", "xhs_uid": "uid-locked", "nickname": "隐私画像", "doc": "这是一份隐私画像。"}
    )

    listing = client.get("/admin/api/stylist-context", headers=admin_headers)
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["editable"] is False
    assert len(payload["users"]) == 1
    row = payload["users"][0]
    # 索引信息保留，画像全文不出现
    assert row["phone"] == "13800003333"
    assert row["xhs_uid"] == "uid-locked"
    assert row["nickname"] == "隐私画像"
    assert row["doc_chars"] == len("这是一份隐私画像。")
    assert "doc" not in row
    assert "这是一份隐私画像" not in listing.text

    # 写操作全部 403
    assert client.post(
        "/admin/api/stylist-context/users",
        headers=admin_headers,
        json={"phone": "13800004444", "doc": "新画像"},
    ).status_code == 403
    assert client.put(
        f"/admin/api/stylist-context/users/{row['entry_id']}",
        headers=admin_headers,
        json={"doc": "改画像"},
    ).status_code == 403
    assert client.delete(
        f"/admin/api/stylist-context/users/{row['entry_id']}", headers=admin_headers
    ).status_code == 403

    # prompt 编辑不受锁影响
    assert client.put(
        "/admin/api/stylist-context/prompt",
        headers=admin_headers,
        json={"prompt": "锁定状态下仍可改 prompt"},
    ).status_code == 200


def test_stylist_context_matches_phone_hash_user_id(monkeypatch, tmp_path: Path) -> None:
    import app.stylist_context as stylist_context

    _use_tmp_stylist_context(monkeypatch, tmp_path)

    stylist_context.upsert_stylist_context_user(
        {"phone": "13821028659", "xhs_uid": "6346eddc", "nickname": "叶瑄", "doc": "画像文本"}
    )
    user_id = stylist_context.user_id_from_phone("13821028659")
    assert user_id and user_id.startswith("u_")

    matched = stylist_context.find_stylist_user_doc(user_id)
    assert matched is not None
    assert matched["nickname"] == "叶瑄"
    assert matched["doc"] == "画像文本"

    assert stylist_context.find_stylist_user_doc("u_somebody_else") is None
    assert stylist_context.find_stylist_user_doc("local_user") is None
