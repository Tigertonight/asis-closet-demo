from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.auth as auth
import app.main as main_module
import app.storage as storage
from app.main import app


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def _synthetic_top_image(color: tuple[int, int, int] = (220, 60, 105)) -> Image.Image:
    image = Image.new("RGB", (720, 900), "#fffafa")
    pixels = image.load()
    for y in range(170, 770):
        width = 210 + int((y - 170) * 0.14)
        left = 360 - width // 2
        right = 360 + width // 2
        for x in range(max(0, left), min(720, right)):
            pixels[x, y] = color
    return image


def _use_tmp_runtime(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path / "outputs" / "auth")
    monkeypatch.setattr(auth, "AUTH_STORE_PATH", tmp_path / "outputs" / "auth" / "auth_store.json")


def _login(client: TestClient, phone: str) -> dict[str, str]:
    start = client.post("/auth/phone/start", json={"phone": phone}).json()
    verified = client.post("/auth/phone/verify", json={"phone": phone, "code": start["dev_code"]}).json()
    return {"Authorization": f"Bearer {verified['access_token']}"}


def test_phone_login_creates_and_reuses_user(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    first = client.post("/auth/phone/start", json={"phone": "13800000001"}).json()
    verified = client.post("/auth/phone/verify", json={"phone": "13800000001", "code": first["dev_code"]}).json()
    second = client.post("/auth/phone/start", json={"phone": "13800000001"}).json()
    verified_again = client.post("/auth/phone/verify", json={"phone": "13800000001", "code": second["dev_code"]}).json()

    assert verified["status"] == "ok"
    assert verified["user"]["phone_e164"] == "+8613800000001"
    assert verified_again["user"]["user_id"] == verified["user"]["user_id"]
    assert "dev_code" not in auth.AUTH_STORE_PATH.read_text(encoding="utf-8")


def test_phone_code_rejects_wrong_and_reused_code(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)

    start = client.post("/auth/phone/start", json={"phone": "13800000002"}).json()
    wrong = client.post("/auth/phone/verify", json={"phone": "13800000002", "code": "000000"})
    ok = client.post("/auth/phone/verify", json={"phone": "13800000002", "code": start["dev_code"]})
    reused = client.post("/auth/phone/verify", json={"phone": "13800000002", "code": start["dev_code"]})

    assert wrong.status_code == 400
    assert ok.status_code == 200
    assert reused.status_code == 400


def test_public_demo_does_not_return_dev_code(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("ASIS_ENV", "demo")
    monkeypatch.setenv("ASIS_AUTH_SECRET", "test-public-secret-that-is-not-default")
    monkeypatch.delenv("ASIS_AUTH_RETURN_DEV_CODE", raising=False)
    client = TestClient(app)

    start = client.post("/auth/phone/start", json={"phone": "13800000021"}).json()

    assert start["status"] == "sent"
    assert "dev_code" not in start


def test_public_demo_rejects_default_auth_secret(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("ASIS_ENV", "demo")
    monkeypatch.delenv("ASIS_AUTH_SECRET", raising=False)
    client = TestClient(app)

    response = client.post("/auth/phone/start", json={"phone": "13800000022"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "request.failed"


def test_auth_rate_limit_is_enforced(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("ASIS_DISABLE_RATE_LIMIT", "0")
    monkeypatch.setenv("ASIS_AUTH_RATE_LIMIT", "1")
    monkeypatch.setenv("ASIS_AUTH_RATE_WINDOW_SECONDS", "3600")
    client = TestClient(app)
    headers = {"x-forwarded-for": "203.0.113.77"}

    first = client.post("/auth/phone/start", json={"phone": "13800000023"}, headers=headers)
    second = client.post("/auth/phone/start", json={"phone": "13800000024"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "request.rate_limited"


def test_xhs_image_proxy_uses_disk_cache(monkeypatch, tmp_path: Path) -> None:
    cache_dir = tmp_path / "xhs_images"
    cache_dir.mkdir(parents=True)
    monkeypatch.setattr(main_module, "XHS_IMAGE_CACHE_DIR", cache_dir)
    source_url = "https://sns-webpic-qc.xhscdn.com/path/to/cover!nc_n_webp_mw_1"
    image_bytes = _png_bytes(Image.new("RGB", (12, 12), "#ff4f86"))

    written = main_module._write_xhs_image_cache(source_url, image_bytes, "image/png")
    cached = main_module._cached_xhs_image_response(source_url)

    assert written.status_code == 200
    assert cached is not None
    assert cached.status_code == 200
    assert any(path.suffix == ".png" for path in cache_dir.iterdir())
    assert any(path.suffix == ".json" for path in cache_dir.iterdir())


def test_closet_requires_login_and_isolates_user_data(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    user_a = _login(client, "13800000003")
    user_b = _login(client, "13800000004")

    anonymous = client.get("/closet/items")
    created = client.post(
        "/closet/import/upload",
        headers=user_a,
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image()), "image/png"))],
    ).json()["items"][0]
    a_items = client.get("/closet/items", headers=user_a).json()
    b_items = client.get("/closet/items", headers=user_b).json()
    b_detail = client.get(f"/closet/items/{created['item_id']}", headers=user_b)

    assert anonymous.status_code == 401
    assert a_items["total"] == 1
    assert b_items["total"] == 0
    assert b_detail.status_code == 404
    assert created["user_id"] != "local_user"
    assert (tmp_path / "outputs" / "users" / created["user_id"] / "closet" / "closet_manifest.json").exists()


def test_user_assets_are_read_under_current_user_only(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_runtime(monkeypatch, tmp_path)
    client = TestClient(app)
    user_a = _login(client, "13800000005")
    user_b = _login(client, "13800000006")

    created = client.post(
        "/closet/import/upload",
        headers=user_a,
        files=[("images", ("top.png", _png_bytes(_synthetic_top_image((60, 120, 220))), "image/png"))],
    ).json()["items"][0]
    asset_path = created["assets"]["preview_path"]

    assert client.get(asset_path, headers=user_a).status_code == 200
    assert client.get(asset_path, headers=user_b).status_code == 404
