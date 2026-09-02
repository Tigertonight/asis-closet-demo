"""内部页面网关测试：线上（demo）模式只对用户开放主流程页面。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.auth as auth
from app.main import app


@pytest.fixture
def demo_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("SELFIT_ENV", "demo")
    monkeypatch.setenv("SELFIT_ADMIN_PASSWORD", "gate-test-pw")
    monkeypatch.setenv("SELFIT_AUTH_SECRET", "gate-test-secret")
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "auth" / "auth_store.json")
    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", tmp_path / "auth" / "admin_password.json")
    return TestClient(app)


def test_internal_pages_redirect_anonymous_to_admin(demo_client: TestClient) -> None:
    """未登录访问任何内部调试页 → 307 /admin?next=原路径。"""

    for path in (
        "/demo",
        "/closet/demo",
        "/try-on/demo",
        "/mvp",
        "/qa",
        "/self-test",
        "/report-builder",
        "/fixtures",
    ):
        response = demo_client.get(path, follow_redirects=False)
        assert response.status_code == 307, path
        location = response.headers["location"]
        assert location.startswith("/admin?next="), (path, location)
        assert path.replace("/", "%2F") in location or path in location, (path, location)


def test_wearwow_gate_redirects_to_login_flow(demo_client: TestClient) -> None:
    """WearWow 是面向用户的内测 app：未登录访问引导回主流程登录页，而非后台密码页。"""

    response = demo_client.get("/wearwow/demo", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/selfit?entry=login"


def test_user_flow_pages_stay_public(demo_client: TestClient) -> None:
    """用户主流程页面不受网关影响。"""

    for path in ("/selfit", "/selfit/mirror"):
        response = demo_client.get(path, follow_redirects=False)
        assert response.status_code == 200, path


def test_admin_login_then_internal_page_accessible(demo_client: TestClient) -> None:
    """管理员登录后（cookie）可访问内部页。"""

    login = demo_client.post("/admin/api/login", json={"password": "gate-test-pw"})
    assert login.status_code == 200

    for path in ("/demo", "/report-builder"):
        response = demo_client.get(path, follow_redirects=False)
        assert response.status_code == 200, (path, response.status_code)


def test_local_dev_mode_does_not_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """本地开发模式（SELFIT_ENV 缺省）不启用网关，方便日常调试。"""

    monkeypatch.delenv("SELFIT_ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("SELFIT_PUBLIC_DEMO", raising=False)
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "auth" / "auth_store.json")
    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", tmp_path / "auth" / "admin_password.json")
    client = TestClient(app)

    response = client.get("/demo", follow_redirects=False)

    assert response.status_code == 200
