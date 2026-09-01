"""内测白名单：管理后台配置手机号，白名单用户可走 onboarding 之外的后续功能。

覆盖三层 gating：
1. 登录响应 / /auth/me 携带 beta_access（前端据此展示后续功能入口）；
2. 后续功能 API（/closet、/try-on、/stylist）线上只放白名单和内部账号；
3. 内部页面网关（/closet/demo 等页面）对白名单用户的登录 cookie 放行。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app.auth as auth
import app.beta_access as beta_access
import app.storage as storage
from app.main import app


def _use_tmp_runtime(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "outputs" / "auth" / "auth_store.json")
    monkeypatch.setattr(
        auth, "ADMIN_PASSWORD_PATH", tmp_path / "outputs" / "auth" / "admin_password.json"
    )
    monkeypatch.setattr(
        beta_access, "BETA_ALLOWLIST_PATH", tmp_path / "outputs" / "auth" / "beta_allowlist.json"
    )


def _demo_env(monkeypatch) -> None:
    monkeypatch.setenv("SELFIT_ENV", "demo")
    monkeypatch.setenv("SELFIT_AUTH_SECRET", "beta-test-secret")
    monkeypatch.setenv("SELFIT_ADMIN_PASSWORD", "beta-test-admin-pw")


def _local_env(monkeypatch) -> None:
    monkeypatch.delenv("SELFIT_ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("SELFIT_PUBLIC_DEMO", raising=False)
    monkeypatch.setenv("SELFIT_AUTH_SECRET", "beta-test-secret")


def _login_direct(client: TestClient, phone: str) -> dict[str, str]:
    response = client.post("/auth/phone/direct", json={"phone": phone})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_beta_allowlist_crud(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)

    entry = beta_access.add_beta_user("13800000001", "种子用户")
    assert entry["phone_e164"] == "+8613800000001"
    assert entry["note"] == "种子用户"

    # 重复添加同一手机号：不新建，只更新备注
    beta_access.add_beta_user("+8613800000001", "改备注")
    users = beta_access.list_beta_users()
    assert [item["phone_e164"] for item in users] == ["+8613800000001"]
    assert users[0]["note"] == "改备注"

    assert beta_access.is_beta_phone("+8613800000001") is True
    assert beta_access.is_beta_phone("+8613800000002") is False
    assert beta_access.is_beta_phone(None) is False

    assert beta_access.remove_beta_user("+8613800000001") is True
    assert beta_access.remove_beta_user("+8613800000001") is False
    assert beta_access.list_beta_users() == []


def test_add_beta_user_rejects_invalid_phone(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)

    try:
        beta_access.add_beta_user("12345", "")
    except Exception as exc:  # HTTPException
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("无效手机号应被拒绝")


def test_admin_beta_users_api_crud(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    _demo_env(monkeypatch)
    client = TestClient(app)

    # 未登录不可管理
    assert client.get("/admin/api/beta-users").status_code == 401

    login = client.post("/admin/api/login", json={"password": "beta-test-admin-pw"})
    assert login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    created = client.post(
        "/admin/api/beta-users",
        json={"phone": "13800000001", "note": "内测第一批"},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["betaUser"]["phone"] == "+8613800000001"

    listed = client.get("/admin/api/beta-users", headers=admin_headers)
    assert listed.status_code == 200
    assert [item["phone"] for item in listed.json()["betaUsers"]] == ["+8613800000001"]

    removed = client.delete(
        f"/admin/api/beta-users/{listed.json()['betaUsers'][0]['phone']}", headers=admin_headers
    )
    assert removed.status_code == 200
    assert client.get("/admin/api/beta-users", headers=admin_headers).json()["betaUsers"] == []

    missing = client.delete("/admin/api/beta-users/+8613800000001", headers=admin_headers)
    assert missing.status_code == 404


def test_admin_beta_users_api_rejects_normal_user(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    _demo_env(monkeypatch)
    client = TestClient(app)

    headers = _login_direct(client, "13800000002")
    response = client.get("/admin/api/beta-users", headers=headers)
    assert response.status_code == 403


def test_login_reports_beta_access(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    _demo_env(monkeypatch)
    beta_access.add_beta_user("13800000001", "白名单")
    client = TestClient(app)

    whitelisted = _login_direct(client, "13800000001")
    me = client.get("/auth/me", headers=whitelisted).json()
    assert me["user"]["beta_access"] is True

    outsider = _login_direct(client, "13800000099")
    me = client.get("/auth/me", headers=outsider).json()
    assert me["user"]["beta_access"] is False


def test_beta_gated_api_blocks_outsider_in_demo(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    _demo_env(monkeypatch)
    beta_access.add_beta_user("13800000001", "白名单")
    client = TestClient(app)

    # 匿名 → 401；非白名单登录 → 403（正在内测）
    assert client.get("/closet/items").status_code == 401
    outsider = _login_direct(client, "13800000099")
    blocked = client.get("/closet/items", headers=outsider)
    assert blocked.status_code == 403
    assert "内测" in blocked.json()["detail"]

    # 白名单用户放行
    whitelisted = _login_direct(client, "13800000001")
    ok = client.get("/closet/items", headers=whitelisted)
    assert ok.status_code == 200

    # 管理员账号放行（方便内部验证）
    admin = client.post("/admin/api/login", json={"password": "beta-test-admin-pw"}).json()
    ok_admin = client.get(
        "/closet/items", headers={"Authorization": f"Bearer {admin['access_token']}"}
    )
    assert ok_admin.status_code == 200


def test_beta_gating_covers_followup_apis(monkeypatch, tmp_path: Path) -> None:
    """onboarding 之外的后续功能 API 都挂内测门禁；onboarding 主链路不受影响。"""

    _use_tmp_runtime(monkeypatch, tmp_path)
    _demo_env(monkeypatch)
    client = TestClient(app)
    outsider = _login_direct(client, "13800000099")

    followup_paths = [
        "/closet/items",
        "/closet/preferences",
        "/closet/outfits",
        "/closet/capabilities",
        "/closet/import/jobs/job-not-exist",
        "/stylist/capabilities",
        "/stylist/sessions",
        "/stylist/memory",
        "/try-on/capabilities",
        "/try-on/codex-bridge/jobs",
        "/selfit/try-on/jobs/job-not-exist",
    ]
    for path in followup_paths:
        assert client.get(path, headers=outsider).status_code == 403, path

    # WearWow app 的写端点同样挂门禁（GET 不适用的 POST 路径单独验证）
    for path in (
        "/closet/recommendations/outfits",
        "/closet/import/jobs/job-not-exist/retry",
        "/selfit/try-on/jobs/job-not-exist/retry",
    ):
        assert client.post(path, json={}, headers=outsider).status_code == 403, path

    # onboarding 主链路对普通用户保持开放（含报告摘要——非 beta 用户登录时也要判断是否有历史报告）
    latest = client.get("/reports/latest", headers=outsider)
    assert latest.status_code in {200, 404}, latest.text

    # onboarding 主链路对普通用户保持开放
    created = client.post(
        "/api/v1/selfit/sessions", json={"schemaVersion": "selfit-onboarding-v1"}, headers=outsider
    )
    assert created.status_code in {200, 201}, created.text


def test_local_mode_does_not_gate_logged_in_users(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    _local_env(monkeypatch)
    client = TestClient(app)

    headers = _login_direct(client, "13800000099")
    me = client.get("/auth/me", headers=headers).json()
    assert me["user"]["beta_access"] is True
    assert client.get("/closet/items", headers=headers).status_code == 200


def test_login_sets_user_cookie_and_internal_page_allows_beta_user(monkeypatch, tmp_path: Path) -> None:
    """登录下发用户 cookie；白名单用户凭 cookie 直接打开后续功能页面。"""

    _use_tmp_runtime(monkeypatch, tmp_path)
    _demo_env(monkeypatch)
    beta_access.add_beta_user("13800000001", "白名单")
    client = TestClient(app)

    # 匿名访问内部页面 → 307 到 /admin
    anonymous = client.get("/closet/demo", follow_redirects=False)
    assert anonymous.status_code == 307
    assert anonymous.headers["location"].startswith("/admin?next=")

    # 非白名单用户带 cookie → 仍 307
    outsider_response = client.post("/auth/phone/direct", json={"phone": "13800000099"})
    assert outsider_response.status_code == 200
    outsider_cookie = outsider_response.cookies.get(auth.USER_COOKIE_NAME)
    assert outsider_cookie
    client.cookies.set(auth.USER_COOKIE_NAME, outsider_cookie)
    still_blocked = client.get("/closet/demo", follow_redirects=False)
    assert still_blocked.status_code == 307

    # 白名单用户带 cookie → 放行页面（含 WearWow 新 app）
    beta_response = client.post("/auth/phone/direct", json={"phone": "13800000001"})
    beta_cookie = beta_response.cookies.get(auth.USER_COOKIE_NAME)
    assert beta_cookie
    client.cookies.set(auth.USER_COOKIE_NAME, beta_cookie)
    allowed = client.get("/closet/demo", follow_redirects=False)
    assert allowed.status_code == 200
    wearwow = client.get("/wearwow/demo", follow_redirects=False)
    assert wearwow.status_code == 200

    # 登出清除 cookie
    logout = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {beta_response.json()['access_token']}"},
    )
    assert logout.status_code == 200
    assert logout.headers.get("set-cookie", "").find(f"{auth.USER_COOKIE_NAME}=") != -1


def test_beta_entry_removed_revokes_access(monkeypatch, tmp_path: Path) -> None:
    """移出白名单后立即失去资格（资格实时计算，无缓存）。"""

    _use_tmp_runtime(monkeypatch, tmp_path)
    _demo_env(monkeypatch)
    beta_access.add_beta_user("13800000001", "白名单")
    client = TestClient(app)

    headers = _login_direct(client, "13800000001")
    assert client.get("/closet/items", headers=headers).status_code == 200

    beta_access.remove_beta_user("+8613800000001")
    assert client.get("/closet/items", headers=headers).status_code == 403
