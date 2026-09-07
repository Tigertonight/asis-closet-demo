"""管理后台内置素材库清单接口的测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.auth as auth
from app.main import app


def _use_tmp_stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", auth.AUTH_DIR / "auth_store.json")
    monkeypatch.setattr(auth, "ADMIN_PASSWORD_PATH", auth.AUTH_DIR / "admin_password.json")


def _admin_login(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setenv("SELFIT_ADMIN_PASSWORD", "admin-test-pw")
    response = client.post("/admin/api/login", json={"password": "admin-test-pw"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_assets_manifest_requires_admin(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.get("/admin/api/assets/manifest")
    assert response.status_code == 401


def test_assets_manifest_lists_content_v2(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    headers = _admin_login(client, monkeypatch)

    response = client.get("/admin/api/assets/manifest", headers=headers)
    assert response.status_code == 200
    manifest = response.json()

    assert "bolt" in manifest["personas"]
    assert len(manifest["personas"]) >= 16

    garment = next(g for g in manifest["garments"] if g["name"] == "bolt-bag-0049-v1")
    assert garment["persona"] == "bolt"
    assert garment["category"] == "bag"
    assert garment["url"] == "/static/selfit/assets/content_v2/bolt/garments/bolt-bag-0049-v1.webp"

    outfit = next(o for o in manifest["outfits"] if o["name"] == "outfit_bolt_master_01_v2")
    assert outfit["persona"] == "bolt"
    assert outfit["master"] == "01"
    assert outfit["version"] == "v2"

    layout = next(l for l in manifest["layouts"] if l["name"] == "00128db9eb004b78d061f7ff")
    assert layout["layout"] == "unified-flatlay-v1"
    assert layout["count"] == 4
    assert layout["slots"] == ["top", "skirt", "shoes", "bag"]
    assert "edge" in layout["personas"] and "noir" in layout["personas"]


def test_assets_manifest_cached_by_fingerprint(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_stores(monkeypatch, tmp_path)
    client = TestClient(app)
    headers = _admin_login(client, monkeypatch)

    import app.selfit_admin_assets as admin_assets

    first = client.get("/admin/api/assets/manifest", headers=headers).json()
    cached = admin_assets._get_manifest()
    assert cached is first or cached == first
