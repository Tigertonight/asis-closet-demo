"""失败试穿列表（/admin/api/failed-tryons）的聚合与筛选测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.auth as auth
import app.selfit_admin_submissions as submissions
from app.main import app


def _use_tmp_stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", auth.AUTH_DIR / "auth_store.json")
    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", auth.AUTH_DIR / "admin_password.json")
    monkeypatch.setattr(submissions, "USERS_ROOT", tmp_path / "outputs" / "users")
    monkeypatch.setattr(submissions, "HIDDEN_STORE_PATH", tmp_path / "outputs" / "admin_hidden.json")


def _admin_login(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setenv("SELFIT_ADMIN_PASSWORD", "admin-test-pw")
    response = client.post("/admin/api/login", json={"password": "admin-test-pw"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _write_failed_job(tmp_path: Path, user_id: str, job_id: str, *, code: str = "person.multiple_faces", message: str = "", created: str = "2026-09-14T10:00:00Z") -> None:
    jobs_dir = tmp_path / "outputs" / "users" / user_id / "tryon" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    person_dir = tmp_path / "uploads" / "users" / user_id
    person_dir.mkdir(parents=True, exist_ok=True)
    person_file = person_dir / f"person_{job_id}.jpg"
    person_file.write_bytes(b"\xff\xd8fake")
    (jobs_dir / f"{job_id}.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "user_id": user_id,
                "status": "failed",
                "kind": "tryon",
                "outfit_id": "outfit_x",
                "person_path": str(person_file),
                "attempt": 2,
                "created_at": created,
                "updated_at": created,
                "result": {"decision": {"blocking_errors": [{"code": code, "message": message or "拦截", "suggestion": ""}]}},
                "error": {"message": message or "拦截", "retryable": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_failed_tryons_lists_and_filters_by_reason(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    # 两个用户三个失败任务 + 一个成功任务（不应出现）
    _write_failed_job(tmp_path, "u_aaa", "aaaaaaaaaaaaaaaaaa", code="person.multiple_faces", message="检测到多人脸", created="2026-09-14T10:00:00Z")
    _write_failed_job(tmp_path, "u_aaa", "bbbbbbbbbbbbbbbbbb", code="quality.face_changed", message="生成图中的面部与原照片差异较大", created="2026-09-14T11:00:00Z")
    _write_failed_job(tmp_path, "u_bbb", "cccccccccccccccccc", code="person.multiple_faces", message="检测到多人脸", created="2026-09-14T12:00:00Z")
    ok_dir = tmp_path / "outputs" / "users" / "u_aaa" / "tryon" / "jobs"
    (ok_dir / "dddddddddddddddddd.json").write_text(json.dumps({"job_id": "dddddddddddddddddd", "status": "completed"}))

    response = client.get("/admin/api/failed-tryons", headers=admin_headers)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["failed"]) == 3
    # 最新在前
    assert payload["failed"][0]["jobId"] == "cccccccccccccccccc"
    # 原因标签映射
    labels = {row["reasonLabel"] for row in payload["failed"]}
    assert labels == {"检测到多人脸", "面部与原照差异大"}
    # 手机号 join（u_aaa 注册过手机号）
    login = client.post("/auth/phone/direct", json={"phone": "13800001234"})
    # breakdown 按次数排序
    counts = {item["reason"]: item["count"] for item in payload["breakdown"]}
    assert counts == {"person.multiple_faces": 2, "quality.face_changed": 1}

    # 按原因筛选
    filtered = client.get("/admin/api/failed-tryons?reason=person.multiple_faces", headers=admin_headers).json()
    assert len(filtered["failed"]) == 2
    assert all(row["reasonCode"] == "person.multiple_faces" for row in filtered["failed"])
    # 筛选不影响 breakdown（全量口径）
    assert {item["reason"]: item["count"] for item in filtered["breakdown"]} == counts

    # 人物照可下载 + 路径限制
    person = client.get("/admin/api/failed-tryons/cccccccccccccccccc/person?user_id=u_bbb", headers=admin_headers)
    assert person.status_code == 200
    assert person.headers["content-type"].startswith("image/jpeg")
    # 缺 user_id / 不存在任务 / 路径越界
    assert client.get("/admin/api/failed-tryons/cccccccccccccccccc/person", headers=admin_headers).status_code == 422
    assert client.get("/admin/api/failed-tryons/eeeeeeeeeeeeeeeeee/person?user_id=u_bbb", headers=admin_headers).status_code == 404

    # 鉴权（独立 client，不带 admin cookie）
    anonymous = TestClient(app)
    assert anonymous.get("/admin/api/failed-tryons").status_code == 401
    stranger = anonymous.post("/auth/phone/direct", json={"phone": "13800005678"}).json()
    assert anonymous.get(
        "/admin/api/failed-tryons",
        headers={"Authorization": f"Bearer {stranger['access_token']}"},
    ).status_code == 403


def test_failed_tryons_falls_back_to_message_label(monkeypatch, tmp_path: Path) -> None:
    """无 blocking code 的老数据：按 error.message 关键词归类；都匹配不上归 request.failed。"""
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    admin_headers = _admin_login(client, monkeypatch)

    jobs_dir = tmp_path / "outputs" / "users" / "u_ccc" / "tryon" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    (jobs_dir / "ffffffffffffffffff.json").write_text(json.dumps({
        "job_id": "ffffffffffffffffff", "status": "failed", "kind": "tryon",
        "error": {"message": "未接入真实 AI 试穿模型", "retryable": True},
        "result": {}, "created_at": "2026-09-14T09:00:00Z",
    }))
    (jobs_dir / "111111111111111111.json").write_text(json.dumps({
        "job_id": "111111111111111111", "status": "failed", "kind": "inspiration",
        "note": {"id": "note:mute:outfits-01"},
        "error": {"message": "某个奇怪的新错误", "retryable": False},
        "result": {}, "created_at": "2026-09-14T09:30:00Z",
    }))

    payload = client.get("/admin/api/failed-tryons", headers=admin_headers).json()

    rows = {row["reasonCode"]: row for row in payload["failed"]}
    assert rows["image_edit.mock_provider"]["reasonLabel"] == "未接入真实生图模型"
    assert rows["request.failed"]["reasonLabel"] == "请求被拒绝"
    assert rows["request.failed"]["kind"] == "inspiration"
    assert rows["request.failed"]["target"] == "note:mute:outfits-01"
